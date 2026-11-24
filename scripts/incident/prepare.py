"""Turn OpenF1 lap-1 CSVs into a ready-to-animate reconstruction (no Blender needed).

Usage (from C:\\f1hud_app):
  .\\.venv\\Scripts\\python.exe scripts\\incident\\prepare.py scripts\\incident\\mexico2026_t4.json

Writes <work>/prepared.json: the lap line, a stylised track (centre, edges, kerbs), and per-car
position/heading/telemetry every 1/100 s. Positions along the lap come from the timing data;
side-by-side (lateral) positions come from the config, because the feed snaps both cars to one line.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d

ROOT = Path(__file__).absolute().parents[2]
STEP = 0.01  # seconds


def ts(value):
    return datetime.fromisoformat(value).timestamp()


def read_positions(path, t0):
    rows = [(ts(r['date']) - t0, float(r['x']) / 10, float(r['y']) / 10, float(r['z']) / 10) for r in csv.DictReader(open(path))]
    return np.array(rows)


def read_car(path, t0):
    out = []
    for r in csv.DictReader(open(path)):
        out.append((ts(r['date']) - t0, float(r['speed'] or 0), float(r['throttle'] or 0), float(r['brake'] or 0), float(r['n_gear'] or 0)))
    return np.array(out)


def resample_loop(xy, z, step=1.0):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    s = np.arange(0, d[-1], step)
    pts = np.column_stack([np.interp(s, d, xy[:, 0]), np.interp(s, d, xy[:, 1])])
    zz = np.interp(s, d, z)
    return s, pts, zz


def normals(pts):
    t = np.gradient(pts, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    return t, np.column_stack([t[:, 1], -t[:, 0]])  # right-hand normal


def main(config_path):
    cfg = json.loads(Path(config_path).read_text(encoding='utf-8'))
    data = ROOT / cfg['data_dir']
    work = data / 'work'
    work.mkdir(parents=True, exist_ok=True)
    t0 = ts(cfg['race_start_utc'])
    ref = cfg['lap_reference']
    cars = {n: read_positions(data / f'mexico2026_lap1_{n}.csv', t0) for n in cfg['drivers']}
    tele = {n: read_car(data / f'mexico2026_lap1_{n}_car.csv', t0) for n in cfg['drivers']}

    # 1) Lap line: the reference car's first lap, from its grid slot back to the same place.
    r = cars[ref]
    keep = np.r_[True, np.linalg.norm(np.diff(r[:, 1:3], axis=0), axis=1) > 0.05]
    r = r[keep]
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(r[:, 1:3], axis=0), axis=1))]
    start = r[0, 1:3]
    far = np.where(d > 1000)[0]
    back = far[np.argmin(np.linalg.norm(r[far, 1:3] - start, axis=1))]
    lap = r[:back + 1]
    s, line, z = resample_loop(lap[:, 1:3], lap[:, 3])
    n = len(s)
    L = float(s[-1] + np.linalg.norm(line[-1] - line[0]))
    line = np.column_stack([gaussian_filter1d(line[:, 0], 2.5, mode='wrap'), gaussian_filter1d(line[:, 1], 2.5, mode='wrap')])
    z = gaussian_filter1d(z, 40, mode='wrap')
    z -= z.min()
    origin = line[int(np.argmin(np.abs(s - cfg['corners']['T4'])))].copy()
    line -= origin
    tan, nor = normals(line)
    head = np.unwrap(np.arctan2(tan[:, 1], tan[:, 0]))
    curv = gaussian_filter1d(np.gradient(head) / np.gradient(s), 4, mode='wrap')  # + left, - right

    # 2) Stylised track: the racing line sits near the inside edge at each apex, so shift the
    #    centre towards the outside in proportion to how tight the corner is.
    hw = float(cfg['track_half_width'])
    g = np.clip(np.abs(curv) / 0.022, 0, 1)
    g = gaussian_filter1d(g, 10, mode='wrap')
    shift = np.sign(curv) * (hw - 1.3) * g
    shift = gaussian_filter1d(shift, 6, mode='wrap')
    centre = line + nor * shift[:, None]
    left = centre - nor * hw
    right = centre + nor * hw
    kerb_l = gaussian_filter1d((curv > 0) * g, 3, mode='wrap') > 0.35   # inside of left-handers
    kerb_r = gaussian_filter1d((curv < 0) * g, 3, mode='wrap') > 0.35
    kerb_lo = gaussian_filter1d((curv < 0) * g, 3, mode='wrap') > 0.55  # exit kerbs on the outside
    kerb_ro = gaussian_filter1d((curv > 0) * g, 3, mode='wrap') > 0.55

    def at(arr, ss):
        ss = np.mod(ss, L)
        return np.column_stack([np.interp(ss, s, arr[:, i], period=L) for i in range(arr.shape[1])]) if arr.ndim == 2 else np.interp(ss, s, arr, period=L)

    # 3) Cars: distance along the lap line from each position sample, cleaned and made monotone.
    tree_pts = line + origin
    out_cars = {}
    T = np.arange(0, float(min(c[-1, 0] for c in cars.values())), STEP)
    for num, c in cars.items():
        prev = None
        ss = []
        for x, y in c[:, 1:3]:
            dd = np.linalg.norm(tree_pts - (x, y), axis=1)
            if prev is not None:  # stay near the last match so a lap later never wins
                window = np.abs(((s - prev + L / 2) % L) - L / 2) < 120
                dd = np.where(window, dd, np.inf)
            i = int(np.argmin(dd))
            j = (i + 1) % n
            seg = tree_pts[j] - tree_pts[i]
            k = float(np.clip(np.dot((x, y) - tree_pts[i], seg) / max(np.dot(seg, seg), 1e-9), 0, 1))
            cur = s[i] + k * (s[j] - s[i] if j else (L - s[i]))
            if prev is not None:
                while cur < prev - L / 2:
                    cur += L
            ss.append(cur)
            prev = cur % L if prev is None else cur
            prev = cur
        ss = np.array(ss)
        tt = c[:, 0]
        # Drop samples implying an impossible speed against the car's own speed trace (feed glitches).
        v_meas = np.interp(tt, tele[num][:, 0], tele[num][:, 1]) / 3.6
        good = np.ones(len(ss), bool)
        for i in range(1, len(ss) - 1):
            dt = tt[i + 1] - tt[i - 1]
            if dt > 0 and abs((ss[i + 1] - ss[i - 1]) / dt - v_meas[i]) > max(8, 0.35 * v_meas[i]):
                good[i] = False
        tt, ss = tt[good], np.maximum.accumulate(ss[good])
        if ss[0] > L / 2:  # grid slot behind the line
            ss = ss - L
        # Side-by-side offsets (config), smoothed along the lap, and how much longer/shorter the
        # driven path is than the lap line there (a cut across a corner is much shorter).
        keys = np.array(cfg['lateral'][num], dtype=float)
        lat_s = gaussian_filter1d(np.interp(s, keys[:, 0], keys[:, 1]), 4, mode='wrap')
        driven = line + nor * lat_s[:, None]
        dA = np.linalg.norm(np.roll(driven, -1, axis=0) - driven, axis=1) / np.maximum(np.diff(np.r_[s, L]), 1e-6)
        dA = np.clip(dA, 0.25, 3)
        # Integrate the car's own speed trace along that driven path, then pull it onto the timing
        # samples slowly. Samples inside a scripted off-track section are skipped: the feed keeps the
        # car on the racing line there, which is exactly what we are correcting.
        v = np.interp(T, tele[num][:, 0], tele[num][:, 1]) / 3.6
        skip = np.zeros(len(tt), bool)
        for zone in cfg.get('off_track', []):
            if zone['car'] == num:
                skip |= (np.mod(ss, L) > zone['s_from'] - 10) & (np.mod(ss, L) < zone['s_to'] + 45)
        resid = np.zeros(len(T))
        for _ in range(4):  # the path stretch depends on where the car really is: iterate
            s_int = np.empty(len(T)); s_int[0] = ss[0]
            for k in range(1, len(T)):
                s_int[k] = s_int[k - 1] + v[k - 1] * STEP / np.interp((s_int[k - 1] + resid[k - 1]) % L, s, dA)
            keep_t, keep_r = tt[~skip], ss[~skip] - np.interp(tt[~skip], T, s_int)
            resid = gaussian_filter1d(np.interp(T, keep_t, keep_r), 0.8 / STEP)
        s_final = np.maximum.accumulate(s_int + resid)
        lat = np.interp(np.mod(s_final, L), s, lat_s)
        base = at(line, s_final)
        nn = at(nor, s_final)
        nn /= np.linalg.norm(nn, axis=1, keepdims=True)
        pos = base + nn * lat[:, None]
        pos_s = np.column_stack([gaussian_filter1d(pos[:, 0], 0.08 / STEP), gaussian_filter1d(pos[:, 1], 0.08 / STEP)])
        vel = np.gradient(pos_s, STEP, axis=0)
        yaw = np.unwrap(np.arctan2(vel[:, 1], vel[:, 0]))
        moving = np.linalg.norm(vel, axis=1) > 0.5
        yaw = np.where(moving, yaw, yaw[np.argmax(moving)] if moving.any() else 0)
        zc = at(z, s_final)
        tl = tele[num]
        out_cars[num] = dict(
            s=s_final.round(3).tolist(), x=pos_s[:, 0].round(3).tolist(), y=pos_s[:, 1].round(3).tolist(), z=zc.round(3).tolist(),
            yaw=yaw.round(4).tolist(), lateral=lat.round(3).tolist(),
            speed=np.interp(T, tl[:, 0], tl[:, 1]).round(1).tolist(), throttle=np.interp(T, tl[:, 0], tl[:, 2]).round(0).tolist(),
            brake=(np.interp(T, tl[:, 0], tl[:, 3]) > 50).astype(int).tolist(), gear=np.interp(T, tl[:, 0], tl[:, 4]).round(0).astype(int).tolist(),
            check=dict(removed_samples=int((~good).sum()), max_speed_error_kmh=float(np.abs(np.linalg.norm(vel, axis=1) - v)[int(1 / STEP):int(60 / STEP)].max() * 3.6)))

    # 4) Facts for the captions, measured from the data.
    def brake_on(num, t_from, t_to):
        tl = tele[num]
        m = (tl[:, 0] >= t_from) & (tl[:, 0] <= t_to) & (tl[:, 3] > 50)
        i = int(np.argmax(m))
        return float(tl[i, 0]), float(tl[max(i - 1, 0), 1])

    def s_at(num, t):
        return float(np.interp(t, T, out_cars[num]['s']))

    def time_gap(lead, chase, t):
        """Seconds until the chasing car reaches where the leading car is at time t."""
        target = s_at(lead, t)
        return float(np.interp(target, out_cars[chase]['s'], T) - t)

    other = [k for k in cfg['drivers'] if k != ref][0]
    h1, h1v = brake_on(ref, 12, 16)
    l1, l1v = brake_on(other, 12, 16)
    h4, h4v = brake_on(ref, 29, 33)
    l4, l4v = brake_on(other, 29, 33)
    facts = dict(
        t1_brake_gap=l1 - h1, t4_brake_gap=l4 - h4,
        ham_t4_brake_speed=int(round(h4v)), lec_t4_brake_speed=int(round(l4v)),
        gap_t3=s_at(ref, 25.5) - s_at(other, 25.5), gap_t4=abs(s_at(ref, h4) - s_at(other, h4)),
        lec_vmax=int(max(cars_v for tt_, cars_v, *_ in tele[other] if 26 <= tt_ <= 32)),
        ham_vmax=int(max(cars_v for tt_, cars_v, *_ in tele[ref] if 26 <= tt_ <= 32)),
        gap_after=time_gap(other, ref, 41.0))
    track = dict(length=L, half_width=hw, s=s.round(2).tolist(), line=line.round(3).tolist(), centre=centre.round(3).tolist(),
                 left=left.round(3).tolist(), right=right.round(3).tolist(), z=z.round(3).tolist(), curv=curv.round(5).tolist(),
                 kerbs=dict(left=kerb_l.astype(int).tolist(), right=kerb_r.astype(int).tolist(),
                            left_out=kerb_lo.astype(int).tolist(), right_out=kerb_ro.astype(int).tolist()),
                 origin_openf1_m=origin.round(2).tolist())
    out = dict(step=STEP, t=T.round(3).tolist(), track=track, cars=out_cars, facts=facts)
    (work / 'prepared.json').write_text(json.dumps(out), encoding='utf-8')
    print('Lap line', round(L, 1), 'm,', len(T), 'samples')
    for k, v in facts.items():
        print(f'  {k}: {v:.3f}' if isinstance(v, float) else f'  {k}: {v}')
    for num, c in out_cars.items():
        print(f"  #{num}: removed {c['check']['removed_samples']} glitchy samples, max speed mismatch {c['check']['max_speed_error_kmh']:.1f} km/h")
    print('Saved', work / 'prepared.json')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'scripts' / 'incident' / 'mexico2026_t4.json')
