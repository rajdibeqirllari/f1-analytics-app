"""Reconstructed racing lines (lateral placement only) and replay team-radio timing."""
import unittest

import numpy as np

from services import racing_lines as rl
from services import scene3d as sc


def oval():
    t = np.linspace(0, 2 * np.pi, 600, endpoint=False)
    return sc.Track(900 * np.cos(t), 400 * np.sin(t), None, source='oval')


class ReconstructTests(unittest.TestCase):
    def setUp(self):
        self.tr = oval()

    def _run(self, S, LR=None, keep=None, step=0.25):
        C, K = S.shape
        times = np.arange(K) * step
        LR = np.zeros_like(S) if LR is None else LR
        keep = np.zeros(S.shape, bool) if keep is None else keep
        n = len(self.tr.x)
        return rl.reconstruct(times, S, LR, keep, self.tr.s, self.tr.length, rl._curvature(self.tr.x, self.tr.y),
                              np.full(n, 7.0), np.full(n, 7.0), step=step)

    def test_timing_is_never_touched(self):
        # only a lateral offset comes back: the along-track inputs are not modified
        K = 200
        S = np.vstack([np.linspace(100, 600, K), np.linspace(102, 590, K)])
        S0 = S.copy()
        o, q, meta = self._run(S)
        np.testing.assert_array_equal(S, S0)
        self.assertEqual(o.shape, S.shape)

    def test_side_by_side_cars_are_separated_and_hold_their_side(self):
        K = 240
        a = np.linspace(100, 1300, K)
        b = a + np.linspace(-15, 15, K)          # b passes a over 60 s
        o, q, _ = self._run(np.vstack([a, b]))
        ds = b - a
        overlap = np.abs(ds) < rl.CAR_L
        sep = np.abs(o[0] - o[1])
        self.assertTrue(np.all(sep[overlap] >= rl.CAR_W))            # footprints never intersect
        sides = np.sign(o[0] - o[1])[overlap]
        self.assertEqual(len(set(sides.tolist())), 1)                 # one side for the whole encounter
        self.assertTrue(np.all(np.abs(o) <= 7.0 - rl.EDGE_MARGIN + 1e-6))

    def test_pit_lane_and_trusted_samples_keep_raw_position(self):
        K = 120
        a = np.linspace(100, 400, K)
        S = np.vstack([a, a + 2])
        keep = np.zeros(S.shape, bool)
        keep[1] = True
        o, q, _ = self._run(S, keep=keep)
        self.assertTrue(np.all(o[1] == 0))

    def test_grid_is_staggered_by_slot(self):
        # 6 stationary cars 8 m apart (one slot vacant), then everybody launches
        K = 400
        slots = [0, 1, 2, 4, 5, 6]            # slot 3 vacant
        S = np.zeros((6, K))
        for i, sl in enumerate(slots):
            base = 300 - 8 * sl
            S[i] = base
            S[i, 200:] = base + 0.5 * 4 * (np.arange(K - 200) * 0.25) ** 2 / 4
        o, q, meta = self._run(S)
        self.assertIsNotNone(meta['launch'])
        k = 100
        sides = np.sign(o[:, k])
        for i, sl in enumerate(slots):
            self.assertEqual(sides[i], sides[0] * (1 if sl % 2 == 0 else -1))
        self.assertTrue(np.all(q[:, k] & 4))


class RadioClockTests(unittest.TestCase):
    def test_replay_radio_maps_to_payload_seconds(self):
        from unittest import mock
        from services import replay_scene as rs
        item = dict(radio_clock=dict(offset=1_000_000.0, session_key=1, numbers={'4': 'NOR'}))
        payload = dict(frames=[dict(t=0.0), dict(t=500.0)], drivers={'NOR': dict(color='#F47600')})
        rows = [dict(date='1970-01-12T13:48:40+00:00', driver_number=4, recording_url='x.mp3')]   # 1_000_120 s
        with mock.patch('services.openf1_comparison.historical', return_value=rows):
            out = rs.radio_events(item, payload)
        self.assertEqual(len(out['events']), 1)
        self.assertAlmostEqual(out['events'][0]['t'], 120.0, places=3)
        self.assertEqual(out['events'][0]['code'], 'NOR')

    def test_fastf1_replays_report_no_radio(self):
        from services import replay_scene as rs
        out = rs.radio_events(dict(radio_clock=None), dict(frames=[]))
        self.assertEqual(out['events'], [])
        self.assertTrue(out['reason'])


if __name__ == '__main__':
    unittest.main()
