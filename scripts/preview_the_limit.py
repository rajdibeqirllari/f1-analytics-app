"""Re-edit a verified cinematic render into THE LIMIT without a Blender rerun.

Explicit proof-tool inputs: original private render config and its completed
MP4. Cadence/frame count are checked before compositing; source clock is never
reconstructed from playback speed. Production jobs also support The Limit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image
import services.openf1_comparison as provider
from services.video_comparison import VideoSelection
from services.video_3d_overlay import font
from services.car_style import comparison_styles
from services.limit_overlay import LimitTelemetryOverlay
from services.limit_story import limit_timeline


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    config=json.loads(args.config.read_text())
    def cached(endpoint,params):
        key=hashlib.sha256(json.dumps([endpoint,params],sort_keys=True).encode()).hexdigest()
        return json.loads((provider.CACHE/(key+'.json')).read_text(encoding='utf8'))
    provider.historical=cached
    payload=config['comparison'];a,b=payload['laps']
    # Proof sample uses the confirmed historical Q selection. Assert exact
    # selected lap numbers/times, rather than silently substituting best laps.
    if payload['session']!='Qualifying':raise ValueError('This proof helper expects qualifying.')
    comparison=provider.comparison(VideoSelection(payload['year'],payload['event'],'Q',a['code'],b['code']))
    for actual,expected in zip(comparison.laps,payload['laps']):
        if actual.number!=expected['number'] or abs(actual.lap_time-expected['lap_time'])>1e-6:
            raise ValueError('Replay metadata does not match the selected cached laps.')
    base_timeline=config['timeline'];fps=config['fps'];size=tuple(config['size'])
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(args.video)]))
    stream=next(v for v in info['streams'] if v['codec_type']=='video')
    from fractions import Fraction
    if (stream['width'],stream['height'])!=size or Fraction(stream['avg_frame_rate'])!=fps or int(stream['nb_frames'])!=len(base_timeline['source_times']):
        raise ValueError('Replay dimensions, cadence or frames do not match its render config.')
    timeline=limit_timeline(base_timeline)
    path=dict(config['driving_path'],the_limit=True,timeline=timeline)
    overlay=LimitTelemetryOverlay(comparison,size,config['start'],config['end'],config['full'],path,
                                  [s['display'] for s in comparison_styles(comparison.laps)],font)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    pending=args.output.with_suffix('.partial.mp4')
    flags=dict(creationflags=subprocess.CREATE_NO_WINDOW) if hasattr(subprocess,'CREATE_NO_WINDOW') else {}
    decoder=encoder=None
    try:
        with tempfile.TemporaryFile() as errors:
            decoder=subprocess.Popen(['ffmpeg','-v','error','-i',str(args.video),'-f','rawvideo','-pix_fmt','rgb24','-vsync','0','pipe:1'],stdout=subprocess.PIPE,stderr=errors,**flags)
            encoder=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{size[0]}x{size[1]}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p','-fps_mode','passthrough','-movflags','+faststart',str(pending)],stdin=subprocess.PIPE,stderr=errors,**flags)
            nbytes=size[0]*size[1]*3
            first=None;intro=round(timeline['limit_intro_seconds']*fps)
            for number,elapsed in enumerate(base_timeline['source_times']):
                raw=decoder.stdout.read(nbytes)
                if len(raw)!=nbytes:raise RuntimeError('Existing replay ended before its source clock.')
                image=Image.frombytes('RGB',size,raw)
                if first is None:
                    first=image
                    for frame in range(intro):
                        result=overlay.from_replay(first,elapsed,frame/fps)
                        encoder.stdin.write(result.tobytes())
                        if frame==round(1.9*fps):result.save(args.output.with_suffix('.png'))
                result=overlay.from_replay(image,elapsed,(intro+number)/fps)
                encoder.stdin.write(result.tobytes())
                if number==len(base_timeline['source_times'])-1:result.save(args.output.with_name(args.output.stem+'-payoff.png'))
                if number%300==0:print(f'{number}/{len(base_timeline["source_times"])} replay frames',flush=True)
            encoder.stdin.close();encoder.wait();decoder.wait()
            if encoder.returncode or decoder.returncode:
                errors.seek(0);raise RuntimeError(errors.read().decode(errors='replace')[-2000:])
        pending.replace(args.output)
        report=dict(source_video=str(args.video.resolve()),source_config=str(args.config.resolve()),
                    reused_scene=True,fps=fps,frames=len(timeline['source_times']),seconds=timeline['output_seconds'],
                    laps=[dict(code=l.code,lap=l.number,time=l.lap_time) for l in comparison.laps],
                    beats=overlay.story.beats,height='Exaggerated matched-distance time advantage, not elevation')
        args.output.with_suffix('.json').write_text(json.dumps(report,indent=2))
        print(args.output,flush=True)
    finally:
        for process in (decoder,encoder):
            if process and process.poll() is None:process.kill();process.wait()
        pending.unlink(missing_ok=True)


if __name__=='__main__':main()
