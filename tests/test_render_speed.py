import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from services.video_3d import render_cache_key
from services.video_3d import render_3d_mp4
from test_video_comparison import comparison_fixture


class RenderSpeedTests(unittest.TestCase):
    def test_cache_ignores_temp_directory_but_not_render_options(self):
        config={'work_dir':'one','fps':24,'size':[540,960],'camera':'Night chase A',
                'start':0,'end':90,'comparison':{'laps':[{'samples':{'Speed':[1,2]}}]}}
        key=render_cache_key(config)
        self.assertEqual(key,render_cache_key(dict(config,work_dir='two')))
        for changes in ({'fps':30},{'size':[720,1280]},{'camera':'Night chase B'},{'quality':'High'},
                        {'end':30},{'asset_environment':'different.blend'},
                        {'comparison':{'laps':[{'samples':{'Speed':[2,3]}}]}}):
            self.assertNotEqual(key,render_cache_key(dict(config,**changes)))

    def test_completed_identical_job_reuses_mp4_but_changed_fps_renders(self):
        def encode(comparison,folder,destination,**kwargs):
            Path(destination).write_bytes(b'encoded-test-data'*200)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as directory, \
             patch('services.video_3d.availability',return_value=(True,'')), \
             patch('services.video_3d.fit_path',return_value={}), \
             patch('services.video_3d.prepare_driving_path',return_value={}), \
             patch('services.video_3d.run_blender') as worker, \
             patch('services.video_3d.render_cache_key',wraps=render_cache_key) as keys, \
             patch('services.video_3d_overlay.encode_frames',side_effect=encode) as encoder:
            comparison=comparison_fixture()
            first=Path(directory)/'first.mp4';second=Path(directory)/'second.mp4'
            render_3d_mp4(comparison,first,start=0,end=1)
            self.assertEqual(len(list((Path(directory)/'render_cache').glob('*.mp4'))),1)
            cached=next((Path(directory)/'render_cache').glob('*.mp4'))
            self.assertGreater(cached.stat().st_size,1000)
            self.assertEqual(cached.stem,render_cache_key(keys.call_args_list[0].args[0]))
            render_3d_mp4(comparison,second,start=0,end=1)
            left=dict(keys.call_args_list[0].args[0]);right=dict(keys.call_args_list[1].args[0])
            left.pop('work_dir');right.pop('work_dir')
            self.assertEqual(left,right)
            self.assertEqual(first.read_bytes(),second.read_bytes())
            self.assertEqual(worker.call_count,1);self.assertEqual(encoder.call_count,1)
            render_3d_mp4(comparison,second,start=0,end=1,fps=30)
            self.assertEqual(worker.call_count,2)
