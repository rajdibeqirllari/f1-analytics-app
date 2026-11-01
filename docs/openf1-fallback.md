# Historical OpenF1 fallback

FastF1 remains first choice. Its existing disk cache is not cleared or modified
by the OpenF1 fallback. When loading a session fails, the driver/lap catalogue
tries OpenF1. Comparison videos and interactive lap traces also fall back if
FastF1 cannot provide usable telemetry. The existing Auto telemetry-export source
uses the same historical session resolver and cached OpenF1 car streams.

OpenF1 fallback is for completed historical sessions from 2023 onwards. It
requires a uniquely matched venue/session, actual timed laps, mandatory car
channels, and reliably time-matched nondegenerate positions for comparisons.
Sparse streams, missing timestamps, or gaps exceeding two seconds are rejected.
Unknown events are not silently replaced with another event in the same country.

The UI identifies OpenF1 and states the limitations. Q1/Q2/Q3 filtering is
disabled. Fastest means fastest timed non-out lap, not a certified valid lap:
deleted laps and race-control validity are not inferred. Absent DRS values remain
null in telemetry exports and unavailable in live comparison state. Internal
renderer compatibility samples may contain default DRS values, but no DRS display
may present those defaults as observed data. Energy modes are not fabricated.
Ghost routes remain illustrative, not proof of either driver's precise line.

Full-session race replay, timing tables, and existing engineering charts remain
FastF1-only. This is not a replacement implementation of FastF1's Session API.

Successful nonempty historical responses are persisted under
`outputs/openf1_cache`, separate from `fastf1_cache`. Session discovery refreshes
after a day; completed-session streams remain cached. Requests are serialized and
spaced at least 2.1 seconds apart in each process; external consumers of the same
IP may still cause server rate limiting. Failed/empty downloads are not cached.

Use is scoped to the user's stated non-commercial social-media workflow.
Review https://openf1.org/ before monetization, sponsorships, or commercial use.

Verified with Belgian GP 2026 Race, VER/LEC lap 23. Tests:
`python -m unittest discover -s tests`.
