import unittest
from unittest.mock import Mock,patch
from streamlit.testing.v1 import AppTest


def creator_page():
    from ui.video_studio import render_video_studio
    render_video_studio(latest={'year':2026,'event_name':'Singapore Grand Prix'},
                        event_loader=lambda year:['Singapore Grand Prix','Italian Grand Prix'])


class CreatorFlowTests(unittest.TestCase):
    def test_visual_choices_keep_driver_and_renderer_settings(self):
        entries={'VER':{'name':'Max Verstappen','team':'Red Bull','color':'3671C6','laps':[3,8]},
                 'LEC':{'name':'Charles Leclerc','team':'Ferrari','color':'FF0000','laps':[4,9]}}
        manager=Mock();manager.snapshot.return_value=None;manager.submit.return_value='mock-job'
        with patch('ui.video_studio.catalog',return_value={'drivers':entries}), \
             patch('ui.video_studio.availability',return_value=(True,'')), \
             patch('ui.video_studio.video_jobs',return_value=manager):
            app=AppTest.from_function(creator_page,default_timeout=20).run()
            app.button(key='video_load_session').click().run()
            self.assertFalse(app.exception)
            app.selectbox(key='video_driver_b').set_value('LEC').run()
            app.radio(key='video_night_focus_v2').set_value(1).run()
            app.select_slider(key='video_render_quality').set_value('High').run()
            self.assertEqual(app.selectbox(key='video_driver_b').value,'LEC')
            app.button(key='video_build_preview').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(manager.submit.call_args.kwargs['camera'],'Night chase B')
            self.assertEqual(manager.submit.call_args.kwargs['environment'],'Telemetry-built')
            self.assertEqual(manager.submit.call_args.kwargs['quality'],'High')
            self.assertEqual(manager.submit.call_args.args[0].driver_a,'VER')
            self.assertEqual(manager.submit.call_args.args[0].driver_b,'LEC')
            app.button(key='choose_2D · Telemetry').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key='video_camera').value,'Follow cars')
