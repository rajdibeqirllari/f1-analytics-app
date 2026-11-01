"""Make a local listening test using actual Austin FP1 telemetry and pack samples."""
import json
from pathlib import Path
from services.engine_audio import bank_for_team,telemetry_controls
from services.engine_samples import render_sample_audio
from services.video_comparison import VideoSelection
from services.openf1_comparison import comparison

if __name__=='__main__':
    c=comparison(VideoSelection(2026,'United States Grand Prix','FP1','LEC','VER'))
    for lap in c.laps:
        bank=bank_for_team(lap.team,c.year)
        controls=telemetry_controls(lap,0,10)
        controls={k:v.tolist() if hasattr(v,'tolist') else v for k,v in controls.items()}
        spec=dict(bank=str(bank['bank']),controls=controls)
        output=Path('tmp')/(lap.code+'-sampled-engine-v2.wav')
        render_sample_audio(spec,output)
        print(lap.code,lap.team,lap.number,output.resolve(),flush=True)
        (output.with_suffix('.json')).write_text(json.dumps(spec),encoding='utf8')
