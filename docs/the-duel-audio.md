# The Duel — HEAR THE GAP

> Historical v1/v2 implementation notes below. The current production default
> now uses published recordings instead of procedural backing music. See
> [recorded-soundtracks.md](recorded-soundtracks.md) and the asset attribution
> record in `assets/music/ATTRIBUTION.md`.

Audio is ON by default for **all user-facing video modes**: 2D, cinematic,
chase, onboard, Race Hype Cut and The Limit, in previews and final downloads.
The site, older video studio, API omission defaults and background job defaults
all select **The Duel** at 80%. Switching to 2D no longer forces Silent.
Choose **Silent** explicitly to omit the audio track. Existing MP4s are not
modified automatically; render again to apply audio. Completed scene caches
remain reusable, so audio does not require another Blender pass on a cache hit.

This is original procedural instrumental sound design, not a sampled engine,
licensed song, fake team radio, narration or a recreation of actual car sound.
No external music service or new audio asset download is required.

## Editorial structure

- Rounded opening impact and rising air texture during the analytical intro.
- Two contrasting melodic voices, gently weighted by the same signed
  matched-distance gap used by the HUD. Both remain audible in mono.
- Revised v2: immediate 128 BPM cinematic pulse, stronger kick/snare and a
  warm harmonic bass ostinato, reduced high arpeggio, softer lower-pitched gain
  accents and a lower, warmer finish signature. Music enters after 80ms rather
  than waiting for the 3.2-second intro. No time-stretching of
  samples at 3×/20×; musical tempo stays steady while telemetry uses the exact
  exported source clock.
- Brief ducks and driver-specific accents at the measured-gain section entries.
  These align with The Limit's three visual callouts.
- Music drops at the exact full-lap finish. An original three-note RACE HYPE
  signature plays during the result hold. Short clips receive an ending fade,
  not a false result sting.

## Implementation and safety

`services/duel_audio.py` streams deterministic 48 kHz stereo PCM in one-second
blocks. Cancellation is checked between blocks and while FFmpeg runs. Audio
is two-pass loudness normalized (base target -16 LUFS, -2 dBTP), then the user's
volume adjustment is applied. Zero volume is permitted; Silent omits the track.
AAC is muxed into an atomic partial MP4 with **`-c:v copy`**. There is no second
Blender render and no video re-encode. Silent scene caches remain reusable.
Audio selection/volume are returned in job metadata. Failed audio jobs remove
only their own UUID-named uncompleted output, never a user's source video.

## Verification

- 179 regression tests passed; frontend TypeScript/Vite build passed.
- Tests cover validation, exact source-clock cue mapping, reversed-driver
  dominance, deterministic finite stereo PCM, mono compatibility, cancellation,
  API/queue settings and real AAC muxing. The mux test compares every original
  video packet hash and PTS with the output.
- Added all-camera defaults/API omission coverage, exact 2D clip-hold clock
  matching, and real default 2D preview AND final MP4s verified to contain AAC.
- Complete sample also verified all 2,292 original video packet hashes/PTS
  identical. Decoded mono/stereo RMS ratio .99883. Live studio selector was
  exercised Silent → The Duel; volume returns at 80%. Native browser player
  reports 38.2s, playing, unmuted, ready state 4 with no media error.
- Complete sample:
  `output/video_studio/2026-ANT-VER-COTA-THE-LIMIT-THE-DUEL-60fps.mp4`.
  540×960 / 60fps / 38.2s / AAC stereo 48 kHz. At 80% volume, decoded AAC
  measured -17.80 LUFS integrated and -3.85 dBTP (not clipped).
- Cue times 12.304s, 28.714s, 33.524s; exact finish 36.183s.
- Revised v2 sample:
  `output/video_studio/2026-ANT-VER-COTA-CINEMATIC-PULSE-60fps.mp4`.
  No vocal recording is included. The user elected to keep the revised
  instrumental; the optional vocal-generation request did not start.

Reproduce the audio-only post pass on the existing verified sample:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_duel_audio --config tmp/trail-alignment/after/config.json --video output/video_studio/2026-ANT-VER-COTA-THE-LIMIT-60fps.mp4 --output output/video_studio/2026-ANT-VER-COTA-THE-LIMIT-THE-DUEL-60fps.mp4 --the-limit --volume 80
```

An engaging soundtrack cannot guarantee retention or virality. Subjective
listening feedback should drive the next musical revision; no claim of a
human listening evaluation is made by the technical checks above.
