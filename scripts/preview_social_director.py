"""Local production-path preview; real cached Austin telemetry, not demo timings."""
from pathlib import Path
import shutil
import json
import hashlib
import services.video_3d as renderer
import services.openf1_comparison as source
from services.openf1_comparison import comparison
from services.video_comparison import VideoSelection

if __name__=='__main__':
    output=Path('tmp/social-director');output.mkdir(exist_ok=True)
    original=renderer.run_blender
    def audited(*args,**kwargs):
        try:return original(*args,**kwargs)
        finally:
            log=kwargs['log_path']
            for name in ('blender.log','validation.json'):
                p=log.parent/name
                if p.is_file():shutil.copyfile(p,output/name)
    renderer.run_blender=audited
    # Reproducible local proof from the user's existing successful cached data.
    # Do not make a preview depend on refreshing an expired sessions listing.
    historical=source.historical
    def cached(endpoint,params):
        key=hashlib.sha256(json.dumps([endpoint,params],sort_keys=True).encode()).hexdigest()
        path=source.CACHE/(key+'.json')
        if path.is_file():return json.loads(path.read_text(encoding='utf8'))
        return historical(endpoint,params)
    source.historical=cached
    c=comparison(VideoSelection(2026,'United States Grand Prix','FP1','LEC','VER'))
    import sys
    speed=int(sys.argv[1]) if len(sys.argv)>1 else 5
    print(renderer.render_3d_mp4(c,output/f'race-hype-cut-{speed}x.mp4',camera='Social director',
        size=(540,960),fps=24,start=0,end=20,quality='Fast',playback_speed=speed),flush=True)
