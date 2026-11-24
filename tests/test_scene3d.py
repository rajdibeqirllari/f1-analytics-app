"""3D Broadcast scene: shared clock positions from timing crossings, recorded positions, and the live rules."""
import math
import time
from pathlib import Path

import unittest
from unittest import mock

import numpy as np

from services import live_timing as lt
from services import scene3d as sc


def oval(n=400, straight=800.0, radius=120.0):
    """A stadium-shaped circuit (two straights, two hairpins), anticlockwise, starting mid-straight."""
    pts = []
    per = 2 * straight + 2 * math.pi * radius
    for i in range(n):
        d = i / n * per
        if d < straight / 2:
            pts.append((d, -radius))
        elif d < straight / 2 + math.pi * radius:
            a = (d - straight / 2) / radius - math.pi / 2
            pts.append((straight / 2 + radius * math.cos(a), radius * math.sin(a)))
        elif d < 1.5 * straight + math.pi * radius:
            pts.append((straight / 2 - (d - straight / 2 - math.pi * radius), radius))
        elif d < 1.5 * straight + 2 * math.pi * radius:
            a = (d - 1.5 * straight - math.pi * radius) / radius + math.pi / 2
            pts.append((-straight / 2 + radius * math.cos(a), radius * math.sin(a)))
        else:
            pts.append((-straight / 2 + (d - 1.5 * straight - 2 * math.pi * radius), -radius))
    x, y = zip(*pts)
    return sc.Track(np.array(x), np.array(y), None, source='test oval')


def test_profile_slows_for_corners():
    tr = oval(radius=40)
    v = tr._speeds()
    straight = v[(tr.s > 50) & (tr.s < 200)].mean()
    hairpin = v[(tr.s > 400 + 40 * 0.8) & (tr.s < 400 + 40 * 2.3)].mean()
    assert straight > 0.8 and hairpin < 0.6 * straight
    assert np.all(np.diff(tr.profile) > 0)   # time to distance is strictly increasing


def _msg(num, ts, **line):
    return (ts, 'TimingData', {'Lines': {num: line}})


def _seg(si, gi, status=2048):
    return {'Sectors': {str(si): {'Segments': {str(gi): {'Status': status}}}}}


def _timeline(events):
    tl = sc.Timeline()
    tl.update(events)
    return tl


def base_events(t0=1000.0):
    ev = [(t0, 'DriverList', {'1': {'Tla': 'AAA', 'TeamColour': 'ff0000'}, '2': {'Tla': 'BBB', 'TeamColour': '00ff00'}}),
          (t0, 'TimingData', {'Lines': {n: {'Position': p, 'NumberOfLaps': 0, 'Sectors': [
              {'Segments': [{'Status': 0}] * 2}, {'Segments': [{'Status': 0}] * 2}, {'Segments': [{'Status': 0}] * 2}]}
              for n, p in (('1', '1'), ('2', '2'))}})]
    return ev


def test_crossings_place_each_car_by_its_own_timing_not_its_rank():
    # Car 1 leads; car 2 is classified P2 but a lap down, and physically ~5 s AHEAD of the leader on the circuit.
    # Each car must be placed only from its own crossings, never from its rank.
    ev = base_events()
    t = 1000.0
    for lap in range(3):
        for k, (si, gi) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]):
            ev.append(_msg('1', t + lap * 60 + 10 * (k + 1), **_seg(si, gi)))
        ev.append(_msg('1', t + lap * 60 + 60, **_seg(2, 1), NumberOfLaps=lap + 1, LastLapTime={'Value': '1:00.000'}))
        ev.append(_msg('1', t + lap * 60 + 61, Sectors={str(s): {'Segments': {'0': {'Status': 0}, '1': {'Status': 0}}} for s in range(3)}))
    # Car 2 crosses the same points 55 s after the leader, i.e. one lap later minus 5 s.
    for lap in range(2):
        for k, (si, gi) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]):
            ev.append(_msg('2', t + 55 + lap * 60 + 10 * (k + 1), **_seg(si, gi)))
        ev.append(_msg('2', t + 55 + lap * 60 + 60, **_seg(2, 1), NumberOfLaps=lap + 1, LastLapTime={'Value': '1:00.000'}))
        ev.append(_msg('2', t + 55 + lap * 60 + 61, Sectors={str(s): {'Segments': {'0': {'Status': 0}, '1': {'Status': 0}}} for s in range(3)}))
    ev.sort(key=lambda e: e[0])
    tl = _timeline(ev)
    est = sc.Estimator(tl, oval())
    L = est.track.length
    times = np.array([t + 150.0])
    s1, _ = est.sample('1', times, frontier=t + 200)
    s2, _ = est.sample('2', times, frontier=t + 200)
    # Leader: 2.5 laps; car 2: about 1.4 laps. On the circuit car 2 is physically ahead of the leader (by lap
    # fraction), even though it is a lap down and classified behind.
    assert 2 * L < s1[0] < 3 * L and L < s2[0] < 2 * L
    ahead = ((s2[0] % L) - (s1[0] % L)) % L
    assert 0 < ahead < L / 4


def test_interpolation_is_monotonic_and_bounded_extrapolation_goes_stale():
    ev = base_events()
    for k, (si, gi) in enumerate([(0, 0), (0, 1), (1, 0)]):
        ev.append(_msg('1', 1000 + 10 * (k + 1), **_seg(si, gi)))
    tl = _timeline(ev)
    est = sc.Estimator(tl, oval())
    times = np.arange(1005, 1060, 0.5)
    s, f = est.sample('1', times, frontier=1030)
    ok = ~np.isnan(s)
    assert np.all(np.diff(s[ok]) >= -1e-6)                          # never backwards
    assert set(f[(times > 1010) & (times < 1030)]) == {0}            # between crossings
    assert 1 in f[(times > 1030) & (times <= 1030 + sc.EXTRAPOLATE_S)]
    late = times > 1030 + sc.EXTRAPOLATE_S + 0.5
    assert set(f[late]) == {2} and np.ptp(s[late]) == 0               # holds, flagged stale
    assert np.isnan(s[times < 1010]).all()                           # no crossing yet: not on track


def test_pit_lane_hides_the_car_and_stopped_holds():
    ev = base_events()
    ev += [_msg('1', 1010, **_seg(0, 0)), _msg('1', 1020, **_seg(0, 1)), _msg('1', 1025, InPit=True),
           _msg('1', 1050, InPit=False), _msg('1', 1060, **_seg(1, 0)), _msg('1', 1070, Stopped=True)]
    tl = _timeline(ev)
    est = sc.Estimator(tl, oval())
    s, f = est.sample('1', np.array([1015.0, 1030.0, 1065.0, 1075.0, 1085.0]), frontier=1100)
    assert not np.isnan(s[0]) and np.isnan(s[1])          # in the pit lane: not drawn (no invented pit path)
    assert f[3] == 2 and f[4] == 2 and s[3] == s[4]       # stopped: frozen at the last crossing


def test_timeline_does_not_share_segment_lists_with_the_timing_screen():
    """Regression: live_timing.merge inserts lists by reference; the timing screen must not pre-apply crossings."""
    ev = base_events()
    ev += [_msg('1', 1010, **_seg(0, 0)), _msg('1', 1020, **_seg(0, 1))]
    state = lt.LiveState()
    for ts, topic, data in ev[:2]:
        state.apply(topic, data, ts)
    tl = sc.Timeline()
    tl.update(ev[:2])
    for ts, topic, data in ev[2:]:        # the timing screen sees the new messages first (follow mode)
        state.apply(topic, data, ts)
    tl.update(ev)
    assert [c[3] for c in tl.crossings['1'] if c[2] == 'seg'] == [(0, 0), (0, 1)]


class FakeFeed:
    def __init__(self, path, events, mode='follow', growing=True):
        self.path, self.events, self.mode, self._growing = Path(path), events, mode, growing
        import threading
        self.lock = threading.RLock()

    def _read_new(self):
        pass

    def growing(self):
        return self._growing

    def last_time(self):
        return max(e[0] for e in self.events)


def test_live_feed_never_uses_recorded_positions_even_when_cached():
    ev = base_events() + [(1000.0, 'SessionInfo', {'Meeting': {'Name': 'Test GP'}, 'Name': 'Race', 'StartDate': '2026-01-01T14:00:00'}),
                          _msg('1', 1010, **_seg(0, 0))]
    m = sc.SceneManager(lambda y, e: {'x': [0, 100, 100, 0], 'y': [0, 0, 100, 100], 'length': 400})
    feed = FakeFeed('rec.txt', ev, 'follow', growing=True)
    tl = m._sync(feed)
    track = oval()
    cars = {'1': dict(t=np.array([1000.0, 1001.0]), x=np.array([0.0, 1.0]), y=np.array([0.0, 0.0]), z=np.zeros(2))}
    m.recorded[m._session_id(tl)] = sc.Recorded({'provider': 'OpenF1', 'year': 2026, 'event': 'Test GP', 'name': 'Race'}, cars, track, {}, 4.0)
    d = m.describe(feed)
    assert d['source'] == 'estimated' and 'Live session' in d['recorded']['reason']
    assert m.samples(feed, 1000, 1010)['source'] == 'estimated'
    # The same recording replayed once finished may use them.
    done = FakeFeed('rec.txt', ev, 'replay', growing=False)
    assert m.describe(done)['source'] == 'recorded'


def test_recorded_positions_refuse_a_different_session():
    session = {'session_key': 1, 'date_start': '2026-11-07T18:00:00+00:00', 'gmt_offset': '-03:00:00', 'session_name': 'Qualifying'}
    with mock.patch('services.openf1_comparison.resolve', lambda y, e, c: session),             mock.patch('services.openf1_comparison.historical', lambda *a, **k: []):
        try:
            sc.load_recorded(2026, 'São Paulo Grand Prix', 'Race', '2026-11-08T14:00:00')
        except ValueError as exc:
            assert 'different session' in str(exc)
        else:
            raise AssertionError('a different session was accepted')


def test_outline_is_scaled_to_metres():
    outline = {'x': [0, 10000, 10000, 0], 'y': [0, 0, 5000, 5000], 'length': 3000.0, 'source': 'x'}
    tr = sc.track_from_outline(outline)
    assert abs(tr.length - 3000) < 60


class Scene3D(unittest.TestCase):
    """unittest entry points (the repo runs tests with unittest)."""


for _name in [n for n in list(globals()) if n.startswith('test_')]:
    _fn = globals().pop(_name)
    setattr(Scene3D, _name, (lambda f: lambda self: f())(_fn))

if __name__ == '__main__':
    unittest.main()
