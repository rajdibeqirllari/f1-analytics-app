"""Original, tileable PBR textures for the Lusail venue and the cars (no photos, no brands).

Every texture is periodic (noise made in the frequency domain), so it tiles without seams. Output:
assets/3d/qatar/textures/*.png|jpg. Run with the project venv:  .venv\\Scripts\\python.exe scripts\\qatar\\make_textures.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets/3d/qatar/textures'
RNG = np.random.default_rng(20261125)


def pnoise(n, beta, seed=None):
    """Periodic 1/f^beta noise in [0, 1]."""
    r = np.random.default_rng(seed) if seed is not None else RNG
    f = np.fft.fftfreq(n)
    fx, fy = np.meshgrid(f, f)
    k = np.sqrt(fx ** 2 + fy ** 2)
    k[0, 0] = 1
    spec = (r.normal(size=(n, n)) + 1j * r.normal(size=(n, n))) / k ** beta
    spec[0, 0] = 0
    a = np.real(np.fft.ifft2(spec))
    return (a - a.min()) / (a.max() - a.min())


def blur_periodic(a, sigma):
    n = a.shape[0]
    f = np.fft.fftfreq(n)
    fx, fy = np.meshgrid(f, f)
    g = np.exp(-2 * (np.pi * sigma) ** 2 * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def normal_from_height(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    nz = 1 / np.sqrt(dx ** 2 + dy ** 2 + 1)
    n = np.dstack([-dx * nz, dy * nz, nz])      # OpenGL convention (+Y up), as glTF expects
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def save(name, arr, q=92):
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    p = OUT / name
    if name.endswith('.jpg'):
        img.save(p, quality=q, optimize=True)
    else:
        img.save(p, optimize=True)
    print(name, img.size, f'{p.stat().st_size / 1024:.0f} KB')


def stones(n, count, rmin, rmax, seed):
    """Periodic aggregate: discs of random size/brightness (height map + albedo jitter)."""
    r = np.random.default_rng(seed)
    h = np.zeros((n, n))
    alb = np.zeros((n, n))
    yy, xx = np.mgrid[0:n, 0:n]
    for _ in range(count):
        cx, cy, rad = r.uniform(0, n), r.uniform(0, n), r.uniform(rmin, rmax)
        x0, x1, y0, y1 = int(cx - rad - 1), int(cx + rad + 2), int(cy - rad - 1), int(cy + rad + 2)
        ys = np.arange(y0, y1) % n
        xs = np.arange(x0, x1) % n
        gx, gy = np.meshgrid(np.arange(x0, x1) - cx, np.arange(y0, y1) - cy)
        d = np.sqrt(gx ** 2 * r.uniform(.6, 1.4) + gy ** 2) / rad
        m = np.clip(1 - d, 0, 1) ** .5
        sub_h = h[np.ix_(ys, xs)]
        sub_a = alb[np.ix_(ys, xs)]
        h[np.ix_(ys, xs)] = np.maximum(sub_h, m * r.uniform(.5, 1))
        bright = r.choice([r.uniform(.42, .62), r.uniform(.16, .30)], p=[.25, .75])
        sub_a[m > 0] = np.where(m[m > 0] > sub_h[m > 0], bright, sub_a[m > 0])
        alb[np.ix_(ys, xs)] = sub_a
    return h, alb


def asphalt():
    n = 1024   # covers 4 m x 4 m -> ~4 mm per texel at onboard height
    h, a = stones(n, 26000, 1.2, 4.2, 1)
    low = pnoise(n, 1.6, 2)
    mid = pnoise(n, 1.1, 3)
    base = 0.22 + 0.05 * (low - .5) + 0.03 * (mid - .5)
    alb = np.where(h > 0.05, base * 0.62 + a * 0.30, base * 0.80)
    alb = alb + (RNG.random((n, n)) - .5) * 0.04
    g = np.clip(alb, 0, 1) * 255
    save('asphalt_albedo.jpg', np.dstack([g * 0.98, g * 0.99, g * 1.02]))
    hh = blur_periodic(h, .8) + 0.15 * (mid - .5)
    save('asphalt_normal.png', normal_from_height(hh, 6.0))
    rough = np.clip(0.88 - 0.18 * (h > 0.4) * a - 0.04 * (low - .5), 0.5, 1)
    occ = np.clip(1 - 0.35 * (1 - blur_periodic(h, 2)) * (h < 0.05), 0.5, 1)
    save('asphalt_orm.png', np.dstack([occ * 255, rough * 255, np.zeros((n, n))]))


def paint():
    """Painted run-off / lines: thin coat over asphalt (aggregate shows through)."""
    n = 512
    h, a = stones(n, 7000, 1.0, 3.2, 4)
    low = pnoise(n, 1.4, 5)
    v = 0.86 + 0.08 * (low - .5) - 0.12 * (h > 0.55) * (1 - a)
    save('paint_mask.jpg', np.dstack([v * 255] * 3))
    save('paint_normal.png', normal_from_height(blur_periodic(h, 1.2) * 0.5, 3.0))


def kerb():
    """One kerb tile (1 m along x 1 m across): raised ribs across the kerb, rounded inner edge."""
    n = 256
    x = np.linspace(0, 1, n, endpoint=False)
    rib = 0.5 + 0.5 * np.cos(2 * np.pi * x * 4)          # 4 ribs per metre (saw-tooth profile approximated)
    h = np.tile(rib[None, :] ** 2, (n, 1)) * 0.6 + pnoise(n, 1.2, 6) * 0.08
    save('kerb_normal.png', normal_from_height(h, 4.0))
    wear = pnoise(n, 1.3, 7)
    save('kerb_wear.jpg', np.dstack([(0.85 + 0.15 * wear) * 255] * 3))


def concrete():
    n = 512
    low, mid = pnoise(n, 1.7, 8), pnoise(n, 1.0, 9)
    v = 0.62 + 0.10 * (low - .5) + 0.05 * (mid - .5) + (RNG.random((n, n)) - .5) * 0.03
    save('concrete_albedo.jpg', np.dstack([v * 250, v * 248, v * 242]))
    save('concrete_normal.png', normal_from_height(mid * 0.6, 2.0))


def fence():
    """Debris fence mesh: diamond wire, 1 tile = 0.5 m x 0.5 m (alpha). Thin wires, mipmapped in the browser."""
    n = 256
    yy, xx = np.mgrid[0:n, 0:n] / n
    a = np.minimum(np.abs(((xx + yy) * 4) % 1 - .5), np.abs(((xx - yy) * 4) % 1 - .5))
    wire = np.clip(1 - (a - 0.045) / 0.04, 0, 1) * 0.92 + 0.10          # wire + mesh density haze (reads as a fence far away)
    rails = ((np.abs(yy - 0.02) < 0.012) | (np.abs(yy - 0.52) < 0.008)).astype(float)
    wire = np.maximum(wire, rails)
    rgba = np.dstack([np.full((n, n), 150), np.full((n, n), 155), np.full((n, n), 160), wire * 235])
    save('fence_rgba.png', rgba)


def carbon():
    """2x2 twill weave, 1 tile = 4 cm. Albedo almost black, normal + roughness give the weave under light."""
    n = 512
    tows = 16
    yy, xx = np.mgrid[0:n, 0:n] / n * tows
    i, j = np.floor(xx).astype(int), np.floor(yy).astype(int)
    over = ((i + j) // 2) % 2 == 0           # twill: shifts by one each row, two over two under
    fx, fy = xx % 1, yy % 1
    hw = np.where(over, np.sin(np.pi * fy), np.sin(np.pi * fx))
    h = hw * 0.8 + pnoise(n, 1.0, 10) * 0.05
    alb = 0.07 + 0.025 * np.where(over, 1, 0) + 0.01 * pnoise(n, 1.5, 11)
    save('carbon_albedo.jpg', np.dstack([alb * 255, alb * 255, alb * 262]))
    save('carbon_normal.png', normal_from_height(h, 2.5))
    rough = np.where(over, 0.32, 0.42)
    save('carbon_orm.png', np.dstack([np.full((n, n), 255), rough * 255, np.zeros((n, n))]))


def facade():
    """Pit building glass: 8 m bays (one garage), two glass storeys, mullions every 1.6 m. RGB + emissive mask."""
    w, hgt = 1024, 512   # 16 m wide (two bays) x 8 m tall per tile
    img = np.zeros((hgt, w, 3))
    em = np.zeros((hgt, w))
    img[:] = (205, 208, 210)                    # white cladding
    for storey, (y0, y1) in enumerate(((40, 220), (280, 470))):
        img[y0:y1] = (38, 52, 64)              # glass
        r = np.random.default_rng(12 + storey)
        for bx in range(0, w, 51):              # 1.6 m panels
            lit = r.random() < 0.7
            if lit:
                img[y0 + 4:y1 - 4, bx + 3:bx + 48] = (150, 160, 170)
                em[y0 + 4:y1 - 4, bx + 3:bx + 48] = r.uniform(.5, 1)
            img[y0:y1, bx:bx + 3] = (175, 178, 182)
    img[:, ::512][:, :] = (120, 120, 125)
    save('facade_albedo.jpg', img)
    save('facade_emissive.jpg', np.dstack([em * 255, em * 240, em * 220]))


def seats():
    """Grandstand rows: 0.8 m rows, seats 0.5 m (maroon + white pattern, no lettering). 1 tile = 4 m x 4 m."""
    n = 512
    yy, xx = np.mgrid[0:n, 0:n]
    row = (yy // 102) % 2
    seat = ((xx // 64) % 2 == 0)
    col = np.where(seat[..., None], np.array([132, 24, 58]), np.array([108, 18, 46]))
    col = np.where((yy % 102 < 18)[..., None], np.array([60, 60, 64]), col)
    save('seats_albedo.jpg', col + row[..., None] * 6)


def crowd():
    """Distant crowd: speckle of muted colours on dark (reads as people at 50 m+). 1 tile = 8 m x 4 m."""
    w, h = 512, 256
    r = np.random.default_rng(13)
    pal = np.array([[230, 230, 228], [40, 40, 44], [140, 30, 50], [30, 60, 120], [200, 170, 60], [90, 90, 96], [190, 120, 100]])
    img = np.full((h, w, 3), 28.0)
    for _ in range(5200):
        x, y = r.integers(0, w - 4), r.integers(0, h - 6)
        c = pal[r.integers(0, len(pal))] * r.uniform(.6, 1.0)
        img[y:y + 6, x:x + 4] = c
        img[y - 3 if y > 3 else y:y, x + 1:x + 3] = (180, 140, 120)
    save('crowd_albedo.jpg', img)


def sand():
    n = 512
    low, mid = pnoise(n, 1.8, 14), pnoise(n, 0.9, 15)
    v = 0.68 + 0.12 * (low - .5) + 0.06 * (mid - .5)
    save('sand_albedo.jpg', np.dstack([v * 228, v * 196, v * 150]))


def turf():
    """Artificial grass (Lusail lines the run-off with it): short blades, slightly striped."""
    n = 512
    mid, hi = pnoise(n, 0.8, 16), RNG.random((n, n))
    stripe = 0.5 + 0.5 * np.sin(np.linspace(0, 8 * np.pi, n, endpoint=False))[None, :]
    v = 0.55 + 0.15 * (mid - .5) + 0.12 * (hi - .5) + 0.05 * stripe
    save('turf_albedo.jpg', np.dstack([v * 70, v * 128, v * 52]))


if __name__ == '__main__':
    asphalt(); paint(); kerb(); concrete(); fence(); carbon(); facade(); seats(); crowd(); sand(); turf()
