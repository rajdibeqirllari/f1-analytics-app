import unittest
import numpy as np
from services.engine_samples import steady_grain,synthesize,calibrated_layers,mix_layers


class SampleMixerTests(unittest.TestCase):
    def test_real_controls_drive_continuous_pitch_and_output(self):
        rate=48000
        t=np.arange(rate*2)/rate
        source=(np.sin(2*np.pi*440*t)*.2).astype(np.float32)
        samples={'on':(source,rate),'decel':(source*.5,rate)}
        controls=dict(time=[0,1,2],rpms=[7000,10500,12500],
                      throttle=[1,1,0],speed_kmh=[100,200,150],
                      shifts=[dict(time=1.,direction='up')])
        audio=synthesize(controls,samples)
        self.assertEqual(len(audio),96000)
        self.assertTrue(np.isfinite(audio).all())
        self.assertGreater(np.sqrt(np.mean(audio*audio)),.03)
        self.assertLess(np.max(np.abs(audio)),1)
        self.assertEqual(audio[0],0)
        self.assertEqual(audio[-1],0)
        self.assertLess(np.quantile(np.abs(np.diff(audio)),.999),.05)

    def test_silence_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'audible'):
            steady_grain(np.zeros(48000),48000)

    def test_native_source_pitch_is_calibrated_instead_of_assumed(self):
        rate=16000
        t=np.arange(rate*4)/rate
        for native in (310.,610.):
            layers=calibrated_layers((.2*np.sin(2*np.pi*native*t)).astype(np.float32),rate)
            self.assertGreater(len(layers[0]['audio'])/rate,1.)
            self.assertAlmostEqual(layers[0]['pitch'],native,delta=1.)
            audio=mix_layers(layers,np.full(rate*2,500.))
            spectrum=np.abs(np.fft.rfft(audio[rate//2:rate*3//2]))
            peak=np.fft.rfftfreq(rate,1/rate)[np.argmax(spectrum)]
            self.assertAlmostEqual(peak,500.,delta=3.)
