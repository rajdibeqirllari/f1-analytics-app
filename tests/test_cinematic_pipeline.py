import unittest
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageDraw
from services.cinematic_timeline import cinematic_timeline,validate_options
from services.cinematic_camera import cinematic_ghost_rig
from services.trajectory_spline import RouteSpline
from services.video_3d_overlay import TelemetryOverlay,encode_frames
from test_video_comparison import comparison_fixture


class CinematicPipelineTests(unittest.TestCase):
    def test_native60_constant_clock_and_exact_finish(self):
        c=comparison_fixture();t=cinematic_timeline(c,0,c.duration,60,3,full=True)
        n=int(np.ceil(c.duration/3*60));samples=np.array(t['source_times'])
        np.testing.assert_allclose(np.diff(samples[:n]),.05,atol=1e-12)
        self.assertEqual(samples[n],c.duration);self.assertEqual(samples[-1],c.duration)
        self.assertEqual(len(samples),n+121)

    def test_dynamic_timeline_is_monotone_targeted_and_preview_matches_final(self):
        c=comparison_fixture();old=[lap.samples.copy() for lap in c.laps]
        timeline=cinematic_timeline(c,0,c.duration,60,3,'Dynamic cinematic',35,True)
        source=np.array(timeline['source_times']);active=source[source<c.duration]
        self.assertTrue((np.diff(active)>0).all());self.assertAlmostEqual(timeline['output_seconds'],35,places=2)
        clip=cinematic_timeline(c,0,10,60,3,'Dynamic cinematic',35,False)
        np.testing.assert_allclose(source[:len(clip['source_times'])],clip['source_times'])
        for lap,prior in zip(c.laps,old):self.assertTrue(lap.samples.equals(prior))

    def test_camera_is_continuous_safe_and_preserves_car_poses(self):
        from scripts.cinematic_math import project_cars
        t=np.arange(900)/60;a=t*.6;center=np.column_stack([40*np.sin(a),40*np.cos(a),np.sin(a)])
        heading=np.column_stack([np.cos(a),-np.sin(a),np.zeros(len(t))])
        positions=np.stack([center,center-heading*(2+4*np.sin(a)**2)[:,None]],axis=1)
        tangents=np.stack([heading,heading],axis=1);old=positions.copy()
        for size in ((540,960),(960,540)):
            loc,target,side,zoom=cinematic_ghost_rig(positions,tangents,60,size)
            q=project_cars(positions,tangents,loc,target,size)
            if size[0]>size[1]:q[:,:,:,0]-=.1
            q[:,:,:,1]+=.1*max(1,size[0]/size[1])
            self.assertTrue(np.isfinite(loc).all());self.assertTrue((q[:,:,:,2]>0).all())
            self.assertLess(np.max(np.linalg.norm(np.diff(loc,axis=0),axis=1)),2)
            self.assertGreaterEqual(q[:,:,:,0].min(),.11);self.assertLessEqual(q[:,:,:,0].max(),.89)
        np.testing.assert_array_equal(positions,old)

    def test_spline_stays_inside_bounded_route_corridor(self):
        p=np.linspace(0,1,100);xyz=np.column_stack([p*200,np.sin(p*8)*20,p*0])
        spline=RouteSpline(p,xyz)
        for v in np.linspace(0,1,1000):
            position,tangent=spline.pose(v);linear=np.array([np.interp(v,p,xyz[:,i]) for i in range(3)])
            self.assertLessEqual(np.linalg.norm(position-linear),.120001)
            self.assertAlmostEqual(np.linalg.norm(tangent),1)

    def test_hook_and_result_are_derived_from_data(self):
        c=comparison_fixture();route={'social_director':True,'cinematic_ghost':True,'playback_speed':3,
                                    'progress':c.track[:,0],'xy':c.track[:,1:3],'half_separation':np.zeros(len(c.track))}
        overlay=TelemetryOverlay(c,(540,960),0,c.duration,True,route)
        labels=[];original=ImageDraw.ImageDraw.text
        def record(draw,xy,value,*a,**kw):labels.append(str(value));return original(draw,xy,value,*a,**kw)
        with patch.object(ImageDraw.ImageDraw,'text',record):
            overlay.render(Image.new('RGB',(540,960)),.5,.3)
            overlay.render(Image.new('RGB',(540,960)),c.duration,12)
        self.assertIn('2.000 SECONDS. WHO WAS FASTER?',labels)
        self.assertIn('FINAL GAP  2.000s',labels)

    def test_invalid_options_rejected(self):
        for kw in (dict(pacing='bad'),dict(target_duration=None),dict(target_duration=100),dict(camera_options=[]),dict(camera_options={'zoom':None}),dict(camera_options={'bad':1})):
            with self.assertRaises(ValueError):validate_options(**kw)

    def test_landscape_finish_stays_inside_frame_and_keeps_credit_clear(self):
        c=comparison_fixture();route={'social_director':True,'cinematic_ghost':True,
            'progress':c.track[:,0],'xy':c.track[:,1:3],'half_separation':np.zeros(len(c.track))}
        overlay=TelemetryOverlay(c,(960,540),0,c.duration,True,route)
        labels=[];original=ImageDraw.ImageDraw.text
        def record(draw,xy,value,*a,**kw):labels.append((str(value),xy));return original(draw,xy,value,*a,**kw)
        with patch.object(ImageDraw.ImageDraw,'text',record):
            overlay.render(Image.new('RGB',(960,540)),c.duration,35)
        final_y=next(xy[1] for value,xy in labels if value.startswith('FINAL GAP'))
        self.assertLess(final_y,480)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg missing')
    def test_real_encoder_keeps_every_native60_frame_and_shared_timestamp(self):
        c=comparison_fixture();timeline=cinematic_timeline(c,0,.6,60,3)
        times=[];output_times=[]
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as folder:
            folder=Path(folder);frames=folder/'frames';frames.mkdir()
            for i in range(12):
                image=Image.new('RGB',(128,128),'black')
                ImageDraw.Draw(image).rectangle((i*7,35,i*7+18,85),fill='white')
                image.save(frames/f'frame_{i+1:04d}.png')
            def compose(source,elapsed,output_time):
                times.append(elapsed);output_times.append(output_time);return source.convert('RGB')
            with patch('services.video_3d_overlay.TelemetryOverlay') as overlay:
                overlay.return_value.render.side_effect=compose
                output=folder/'native.mp4'
                encode_frames(c,frames,output,size=(128,128),fps=60,start=0,end=.6,
                    frames=12,full=False,playback_speed=3,driving_path={'timeline':timeline})
            info=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
                '-show_entries','stream=avg_frame_rate,nb_frames','-of','json',str(output)]))['streams'][0]
            self.assertEqual(info['avg_frame_rate'],'60/1');self.assertEqual(int(info['nb_frames']),12)
            decoded=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
            decoded=np.frombuffer(decoded,dtype=np.uint8).reshape(12,128,128,3)
            self.assertEqual(len({frame.tobytes() for frame in decoded}),12)
        np.testing.assert_allclose(times,np.arange(12)*.05,atol=1e-12)
        np.testing.assert_allclose(output_times,np.arange(12)/60,atol=1e-12)
