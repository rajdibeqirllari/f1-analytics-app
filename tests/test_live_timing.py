"""Live timing: FastF1 recording lines, delta merging, qualifying gaps, follow + replay."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from services import live_timing as lt

INIT = [
    ['SessionInfo', json.dumps({'Meeting': {'Name': 'Mexico City Grand Prix'}, 'Type': 'Qualifying', 'Name': 'Qualifying', 'StartDate': '2026-10-31T15:00:00'}), ''],
    ['DriverList', json.dumps({'12': {'Tla': 'ANT', 'TeamColour': '00D7B6', 'FullName': 'Kimi ANTONELLI'}, '1': {'Tla': 'VER', 'TeamColour': '4781D7'}}), ''],
    ['TimingData', json.dumps({'SessionPart': 1, 'Lines': {n: {'Position': p, 'Sectors': [{'Segments': [{'Status': 0}] * 4} for _ in range(3)],
                                                                 'Stats': [{'TimeDiffToFastest': '', 'TimeDiffToPositionAhead': ''}]} for n, p in (('12', '1'), ('1', '2'))}}), ''],
    ['CarData.z', 'eJxLTEoGAAJNASc=', ''],
]
UPD = [
    ['TimingData', {'Lines': {'12': {'Sectors': {'0': {'Segments': {'2': {'Status': 2051}}}}}}}, '2026-10-31T21:00:10.000Z'],
    ['TimingData', {'Lines': {'1': {'Position': '1', 'BestLapTime': {'Value': '1:15.912'}, 'Stats': {'0': {'TimeDiffToFastest': ''}}},
                              '12': {'Position': '2', 'Stats': {'0': {'TimeDiffToFastest': '+0.104', 'TimeDiffToPositionAhead': '+0.104'}}}}}, '2026-10-31T21:00:20.000Z'],
    ['TrackStatus', {'Status': '2', 'Message': 'Yellow'}, '2026-10-31T21:00:30.000Z'],
    ['RaceControlMessages', {'Messages': {'3': {'Utc': '2026-10-31T21:00:30', 'Flag': 'YELLOW', 'Message': 'YELLOW IN TRACK SECTOR 4'}}}, '2026-10-31T21:00:30.000Z'],
]


def _write(lines):
    f = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8')
    f.write('\n'.join(str(x) for x in lines) + '\n')
    f.close()
    return Path(f.name)


class LiveTimingTest(unittest.TestCase):
    def test_merge_handles_index_keyed_list_updates(self):
        self.assertEqual(lt.merge([{'a': 1}, {'a': 2}], {'1': {'a': 5}}), [{'a': 1}, {'a': 5}])

    def test_follow_builds_tower_with_qualifying_gaps(self):
        snap = lt.Feed(_write(INIT + UPD), 'follow').snapshot()
        codes = [d['code'] for d in snap['drivers']]
        self.assertEqual(codes, ['VER', 'ANT'])
        self.assertEqual(snap['drivers'][1]['gap'], '+0.104')
        self.assertEqual(snap['flag']['state'], 'yellow')
        self.assertEqual(snap['race_control'][0]['message'], 'YELLOW IN TRACK SECTOR 4')
        self.assertTrue(snap['session']['qualifying'])
        self.assertIsNotNone(snap['drivers'][1]['progress'])  # placed from its last mini-sector

    def test_replay_only_applies_messages_up_to_the_clock(self):
        feed = lt.Feed(_write(INIT + UPD), 'replay')
        feed.seek(feed.first_time() + 5)  # before the lap at +10 s
        snap = feed.snapshot()
        self.assertEqual([d['code'] for d in snap['drivers']], ['ANT', 'VER'])
        self.assertEqual(snap['flag']['state'], 'green')

    def test_follow_picks_up_lines_written_later(self):
        path = _write(INIT)
        feed = lt.Feed(path, 'follow')
        self.assertEqual(feed.snapshot()['drivers'][0]['code'], 'ANT')
        with path.open('a', encoding='utf-8') as f:
            f.write(str(UPD[1]) + '\n')
        self.assertEqual(feed.snapshot()['drivers'][0]['code'], 'VER')

    def test_sector_yellows_set_and_clear(self):
        msgs = [{'Flag': 'YELLOW', 'Scope': 'Sector', 'Sector': 13}, {'Flag': 'DOUBLE YELLOW', 'Scope': 'Sector', 'Sector': 14},
                {'Flag': 'CLEAR', 'Scope': 'Sector', 'Sector': 13}]
        self.assertEqual(lt.active_yellows(msgs)[0], [{'sector': 14, 'double': True}])
        self.assertEqual(lt.active_yellows(msgs + [{'Flag': 'CLEAR', 'Scope': 'Track'}])[0], [])
        self.assertEqual(lt.active_yellows(msgs)[1], 14)

    def test_clock_parsing(self):
        self.assertEqual(lt.clock_seconds('1:15.912'), 75.912)
        self.assertEqual(lt.clock_seconds('00:12:00'), 720)
        self.assertIsNone(lt.clock_seconds('1L'))


if __name__ == '__main__':
    unittest.main()
