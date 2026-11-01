"""Local year-routing audit / short render using real Singapore telemetry."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.video_comparison import Comparison,ComparisonLap,VideoSelection,build_comparison
from services.video_3d import comparison_payload,render_3d_mp4,run_blender,blender_executable,CAR,CAR_METADATA,CIRCUIT,render_range
from services.singapore_asset import model_route,layout_for
from services.cornering import cornering_route
from services.circuits_3d import presentation
year=int(sys.argv[sys.argv.index('--year')+1]) if '--year' in sys.argv else 2026
folder=ROOT/'tmp/reference_review'/f'singapore_{year}';folder.mkdir(exist_ok=True)
payload=folder/'input.json'
if not payload.exists():
    if year==2026:
        p=json.loads((ROOT/'tmp/reference_review/night_chase_singapore_input.json').read_text())
    else:
        c=build_comparison(VideoSelection(year,'Singapore Grand Prix','Q','LEC','VER'))
        p=comparison_payload(c)
    payload.write_text(json.dumps(p))
p=json.loads(payload.read_text())
laps=tuple(ComparisonLap(**dict(lap,samples=pd.DataFrame(lap['samples']),warnings=[])) for lap in p['laps'])
c=Comparison(p['year'],p['event'],p['session'],laps,np.asarray(p['track']),p['warnings'])
if '--render' in sys.argv:
    environment='Telemetry-built' if '--telemetry' in sys.argv else 'Original model'
    suffix='telemetry' if '--telemetry' in sys.argv else 'layout'
    render_3d_mp4(c,ROOT/'output/video_studio'/f'singapore_{year}_{suffix}_check.mp4',
        camera='Night chase A',start=18,end=19,quality='Fast',environment=environment)
else:
    route=model_route(c)
    route.update(half_separation=[0.]*len(route['progress']),separation_range=[0.,0.],night_chase={'focus':0})
    start,end,frames,full=render_range(c,0,None,24)
    pres=presentation(year,c.event);pres.update(backend='original-glb',description=route['adaptation'],credit=route['environment_credit'])
    config=dict(comparison=p,alignment={'parameters':[0.,0.,0.,0.],'road_origin':[0.,0.],'mapped_xy':route['xy']},
        driving_path=route,source_glb=route['source_glb'],source_reference=str(layout_for(year)['reference']),circuit_presentation=pres,
        work_dir=str(folder),car=str(CAR),car_metadata=str(CAR_METADATA),circuit=str(CIRCUIT),start=start,end=end,
        frames=frames,full=full,fps=24,size=[540,960],camera='Night chase A',quality='Fast')
    target=folder/'config.json';target.write_text(json.dumps(config))
    run_blender([str(blender_executable()),'--background','--disable-autoexec','--python-exit-code','1',
        '--python',str(ROOT/'scripts/render_3d_test.py'),'--','--config',str(target),'--validate-only'],
        cancelled=None,progress_callback=None,frames=frames,log_path=folder/'blender.log')
    print('SINGAPORE_YEAR_AUDIT_PASS',year,route['source_model'],flush=True)
