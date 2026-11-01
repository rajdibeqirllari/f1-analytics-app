"""Local integration smoke test using synthetic controls, not a race recording."""
from pathlib import Path
from services.engine_audio import bank_for_team
from services.fmod_audio import render_controls
import numpy as np

if __name__=='__main__':
    t=np.arange(0,3.01,.01)
    controls=dict(time=t.tolist(),rpms=(6500+5000*np.minimum(t/2,1)).tolist(),
                  throttle=np.ones(len(t)).tolist(),speed_kmh=(100+50*t).tolist(),
                  shifts=[dict(time=1.,direction='up'),dict(time=2.,direction='up')])
    for team in ('Red Bull Racing','Ferrari'):
        bank=bank_for_team(team,2026)
        out=Path('tmp')/(bank['profile']+'-engine-test.wav')
        render_controls(bank['bank'],bank['events'],controls,out)
        print(out.resolve())
