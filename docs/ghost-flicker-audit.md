# Uploaded onboard flicker investigation

Source: user-provided `2026_LEC_VER_3d_c8ab56c47246_preview.mp4`, 540x960,
24fps, 2357 frames, 98.208 seconds. User reported Fast.

Largest cockpit-region brightness jumps occur near 23.5, 43.417, 84.708,
20.0, 41.542 and 50.25 seconds. Adjacent frame inspection shows overlapping
ghost surfaces and lens-near geometry changing abruptly, while the sampled
road region is relatively steady. This does not rule out other flicker.

Tested changes:

- Blended ghost materials show their frontmost surfaces, not all inner shells.
- Only ghost fragments within 0.30–2.5m of the camera smoothly fade toward
  transparent, avoiding hard near-plane slicing. Rival body farther away keeps
  0.42 alpha. Opaque focus car, trajectory, timing and samples unchanged.

Before/after render: Austin 2026 FP1, LEC/VER lap12, onboard B, 23.25–23.75s,
540x960, 24fps, Fast 8 samples. Local files under `tmp/flicker-audit/`.
Maximum adjacent-frame mean brightness change in x175:365/y700:850:
23.024 before, 7.113 after (~69% smaller). This is a diagnostic region metric
over 12 frames, NOT a full-lap flicker or perceptual-quality score.
The single-shell change alone only reduced that metric to 21.741; proximity
fade was necessary for the larger improvement.

Render version bumped to avoid serving old cached exports. Fifteen focused
material/3D/pipeline tests pass. No resolution, sample-count or FPS changes.
Full-lap and additional-resolution review remains necessary.

Official explanation of blended ordering and Transparency Overlap:
https://docs.blender.org/manual/nl/4.5/render/eevee/material_settings.html
