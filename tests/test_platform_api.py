"""HTTP integration and data-integrity checks; fixtures are test-only samples."""
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
from api.main import app
from api import engines
from api.files import approved,ROOT

class PlatformAPITests(unittest.TestCase):
    def setUp(self): self.client=TestClient(app)

    def wait(self,key):
        for _ in range(100):
            response=self.client.get('/api/jobs/'+key)
            self.assertEqual(response.status_code,200)
            job=response.json()
            if job['status'] in ('complete','failed','cancelled'): return job
            time.sleep(.02)
        self.fail('Test job did not complete')

    def selection(self):
        return dict(year=2024,event='Italian Grand Prix',session='Q',driver='LEC',driver_b='VER')

    def test_server_never_imports_streamlit_entry_points(self):
        self.assertNotIn('app',sys.modules)
        self.assertNotIn('overlay_app',sys.modules)
        self.assertNotIn('ui.workspaces',sys.modules)

    def test_all_spa_routes_and_health(self):
        for route in ('/','/timing','/analysis','/videos','/telemetry','/overlays','/replay','/radio','/downloads'):
            response=self.client.get(route)
            self.assertEqual(response.status_code,200)
            self.assertIn('id="root"',response.text)
        health=self.client.get('/api/health').json()
        self.assertEqual(sum(map(len,health['charts'].values())),17)

    def test_catalog_and_provider_errors_are_async_and_visible(self):
        with patch('api.engines.catalog',return_value={'drivers':{'LEC':{'laps':[1]}}}):
            response=self.client.post('/api/jobs',json=dict(kind='catalog',selection=self.selection()))
            self.assertEqual(response.status_code,202)
            job=self.wait(response.json()['id'])
            self.assertEqual(job['result']['drivers']['LEC']['laps'],[1])
        with patch('api.engines.catalog',side_effect=ValueError('Timing provider unavailable')):
            key=self.client.post('/api/jobs',json=dict(kind='catalog',selection=self.selection())).json()['id']
            job=self.wait(key)
            self.assertEqual(job['status'],'failed')
            self.assertIn('provider unavailable',job['error'])
            self.assertIsNone(job['result'])

    def test_download_ids_cannot_escape_output_roots(self):
        self.assertFalse(approved(ROOT/'app.py'))
        self.assertFalse(approved(ROOT/'assets'/'3d'/'singapore.glb'))
        self.assertFalse(approved(ROOT/'outputs'/'..'/'app.py'))
        self.assertEqual(self.client.get('/api/files/not-a-real-id').status_code,404)
        self.assertEqual(self.client.get('/art/3d/circuits/singapore/singapore.glb').status_code,404)

    def test_cross_site_changes_are_rejected(self):
        response=self.client.post('/api/jobs',headers={'Origin':'https://example.com'},json=dict(kind='catalog',selection=self.selection()))
        self.assertEqual(response.status_code,403)

    def test_upload_exports_keep_future_fields_null(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with patch('api.main.ROOT',root),patch('api.engines.ROOT',root),patch('api.files.ROOT',root),patch('api.files.OUTPUT_ROOTS',{'outputs':root/'outputs'}):
                self.check_upload_exports()

    def check_upload_exports(self):
        # A minimal test fixture, never displayed as a genuine racing session.
        csv=b'Time,Speed,RPM,nGear,Throttle,Brake\n0,100,9000,3,50,0\n0.1,102,9100,3,60,0\n'
        upload=self.client.post('/api/uploads',files={'file':('test-fixture.csv',csv,'text/csv')})
        self.assertEqual(upload.status_code,200)
        key=self.client.post('/api/jobs',json=dict(kind='telemetry',selection=self.selection(),options=dict(source='Upload CSV',upload_id=upload.json()['id']))).json()['id']
        job=self.wait(key)
        self.assertEqual(job['status'],'complete',job['error'])
        self.assertEqual(len(job['result']['files']),4)
        self.assertEqual(job['result']['metadata']['source'],'Upload CSV')
        for row in job['result']['preview']:
            for col in ('boost_mode','recharge_mode','active_aero_mode','overtake_mode'): self.assertIsNone(row[col])
        for file in job['result']['files']:
            response=self.client.get(file['url']+'?download=true')
            self.assertEqual(response.status_code,200)
            self.assertIn('attachment',response.headers['content-disposition'])

    def test_auto_source_preserves_actual_openf1_fallback(self):
        fixture=pd.DataFrame({'time_sec':[0.,.1],'speed_kmh':[100.,101.]})
        from api.main import Selection
        with patch('api.engines.session_for',side_effect=ValueError('FastF1 unavailable')),patch('api.engines.load_openf1_lap',return_value=(fixture,fixture,{},dict(lap_number=7))):
            lap,full,meta=engines.load_telemetry(Selection(**self.selection()),'Auto')
            self.assertEqual(meta['source'],'OpenF1')
            self.assertEqual(meta['lap_number'],7)
            self.assertIn('FastF1 unavailable',meta['fallback'])

    def test_invalid_job_inputs_and_video_camera(self):
        response=self.client.post('/api/jobs',json=dict(kind='video',selection=self.selection(),options=dict(camera='unknown')))
        self.assertEqual(response.status_code,422)
        response=self.client.post('/api/jobs',json=dict(kind='video',selection=self.selection(),options=dict(start=10,end=5)))
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.client.post('/api/jobs',json=dict(kind='unknown',selection=self.selection())).status_code,422)
        self.assertEqual(self.client.post('/api/jobs',json=dict(kind='replay',selection={**self.selection(),'session':'FP1'})).status_code,422)

    def test_video_handoff_uses_existing_worker_and_telemetry_only(self):
        with patch('api.main.videos.submit',return_value='test-render') as render:
            response=self.client.post('/api/jobs',json=dict(kind='video',selection=self.selection(),options=dict(style='3D',camera='Night chase B',quality='High',resolution=720,preview=False)))
            self.assertEqual(response.status_code,202)
            self.assertEqual(render.call_args.kwargs['environment'],'Telemetry-built')
            self.assertEqual(render.call_args.kwargs['camera'],'Night chase B')
            self.assertEqual(render.call_args.args[0].driver_a,'LEC')
            self.assertEqual(render.call_args.args[0].driver_b,'VER')
            self.assertFalse(render.call_args.kwargs['preview'])

    def test_accelerated_director_handoff_and_invalid_speeds(self):
        with patch('api.main.videos.submit',return_value='speed-test-render') as render:
            response=self.client.post('/api/jobs',json=dict(kind='video',selection=self.selection(),
                options=dict(style='3D',camera='Social director',playback_speed=3)))
            self.assertEqual(response.status_code,202)
            self.assertEqual(render.call_args.kwargs['camera'],'Social director')
            self.assertEqual(render.call_args.kwargs['playback_speed'],3)
            self.assertEqual(render.call_args.kwargs['fps'],24)
            for speed in (0,-1,4,100,True,None):
                response=self.client.post('/api/jobs',json=dict(kind='video',selection=self.selection(),
                    options=dict(playback_speed=speed)))
                self.assertEqual(response.status_code,422)
            self.assertEqual(render.call_count,1)

    def test_native60_cinematic_controls_are_validated_and_forwarded(self):
        with patch('api.main.videos.submit',return_value='cinematic-test') as render:
            options=dict(style='3D',camera='Cinematic Ghost Chase',fps=60,playback_speed=3,
                         pacing='Dynamic cinematic',target_duration=35,camera_options=dict(smoothness=.6))
            response=self.client.post('/api/jobs',json=dict(kind='video',selection=self.selection(),options=options))
            self.assertEqual(response.status_code,202)
            for key in ('fps','camera','pacing','target_duration','camera_options'):
                self.assertEqual(render.call_args.kwargs[key],options[key])
            for bad in (dict(target_duration=None),dict(target_duration=29),dict(pacing='fake'),dict(camera_options={'zoom':99})):
                response=self.client.post('/api/jobs',json=dict(kind='video',selection=self.selection(),options={**options,**bad}))
                self.assertEqual(response.status_code,422)
            self.assertEqual(render.call_count,1)

if __name__=='__main__': unittest.main()
