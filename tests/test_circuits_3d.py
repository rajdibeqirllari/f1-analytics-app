import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from services.circuits_3d import CIRCUITS,circuit_for,presentation
from services.procedural_circuit import build_circuit,strip_mesh
from services.video_3d import availability,render_3d_mp4,CAR,CAR_METADATA
from test_video_comparison import comparison_fixture
from pathlib import Path
import json,tempfile


class CircuitTests(unittest.TestCase):
    def test_catalogue_years_and_unknown_venues_are_explicit(self):
        self.assertGreaterEqual(len(CIRCUITS),24)
        self.assertEqual(len({c.key for c in CIRCUITS}),len(CIRCUITS))
        self.assertTrue(all(c.backend=='telemetry' for c in CIRCUITS))
        for event in ('Italian Grand Prix','British Grand Prix','Belgian Grand Prix',
                      'Singapore Grand Prix','Monaco Grand Prix','Austrian Grand Prix','Bahrain Grand Prix'):
            self.assertEqual(circuit_for(2024,event).backend,'telemetry')
            self.assertIsNone(circuit_for(2017,event))
        self.assertEqual(circuit_for(2022,'French Grand Prix').backend,'telemetry')
        self.assertEqual(circuit_for(2024,'French Grand Prix').backend,'telemetry')
        self.assertIsNone(circuit_for(2024,'Unknown Grand Prix'))

    def test_generated_circuits_do_not_need_a_paul_ricard_asset(self):
        with patch('services.video_3d.blender_executable',return_value='blender'), \
             patch('services.video_3d.shutil.which',return_value='ffmpeg'), \
             patch('pathlib.Path.is_file',autospec=True,side_effect=lambda path:path in (CAR,CAR_METADATA)):
            self.assertTrue(availability(2024,'Italian Grand Prix')[0])
            self.assertTrue(availability(2022,'French Grand Prix')[0])
        with patch('services.video_3d.blender_executable',return_value=None):
            self.assertIn('Blender',availability(2024,'Italian Grand Prix')[1])

    def test_titles_and_credits_do_not_misattribute_generated_tracks(self):
        monza=presentation(2024,'Italian Grand Prix')
        self.assertEqual(monza['name'],'Monza')
        self.assertNotIn('narlankaaditya',monza['credit'])
        self.assertIn('estimated grade / flat fallback',monza['description'])
        self.assertIn('CC BY',presentation(2022,'French Grand Prix')['credit'])

    def fixture(self):
        p=np.linspace(0,1,720);angle=p*2*np.pi
        return SimpleNamespace(track=np.column_stack([p,400*np.cos(angle),400*np.sin(angle),p*3]))

    def test_procedural_route_is_closed_contained_and_preserves_input(self):
        comparison=self.fixture();original=comparison.track.copy()
        mesh,route=build_circuit(comparison)
        np.testing.assert_array_equal(original,comparison.track)
        np.testing.assert_allclose(route['xy'][0],route['xy'][-1])
        self.assertTrue(np.isfinite(mesh['vertices']).all())
        self.assertEqual(mesh['half_width_metres'],6)
        self.assertEqual(set(mesh['materials']),{0,2,3})
        self.assertGreater(route['minimum_center_clearance'],4)
        self.assertLess(abs(route['length_metres']-2*np.pi*400),15)

    def test_bad_or_incomplete_layouts_fail_before_renderer(self):
        comparison=self.fixture();comparison.track[0,1]=np.nan
        with self.assertRaisesRegex(ValueError,'finite'):build_circuit(comparison)
        comparison=self.fixture();comparison.track[-1,1]+=100
        with self.assertRaisesRegex(ValueError,'close'):build_circuit(comparison)
        comparison=self.fixture();comparison.track[:,1:3]/=10
        with self.assertRaisesRegex(ValueError,'length'):build_circuit(comparison)

    def test_generated_geometry_reaches_preview_and_export_pipeline(self):
        comparison=comparison_fixture();comparison.year=2024;comparison.event='Italian Grand Prix'
        mesh={'vertices':[[0,0,0]],'faces':[],'materials':[]}
        route={'xy':[[0,0],[1,1]],'progress':[0,1],'half_separation':[1.25,1.25]}
        def worker(command,**kwargs):
            config=json.loads(Path(command[command.index('--config')+1]).read_text())
            self.assertEqual(config['generated_road'],mesh)
            actual=config['driving_path']
            self.assertEqual({k:v for k,v in actual.items() if k not in ('timeline','output_fps')},dict(route,track_source='Telemetry-built',playback_speed=1.))
            self.assertEqual(actual['timeline'],config['timeline'])
            self.assertEqual(actual['output_fps'],config['fps'])
            self.assertEqual(config['circuit_presentation']['name'],'Monza')
            self.assertEqual(config['scenery_plan'],{'version':'test-plan'})
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root/'tmp') as folder, \
             patch('services.video_3d.availability',return_value=(True,'')), \
             patch('services.procedural_circuit.build_circuit',return_value=(mesh,route)), \
             patch('services.circuit_scenery.scenery_plan',return_value={'version':'test-plan'}), \
             patch('services.video_3d.fit_path') as fit, \
             patch('services.video_3d.run_blender',side_effect=worker), \
             patch('services.video_3d_overlay.encode_frames') as encode:
            for size,fps in [((540,960),24),((1280,720),30),((1080,1920),60)]:
                render_3d_mp4(comparison,Path(folder)/'video.mp4',start=0,end=1,size=size,fps=fps)
                self.assertEqual(encode.call_args.kwargs['size'],size)
                actual=encode.call_args.kwargs['driving_path']
                self.assertEqual({k:v for k,v in actual.items() if k not in ('timeline','output_fps')},dict(route,track_source='Telemetry-built',playback_speed=1.))
                self.assertEqual(len(actual['timeline']['source_times']),fps)
            fit.assert_not_called()


if __name__=='__main__':unittest.main()
