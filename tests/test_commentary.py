import unittest
from pathlib import Path

from services import commentary as cm


class Quiet(cm.Commentator):
    """No background threads: tests read the pending events directly."""
    def _writer(self):
        pass

    def _radio_worker(self):
        pass


class FakeState:
    def __init__(self, rc=None):
        self.topics = {'RaceControlMessages': {'Messages': rc or []}}


def row(num, code, pos, best=None, **kw):
    r = dict(number=num, code=code, name=f'Test {code}', team='T', position=pos, best=best, gap=None,
             last={'value': None, 'overall': False}, tyre={'compound': 'SOFT'}, in_pit=False, pit_out=False,
             knocked_out=False, retired=False, stopped=False)
    r.update(kw)
    return r


def snap(rows, **sess):
    return dict(drivers=rows, now=1000.0, feed=dict(mode='follow'), session=dict(dict(qualifying=True, part=1, type='Qualifying'), **sess))


class CommentaryTests(unittest.TestCase):
    def test_rc_text_keeps_codes(self):
        rows = {'87': row('87', 'BEA', 1)}
        self.assertEqual(cm._rc_text('FIA STEWARDS: CAR 87 (BEA) UNDER INVESTIGATION (14:59:59)', rows),
                         'FIA stewards: car 87 (BEA) under investigation')

    def test_rc_priority(self):
        self.assertEqual(cm._rc_priority({'Message': 'RED FLAG', 'Flag': 'RED'}), 5)
        self.assertEqual(cm._rc_priority({'Message': 'CLEAR IN TRACK SECTOR 4', 'Flag': 'CLEAR', 'Scope': 'Sector'}), 0)

    def test_first_poll_is_baseline_then_new_messages_queue(self):
        c = Quiet(Path('.'))
        state = FakeState([{'Message': 'OLD'}])
        c.observe(state, snap([row('1', 'VER', 1)]), 'x.txt')
        self.assertEqual(c.pending, [])
        state.topics['RaceControlMessages']['Messages'].append({'Message': 'RED FLAG', 'Flag': 'RED'})
        c.observe(state, snap([row('1', 'VER', 1)]), 'x.txt')
        self.assertEqual([e['prio'] for e in c.pending], [5])

    def test_new_fastest_lap_in_qualifying(self):
        c = Quiet(Path('.'))
        state = FakeState()
        c.observe(state, snap([row('1', 'VER', 1, '1:10.500'), row('4', 'NOR', 2, '1:10.700')]), 'x.txt')
        c.observe(state, snap([row('4', 'NOR', 1, '1:10.300'), row('1', 'VER', 2, '1:10.500', gap='+0.200')]), 'x.txt')
        fastest = [e for e in c.pending if e['kind'] == 'fastest']
        self.assertEqual(len(fastest), 1)
        self.assertIn('Nor is now P1', fastest[0]['text'])
        self.assertIn("beating Ver's time by 0.200", fastest[0]['text'])


class PacingTests(unittest.TestCase):
    def test_drop_repeats(self):
        recent = ['Leclerc takes the lead from Hamilton!', 'Hamilton takes the lead as the race begins!']
        self.assertEqual(cm._drop_repeats('Leclerc takes the lead from Hamilton, while Colapinto passes Norris for P8.', recent),
                         'Colapinto passes Norris for P8.')
        self.assertEqual(cm._drop_repeats('Hamilton leads the pack as the race begins!', recent), '')
        self.assertEqual(cm._drop_repeats('Verstappen passes Hamilton for P2!', recent), 'Verstappen passes Hamilton for P2!')

    def test_old_events_are_dropped_and_only_one_line_is_taken(self):
        c = Quiet(Path('.'))
        c.clock = 1000.0
        c.pending = [dict(prio=4, kind='x', text='old', t=950.0, drivers=[]),
                     dict(prio=3, kind='x', text='a', t=998.0, drivers=[]),
                     dict(prio=4, kind='x', text='b', t=999.0, drivers=[])]
        batch = c._take()
        self.assertEqual([e['text'] for e in batch], ['b', 'a'])
        self.assertEqual(c.pending, [])
        self.assertIsNone(c._take())   # still "speaking": nothing new until the line ends

    def test_short_numbers(self):
        self.assertEqual(cm.short_numbers('Norris sets a 1:31.785, 0.359 off P1.'), 'Norris sets a 1:31.7, 0.3 off P1.')
        self.assertEqual(cm.short_numbers('beating his time by 0.055, 12.220 quicker'), 'beating his time by 0.05, 12.2 quicker')
        self.assertEqual(cm.short_numbers('Up to P10 on lap 23, 4:00 remaining, +1.5'), 'Up to P10 on lap 23, 4:00 remaining, +1.5')

    def test_urgent_cuts_in(self):
        c = Quiet(Path('.'))
        c.clock, c.busy_until, c.last_prio = 1000.0, 1e12, 3
        c.pending = [dict(prio=5, kind='race_control', text='Red flag', t=1000.0, drivers=[])]
        self.assertEqual(c._take()[0]['text'], 'Red flag')


if __name__ == '__main__':
    unittest.main()
