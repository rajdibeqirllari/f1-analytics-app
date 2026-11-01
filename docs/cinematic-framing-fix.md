# Cinematic safe-frame correction

Reported failure: Mexico City 2025 qualifying / The Limit / Dynamic cinematic,
actual Blender min Y .379186 against the unchanged required .38 boundary.
Track coverage and car/asphalt checks had already passed.

## Cause and fix

The camera planner used a generic horizontal car proxy: along -2.3..3m,
width +/-1.15m, height 0..1.5m. The real prepared model extends 2.395m behind
the root, and its root rotates with road pitch. The final Blender guard used
those real local bounds and the actual XYZ Euler transform. Thus the planner
and validator were checking different geometry.

The cinematic planner now receives the same metadata-derived local corners
and applies the exact root transform (local -Y nose, Rz(yaw+pi/2) @ Rx(-pitch)).
It uses a slightly interior fitting target to allow float32 rounding, while
the final original safe-frame guard is unchanged. Camera distance is adjusted
by the existing damped zoom envelope. No lap samples, car positions, timing,
track geometry, trajectory ribbons or audio logic were altered.

Only affected cinematic cache keys receive a projection-version revision so
old camera exports are not mistaken for corrected renders.

## Validation

`scripts/validate_cinematic_projection.py` compares NumPy against Blender's
`world_to_camera_view` for the actual model bounds and root rotations. Steep
turning cases pass at portrait/landscape 540p/1080p, including close-camera
controls and overhead variants. Synthetic normalized projection error <8e-7.

`scripts/prepare_mexico_camera_validation.py` builds offline cases from cached
2025 Mexico Q data (no timing substitution or new download), using the normal
procedural road, cornering route, surface BVH heights, constrained spline and
speed-integrated poses. All three locally cached pairings (LEC/VER, NOR/VER,
NOR/LEC), with 5,220 route knots and the reported 2,592-frame timeline, pass
exact Blender projection checks for every frame in portrait/landscape and
chase/overhead. Minimum portrait Y .39563 or greater, vs unchanged .38 guard.
Kilometre-scale Blender float32 rounding differs from NumPy by <1.34e-5
normalized image units (subpixel). This diagnostic tolerance does not relax
any HUD boundary.

This is full-timeline camera validation, not a claim of a newly rendered full
video or that the user's driver pairing was explicitly identified.

Reports: `tmp/mexico-camera/*.validation.json` and
`tmp/camera-projection-validation.json`.
