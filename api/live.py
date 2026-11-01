"""Live timing endpoints: record F1's free stream, follow it live, or replay a recording."""
import re
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.files import ROOT
from services import live_timing as lt

router = APIRouter()
FOLDERS = {'live': ROOT / 'outputs' / 'live', 'tmp': ROOT / 'tmp'}
NAME = re.compile(r'^[\w\-. ]{1,120}\.txt$')
_lock = Lock()
_feed: lt.Feed | None = None
_recorder = lt.Recorder(ROOT)


def _path(folder: str, name: str) -> Path:
    if folder not in FOLDERS or not NAME.match(name or ''):
        raise HTTPException(422, 'Choose a recording from the list.')
    path = FOLDERS[folder] / name
    if not path.is_file():
        raise HTTPException(404, 'That recording is no longer there.')
    return path


@router.get('/api/live/files')
def files():
    rows = []
    for folder, base in FOLDERS.items():
        if not base.is_dir():
            continue
        for p in base.glob('*.txt'):
            st = p.stat()
            if st.st_size == 0 and time.time() - st.st_mtime > 120:
                continue
            try:
                with p.open('r', encoding='utf-8', errors='replace') as f:
                    head = f.read(4000)
            except OSError:
                continue
            if "['" not in head and st.st_size > 0:
                continue  # not a live timing recording
            rows.append(dict(folder=folder, name=p.name, size=st.st_size, modified=st.st_mtime,
                             growing=time.time() - st.st_mtime < 15))
    return sorted(rows, key=lambda r: r['modified'], reverse=True)


class Open(BaseModel):
    folder: str
    name: str
    mode: str = 'follow'
    speed: float = 1.0


@router.post('/api/live/open')
def open_feed(body: Open):
    global _feed
    if body.mode not in ('follow', 'replay'):
        raise HTTPException(422, 'Mode must be follow or replay.')
    path = _path(body.folder, body.name)
    with _lock:
        _feed = lt.Feed(path, body.mode, max(.25, min(60.0, body.speed)))
    return {'ok': True}


@router.post('/api/live/close')
def close_feed():
    global _feed
    with _lock:
        _feed = None
    return {'ok': True}


@router.post('/api/live/record')
def record():
    global _feed
    if _recorder.running():
        path = _recorder.path
    else:
        path = FOLDERS['live'] / f"live_{datetime.now().strftime('%Y-%m-%d_%H%M')}.txt"
        _recorder.start(path)
    with _lock:
        _feed = lt.Feed(path, 'follow')
    return dict(_recorder.status(), folder='live', name=path.name)


@router.post('/api/live/stop-recording')
def stop_recording():
    _recorder.stop()
    return _recorder.status()


class Control(BaseModel):
    speed: float | None = None
    seek: float | None = None   # seconds from the start of the recording
    paused: bool | None = None


@router.post('/api/live/control')
def control(body: Control):
    if not _feed or _feed.mode != 'replay':
        raise HTTPException(409, 'Open a recording as a replay first.')
    if body.speed is not None:
        _feed.set_speed(max(.25, min(60.0, body.speed)))
    if body.seek is not None:
        start = _feed.first_time() or 0
        _feed.seek(start + max(0.0, body.seek))
    if body.paused is not None:
        _feed.pause(body.paused)
    return {'ok': True}


@router.get('/api/live/state')
def state():
    rec = _recorder.status()
    if not _feed:
        return dict(feed=None, recorder=rec)
    with _lock:
        snap = _feed.snapshot()
    snap['recorder'] = rec
    return snap


@lru_cache(maxsize=8)
def _outline(year, event):
    return lt.track_outline(year, event)


@router.get('/api/live/track')
def track(event: str, year: int | None = None):
    try:
        return _outline(year, event)
    except Exception as exc:
        raise HTTPException(404, str(exc))
