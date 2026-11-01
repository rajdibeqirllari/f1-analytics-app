"""Accelerated output samples real lap time, never fabricated faster telemetry."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from services.video_timeline import PLAYBACK_SPEEDS, frame_count, source_elapsed, validate_playback_speed
from services.video_3d import render_range, render_cache_key, render_3d_mp4
from services.video_renderer import VideoJob, VideoJobs, render_mp4
from test_video_comparison import comparison_fixture


ROOT=Path(__file__).resolve().parents[1]


class VideoSpeedTests(unittest.TestCase):
    def test_supported_speeds_are_bounded_and_default_is_real_time(self):
        self.assertEqual(validate_playback_speed(),1)
        for speed in PLAYBACK_SPEEDS:
            self.assertEqual(validate_playback_speed(speed),speed)
        for invalid in (0,-1,1.5,4,100,float('nan'),float('inf'),None,True,False,[],{}):
            with self.subTest(invalid=invalid),self.assertRaisesRegex(ValueError,'playback speed'):
                validate_playback_speed(invalid)

    def test_frame_budget_speeds_action_but_preserves_exact_finish_and_hold(self):
        comparison=comparison_fixture()
        for fps in (24,30):
            for speed in PLAYBACK_SPEEDS:
                start,end,count,full=render_range(comparison,0,None,fps,speed)
                self.assertTrue(full)
                action_count=frame_count(start,end,fps,speed)
                self.assertEqual(count,action_count+1+2*fps)
                self.assertLess(source_elapsed(action_count-1,start,end,fps,speed),end)
                self.assertEqual(source_elapsed(action_count,start,end,fps,speed),comparison.duration)
                self.assertEqual(source_elapsed(count-1,start,end,fps,speed),comparison.duration)
        self.assertEqual(render_range(comparison,4,12,24,2),(4.,12.,96,False))
        self.assertEqual(source_elapsed(12,4,12,24,2),5.)
        self.assertEqual(frame_count(0,96,24,20,hold=True),165)

    def test_speed_changes_private_render_cache_identity(self):
        config={'start':0,'end':22,'fps':24,'size':[540,960],'playback_speed':1}
        self.assertNotEqual(render_cache_key(config),render_cache_key({**config,'playback_speed':5}))

    def test_invalid_speed_never_queues_a_job_or_loads_telemetry(self):
        manager=VideoJobs()
        try:
            with patch.object(manager.executor,'submit') as queued:
                with self.assertRaises(ValueError):manager.submit(None,playback_speed=4)
                queued.assert_not_called()
            self.assertEqual(manager.jobs,{})
        finally:manager.executor.shutdown()

    def test_job_routes_speed_and_preserves_result_metadata_for_2d_and_3d(self):
        comparison=comparison_fixture()
        selection=type('Selection',(),{'year':2022,'driver_a':'AAA','driver_b':'BBB'})()
        manager=VideoJobs()
        try:
            for style,target in (('2D','services.video_renderer.render_mp4'),('3D','services.video_3d.render_3d_mp4')):
                job=VideoJob('speed'+style,style=style,start=3,end=12,playback_speed=8,audio='Silent')
                manager.jobs[job.id]=job
                with patch(target) as render:
                    manager._run(job,selection,comparison,(540,960),24,'Follow cars',True)
                    self.assertEqual(render.call_args.kwargs['playback_speed'],8)
                    self.assertEqual(render.call_args.kwargs['fps'],24)
                    self.assertEqual(render.call_args.kwargs['start'],3)
                    self.assertEqual(render.call_args.kwargs['end'],12)
                snapshot=manager.snapshot(job.id)
                self.assertEqual(snapshot['status'],'complete')
                self.assertEqual(snapshot['playback_speed'],8)
                self.assertEqual(comparison.duration,22)
        finally:manager.executor.shutdown()

    def test_3d_config_and_compositor_receive_same_speed(self):
        comparison=comparison_fixture()
        captured=[]
        def worker(command,**kwargs):
            config=json.loads(Path(command[command.index('--config')+1]).read_text())
            captured.append(config)
        with patch('services.video_3d.availability',return_value=(True,'')), \
             patch('services.video_3d.fit_path',return_value={}), \
             patch('services.video_3d.prepare_driving_path',return_value={}), \
             patch('services.video_3d.run_blender',side_effect=worker), \
             patch('services.video_3d_overlay.encode_frames') as encode:
            render_3d_mp4(comparison,ROOT/'tmp/speed-config-test.mp4',start=4,end=12,playback_speed=5)
        self.assertEqual(captured[0]['playback_speed'],5)
        self.assertEqual(captured[0]['driving_path']['playback_speed'],5)
        self.assertEqual(captured[0]['frames'],39)
        self.assertEqual(encode.call_args.kwargs['playback_speed'],5)
        self.assertTrue(encode.call_args.kwargs['require_ready'])
        self.assertTrue(encode.call_args.kwargs['discard_frames'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_encoded_2d_keeps_fps_and_true_finish_at_accelerated_speed(self):
        elapsed=[]
        def render(source_time):
            elapsed.append(source_time)
            return Image.new('RGB',(128,128),'gray')
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
            path=Path(folder)/'speed.mp4'
            with patch('services.video_renderer.ComparisonRenderer') as renderer:
                renderer.return_value.render.side_effect=render
                render_mp4(comparison_fixture(),path,size=(128,128),fps=24,start=20,end=22,playback_speed=2)
            info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))
            stream=info['streams'][0]
            self.assertEqual(stream['r_frame_rate'],'24/1')
            self.assertEqual(int(stream['nb_frames']),24+1+48)
        self.assertEqual(elapsed[0],20.)
        self.assertAlmostEqual(elapsed[12],21.)
        self.assertEqual(elapsed[24],22.)
        self.assertEqual(elapsed[-1],22.)


if __name__=='__main__':unittest.main()
