# Fix prompt — Race Hype site audit (2026-11-11)

Copy everything below the line into a new Claude session opened in `C:\f1hud_app`.

---

You are working on **Race Hype**, a local F1 fan app (FastAPI engine + React 19/TypeScript/Vite frontend) in
`C:\f1hud_app`. The owner streams it to YouTube/TikTok through OBS. Read `CLAUDE.md` first: it explains how to run
everything, the data sources, and rules you must keep.

A full audit of `http://localhost:8000/hype` was done on 2026-11-11. Fix the issues below, in priority order. For each
one: reproduce it, fix the root cause (not the symptom), test it, then move on.

## Ground rules (do not break these)

1. **Engine restarts:** the engine runs at `http://127.0.0.1:8000` (`.\scripts\start-platform.ps1 -SkipBuild`). Before
   restarting it, check that **no job is running** (`/api/jobs/...` in its log) and that **no live recording is
   running** (`GET /api/live/state` → `recorder.running`). If a recording runs, stop only the uvicorn processes (not
   the `record_live.py` child) so the recording survives. When possible, test backend changes on a second engine:
   `.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8001` (note: browser POSTs from port 8001 are refused by
   the origin check, see issue 13; use PowerShell/curl for POSTs there, or fix issue 13 first).
2. **The Live feed is global state.** Opening/closing a recording changes it for every viewer, including the OBS
   browser source. If you must use the main engine, note its feed (file, mode, position, paused, speed) and the
   commentator settings first, and restore them afterwards.
3. **Streaming/copyright rules:** no F1, team or sponsor logos; no F1-owned photos; the Live page must say it is an
   unofficial fan view. Team radio audio is only played in the opt-in "Real radio" mode; in the default "Stream safe"
   mode the AI only summarizes it. Keep that.
4. **Commentator style was decided by the owner:** keep voice `bm_george`, natural delivery. Do NOT add example lines
   to the AI prompt and do NOT add pitch/volume effects (both were tried and reverted). Keep short numbers (1:31.7, 0.3)
   and the pacing logic described in `CLAUDE.md`.
5. Make `*.before-<change>.bak` copies of files before big edits (project convention). Run
   `.\.venv\Scripts\python.exe -m unittest tests.test_commentary tests.test_live_timing tests.test_openf1_fallback`
   and `npm run build` in `frontend/` before you finish. Do not commit unless asked.
6. Keep the site's look (dark broadcast style, Big Shoulders Display + Barlow, scoped `.rhx` CSS).

## Issues

### High priority (features that fail)

**1. Timing page has no fallback: always fails for recent sessions.**
- Repro: Weekend → São Paulo → Race → Load session (works, via OpenF1) → Timing → Load timing → red error
  "Timing data could not be downloaded … refuses downloads without an F1 TV login".
- Cause: `api/engines.py` `timing()` only uses FastF1 (`session_for(s)` / `session.load`). F1's archive needs a login
  since 15 Oct 2026, so this fails for every session not already cached.
- Fix: add the same fallback chain the rest of the app uses: FastF1 cache → **OpenF1** (`services/openf1_comparison.py`
  / `services/openf1_service.py`: classification, laps, sectors, stints/compound, race control, weather) → and, where
  one exists, the owner's own **live recording** in `outputs/live/*.txt` (parse with `services/live_timing.py`; match
  it by `SessionInfo` meeting name + session type). Show which source was used (the page already has a `source` field).

**2. Replay page fails with a raw programmer error and has no fallback.**
- Repro: São Paulo → Race → Replay → Load replay → error text
  "The data you are trying to access has not been loaded yet. See `Session.load`".
- Fix: (a) never show raw exception text: catch it and show a plain message that says what to do; (b) add a fallback:
  OpenF1 `location` data (positions) for the session, or build the replay from the owner's live recording (mini-sector
  estimated positions, the same as the Live page). Look at the replay engine used by `api/main.py`
  (`/api/replays/...`) and `pages/Replay.tsx`.

**3. The commentator voice stops after an engine restart (until the page is reloaded).**
- Cause: `services/commentary.py` numbers lines from 1 again after a restart (`self.next_id`), but
  `frontend/src/hype/pages/Live.tsx` `useVoice` only speaks lines whose id is greater than the highest id it has seen
  (`spoken.current`). After a restart every new id is lower, so nothing is spoken. This hits the OBS browser source,
  which stays open for hours.
- Fix: give each engine run an id (e.g. a random `run` token or start timestamp returned in `commentary`) and reset
  `spoken.current` in the page when it changes; or make line ids globally unique (timestamp-based). Voice files
  `line_N.wav` must not collide across runs either.

**4. Radio lines can be spoken long after the clip aired (backlog).**
- Cause: in `services/commentary.py` `_radio()`, the radio event is stamped with the feed clock **after** download +
  transcription (`self.clock`), and `_radio_worker` processes every queued clip in order. At replay speeds above 1×
  (or when several clips arrive at once) the queue grows, and stale clips are later announced as if they were fresh,
  defeating the "max 15 s old" rule.
- Fix: keep the clip's real air time (`Utc` from the TeamRadio capture) and drop clips whose air time is older than
  `URGENT_AGE * speed` relative to the feed clock, both before downloading and before queueing the event. Skip the
  download/transcription entirely for clips that are already too old.

**5. Library page lists internal files.**
- Repro: Library shows ~1,500 items, mostly OpenF1 cache JSON (hash names), commentator voice clips (`line_N.wav`),
  downloaded team radio (`*.mp3`) and transcripts (`*.mp3.json`).
- Fix: exclude `outputs/openf1_cache/`, `outputs/live/voice/`, `outputs/live/radio/` (and any other cache folders) from
  the Library listing. The downloaded radio is F1-owned audio and must not appear as the owner's work.

### Medium priority (wrong or confusing)

**6. F1-owned images and sponsor logos in the driver picker.**
- The "Pick the duel" cards (`frontend/src/hype/DriverDuel.tsx`) show car renders from `/art/f1_2026/*.png` with real
  team liveries and sponsor logos (e.g. "ORACLE" on the Red Bull), and load driver photos straight from
  `media.formula1.com` (hidden by CSS when a car image exists, but still requested). Both clash with rule 3.
- Fix: stop hotlinking formula1.com photos (remove the request, not just hide it). Replace the car renders with
  logo-free art (e.g. a neutral silhouette tinted in the team colour) or make them opt-in with a clear "not for
  streaming" note. Check other pages (Video/Overlay outputs) for the same assets.

**7. Every tool page starts on round 1 (Australian GP).**
- Repro: open `/hype` or any tool page fresh: "2026 Australian, Qualifying, Not loaded", 249 days ago. The Live page
  URL even gets `?event=Australian+Grand+Prix…` appended.
- Fix: default to the most recent completed round (today: São Paulo) or the next one if a session is within a few
  days; keep the user's last choice if they made one.

**8. Commentator controls: some are global, some per viewer.**
- "On/Off", "EN/SQ" and the Kokoro voice choice are saved on the engine (`POST /api/live/commentary`), so changing them
  in any browser also changes the OBS stream. "Voice" and "Team radio" mode are per browser (localStorage).
- Fix: make it explicit and safe: label the engine-wide settings as such (e.g. "Applies to the stream"), or move
  language/voice to per-viewer and have the engine generate audio for the stream's settings only. At minimum, show the
  OBS user which settings affect the stream.

**9. Commentator driver tags don't match the sentence.**
- Each line is tagged with every driver from all events in its batch, including events the AI didn't mention (e.g.
  "Leclerc past Sainz…" tagged ALB, LEC, PIA, SAI, VER).
- Fix: tag only drivers whose surname/code appears in the final text (fall back to the lead event's drivers).

**10. The AI sometimes states things the data didn't say.**
- Seen in a race replay: "false starts for Verstappen and Albon!", "Hamilton in trouble at turn 5". Verify against
  the race-control messages of that batch; if a line contains claims not supported by the event facts, regenerate once
  or fall back to the plain template line. Keep the existing "use only the facts given" rule; no example lines.

**11. Live page start screen always says "Watch qualifying live".**
- `Live.tsx` (`Sources`, `<h2>Watch qualifying live</h2>`) is hard-coded. Use the next/current session from the
  calendar ("Watch the race live", "Watch FP2 live"…), or a neutral "Watch a session live".

**12. Recordings list is hard to use.**
- It shows only file names like `live_2026-11-08_1804.txt`. Read the `SessionInfo` from each file (meeting + session
  name) and show "São Paulo GP · Race, 8 Nov 18:04" with the size. Add rename/delete (with a confirm) for empty or
  test recordings (there are several 0.1–0.3 MB files).

**13. Origin check hard-codes ports.**
- `api/main.py` `local_origin` only accepts `localhost/127.0.0.1` on ports 8000 and 5173, so the app refuses its own
  interface on any other port ("This local app accepts changes from its own interface only."). Compare the request's
  `Origin` host:port with the request's own `Host` header instead (still rejecting foreign origins).

**14. Team radio page details.**
- Lap column shows "—" for every clip, and the first clips of the race all show 00:00:00 (pre-race clips). Show the lap
  (from laps/timing data by clip time) and label pre-session clips "Pre-race". The page could also show the
  transcripts the commentator already creates (`outputs/live/radio/**/**.mp3.json`).

**15. Missing driver in OpenF1 sessions.**
- "21 drivers ready from OpenF1" for the São Paulo race: BOT (retired on lap 1, no timed lap) is missing from the duel
  grid. Include drivers without timed laps in the list (disabled or marked DNF) so the grid shows all 22.

### Low priority (polish)

**16. Phone layout (375 px wide):** the top menu scrolls sideways with no visual hint, so Radio and Library are
hidden off-screen; add a fade/arrow or wrap to two rows. The Live timing table scrolls sideways and hides the Tyre
column; on phones hide Best/Last instead and keep Pos, Driver, Gap, Tyre.

**17. Weekend page:** the big headline drops accents ("SAO PAULO") while other pages show "SÃO PAULO": be consistent.
The year odometer puts 40 digits (0–9 ×4) into the page text, so screen readers read them; mark the reel
`aria-hidden` and give the year a proper label.

**18. Button naming:** tool pages use "Load session", "Load timing", "Load replay", "Find team radio" for the same kind
of action; harmless, but consider one consistent pattern.

## Not tested in the audit (check these too)

- Rendering in Video, Overlay and Telemetry export (only page loads were checked).
- "Go live" (starting a new recording) and "Follow live" during a real session.
- "Real radio" mode audio playback inside the OBS browser source; Albanian (SQ) commentary.
- Footage feature broken pipe (open item in `CLAUDE.md`).

## Done means

- Issues 1–5 fixed and verified in the browser on the São Paulo race (Timing shows a classification; Replay plays or
  explains clearly; voice keeps speaking after an engine restart without reloading the page; no stale radio lines at
  5× replay; Library shows only real outputs).
- As many of 6–18 as possible fixed; list anything you skipped and why.
- Tests and `npm run build` pass; `CLAUDE.md` updated with what changed; nothing committed unless the owner asks.
