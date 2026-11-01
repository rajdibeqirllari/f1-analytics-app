"""Live timing from F1's free stream, recorded by FastF1's SignalR client.

A recording is a text file of messages, one per line, as written by
fastf1.livetiming.client.SignalRClient:
  * the subscription reply: one line per topic, ``['Topic', '<json string>', '']``
  * live updates: ``['Topic', {...delta...}, '2026-10-31T21:03:12.345Z']``

Updates are partial: they are merged into the running state. Lists arrive as dicts keyed by
index ("0", "1", …). The ``.z`` topics (car positions, car telemetry) need an F1 TV login and
are skipped.

Two ways to read a recording:
  * follow: keep reading new lines as they are written (live)
  * replay: play the recorded messages back on a clock, at any speed, with seeking
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

TOPICS_KEPT = {'DriverList', 'TimingData', 'TimingAppData', 'TimingStats', 'SessionInfo', 'SessionStatus',
               'TrackStatus', 'RaceControlMessages', 'ExtrapolatedClock', 'LapCount', 'WeatherData', 'SessionData'}
TRACK_STATUS = {'1': ('green', 'Track clear'), '2': ('yellow', 'Yellow flag'), '3': ('yellow', 'Flag'),
                '4': ('sc', 'Safety car'), '5': ('red', 'Red flag'), '6': ('vsc', 'Virtual safety car'),
                '7': ('vsc', 'VSC ending')}


def parse_line(line: str):
    line = line.strip()
    if not line or line[0] != '[':
        return None
    try:
        msg = ast.literal_eval(line)
    except (ValueError, SyntaxError):
        try:
            msg = json.loads(line)
        except ValueError:
            return None
    if not isinstance(msg, list) or len(msg) < 2:
        return None
    topic, data = msg[0], msg[1]
    if topic not in TOPICS_KEPT:
        return None
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return None
    ts = msg[2] if len(msg) > 2 and msg[2] else None
    return topic, data, parse_ts(ts) if ts else None


def parse_ts(value: str) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def merge(target: Any, patch: Any) -> Any:
    """Deep-merge a live delta into the current state."""
    if isinstance(patch, dict):
        if isinstance(target, list):
            for k, v in patch.items():
                if str(k).isdigit():
                    i = int(k)
                    while len(target) <= i:
                        target.append({})
                    target[i] = merge(target[i], v)
            return target
        if not isinstance(target, dict):
            target = {}
        if patch.get('_deleted'):
            for k in patch['_deleted']:
                target.pop(k, None)
        for k, v in patch.items():
            if k != '_deleted':
                target[k] = merge(target.get(k), v)
        return target
    return patch


def clock_seconds(text: Any) -> float | None:
    """'1:23.456' / '00:12:00' / '+0.123' / '1 L' → seconds (None for laps or blanks)."""
    if text in (None, ''):
        return None
    s = str(text).strip().lstrip('+')
    if not s or 'L' in s.upper():
        return None
    try:
        parts = [float(p) for p in s.split(':')]
    except ValueError:
        return None
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


class LiveState:
    def __init__(self):
        self.topics: dict[str, Any] = {}
        self.last_ts: float | None = None
        self.first_ts: float | None = None
        # Where each car last crossed a timing segment: (sector, segment, timestamp)
        self.marks: dict[str, tuple[int, int, float]] = {}
        self.lap_marks: dict[str, float] = {}

    def apply(self, topic: str, data: Any, ts: float | None):
        if ts is not None:
            self.last_ts = ts if self.last_ts is None else max(self.last_ts, ts)
            if self.first_ts is None:
                self.first_ts = ts
        if topic == 'TimingData' and ts is not None and isinstance(data, dict):
            for num, line in (data.get('Lines') or {}).items():
                self._note_segments(num, line, ts)
        if topic == 'RaceControlMessages' and isinstance(data, dict) and isinstance(data.get('Messages'), dict):
            cur = self.topics.setdefault('RaceControlMessages', {'Messages': []})
            msgs = cur.setdefault('Messages', [])
            if isinstance(msgs, dict):
                msgs = cur['Messages'] = list(msgs.values())
            msgs.extend(data['Messages'].values())
            return
        self.topics[topic] = merge(self.topics.get(topic), data)

    def _note_segments(self, num: str, line: dict, ts: float):
        if not isinstance(line, dict):
            return
        sectors = line.get('Sectors')
        items = sectors.items() if isinstance(sectors, dict) else enumerate(sectors or [])
        best = None
        for si, sec in items:
            segs = sec.get('Segments') if isinstance(sec, dict) else None
            if not segs:
                continue
            seg_items = segs.items() if isinstance(segs, dict) else enumerate(segs)
            for gi, seg in seg_items:
                if isinstance(seg, dict) and seg.get('Status', 0):
                    key = (int(si), int(gi))
                    if best is None or key > best:
                        best = key
        if best is not None:
            self.marks[num] = (best[0], best[1], ts)
        if 'LastLapTime' in line or line.get('NumberOfLaps') is not None:
            self.lap_marks[num] = ts

    # ------------------------------------------------------------- snapshot
    def snapshot(self, now: float | None) -> dict[str, Any]:
        now = now if now is not None else (self.last_ts or time.time())
        t = self.topics
        info = t.get('SessionInfo') or {}
        timing = (t.get('TimingData') or {})
        lines = timing.get('Lines') or {}
        drivers = t.get('DriverList') or {}
        app = (t.get('TimingAppData') or {}).get('Lines') or {}
        stats = (t.get('TimingStats') or {}).get('Lines') or {}
        part = timing.get('SessionPart')
        qualifying = str(info.get('Type', '')).lower().startswith('qual') or part is not None
        total_segments = 0
        seg_counts: list[int] = []
        rows = []
        overall_best: list[float] = [float('inf')] * 3
        for num, ln in lines.items():
            if not isinstance(ln, dict):
                continue
            for i, s in enumerate(_as_list(ln.get('Sectors'))[:3]):
                v = clock_seconds((s or {}).get('Value'))
                if v and (s or {}).get('OverallFastest'):
                    overall_best[i] = min(overall_best[i], v)
        for num, ln in lines.items():
            if not isinstance(ln, dict):
                continue
            d = drivers.get(num) or {}
            secs = _as_list(ln.get('Sectors'))[:3]
            if not seg_counts and secs:
                seg_counts = [len(_as_list((s or {}).get('Segments'))) for s in secs]
                total_segments = sum(seg_counts)
            stints = _as_list((app.get(num) or {}).get('Stints'))
            stint = stints[-1] if stints else {}
            gap, interval = _gaps(ln, part)
            best_lap = (ln.get('BestLapTime') or {}).get('Value')
            if qualifying and isinstance(ln.get('BestLapTimes'), (list, dict)) and part:
                parts = _as_list(ln.get('BestLapTimes'))
                if len(parts) >= int(part):
                    best_lap = (parts[int(part) - 1] or {}).get('Value') or best_lap
            last = ln.get('LastLapTime') or {}
            rows.append(dict(
                number=num, code=d.get('Tla') or num, name=d.get('FullName') or d.get('BroadcastName') or num,
                team=d.get('TeamName') or '', color=(d.get('TeamColour') or '62d7da'),
                position=_int(ln.get('Position')) or _int(d.get('Line')) or 99,
                gap=gap, interval=interval, best=best_lap or None,
                last=dict(value=last.get('Value') or None, personal=bool(last.get('PersonalFastest')), overall=bool(last.get('OverallFastest'))),
                sectors=[dict(value=(s or {}).get('Value') or None, personal=bool((s or {}).get('PersonalFastest')),
                              overall=bool((s or {}).get('OverallFastest'))) for s in secs],
                segments=[[_int(g.get('Status')) or 0 for g in _as_list((s or {}).get('Segments'))] for s in secs],
                laps=_int(ln.get('NumberOfLaps')), in_pit=bool(ln.get('InPit')), pit_out=bool(ln.get('PitOut')),
                retired=bool(ln.get('Retired')), stopped=bool(ln.get('Stopped')), knocked_out=bool(ln.get('KnockedOut')),
                cutoff=bool(ln.get('Cutoff')),
                tyre=dict(compound=(stint.get('Compound') or '').upper() or None, new=str(stint.get('New', '')).lower() == 'true',
                          laps=_int(stint.get('TotalLaps'))),
                speed_trap=_float(((stats.get(num) or {}).get('BestSpeeds') or {}).get('ST', {}).get('Value')),
            ))
        rows.sort(key=lambda r: r['position'])
        for r in rows:
            r['progress'] = self._progress(r, total_segments, seg_counts, now)
        status = (t.get('TrackStatus') or {})
        flag, flag_text = TRACK_STATUS.get(str(status.get('Status', '1')), ('green', status.get('Message') or 'Track clear'))
        clock = t.get('ExtrapolatedClock') or {}
        remaining = clock_seconds(clock.get('Remaining'))
        if remaining is not None and clock.get('Extrapolating') and clock.get('Utc'):
            since = now - (parse_ts(clock['Utc']) or now)
            remaining = max(0.0, remaining - since)
        all_msgs = _as_list((t.get('RaceControlMessages') or {}).get('Messages'))
        msgs = all_msgs[-30:]
        yellows, marshal_max = active_yellows(all_msgs)
        weather = t.get('WeatherData') or {}
        lap_count = t.get('LapCount') or {}
        meeting = info.get('Meeting') or {}
        return dict(
            session=dict(name=info.get('Name') or '', type=info.get('Type') or '', meeting=meeting.get('Name') or '',
                         circuit=(meeting.get('Circuit') or {}).get('ShortName') or '', country=(meeting.get('Country') or {}).get('Name') or '',
                         status=(t.get('SessionStatus') or {}).get('Status') or '', part=part, qualifying=qualifying,
                         remaining=remaining, lap=_int(lap_count.get('CurrentLap')), laps=_int(lap_count.get('TotalLaps')),
                         year=_year(info)),
            flag=dict(state=flag, text=flag_text), drivers=rows, segments=seg_counts,
            yellows=yellows, marshal_sectors=marshal_max,
            race_control=[dict(time=m.get('Utc'), category=m.get('Category'), flag=m.get('Flag'), message=m.get('Message'),
                               driver=m.get('RacingNumber')) for m in reversed(msgs) if isinstance(m, dict)],
            weather=dict(air=_float(weather.get('AirTemp')), track=_float(weather.get('TrackTemp')),
                         rain=str(weather.get('Rainfall', '0')) not in ('0', '', 'False'), wind=_float(weather.get('WindSpeed'))),
            now=now, received=self.last_ts,
        )

    def _progress(self, row: dict, total: int, counts: list[int], now: float) -> float | None:
        """Approximate position around the lap from the last timing segment passed (0 = finish line)."""
        if not total or row['in_pit'] or row['retired'] or row['stopped']:
            return None
        mark = self.marks.get(row['number'])
        if not mark:
            return None
        si, gi, ts = mark
        idx = sum(counts[:si]) + gi + 1
        if idx > total:
            return None
        best = clock_seconds(row['best']) or clock_seconds(row['last']['value']) or 90.0
        per_seg = best / total
        ahead = min(0.95, max(0.0, (now - ts) / per_seg)) if per_seg > 0 else 0
        # A car that hasn't reported for a long time (garage, slow lap) isn't extrapolated.
        if now - ts > per_seg * 6:
            ahead = 0
        return ((idx + ahead) / total) % 1.0


def active_yellows(messages: list) -> tuple[list[dict], int]:
    """Marshal sectors under yellow right now, from race control in order.

    Sector-scoped YELLOW / DOUBLE YELLOW sets a sector, CLEAR in that sector removes it, and a track-wide
    CLEAR, GREEN or RED resets them all. Also returns the highest marshal sector number seen, which the map
    uses to place sectors around the lap.
    """
    active: dict[int, str] = {}
    highest = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        sector = _int(m.get('Sector'))
        if sector:
            highest = max(highest, sector)
        flag = str(m.get('Flag') or '').upper()
        scope = str(m.get('Scope') or '').lower()
        if scope == 'sector' and sector:
            if flag in ('YELLOW', 'DOUBLE YELLOW'):
                active[sector] = flag
            elif flag in ('CLEAR', 'GREEN'):
                active.pop(sector, None)
        elif scope == 'track' and flag in ('CLEAR', 'GREEN', 'RED', 'CHEQUERED'):
            active.clear()
    return [dict(sector=k, double=v == 'DOUBLE YELLOW') for k, v in sorted(active.items())], highest


def _as_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [v[k] for k in sorted(v, key=lambda x: int(x) if str(x).isdigit() else 0)]
    return []


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _year(info: dict) -> int | None:
    try:
        return int(str(info.get('StartDate', ''))[:4])
    except ValueError:
        return None


def _gaps(ln: dict, part: Any) -> tuple[str | None, str | None]:
    """Race: GapToLeader / IntervalToPositionAhead. Qualifying: TimeDiffToFastest / ToPositionAhead (per part)."""
    if 'GapToLeader' in ln or 'IntervalToPositionAhead' in ln:
        return ln.get('GapToLeader') or None, (ln.get('IntervalToPositionAhead') or {}).get('Value') or None
    stats = _as_list(ln.get('Stats'))
    if part and stats and len(stats) >= int(part):
        s = stats[int(part) - 1] or {}
        # The live feed spells it 'TimeDifftoPositionAhead' (lowercase t); accept both.
        return s.get('TimeDiffToFastest') or None, s.get('TimeDiffToPositionAhead') or s.get('TimeDifftoPositionAhead') or None
    return ln.get('TimeDiffToFastest') or None, ln.get('TimeDiffToPositionAhead') or ln.get('TimeDifftoPositionAhead') or None


# ------------------------------------------------------------------ sources

class Feed:
    """One recording file, followed live or replayed on a clock."""

    def __init__(self, path: Path, mode: str = 'follow', speed: float = 1.0):
        self.path = Path(path)
        self.mode = mode
        self.speed = speed
        self.lock = threading.RLock()
        self.events: list[tuple[float | None, str, Any]] = []
        self.offset = 0
        self.partial = ''
        self.state = LiveState()
        self.cursor = 0
        self.wall0 = time.time()
        self.t0: float | None = None   # replay clock origin (recording time)
        self.paused = False
        self.paused_at: float | None = None
        self._read_new()
        if mode == 'replay':
            self.t0 = self.first_time()

    def first_time(self) -> float | None:
        return next((ts for ts, *_ in self.events if ts is not None), None)

    def last_time(self) -> float | None:
        return next((ts for ts, *_ in reversed(self.events) if ts is not None), None)

    def _read_new(self):
        if not self.path.exists():
            return
        with self.path.open('r', encoding='utf-8', errors='replace') as f:
            f.seek(self.offset)
            chunk = f.read()
            self.offset = f.tell()
        text = self.partial + chunk
        lines = text.split('\n')
        self.partial = lines.pop()  # may be an unfinished line
        for line in lines:
            parsed = parse_line(line)
            if parsed:
                self.events.append((parsed[2], parsed[0], parsed[1]))

    def clock(self) -> float | None:
        if self.mode != 'replay' or self.t0 is None:
            return None
        if self.paused and self.paused_at is not None:
            return self.paused_at
        return self.t0 + (time.time() - self.wall0) * self.speed

    def seek(self, t: float):
        with self.lock:
            self.t0, self.wall0 = t, time.time()
            if self.paused:
                self.paused_at = t
            self.state, self.cursor = LiveState(), 0

    def set_speed(self, speed: float):
        with self.lock:
            now = self.clock()
            self.speed = speed
            if now is not None:
                self.t0, self.wall0 = now, time.time()

    def pause(self, paused: bool):
        with self.lock:
            if paused and not self.paused:
                self.paused_at, self.paused = self.clock(), True
            elif not paused and self.paused:
                self.t0, self.wall0, self.paused = self.paused_at, time.time(), False

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            self._read_new()
            if self.mode == 'replay':
                now = self.clock()
                if now is not None and self.state.last_ts is not None and now < self.state.last_ts:
                    self.state, self.cursor = LiveState(), 0
                while self.cursor < len(self.events):
                    ts, topic, data = self.events[self.cursor]
                    if ts is not None and now is not None and ts > now:
                        break
                    self.state.apply(topic, data, ts)
                    self.cursor += 1
            else:
                while self.cursor < len(self.events):
                    ts, topic, data = self.events[self.cursor]
                    self.state.apply(topic, data, ts)
                    self.cursor += 1
                # Live: extrapolate from the stream's own clock, advanced by wall time since the last line.
                now = (self.state.last_ts + (time.time() - self._last_wall())) if self.state.last_ts else None
            snap = self.state.snapshot(now)
            snap['feed'] = dict(mode=self.mode, file=self.path.name, speed=self.speed, paused=self.paused,
                                start=self.first_time(), end=self.last_time(), clock=now, messages=len(self.events),
                                updated=self.path.stat().st_mtime if self.path.exists() else None)
            return snap

    def _last_wall(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return time.time()


class Recorder:
    """Runs scripts/record_live.py in the background, writing to a file."""

    def __init__(self, root: Path):
        self.root = root
        self.proc: subprocess.Popen | None = None
        self.path: Path | None = None
        self.log: Path | None = None

    def start(self, path: Path) -> None:
        if self.running():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.log = path.with_suffix('.log')
        logf = self.log.open('w', encoding='utf-8')
        self.proc = subprocess.Popen([sys.executable, str(self.root / 'scripts' / 'record_live.py'), str(path)],
                                     cwd=str(self.root), stdout=logf, stderr=subprocess.STDOUT)

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.running():
            self.proc.terminate()

    def status(self) -> dict[str, Any]:
        tail = ''
        if self.log and self.log.exists():
            tail = self.log.read_text(encoding='utf-8', errors='replace')[-800:]
        return dict(running=self.running(), file=self.path.name if self.path else None,
                    exit_code=None if self.proc is None or self.running() else self.proc.returncode, log=tail)


# ------------------------------------------------------------------ track outline

def _outline_from(year: int, event: str, code: str, points: int) -> dict[str, Any]:
    import numpy as np
    import fastf1
    s = fastf1.get_session(year, event, code)
    s.load(laps=True, telemetry=True, weather=False, messages=False)
    tel = s.laps.pick_fastest().get_telemetry()
    x, yy, d = tel['X'].to_numpy(float), tel['Y'].to_numpy(float), tel['Distance'].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(yy) & np.isfinite(d)
    x, yy, d = x[ok], yy[ok], d[ok]
    if len(x) < 50:
        raise ValueError('too few position samples')
    grid = np.linspace(0, d[-1], points, endpoint=False)   # lap telemetry starts at the finish line
    rotation = 0.0
    try:
        rotation = float(s.get_circuit_info().rotation)
    except Exception:
        pass
    return dict(x=np.round(np.interp(grid, d, x)).tolist(), y=np.round(np.interp(grid, d, yy)).tolist(),
                rotation=rotation, length=float(d[-1]), source=f'{year} {s.event["EventName"]} {code}')


def track_outline(year: int | None, event: str, points: int = 500, store: Path | None = None) -> dict[str, Any]:
    """Circuit shape from a past fastest lap at this event, starting at the finish line.

    The session being watched is skipped: it's still running, and downloading it can stall for minutes.
    Past seasons are tried from the local cache first (no network), then online. Results are saved.
    """
    import fastf1
    import re as _re
    slug = _re.sub(r'[^a-z0-9]+', '-', event.lower()).strip('-')
    saved = store / f'{slug}.json' if store else None
    if saved and saved.is_file():
        return json.loads(saved.read_text(encoding='utf-8'))
    years = [y for y in ((year or 2026) - 1, (year or 2026) - 2, (year or 2026) - 3) if y >= 2018]
    tried = []
    for offline in (True, False):
        for y in years:
            for code in ('Q', 'R'):
                try:
                    fastf1.Cache.offline_mode(offline)
                    result = _outline_from(y, event, code, points)
                    if saved:
                        saved.parent.mkdir(parents=True, exist_ok=True)
                        saved.write_text(json.dumps(result), encoding='utf-8')
                    return result
                except Exception as exc:
                    tried.append(f"{y} {code}{' (cache)' if offline else ''}: {str(exc)[:80]}")
                finally:
                    fastf1.Cache.offline_mode(False)
    raise ValueError('No circuit outline available. ' + '; '.join(tried[:4]))
