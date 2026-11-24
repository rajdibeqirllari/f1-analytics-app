"""Opaque file IDs and an explicit output allowlist; no arbitrary path downloads."""
from hashlib import sha256
from pathlib import Path
import os
from threading import RLock

ROOT=Path(__file__).resolve().parents[1]
OUTPUT_ROOTS={name:(ROOT/name).resolve() for name in ('outputs','output','charts')}
TYPES={'.mp4':'Videos','.webm':'Overlays','.mov':'Overlays','.png':'Images','.jpg':'Images',
       '.csv':'Telemetry','.tsv':'Telemetry','.json':'Data','.mp3':'Audio','.wav':'Audio','.zip':'Sequences'}
_known={}
_lock=RLock()
# Internal working files, never listed or served as downloads (they stay on disk):
#  * caches (OpenF1 responses, radio archive cache), HUD frame folders, uploads
#  * outputs/live: recordings, the commentator's voice lines, and downloaded F1 team radio + transcripts.
#    F1's radio audio is served only by the Live page's opt-in "Real radio" route, never from the Library.
PRIVATE_DIRS={'cache','hud_frames','uploads','openf1_cache','live','replay_logs','work','frames','render_cache'}
# Blender/3D working folders (output/video_studio/3d_xxxx) hold intermediate frames and scene files.
PRIVATE_PREFIXES=('3d_',)


def private(path):
    resolved=Path(path).resolve()
    for base in OUTPUT_ROOTS.values():
        if resolved.is_relative_to(base):
            parts=resolved.relative_to(base).parts[:-1]
            return any(p.lower() in PRIVATE_DIRS or p.lower().startswith(PRIVATE_PREFIXES) for p in parts) or resolved.name.endswith('.audio.json')
    return True


def approved(path):
    resolved=Path(path).resolve()
    return (any(resolved.is_relative_to(base) for base in OUTPUT_ROOTS.values()) and resolved.suffix.lower() in TYPES
            and not private(resolved))


def servable(path):
    """Files the app may hand out by id. Downloaded team radio (outputs/radio/cache) is served for the Radio page's
    own player through /api/radio, not here."""
    return approved(path)


def descriptor(path):
    path=Path(path).resolve()
    if not approved(path) or not path.is_file():
        raise ValueError('This output is not available for download.')
    key=sha256(str(path).encode()).hexdigest()[:32]
    with _lock: _known[key]=path
    stat=path.stat()
    return dict(id=key,name=path.name,category=TYPES[path.suffix.lower()],size=stat.st_size,
                modified=stat.st_mtime,url=f'/api/files/{key}',relative=str(path.relative_to(ROOT)))


def library():
    rows=[]
    for base in OUTPUT_ROOTS.values():
        if not base.exists(): continue
        for directory,dirs,files in os.walk(base,followlinks=False):
            # Prune before traversal: a HUD sequence may contain hundreds of thousands of frames.
            dirs[:]=[d for d in dirs if d.lower() not in PRIVATE_DIRS and not d.lower().startswith(PRIVATE_PREFIXES) and not Path(directory,d).is_symlink()]
            for name in files:
                path=Path(directory,name)
                if path.suffix.lower() not in TYPES or '.partial.' in name: continue
                if approved(path): rows.append(descriptor(path))
    return sorted(rows,key=lambda row:row['modified'],reverse=True)


def resolve(key):
    with _lock: path=_known.get(key)
    if path and path.is_file() and approved(path): return path
    for row in library():
        if row['id']==key:
            path=ROOT/row['relative']
            if approved(path): return path
    raise FileNotFoundError('Output not found.')
