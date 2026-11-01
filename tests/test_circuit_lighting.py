import unittest
from services.circuit_lighting import race_lighting


class CircuitLightingTests(unittest.TestCase):
    def test_daytime_tracks_do_not_become_night_races(self):
        for event in ('Monaco Grand Prix','Austrian Grand Prix','Italian Grand Prix','United States Grand Prix'):
            self.assertEqual(race_lighting(2026,event),'day')

    def test_night_venues_and_historical_cutoffs(self):
        for event in ('Singapore Grand Prix','Bahrain Grand Prix','Saudi Arabian Grand Prix','Qatar Grand Prix','Las Vegas Grand Prix'):
            self.assertEqual(race_lighting(2025,event),'night')
        self.assertEqual(race_lighting(2013,'Bahrain Grand Prix'),'day')
        self.assertEqual(race_lighting(2025,'Abu Dhabi Grand Prix'),'twilight')
