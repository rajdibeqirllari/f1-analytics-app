"""Verify all existing HUD encoders with a short excerpt of real lap telemetry."""
import json
from pathlib import Path
from api.engines import load_telemetry
from api.main import Selection
from services.hud_renderer import normalize_hud_telemetry,export_hud_alpha_video,export_hud_png_sequence,zip_png_sequence

root=Path(__file__).resolve().parents[1]
s=Selection(year=2025,event='Austrian Grand Prix',session='Q',driver='VER')
frame,_,metadata=load_telemetry(s,'FastF1')
frame=normalize_hud_telemetry(frame,'FastF1')
frame=frame[frame.t<=.6].copy()
common=dict(fps=24,canvas_size=(320,180),hud_width=150,position_preset='Custom',custom_x=15,custom_y=15,hud_year=2025)
folder=root/'outputs'/'hud_exports';folder.mkdir(parents=True,exist_ok=True)
report=[]
for mode in ('WebM VP9 Alpha','MOV ProRes 4444','PNG Sequence'):
    label='integration_real_Austria_2025_'+mode.replace(' ','_')
    if mode=='PNG Sequence':
        result=export_hud_png_sequence(frame,root/'assets'/'hud',root/'outputs'/'hud_frames',label,**common)
        path=folder/(label+'.zip');path.write_bytes(zip_png_sequence(result.frames_dir))
    else:
        result=export_hud_alpha_video(frame,root/'assets'/'hud',folder,root/'outputs'/'hud_frames',label,format_label=mode,**common)
        path=result.output_path
    assert path.is_file() and path.stat().st_size>0
    report.append(dict(format=mode,file=str(path),frames=result.frame_count,size=path.stat().st_size))
    print(json.dumps(report[-1]),flush=True)
(root/'tmp'/'platform-hud-encoders.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
