import unittest
import json,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
from types import SimpleNamespace
import numpy as np
from scipy.spatial import cKDTree
from services.singapore_asset import available,model_route,layout_for
from services.video_3d import render_3d_mp4
from test_video_comparison import comparison_fixture


class SingaporeAssetTests(unittest.TestCase):
    def test_year_boundary_is_shared_and_original_remains_legacy(self):
        for year in (2018,2021,2022):
            self.assertEqual(layout_for(year)['source'].name,'singapore.glb')
            self.assertEqual(layout_for(year)['key'],'pre-2023')
        for year in (2023,2024,2026,2030):
            self.assertEqual(layout_for(year)['source'].name,'singapore-2023.glb')
            self.assertEqual(layout_for(year)['key'],'2023-onward')
        self.assertNotEqual(layout_for(2022)['environment'],layout_for(2023)['environment'])

    def test_only_complete_current_bundle_is_available(self):
        source_stat=SimpleNamespace(st_size=123,st_mtime_ns=456)
        with patch('pathlib.Path.is_file',return_value=True), \
             patch('pathlib.Path.stat',return_value=source_stat), \
             patch('pathlib.Path.read_text',return_value='{"mode":"unmodified-glb","source_size":123,"source_mtime_ns":456}'):
            for year in (2022,2023,2026):self.assertTrue(available(year,'Singapore Grand Prix'))
            source_stat.st_size=124
            self.assertFalse(available(2023,'Singapore Grand Prix'))
        with patch('pathlib.Path.is_file',side_effect=lambda:self.fail('unexpected call')):
            self.assertFalse(available(2026,'Italian Grand Prix'))
        with patch('pathlib.Path.is_file',autospec=True,side_effect=lambda p:p!=layout_for(2023)['environment']):
            self.assertFalse(available(2026,'Singapore Grand Prix'))

    def fixture(self):
        p=np.linspace(0,1,720);a=p*2*np.pi
        xy=np.column_stack([700*np.cos(a)+100,700*np.sin(a)-200])
        track=np.column_stack([p,xy,5+np.sin(a)])
        points=np.column_stack([xy,47+.5*np.sin(a)])
        profile={'parameters':[0,0,0,0],'telemetry_origin':[0,0]}
        guide=Mock();guide.route.return_value={'xy':xy.tolist(),'progress':p.tolist(),
            'half_separation':[0.]*len(p),'separation_range':[0.,0.],'length_metres':4400}
        return SimpleNamespace(track=track), ({'points':points,'tree':cKDTree(points[:,:2]),'guide':guide},profile)

    def test_model_route_preserves_input_and_does_not_generate_a_track(self):
        comparison,ref=self.fixture();original=comparison.track.copy()
        with patch('services.singapore_asset.reference',return_value=ref), \
             patch('services.procedural_circuit.build_circuit') as build:
            route=model_route(comparison)
            build.assert_not_called()
        np.testing.assert_array_equal(original,comparison.track)
        xy=np.asarray(route['xy'])
        self.assertLess(np.linalg.norm(xy.mean(axis=0)-[100,-200]),3)
        self.assertEqual(route['source_glb'],str(layout_for(2023)['source']))
        self.assertTrue(route['unmodified_glb'])
        self.assertNotIn('asset_environment',route)
        self.assertFalse(route['provenance_verified'])
        self.assertIn('unchanged',route['environment_credit'])

    def test_wrong_session_alignment_fails_before_rendering(self):
        comparison,ref=self.fixture();comparison.track[:,1:3]+=10000
        with patch('services.singapore_asset.reference',return_value=ref):
            with self.assertRaisesRegex(ValueError,'aligned safely'):
                model_route(comparison)

    def test_driving_corridor_uses_year_selected_reference_and_environment(self):
        for year in (2022,2023,2026):
            comparison,ref=self.fixture();comparison.year=year
            with patch('services.singapore_asset.reference',return_value=ref) as load:
                route=model_route(comparison)
            load.assert_called_once_with(year)
            self.assertEqual(route['source_model'],str(layout_for(year)['source']))
            self.assertEqual(route['source_glb'],str(layout_for(year)['source']))

    def test_original_singapore_sources_are_rejected_for_previews_and_exports(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as folder:
            for year,fps in ((2022,24),(2023,30),(2026,24)):
                c=comparison_fixture();c.year=year;c.event='Singapore Grand Prix'
                route={'progress':[0.,1.],'xy':[[0.,0.],[0.,0.]],'half_separation':[0.,0.],
                       'source_glb':str(layout_for(year)['source']),'unmodified_glb':True,
                       'adaptation':'Original GLB','environment_credit':'Unchanged model'}
                configs=[]
                def worker(command,**kwargs):
                    configs.append(json.loads(Path(command[command.index('--config')+1]).read_text()))
                with patch('services.video_3d.availability',return_value=(True,'')), \
                     patch('services.singapore_asset.available',return_value=True), \
                     patch('services.singapore_asset.model_route',return_value=route), \
                     patch('services.procedural_circuit.build_circuit') as build, \
                     patch('services.cornering.cornering_route') as cornering, \
                     patch('services.video_3d.run_blender',side_effect=worker), \
                     patch('services.video_3d_overlay.encode_frames'):
                    with self.assertRaisesRegex(ValueError,'disabled'):
                        render_3d_mp4(c,Path(folder)/f'{year}.mp4',fps=fps,camera='Night chase A',
                                      start=0,end=1,environment='Original model')
                    build.assert_not_called();cornering.assert_not_called()
                self.assertEqual(configs,[])

    def test_telemetry_track_does_not_depend_on_original_model(self):
        c=comparison_fixture();c.year=2026;c.event='Singapore Grand Prix'
        mesh={'vertices':[[0,0,0]],'faces':[],'materials':[]}
        route={'xy':[[0,0],[1,1]],'progress':[0,1],'half_separation':[1.25,1.25]}
        with patch('services.video_3d.availability',return_value=(True,'')), \
             patch('services.singapore_asset.available',return_value=False), \
             patch('services.singapore_asset.model_route') as original, \
             patch('services.procedural_circuit.build_circuit',return_value=(mesh,route)) as build, \
             patch('services.circuit_scenery.scenery_plan',return_value={'version':'test-plan'}), \
             patch('services.video_3d.run_blender') as worker, \
             patch('services.video_3d_overlay.encode_frames'):
                render_3d_mp4(c,Path('tmp/unpublished.mp4'),start=0,end=1)
        build.assert_called_once();worker.assert_called_once();original.assert_not_called()
