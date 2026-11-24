# Mexico 2026 · Lap 1 · Turn 4 — 3D reconstruction

Everything is generated: no broadcast footage, no Ferrari or F1 logos.

## Make the video

From `C:\f1hud_app`:

```
.\.venv\Scripts\python.exe scripts\incident\make_video.py --preview   # quick check: 540x960, 15 fps
.\.venv\Scripts\python.exe scripts\incident\make_video.py             # final: 1080x1920, 30 fps
```

Output: `outputs\incident\mexico2026_t4.mp4` (or `.preview.mp4`).
After changing only texts in the JSON, add `--skip-render` (re-does captions in about a minute).
Add `--open-blend` to also save `outputs\incident\work\mexico2026_t4.blend` to open in Blender.

## What comes from data, what is approximate

| From OpenF1 timing data | Approximate (set in the JSON) |
|---|---|
| Where each car is along the lap, every moment | Side-by-side position (inside/outside) |
| Speed, gear, throttle, brake | The exact cut line across Turn 5 |
| Braking points (T1: LEC 0.48 s later, T4: 0.24 s later) | Track width, kerbs, scenery |
| Gap after Turn 5 (~0.8 s) | |

The feed snaps both cars onto one racing line, so it cannot show who was on the
inside. The `lateral` lists follow the stewards' and drivers' descriptions:
LEC round the outside of T4, HAM off on the inside, LEC across the inside of T5.

## Edit

`mexico2026_t4.json`:
- `shots`: order, camera type (`heli`, `trackside`, `chase`, `drone`, `top`, `orbit`), data time range, slow motion (`speed`), freeze (`hold` seconds).
- `captions`: `at_t` = data time (seconds after the start), `at` = seconds into the shot. `{t4_brake_gap:.2f}` etc. are filled from the data.
- `lateral`: metres right (+) / left (−) of the line at a lap distance. Corners: T1 984, T2 1062, T3 1116, T4 1820, T5 1884, T6 2026.
- `livery`, `drivers.tag/tcam/helmet`: colours.

Car model: Qvist_designs (CC BY 4.0), credited at the end of the video.
