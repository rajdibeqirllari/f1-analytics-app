import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from services.video_3d import availability, fit_path, render_range, run_blender, render_3d_mp4
from services.video_3d_overlay import TelemetryOverlay, encode_frames
from services.video_renderer import VideoJobs, VideoJob
from test_video_comparison import comparison_fixture

ROOT=Path(__file__).resolve().parents[1]


class ThreeDTests(unittest.TestCase):
    def test_camera_is_validated_before_loading_or_queueing(self):
        manager=VideoJobs()
        selection=type('Selection',(),{'year':2026,'event':'Singapore Grand Prix'})()
        try:
            with patch('services.video_3d.availability') as available:
                with self.assertRaisesRegex(ValueError,'Select the chase driver again'):
                    manager.submit(selection,style='3D',camera='VER')
                available.assert_not_called()
            self.assertEqual(manager.jobs,{})
        finally:
            manager.executor.shutdown()

    def test_support_is_explicit_and_missing_dependencies_are_actionable(self):
        self.assertFalse(availability(2025,'Unknown Grand Prix')[0])
        with patch('services.video_3d.blender_executable',return_value=None):
            ready,reason=availability(2022,'French Grand Prix')
            self.assertFalse(ready); self.assertIn('Blender',reason)

    def test_ranges_retain_finish_and_clip_duration(self):
        comparison=comparison_fixture()
        start,end,frames,full=render_range(comparison,0,None,24)
        self.assertTrue(full); self.assertEqual(end,22); self.assertEqual(frames,577)
        self.assertEqual(render_range(comparison,4,12,24),(4.,12.,192,False))
        self.assertEqual(render_range(comparison,21,40,30),(21.,22,30,False))
        self.assertEqual(render_range(comparison,0,3,60),(0.,3.,180,False))
        for start,end,fps in [(22,30,24),(float('nan'),12,24),(0,float('inf'),24),(0,12,120)]:
            with self.assertRaises(ValueError): render_range(comparison,start,end,fps)

    def test_overlay_is_dynamic_and_both_orientations_scale(self):
        comparison=comparison_fixture()
        for size in [(540,960),(960,540),(720,1280),(1920,1080)]:
            overlay=TelemetryOverlay(comparison,size,0,22,True)
            first=overlay.render(Image.new('RGB',size,'gray'),0)
            finish=overlay.render(Image.new('RGB',size,'gray'),22)
            self.assertEqual(first.size,size)
            self.assertFalse(np.array_equal(np.asarray(first),np.asarray(finish)))

    def test_calibrated_fit_and_wrong_geometry_rejection(self):
        comparison=comparison_fixture()
        comparison.year=2022; comparison.event='French Grand Prix'
        profile={'parameters':[0.,np.log(2.5),0.,0.], 'telemetry_origin':[0.,0.],'road_origin':[0.,0.]}
        with patch('services.video_3d.PROFILE') as path,patch('services.video_3d._road_points') as road:
            path.read_text.return_value=json.dumps(profile)
            road.return_value=comparison.track[:,1:3]*2.5
            result=fit_path(comparison)
            self.assertLess(result['rms_metres'],.1)
            road.return_value=np.array([[10000.,10000.]])
            with self.assertRaisesRegex(ValueError,'align safely'): fit_path(comparison)

    def test_owned_blender_process_is_killed_on_cancel(self):
        processes=[]
        original=subprocess.Popen
        def spawn(*args,**kwargs):
            process=original(*args,**kwargs); processes.append(process); return process
        ROOT.joinpath('tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            started=time.monotonic()
            with patch('services.video_3d.subprocess.Popen',side_effect=spawn):
                with self.assertRaises(InterruptedError):
                    run_blender([sys.executable,'-c','import time; time.sleep(30)'],
                        cancelled=lambda:time.monotonic()-started>.5,progress_callback=None,
                        frames=2,log_path=Path(directory)/'worker.log')
            self.assertIsNotNone(processes[0].poll())
            self.assertLess(time.monotonic()-started,5)

    def test_blender_failure_is_reported(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            with self.assertRaisesRegex(RuntimeError,'known render failure'):
                run_blender([sys.executable,'-c',"print('known render failure'); raise SystemExit(1)"],
                    cancelled=None,progress_callback=None,frames=2,log_path=Path(directory)/'worker.log')

    def test_repeated_shadow_overflow_stops_instead_of_rendering_bad_frames(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            command=[sys.executable,'-u','-c',
                "import time; print(('Shadow buffer full\\n'*8),flush=True); time.sleep(20)"]
            with self.assertRaisesRegex(RuntimeError,'shadow-memory budget'):
                run_blender(command,cancelled=None,progress_callback=None,frames=24,
                            log_path=Path(directory)/'worker.log')

    def test_surface_trail_update_failure_aborts_export_worker(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            command=[sys.executable,'-u','-c',
                     "import time; print('TRAIL_ALIGNMENT_ERROR test alignment failure',flush=True); time.sleep(20)"]
            with self.assertRaisesRegex(RuntimeError,'Surface trajectory update failed'):
                run_blender(command,cancelled=None,progress_callback=None,frames=24,
                            log_path=Path(directory)/'worker.log')

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg missing')
    def test_encoding_cancellation_and_incomplete_frames_never_publish(self):
        comparison=comparison_fixture()
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            folder=Path(directory); destination=folder/'test.mp4'
            options=dict(size=(540,960),fps=24,start=0,end=1,frames=2,full=False)
            with self.assertRaisesRegex(RuntimeError,'incomplete'): encode_frames(comparison,folder,destination,**options)
            for i in (1,2): Image.new('RGB',(540,960),'gray').save(folder/f'frame_{i:04d}.png')
            with self.assertRaises(InterruptedError): encode_frames(comparison,folder,destination,cancelled=lambda:True,**options)
            self.assertFalse(destination.exists()); self.assertFalse(destination.with_suffix('.partial.mp4').exists())
            encode_frames(comparison,folder,destination,**options)
            self.assertGreater(destination.stat().st_size,1000)

    def test_background_job_routes_options_and_metadata_to_3d(self):
        comparison=comparison_fixture()
        selection=type('Selection',(),{'year':2022,'driver_a':'AAA','driver_b':'BBB'})()
        manager=VideoJobs()
        job=VideoJob('test',style='3D',start=4,end=12,environment='Telemetry-built',quality='Balanced',audio='Silent')
        manager.jobs[job.id]=job
        with patch('services.video_3d.render_3d_mp4') as render:
            manager._run(job,selection,comparison,(540,960),24,'Follow cars',True)
            self.assertEqual(render.call_args.kwargs['start'],4)
            self.assertEqual(render.call_args.kwargs['end'],12)
            self.assertEqual(render.call_args.kwargs['environment'],'Telemetry-built')
            self.assertEqual(render.call_args.kwargs['quality'],'Balanced')
            self.assertEqual(manager.snapshot('test')['style'],'3D')
            self.assertEqual(manager.snapshot('test')['status'],'complete')
        manager.executor.shutdown()

    def test_night_job_keeps_focus_and_range_for_preview_and_export(self):
        comparison=comparison_fixture()
        selection=type('Selection',(),{'year':2026,'driver_a':'AAA','driver_b':'BBB'})()
        manager=VideoJobs()
        with patch('services.video_3d.render_3d_mp4') as render:
            for preview,size,fps in ((True,(540,960),24),(False,(720,1280),30)):
                job=VideoJob('night'+str(preview),style='3D',start=7,end=17,audio='Silent')
                manager.jobs[job.id]=job
                manager._run(job,selection,comparison,size,fps,'Night chase B',preview)
                self.assertEqual(render.call_args.kwargs['camera'],'Night chase B')
                self.assertEqual(render.call_args.kwargs['start'],7)
                self.assertEqual(render.call_args.kwargs['end'],17)
                self.assertIn('_night_',str(render.call_args.args[1]))
                self.assertEqual(manager.snapshot(job.id)['status'],'complete')
        manager.executor.shutdown()

    def test_relative_destination_is_resolved_before_blender_changes_directory(self):
        comparison=comparison_fixture()
        captured=[]
        def worker(command,**kwargs):
            config=json.loads(Path(command[command.index('--config')+1]).read_text())
            captured.append(config['work_dir'])
            self.assertTrue(Path(config['work_dir']).is_absolute())
        with patch('services.video_3d.availability',return_value=(True,'')), \
             patch('services.video_3d.fit_path',return_value={}), \
             patch('services.video_3d.prepare_driving_path',return_value={}), \
             patch('services.video_3d.run_blender',side_effect=worker), \
             patch('services.video_3d_overlay.encode_frames'):
            render_3d_mp4(comparison,Path('tmp/relative_destination_test.mp4'),start=0,end=1)
        self.assertFalse(Path(captured[0]).exists())

    def test_unsafe_asphalt_route_never_starts_renderer_or_publishes_video(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            target=Path(directory)/'unsafe.mp4'
            with patch('services.video_3d.availability',return_value=(True,'')), \
                 patch('services.video_3d.fit_path',return_value={}), \
                 patch('services.video_3d.prepare_driving_path',side_effect=ValueError('Unsafe asphalt route')), \
                 patch('services.video_3d.run_blender') as worker:
                with self.assertRaisesRegex(ValueError,'Unsafe asphalt route'):
                    render_3d_mp4(comparison_fixture(),target,start=0,end=1)
                worker.assert_not_called()
            self.assertFalse(target.exists())


if __name__=='__main__': unittest.main()
