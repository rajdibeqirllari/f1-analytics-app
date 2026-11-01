import unittest
import numpy as np

from scripts.cinematic_math import chase_rig, smooth_signal, trail_opacity, project_cars, motion_progress, ghost_lane_side


class CinematicTests(unittest.TestCase):
    def test_ghost_lanes_match_card_order_in_rear_chase_view(self):
        for size in ((720,1280),(1280,720)):
            for angle in np.linspace(-np.pi,np.pi,9):
                heading=np.array([np.cos(angle),np.sin(angle),0.])
                lateral=np.array([-heading[1],heading[0],0.])
                center=np.arange(24)[:,None]*heading
                positions=np.stack([center+lateral*ghost_lane_side(i)*1.25 for i in range(2)],axis=1)
                original=positions.copy()
                tangents=np.broadcast_to(heading,positions.shape).copy()
                location,target,_,_=chase_rig(positions,tangents,24,size=size)
                projected=project_cars(positions,tangents,location,target,size)
                x=projected[:,:,:,0].mean(axis=2)
                self.assertTrue(np.all(x[:,0]<x[:,1]))
                np.testing.assert_array_equal(positions,original)

    def test_motion_matches_speed_integral_anchors_and_official_endpoints(self):
        samples={'t':[0.,1.,3.], 'speed':[36.,72.,36.], 'progress':[0.,1/3,1.]}
        np.testing.assert_allclose(motion_progress(samples,samples['t']),samples['progress'])
        self.assertAlmostEqual(float(motion_progress(samples,.5)),6.25/45)
        np.testing.assert_allclose(motion_progress(samples,[-1,4]),[0,1])
        self.assertEqual(samples['speed'],[36.,72.,36.])

    def test_motion_is_forward_continuous_and_independent_of_frame_rate(self):
        samples={'t':[0.,1.,3.], 'speed':[36.,72.,36.]}
        time=np.linspace(0,3,1001)
        self.assertTrue(np.all(np.diff(motion_progress(samples,time))>0))
        epsilon=1e-5
        left=(motion_progress(samples,1)-motion_progress(samples,1-epsilon))/epsilon
        right=(motion_progress(samples,1+epsilon)-motion_progress(samples,1))/epsilon
        self.assertAlmostEqual(left,right,places=5)
        np.testing.assert_allclose(motion_progress(samples,np.arange(91)/30)[::2],
                                   motion_progress(samples,np.arange(46)/15))

    def rig_fixture(self, fps=24):
        time=np.arange(fps*4)/fps
        center=np.column_stack([time*60, np.zeros(len(time)), np.zeros(len(time))])
        positions=np.stack([center+[0,-1.25,0],center+[0,1.25,0]],axis=1)
        angles=.08*np.sin(time*2*np.pi*8)
        tangents=np.stack([np.column_stack([np.cos(angles),np.sin(angles),np.zeros(len(time))])]*2,axis=1)
        return positions,tangents

    def test_constant_signal_and_single_frame_are_preserved(self):
        for length in (1,100):
            original=np.ones((length,3))*7
            np.testing.assert_allclose(smooth_signal(original,24,.25),original)
        with self.assertRaises(ValueError): smooth_signal([np.nan],24,.25)

    def test_camera_damps_heading_jitter_without_changing_car_samples(self):
        positions,tangents=self.rig_fixture()
        original=positions.copy()
        location,target,side,zoom=chase_rig(positions,tangents,24)
        np.testing.assert_array_equal(positions,original)
        raw_yaw=np.arctan2(tangents[:,0,1],tangents[:,0,0])
        smoothed_yaw=np.arctan2(-side[:,0],side[:,1])
        self.assertLess(np.std(np.diff(smoothed_yaw)),np.std(np.diff(raw_yaw))*.2)
        self.assertTrue(np.isfinite(location).all()); self.assertTrue(np.isfinite(target).all())
        np.testing.assert_allclose(zoom,1.)

    def test_heading_crossing_pi_does_not_spin_camera(self):
        positions,_=self.rig_fixture()
        yaw=np.linspace(3.,3.3,len(positions))
        tangents=np.stack([np.column_stack([np.cos(yaw),np.sin(yaw),np.zeros(len(yaw))])]*2,axis=1)
        _,_,side,_=chase_rig(positions,tangents,24)
        rig_yaw=np.unwrap(np.arctan2(-side[:,0],side[:,1]))
        self.assertLess(np.max(np.abs(np.diff(rig_yaw))),.01)

    def test_framing_never_violates_required_separation_zoom(self):
        positions,tangents=self.rig_fixture()
        positions[35:55,1,0]+=80
        _,_,_,zoom=chase_rig(positions,tangents,24)
        floor=np.maximum(1,np.linalg.norm(positions[:,0]-positions[:,1],axis=1)/12)
        self.assertTrue(np.all(zoom>=floor))

    def test_trails_never_reveal_future_and_fade_after_finish(self):
        times=np.array([0.,1.,2.,3.,4.])
        np.testing.assert_allclose(trail_opacity(times,2),[0,.25,1,0,0])
        self.assertTrue(np.all(trail_opacity(times,6)==0))

    def test_complete_cars_fit_both_formats_without_obscuring_panels(self):
        positions,tangents=self.rig_fixture()
        positions[:,1,0]+=np.linspace(0,90,len(positions))
        for size,limits in [((540,960),(.10,.90,.22,.73)),((960,540),(.32,.93,.32,.78))]:
            camera,target,_,_=chase_rig(positions,tangents,24,size)
            projected=project_cars(positions,tangents,camera,target,size)
            self.assertTrue(np.all(projected[:,:,:,0]>=limits[0]))
            self.assertTrue(np.all(projected[:,:,:,0]<=limits[1]))
            self.assertTrue(np.all(projected[:,:,:,1]>=limits[2]))
            self.assertTrue(np.all(projected[:,:,:,1]<=limits[3]))

    def test_framing_thresholds_do_not_reintroduce_zoom_jumps(self):
        positions,tangents=self.rig_fixture()
        positions[:,1,0]+=np.linspace(0,35,len(positions))
        _,_,_,zoom=chase_rig(positions,tangents,24)
        self.assertLess(np.max(np.abs(np.diff(zoom,n=2))),.008)


if __name__=='__main__': unittest.main()
