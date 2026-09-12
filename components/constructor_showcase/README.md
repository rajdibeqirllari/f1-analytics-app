# Overview constructor scanner

The native hero stays in Streamlit's page DOM. A zero-height, same-origin HTML
component attaches a non-passive wheel listener only to the hero. It consumes
vertical wheel input while cars can advance in that direction. At either end,
outward scrolling returns to the page. Ctrl-wheel zoom is never intercepted.
No wheel listener is installed on Season Overview or the page. Touch swipes,
keyboard page scrolling and scrollbar drags remain native and do not change cars.
It disposes observers/listeners when its hero or iframe is removed.

Autoplay advances every 3 seconds with a 750ms eased, overlapping glide and
crossfade, including last-to-first. Reduced motion uses only the crossfade.
Manual hero wheel input cancels the automatic transition and restarts the idle
timer; outside scrolling is still native. A small pause/resume button controls
autoplay. Timers pause while the hero is offscreen or the document is hidden,
restart without catch-up on return, and are cleared on component cleanup.

The hero and `season_content` stay in normal document flow with compact spacing.
There is no scroll spacer, sticky pinning or season translation. Car progress is
local to the hero and independent of page position. No React nodes are moved.

Viewport-relative wheel distance is measured on resize; normalized car progress
is preserved. Each animation frame samples the accumulated hero input without
layout reads, Python reruns, a wheel queue or a nested scrollbar.

## Standings and images

`ui/workspaces.py` gets `get_season_overview(2026)` once and gives that same
object to the hero and the current-season table. Selecting an older table
season does not reorder the 2026 cars. The existing overview service sorts
constructor rows by points descending, retaining official position as the
tie-breaker (countback). No separate standings API or copied points are used.

`CONSTRUCTOR_ASSETS` in `ui/constructor_config.py` maps provider IDs and name
aliases to the existing PNGs and calibration. `constructors_from_standings`
retains the shared rows' ranking, so Mercedes/Ferrari swapping points changes
the order without touching animation code. Unknown teams are not assigned
invented images. If standings are unavailable, a static Mercedes asset is
explicitly UNRANKED and no scroll story is created. It is not a fake P1.

The existing PNGs are embedded once as eager images, preserving their alpha and
aspect ratio. All 11 must decode before the timeline starts. This avoids static
server configuration, external dependencies, absolute browser paths and image
loads during a transition. Original assets are not modified. The initial media
payload is about 10 MB (base64); there are no further image requests on scroll.

## Tuning

All artist/developer settings live in `ui/constructor_config.py`:

- `autoAdvanceMs = 3000`, `autoTransitionMs = 750`: autoplay cadence and fade duration.

- `SCROLL_PER_CONSTRUCTOR_VH = 22`: the single scroll-speed control. Every team
  receives 22% of the real page viewport's height, INCLUDING the final team.
  With an 856px viewport, this is 188.32px/team and 2071.52px total for 11 teams.
- `transitionStart` / `transitionEnd` (0.45 / 1.0): overlapping crossfade range
  inside each segment. Opacities sum to 1; at least one car is always >= 0.5.
- `finalExitStart` (0.70): final team rests at full opacity for 70% of its own
  segment before a subtle exit. `finalExitOpacity` (0.78) keeps it visible as
  the viewport releases, rather than fading to an empty panel.
- Navbar and season use the existing normal page layout.
- `transitionDistance`, `settleDistance`, `verticalDistance`, `rotationDegrees`, `scaleDrift`:
  restrained scroll transforms; independent from artist calibration.
- `carWidthPercent` / `mobileCarWidthPercent`: image-stage width (94% / 90%).
- Each constructor's `scale`, `x`, `y`: calibrated transform in CSS pixels,
  applied to a separate nested element. Positive x is right, positive y down.
- `DEBUG_CAR_ALIGNMENT = True`: enables center / tyre baseline / wheel guides,
  live calibration and progress readout, and developer-only previous/next
  buttons. Restore `False` before sharing the app.

The hero's left-side copy, fonts, color system and proportions stay in the
existing studio styles. Only scanner styles are added here. Reduced-motion
users get the same scroll-controlled crossfades with no translation, rotation,
scale drift or background parallax. Phones use less movement and a smaller stage.

## Verification

Run `node --test tests/constructor_timeline.test.js` and
`.venv/Scripts/python.exe -m unittest discover -s tests -p test_constructor_standings.py`
from the project root. Also verify the running app: current standings leader
at the top (currently Mercedes), intermediate crossfades,
Cadillac and wheel boundary handoff, reverse hero scroll, season reruns, navigating
away/back, and phone-width layout. If upgrading Streamlit, check that its HTML
component still grants same-origin access. There is no attempt to bypass a
sandbox that disallows it; the already-rendered standings leader is the static
fallback. The left-side copy and all original car PNGs remain untouched.
