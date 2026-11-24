"""Replay data when FastF1 can't load the session: car positions from OpenF1.

The payload has the same shape as ``replay_service.build_replay_payload`` so the Replay page plays it unchanged.
OpenF1's free ``location`` data gives X/Y a few times a second; speed is worked out from those positions, and the
channels OpenF1 would need 22 more large downloads for (gear, throttle, brake, DRS) are left at zero.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services import live_timing as lt
from services import replay_service as rs

ARCHIVE_NOTE = ("F1's timing archive needs an F1 TV login since 15 Oct 2026, so the full replay only works for "
                "sessions already in your cache.")


def _statuses(messages: list[dict], t0: pd.Timestamp, duration: float) -> list[dict[str, Any]]:
    """Track status over time from race control: green, yellow, safety car, VSC, red."""
    base, yellow = '1', set()
    out: list[dict[str, Any]] = []

    def push(at: float):
        code = '2' if base == '1' and yellow else base
        if not out or out[-1]['status'] != code:
            out.append(dict(status=code, start_time=at, end_time=None, label=rs._status_label(code)))

    push(0.0)
    for m in sorted(messages, key=lambda m: str(m.get('date', ''))):
        when = pd.to_datetime(m.get('date'), utc=True, errors='coerce')
        if pd.isna(when):
            continue
        at = max(0.0, float((when - t0).total_seconds()))
        text = str(m.get('message') or '').upper()
        flag = str(m.get('flag') or '').upper()
        scope = str(m.get('scope') or '').lower()
        sector = m.get('sector')
        if 'VIRTUAL SAFETY CAR' in text or 'VSC' in text:
            base = '7' if 'ENDING' in text else '6' if 'DEPLOYED' in text else base
        elif 'SAFETY CAR' in text and 'DEPLOYED' in text:
            base = '4'
        elif flag == 'RED':
            base, yellow = '5', set()
        elif scope == 'track' and flag in ('GREEN', 'CLEAR'):
            base, yellow = '1', set()
        elif 'TRACK CLEAR' in text or 'GREEN LIGHT' in text:
            base, yellow = '1', set()
        elif scope == 'sector' and sector is not None:
            if flag in ('YELLOW', 'DOUBLE YELLOW'):
                yellow.add(sector)
            elif flag in ('CLEAR', 'GREEN'):
                yellow.discard(sector)
        push(at)
    for a, b in zip(out, out[1:]):
        a['end_time'] = b['start_time']
    out[-1]['end_time'] = max(out[-1]['start_time'], duration)
    return out


def build_openf1_replay(year: int, event: str, code: str, sample_rate_hz: int = 3, progress_callback=None) -> dict[str, Any]:
    from services.openf1_comparison import historical, resolve, apply_lap_deletions

    def progress(value: float, text: str) -> None:
        if progress_callback:
            progress_callback(value, text)

    progress(.05, 'FastF1 has no data for this session. Asking OpenF1 instead')
    session = resolve(year, event, code)
    key = int(session['session_key'])
    drivers = historical('drivers', {'session_key': key})
    laps = pd.DataFrame(historical('laps', {'session_key': key}))
    if laps.empty or 'date_start' not in laps:
        raise ValueError('OpenF1 has no laps for this session.')
    laps['start'] = pd.to_datetime(laps.date_start, utc=True, format='ISO8601', errors='coerce')
    laps['lap_duration'] = pd.to_numeric(laps.get('lap_duration'), errors='coerce')
    laps = laps.dropna(subset=['start'])
    if laps.empty:
        raise ValueError('OpenF1 has no timestamped laps for this session.')
    try:
        stints = historical('stints', {'session_key': key})
    except Exception:
        stints = []
    try:
        messages = historical('race_control', {'session_key': key})
    except Exception:
        messages = []

    # The part of the session with cars on timed laps (a little before the first recorded lap start: lap one of a
    # race often has no start time of its own).
    begin = laps.start.min() - pd.Timedelta(seconds=120 if int(laps.lap_number.min()) > 1 else 5)
    end = (laps.start + pd.to_timedelta(laps.lap_duration.fillna(0), unit='s')).max() + pd.Timedelta(seconds=5)

    meta: dict[str, dict[str, Any]] = {}
    data: dict[str, dict[str, np.ndarray]] = {}
    raw_xy: dict[int, pd.DataFrame] = {}
    for i, d in enumerate(drivers):
        number = int(d['driver_number'])
        acronym = str(d.get('name_acronym') or number).upper()
        progress(.1 + .6 * i / max(1, len(drivers)), f'Car positions from OpenF1: {acronym} ({i + 1}/{len(drivers)})')
        try:
            loc = pd.DataFrame(historical('location', {'session_key': key, 'driver_number': number}))
        except Exception:
            continue
        if loc.empty or not {'date', 'x', 'y'}.issubset(loc):
            continue
        loc['when'] = pd.to_datetime(loc.date, utc=True, format='ISO8601', errors='coerce')
        loc = loc.dropna(subset=['when', 'x', 'y']).sort_values('when').drop_duplicates('when')
        loc = loc[(loc.when >= begin) & (loc.when <= end) & ~((loc.x == 0) & (loc.y == 0))]
        if len(loc) < 20:
            continue
        raw_xy[number] = loc
        t = (loc.when - begin).dt.total_seconds().to_numpy(float)
        x, y = loc.x.to_numpy(float), loc.y.to_numpy(float)
        step = np.r_[0.0, np.hypot(np.diff(x), np.diff(y))]
        dt = np.r_[1.0, np.maximum(np.diff(t), .05)]
        speed = pd.Series(step / 10 / dt * 3.6).rolling(5, center=True, min_periods=1).median().clip(0, 380).to_numpy(float)
        mine = laps[laps.driver_number == number].sort_values('start')
        starts = (mine.start - begin).dt.total_seconds().to_numpy(float)
        numbers = mine.lap_number.to_numpy(float)
        idx = np.searchsorted(starts, t, side='right') - 1
        lap = np.where(idx >= 0, numbers[np.clip(idx, 0, max(0, len(numbers) - 1))] if len(numbers) else 1, 1).astype(float)
        tyre = np.array(['UNKNOWN'] * len(t), dtype=object)
        age = np.array([None] * len(t), dtype=object)
        for s in stints:
            if s.get('driver_number') != number or s.get('lap_start') is None:
                continue
            last = s.get('lap_end') if s.get('lap_end') is not None else 10 ** 6
            mask = (lap >= s['lap_start']) & (lap <= last)
            tyre[mask] = str(s.get('compound') or 'UNKNOWN').upper()
            start_age = int(s.get('tyre_age_at_start') or 0)
            age[mask] = [int(start_age + v - s['lap_start']) for v in lap[mask]]
        zero = np.zeros_like(t)
        data[acronym] = dict(t=t, x=x, y=y, dist=np.cumsum(step), lap=lap, speed=speed, gear=zero, drs=zero,
                             throttle=zero, brake=zero, tyre=tyre, tyre_age=age)
        colour = str(d.get('team_colour') or 'E10600').lstrip('#')
        meta[acronym] = dict(name=str(d.get('full_name') or acronym), team=str(d.get('team_name') or ''),
                             number=str(number), color='#' + colour)
    if len(data) < 2:
        raise ValueError('OpenF1 has no usable car positions for this session.')

    progress(.74, 'Drawing the circuit from the fastest lap')
    timed = laps.dropna(subset=['lap_duration'])
    timed = timed[(timed.lap_duration > 0) & timed.driver_number.isin(list(raw_xy))]
    try:
        timed = apply_lap_deletions(timed, messages)
        timed = timed[~timed.deleted]
    except Exception:
        pass
    if 'is_pit_out_lap' in timed:
        timed = timed[timed.is_pit_out_lap != True]  # noqa: E712
    if timed.empty:
        raise ValueError('OpenF1 has no timed lap to draw the circuit from.')
    fastest = timed.sort_values('lap_duration').iloc[0]
    loc = raw_xy[int(fastest.driver_number)]
    one = loc[(loc.when >= fastest.start) & (loc.when <= fastest.start + pd.Timedelta(seconds=float(fastest.lap_duration)))]
    xy = one[['x', 'y']].to_numpy(float)
    if len(xy) < 50:
        raise ValueError('OpenF1 positions do not cover a full lap for the circuit outline.')
    xy = rs._downsample_points(xy, 360)
    inner, outer = rs._offset_boundaries(xy, 70.0)
    track = dict(centerline=rs._round_points(xy), inner_boundary=rs._round_points(inner), outer_boundary=rs._round_points(outer),
                 drs_zones=[], start_finish=rs._round_point(xy[0]))

    duration = max(1.0, float((end - begin).total_seconds()))
    rate = max(1, min(10, int(sample_rate_hz)))
    limit = 6000
    if int(duration * rate) + 1 > limit:
        timeline = np.linspace(0, duration, limit)
        effective = round(limit / duration, 2)
    else:
        timeline = np.arange(0, duration, 1.0 / rate)
        effective = rate
    progress(.8, 'Sampling replay frames')
    statuses = _statuses(messages, begin, duration)
    frames = rs._build_frames(timeline, 0.0, data, statuses, track)
    if not frames:
        raise ValueError('OpenF1 positions produced no replay frames.')
    progress(.95, 'Finalizing replay')
    return dict(
        meta=dict(year=int(year), event=str(event), round=0, session=rs.session_type_to_code(code),
                  duration_seconds=round(duration, 2), sample_rate_hz=effective, requested_sample_rate_hz=int(sample_rate_hz),
                  source='OpenF1',
                  attribution='Car positions from OpenF1 (free, non-commercial). Speed is worked out from positions; '
                              'gear, throttle, brake and DRS are not included.'),
        track=track, drivers=meta, frames=frames,
        technical=dict(frame_count=len(frames), driver_count=len(meta), track_statuses=statuses,
                       nullable_future_fields=['active_aero_mode', 'overtake_mode', 'boost_mode', 'recharge_mode']))


def replay_with_fallback(year: int, event: str, code: str, sample_rate_hz: int = 3, refresh: bool = False,
                         progress_callback=None, recordings: list[Path] | None = None, cache: bool = True) -> dict[str, Any]:
    """FastF1 (cache) first, then OpenF1 positions. Errors are plain sentences that say what to do next."""
    try:
        return rs.build_replay_payload(year, event, code, sample_rate_hz, refresh=refresh, progress_callback=progress_callback)
    except InterruptedError:
        raise
    except Exception:
        pass   # the usual reason is the closed archive; the message below explains it without the raw error
    try:
        payload = build_openf1_replay(year, event, code, sample_rate_hz, progress_callback)
    except InterruptedError:
        raise
    except Exception as exc:
        own = lt.find_recording(recordings or [], year, event, code)
        hint = (f' You recorded this session yourself: open {own.name} on the Live page to replay its timing screen.'
                if own else ' Try a session that is in your cache, or a finished session from 2023 onwards.')
        raise ValueError(f'This replay could not be loaded. {ARCHIVE_NOTE} The OpenF1 fallback did not work either: '
                         f'{exc}{hint}') from exc
    if cache:
        selection = rs.ReplaySelection(int(year), str(event), rs.session_type_to_code(code), int(sample_rate_hz))
        path = rs.cache_path(selection)
        payload['meta']['cache_file'] = str(path)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)
    if progress_callback:
        progress_callback(1.0, 'Replay ready')
    return payload
