import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import wave
import numpy as np
from PIL import Image,ImageDraw
from services.recorded_music import music_info,load_track,recorded_block,add_music_credit,strong_entry
from services.duel_audio import validate_audio
from services.recorded_music import render_recorded_score


class RecordedMusicTests(unittest.TestCase):
    def test_callouts_and_result_do_not_interrupt_music(self):
        rate=48000
        # A constant test recording isolates mixer-induced dips from natural
        # quiet moments in an artist's recording. Cue at 1s, result at 2s.
        source=np.full((rate*10,2),.15,dtype=np.float32)
        controls=dict(times=np.arange(241)/60,dominance=np.zeros(241),
                      cues=[dict(time=1.,driver=0,gain=.1)],finish=2.,seconds=4.)
        with tempfile.TemporaryDirectory() as folder,patch('services.recorded_music.load_track',return_value=source),\
             patch('services.recorded_music.strong_entry',return_value=0),\
             patch('services.duel_audio.duel_controls',return_value=controls):
            path=Path(folder)/'continuous.wav'
            report=render_recorded_score(None,None,path)
            with wave.open(str(path)) as wav:
                samples=np.frombuffer(wav.readframes(wav.getnframes()),'<i2').reshape(-1,2)/32768
            baseline=np.sqrt((samples[int(.4*rate):int(.6*rate)]**2).mean())
            for start,end in ((.85,.99),(1.1,1.25),(1.95,2.05),(2.5,3.5)):
                rms=np.sqrt((samples[int(start*rate):int(end*rate)]**2).mean())
                self.assertGreater(rms,baseline*.95)
            self.assertLess(np.abs(samples[-1]).max(),.001)
            self.assertFalse(report['cue_ducking'])
            self.assertTrue(report['music_continues_through_results'])

    def test_recordings_are_local_valid_stereo_and_have_credits(self):
        for style,title in (('The Duel','Industrial Cinematic'),('Grit & Drums','Gearhead')):
            samples=load_track(style)
            self.assertEqual(samples.shape[1],2);self.assertGreater(len(samples),48000*60)
            self.assertTrue(np.isfinite(samples).all())
            entry=strong_entry(samples);self.assertGreaterEqual(entry,0);self.assertLess(entry,60)
            info=music_info(style)
            self.assertEqual(info['title'],title)
            self.assertIn('creativecommons.org/licenses/by/4.0/',info['attribution'])
            self.assertIn('Edited:',info['attribution'])
            self.assertEqual(validate_audio(style,80),(style,80))

    def test_missing_recording_fails_without_synthetic_fallback(self):
        with patch('pathlib.Path.is_file',return_value=False):
            with self.assertRaisesRegex(ValueError,'no synth fallback'):
                load_track('The Duel')

    def test_long_video_loop_is_continuous_at_wrap(self):
        rate=48000;t=np.arange(rate*10)/rate
        source=np.column_stack([.2*np.sin(t*2*np.pi*23.7),.2*np.cos(t*2*np.pi*31.2)]).astype(np.float32)
        period=10-1-.25
        output=recorded_block(source,np.array([period-1/rate,period,period+1/rate]),1.)
        self.assertLess(np.abs(np.diff(output,axis=0)).max(),.002)

    def test_visible_attribution_added_in_all_aspect_ratios(self):
        original=ImageDraw.ImageDraw.text
        for size in ((540,960),(960,540),(1080,1920),(1920,1080)):
            labels=[]
            def record(draw,xy,value,*args,**kwargs):
                labels.append((xy,str(value)));return original(draw,xy,value,*args,**kwargs)
            with patch.object(ImageDraw.ImageDraw,'text',record):
                output=add_music_credit(Image.new('RGB',size),music_info())
            self.assertEqual(output.size,size)
            self.assertTrue(any('Industrial Cinematic' in value for _,value in labels))
            self.assertTrue(any('creativecommons.org/licenses/by/4.0/' in value for _,value in labels))
            self.assertTrue(all(0<=xy[1]<size[1] for xy,_ in labels))
        self.assertIsNone(music_info('Silent'))


if __name__=='__main__':unittest.main()
