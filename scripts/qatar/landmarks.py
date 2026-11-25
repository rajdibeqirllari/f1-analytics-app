"""Adds landmarks to assets/3d/qatar/lusail_layout.json: corners, timing lines and the grid.

* Corners T1-T16: curvature peaks of the OSM centreline, assigned in order and checked against the FIA map's
  turn directions (R L R R R L R L R L L R R R L R). T11 is a long sweep: its apex is the middle of the bend.
* Control line: station 0 (where OpenF1 laps start = the timing line).
* Grid: the 20 cars' parked positions in the 2025 race, 20-4 s before the first lap starts (median of samples).
  The start line sits 2.6 m ahead of the pole car's centre (half a wheelbase + front overhang to the front axle
  is not modelled; the box is painted ahead of the car's front wing).
* FIA-text distances (S1 80 m before T6, S2 75 m before T12, speed trap 205 m before T1, DRS detection 40 m after
  T15, activation 305 m after T16) measured from the apex stations: approximate, flagged as such.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
LAYOUT = ROOT / 'assets/3d/qatar/lusail_layout.json'
TURNS = 'RLRRRLRLRLLRRRLR'
# Apex stations (m) from the curvature peaks (prepare_lusail.py output, 2 m stations); T11 = middle of 3270-3394.
APEX = [774, 1090, 1291, 1723, 1868, 2154, 2644, 2833, 2932, 3144, 3338, 3780, 3974, 4180, 4488, 4922]


def main():
    import pandas as pd
    from services.openf1_comparison import historical, resolve
    d = json.loads(LAYOUT.read_text(encoding='utf-8'))
    x, y = np.array(d['centre']['x']), np.array(d['centre']['y'])
    k = np.array(d['curvature'])
    st, n, L = d['step'], len(x), d['length']
    corners = []
    for i, (s, dirn) in enumerate(zip(APEX, TURNS), 1):
        j = int(round(s / st)) % n
        got = 'L' if k[j] > 0 else 'R'
        if got != dirn:
            raise SystemExit(f'T{i} direction {got} != FIA {dirn}')
        corners.append(dict(n=i, station=s, dir=dirn, radius=round(1 / max(1e-6, abs(k[j]))), x=x[j], y=y[j]))

    key = int(resolve(2025, 'Qatar Grand Prix', 'R')['session_key'])
    laps = pd.DataFrame(historical('laps', {'session_key': key}))
    l1 = pd.to_datetime(laps[laps.lap_number == 1].date_start, utc=True, format='ISO8601', errors='coerce').dropna()
    go = l1.min().value / 1e9
    tan = np.c_[np.gradient(x), np.gradient(y)]
    tan /= np.linalg.norm(tan, axis=1)[:, None]
    grid = []
    for drv in historical('drivers', {'session_key': key}):
        loc = pd.DataFrame(historical('location', {'session_key': key, 'driver_number': int(drv['driver_number'])}))
        t = pd.to_datetime(loc.date, utc=True, format='ISO8601', errors='coerce').astype('int64') / 1e9
        m = (t > go - 20) & (t < go - 4) & ~((loc.x == 0) & (loc.y == 0))
        if m.sum() < 5:
            continue
        px, py = float(np.median(loc.x[m])) / 10, float(np.median(loc.y[m])) / 10
        spread = float(np.hypot(loc.x[m] / 10 - px, loc.y[m] / 10 - py).max())
        j = int(np.argmin((x - px) ** 2 + (y - py) ** 2))
        lat = float((px - x[j]) * -tan[j, 1] + (py - y[j]) * tan[j, 0])
        grid.append(dict(code=drv.get('name_acronym'), x=round(px, 2), y=round(py, 2), station=round(j * st, 1), lateral=round(lat, 2),
                         spread=round(spread, 2)))
    pitlane = [g for g in grid if abs(g["lateral"]) > 9]
    grid = [g for g in grid if abs(g["lateral"]) <= 9]
    grid.sort(key=lambda g: -g["station"])
    for i, g in enumerate(grid, 1):
        g['slot'] = i
    pole = grid[0]
    start = pole['station'] + 2.6
    print('grid (front to back):', [(g['code'], g['station'], g['lateral']) for g in grid])
    rows = np.diff([g['station'] for g in grid])
    print(f'start line {start:.1f} m after the control line; slot spacing median {np.median(-rows):.2f} m')
    a = lambda s: round(s % L, 1)
    d['landmarks'] = dict(
        control_line=0.0, start_line=round(start, 1), corners=corners, grid=grid, pit_lane_starters=pitlane,
        grid_note='Slot stations measured (8.00 m spacing). Left/right stagger is not in the feed (cars snapped to one line): pole on the right (inside of T1) is an estimate.',
        approx=dict(sector1=a(APEX[5] - 80), sector2=a(APEX[11] - 75), speed_trap=a(APEX[0] - 205),
                    drs_detection=a(APEX[14] + 40), drs_activation=a(APEX[15] + 305),
                    note='FIA map distances measured from the apex stations here; the FIA reference point may differ (±30 m).'),
        sources=dict(corners='OSM centreline curvature + FIA map turn order', grid=f'OpenF1 location, session {key}, 4-20 s before lap 1',
                     timing='FIA circuit map Qatar 2025 v2'))
    LAYOUT.write_text(json.dumps(d), encoding='utf-8')
    print('landmarks written')


if __name__ == '__main__':
    main()
