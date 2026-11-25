"""Bundled Lusail outline for the Live page (2D map + estimated 3D positions): frontend/src/hype/circuits/qatar-grand-prix.json.

Same geometry as the 3D venue (assets/3d/qatar/lusail_layout.json): OSM centreline in the F1 position frame
(tenths of a metre, unrotated -> `frame: "f1"`), measured elevation, OSM asphalt edges, OSM pit lane fractions.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
d = json.loads((ROOT / 'assets/3d/qatar/lusail_layout.json').read_text(encoding='utf-8'))
n = len(d['centre']['x'])
k = 2
out = dict(
    x=[round(v * 10, 1) for v in d['centre']['x'][::k]], y=[round(v * 10, 1) for v in d['centre']['y'][::k]],
    z=d['centre']['z'][::k], z_offset=d['z_offset'], frame='f1', rotation=0, length=d['length'],
    edges=dict(left=d['edges']['left'][::k], right=d['edges']['right'][::k]),
    pit=dict(entry=round(d['pit']['entry_station'] / n, 4), exit=round(d['pit']['exit_station'] / n, 4)),
    source='OpenStreetMap (ODbL) centreline and asphalt edges, aligned to OpenF1 positions; FIA length 5.419 km',
)
p = ROOT / 'frontend/src/hype/circuits/qatar-grand-prix.json'
p.write_text(json.dumps(out), encoding='utf-8')
print(p, len(out['x']), 'points', f'{p.stat().st_size / 1e3:.0f} KB', out['pit'])
