import unittest
import numpy as np
from services.social_director import director_rig


class DirectorTests(unittest.TestCase):
    def test_dynamic_camera_preserves_source_and_is_finite(self):
        t=np.linspace(0,14,336);a=t*.18
        center=np.column_stack([80*np.cos(a),80*np.sin(a),4*np.sin(a)])
        tangent=np.column_stack([-np.sin(a),np.cos(a),.05*np.cos(a)])
        positions=np.stack([center,center-tangent*2],axis=1)
        headings=np.stack([tangent,tangent],axis=1)
        before=positions.copy()
        for size in ((540,960),(960,540)):
            location,target,side,zoom=director_rig(positions,headings,24,size=size,times=t)
            self.assertTrue(np.isfinite(location).all())
            self.assertGreater(np.ptp(location[:,2]-target[:,2]),5)
            self.assertTrue((zoom>=1).all())
            self.assertLess(np.max(np.linalg.norm(np.diff(location,axis=0),axis=1)),15)
        np.testing.assert_array_equal(before,positions)

    def test_bad_poses_are_rejected(self):
        with self.assertRaises(ValueError):director_rig(np.zeros((2,3)),np.zeros((2,3)),24)

    def test_angle_changes_orbit_without_cutting_in_towards_cars(self):
        t=np.arange(145)/24
        center=np.column_stack([t*40,np.zeros(len(t)),np.zeros(len(t))])
        positions=np.stack([center,center+[2,0,0]],axis=1)
        headings=np.broadcast_to([1.,0.,0.],positions.shape).copy()
        location,_,_,zoom=director_rig(positions,headings,24,times=t)
        radius=np.linalg.norm((location-positions.mean(axis=1))[:,:2],axis=1)/zoom
        # First two views are 23.7m and 21.6m out. Their transition must not
        # take a straight-line shortcut through the inside of that orbit.
        self.assertGreaterEqual(radius[t<=5].min(),np.hypot(12,18)-1e-6)

    def test_accelerated_hairpin_limits_heading_swing_and_tracks_both_cars(self):
        from scripts.cinematic_math import project_cars
        t=np.arange(120)/24
        yaw=np.pi*np.clip((t-1.8)/.25,0,1)+3.
        heading=np.column_stack([np.cos(yaw),np.sin(yaw),np.zeros(len(t))])
        center=np.cumsum(heading*2,axis=0)
        positions=np.stack([center,center-heading*5],axis=1)
        headings=np.stack([heading,heading],axis=1)
        location,target,side,zoom=director_rig(positions,headings,24,times=t*8,playback_speed=8)
        camera_yaw=np.unwrap(np.arctan2(-side[:,0],side[:,1]))
        self.assertLessEqual(np.max(np.abs(np.diff(camera_yaw)))*24,np.deg2rad(110)+1e-6)
        projected=project_cars(positions,headings,location,target,(540,960))
        projected[:,:,:,1]+=.1
        self.assertTrue((projected[:,:,:,2]>0).all())
        self.assertTrue(((projected[:,:,:,0]>=.12)&(projected[:,:,:,0]<=.86)).all())
        self.assertTrue(((projected[:,:,:,1]>=.41)&(projected[:,:,:,1]<=.77)).all())

    def test_single_frame_is_valid_and_unordered_time_is_rejected(self):
        positions=np.array([[[0.,0.,0.],[2.,0.,0.]]])
        headings=np.broadcast_to([1.,0.,0.],positions.shape).copy()
        self.assertTrue(np.isfinite(director_rig(positions,headings,24)[0]).all())
        with self.assertRaisesRegex(ValueError,'ordered'):
            director_rig(np.repeat(positions,2,axis=0),np.repeat(headings,2,axis=0),24,times=[1,0])
