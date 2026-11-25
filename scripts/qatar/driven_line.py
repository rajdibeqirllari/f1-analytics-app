"""Median driven line per station (lateral offset, m, left positive) from every clean race lap of 2025 (OpenF1).

Used only to paint where the rubber goes down (the darker line on the asphalt). The road edges never use it.
Note: the feed pulls cars towards one line, so the spread is narrower than the real one; the median is what counts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.qatar.prepare_lusail import openf1, lap_points, smooth_closed  # noqa: E402

LAYOUT = ROOT / 'assets/3d/qatar/lusail_layout.json'


def main():
    d = json.loads(LAYOUT.read_text(encoding='utf-8'))
    c = np.c_[d['centre']['x'], d['centre']['y']]
    n = len(c)
    tan = np.roll(c, -3, 0) - np.roll(c, 3, 0)
    tan /= np.linalg.norm(tan, axis=1)[:, None]
    nor = np.c_[-tan[:, 1], tan[:, 0]]
    _, cars, clean, _ = openf1()
    cloud = np.vstack([lap_points(cars, *k)[0] for k in clean])
    _, idx = cKDTree(c).query(cloud[:, :2])
    lat = np.einsum('ij,ij->i', cloud[:, :2] - c[idx], nor[idx])
    med = np.full(n, np.nan)
    o = np.argsort(idx)
    b = np.searchsorted(idx[o], np.arange(n + 1))
    for i in range(n):
        if b[i + 1] - b[i] > 20:
            med[i] = np.median(lat[o][b[i]:b[i + 1]])
    ok = ~np.isnan(med)
    med = smooth_closed(np.interp(np.arange(n), np.arange(n)[ok], med[ok], period=n), 7)
    d['driven_line'] = np.round(med, 2).tolist()
    LAYOUT.write_text(json.dumps(d), encoding='utf-8')
    print(f'driven line: |offset| median {np.median(np.abs(med)):.2f} m, max {np.abs(med).max():.2f} m')


if __name__ == '__main__':
    main()
