# Quality-preserving pipeline changes

## Shadow-buffer regression fix

The user's 1080x1920 Balanced full-lap render repeatedly overflowed the default
512 MB EEVEE shadow atlas (about 2212 requested pages / 2048 available).
The atlas is now explicitly 1024 MB on this local RTX 3060 12 GB installation.
Shadow resolution, ray count, samples, geometry and FPS were not reduced.
Render cache version is v25. Repeated shadow overflow now aborts an export
instead of silently producing thousands of frames with missing shadows.

Regression: Austin 2026 FP1 LEC/VER, onboard B, 2.5–3.5 seconds, 1080x1920,
24fps, Balanced (24 samples). All 24 frames completed with ZERO shadow-buffer
warnings. Steady frame time (excluding first frame) averaged 0.875s. Overall
startup+render+encode was 53.06s. This fixes an error condition, not the main
per-frame rendering cost: extrapolated full laps still take tens of minutes.
The earlier 0.93s timing came from a different live segment, not a controlled
before/after speed benchmark. No precise speedup percentage is claimed.
Evidence: `tmp/shadow-budget/{blender.log,validation.json,summary.json}`.
Eighteen focused quality / 3D / streaming pipeline tests passed.

- EEVEE samples remain Fast 8, Balanced 24, High 64. Resolution, FPS, color
  transform, geometry, lighting and H.264 settings are unchanged.
- HUD composition / FFmpeg encoding now consumes completed Blender frames while
  Blender is still rendering the next ones. Previously composition started only
  after every frame had rendered.
- Successfully consumed temporary PNGs are removed during streaming. Compression
  is low-effort lossless PNG (10), not uncompressed full-lap image storage.
- Locator trails are evaluated in one vectorized call per driver rather than
  repeatedly reintegrating lap samples for each dot. Static chase gradients are
  drawn once and copied without changing pixels.
- Exact completed-video cache remains in use.

Verification: 240 locator frames were byte-identical before/after optimization;
the locator-only benchmark measured 0.890s before and 0.229s after (~3.9x).
This is not a 3.9x whole-render claim. Streaming/sequential test MP4s have
identical SHA-256 hashes. Failed frame production publishes no partial video.
Two streaming tests, three locator tests and twelve 3D tests passed. A real
Austin onboard render completed at 540x960 / 24fps / High (12 frames). No
baseline whole-clip timing comparison was measured. A broad suite run was
interrupted; no full-suite success is claimed.

Residual flicker is not diagnosed or fixed by these throughput changes. Need
the user's current clip and quality setting to distinguish surface aliasing,
shadow changes, transparency, geometry overlap or compression artifacts.
No samples or resolution were reduced to conceal the problem.

Blender documents PNG compression as a lossless speed/size tradeoff:
https://docs.blender.org/api/4.0/bpy.types.ImageFormatSettings.html
