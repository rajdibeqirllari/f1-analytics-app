# RACE HYPE — Immersive F1 Fan Dashboard

A redesigned, interactive, self-contained HTML/CSS/JavaScript frontend based on the user's existing Race Hype dashboard. No build tools or API keys are necessary.

## Run

Double-click `index.html`, or serve the folder locally:

```bash
python -m http.server 8501
```

Then open http://localhost:8501.

## What works

- Navigation across eight sections, including responsive desktop/mobile navigation.
- Session/event selection; driver selections; clickable timing table; animated circuit/replay with scrub/pause/speed controls.
- Two-driver telemetry graphs with channel switching and CSV export.
- Lap table with selectable driver/row count and CSV export.
- Sector comparison and head-to-head layout switching.
- Creator overlay customization, plus a genuinely transparent 1920×1080 PNG download.
- Fictional team-radio transcript browser with browser speech playback and text export.
- Interface sound toggle.

## Real-data integration

**This is a UI/frontend prototype, not a source of real timing or official radio.** Its stats and waveforms are synthetic and clearly marked as demonstration data. The app is not affiliated with Formula 1.

For live/historical production use, replace demo records in `app.js` using your backend. Suggested architecture: Python/FastF1 for historical telemetry, the OpenF1 API where licensed/available, and your own cache/API. Audio clips and 3D driver path views require separately authorized media and synchronized position data.

## Visual note and attribution

The Ferrari image in `assets/ferrari-race.png` is cropped from the screenshot of Race Hype supplied by the user. Replace it with your own properly licensed high-resolution photography or original artwork before distributing this design publicly.
