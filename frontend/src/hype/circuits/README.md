# Bundled circuit outlines

One JSON per event, named by the event slug (accents removed): `x`/`y` in tenths of a metre, starting at the finish line
in racing direction, plus `rotation`, `length`, `source` and the pit lane (`pit.entry` / `pit.exit` as lap fractions).

- `mexico-city-grand-prix.json`: OpenF1 fastest lap, hand-tuned.
- `sao-paulo-grand-prix.json`: from the open GeoJSON in https://github.com/bacinger/f1-circuits (`br-1940.geojson`),
  resampled, turned to racing direction (anticlockwise) and started ~300 m before the Senna S.

## bacinger/f1-circuits license (MIT)

Copyright (c) 2019-2025 Tomislav Bacinger

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
