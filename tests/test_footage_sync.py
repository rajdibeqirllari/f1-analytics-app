"""Engine-sound sync: synthetic onboard clips with a known lap start."""
import unittest

import numpy as np
import pandas as pd

from services import footage_sync as fs


def _session(seed, lap_len=94.0, pre=40.0, post=30.0):
    rng = np.random.default_rng(seed)
    dt = 0.002
    t = np.arange(0, pre + lap_len + post, dt)
    rpm = np.empty_like(t); gear = np.empty_like(t); speed = np.empty_like(t)
    i, g, r, v = 0, 3, 9500.0, 120.0
    while i < len(t):
        acc = rng.random() < .6
        for _ in range(int((rng.uniform(3, 9) if acc else rng.uniform(1.5, 3.5)) / dt)):
            if i >= len(t):
                break
            if acc:
                r += 2600 / (g * .55) * dt * rng.uniform(.9, 1.1); v += 54 / g * dt
                if r > 11800 and g < 8:
                    g += 1; r -= 1500 + rng.uniform(-150, 150)
                r = min(r, 12100)
            else:
                v = max(80, v - 180 * dt); r -= 1800 * dt
                if r < 9200 and g > 3:
                    g -= 1; r += 1600
            rpm[i], gear[i], speed[i] = r, g, v; i += 1
    ts = np.cumsum(rng.uniform(.2, .3, size=int(t[-1] / .2))); ts = ts[ts < t[-1]]
    idx = (ts / dt).astype(int)
    base = pd.Timestamp('2026-11-01 20:00:00', tz='UTC')
    full = pd.DataFrame(dict(date=[(base + pd.Timedelta(seconds=float(x))).isoformat() for x in ts], session_time=ts,
                             rpm=rpm[idx], gear=gear[idx], speed_kmh=speed[idx], throttle_pct=100.0, brake_active=False))
    lap = full[(full.session_time >= pre) & (full.session_time <= pre + lap_len)].copy()
    first = lap.iloc[[0]].copy(); first['session_time'] = pre; first['date'] = (base + pd.Timedelta(seconds=pre)).isoformat()
    return t, rpm, full, pd.concat([first, lap]).reset_index(drop=True), pre


def _audio(t, rpm, start, length, noise, seed):
    rng = np.random.default_rng(seed)
    tt = np.arange(0, length, 1 / fs.SR) + start
    ph = 2 * np.pi * np.cumsum(np.interp(tt, t, rpm) / 60 * 3) / fs.SR
    sig = sum(.8 ** k * np.sin(k * ph + rng.uniform(0, 6)) for k in range(1, 7))
    sig = sig / np.abs(sig).max() + noise * rng.normal(size=len(tt))
    return (sig / np.abs(sig).max()).astype(np.float32)


class FootageSyncTest(unittest.TestCase):
    def test_finds_lap_start_from_engine_sound(self):
        for seed, start, noise in [(1, 33.7, .3), (2, 38.0, .6), (4, 41.2, .9)]:
            t, rpm, full, lap, pre = _session(seed)
            out = fs.estimate_offset(fs.pitch_track(_audio(t, rpm, start, 95, noise, seed)), fs.build_telemetry(lap, full), 95)
            self.assertLess(abs(out['lap_start_in_clip'] - (pre - start)), 0.1, seed)
            self.assertEqual(out['level'], 'strong')

    def test_harmonic_hops_are_folded_back(self):
        f = np.log(np.r_[np.full(50, 100.0), np.full(80, 200.0), np.full(50, 100.0), np.full(40, 85.0)])
        out = fs._unwrap_harmonic_jumps(f)
        self.assertLess(np.ptp(out[:180]), 0.01)          # the ×2 hop is undone
        self.assertAlmostEqual(out[-1] - out[0], np.log(.85), places=3)  # a real pitch drop is kept

    def test_clip_of_another_lap_is_flagged_weak(self):
        t, rpm, full, lap, _ = _session(1)
        t2, rpm2, *_ = _session(99)
        out = fs.estimate_offset(fs.pitch_track(_audio(t2, rpm2, 35, 95, .5, 3)), fs.build_telemetry(lap, full), 95)
        self.assertEqual(out['level'], 'weak')

    def test_noise_without_an_engine_is_not_trusted(self):
        *_, full, lap, _ = _session(1)
        for noise in (np.random.default_rng(0).normal(size=fs.SR * 40), np.cumsum(np.random.default_rng(1).normal(size=fs.SR * 40))):
            noise = (noise / np.abs(noise).max()).astype(np.float32)
            try:
                out = fs.estimate_offset(fs.pitch_track(noise), fs.build_telemetry(lap, full), 40)
            except ValueError:
                continue  # too unclear to analyse at all
            self.assertEqual(out['level'], 'weak')

    def test_hud_position_stays_inside_the_frame(self):
        self.assertEqual(fs.hud_position('Bottom left', (1920, 1080), (460, 460), 0, 0), (77, 566))
        self.assertEqual(fs.hud_position('Custom', (1080, 1920), (460, 460), 5000, -20), (620, 0))


if __name__ == '__main__':
    unittest.main()
