"""Your footage + real telemetry: upload an onboard clip, sync it from the engine sound, burn the HUD in."""
import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.files import ROOT, descriptor
from api import engines
from services import footage_sync as fs

router = APIRouter()
UPLOADS = ROOT / 'outputs' / 'uploads' / 'footage'   # 'uploads' folders stay out of My Downloads
EXPORTS = ROOT / 'outputs' / 'footage'
MAX_BYTES = 8 * 1024 ** 3


def _clip(key: str):
    if not fs.ID_RE.match(key or ''):
        raise ValueError('Upload your clip first.')
    meta = UPLOADS / f'{key}.json'
    if not meta.is_file():
        raise ValueError('That clip is no longer available. Upload it again.')
    info = json.loads(meta.read_text(encoding='utf-8'))
    path = UPLOADS / info['file']
    if not path.is_file():
        raise ValueError('That clip is no longer available. Upload it again.')
    return path, info


@router.post('/api/footage')
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or '').suffix.lower()
    if ext not in fs.VIDEO_EXT:
        raise HTTPException(422, 'Choose an MP4, MOV, MKV, M4V or WebM video.')
    UPLOADS.mkdir(parents=True, exist_ok=True)
    key = uuid4().hex
    path = UPLOADS / f'{key}{ext}'
    size = 0
    try:
        with path.open('wb') as out:
            while chunk := await file.read(8 * 1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, 'Clips must be smaller than 8 GB.')
                out.write(chunk)
        info = fs.probe(path)
        fs.poster(path, UPLOADS / f'{key}.jpg', at=min(1.0, info['duration'] / 2))
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc))
    info.update(id=key, file=path.name, name=Path(file.filename or path.name).name, size=size)
    (UPLOADS / f'{key}.json').write_text(json.dumps(info), encoding='utf-8')
    return dict(info, poster=f'/api/footage/{key}/poster', video=f'/api/footage/{key}/video')


@router.get('/api/footage/{key}/poster')
def poster(key: str):
    try:
        _clip(key)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return FileResponse(UPLOADS / f'{key}.jpg', media_type='image/jpeg')


@router.get('/api/footage/{key}/video')
def video(key: str):
    try:
        path, _ = _clip(key)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return FileResponse(path)


def _telemetry(s, options):
    source = options.get('source', 'Auto')
    if source not in ('Auto', 'FastF1', 'OpenF1'):
        raise ValueError('Syncing to your clip needs session telemetry (Auto, FastF1 or OpenF1), not an uploaded CSV.')
    lap, full, meta = engines.load_telemetry(s, source)
    return fs.build_telemetry(lap, full), meta


def sync(s, options, progress):
    path, info = _clip(options.get('footage_id'))
    if not info.get('has_audio'):
        raise ValueError('This clip has no sound, so it can only be lined up by hand.')
    tel, meta = _telemetry(s, options)
    progress(.3, 'Listening to the engine')
    track = fs.pitch_track(fs.extract_audio(path))
    progress(.8, 'Matching gear changes to the data')
    result = fs.estimate_offset(track, tel, info['duration'])
    result['telemetry'] = fs.telemetry_for_page(tel, result['lap_start_in_clip'], info['duration'])
    result.update(source=meta['source'], lap_number=meta.get('lap_number'), fallback=meta.get('fallback'))
    return engines.clean(result)


def render(s, options, progress):
    path, info = _clip(options.get('footage_id'))
    lap_in_clip = float(options.get('lap_start_in_clip'))
    if not -3600 < lap_in_clip < info['duration'] + 3600:
        raise ValueError('The lap start is outside this clip.')
    hud_width = int(options.get('hud_width', 460))
    if not 100 <= hud_width <= 1500:
        raise ValueError('HUD width must be 100–1500 pixels.')
    position = options.get('position', 'Bottom left')
    if position not in ('Bottom left', 'Bottom center', 'Bottom right', 'Custom'):
        raise ValueError('Choose a supported HUD position.')
    tel, meta = _telemetry(s, options)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    out = EXPORTS / f"{s.year}_{s.driver}_lap{meta.get('lap_number') or ''}_onboard_{uuid4().hex[:8]}.mp4"
    progress(.1, 'Starting the encoder')
    result = fs.render_burn_in(path, info, tel, lap_in_clip, assets_dir=ROOT / 'assets' / 'hud', out_path=out,
                               hud_width=hud_width, position=position, x=int(options.get('x', 0)), y=int(options.get('y', 0)),
                               hud_year=s.year, progress=progress)
    return engines.clean(dict(file=descriptor(out), source=meta['source'], lap_number=meta.get('lap_number'), **result))
