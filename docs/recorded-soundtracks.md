# Published instrumental soundtracks

## Site choices

- **Industrial Cut** (default, API id `The Duel` for compatibility):
  *Industrial Cinematic* by Kevin MacLeod. Published percussion/synth full mix.
- **Grit & Drums**: *Gearhead* by Kevin MacLeod. Published guitar/bass/drum-kit
  full mix. Uses the same adaptive edit logic.
- **Silent**: no audio and no music credit.

No vocals. No Justice/Hans Zimmer recordings, imitations or copied reference
arrangements. No generated synth backing in the production audio path. These
are full recordings, **not separate stems**, and the mixer does not pretend to
isolate their drum/bass instruments. Original short accents are sound design,
not recordings of actual pit tools or engines.

## Arrangement

The editor finds an energetic onset within the first minute, avoiding a long
quiet intro. Music tempo/pitch remain fixed while video source time changes.
The complete recording plays forward naturally; long videos loop it using a
250ms equal-power crossfade. Close timing subtly raises the level. Measured
gain sections retain restrained accents, but NEVER duck or pause the backing
music. Music continues through the result card and analytical finale. Only
the last 180ms of the exported file receives an ending fade. This behavior
applies to both soundtrack choices and all video modes.

The artist provides complete mixes publicly. Independent instrument-layer
arrangement is intentionally NOT claimed. Obtaining genuine stems could enable
that refinement later.

## Attribution and export

Both recordings came directly from the composer's official downloads and are
used under CC BY 4.0. Full provenance, source URLs, author credit, edit notice
and SHA256 hashes are in `assets/music/ATTRIBUTION.md`.

Normal 2D/3D jobs pass the selected credit to the image compositor. A two-line
credit strip is drawn into every encoded frame (including analytical intro and
finale), retaining title/author, source domain, licence URL and an edit notice.
The full credit is also in job result metadata, MP4 comment and the site's
copyable music-credit section. Users should preserve the visible strip and
copy the credit into their social post descriptions. No guarantee is made
against automated platform claims.

Credits are part of the visual render cache key, avoiding reuse with the wrong
track attribution. Changing track can therefore require a new credited render;
changing only volume reuses the same credited video cache. The audio mux uses
`-c:v copy`; source-clock motion is never altered for audio.

The local proof helper adds the footer to older uncredited completed samples
with **one H.264 CRF18 encode**, then copies that credited video during the audio
mux. Thus these two proof samples are not claimed bit-identical to the old
uncredited source. New normal jobs draw the credit in their first encode pass.

## Validation

- 184 tests passed; TypeScript/Vite build passed.
- Real default 2D preview/final audio tests, 3D routing, API settings, AAC mux,
  no-synthetic-fallback guard, waveform validity, continuous long-loop seam,
  and attribution layout at portrait/landscape 540p/1080p are covered.
- Both proof MP4s: 540×960, native 60fps, 2,292 frames, 38.2 seconds, 48kHz AAC.
- Industrial Cut at 80%: -17.97 LUFS integrated / -5.33 dBTP decoded AAC.
- Grit & Drums at 80%: -18.16 LUFS integrated / -2.71 dBTP decoded AAC.
- Credit frame visually inspected; source clock and 0.179s result unchanged.
- Continuous-music regression uses a constant test recording to isolate any
  mixer-induced dips at gain cues and the finish. The result hold stays at
  full backing level; only the actual file ending fades.
- Corrected real preview RMS: cue 12.20–12.28s .10612 (old .01448), cue
  28.60–28.68s .10741 (old .01566), result 36.5–37.5s .09541 (old .00399).
  All 2,292 video packets and PTS match the earlier credited sample exactly.

Samples:

`output/video_studio/2026-ANT-VER-INDUSTRIAL-CUT-60fps.mp4`

`output/video_studio/2026-ANT-VER-GRIT-AND-DRUMS-60fps.mp4`

Corrected continuous-music proof (supersedes the earlier sample's mix):

`output/video_studio/2026-ANT-VER-INDUSTRIAL-CONTINUOUS-60fps.mp4`
