# 3D asset intake

Downloaded 2026-10-10 for RACE HYPE's future telemetry-driven 3D renderer.
Video Studio offers a licensed-model 3D beta for French Grand Prix 2022, plus
seven telemetry-built circuits, including Singapore (2018 onward). Its background
Blender renderer imports geometric datablocks with automatic Python execution
disabled. Unsupported selections retain the working 2D renderer.

## Detailed car

### Active rendering model: Qvist_designs concept

- Source: https://sketchfab.com/3d-models/f1-2026-concept-polygon-model-ea3bde709b1e4dc9b0ec8557d106ed42
- **F1 2026 concept (polygon model)** by **Qvist_designs**.
- License: **CC BY 4.0**, https://creativecommons.org/licenses/by/4.0/.
- Original download: `cars/qvist/source.glb`; its embedded asset metadata records
  the creator, title, source and license. Keep the original untouched.
- Prepared server-side copy: `cars/qvist/car.blend` and `metadata.json`.
- Modifications: millimetres → metres, orientation/origin normalization, mesh
  welding, separation of four wheels, reduced tessellation (~251k faces),
  paint/carbon/accent assignments, animated wheels and team-inspired materials.
- Reproduce preparation with Blender `--background --disable-autoexec
  --python-exit-code 1 --python scripts/prepare_qvist_car.py -- --prepare`.
- Colors follow **session team metadata**, not a driver's current team. Shared
  teams retain the same body paint with different accents and display colors.
- This is still one generic concept shape, **not an authentic team/year model**.
- Creator/license/modification credit is shown in the video, linked in Video
  Studio's accuracy expander and embedded with source/license URLs in MP4 tags.

### Previous detailed model (retained, not the active renderer)

- **F1 Concept Car 2026**, by **BGRT-Studio**.
- Source: https://www.cgtrader.com/free-3d-models/car/racing-car/f1-concept-car-2026
- Creator: https://www.cgtrader.com/designers/bgrt-studio
- License displayed: **Royalty Free License (No AI)**. This is not CC0.
- Downloaded optimized FBX: `incoming/cgtrader_optimized_F1_Concept_2026.fbx`.
- Full ZIP downloaded: `incoming/F1_Concept_2026.zip` (435,495,635 bytes).
- Blender model and textures extracted under `cars/bgrt/F1_Concept_2026/`.
- Generic concept car, not an authenticated team/year replica.
- Intended use: server-side rendering of composed comparison videos. Do not
  expose the raw model through a public static directory, downloads, or a public
  source repository. No AI training use.
- Platform license: https://help.cgtrader.com/hc/en-us/articles/360015124437-Royalty-Free-License
- Free-model commercial guidance: https://help.cgtrader.com/hc/en-us/articles/360015122437-Can-I-commercially-use-a-free-model

## Real circuit

- **Paul Ricard F1 circuit**, by **narlankaaditya**.
- Source: https://sketchfab.com/3d-models/paul-ricard-f1-circuit-d71a363f263a4504aff08d17366e7ccf
- License: **CC BY 4.0**, https://creativecommons.org/licenses/by/4.0/
- Download page explicitly states commercial use allowed, author credit required.
- Files: `incoming/paul_ricard_f1_circuit.glb`,
  `incoming/paul-ricard-f1-circuit.zip` (original Blender source).
- Original Blender file extracted under `circuits/paul_ricard/source/`.
- Suggested video/platform credit: "Paul Ricard F1 circuit" by narlankaaditya,
  via Sketchfab, licensed CC BY 4.0. Link the source and license and disclose any
  modifications (alignment, materials, scenery, etc.).
- Circuit geometry includes elevation; it is not a complete photorealistic
  environment. Telemetry alignment, scale, orientation and start-line placement
  must be validated before claiming accurate reconstructions.

## CC0 fallback assets

| Asset | Creator | Source | Archive |
|---|---|---|---|
| Low-poly Formula 1 car | DREAM_SEARCH_REPEAT | https://opengameart.org/content/low-poly-formula-1-car | `incoming/opengameart_f1_car_cc0.blend` |
| Low-poly race car | mabaci | https://opengameart.org/content/free-low-poly-3d-race-car-model-%F0%9F%8F%8D%EF%B8%8F%F0%9F%8F%81%F0%9F%9A%A6%F0%9F%8F%86 | `incoming/opengameart_racecar_cc0.zip` |
| Car Kit | Kenney | https://kenney.nl/assets/car-kit | `incoming/kenney_car-kit.zip` |
| Racing Kit | Kenney | https://kenney.nl/assets/racing-kit | `incoming/kenney_racing-kit.zip` |

Kenney Racing Kit is modular track/scenery, NOT a real F1 circuit.
Retain each archive's license alongside extracted assets.

## Validation and next integration step

Run `.venv/Scripts/python.exe scripts/inspect_3d_assets.py` for archive paths,
SHA-256 checksums, GLB structure and FBX/Blender headers. This is structural
inspection, not visual/render approval. No untrusted embedded code is executed.

## First 3D test (completed)

- Video: `output/video_studio/3d_test/paul_ricard_LEC_VER_3d_test.mp4`.
- 8 seconds, portrait 540 x 960, 24 fps, 192 frames, silent H.264 MP4.
- French Grand Prix 2022 qualifying Q3: LEC lap 16 (90.872 s), VER lap 13
  (91.176 s), showing lap-relative seconds 4.00 through 11.96.
- Generic cars are recolored for identification, not official Ferrari/Red Bull
  replicas. This initial prototype used fixed 2.5 m lateral separation. The
  integrated renderer below now uses an asphalt-constrained route and adaptive spacing.
- Real lap timing and speed/gear samples drive the animation. This is a ghost
  comparison, NOT an inferred real overtake, crash or exact racing-line replay.
- The circuit geometry was rescaled (2.558 model units per telemetry metre) and
  rotated/translated to the telemetry. Road-sample RMS is 1.737 model units
  (approximately 0.679 m). 98.9% of reference samples raycast onto asphalt/kerbs;
  1.1% hit the model's sand material. This is a structural fit check, NOT a claim
  of surveyed spatial accuracy. Scenery, ground, materials and helmet are styled.
- Portable official Blender 4.5.9 LTS under `tools/blender/`; SHA-256 checked
  against the vendor's checksum. No system install or downloaded asset code run.
- The editable test scene is stored beside the MP4. It contains licensed geometry
  and must remain private, just like the source car asset.

To reproduce from the project directory (PowerShell):

```powershell
.venv/Scripts/python.exe scripts/prepare_3d_test.py
& tools/blender/blender-4.5.9-windows-x64/blender.exe --background --disable-autoexec --python-exit-code 1 --python scripts/inspect_blender_assets.py
.venv/Scripts/python.exe scripts/align_3d_test.py
& tools/blender/blender-4.5.9-windows-x64/blender.exe --background --disable-autoexec --python-exit-code 1 --python scripts/render_3d_test.py -- --animate
.venv/Scripts/python.exe scripts/compose_3d_test.py
```

## Integrated Video Studio workflow

Choose **3D · Cinematic beta**, select a circuit preset, click **Use circuit
preset**, then **Load session**. Choose actual drivers and valid fastest/numbered laps. Pick
portrait or landscape, following camera or full circuit, and a 2–30 second clip
or full lap. Preview at 540p/24 fps; export at 720p or 1080p, 24 or 30 fps.
Full laps preserve both original timings and include a two-second final result.
Short clips are clamped to the slower lap's duration. No audio is generated.

One shared render worker handles both 2D and 3D jobs, with a bounded queue,
progress and cancellation. Each 3D job checks its path against calibrated road
geometry, builds a smooth arc-length route on asphalt only (not kerbs/runoff),
tapers decorative ghost spacing in narrow sections and checks nine body-bound
footprint points per car per rendered frame against the exact asphalt triangles.
It uses a private temporary directory,
and publishes only a fully encoded MP4. Cancellation kills the owned Blender
process and removes temporary frames/partial encodes; existing outputs remain.
Unsafe alignment or missing dependencies produces an actionable error.

Monza, Silverstone and Spa use procedural geometry from the selected lap's
telemetry layout. No additional third-party circuit model is downloaded or
credited to the Paul Ricard author. Their 12 m asphalt, alternating kerbs, grass
and flat elevation are illustrative, not surveyed or authentic venue scenery.
These tracks require the private generic car bundle but not Paul Ricard's asset
or calibration. They retain distance-based motion, footprint/camera checks,
private temporary frames, cancellation and atomic MP4 publication.

### Deployment

Provide FFmpeg on PATH and Blender on PATH or through `RACE_HYPE_BLENDER`.
Locally the service discovers the official portable Blender under `tools/blender`.
Provision these private files outside any web-accessible static directory:

- `cars/bgrt/F1_Concept_2026/F1_Concept_2026.blend`
- `cars/bgrt/metadata.json` (evaluated import transforms)
- `circuits/paul_ricard/source/PaulRicardnosides.blend`
- `circuits/paul_ricard/mesh.npz` (derived alignment geometry)
- `paul_ricard_alignment.json` (calibration/source credit)

The renderer does not expose Blender scenes or source models. Raw assets and
portable Blender remain excluded from Git. This is still a stylized beta: no
official team replicas, surveyed racing lines, crash physics or real-overtake
inference. Additional licensed models require their own calibrated asset profiles;
telemetry-built venues require a catalogue entry plus layout/render validation.
# Singapore source eras

The local Singapore files are selected automatically by session year:
`circuits/singapore/singapore.glb` through 2022, and
`circuits/singapore/singapore-2023.glb` from 2023 onward. Both source files
are imported directly with all original mesh/material data preserved. Read-only
asphalt indexes and source fingerprints are separate in
`circuits/singapore/prepared/source-pre-2023` and `source-2023-onward`.
The new source's separately named road, walls, fencing and cleared site are
included as supplied. No source mesh is deleted, decimated, recolored or
covered by a telemetry-built road. Telemetry animates the cars/HUD; car routes
are constrained to the original model asphalt. Footprint/scenery checks stop
unsafe renders rather than changing the track. Run
`scripts/index_singapore_sources.py` in trusted Blender to refresh the index;
the former adapting preparation script is now a compatibility wrapper for it.

Original-source provenance remains unverified; the local edit does not clear
third-party rights. Keep both GLBs and prepared environments server-side.

