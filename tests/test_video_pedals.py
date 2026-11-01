import unittest
import numpy as np
from PIL import Image
from services.video_3d_overlay import TelemetryOverlay
from test_video_comparison import comparison_fixture


class PedalTests(unittest.TestCase):
    def fixture(self):
        c=comparison_fixture()
        for lap in c.laps:
            lap.samples['throttle']=lap.samples['t']/lap.lap_time*100
            lap.samples['brake']=lap.samples['t']>=10
            lap.__post_init__()
        return c

    def test_throttle_interpolates_and_brake_never_anticipates_source(self):
        c=self.fixture();before=[lap.samples.copy() for lap in c.laps]
        for size in ((540,960),(960,540),(1080,1920)):
            portrait=size[1]>size[0];s=size[0]/(540 if portrait else 960)
            overlay=TelemetryOverlay(c,size,0,22,True)
            def pixel(image,x,y):return image.getpixel((round(x*s),round(y*s)))
            y=118 if portrait else 128
            early=overlay.render(Image.new('RGB',size),5)
            self.assertEqual(pixel(early,48,y+84),(34,230,111))
            self.assertEqual(pixel(early,128,y+84),(49,64,78))
            just_before=overlay.render(Image.new('RGB',size),9.99)
            on=overlay.render(Image.new('RGB',size),10)
            self.assertEqual(pixel(just_before,200,y+84),(49,64,78))
            self.assertEqual(pixel(on,200,y+84),(255,69,85))
            finished=overlay.render(Image.new('RGB',size),22)
            self.assertEqual(pixel(finished,48,y+84),(49,64,78))
        for lap,old in zip(c.laps,before):self.assertTrue(lap.samples.equals(old))

    def test_missing_channels_do_not_display_fabricated_inputs(self):
        c=self.fixture()
        c.laps[0].warnings=['Throttle is unavailable; its display is omitted.',
                            'Brake is unavailable; its display is omitted.']
        image=TelemetryOverlay(c,(540,960),0,22,True).render(Image.new('RGB',(540,960)),12)
        self.assertEqual(image.getpixel((48,202)),(49,64,78))
        self.assertEqual(image.getpixel((200,202)),(49,64,78))
