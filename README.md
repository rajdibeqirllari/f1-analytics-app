# RACE HYPE — React + Python motorsport platform

The immersive application runs at **http://localhost:8000**, with React and
TypeScript connected to the existing Python engines through FastAPI. See
[installation, architecture and verification](docs/MIGRATION.md). The original
Streamlit app remains runnable at http://localhost:8501 during migration.

## Streamlit and rendering reference

## Video Studio

The **Video Studio** workspace creates deterministic 2D and supported-circuit 3D
ghost-lap comparison videos from real FastF1 telemetry. No generative-video API
or paid service is used.

1. Choose a year, Grand Prix and session, then **Load session**.
2. Select two different drivers. Compare their fastest valid laps, or choose a
   lap independently for each driver. Qualifying supports Q1/Q2/Q3 filtering.
3. Choose vertical 9:16 or landscape 16:9 and a following or full-circuit camera.
4. **Build full lap preview**, then **Export MP4** at 720p/1080p and 30/60 fps.
5. Download the current video. Generated files remain in `output/video_studio/`.

Requires FFmpeg on PATH alongside the Python dependencies. Keep Streamlit running
while rendering; jobs execute in a bounded background queue and can be cancelled.
Previews are full-lap silent H.264 MP4s at 540p/24 fps. Exports use the same renderer.
Initial session loading needs internet access unless the session is already cached.

### Accuracy and scope

- Both laps begin at elapsed lap time zero, but retain their individual official
  durations. Final timing differences use those official lap times.
- Intermediate delta is estimated at matching **normalized integrated-speed
  distance**; it is not official sector timing or centimetre-accurate positioning.
- Cars follow one shared telemetry-derived reference path, separated sideways for
  readability. These are lap ghosts, **not a reconstruction of actual overtakes**.
- Speed, gear, throttle and brake come from telemetry. Discrete gear/brake changes
  hold the latest sample. Missing channels are marked unavailable.
- Incomplete laps and telemetry gaps longer than two seconds are rejected. Pit,
  deleted, non-green and potentially inaccurate laps carry visible data notes.
- The 2D renderer uses original car silhouettes. The 3D beta uses licensed generic
  models and stylized circuit scenery. Neither generates onboard footage, crash
  physics or engine sound.

### 3D beta

Choose **3D · Cinematic beta** → select a **3D circuit preset** →
**Use circuit preset** → **Load session**.
Select drivers and laps, clip start/duration (or full lap), format and camera.
**Build 3D preview**, then export/download an MP4. Preview is 540p/24 fps;
3D export supports 720p/1080p at 24/30 fps. The original 2D workflow still supports
all available sessions and 60 fps. Supported 3D circuits:

| Circuit | Years | Geometry |
|---|---|---|
| Paul Ricard / French GP | 2022 | Calibrated licensed model |
| Singapore / Marina Bay | 2018 onward | Original GLB selected by year |
| Monaco | 2018 onward | Telemetry-built layout |
| Red Bull Ring / Austrian GP | 2018 onward | Telemetry-built layout |
| Bahrain | 2018 onward | Telemetry-built layout |
| Monza / Italian GP | 2018 onward | Telemetry-built layout |
| Silverstone / British GP | 2018 onward | Telemetry-built layout |
| Spa-Francorchamps / Belgian GP | 2018 onward | Telemetry-built layout |

Telemetry-built circuits use the selected session's complete reference lap, not
an unrelated year's downloaded model. Asphalt is illustratively 12 m wide, kerbs
and grass are stylized, and elevation is flat. These are **not scanned/surveyed
circuits or authentic venue scenery**. Missing telemetry, open/implausible layouts
or unsafe car footprints are rejected; 2D remains available. Titles and source
credits follow the selected circuit. The presets are convenient starting points;
you can still change years, drivers, sessions and laps.

The chase camera now uses offline, symmetric damping for stable cornering and
smooth pull-back framing. Team-colored ribbons follow each ghost's timed path and
fade over two seconds (four seconds on the circuit overview). Warm directional
sunlight, cool soft fill and higher-contrast grading give both preview and export
the same cinematic treatment. Concept cars now use the Qvist_designs model,
with team-inspired body paint from the selected session's team metadata, dark
tires/carbon and contrasting accents. Trails, cards and map markers match;
teammates use distinct accents without changing their team's main body paint.
Creator, source, CC BY 4.0 license and modifications are credited in the app/video.
This generic 2026 concept shape is not an authentic historical/team replica.
These effects change presentation only, not lap
samples, car timing or the comparison delta.

Both 3D previews and exports include a fixed-aspect circuit locator with a
start/finish marker, team-colored car positions, short movement ribbons and a driver
legend. Its positions follow the exact timed, asphalt-constrained ghost routes
used by Blender, rather than a separate approximation of telemetry coordinates.

Requires server-side Blender and FFmpeg. Local portable Blender is auto-detected;
on another host set `RACE_HYPE_BLENDER` to its executable. Rendering runs in the
same bounded, cancellable background queue as 2D. Keep the app running until
completion. Full laps can take substantially longer than short clips.

Every 3D selection is checked against the selected circuit's asphalt. Its shared display
route is smoothed, constrained to asphalt and resampled by geometric distance.
Continuous integration of interpolated telemetry speed avoids velocity jumps at
sample boundaries while retaining the original progress anchors and lap clocks.
Ghost spacing tapers smoothly in narrow sections; each rendered frame's complete
car footprint is checked against actual asphalt triangles before publication.
Generic recolored cars use decorative separation, not
official team liveries or inferred real racing lines/overtakes. Source models and
temporary frames stay private; only completed MP4s are offered for download.
Provision the private assets separately from Git. See [3D assets and deployment](assets/3d/README.md)
for required files, licenses, attribution and known accuracy limitations.

### Night Chase

Night Chase now uses a shared asphalt-constrained minimum-curvature display
line, curvature-derived front-wheel steering and modest camera heading
follow-through. These are illustrative animation features, not recovered
driver-specific racing lines or measured steering inputs. Both drivers retain
their source lap timing and telemetry. Road furniture follows the unchanged
road center; the whole car footprint is checked before publishing a render.
The telemetry-built night streetscape remains original scenery. Singapore
sessions automatically select the supplied source by year:

| Session year | Source in `assets/3d/circuits/singapore` |
| --- | --- |
| 2022 and earlier (within supported telemetry years) | `singapore.glb` |
| 2023 onward | `singapore-2023.glb` |

Both GLBs are now imported **directly**, not through the former modified
environment copies. Original vertices, faces, UVs, transforms, materials,
barriers, road markings and scenery remain unchanged. No replacement road,
generated kerbs/fences, added ground, decimation or scenery deletion is used
for Singapore. Camera/light rigs, cars, trails and HUD are separate additions.

Only a read-only asphalt index is cached in `prepared/source-pre-2023` or
`prepared/source-2023-onward`. The index is not rendered. Previews and exports
share `layout_for(year)` and `model_route(comparison)`: source telemetry drives
lap clocks/telemetry, with car motion constrained to the existing GLB asphalt.
This does not establish recorded individual racing lines. The GLB itself is
not a surveyed venue, regardless of whether its source geometry is preserved.

Run `scripts/index_singapore_sources.py` in trusted Blender after replacing a
GLB. Source size/mtime is checked and SHA-256 recorded. Missing/stale source
data or unsafe alignment stops an **Original GLB** render; it never silently
changes the track source. **Track source** now offers **Original GLB** alongside
**Telemetry-built** for Singapore, and **Circuit model** alongside
**Telemetry-built** for Paul Ricard 2022. Every supported circuit has the
telemetry-built option; circuits without an installed model show that option
alone. Preview/export jobs, cache keys and attribution honor the explicit
choice. Telemetry mode never imports the model. Paul Ricard telemetry also
supports 2018–2022 sessions where data exists; its supplied model stays limited
to the calibrated 2022 version. Night Chase works with every telemetry track;
the Paul Ricard model remains a Cinematic option. Cache keys include the
GLB/index revision, selected source and render version.
Validation compares source geometry, UVs, transforms and material graphs
before and after scene assembly. Former hybrid prepared scenes are unused.

The supplied model's uploader lists CC BY 4.0 but also tags it as ripped /
Assetto Corsa. Provenance and public/commercial rights are **not verified**.
The UI warns before rendering; creator credits are included in video frames
and MP4 metadata. Keep source geometry private and resolve rights before
publishing footage using that environment. No paid assets are required.

Choose **3D · Night Chase**, load a supported telemetry-built circuit/session,
select two laps, then choose the **Chase driver**. Singapore is the starting
preset; the other telemetry-built circuits also support this presentation.
Paul Ricard's licensed asset backend remains available in Cinematic beta.

Night Chase adds a low rear camera following the selected driver, an overlapping
transparent comparison ghost, original procedural buildings, barriers, catch
fences, floodlights, bridge signs and road markings. The other ghost can leave
the close camera view; the mini-map continues to track both cars. Trails show
recorded braking in red and throttle in green, dimming when throttle is lifted.
Brake is a sampled boolean signal, not a pressure percentage. The compact driver
panels use the same speed, gear, lap clocks, pedal data and matching-distance
delta as the existing workflow. RH branding is composed automatically.

Previews and exports share the same rendering/composition pipeline, isolated
temporary frames, cancellation and completed-MP4 publication. Camera framing is
validated for the selected chase car; the asphalt footprint check still covers
both ghosts on every frame. Source lap samples and official durations are not
modified. The existing 2D and Cinematic beta options retain their presentation.

The environment is illustrative, not a surveyed recreation of Marina Bay or the
reference video's assets. Cars use the existing licensed Qvist concept with
session-specific team-inspired colors, not authentic team liveries. The shared
ghost route does not establish individual real racing lines or engine power.

### 3D render speed

Procedural night floodlights use bounded 55 m illumination and no city-wide shadows. An
eight-light pool follows the chase car while all emissive lamp fixtures remain
visible. Singapore's original-GLB mode does not add these fixtures or any
procedural scenery; only the existing camera/light rig illuminates it.
A local chase fill retains nearby shadows. Fast (default), Balanced
and High use 2, 8 and 32 edge-smoothing samples respectively; resolution, FPS,
lap clocks and car motion stay unchanged. Ghosts/trails use alpha blending
instead of noisy stochastic transparency. Fast can show more edge aliasing.

Completed identical renders are reused from a private `render_cache` folder.
Keys include lap data, camera, clip range, size, FPS, quality, branding version
and geometry revisions; changed selections cannot reuse the wrong video.
An approximate remaining render time appears after the first few frames.
# React + Python platform

The new integrated platform runs alongside the original Streamlit app. All nine
workspaces use the Python data/rendering engines. Install dependencies, then run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\scripts\start-platform.ps1 -SkipBuild
```

Open http://localhost:8000. The original Streamlit app remains on port 8501.
See [migration and architecture documentation](docs/MIGRATION.md) for development,
data integrity, licensing, local job behavior and validation details.

