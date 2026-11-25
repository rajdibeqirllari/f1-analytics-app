"""Sponsor wordmark atlases for the 2026 cars (one per constructor): assets/3d/cars2026/decals/<team>.png + .json.

Each wordmark is set in a font on a transparent background in the brand colour; the JSON gives each placement's UV
rectangle (atlas space, v up) and aspect ratio. Numbers are not in the atlas: the browser draws each driver's number
on that car's own material, so teammates never share a number texture.
Run: .venv\\Scripts\\python.exe scripts\\cars2026\\make_decals.py
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'cars2026'))
from teams import FONTS, TEAMS  # noqa: E402

OUT = ROOT / 'assets/3d/cars2026/decals'
SIZE = 1024
TEXT_H = 120


def render(text, font_key, colour):
    f = ImageFont.truetype(FONTS.get(font_key, FONTS['sans']), TEXT_H)
    box = f.getbbox(text)
    w, h = box[2] - box[0], box[3] - box[1]
    pad = 10
    im = Image.new('RGBA', (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad - box[0], pad - box[1]), text, font=f, fill=colour)
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for key, t in TEAMS.items():
        atlas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
        x, y, row = 4, 4, 0
        rects = {}
        for placement, text, font, colour in t['sponsors']:
            im = render(text, font, colour)
            if im.width > SIZE - 8:
                im = im.resize((SIZE - 8, int(im.height * (SIZE - 8) / im.width)), Image.LANCZOS)
            if x + im.width > SIZE - 4:
                x, y, row = 4, y + row + 6, 0
            atlas.alpha_composite(im, (x, y))
            # UV: u left->right, v bottom->top (glTF flips on export; Blender's convention is v up)
            rects[placement] = dict(text=text, uv=[x / SIZE, 1 - (y + im.height) / SIZE, (x + im.width) / SIZE, 1 - y / SIZE],
                                    aspect=round(im.width / im.height, 4))
            x += im.width + 6
            row = max(row, im.height)
        atlas.save(OUT / f'{key}.png', optimize=True)
        (OUT / f'{key}.json').write_text(json.dumps(rects, indent=1), encoding='utf-8')
        print(key, len(rects), 'decals', f'{(OUT / f"{key}.png").stat().st_size / 1024:.0f} KB')


if __name__ == '__main__':
    main()
