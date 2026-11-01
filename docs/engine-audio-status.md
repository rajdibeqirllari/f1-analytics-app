# Local engine-audio integration status

## Revision 2 — listening review pending

The first prototype was rejected by the user. Do not enable it in video exports.
The new prototype replaces single 0.32-second fixed-reference looping with
multiple stable sections up to 1.6 seconds long, individual dominant-band pitch
estimates, continuous source playback, soft layer selection and 25ms pedal
transition smoothing. Native reference pitch is no longer assumed to be 10500
RPM. Mapping the measured dominant band to RPM/20 still assumes a V6 firing
component and may pick an overtone; it is not original source-RPM metadata.
The SDK Studio graph remains unavailable; these are custom approximate mixes.

New ten-second outputs, preserving the rejected files for comparison:

- `tmp/LEC-sampled-engine-v2.wav`
- `tmp/VER-sampled-engine-v2.wav`

Five tests pass, including output-pitch calibration from two differently pitched
synthetic source recordings. This establishes signal correctness, not perceived
realism. No website changes; listening approval is still required.

## Alternative prototype — works without the Studio master bank

`services/engine_samples.py` decodes the pack's unencrypted embedded FSB
subsounds using the matching FMOD Core SDK. It never patches the source bank
or uses proprietary game master-bank files. A custom continuous-phase sample
mixer blends on/off-throttle grains, varies pitch with measured RPM, applies
brief upshift cuts, and adds speed-scaled wind. Sample reference pitch is an
artistic calibration (10500 RPM), not recovered original recording RPM.
This is an experimental recreation, not the author's original Studio mix.

Verified sample mappings currently cover Ferrari and Red Bull only. Local
decoded samples are cached beside each supplied bank, under ignored
`assets/sounds/`; no samples or native libraries are distributed.

`python -m scripts.test_sampled_engine` creates ten-second Ferrari/Red Bull WAV
listening tests from actual 2026 Austin FP1 lap-12 telemetry, without changing
the website or video exports. Output paths:

- `tmp/LEC-sampled-engine-preview.wav`
- `tmp/VER-sampled-engine-preview.wav`

Four discovery/control and mixer tests pass. Outputs contain 480000 samples
at 48000 Hz; they are non-silent. Listening review and pitch calibration are
still needed before offering this as a finished video-audio mode. Braking
does not trigger invented tyre skid; ghost rival audio is not mixed.

Core SDK guidance: https://fmod.com/docs/2.04/api/core-api-sound.html
(Implementation signatures/flags come from the local 1.08.12 headers.)

Audio Engine supplied by FMOD by Firelight Technologies.
The user accepted the supplied FMOD 1.08.12 license for local use. SDK and
sound banks remain local, ignored by Git, and must not be redistributed.

## Verified

- FMOD Studio API 1.08.12 x64 starts with offline WAV output.
- The unmodified SDK distance-filter example compiles for x64 with the installed
  Visual Studio Build Tools; the banks require this plug-in.
- Red Bull engine event metadata exposes `rpms` (0–15000) and `throttle` (0–1).
- Gear event exposes `state` (0–1); wind exposes `speed` (0–500).
- Team-bank lookup and timestamped telemetry-control tests pass.

## Blocking dependency — no working video audio yet

Starting the supplied bank's events fails: FMOD reports `Bus not found`, with
missing bus GUIDs including `{db9dca15-49f5-4c00-93ca-e76ccaf1160e}` and
`{1c1f5d35-07d5-4d6f-b916-cd0eb4adfd60}`. The pack contains car banks only,
not their shared mixer/master bank. The attempted test WAV is silent and is
not a successful audio sample. Full diagnostics are in local `fmod-probe.log`.

Ask the pack creator for a standalone matching mixer/master bank (and permission
for rendered social-video use), or standalone engine WAV loops/stems. A random
master bank from another FMOD project will not match these GUIDs. Do not source
proprietary game files or remove dependencies by patching the supplied banks.

If a permitted matching bank becomes available, place it at
`assets/sounds/fmod-api-1.08.12/master.bank`, then rerun the isolated native test
`python -m scripts.test_engine_render`. Verify non-silent output, timing, shift
direction, headroom, all team mappings and real telemetry before connecting
`prepare_audio` / `add_engine_audio` to video jobs. No audio switch is currently
enabled in the website. Existing video generation is unchanged.
