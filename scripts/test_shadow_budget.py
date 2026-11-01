"""1080p Balanced regression at the start of the user's problematic lap.

Keep Blender log/validation outside its ephemeral work directory for auditing.
"""
from pathlib import Path
import shutil
import time
import services.video_3d as renderer
from services.openf1_comparison import comparison
from services.video_comparison import VideoSelection

if __name__=='__main__':
    out=Path('tmp/shadow-budget');out.mkdir(exist_ok=True)
    original=renderer.run_blender
    def audited(*args,**kwargs):
        try:return original(*args,**kwargs)
        finally:
            log=kwargs['log_path']
            if log.is_file():shutil.copyfile(log,out/'blender.log')
            validation=log.parent/'validation.json'
            if validation.is_file():shutil.copyfile(validation,out/'validation.json')
    renderer.run_blender=audited
    c=comparison(VideoSelection(2026,'United States Grand Prix','FP1','LEC','VER'))
    start=time.monotonic()
    result=renderer.render_3d_mp4(c,out/'1080-balanced.mp4',size=(1080,1920),fps=24,
        camera='Onboard ghost B',start=2.5,end=3.5,quality='Balanced')
    log=(out/'blender.log').read_text(errors='replace')
    if 'Shadow buffer full' in log:raise AssertionError('Shadow atlas still overflows.')
    print('OUTPUT',result,'TOTAL_SECONDS',round(time.monotonic()-start,2),'SHADOW_OVERFLOWS',0)
