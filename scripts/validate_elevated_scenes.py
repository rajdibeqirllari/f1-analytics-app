"""Blender geometry-only regressions for elevated day/night director scenes."""
from pathlib import Path
import json
import shutil
import numpy as np
import pandas as pd
import services.video_3d as renderer
import services.video_3d_overlay as overlay
from services.video_comparison import Comparison,ComparisonLap

if __name__=='__main__':
    output=Path('tmp/elevated-validation');output.mkdir(exist_ok=True)
    original=renderer.run_blender
    overlay.encode_frames=lambda *args,**kwargs:None
    for name in ('spa_3d_input','night_chase_singapore_input'):
        d=json.loads((Path('tmp/reference_review')/(name+'.json')).read_text())
        laps=[]
        for l in d['laps']:
            v=dict(l);v['samples']=pd.DataFrame(v['samples']);v.setdefault('warnings',[])
            laps.append(ComparisonLap(**v))
        c=Comparison(d['year'],d['event'],d['session'],tuple(laps),np.array(d['track']),d['warnings'])
        def validate(command,**kwargs):
            command=[x for x in command if x!='--animate']+['--validate-only']
            try:return original(command,**kwargs)
            finally:
                folder=kwargs['log_path'].parent
                for file in ('validation.json','blender.log'):
                    p=folder/file
                    if p.exists():shutil.copyfile(p,output/(name+'-'+file))
        renderer.run_blender=validate
        renderer.render_3d_mp4(c,output/(name+'.mp4'),camera='Social director',
            size=(540,960),fps=24,start=0,end=.25,quality='Fast')
        print('VALIDATED',name,flush=True)
