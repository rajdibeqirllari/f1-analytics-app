"""Lusail venue for the 3D Broadcast: geometry, frames and the estimated racing line (no network needed)."""
import json
import unittest
from pathlib import Path

import numpy as np

from services import scene3d as sc

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / 'assets/3d/qatar/lusail_layout.json'
MANIFEST = ROOT / 'frontend/public/venues/lusail/manifest.json'


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(LAYOUT.read_text(encoding='utf-8'))

    def test_length_matches_fia(self):
        self.assertAlmostEqual(self.d['length'], 5419.0, delta=5419.0 * 0.002)   # FIA map: 5.419 km

    def test_clockwise_and_sixteen_corners_in_fia_order(self):
        x, y = np.array(self.d['centre']['x']), np.array(self.d['centre']['y'])
        area = 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)
        self.assertLess(area, 0)
        c = self.d['landmarks']['corners']
        self.assertEqual([k['dir'] for k in c], list('RLRRRLRLRLLRRRLR'))
        self.assertEqual([k['station'] for k in c], sorted(k['station'] for k in c))

    def test_edges_are_plausible_widths(self):
        w = np.array(self.d['edges']['left']) + np.array(self.d['edges']['right'])
        self.assertTrue(10.0 < np.median(w) < 14.0)
        self.assertGreater(w.min(), 8.0)

    def test_grid_slots_eight_metres(self):
        st = [g['station'] for g in self.d['landmarks']['grid']]
        self.assertAlmostEqual(float(np.median(-np.diff(st))), 8.0, delta=0.6)
        self.assertGreater(self.d['landmarks']['start_line'], st[0])


class OutlineTests(unittest.TestCase):
    def test_bundled_outline_keeps_f1_frame_and_elevation(self):
        tr = sc.track_from_outline(sc._bundled_outline('Qatar Grand Prix'))
        self.assertIsNotNone(tr.frame)
        self.assertGreater(float(tr.z.max() - tr.z.min()), 2.0)          # Lusail varies ~4 m
        self.assertEqual(tr.payload()['frame'], tr.frame)

    def test_racing_line_stays_inside_the_real_edges(self):
        o = sc._bundled_outline('Qatar Grand Prix')
        tr = sc.track_from_outline(o)
        x, y = np.array(o['x']) / 10, np.array(o['y']) / 10
        x, y = x - x.mean(), y - y.mean()
        i = np.argmin((tr.x[:, None] - x[None, :]) ** 2 + (tr.y[:, None] - y[None, :]) ** 2, axis=1)
        left, right = np.array(o['edges']['left'])[i], np.array(o['edges']['right'])[i]
        self.assertTrue(np.all(tr.line <= left - 1.2))
        self.assertTrue(np.all(tr.line >= -(right - 1.2)))

    def test_rotated_outline_has_no_frame(self):
        o = dict(sc._bundled_outline('Qatar Grand Prix'), rotation=12.0)
        self.assertIsNone(sc.track_from_outline(o).frame)

    def test_track_without_frame_or_edges_unchanged(self):
        t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
        tr = sc.Track(500 * np.cos(t), 300 * np.sin(t), None, source='ellipse')
        self.assertIsNone(tr.payload()['frame'])
        self.assertLessEqual(float(np.abs(tr.line).max()), sc.LINE_HALF_WIDTH + 1e-9)


class ManifestTests(unittest.TestCase):
    def test_manifest_matches_layout_frame(self):
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        d = json.loads(LAYOUT.read_text(encoding='utf-8'))
        self.assertEqual(m['z_offset'], d['z_offset'])
        # the asset centreline + origin is the layout centreline (same F1 frame)
        self.assertAlmostEqual(m['centre']['x'][0] + m['origin'][0], d['centre']['x'][0], places=1)
        self.assertAlmostEqual(m['centre']['y'][0] + m['origin'][1], d['centre']['y'][0], places=1)
        self.assertTrue((MANIFEST.parent / m['glb']).is_file())
        self.assertGreater(len(m['instances']['poles']), 100)

    def test_exact_placement_arithmetic(self):
        """scene = F1 - frame and asset = F1 - origin  =>  asset = scene + frame - origin (venue.ts place())."""
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        f1 = np.array([1234.5, -678.9])
        frame = np.array([165.469, 347.459])
        scene = f1 - frame
        asset = scene + frame - np.array(m['origin'])
        np.testing.assert_allclose(asset, f1 - np.array(m['origin']))


if __name__ == '__main__':
    unittest.main()
