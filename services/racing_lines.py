"""Reconstructed racing lines for the 3D Broadcast: lateral placement only, timing untouched.

Why: F1's position feed (and OpenF1, which relays it) snaps every car onto practically the same line. On the 2025 Abu
Dhabi race, cars within 8 m of each other along the lap differ laterally by a median of 0.05 m, so a grid is drawn
single file and close racing makes cars drive through each other. Live timing-only sessions have no lateral data at all.

What this does (a pure function of the whole timeline, so every camera, any seek and any playback speed show the same
manoeuvre):
* Each car keeps its own distance along the lap at every instant (recorded coordinates or timing crossings): no car
  is ever moved forwards or backwards, so order, gaps and line-crossing times stay exactly as recorded.
* Only the lateral offset from the source line is reconstructed, and only where the source is ambiguous (on track,
  close to the snapped line). Pit lane, stops and off-track excursions keep their recorded position.
* Grid: before lights out, stationary cars are placed in staggered slots. The slot is taken from each car's own
  measured position (8 m per slot), so vacant slots keep the pattern; the pole side is the inside of the first corner.
* Close racing: when two footprints would overlap, the pair gets one side for the whole encounter (the car arriving
  from behind takes the inside of the next corner unless the data already separates them), the shift starts ~1.2 s
  before the overlap, is held while the cars overlap and blends back ~1.6 s after they are clear. The shift is the
  smallest that keeps 2.25 m between centres, split between the two cars and kept inside the usable road width.
* Where the road is too narrow for the cars involved, the overlap that remains is flagged as uncertain (q bit 2).

Output per car on a regular time grid: `o` (lateral offset, m, left positive, added to the source position along the
track normal) and `q` flags: 1 = adjusted, 2 = uncertain, 4 = grid reconstruction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

CAR_L = 5.6          # footprint length incl. a little margin (2026 cars ~5.5 m)
CAR_W = 1.9          # footprint width (2026 max width)
SEP = 2.25           # centre-to-centre lateral distance kept while footprints overlap longitudinally
NEAR = 10.0          # beyond this along-track gap two cars never need to move apart
HARD = CAR_L + 0.6   # at or below this gap they must be fully separated
ANTICIPATE_S = 1.2
RELEASE_S = 1.6
GRID_SLOT_M = 8.0
EDGE_MARGIN = 1.05   # car centre stays this far inside the asphalt edge


@dataclass
class Result:
    t: np.ndarray
    o: np.ndarray          # (C, K) float32
    q: np.ndarray          # (C, K) uint8
    codes: list
    meta: dict

    def window(self, t0: float, t1: float, step: float = 0.25):
        """Offsets resampled on [t0, t1] (inclusive) for the samples endpoint."""
        k0 = max(0, int(math.floor((t0 - self.t[0]) / self.meta['step'])) - 1)
        k1 = min(len(self.t), int(math.ceil((t1 - self.t[0]) / self.meta['step'])) + 2)
        if k1 <= k0:
            return None
        tt = self.t[k0:k1]
        cars = {}
        for i, c in enumerate(self.codes):
            o, q = self.o[i, k0:k1], self.q[i, k0:k1]
            if not np.any(o) and not np.any(q):
                continue
            cars[c] = dict(o=np.round(o, 2).tolist(), q=q.astype(int).tolist())
        return dict(t0=round(float(tt[0]), 3), step=self.meta['step'], cars=cars)


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _curvature(x, y):
    n = len(x)
    seg = max(0.5, float(np.mean(np.hypot(np.diff(x), np.diff(y)))))
    head = np.unwrap(np.arctan2(np.roll(y, -1) - y, np.roll(x, -1) - x))
    w = max(2, int(round(12 / seg)))
    dh = np.roll(head, -w) - np.roll(head, w)
    dh = (dh + np.pi) % (2 * np.pi) - np.pi
    return dh / (2 * w * seg)


def _max_filter_time(a, back, fwd):
    """Running max over [k-back, k+fwd] along the last axis (back/fwd in samples)."""
    out = a.copy()
    for s_ in range(1, fwd + 1):
        out[..., :-s_] = np.maximum(out[..., :-s_], a[..., s_:])
    for s_ in range(1, back + 1):
        out[..., s_:] = np.maximum(out[..., s_:], a[..., :-s_])
    return out


def reconstruct(times, S, LR, keep_raw, track_s, track_len, curvature, edge_left, edge_right, step=0.25, pole_side=None, debug=None):
    """times (K,), S (C,K) cumulative lap distance (nan = no position), LR (C,K) source lateral (left positive),
    keep_raw (C,K) bool (pit lane / off track / trusted lateral). Track arrays per station: track_s, curvature,
    edge_left/right (asphalt half-widths). Returns (o, q, meta)."""
    C, K = S.shape
    L = float(track_len)
    present = ~np.isnan(S)
    pos = np.where(present, np.mod(np.nan_to_num(S), L), np.nan)
    st_idx = np.clip(np.searchsorted(track_s, np.nan_to_num(pos)) - 1, 0, len(track_s) - 1)
    lo = -(edge_right[st_idx] - EDGE_MARGIN)
    hi = edge_left[st_idx] - EDGE_MARGIN
    amb = present & ~keep_raw
    P = np.where(present, np.nan_to_num(LR), 0.0)          # preferred lateral (source line)
    q = np.zeros((C, K), np.uint8)
    meta = dict(step=step, launch=None, pole_side=None, grid_cars=0)

    # ---------------------------------------------------------------- grid before lights out
    V = np.zeros((C, K))
    if K > 2:
        V[:, 1:-1] = (np.nan_to_num(S[:, 2:]) - np.nan_to_num(S[:, :-2])) / (2 * step)
        V[~present] = 0
    moving = (V > 3) & amb
    still = (np.abs(V) < 0.5) & amb
    frac_m = moving.sum(0) / np.maximum(1, present.sum(0))
    frac_s = still.sum(0) / np.maximum(1, present.sum(0))
    w10 = int(round(10 / step))
    launch_k = None
    for k in range(w10, K - int(4 / step)):
        if frac_s[k - w10:k].mean() > 0.6 and frac_m[k:k + int(4 / step)].max() > 0.6 and frac_m[k - 1] < 0.3:
            launch_k = k
            break
    if launch_k is not None:
        meta['launch'] = round(float(times[launch_k]), 2)
        kk = max(0, launch_k - 2)
        grid = [c for c in range(C) if still[c, kk] and present[c, kk]]
        if len(grid) >= 4:
            front = max(grid, key=lambda c: pos[c, kk] if (pos[c, kk] < L * 0.5 or True) else -1)
            # the frontmost car in racing direction: the one with the largest distance to the others behind it
            def ahead(a, b):
                return ((pos[a, kk] - pos[b, kk] + L / 2) % L) - L / 2
            front = max(grid, key=lambda a: sum(ahead(a, b) > 0 for b in grid))
            if pole_side is None:
                ps = st_idx[front, kk]
                look = (np.arange(ps, ps + int(800 / max(1e-6, track_s[1] - track_s[0])))) % len(track_s)
                big = np.where(np.abs(curvature[look]) > 1 / 200)[0]
                pole_side = float(np.sign(curvature[look[big[0]]])) if len(big) else 1.0
            meta['pole_side'] = 'left' if pole_side > 0 else 'right'
            for c in grid:
                slot = int(round((ahead(front, c)) / GRID_SLOT_M))
                side = pole_side if slot % 2 == 0 else -pole_side
                k_end = launch_k
                # after the launch the grid lateral fades out over the first 250 m of the car's own run
                s0 = S[c, launch_k] if present[c, launch_k] else np.nan
                lat = side * np.minimum(3.0, np.minimum(hi[c], -lo[c]) - 0.4)
                g = np.zeros(K)
                g[:k_end] = 1.0
                if not np.isnan(s0):
                    run = np.nan_to_num(S[c, k_end:] - s0)
                    g[k_end:] = 1 - _smoothstep(run / 250.0)
                pre = still[c] | (np.arange(K) >= k_end)
                g = np.where(pre & amb[c], g, 0.0)
                P[c] = P[c] * (1 - g) + lat * g
                q[c][g > 0.01] |= 4
            meta['grid_cars'] = len(grid)

    # ---------------------------------------------------------------- pair proximity (vectorised over time)
    ia, ib = np.triu_indices(C, 1)
    ds = ((pos[ia] - pos[ib] + L / 2) % L) - L / 2               # a ahead of b if > 0
    both = amb[ia] & amb[ib]
    prox = np.where(both, _smoothstep((NEAR - np.abs(np.nan_to_num(ds, nan=1e9))) / (NEAR - HARD)), 0.0)
    back, fwd = int(round(RELEASE_S / step)), int(round(ANTICIPATE_S / step))
    W = _max_filter_time(prox, back, fwd)
    # smooth edges (0.5 s) so shifts ease in and out
    kern = np.ones(3) / 3
    W = np.apply_along_axis(lambda r: np.convolve(r, kern, mode='same'), 1, W) if W.size else W
    W = np.maximum(W, prox)
    active_pairs = np.where(W.max(1) > 0.01)[0] if W.size else np.array([], int)

    # ---------------------------------------------------------------- sides + per-instant minimal separation
    # Processed in time order over the whole timeline (deterministic). A pair gets its side when the encounter starts,
    # from where the two cars actually are at that moment (their previous reconstructed lateral), so all sides in a
    # pack come from one left-to-right order and can always be satisfied together; the side is then held until the
    # encounter ends. Equal laterals (the feed's single line) fall back to: the car arriving from behind takes the inside
    # of the next corner.
    o = np.zeros((C, K))
    side = np.zeros_like(W)
    held: dict[int, float] = {}
    prevA = P[:, 0].copy()
    busy_mask = (W[active_pairs].max(0) > 0.01) if len(active_pairs) else np.zeros(K, bool)
    for k in range(K):
        if not busy_mask[k]:
            held.clear()
            prevA = P[:, k].copy()
            continue
        pk = active_pairs[W[active_pairs, k] > 0.01]
        live = set(int(x) for x in pk)
        for gone in [x for x in held if x not in live]:
            del held[gone]
        for p_ in pk:
            p_ = int(p_)
            if p_ in held:
                continue
            a, b = ia[p_], ib[p_]
            dA = prevA[a] - prevA[b]
            if abs(dA) > 0.3:
                sgn = 1.0 if dA > 0 else -1.0
            else:
                attacker, defender = (b, a) if (ds[p_, k] > 0) else (a, b)
                st = st_idx[defender, k]
                look = (np.arange(st, st + 150)) % len(track_s)   # ~300 m ahead
                kap = curvature[look]
                j = int(np.argmax(np.abs(kap)))
                corner = float(np.sign(kap[j])) if abs(kap[j]) > 1 / 300 else 1.0
                sgn = corner if attacker == a else -corner
            held[p_] = sgn
        cars = np.unique(np.r_[ia[pk], ib[pk]])
        base = P[:, k].copy()
        A = base.copy()
        # start from where the cars were (continuity), pulled back towards their own line
        A[cars] = base[cars] + 0.85 * (prevA[cars] - P[cars, k - 1 if k else 0])
        need = W[pk, k] * SEP
        for _ in range(60):
            moved = 0.0
            for p_, r in zip(pk, need):
                a, b, s_ = ia[p_], ib[p_], held[int(p_)]
                side[p_, k] = s_
                v = r - s_ * (A[a] - A[b])
                if v <= 1e-3:
                    continue
                na, nb = np.clip(A[a] + s_ * v / 2, lo[a, k], hi[a, k]), np.clip(A[b] - s_ * v / 2, lo[b, k], hi[b, k])
                rest = v - s_ * ((na - A[a]) - (nb - A[b]))
                if rest > 1e-3:
                    nb = np.clip(nb - s_ * rest, lo[b, k], hi[b, k])
                    rest = v - s_ * ((na - A[a]) - (nb - A[b]))
                    if rest > 1e-3:
                        na = np.clip(na + s_ * rest, lo[a, k], hi[a, k])
                moved += abs(na - A[a]) + abs(nb - A[b])
                A[a], A[b] = na, nb
            # relax towards the own line where no constraint needs the shift (smallest adjustment)
            if moved < 1e-3:
                break
        o[cars, k] = A[cars] - base[cars]
        prevA = P[:, k] + o[:, k]
        for p_ in pk:
            a, b = ia[p_], ib[p_]
            if abs(ds[p_, k]) < CAR_L and abs(A[a] - A[b]) < CAR_W:
                q[a, k] |= 2
                q[b, k] |= 2

    if debug is not None:
        debug.update(ia=ia, ib=ib, W=W, side=side, prox=prox, ds=ds)
    o = o + (P - np.where(present, np.nan_to_num(LR), 0.0))      # grid lateral is part of the offset
    o[~amb] = 0.0
    q[np.abs(o) > 0.05] |= 1
    meta['uncertain_samples'] = int(np.count_nonzero(q & 2))
    meta['adjusted_samples'] = int(np.count_nonzero(q & 1))
    return o.astype(np.float32), q, meta


def from_recorded(cars: dict, track, edges=None, step: float = 0.25, t_range=None, pole_side=None) -> Result:
    """Recorded coordinates (per car t, x, y in the scene frame) -> reconstruction on a regular grid."""
    from scipy.spatial import cKDTree
    codes = list(cars)
    t_all = np.concatenate([np.asarray(cars[c]['t'], float) for c in codes])
    t0, t1 = (float(t_all.min()), float(t_all.max())) if t_range is None else t_range
    times = np.arange(t0, t1 + step / 2, step)
    X, Y = track.x, track.y
    tx, ty = np.gradient(X), np.gradient(Y)
    n = np.hypot(tx, ty)
    tx, ty = tx / n, ty / n
    kd = cKDTree(np.c_[X, Y])
    L = float(track.length)
    if edges is None:
        el = np.full(len(X), 7.0)
        er = np.full(len(X), 7.0)
    else:
        el, er = edges
    S = np.full((len(codes), len(times)), np.nan)
    LR = np.full_like(S, np.nan)
    keep = np.zeros(S.shape, bool)
    for i, c in enumerate(codes):
        t = np.asarray(cars[c]['t'], float)
        if len(t) < 2:
            continue
        x = np.interp(times, t, np.asarray(cars[c]['x'], float))
        y = np.interp(times, t, np.asarray(cars[c]['y'], float))
        gap = np.interp(times, t[1:], np.diff(t))
        inside = (times >= t[0]) & (times <= t[-1]) & (gap < 3.0)
        dist, j = kd.query(np.c_[x, y])
        lat = (x - X[j]) * -ty[j] + (y - Y[j]) * tx[j]
        s = track.s[j].astype(float)
        jumps = np.diff(s, prepend=s[0])
        s = s + L * np.cumsum(np.where(jumps < -L / 2, 1, np.where(jumps > L / 2, -1, 0)))
        S[i] = np.where(inside, s, np.nan)
        LR[i] = np.where(inside, lat, np.nan)
        # trusted / not ours to change: pit lane and off track (beyond the asphalt) keep the recorded position
        keep[i] = (lat > el[j] + 0.5) | (lat < -(er[j] + 0.5)) | (dist > 15)
    kappa = _curvature(X, Y)
    o, q, meta = reconstruct(times, S, LR, keep, track.s, L, kappa, el, er, step=step, pole_side=pole_side)
    return Result(times, o, q, codes, meta)


def from_estimated(samples: dict, track, times, edges=None, pole_side=None) -> Result:
    """Timing-only (estimated) cars: per car cumulative distance on a regular grid; source lateral = racing line."""
    codes = list(samples)
    S = np.array([np.asarray(samples[c], float) for c in codes]) if codes else np.zeros((0, len(times)))
    L = float(track.length)
    line = track.line
    pos = np.mod(np.nan_to_num(S), L)
    j = np.clip(np.searchsorted(track.s, pos) - 1, 0, len(track.s) - 1)
    LR = np.where(np.isnan(S), np.nan, line[j])
    keep = np.zeros(S.shape, bool)
    el, er = edges if edges is not None else (np.full(len(track.x), 7.0), np.full(len(track.x), 7.0))
    kappa = _curvature(track.x, track.y)
    step = float(times[1] - times[0]) if len(times) > 1 else 0.25
    o, q, meta = reconstruct(np.asarray(times), S, LR, keep, track.s, L, kappa, el, er, step=step, pole_side=pole_side)
    return Result(np.asarray(times), o, q, codes, meta)


def footprint_overlaps(times, xs, ys, hs, codes):
    """Count instants where two car footprints (oriented boxes CAR_L x CAR_W) intersect. xs/ys/hs: (C, K)."""
    C, K = xs.shape
    hits = []
    for k in range(K):
        for a in range(C):
            if np.isnan(xs[a, k]):
                continue
            for b in range(a + 1, C):
                if np.isnan(xs[b, k]):
                    continue
                dx, dy = xs[b, k] - xs[a, k], ys[b, k] - ys[a, k]
                if dx * dx + dy * dy > 49:
                    continue
                if _obb_overlap(xs[a, k], ys[a, k], hs[a, k], xs[b, k], ys[b, k], hs[b, k]):
                    hits.append((float(times[k]), codes[a], codes[b]))
    return hits


def _obb_overlap(x1, y1, h1, x2, y2, h2, l=CAR_L - 0.4, w=CAR_W - 0.1):
    axes = [(math.cos(h1), math.sin(h1)), (-math.sin(h1), math.cos(h1)), (math.cos(h2), math.sin(h2)), (-math.sin(h2), math.cos(h2))]

    def corners(x, y, h):
        c, s = math.cos(h), math.sin(h)
        return [(x + c * dx - s * dy, y + s * dx + c * dy) for dx, dy in ((l / 2, w / 2), (l / 2, -w / 2), (-l / 2, w / 2), (-l / 2, -w / 2))]
    A, B = corners(x1, y1, h1), corners(x2, y2, h2)
    for ax, ay in axes:
        pa = [px * ax + py * ay for px, py in A]
        pb = [px * ax + py * ay for px, py in B]
        if max(pa) < min(pb) or max(pb) < min(pa):
            return False
    return True


def venue_edges(event: str, track):
    """Real asphalt half-widths for a scene track when the event has a bundled outline with edges in the F1 frame
    (Lusail), mapped through the scene's frame offset; None otherwise (the generic 7 m half-width is used)."""
    if getattr(track, 'edges_lr', None) is not None:
        return track.edges_lr
    from services import scene3d as sc
    o = sc._bundled_outline(event or '')
    if not o or not o.get('edges') or o.get('frame') != 'f1' or not getattr(track, 'frame', None):
        return None
    from scipy.spatial import cKDTree
    fx, fy = track.frame[0], track.frame[1]
    pts = np.c_[np.asarray(o['x'], float) / 10 - fx, np.asarray(o['y'], float) / 10 - fy]
    d, j = cKDTree(pts).query(np.c_[track.x, track.y])
    if float(np.median(d)) > 6:
        return None
    return np.asarray(o['edges']['left'], float)[j], np.asarray(o['edges']['right'], float)[j]
