"""YouTube thumbnail (1280x720) for a Race Hype live stream.

    .venv\\Scripts\\python.exe scripts\\make_thumbnail.py --event "São Paulo GP" --circuit sao-paulo-grand-prix

Dark broadcast look like the site: circuit outline from frontend/src/hype/circuits, RH logo, LIVE badge,
"Unofficial fan stream" so it stays clear of F1 branding.
"""
import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / 'frontend' / 'src' / 'hype' / 'fonts'
RED = (225, 6, 0)
S = 2  # supersampling for smooth edges
W, H = 1280 * S, 720 * S


def display(size, weight=900):
    f = ImageFont.truetype(str(FONTS / 'big-shoulders-display-latin-wght-normal.woff2'), size * S)
    f.set_variation_by_axes([weight])
    return f


def body(size, w=600):
    return ImageFont.truetype(str(FONTS / f'barlow-latin-{w}-normal.woff2'), size * S)


def outline_points(slug, box):
    t = json.loads((ROOT / 'frontend' / 'src' / 'hype' / 'circuits' / f'{slug}.json').read_text(encoding='utf-8'))
    r = -(t.get('rotation') or 0) * math.pi / 180
    c, s = math.cos(r), math.sin(r)
    pts = [(x * c - y * s, -(x * s + y * c)) for x, y in zip(t['x'], t['y'])]   # same transform as the Live map
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, x1, y1 = box
    k = min((x1 - x0) / (max(xs) - min(xs)), (y1 - y0) / (max(ys) - min(ys)))
    ox = x0 + ((x1 - x0) - (max(xs) - min(xs)) * k) / 2 - min(xs) * k
    oy = y0 + ((y1 - y0) - (max(ys) - min(ys)) * k) / 2 - min(ys) * k
    return [(px * k + ox, py * k + oy) for px, py in pts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--event', default='São Paulo GP')
    ap.add_argument('--session', default='Live timing · AI commentary')
    ap.add_argument('--circuit', default='sao-paulo-grand-prix')
    ap.add_argument('--out', default=str(ROOT / 'outputs' / 'thumbnails' / 'sao-paulo-live.png'))
    a = ap.parse_args()

    img = Image.new('RGB', (W, H), (9, 12, 17))
    d = ImageDraw.Draw(img)
    # Background: soft red glow on the right, faint diagonal speed lines
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W * .45, -H * .3, W * 1.25, H * 1.2), fill=120)
    glow = glow.filter(ImageFilter.GaussianBlur(220 * S))
    img = Image.composite(Image.new('RGB', (W, H), (70, 8, 10)), img, glow)
    d = ImageDraw.Draw(img)
    for i in range(-H, W, 46 * S):
        d.line([(i, H), (i + H * .55, 0)], fill=(16, 21, 28), width=3 * S)

    # Circuit: glow, kerb, asphalt, a red racing line, chequered finish and a few "cars"
    pts = outline_points(a.circuit, (W * .555, H * .12, W * .96, H * .88))
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.line(pts + [pts[0]], fill=(255, 40, 30, 255), width=34 * S, joint='curve')
    layer = layer.filter(ImageFilter.GaussianBlur(26 * S))
    img.paste(layer, (0, 0), layer)
    d = ImageDraw.Draw(img)
    d.line(pts + [pts[0]], fill=(235, 238, 242), width=26 * S, joint='curve')
    d.line(pts + [pts[0]], fill=(30, 36, 44), width=18 * S, joint='curve')
    n = len(pts)
    d.line(pts[:int(n * .42)], fill=RED, width=7 * S, joint='curve')
    fx, fy = pts[0]
    for i in range(-2, 2):
        for j in range(2):
            col = (240, 240, 240) if (i + j) % 2 else (15, 15, 15)
            d.rectangle((fx + i * 9 * S, fy - 18 * S + j * 9 * S, fx + (i + 1) * 9 * S, fy - 9 * S + j * 9 * S), fill=col)
    for frac, col in ((.41, (255, 255, 255)), (.37, (255, 135, 0)), (.33, (39, 244, 210)), (.70, (54, 113, 198))):
        x, y = pts[int(frac * n) % n]
        d.ellipse((x - 15 * S, y - 15 * S, x + 15 * S, y + 15 * S), fill=col, outline=(9, 12, 17), width=4 * S)

    # Logo
    logo = Image.open(ROOT / 'frontend' / 'src' / 'assets' / 'rh-logo.png').convert('RGBA').resize((150 * S, 150 * S), Image.LANCZOS)
    img.paste(logo, (48 * S, 36 * S), logo)

    # LIVE badge
    d = ImageDraw.Draw(img)
    bx, by = 62 * S, 222 * S
    d.rounded_rectangle((bx, by, bx + 168 * S, by + 62 * S), radius=8 * S, fill=RED)
    d.ellipse((bx + 20 * S, by + 21 * S, bx + 40 * S, by + 41 * S), fill=(255, 255, 255))
    d.text((bx + 52 * S, by + 4 * S), 'LIVE', font=display(54), fill=(255, 255, 255))

    # Headline
    words = a.event.upper().split()
    line1, line2 = (' '.join(words[:-1]), words[-1]) if len(words) > 1 else (words[0], '')
    d.text((56 * S, 292 * S), line1, font=display(148), fill=(255, 255, 255))
    d.text((56 * S, 432 * S), line2, font=display(148), fill=RED)
    d.text((62 * S, 590 * S), a.session.upper(), font=body(36, 600), fill=(220, 226, 232))
    d.rectangle((62 * S, 642 * S, 62 * S + 70 * S, 642 * S + 5 * S), fill=RED)
    d.text((62 * S, 656 * S), 'Unofficial fan stream  ·  @theracehype', font=body(22, 500), fill=(150, 160, 170))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.resize((1280, 720), Image.LANCZOS).save(out, optimize=True)
    print(out, out.stat().st_size // 1024, 'KB')


if __name__ == '__main__':
    main()
