import unittest
import numpy as np
from scipy.spatial import cKDTree
from services.circuit_scenery import scenery_profile,scenery_plan


class CircuitSceneryTests(unittest.TestCase):
    def route(self):
        a=np.linspace(0,2*np.pi,900)
        return {'xy':np.column_stack([400*np.cos(a),650*np.sin(a)]).tolist()}

    def test_venue_profiles_are_distinct(self):
        self.assertEqual(scenery_profile('Australian Grand Prix')['kind'],'parkland')
        self.assertEqual(scenery_profile('Belgian Grand Prix')['kind'],'woodland')
        self.assertEqual(scenery_profile('Bahrain Grand Prix')['kind'],'desert')
        self.assertEqual(scenery_profile('Monaco Grand Prix')['kind'],'city')
        self.assertNotEqual(scenery_profile('Bahrain Grand Prix')['ground'],scenery_profile('Australian Grand Prix')['ground'])

    def test_deterministic_safe_and_bounded(self):
        route=self.route();p=scenery_plan(route,'Australian Grand Prix')
        self.assertEqual(p,scenery_plan(route,'Australian Grand Prix'))
        self.assertLessEqual(len(p['trees']),650)
        tree=cKDTree(np.asarray(route['xy']))
        for item in p['trees']:
            self.assertGreaterEqual(tree.query(item['center'])[0],p['road_half']+item['radius']+7)
        for item in p['structures']:
            self.assertGreaterEqual(tree.query(item['center'])[0],p['road_half']+23)
        self.assertIsNotNone(p['lake'])
        self.assertGreaterEqual(tree.query(p['lake']['center'])[0],p['lake']['radius']+p['road_half']+18)

    def test_no_lake_for_woodland_or_unknown_circuit(self):
        self.assertIsNone(scenery_plan(self.route(),'Belgian Grand Prix')['lake'])
        self.assertIsNone(scenery_plan(self.route(),'Unlisted Grand Prix')['lake'])

    def test_uses_road_center_not_ghost_offset(self):
        route=self.route();route['centerline_xy']=route['xy'];route['xy']=[[10000,10000]]*900
        plan=scenery_plan(route,'Australian Grand Prix')
        self.assertLess(np.max(plan['points']),1000)

    def test_invalid_route_rejected(self):
        with self.assertRaisesRegex(ValueError,'centerline'):
            scenery_plan({'xy':[[0,0]]*20},'Australian Grand Prix')
