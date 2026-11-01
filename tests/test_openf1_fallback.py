import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from services import openf1_comparison as fallback
from services.openf1_service import car_data_to_canonical
from services.export_service import make_after_effects_tsv, make_racerender_csv
from services.video_comparison import VideoSelection, build_comparison, session_catalog


class OpenF1FallbackTests(unittest.TestCase):
    def test_deletion_time_overrides_mismatched_notice_lap_number(self):
        laps=pd.DataFrame({'driver_number':[3,3,16], 'lap_number':[14,12,12],
                           'lap_duration':[95.860,96.136,96.052]})
        messages=[{'date':'2026-10-23T18:09:02Z','message':
            'CAR 3 (VER) TIME 1:35.860 DELETED - TRACK LIMITS AT TURN 19 LAP 15'}]
        marked=fallback.apply_lap_deletions(laps,messages)
        self.assertEqual(marked.deleted.tolist(),[True,False,False])
        valid=marked[~marked.deleted]
        self.assertAlmostEqual(valid[valid.driver_number==3].lap_duration.min()-valid[valid.driver_number==16].lap_duration.min(),.084)
        messages.append({'date':'2026-10-23T18:10:00Z','message':'CAR 3 (VER) TIME 1:35.860 REINSTATED'})
        self.assertFalse(fallback.apply_lap_deletions(laps,messages).deleted.any())

    def data(self, endpoint, params):
        if endpoint == 'sessions':
            return [dict(session_key=10, session_name='Race', country_name='Belgium',
                         location='Spa', date_end='2026-07-19T15:00:00Z')]
        if endpoint == 'drivers':
            return [dict(driver_number=n, name_acronym=c, full_name=c, team_name='Team',
                         team_colour='ff0000') for n, c in [(1, 'AAA'), (2, 'BBB')]]
        if endpoint == 'laps':
            return [dict(driver_number=n, lap_number=3, lap_duration=20.,
                         date_start='2026-07-19T13:00:00Z', is_pit_out_lap=False,
                         duration_sector_1=6., duration_sector_2=7., duration_sector_3=7.) for n in (1, 2)]
        result = []
        for t in np.linspace(0, 20, 81):
            row = dict(date=(pd.Timestamp('2026-07-19T13:00:00Z') + pd.Timedelta(seconds=t)).isoformat())
            if endpoint == 'car_data':
                row.update(speed=200, throttle=80, brake=0, rpm=10000, n_gear=6, drs=None)
            else:
                row.update(x=1000*np.cos(t/20*2*np.pi), y=1000*np.sin(t/20*2*np.pi), z=0)
            result.append(row)
        return result

    def selection(self, **kw):
        return VideoSelection(2026, 'Belgian Grand Prix', 'R', 'AAA', 'BBB', **kw)

    def test_catalog_falls_back_and_exposes_source(self):
        with patch('services.video_comparison.load_video_session', side_effect=ValueError('offline')), \
             patch.object(fallback, 'historical', side_effect=self.data):
            result = session_catalog(2026, 'Belgian Grand Prix', 'R')
        self.assertEqual(result['source'], 'OpenF1')
        self.assertEqual(result['drivers']['AAA']['laps'], [3])
        self.assertFalse(result['qualifying_segments'])

    def test_comparison_uses_real_channels_and_preserves_duration(self):
        with patch.object(fallback, 'historical', side_effect=self.data):
            result = fallback.comparison(self.selection())
        self.assertEqual(result.laps[0].source, 'OpenF1')
        self.assertEqual(result.laps[0].lap_time, 20.)
        self.assertEqual(result.laps[0].sectors, (6., 7., 7.))
        self.assertEqual(result.laps[0].at(10)['throttle'], 80.)
        self.assertIsNone(result.laps[0].at(10)['drs'])
        self.assertTrue(any('DRS is unavailable' in w for w in result.warnings))
        self.assertEqual(result.track.shape, (720, 4))

    def test_fastf1_success_does_not_call_fallback(self):
        with patch('services.video_comparison._build_fastf1_comparison', return_value='fastf1'), \
             patch.object(fallback, 'comparison') as other:
            self.assertEqual(build_comparison(self.selection()), 'fastf1')
            other.assert_not_called()

    def test_failed_fastf1_telemetry_can_fall_back(self):
        with patch('services.video_comparison._build_fastf1_comparison', side_effect=KeyError('Date')), \
             patch.object(fallback, 'historical', side_effect=self.data):
            self.assertEqual(build_comparison(self.selection()).laps[0].source, 'OpenF1')

    def test_qualifying_parts_are_not_invented(self):
        with self.assertRaisesRegex(ValueError, 'cannot verify'):
            fallback.comparison(self.selection(qualifying_part='Q3'))

    def test_gapped_positions_rejected(self):
        def data(endpoint, params):
            rows = self.data(endpoint, params)
            return rows[:20]+rows[40:] if endpoint == 'location' else rows
        with patch.object(fallback, 'historical', side_effect=data):
            with self.assertRaisesRegex(ValueError, 'coverage'):
                fallback.comparison(self.selection())

    def test_future_or_ambiguous_session_rejected(self):
        with patch.object(fallback, 'historical', return_value=[dict(session_key=10,
            session_name='Race',country_name='Belgium',date_end='2099-01-01T00:00:00Z')]):
            with self.assertRaisesRegex(ValueError, 'completed historical'):
                fallback.resolve(2026, 'Belgian Grand Prix', 'R')
        with patch.object(fallback, 'historical', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'uniquely'):
                fallback.resolve(2026, 'Belgian Grand Prix', 'R')

    def test_missing_drs_stays_null_in_exports(self):
        result = car_data_to_canonical(self.data('car_data', {}), session_key=10, driver_number=1)
        self.assertTrue(result.drs_active.isna().all())
        self.assertEqual(len(result), 81)  # fractional and whole-second ISO timestamps
        after_effects = make_after_effects_tsv(result, 30)
        self.assertTrue(after_effects.DRS.isna().all())
        self.assertTrue((after_effects.Brake == False).all())
        self.assertIn('DRS', after_effects.to_csv(index=False, sep='\t'))
        self.assertEqual(len(make_racerender_csv(result)), 81)

    def test_after_effects_exports_real_and_missing_boolean_channels(self):
        result = car_data_to_canonical(self.data('car_data', {}), session_key=10, driver_number=1)
        result['drs_active'] = pd.Series([True]*40+[False]*41, dtype='boolean')
        result['brake_active'] = pd.Series([pd.NA]*81, dtype='boolean')
        exported = make_after_effects_tsv(result, 30)
        self.assertTrue(exported.Brake.isna().all())
        self.assertTrue(exported.DRS.iloc[0])
        self.assertFalse(exported.DRS.iloc[-1])

    def test_successful_responses_cached_but_empty_responses_not_cached(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(fallback, 'CACHE', Path(folder)), \
             patch.object(fallback, '_last_request', 0), patch.object(fallback.time, 'sleep'), \
             patch.object(fallback, 'openf1_get', return_value=[{'real': 1}]) as get:
            self.assertEqual(fallback.historical('laps', {'session_key':10}), [{'real': 1}])
            fallback.historical('laps', {'session_key':10})
            self.assertEqual(get.call_count, 1)
            get.return_value = []
            fallback.historical('laps', {'session_key':11})
            fallback.historical('laps', {'session_key':11})
            self.assertEqual(get.call_count, 3)


class ResolveNamesTests(unittest.TestCase):
    """OpenF1 uses venue/country names, not FastF1's event names."""
    SESSIONS = [dict(session_key=1, meeting_key=11, session_name='Practice 1', country_name='United Arab Emirates',
                     location='Yas Island', circuit_short_name='Yas Marina Circuit', date_end='2025-12-05T10:30:00Z'),
                dict(session_key=2, meeting_key=12, session_name='Practice 1', country_name='Saudi Arabia',
                     location='Jeddah', circuit_short_name='Jeddah', date_end='2025-04-18T14:30:00Z'),
                dict(session_key=3, meeting_key=13, session_name='Practice 1', country_name='Italy',
                     location='Imola', circuit_short_name='Imola', date_end='2025-05-16T14:30:00Z'),
                dict(session_key=4, meeting_key=14, session_name='Practice 1', country_name='Italy',
                     location='Monza', circuit_short_name='Monza', date_end='2025-09-05T14:30:00Z')]

    def run_resolve(self, event, meetings=()):
        data = lambda endpoint, params: list(meetings) if endpoint == 'meetings' else self.SESSIONS
        with patch.object(fallback, 'historical', side_effect=data):
            return fallback.resolve(2025, event, 'FP1')['session_key']

    def test_event_names_resolve_without_meetings(self):
        self.assertEqual(self.run_resolve('Abu Dhabi Grand Prix'), 1)
        self.assertEqual(self.run_resolve('Saudi Arabian Grand Prix'), 2)
        self.assertEqual(self.run_resolve('Emilia Romagna Grand Prix'), 3)
        self.assertEqual(self.run_resolve('Italian Grand Prix'), 4)

    def test_meeting_name_wins(self):
        self.assertEqual(self.run_resolve('Abu Dhabi Grand Prix', [dict(meeting_key=11, meeting_name='Abu Dhabi Grand Prix')]), 1)


if __name__ == '__main__':
    unittest.main()
