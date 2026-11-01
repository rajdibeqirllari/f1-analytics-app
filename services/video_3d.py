"""Cancellable Blender rendering for licensed and telemetry-built 3D circuits.

Source geometry stays server-side. Only composed MP4s are exposed to users.
"""
from __future__ import annotations

from functools import lru_cache
import json
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from services.video_comparison import Comparison
from services.circuits_3d import circuit_for,presentation,resolve_environment
from services.video_timeline import validate_playback_speed, frame_count


def render_cache_key(config):
    """Include all render inputs, versions and private geometry revisions."""
    from services.car_style import RENDER_VERSION
    from services.video_branding import BRANDING_VERSION,LOGO
    from services.circuit_scenery import VERSION as SCENERY_VERSION
    value={k:v for k,v in config.items() if k!='work_dir'}
    if config.get('camera') in ('Cinematic Ghost Chase','Classic Broadcast','The Limit'):
        value['cinematic_projection']='pitched-actual-mesh-bounds-v2'
    value['versions']=[RENDER_VERSION,BRANDING_VERSION,SCENERY_VERSION]
    if LOGO.is_file():value['logo_revision']=LOGO.stat().st_mtime_ns
    revisions=[]
    for key in ('car','car_metadata','circuit','asset_environment','source_glb','source_reference'):
        path=Path(config.get(key,''))
        if path.is_file():
            stat=path.stat();revisions.append((key,stat.st_size,stat.st_mtime_ns))
    value['geometry_revisions']=revisions
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets/3d"
CAR = ASSETS / "cars/qvist/car.blend"
CAR_METADATA = ASSETS / "cars/qvist/metadata.json"
CIRCUIT = ASSETS / "circuits/paul_ricard/source/PaulRicardnosides.blend"
CIRCUIT_MESH = ASSETS / "circuits/paul_ricard/mesh.npz"
PROFILE = ASSETS / "paul_ricard_alignment.json"


def blender_executable() -> Path | None:
    configured = os.environ.get("RACE_HYPE_BLENDER")
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None
    found = shutil.which("blender")
    if found:
        return Path(found)
    return next((p for p in sorted((ROOT / "tools/blender").glob("blender-*/blender.exe"), reverse=True)
                 if p.is_file()), None)


def availability(year: int, event: str, environment='Auto') -> tuple[bool, str]:
    circuit=circuit_for(year,event)
    if circuit is None:
        from services.circuits_3d import CIRCUITS
        names=', '.join(c.name for c in CIRCUITS if c.backend=='telemetry')
        return False, "Choose a supported calendar event from 2018 onward. A complete session telemetry layout is required for 3D."
    try:source=resolve_environment(year,event,environment)
    except ValueError as exc:return False,str(exc)
    if not blender_executable():
        return False, "Blender is missing. Set RACE_HYPE_BLENDER to a Blender executable on the render server."
    if not shutil.which("ffmpeg"):
        return False, "FFmpeg is required for 3D MP4 export."
    required=(CAR,CAR_METADATA,CIRCUIT,CIRCUIT_MESH,PROFILE) if source=='Original model' and circuit.backend=='asset' else (CAR,CAR_METADATA)
    if not all(p.is_file() for p in required):
        return False, "The private car/circuit asset bundle is missing from this render server."
    if event=='Singapore Grand Prix' and source=='Original model':
        from services.singapore_asset import available,layout_for
        if not available(year,event):
            return False,'The original Singapore GLB / read-only asphalt index is missing or stale. Run scripts/index_singapore_sources.py with Blender. No replacement track will be generated.'
        return True,f"{layout_for(year)['source'].name} · original GLB geometry/materials · generic cars"
    return True, f"{circuit.name} · {presentation(year,event,source)['description']} · generic cars · server-side Blender"


def render_range(comparison: Comparison, start: float, end: float | None, fps: int, playback_speed=1):
    playback_speed=validate_playback_speed(playback_speed)
    if fps not in (24, 30, 60):
        raise ValueError("3D supports 24, 30 or 60 fps.")
    if not math.isfinite(float(start)) or (end is not None and not math.isfinite(float(end))):
        raise ValueError("Clip times must be finite.")
    start = max(0., float(start))
    full = end is None
    end = comparison.duration if full else min(comparison.duration, float(end))
    if end <= start:
        raise ValueError("Clip start must be before the end of the selected laps.")
    # Full laps include the exact finish and a two-second result hold.
    frames = frame_count(start,end,fps,playback_speed,hold=full)
    return start, end, frames, full


@lru_cache(maxsize=1)
def _road_points():
    with np.load(CIRCUIT_MESH) as mesh:
        triangles = mesh["Plane"][mesh["Plane_triangles"][mesh["Plane_materials"] == 0]]
    return np.concatenate([triangles.mean(axis=1), triangles[:,0], triangles[:,1], triangles[:,2]])[:,:2]


def fit_path(comparison: Comparison):
    from scipy.optimize import minimize
    from scipy.spatial import cKDTree
    profile = json.loads(PROFILE.read_text(encoding="utf8"))
    road = _road_points()
    tree = cKDTree(road)
    original = comparison.track[:,1:3]
    origin = original.mean(axis=0)
    xy = original-origin
    road_origin = np.array(profile["road_origin"])
    previous = np.array(profile["parameters"], dtype=float)

    def rotation(angle):
        return np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])

    # Preserve calibrated world orientation when the reference lap/mean changes.
    previous[2:] += (origin-np.array(profile["telemetry_origin"])) @ rotation(previous[0]).T * math.exp(previous[1])

    def mapped(params):
        return xy @ rotation(params[0]).T * math.exp(params[1]) + road_origin + params[2:]

    def loss(params):
        return float(np.mean(tree.query(mapped(params))[0]**2))

    bounds = [(previous[0]-.12, previous[0]+.12), (previous[1]-.035, previous[1]+.035),
              (previous[2]-60, previous[2]+60), (previous[3]-60, previous[3]+60)]
    result = minimize(loss, previous, method="Powell", bounds=bounds,
                      options={"maxiter":120, "xtol":1e-6, "ftol":1e-5})
    params = result.x if loss(result.x) < loss(previous) else previous
    points = mapped(params)
    distances = tree.query(points)[0]/math.exp(params[1])
    rms = float(np.sqrt(np.mean(distances**2)))
    if rms > 1.6 or float(np.percentile(distances,95)) > 2.8 or distances.max() > 6:
        raise ValueError("This lap does not align safely with the available 3D circuit. Choose a different lap or use 2D.")
    return {"parameters":params.tolist(), "road_origin":road_origin.tolist(),
            "mapped_xy":points.tolist(), "rms_metres":rms}


def comparison_payload(comparison):
    return {"year":comparison.year, "event":comparison.event, "session":comparison.session,
            "track":comparison.track.tolist(), "warnings":comparison.warnings,
            "laps":[{"code":lap.code, "name":lap.name, "team":lap.team, "color":lap.color,
                     "number":lap.number, "lap_time":lap.lap_time,
                     "samples":lap.samples.to_dict(orient="list")} for lap in comparison.laps]}


@lru_cache(maxsize=1)
def _road_guide(scale):
    from services.driving_path import RoadGuide
    with np.load(CIRCUIT_MESH) as mesh:
        vertices=mesh['Plane']/scale
        triangles=mesh['Plane_triangles'][mesh['Plane_materials']==0]
    return RoadGuide(vertices,triangles)


def prepare_driving_path(alignment):
    scale=math.exp(alignment['parameters'][1])
    route=_road_guide(scale).route(np.array(alignment['mapped_xy'])/scale)
    offset=np.array(alignment['road_origin'])+np.array(alignment['parameters'][2:])
    route['xy']=(np.array(route['xy'])-offset/scale).tolist()
    return route


def run_blender(command, *, cancelled, progress_callback, frames, log_path, timeout=7200):
    """Drain stdout to a file, poll progress, and terminate the owned process on cancel."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    started = time.monotonic()
    process = None
    with log_path.open("wb") as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            with log_path.open("r", encoding="utf8", errors="replace") as reader:
                seen = 0
                shadow_overflows=0
                first_frame_at=None;first_seen=0
                while process.poll() is None:
                    if cancelled and cancelled():
                        raise InterruptedError("3D generation cancelled.")
                    if time.monotonic()-started > timeout:
                        raise TimeoutError("3D rendering exceeded two hours. Try a shorter clip or lower resolution.")
                    for line in reader.readlines():
                        if 'TRAIL_ALIGNMENT_ERROR' in line:
                            raise RuntimeError('Surface trajectory update failed; no partial video was published. '+line.strip())
                        if 'Shadow buffer full' in line:
                            shadow_overflows+=1
                            if shadow_overflows>=8:
                                raise RuntimeError('The scene exceeded the shadow-memory budget. Rendering was stopped to avoid missing shadows and flicker; no partial video was published.')
                        match = re.search(r"Saved:.*frame_(\d+)\.png", line)
                        if match:
                            seen = max(seen, int(match[1]))
                    if progress_callback:
                        if seen and first_frame_at is None:
                            first_frame_at=time.monotonic();first_seen=seen
                        eta=''
                        if first_frame_at is not None and seen-first_seen>=4:
                            remaining=(frames-seen)*(time.monotonic()-first_frame_at)/(seen-first_seen)
                            estimate=f'{max(1,math.ceil(remaining))} s' if remaining<90 else f'{math.ceil(remaining/60)} min'
                            eta=f' · about {estimate} remaining' if seen<frames else ' · preparing encode'
                        progress_callback(.08 + .77*min(seen/frames,1),
                                          f"Blender · frame {seen:,} / {frames:,}"+eta if seen else "Preparing the 3D scene and shaders")
                    time.sleep(.2)
            if cancelled and cancelled():
                raise InterruptedError("3D generation cancelled.")
            if process.returncode:
                tail = log_path.read_text(encoding="utf8", errors="replace")[-1800:]
                raise RuntimeError("Blender could not render this selection: " + tail)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=20)


def render_3d_mp4(comparison: Comparison, destination: Path, *, size=(540,960), fps=24,
                  camera="Follow cars", start=0., end=None, progress_callback=None, cancelled=None,
                  environment="Auto",quality="Fast",playback_speed=1,pacing='Constant',target_duration=35,camera_options=None,alignment_debug=False,music_credit=None):
    from services.cinematic_timeline import cinematic_timeline,validate_options
    camera_options=validate_options(pacing,target_duration,camera_options)
    playback_speed=validate_playback_speed(playback_speed)
    ready, reason = availability(comparison.year, comparison.event,environment=environment)
    if not ready:
        raise ValueError(reason)
    if camera not in ("Follow cars", "Full circuit", "Night chase A", "Night chase B", "Onboard ghost A", "Onboard ghost B", "Social director",'Cinematic Ghost Chase','Classic Broadcast','The Limit'):
        raise ValueError(f"Unsupported 3D camera: {camera!r}. Select the chase driver again.")
    if quality not in ('Fast','Balanced','High'):
        raise ValueError('Choose Fast, Balanced or High render quality.')
    if size not in ((540,960),(960,540),(720,1280),(1280,720),(1080,1920),(1920,1080)):
        raise ValueError("Unsupported 3D video dimensions.")
    if cancelled and cancelled():
        raise InterruptedError()
    start, end, frames, full = render_range(comparison,start,end,fps,playback_speed)
    timeline=cinematic_timeline(comparison,start,end,fps,playback_speed,pacing,target_duration,full)
    if camera=='The Limit':
        from services.limit_story import limit_timeline
        timeline=limit_timeline(timeline)
    frames=len(timeline['source_times'])
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    circuit=circuit_for(comparison.year,comparison.event)
    # availability already rejects unknown selections; the fallback keeps
    # isolated tests that mock availability independent of the catalogue.
    # Unknown-circuit fallback exists only for isolated tests mocking readiness.
    source=resolve_environment(comparison.year,comparison.event,environment) if circuit else environment
    generated=circuit is not None and source=='Telemetry-built'
    onboard=camera in ('Onboard ghost A','Onboard ghost B')
    cinematic=camera in ('Cinematic Ghost Chase','Classic Broadcast','The Limit')
    director=camera=='Social director' or cinematic
    night=camera in ('Night chase A','Night chase B') or onboard or director
    from services.singapore_asset import available as singapore_available,model_route,layout_for
    if environment not in ('Auto','Original model','Telemetry-built'):
        raise ValueError('Unsupported circuit environment.')
    singapore=comparison.event=='Singapore Grand Prix' and source=='Original model'
    if singapore and not singapore_available(comparison.year,comparison.event):
        raise ValueError('The original Singapore GLB index is unavailable. No telemetry-built track fallback is allowed.')
    if night and not generated and not singapore:
        raise ValueError('Night Chase supports Telemetry-built tracks and the original Singapore GLB. Choose Telemetry-built or switch to Cinematic for this model.')
    if singapore:
        if progress_callback:progress_callback(.02,'Aligning car motion to original GLB asphalt · track unchanged')
        driving_path=model_route(comparison,overlap=night)
        alignment={'parameters':[0.,0.,0.,0.],'road_origin':[0.,0.],
                   'mapped_xy':driving_path['xy'],'rms_metres':0.}
    elif generated:
        if progress_callback: progress_callback(.02,'Building a telemetry-derived 3D circuit')
        from services.procedural_circuit import build_circuit
        road_mesh,driving_path=build_circuit(comparison)
        alignment={'parameters':[0.,0.,0.,0.],'road_origin':[0.,0.],
                   'mapped_xy':driving_path['xy'],'rms_metres':0.}
    else:
        if progress_callback: progress_callback(.02,"Checking circuit / telemetry alignment")
        alignment = fit_path(comparison)
        if progress_callback: progress_callback(.04,'Building a smooth asphalt-constrained route')
        driving_path=prepare_driving_path(alignment)
    if night:
        from services.cornering import cornering_route
        if not singapore:
            driving_path=cornering_route(driving_path,road_mesh,max_offset=3.8) if onboard or director else cornering_route(driving_path,road_mesh)
        driving_path=dict(driving_path,half_separation=[0.]*len(driving_path['progress']),
                          separation_range=[0.,0.],night_chase={'focus':int(camera in ('Night chase B','Onboard ghost B'))})
        from services.circuit_lighting import race_lighting
        driving_path['race_lighting']=race_lighting(comparison.year,comparison.event)
    if cancelled and cancelled(): raise InterruptedError()
    driving_path=dict(driving_path,track_source=source,playback_speed=playback_speed)
    if music_credit:driving_path['music_credit']=music_credit
    if onboard:driving_path['onboard_ghost']=True
    if director:driving_path['social_director']=True
    if cinematic:driving_path['cinematic_ghost']=True
    if camera=='The Limit':driving_path['the_limit']=True
    if alignment_debug:driving_path['alignment_debug']=True
    driving_path['timeline']=timeline
    driving_path['output_fps']=fps
    # Every job is isolated; cleanup removes only this owned temp directory.
    with tempfile.TemporaryDirectory(prefix="3d_", dir=destination.parent) as folder:
        work = Path(folder)
        config = {"comparison":comparison_payload(comparison), "alignment":alignment,
                  "work_dir":str(work), "car":str(CAR), "car_metadata":str(CAR_METADATA),
                  "circuit":str(CIRCUIT), "start":start, "end":end, "frames":frames,
                  "full":full, "fps":fps, "size":list(size), "camera":camera,
                  "playback_speed":playback_speed,'timeline':timeline,'camera_options':camera_options,
                  'pacing':pacing,'target_duration':target_duration}
        config['quality']=quality
        if alignment_debug:config['alignment_debug']=True
        config['track_source']=source
        config['driving_path']=driving_path
        from services.circuit_lighting import race_lighting
        if generated and not (night and race_lighting(comparison.year,comparison.event) in ('night','twilight')):
            from services.circuit_scenery import scenery_plan
            config['scenery_plan']=scenery_plan(driving_path,comparison.event)
        if singapore:
            config['source_glb']=driving_path['source_glb']
            config['source_reference']=str(layout_for(comparison.year)['reference'])
        config['circuit_presentation']=presentation(comparison.year,comparison.event,source)
        if generated:
            config['circuit_presentation']['elevation']=road_mesh.get('elevation')
        if singapore:
            config['circuit_presentation'].update(backend='original-glb',
                description=driving_path['adaptation'],credit=driving_path['environment_credit'])
        if generated and not singapore: config['generated_road']=road_mesh
        cache=destination.parent/'render_cache'/f'{render_cache_key(config)}.mp4'
        if cache.is_file() and cache.stat().st_size>1000:
            if cancelled and cancelled():raise InterruptedError()
            pending=destination.with_suffix('.partial.mp4')
            try:
                shutil.copyfile(cache,pending)
                if cancelled and cancelled():raise InterruptedError()
                pending.replace(destination)
            finally:
                pending.unlink(missing_ok=True)
            if progress_callback:progress_callback(1.,'Reused completed render · no Blender wait')
            return destination
        config_path=work/"config.json"
        config_path.write_text(json.dumps(config),encoding="utf8")
        command=[str(blender_executable()),"--background","--disable-autoexec","--python-exit-code","1",
                 "--python",str(ROOT/"scripts/render_3d_test.py"),"--","--config",str(config_path),"--animate"]
        from services.video_3d_overlay import encode_frames
        producer_done=threading.Event();pipeline_failed=threading.Event()
        def pipeline_cancelled():
            return pipeline_failed.is_set() or bool(cancelled and cancelled())
        def compose():
            try:
                return encode_frames(comparison,work/'frames',destination,size=size,fps=fps,start=start,end=end,
                    frames=frames,full=full,cancelled=pipeline_cancelled,
                    playback_speed=playback_speed,
                    driving_path=config['driving_path'],producer_done=producer_done,discard_frames=True,require_ready=True)
            except BaseException:
                pipeline_failed.set()
                raise
        with ThreadPoolExecutor(max_workers=1,thread_name_prefix='3d-compose') as pool:
            composed=pool.submit(compose)
            try:
                run_blender(command,cancelled=pipeline_cancelled,progress_callback=progress_callback,
                            frames=frames,log_path=work/'blender.log')
            except BaseException:
                pipeline_failed.set()
                if composed.done():composed.result()
                raise
            finally:
                producer_done.set()
            composed.result()
        if destination.is_file():
            # Cache only successfully composed, fully encoded videos.
            # Cache errors must never turn a successful export into a failure.
            pending_cache=cache.with_suffix('.partial.mp4')
            try:
                cache.parent.mkdir(exist_ok=True)
                shutil.copyfile(destination,pending_cache);pending_cache.replace(cache)
            except OSError:
                pass
            finally:
                try:pending_cache.unlink(missing_ok=True)
                except OSError:pass
    return destination
