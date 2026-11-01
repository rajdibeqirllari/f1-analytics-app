"""Production-path proof using the user's cached qualifying laps, no fake data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import services.openf1_comparison as provider
import services.video_3d as renderer
from services.video_comparison import VideoSelection


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--full',action='store_true')
    p.add_argument('--resolution',type=int,default=540);p.add_argument('--fps',type=int,default=60)
    p.add_argument('--pacing',default='Dynamic cinematic');p.add_argument('--quality',default='Balanced')
    p.add_argument('--start',type=float,default=0);p.add_argument('--end',type=float,default=12)
    p.add_argument('--output',type=Path,default=Path('output/video_studio/cinematic-proof'))
    p.add_argument('--alignment-debug',action='store_true')
    p.add_argument('--the-limit',action='store_true')
    p.add_argument('--overhead',action='store_true');args=p.parse_args()
    output=args.output;output.mkdir(exist_ok=True,parents=True)
    original=renderer.run_blender
    def audited(*a,**kw):
        try:return original(*a,**kw)
        finally:
            for name in ('blender.log','validation.json','camera-motion.npz','trail-alignment.json','trail-debug.npz','config.json'):
                source=kw['log_path'].parent/name
                if source.is_file():shutil.copyfile(source,output/name)
    renderer.run_blender=audited
    def cached(endpoint,params):
        key=hashlib.sha256(json.dumps([endpoint,params],sort_keys=True).encode()).hexdigest()
        path=provider.CACHE/(key+'.json')
        if not path.is_file():raise FileNotFoundError(f'Required historical cache missing: {endpoint} {params}')
        return json.loads(path.read_text(encoding='utf8'))
    provider.historical=cached
    comparison=provider.comparison(VideoSelection(2026,'United States Grand Prix','Q','ANT','VER'))
    print([(l.code,l.number,l.lap_time) for l in comparison.laps],flush=True)
    gap=abs(comparison.laps[0].lap_time-comparison.laps[1].lap_time)
    if abs(gap-.179)>.001:raise ValueError('Selected data does not match the confirmed qualifying comparison.')
    metadata=dict(session=comparison.session,laps=[dict(driver=l.code,lap=l.number,time=l.lap_time) for l in comparison.laps],gap=gap)
    (output/'source.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
    destination=output/f'ANT-VER-COTA-Q-{args.resolution}p-{args.fps}fps-{"full" if args.full else "clip"}.mp4'
    last_message=[None]
    def progress(value,message):
        key=(int(value*20),message.split(' · ')[0])
        if key!=last_message[0]:print(f'{value:.1%} {message}',flush=True);last_message[0]=key
    result=renderer.render_3d_mp4(comparison,destination,size=(args.resolution,args.resolution*16//9),fps=args.fps,
        start=args.start,end=None if args.full else args.end,quality=args.quality,playback_speed=3,
        camera='The Limit' if args.the_limit else 'Classic Broadcast' if args.overhead else 'Cinematic Ghost Chase',pacing=args.pacing,target_duration=35,alignment_debug=args.alignment_debug,
        progress_callback=progress)
    print(result,flush=True)
