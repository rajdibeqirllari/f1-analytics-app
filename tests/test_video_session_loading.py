import unittest
from unittest.mock import patch,Mock
import pandas as pd
from fastf1.exceptions import DataNotLoadedError
from services.video_comparison import load_video_session


class SessionLoadingTests(unittest.TestCase):
    def tearDown(self):
        load_video_session.cache_clear()

    def test_failed_download_is_not_cached_and_can_retry(self):
        class Missing:
            def load(self,**kwargs):pass
            @property
            def laps(self):raise DataNotLoadedError('missing')
        good=Mock(laps=pd.DataFrame({'LapNumber':[1]}))
        load_video_session.cache_clear()
        with patch('services.video_comparison.fastf1.get_session',side_effect=[Missing(),good]),patch('services.video_comparison.fastf1.Cache.enable_cache'):
            with self.assertRaisesRegex(ValueError,'Older seasons are supported'):
                load_video_session(2024,'United States Grand Prix','Q')
            self.assertEqual(load_video_session.cache_info().currsize,0)
            self.assertIs(load_video_session(2024,'United States Grand Prix','Q'),good)

    def test_empty_session_is_not_cached(self):
        load_video_session.cache_clear()
        with patch('services.video_comparison.fastf1.get_session',return_value=Mock(laps=pd.DataFrame())),patch('services.video_comparison.fastf1.Cache.enable_cache'):
            with self.assertRaisesRegex(ValueError,'No timed laps'):
                load_video_session(2024,'United States Grand Prix','Q')
            self.assertEqual(load_video_session.cache_info().currsize,0)
