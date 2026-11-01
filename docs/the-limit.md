# THE LIMIT — RACE HYPE time sculpture

Select **Race Hype Cut → Story / camera style → The Limit**, then render.
The 3.2-second opening is additional to the configured action/result duration.
A 35-second dynamic full lap therefore exports at 38.2 seconds. Available in
portrait/landscape and the existing preview/final resolutions and cadences.

## Implemented

- Perspective-projected, animated circuit-shaped time canyon in a dark analytical
  studio. Uses the actual private driving route supplied to Blender.
- Signed ridge height equals matched-distance elapsed-time advantage. Cyan/blue
  (selected session team colors) identifies which driver has the advantage.
  Height is normalized/exaggerated and explicitly labelled **not track elevation**.
- Immediate gap hook, travelling spark, perspective push-in and dissolve into
  the existing native-3D cinematic replay. This is an editorial transition, not
  one continuous Blender camera shot through a physical canyon on the circuit.
- Up to three non-overlapping strongest timing swings over windows spanning
  6% of lap distance. Callouts report the measured swing, not an invented
  corner name, physical cause or guaranteed recoverable time. Cues start at
  section entry and remain for 1.65 output seconds regardless of playback speed
  (unless the exact finish interrupts them).
- Exact result card followed by the sculpture payoff, RH logo, handle and
  YouTube/Instagram/TikTok follow labels.
- Intro is an added shared-clock hold: **no lap action is skipped**, and both
  cars, telemetry and surface trails keep their original shared source clock.
- All existing replay accuracy disclosures remain: illustrative shared racing
  line, estimated grade, concept cars. No new surveyed data or vehicle physics.

This first version does not add physical speed-gate geometry, debris/time
particles or a continuous 3D morph. These are possible later refinements, not
features claimed in this release. No soundtrack has been added.

## Verification

- Full frontend build passed.
- Final regression suite: **169 tests passed**. Complete final MP4 decoded
  successfully with FFmpeg, and native in-app browser playback reported 38.2s,
  ready state 4, playing, with no media error.
- Unit tests cover source-clock preservation, exact matched-distance canyon
  data and gain beats, invalid inputs, portrait/landscape composition, winner
  labels, HTTP acceptance and job-queue validation.
- New production-path short sample: 540×960, native 60fps, 472 frames, 7.8667s
  including intro. Blender: 100% drivable coverage, 8,496 footprint checks pass;
  camera safe frame x=.214–.842, y=.387–.689.
- Complete sample: `output/video_studio/2026-ANT-VER-COTA-THE-LIMIT-60fps.mp4`,
  540×960, 60fps, 2,292 frames, 38.2s. Uses the previously verified v30
  surface-locked cinematic replay plus new editorial graphics. The proof tool
  verifies its dimensions, cadence and frame count against the original render
  config, and verifies the selected cached lap numbers/times.
- Source: COTA 2026 qualifying, ANT lap 14 1:34.035 / VER lap 8 1:34.214.
  Finish gap is unchanged at 0.179s.

## Reproduce

New Blender render through the normal production pipeline:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_cinematic_ghost --the-limit --end 12 --quality Fast --output tmp/the-limit/proof
```

Re-edit the verified completed full replay without another Blender render:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_the_limit --config tmp/trail-alignment/after/config.json --video output/video_studio/2026-ANT-VER-COTA-Surface-Locked-Trail-540p-60fps.mp4 --output output/video_studio/2026-ANT-VER-COTA-THE-LIMIT-60fps.mp4
```

The replay-reuse command is a local proof tool, not an automatic website cache
shortcut. Normal site jobs use the standard render/cache pipeline.
