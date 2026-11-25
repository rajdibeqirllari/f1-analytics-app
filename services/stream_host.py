"""Independent OBS host. Only an open overlay drives polling and speech generation."""
import logging
import os
import re
import threading
import time
from collections import deque
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from services.commentary import OLLAMA_MODEL, Speaker, _ask_ollama, surname, unsupported

app = FastAPI(docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:8000', 'http://localhost:8000'])
SOURCE = os.environ.get('RACEHYPE_HOST_TIMING_URL', 'http://127.0.0.1:8000/api/live/state')
PERSONA = """You're Emma, watching a race with a friend. Speak conversational English.
Pick one thing in this timing change you personally care about. Let curiosity, relief or delight
come through in the phrasing. Sometimes a little question is enough. Use contractions.
Talk directly to one listener. Use the driver's surname when it makes sense. Say what
you want to see next or what caught your attention. Never name your emotion aloud
or use abstract praise. Leave an ordinary midfield position change alone.
Give a short spoken thought, under 22 words. Ground every claim in the supplied observation.
You only have timing. Never invent a passing side, cause, driver intention or visible action.
Avoid announcing the timing sheet, canned hype, stage directions and repeated openings.
If there's nothing interesting to add, reply SKIP."""


def moment(previous, current):
    flag = current.get('flag') or {}
    if flag != previous.get('flag') and flag.get('state') in ('red', 'sc', 'vsc', 'green'):
        return flag['text'], 5
    if current.get('session', {}).get('type', '').lower() not in ('race', 'sprint'):
        return None
    old = {r['number']: r for r in previous.get('drivers', [])}
    rows = sorted(current.get('drivers', []), key=lambda r: r['position'])
    for r in rows[:10]:
        before = old.get(r['number'])
        if not before:
            continue
        if r['position'] <= 4 and r['position'] < before['position']:
            return f"{surname(r)} has moved from P{before['position']} to P{r['position']} on timing.", 5 if r['position'] == 1 else 4
        if r.get('in_pit') and not before.get('in_pit'):
            return f"{surname(r)} is in the pits, having been P{before['position']}.", 3
    for ahead, r in zip(rows, rows[1:8]):
        before = old.get(r['number'], {})
        if before.get('position') != r['position'] or old.get(ahead['number'], {}).get('position') != ahead['position']:
            continue
        try:
            gap, prior = float(r['interval']), float(before['interval'])
        except (ValueError, TypeError, KeyError):
            continue
        if 0 < gap <= .8 < prior and prior > gap + .15 and not any(x.get('in_pit') for x in (ahead, r)):
            return f"{surname(r)} closed from {prior:.1f} to {gap:.1f} seconds behind {surname(ahead)}.", 3
    return None


class Host:
    def __init__(self):
        self.lock = threading.Lock()
        self.previous = {}
        self.key = None
        self.recent = deque(maxlen=4)
        self.line = None
        self.run = uuid4().hex[:10]
        self.serial = 0
        self.busy = False
        self.next_time = 0
        self.error = ''
        self.speaker = Speaker(Path(__file__).resolve().parents[1])
        self.speaker.out = self.speaker.out.parent / 'host-voice'

    def poll(self):
        # Serialize sampling too: two OBS sources must see the same timeline.
        with self.lock:
            response = requests.get(SOURCE, timeout=4)
            response.raise_for_status()
            snap = response.json()
            feed = snap.get('feed') or {}
            key = (feed.get('file'), (snap.get('commentary') or {}).get('run'), feed.get('paused'))
            if key != self.key:
                self.key, self.run = key, uuid4().hex[:10]
                self.recent.clear()
                self.line, self.next_time, self.error = None, 0, ''
            elif feed and not feed.get('paused') and not self.busy and time.monotonic() >= self.next_time:
                event = moment(self.previous, snap)
                if event:
                    self.busy = True
                    self.serial += 1
                    threading.Thread(target=self.react, args=(event, snap, self.run, self.serial, list(self.recent)), daemon=True).start()
            self.previous = snap
            return dict(feed=feed or None, host=dict(run=self.run, lines=[self.line] if self.line else [], error=self.error))

    def react(self, event, snap, run, serial, memory):
        fact, priority = event
        try:
            recent = '\n'.join(memory)
            text = _ask_ollama(OLLAMA_MODEL, PERSONA, f"Observation: {fact}\nPreviously said: {recent}\nSpeak naturally in one breath.", .85)
            if (not text or 'SKIP' in text.upper() or len(text.split()) > 30 or text in memory
                    or unsupported(text, [fact], snap.get('drivers', []), 'en')):
                return
            path, duration = self.speaker.speak(text, 3 if priority >= 4 else 2, 'bf_emma', serial, run)
            with self.lock:
                if run == self.run:
                    self.line = dict(id=serial, text=text, audio='/voice/'+path.split('/')[-1],
                                     event_clock=snap['feed']['clock'], prio=priority)
                    self.recent.append(text)
                    self.next_time = time.monotonic() + duration + 7
                    self.error = ''
        except Exception:
            logging.exception('Host reaction failed')
            with self.lock:
                if run == self.run:
                    self.error = 'Host voice or local language model unavailable'
        finally:
            with self.lock:
                self.busy = False


host = Host()


@app.get('/state')
def state():
    try:
        return host.poll()
    except requests.RequestException:
        raise HTTPException(503, 'Timing unavailable')


@app.get('/voice/{name}')
def voice(name: str):
    path = host.speaker.out / name
    if not re.fullmatch(r'line_[0-9a-f]{10}_\d+\.wav', name) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='audio/wav')
