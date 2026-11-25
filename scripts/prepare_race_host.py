"""Package the local Open-LLM-VTuber avatar for Race Hype's OBS source."""
from pathlib import Path
from shutil import copy2, copytree

root = Path(__file__).resolve().parents[1]
out = root / 'frontend/public/design/race-host'
upstream = root / 'tools/Open-LLM-VTuber'
modules = root / 'tools/racehost-renderer/node_modules'
out.mkdir(parents=True, exist_ok=True)
for name, source in {
    'pixi.js': modules / 'pixi.js/dist/browser/pixi.min.js',
    'display.js': modules / 'pixi-live2d-display/dist/cubism4.min.js',
    'cubism.js': upstream / 'frontend/libs/live2dcubismcore.min.js',
    'LICENSE-Live2D.md': upstream / 'LICENSE-Live2D.md',
    'index.html': root / 'components/race_host/index.html',
    'host.js': root / 'components/race_host/host.js',
}.items():
    copy2(source, out / name)
copytree(upstream / 'live2d-models/mao_pro/runtime', out / 'model', dirs_exist_ok=True)
