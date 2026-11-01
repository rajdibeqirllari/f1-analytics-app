"""Local licensed sound-bank discovery, telemetry controls and export muxing."""
from pathlib import Path
import re
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/'assets'/'sounds'/'F1 2026 Sound Pack'/'formula ultra'
PROFILES={'redbull':'rbv2','ferrari':'ferrari v3','mercedes':'merc',
          'mclaren':'mclaren','astonmartin':'aston','audi':'audi'}


def bank_for_team(team, year):
    if int(year)!=2026:
        raise ValueError('This pack is a 2026 sound recreation, not an authentic historical engine pack.')
    key=re.sub('[^a-z]','',str(team).lower())
    matches=[k for k in PROFILES if k in key]
    if len(matches)!=1:
        raise ValueError(f'No verified sound profile for team {team}; choose a supported profile explicitly.')
    folder=PACK/PROFILES[matches[0]]
    bank=folder/'formula_ultra_26.bank';guids=folder/'GUIDs.txt'
    if not bank.is_file() or not guids.is_file():raise ValueError('Selected sound bank or event GUID list is missing.')
    events={}
    for line in guids.read_text(encoding='utf-8-sig').splitlines():
        match=re.match(r'(\{[0-9a-fA-F-]+\})\s+(event:/cars/[^/]+/([^/]+))$',line.strip())
        if match:events[match[3]]={'guid':match[1],'path':match[2]}
    for name in ('engine_int','gear_int','wind'):
        if name not in events:raise ValueError(f'The sound bank has no {name} event mapping.')
    return dict(profile=matches[0],bank=bank,events=events)


def telemetry_controls(lap,start=0.,end=None,rate=100):
    """RPM/load controls plus discrete shift triggers, never fabricated revs.

RPM/throttle/speed are interpolated, gears and brake are held at recorded values.
Units here are explicit; FMOD parameter ranges still require runtime inspection.
"""
    data=lap.samples
    if any('RPM is unavailable' in w for w in lap.warnings):raise ValueError('RPM is unavailable; engine audio cannot be synchronized honestly.')
    required=['t','rpm','throttle','speed','gear','brake']
    if not set(required).issubset(data):raise ValueError('Engine audio needs timestamped RPM, throttle, speed, gear and brake.')
    if not np.isfinite(data[required].to_numpy(dtype=float)).all():raise ValueError('Engine control channels contain missing values.')
    if not 20<=rate<=200:raise ValueError('Unsupported engine control rate.')
    end=lap.lap_time if end is None else min(float(end),lap.lap_time)
    if not 0<=start<end:raise ValueError('Choose a nonempty interval within the lap.')
    t=np.r_[np.arange(start,end,1/rate),end]
    source=data.t.to_numpy();index=np.clip(np.searchsorted(source,t,side='right')-1,0,len(source)-1)
    gear=data.gear.to_numpy()[index].astype(int)
    shifts=np.flatnonzero(np.diff(gear)!=0)+1
    return dict(time=t-start,rpms=np.interp(t,source,data.rpm),
                throttle=np.clip(np.interp(t,source,data.throttle)/100,0,1),
                speed_kmh=np.interp(t,source,data.speed),gear=gear,
                brake=data.brake.to_numpy()[index].astype(bool),
                shifts=[dict(time=float(t[i]-start),direction='up' if gear[i]>gear[i-1] else 'down') for i in shifts])


def prepare_audio(comparison, camera, start=0., end=None):
    if camera not in ('Night chase A','Night chase B','Onboard ghost A','Onboard ghost B'):
        raise ValueError('Engine audio needs a selected chase or onboard driver.')
    lap=comparison.laps[int(camera.endswith(' B'))]
    bank=bank_for_team(lap.team,comparison.year)
    from services.fmod_audio import SDK
    if not (SDK.parent/'master.bank').is_file():
        raise ValueError('The sound pack depends on a missing master/mixer bank. Obtain a matching standalone master.bank from its creator before enabling audio.')
    for p in (SDK/'lowlevel/lib/fmod64.dll',SDK/'studio/lib/fmodstudio64.dll',
              SDK/'lowlevel/lib/fmod_distance_filter64.dll'):
        if not p.is_file():raise ValueError('The local licensed FMOD runtime or distance-filter plug-in is missing.')
    controls=telemetry_controls(lap,start,end)
    return dict(bank=str(bank['bank']),events=bank['events'],
                controls={k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in controls.items()})


def add_engine_audio(video, spec, cancelled=None):
    """Isolate native bank playback in a worker; replace video only after mux success."""
    import json
    import subprocess
    import sys
    import tempfile
    import time
    video=Path(video)
    with tempfile.TemporaryDirectory(prefix='engine_',dir=video.parent) as folder:
        folder=Path(folder); config=folder/'controls.json'; wav=folder/'engine.wav'
        config.write_text(json.dumps(spec),encoding='utf8')
        def run(command):
            with (folder/'worker.log').open('wb') as log:
                process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=log)
                started=time.monotonic()
                try:
                    while process.poll() is None:
                        if cancelled and cancelled():raise InterruptedError('Audio rendering cancelled.')
                        if time.monotonic()-started>600:raise TimeoutError('Engine audio rendering timed out.')
                        time.sleep(.1)
                    if process.returncode:
                        raise RuntimeError('Engine audio failed: '+(folder/'worker.log').read_text(errors='replace')[-1800:])
                finally:
                    if process.poll() is None:
                        process.kill();process.wait()
        run([sys.executable,'-m','services.fmod_audio',str(config),str(wav)])
        target=folder/'muxed.mp4'
        run(['ffmpeg','-y','-v','error','-i',str(video),'-i',str(wav),
             '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k',
             '-af','alimiter=limit=0.95:level=false,apad','-shortest',
             '-metadata','description=Recreated engine audio; FMOD by Firelight Technologies. Not an actual onboard recording.',
             '-movflags','+faststart',str(target)])
        if cancelled and cancelled():raise InterruptedError('Audio rendering cancelled.')
        target.replace(video)
