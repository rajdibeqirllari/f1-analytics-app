import unittest
import numpy as np
from PIL import Image
from services.video_3d_overlay import TelemetryOverlay, font
from services.video_minimap import TrackMap
from test_video_comparison import comparison_fixture


class MinimapTests(unittest.TestCase):
    def test_positions_follow_timed_display_route_not_raw_source_xy(self):
        c=comparison_fixture()
        p=np.linspace(0,1,9)
        route={'progress':p, 'xy':np.column_stack([20+200*np.minimum(p,1-p),np.full(9,10)]),
               'half_separation':np.ones(9)}
        m=TrackMap(c,route,(354,740,154,138),1,font)
        np.testing.assert_allclose(m.position(0,5),[70,11],atol=1e-7)
        np.testing.assert_allclose(m.position(1,5.5),[70,9],atol=1e-7)
        np.testing.assert_allclose(m.position(0,30),m.position(0,20))

    def test_projection_preserves_aspect_and_fits_panel(self):
        c=comparison_fixture(); before=c.track.copy()
        for size in ((540,960),(720,1280),(1920,1080)):
            overlay=TelemetryOverlay(c,size,0,22,True)
            m=overlay.minimap; points=m.project(m.route);x,y,w,h=m.box
            self.assertTrue((points[:,0]>x).all() and (points[:,0]<x+w).all())
            self.assertTrue((points[:,1]>y+16*m.scale).all() and (points[:,1]<y+h-16*m.scale).all())
            self.assertAlmostEqual(np.ptp(points[:,0])/np.ptp(points[:,1]),
                                   np.ptp(m.route[:,0])/np.ptp(m.route[:,1]))
            image=overlay.render(Image.new('RGB',size),5)
            self.assertEqual(image.size,size)
            self.assertNotEqual(image.getpixel((x+5,y+round(h/2))),(0,0,0))
        np.testing.assert_array_equal(before,c.track)

    def test_map_moves_without_changing_timing_or_input(self):
        c=comparison_fixture();original=[lap.samples.copy() for lap in c.laps]
        overlay=TelemetryOverlay(c,(540,960),0,22,True)
        a=overlay.minimap.project(overlay.minimap.position(0,2))
        b=overlay.minimap.project(overlay.minimap.position(0,12))
        self.assertGreater(np.linalg.norm(a-b),30)
        for lap,prior in zip(c.laps,original):self.assertTrue(lap.samples.equals(prior))
        self.assertEqual(c.delta_at(1),2)


if __name__=='__main__':unittest.main()
