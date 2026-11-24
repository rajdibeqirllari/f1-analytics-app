"""Explicit OpenF1 fallback; never impersonates a complete FastF1 Session.

Only real timed laps, car channels and time-matched coordinates are used.
Historical responses are cached separately from FastF1's cache.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from threading import Lock

import numpy as np
import pandas as pd

from services.openf1_service import openf1_get, session_code_to_openf1_name

CACHE = Path(__file__).resolve().parents[1] / 'outputs' / 'openf1_cache'
_lock = Lock()
_last_request = 0.0
NOTICE = ('OpenF1 fallback · non-commercial use. Available race-control lap deletions are applied; '
          'completeness and qualifying segments are not certified. Fastest means fastest non-deleted timed non-out lap. '
          'Missing DRS/2026 energy-mode channels are unavailable, not measured OFF. '
          'Ghosts share an illustrative route, not exact racing lines.')


def apply_lap_deletions(laps, messages):
    """Apply deletion/reinstatement notices; never adjust recorded durations."""
    result=laps.copy();result['deleted']=False
    for item in sorted(messages,key=lambda m:str(m.get('date',''))):
        message=str(item.get('message','')).upper()
        if 'TIME' not in message or not re.search(r'\b(DELETED|REINSTATED)\b',message):continue
        car=re.search(r'\bCAR\s+(\d+)\b',message)
        driver=int(car.group(1)) if car else item.get('driver_number')
        number=re.search(r'\bLAP\s+(\d+)\b',message)
        duration=re.search(r'\bTIME\s+(\d+):(\d{2}\.\d+)\b',message)
        if driver is None:raise ValueError('Cannot identify the driver in a lap-deletion notice; fastest-valid selection is unsafe.')
        mask=result.driver_number.eq(int(driver))
        if duration:
            # OpenF1's lap numbering can differ from the lap number in the
            # notice. Match the recorded deleted TIME for that car first.
            seconds=int(duration.group(1))*60+float(duration.group(2))
            mask &= (result.lap_duration-seconds).abs()<.0011
        elif number:mask &= result.lap_number.eq(int(number.group(1)))
        else:raise ValueError('Cannot identify the lap in a deletion notice; fastest-valid selection is unsafe.')
        result.loc[mask,'deleted']='REINSTATED' not in message
    return result


def historical(endpoint, params):
    """Cache successful nonempty historical responses; respect free-tier pacing."""
    global _last_request
    key = hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()
    path = CACHE / (key + '.json')
    with _lock:
        if path.exists() and (endpoint not in ('sessions', 'meetings') or time.time() - path.stat().st_mtime < 86400):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, list) and data:
                    return data
            except (OSError, ValueError):
                pass
        delay = max(0, 2.1 - (time.monotonic() - _last_request))
        if delay:
            time.sleep(delay)
        _last_request = time.monotonic()
        data = openf1_get(endpoint, params)
        if data:
            CACHE.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data), encoding='utf-8')
            temporary.replace(path)
        return data


def _norm(value):
    """Lower-case ASCII words: 'São Paulo Grand Prix' -> 'sao paulo grand prix'."""
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


# Event adjectives differ from the API's country and venue names. Match precisely,
# never pick the first race in a country (Spain/USA/Italy have multiple venues).
ALIASES = {'belgian': 'belgium', 'italian': 'monza', 'dutch': 'netherlands',
           'hungarian': 'hungary', 'australian': 'australia', 'chinese': 'china',
           'japanese': 'japan', 'canadian': 'canada', 'austrian': 'austria',
           'british': 'silverstone', 'united states': 'austin',
           'mexico city': 'mexico', 'mexican': 'mexico', 'sao paulo': 'brazil', 'brazilian': 'brazil',
           'french': 'france', 'spanish': 'madrid', 'barcelona': 'barcelona',
           'abu dhabi': 'yas', 'saudi arabian': 'jeddah', 'emilia romagna': 'imola',
           'azerbaijan': 'baku', 'las vegas': 'las vegas', 'miami': 'miami', 'qatar': 'qatar',
           'bahrain': 'bahrain', 'singapore': 'singapore', 'monaco': 'monaco', 'portuguese': 'portugal'}


def resolve(year, event, code):
    if int(year) < 2023:
        raise ValueError('OpenF1 historical fallback supports 2023 onwards.')
    sessions = historical('sessions', {'year': int(year)})
    wanted = session_code_to_openf1_name(code).lower()
    candidates = [s for s in sessions if str(s.get('session_name', '')).lower() == wanted and not s.get('is_cancelled')]
    # 1) Exact meeting name ("Abu Dhabi Grand Prix") via OpenF1 meetings.
    matches = []
    try:
        meetings = historical('meetings', {'year': int(year)})
    except Exception:
        meetings = []
    target = _norm(event)
    keys = {m.get('meeting_key') for m in meetings if target and target in (_norm(m.get('meeting_name')), _norm(m.get('meeting_official_name')))}
    if keys:
        matches = [s for s in candidates if s.get('meeting_key') in keys]
    # 2) Country / venue words.
    if len(matches) != 1:
        query = target.replace('grand prix', '').strip()
        if query == 'spanish' and int(year) < 2026:
            query = 'barcelona'
        else:
            query = ALIASES.get(query, query)
        matches = [s for s in candidates if query and query in _norm(' '.join(str(s.get(k, '')) for k in
                   ('country_name', 'location', 'circuit_short_name', 'meeting_name')))]
    if len(matches) != 1:
        raise ValueError(f'OpenF1 cannot uniquely identify {year} {event} ({code}); no substitute session was selected.')
    session = matches[0]
    end = pd.to_datetime(session.get('date_end'), utc=True, errors='coerce')
    if pd.isna(end) or end + pd.Timedelta(minutes=30) > pd.Timestamp.now(tz='UTC'):
        raise ValueError('OpenF1 fallback only loads completed historical sessions, not live or future sessions.')
    return session


def bundle(year, event, code):
    session = resolve(year, event, code)
    key = int(session['session_key'])
    drivers = historical('drivers', {'session_key': key})
    laps = pd.DataFrame(historical('laps', {'session_key': key}))
    required = {'driver_number', 'lap_number', 'lap_duration', 'date_start'}
    if laps.empty or not required.issubset(laps):
        raise ValueError('OpenF1 has no timestamped timed laps for this session.')
    laps['lap_duration'] = pd.to_numeric(laps['lap_duration'], errors='coerce')
    laps = laps.dropna(subset=list(required))
    laps = laps[laps.lap_duration > 0]
    messages=historical('race_control',{'session_key':key})
    laps=apply_lap_deletions(laps,messages)
    return session, drivers, laps


def catalog(year, event, code):
    session, drivers, laps = bundle(year, event, code)
    entries = {}
    status = {}
    try:   # why a driver has no timed lap (retired on lap one, did not start)
        for r in historical('session_result', {'session_key': int(session['session_key'])}):
            status[r.get('driver_number')] = 'DSQ' if r.get('dsq') else 'DNS' if r.get('dns') else 'DNF' if r.get('dnf') else ''
    except Exception:
        pass
    for d in drivers:
        numbers = laps[laps.driver_number == d['driver_number']].lap_number
        acronym = str(d.get('name_acronym') or d['driver_number'])
        # Drivers without a timed lap stay in the grid (shown disabled), so nobody silently disappears.
        entries[acronym] = dict(name=d.get('full_name') or acronym, team=d.get('team_name') or '',
            color=d.get('team_colour') or '', portrait='',
            laps=sorted({int(n) for n in numbers}))
        if numbers.empty:
            entries[acronym]['status'] = status.get(d['driver_number']) or 'No timed lap'
    if sum(1 for e in entries.values() if e['laps']) < 2:
        raise ValueError('OpenF1 has fewer than two drivers with timed laps.')
    return dict(drivers=entries, event=event, session=session['session_name'], source='OpenF1',
                qualifying_segments=False, notice=NOTICE)


def comparison(selection):
    from services.video_comparison import Comparison, ComparisonLap, prepare_lap_samples
    if selection.qualifying_part != 'All':
        raise ValueError('OpenF1 fallback cannot verify Q1/Q2/Q3 boundaries. Select All qualifying segments.')
    session, drivers, laps = bundle(selection.year, selection.event, selection.session)
    key = int(session['session_key'])
    prepared = []
    for code, number in [(selection.driver_a, selection.lap_a), (selection.driver_b, selection.lap_b)]:
        driver = next((d for d in drivers if str(d.get('name_acronym') or d['driver_number']) == code), None)
        if driver is None:
            raise ValueError(f'OpenF1 has no driver {code} in this session.')
        rows = laps[laps.driver_number == driver['driver_number']]
        if number is not None:
            rows = rows[rows.lap_number == number]
        elif 'is_pit_out_lap' in rows:
            rows = rows[rows.is_pit_out_lap != True]  # noqa: E712
        if number is None:rows=rows[~rows.deleted]
        if rows.empty:
            raise ValueError(f'OpenF1 has no selected timed lap for {code}.')
        lap = rows.sort_values('lap_duration').iloc[0]
        if bool(lap.deleted):
            raise ValueError(f'{code} lap {int(lap.lap_number)} was deleted by race control. Select a non-deleted lap.')
        start = pd.Timestamp(lap.date_start)
        duration = float(lap.lap_duration)
        end = start + pd.Timedelta(seconds=duration)
        params = {'session_key': key, 'driver_number': int(driver['driver_number'])}
        frames = []
        for endpoint in ('car_data', 'location'):
            frame = pd.DataFrame(historical(endpoint, params))
            if frame.empty or 'date' not in frame:
                raise ValueError(f'OpenF1 has no {endpoint} timestamps for {code}.')
            frame['Date'] = pd.to_datetime(frame.date, utc=True, format='ISO8601', errors='coerce')
            frame = frame.dropna(subset=['Date']).sort_values('Date').drop_duplicates('Date')
            frame = frame[(frame.Date >= start - pd.Timedelta(seconds=.5)) &
                          (frame.Date <= end + pd.Timedelta(seconds=.5))]
            if len(frame) < 20 or (frame.Date.diff().dt.total_seconds().max() > 2):
                raise ValueError(f'OpenF1 {endpoint} coverage for {code} is incomplete; choose another lap.')
            frames.append(frame)
        car, location = frames
        mandatory = {'speed', 'throttle', 'brake', 'rpm', 'n_gear'}
        if not mandatory.issubset(car) or car[list(mandatory)].isna().any().any():
            raise ValueError(f'OpenF1 pedal/speed channels for {code} are incomplete.')
        if not {'x', 'y', 'z'}.issubset(location):
            raise ValueError(f'OpenF1 has no spatial coordinates for {code}.')
        location = location.dropna(subset=['x', 'y', 'z'])
        if len(location) < 20 or location[['x', 'y']].max().sub(location[['x', 'y']].min()).max() < 100:
            raise ValueError(f'OpenF1 positions for {code} do not describe a usable lap.')
        raw = pd.merge_asof(car, location[['Date', 'x', 'y', 'z']], on='Date',
                            direction='nearest', tolerance=pd.Timedelta(milliseconds=500))
        if raw[['x', 'y', 'z']].isna().any().any():
            raise ValueError(f'OpenF1 positions cannot be matched reliably to telemetry for {code}.')
        raw = raw.rename(columns={'speed': 'Speed', 'throttle': 'Throttle', 'brake': 'Brake',
             'rpm': 'RPM', 'n_gear': 'nGear', 'drs': 'DRS', 'x': 'X', 'y': 'Y', 'z': 'Z'})
        raw['SessionTime'] = raw.Date - start
        samples, warnings = prepare_lap_samples(raw, 0, duration)
        warnings.append(NOTICE)
        if lap.get('is_pit_out_lap') is True:
            warnings.append('This lap is a pit-out lap.')
        color = str(driver.get('team_colour') or '62d7da').lstrip('#')
        prepared.append(ComparisonLap(code, str(driver.get('full_name') or code),
            str(driver.get('team_name') or ''), '#' + color, int(lap.lap_number), duration, samples, warnings,
            source='OpenF1', sectors=tuple(None if pd.isna(lap.get(f'duration_sector_{i}'))
                else float(lap[f'duration_sector_{i}']) for i in (1, 2, 3)),
            unavailable_channels=('drs',) if 'DRS' not in raw or raw.DRS.isna().all() else ()))
    reference = min(prepared, key=lambda lap: lap.lap_time).samples.drop_duplicates('progress')
    grid = np.linspace(0, 1, 720)
    track = np.column_stack([grid] + [np.interp(grid, reference.progress, reference[c]) for c in ('x', 'y', 'z')])
    return Comparison(selection.year, selection.event, session['session_name'], tuple(prepared), track,
                      [f'{lap.code}: {w}' for lap in prepared for w in lap.warnings])
