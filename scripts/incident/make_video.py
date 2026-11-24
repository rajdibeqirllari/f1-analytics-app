"""One command: data -> Blender render -> overlays -> MP4.

From C:\\f1hud_app:
  .\\.venv\\Scripts\\python.exe scripts\\incident\\make_video.py            # full quality, 1080x1920 30 fps
  .\\.venv\\Scripts\\python.exe scripts\\incident\\make_video.py --preview  # half size, 15 fps, fast check
  ... --skip-render       re-do only the overlays/captions (after editing texts in the JSON)
  ... --no-sound          skip the generated soundtrack (adds <name>.sound.mp4 otherwise)
  ... --open-blend        also save the Blender scene to outputs\\incident\\work\\mexico2026_t4.blend
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
HERE = Path(__file__).absolute().parent
CONFIG = HERE / 'mexico2026_t4.json'
BLENDER = ROOT / 'tools' / 'blender' / 'blender-4.5.9-windows-x64' / 'blender.exe'
args = sys.argv[1:]
preview = ['--preview'] if '--preview' in args else []


def run(cmd, label):
    print(f'\n== {label}', flush=True)
    start = time.time()
    proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    total = None
    for line in proc.stdout:
        if line.startswith('FRAMES'):
            total = int(line.split()[1])
            print(line.strip(), flush=True)
        elif line.startswith('RENDERED'):
            done = int(line.split()[1])
            el = time.time() - start
            if total:
                eta = el / max(done, 1) * (total - done)
                print(f'\r  frame {done}/{total}  ~{eta / 60:.0f} min left   ', end='', flush=True)
        elif any(k in line for k in ('Error', 'Traceback', 'error:', 'Saved', 'overlay', 'Lap line', '  ')):
            print(line.rstrip(), flush=True)
    if proc.wait():
        sys.exit(f'{label} failed (exit {proc.returncode}). Scroll up for the error.')
    print(f'  done in {(time.time() - start) / 60:.1f} min', flush=True)


run([sys.executable, HERE / 'prepare.py', CONFIG], 'Preparing data')
if '--skip-render' not in args:
    if not BLENDER.exists():
        sys.exit(f'Blender not found at {BLENDER}')
    extra = ['--save-blend'] if '--open-blend' in args else []
    run([BLENDER, '--background', '--factory-startup', '--python-exit-code', '1', '--python', HERE / 'build_scene.py', '--',
         '--config', CONFIG, *preview, *extra], 'Rendering 3D frames in Blender')
run([sys.executable, HERE / 'overlay.py', CONFIG, *preview], 'Overlays and MP4')
if '--no-sound' not in args:
    run([sys.executable, HERE / 'sound.py', CONFIG, *preview], 'Soundtrack and sound effects')
