# Surface-locked trajectory ribbon

## Diagnosis

The old ribbon was already a Blender world-space mesh, using the same camera
as the cars and asphalt. No separate canvas projection, extra camera transform
or mismatched circuit scale was found.

Actual differences:

- Ribbon edges were placed **85mm above the asphalt**, producing visible
  separation/parallax, rather than representing thin surface paint.
- Cars used `RouteSpline`; the ribbon connected its original knots with straight
  quads. On this COTA route, maximum measured midpoint discrepancy was6.997mm.
- The ribbon head was cut by interpolated shader `lap_seconds`, using a120Hz
  numerical inverse clock. It was not an explicit vertex at the current car pose.
- Both ghost ribbons occupied the same layer where their history overlapped.

This is a rear **trajectory-history trail**, not a surveyed ideal racing line.
The fix locks it to the actual rendered vehicle path and visible asphalt;
it does not invent a different racing line or change the circuit layout.

## Implementation

`services/surface_trail.py` now constructs an adaptive ribbon from the same
`pose_at_progress` function used for cars. World-space XY is preserved; the
authoritative asphalt BVH supplies Z only, never snapping XY to another route.

- Uniform approximately20cm samples plus original knots and adaptive refinement.
- Maximum curve/chord error0.5mm; no separate decorative smoothing.
- Explicit per-frame head and tail generated at exact source timestamps.
- Analytic inverse of the same integrated speed curve used by `motion_progress`.
- Ribbon width24cm in Cinematic mode; the existing fade duration/color semantics
  remain. Geometry, alpha and pedal colors update together before frame render.
- Nominal paint height2mm, with1mm separation between ghost layers. Both ribbon
  edges and triangle centroids are checked against asphalt, not surrounding terrain.
- Identity object transform; the normal scene camera projects road, cars and
  ribbon together. No screen-space position correction is used.
- Update failure aborts publishing rather than silently exporting a stale trail.
- Render cache version30 invalidates previously generated ribbon renders.

## Measurements: complete cached COTA2026 qualifying comparison

ANT1:34.035 /VER1:34.214 /gap0.179s, unchanged.

| Check | Result |
| --- | ---: |
| Adaptive trajectory points | 33,252 |
| Maximum spacing | 0.200098m |
| Maximum curve/chord discrepancy | 0.4992mm |
| Off-asphalt projected vertices | 0 |
| Face-centroid surface clearance, first layer | 0.342–3.628mm |
| Second-layer additional height | 1mm |
| Head/car XY discrepancy, CPU world-space calculation | ≤7.11e-15m |
| Inverse clock discrepancy | ≤2.85e-14s |
| Frame endpoint checks | 2100frames, both drivers |
| Complete-car asphalt footprint checks | 37,800passed |

Numerical head equality above is before ordinary float32 GPU conversion, not
a claim of subatomic physical measurement. Millimetre paint clearance avoids
coplanar depth fighting; it is intentionally not mathematically zero height.

The original and corrected full-lap pose archives have **exactly identical**
source times, car positions, camera positions, targets and zoom arrays. Only
the ribbon implementation changed. Lap outcomes and camera framing were not
adjusted to hide alignment errors.

## Visual/export validation

- Corrected complete35s preview:540×960, native60fps,2100frames, Fast quality.
- 0near-duplicate transitions among1978moving-frame comparisons; even60fps PTS.
- Reviewed12consecutive frames around source10s,42s and90s, plus matched-source
  before/after frames at0,10,25,45,70,90s and the finish.
- Debug export includes white route knots, cyan interpolated trajectory, green
  asphalt boundaries and yellow actual car-root markers. Source8.929s closely
  matches the supplied8.917s screenshot; the trail coincides with the cyan curve.
- No trail-update errors, shadow-buffer overflow warnings or Blender tracebacks
  in either completed render.
- The before movie is1080p Balanced; the new proof movie is540p Fast. Comparison
  is for geometric alignment, not a claim of a controlled image-quality benchmark.

Artifacts:

- `output/video_studio/2026-ANT-VER-COTA-Surface-Locked-Trail-540p-60fps.mp4`
- `output/video_studio/2026-ANT-VER-COTA-Trail-Alignment-DEBUG.mp4`
- `tmp/trail-alignment/comparison/before-after-comparison.mp4`
- `tmp/trail-alignment/comparison/matched-source-comparison.jpg`
- `tmp/trail-alignment/debug/corner-8.917-debug.png`
- `tmp/trail-alignment/after/{trail-alignment.json,trail-debug.npz,cadence.json}`

Previously downloaded MP4s remain unchanged. Generate a new export to apply the
fix at720p/1080p or with different settings. The circuit itself is still a
telemetry-derived illustration, not a surveyed real-world track/apex model.

## Debug usage

The diagnostic helper uses the cached ANT/VER qualifying comparison:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_cinematic_ghost --alignment-debug --end 12 --quality Fast --output tmp/trail-alignment/debug-check
```

Other callers of `render_3d_mp4` can set `alignment_debug=True`. This diagnostic
is intentionally off in normal exports; the website has no new mandatory setting.

Changed runtime files: `services/surface_trail.py`, `scripts/render_3d_test.py`,
`services/video_3d.py`, `services/car_style.py`, `scripts/trail_alignment_debug.py`,
`services/cinematic_overlay.py`. Proof/comparison helpers and trail/worker tests
were also extended. Existing car trajectory, lap clocks and camera code were
not altered.
