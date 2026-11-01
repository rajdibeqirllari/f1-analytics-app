import unittest
from types import SimpleNamespace
import pandas as pd
from services.engine_audio import bank_for_team,telemetry_controls


class EngineAudioTests(unittest.TestCase):
    def test_bank_uses_team_not_driver(self):
        self.assertEqual(bank_for_team('Red Bull Racing',2026)['profile'],'redbull')
        self.assertEqual(bank_for_team('Scuderia Ferrari',2026)['profile'],'ferrari')
        with self.assertRaises(ValueError):bank_for_team('Unknown',2026)
        with self.assertRaises(ValueError):bank_for_team('Mercedes',2022)

    def test_real_inputs_and_discrete_shifts(self):
        lap=SimpleNamespace(lap_time=2.,warnings=[],samples=pd.DataFrame(dict(
            t=[0.,1.,2.],rpm=[6000,10000,7000],throttle=[0,100,0],
            speed=[100,200,150],gear=[3,4,3],brake=[False,False,True])))
        controls=telemetry_controls(lap,rate=20)
        self.assertEqual(controls['rpms'][10],8000)
        self.assertEqual(controls['throttle'][10],.5)
        self.assertEqual(controls['gear'][19],3)
        self.assertEqual(controls['shifts'],[dict(time=1.,direction='up'),dict(time=2.,direction='down')])
        lap.warnings=['RPM is unavailable; its display is omitted.']
        with self.assertRaisesRegex(ValueError,'RPM'):telemetry_controls(lap)
