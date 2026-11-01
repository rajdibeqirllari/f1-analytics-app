import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw
from services.limit_story import LimitStory, limit_timeline
from services.video_3d_overlay import TelemetryOverlay
from services.cinematic_timeline import cinematic_timeline
from test_video_comparison import comparison_fixture


class LimitTests(unittest.TestCase):
    def setUp(self):
        self.c = comparison_fixture()
        self.path = dict(progress=self.c.track[:,0], xy=self.c.track[:,1:3],
                         half_separation=np.zeros(len(self.c.track)), social_director=True,
                         cinematic_ghost=True, the_limit=True, playback_speed=3)

    def test_intro_does_not_skip_or_change_lap(self):
        old=cinematic_timeline(self.c,0,self.c.duration,60,3,full=True)
        new=limit_timeline(old)
        self.assertEqual(new['source_times'][:192],[0]*192)
        self.assertEqual(new['source_times'][192:],old['source_times'])
        self.assertEqual(new['trail_times'][192:],old['trail_times'])
        self.assertAlmostEqual(new['output_seconds'],old['output_seconds']+3.2)
        self.assertEqual(new['action_seconds'],old['action_seconds'])

    def test_sculpture_and_beats_use_matched_distance_data(self):
        story=LimitStory(self.c,self.path)
        np.testing.assert_allclose(story.delta,[self.c.delta_at(p) for p in story.progress])
        for beat in story.beats:
            swing=self.c.delta_at(beat['end'])-self.c.delta_at(beat['start'])
            self.assertAlmostEqual(beat['gain'],abs(swing))
            self.assertEqual(beat['driver'],0 if swing>0 else 1)
        for yaw in (-2,0,2):
            a,b=story.project(yaw,zoom=3,focus=.3)
            self.assertTrue(np.isfinite(a).all() and np.isfinite(b).all())

    def test_live_api_and_job_queue_accept_the_limit(self):
        from api.main import app,video_requests
        from fastapi.testclient import TestClient
        from services.video_renderer import VideoJobs
        from services.video_comparison import VideoSelection
        with patch('api.main.videos.submit',return_value='limit-test') as submit:
            response=TestClient(app).post('/api/jobs',json=dict(kind='video',
                selection=dict(year=2026,event='United States Grand Prix',session='Q',driver='ANT',driver_b='VER'),
                options=dict(style='3D',camera='The Limit',fps=60,pacing='Dynamic cinematic')))
            self.assertEqual(response.status_code,202,response.text)
            self.assertEqual(submit.call_args.kwargs['camera'],'The Limit')
            video_requests.pop('limit-test',None)
        queue=VideoJobs()
        try:
            with patch.object(queue.executor,'submit'),patch('services.video_3d.availability',return_value=(True,'')):
                key=queue.submit(VideoSelection(2026,'United States Grand Prix','Q','ANT','VER'),
                                 style='3D',camera='The Limit',fps=60)
                self.assertIn(key,queue.jobs)
        finally:queue.executor.shutdown(wait=False)

    def test_invalid_geometry_and_time_rejected(self):
        with self.assertRaises(ValueError):LimitStory(self.c,dict(self.path,xy=[[float('nan'),0]]))
        with self.assertRaises(ValueError):LimitStory(self.c,dict(self.path,progress=np.zeros(len(self.c.track))))
        with patch.object(self.c,'delta_at',return_value=float('nan')):
            with self.assertRaises(ValueError):LimitStory(self.c,self.path)

    def test_gain_callout_uses_readable_output_seconds(self):
        self.path['timeline']=limit_timeline(cinematic_timeline(self.c,0,self.c.duration,60,20,full=True))
        overlay=TelemetryOverlay(self.c,(540,960),0,self.c.duration,True,self.path).director_overlay
        beat=min(overlay.story.beats,key=lambda b:b['start'])
        cue=self.c.laps[0].time_at_distance(beat['start'])
        clock=np.asarray(self.path['timeline']['source_times']);out=np.arange(len(clock))/60
        cue_out=np.interp(cue,clock,out)
        labels=[];original=ImageDraw.ImageDraw.text
        def record(draw,xy,value,*args,**kwargs):
            labels.append(str(value));return original(draw,xy,value,*args,**kwargs)
        with patch.object(ImageDraw.ImageDraw,'text',record):
            # 1.5 real screen seconds later, even at 20x, label is present.
            # Use an unfinished pose to isolate the editorial lifetime rule.
            overlay.from_replay(Image.new('RGB',(540,960)),cue,cue_out+1.5)
        self.assertTrue(any('FINDS' in v for v in labels))

    def test_portrait_landscape_intro_replay_payoff_and_labels(self):
        timeline=limit_timeline(cinematic_timeline(self.c,0,self.c.duration,60,3,full=True))
        self.path['timeline']=timeline
        labels=[];original=ImageDraw.ImageDraw.text
        def record(draw,xy,value,*args,**kwargs):
            labels.append(str(value));return original(draw,xy,value,*args,**kwargs)
        with patch.object(ImageDraw.ImageDraw,'text',record):
            for size in ((540,960),(960,540)):
                overlay=TelemetryOverlay(self.c,size,0,self.c.duration,True,self.path)
                for elapsed,out in ((0,0),(0,2.9),(3,4.2),(self.c.duration,timeline['output_seconds']-.1)):
                    result=overlay.render(Image.new('RGB',size),elapsed,out)
                    self.assertEqual(result.size,size);self.assertEqual(result.mode,'RGB')
        self.assertIn('2.000 SECONDS',labels)
        self.assertIn('Exaggerated timing sculpture · NOT track elevation',labels)
        self.assertTrue(any('WINS BY 2.000s' in label for label in labels))


if __name__=='__main__':unittest.main()
