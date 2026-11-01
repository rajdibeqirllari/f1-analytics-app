import unittest
import numpy as np
from services.surface_trail import SurfaceRibbon,DistanceClock


class SurfaceTrailTests(unittest.TestCase):
    def clock(self):
        return DistanceClock({'t':[0.,1.,2.,3.],'speed':[72.,144.,36.,108.]})

    def ribbon(self):
        def pose(p):
            a=p*np.pi*2
            return np.array([25*np.cos(a),25*np.sin(a),.04]),np.array([-np.sin(a),np.cos(a),0.])
        def ground(xy):return np.array([xy[0],xy[1],0.])
        return SurfaceRibbon(pose,ground,[0,.25,.5,.75,1],2*np.pi*25)

    def test_exact_inverse_clock_including_acceleration_and_braking(self):
        clock=self.clock();t=np.linspace(0,3,3001)
        np.testing.assert_allclose(clock.time(clock.progress(t)),t,atol=1e-12)

    def test_head_and_tail_are_exact_car_trajectory_at_same_time(self):
        clock=self.clock();ribbon=self.ribbon()
        for t in np.linspace(.01,3,150):
            vertices,times,alpha=ribbon.frame(clock,t,t)
            center,_=ribbon.pose(float(clock.progress(t)))
            np.testing.assert_allclose(vertices[-2:,:2].mean(axis=0),center[:2],atol=1e-12)
            self.assertAlmostEqual(times[-1],t);self.assertAlmostEqual(alpha[-1],1)
            self.assertTrue((times<=t+1e-12).all());self.assertTrue((times>=max(0,t-.28)-1e-12).all())
            self.assertTrue((np.abs(vertices[:,2]-.002)<1e-12).all())
        self.assertLessEqual(ribbon.metrics['max_curve_chord_error_metres'],.0005)
        self.assertLessEqual(ribbon.metrics['max_spacing_metres'],.25)

    def test_hold_fades_without_overshooting_and_stationary_path_has_no_history(self):
        ribbon=self.ribbon();clock=self.clock()
        vertices,times,alpha=ribbon.frame(clock,3,3.1)
        self.assertLess(alpha.max(),1);self.assertLessEqual(times.max(),3)
        self.assertEqual(len(ribbon.frame(clock,3,3.3)[0]),0)
        self.assertEqual(len(ribbon.frame(clock,0,0)[0]),0)

    def test_same_world_geometry_is_camera_independent_and_road_projection_is_required(self):
        ribbon=self.ribbon();vertices,_,_=ribbon.frame(self.clock(),1.7,1.7)
        original=vertices.copy()
        # No camera/projector is an input to frame generation.
        np.testing.assert_array_equal(ribbon.frame(self.clock(),1.7,1.7)[0],original)
        def missing(xy):raise ValueError('off asphalt')
        with self.assertRaisesRegex(ValueError,'off asphalt'):
            SurfaceRibbon(ribbon.pose,missing,[0,1],200)

    def test_elevated_surface_and_two_ghost_layers_stay_attached(self):
        def pose(p):
            a=p*2*np.pi;x,y=25*np.cos(a),25*np.sin(a)
            return np.array([x,y,.1*x+.05*y+.04]),np.array([-np.sin(a),np.cos(a),0])
        def ground(xy):return np.r_[xy,.1*xy[0]+.05*xy[1]]
        ribbon=SurfaceRibbon(pose,ground,np.linspace(0,1,20),2*np.pi*25)
        for layer in (0,.001):
            vertices,_,_=ribbon.frame(self.clock(),1.6,1.6,layer=layer)
            clearance=vertices[:,2]-(.1*vertices[:,0]+.05*vertices[:,1])
            np.testing.assert_allclose(clearance,.002+layer,atol=1e-12)

    def test_stationary_interval_does_not_create_a_false_moving_trail(self):
        clock=DistanceClock({'t':[0.,1.,2.,3.],'speed':[72.,0.,0.,72.]})
        ribbon=self.ribbon()
        self.assertEqual(len(ribbon.frame(clock,1.5,1.5)[0]),0)
        moving=np.array([.1,.8,2.2,2.9])
        np.testing.assert_allclose(clock.time(clock.progress(moving)),moving,atol=1e-12)
        with self.assertRaises(ValueError):DistanceClock({'t':[0,1],'speed':[float('nan'),72]})
