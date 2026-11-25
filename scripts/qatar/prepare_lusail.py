"""Lusail layout for the 3D Broadcast: geometry from independent sources, aligned to the OpenF1 position frame.

Sources (recorded in the output):
* OpenStreetMap (ODbL, (c) OpenStreetMap contributors), extract 2026-11-25 in assets/3d/qatar/refs/osm:
  - the asphalt surface polygon (area:highway=raceway, relation 18052714)  -> road edges
  - the circuit centreline (relation 21297662 main loop)                     -> layout
  - the F1 pit entry + pit lane ways                                          -> pit lane
  - buildings, grandstand, bleachers, fences, walls, sand/grass areas         -> venue footprints
* OpenF1 location, 2025 Qatar GP race (session 9850), all 20 cars             -> frame, elevation, checks only
  (the driven paths never shape the road; they are used to align the map and to check that every car stays on it)
* FIA circuit map, Qatar 2025 v2 (27.11.25): centreline length 5.419 km, S1 80 m before T6, S2 75 m before T12,
  speed trap 205 m before T1, DRS detection 40 m after T15, activation 305 m after T16 -> scale + landmark checks

Output frame ("Lusail frame"): OpenF1 x/y/z divided by 10 (metres), NOT centred. Each 3D scene centres its own data on
its fastest lap, so the browser fits this frame to the scene (rotation + translation) when it loads.

Run:  .venv\\Scripts\\python.exe scripts\\qatar\\prepare_lusail.py
"""
from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OSM = ROOT / 'assets/3d/qatar/refs/osm/lusail_osm.xml'
OUT = ROOT / 'assets/3d/qatar/lusail_layout.json'
SESSION = (2025, 'Qatar Grand Prix', 'R')
FIA_LENGTH = 5419.0
STEP = 2.0


# ------------------------------------------------------------------ OSM
def load_osm():
    r = ET.parse(OSM).getroot()
    nodes = {n.get('id'): (float(n.get('lat')), float(n.get('lon'))) for n in r.iter('node')}
    ways = {}
    for w in r.iter('way'):
        ways[w.get('id')] = dict(nd=[n.get('ref') for n in w.iter('nd')], tags={t.get('k'): t.get('v') for t in w.iter('tag')})
    rels = {}
    for rel in r.iter('relation'):
        rels[rel.get('id')] = dict(members=[(m.get('type'), m.get('ref'), m.get('role')) for m in rel.iter('member')],
                                   tags={t.get('k'): t.get('v') for t in rel.iter('tag')})
    return nodes, ways, rels


def projector(nodes):
    lat0 = np.mean([v[0] for v in nodes.values()])
    lon0 = np.mean([v[1] for v in nodes.values()])
    a, e2 = 6378137.0, 6.69437999014e-3
    s = math.sin(math.radians(lat0))
    M = a * (1 - e2) / (1 - e2 * s * s) ** 1.5
    N = a / math.sqrt(1 - e2 * s * s)

    def f(ids):
        ll = np.array([nodes[i] for i in ids if i in nodes])
        return np.c_[np.radians(ll[:, 1] - lon0) * N * math.cos(math.radians(lat0)), np.radians(ll[:, 0] - lat0) * M]
    return f, (lat0, lon0)


def chain(way_ids, ways):
    """Join ways end to end (reversing where needed) into one node list."""
    segs = [list(ways[w]['nd']) for w in way_ids if w in ways]
    out = segs.pop(0)
    while segs:
        for i, s in enumerate(segs):
            if s[0] == out[-1]:
                out += s[1:]
            elif s[-1] == out[-1]:
                out += s[::-1][1:]
            elif s[-1] == out[0]:
                out = s[:-1] + out
            elif s[0] == out[0]:
                out = s[::-1][:-1] + out
            else:
                continue
            segs.pop(i)
            break
        else:
            break
    return out


def rings(rel, ways):
    """Outer/inner rings of a multipolygon relation (each ring a closed node list)."""
    res = {'outer': [], 'inner': []}
    for role in res:
        ids = [ref for t, ref, rl in rel['members'] if t == 'way' and rl == role]
        pool = [list(ways[i]['nd']) for i in ids if i in ways]
        while pool:
            ring = pool.pop(0)
            changed = True
            while ring[0] != ring[-1] and changed:
                changed = False
                for i, s in enumerate(pool):
                    if s[0] == ring[-1]:
                        ring += s[1:]
                    elif s[-1] == ring[-1]:
                        ring += s[::-1][1:]
                    else:
                        continue
                    pool.pop(i)
                    changed = True
                    break
            res[role].append(ring)
    return res


# ------------------------------------------------------------------ geometry helpers
def resample(p, step=STEP, closed=True):
    q = np.r_[p, p[:1]] if closed else p
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(q, axis=0).T))]
    n = max(8, int(round(d[-1] / step)))
    g = np.linspace(0, d[-1], n, endpoint=not closed)
    return np.c_[np.interp(g, d, q[:, 0]), np.interp(g, d, q[:, 1])], float(d[-1])


def smooth_closed(a, k):
    if k <= 1:
        return a
    pad = np.r_[a[-k:], a, a[:k]]
    return np.convolve(pad, np.ones(k) / k, mode='same')[k:-k]


def tangents(p):
    d = np.roll(p, -3, axis=0) - np.roll(p, 3, axis=0)
    return d / np.maximum(1e-9, np.linalg.norm(d, axis=1))[:, None]


def umeyama(src, dst, scale=True):
    ms, md = src.mean(0), dst.mean(0)
    A, B = src - ms, dst - md
    U, S, Vt = np.linalg.svd(B.T @ A / len(src))
    D = np.eye(2)
    if np.linalg.det(U @ Vt) < 0:
        D[1, 1] = -1
    R = U @ D @ Vt
    s = (S * np.diag(D)).sum() / A.var(0).sum() if scale else 1.0
    t = md - s * R @ ms
    return s, R, t


def ray_hits(o, d, segs):
    """Distances along ray o + t*d (t>0) to every segment in segs (N,2,2)."""
    p, q = segs[:, 0], segs[:, 1]
    e = q - p
    den = d[0] * e[:, 1] - d[1] * e[:, 0]
    with np.errstate(divide='ignore', invalid='ignore'):
        t = ((p[:, 0] - o[0]) * e[:, 1] - (p[:, 1] - o[1]) * e[:, 0]) / den
        u = ((p[:, 0] - o[0]) * d[1] - (p[:, 1] - o[1]) * d[0]) / den
    ok = (np.abs(den) > 1e-12) & (t > 0) & (u >= 0) & (u <= 1)
    return t[ok]


# ------------------------------------------------------------------ OpenF1
def openf1():
    import pandas as pd
    from services.openf1_comparison import historical, resolve
    s = resolve(*SESSION)
    key = int(s['session_key'])
    drivers = historical('drivers', {'session_key': key})
    laps = pd.DataFrame(historical('laps', {'session_key': key}))
    laps['start'] = pd.to_datetime(laps.date_start, utc=True, format='ISO8601', errors='coerce')
    laps['lap_duration'] = pd.to_numeric(laps.lap_duration, errors='coerce')
    cars = {}
    for d in drivers:
        num = int(d['driver_number'])
        loc = pd.DataFrame(historical('location', {'session_key': key, 'driver_number': num}))
        t = pd.to_datetime(loc.date, utc=True, format='ISO8601', errors='coerce')
        ok = t.notna() & ~((loc.x == 0) & (loc.y == 0))
        ts = (t[ok].astype('int64') / 1e9).to_numpy(float)
        o = np.argsort(ts)
        cars[num] = dict(code=d.get('name_acronym'), t=ts[o], x=loc.x[ok].to_numpy(float)[o] / 10,
                         y=loc.y[ok].to_numpy(float)[o] / 10, z=loc.z[ok].to_numpy(float)[o] / 10)
    # Clean laps: timed, not pit in/out, within 7 % of the driver's best (race pace, no safety car).
    clean = []
    for num, g in laps.dropna(subset=['lap_duration', 'start']).groupby('driver_number'):
        best = g.lap_duration.min()
        for _, lap in g.iterrows():
            if lap.lap_duration <= best * 1.07 and not lap.get('is_pit_out_lap') and int(num) in cars:
                clean.append((int(num), lap.start.value / 1e9, float(lap.lap_duration)))
    fl = laps.dropna(subset=['lap_duration']).sort_values('lap_duration').iloc[0]
    fastest = (int(fl.driver_number), fl.start.value / 1e9, float(fl.lap_duration))
    return key, cars, clean, fastest


def lap_points(cars, num, t0, dur):
    c = cars[num]
    m = (c['t'] >= t0) & (c['t'] <= t0 + dur)
    return np.c_[c['x'][m], c['y'][m], c['z'][m]], c['t'][m]


# ------------------------------------------------------------------ main
def main():
    nodes, ways, rels = load_osm()
    proj, origin = projector(nodes)
    loop_ids = ['152483595', '1553605580']
    loop = proj(chain(loop_ids, ways))
    if np.allclose(loop[0], loop[-1]):
        loop = loop[:-1]
    pit = proj(chain(['1037707300', '196193732'], ways))
    road = rings(rels['18052714'], ways)
    road_rings = {k: [proj(r) for r in v] for k, v in road.items()}

    key, cars, clean, fastest = openf1()
    fl, flt = lap_points(cars, *fastest)
    print(f'OpenF1 session {key}: {len(cars)} cars, {len(clean)} clean laps, fastest #{fastest[0]} {fastest[2]:.3f}s, '
          f'path {np.sum(np.hypot(*np.diff(fl[:, :2], axis=0).T)):.0f} m')

    # Every clean-lap sample (x, y, z) of every car: alignment target and on-road check.
    cloud = np.vstack([lap_points(cars, *c)[0] for c in clean])
    print(f'{len(cloud)} clean-lap samples')

    # ---- align the OSM centreline to the cloud (rotation + translation + scale), trying both directions/mirror.
    cl, osm_len = resample(loop, STEP)
    tree = cKDTree(cloud[:, :2])
    best = None
    for mirror in (False, True):
        src0 = cl * ([1, -1] if mirror else [1, 1])
        for ang in np.radians(np.arange(0, 360, 6)):
            R0 = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
            s, R, t = 1.0, R0, cloud[:, :2].mean(0) - (R0 @ src0.mean(0))
            for _ in range(40):
                cur = (s * (R @ src0.T)).T + t
                dist, idx = tree.query(cur)
                keep = dist < np.percentile(dist, 90) + 1
                s, R, t = umeyama(src0[keep], cloud[idx[keep], :2])
            cur = (s * (R @ src0.T)).T + t
            err = float(np.median(tree.query(cur)[0]))
            if best is None or err < best[0]:
                best = (err, mirror, s, R, t)
    err, mirror, s, R, t = best
    print(f'OSM->OpenF1: mirror={mirror} scale={s:.5f} rot={math.degrees(math.atan2(R[1, 0], R[0, 0])):.2f} deg '
          f'median centreline-to-nearest-sample {err:.2f} m')
    M = lambda p: (s * (R @ (np.asarray(p) * ([1, -1] if mirror else [1, 1])).T)).T + t
    # Scale is fitted only as a check (map and positions are both metric); apply rotation + translation at scale 1.
    s_fit = s
    s = 1.0
    if mirror:
        raise SystemExit('Unexpected mirror between OSM and OpenF1.')
    # re-solve translation/rotation at fixed scale 1
    src0 = cl
    for _ in range(40):
        cur = (R @ src0.T).T + t
        dist, idx = tree.query(cur)
        keep = dist < np.percentile(dist, 90) + 1
        _, R, t = umeyama(src0[keep], cloud[idx[keep], :2], scale=False)
    centre = (R @ cl.T).T + t

    # Driving direction must match the cars (clockwise at Lusail).
    fl_tree = cKDTree(centre)
    _, ia = fl_tree.query(fl[len(fl) // 4, :2])
    _, ib = fl_tree.query(fl[len(fl) // 4 + 8, :2])
    if ((ib - ia) % len(centre)) > len(centre) / 2:
        centre = centre[::-1]
    area = 0.5 * np.sum(centre[:, 0] * np.roll(centre[:, 1], -1) - np.roll(centre[:, 0], -1) * centre[:, 1])
    # Start index 0 at the timing line: where the fastest lap begins (OpenF1 lap start = control line crossing).
    _, i0 = cKDTree(centre).query(fl[0, :2])
    centre = np.roll(centre, -i0, axis=0)
    centre, length = resample(centre, STEP)
    n = len(centre)
    print(f'centreline {length:.1f} m (FIA 5419 m, {100 * (length / FIA_LENGTH - 1):+.2f} %), '
          f'{"clockwise" if area < 0 else "anticlockwise"}, {n} stations')

    tan = tangents(centre)
    nor = np.c_[-tan[:, 1], tan[:, 0]]            # left of the driving direction
    S = np.arange(n) * (length / n)

    # ---- elevation: median sample z per station (+-3 m), smoothed.
    ctree = cKDTree(centre)
    dist, idx = ctree.query(cloud[:, :2])
    z = np.full(n, np.nan)
    for i in range(n):
        pass
    order = np.argsort(idx)
    zs = cloud[order, 2]
    bounds = np.searchsorted(idx[order], np.arange(n + 1))
    for i in range(n):
        a, b = bounds[i], bounds[i + 1]
        if b > a:
            z[i] = np.median(zs[a:b])
    ok = ~np.isnan(z)
    z = np.interp(np.arange(n), np.arange(n)[ok], z[ok], period=n)
    z = smooth_closed(z, 15)
    zmin = float(z.min())
    print(f'elevation range {z.max() - zmin:.1f} m (min {zmin:.1f} in the OpenF1 frame)')

    # ---- road edges: normal rays against the OSM asphalt polygon (outer ring = outside of the track ribbon,
    # inner rings = infield islands). Distances capped where the ray runs into the pit lane / another section.
    allsegs = []
    for role in ('outer', 'inner'):
        for rg in road_rings[role]:
            p = (R @ rg.T).T + t
            allsegs.append(np.stack([p[:-1], p[1:]], axis=1))
    segs = np.concatenate(allsegs)
    left = np.zeros(n)
    right = np.zeros(n)
    for i in range(n):
        for side, arr in ((1, left), (-1, right)):
            h = ray_hits(centre[i], nor[i] * side, segs)
            arr[i] = h.min() if len(h) else np.nan
    raw_left, raw_right = left.copy(), right.copy()
    # Rays that leave through a junction (pit entry/exit, service roads) report silly widths: limit and fill.
    for arr in (left, right):
        bad = np.isnan(arr) | (arr > 12) | (arr < 3)
        arr[bad] = np.nan
        ok = ~np.isnan(arr)
        arr[:] = np.interp(np.arange(n), np.arange(n)[ok], arr[ok], period=n)
        arr[:] = smooth_closed(arr, 9)
    width = left + right
    print(f'asphalt width from OSM polygon: median {np.median(width):.1f} m, p5 {np.percentile(width, 5):.1f}, '
          f'p95 {np.percentile(width, 95):.1f}; {int(np.sum(np.isnan(raw_left) | np.isnan(raw_right)))} stations filled')

    # ---- check: every clean-lap sample's lateral offset vs the edges (car half-width 0.95 m).
    lat = np.einsum('ij,ij->i', cloud[:, :2] - centre[idx], nor[idx])
    over_l = lat - (left[idx] - 0.95)
    over_r = -lat - (right[idx] - 0.95)
    over = np.maximum(over_l, over_r)
    print(f'samples with the car body over the edge: {100 * np.mean(over > 0):.2f} % (> 1 m over: {100 * np.mean(over > 1):.2f} %), '
          f'p99 lateral |offset| {np.percentile(np.abs(lat), 99):.1f} m')
    env_lo = np.full(n, np.nan)
    env_hi = np.full(n, np.nan)
    lat_o = lat[order]
    for i in range(n):
        a, b = bounds[i], bounds[i + 1]
        if b - a > 20:
            env_lo[i], env_hi[i] = np.percentile(lat_o[a:b], [1, 99])

    # ---- curvature + corners (signed: +left / -right), apex = curvature peak.
    head = np.unwrap(np.arctan2(tan[:, 1], tan[:, 0]))
    w = 6
    dh = np.roll(head, -w) - np.roll(head, w)
    dh = (dh + np.pi) % (2 * np.pi) - np.pi
    kappa = smooth_closed(dh / (2 * w * STEP), 5)

    # ---- pit lane (OSM) in the frame, ordered entry -> exit
    pitp = (R @ pit.T).T + t
    _, pa = ctree.query(pitp[0])
    _, pb = ctree.query(pitp[-1])
    pit_res, pit_len = resample(pitp, STEP, closed=False)

    def poly(p):
        return np.round((R @ p.T).T + t, 2).tolist()

    feats = dict(buildings=[], grandstands=[], bleachers=[], fences=[], walls=[], sand=[], grass=[], service_roads=[])
    for wid, w_ in ways.items():
        tg = w_['tags']
        if len(w_['nd']) < 2:
            continue
        try:
            p = proj(w_['nd'])
        except Exception:
            continue
        if len(p) < 2:
            continue
        cen = (R @ p.mean(0)) + t
        if np.min(np.hypot(*(centre - cen).T)) > 450:
            continue
        rec = dict(id=wid, pts=poly(p))
        if tg.get('building') == 'grandstand':
            feats['grandstands'].append(rec)
        elif 'building' in tg:
            rec['levels'] = tg.get('building:levels')
            rec['height'] = tg.get('height')
            rec['kind'] = tg.get('building')
            feats['buildings'].append(rec)
        elif tg.get('leisure') == 'bleachers':
            feats['bleachers'].append(rec)
        elif tg.get('barrier') == 'fence':
            feats['fences'].append(rec)
        elif tg.get('barrier') == 'wall':
            feats['walls'].append(rec)
        elif tg.get('natural') == 'sand':
            feats['sand'].append(rec)
        elif tg.get('landuse') in ('grass', 'greenery'):
            feats['grass'].append(rec)
        elif tg.get('highway') in ('service', 'unclassified') and len(p) > 3:
            feats['service_roads'].append(rec)
    for rid, rel in rels.items():
        kind = rel['tags'].get('natural') or rel['tags'].get('landuse')
        if kind in ('sand', 'grass') and rel['tags'].get('type') == 'multipolygon':
            rr = rings(rel, ways)
            for ring in rr['outer']:
                p = proj(ring)
                if len(p) >= 3 and np.min(np.hypot(*(centre - ((R @ p.mean(0)) + t)).T)) < 450:
                    feats['sand' if kind == 'sand' else 'grass'].append(dict(id=rid, pts=poly(p),
                                                                           holes=[poly(proj(h)) for h in rr['inner']]))
    print({k: len(v) for k, v in feats.items()})

    out = dict(
        version=1,
        frame='OpenF1 position frame / 10 (metres), z relative to the lowest centreline point',
        z_offset=round(zmin, 3),
        sources=dict(
            osm=dict(extract='2026-11-25, api.openstreetmap.org bbox 51.440,25.476,51.462,25.498', licence='ODbL 1.0',
                     attribution='(c) OpenStreetMap contributors', centreline_ways=loop_ids, road_polygon='relation 18052714',
                     pit_ways=['1037707300', '196193732'], projection_origin=[round(origin[0], 6), round(origin[1], 6)]),
            openf1=dict(session=f'{SESSION[0]} {SESSION[1]} {SESSION[2]}', session_key=key, cars=len(cars), clean_laps=len(clean),
                        use='alignment, elevation and on-road check only'),
            fia='Circuit map Qatar 2025, version 2, issued 27.11.25 (centreline length 5.419 km, sector/speed-trap/DRS distances)'),
        fit=dict(scale_check=round(s_fit, 5), rotation_deg=round(math.degrees(math.atan2(R[1, 0], R[0, 0])), 3),
                 translation=np.round(t, 3).tolist(), median_err_m=round(err, 3)),
        length=round(length, 2), step=round(length / n, 4),
        centre=dict(x=np.round(centre[:, 0], 2).tolist(), y=np.round(centre[:, 1], 2).tolist(), z=np.round(z - zmin, 3).tolist()),
        edges=dict(left=np.round(left, 2).tolist(), right=np.round(right, 2).tolist()),
        envelope=dict(lo=[None if np.isnan(v) else round(float(v), 2) for v in env_lo],
                      hi=[None if np.isnan(v) else round(float(v), 2) for v in env_hi]),
        curvature=np.round(kappa, 5).tolist(),
        pit=dict(x=np.round(pit_res[:, 0], 2).tolist(), y=np.round(pit_res[:, 1], 2).tolist(), length=round(pit_len, 1),
                 entry_station=int(pa), exit_station=int(pb)),
        features=feats,
    )
    OUT.write_text(json.dumps(out), encoding='utf-8')
    print('wrote', OUT.relative_to(ROOT), f'{OUT.stat().st_size / 1e6:.2f} MB')


if __name__ == '__main__':
    main()
