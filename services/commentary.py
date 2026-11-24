"""AI commentator for the live timing feed.

The Live page polls /api/live/state about once a second. Each poll hands the latest LiveState + snapshot to
``Commentator.observe``, which compares it with the previous one and turns the differences into events:

  * race control messages (flags, investigations, penalties, deleted laps…)
  * qualifying: new best laps, provisional pole, drivers dropping into / escaping the elimination zone, Q-part changes
  * race: overtakes, pit stops and tyre changes, fastest laps, retirements
  * team radio: the clip is downloaded from F1's static archive, transcribed with faster-whisper, then commented on

A background thread turns the most important pending events into one short spoken line. With an Anthropic key
(``ANTHROPIC_API_KEY`` in the environment or in the project's ``.env``) Claude writes the line; without one a plain
sentence built from the facts is used, so the feature works offline too.

Everything runs on the feed's clock, so a replay is commented exactly like the live session (events that are already
too old when their turn comes — e.g. at 30× replay speed — are dropped).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from services.live_timing import _as_list, clock_seconds, parse_ts

MODEL = os.environ.get('RACEHYPE_COMMENTARY_MODEL', 'claude-haiku-5-5')
OLLAMA_URL = os.environ.get('RACEHYPE_OLLAMA_URL', 'http://127.0.0.1:11434')
OLLAMA_MODEL = os.environ.get('RACEHYPE_OLLAMA_MODEL', 'qwen2.5:7b')
WHISPER_MODEL = os.environ.get('RACEHYPE_WHISPER_MODEL', 'small.en')
STATIC = 'https://livetiming.formula1.com/static/'
MAX_AGE = 15.0        # seconds (at 1x) an event may wait before it is too old to mention: commentary must be NOW
URGENT_AGE = 30.0     # red flags, safety cars, pole… may wait a little longer
URGENT = 5
LEAD = 1.5            # start writing the next line this long before the current one finishes (AI + voice take ~2 s)

SYSTEM = """You are the live commentator for "Race Hype", an F1 fan channel, calling a session from the live timing feed.
Write ONE line to be read aloud by a text-to-speech voice: 1-2 short sentences, at most 30 words.
Sound like a real TV commentator: energetic, natural, specific. Vary your openings; never start two lines the same way.
Use driver surnames (Verstappen, Norris). Use only the facts given; never invent incidents, gaps or reasons.
Keep numbers short like a TV commentator: lap times to the tenth (1:10.5), gaps to the tenth (0.3), never three decimals.
If several events are given, lead with the most important one and fold in the rest briefly.
Team radio: NEVER quote it word for word. Summarize what the driver or engineer said in your own words, as reported speech
("Hamilton's engineer is telling him to look after the rears"). Transcripts come from speech recognition and may contain errors:
if the gist is unclear, just say the driver has been talking to the team.
Match the intensity you are given: HIGH = a big moment, sound genuinely excited, short punchy phrases and an exclamation;
NORMAL = lively but measured; LOW = calm, conversational.
No emojis, hashtags, stage directions or quotation marks around the whole line."""

LANG = {'en': 'Write in English.', 'sq': 'Write in Albanian (shqip). Keep driver surnames and team names as they are.'}
TRANSLATE = {'sq': 'Translate the user\'s text into Albanian (shqip). Translate only: add nothing, leave nothing out. '
                   'Keep driver surnames, team names, numbers and positions like P3 exactly as they are. Reply with the translation only.'}


def template_line(batch: list[dict]) -> str:
    """The plain line built from the facts themselves (no AI)."""
    return ' '.join(e['text'] if e['text'].endswith(('.', '!', '?', '"')) else e['text'] + '.'
                    for i, e in enumerate(batch[:2]) if i == 0 or e['prio'] >= 3)


def _env_key() -> str | None:
    key = os.environ.get('ANTHROPIC_API_KEY')
    if key:
        return key.strip()
    env = Path(__file__).resolve().parents[1] / '.env'
    try:
        for line in env.read_text(encoding='utf-8').splitlines():
            k, _, v = line.partition('=')
            if k.strip() == 'ANTHROPIC_API_KEY' and v.strip():
                return v.strip().strip('"\'')
    except OSError:
        pass
    return None


def surname(row: dict) -> str:
    name = str(row.get('name') or row.get('code') or '')
    last = name.split()[-1] if name.split() else name
    return last.capitalize() if last.isupper() else last


def _hms(ts: float | None) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%H:%M:%S') if ts else ''


def _rc_priority(m: dict) -> int:
    """How worth mentioning a race control message is (0 = skip)."""
    text = str(m.get('Message') or '').upper()
    flag = str(m.get('Flag') or '').upper()
    cat = str(m.get('Category') or '').upper()
    if flag == 'BLUE' or text.startswith('CLEAR IN TRACK SECTOR') or 'BLUE FLAG' in text:
        return 0
    if flag == 'RED' or 'SAFETY CAR' in text or cat == 'SAFETYCAR':
        return 5
    if flag == 'CHEQUERED':
        return 4
    if 'PENALTY' in text or 'STEWARDS' in text or 'INVESTIGATION' in text or 'REPRIMAND' in text:
        return 4
    if flag == 'DOUBLE YELLOW':
        return 3
    if 'DELETED' in text or 'NOTED' in text or 'GREEN LIGHT' in text or 'RAIN' in text:
        return 3
    if flag == 'YELLOW':
        return 2
    if flag in ('GREEN', 'CLEAR') and str(m.get('Scope') or '').lower() == 'track':
        return 2
    if 'DRS' in text:
        return 1
    return 1


COMPOUNDS = {'SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'}
KEEP_UPPER = {'FIA', 'DRS', 'VSC', 'SC', 'Q1', 'Q2', 'Q3', 'FP1', 'FP2', 'FP3', 'S1', 'S2', 'S3'}


def _rc_text(text: str, rows: dict) -> str:
    """'CAR 87 (BEA) LAP DELETED - TRACK LIMITS (14:59:59)' → 'Car 87 (BEA) lap deleted - track limits'."""
    text = re.sub(r'\s*\(?\b\d{1,2}:\d{2}:\d{2}\)?', '', text).strip()
    codes = {r['code'] for r in rows.values()} | KEEP_UPPER
    words = [w if re.sub(r'\W', '', w) in codes else w.lower() for w in text.split()]
    out = ' '.join(words)
    return out[:1].upper() + out[1:]


VOICES = {  # Kokoro English voices that suit commentary (b* = British, a* = American)
    'bm_george': 'George (British)', 'bm_lewis': 'Lewis (British)', 'bm_daniel': 'Daniel (British)', 'bm_fable': 'Fable (British)',
    'am_michael': 'Michael (American)', 'am_adam': 'Adam (American)', 'am_eric': 'Eric (American)', 'am_onyx': 'Onyx (American)',
    'am_puck': 'Puck (American)', 'bf_emma': 'Emma (British)', 'af_heart': 'Heart (American)', 'af_bella': 'Bella (American)',
}
DEFAULT_VOICE = os.environ.get('RACEHYPE_VOICE', 'bm_george')

class Speaker:
    """Kokoro text-to-speech (Apache 2.0, runs locally): one WAV per commentary line, faster on bigger moments."""

    def __init__(self, root: Path):
        self.dir = root / 'assets' / 'tts'
        self.out = root / 'outputs' / 'live' / 'voice'
        self._model = None
        self._failed = ''
        self._lock = threading.Lock()

    def available(self) -> bool:
        return not self._failed and (self.dir / 'kokoro-v1.0.onnx').is_file() and (self.dir / 'voices-v1.0.bin').is_file()

    def _load(self):
        if self._model is None:
            try:
                from kokoro_onnx import Kokoro
                self._model = Kokoro(str(self.dir / 'kokoro-v1.0.onnx'), str(self.dir / 'voices-v1.0.bin'))
            except Exception as exc:
                self._failed = f'{type(exc).__name__}: {exc}'
                raise
        return self._model

    def speak(self, text: str, prio: int, voice: str, line_id: int, run: str = '') -> str:
        import soundfile as sf
        voice = voice if voice in VOICES else DEFAULT_VOICE
        speed = {5: 1.18, 4: 1.12, 3: 1.05}.get(prio, 0.98)   # big moments come out quicker, like a real call
        spoken = re.sub(r'\b(\d):(\d{2})\b', r'\1 \2', text)   # "1:31.7" reads as "one thirty-one point seven", no pause
        with self._lock:
            samples, rate = self._load().create(spoken, voice=voice, speed=speed, lang='en-gb' if voice.startswith('b') else 'en-us')
        self.out.mkdir(parents=True, exist_ok=True)
        # The engine-run id keeps names unique: line numbers start again after a restart, and a page that has been
        # open for hours (OBS) must never be handed an old file under a new line's name.
        name = f'line_{run}_{line_id}.wav' if run else f'line_{line_id}.wav'
        sf.write(str(self.out / name), samples, rate)
        for old in sorted(self.out.glob('line_*.wav'), key=lambda p: p.stat().st_mtime)[:-80]:
            old.unlink(missing_ok=True)   # keep only the latest lines
        return f'/api/live/voice/{name}?v={int(time.time())}', len(samples) / rate


class Commentator:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.RLock()
        self.enabled = True
        self.language = 'en'
        self.lines: deque[dict] = deque(maxlen=60)
        self.next_id = 1
        self.run = uuid4().hex[:8]   # this engine run; line ids restart with each run
        self.gen = 0                 # timeline: goes up on every new recording and every seek
        self.pending: list[dict] = []
        self.recent: deque[str] = deque(maxlen=6)
        self.busy_until = 0.0     # wall time when the line being spoken ends
        self.last_prio = 0
        self.busy = False
        self.clock: float | None = None
        self.speed = 1.0
        self.error = ''
        self.radio_status = ''
        self._radio_q: deque[dict] = deque()
        self._whisper = None
        self._whisper_failed = ''
        self.speaker = Speaker(root)
        self.voice = DEFAULT_VOICE
        self._ollama: str | None = None
        self._ollama_checked = 0.0
        self.reset(None)
        threading.Thread(target=self._writer, daemon=True, name='commentary-writer').start()
        threading.Thread(target=self._radio_worker, daemon=True, name='commentary-radio').start()

    # ------------------------------------------------------------------ state
    def reset(self, file: str | None):
        with self.lock:
            self.file = file
            self._state = None
            self.prev: dict[str, dict] | None = None
            self.prev_session: dict = {}
            self.rc_seen = 0
            self.radio_seen = 0
            self.tyres: dict[str, str] = {}
            self.fastest_lap_by: str | None = None
            self.pending.clear()
            self._radio_q.clear()
            self.recent.clear()
            # A different recording is a different story: its lines must not sit under the new one, and anything
            # still being written for the old one is dropped when it arrives (its generation no longer matches).
            self.lines.clear()
            self.gen += 1
            self.busy_until = 0.0
            self.last_prio = 0

    def settings(self, enabled: bool | None = None, language: str | None = None, voice: str | None = None):
        with self.lock:
            if voice in VOICES:
                self.voice = voice
            if enabled is not None:
                self.enabled = enabled
                if not enabled:
                    self.pending.clear()
            if language in LANG:
                self.language = language

    def engine(self) -> tuple[str, str] | None:
        """Which AI writes the lines: Claude with a key, else a local Ollama model if it is running (free), else None."""
        if _env_key():
            return 'claude', MODEL
        if time.time() - self._ollama_checked > 20:
            self._ollama_checked = time.time()
            try:
                tags = requests.get(OLLAMA_URL + '/api/tags', timeout=1.5).json().get('models', [])
                names = [m.get('name', '') for m in tags]
                found = OLLAMA_MODEL if OLLAMA_MODEL in names or OLLAMA_MODEL + ':latest' in names else None
                if found and not self._ollama:
                    # Loading the model onto the GPU takes ~30 s the first time: do it now, not on the first event.
                    threading.Thread(target=lambda: requests.post(OLLAMA_URL + '/api/generate', timeout=180,
                                     json=dict(model=found, prompt='', keep_alive='60m')), daemon=True).start()
                self._ollama = found
            except (requests.RequestException, ValueError):
                self._ollama = None
        return ('ollama', self._ollama) if self._ollama else None

    def status(self, limit: int = 20) -> dict[str, Any]:
        eng = self.engine()
        with self.lock:
            return dict(enabled=self.enabled, language=self.language, ai=bool(eng), run=f'{self.run}-{self.gen}',
                        model=(f'Claude {eng[1]}' if eng[0] == 'claude' else f'{eng[1]} on your PC (Ollama)') if eng else '',
                        error=self.error, radio=self.radio_status, lines=list(self.lines)[-limit:][::-1],
                        tts=dict(available=self.speaker.available(), voice=self.voice, voices=VOICES))

    # ---------------------------------------------------------------- observe
    def observe(self, state, snap: dict, file: str | None):
        """Compare the latest state with the previous one and queue events."""
        with self.lock:
            if file != self.file:
                self.reset(file)
            feed = snap.get('feed') or {}
            self.clock = snap.get('now')
            self.speed = float(feed.get('speed') or 1.0) if feed.get('mode') == 'replay' else 1.0
            rows = {r['number']: r for r in snap.get('drivers') or []}
            sess = snap.get('session') or {}
            rc = _as_list((state.topics.get('RaceControlMessages') or {}).get('Messages'))
            radios = _as_list((state.topics.get('TeamRadio') or {}).get('Captures'))
            if state is not self._state or self.prev is None or not rows:
                # New recording, a seek or the very first poll: take the current picture as the baseline.
                if self._state is not None and state is not self._state:
                    # A seek (or the same file opened again): a new timeline. Lines from the old one go, and a line
                    # still being generated for it is thrown away when it comes back.
                    self.gen += 1
                    self.lines.clear()
                    self.recent.clear()
                    self.busy_until = 0.0
                    self.last_prio = 0
                self._state, self.prev, self.prev_session = state, rows or None, dict(sess)
                self.rc_seen, self.radio_seen = len(rc), len(radios)
                self.tyres = {n: r['tyre']['compound'] for n, r in rows.items() if (r.get('tyre') or {}).get('compound') in COMPOUNDS}
                self.fastest_lap_by = next((n for n, r in rows.items() if r['last'].get('overall')), None)
                self.pending.clear()
                self._radio_q.clear()
                return
            if not self.enabled:
                self.prev, self.prev_session, self.rc_seen, self.radio_seen = rows, dict(sess), len(rc), len(radios)
                return
            now = self.clock
            self._race_control(rc[self.rc_seen:], rows, now)
            self.rc_seen = len(rc)
            self._session(sess, rows, now)
            if sess.get('qualifying'):
                self._qualifying(rows, sess, now)
            elif str(sess.get('type', '')).lower() in ('race', 'sprint'):
                self._race(rows, sess, now)
            else:
                self._practice(rows, now)
            self._pits(rows, sess, now)
            for cap in radios[self.radio_seen:]:
                if isinstance(cap, dict) and cap.get('Path'):
                    # When the clip really aired (its own Utc), not when we finish downloading and transcribing it.
                    aired = parse_ts(cap['Utc']) if cap.get('Utc') else None
                    item = dict(cap, session_path=(state.topics.get('SessionInfo') or {}).get('Path'), feed_t=now,
                                aired=aired if aired is not None else now, gen=self.gen,
                                row=rows.get(str(cap.get('RacingNumber'))))
                    if not self._radio_stale(item):
                        self._radio_q.append(item)
            self.radio_seen = len(radios)
            self.prev, self.prev_session = rows, dict(sess)

    def _event(self, prio: int, kind: str, text: str, now: float | None, drivers=(), **extra):
        if prio <= 0:
            return
        self.pending.append(dict(prio=prio, kind=kind, text=text, t=now, drivers=list(drivers), **extra))

    def _race_control(self, msgs: list, rows: dict, now):
        for m in msgs:
            if not isinstance(m, dict):
                continue
            text = str(m.get('Message') or '').strip()
            num = str(m.get('RacingNumber') or '')
            who = rows.get(num)
            if not who:  # "CAR 87 (BEA)" style mentions
                found = re.search(r'CAR (\d+)', text.upper())
                who = rows.get(found.group(1)) if found else None
            self._event(_rc_priority(m), 'race_control', f'Race control: {_rc_text(text, rows)}', now,
                        [who['code']] if who else [])

    def _session(self, sess: dict, rows: dict, now):
        p = self.prev_session
        if sess.get('status') != p.get('status') and sess.get('status'):
            st = sess['status']
            label = {'Started': 'The session is underway', 'Finished': 'The session is over', 'Aborted': 'The session has been stopped',
                     'Ends': 'The chequered flag is out'}.get(st)
            if label:
                name = f"Q{sess['part']}" if sess.get('qualifying') and sess.get('part') else (sess.get('name') or 'session')
                self._event(4, 'session', f'{label} ({name}).', now)
        if sess.get('qualifying') and sess.get('part') and p.get('part') and sess['part'] != p['part']:
            out = [r for r in self.prev.values() if not r.get('knocked_out') and r['number'] in rows and rows[r['number']].get('knocked_out')]
            names = ', '.join(surname(r) for r in sorted(out, key=lambda r: r['position']))
            self._event(5, 'session', f"Q{p['part']} is over, Q{sess['part']} is next." + (f' Knocked out: {names}.' if names else ''),
                        now, [r['code'] for r in out])

    def _qualifying(self, rows: dict, sess: dict, now):
        if sess.get('part') != self.prev_session.get('part'):
            return  # best laps reset with each part; the part change itself was announced
        count = len(rows)
        part = sess.get('part')
        cut = count - 5 if part == 1 else count - 11 if part == 2 else None
        danger = lambda r: cut is not None and r['position'] >= cut and not r.get('knocked_out')
        timed = sum(1 for r in rows.values() if r.get('best') and not r.get('knocked_out'))
        settled = timed >= max(8, (cut or 10))   # before most cars have a time, positions mean little
        for num, r in rows.items():
            old = self.prev.get(num)
            if not old or not r.get('best') or r['best'] == old.get('best'):
                continue
            t_new, t_old = clock_seconds(r['best']), clock_seconds(old.get('best'))
            if t_old and t_new and t_new >= t_old:
                continue
            first = not old.get('best')
            pos, was = r['position'], old['position']
            gap = f", {r['gap'].lstrip('+')} off P1" if pos > 1 and r.get('gap') else ''
            who = surname(r)
            if pos == 1:
                prev_p1 = next((o for o in self.prev.values() if o['position'] == 1 and o['number'] != num and o.get('best')), None)
                if not prev_p1:
                    self._event(2, 'fastest', f'{who} sets the early benchmark, {r["best"]}.', now, [r['code']])
                    continue
                margin = (rows.get(prev_p1['number']) or {}).get('gap')
                txt = (f'{who} is now P1 with a {r["best"]}' + (f', beating {surname(prev_p1)}\'s time by {margin.lstrip("+")}' if margin else '')
                       + f'. {surname(prev_p1)} drops to P2.')
                self._event(5 if part == 3 else 4, 'fastest', txt + (' Provisional pole!' if part == 3 else ''), now, [r['code']])
            elif settled and not first and danger(old) and not danger(r):
                dropped = [surname(o) for o in rows.values() if danger(o) and o.get('best') and self.prev.get(o['number']) and not danger(self.prev[o['number']])]
                txt = f'{who} escapes the drop zone with a {r["best"]}, up to P{pos}.' + (f' That pushes {", ".join(dropped)} into the elimination zone.' if dropped else '')
                self._event(4, 'improve', txt, now, [r['code']])
            elif settled and part == 3 and pos <= 3:
                self._event(4, 'improve', f'{who} goes P{pos} with a {r["best"]}{gap}.', now, [r['code']])
            elif settled and (was - pos >= 3):
                self._event(2 + (pos <= 5), 'improve', f'{who} improves to P{pos} with a {r["best"]}{gap}.', now, [r['code']])
            else:
                self._event(1, 'improve', f'{who} {"sets a" if first else "improves to P" + str(pos) + ","} {r["best"]}.', now, [r['code']])

    def _race(self, rows: dict, sess: dict, now):
        moves = []
        for num, r in rows.items():
            old = self.prev.get(num)
            if not old or r['position'] >= old['position'] or r.get('in_pit') or r.get('pit_out'):
                continue
            for o_num, o in self.prev.items():
                cur = rows.get(o_num)
                if not cur or o_num == num or cur.get('in_pit') or cur.get('pit_out') or cur.get('retired') or cur.get('stopped'):
                    continue
                if o['position'] < old['position'] and cur['position'] > r['position']:
                    moves.append((r['position'], r, cur))
        moves.sort(key=lambda m: m[0])
        for p, r, o in [m for m in moves if m[0] == 1]:   # a new leader always gets its own, top-priority call
            self._event(5, 'overtake', f'{surname(r)} takes the lead from {surname(o)}!', now, [r['code'], o['code']])
        moves = [m for m in moves if m[0] != 1]
        if len(moves) > 4:
            top = ', '.join(f'{surname(r)} up to P{p}' for p, r, _ in moves[:3])
            self._event(3, 'overtake', f'Positions changing everywhere: {top}.', now, [r['code'] for _, r, _ in moves[:3]])
        else:
            for p, r, o in moves:
                self._event(4 if p <= 3 else 3, 'overtake', f'{surname(r)} passes {surname(o)} for P{p}.', now, [r['code'], o['code']])
        for num, r in rows.items():
            old = self.prev.get(num) or {}
            if r['last'].get('overall') and r['last'].get('value') and r['last'].get('value') != (old.get('last') or {}).get('value'):
                again = self.fastest_lap_by == num   # the same driver lowering it again is barely news
                self.fastest_lap_by = num
                self._event(1 if again else 2, 'fastest_lap', f"Fastest lap of the race for {surname(r)}, a {r['last']['value']}.", now, [r['code']])
            if (r.get('retired') or r.get('stopped')) and not (old.get('retired') or old.get('stopped')):
                self._event(4, 'retired', f"{surname(r)} has stopped, running P{r['position']}.", now, [r['code']])
        if sess.get('lap') and sess.get('laps') and sess['lap'] == sess['laps'] and self.prev_session.get('lap') != sess['lap']:
            lead = min(rows.values(), key=lambda r: r['position'])
            self._event(4, 'session', f'Final lap! {surname(lead)} leads.', now, [lead['code']])

    def _practice(self, rows: dict, now):
        for num, r in rows.items():
            old = self.prev.get(num)
            if old and r['position'] == 1 and old['position'] != 1 and r.get('best') and r['best'] != old.get('best'):
                self._event(3, 'fastest', f"{surname(r)} goes to the top of the times, {r['best']}.", now, [r['code']])

    def _pits(self, rows: dict, sess: dict, now):
        racing = str(sess.get('type', '')).lower() in ('race', 'sprint')
        for num, r in rows.items():
            old = self.prev.get(num) or {}
            if r.get('knocked_out'):
                continue
            old_c = (old.get('tyre') or {}).get('compound')
            if racing and r.get('in_pit') and not old.get('in_pit'):
                on = f', coming off {old_c.lower()}s' if old_c in COMPOUNDS else ''
                self._event(3 if r['position'] <= 6 else 2, 'pit', f"{surname(r)} pits from P{r['position']}{on}.", now, [r['code']])
            new_c, known = (r.get('tyre') or {}).get('compound'), self.tyres.get(num)
            if new_c not in COMPOUNDS:
                continue  # 'UNKNOWN' / blank while a new stint is being created
            self.tyres[num] = new_c
            if racing and known and new_c != known:
                self._event(3 if r['position'] <= 6 else 2, 'tyres', f"{surname(r)} rejoins on {new_c.lower()}s, now P{r['position']}.", now, [r['code']])

    # ----------------------------------------------------------------- writer
    def _writer(self):
        while True:
            time.sleep(.3)
            try:
                batch = self._take()
                if batch:
                    self._say(batch, self._batch_gen)
            except Exception as exc:  # never let the thread die
                self.error = f'{type(exc).__name__}: {exc}'

    def _take(self) -> list[dict] | None:
        """Pick what to say next. Lines are paced to the voice: nothing new is written while the previous line is still
        being spoken, so no backlog can build up. When it's time, the freshest important events are folded into one line
        and everything older is dropped, so the commentator always talks about what is happening now."""
        with self.lock:
            if not self.pending or not self.enabled:
                return None
            now = self.clock or 0
            speed = max(1.0, self.speed)   # at 5x replay, 15 s of real time is 75 s of feed time
            fresh = lambda e: e['t'] is None or now - e['t'] <= (e.get('max_age') or (URGENT_AGE if e['prio'] >= URGENT else MAX_AGE)) * speed
            self.pending = [e for e in self.pending if fresh(e)]
            if not self.pending:
                return None
            top = max(e['prio'] for e in self.pending)
            wait = self.busy_until - LEAD
            if top >= URGENT and self.last_prio < URGENT:
                wait = 0   # a red flag / pole cuts in (the page interrupts the line being spoken)
            elif top <= 1:
                wait = self.busy_until + 6.0   # filler only in genuinely quiet moments
            elif top == 2:
                wait = self.busy_until + 2.0
            if time.time() < wait:
                return None
            self.pending.sort(key=lambda e: (-e['prio'], -(e['t'] or 0)))   # most important, then most recent
            self.busy = len(self.pending) >= 3
            batch = self.pending[:4]
            self.pending = []   # whatever didn't make it is folded in or already old news
            self.last_prio = batch[0]['prio']
            self.busy_until = time.time() + 8.0   # placeholder until the real length of the line is known
            self._batch_gen = self.gen
            return batch

    def _context(self) -> str:
        rows = sorted((self.prev or {}).values(), key=lambda r: r['position'])
        s = self.prev_session or {}
        head = f"{s.get('meeting', '')} {s.get('name', '')}".strip()
        if s.get('qualifying') and s.get('part'):
            head += f", Q{s['part']}"
        if s.get('lap'):
            head += f", lap {s['lap']}/{s.get('laps')}"
        if s.get('remaining') is not None:
            head += f", {int(s['remaining'] // 60)}:{int(s['remaining'] % 60):02d} remaining"
        order = '; '.join(f"P{r['position']} {surname(r)} ({r['team']}) {r.get('best') or ''} {r.get('gap') or ''}{' OUT' if r.get('knocked_out') else ''}{' PIT' if r.get('in_pit') else ''}".strip()
                          for r in rows[:22] if r['position'] < 99)
        return f'Session: {head}\nOrder: {order}'

    def _ask(self, eng: tuple[str, str], system: str, prompt: str, temperature: float) -> str | None:
        return (_ask_claude(_env_key(), system, prompt) if eng[0] == 'claude'
                else _ask_ollama(eng[1], system, prompt, temperature))

    def _say(self, batch: list[dict], gen: int | None = None):
        eng = self.engine()
        text, source = None, 'template'
        with self.lock:
            gen = self.gen if gen is None else gen
            rows = list((self.prev or {}).values())
        facts_for_check = [e['text'] for e in batch] + [e['transcript'] for e in batch if e.get('transcript')]
        if eng:
            facts = '\n'.join(f"- [{e['kind']}] {e['text']}" + (f"\n  Radio transcript (summarize ONLY what it clearly says, add nothing, do not quote it): {e['transcript']}" if e.get('transcript') else '') for e in batch)
            said = '\n'.join(f'- {s}' for s in self.recent) or '- (nothing yet)'
            intensity = 'HIGH' if batch[0]['prio'] >= 4 else 'NORMAL' if batch[0]['prio'] == 3 else 'LOW'
            pace = ('\nIt is BUSY: lots happening at once. One rapid-fire sentence, at most 16 words, lead with the biggest thing.'
                    if self.busy else '')
            prompt = short_numbers(f"{self._context()}\n\nWhat you said recently (don't repeat it):\n{said}\n\nJust happened, most important first:\n{facts}\n\n"
                                   f"Intensity: {intensity}{pace}\nYour line:")
            try:
                system = SYSTEM + '\n' + LANG.get(self.language, '')
                radio_heavy = any(e.get('transcript') for e in batch)   # facts matter more than flair: keep the model literal
                text = self._ask(eng, system, prompt, 0.2 if radio_heavy else 0.8)
                source, self.error = 'ai', ''
                # The model sometimes says things the data never said ("false starts", "in trouble at turn 5").
                # Check the line against this batch's facts; one more try, then the plain line built from the facts.
                wrong = unsupported(text, facts_for_check, rows, self.language) if text else []
                if wrong:
                    retry = prompt[:-len('Your line:')] + ('A previous attempt mentioned things that are not in the facts above ('
                                                           + ', '.join(wrong) + '). Use only the facts given.\nYour line:')
                    text = self._ask(eng, system, retry, 0.2)
                    if text and unsupported(text, facts_for_check, rows, self.language):
                        text, source = None, 'template'
                        if self.language != 'en':
                            # The plain line is English; in Albanian, translate just that line (nothing added),
                            # and only fall back to English if even the translation adds things.
                            translated = self._ask(eng, TRANSLATE.get(self.language, ''), template_line(batch), 0.0)
                            if translated and not unsupported(translated, facts_for_check, rows, self.language):
                                text, source = translated, 'template'
            except Exception as exc:
                text, source = None, 'template'
                self.error = f'AI commentary failed, using plain lines: {exc}'
        if text:
            text = _drop_repeats(text, self.recent)
            if not text:   # the model only repeated itself: nothing new worth saying
                with self.lock:
                    self.busy_until = time.time()
                return
        if not text:
            text = template_line(batch)
        text = short_numbers(text)
        lead = batch[0]
        radio = next((e['radio'] for e in batch if e.get('radio')), None)
        with self.lock:
            if gen != self.gen:   # the recording changed or was seeked while the AI was writing: not this timeline's line
                self.busy_until = time.time()
                return
            line_id = self.next_id
            self.next_id += 1
            voice, language = self.voice, self.language
        audio, seconds = None, len(text.split()) / 2.7   # browser voice: ~2.7 words per second
        if language == 'en' and self.speaker.available():
            try:
                audio, seconds = self.speaker.speak(text, lead['prio'], voice, line_id, self.run)
            except Exception as exc:
                self.error = f'Voice failed, using the browser voice: {type(exc).__name__}: {exc}'
        with self.lock:
            if gen != self.gen:   # same check after the voice was made (~1 s)
                self.busy_until = time.time()
                return
            self.busy_until = time.time() + seconds + 0.4
            self.recent.append(text)
            self.lines.append(dict(id=line_id, time=_hms(lead['t']), text=text, kind=lead['kind'], prio=lead['prio'], source=source,
                                   drivers=line_drivers(text, batch, rows), radio=radio, audio=audio,
                                   lag=round(((self.clock or 0) - (lead['t'] or self.clock or 0)) / max(1.0, self.speed), 1),
                                   facts=[e['text'] for e in batch]))

    # ------------------------------------------------------------------ radio
    def _radio_worker(self):
        while True:
            time.sleep(.5)
            with self.lock:
                cap = self._radio_q.popleft() if self._radio_q else None
                file = self.file
            if not cap or self._radio_stale(cap):
                continue   # an old clip is not news: skip it before spending time on the download
            try:
                self._radio(cap, file)
            except Exception as exc:
                self.radio_status = f'Radio failed: {type(exc).__name__}: {exc}'

    def radio_dir(self, file: str | None) -> Path:
        stem = Path(file or 'live').stem
        return self.root / 'outputs' / 'live' / 'radio' / re.sub(r'[^\w\-]+', '_', stem)

    def _radio_stale(self, cap: dict) -> bool:
        """True when the clip aired too long ago on the feed clock (or belongs to another timeline) to be called fresh.

        Clips bunch up, and at 5x or 30x replay the feed runs far ahead of the download + transcription, so each clip
        is judged by when it aired, scaled by the replay speed like every other event."""
        with self.lock:
            if cap.get('gen') is not None and cap['gen'] != self.gen:
                return True
            aired, now = cap.get('aired'), self.clock
            if aired is None or now is None:
                return False
            return now - aired > URGENT_AGE * max(1.0, self.speed)

    def _radio(self, cap: dict, file: str | None):
        if not cap.get('session_path'):
            return
        name = Path(str(cap['Path'])).name
        folder = self.radio_dir(file)
        folder.mkdir(parents=True, exist_ok=True)
        mp3, meta = folder / name, folder / (name + '.json')
        row = cap.get('row') or {}
        code = row.get('code') or str(cap.get('RacingNumber'))
        if meta.exists():
            transcript = json.loads(meta.read_text(encoding='utf-8')).get('text', '')
        else:
            if not mp3.exists():
                url = STATIC + urllib.parse.quote(str(cap['session_path']) + str(cap['Path']))
                self.radio_status = f'Downloading radio {code}…'
                for attempt in range(6):  # live clips can appear in the feed before the file is published
                    r = requests.get(url, timeout=20, headers={'User-Agent': 'RaceHype/1.0'})
                    if r.ok and r.content:
                        mp3.write_bytes(r.content)
                        break
                    if self._radio_stale(cap):
                        self.radio_status = f'Radio {code}: skipped, too old to mention.'
                        return
                    time.sleep(5 + attempt * 5)
                else:
                    self.radio_status = f'Radio {code}: clip not available ({r.status_code}).'
                    return
            self.radio_status = f'Transcribing radio {code}…'
            transcript = self._transcribe(mp3)
            meta.write_text(json.dumps(dict(text=transcript, driver=code, utc=cap.get('Utc')), ensure_ascii=False), encoding='utf-8')
        if self._radio_stale(cap):
            self.radio_status = f'Radio {code}: skipped, too old to mention.'
            return
        self.radio_status = f'Radio {code} ready.'
        with self.lock:
            if file != self.file:
                return
            # The event keeps the time the clip aired, so the freshness rules see its real age (not "now").
            # The commentator only ever summarizes the clip. The clip link and transcript ride along so the page can play/show
            # them in its "Real radio" mode (not stream safe: the audio belongs to F1); "Stream safe" mode ignores them.
            who = surname(row) if row else code
            # A clip without clear words is not worth a line of its own (it can still ride along with another event).
            self._event(3 if transcript else 1, 'radio', f'{who} has been on the radio to the team.', cap.get('aired') or self.clock, [code],
                        max_age=URGENT_AGE,
                        radio=dict(code=code, url=f'/api/live/radio/{folder.name}/{name}', transcript=transcript), transcript=transcript)

    def _transcribe(self, mp3: Path) -> str:
        if self._whisper is None and not self._whisper_failed:
            try:
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(WHISPER_MODEL, device='cpu', compute_type='int8')
            except Exception as exc:
                self._whisper_failed = f'{type(exc).__name__}: {exc}'
        if self._whisper is None:
            self.radio_status = f'Speech-to-text unavailable: {self._whisper_failed}'
            return ''
        segments, _ = self._whisper.transcribe(str(mp3), language='en', beam_size=3, vad_filter=True,
                                               initial_prompt='Formula 1 team radio between a driver and race engineer.')
        text = ' '.join(s.text.strip() for s in segments).strip()
        return '' if 'team radio between a driver' in text.lower() else text  # the prompt echoed back = no speech


# Things a line may only say when the facts say them too. Each pattern is matched against the line and against the
# facts, so wording can differ ("retires" vs "has stopped") as long as both fall in the same group.
INCIDENTS = {
    'a crash': r'\bcrash\w*|\bshunt\w*|\bin(?:to)? the (?:wall|barriers?)\b',
    'contact': r'\bcolli\w+|\bcontact\b|\btouch(?:es|ed|ing)?\b',
    'a spin': r'\bsp(?:in|ins|un|inning)\b',
    'a false start': r'\b(?:false|jump(?:ed)?) starts?\b',
    'a penalty': r'\bpenalt\w+',
    'an investigation': r'\binvestigat\w+|\bstewards?\b',
    'a puncture': r'\bpuncture\w*',
    'damage': r'\bdamaged?\b|\bbroken\b',
    'trouble': r'\btrouble\b|\bproblems?\b|\bissues?\b|\bstruggl\w+',
    'a retirement': r'\bretire\w*|\bdnf\b|\bout of the race\b|\bstopped\b',
    'fire or smoke': r'\bfire\b|\bsmok\w+',
    'a failure': r'\bfailures?\b|\bblown\b',
    'a lock-up': r'\block(?:s|ed|ing)?[- ]?up\b',
    'going off': r'\bgravel\b|\boff (?:the )?track\b|\b(?:runs?|ran|went|goes) wide\b',
    'a safety car': r'\bsafety car\b|\bvsc\b',
    'a red flag': r'\bred flags?\b',
    'a yellow flag': r'\byellows?\b',
    'rain': r'\brain\w*',
}
_INCIDENTS = {k: re.compile(v, re.I) for k, v in INCIDENTS.items()}
_TURN = re.compile(r'\b(?:turn|corner) ?(\d{1,2})\b', re.I)
_POS = re.compile(r'\bP(\d{1,2})\b')


def _named(text: str, rows: list[dict]) -> list[dict]:
    """Drivers whose surname appears in the text."""
    low = text.lower()
    return [r for r in rows if surname(r) and re.search(r'(?<![a-z])' + re.escape(surname(r).lower()) + r'(?![a-z])', low)]


def unsupported(text: str, facts: list[str], rows: list[dict], language: str = 'en') -> list[str]:
    """What an AI line claims that this batch's facts don't back up: other drivers, positions, incidents, corners.

    The race leader may always be named (the model is given the running order). Incident words are only checked in
    English; names and positions are checked in any language."""
    fact_text = ' '.join(facts)
    low_facts = fact_text.lower()
    problems = []
    named = _named(text, rows)
    for r in named:
        # Race control names cars by code ("CAR 1 (VER)"), so the code counts as the fact naming the driver.
        by_code = bool(r.get('code')) and re.search(r'\b' + re.escape(str(r['code'])) + r'\b', fact_text)
        if surname(r).lower() not in low_facts and not by_code and r.get('position') != 1:
            problems.append(surname(r))
    for m in _POS.finditer(text):
        n = int(m.group(1))
        if f'p{n}' not in re.findall(r'p\d{1,2}', low_facts) and not any(r.get('position') == n for r in named):
            problems.append(f'P{n}')
    if language == 'en':
        for label, pattern in _INCIDENTS.items():
            if pattern.search(text) and not pattern.search(fact_text):
                problems.append(label)
        turns = {m.group(1) for m in _TURN.finditer(fact_text)}
        problems += [f'turn {m.group(1)}' for m in _TURN.finditer(text) if m.group(1) not in turns]
    return list(dict.fromkeys(problems))


def line_drivers(text: str, batch: list[dict], rows: list[dict]) -> list[str]:
    """Driver tags for a line: the drivers its text actually names, else the lead event's drivers.

    A batch folds several events into one line and the writer often leaves some out; tagging every driver of the
    batch put names on the line that it never mentions."""
    named = sorted({r['code'] for r in _named(text, rows) if r.get('code')})
    return named or sorted(set(batch[0].get('drivers') or []))


STOP = set('the and with for from his her their its this that just now has have are was were into onto off out but while as at to of on in by a an is it be'.split())
CLAUSE = re.compile(r'(?<=[.!?])\s+|,\s*(?:and|while|as|with)?\s*|\s+(?:while|as)\s+')
SYNONYM = {'leads': 'lead', 'leading': 'lead', 'takes': 'take', 'took': 'take', 'passes': 'pass', 'passed': 'pass', 'overtakes': 'pass',
           'overtook': 'pass', 'pits': 'pit', 'pitted': 'pit', 'stops': 'pit', 'stopping': 'pit', 'begins': 'start', 'starts': 'start'}


LAPTIME = re.compile(r'\b(\d):(\d{2})\.(\d)\d{1,2}\b')
DECIMAL = re.compile(r'(?<![\d:.])(\d+)\.(\d)(\d)\d?\b')


def short_numbers(text: str) -> str:
    """Say numbers like a TV commentator: 1:31.785 → 1:31.7, 0.359 → 0.3, 12.220 → 12.2 (cut, not rounded).
    Gaps under a tenth keep two decimals (0.055 → 0.05), otherwise they would all read as 0.0."""
    text = LAPTIME.sub(r'\1:\2.\3', text)
    return DECIMAL.sub(lambda m: f'{m[1]}.{m[2]}{m[3]}' if m[1] == '0' and m[2] == '0' else f'{m[1]}.{m[2]}', text)


def _words(s: str) -> set[str]:
    return {SYNONYM.get(w, w) for w in re.findall(r"[a-z0-9']+", s.lower()) if w not in STOP and len(w) > 1}


def _drop_repeats(text: str, recent) -> str:
    """Remove parts of the line that mostly repeat something said in the last few lines (small models love to recap)."""
    said = [_words(c) for line in recent for c in CLAUSE.split(line) if c]
    keep = []
    for clause in (c.strip() for c in CLAUSE.split(text.strip()) if c and c.strip()):
        w = _words(clause)
        if w and not any(len(w & old) / len(w) >= .6 for old in said if old):
            keep.append(clause.rstrip('.!?,'))
    if not keep:
        return ''
    out = ', '.join(keep)
    end = '!' if text.rstrip().endswith('!') else '.'
    return out[:1].upper() + out[1:] + end


def _ask_ollama(model: str, system: str, prompt: str, temperature: float = 0.8) -> str | None:
    r = requests.post(OLLAMA_URL + '/api/chat', timeout=90, json=dict(
        model=model, stream=False, keep_alive='60m',
        options=dict(temperature=temperature, num_predict=90),
        messages=[dict(role='system', content=system), dict(role='user', content=prompt)]))
    r.raise_for_status()
    text = (r.json().get('message') or {}).get('content', '').strip().strip('"').strip()
    # Small local models sometimes ramble: keep the first two sentences.
    parts = re.split(r'(?<=[.!?])\s+', text)
    return ' '.join(parts[:2]).strip() or None


def _ask_claude(key: str, system: str, prompt: str) -> str:
    r = requests.post('https://api.anthropic.com/v1/messages', timeout=20,
                      headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                      json=dict(model=MODEL, max_tokens=150, system=system, messages=[dict(role='user', content=prompt)]))
    if not r.ok:
        try:
            detail = r.json().get('error', {}).get('message') or r.text
        except ValueError:
            detail = r.text
        raise RuntimeError(f'{r.status_code} {detail[:200]}')
    parts = [b.get('text', '') for b in r.json().get('content', []) if b.get('type') == 'text']
    return ' '.join(parts).strip().strip('"') or None
