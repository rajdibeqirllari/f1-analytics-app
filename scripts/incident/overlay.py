"""Overlay pass: driver tags, telemetry cards, captions, trails and the verdict card, then MP4.

  .\\.venv\\Scripts\\python.exe scripts\\incident\\overlay.py scripts\\incident\\mexico2026_t4.json [--preview] [--stills 35,148]

Reads <work>/frames(_preview)/ and frames(_preview).json from build_scene.py and writes
outputs/incident/mexico2026_t4(.preview).mp4 (or PNG stills with --stills).
"""
import json
import math
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).absolute().parents[2]
HERE = Path(__file__).absolute().parent
argv = sys.argv[1:]
CFG = json.loads(Path(argv[0] if argv and not argv[0].startswith('--') else HERE / 'mexico2026_t4.json').read_text(encoding='utf-8'))
PREVIEW = '--preview' in argv
STILLS = [int(x) for x in argv[argv.index('--stills') + 1].split(',')] if '--stills' in argv else None
WORK = ROOT / CFG['data_dir'] / 'work'
META = json.loads((WORK / ('frames_preview.json' if PREVIEW else 'frames.json')).read_text(encoding='utf-8'))
FR = WORK / ('frames_preview' if PREVIEW else 'frames')
W, H = META['size']
FPS = META['fps']
K = W / 1080  # layout scale
FACTS = META['facts']
SHOTS = {s['id']: s for s in CFG['shots']}
DRV = CFG['drivers']
CORNERS = CFG['corners']
L_ZONES = CFG.get('off_track', [])


def font(name, size):
    return ImageFont.truetype(str(HERE / 'fonts' / name), max(8, int(size * K)))


F_TITLE = lambda s: font('BigShoulders-900.ttf', s)
F_BOLD = lambda s: font('barlow-latin-600-normal.ttf', s)
F_MED = lambda s: font('barlow-latin-500-normal.ttf', s)
F_REG = lambda s: font('barlow-latin-400-normal.ttf', s)
RED = (255, 59, 59)
INK = (10, 14, 20)


def rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ease(x):
    x = min(max(x, 0), 1)
    return x * x * (3 - 2 * x)


def fmt(text):
    try:
        return text.format(**FACTS)
    except (KeyError, ValueError):
        return text


# Which output frame each caption starts at.
frames = META['frames']
by_shot = {}
for i, f in enumerate(frames):
    by_shot.setdefault(f['shot'], []).append(i)


def caption_windows():
    out = []
    for sid, idxs in by_shot.items():
        shot = SHOTS[sid]
        first = frames[idxs[0]]['frame']
        for c in shot.get('captions', []):
            if 'at_t' in c:
                start = next((frames[i]['frame'] for i in idxs if frames[i]['t'] >= c['at_t'] - 1e-6), first)
            else:
                start = first + int(round(c.get('at', 0) * FPS))
            out.append((start, start + int(round(c['dur'] * FPS)), sid, c))
    return out


CAPS = caption_windows() if not STILLS else None


def caption_windows_full():
    # Stills are a subset of frames: compute windows from the shot timing in the config instead.
    out = []
    frame = 1
    for shot in CFG['shots']:
        n = int(round(shot['hold'] * FPS)) if shot.get('hold') else int(round((shot['t'][1] - shot['t'][0]) / shot['speed'] * FPS))
        for c in shot.get('captions', []):
            if 'at_t' in c:
                start = frame + int(round((c['at_t'] - shot['t'][0]) / shot['speed'] * FPS))
            else:
                start = frame + int(round(c.get('at', 0) * FPS))
            out.append((start, start + int(round(c['dur'] * FPS)), shot['id'], c))
        frame += n
    return out


if STILLS:
    CAPS = caption_windows_full()


FROST = []      # panels to back with frosted glass this frame: (box, radius, opacity)
CUR_ALPHA = [1.0]


def panel(draw, box, radius=18, fill=(12, 16, 22, 150), outline=(255, 255, 255, 46), frost=True):
    if frost:
        FROST.append((tuple(int(v) for v in box), int(radius * K), CUR_ALPHA[0]))
    draw.rounded_rectangle(box, radius=int(radius * K), fill=fill, outline=outline, width=max(1, int(1.5 * K)))


def frosted(img):
    """Blur what is behind each panel (glass look)."""
    for (x0, y0, x1, y1), r, a in FROST:
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
        if x1 - x0 < 4 or y1 - y0 < 4 or a <= 0:
            continue
        region = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(18 * K))
        mask = Image.new('L', region.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, x1 - x0 - 1, y1 - y0 - 1), radius=r, fill=int(255 * a))
        img.paste(region, (x0, y0), mask)
    FROST.clear()


yy, xx = np.mgrid[0:H, 0:W]
_r = np.sqrt(((xx - W / 2) / (W * .62)) ** 2 + ((yy - H / 2) / (H * .62)) ** 2)
VIGNETTE = Image.new('RGBA', (W, H), (0, 0, 0, 0))
VIGNETTE.putalpha(Image.fromarray((np.clip(_r - .55, 0, 1) ** 1.6 * 210).astype('uint8')))
del yy, xx, _r


def grade(img):
    """Gentle bloom on highlights, a touch of contrast and a vignette."""
    rgb_ = img.convert('RGB')
    blur = rgb_.filter(ImageFilter.GaussianBlur(16 * K))
    bright = blur.point(lambda v: max(0, v - 170) * 3)
    out = Image.fromarray(np.clip(np.asarray(rgb_, np.float32) + np.asarray(bright, np.float32) * .35, 0, 255).astype('uint8'))
    out = out.convert('RGBA')
    out.alpha_composite(VIGNETTE)
    return out


def wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ''
    for w in words:
        trial = (cur + ' ' + w).strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def glow_line(layer, pts, color, width, glow=3.0, alpha=230):
    if len(pts) < 2:
        return
    g = Image.new('RGBA', layer.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    d.line(pts, fill=(*color, 150), width=int(width * glow), joint='curve')
    g = g.filter(ImageFilter.GaussianBlur(width * 1.6))
    layer.alpha_composite(g)
    ImageDraw.Draw(layer).line(pts, fill=(*color, alpha), width=max(1, int(width)), joint='curve')


def corner_name(s):
    best = min(CORNERS.items(), key=lambda kv: abs(kv[1] - s))
    return best[0] if abs(best[1] - s) < 70 else None


TOP_SHADE = Image.new('RGBA', (W, H), (6, 9, 13, 0))
TOP_SHADE.putalpha(Image.fromarray((np.clip(1 - np.linspace(0, 1, H) / .24, 0, 1) ** 1.4 * 150).astype("uint8")[:, None].repeat(W, 1)))


def draw_frame(f):
    img = Image.open(FR / f"{f['frame']:05d}.png").convert('RGBA')
    if img.size != (W, H):
        img = img.resize((W, H))
    img = grade(img)
    FROST.clear()
    CUR_ALPHA[0] = 1.0
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    lay.alpha_composite(TOP_SHADE)
    d = ImageDraw.Draw(lay)
    shot = SHOTS[f['shot']]
    caps = [c for c in CAPS if c[0] <= f['frame'] < c[1]]
    full_card = any(c[3].get('kind') in ('title', 'verdict') for c in caps)

    # Track limits and trails (top view / freeze).
    if f.get('limits'):
        for side in ('left', 'right'):
            pts = [tuple(p) for p in f['limits'][side] if -W < p[0] < 2 * W and -H < p[1] < 2 * H]
            glow_line(lay, pts, (255, 255, 255), 4 * K, glow=4, alpha=210)

    # Off-track highlights: ring around a car while it is inside a scripted off-track zone.
    for z in L_ZONES:
        c = f['cars'][z['car']]
        x, y, depth = c['screen']
        if z['s_from'] <= c['s'] <= z['s_to'] and depth > 0:
            pulse = .5 + .5 * math.sin(f['frame'] / FPS * 9)
            r = (34 + 10 * pulse) * K * (1.6 if shot['camera'] == 'top' else 1)
            d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 70, 50, 235), width=int(5 * K))
            tag = 'OFF TRACK'
            fnt = F_BOLD(26)
            tw = d.textlength(tag, font=fnt)
            panel(d, (x - tw / 2 - 12 * K, y + r + 6 * K, x + tw / 2 + 12 * K, y + r + 44 * K), radius=8, fill=(200, 30, 30, 230), outline=None, frost=False)
            d.text((x, y + r + 25 * K), tag, font=fnt, fill='white', anchor='mm')

    # Driver tags (pill above each car), or dots in the top view.
    placed = []
    for num, c in sorted(f['cars'].items(), key=lambda kv: kv[1]['screen'][2], reverse=True):
        x, y, depth = c['screen']
        if depth <= 0 or not (-50 < x < W + 50 and -50 < y < H + 50) or full_card:
            continue
        col = rgb(DRV[num]['tag'])
        if shot['camera'] == 'top':
            r = 13 * K
            d.ellipse((x - r, y - r, x + r, y + r), fill=(*col, 255), outline=INK, width=int(3 * K))
        label = DRV[num]['code']
        fnt = F_TITLE(34)
        tw = d.textlength(label, font=fnt)
        bw, bh = tw + 40 * K, 42 * K
        bx, by = x - bw / 2, y - bh - (34 if shot['camera'] != 'top' else 26) * K
        for px, py in placed:
            if abs(px - bx) < bw and abs(py - by) < bh + 6 * K:
                by = py - bh - 8 * K
        placed.append((bx, by))
        panel(d, (bx, by, bx + bw, by + bh), radius=21, fill=(12, 16, 22, 170), outline=(*col, 220))
        d.ellipse((bx + 12 * K, by + bh / 2 - 6 * K, bx + 24 * K, by + bh / 2 + 6 * K), fill=(*col, 255))
        d.text((bx + 30 * K + tw / 2, by + bh / 2 + 1 * K), label, font=fnt, fill='white', anchor='mm')
        if shot['camera'] != 'top':
            d.line((x, by + bh, x, y - 8 * K), fill=(*col, 160), width=max(1, int(2 * K)))

    # Header.
    d.rectangle((48 * K, 70 * K, 76 * K, 82 * K), fill=RED)
    d.text((88 * K, 76 * K), 'RACE HYPE', font=F_BOLD(30), fill='white', anchor='lm')
    chip = '3D RECONSTRUCTION'
    fnt = F_BOLD(22)
    tw = d.textlength(chip, font=fnt)
    panel(d, (W - 48 * K - tw - 28 * K, 56 * K, W - 48 * K, 96 * K), radius=20, fill=(10, 14, 20, 190), outline=(255, 255, 255, 90))
    d.text((W - 48 * K - tw / 2 - 14 * K, 76 * K), chip, font=fnt, fill=(235, 238, 242), anchor='mm')
    sp = shot.get('speed', 1)
    badge = 'FREEZE FRAME' if shot.get('hold') and shot['id'] != 'verdict' and shot['id'] != 'intro' else (f'{sp:g}× SLOW MOTION' if sp < .99 else None)
    if shot['id'] == 'verdict':
        badge = None
    if badge and not full_card:
        tw = d.textlength(badge, font=fnt)
        panel(d, (W - 48 * K - tw - 28 * K, 106 * K, W - 48 * K, 146 * K), radius=20, fill=(255, 210, 63, 235), outline=None, frost=False)
        d.text((W - 48 * K - tw / 2 - 14 * K, 126 * K), badge, font=fnt, fill=INK, anchor='mm')

    # Telemetry cards (top), hidden under full cards.
    if not full_card:
        lead_s = max(c['s'] for c in f['cars'].values())
        turn = corner_name(lead_s)
        d.text((48 * K, 122 * K), f"LAP 1{' · TURN ' + turn[1:] if turn else ''}", font=F_BOLD(26), fill=(220, 224, 230), anchor='lm')
        names = [CFG['drivers'][n]['name'].upper() for n in DRV]
        fnt_d = F_BOLD(30)
        w1, w2, wv = d.textlength(names[0], font=fnt_d), d.textlength(names[1], font=fnt_d), d.textlength('VS', font=F_TITLE(30))
        pw = w1 + w2 + wv + 80 * K
        px0 = (W - pw) / 2
        d.rounded_rectangle((px0, 352 * K, px0 + pw, 352 * K + 52 * K), radius=int(26 * K), fill=(246, 246, 244, 235))
        d.text((px0 + 24 * K, 352 * K + 26 * K), names[0], font=fnt_d, fill=INK, anchor='lm')
        d.text((px0 + 40 * K + w1 + wv / 2, 352 * K + 27 * K), 'VS', font=F_TITLE(30), fill=RED, anchor='mm')
        d.text((px0 + 56 * K + w1 + wv, 352 * K + 26 * K), names[1], font=fnt_d, fill=INK, anchor='lm')
        order = sorted(f['cars'], key=lambda n: -f['cars'][n]['s'] if f['shot'] != 'intro' else DRV[n]['grid'])
        cw = (W - 48 * K * 2 - 20 * K) / 2
        for k, num in enumerate(order):
            c = f['cars'][num]
            col = rgb(DRV[num]['tag'])
            x0 = 48 * K + k * (cw + 20 * K)
            y0 = 158 * K
            panel(d, (x0, y0, x0 + cw, y0 + 172 * K), radius=22)
            d.rectangle((x0 + 20 * K, y0 + 22 * K, x0 + 27 * K, y0 + 62 * K), fill=col)
            d.text((x0 + 40 * K, y0 + 42 * K), DRV[num]['code'], font=F_TITLE(46), fill='white', anchor='lm')
            d.text((x0 + cw - 22 * K, y0 + 42 * K), f"P{k + 1}", font=F_BOLD(28), fill=(200, 206, 214), anchor='rm')
            d.text((x0 + 20 * K, y0 + 112 * K), f"{int(round(c['speed']))}", font=F_TITLE(64), fill='white', anchor='lm')
            sw = d.textlength(f"{int(round(c['speed']))}", font=F_TITLE(64))
            d.text((x0 + 28 * K + sw, y0 + 122 * K), 'KM/H', font=F_BOLD(20), fill=(170, 176, 186), anchor='lm')
            d.text((x0 + cw - 22 * K, y0 + 112 * K), f"G{int(c['gear']) or 'N'}", font=F_TITLE(48), fill=col, anchor='rm')
            # throttle / brake bars
            bx0, bx1, by = x0 + 20 * K, x0 + cw - 20 * K, y0 + 152 * K
            d.rounded_rectangle((bx0, by, bx1, by + 10 * K), radius=int(5 * K), fill=(255, 255, 255, 30))
            tw_ = (bx1 - bx0) * min(max(c['throttle'], 0), 100) / 100
            d.rounded_rectangle((bx0, by, bx0 + max(tw_, 1), by + 10 * K), radius=int(5 * K), fill=(43, 212, 107, 255))
            if c['brake']:
                d.rounded_rectangle((bx0, by + 14 * K, bx1, by + 22 * K), radius=int(4 * K), fill=(255, 70, 59, 255))

    # Captions.
    for start, end, sid, c in caps:
        kind = c.get('kind')
        a = ease((f['frame'] - start) / (.3 * FPS)) * ease((end - f['frame']) / (.3 * FPS))
        if kind == 'title':
            draw_title(lay, c, a)
        elif kind == 'verdict':
            draw_verdict(lay, a, (f['frame'] - start) / FPS)
        else:
            draw_caption(lay, c, a)

    # Footer: always say it is a reconstruction.
    d.text((48 * K, H - 46 * K), 'Reconstruction from timing data · not real footage', font=F_REG(22), fill=(225, 230, 236, 170), anchor='lm')
    frosted(img)
    img.alpha_composite(lay)
    return img.convert('RGB')


def draw_caption(lay, c, a):
    if a <= 0:
        return
    CUR_ALPHA[0] = a
    layer = Image.new('RGBA', lay.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, width = 48 * K, W - 96 * K
    lines = wrap(d, fmt(c['text']), F_BOLD(46), width - 64 * K)
    title = fmt(c.get('title', '')).upper()
    h = 56 * K + len(lines) * 58 * K + (62 * K if title else 0)
    y0 = H - 250 * K - h + (1 - a) * 40 * K
    col = rgb(DRV[c['car']]['tag']) if c.get('car') else RED
    panel(d, (x0, y0, x0 + width, y0 + h), radius=26, fill=(12, 16, 22, 165))
    CUR_ALPHA[0] = 1.0
    d.rectangle((x0, y0 + 24 * K, x0 + 8 * K, y0 + h - 24 * K), fill=col)
    y = y0 + 30 * K
    if title:
        d.text((x0 + 36 * K, y + 24 * K), title, font=F_TITLE(54), fill=col, anchor='lm')
        y += 62 * K
    for line in lines:
        d.text((x0 + 36 * K, y + 26 * K), line, font=F_BOLD(46), fill='white', anchor='lm')
        y += 58 * K
    layer.putalpha(Image.eval(layer.getchannel('A'), lambda v: int(v * a)))
    lay.alpha_composite(layer)


def draw_title(lay, c, a):
    layer = Image.new('RGBA', lay.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    grad = Image.linear_gradient('L').resize((W, H)).point(lambda v: int(v * .85))
    shade = Image.new('RGBA', (W, H), (5, 8, 12, 0))
    shade.putalpha(grad)
    layer.alpha_composite(shade)
    y = H * .58
    d.text((60 * K, y), c['kicker'].upper(), font=F_BOLD(34), fill=RED, anchor='ls')
    y += 30 * K
    for line in wrap(d, c['title'].upper(), F_TITLE(132), W - 120 * K):
        y += 128 * K
        d.text((60 * K, y), line, font=F_TITLE(132), fill='white', anchor='ls')
    y += 30 * K
    for line in wrap(d, fmt(c['text']), F_MED(44), W - 120 * K):
        y += 58 * K
        d.text((60 * K, y), line, font=F_MED(44), fill=(225, 230, 236), anchor='ls')
    layer.putalpha(Image.eval(layer.getchannel('A'), lambda v: int(v * a)))
    lay.alpha_composite(layer)


def draw_verdict(lay, a, t):
    v = CFG['verdict']
    layer = Image.new('RGBA', lay.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle((0, 0, W, H), fill=(6, 9, 13, 215))
    x0, width = 60 * K, W - 120 * K
    y = 300 * K
    d.text((x0, y), v['kicker'].upper(), font=F_BOLD(36), fill=RED, anchor='ls')
    for line in wrap(d, v['title'].upper(), F_TITLE(120), width):
        y += 118 * K
        d.text((x0, y), line, font=F_TITLE(120), fill='white', anchor='ls')
    y += 40 * K
    for line in v['lines']:
        for k, part in enumerate(wrap(d, line, F_BOLD(42), width - 40 * K)):
            y += 56 * K
            d.text((x0 + 30 * K, y), part, font=F_BOLD(42), fill=(230, 234, 240), anchor='ls')
            if k == 0:
                d.ellipse((x0, y - 26 * K, x0 + 14 * K, y - 12 * K), fill=RED)
        y += 10 * K
    y += 50 * K
    for k, (code, quote) in enumerate(v['quotes']):
        num = next(n for n, dd in DRV.items() if dd['code'] == code)
        col = rgb(DRV[num]['tag'])
        reveal = ease((t - 1.2 - k * 1.0) / .4)
        if reveal <= 0:
            continue
        lines = wrap(d, quote, F_MED(40), width - 60 * K)
        h = 80 * K + len(lines) * 52 * K
        panel(d, (x0, y, x0 + width, y + h), radius=20, fill=(16, 21, 28, int(235 * reveal)), outline=(*col, int(160 * reveal)))
        d.text((x0 + 28 * K, y + 44 * K), code, font=F_TITLE(46), fill=(*col, int(255 * reveal)), anchor='lm')
        yy = y + 78 * K
        for line in lines:
            d.text((x0 + 28 * K, yy + 20 * K), line, font=F_MED(40), fill=(240, 242, 245, int(255 * reveal)), anchor='lm')
            yy += 52 * K
        y += h + 24 * K
    y += 30 * K
    d.text((x0, y + 30 * K), v['result'], font=F_BOLD(40), fill='white', anchor='lm')
    if t > 3.2:
        cta = v['cta'].upper()
        fnt = F_TITLE(64)
        tw = d.textlength(cta, font=fnt)
        panel(d, (x0, y + 90 * K, x0 + tw + 60 * K, y + 180 * K), radius=24, fill=(*RED, 240), outline=None)
        d.text((x0 + 30 * K, y + 135 * K), cta, font=fnt, fill='white', anchor='lm')
    lines = wrap(d, CFG['credits'], F_REG(24), width)
    yy = H - 110 * K - len(lines) * 32 * K
    for line in lines:
        d.text((x0, yy), line, font=F_REG(24), fill=(200, 206, 214), anchor='lm')
        yy += 32 * K
    layer.putalpha(Image.eval(layer.getchannel('A'), lambda v_: int(v_ * a)))
    lay.alpha_composite(layer)


def main():
    if STILLS:
        out = WORK / 'stills'
        out.mkdir(exist_ok=True)
        for f in frames:
            if f['frame'] in STILLS and (FR / f"{f['frame']:05d}.png").exists():
                draw_frame(f).save(out / f"{f['shot']}_{f['frame']:05d}.png")
                print('still', f['frame'])
        return
    target = ROOT / CFG['data_dir'] / ('mexico2026_t4.preview.mp4' if PREVIEW else 'mexico2026_t4.mp4')
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i, f in enumerate(frames):
        enc.stdin.write(draw_frame(f).tobytes())
        if i % 30 == 0:
            print(f'overlay {i + 1}/{len(frames)}', flush=True)
    enc.stdin.close()
    if enc.wait():
        raise SystemExit('ffmpeg failed')
    print('Saved', target)


if __name__ == '__main__':
    main()
