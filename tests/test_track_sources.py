import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from services.circuits_3d import CIRCUITS,environment_options,resolve_environment
from services.video_3d import availability,render_3d_mp4,CAR,CAR_METADATA
from test_video_comparison import comparison_fixture

ROOT=Path(__file__).resolve().parents[1]


class TrackSourceTests(unittest.TestCase):
    def test_every_supported_circuit_offers_only_telemetry(self):
        for circuit in CIRCUITS:
            options=environment_options(circuit.preset_year,circuit.event)
            self.assertEqual(options,('Telemetry-built',))
            with self.assertRaisesRegex(ValueError,'disabled'):
                resolve_environment(circuit.preset_year,circuit.event,'Original model')
        self.assertEqual(environment_options(2021,'French Grand Prix'),('Telemetry-built',))
        self.assertEqual(resolve_environment(2022,'French Grand Prix','Auto'),'Telemetry-built')
        self.assertEqual(resolve_environment(2026,'Singapore Grand Prix','Auto'),'Telemetry-built')

    def test_telemetry_mode_needs_no_circuit_asset_bundle(self):
        with patch('services.video_3d.blender_executable',return_value='blender'), \
             patch('services.video_3d.shutil.which',return_value='ffmpeg'), \
             patch('pathlib.Path.is_file',autospec=True,side_effect=lambda path:path in (CAR,CAR_METADATA)):
            for year,event in ((2022,'French Grand Prix'),(2026,'Singapore Grand Prix')):
                self.assertTrue(availability(year,event,'Telemetry-built')[0])
                self.assertFalse(availability(year,event,'Original model')[0])

    def test_all_telemetry_preview_and_export_jobs_remain_separate_from_models(self):
        mesh={'vertices':[[0,0,0]],'faces':[],'materials':[]}
        route={'xy':[[0,0],[1,1]],'progress':[0,1],'half_separation':[0,0]}
        for circuit in CIRCUITS:
            for fps,size in ((24,(540,960)),(30,(720,1280))):
                comparison=comparison_fixture();comparison.event=circuit.event;comparison.year=circuit.preset_year
                configs=[]
                def worker(command,**kwargs):
                    configs.append(json.loads(Path(command[command.index('--config')+1]).read_text()))
                with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder, \
                     patch('services.video_3d.availability',return_value=(True,'')), \
                     patch('services.procedural_circuit.build_circuit',return_value=(mesh,route)) as build, \
                     patch('services.cornering.cornering_route',side_effect=lambda route,mesh:route), \
                     patch('services.circuit_scenery.scenery_plan',return_value={'version':'test-plan'}), \
                     patch('services.singapore_asset.model_route') as original, \
                     patch('services.video_3d.run_blender',side_effect=worker), \
                     patch('services.video_3d_overlay.encode_frames'):
                    render_3d_mp4(comparison,Path(folder)/'result.mp4',fps=fps,size=size,
                        camera='Night chase A',start=0,end=1,environment='Telemetry-built')
                    build.assert_called_once();original.assert_not_called()
                config=configs[0]
                self.assertEqual(config['generated_road'],mesh)
                self.assertEqual(config['track_source'],'Telemetry-built')
                self.assertNotIn('source_glb',config);self.assertNotIn('asset_environment',config)
                self.assertEqual(config['circuit_presentation']['backend'],'telemetry')
                self.assertNotIn('narlankaaditya',config['circuit_presentation']['credit'])
