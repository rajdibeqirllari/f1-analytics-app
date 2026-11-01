import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import tempfile
import threading
import subprocess
import numpy as np
from PIL import Image, ImageDraw
from services.director_overlay import lap_clock
from services.video_3d_overlay import TelemetryOverlay, encode_frames
from test_video_comparison import comparison_fixture


def director_fixture(size=(540,960)):
    c=comparison_fixture()
    p=c.track[:,0]
    route={'progress':p,'xy':c.track[:,1:3],'half_separation':np.zeros(len(p)),
           'night_chase':{'focus':0},'social_director':True,'playback_speed':5}
    return c,TelemetryOverlay(c,size,0,22,True,route)


class DirectorOverlayTests(unittest.TestCase):
    def test_clock_rounds_milliseconds_and_matched_distance_leader_is_not_inverted(self):
        c,overlay=director_fixture();director=overlay.director_overlay
        self.assertIsNotNone(director);self.assertIsNone(overlay.night_overlay)
        self.assertEqual(lap_clock(59.9996),'1:00.000')
        self.assertEqual(lap_clock(96.052),'1:36.052')
        self.assertIsNone(director.state(0)['leader'])
        self.assertEqual(director.state(10)['leader'],0)
        self.assertAlmostEqual(director.state(10)['delta'],c.delta_at(10/22))
        final=director.state(25)
        self.assertEqual(final['delta'],2);self.assertTrue(final['finished'])
        c.laps=tuple(reversed(c.laps))
        self.assertEqual(director.state(25)['leader'],1)
        self.assertEqual(director.state(25)['delta'],-2)

    def test_aspect_scaling_safe_subject_zone_and_original_samples(self):
        for size in ((540,960),(1080,1920),(960,540),(1920,1080)):
            c,overlay=director_fixture(size);prior=[v.samples.copy() for v in c.laps]
            image=overlay.render(Image.new('RGB',size),10)
            self.assertEqual(image.size,size)
            self.assertEqual(image.mode,'RGB')
            if size[1]>size[0]:
                s=size[0]/540;pixels=np.asarray(image)
                # The camera target zone is entirely untouched, not hidden by graphics.
                self.assertEqual(pixels[round(220*s):round(580*s)].max(),0)
                self.assertGreater(pixels[round(818*s):round(892*s),round(26*s):round(126*s)].max(),200)
                self.assertLess(pixels[:round(898*s),round(478*s):].max(),80)
            for lap,old in zip(c.laps,prior):self.assertTrue(lap.samples.equals(old))

    def test_missing_channels_are_not_painted_as_measurements_or_aero_modes(self):
        c,overlay=director_fixture();c.laps[0].unavailable_channels=('brake','throttle','gear')
        labels=[];original=ImageDraw.ImageDraw.text
        def record(draw,position,value,*args,**kwargs):
            labels.append(str(value));return original(draw,position,value,*args,**kwargs)
        with patch.object(ImageDraw.ImageDraw,'text',record):
            overlay.render(Image.new('RGB',(540,960)),10)
        self.assertIn('BRAKE —',labels);self.assertIn('T —',labels);self.assertIn('5× SPEED',labels)
        self.assertFalse(any('Straight mode' in label for label in labels))
        self.assertEqual(overlay.director_overlay.sectors,[])
        c.laps[0].sectors=(5,7,8)
        route=overlay.director_overlay.path
        with_sectors=TelemetryOverlay(c,(540,960),0,22,True,route).director_overlay
        np.testing.assert_allclose(with_sectors.sectors,[.25,.6])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_real_streamed_director_encode_samples_source_time_at_five_times_speed(self):
        c,overlay=director_fixture();route=overlay.director_overlay.path
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as temp:
            folder=Path(temp);frames=folder/'frames';frames.mkdir();done=threading.Event();times=[]
            original=TelemetryOverlay.render
            def record(obj,source,elapsed,output_time=None):
                self.assertIsNotNone(obj.director_overlay)
                self.assertEqual(obj.director_overlay.path['playback_speed'],5)
                times.append(elapsed)
                return original(obj,source,elapsed,output_time)
            output=folder/'director-speed.mp4'
            with patch.object(TelemetryOverlay,'render',record),ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(encode_frames,c,frames,output,size=(540,960),fps=4,start=0,end=10,
                                   frames=9,full=False,playback_speed=5,driving_path=route,
                                   producer_done=done,require_ready=True)
                try:
                    for i in range(9):
                        Image.new('RGB',(540,960),(20+i,35,45)).save(frames/f'frame_{i+1:04d}.png')
                        (frames/f'frame_{i+1:04d}.ready').touch()
                finally:done.set()
                future.result(timeout=30)
            np.testing.assert_allclose(times,np.arange(9)*1.25)
            duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration',
                                                   '-of','default=noprint_wrappers=1:nokey=1',str(output)],text=True).strip())
            self.assertAlmostEqual(duration,9/4,places=2)
            self.assertGreater(output.stat().st_size,1000)


if __name__=='__main__':unittest.main()
