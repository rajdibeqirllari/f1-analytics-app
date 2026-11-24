"""Regression tests for the 2026-11-11 audit (FIX_PROMPT_FULL.md). Each test names the issue it covers."""
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

from services import commentary as cm
from services import live_timing as lt
from services.export_service import normalize_telemetry
from services.hud_renderer import normalize_hud_telemetry


class Quiet(cm.Commentator):
    def _writer(self):
        pass

    def _radio_worker(self):
        pass


def row(num, code, pos, best=None, name=None, **kw):
    r = dict(number=num, code=code, name=name or f'Test {code}', team='T', position=pos, best=best, gap=None,
             last={'value': None, 'overall': False}, tyre={'compound': 'SOFT'}, in_pit=False, pit_out=False,
             knocked_out=False, retired=False, stopped=False)
    r.update(kw)
    return r


class RecordingNames(unittest.TestCase):
    """#1: two recordings started in the same minute must not share (and truncate) a file."""

    def test_same_minute_gets_new_file_and_never_truncates(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            now = datetime(2026, 11, 8, 18, 4, 30)
            first = lt.new_recording_path(folder, now)
            first.write_text("['TimingData', {}, '2026-11-08T18:04:31Z']\n", encoding='utf-8')
            second = lt.new_recording_path(folder, now)   # same second even
            self.assertNotEqual(first, second)
            self.assertTrue(first.read_text(encoding='utf-8'))   # first recording untouched
            self.assertTrue(second.exists())

    def test_recorder_starts_fake_process_on_unique_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fake = [sys.executable, '-c', 'import sys; open(sys.argv[1], "a").write("x\\n")']
            rec = lt.Recorder(folder, command=fake)
            a = lt.new_recording_path(folder)
            rec.start(a)
            rec.proc.wait(10)
            b = lt.new_recording_path(folder)
            rec.start(b)
            rec.proc.wait(10)
            self.assertNotEqual(a, b)
            self.assertEqual(a.read_text(), 'x\n')
            self.assertEqual(b.read_text(), 'x\n')

    def test_record_script_appends(self):
        text = Path('scripts/record_live.py').read_text(encoding='utf-8')
        self.assertIn("filemode='a'", text)


class CsvImport(unittest.TestCase):
    """#5 / #6: column matching and DRS booleans."""

    def test_throttle_is_never_time(self):
        frame = pd.DataFrame({'Throttle': [10, 50, 100], 'Speed': [100, 150, 200]})
        with self.assertRaisesRegex(ValueError, 'time column'):
            normalize_telemetry(frame, 'Upload CSV')
        with self.assertRaisesRegex(ValueError, 'time column'):
            normalize_hud_telemetry(frame, 'Upload CSV')

    def test_whole_word_time_still_matches(self):
        out = normalize_telemetry(pd.DataFrame({'Lap Time': [0.0, 0.5, 1.0], 'Speed (km/h)': [1, 2, 3], 'Throttle': [5, 6, 7]}), 'Upload CSV')
        self.assertEqual(out.time_sec.tolist(), [0.0, 0.5, 1.0])
        self.assertEqual(out.throttle_pct.tolist(), [5, 6, 7])

    def test_drs_booleans_and_codes(self):
        cases = {'bool': [True, False], 'strings': ['true', 'false'], 'ints': [1, 0]}
        for column in ('drs_active', 'DRS'):
            for label, values in cases.items():
                out = normalize_telemetry(pd.DataFrame({'time_sec': [0, 1], 'Speed': [1, 2], column: values}), 'Upload CSV')
                self.assertEqual(out.drs_active.tolist(), [True, False], f'{column} {label}')
        out = normalize_telemetry(pd.DataFrame({'time_sec': [0, 1, 2], 'Speed': [1, 2, 3], 'DRS': [12, 8, 14]}), 'Upload CSV')
        self.assertEqual(out.drs_active.tolist(), [True, False, True])
        self.assertEqual(out.drs_raw.tolist(), [12, 8, 14])
        # FastF1 sends codes: 1 is "not open", never a boolean True
        out = normalize_telemetry(pd.DataFrame({'Time': [0, 1], 'Speed': [1, 2], 'DRS': [1, 0]}), 'FastF1')
        self.assertEqual(out.drs_active.tolist(), [False, False])

    def test_export_import_round_trip_keeps_drs(self):
        from services.export_service import make_after_effects_tsv
        src = normalize_telemetry(pd.DataFrame({'time_sec': [0, .5, 1], 'Speed': [1, 2, 3], 'DRS': [12, 12, 0]}), 'FastF1')
        exported = make_after_effects_tsv(src, 2)
        exported.insert(0, 'time_sec', exported.frame / 2)
        back = normalize_telemetry(pd.read_csv(pd.io.common.StringIO(exported.to_csv(index=False))), 'Upload CSV')
        self.assertEqual(back.drs_active.tolist(), [True, True, False])


class QualifyingSegment(unittest.TestCase):
    """#3 / #7: Q1/Q2/Q3 never filters a race and is never silently ignored by OpenF1."""

    def test_selection_resets_segment_outside_qualifying(self):
        from api.main import Selection
        self.assertEqual(Selection(year=2026, event='X GP', session='R', qualifying_part='Q2').qualifying_part, 'All')
        self.assertEqual(Selection(year=2026, event='X GP', session='Q', qualifying_part='Q2').qualifying_part, 'Q2')

    def test_filtered_laps_ignores_segment_for_race(self):
        from services.video_comparison import filtered_laps

        class Laps(pd.DataFrame):
            @property
            def _constructor(self):
                return Laps

            def pick_drivers(self, code):
                return self[self.Driver == code]

            def split_qualifying_sessions(self):
                raise AssertionError('a race must not be split into Q1/Q2/Q3')

        laps = Laps({'Driver': ['VER', 'VER'], 'LapTime': [1, 2], 'LapStartTime': [0, 1], 'LapNumber': [1, 2]})
        session = SimpleNamespace(name='Race', laps=laps)
        self.assertEqual(len(filtered_laps(session, 'VER', 'Q2')), 2)

    def test_openf1_rejects_segment(self):
        from services.openf1_service import load_openf1_lap
        with mock.patch('services.openf1_service.find_openf1_session') as find:
            with self.assertRaisesRegex(RuntimeError, 'Q1/Q2/Q3'):
                load_openf1_lap(2026, 'X', 'Q', 'VER', 'Fastest', None, qualifying_part='Q1')
            find.assert_not_called()


class FastestLap(unittest.TestCase):
    """#11: the field's best, not the leader's."""

    def test_field_best(self):
        rows = [dict(number='1', best='1:12.983'), dict(number='12', best='1:12.689'), dict(number='3', best=None),
                dict(number='4', best='bad')]
        lt.mark_fastest(rows)
        self.assertEqual([r['number'] for r in rows if r['fastest']], ['12'])

    def test_ties_and_knocked_out(self):
        rows = [dict(number='1', best='1:10.000'), dict(number='2', best='1:10.000'), dict(number='3', best='1:09.000', knocked_out=True)]
        lt.mark_fastest(rows, qualifying=True)
        self.assertEqual([r['number'] for r in rows if r['fastest']], ['1', '2'])

    def test_saved_recordings(self):
        for name, code in (('live_2026-11-08_1804.txt', 'ANT'), ('live_2026-11-01_2102.txt', 'HAM')):
            path = Path('outputs/live') / name
            if not path.exists():
                continue
            snap = lt.final_snapshot(path)
            self.assertEqual([r['code'] for r in snap['drivers'] if r['fastest']], [code], name)


def recording(tmp: Path, seconds=10) -> Path:
    path = tmp / 'rec.txt'
    lines = [f"['LapCount', {{'CurrentLap': {i}}}, '2026-11-08T18:00:{i:02d}Z']" for i in range(seconds + 1)]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    old = time.time() - 60
    import os
    os.utime(path, (old, old))   # finished file (not still growing)
    return path


class Playback(unittest.TestCase):
    """#12: replay stays inside the recording and stops at the end."""

    def test_clamp_and_stop_at_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = lt.Feed(recording(Path(tmp)), 'replay', 30)
            start, end = feed.first_time(), feed.last_time()
            feed.seek(end + 999)
            self.assertEqual(feed.clock(), end)
            feed.seek(start - 999)
            self.assertEqual(feed.clock(), start)
            feed.pause(False)
            feed.wall0 -= 10   # 10 s at 30x is far past the end
            self.assertEqual(feed.clock(), end)
            self.assertTrue(feed.paused and feed.at_end())
            self.assertTrue(feed.snapshot()['feed']['ended'])
            feed.pause(False)   # play at the end restarts from the beginning
            self.assertFalse(feed.paused)
            self.assertLess(feed.clock() - start, 1)

    def test_growing_file_is_not_ended(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = recording(Path(tmp))
            path.touch()
            feed = lt.Feed(path, 'replay', 30)
            feed.wall0 -= 10
            self.assertEqual(feed.clock(), feed.last_time())
            self.assertFalse(feed.paused)


class CommentaryGenerations(unittest.TestCase):
    """#14 / #15 / #16 / #25 / #26."""

    def setUp(self):
        self.c = Quiet(Path(tempfile.mkdtemp()))

    def test_run_id_and_voice_names_unique_per_engine(self):
        other = Quiet(Path('.'))
        self.assertNotEqual(self.c.status()['run'].split('-')[0], other.status()['run'].split('-')[0])

    def test_source_change_clears_lines_and_drops_stale_line(self):
        state = SimpleNamespace(topics={})
        snap = dict(drivers=[row('1', 'VER', 1)], now=100.0, feed=dict(mode='replay', speed=1), session=dict(type='Race'))
        self.c.observe(state, snap, 'mexico.txt')
        self.c.lines.append(dict(id=1, text='old'))
        gen = self.c.gen
        self.c.observe(SimpleNamespace(topics={}), snap, 'brazil.txt')
        self.assertFalse(self.c.lines)
        self.c._say([dict(prio=3, kind='x', text='Verstappen pits.', t=100.0, drivers=['VER'])], gen)   # written for Mexico
        self.assertFalse(self.c.lines)

    def test_seek_bumps_generation(self):
        snap = dict(drivers=[row('1', 'VER', 1)], now=100.0, feed=dict(mode='replay', speed=1), session=dict(type='Race'))
        self.c.observe(SimpleNamespace(topics={}), snap, 'a.txt')
        gen = self.c.gen
        self.c.observe(SimpleNamespace(topics={}), snap, 'a.txt')   # same file, new LiveState = a seek
        self.assertGreater(self.c.gen, gen)

    def test_old_radio_is_dropped(self):
        self.c.clock, self.c.speed = 1000.0, 5.0
        self.assertTrue(self.c._radio_stale(dict(aired=1000.0 - cm.URGENT_AGE * 5 - 1, gen=self.c.gen)))
        self.assertFalse(self.c._radio_stale(dict(aired=990.0, gen=self.c.gen)))
        self.assertTrue(self.c._radio_stale(dict(aired=999.0, gen=self.c.gen - 1)))

    def test_tags_only_named_drivers(self):
        rows = [row('16', 'LEC', 3, name='Charles LECLERC'), row('55', 'SAI', 4, name='Carlos SAINZ'), row('23', 'ALB', 9, name='Alexander ALBON')]
        batch = [dict(drivers=['LEC', 'SAI']), dict(drivers=['ALB'])]
        self.assertEqual(cm.line_drivers('Leclerc past Sainz for P3!', batch, rows), ['LEC', 'SAI'])
        self.assertEqual(cm.line_drivers('Big move into turn one!', batch, rows), ['LEC', 'SAI'])

    def test_unsupported_claims(self):
        rows = [row('1', 'VER', 2, name='Max VERSTAPPEN'), row('23', 'ALB', 9, name='Alexander ALBON'), row('44', 'HAM', 5, name='Lewis HAMILTON'),
                row('4', 'NOR', 1, name='Lando NORRIS')]
        facts = ['Race control: car 1 (VER) time penalty']
        self.assertIn('a false start', cm.unsupported('False starts for Verstappen and Albon!', facts, rows))
        self.assertIn('Albon', cm.unsupported('False starts for Verstappen and Albon!', facts, rows))
        self.assertIn('turn 5', cm.unsupported('Hamilton in trouble at turn 5', ['Hamilton pits from P5.'], rows))
        self.assertEqual(cm.unsupported('A penalty for Verstappen, Norris still leads.', facts, rows), [])

    def test_ai_line_falls_back_to_template(self):
        self.c.prev = {'1': row('1', 'VER', 1, name='Max VERSTAPPEN')}
        with mock.patch.object(self.c, 'engine', return_value=('ollama', 'x')), \
                mock.patch.object(self.c, '_ask', return_value='Verstappen crashes at turn 3!'), \
                mock.patch.object(self.c.speaker, 'available', return_value=False):
            self.c._say([dict(prio=3, kind='pit', text='Verstappen pits from P1.', t=None, drivers=['VER'])])
        self.assertEqual(self.c.lines[-1]['text'], 'Verstappen pits from P1.')
        self.assertEqual(self.c.lines[-1]['source'], 'template')

    def test_albanian_falls_back_to_translated_plain_line(self):
        self.c.prev = {'1': row('1', 'VER', 2, name='Max VERSTAPPEN'), '63': row('63', 'RUS', 3, name='George RUSSELL')}
        self.c.language = 'sq'
        answers = iter(['Verstappen dhe Russell përplasen!', 'Russell në telashe!', 'Verstappen hyn në pit nga P1.'])
        with mock.patch.object(self.c, 'engine', return_value=('ollama', 'x')), \
                mock.patch.object(self.c, '_ask', side_effect=lambda *a: next(answers)), \
                mock.patch.object(self.c.speaker, 'available', return_value=False):
            self.c._say([dict(prio=3, kind='pit', text='Verstappen pits from P1.', t=None, drivers=['VER'])])
        self.assertEqual(self.c.lines[-1]['text'], 'Verstappen hyn në pit nga P1.')


class OriginAndLibrary(unittest.TestCase):
    """#30 / #31."""

    def test_origin(self):
        from api.main import origin_allowed
        self.assertTrue(origin_allowed('http://127.0.0.1:8001', '127.0.0.1:8001'))
        self.assertTrue(origin_allowed('http://localhost:5173', '127.0.0.1:8000'))
        self.assertTrue(origin_allowed(None, '127.0.0.1:8000'))
        self.assertFalse(origin_allowed('https://evil.example', '127.0.0.1:8000'))
        self.assertFalse(origin_allowed('http://127.0.0.1:9999', '127.0.0.1:8000'))

    def test_private_files(self):
        from api.files import ROOT, approved
        for rel in ('outputs/live/voice/line_1.wav', 'outputs/live/radio/x/NOR.mp3', 'outputs/openf1_cache/abc.json',
                    'output/video_studio/3d_abc/frames/0001.png', 'output/video_studio/render_cache/a.mp4'):
            self.assertFalse(approved(ROOT / rel), rel)
        self.assertTrue(approved(ROOT / 'outputs/charts/a.png'))


class RecordingLookup(unittest.TestCase):
    """#8 / #40: recordings know their session; the timing fallback finds them."""

    def test_info_and_find(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'live_x.txt'
            info = "{'Meeting': {'Name': 'São Paulo Grand Prix'}, 'Name': 'Race', 'Type': 'Race', 'StartDate': '2026-11-08T14:00:00'}"
            path.write_text(f"['SessionInfo', {info}, '2026-11-08T17:00:00Z']\n", encoding='utf-8')
            self.assertEqual(lt.recording_info(path)['meeting'], 'São Paulo Grand Prix')
            self.assertEqual(lt.find_recording([Path(tmp)], 2026, 'Sao Paulo Grand Prix', 'R'), path)
            self.assertIsNone(lt.find_recording([Path(tmp)], 2026, 'Sao Paulo Grand Prix', 'Q'))


if __name__ == '__main__':
    unittest.main()
