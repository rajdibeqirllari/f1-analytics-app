# RACE HYPE: React + Python migration

## Repository audit

The original app is Streamlit. `app.py` defines reusable FastF1 analysis functions,
then runs the modern workspace router, then `st.stop()`. The retained legacy UI is
an inert string. The API never imports `app.py`, `overlay_app.py`, or UI workspaces.

Existing services provide canonical FastF1/OpenF1 telemetry, production export
formats, Pillow/FFmpeg overlay rendering, comparison/video jobs, Blender rendering,
replay cache/payload builders and f1radio archives. Existing browser components
provide real replay seeking, playback speed, driver focus, labels and DRS controls.
The overview uses published Jolpica results and standings independently of telemetry.

`services/analysis_service.py` is a mechanical extraction of 43 existing helper and
chart functions. Their mathematics were preserved. Plotting runs under a lock
because Matplotlib settings are global. `tools/extract_analysis.py` records the
extraction, but is not part of startup. Streamlit remains independently runnable.

The supplied ZIP contains one HTML/CSS/JS visual prototype and Ferrari artwork.
Its generated curves, timing rows, car motion and speech synthesis are demonstration
code and are not used. Its supplied stylesheet and artwork are preserved under
`frontend/public/design` as the visual reference. No essential source modules are
missing. Blender/FFmpeg availability and external data availability are runtime
conditions, reported by the API and UI.

## Architecture

- `frontend/`: React, TypeScript, Vite, React Router, Recharts. Session context is
  carried in URL query parameters and local storage. Related workspaces share a
  loaded driver catalog and cached requests.
- `api/main.py`: FastAPI routes, real service adapters, bounded background tasks,
  the existing VideoJobs worker, approved downloads, CSV upload and replay viewer.
- `api/engines.py`: timing classification, actual telemetry traces and adapters
  into the existing analysis, HUD, replay and radio engines.
- `api/files.py`: opaque file IDs, explicit output roots and file type allowlist.
  Neither arbitrary paths nor the assets/3d directory are exposed.

The application is a local workstation. Bind to loopback. One API process owns the
render queues; do not run multiple Uvicorn workers. Active metadata lives in memory;
saved outputs and existing service disk caches survive restarts. Cancellation is
cooperative: a provider request or FFmpeg encode already in progress may finish
before stopping. Never label historical session data as a live feed.

## Installation and startup

```powershell
cd C:\f1hud_app
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000. `scripts/start-platform.ps1` performs the build/start
sequence. For frontend development, run `npm run dev` in `frontend/` alongside
the API. Vite proxies /api and /art to the API on port 8000.

The original app is still available with:
`\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501`.

## Data and assets

Choose a real supported weekend. Failed session downloads produce explicit errors;
no synthetic laps, classifications or championship rows are substituted. Uploaded
CSV data is identified as uploaded. Missing future telemetry channels remain null.
Full FastF1 exports use the driver's session car-data stream; selected-lap exports
use lap telemetry. Their available columns can therefore differ.

3D uses telemetry-built illustrative circuits only. Generic concept car credit:
Qvist_designs, CC BY 4.0, https://sketchfab.com/3d-models/f1-2026-concept-polygon-model-ea3bde709b1e4dc9b0ec8557d106ed42.
Camera paths, track widths, scenery and ghost routes are illustrative; they do not
prove individual racing lines. Audio is only played from actual archive recordings.
User-supplied artwork retains its original licensing obligations; no new third-party
models are included. The supplied prototype README is retained with the artwork.

## Validation

Run `python -m unittest discover -s tests` and `npm run build` in frontend.
API integration tests are in `tests/test_platform_api.py`; use FastAPI TestClient.
Provider-independent tests use explicitly labelled fixtures; live historical smoke
checks must report provider failures separately from UI/API failures. See the final
validation checkpoint in this document for the checks actually performed.

## Validation checkpoint — 19 October 2026

Implemented: all nine React destinations, shared URL/session state, real driver
catalogs/portraits, published results and standings, historical timing/weather/
race-control messages, interactive telemetry traces, all 17 chart exports, video
preview/final/cancel/progress, four telemetry packages, HUD preview and all three
alpha export formats, actual browser replay, real radio playback/downloads and an
output library with search/filter/preview/download.

Checks performed:

- Production TypeScript/Vite build passed; workspace bundles load lazily.
- Nine API integration tests passed, including unavailable-provider errors,
  automatic source fallback, nullable future fields, actual worker handoff,
  upload/download behavior, output path restrictions and unsupported replay input.
- Final complete Python discovery: **95 tests passed**. The initial run exposed
  five obsolete cases expecting eight circuits or enabled original GLB sources.
  Those assertions were migrated to the user's current expanded-catalogue and
  telemetry-only requirements in `test_circuits_3d.py`, `test_singapore_asset.py`
  and `test_track_sources.py`. They now verify that imported models are rejected
  for previews and exports, and that telemetry tracks need no original bundle.
  No legacy GLB behavior was re-enabled and no test was skipped.
- Affected API/comparison/creator/standings tests: 25 passed; 3D renderer tests
  discovered separately: 12 passed. Original constructor timeline Node tests:
  9 passed. Directly selecting some legacy Python modules requires `tests/` on
  the import path, so use unittest discovery for those modules.
- **2025 Austrian GP qualifying:** real 20-driver catalog, both VER/LEC telemetry
  traces (491 samples each), canonical and full-session telemetry, After Effects
  TSV, RaceRender CSV, timing/weather/messages, HUD preview, replay payload and
  ten actual radio archive clips. An actual recording returned audio/mpeg and
  102,144 bytes through the audio route.
- All **17 chart calculations** rendered on the cached **2024 Monaco race**.
  Reports: `tmp/platform-analysis-verification.json` and smoke JSON reports.
- Real short 2D preview rendered at 540×960 / 24 fps (a one-second interval plus
  the existing two-second result hold). Real 3D preview rendered, followed by a
  720p / 30 fps final 3D MP4 export. These were short verification clips, not a
  complete lap or a full-lap performance benchmark. HTTP video seeking returned
  206 Partial Content for a requested byte range.
- All three HUD formats exported using a short excerpt of actual Austrian
  telemetry: WebM VP9 Alpha, MOV ProRes 4444, PNG Sequence. WebM alpha_mode=1;
  decoded alpha extrema were 0–255. ProRes pixel format was yuva444p12le.
- All nine React routes opened in the browser. Driver/weekend context carried
  between related tools; real telemetry was plotted; a preview rendered from
  React controls and became playable/downloadable. The real replay cockpit was
  loaded with recorded geometry and playback controls.
- Desktop and 390px phone layouts inspected. Phone document width equalled
  scroll width (no horizontal overflow); the mobile menu exposes all nine labels.

External OpenF1 downloads and a forced live-provider fallback were not exercised;
automatic fallback routing was verified using test fixtures. Unsupported or
unavailable source sessions still need explicit source errors. Full-lap 1080p
Blender rendering was not rerun. Pre-season/testing selectors from the legacy
application remain available in Streamlit; this React release exposes the race
weekend workflows listed above. Streamlit has not been retired or declared fully
replaced. Source availability and coverage remain provider-dependent.

Reproducible checks:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_platform_api
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test tests/constructor_timeline.test.js
.\.venv\Scripts\python.exe scripts/smoke_platform.py
.\.venv\Scripts\python.exe -m scripts.verify_analysis_charts
.\.venv\Scripts\python.exe -m scripts.verify_hud_exports
```
