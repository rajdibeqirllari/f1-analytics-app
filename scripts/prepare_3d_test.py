"""Produce real lap timing/path inputs for the first Blender ghost-lap test."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.video_comparison import VideoSelection, build_comparison

comparison = build_comparison(VideoSelection(2022, 'French Grand Prix', 'Q', 'LEC', 'VER', qualifying_part='Q3'))
payload = {'year': comparison.year, 'event': comparison.event, 'session': comparison.session,
           'track': comparison.track.tolist(), 'warnings': comparison.warnings,
           'laps': [{'code': lap.code, 'name': lap.name, 'team': lap.team, 'color': lap.color,
                     'number': lap.number, 'lap_time': lap.lap_time,
                     'samples': lap.samples.to_dict(orient='list')} for lap in comparison.laps]}
output = ROOT / 'tmp/reference_review/paul_ricard_3d_input.json'
output.write_text(json.dumps(payload), encoding='utf8')
print('COMPARISON_READY', output, [(lap.code, lap.number, lap.lap_time) for lap in comparison.laps])
