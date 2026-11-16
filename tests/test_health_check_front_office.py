"""Health report: the front-office offseason (GM firings, retirements, hirings) in a season."""
import unittest
from types import SimpleNamespace

from scripts import health_check
from scripts.health_check import coach_change_count, front_office_metrics


def gm(gm_id, name, **skills):
    return SimpleNamespace(gm_id=gm_id, name=name, skills=skills)


FO = SimpleNamespace(
    gms={"a": gm("a", "Ann", trade=80, scouting=60), "b": gm("b", "Bob", trade=50, scouting=50),
         "c": gm("c", "Cy", trade=90, scouting=90)},
    seats={"Lakers": "a", "Suns": "b", "Heat": "c"},
)
EVENTS = {
    "teams": ["Lakers", "Suns", "Heat"],
    "coach_fired": 1,
    "coach_changes": 4,
    "retired": [{"gm": "Old", "gm_id": "o", "team": "Suns"}],
    "fired": [{"team": "Lakers", "gm": "Lou", "gm_id": "l", "reason": "missed playoffs"},
              {"team": "Heat", "gm": "Hal", "gm_id": "h", "reason": "bad run"}],
    "hired": [{"team": "Lakers", "gm": "Ann", "gm_id": "a", "historical": True, "over": []},
              {"team": "Suns", "gm": "Bob", "gm_id": "b", "historical": False, "over": []},
              {"team": "Heat", "gm": "Cy", "gm_id": "c", "historical": False, "over": []}],
}


class FrontOfficeMetricsTests(unittest.TestCase):
    def test_front_office_metrics_counts(self):
        m = front_office_metrics(EVENTS, FO)
        self.assertEqual((m["gm_fired"], m["gm_retired"], m["gm_hired"], m["historical_hired"], m["coach_fired"]),
                         (2, 1, 3, 1, 1))
        self.assertEqual(m["changes"][0], ("Lakers", "Lou", "Ann", "missed playoffs"))
        self.assertEqual(m["changes"][1], ("Suns", "Old", "Bob", "retired"))
        self.assertEqual(m["top_gm"], {"name": "Cy", "average": 90.0})
        self.assertEqual((m["empty_seats"], m["double_seats"]), (0, 0))
        self.assertEqual(m["coach_changes"], 4)
        self.assertEqual(m["seated_skill_avg"], 70.0)   # Ann 70, Bob 50, Cy 90

    def test_report_shows_coach_changes_and_seated_skill(self):
        season = {
            "season": 1, "sim_seconds": 10, "champion": "A",
            "wins": {"max": 60, "min": 20, "stdev": 9.0}, "payroll": {"over_tax": 1, "over_second_apron": 0,
                                                                     "under_cap": 3, "cap": 40.0, "avg": 45.0},
            "trades": {"total": 2, "max_per_team": 1, "by_type": {"a": 2}, "by_period": {"deadline": 2}},
            "rosters": {"min": 13, "max": 15}, "retired_this_season": 3, "log_errors": 0,
            "strategy": {"flips_preseason_to_deadline": 2, "preseason_distribution": {}},
            "talent": {"avg_top8_ovr": 80.0, "players_90": 1, "players_85": 5}, "owner_personalities": {},
            "front_office": front_office_metrics(EVENTS, FO),
        }
        report = health_check.render_report({"config": {"label": "t"}, "status": "ok", "seasons": [season]})
        self.assertIn("| coaches fired | coach changes |", report)
        self.assertIn("| seated GM avg skill |", report)
        self.assertIn("| 1 | 2 | 1 | 3 | 1 | 1 | 4 | 0 | 0 | 70 | Cy (90) |", report)

    def test_coach_change_count(self):
        before = {"Lakers": "Phil", "Suns": "Mike", "Heat": "Pat", "Jazz": None}
        after = {"Lakers": "Phil", "Suns": "Interim Joe", "Heat": None, "Jazz": "Jerry"}
        self.assertEqual(coach_change_count(before, after), 3)
        self.assertEqual(coach_change_count({}, after), 0)

    def test_empty_and_double_seats(self):
        fo = SimpleNamespace(gms=FO.gms, seats={"Lakers": "a", "Suns": "a"})
        m = front_office_metrics(EVENTS, fo)
        self.assertEqual((m["empty_seats"], m["double_seats"]), (1, 1))

    def test_quiet_season(self):
        m = front_office_metrics({"teams": ["Lakers"], "retired": [], "fired": [], "hired": []}, FO)
        self.assertEqual((m["gm_fired"], m["gm_retired"], m["gm_hired"], m["coach_fired"], m["coach_changes"],
                          m["changes"]), (0, 0, 0, 0, 0, []))


if __name__ == "__main__":
    unittest.main()
