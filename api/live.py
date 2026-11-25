"""Live timing endpoints: record F1's free stream, follow it live, or replay a recording."""
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.files import ROOT
from services import live_timing as lt
from services.commentary import Commentator
from services.scene3d import SceneManager

router = APIRouter()
FOLDERS = {'live': ROOT / 'outputs' / 'live', 'tmp': ROOT / 'tmp'}
NAME = re.compile(r'^[\w\-. ]{1,120}\.txt$')
_lock = Lock()
_feed: lt.Feed | None = None
_recorder = lt.Recorder(ROOT)
_commentator = Commentator(ROOT)
LABELS = FOLDERS['live'] / 'labels.json'   # the owner's names for recordings, and which ones are hidden
_labels_lock = Lock()


def _labels() -> dict:
    try:
        data = json.loads(LABELS.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _path(folder: str, name: str) -> Path:
    if folder not in FOLDERS or not NAME.match(name or ''):
        raise HTTPException(422, 'Choose a recording from the list.')
    path = FOLDERS[folder] / name
    if not path.is_file():
        raise HTTPException(404, 'That recording is no longer there.')
    return path


@router.get('/api/live/files')
def files(hidden: bool = False):
    rows = []
    labels = _labels()
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
            label = labels.get(f'{folder}/{p.name}') or {}
            if label.get('hidden') and not hidden:
                continue
            info = lt.recording_info(p)
            rows.append(dict(folder=folder, name=p.name, size=st.st_size, modified=st.st_mtime,
                             growing=time.time() - st.st_mtime < lt.GROWING_AFTER,
                             meeting=info.get('meeting') or '', session=info.get('session') or '', start=info.get('start') or '',
                             title=label.get('title') or '', hidden=bool(label.get('hidden'))))
    return sorted(rows, key=lambda r: r['modified'], reverse=True)


class Label(BaseModel):
    folder: str
    name: str
    title: str | None = None     # the owner's own name for the recording ('' removes it); the file is never renamed
    hidden: bool | None = None   # hidden recordings stay on disk, they just leave the list


@router.post('/api/live/files/label')
def label_file(body: Label):
    _path(body.folder, body.name)
    with _labels_lock:
        labels = _labels()
        entry = dict(labels.get(f'{body.folder}/{body.name}') or {})
        if body.title is not None:
            entry['title'] = re.sub(r'\s+', ' ', body.title).strip()[:80]
        if body.hidden is not None:
            entry['hidden'] = bool(body.hidden)
        entry = {k: v for k, v in entry.items() if v}
        if entry:
            labels[f'{body.folder}/{body.name}'] = entry
        else:
            labels.pop(f'{body.folder}/{body.name}', None)
        LABELS.parent.mkdir(parents=True, exist_ok=True)
        tmp = LABELS.with_suffix('.tmp')
        tmp.write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding='utf-8')
        tmp.replace(LABELS)
    return {'ok': True}


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
        # A name nobody has used, created exclusively: starting twice in one minute must not wipe the first file.
        path = lt.new_recording_path(FOLDERS['live'])
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
        try:
            with _feed.lock:
                _commentator.observe(_feed.state, snap, _feed.path.name)
        except Exception as exc:  # commentary must never break the timing screen
            _commentator.error = f'{type(exc).__name__}: {exc}'
    snap['recorder'] = rec
    snap['commentary'] = _commentator.status()
    return snap


class CommentarySettings(BaseModel):
    enabled: bool | None = None
    language: str | None = None
    voice: str | None = None


@router.post('/api/live/commentary')
def commentary_settings(body: CommentarySettings):
    _commentator.settings(body.enabled, body.language, body.voice)
    return _commentator.status()


@router.get('/api/live/radio/{folder}/{name}')
def radio_clip(folder: str, name: str):
    """A downloaded team radio clip, for the Live page's "Real radio" mode (not stream safe: the audio belongs to F1)."""
    if not re.match(r'^[\w\-]{1,120}$', folder) or not re.match(r'^[\w\-.]{1,120}\.mp3$', name):
        raise HTTPException(422, 'Bad radio clip name.')
    path = ROOT / 'outputs' / 'live' / 'radio' / folder / name
    if not path.is_file():
        raise HTTPException(404, 'Radio clip not downloaded.')
    return FileResponse(path, media_type='audio/mpeg')


@router.get('/api/live/voice/{name}')
def commentary_voice(name: str):
    """The commentator's spoken lines (Kokoro)."""
    if not re.match(r'^line_(?:[0-9a-f]{6,12}_)?\d{1,9}\.wav$', name):
        raise HTTPException(422, 'Bad voice file name.')
    path = ROOT / 'outputs' / 'live' / 'voice' / name
    if not path.is_file():
        raise HTTPException(404, 'Voice line not found.')
    return FileResponse(path, media_type='audio/wav')


@lru_cache(maxsize=8)
def _outline(year, event):
    # Saved to disk: OpenF1 locks its free data during live weekends, so an outline fetched once must survive restarts.
    return lt.track_outline(year, event, store=FOLDERS['live'] / 'circuits')


@router.get('/api/live/track')
def track(event: str, year: int | None = None):
    try:
        return _outline(year, event)
    except Exception as exc:
        raise HTTPException(404, str(exc))


# ------------------------------------------------------------------ 3D Broadcast
# One shared race scene for the open recording. Camera and driver choices live in each browser; these endpoints
# only read the engine's feed and never change its playback.
_scene = SceneManager(lambda year, event: _outline(year, event))


@router.get('/api/live/scene')
def scene(source: str = 'auto'):
    """Circuit, drivers and which positions this session has: recorded coordinates or estimated from timing."""
    feed = _feed
    if not feed:
        raise HTTPException(409, 'Open a recording first.')
    if source not in ('auto', 'estimated'):
        raise HTTPException(422, 'source must be auto or estimated.')
    return _scene.describe(feed, source)


@router.get('/api/live/scene/samples')
def scene_samples(t0: float, t1: float, source: str = 'auto', step: float = 0.25):
    """Timestamped positions for every car between t0 and t1 (recording clock, epoch seconds), plus the timing
    feed's classification over the same window."""
    feed = _feed
    if not feed:
        raise HTTPException(409, 'Open a recording first.')
    if not (t1 > t0) or t1 - t0 > 900:
        raise HTTPException(422, 'Ask for a window of up to 15 minutes.')
    return _scene.samples(feed, t0, t1, source, step)



@router.get('/api/live/radio-events')
def radio_events():
    """Team radio captures in the open recording up to the feed clock, timed by when each clip aired (its own Utc).

    Independent of the AI commentator: the fullscreen broadcast shows these whether commentary is on or off. A clip the
    commentator already downloaded/transcribed is reused (transcript + local URL); otherwise the F1 static URL is given
    (the page plays it only in "Real radio" mode; "Stream safe" shows a neutral notice or the transcript summary)."""
    import json as _json
    import re as _re
    import urllib.parse as _up
    from services.commentary import STATIC
    if not _feed:
        return dict(file=None, events=[])
    with _lock:
        snap = _feed.snapshot()          # advances the feed to its clock first (topics are applied on snapshot)
        with _feed.lock:
            st = _feed.state
            caps = (st.topics.get('TeamRadio') or {}).get('Captures') or []
            if isinstance(caps, dict):
                caps = list(caps.values())
            session_path = (st.topics.get('SessionInfo') or {}).get('Path') or ''
    codes = {str(r.get('number')): (r.get('code') or str(r.get('number')), r.get('color') or '') for r in snap.get('drivers') or []}
    folder = ROOT / 'outputs' / 'live' / 'radio' / _re.sub(r'[^\w\-]+', '_', Path(_feed.path.name).stem)
    out = []
    for cap in caps:
        if not isinstance(cap, dict) or not cap.get('Path') or not cap.get('Utc'):
            continue
        t = lt.parse_ts(cap['Utc'])
        if t is None:
            continue
        num = str(cap.get('RacingNumber') or '')
        name = Path(str(cap['Path'])).name
        transcript = ''
        meta = folder / (name + '.json')
        if meta.is_file():
            try:
                transcript = _json.loads(meta.read_text(encoding='utf-8')).get('text', '')
            except (OSError, ValueError):
                transcript = ''
        url = f'/api/live/radio/{folder.name}/{name}' if (folder / name).is_file() else (STATIC + _up.quote(str(session_path) + str(cap['Path'])) if session_path else None)
        code, color = codes.get(num, (num, ''))
        out.append(dict(id=f'{num}:{cap["Utc"]}', t=round(t, 3), num=num, code=code, color=color, url=url, transcript=transcript))
    out.sort(key=lambda e: e['t'])
    return dict(file=_feed.path.name, events=out)
