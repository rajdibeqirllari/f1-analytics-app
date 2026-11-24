"""3D Broadcast on the Replay page: native positions must line up with the replay clock, or the view says so;
and the estimated racing line takes corners outside-apex-outside."""
import math
import unittest
from unittest import mock

import numpy as np

from services import replay_scene as rp
from tests.test_scene3d import oval


def fake_payload(rate=1.0, duration=120.0):
    """A replay payload of three cars lapping a 1 km circle, sampled at `rate` Hz (OpenF1 units: 1/10 m)."""
    R = 1000 / (2 * math.pi) * 10
    def xy(code, t):
        a = (t * 60 / 1000 + {'AAA': 0, 'BBB': .02, 'CCC': .5}[code]) * 2 * math.pi
        return R * math.cos(a), R * math.sin(a)
    frames = []
    for t in np.arange(0, duration, 1 / rate):
        frames.append(dict(t=float(t), lap=1 + int(t // 17), drivers={c: dict(zip(('x', 'y'), xy(c, t))) for c in ('AAA', 'BBB', 'CCC')}))
    centre = [list(xy('AAA', t)) for t in np.linspace(0, 1000 / 60, 300, endpoint=False)]
    return dict(meta=dict(year=2026, event='Test GP', session='R', source='OpenF1', sample_rate_hz=rate),
                drivers={c: dict(name=c, team='T', number=str(i), color='#ffffff') for i, c in enumerate(('AAA', 'BBB', 'CCC'))},
                track=dict(centerline=centre), frames=frames), xy


class ReplayScene(unittest.TestCase):
    def native(self, xy, offset, rate=4.0):
        t = np.arange(-20, 140, 1 / rate)
        return {c: (t + offset, *[np.array(v) for v in zip(*[xy(c, s) for s in t])], np.zeros(len(t))) for c in ('AAA', 'BBB', 'CCC')}

    def test_alignment_check_accepts_the_right_offset_and_rejects_a_wrong_one(self):
        payload, xy = fake_payload()
        native = self.native(xy, 5000.0)
        self.assertLess(rp._check(payload, native, 5000.0), 0.5)
        self.assertGreater(rp._check(payload, native, 5003.0), rp.ALIGN_TOLERANCE_M)

    def test_native_positions_are_used_on_the_replay_clock(self):
        payload, xy = fake_payload()
        native = self.native(xy, 5000.0, rate=8.0)
        with mock.patch.object(rp, '_openf1_native', return_value=(native, 5000.0, ('AAA', 5000.0, 1000 / 60), 'test feed')):
            out = rp.build(payload)
        self.assertEqual(out['label'], 'Recorded positions')
        car = out['rec'].cars['AAA']
        self.assertAlmostEqual(float(car['t'][0]), -20.0, places=3)        # payload seconds, not epoch
        self.assertGreater(out['rec'].rate, 7.5)

    def test_misaligned_or_missing_native_data_falls_back_to_replay_frames(self):
        payload, xy = fake_payload()
        native = self.native(xy, 5000.0)
        with mock.patch.object(rp, '_openf1_native', return_value=(native, 5004.0, ('AAA', 5000.0, 1000 / 60), 'test feed')):
            out = rp.build(payload)
        self.assertIn('coarse', out['label'])
        self.assertIn('did not line up', out['detail'])
        with mock.patch.object(rp, '_openf1_native', side_effect=RuntimeError('offline')):
            self.assertIn('coarse', rp.build(payload)['label'])

    def test_racing_line_goes_wide_before_a_hairpin_and_clips_the_apex(self):
        tr = oval(radius=40)            # anticlockwise: left (positive) is the inside
        at = lambda d: float(tr.line[np.argmin(abs(tr.s - d))])
        self.assertLess(at(330), -3.0)          # outside on the approach
        self.assertGreater(at(463), 5.0)        # inside at the apex (mid-hairpin)
        self.assertLess(at(570), -3.0)          # back out on the exit
        self.assertLessEqual(np.abs(tr.line).max(), 5.4 + 1e-6)


if __name__ == '__main__':
    unittest.main()
