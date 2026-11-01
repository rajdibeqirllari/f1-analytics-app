import unittest
import numpy as np
from services.render_stability import ground_mesh


class RenderStabilityTests(unittest.TestCase):
    def test_tiled_ground_covers_road_and_stays_below_it(self):
        road=np.array([[-1000,-2000,0],[1000,2000,0],[0,0,0]])
        vertices,faces=ground_mesh(road)
        vertices=np.asarray(vertices)
        self.assertTrue(np.allclose(vertices[:,2],-.12))
        self.assertTrue((vertices[:,:2].min(axis=0)<=road[:,:2].min(axis=0)-1200).all())
        self.assertTrue((vertices[:,:2].max(axis=0)>=road[:,:2].max(axis=0)+1200).all())
        self.assertGreater(len(faces),100)
        for face in faces:
            quad=vertices[list(face)]
            self.assertLessEqual(np.max(np.linalg.norm(np.diff(np.vstack([quad,quad[0]]),axis=0),axis=1)),80.001)

    def test_invalid_terrain_rejected(self):
        with self.assertRaises(ValueError):ground_mesh([[0,0,float('nan')]])
