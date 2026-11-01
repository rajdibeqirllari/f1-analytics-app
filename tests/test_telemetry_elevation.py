import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from scipy.interpolate import LinearNDInterpolator

from services.procedural_circuit import build_circuit, strip_mesh, telemetry_elevation
from services.circuit_scenery import scenery_plan


class TelemetryElevationTests(unittest.TestCase):
    def reference(self):
        p=np.linspace(0,1,720);angle=p*2*np.pi
        return np.column_stack([p,400*np.cos(angle),600*np.sin(angle),120+30*np.sin(angle)])

    def test_preserves_metres_relative_grade_and_source(self):
        reference=self.reference();original=reference.copy()
        mesh,route=build_circuit(SimpleNamespace(track=reference))
        elevation=mesh['elevation'];z=np.asarray(route['elevation_profile']['z'])
        self.assertEqual(elevation['status'],'telemetry-estimated')
        self.assertFalse(elevation['surveyed'])
        self.assertLess(abs(np.ptp(z)-60),.2)
        self.assertLess(abs(np.median(z)),.01)
        self.assertEqual(z[0],z[-1])
        self.assertLess(elevation['max_grade'],.10)
        np.testing.assert_array_equal(reference,original)
        rings=np.asarray(mesh['vertices']).reshape(4,-1,3)
        for ring in rings:
            np.testing.assert_allclose(ring[:,2],z)

    def test_missing_drift_or_spikes_fall_back_without_fabricated_hills(self):
        reference=self.reference();points=reference[:,1:3]
        cases=[]
        missing=reference.copy();missing[:,3]=0;cases.append(missing)
        drift=reference.copy();drift[:,3]+=np.linspace(0,10,len(drift));cases.append(drift)
        spike=reference.copy();spike[300,3]+=80;cases.append(spike)
        for trace in cases:
            with self.subTest(trace_range=np.ptp(trace[:,3])):
                heights,metadata=telemetry_elevation(trace,points)
                self.assertEqual(metadata['status'],'flat-fallback')
                self.assertTrue(metadata['reason'])
                self.assertEqual(np.max(np.abs(heights)),0)

    def test_terrain_stays_below_asphalt_between_anchors(self):
        mesh,route=build_circuit(SimpleNamespace(track=self.reference()))
        terrain=np.asarray(mesh['terrain']['vertices'])
        sample=LinearNDInterpolator(terrain[:,:2],terrain[:,2])
        road=np.asarray(mesh['vertices']).reshape(4,-1,3)
        midpoints=(road[:,:-1]+road[:,1:])*.5
        clearance=midpoints[:,:,2]-sample(midpoints[:,:,:2])
        self.assertTrue(np.isfinite(clearance).all())
        self.assertGreater(np.min(clearance),.12)
        self.assertLess(len(terrain),20000)

    def test_scenery_uses_matching_ground_heights(self):
        mesh,route=build_circuit(SimpleNamespace(track=self.reference()))
        terrain=np.asarray(mesh['terrain']['vertices'])
        sample=LinearNDInterpolator(terrain[:,:2],terrain[:,2])
        plan=scenery_plan(route,'Belgian Grand Prix')
        self.assertEqual(len(plan['heights']),len(plan['points']))
        self.assertGreater(np.ptp(plan['heights']),59)
        self.assertTrue(plan['trees'])
        for item in plan['trees']+plan['structures']:
            expected=float(sample(item['center'])[0])
            self.assertAlmostEqual(item['base_z'],expected,places=7)

    def test_flat_strip_default_remains_compatible(self):
        road=strip_mesh(self.reference()[:,1:3])
        self.assertEqual(np.ptp(np.asarray(road['vertices'])[:,2]),0)
        with self.assertRaisesRegex(ValueError,'Road heights'):
            strip_mesh(self.reference()[:,1:3],heights=[0])

    def test_unsafe_overlapping_heightfield_has_an_explicit_flat_fallback(self):
        with patch('services.procedural_circuit.terrain_clearance',return_value=-1.):
            mesh,route=build_circuit(SimpleNamespace(track=self.reference()))
        self.assertEqual(mesh['elevation']['status'],'flat-fallback')
        self.assertIn('overlapping',mesh['elevation']['reason'])
        self.assertNotIn('terrain',mesh)
        self.assertEqual(np.max(np.abs(route['elevation_profile']['z'])),0)


if __name__=='__main__':
    unittest.main()
