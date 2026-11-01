import unittest
import numpy as np
from PIL import Image
from services.video_branding import add_social_brand, LOGO, _sprite
from services.video_renderer import ComparisonRenderer
from services.video_3d_overlay import TelemetryOverlay
from test_video_comparison import comparison_fixture


class BrandingTests(unittest.TestCase):
    def test_transparency_aspect_ratio_and_reserved_header(self):
        for size in ((540,960),(720,1280),(1080,1920),(960,540),(1920,1080)):
            image=Image.new('RGB',size,(12,20,30))
            before=np.array(image)
            result=add_social_brand(image)
            changed=np.any(np.array(result)!=before,axis=2)
            y,x=np.where(changed)
            scale=size[0]/(540 if size[1]>size[0] else 960)
            self.assertGreater(len(x),100)
            self.assertGreater(x.min(),size[0]*.7)
            self.assertLess(y.max(),round(94*scale))
            self.assertEqual(result.getpixel((0,0)),(12,20,30))
            sprite=_sprite(round(122*scale),round(98*scale),LOGO.stat().st_mtime_ns)
            self.assertEqual(sprite.mode,'RGBA')
            self.assertEqual(sprite.getpixel((0,0))[3],0)

    def test_both_compositions_use_the_same_brand_without_changing_samples(self):
        c=comparison_fixture()
        before=[lap.samples.copy() for lap in c.laps]
        for size in ((540,960),(960,540)):
            a=ComparisonRenderer(c,size).render(5)
            b=TelemetryOverlay(c,size,0,22,True).render(Image.new('RGB',size),5)
            scale=size[0]/(540 if size[1]>size[0] else 960)
            box=(round(size[0]-110*scale),round(20*scale),round(size[0]-40*scale),round(75*scale))
            self.assertGreater(np.array(a.crop(box)).max(),200)
            self.assertGreater(np.array(b.crop(box)).max(),200)
        for lap,prior in zip(c.laps,before):
            self.assertTrue(lap.samples.equals(prior))
