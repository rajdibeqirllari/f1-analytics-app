"""3D Broadcast for the Replay page: the replay's own session, in one shared 3D world.

The replay payload is capped at 6,000 frames (about one sample a second for a race), which is too coarse for
cars taking corners in 3D. So the scene uses the session's native positions at full rate when they are available
and line up exactly with the payload's clock:

* OpenF1 replays: OpenF1 ``location`` (~4 Hz, x/y/z), same session key. The payload's time 0 is reproduced
  from the same laps the replay was built from, then checked against the payload's own frames.
* FastF1 replays: FastF1 ``pos_data`` from the local cache (offline only), time 0 = the replay engine's origin.

If neither lines up (checked, never assumed), the payload frames themselves are used and the view says so.
All times in this module are payload seconds (the Replay page's clock), so the browser never needs epoch time.
"""
from __future__ import annotations

import threading
from typing import Any

import numpy as np

from services import scene3d as sc

ALIGN_TOLERANCE_M = 3.0
SESSION_NAMES = {'R': 'Race', 'Q': 'Qualifying', 'S': 'Sprint', 'SQ': 'Sprint Qualifying'}


def _check(payload: dict, native: dict[str, tuple], offset: float) -> float:
    """Median distance (m) between the payload frames and the native data at offset, over a few drivers."""
    frames = payload.get('frames') or []
    if not frames:
        return float('inf')
    errs = []
    picks = frames[len(frames) // 5::max(1, len(frames) // 40)][:40]
    for code, (t, x, y, _z) in list(native.items())[:6]:
        for f in picks:
            car = (f.get('drivers') or {}).get(code)
            if not car or car.get('x') is None:
                continue
            ta = f['t'] + offset
            if ta < t[0] or ta > t[-1]:
                continue
            errs.append(np.hypot(np.interp(ta, t, x) - car['x'], np.interp(ta, t, y) - car['y']) / 10)
    return float(np.median(errs)) if len(errs) >= 10 else float('inf')


def _openf1_native(payload: dict):
    import pandas as pd
    from services.openf1_comparison import historical, resolve
    meta = payload['meta']
    session = resolve(int(meta['year']), str(meta['event']), str(meta['session']))
    key = int(session['session_key'])
    laps = pd.DataFrame(historical('laps', {'session_key': key}))
    laps['start'] = pd.to_datetime(laps.date_start, utc=True, format='ISO8601', errors='coerce')
    laps['lap_duration'] = pd.to_numeric(laps.get('lap_duration'), errors='coerce')
    laps = laps.dropna(subset=['start'])
    # The replay's time 0, exactly as services/replay_fallback.build_openf1_replay chose it.
    begin = laps.start.min() - pd.Timedelta(seconds=120 if int(laps.lap_number.min()) > 1 else 5)
    offset = begin.value / 1e9
    by_number = {str(int(d['driver_number'])): str(d.get('name_acronym') or d['driver_number']).upper()
                 for d in historical('drivers', {'session_key': key})}
    native = {}
    for number, code in by_number.items():
        if code not in payload['drivers']:
            continue
        try:
            loc = pd.DataFrame(historical('location', {'session_key': key, 'driver_number': int(number)}))
        except Exception:
            continue
        if loc.empty or not {'date', 'x', 'y'}.issubset(loc):
            continue
        when = pd.to_datetime(loc.date, utc=True, format='ISO8601', errors='coerce')
        ok = when.notna() & ~((loc.x == 0) & (loc.y == 0))
        loc, when = loc[ok], when[ok]
        t = (when.astype('int64') / 1e9).to_numpy(float)
        order = np.argsort(t, kind='stable')
        t = t[order]
        keep = np.r_[True, np.diff(t) > 0]
        z = loc.z.to_numpy(float) if 'z' in loc else np.zeros(len(loc))
        native[code] = (t[keep], loc.x.to_numpy(float)[order][keep],
                        loc.y.to_numpy(float)[order][keep], z[order][keep])
    timed = laps.dropna(subset=['lap_duration'])
    timed = timed[(timed.lap_duration > 0) & timed.driver_number.astype(str).map(by_number).isin(list(native))]
    if 'is_pit_out_lap' in timed:
        timed = timed[timed.is_pit_out_lap != True]  # noqa: E712
    fastest = None
    if not timed.empty:
        lap = timed.sort_values('lap_duration').iloc[0]
        fastest = (by_number[str(int(lap.driver_number))], lap.start.value / 1e9, float(lap.lap_duration))
    _openf1_native.last = dict(offset=offset, session_key=key, numbers=by_number)
    return native, offset, fastest, f"OpenF1 location, session {key}"


def _fastf1_native(payload: dict):
    import fastf1
    from services import replay_service as rs
    meta = payload['meta']
    fastf1.Cache.offline_mode(True)
    try:
        s = fastf1.get_session(int(meta['year']), str(meta['event']), str(meta['session']))
        s.load(laps=True, telemetry=True, weather=False, messages=False)
    finally:
        fastf1.Cache.offline_mode(False)
    native, starts = {}, []
    for code, d in payload['drivers'].items():
        pos = s.pos_data.get(str(d.get('number')))
        if pos is None or pos.empty:
            continue
        pos = pos.dropna(subset=['Time', 'X', 'Y'])
        t = pos['Time'].dt.total_seconds().to_numpy(float)
        keep = np.r_[True, np.diff(t) > 0]
        z = pos['Z'].to_numpy(float) if 'Z' in pos else np.zeros(len(pos))
        native[code] = (t[keep], pos['X'].to_numpy(float)[keep], pos['Y'].to_numpy(float)[keep], z[keep])
        starts.append(t[0])
    if not native:
        raise ValueError('FastF1 cache has no position data for this session.')
    offset = min(starts)
    window = rs._session_lap_window(s)
    if window is not None:
        offset = max(offset, window[0])
    fastest = None
    try:
        lap = s.laps.pick_fastest()
        code = str(lap['Driver'])
        fastest = (code, float(lap['LapStartTime'].total_seconds()), float(lap['LapTime'].total_seconds()))
    except Exception:
        pass
    return native, offset, fastest, 'FastF1 position data (local cache)'


def build(payload: dict) -> dict[str, Any]:
    """Native positions in payload seconds and the scene frame, or the payload frames as a checked fallback."""
    meta = payload['meta']
    notes = []
    loaders = [_openf1_native] if meta.get('source') == 'OpenF1' else [_fastf1_native]
    for loader in loaders:
        try:
            native, offset, fastest, label = loader(payload)
            err = _check(payload, native, offset)
            if err <= ALIGN_TOLERANCE_M and fastest:
                return _scene_from(native, offset, fastest, payload, label, err)
            notes.append(f'{label} did not line up with this replay (median {err:.1f} m apart).')
        except Exception as exc:
            notes.append(f'Native positions unavailable: {str(exc)[:160]}')
    return _scene_from_frames(payload, ' '.join(notes))


def _scene_from(native, offset, fastest, payload, label, err) -> dict[str, Any]:
    code, start, duration = fastest
    t, x, y, z = native[code]
    m = (t >= start) & (t <= start + duration)
    if m.sum() < 80:
        raise ValueError('The fastest lap has too few samples to draw the circuit.')
    cx, cy, z0 = float(np.mean(x[m])), float(np.mean(y[m])), float(np.min(z[m]))
    conv = lambda a, b, c: ((a - cx) / 10, (b - cy) / 10, (c - z0) / 10)
    tx, ty, tz = conv(x[m], y[m], z[m])
    keep = np.r_[True, np.hypot(np.diff(tx), np.diff(ty)) > .3]
    track = sc.Track(tx[keep], ty[keep], tz[keep], source=f'fastest lap ({code}), {label}', frame=(cx / 10, cy / 10, z0 / 10))
    cars = {}
    for c, (tt, xx, yy, zz) in native.items():
        a, b, h = conv(xx, yy, zz)
        cars[c] = dict(t=tt - offset, x=np.round(a, 2), y=np.round(b, 2), z=np.round(h, 2))
    dts = np.diff(next(iter(native.values()))[0])
    rate = float(1 / np.median(dts[dts > 0]))
    meta = payload['meta']
    rec = sc.Recorded(dict(provider=label, year=meta['year'], event=meta['event'], name=SESSION_NAMES.get(meta['session'], meta['session'])),
                      cars, track, _meta(payload), rate)
    return dict(rec=rec, label='Recorded positions',
                detail=f'{label}, ~{rate:.1f} samples/s per car, lined up with the replay clock (median {err:.2f} m)')


def _scene_from_frames(payload: dict, why: str) -> dict[str, Any]:
    pts = np.array([p for p in payload['track']['centerline'] if p and p[0] is not None], float)
    cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
    track = sc.Track((pts[:, 0] - cx) / 10, (pts[:, 1] - cy) / 10, None, source='replay outline', frame=(cx / 10, cy / 10, 0.0))
    series: dict[str, list] = {}
    for f in payload['frames']:
        for code, car in (f.get('drivers') or {}).items():
            if car.get('x') is not None:
                series.setdefault(code, []).append((f['t'], (car['x'] - cx) / 10, (car['y'] - cy) / 10))
    cars = {}
    for code, rows in series.items():
        a = np.array(rows, float)
        cars[code] = dict(t=a[:, 0], x=np.round(a[:, 1], 2), y=np.round(a[:, 2], 2), z=np.zeros(len(a)))
    rate = float(payload['meta'].get('sample_rate_hz') or 1)
    meta = payload['meta']
    rec = sc.Recorded(dict(provider='replay frames', year=meta['year'], event=meta['event'], name=SESSION_NAMES.get(meta['session'], meta['session'])),
                      cars, track, _meta(payload), rate)
    return dict(rec=rec, label='Recorded positions (coarse)',
                detail=f'Replay frames only, {rate:.1f} samples/s: corners are approximated. {why}'.strip())


def _meta(payload: dict) -> dict[str, dict]:
    return {code: dict(code=code, name=d.get('name') or code, team=d.get('team') or '', color=d.get('color') or '#62d7da',
                       number=str(d.get('number') or ''))
            for code, d in payload['drivers'].items()}


class ReplayScenes:
    """One scene per loaded replay, built in the background (OpenF1 parsing / FastF1 loading takes seconds)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.items: dict[str, Any] = {}

    def get(self, token: str, payload: dict) -> dict[str, Any]:
        meta = payload['meta']
        key = f"{meta['year']}|{meta['event']}|{meta['session']}|{meta.get('source', 'FastF1')}|{len(payload['frames'])}"
        with self.lock:
            hit = self.items.get(key)
            if hit is None:
                hit = self.items[key] = dict(status='loading')
                threading.Thread(target=self._work, args=(key, payload), daemon=True).start()
        return hit

    def _work(self, key: str, payload: dict) -> None:
        try:
            result = build(payload)
            result['radio_clock'] = getattr(_openf1_native, 'last', None) if payload['meta'].get('source') == 'OpenF1' else None
            # Reconstructed racing lines (lateral placement only) for the whole session, once.
            try:
                from services import racing_lines as rl
                rec = result['rec']
                fr = payload.get('frames') or []
                span = (float(fr[0]['t']) - 60, float(fr[-1]['t'])) if fr else None   # the replay's own range (grid included)
                result['recon'] = rl.from_recorded(rec.cars, rec.track, edges=rl.venue_edges(str(payload['meta'].get('event') or ''), rec.track), t_range=span)
            except Exception as exc:   # the view still works with raw positions
                result['recon'] = None
                result['recon_error'] = str(exc)[:200]
            result['status'] = 'ready'
        except Exception as exc:
            result = dict(status='error', reason=str(exc)[:240])
        with self.lock:
            self.items[key] = result

    def describe(self, token: str, payload: dict) -> dict[str, Any]:
        item = self.get(token, payload)
        meta = payload['meta']
        base = dict(file=token, mode='replay', session=dict(meeting=meta['event'], name=SESSION_NAMES.get(meta['session'], meta['session']),
                    year=meta['year'], type=meta['session'], start=''),
                    total_laps=max((f.get('lap') or 0) for f in payload['frames']) if payload['frames'] else None)
        if item['status'] == 'loading':
            return dict(base, ok=False, loading=True, error='Loading positions for the 3D view…', recorded=dict(status='loading'))
        if item['status'] == 'error':
            return dict(base, ok=False, error=f"The 3D view could not be built: {item['reason']}", recorded=dict(status='unavailable'))
        rec = item['rec']
        return dict(base, ok=True, source='recorded', label=item['label'], detail=item['detail'], key=f'{token}|recorded',
                    track=rec.track.payload(), drivers=rec.meta, recorded=dict(status='unavailable', reason=''))

    def samples(self, token: str, payload: dict, t0: float, t1: float) -> dict[str, Any]:
        item = self.get(token, payload)
        if item.get('status') != 'ready':
            raise ValueError('The 3D view is still loading.')
        rec = item['rec']
        span = t1 - t0
        stride = 1 if span <= 120 else 2 if span <= 300 else 4
        cars = {}
        for code in rec.cars:
            w = rec.window(code, t0, t1, stride)
            if w is None or not len(w[0]):
                continue
            ts, x, y, z = w
            cars[code] = dict(t=np.round(ts - t0, 3).tolist(), x=x.tolist(), y=y.tolist(), z=z.tolist())
        recon = item.get('recon')
        return dict(key=f'{token}|recorded', t0=t0, t1=t1, frontier=float(payload['frames'][-1]['t']) if payload['frames'] else t1,
                    source='recorded', step=None, cars=cars, timing={}, recon=recon.window(t0, t1) if recon is not None else None)


def radio_events(item: dict, payload: dict) -> dict:
    """OpenF1 team radio for the replay's session, in payload seconds (the Replay page's clock).

    Uses the same time zero the 3D scene was aligned with (checked against the payload frames). Sessions replayed from
    the FastF1 cache have no epoch reference here, so they report no radio rather than guessing a time."""
    rc = item.get('radio_clock')
    if not rc:
        return dict(events=[], reason='Team radio timing is only available for replays built from OpenF1.')
    import pandas as pd
    from services.openf1_comparison import historical
    try:
        rows = historical('team_radio', {'session_key': int(rc['session_key'])})
    except Exception as exc:
        return dict(events=[], reason=f'OpenF1 team radio unavailable: {str(exc)[:120]}')
    out = []
    end = float(payload['frames'][-1]['t']) if payload.get('frames') else None
    for r in rows or []:
        when = pd.to_datetime(r.get('date'), utc=True, errors='coerce')
        if when is pd.NaT or when is None:
            continue
        t = when.value / 1e9 - float(rc['offset'])
        if t < 0 or (end is not None and t > end + 60):
            continue
        num = str(int(r.get('driver_number') or 0))
        code = rc['numbers'].get(num, num)
        info = (payload.get('drivers') or {}).get(code) or {}
        out.append(dict(id=f"{num}:{r.get('date')}", t=round(t, 3), num=num, code=code, color=info.get('color') or '',
                        url=r.get('recording_url'), transcript=''))
    out.sort(key=lambda e: e['t'])
    return dict(events=out, reason='' if out else 'No team radio published for this session.')
