"""Benchmark actual full-lap scene complexity without rendering the full lap."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.video_3d import run_blender,blender_executable
source=ROOT/'tmp/reference_review/night_chase_audit/config.json'
config=json.loads(source.read_text())
folder=ROOT/'tmp/reference_review/singapore_speed';folder.mkdir(exist_ok=True)
config.update(work_dir=str(folder),frames=4,start=18.,quality='Fast')
if '--samples' in sys.argv:config['benchmark_samples']=int(sys.argv[sys.argv.index('--samples')+1])
if '--720' in sys.argv:config['size']=[720,1280]
target=folder/'config.json';target.write_text(json.dumps(config))
run_blender([str(blender_executable()),'--background','--disable-autoexec','--profile-gpu','--python-exit-code','1',
    '--python',str(ROOT/'scripts/render_3d_test.py'),'--','--config',str(target),'--animate'],
    cancelled=None,progress_callback=None,frames=4,log_path=folder/'blender.log')
