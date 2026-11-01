"""Offline cached Mexico Q cases for exact Blender camera validation."""
import hashlib,json
from pathlib import Path
import services.openf1_comparison as provider
from services.video_comparison import VideoSelection
from services.procedural_circuit import build_circuit
from services.cornering import cornering_route
from services.cinematic_timeline import cinematic_timeline
from services.limit_story import limit_timeline

def cached(endpoint,params):
    key=hashlib.sha256(json.dumps([endpoint,params],sort_keys=True).encode()).hexdigest()
    return json.loads((provider.CACHE/(key+'.json')).read_text())
provider.historical=cached
destination=Path('tmp/mexico-camera');destination.mkdir(parents=True,exist_ok=True)
for a,b in (('LEC','VER'),('NOR','VER'),('NOR','LEC')):
    comparison=provider.comparison(VideoSelection(2025,'Mexico City Grand Prix','Q',a,b))
    mesh,route=build_circuit(comparison);route=cornering_route(route,mesh,max_offset=3.8)
    timeline=limit_timeline(cinematic_timeline(comparison,0,comparison.duration,60,3,'Dynamic cinematic',40,True))
    case=dict(mesh=mesh,route=route,timeline=timeline,
              laps=[dict(code=l.code,time=l.lap_time,samples=l.samples.to_dict(orient='list')) for l in comparison.laps])
    path=destination/f'{a}-{b}.json';path.write_text(json.dumps(case))
    print(str(path),len(route['progress']),len(timeline['source_times']),flush=True)
