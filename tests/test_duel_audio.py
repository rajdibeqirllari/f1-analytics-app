import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import patch
import numpy as np
from services.duel_audio import validate_audio,duel_controls,synthesize_duel,attach_duel,soundtrack_timeline
from test_video_comparison import comparison_fixture


class DuelAudioTests(unittest.TestCase):
    def test_invalid_inputs_rejected(self):
        for style,volume in (('engine',80),('The Duel',float('nan')),('Silent',-1),('Silent',101),('Silent',True),('Silent',None)):
            with self.assertRaises(ValueError):validate_audio(style,volume)

    def test_controls_match_hud_and_same_source_clock(self):
        c=comparison_fixture();timeline,full=soundtrack_timeline(c,fps=60,camera='The Limit',pacing='Dynamic cinematic')
        controls=duel_controls(c,timeline,full)
        self.assertAlmostEqual(controls['seconds'],38.2)
        self.assertAlmostEqual(controls['finish'],3.2+timeline['action_seconds'])
        self.assertGreater(controls['dominance'][-1],0)  # fixture A wins
        self.assertTrue(np.all(np.abs(controls['dominance'])<=1))
        for cue in controls['cues']:
            self.assertGreaterEqual(cue['time'],3.2)
            self.assertLess(cue['time'],controls['seconds'])
        c.laps=c.laps[::-1]
        reversed_controls=duel_controls(c,timeline,full)
        np.testing.assert_allclose(reversed_controls['dominance'],-controls['dominance'])

    def test_2d_clock_matches_its_renderer_including_clip_hold(self):
        from services.video_timeline import frame_count,source_elapsed
        c=comparison_fixture()
        for end in (3,None):
            timeline,full=soundtrack_timeline(c,fps=30,end=end,style='2D',playback_speed=3)
            last=c.duration if end is None else end
            expected=[source_elapsed(i,0,last,30,3) for i in range(frame_count(0,last,30,3,hold=True))]
            np.testing.assert_allclose(timeline['source_times'],expected)
            self.assertEqual(full,end is None)

    def test_audio_defaults_on_for_all_cameras_and_api_omission(self):
        from services.video_renderer import VideoJobs,VideoJob
        from services.video_comparison import VideoSelection
        from api.main import app,video_requests
        from fastapi.testclient import TestClient
        manager=VideoJobs();selection=VideoSelection(2026,'United States Grand Prix','Q','ANT','VER')
        self.assertEqual(VideoJob('default').audio,'The Duel')
        try:
            with patch.object(manager.executor,'submit'),patch('services.video_3d.availability',return_value=(True,'')):
                for style,camera in (('2D','Follow cars'),('3D','The Limit'),('3D','Follow cars'),('3D','Full circuit'),('3D','Night chase B'),('3D','Onboard ghost A'),('3D','Social director'),('3D','Cinematic Ghost Chase'),('3D','Classic Broadcast')):
                    key=manager.submit(selection,style=style,camera=camera)
                    self.assertEqual(manager.snapshot(key)['audio'],'The Duel')
                    manager.jobs[key].status='complete'
            with patch('api.main.videos.submit',return_value='default-audio-test') as submit:
                response=TestClient(app).post('/api/jobs',json=dict(kind='video',
                    selection=dict(year=2026,event='United States Grand Prix',session='Q',driver='ANT',driver_b='VER'),
                    options=dict(style='2D')))
                self.assertEqual(response.status_code,202,response.text)
                self.assertEqual(submit.call_args.kwargs['audio'],'The Duel')
                video_requests.pop('default-audio-test',None)
        finally:manager.executor.shutdown(wait=False)

    def test_pcm_is_deterministic_finite_stereo_and_bounded(self):
        c=comparison_fixture();timeline,full=soundtrack_timeline(c,fps=30,end=3,camera='The Limit')
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a.wav';b=Path(folder)/'b.wav'
            report=synthesize_duel(c,timeline,a,full=full)
            synthesize_duel(c,timeline,b,full=full)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            with wave.open(str(a)) as source:
                self.assertEqual(source.getframerate(),48000);self.assertEqual(source.getnchannels(),2)
                self.assertEqual(source.getnframes(),round(report['seconds']*48000))
                pcm=np.frombuffer(source.readframes(source.getnframes()),'<i2').reshape(-1,2)/32768
            self.assertLess(np.abs(pcm).max(),.99)
            self.assertGreater(np.sqrt((pcm**2).mean()),.01)
            self.assertLess(abs(pcm.mean()),.005)
            self.assertGreater(np.sqrt((pcm.mean(1)**2).mean()),np.sqrt((pcm**2).mean())*.9)

    def test_cancelled_audio_never_publishes(self):
        c=comparison_fixture();timeline,full=soundtrack_timeline(c,fps=30,end=3)
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'result.mp4'
            with self.assertRaises(InterruptedError):
                attach_duel(c,Path(folder)/'source.mp4',destination,timeline,full=full,cancelled=lambda:True)
            self.assertFalse(destination.exists());self.assertFalse(list(Path(folder).glob('*.partial.mp4')))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_real_mux_copies_video_packets_and_has_aac(self):
        c=comparison_fixture();timeline,full=soundtrack_timeline(c,fps=30,end=3,camera='Cinematic Ghost Chase')
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4';destination=Path(folder)/'duel.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:s=96x160:r=30',
                            '-frames:v',str(len(timeline['source_times'])),'-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
            attach_duel(c,source,destination,timeline,full=full)
            info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(destination)]))
            audio=next(v for v in info['streams'] if v['codec_type']=='audio')
            self.assertEqual(audio['codec_name'],'aac');self.assertEqual(audio['sample_rate'],'48000')
            def packets(path):
                return json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_packets','-show_data_hash','sha256',
                    '-show_entries','packet=pts_time,data_hash','-of','json',str(path)]))['packets']
            self.assertEqual(packets(source),packets(destination))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_real_default_2d_preview_and_final_files_include_audio(self):
        from services.video_renderer import VideoJobs,VideoJob
        from services.video_comparison import VideoSelection
        c=comparison_fixture();selection=VideoSelection(2026,'United States Grand Prix','Q','ANT','VER')
        manager=VideoJobs()
        try:
            with tempfile.TemporaryDirectory() as folder,patch('services.video_renderer.OUTPUT',Path(folder)):
                for preview in (True,False):
                    job=VideoJob('real-2d-'+str(preview),style='2D',end=1,playback_speed=3)
                    manager.jobs[job.id]=job
                    manager._run(job,selection,c,(96,160),30,'Follow cars',preview)
                    self.assertEqual(job.status,'complete',job.error)
                    streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(job.result)]))['streams']
                    self.assertTrue(any(s['codec_type']=='audio' and s['codec_name']=='aac' for s in streams))
                    timeline,_=soundtrack_timeline(c,fps=30,end=1,playback_speed=3,style='2D')
                    video=next(s for s in streams if s['codec_type']=='video')
                    self.assertEqual(int(video['nb_frames']),len(timeline['source_times']))
        finally:manager.executor.shutdown(wait=False)

    def test_api_and_queue_store_audio_options(self):
        from api.main import app,video_requests
        from fastapi.testclient import TestClient
        from services.video_renderer import VideoJobs
        from services.video_comparison import VideoSelection
        with patch('api.main.videos.submit',return_value='duel-test') as submit:
            response=TestClient(app).post('/api/jobs',json=dict(kind='video',
                selection=dict(year=2026,event='United States Grand Prix',session='Q',driver='ANT',driver_b='VER'),
                options=dict(style='3D',camera='The Limit',audio='The Duel',audio_volume=65)))
            self.assertEqual(response.status_code,202,response.text)
            self.assertEqual(submit.call_args.kwargs['audio'],'The Duel')
            self.assertEqual(submit.call_args.kwargs['audio_volume'],65)
            video_requests.pop('duel-test',None)
        manager=VideoJobs()
        try:
            with patch.object(manager.executor,'submit'),patch('services.video_3d.availability',return_value=(True,'')):
                key=manager.submit(VideoSelection(2026,'United States Grand Prix','Q','ANT','VER'),style='3D',camera='The Limit',audio='The Duel',audio_volume=65)
                self.assertEqual(manager.snapshot(key)['audio'],'The Duel')
                self.assertEqual(manager.snapshot(key)['audio_volume'],65)
        finally:manager.executor.shutdown(wait=False)

    def test_worker_adds_audio_once_after_render_and_cleans_failed_owned_output(self):
        from services.video_renderer import VideoJobs,VideoJob
        from services.video_comparison import VideoSelection
        c=comparison_fixture();selection=VideoSelection(2026,'United States Grand Prix','Q','ANT','VER')
        manager=VideoJobs()
        def render(comparison,path,**kwargs):Path(path).write_bytes(b'test-only-video')
        try:
            with tempfile.TemporaryDirectory() as folder,patch('services.video_renderer.OUTPUT',Path(folder)),\
                    patch('services.video_3d.render_3d_mp4',side_effect=render) as scene,\
                    patch('services.duel_audio.attach_duel') as mix:
                job=VideoJob('duel-worker',style='3D',end=3,audio='The Duel',audio_volume=65)
                manager.jobs[job.id]=job
                manager._run(job,selection,c,(540,960),30,'The Limit',True)
                self.assertEqual(job.status,'complete');self.assertTrue(job.result.exists())
                self.assertEqual(scene.call_count,1);self.assertEqual(mix.call_count,1)
                self.assertEqual(mix.call_args.kwargs['volume'],65)
                self.assertEqual(mix.call_args.args[1],mix.call_args.args[2])
                mix.side_effect=RuntimeError('test mix failed')
                failed=VideoJob('duel-worker-failed',style='3D',end=3,audio='The Duel')
                manager.jobs[failed.id]=failed
                manager._run(failed,selection,c,(540,960),30,'The Limit',True)
                self.assertEqual(failed.status,'failed')
                self.assertEqual(list(Path(folder).glob('*.mp4')),[job.result])
        finally:manager.executor.shutdown(wait=False)


if __name__=='__main__':unittest.main()
