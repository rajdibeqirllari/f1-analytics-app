from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from fastf1.core import Laps

import numpy as np
import pandas as pd

from services.video_comparison import Comparison, ComparisonLap, prepare_lap_samples, _select_lap
from services.video_renderer import ComparisonRenderer, lap_clock, render_mp4


def fixture(duration=20, offset=1000):
    t=np.linspace(0,duration,161)
    angle=t/duration*2*np.pi
    return pd.DataFrame({"SessionTime":pd.to_timedelta(offset+t,unit="s"),
                         "Speed":np.full(len(t),220),"X":1000*np.cos(angle),"Y":1000*np.sin(angle),
                         "Throttle":np.full(len(t),90),"RPM":np.full(len(t),11000),
                         "nGear":np.full(len(t),7),"Brake":False,"DRS":12})


def comparison_fixture():
    laps=[]
    for duration,offset,code,color in [(20,1000,"AAA","#63f3d1"),(22,9000,"BBB","#ff655e")]:
        data,warnings=prepare_lap_samples(fixture(duration,offset),offset,duration)
        laps.append(ComparisonLap(code,code+" Driver","Team",color,4,duration,data,warnings))
    data=laps[0].samples
    track=data[["progress","x","y","z"]].to_numpy()
    return Comparison(2025,"Test Grand Prix","Qualifying",tuple(laps),track,[])


class ComparisonTests(unittest.TestCase):
    def test_independent_session_epochs_and_original_lap_durations(self):
        comparison=comparison_fixture()
        a,b=comparison.laps
        self.assertAlmostEqual(a.at(10)["progress"],.5)
        self.assertAlmostEqual(b.at(11)["progress"],.5)
        self.assertEqual(a.samples["t"].iloc[0],0)
        self.assertEqual(b.samples["t"].iloc[0],0)
        self.assertTrue(a.at(20)["finished"])
        self.assertFalse(b.at(20)["finished"])
        self.assertAlmostEqual(b.at(20)["progress"],20/22)

    def test_delta_sign_and_official_finish_difference(self):
        comparison=comparison_fixture()
        self.assertAlmostEqual(comparison.delta_at(0),0)
        self.assertAlmostEqual(comparison.delta_at(.5),1)
        self.assertAlmostEqual(comparison.delta_at(1),2)

    def test_discrete_channels_never_anticipate_a_change(self):
        raw=fixture()
        raw.loc[raw.index>=80,"nGear"]=3
        raw.loc[raw.index>=80,"Brake"]=True
        data,_=prepare_lap_samples(raw,1000,20)
        lap=ComparisonLap("AAA","A","Team","#ffffff",1,20,data,[])
        self.assertEqual(lap.at(9.99)["gear"],7)
        self.assertFalse(lap.at(9.99)["brake"])
        self.assertEqual(lap.at(10)["gear"],3)
        self.assertTrue(lap.at(10)["brake"])

    def test_incomplete_lap_and_gaps_are_rejected(self):
        raw=fixture()
        with self.assertRaisesRegex(ValueError,"complete"):
            prepare_lap_samples(raw.iloc[20:],1000,20)
        with self.assertRaisesRegex(ValueError,"gap"):
            prepare_lap_samples(raw.drop(raw.index[50:90]),1000,20)

    def test_render_sizes_and_time_formatter(self):
        comparison=comparison_fixture()
        for size in [(540,960),(960,540)]:
            renderer=ComparisonRenderer(comparison,size)
            for elapsed in [0,10,22]:
                self.assertEqual(renderer.render(elapsed).size,size)
        self.assertEqual(lap_clock(59.9996),"1:00.000")

    def test_missing_channels_are_disclosed(self):
        raw=fixture().drop(columns=["nGear","Throttle","Brake"])
        _,warnings=prepare_lap_samples(raw,1000,20)
        for channel in ["nGear","Throttle","Brake"]:
            self.assertTrue(any(channel+" is unavailable" in warning for warning in warnings))

    def test_fastest_excludes_deleted_but_explicit_lap_is_available(self):
        laps=Laps(pd.DataFrame({"Driver":["AAA"]*3,"DriverNumber":["1"]*3,
                               "LapNumber":[1,2,3],"LapTime":pd.to_timedelta([20,18,19],unit="s"),
                               "LapStartTime":pd.to_timedelta([0,30,60],unit="s"),
                               "Deleted":[False,True,None]}))
        session=SimpleNamespace(laps=laps)
        self.assertEqual(_select_lap(session,"AAA",None,"All")["LapNumber"],3)
        self.assertEqual(_select_lap(session,"AAA",2,"All")["LapNumber"],2)
        with self.assertRaisesRegex(ValueError,"No suitable lap"):
            _select_lap(session,"AAA",99,"All")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg not installed")
    def test_real_mp4_encoding_finish_hold_and_cancellation(self):
        test_root=Path(__file__).resolve().parents[1]/"tmp"
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            path=Path(directory)/"test.mp4"
            render_mp4(comparison_fixture(),path,size=(270,480),fps=24,start=21.5,end=22)
            probe=subprocess.check_output(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)])
            info=json.loads(probe)
            stream=info["streams"][0]
            self.assertEqual((stream["width"],stream["height"]),(270,480))
            self.assertEqual(stream["codec_name"],"h264")
            self.assertEqual(stream["nb_frames"],"61")
            self.assertAlmostEqual(float(info["format"]["duration"]),61/24,places=2)
            cancelled=Path(directory)/"cancelled.mp4"
            with self.assertRaises(InterruptedError):
                render_mp4(comparison_fixture(),cancelled,size=(270,480),cancelled=lambda:True)
            self.assertFalse(cancelled.exists())
            self.assertFalse(cancelled.with_suffix(".partial.mp4").exists())


if __name__=="__main__":
    unittest.main()
