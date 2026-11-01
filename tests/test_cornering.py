import unittest
import numpy as np
from services.cornering import curvature,steering_angle,cornering_route
from services.procedural_circuit import strip_mesh


class CorneringTests(unittest.TestCase):
    def test_steering_follows_bend_direction_and_is_bounded(self):
        p=np.linspace(0,1,401);a=p*2*np.pi
        xy=np.column_stack([50*np.cos(a),50*np.sin(a)])
        np.testing.assert_allclose(curvature(xy),1/50,rtol=.001)
        self.assertAlmostEqual(steering_angle(p,xy,.4),np.arctan(3.4/50),places=5)
        self.assertLess(steering_angle(p,xy[::-1],.4),0)

    def test_shared_cornering_path_is_closed_bounded_and_keeps_road_unchanged(self):
        p=np.linspace(0,1,801);a=p*2*np.pi
        xy=np.column_stack([90*np.cos(a),55*np.sin(a)])
        mesh=strip_mesh(xy);old=np.array(mesh['vertices']).copy()
        route={'progress':p.tolist(),'xy':xy.tolist(),'half_separation':[1.25]*len(p)}
        new=cornering_route(route,mesh)
        self.assertFalse(new['cornering']['measured_racing_lines'])
        self.assertGreater(new['cornering']['max_offset_metres'],.1)
        self.assertLessEqual(new['cornering']['max_offset_metres'],2.4)
        np.testing.assert_array_equal(mesh['vertices'],old)
        np.testing.assert_allclose(new['xy'][0],new['xy'][-1])
        self.assertTrue(np.all(np.diff(new['progress'])>0))
        np.testing.assert_array_equal(new['centerline_xy'],xy)
        self.assertEqual(set(new['half_separation']),{0.})

    def test_onboard_wider_estimated_line_stays_bounded(self):
        p=np.linspace(0,1,801);a=p*2*np.pi
        xy=np.column_stack([90*np.cos(a),55*np.sin(a)])
        mesh=strip_mesh(xy)
        route={'progress':p.tolist(),'xy':xy.tolist(),'half_separation':[0.]*len(p)}
        new=cornering_route(route,mesh,max_offset=3.8)
        self.assertFalse(new['cornering']['measured_racing_lines'])
        self.assertLessEqual(new['cornering']['max_offset_metres'],3.8)
        np.testing.assert_allclose(new['xy'][0],new['xy'][-1])
