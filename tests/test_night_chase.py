import unittest
import numpy as np
from PIL import Image
from services.night_chase import night_chase_rig
from scripts.cinematic_math import project_cars
from services.video_3d_overlay import TelemetryOverlay
from services.video_minimap import TrackMap
from test_video_comparison import comparison_fixture


class NightChaseTests(unittest.TestCase):
    def test_camera_allows_visible_turn_in_without_losing_selected_car(self):
        t=np.arange(144)/24;angle=t*.4
        center=np.column_stack([35*np.sin(angle),35*(1-np.cos(angle)),np.zeros(len(t))])
        direction=np.column_stack([np.cos(angle),np.sin(angle),np.zeros(len(t))])
        positions=np.stack([center,center],axis=1);tangents=np.stack([direction,direction],axis=1)
        for size in ((540,960),(960,540)):
            location,target,_,_=night_chase_rig(positions,tangents,24,size)
            view=np.unwrap(np.arctan2((target-location)[:,1],(target-location)[:,0]))
            self.assertGreater(np.degrees(np.abs(view[40:]-angle[40:])).mean(),2)
            projected=project_cars(positions[:,:1],tangents[:,:1],location,target,size)
            self.assertGreater(projected[...,0].min(),.25)
            self.assertLess(projected[...,0].max(),.96)

    def test_portrait_social_safe_zones_stay_clear_of_text_and_branding(self):
        c=comparison_fixture();p=c.track[:,0]
        route={'progress':p,'xy':c.track[:,1:3],'half_separation':np.zeros(len(p)),
               'night_chase':{'focus':0}}
        for size in ((540,960),(720,1280),(1080,1920)):
            overlay=TelemetryOverlay(c,size,0,22,True,route)
            pixels=np.asarray(overlay.render(Image.new('RGB',size),5))
            s=size[0]/540
            self.assertLess(pixels[:round(90*s)].max(),100)
            self.assertLess(pixels[round(760*s):round(900*s)].max(),100)
            self.assertLess(pixels[:round(900*s),round(480*s):].max(),100)
            self.assertGreater(pixels[round(902*s):round(904*s)].max(),150)
            self.assertGreater(pixels[round(931*s):round(945*s)].max(),100)
            self.assertGreater(pixels[round(485*s):round(570*s),round(20*s):round(152*s)].max(),200)
            self.assertLess(pixels[round(630*s):round(715*s),round(20*s):round(152*s)].max(),100)

    def test_selected_driver_stays_in_frame_when_other_ghost_diverges(self):
        for size in ((540,960),(960,540)):
            for focus in (0,1):
                t=np.arange(120)/24
                center=np.column_stack([t*60,np.zeros(len(t)),np.zeros(len(t))])
                positions=np.stack([center,center+[70,0,0]],axis=1)
                tangents=np.broadcast_to([1.,0.,0.],positions.shape).copy()
                before=positions.copy()
                location,target,_,_=night_chase_rig(positions,tangents,24,size,focus)
                projected=project_cars(positions[:,focus:focus+1],tangents[:,focus:focus+1],location,target,size)
                self.assertGreater(projected[:,:,:,0].min(),.25)
                self.assertLess(projected[:,:,:,0].max(),.96)
                self.assertGreater(projected[:,:,:,1].min(),.13)
                self.assertLess(projected[:,:,:,1].max(),.79)
                np.testing.assert_array_equal(positions,before)
        with self.assertRaises(ValueError):night_chase_rig(positions,tangents,24,focus=2)

    def test_overlap_and_locator_use_identical_route_without_lane_offsets(self):
        c=comparison_fixture();p=c.track[:,0]
        route={'progress':p,'xy':c.track[:,1:3],'half_separation':np.zeros(len(p)),
               'night_chase':{'focus':0}}
        before=[lap.samples.copy() for lap in c.laps]
        for size in ((540,960),(960,540),(720,1280),(1280,720),(1080,1920),(1920,1080)):
            overlay=TelemetryOverlay(c,size,0,22,True,route)
            self.assertIsNotNone(overlay.night_overlay)
            m=overlay.night_overlay.map
            np.testing.assert_allclose(m.position(0,5),m.position(1,5.5),atol=1e-9)
            start=overlay.render(Image.new('RGB',size),0)
            end=overlay.render(Image.new('RGB',size),22)
            self.assertEqual(start.size,size)
            self.assertFalse(np.array_equal(np.array(start),np.array(end)))
        for lap,old in zip(c.laps,before):self.assertTrue(lap.samples.equals(old))
