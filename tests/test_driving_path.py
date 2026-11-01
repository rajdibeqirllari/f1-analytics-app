import unittest
import numpy as np
from services.driving_path import RoadGuide,arc_route,directions


class DrivingPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        theta=np.linspace(0,2*np.pi,241)[:-1]
        inner=np.column_stack([44*np.cos(theta),44*np.sin(theta),np.zeros(len(theta))])
        outer=inner*56/44
        vertices=np.vstack([inner,outer]); n=len(theta)
        triangles=[]
        for i in range(n):
            j=(i+1)%n
            triangles.extend([(i,j,i+n),(j,j+n,i+n)])
        cls.guide=RoadGuide(vertices,np.array(triangles),step=.2)

    def test_arc_parameterization_removes_uneven_source_sampling(self):
        xy=np.array([[0,0],[1,0],[90,0],[100,0]])
        p,points,length=arc_route(xy)
        np.testing.assert_allclose(np.diff(points[:,0]),length/(len(p)-1))
        self.assertEqual(length,100)

    def test_route_preserves_input_and_contains_both_full_footprints(self):
        theta=np.linspace(0,2*np.pi,241)
        reference=np.column_stack([54*np.cos(theta),54*np.sin(theta)])
        original=reference.copy(); route=self.guide.route(reference)
        np.testing.assert_array_equal(reference,original)
        points=np.array(route['xy']); tangent=directions(points)
        side=np.column_stack([-tangent[:,1],tangent[:,0]])
        separation=np.array(route['half_separation'])
        np.testing.assert_allclose(points[0],points[-1])
        self.assertLess(np.max(np.abs(np.diff(separation))),.025)
        for sign in (-1,1):
            for along in (-2.3,3.):
                for lateral in (-1.15,1.15):
                    corner=points+tangent*along+side*(sign*separation+lateral)[:,None]
                    self.assertGreaterEqual(self.guide.clearance(corner).min(),.5)

    def test_incomplete_or_distant_routes_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'complete circuit'):
            self.guide.route(np.array([[0,0],[100,0],[100,100]]))
        theta=np.linspace(0,2*np.pi,241)
        with self.assertRaises(ValueError):
            self.guide.route(np.column_stack([100*np.cos(theta),100*np.sin(theta)]))


if __name__=='__main__': unittest.main()
