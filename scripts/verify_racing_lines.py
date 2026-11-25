"""Footprint check for the reconstructed racing lines: raw vs reconstructed, whole session, same maths as the browser.

  .venv\\Scripts\\python.exe scripts\\verify_racing_lines.py 2025 "Abu Dhabi Grand Prix" R
Writes outputs/v3/racing_lines_<year>_<event>.json: overlap counts, remaining intersections, close passes.
"""
from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.disable(logging.WARNING)


def main(year: int, event: str, session: str, step: float = 0.5):
    from services import racing_lines as rl, replay_fallback as rf, replay_scene as rs
    from scipy.spatial import cKDTree
    p = rf.replay_with_fallback(year, event, session, 3)
    rec = rs.build(p)['rec']
    tr = rec.track
    fr = p['frames']
    res = rl.from_recorded(rec.cars, tr, edges=rl.venue_edges(event, tr), t_range=(float(fr[0]['t']) - 60, float(fr[-1]['t'])))
    X, Y = tr.x, tr.y
    tx, ty = np.gradient(X), np.gradient(Y)
    n = np.hypot(tx, ty)
    tx, ty = tx / n, ty / n
    kd = cKDTree(np.c_[X, Y])
    times = np.arange(max(res.t[0], float(fr[0]['t'])), res.t[-1], step)
    codes = res.codes
    C = len(codes)
    xs = {m: np.full((C, len(times)), np.nan) for m in ('raw', 'recon')}
    ys = {m: np.full((C, len(times)), np.nan) for m in ('raw', 'recon')}
    hs = {m: np.full((C, len(times)), np.nan) for m in ('raw', 'recon')}
    S = np.full((C, len(times)), np.nan)
    for i, c in enumerate(codes):
        d = rec.cars[c]
        t = np.asarray(d['t'], float)
        x = np.interp(times, t, d['x'])
        y = np.interp(times, t, d['y'])
        ok = (times >= t[0]) & (times <= t[-1])
        vx, vy = np.gradient(x, step), np.gradient(y, step)
        sp = np.hypot(vx, vy)
        h = np.unwrap(np.arctan2(vy, vx))
        dist, j = kd.query(np.c_[x, y])
        lat = (x - X[j]) * -ty[j] + (y - Y[j]) * tx[j]
        ok = ok & (dist < 9) & (np.abs(lat) < 7.5)          # on track only (pit lane / garages are recorded as-is)
        h = np.where(sp > 3, h, np.arctan2(ty[j], tx[j]))
        o = np.interp(times, res.t, res.o[i])
        do = np.gradient(o, step)
        xs['raw'][i] = np.where(ok, x, np.nan)
        ys['raw'][i] = np.where(ok, y, np.nan)
        hs['raw'][i] = h
        xs['recon'][i] = np.where(ok, x - ty[j] * o, np.nan)
        ys['recon'][i] = np.where(ok, y + tx[j] * o, np.nan)
        hs['recon'][i] = h + np.where(sp > 2, np.arctan2(do, np.maximum(8, sp)), 0)
        S[i] = np.where(ok, tr.s[j], np.nan)
    out = dict(session=f'{year} {event} {session}', step=step, meta=res.meta, cars=C)
    for m in ('raw', 'recon'):
        hits = rl.footprint_overlaps(times, xs[m], ys[m], hs[m], codes)
        out[m] = dict(overlap_instants=len(hits), unique_pairs=len({(a, b) for _, a, b in hits}),
                      first=[(round(t, 1), a, b) for t, a, b in hits[:40]])
    # close passes: order swaps between two cars within 12 m, both on track and moving, outside the first 30 s
    L = tr.length
    passes = []
    for a in range(C):
        for b in range(a + 1, C):
            ds = ((S[a] - S[b] + L / 2) % L) - L / 2
            close = np.abs(ds) < 12
            sw = np.where(close[1:] & close[:-1] & (np.sign(ds[1:]) != np.sign(ds[:-1])) & (np.abs(ds[1:] - ds[:-1]) < 10))[0]
            for k in sw:
                if times[k] > 30:
                    passes.append(dict(t=round(float(times[k]), 1), a=codes[a], b=codes[b], ahead_after=codes[a] if ds[k + 1] > 0 else codes[b]))
    out['close_passes'] = sorted(passes, key=lambda q: q['t'])[:80]
    safe = event.lower().replace(' ', '_')
    path = ROOT / f'outputs/v3/racing_lines_{year}_{safe}_{session}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in out.items() if k not in ('close_passes',)}, indent=1)[:3000])
    print('close passes (first 25):', [(q['t'], q['a'], q['b'], '->', q['ahead_after']) for q in out['close_passes'][:25]])


if __name__ == '__main__':
    main(int(sys.argv[1]), sys.argv[2], sys.argv[3])
