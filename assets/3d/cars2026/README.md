# 2026 field (all eleven constructors)

Built by `scripts/cars2026/build_field.py` from `scripts/cars2026/teams.py` (entry list, liveries, sponsors, number styles, dated sources and the list of official artwork NOT reproduced). One `.blend` + GLB per constructor; teammates share geometry and livery, numbers and T-cam colour are per car in the browser. The W17/RB22 notes below describe the original archetypes the field is built from.

# 2026 cars: Mercedes W17 and Red Bull RB22

Original parametric models built by `scripts/qatar/build_cars_blend.py` (Blender 4.5.9). Nothing is copied from a
third-party model; the numbers and shapes come from the dated references below. No logos, sponsor names or numbers:
the liveries are plain colour fields.

| | W17 | RB22 |
|---|---|---|
| Blender source | `w17.blend` | `rb22.blend` |
| Browser asset | `frontend/public/cars/2026/w17.glb` (254 KB) | `rb22.glb` (245 KB) |
| Triangles (LOD0 / LOD1 / wheels+driver) | 29.8k / 3.6k / 6.5k | 29.7k / 3.5k / 6.5k |

Rebuild: `tools\blender\blender-4.5.9-windows-x64\blender.exe --background --factory-startup --python-exit-code 1 --python scripts\qatar\build_cars_blend.py -- --clay`
(`--clay` also renders the clay comparison `outputs/qatar/cars_clay_compare.png`).

## Dimensions (both)

Wheelbase 3,400 mm and width 1,900 mm (Mercedes W17 technical sheet, Jan 2026; 2026 maximums), length ~5.5 m,
height ~0.97 m. Tyres 18-inch, front ~280 x 705 mm, rear ~375 x 710 mm (2026 sizes as reported, not measured).
Front wheel centres ±0.81 m, rear ±0.76 m (from width minus tyre widths). The RB22 wheelbase is assumed to be the
3,400 mm maximum (not published).

## Shapes and references

**W17** (Mercedes-AMG F1 W17 E Performance): mercedesamgf1.com spec sheet (Jan 2026: pushrod front and rear); The Race,
Gary Anderson (Jan 2026: high radiator inlet, undercut, three-element front wing detached from the nose, bargeboards,
engine-cover fin); Wikipedia W17; Hungarian GP photo of Russell, 26 Jul 2026 (black with silver upper bodywork and
Petronas-teal accents). Modelled: slender nose ending above the second flap with pylons, high narrow inlet, high flat
sidepod top carried far back, deep undercut, rounded airbox, engine-cover fin, swan-neck rear wing pylon, diffuser
sidewalls. Finish: satin (not confirmed).

**RB22**: Giorgio Piola Design (3 May 2026: bathtub gully, deep undercut, downwash ramp, "Macarena" wing, no diffuser
sidewalls); RacingNews365 / Autosport launch analysis (Jan 2026: thick nose with an arrow-shaped tip on two small
pillars, short straight sidepods); Red Bull launch, Detroit 15 Jan 2026 (gloss finish, brighter blue); Japan update
side comparison (Apr 2026: navy with yellow on the airbox/nose). Modelled: low arrow tip on two pillars to the
mainplane, wide low inlet, short sidepods with a top gully and a steep ramp, taller pointed airbox, twin rear wing
pillars, open diffuser. Finish: gloss metallic navy.

**Not modelled / still approximate**: active-aero element positions, exact wing profiles and element counts, floor
fences and edge details, brake ducts, suspension pickup points (layout is generic pushrod), cockpit rim shape, mirror
mounting, late-season upgrades (e.g. the RB22 Las Vegas dive plane, 21 Nov 2026). Silhouettes differ clearly from the
side and rear (sidepod line, airbox, fin, rear wing supports, diffuser); from the front three-quarter the difference is
smaller.

## Named nodes (for the browser)

`LOD0` / `LOD1` groups, `steer_FL|FR|RL|RR` (pivot at the hub) → `wheel_*` (spin), `driver_helmet`, `cam_pod`
(T-cam lens above the airbox), `cam_cockpit` (driver's eye), `mount_label`. Blender X forward / Y left / Z up →
glTF/three.js x forward, y up, z right, the engine's car frame.

## Season and team resolution

`frontend/src/hype/broadcast/models.ts`: a model is used only for its own season and constructor (Mercedes,
Red Bull Racing; Racing Bulls does not match). On sessions from another season the viewer can switch on
**Preview 2026 cars**, which shows an amber "Preview" badge; it is never applied silently. All other teams keep the
generic car.

## The Qvist model (assets/3d/cars/qvist) was not reused

"F1 2026 concept (polygon model)" by Qvist_designs (Sketchfab, CC BY 4.0): a pre-season speculative concept built before
the real 2026 cars, one generic shape (3.40 m wheelbase, 1.88 m wide, ~251k faces after preparation, ~800k in the
source). Its proportions match the 2026 rules but it is neither a W17 nor an RB22, and at ~250k faces per car it is
too heavy for 20 cars in the browser. It stays the video renderer's car; no geometry from it is used here.
