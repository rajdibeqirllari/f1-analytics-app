"""Synthetic provider fixtures; no live rankings or points in production code."""
import unittest
from pathlib import Path

from services.overview_service import _parse_standings
from ui.constructor_config import CONSTRUCTOR_ASSETS, constructors_from_standings


def ranked_rows(items):
    payload = {"StandingsTable": {"StandingsLists": [{"season": "2026", "round": "13", "ConstructorStandings": items}]}}
    return _parse_standings(payload, 2026, drivers=False)[0]


def row(team_id, name, points, position):
    return {"Constructor": {"constructorId": team_id, "name": name}, "points": str(points), "position": str(position), "wins": "0"}


class ConstructorStandingsTest(unittest.TestCase):
    def test_service_points_sort_drives_both_table_and_showcase(self):
        rows = ranked_rows([row("ferrari", "Ferrari", 338, 2), row("mercedes", "Mercedes", 425, 1)])
        cars = constructors_from_standings(rows)
        self.assertEqual([car["id"] for car in cars], ["mercedes", "ferrari"])
        self.assertEqual([car["points"] for car in cars], [r["points"] for r in rows])
        self.assertEqual(cars[0]["index"], 1)

    def test_lead_change_needs_no_animation_change(self):
        rows = ranked_rows([row("mercedes", "Mercedes", 425, 1), row("ferrari", "Ferrari", 450, 2)])
        cars = constructors_from_standings(rows)
        self.assertEqual(cars[0]["id"], "ferrari")
        self.assertEqual(cars[0]["index"], 1)

    def test_ties_use_official_countback_position(self):
        rows = ranked_rows([row("ferrari", "Ferrari", 100, 2), row("mercedes", "Mercedes", 100, 1)])
        self.assertEqual([r["team_id"] for r in rows], ["mercedes", "ferrari"])

    def test_all_eleven_provider_names_map_without_manual_ranking(self):
        ids = ["mercedes", "ferrari", "mclaren", "red_bull", "rb", "alpine", "haas", "audi", "williams", "aston_martin", "cadillac"]
        names = ["Mercedes", "Ferrari", "McLaren", "Red Bull", "RB F1 Team", "Alpine F1 Team", "Haas F1 Team", "Audi", "Williams", "Aston Martin", "Cadillac F1 Team"]
        rows = ranked_rows([row(i, n, 110-p, p) for p, (i, n) in enumerate(zip(ids, names), 1)][::-1])
        cars = constructors_from_standings(rows)
        self.assertEqual([c["id"] for c in cars], ["mercedes", "ferrari", "mclaren", "redbull", "racingbulls", "alpine", "haas", "audi", "williams", "astonmartin", "cadillac"])
        self.assertEqual([c["index"] for c in cars], list(range(1, 12)))
        for car in cars:
            self.assertTrue((Path(__file__).resolve().parents[1] / "assets" / "f1_2026" / car["image"]).is_file())

    def test_display_name_alias_fallback(self):
        cars = constructors_from_standings([{"team": n} for n in ["Red Bull Racing", "Racing Bulls", "Haas F1 Team", "Aston Martin"]])
        self.assertEqual([c["id"] for c in cars], ["redbull", "racingbulls", "haas", "astonmartin"])

    def test_missing_data_does_not_invent_standings(self):
        self.assertEqual(constructors_from_standings([]), [])
        self.assertEqual(constructors_from_standings([{"team": "Unknown entrant"}]), [])
        cars = constructors_from_standings([{"team": "Mercedes", "points": None}])
        self.assertIsNone(cars[0]["points"])

    def test_calibration_is_preserved_and_source_rows_not_mutated(self):
        rows = [{"team_id": "mercedes", "points": 20, "position": 1}]
        cars = constructors_from_standings(rows)
        for field in ("scale", "x", "y"):
            self.assertEqual(cars[0][field], CONSTRUCTOR_ASSETS["mercedes"][field])
        self.assertEqual(rows, [{"team_id": "mercedes", "points": 20, "position": 1}])


if __name__ == "__main__":
    unittest.main()
