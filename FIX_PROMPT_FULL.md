# Full fix prompt — Race Hype (merged audit, 2026-11-11)

Merges the Claude Code audit (`FIX_PROMPT.md`) with the ChatGPT audit, after checking every ChatGPT claim against the
code. Copy everything below the line into a new Claude session opened in `C:\f1hud_app`.

---

Audit and fix **Race Hype** in `C:\f1hud_app`, starting at `http://localhost:8000/hype/live`.

Read `CLAUDE.md` first. Preserve the existing dark broadcast design (Big Shoulders Display + Barlow, scoped `.rhx`
CSS) and all unrelated working-tree changes. Fix the app, not just the wording. Work through every menu: Weekend,
Live, Replay, Video, Overlay (including "Add it to your clip"), Analysis, Timing, Telemetry, Radio, Library, and the
Classic workspace link.

Two earlier audits found the issues below. Each one is tagged with how it was confirmed:
- **[Browser]**: seen in the running app.
- **[Code]**: confirmed by reading the code (deterministic).
- **[Ran]**: confirmed by running the code on a small test input.
- **[Needs E2E]**: plausible from the code, but must be reproduced end to end first.

Reproduce each issue before changing it. Do not dismiss a code-confirmed problem just because existing tests pass:
the existing live/commentary suites pass and do not cover these defects.

## Operational constraints

1. **Never restart the engine while a job is running.** Check first (`/api/jobs/...` activity in the engine log). Also
   check `GET /api/live/state` → `recorder.running`. If a live recording is running, stop only the uvicorn processes
   (`Get-CimInstance Win32_Process` → command line contains `uvicorn ... --port 8000`), never the `record_live.py`
   child, so the recording survives.
2. **The Live feed is global engine state.** Opening/closing/seeking a recording and the commentator's On/Off,
   language and voice change it for every viewer, including the owner's OBS browser source. Prefer a second engine for
   tests: `.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8001` (browser POSTs from port 8001 are refused
   until issue 30 is fixed; use PowerShell/curl for POSTs there). If you must use port 8000, save the feed (file,
   mode, position, paused, speed) and the commentary settings first and restore them exactly afterwards.
3. **Do not delete existing outputs, recordings, caches or uploads.** Use isolated fixtures (temp folders, copies of
   small recordings) for tests.
4. **Do not launch costly full renders or overwrite existing media.** Use short previews and isolated output paths.
5. **Keep the owner's decisions in `CLAUDE.md`:**
   - Commentator voice `bm_george`, natural delivery, short numbers (1:31.7, 0.3), and the pacing logic.
   - Do NOT add example lines to the AI prompt and do NOT add pitch/volume effects (both were tried and reverted).
   - Team radio: "Stream safe" (default) = AI summary only. "Real radio" = opt-in clip playback, with a warning.
   - No F1, team or sponsor logos, no F1-owned photos, and keep the "Unofficial fan view" labels.
   - Bundled circuits live in `frontend/src/hype/circuits/` (Mexico, São Paulo).
6. Do not rewrite the app or change its visual identity. Make `*.before-<change>.bak` copies before big edits (project
   convention). Do not commit unless the owner asks.

## Priority 1: data loss, wrong data, stuck workflows

**1. Recordings can overwrite each other. [Code]**
`api/live.py:89` names recordings `live_YYYY-MM-DD_HHMM.txt` (minute precision), and `scripts/record_live.py:83` calls
FastF1's `SignalRClient(out, …)`, whose default `filemode='w'` truncates. Start → stop → start within the same minute
wipes the first recording. Fix: unique names (seconds plus a suffix if the file exists), and exclusive creation (open
with `'x'`/append, never truncate). Test two starts in the same minute with a fake recorder in a temp folder.

**2. A job-polling error can permanently disable action buttons. [Code]**
`frontend/src/state.tsx` `useTask`: the poll `catch` sets `error` and `setId(null)`, but keeps the old `job` with
`status:'running'`. `busy` stays true and `cancel()` has no id anymore. Fix: retry with backoff on network errors,
and on a real failure move to a consistent terminal error state (clear or mark the job) so buttons work again.

**3. The qualifying filter leaks into Race/Practice. [Code]**
`frontend/src/hype/pages/Picker.tsx:33,46,47,102`: changing event, year or session clears drivers/laps but not
`qualifying_part`. `services/video_comparison.py:124` `filtered_laps` splits by Q1/Q2/Q3 whenever
`qualifying_part != 'All'`, even for a race. Fix: reset `qualifying_part` to `All` on every event/year/session change
and whenever the session isn't qualifying, and enforce it on the backend (`api/main.py` selection model or
`filtered_laps`). Test Q2 → Race → load → traces, video preview and telemetry export.

**4. Returning to a cached weekend can leave drivers blank. [Needs E2E]**
`state.tsx` reconciles driver selection only when `catalogJob.result` changes (lines 59–65). Going back to a cached
catalog (A → B → A, or browser Back) uses `catalogs[signature]` without reconciling, while the picker has already
cleared the drivers. Fix: reconcile against the active catalog, whether it came from a job or the cache. Test
A → B → A, including browser history.

**5. CSV import treats Throttle as time. [Ran]**
A CSV with `Throttle, Speed` and no time column was accepted: `services/export_service.py` `normalize_telemetry` and
`services/hud_renderer.py` both turned throttle values `[10, 50, 100]` into time `[0, 40, 90]`. Cause:
`_first_column(...)` fuzzy-matches the alias `t` to `Throttle`. Fix: exact/whole-word matching for time columns,
require an unambiguous time column or an explicit mapping, and reject the file with a clear message otherwise.

**6. CSV DRS booleans are read as DRS codes. [Ran]**
`normalize_telemetry` with a `drs_active` (or `DRS`) column of real booleans `True/False` gives `drs_raw=[1,0]`,
`drs_active=[False,False]`, because the boolean becomes raw code 1, which isn't an "active" DRS code. The string
`"true"` happens to work. A CSV exported by the app (`DRS` boolean column) and re-imported therefore loses DRS. Fix:
treat boolean/boolean-like columns as `drs_active` directly, and only apply the numeric DRS code table (10/12/14…) to
`drs_raw`. Test true/false, "true"/"false", 0/1, the numeric codes, and an export → import round trip.

**7. OpenF1 ignores the Q1/Q2/Q3 choice. [Code]**
`services/openf1_service.py:159` `load_openf1_lap(year, event, session, driver, lap_mode, lap_number)` has no
`qualifying_part` parameter, and `api/engines.py:127` doesn't pass one. With OpenF1 as the source, "Q1 + Fastest"
silently returns the whole-session fastest lap. Fix: apply the segment (split laps by session-part start times from
OpenF1 `race_control`/`sessions` data, as `openf1_comparison.py:167` already does for comparisons), or reject the
combination with a clear message. Never silently change the selected lap.

**8. Timing page fails for recent sessions; it has no fallback. [Browser]**
Weekend → São Paulo → Race → Load session works (via OpenF1), but Timing → Load timing shows "Timing data could not be
downloaded … refuses downloads without an F1 TV login". `api/engines.py:63` `timing()` only uses FastF1. Fix: add the
app's fallback chain: FastF1 cache → OpenF1 (classification, laps, sectors, stints, race control, weather) → the
owner's own live recording in `outputs/live/*.txt` (parse with `services/live_timing.py`, match by `SessionInfo`
meeting + session type). Show the source used.

**9. Replay page fails with a raw programmer error; it has no fallback. [Browser]**
São Paulo → Race → Replay → Load replay shows "The data you are trying to access has not been loaded yet. See
`Session.load`". Fix: never show raw exception text; show a plain message with what to do. Add a fallback: OpenF1
`location` positions, or a replay built from the owner's live recording (mini-sector estimated positions, as on the
Live page). See `services/replay_service.py`, `/api/replays/...` in `api/main.py` and `pages/Replay.tsx`.

**10. Every page defaults to round 1 (Australian GP). [Browser + Code]**
`state.tsx:57` falls back to `schedule.value[0]` when the event is empty or unknown, so a fresh visit shows "2026
Australian, Qualifying, 249 days ago", and the Live page URL gets `?event=Australian+Grand+Prix…`. Fix: default to
the most recent completed round (or the next one if a session is within a few days); keep the user's last valid
choice.

## Priority 2: Live, commentary, Replay

**11. The Live "fastest lap" highlight uses the leader's best, not the field's best. [Code + recordings]**
`Live.tsx` (timing tower, `lead?.best===r.best`). Confirmed with saved recordings: Mexico
`live_2026-11-01_2102.txt` (VER 1:19.328 highlighted, HAM 1:19.268 is faster); Brazil `live_2026-11-08_1804.txt`
(NOR 1:12.983 vs ANT 1:12.689). Fix: highlight the minimum valid best across the field (the feed's `OverallFastest`
flag where present), handling missing/invalid times and ties.

**12. Recorded playback runs past the end of the file. [Code]**
`services/live_timing.py` `Feed.clock()`/`seek()` have no upper bound, and `paused` stays false at the end. Fix: clamp
seek and clock to [start, end], stop (pause) at EOF, and make "play from the end" restart predictably. Don't apply EOF
rules to a recording that is still growing (follow mode).

**13. Live failures are hidden or swallowed. [Code]**
`Live.tsx` shows the polling error only when no feed is open, so an open feed can freeze with no warning. `open` and
`record` use `try/finally` with no `catch` (unhandled rejections), and `control`/commentary settings use
`.catch(()=>{})`. Fix: show a stale/disconnected banner and actionable errors even when old data is on screen; add
pending and retry states; never present stale data as current.

**14. The commentator voice stops after an engine restart until the page is reloaded. [Code]**
`services/commentary.py` restarts line ids at 1 (`self.next_id`) on every engine start, while `Live.tsx` `useVoice`
only speaks ids greater than the highest it has seen (`spoken.current`). The OBS browser source stays open for hours,
so this silences the stream. Voice files `line_N.wav` also collide across runs. Fix: add an engine-run/source
generation id to `commentary` and reset the page's speech state when it changes, or use globally unique line ids and
file names.

**15. Commentary survives source changes and seeks. [Code]**
`Commentator.reset()` keeps the old recording's lines (`lines.clear()` only when `file is None`), and an in-flight
`_say()` (AI + voice, ~2 s) can append a line from the old recording or the pre-seek timeline. Fix: stamp work with a
source/timeline generation id, drop results whose generation is stale, clear (or clearly separate) history on a
source change, and reset queued speech/audio in the page. Test Mexico → Brazil, and forward/backward seeks while a
line is being generated.

**16. Radio lines can be spoken long after the clip aired. [Code]**
`commentary.py` `_radio()` stamps the radio event with the feed clock after download + transcription, and
`_radio_worker` works through every queued clip in order. At replay speeds above 1×, or when clips bunch up, stale
clips are later announced as fresh, which defeats the 15 s freshness rule. Fix: keep each capture's real `Utc` time,
and drop clips older than `URGENT_AGE × speed` relative to the feed clock, both before downloading and before queueing.

**17. "Stream safe" does not stop real radio that is already playing. [Code]**
`Live.tsx` `pickRadio(false)` only updates state, so a clip that is playing keeps going while the UI says "Stream
safe". Fix: stop any real-radio audio immediately when entering Stream safe. This matters for streaming.

**18. Manual radio playback is unmanaged. [Code]**
The ▶ Radio button creates a new `Audio` on every click (`play(url)`), so clips overlap, and Voice off, Stream safe
and leaving the page don't stop them. Fix: one managed playback controller shared by the voice queue and manual
playback, cleaned up on every transition and on unmount.

**19. Albanian text-only fallback still speaks in a default voice. [Code]**
When no `sq` voice exists, the panel says text only, but `useVoice`'s browser fallback still builds an utterance with
the default (English) voice. Fix: honour text-only mode, and report accurately whether audio is available.

**20. Live circuit requests can race and never retry. [Code]**
`Live.tsx` sets `asked.current=trackKey` before requesting `/api/live/track`, and the response isn't checked against
the current key. A slow response for the previous circuit can overwrite the new one, and a failed key is never
retried. Fix: abort/ignore responses for a stale key, and allow retry (button or backoff) after failure.

**21. Opening Replay settings resets playback. [Code]**
`Replay.tsx:220` returns `<Player>` only when `!settings`, so opening settings unmounts it and Back remounts it:
position, speed and focused driver are lost. Fix: keep the player mounted (hide it, or show settings beside it).

**22. Replay keyboard controls interfere with other controls. [Code]**
`Replay.tsx:131`: the Space handler only skips non-range `<input>`s, so Space on a focused button, select or textarea
also toggles playback (a focused Play button toggles twice). End-of-replay handling also differs from the Play
button. Fix: skip buttons, selects, textareas, contenteditable and modified keys; share one play/pause function that
handles EOF the same way.

**23. Replay doesn't strip accents from circuit names (São Paulo). [Code]**
`Replay.tsx:10` `slug()` lacks the accent removal `Live.tsx` has, so the bundled `sao-paulo-grand-prix.json` rotation
is missed. Fix: one shared slug helper (frontend), matching `services/live_timing.py` `track_outline`; test accented
names.

**24. Commentator controls: some reach the stream, others are per browser. [Code]**
On/Off, EN/SQ and the Kokoro voice are saved on the engine (`POST /api/live/commentary`), so changing them in any
browser changes the OBS stream. Voice and Team radio mode are per browser (localStorage). Fix: label engine-wide
settings clearly ("Applies to the stream"), or move language/voice to per viewer.

**25. Commentator driver tags don't match the sentence. [Browser]**
Lines are tagged with every driver from the whole event batch, including events the AI left out (e.g. "Leclerc past
Sainz…" tagged ALB, LEC, PIA, SAI, VER). Fix: tag only drivers named in the final text, falling back to the lead
event's drivers.

**26. The AI sometimes states things the data didn't say. [Browser]**
Seen in the Brazil race replay: "false starts for Verstappen and Albon!", "Hamilton in trouble at turn 5". Fix: check
each line's driver names, positions and incident words against that batch's facts; if unsupported, regenerate once
or use the plain template line. Keep "use only the facts given"; no example lines.

## Priority 2: Overlays, footage, Library, images

**27. Overlay "Custom" canvas is a dead control. [Browser, ChatGPT audit; Code]**
Overlay → Your CSV → Canvas → Custom keeps 9:16 selected and never shows Width/Height. `Overlays.tsx:18` derives the
preset only from the dimensions, and `onChange` (line 36) ignores `custom`. Fix: explicit custom-mode state; keep
Width/Height editable even when the values match a preset.

**28. Manual footage sync is unreachable after auto-sync fails. [Code]**
`Footage.tsx:105` shows the manual controls only when a sync result exists or the clip has no audio. A clip with audio
that can't be matched (short, noisy) has no manual fallback. Fix: always offer manual sync.

**29. Footage sync survives a qualifying-segment change. [Code]**
`Footage.tsx:78` resets sync on clip/year/event/session/driver/lap/source, but not `qualifying_part`. Q1 → Q2 with
"Fastest" reuses the old offset on a different lap. Fix: invalidate on any change to the telemetry identity.

**30. The origin check hard-codes ports. [Browser + Code]**
`api/main.py:62` `local_origin` only accepts localhost/127.0.0.1 on ports 8000 and 5173 ("This local app accepts
changes from its own interface only." on other ports). Fix: compare the `Origin` host:port with the request's own
`Host`, still rejecting foreign origins.

**31. Library exposes internal files. [Browser + Code]**
`/api/files` (`api/files.py`) returns ~1,500 entries: hashed `outputs/openf1_cache/*.json`, commentator voice
`outputs/live/voice/line_N.wav`, and downloaded team radio `outputs/live/radio/**.mp3` + transcripts, which is F1-owned
audio. Meanwhile `Library.tsx:31` claims "source models and caches stay private". Fix: list only deliberate user
deliverables, and apply the same policy to listing and file serving. Do not delete the internal files.

**32. Library renders every preview at once. [Code]**
`Library.tsx:27` maps every file and creates `<video preload="metadata">` for hundreds of videos. Fix: pagination or
virtualization, and load media only when visible/opened. Verify with the existing large library.

**33. Library modal accessibility. [Needs E2E]**
Check: focus is trapped while open, Escape closes, background can't be focused, focus returns to the card. Check the
image/audio/video previews and the "download to open" fallback (e.g. `.mov`).

**34. F1-owned images and sponsor logos in the driver picker. [Browser]**
"Pick the duel" (`frontend/src/hype/DriverDuel.tsx`) shows car renders from `/art/f1_2026/*.png` with real liveries
and sponsor logos (e.g. "ORACLE" on the Red Bull), and requests driver photos from `media.formula1.com` (hidden by CSS
when a car image exists, but still fetched). Fix: stop hotlinking formula1.com (remove the request, not just hide
it); replace the car renders with logo-free art (e.g. a team-colour silhouette) or make them opt-in with a "not for
streaming" note. Check Video/Overlay outputs for the same assets.

## Priority 3: shared controls and polish

**35. Mobile navigation loses its accessible names, and items hide off-screen. [Browser + Code]**
At ≤760 px, `kit.css:357` hides the nav labels with `display:none` (which removes them from the accessibility tree)
while the icons are decorative. The nav also scrolls sideways with no hint, so Radio and Library are off-screen at
375 px. Fix: `aria-label` on every link, visually-hidden labels instead of `display:none`, clear active/focus states,
and a scroll hint or two-row wrap.

**36. Choice group labels with spaces break `aria-labelledby`. [Code]**
`kit.tsx:55–56` builds `id={'l-'+label}`, so "Data source" or "Frame rate" give IDs with spaces, which
`aria-labelledby` reads as two IDs. Fix: `useId()`.

**37. Choice keyboard edge cases. [Code]**
`kit.tsx:52–54`: with no enabled options, `live[...]` is undefined and `next.value` throws. With no current selection
(`i=-1`), arrows jump oddly. Fix: guard both, and keep roving-tabindex behaviour sensible.

**38. Old results shown as if they match new settings. [Needs E2E]**
Changing session, driver, lap, qualifying segment, source, frame rate, canvas or other render settings must not leave
an old preview/result looking current (#29 is one confirmed case). Invalidate results, or label the exact settings
used.

**39. Misleading states and copy. [Browser + Code]**
- The Live page shows "No recordings yet" before the list has loaded (`files` starts as `[]`).
- "Watch qualifying live" is hard-coded (`Live.tsx` `Sources`); use the current/next session or a neutral title.
- Show distinct loading, empty, error, stale and ready states.

**40. The recordings list is hard to use. [Browser]**
It shows only file names like `live_2026-11-08_1804.txt`. Read each file's `SessionInfo` and show "São Paulo GP ·
Race, 8 Nov 18:04" with its size. Add rename and hide. Deleting must only happen on the owner's explicit, confirmed
click; never delete recordings as part of testing.

**41. Team radio page details. [Browser]**
The lap column is "—" for every clip, and pre-race clips all show 00:00:00. Show the lap (matched by time) and label
pre-session clips "Pre-race". Optionally show the transcripts the commentator already creates
(`outputs/live/radio/**/*.mp3.json`).

**42. A driver is missing from OpenF1 sessions. [Browser]**
"21 drivers ready from OpenF1" for the São Paulo race: BOT (retired on lap 1, no timed lap) is missing from the duel
grid. Include drivers without timed laps (disabled, or marked DNF).

**43. Weekend page polish. [Browser]**
- The headline drops accents ("SAO PAULO") while other pages show "SÃO PAULO".
- The year odometer puts 40 digits (0–9 ×4) into the page text, which screen readers read out. Mark the reel
  `aria-hidden` and give the year a proper label.
- Load buttons are named inconsistently ("Load session", "Load timing", "Load replay", "Find team radio"); consider one
  pattern.

## End-to-end verification required

Do not claim any of these were already tested. Exercise them after the fixes, on the built app served at
`http://localhost:8000` (not only the dev server):

- **Everywhere:** every navigation item, sub-mode, button, selector, disclosure, dialog and back action, plus the
  Classic workspace link.
- **Weekend:** year/event/session switching; cached and uncached sessions; future sessions; Q1/Q2/Q3; driver/lap
  selections; browser Back/Forward.
- **Live (saved recordings):** pause/play, every speed, scrubbing both ways, EOF, focused driver, circuit map
  (Mexico, São Paulo), commentary on/off, EN/SQ, voice, Stream safe / Real radio, engine restart with the page open.
- **Replay:** load, settings/back, keyboard, focus, speeds, cache controls with isolated test data.
- **Video:** styles/cameras, duration, audio, quality, preview, cancel, failed job, short export.
- **Overlay:** presets and custom size, drag/keyboard HUD placement, preview, each export format, CSV mode, "Add it to
  your clip" (footage: failed auto-sync → manual fallback, alignment preview, short export).
- **Analysis:** traces, charts, strategy; changing drivers and sessions.
- **Timing:** classification, driver details, sectors, weather/race control, missing data, the new fallbacks.
- **Telemetry:** all sources and export formats; CSV validation and data correctness (#5, #6).
- **Radio:** find, filter, play, download; empty and upstream-failure states.
- **Library:** search, categories, refresh, media dialogs, downloads, large-library behaviour.
- **Cross-cutting:** desktop and 375 px widths, keyboard-only use, console errors, network failures, backend
  unavailable, page refresh, browser history.

## Tests and checks

- Add focused regression tests for:
  - Data loss: #1.
  - State transitions: #2, #3, #4, #12, #14, #15.
  - Data interpretation: #5, #6, #7, #11.
  - Races and freshness: #16, #20.
  - Error recovery: #2, #13.
- Run `npx tsc --noEmit` (or the project's TypeScript check) and `npm run build` in `frontend/`.
- Run the Python tests:
  `.\.venv\Scripts\python.exe -m unittest tests.test_commentary tests.test_live_timing tests.test_openf1_fallback`
  plus any new ones.
- Verify on the built app at port 8000 (Ctrl+F5 after building; restart the engine only following constraint 1).

## Deliver

1. Fixes grouped by severity.
2. For each confirmed issue: how you reproduced it and which test now covers it.
3. A menu-by-menu matrix (Weekend, Live, Replay, Video, Overlay, Footage, Analysis, Timing, Telemetry, Radio,
   Library, Classic): pass / fail / blocked, with notes.
4. Remaining issues, each with a concrete blocker.
5. The exact commands and checks you ran, with their results.
6. `CLAUDE.md` updated with what changed.

Do not claim "everything works" unless that workflow was actually exercised.
