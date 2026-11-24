"""Fetch positions and telemetry for a lap-1 incident from OpenF1 (free historical data).

Usage (from C:\\f1hud_app):
  .\\.venv\\Scripts\\python.exe scripts\\fetch_incident.py
Writes outputs\\incident\\mexico2026_lap1_{16,44}.csv and outline.csv.
"""
import csv, sys, time
from pathlib import Path
import requests

API = 'https://api.openf1.org/v1'
OUT = Path(__file__).resolve().parents[1] / 'outputs' / 'incident'
DRIVERS = (16, 44)
SECONDS = 150  # from the race start: covers the whole first lap


def get(endpoint, **params):
    for attempt in range(4):
        r = requests.get(f'{API}/{endpoint}', params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(3 + attempt * 3); continue
        if r.status_code == 404:
            return []
        r.raise_for_status()
        time.sleep(2.1)  # free tier: 30 requests a minute
        return r.json()
    raise RuntimeError(f'{endpoint}: rate limited')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sessions = [s for s in get('sessions', year=2026, session_name='Race') if 'Mexico' in (s.get('country_name') or '')]
    if not sessions:
        sys.exit('OpenF1 has no 2026 Mexico race session.')
    s = sessions[0]; key = s['session_key']
    print('Session', key, s['date_start'])
    laps = get('laps', session_key=key, lap_number=1)
    starts = sorted(l['date_start'] for l in laps if l.get('date_start'))
    t0 = starts[0] if starts else s['date_start']
    end = (pd_time(t0) + SECONDS)
    for n in DRIVERS:
        loc = get('location', session_key=key, driver_number=n, **{'date>': t0, 'date<': iso(end)})
        car = get('car_data', session_key=key, driver_number=n, **{'date>': t0, 'date<': iso(end)})
        print(f'#{n}: {len(loc)} positions, {len(car)} telemetry samples')
        if not loc:
            print('  OpenF1 has no position data for this car; send me this output.'); continue
        with open(OUT / f'mexico2026_lap1_{n}.csv', 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['date', 'x', 'y', 'z'])
            for p in loc: w.writerow([p['date'], p['x'], p['y'], p['z']])
        with open(OUT / f'mexico2026_lap1_{n}_car.csv', 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['date', 'speed', 'throttle', 'brake', 'n_gear', 'rpm', 'drs'])
            for c in car: w.writerow([c['date'], c.get('speed'), c.get('throttle'), c.get('brake'), c.get('n_gear'), c.get('rpm'), c.get('drs')])
    rc = get('race_control', session_key=key)
    with open(OUT / 'mexico2026_race_control.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['date', 'lap', 'category', 'flag', 'message'])
        for m in rc: w.writerow([m.get('date'), m.get('lap_number'), m.get('category'), m.get('flag'), m.get('message')])
    print('Saved to', OUT)


from datetime import datetime, timezone, timedelta
def pd_time(v): return datetime.fromisoformat(v.replace('Z', '+00:00')).timestamp()
def iso(ts): return datetime.fromtimestamp(ts, timezone.utc).isoformat()

if __name__ == '__main__':
    main()
