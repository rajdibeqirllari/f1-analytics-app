"""Checks the Lusail venue against session data, in the same frames the browser uses.

Recorded mode (2025 Qatar GP race replay, OpenF1 location, every car, every sample on track):
  scene -> venue asset frame exactly as venue.ts does it (asset = scene + track.frame - manifest.origin), then
  * lateral position vs the model's asphalt edges (car half-width 0.95 m), per corner zone
  * recorded elevation vs the model's surface height (the browser puts tyres on the model surface)
  * drift: the same check per lap, first vs last laps
Estimated mode (bundled outline, the Live page's geometry): racing line vs the model's edges, frame offset.

Writes outputs/qatar/alignment_report.json and prints a summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MAN = ROOT / 'frontend/public/venues/lusail/manifest.json'


def asset_geometry(m):
    x, y, z = (np.array(m['centre'][k]) for k in 'xyz')
    t = np.c_[np.roll(x, -2) - np.roll(x, 2), np.roll(y, -2) - np.roll(y, 2)]
    t /= np.linalg.norm(t, axis=1)[:, None]
    return np.c_[x, y], z, np.c_[-t[:, 1], t[:, 0]], np.array(m['edges']['left']), np.array(m['edges']['right'])


def zone_of(st, m):
    for c in m['landmarks']['corners']:
        if abs(((st - c['station']) + 2700) % m['length'] - 2700) < 60:
            return f"T{c['n']}"
    return 'straights'


def recorded(m, report):
    from services import replay_fallback as rf, replay_scene as rs
    p = rf.replay_with_fallback(2025, 'Qatar Grand Prix', 'R', 3)
    rec = rs.build(p)['rec']
    fx, fy, fz = rec.track.frame
    ox, oy = m['origin']
    C, Z, Nn, EL, ER = asset_geometry(m)
    tree = cKDTree(C)
    rows = []
    for code, d in rec.cars.items():
        t = np.asarray(d['t'])
        ax = np.asarray(d['x']) + fx - ox
        ay = np.asarray(d['y']) + fy - oy
        az = np.asarray(d['z']) + fz - m['z_offset']
        dist, i = tree.query(np.c_[ax, ay])
        lat = np.einsum('ij,ij->i', np.c_[ax, ay] - C[i], Nn[i])
        pit = cKDTree(np.c_[m['pit']['x'], m['pit']['y']]).query(np.c_[ax, ay])[0] < 6.0
        on = (dist < 25) & ~(pit & (lat < -7.5))    # on the circuit, not in the pit lane / garages
        over = np.maximum(lat - (EL[i] - 0.95), -lat - (ER[i] - 0.95))
        for k in np.where(on)[0][::2]:
            rows.append((code, t[k], i[k] * m['step'], lat[k], over[k], az[k] - Z[i[k]]))
    a = np.array([(r[1], r[2], r[3], r[4], r[5]) for r in rows])
    t, st, lat, over, dz = a.T
    zones = {}
    names = np.array([zone_of(s, m) for s in st])
    for z_ in sorted(set(names), key=lambda q: (q != 'straights', len(q), q)):
        mm = names == z_
        zones[z_] = dict(samples=int(mm.sum()), body_over_edge_pct=round(100 * float(np.mean(over[mm] > 0)), 2),
                         over_1m_pct=round(100 * float(np.mean(over[mm] > 1)), 2), max_over_m=round(float(over[mm].max()), 2))
    early, late = t < 1200, t > 4000
    report['recorded'] = dict(
        session='2025 Qatar GP race, OpenF1 location (session 9850)', frame=list(rec.track.frame), samples=len(rows),
        body_over_edge_pct=round(100 * float(np.mean(over > 0)), 3), over_1m_pct=round(100 * float(np.mean(over > 1)), 3),
        lateral_p99_m=round(float(np.percentile(np.abs(lat), 99)), 2),
        elevation_recorded_minus_model_m=dict(median=round(float(np.median(dz)), 3), p95_abs=round(float(np.percentile(np.abs(dz), 95)), 3)),
        drift=dict(early_median_abs_lat=round(float(np.median(np.abs(lat[early]))), 2), late_median_abs_lat=round(float(np.median(np.abs(lat[late]))), 2),
                   early_over_pct=round(100 * float(np.mean(over[early] > 0)), 3), late_over_pct=round(100 * float(np.mean(over[late] > 0)), 3)),
        zones=zones)


def estimated(m, report):
    from services import scene3d as sc
    o = sc._bundled_outline('Qatar Grand Prix')
    tr = sc.track_from_outline(o)
    fx, fy, fz = tr.frame
    ox, oy = m['origin']
    C, Z, Nn, EL, ER = asset_geometry(m)
    tree = cKDTree(C)
    tx, ty = tr.x + fx - ox, tr.y + fy - oy
    dist, i = tree.query(np.c_[tx, ty])
    t = np.c_[np.roll(tr.x, -3) - np.roll(tr.x, 3), np.roll(tr.y, -3) - np.roll(tr.y, 3)]
    t /= np.linalg.norm(t, axis=1)[:, None]
    lx, ly = tx - t[:, 1] * tr.line, ty + t[:, 0] * tr.line
    lat = np.einsum('ij,ij->i', np.c_[lx, ly] - C[i], Nn[i])
    over = np.maximum(lat - (EL[i] - 0.95), -lat - (ER[i] - 0.95))
    report['estimated'] = dict(outline='frontend/src/hype/circuits/qatar-grand-prix.json', frame=list(tr.frame), length=round(tr.length, 1),
                               centre_to_model_median_m=round(float(np.median(dist)), 3), centre_to_model_max_m=round(float(dist.max()), 3),
                               line_body_over_edge_pct=round(100 * float(np.mean(over > 0)), 2), line_max_over_m=round(float(over.max()), 2),
                               elevation_track_minus_model_p95_m=round(float(np.percentile(np.abs(tr.z - Z[i]), 95)), 3))


def main():
    m = json.loads(MAN.read_text(encoding='utf-8'))
    report = dict(venue=m['name'], model_length_m=m['length'], fia_length_m=5419.0, fit=m['fit'])
    estimated(m, report)
    recorded(m, report)
    out = ROOT / 'outputs/qatar/alignment_report.json'
    out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'recorded'}, indent=1))
    r = report['recorded']
    print(json.dumps({k: v for k, v in r.items() if k != 'zones'}, indent=1))
    print('zones:', json.dumps(r['zones']))


if __name__ == '__main__':
    main()
