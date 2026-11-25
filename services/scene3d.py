"""3D Broadcast: one shared race world for the Live page.

Every car lives in the same scene at the same session instant (the open recording's clock). Two position sources:

* ``estimated`` (always available, works live with the free recorder): each car's distance along the lap is
  interpolated between the moments the timing feed says it crossed a mini-sector, a sector line or the finish
  line. Between two crossings the car follows a representative lap's time-to-distance profile, so it slows for
  corners. Where the mini-sectors sit on the lap is calibrated from the recording itself. Nothing here comes from
  the classification order: a car is placed only from its own crossings, so a lapped car sits where it really is.
* ``recorded``: timestamped per-driver coordinates (OpenF1 ``location``, ~4 Hz, x/y/z) for the *same* session the
  recording holds, matched by meeting, session name and local start time. The circuit is drawn from the same
  data (the fastest lap), so cars and track share one origin, scale and orientation.

Classification, laps and the official interval always come from the timing feed (as step series), never from
positions. Units in the scene: metres; x east, y north, z up (z = 0 at the lowest point of the circuit).
"""
from __future__ import annotations

import json
import math
import threading
import time
from bisect import bisect_right
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from services import live_timing as lt

ROOT = Path(__file__).resolve().parents[1]
BUNDLED = ROOT / 'frontend' / 'src' / 'hype' / 'circuits'
STEP_M = 2.0              # centreline spacing
EXTRAPOLATE_S = 12.0      # beyond the newest crossing a car keeps moving at most this long, then holds (stale)
LINE_HALF_WIDTH = 5.4    # racing line stays this far from the centreline at most (asphalt is 14 m wide)
HOLD_GAP_S = 45.0         # crossings further apart than this are not bridged (garage, stopped car)
SESSION_CODES = {'race': 'R', 'qualifying': 'Q', 'sprint': 'S', 'sprint qualifying': 'SQ', 'sprint shootout': 'SQ',
                 'practice 1': 'FP1', 'practice 2': 'FP2', 'practice 3': 'FP3'}


# ------------------------------------------------------------------ geometry

def _smooth_closed(a: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return a
    pad = np.r_[a[-k:], a, a[:k]]
    ker = np.ones(k) / k
    out = np.convolve(pad, ker, mode='same')
    return out[k:-k]


def _resample_closed(x, y, z=None, step: float = STEP_M):
    x, y = np.asarray(x, float), np.asarray(y, float)
    z = np.zeros_like(x) if z is None else np.asarray(z, float)
    xs, ys, zs = np.r_[x, x[0]], np.r_[y, y[0]], np.r_[z, z[0]]
    d = np.r_[0, np.cumsum(np.hypot(np.diff(xs), np.diff(ys)))]
    length = float(d[-1])
    n = max(64, int(round(length / step)))
    grid = np.linspace(0, length, n, endpoint=False)
    return np.interp(grid, d, xs), np.interp(grid, d, ys), np.interp(grid, d, zs), length


class Track:
    """Closed centreline at ~2 m spacing, index 0 = finish line, in driving order."""

    def __init__(self, x, y, z, source: str, pit: list[list[float]] | None = None, pit_frac: dict | None = None,
                 frame: tuple | None = None, edges: tuple | None = None):
        """frame: (dx, dy, dz) when the scene is the F1 position frame (OpenF1 / FastF1 x, y, z in metres) minus this
        offset, so venue models in that frame can be placed exactly; None when unknown (rotated outlines).
        edges: (x, y, left, right) asphalt half-widths measured along a reference centreline; the racing line then stays
        inside the real edges instead of a fixed +-LINE_HALF_WIDTH corridor."""
        x, y, z, length = _resample_closed(x, y, z)
        x, y = _smooth_closed(x, 5), _smooth_closed(y, 5)
        z = _smooth_closed(z, 25)
        self.x, self.y, self.z = x, y, z
        seg = np.hypot(np.roll(x, -1) - x, np.roll(y, -1) - y)
        self.length = float(seg.sum()) or length
        self.s = np.r_[0, np.cumsum(seg)[:-1]]
        self.source = source
        self.pit = pit
        self.pit_frac = pit_frac
        self.frame = tuple(round(float(v), 3) for v in frame) if frame is not None else None
        lo = hi = None
        self.edges_lr = None
        if edges is not None:
            ex, ey, el, er = (np.asarray(a, float) for a in edges)
            idx = np.argmin((x[:, None] - ex[None, :]) ** 2 + (y[:, None] - ey[None, :]) ** 2, axis=1)
            hi, lo = el[idx] - 1.3, -(er[idx] - 1.3)     # car centre at least 1.3 m inside the edge
        self.edges_lr = (el[idx], er[idx]) if edges is not None else None
        # A typical racing line (same for every car): wide on entry, clipping the apex, wide on exit.
        self.line = racing_line(x, y, LINE_HALF_WIDTH, lo=lo, hi=hi)
        tx, ty = _tangents(x, y)
        self.profile = speed_profile(x - ty * self.line, y + tx * self.line)   # cumulative profile-time fraction (0..1)

    def at(self, d: np.ndarray | float):
        """x, y, z at lap distance d (metres, any value; wraps)."""
        d = np.mod(d, self.length)
        s = np.r_[self.s, self.length]
        return (np.interp(d, s, np.r_[self.x, self.x[0]]), np.interp(d, s, np.r_[self.y, self.y[0]]),
                np.interp(d, s, np.r_[self.z, self.z[0]]))

    def tau(self, d: float) -> float:
        """Profile time (in laps) to reach lap distance d from the line."""
        return float(np.interp(d, np.r_[self.s, self.length], np.r_[self.profile, 1.0]))

    def dist_of_tau(self, frac: float) -> float:
        return float(np.interp(frac, np.r_[self.profile, 1.0], np.r_[self.s, self.length]))

    def payload(self) -> dict[str, Any]:
        r = lambda a: np.round(a, 2).tolist()
        # Ship every second point (~4 m); the browser smooths it again.
        return dict(x=r(self.x[::2]), y=r(self.y[::2]), z=r(self.z[::2]), length=round(self.length, 1),
                    source=self.source, pit=self.pit, pit_frac=self.pit_frac, frame=self.frame, line=np.round(self.line[::2], 2).tolist(),
                    speed=np.round(self._speeds()[::2], 1).tolist())

    def _speeds(self) -> np.ndarray:
        dt = np.diff(np.r_[self.profile, 1.0])
        ds = np.diff(np.r_[self.s, self.length])
        with np.errstate(divide='ignore', invalid='ignore'):
            v = np.where(dt > 0, ds / np.maximum(dt, 1e-9), 0)
        return v / max(1e-9, v.max())   # relative speed 0..1 (braking zones, camera placement)


def _tangents(x: np.ndarray, y: np.ndarray):
    dx, dy = np.roll(x, -3) - np.roll(x, 3), np.roll(y, -3) - np.roll(y, 3)
    length = np.hypot(dx, dy)
    length[length == 0] = 1
    return dx / length, dy / length


def racing_line(x: np.ndarray, y: np.ndarray, half: float, lo=None, hi=None) -> np.ndarray:
    """Lateral offset (m, left positive) of a smooth line through the corridor of +-half around the centreline.

    Minimises the line's curvature (fourth differences over a 16 m stencil) while keeping it inside the track:
    the classic outside-apex-outside path, swinging wide before a bend, clipping the apex, running out on exit."""
    tx, ty = _tangents(x, y)
    nx, ny = -ty, tx
    off = np.zeros(len(x))
    k = max(1, int(round(16 / max(.5, float(np.mean(np.hypot(np.diff(x), np.diff(y))))))))
    r = lambda a, s: np.roll(a, s)
    for _ in range(4000):
        px, py = x + nx * off, y + ny * off
        d4x = r(px, 2 * k) - 4 * r(px, k) + 6 * px - 4 * r(px, -k) + r(px, -2 * k)
        d4y = r(py, 2 * k) - 4 * r(py, k) + 6 * py - 4 * r(py, -k) + r(py, -2 * k)
        off = np.clip((px - 0.1 * d4x - x) * nx + (py - 0.1 * d4y - y) * ny, -half if lo is None else lo, half if hi is None else hi)
    return _smooth_closed(off, 5)


def speed_profile(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """A representative lap's time-to-distance shape from the circuit's curvature alone.

    Corner speed from a lateral-grip limit, then acceleration and braking limits around the lap. Only the shape
    matters (it is scaled to each car's real crossing times), so cars slow for corners and run fast on straights.
    """
    n = len(x)
    seg = np.hypot(np.roll(x, -1) - x, np.roll(y, -1) - y)
    ds = max(.5, float(seg.mean()))
    head = np.unwrap(np.arctan2(np.roll(y, -1) - y, np.roll(x, -1) - x))
    w = max(2, int(round(12 / ds)))   # heading change over +-12 m
    dh = (np.roll(head, -w) - np.roll(head, w))
    dh = (dh + np.pi) % (2 * np.pi) - np.pi
    kappa = np.abs(dh) / (2 * w * ds)
    kappa = _smooth_closed(kappa, max(1, int(round(10 / ds))))
    with np.errstate(divide='ignore'):
        v = np.minimum(np.sqrt(36.0 / np.maximum(kappa, 1e-6)), 92.0)
    v = np.maximum(v, 18.0)
    for _ in range(2):   # closed loop: two passes settle the wrap-around
        for i in range(n):
            p = v[i - 1]
            acc = max(2.0, 13.0 * (1 - p / 95.0))
            v[i] = min(v[i], math.sqrt(p * p + 2 * acc * seg[i - 1]))
        for i in range(n - 1, -1, -1):
            nx = v[(i + 1) % n]
            v[i] = min(v[i], math.sqrt(nx * nx + 2 * 42.0 * seg[i]))
    t = np.r_[0, np.cumsum(seg / v)[:-1]]
    total = float(np.sum(seg / v))
    return t / total


def _bundled_outline(event: str) -> dict | None:
    import re
    import unicodedata
    plain = unicodedata.normalize('NFD', event or '').encode('ascii', 'ignore').decode()
    slug = re.sub(r'[^a-z0-9]+', '-', plain.lower()).strip('-')
    p = BUNDLED / f'{slug}.json'
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
    return None


def track_from_outline(outline: dict) -> Track:
    """An outline (bundled or the engine's) in metres. Flat unless it carries `z` (metres). An outline marked
    `frame: "f1"` is in the F1 position frame (tenths of a metre, unrotated), so the scene keeps that offset; `edges`
    (left/right half-widths per point) bound the racing line."""
    x, y = np.asarray(outline['x'], float), np.asarray(outline['y'], float)
    poly = float(np.sum(np.hypot(np.roll(x, -1) - x, np.roll(y, -1) - y)))
    length = float(outline.get('length') or 0)
    scale = length / poly if length > 1000 and poly > 0 else (0.1 if poly > 20000 else 1.0)
    mx, my = x.mean(), y.mean()
    x, y = (x - mx) * scale, (y - my) * scale
    z = np.asarray(outline['z'], float) if outline.get('z') else None
    frame = None
    if outline.get('frame') == 'f1' and not outline.get('rotation'):
        frame = (mx * scale, my * scale, float(outline.get('z_offset') or 0.0))
    edges = None
    if outline.get('edges'):
        edges = (x, y, outline['edges']['left'], outline['edges']['right'])
    return Track(x, y, z, source=str(outline.get('source') or 'circuit outline'), pit_frac=outline.get('pit'), frame=frame, edges=edges)


# ------------------------------------------------------------------ timing timeline

def _copy(v: Any) -> Any:
    """Private copy of a feed message. live_timing.merge() inserts lists from messages by reference, so without
    this the timing screen's state and this timeline would share (and silently update) the same segment lists."""
    if isinstance(v, dict):
        return {k: _copy(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_copy(x) for x in v]
    return v


class Timeline:
    """Per-driver crossings and classification, read once from the feed's events (incrementally when growing)."""

    def __init__(self):
        self.upto = 0
        self.lines: dict[str, dict] = {}
        self.drivers: dict[str, dict] = {}
        self.part = None
        self.total_laps: int | None = None
        self.seg_counts: list[int] = []
        # crossings[num] = list of (ts, laps_completed_before, kind, key)  kind: 'seg' (si,gi) | 'sec' i | 'line'
        self.crossings: dict[str, list[tuple[float, int, str, Any]]] = {}
        self.laps: dict[str, list[tuple[float, float | None]]] = {}   # (line ts, lap time)
        self.state: dict[str, list[tuple]] = {}   # (ts, pos, laps, interval, gap, in_pit, retired, stopped, out)
        self.session: dict[str, Any] = {}
        self.first_ts: float | None = None
        self.last_ts: float | None = None
        self._calib: tuple[int, dict] | None = None

    def update(self, events: list) -> None:
        for i in range(self.upto, len(events)):
            ts, topic, data = events[i]
            if ts is not None:
                self.first_ts = ts if self.first_ts is None else self.first_ts
                self.last_ts = ts if self.last_ts is None else max(self.last_ts, ts)
            if topic == 'DriverList' and isinstance(data, dict):
                for num, d in data.items():
                    if isinstance(d, dict) and str(num).isdigit():
                        self.drivers[num] = lt.merge(self.drivers.get(num), _copy(d))
            elif topic == 'SessionInfo' and isinstance(data, dict):
                self.session = lt.merge(self.session, _copy(data))
            elif topic == 'LapCount' and isinstance(data, dict) and data.get('TotalLaps'):
                self.total_laps = lt._int(data.get('TotalLaps'))
            elif topic == 'TimingData' and isinstance(data, dict):
                if data.get('SessionPart') is not None:
                    self.part = data.get('SessionPart')
                for num, delta in (data.get('Lines') or {}).items():
                    if isinstance(delta, dict):
                        self._line(num, _copy(delta), ts)
        self.upto = len(events)

    def _line(self, num: str, delta: dict, ts: float | None) -> None:
        cur = self.lines.get(num) or {}
        laps_before = lt._int(cur.get('NumberOfLaps')) or 0
        cross = self.crossings.setdefault(num, [])
        if ts is not None:
            secs = delta.get('Sectors')
            items = secs.items() if isinstance(secs, dict) else enumerate(secs or [])
            old_secs = lt._as_list(cur.get('Sectors'))
            for si, sec in items:
                if not isinstance(sec, dict):
                    continue
                si = int(si)
                segs = sec.get('Segments')
                seg_items = segs.items() if isinstance(segs, dict) else enumerate(segs or [])
                old_sec = old_secs[si] if si < len(old_secs) and isinstance(old_secs[si], dict) else {}
                old_segs = lt._as_list(old_sec.get('Segments'))
                for gi, seg in seg_items:
                    gi = int(gi)
                    new = lt._int((seg or {}).get('Status')) if isinstance(seg, dict) else None
                    old = lt._int((old_segs[gi] or {}).get('Status')) if gi < len(old_segs) and isinstance(old_segs[gi], dict) else 0
                    if new and not old and new != 2064:   # 2064 = in the pit lane, not a track position
                        cross.append((ts, laps_before, 'seg', (si, gi)))
                if si < 2 and sec.get('Value'):
                    cross.append((ts, laps_before, 'sec', si))
        merged = lt.merge(cur, delta)
        self.lines[num] = merged
        laps_after = lt._int(merged.get('NumberOfLaps')) or 0
        if ts is not None and laps_after > laps_before:
            cross.append((ts, laps_after, 'line', None))
            lap_time = lt.clock_seconds((merged.get('LastLapTime') or {}).get('Value'))
            self.laps.setdefault(num, []).append((ts, lap_time))
        if not self.seg_counts:
            secs = lt._as_list(merged.get('Sectors'))[:3]
            counts = [len(lt._as_list((s or {}).get('Segments'))) for s in secs if isinstance(s, dict)]
            if len(counts) == 3 and all(counts):
                self.seg_counts = counts
        if ts is not None:
            gap, interval = lt._gaps(merged, self.part)
            row = (ts, lt._int(merged.get('Position')), laps_after, interval, gap, bool(merged.get('InPit')),
                   bool(merged.get('Retired')), bool(merged.get('Stopped')), bool(merged.get('KnockedOut')))
            st = self.state.setdefault(num, [])
            if not st or st[-1][1:] != row[1:]:
                st.append(row)

    # ---------------------------------------------------------- calibration
    def calibration(self) -> dict:
        """Where each mini-sector and sector line sits on the lap, as a fraction of lap *time*, from clean laps."""
        n_laps = sum(len(v) for v in self.laps.values())
        if self._calib and self._calib[0] == n_laps:
            return self._calib[1]
        fracs: dict[Any, list[float]] = {}
        for num, laps in self.laps.items():
            cross = self.crossings.get(num) or []
            times = [c[0] for c in cross]
            for (t_end, lap_time), prev in zip(laps[1:], laps[:-1]):
                t_start = prev[0]
                span = t_end - t_start
                if not lap_time or abs(span - lap_time) > 2.5 or span < 40 or span > 200:
                    continue
                if self._in_pit_between(num, t_start, t_end):
                    continue
                a, b = bisect_right(times, t_start), bisect_right(times, t_end - 1e-3)
                for ts, _, kind, key in cross[a:b]:
                    if kind in ('seg', 'sec'):
                        fracs.setdefault((kind, key), []).append((ts - t_start) / span)
        calib = {k: float(np.median(v)) for k, v in fracs.items() if len(v) >= 3}
        self._calib = (n_laps, calib)
        return calib

    def _in_pit_between(self, num: str, a: float, b: float) -> bool:
        for row in self.state.get(num) or []:
            if a - 5 <= row[0] <= b and row[5]:
                return True
        return False

    def frac_of(self, kind: str, key: Any) -> float | None:
        calib = self.calibration()
        if (kind, key) in calib:
            return calib[(kind, key)]
        counts = self.seg_counts
        total = sum(counts)
        if not total:
            return None
        if kind == 'seg':
            si, gi = key
            return min(1.0, (sum(counts[:si]) + gi + 1) / total)
        if kind == 'sec':
            return sum(counts[:key + 1]) / total
        return None

    def state_at(self, num: str, t: float):
        st = self.state.get(num) or []
        i = bisect_right([r[0] for r in st], t) - 1
        return st[i] if i >= 0 else None

    def meta(self) -> dict[str, dict]:
        out = {}
        for num, d in self.drivers.items():
            out[num] = dict(number=str(num), code=d.get('Tla') or num, name=d.get('FullName') or d.get('BroadcastName') or num,
                            team=d.get('TeamName') or '', color='#' + str(d.get('TeamColour') or '62d7da').lstrip('#'))
        return out


class Estimator:
    """Distance along the race for each car at any instant, from its own timing crossings only."""

    def __init__(self, timeline: Timeline, track: Track):
        self.tl, self.track = timeline, track
        self._anchors: dict[str, tuple[int, list[tuple[float, float]]]] = {}

    def anchors(self, num: str) -> list[tuple[float, float]]:
        """(time, cumulative metres) pairs, strictly increasing in both."""
        cross = self.tl.crossings.get(num) or []
        hit = self._anchors.get(num)
        key = len(cross) * 1000 + len(self.tl.calibration())
        if hit and hit[0] == key:
            return hit[1]
        L = self.track.length
        out: list[tuple[float, float]] = []
        for ts, laps, kind, k in cross:
            if kind == 'line':
                d = laps * L
            else:
                f = self.tl.frac_of(kind, k)
                if f is None:
                    continue
                d = laps * L + self.track.dist_of_tau(f)
            if out:
                pt, pd = out[-1]
                if d <= pd + 1 or ts <= pt + 0.05:
                    continue                                   # never backwards
                if (d - pd) / (ts - pt) > 110 and ts - pt < HOLD_GAP_S:
                    continue                                   # implausible jump (late or duplicate message)
            out.append((ts, d))
        self._anchors[num] = (key, out)
        return out

    def tau_cum(self, s):
        """Cumulative profile time (in laps) for cumulative distance s (scalar or array)."""
        s = np.asarray(s, float)
        L, tr = self.track.length, self.track
        n = np.floor(s / L)
        return n + np.interp(s - n * L, np.r_[tr.s, L], np.r_[tr.profile, 1.0])

    def s_of_tau(self, tau):
        tau = np.asarray(tau, float)
        L, tr = self.track.length, self.track
        n = np.floor(tau)
        return n * L + np.interp(tau - n, np.r_[tr.profile, 1.0], np.r_[tr.s, L])

    def sample(self, num: str, times: np.ndarray, frontier: float) -> tuple[np.ndarray, np.ndarray]:
        """Cumulative distance at each time (NaN = not on track), and a flag per sample:
        0 interpolated between two crossings, 1 extrapolated past the newest crossing, 2 holding (stale)."""
        times = np.asarray(times, float)
        n = len(times)
        A = self.anchors(num)
        if not A:
            return np.full(n, np.nan), np.full(n, 2, int)
        at = np.array([a[0] for a in A])
        atau = self.tau_cum(np.array([a[1] for a in A]))
        i = np.searchsorted(at, times, side='right') - 1
        ic = np.clip(i, 0, len(A) - 1)
        nx = np.minimum(ic + 1, len(A) - 1)
        has_next = ic + 1 < len(A)
        off = i < 0
        stopped = np.zeros(n, bool)
        st = self.tl.state.get(num) or []
        if st:
            stt = np.array([r[0] for r in st])
            j = np.searchsorted(stt, times, side='right') - 1
            jc = np.clip(j, 0, len(st) - 1)
            gone = np.array([bool(r[5] or r[6] or r[8]) for r in st])   # pit lane, retired, knocked out
            stp = np.array([bool(r[7]) for r in st])
            off |= (j >= 0) & gone[jc]
            stopped = (j >= 0) & stp[jc]
        t0, t1 = at[ic], at[nx]
        bridge = has_next & (t1 - t0 <= HOLD_GAP_S) & (t1 <= frontier + 1e-6) & ~stopped
        k = np.where(bridge, (times - t0) / np.maximum(t1 - t0, 1e-9), 0.0)
        tau = np.where(bridge, atau[ic] + (atau[nx] - atau[ic]) * k, atau[ic])
        flag = np.where(bridge, 0, 2)
        # Past the newest crossing: keep going at the car's recent pace, for a bounded time only.
        last = ~has_next & ~stopped
        if last.any():
            rate = self._rate(A, len(A) - 1)
            ahead = times - t0
            tau = np.where(last, atau[ic] + rate * np.minimum(ahead, EXTRAPOLATE_S), tau)
            flag = np.where(last, np.where(ahead <= EXTRAPOLATE_S, 1, 2), flag)
        s = self.s_of_tau(tau)
        s[off] = np.nan
        return s, flag

    def _rate(self, A, i) -> float:
        """Profile laps per second over the last ~20 s of crossings (default: a 90 s lap)."""
        j = i
        while j > 0 and A[i][0] - A[j - 1][0] < 20:
            j -= 1
        if j < i and A[i][0] - A[j][0] > 3:
            r = float(self.tau_cum(A[i][1]) - self.tau_cum(A[j][1])) / (A[i][0] - A[j][0])
            return float(min(max(r, 1 / 300), 1 / 55))
        return 1 / 90


# ------------------------------------------------------------------ recorded positions (OpenF1)

class Recorded:
    """Per-driver timestamped coordinates for one session, in the scene frame (metres)."""

    def __init__(self, session: dict, cars: dict[str, dict[str, np.ndarray]], track: Track, meta: dict, rate: float):
        self.session, self.cars, self.track, self.meta, self.rate = session, cars, track, meta, rate
        self.start = min(float(c['t'][0]) for c in cars.values())
        self.end = max(float(c['t'][-1]) for c in cars.values())
        self._recon = None
        self._recon_lock = threading.Lock()

    def recon(self):
        """Reconstructed racing lines for the whole session (computed once, a few seconds)."""
        with self._recon_lock:
            if self._recon is None:
                from services import racing_lines as rl
                span = (self.start, self.end) if self.end - self.start < 6 * 3600 else None
                self._recon = rl.from_recorded(self.cars, self.track, edges=rl.venue_edges(str(self.session.get('event') or ''), self.track), t_range=span)
            return self._recon

    def window(self, num: str, t0: float, t1: float, stride: int = 1):
        c = self.cars.get(num)
        if c is None:
            return None
        a = max(0, int(np.searchsorted(c['t'], t0)) - 2)
        b = min(len(c['t']), int(np.searchsorted(c['t'], t1)) + 2)
        idx = np.arange(a, b, max(1, stride))
        return c['t'][idx], c['x'][idx], c['y'][idx], c['z'][idx]


def _is_live(feed) -> bool:
    return feed.mode == 'follow' and feed.growing()


def _session_code(name: str) -> str | None:
    return SESSION_CODES.get(lt.plain(name))


def load_recorded(year: int, event: str, session_name: str, start_local: str, progress=None) -> Recorded:
    """OpenF1 location for the session the recording holds. Refuses anything that is not the same session."""
    import pandas as pd
    from services.openf1_comparison import historical, resolve
    code = _session_code(session_name)
    if not code:
        raise ValueError(f'No recorded positions for a "{session_name}" session.')
    session = resolve(int(year), event, code)          # refuses live/unfinished sessions
    # Same session, not just the same event: the local start time must match the recording's SessionInfo.
    if start_local:
        try:
            off = str(session.get('gmt_offset') or '00:00:00')
            sign = -1 if off.startswith('-') else 1
            hh, mm, *_ = (off.lstrip('+-').split(':') + ['0', '0'])
            local = pd.to_datetime(session['date_start'], utc=True).tz_localize(None) + sign * timedelta(hours=int(hh), minutes=int(mm))
            if abs((local - pd.to_datetime(start_local)).total_seconds()) > 3600:
                raise ValueError('The recorded positions belong to a different session than this recording.')
        except (KeyError, TypeError) as exc:
            raise ValueError(f'Could not confirm the session: {exc}') from exc
    key = int(session['session_key'])
    drivers = historical('drivers', {'session_key': key})
    raw: dict[str, Any] = {}
    meta: dict[str, dict] = {}
    for i, d in enumerate(drivers):
        num = str(int(d['driver_number']))
        if progress:
            progress(i / max(1, len(drivers)), d.get('name_acronym') or num)
        try:
            loc = pd.DataFrame(historical('location', {'session_key': key, 'driver_number': int(num)}))
        except Exception:
            continue
        if loc.empty or not {'date', 'x', 'y'}.issubset(loc):
            continue
        t = pd.to_datetime(loc.date, utc=True, format='ISO8601', errors='coerce')
        ok = t.notna() & ~((loc.x == 0) & (loc.y == 0))
        loc, t = loc[ok], t[ok]
        if len(loc) < 50:
            continue
        ts = (t.astype('int64') / 1e9).to_numpy(float)
        order = np.argsort(ts, kind='stable')
        z = loc.z.to_numpy(float) if 'z' in loc else np.zeros(len(loc))
        raw[num] = (ts[order], loc.x.to_numpy(float)[order], loc.y.to_numpy(float)[order], z[order])
        meta[num] = dict(number=num, code=str(d.get('name_acronym') or num), name=str(d.get('full_name') or num),
                         team=str(d.get('team_name') or ''), color='#' + str(d.get('team_colour') or '62d7da').lstrip('#'))
    if len(raw) < 2:
        raise ValueError('OpenF1 has no usable car positions for this session.')
    # Circuit from the fastest timed lap's own samples: same frame as the cars.
    laps = pd.DataFrame(historical('laps', {'session_key': key}))
    laps['lap_duration'] = pd.to_numeric(laps.get('lap_duration'), errors='coerce')
    laps = laps.dropna(subset=['lap_duration', 'date_start'])
    laps = laps[(laps.lap_duration > 0) & laps.driver_number.astype(str).isin(list(raw))]
    if 'is_pit_out_lap' in laps:
        laps = laps[laps.is_pit_out_lap != True]  # noqa: E712
    if laps.empty:
        raise ValueError('OpenF1 has no timed lap to draw the circuit from.')
    lap = laps.sort_values('lap_duration').iloc[0]
    t0 = pd.to_datetime(lap.date_start, utc=True).value / 1e9
    ts, x, y, z = raw[str(int(lap.driver_number))]
    m = (ts >= t0) & (ts <= t0 + float(lap.lap_duration))
    if m.sum() < 80:
        raise ValueError('The fastest lap has too few position samples to draw the circuit.')
    cx, cy, z0 = float(np.mean(x[m])), float(np.mean(y[m])), float(np.min(z[m]))
    conv = lambda a, b, c: ((a - cx) / 10, (b - cy) / 10, (c - z0) / 10)   # OpenF1 units are 1/10 m
    tx, ty, tz = conv(x[m], y[m], z[m])
    keep = np.r_[True, np.hypot(np.diff(tx), np.diff(ty)) > .3]
    track = Track(tx[keep], ty[keep], tz[keep],
                  source=f"{year} {event} {session.get('session_name', '')}, fastest lap ({lap.driver_number}), OpenF1",
                  frame=(cx / 10, cy / 10, z0 / 10))
    cars = {}
    for num, (ts, x, y, z) in raw.items():
        a, b, c = conv(x, y, z)
        cars[num] = dict(t=ts, x=np.round(a, 2), y=np.round(b, 2), z=np.round(c, 2))
    dts = np.diff(next(iter(raw.values()))[0])
    rate = float(1 / np.median(dts[dts > 0])) if len(dts) else 0
    info = dict(provider='OpenF1', session_key=key, name=str(session.get('session_name') or ''), year=int(year), event=event)
    return Recorded(info, cars, track, meta, rate)


def pit_lane_from(rec: Recorded, tl: Timeline) -> list[list[float]] | None:
    """The pit lane as driven by one car on a normal stop (from the recorded coordinates)."""
    track = rec.track
    pts = np.c_[track.x, track.y]
    for num, st in tl.state.items():
        for a, b in zip(st, st[1:]):
            if not (b[5] and not a[5]):
                continue
            t_in = b[0]
            out = next((r[0] for r in st if r[0] > t_in and not r[5]), None)
            if out is None or not (10 < out - t_in < 80):
                continue
            w = rec.window(num, t_in - 40, out + 40)
            if w is None or len(w[0]) < 40:
                continue
            _, x, y, _ = w
            d = np.min(np.hypot(x[:, None] - pts[None, :, 0], y[:, None] - pts[None, :, 1]), axis=1)
            off = d > 6
            if off.sum() < 15:
                continue
            idx = np.flatnonzero(off)
            # Longest run of off-track samples.
            runs = np.split(idx, np.flatnonzero(np.diff(idx) > 2) + 1)
            run = max(runs, key=len)
            if len(run) < 15:
                continue
            a0, b0 = max(0, run[0] - 2), min(len(x), run[-1] + 3)
            return [[round(float(px), 1), round(float(py), 1)] for px, py in zip(x[a0:b0], y[a0:b0])]
    return None


# ------------------------------------------------------------------ scene manager

class SceneManager:
    """Caches the timeline, tracks and recorded positions for the feed that is open on the engine."""

    def __init__(self, outline_fn):
        self._recon_cache: dict = {}
        self.outline_fn = outline_fn          # (year, event) -> outline dict (engine's /api/live/track)
        self.lock = threading.RLock()
        self.path: Path | None = None
        self.timeline: Timeline | None = None
        self.tracks: dict[str, Track] = {}
        self.estimators: dict[str, Estimator] = {}
        self.recorded: dict[str, Any] = {}    # session id -> Recorded | dict(status=...)
        self._pits: dict[str, Any] = {}

    def _sync(self, feed) -> Timeline:
        with self.lock:
            if self.path != feed.path or self.timeline is None or self.timeline.upto > len(feed.events):
                self.path, self.timeline = feed.path, Timeline()
                self.estimators.clear()
            with feed.lock:
                feed._read_new()
                self.timeline.update(feed.events)
            return self.timeline

    def _session_id(self, tl: Timeline) -> str:
        info = tl.session
        meeting = (info.get('Meeting') or {}).get('Name') or ''
        return f"{lt._year(info)}|{meeting}|{info.get('Name') or ''}|{info.get('StartDate') or ''}"

    def _estimated_track(self, tl: Timeline) -> Track:
        info = tl.session
        meeting = (info.get('Meeting') or {}).get('Name') or ''
        key = f'est|{meeting}|{lt._year(info)}'
        if key not in self.tracks:
            outline = _bundled_outline(meeting) or self.outline_fn(lt._year(info), meeting)
            self.tracks[key] = track_from_outline(outline)
        return self.tracks[key]

    def _recorded_for(self, tl: Timeline, feed) -> Any:
        """Recorded positions for this exact session, loading in the background the first time."""
        sid = self._session_id(tl)
        info = tl.session
        # A live session (file still growing) never gets coordinates, even ones cached for the same session:
        # the free stream has none, and OpenF1's free data is historical only.
        if _is_live(feed):
            return dict(status='unavailable', reason='Live session: exact car positions need a paid feed, so positions are estimated.')
        with self.lock:
            hit = self.recorded.get(sid)
            if hit is not None:
                return hit
            state = dict(status='loading', progress=0.0, driver='')
            self.recorded[sid] = state

        def work():
            def prog(p, who):
                state['progress'], state['driver'] = round(p, 2), who
            try:
                rec = load_recorded(lt._year(info) or 0, (info.get('Meeting') or {}).get('Name') or '',
                                    info.get('Name') or '', info.get('StartDate') or '', prog)
                if rec.end < (tl.first_ts or 0) or rec.start > (tl.last_ts or 0):
                    raise ValueError('The recorded positions do not cover this recording\'s time span.')
                state['driver'] = 'reconstructing racing lines'
                try:
                    rec.recon()          # computed here, in the background, not inside the first samples request
                except Exception:
                    pass
                result: Any = rec
            except Exception as exc:
                result = dict(status='unavailable', reason=f'No recorded positions: {str(exc)[:200]}')
            with self.lock:
                self.recorded[sid] = result
        threading.Thread(target=work, daemon=True).start()
        return state

    def describe(self, feed, source: str = 'auto') -> dict[str, Any]:
        tl = self._sync(feed)
        info = tl.session
        meeting = (info.get('Meeting') or {}).get('Name') or ''
        base = dict(file=feed.path.name, mode=feed.mode, session=dict(meeting=meeting, name=info.get('Name') or '',
                    year=lt._year(info), type=info.get('Type') or '', start=info.get('StartDate') or ''),
                    total_laps=tl.total_laps)
        rec = self._recorded_for(tl, feed) if meeting else dict(status='unavailable', reason='Session not identified yet.')
        recorded_status = ({'status': 'ready', 'provider': rec.session['provider'], 'rate': round(rec.rate, 2),
                            'start': rec.start, 'end': rec.end} if isinstance(rec, Recorded) else rec)
        use_rec = isinstance(rec, Recorded) and source != 'estimated'
        if use_rec:
            sid = self._session_id(tl)
            if sid not in self._pits:
                try:
                    self._pits[sid] = pit_lane_from(rec, tl)
                except Exception:
                    self._pits[sid] = None
            rec.track.pit = self._pits[sid]
            track = rec.track
            meta = {**rec.meta, **{k: v for k, v in tl.meta().items() if k in rec.meta}}
            label = 'Recorded positions'
            detail = (f"{rec.session['provider']} coordinates, {rec.session['year']} {rec.session['event']} "
                      f"{rec.session['name']}, ~{rec.rate:.1f} samples/s per car")
        else:
            try:
                track = self._estimated_track(tl)
            except Exception as exc:
                return dict(base, ok=False, error=f'No circuit geometry for {meeting or "this session"}: {str(exc)[:160]}',
                            recorded=recorded_status)
            meta = tl.meta()
            label = 'Estimated positions'
            detail = 'From the timing feed: mini-sector, sector and lap crossings, between them a representative lap profile'
        return dict(base, ok=True, source='recorded' if use_rec else 'estimated', label=label, detail=detail,
                    key=f"{feed.path.name}|{feed.mode}|{'recorded' if use_rec else 'estimated'}",
                    track=track.payload(), drivers=meta, recorded=recorded_status)

    def samples(self, feed, t0: float, t1: float, source: str = 'auto', step: float = 0.25) -> dict[str, Any]:
        tl = self._sync(feed)
        t1 = min(t1, t0 + 900)
        sid = self._session_id(tl)
        rec = self.recorded.get(sid)
        use_rec = isinstance(rec, Recorded) and source != 'estimated' and not _is_live(feed)
        frontier = tl.last_ts or t1
        if feed.mode == 'replay' and not feed.growing():
            frontier = max(frontier, feed.last_time() or frontier)
        cars: dict[str, Any] = {}
        est_step = None
        recon = None
        if use_rec:
            span = t1 - t0
            stride = 1 if span <= 120 else 2 if span <= 300 else 4
            for num in rec.cars:
                w = rec.window(num, t0, t1, stride)
                if w is None or not len(w[0]):
                    continue
                ts, x, y, z = w
                cars[num] = dict(t=np.round(ts - t0, 3).tolist(), x=x.tolist(), y=y.tolist(), z=z.tolist())
            try:
                recon = rec.recon().window(t0, t1)
            except Exception:
                recon = None
        else:
            track = self._estimated_track(tl)
            est = self.estimators.get(str(tl.session.get('Path')))
            if est is None or est.track is not track or est.tl is not tl:
                est = self.estimators[str(tl.session.get('Path'))] = Estimator(tl, track)
            est_step = step = max(0.1, min(2.0, step))
            times = np.arange(t0, t1 + 1e-6, step)
            for num in tl.crossings:
                s, f = est.sample(num, times, frontier)
                if np.isnan(s).all():
                    continue
                cars[num] = dict(s=[None if np.isnan(v) else round(float(v), 1) for v in s], f=f.tolist())
            recon = self._estimated_recon(tl, track, est, feed, t0, t1, step, frontier)
        # Classification at the window start plus every change inside it: the HUD shows what the feed said at the
        # displayed instant (position, laps, official interval), never a position-derived order.
        timing = {}
        for num, st in tl.state.items():
            i = max(0, bisect_right([r[0] for r in st], t0) - 1)
            rows = [r for r in st[i:] if r[0] <= t1]
            if rows:
                timing[num] = [[round(r[0] - t0, 3), r[1], r[2], r[3], r[4], int(r[5]), int(r[6]), int(r[7]), int(r[8])] for r in rows]
        return dict(key=f"{feed.path.name}|{feed.mode}|{'recorded' if use_rec else 'estimated'}", t0=t0, t1=t1,
                    frontier=frontier, source='recorded' if use_rec else 'estimated',
                    cars=cars, step=est_step, timing=timing, recon=recon)

    def _estimated_recon(self, tl, track, est, feed, t0, t1, step, frontier):
        """Reconstructed lines for timing-only cars. A finished recording is reconstructed over its whole timeline
        once (so seeking reproduces the same manoeuvre); a growing one over the window plus 20 s of lead-in."""
        from services import racing_lines as rl
        try:
            names = [n for n in tl.crossings]
            if feed.mode == 'replay' and not feed.growing() and tl.first_ts and frontier:
                key = (str(tl.session.get('Path')), id(est), round(frontier, 1))
                res = self._recon_cache.get(key)
                if res is None:
                    times = np.arange(float(tl.first_ts) - 5, float(frontier) + 0.25, 0.25)
                    samples = {n: est.sample(n, times, frontier)[0] for n in names}
                    res = rl.from_estimated(samples, track, times, edges=getattr(track, 'edges_lr', None))
                    self._recon_cache = {key: res}
                return res.window(t0, t1)
            times = np.arange(t0 - 20, t1 + 0.25, 0.25)
            samples = {n: est.sample(n, times, frontier)[0] for n in names}
            return rl.from_estimated(samples, track, times, edges=getattr(track, 'edges_lr', None)).window(t0, t1)
        except Exception:
            return None
