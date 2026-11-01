import unittest
from services.circuits_3d import CIRCUITS, environment_options, resolve_environment
from services.video_3d import availability


class TelemetryOnlyPolicyTests(unittest.TestCase):
    def test_entire_2026_fallback_calendar_has_telemetry_support(self):
        import ast
        from pathlib import Path
        from services.circuits_3d import circuit_for
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf8'))
        races=next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FALLBACK_2026_RACES' for t in node.targets))
        for race in races:
            self.assertIsNotNone(circuit_for(2026,race['EventName']),race['EventName'])
        for event in ('Bahrain Grand Prix','Saudi Arabian Grand Prix'):
            self.assertIsNotNone(circuit_for(2026,event))

    def test_all_presets_default_to_telemetry(self):
        for circuit in CIRCUITS:
            with self.subTest(circuit=circuit.key):
                self.assertEqual(environment_options(circuit.preset_year,circuit.event),('Telemetry-built',))
                self.assertEqual(resolve_environment(circuit.preset_year,circuit.event),'Telemetry-built')

    def test_original_sources_are_rejected_before_rendering(self):
        for year,event in ((2022,'Singapore Grand Prix'),(2026,'Singapore Grand Prix'),(2022,'French Grand Prix')):
            with self.subTest(year=year,event=event):
                ready,reason=availability(year,event,environment='Original model')
                self.assertFalse(ready)
                self.assertIn('disabled',reason)
