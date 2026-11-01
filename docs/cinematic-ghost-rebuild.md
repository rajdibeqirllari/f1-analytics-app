# Cinematic Ghost Chase rebuild — 26 October 2026

## Diagnosis

The app uses **offline Blender → numbered PNGs → Pillow HUD → raw RGB pipe →
FFmpeg/libx264**, not browser animation capture. React only submits/polls jobs.
No `requestAnimationFrame`, browser screen recorder or wall-clock animation is
in the video export path.

The supplied posted file is 1080×1920 /30 fps /1004 frames /33.483s (including
its audio container). Its tags include `te_is_reencode=1`. The earlier native
720×1280 source is 24 fps /803 frames /33.458s. The old UI forced previews to
24 fps and did not allow 60 fps in 3D; an external 24→30 conversion cannot
create additional scene samples.

Scene-only decoded-frame audit, excluding the timer/HUD and finish holds:

| Input | Moving frames examined | Near-duplicate transitions |
| --- | ---: | ---: |
| Posted 30 fps output, first 30s | 900 | 179/899 =19.91% |
| Earlier native 24 fps source, first 30s | 720 | 0/719 |
| Reference, first 60s, 25 fps | 1500 | 0/1499 |
| New browser-triggered 60 fps test, first 1s | 60 | 0/59 |
| Finished1080p native60fps export, moving portion | 1979 | **0/1978** |

Every detected repeat in the posted file is frame-index **1 modulo 5**. Together
with the native source and re-encode metadata, this strongly identifies a later
24→30 cadence conversion, not a telemetry stall or dropped browser frame.
An additional source-to-export comparison confirms the exact mapping for all
300examined frames: `source_index=floor(export_index×24/30)`. Correct-source
scene MAD is0.309 versus13.630 for neighboring source frames. This confirms
rate conversion of the24fps source, rather than a newly rendered30fps movie.
The specific external editor/encoder responsible is not identified.

`scripts/audit_video_cadence.py` documents the fixed scene ROI, thresholds,
decoded adjacent-frame differences, optical flow and presentation timestamps.
It does not modify the video or count a ticking HUD as scene motion. Small
pixel differences alone are not proof of physical motion: the independent
pose/timestamp audit also checks that source time and both-car poses advance.

## Implementation

- Native 24/30/**60 fps** accepted through UI, API, jobs, Blender and FFmpeg.
  Preview and final use the selected cadence. No output-rate conversion or
  artificial frame interpolation; FFmpeg receives one raw image per timestamp.
- A single explicit `source_times` sequence drives car poses, camera poses,
  wheel animation, ribbon clocks and HUD composition. Constant3×/60fps advances
  exactly0.05 source seconds per moving frame. Both drivers use the same clock.
- Dynamic pacing integrates a positive, smoothed interest density derived from
  actual brake/speed channels, matched-distance gaps and changing advantage.
  The clock is monotone; it never reorders time or alters lap durations.
  Preview clips use the same full-lap pacing curve. Target30–40s includes the
  existing two-second result hold.
- New default **Cinematic Ghost Chase** uses predictive heading/targeting,
  time-based zero-phase critically-damped-equivalent filtering, restrained
  corner following, measured brake/high-speed distance adjustments, local
  anticipatory framing and both-car safe-frame checks. No periodic angle cuts,
  side swaps or decorative camera shake.
- **Classic Broadcast / Overhead** and the legacy Race Hype Cut remain available.
  Existing 2D, chase, cockpit and trackside modes are retained.
- Shape-preserving C1 Hermite route sampling is implemented in NumPy so Blender
  needs no SciPy installation. It stays within0.12m of the existing route
  segments; complete-car asphalt checks remain authoritative. This smooths the
  illustrative route, not the recorded lap times or measured racing data.
- Car/camera Euler rotations are made compatible across angle wrapping.
- Compact signature HUD, data-derived two-second question hook, gaining label,
  shorter fading trails, restrained team-colored ghost rim, existing RH/social
  branding, and a two-second winner/lap-time/gap payoff.
- Existing ready-marker synchronization, streaming PNG disposal, cancellation,
  shadow-overflow rejection and atomic MP4 publication remain in place.

## Confirmed comparison

The brief called this FP1, but the reference's0.179s result is **qualifying**.
The user explicitly selected qualifying for the rebuilt sample:

- ANT: lap14, **1:34.035**.
- VER: lap8, **1:34.214**.
- Antonelli faster by **0.179s**. No outcome was changed.

## Full-lap preflight / motion audit

Full sample configuration:1080×1920,60fps,Balanced24samples,H.264CRF18,
dynamic35-second target,2100frames including result hold.

- 37,800 complete-car asphalt-footprint checks passed.
- Both-car image bounds: x0.1924–0.8827, y0.3803–0.7379 (bottom-origin).
- 1980 advancing source/pose samples; zero nonadvancing source timestamps and
  zero repeated combined car poses in active motion.
- Source increments0.03237–0.06300s/frame are intentional dynamic pacing.

On **identical car poses and output times**, comparing the old Social director
rig with the new rig (not pretending to recover camera transforms from the old
encoded video):

| Metric | Old rig | New rig |
| --- | ---: | ---: |
| Translational jerk,95th percentile (m/output-s³) | 12583.27 | 1331.84 |
| Angular speed,95th percentile (°/output-s) | 92.13 | 65.58 |
| Maximum angular speed (°/output-s) | 132.72 | 73.39 |
| Maximum position step (m/frame) | 5.443 | 5.391 |
| Maximum zoom-factor step | 0.0186 | 0.0323 |

Jerk p95 reduction: **89.42%**. Not every individual metric improves: local zoom
can change more quickly to keep separated cars safely framed. These values
are output-time metrics at accelerated playback, not physical racing forces.

## Finished export verification

- **1080×1920 /60fps /2100frames /35.000s**, H.264,yuv420p,43,008,612bytes.
- All2100frames decode without FFmpeg errors. Moving scene near-duplicates:
  **0/1978adjacent transitions**, first32.98output seconds; result holds excluded.
- Presentation intervals16.666–16.667ms; maximum printed-timestamp cadence
  error0.667µs. No missing or repeated timestamps.
- Zero shadow-buffer overflow warnings. All37,800footprint checks passed.
- Reviewed12consecutive frames around source10s,42s and90s, plus matched-source
  before/after frames throughout the lap. Cars remain on the corridor and
  visible; no obvious camera snaps in the inspected sequences. This does not
  certify that every possible surface-aliasing artifact has been eliminated.
- End card correctly shows ANT1:34.035, VER1:34.214, ANT wins0.179s.
- The standalone browser MP4 player (outside the React application viewer)
  decoded1080×1920, played through35s, reached `ended=true`, `error=null`.
- Full render/encode: approximately29m19s from owned-job directory creation
  through finalized MP4; cached data loading/road preparation precede that.

Main deliverable:
`output/video_studio/2026-ANT-VER-COTA-Qualifying-Cinematic-60fps-20261026.mp4`.
It is an unmodified copy of the completed production render, also available
through My Downloads. No external editor was used to create extra frames.

Audit artifacts: `tmp/smoothness-audit/after-full.json`, `reencode-origin.json`,
`camera-motion.json`, `browser-native60.json`, `overhead-compatibility.json`.
Visual review: `tmp/smoothness-audit/comparison/` contains the three consecutive
corner sheets, a matched-source comparison sheet, final result image, and
`before-after-comparison.mp4`. The comparison movie intentionally plays the old
and new output clocks side by side; source clocks differ because dynamic
pacing differs. Its old panel necessarily repeats frames at the composite's
60fps: **do not use this diagnostic composite as the new export's cadence
proof**. The primary native60fps MP4 above is the audited deliverable.

## Files changed in this rebuild

New runtime modules:
`services/cinematic_timeline.py`, `services/cinematic_camera.py`,
`services/trajectory_spline.py`, `services/cinematic_overlay.py`.

Integrated existing modules:
`services/video_3d.py`, `services/video_3d_overlay.py`,
`services/video_renderer.py`, `services/director_overlay.py`,
`services/car_style.py`, `scripts/render_3d_test.py`, `api/main.py`,
`frontend/src/pages/Videos.tsx` and generated `frontend/dist`.

Audit/proof scripts:
`scripts/audit_video_cadence.py`, `scripts/audit_camera_motion.py`,
`scripts/audit_reencode_origin.py`, `scripts/compare_cinematic_exports.py`,
`scripts/preview_cinematic_ghost.py`.

Tests:
`tests/test_cinematic_pipeline.py`, `tests/test_platform_api.py`,
`tests/test_video_3d.py`, `tests/test_director_overlay.py`,
`tests/test_circuits_3d.py`.

Verification:156tests passed; frontend production build passed. A real
browser-triggered native60fps export completed with correct qualifying lap
metadata and a working download. Its PTS intervals are16.666–16.667ms, with
only0.667µs printed-timestamp rounding error.

## Limits and practical use

True60fps is not a render-speed optimization: it needs2.5× the frames of24fps
at the same playback length. This RTX3060 proof is around0.7–0.8s/frame at
1080p Balanced in simpler sections, with some later frames near1s. Observed GPU
memory use during rendering was about2.2GB of12GB, including desktop usage.
Streaming avoids retaining the entire uncompressed movie in memory/on disk.

The circuit/line/scenery remain illustrative, with accepted telemetry-relative
elevation, not a surveyed replica. Cars remain the licensed modified concept
model, not exact2026 team replicas. Source warnings about OpenF1 completeness,
unavailable channels and non-certified qualifying segments remain visible.
No audio is generated; there is no audio track to desynchronize. No viral
reach, complete flicker elimination or official broadcast fidelity is promised.

Use Race Hype Cut → Cinematic Ghost Chase → Dynamic Cinematic Pacing →35s →
60fps for the default treatment, or Smooth Constant Speed →3× for fixed timing.
Try a short source-time clip before the full export. For social posting, keep
the delivered60fps through subsequent editors; re-encoding a24fps source to
30/60fps brings back repeated frames, and upscaling does not add scene detail.
