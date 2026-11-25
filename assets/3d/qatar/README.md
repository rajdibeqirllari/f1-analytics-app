# Lusail (Qatar) venue for the 3D Broadcast

First detailed venue for the Live / Replay 3D Broadcast. The browser loads it only when the session's meeting matches
`qatar|lusail|losail`; every other circuit keeps the procedural world.

## Files

| What | Where |
|---|---|
| Editable Blender source | `assets/3d/qatar/blender/lusail.blend` |
| Browser asset (Draco + WebP, 2.94 MB) + manifest | `frontend/public/venues/lusail/lusail.glb`, `manifest.json` |
| Layout data (centreline, edges, elevation, landmarks, grid, OSM footprints) | `assets/3d/qatar/lusail_layout.json` |
| Original textures (generated, no photos) | `assets/3d/qatar/textures/` |
| References | `refs/osm/lusail_osm.xml` (ODbL), `refs/fia/` (FIA map, local only, gitignored) |
| Live-page outline (2D map + estimated positions) | `frontend/src/hype/circuits/qatar-grand-prix.json` |
| Verification report | `outputs/qatar/alignment_report.json`, captures in `outputs/qatar/captures/` |

## Rebuild (from `C:\f1hud_app`)

```
.venv\Scripts\python.exe scripts\qatar\prepare_lusail.py      # OSM + OpenF1 -> layout (about 10 min, mostly the ICP search)
.venv\Scripts\python.exe scripts\qatar\landmarks.py           # corners, grid slots, start line
.venv\Scripts\python.exe scripts\qatar\driven_line.py         # median driven line (rubber)
.venv\Scripts\python.exe scripts\qatar\make_textures.py       # textures
.venv\Scripts\python.exe scripts\qatar\export_outline.py      # Live-page outline
tools\blender\blender-4.5.9-windows-x64\blender.exe --background --factory-startup --python-exit-code 1 --python scripts\qatar\build_lusail_blend.py
.venv\Scripts\python.exe scripts\qatar\verify_alignment.py    # checks against the 2025 race (needs the OpenF1 cache)
cd frontend; npm run build
```

## Sources and credits

- **OpenStreetMap** (© OpenStreetMap contributors, ODbL 1.0), extract 2026-11-25: asphalt surface polygon
  (relation 18052714) for the road edges, circuit centreline (relation 21297662), F1 pit entry + pit lane ways,
  building/grandstand/bleacher footprints, fences, turf areas. The layout JSON is a derived database (ODbL applies if
  it is published); the rendered venue is a produced work and carries the attribution in the viewer.
- **FIA circuit map, Qatar 2025, version 2 (27.11.25)**: centreline length 5.419 km, turn numbering/directions,
  S1 80 m before T6, S2 75 m before T12, speed trap 205 m before T1, DRS points. Reference only, not shipped.
- **OpenF1** location, 2025 Qatar GP race (session 9850, free/non-commercial): used only to align the map to the F1
  position frame, for elevation, the rubbered line, the grid slot positions and the on-track checks.
- **Ashghal (4 Oct 2023), The Peninsula (24 Sep 2023), Gulf Times (28 Sep 2023)**: 402.1 m pit building, 50 garages,
  Paddock Club above the garages, Lusail Hill at Turn 1.
- **Photos (visual reference only, nothing copied)**: LCSC race photo Nov 2025 (kerb/edge paint, floodlights), 2024 race
  start at T1 (maroon run-off, pale-blue band, pit building lighting), main grandstand render (roof shape).
- No logos, sponsor boards or real signage: boards are plain maroon, the gantry has no branding.

## What is measured, reconstructed, or still needs references

**Measured** (from data): centreline and asphalt edges (OSM polygon; 5,419.5 m vs FIA 5,419 m, +0.01 %); corner
apexes and directions; pit lane path; pit building footprint (406 m vs 402.1 m official) and main grandstand footprint
(417 m); turf areas; elevation (median of 20 cars' samples, range 4.2 m); rubbered line position; grid slot stations
(8.00 m spacing) and start line (234.6 m after the control line, from the pole car's parked position).

**Reconstructed from photos / estimates**: kerb extents per corner and the red/white 2 m pattern; run-off depth,
maroon paint and the pale-blue/white band on the straights; wall + debris-fence line and heights (1.05 m + 3.6 m);
floodlight pole spacing (42 m), height (22 m) and heads; pit building section (storey heights, terraces, purple LED
soffits, canopy at ~16 m); grandstand rake and roof height; Lusail Hill size and position; brake board positions
(T1, T6, T10); grid stagger side (the feed has no lateral offset, pole is assumed on the right); heights of other
buildings; no crossfall/camber on the asphalt.

**Needs better references**: corner-by-corner kerb profiles (sausage kerbs, T12-14 after the 2023 changes), exact
run-off paint layout per corner, real floodlight pole positions/heights and lamp counts, barrier types per corner
(tyre walls / TecPro), marshal posts and service roads, pit building elevation drawings, sector/DRS line paint.

## Alignment (2025 Qatar GP race, `verify_alignment.py`)

- Placement is exact for OpenF1/FastF1 scenes: the scene payload carries `track.frame` (the F1 frame offset) and the
  GLB is authored in that frame (minus `origin`), so no fitting is involved. A rigid fit is the fallback.
- OSM → OpenF1: scale check 1.0016, rotation 0.19°, median 1.8 m to the nearest car sample.
- Browser check vs the scene's own fastest lap (a driven line, so a few metres in corners is expected): median 2.4 m,
  p95 4.3 m; landmarks: control line 2.0 m, start line 1.1 m, T1 1.1 m, T12 3.6 m, T13 2.7 m, T14 3.4 m, T16 1.7 m.
- Every on-track sample of all 20 cars, whole race (280,887): 0.012 % put the car body over the model's edge, none by
  more than 1 m (worst: T9 0.29 m, T7 0.11 m); recorded elevation vs model surface median 0.00 m, p95 0.05 m; no drift
  between early and late laps.
- Estimated mode (bundled outline): racing line never over the edges; outline within 1.06 m (median) of the model.
  No Qatar timing recording exists yet, so estimated-mode cars could not be driven on Lusail in the browser; record the
  2026 weekend (27-29 Nov) to check it.
