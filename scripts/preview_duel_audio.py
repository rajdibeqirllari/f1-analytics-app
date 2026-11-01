"""Add The Duel to a verified local export; no Blender render or video encode."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from fractions import Fraction
from PIL import Image
import services.openf1_comparison as provider
from services.video_comparison import VideoSelection
from services.duel_audio import attach_duel
from services.limit_story import limit_timeline


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--the-limit',action='store_true')
    parser.add_argument('--volume',type=float,default=80)
    parser.add_argument('--soundtrack',choices=['The Duel','Grit & Drums'],default='The Duel')
    parser.add_argument('--already-credited',action='store_true')
    args=parser.parse_args();config=json.loads(args.config.read_text())
    def cached(endpoint,params):
        key=hashlib.sha256(json.dumps([endpoint,params],sort_keys=True).encode()).hexdigest()
        return json.loads((provider.CACHE/(key+'.json')).read_text(encoding='utf8'))
    provider.historical=cached
    payload=config['comparison'];a,b=payload['laps']
    if payload['session']!='Qualifying':raise ValueError('This proof helper expects qualifying.')
    comparison=provider.comparison(VideoSelection(payload['year'],payload['event'],'Q',a['code'],b['code']))
    for actual,expected in zip(comparison.laps,payload['laps']):
        if actual.number!=expected['number'] or abs(actual.lap_time-expected['lap_time'])>1e-6:
            raise ValueError('Replay metadata does not match the cached laps.')
    timeline=limit_timeline(config['timeline']) if args.the_limit else config['timeline']
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(args.video)]))
    stream=next(v for v in info['streams'] if v['codec_type']=='video')
    if Fraction(stream['avg_frame_rate'])!=timeline['fps'] or int(stream['nb_frames'])!=len(timeline['source_times']):
        raise ValueError('Replay cadence/frame count does not match its source clock.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    from services.recorded_music import music_info,add_music_credit
    credit=music_info(args.soundtrack)
    # Old completed proof exports have no licensed-music footer. Add it once
    # before muxing. Normal site renders draw this in their first encode pass.
    if args.already_credited:
        comment=info.get('format',{}).get('tags',{}).get('comment','')
        if credit['title'] not in comment or credit['license'] not in comment:
            raise ValueError('Source metadata does not identify the matching credited soundtrack.')
        report=attach_duel(comparison,args.video,args.output,timeline,full=config['full'],volume=args.volume,soundtrack=args.soundtrack)
    else:
        with tempfile.TemporaryDirectory(prefix='music_proof_') as folder:
            folder=Path(folder);size=(stream['width'],stream['height'])
            height=max(20,round(27*size[0]/(540 if size[1]>size[0] else 960)))
            footer=add_music_credit(Image.new('RGB',size),credit).crop((0,size[1]-height,size[0],size[1]))
            footer.save(folder/'credit.png')
            source=folder/'credited.mp4'
            flags=dict(creationflags=subprocess.CREATE_NO_WINDOW) if hasattr(subprocess,'CREATE_NO_WINDOW') else {}
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(args.video),'-i',str(folder/'credit.png'),
                            '-filter_complex','[0:v][1:v]overlay=0:H-h[v]','-map','[v]','-an',
                            '-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p','-fps_mode','passthrough',str(source)],check=True,**flags)
            report=attach_duel(comparison,source,args.output,timeline,full=config['full'],volume=args.volume,soundtrack=args.soundtrack)
    report['proof_footer_reencode']=not args.already_credited
    args.output.with_suffix('.audio.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2));print(args.output)


if __name__=='__main__':main()
