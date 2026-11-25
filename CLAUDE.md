# Race Hype (C:\f1hud_app) — project notes for Claude Code

Owner posts F1 content as **Race Hype** (TikTok / Instagram / YouTube). Replies can be short; the owner writes English and Albanian.

## Run
- Engine + site: `.\scripts\start-platform.ps1 -SkipBuild` → FastAPI on http://127.0.0.1:8000 (serves the built frontend too).
- Python: `.\.venv\Scripts\python.exe` (Py 3.10, has fastf1, pandas, scipy, Pillow). FFmpeg is on PATH.
- Frontend: `frontend/` (React 19 + TS + Vite 7). `npm run build` → `frontend/dist`, then Ctrl+F5. Backend changes need an engine restart.
- Blender 4.5.9: `tools\blender\blender-4.5.9-windows-x64\blender.exe`.

## The new site: `/hype` (frontend/src/hype)
Separate redesign so the old ChatGPT-built pages stay untouched (`main.tsx` adds the `/hype/*` route; old UI = "Classic workspace").
- `HypeApp.tsx` shell, `nav.ts` (order: Weekend, Live, Replay, Video, Overlay, Analysis, Timing, Telemetry, Radio, Library), `kit.tsx`/`kit.css`/`hype.css` (scoped `.rhx`), fonts Big Shoulders Display + Barlow bundled.
- Style: dark, broadcast-like, no generic "AI" look. Keep it consistent across pages.

## Live timing (no paid OpenF1 / F1 TV)
- Data: F1's free SignalR stream recorded by `scripts/record_live.py` (patched FastF1 recorder; fixes no-auth TypeError and 4096-byte frame truncation) or via the Live page Record button → `outputs/live/*.txt`.
- `services/live_timing.py` (parse/merge/LiveState/Feed follow+replay/Recorder, `active_yellows`, `track_outline`), `api/live.py`, `tests/test_live_timing.py`.
- Feed quirks: `TimeDifftoPositionAhead` (lowercase t); segment codes 2051 purple / 2049 green / 2048 yellow / 2064 pit; RaceControl `Scope: Sector` = marshal sectors (not S1–S3). No car positions in the free stream → map positions are estimated from mini-sectors.
- Live map (`pages/Live.tsx`): one asphalt colour, whole-sector colouring for a selected driver, smooth no-reverse motion, yellow-flag hazard stripes labelled YELLOW FLAG / DOUBLE YELLOW, pit lane line with cars driving in/out.
- Circuit outlines: bundled `frontend/src/hype/circuits/<slug>.json` (Mexico, hand-tuned: straight horizontal, finish line, pit lane) → else engine `/api/live/track`: FastF1 cache (only if the session really is cached) → **OpenF1** fastest lap (new, auto-rotated) → saved to `outputs/live/circuits/`.
- São Paulo (Interlagos) outline: now **bundled** (`circuits/sao-paulo-grand-prix.json`, from the MIT GeoJSON in bacinger/f1-circuits, turned anticlockwise, finish ~300 m before the Senna S, pit 0.86→0.14; attribution in `circuits/README.md`). Reason: OpenF1 returns 401 during live race weekends, and the engine never saved outlines (fixed: `api/live.py` now passes `store=outputs/live/circuits`). Slugs strip accents ("são" → "sao") in both `Live.tsx` and `track_outline`. For new circuits, bundle the same way.
- **Before restarting the engine, check for running jobs** (`/api/jobs/...` in the engine log): a restart on 2026-11-08 killed a job the owner had running.

## 3D Broadcast (Live page, added 2026-11-24)
- Live page switch **2D Map / 3D Broadcast** (per viewer, localStorage `rhx-live-view`); 3D stage sits above the tower, the 2D map stays in the side column. Camera `rhx-b3d-camera` (pod/broadcast/cockpit) and position source `rhx-b3d-source` are per viewer too; driver = the tower's selection (or the 3D Driver dropdown). Nothing changes server playback.
- Backend `services/scene3d.py` (`SceneManager`, `Timeline`, `Estimator`, `load_recorded`), endpoints `GET /api/live/scene?source=auto|estimated` and `GET /api/live/scene/samples?t0&t1` in `api/live.py`. Tests: `tests/test_scene3d.py` (unittest).
- **Estimated** (always; the only mode for a growing follow file): each car's distance comes only from its own mini-sector / sector / line crossings, interpolated through a curvature-based lap profile (slows for corners); mini-sector positions calibrated from the recording's clean laps. Pit lane = car hidden (no invented pit path); stopped = frozen; >12 s past the newest crossing = stale. No lateral info: cars within 6.5 m are drawn see-through. Measured vs São Paulo OpenF1: median 42 m, p90 104 m error.
- **Recorded**: OpenF1 `location` (~4.1 Hz, x/y/z) for the *same* session (meeting + session + local start time checked), cached in `outputs/openf1_cache`; circuit built from the fastest lap of the same data (one frame, 1/10 m → m). Never for a growing follow file, even if cached. São Paulo 2026 race (`live_2026-11-08_1804.txt`) has it.
- `live_timing.merge` inserts message lists by reference → `scene3d._copy` gives the timeline private copies (otherwise follow mode silently loses crossings).
- Frontend `frontend/src/hype/broadcast/` (lazy chunk with three@0.170): `data.ts` (clock, buffer, Hermite interpolation, poses as pure functions of time), `engine.ts` (world, cameras, loop), `car.ts` (procedural generic car, no liveries), `Broadcast3D.tsx`, `broadcast.css`. Live view runs `LIVE_DELAY` = 5 s behind the feed. Inspection hook: `window.__rhxBroadcast`.
- Good demo: São Paulo race replay, seek 4436 s, ride with ANT (P5): RUS ahead, ANT passes on the pit straight ~4451 s (official P4/P5 swap 4453 s). HAM/LEC/LIN battle ~664–700 s.
- **Replay page too** (2026-11-24): same switch (localStorage `rhx-replay-view`), same component with `api` (`/api/replays/{token}/scene[/samples]`, `services/replay_scene.py`) + the page's clock (`feed.exact`) + the tower's classification (`timing`). The payload is capped at 6,000 frames (~1 Hz for a race), so the scene loads native positions (OpenF1 `location` for OpenF1 replays, FastF1 cache `pos_data` otherwise), reproduces the payload's time 0 and checks it against the frames (≤ 3 m), else falls back to the frames, labelled "coarse". Las Vegas 2026 race: OpenF1 4.2 Hz, aligned to 0.01 m; VER/RUS lead fight lap 3 at ~208–250 s. Tests: `tests/test_replay_scene.py`.
- Racing line (estimated cars, both pages): `scene3d.racing_line` = minimum curvature (4th differences, 16 m stencil) within ±5.4 m; the lap speed profile uses it. Same line for every car (no invented passes).
- Environment from the meeting name (`engine.applyEnv`): street circuits (Las Vegas, Monaco, Singapore, Baku, Jeddah, Miami, Madrid) = walls 4 m from the asphalt + catch fences, concrete, close buildings, lane dashes on straights, camera platforms behind the wall above the fence; night races (Las Vegas, Singapore, Bahrain, Jeddah, Qatar, Abu Dhabi) = dark sky, floodlight poles, lit windows. Based on the owner's Las Vegas 2026 broadcast (reference only; no footage, logos or real buildings used).

## Qatar venue + 2026 car models (3D Broadcast, added 2026-11-25)
- Lusail venue: `assets/3d/qatar/` (README = sources, measured vs reconstructed, rebuild steps), Blender `assets/3d/qatar/blender/lusail.blend`, browser `frontend/public/venues/lusail/{lusail.glb,manifest.json}`. Built by `scripts/qatar/*` (prepare_lusail → landmarks → driven_line → make_textures → export_outline → build_lusail_blend.py in Blender → verify_alignment).
- Geometry: OSM asphalt polygon + centreline (ODbL, attribution shown in the viewer) aligned to the OpenF1 frame (5,419.5 m vs FIA 5,419 m). Telemetry is used only for alignment, elevation, the rubber line and the grid slots.
- Placement: scene payloads now carry `track.frame` (= F1 frame offset; `scene3d.Track(frame=…)`, set by `load_recorded`, `replay_scene`, and bundled outlines with `frame: "f1"`). `venue.ts` places the GLB exactly from it, else a rigid ICP fit; refuses venues > 8 m off. Car z comes from the venue surface (`heightAt`).
- Bundled `circuits/qatar-grand-prix.json` has `z`, `edges` → `racing_line(lo, hi)` keeps estimated cars inside the real edges.
- Cars: `assets/3d/cars2026/` (README), `scripts/qatar/build_cars_blend.py` → `frontend/public/cars/2026/{w17,rb22}.glb` (LOD0/LOD1, steer_/wheel_ pivots, cam_pod / cam_cockpit mounts). `models.ts` resolves by season + constructor; other seasons only via the viewer's **Preview 2026 cars** toggle (localStorage `rhx-b3d-preview-models`), which shows an amber PREVIEW badge. Qvist model assessed and not reused (generic concept, ~250k faces).
- Engine: procedural circuit lives in `this.proc` (hidden when the venue lines up), skyline in `this.far`; venue scenes get night IBL (`nightEnvironment`), a key light with shadows following the camera, venue-aware broadcast camera sites (raycast + pole clearance + occlusion re-cut).
- Static mounts in `api/main.py` for `/venues`, `/cars`, `/draco` (the catch-all route would answer them with index.html). Engine restart needed after changing that file.
- Verified on 2025 Qatar GP race (OpenF1): 0.012 % of 280,887 car samples over the model's edge, elevation p95 5 cm; 1080p full field on the RTX 3060: 4.2 ms median / 13.1 ms worst per frame (forced GPU finish). Demo: Replay → 2025 Qatar Grand Prix · Race → 3D Broadcast → RUS → TV Pod, seek 0–13 s (VER directly ahead on the grid/launch). Tests: `tests/test_qatar_venue.py`.
- Not done: estimated mode on Lusail not driven in the browser (no Qatar timing recording yet — record the 27–29 Nov 2026 weekend); KTX2 textures (WebP in the GLB instead); kerbs/barriers per corner are reconstructions.

## AI commentator (Live page)
- `services/commentary.py` (`Commentator`), wired in `api/live.py`: each `/api/live/state` poll diffs the state → events (race control, quali fastest/drop zone/Q-part changes, race overtakes/pits/tyres/fastest lap, team radio) → one line per batch, returned as `commentary` in the state. `POST /api/live/commentary {enabled, language: en|sq}`, `GET /api/live/radio/{folder}/{file}.mp3`.
- AI engine order: Claude if `ANTHROPIC_API_KEY` is in `.env` → else **Ollama (free, owner's choice)** `qwen2.5:7b` on the RTX 3060 (~1 s/line, `RACEHYPE_OLLAMA_MODEL`), warmed up on detection → else plain template lines. Ollama is weak in Albanian and occasionally mixes up facts.
- Radio: `TeamRadio` topic → mp3 from livetiming static (works without login; URL-quote the path!) → faster-whisper `small.en` (`RACEHYPE_WHISPER_MODEL`), cached in `outputs/live/radio/<recording>/`. ~2 s per clip on CPU; transcripts of noisy radio are imperfect.
- Voice = **Kokoro** (`kokoro-onnx`, Apache 2.0, safe for monetized streams): `Speaker` writes `outputs/live/voice/line_N.wav`, served by `GET /api/live/voice/...`; model files in `assets/tts/` (gitignored, from the kokoro-onnx GitHub release). Default voice `bm_george` (owner's pick); speed rises with priority + the LLM gets an intensity (HIGH/NORMAL/LOW). A "Crofty-style" rewrite (example lines in the prompt + pitch/volume changes) was tried and REVERTED by the owner: the model copied the example lines ("Norris, Norris has gone purple!") and the voice changed too much. Don't put example lines in the prompt; keep the voice natural. English only; SQ falls back to the browser voice. Tests: `tests/test_commentary.py`.
- **Pacing (keeps it live):** the writer waits until the current line has almost finished playing (`busy_until` from the WAV length), then folds the freshest events (max 15 s old, urgent 30 s, scaled by replay speed) into ONE line and drops the rest; a BUSY hint makes lines ≤16 words; `_drop_repeats` strips clauses the model already said; urgent (prio 5: red flag, new leader, pole) cuts in and the page interrupts. Page keeps at most one waiting line. Measured lag at Mexico race start: 2–7 s.
- **Streaming rules (owner's decision):** panel switch **Team radio: Stream safe / Real radio** (per viewer, localStorage `rhx-comm-radio-mode`, default safe). Stream safe = AI summaries only (low temperature so they stay literal). Real radio = page plays the clip (`GET /api/live/radio/{folder}/{file}.mp3`) before the line and shows ▶ + transcript, with a "Not stream safe" warning. The AI always summarizes, never quotes. No F1 logos; Live page says "Unofficial fan view, not affiliated with Formula 1".

## Data sources (important)
- Since ~15 Oct 2026 F1's archive (livetiming.formula1.com/static) needs an F1 TV login → FastF1 only works for already-cached sessions.
- Fallback: OpenF1 historical (free, non-commercial, ~30 req/min): `services/openf1_comparison.py` (`resolve` matches meeting name first, then venue aliases incl. Abu Dhabi→yas, Saudi→jeddah, Italian→monza). Tests: `tests/test_openf1_fallback.py`.

## Replay page (`pages/Replay.tsx`)
Same UI as Live, fed by the replay engine payload via `GET /api/replays/{token}/data` (added in `api/main.py`). Race order by distance covered; qualifying order by estimated best lap; pit lane drawn from pit-speed samples.

## 3D incident video: `scripts/incident/` (Mexico 2026, lap 1, T4, HAM vs LEC)
- `make_video.py [--preview] [--skip-render] [--no-sound]` → `outputs/incident/mexico2026_t4.mp4` (+ `.sound.mp4`).
- `prepare.py` (OpenF1 CSVs in `outputs/incident/` → `work/prepared.json`), `build_scene.py` + `scenery.py` (Blender, procedural Mexico dressing, car = `assets/3d/cars/qvist/car.blend`, CC BY 4.0), `overlay.py` (captions/HUD, frosted panels), `sound.py` (original synthesized music + SFX; synthetic engines OFF by default — owner disliked them; `--engines` turns them on).
- Everything editable in `mexico2026_t4.json` (shots, captions, `lateral` side-by-side offsets — the feed snaps both cars to one line, so inside/outside comes from race reports).
- Rules: no real footage, no F1/Ferrari/sponsor logos, label it a reconstruction.
- `scripts/fetch_incident.py` fetches the OpenF1 data.

## Other open items
- Footage feature (`services/footage_sync.py`, `api/footage.py`): Windows render "[Errno 32] Broken pipe" never resolved; stderr is now captured — get the real FFmpeg message.
- Publishing the site online is still only a plan: needs a "public mode" first (read-only Live for visitors, password for heavy actions). Hosting options discussed: own PC + Cloudflare Tunnel, or Oracle Cloud Always Free.

## Audit fixes (2026-11-12, from FIX_PROMPT_FULL.md)
- Recordings: `lt.new_recording_path` (seconds + suffix, exclusive create); `record_live.py` appends (`filemode='a'`). Labels/hide in `outputs/live/labels.json` (`POST /api/live/files/label`), files never renamed or deleted. List shows meeting · session from `SessionInfo` (`lt.recording_info`).
- Feed: replay clamps to [start, end], pauses at EOF (`feed.ended`), Play at the end restarts; growing files are exempt. Fastest lap = field minimum (`row['fastest']`, `lt.mark_fastest`), not the leader's.
- Commentary: `run` id (engine run + timeline generation) in `/api/live/state` commentary; page resets speech when it changes. Voice files `line_<run>_<n>.wav`. Lines cleared on source change/seek; stale `_say` results dropped by generation. Radio judged by its own `Utc` (dropped when older than URGENT_AGE × speed). Tags = drivers named in the text. `unsupported()` checks names/positions/incidents/turns against the batch facts → one retry → template line. Prompt unchanged (no example lines).
- Live page: one audio channel (voice + real radio + ▶ Radio); Stream safe cuts a playing clip; text-only when no voice for the language; stale/disconnected banner; actions show errors; circuit fetch ignores stale answers + Try again. Engine-wide controls labelled "applies to the stream".
- Timing fallback: `services/timing_fallback.py` (FastF1 → OpenF1 → own recording via `lt.find_recording`), source shown. Replay fallback: `services/replay_fallback.py` (OpenF1 `location`, speed from positions; gear/throttle/brake/DRS not included), plain error messages.
- Data: `export_service._first_column` matches whole words only (Throttle ≠ time); boolean DRS columns = `drs_active`, codes only for FastF1/OpenF1. `qualifying_part` forced to All outside Q/SQ (frontend + `Selection` validator + `filtered_laps`). OpenF1 rejects Q1/Q2/Q3 instead of returning the wrong lap. Catalogs keep drivers without laps (`status`, shown disabled).
- Library (`api/files.py` PRIVATE_DIRS): no caches, `outputs/live` (voice, radio, recordings), render frames, `render_cache`, `3d_*` work folders; same rule for listing and serving. Paginated (48), lazy video thumbnails, modal traps focus.
- Driver picker: no F1 car renders / formula1.com photos; team-colour silhouette instead.
- Origin check compares Origin with Host (any port) + Vite 5173.
- Tests: `tests/test_audit_fixes.py`. Test engine config: `.claude/launch.json` (port 8001).
- Radio page: clips get their lap by time from OpenF1 lap starts (`radio_service._laps_by_time`), else "Pre-race". Albanian commentary: when both AI tries fail the fact check, the plain fact line is translated (checked again) instead of switching to English.
- OpenF1 + Q1/Q2/Q3 is only refused for "Fastest"; a lap chosen by number works.
- End-to-end checked on a test engine (2026-11-12): Weekend (Q2→Race reset, cached catalog), Video 2D 5 s preview + cancel, Analysis traces/Q2/charts, Telemetry FastF1/OpenF1-Q2 error/CSV checks, Overlay CSV preview + 1 s WebM + outdated note, Footage manual + failed sync + 3 s render, Radio laps/filter/error, Live real radio/Stream safe/SQ text-only, Library dialog, Classic link.
- Not done: frontend has no test runner; the qwen model's Albanian is weak and can credit the leader with someone else's move (the leader may always be named); load-button naming (#43) unchanged; Back leaves the picker because it replaces history entries.

## Backups
Files changed earlier have `*.before-*.bak` copies next to them (e.g. `api/main.before-replay-ui.py.bak`).
