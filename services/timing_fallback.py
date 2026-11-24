"""Timing page data when FastF1 can't load the session.

Since October 2026 F1's timing archive needs an F1 TV login, so FastF1 only works for sessions already in the cache.
The Timing page then falls back, in order, to:

  1. OpenF1 (free, completed sessions from 2023): classification, laps, sectors, stints, race control, weather.
  2. The owner's own live recording in ``outputs/live`` (or ``tmp``), matched by meeting and session, played to its end.

Every result says which source it came from. Nothing is invented: fields a source doesn't have stay empty.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from services import live_timing as lt

ARCHIVE_NOTE = ("F1's timing archive needs an F1 TV login since 15 Oct 2026, so FastF1 only works for sessions "
                "already in your cache.")


def _last(value: Any) -> Any:
    """Qualifying results come as [Q1, Q2, Q3]: the last part the driver took part in is the one that classifies."""
    if isinstance(value, list):
        return next((v for v in reversed(value) if v is not None), None)
    return value


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def from_openf1(year: int, event: str, code: str) -> dict[str, Any]:
    from services.openf1_comparison import bundle, historical
    session, drivers, laps = bundle(year, event, code)
    key = int(session['session_key'])

    def optional(endpoint: str) -> list[dict]:
        try:
            return historical(endpoint, {'session_key': key})
        except Exception:
            return []

    results = {int(r['driver_number']): r for r in optional('session_result') if r.get('driver_number') is not None}
    stints = optional('stints')
    weather = optional('weather')
    messages = optional('race_control')
    if not results:
        # Older sessions have no result table: fall back to the last recorded running order.
        for p in sorted(optional('position'), key=lambda r: str(r.get('date', ''))):
            if p.get('driver_number') is not None:
                results[int(p['driver_number'])] = dict(position=p.get('position'))
    rows = []
    for d in drivers:
        number = int(d['driver_number'])
        mine = laps[laps.driver_number == number].sort_values('lap_number')
        valid = mine[~mine.deleted] if 'deleted' in mine else mine
        last = mine.iloc[-1] if len(mine) else None
        res = results.get(number, {})
        gap = _last(res.get('gap_to_leader'))
        position = res.get('position')
        status = 'DSQ' if res.get('dsq') else 'DNS' if res.get('dns') else 'DNF' if res.get('dnf') else ('Finished' if res else '')
        compound = None
        own = sorted((s for s in stints if s.get('driver_number') == number), key=lambda s: s.get('stint_number') or 0)
        if own:
            compound = own[-1].get('compound')
        leader = position == 1
        rows.append(dict(
            driver=str(d.get('name_acronym') or number), number=str(number), name=d.get('full_name'), team=d.get('team_name'),
            color=d.get('team_colour'), position=int(position) if _number(position) is not None else None,
            time=_number(_last(res.get('duration'))) if leader else _number(gap),
            gap=None if leader or _number(gap) is not None or gap in (None, '') else str(gap),
            status=status,
            best=_number(valid.lap_duration.min()) if len(valid) else None,
            last=_number(last.lap_duration) if last is not None else None,
            s1=_number(last.get('duration_sector_1')) if last is not None else None,
            s2=_number(last.get('duration_sector_2')) if last is not None else None,
            s3=_number(last.get('duration_sector_3')) if last is not None else None,
            compound=compound, speed=_number(last.get('st_speed')) if last is not None else None,
            lap=int(last.lap_number) if last is not None else None))
    rows.sort(key=lambda r: r['position'] if r['position'] is not None else 999)
    latest = weather[-1] if weather else None
    return dict(
        rows=rows,
        weather=dict(AirTemp=latest.get('air_temperature'), TrackTemp=latest.get('track_temperature'),
                     WindSpeed=latest.get('wind_speed'), Rainfall=bool(latest.get('rainfall'))) if latest else None,
        messages=[dict(Time=m.get('date'), Category=m.get('category'), Flag=m.get('flag'), Message=m.get('message'))
                  for m in sorted(messages, key=lambda m: str(m.get('date', '')))],
        track=[], source='OpenF1',
        mode='From OpenF1 (free, non-commercial data). Lap channels are each driver\'s last timed lap; '
             'deleted laps are left out of the best times.')


def from_recording(path: Path) -> dict[str, Any]:
    snap = lt.final_snapshot(path)
    if not snap.get('drivers'):
        raise ValueError(f'{Path(path).name} has no timing rows.')
    rows = []
    for r in snap['drivers']:
        sectors = [lt.clock_seconds((s or {}).get('value')) for s in r.get('sectors') or []] + [None, None, None]
        rows.append(dict(
            driver=r['code'], number=r['number'], name=r['name'], team=r['team'], color=r['color'],
            position=r['position'] if r['position'] < 99 else None, time=None,
            gap=None if r['position'] == 1 else r.get('gap'),
            status='Stopped' if r.get('retired') or r.get('stopped') else '',
            best=lt.clock_seconds(r.get('best')), last=lt.clock_seconds((r.get('last') or {}).get('value')),
            s1=sectors[0], s2=sectors[1], s3=sectors[2], compound=(r.get('tyre') or {}).get('compound'),
            speed=r.get('speed_trap'), lap=r.get('laps')))
    raw = snap.get('weather_raw') or {}
    weather = None
    if raw:
        weather = dict(AirTemp=_number(raw.get('AirTemp')), TrackTemp=_number(raw.get('TrackTemp')),
                       WindSpeed=_number(raw.get('WindSpeed')), Rainfall=str(raw.get('Rainfall', '0')) not in ('0', '', 'False'))
    s = snap.get('session') or {}
    return dict(
        rows=rows, weather=weather,
        messages=[dict(Time=m.get('Utc'), Category=m.get('Category'), Flag=m.get('Flag'), Message=m.get('Message'))
                  for m in snap.get('all_race_control') or []],
        track=[], source=f'Your live recording ({Path(path).name})',
        mode=f"The last timing screen of your own recording of {s.get('meeting') or 'this session'} "
             f"({s.get('name') or 'session'}). It only covers what was recorded.")


def timing(year: int, event: str, code: str, primary: Exception | None, folders: list[Path]) -> dict[str, Any]:
    reasons = []
    try:
        return from_openf1(year, event, code)
    except Exception as exc:
        reasons.append(f'OpenF1: {exc}')
    recording = None
    try:
        recording = lt.find_recording(folders, year, event, code)
        if recording:
            return from_recording(recording)
    except Exception as exc:
        reasons.append(f'Your recording {recording.name if recording else ""}: {exc}')
    if not recording:
        reasons.append('No live recording of yours matches this session.')
    raise ValueError(f"Timing isn't available for {year} {event} ({code}). {ARCHIVE_NOTE} "
                     + ' '.join(reasons) + ' Pick a cached session, a 2023 or later session that has finished, '
                     'or record the session from the Live page.')
