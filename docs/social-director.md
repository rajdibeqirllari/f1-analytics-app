# RACE HYPE Cut

New video mode: `Create Comparison Videos` → `Race Hype Cut`.
Internal camera: `Social director`. Existing modes remain available.

## Implemented

- Deterministic changing three-quarter, lateral tracking and aerial camera
  angles, eased orbital transitions and complete-car safe-frame validation.
  Corner anticipation and bounded heading swings improve tracking; angle
  changes slow down during rapid turns and maintain their orbital distance.
- Original RH timer / matched-distance leader gap / live gap history with real
  sector markers when available / map / speed / gear / throttle / brake rows.
- Existing user RH logo and FOLLOW US ON social graphic. No borrowed creator
  branding, official F1 logos or copied timing graphics.
- 1×, 2×, 3×, 5×, 8×, 10×, 20× direct generation in both 2D and 3D. Accelerated
  output samples fewer frames; output FPS remains selected, displayed clocks
  use source lap time, and full-lap result hold remains two output seconds.
- Smoothed relative telemetry elevation where valid. Road, attached terrain,
  daytime scenery and night assemblies share a height baseline. Unreliable,
  drifting, spiky or unrepresentable profiles explicitly fall back flat.
- Controlled paint/clear-coat, carbon, tyre and rim finish refinements on the
  existing licensed Qvist concept car. No exact car geometry claim.

## Verification

- 147 tests passed; frontend production build completed.
- Refined camera / 3× proof: real cached Austin FP1 source0–20s becomes
  160frames /6.667s at540x960/24fps/Fast. Native complete-car safe-frame and
  asphalt footprint checks passed; zero shadow-buffer overflow warnings.
  Preview: `tmp/social-director/race-hype-cut-3x.mp4`.
- Updated website end-to-end proof: Race Hype Cut /3× /540p Balanced,
  Austin FP1 ANT/VER,10source seconds became3.333output seconds and reached
  Completed with a download link. Screenshot: `tmp/social-director/website-3x-verified.png`.
- Real cached Austin 2026 FP1 LEC/VER proof: source0–20s at5× =96frames/4s,
  source0–20s at2× =240frames/10s, both540x960/24fps/Fast.
- Native Blender safe-frame and complete asphalt footprint checks passed;
  zero shadow-buffer overflow warnings in previews.
- Austin accepted telemetry height range ~30.10m, explicitly not surveyed.
- Native geometry-only day/night regression scenes at Spa and Singapore passed.
- Scene previews: `tmp/social-director/race-hype-cut-2x.mp4` and `...-5x.mp4`.
- Production website UI verification completed: selected Race Hype Cut, loaded
  real Austin FP1 session, selected5×, generated10source seconds as2output
  seconds at540p Balanced. Player reached completed state, download available,
  completed speed correctlyshown5× and lap12 results96.052/96.136 retained.
  Screenshot: `tmp/social-director/website-verified.png`.
- The ten-second2× multi-angle demo was copied to My Downloads as
  `2026_LEC_VER_RaceHypeCut_2x_demo.mp4`.

## Limits

Telemetry is not a surveyed centerline/heightmap. Widths, kerbs, terrain away
from the track, furniture and racing line remain illustrative; no banking is
invented. Some layouts need flat fallback (for example the tested Monaco trace
cannot form a safe heightfield with the illustrative constant-width road).
The car is a generic licensed concept model, not an exact official team/year
replica. Higher geometric fidelity needs appropriately licensed source assets.
No sound is included. No claim is made that these editorial changes guarantee
virality. At1×, Blender's full-lap rendering cost remains substantial; speed
options reduce actual generated frame count but do not remove startup costs.
