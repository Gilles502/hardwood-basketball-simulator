"""Health check: the AI GM additions (front office in the reload fingerprint, plan changes per season)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.front_office.models import TeamPlan
from core.front_office.state import FrontOfficeState
from scripts import health_check


def torneo_with_plans():
    fo = FrontOfficeState(seats={"B": "gm_b", "A": "gm_a"})
    fo.plans["A"] = TeamPlan("REBUILDER", 2003, 1, "r", history=[
        {"year": 2002, "from": None, "to": "PLAYOFF", "reason": "x", "checkpoint": "start"},
        {"year": 2002, "from": "PLAYOFF", "to": "REBUILDER", "reason": "y", "checkpoint": "deadline"},
    ])
    fo.plans["B"] = TeamPlan("MIDDLE", 2003, 1, "r", history=[
        {"year": 2002, "from": None, "to": "CONTENDER", "reason": "x", "checkpoint": "start"},
        {"year": 2003, "from": "CONTENDER", "to": "MIDDLE", "reason": "z", "checkpoint": "new_season"},
    ])
    return SimpleNamespace(front_office=fo, squadre=[], season_number=2, starting_year=2002)


class PlanMetricsTests(unittest.TestCase):
    def test_plan_change_counts_skip_first_plans(self):
        counts = health_check._plan_change_counts(torneo_with_plans())
        self.assertEqual(counts, {"deadline": 1, "new_season": 1})
        self.assertEqual(health_check._plan_change_counts(SimpleNamespace()), {})

    def test_plan_metrics_are_the_changes_of_one_cycle(self):
        t = torneo_with_plans()
        before = {"deadline": 0, "new_season": 1}
        m = health_check._plan_metrics(t, before)
        self.assertEqual(m["in_season"], 1)
        self.assertEqual(m["new_season"], 0)
        self.assertEqual(m["distribution"], {"REBUILDER": 1, "MIDDLE": 1})

    def test_fingerprint_has_seats_and_plan_states(self):
        fp = health_check._fingerprint(torneo_with_plans())
        self.assertEqual(fp["front_office"], {"seats": {"A": "gm_a", "B": "gm_b"},
                                              "plans": {"A": "REBUILDER", "B": "MIDDLE"}})

    def test_report_shows_plan_changes(self):
        season = {
            "season": 1, "sim_seconds": 10, "champion": "A",
            "wins": {"max": 60, "min": 20, "stdev": 9.0}, "payroll": {"over_tax": 1, "over_second_apron": 0,
                                                                     "under_cap": 3, "cap": 40.0, "avg": 45.0},
            "trades": {"total": 2, "max_per_team": 1, "by_type": {"a": 2}, "by_period": {"deadline": 2}},
            "rosters": {"min": 13, "max": 15}, "retired_this_season": 3, "log_errors": 0,
            "strategy": {"flips_preseason_to_deadline": 2, "preseason_distribution": {}},
            "talent": {"avg_top8_ovr": 80.0, "players_90": 1, "players_85": 5}, "owner_personalities": {},
            "plans": {"in_season": 1, "new_season": 2, "distribution": {"MIDDLE": 30}},
        }
        report = health_check.render_report({"config": {"label": "t"}, "status": "ok", "seasons": [season]})
        self.assertIn("plan changes", report)
        self.assertIn("In-season plan changes, total: 1 (1.0/season", report)
        self.assertIn("| 1/2 |", report)


class TraitMetricsTests(unittest.TestCase):
    def _torneo(self):
        from core.front_office.models import CpuGM

        def gm(gm_id, team, traits, trade=60):
            return CpuGM(gm_id=gm_id, name=gm_id, age=45, years_as_gm=1, traits=traits,
                         skills={"trade": trade, "contracts": 60, "draft": 60}, team=team)
        fo = FrontOfficeState(gms={"a": gm("a", "A", ["TRADE_HAPPY"], trade=75), "b": gm("b", "B", ["YOUTH_FIRST"])},
                              seats={"A": "a", "B": "b"})
        return SimpleNamespace(front_office=fo, squadre=[],
                               pick_ownership={1: {"R1-A": "A", "R1-B": "A"}, 2: {"R2-B": "B"}})

    def test_trait_metrics_counts_each_side(self):
        trades = [{"teams": ["A", "B"]}, {"teams": ["A", "C", "A"]}]
        m = health_check._trait_metrics(self._torneo(), trades)
        self.assertEqual(m["trades_per_gm"]["TRADE_HAPPY"], 2.0)
        self.assertEqual(m["trades_per_gm"]["YOUTH_FIRST"], 1.0)
        self.assertEqual(m["trades_per_gm"]["ALL"], 1.5)
        self.assertEqual(m["picks_per_gm"]["TRADE_HAPPY"], 2.0)
        self.assertEqual(m["picks_per_gm"]["YOUTH_FIRST"], 1.0)
        self.assertEqual(m["gms"], {"TRADE_HAPPY": 1, "YOUTH_FIRST": 1, "VULTURE": 1, "ALL": 2})
        self.assertEqual(m["trades_per_gm"]["VULTURE"], 2.0)

    def test_auctions_won_by_vultures(self):
        trades = [{"type": "veteran_sale", "teams": ["S", "A"]},
                  {"type": "roster_congestion", "teams": ["S", "B"]},
                  {"type": "cap_relief", "teams": ["A", "B"]}]
        m = health_check._trait_metrics(self._torneo(), trades)
        self.assertEqual(m["auctions"], 2)
        self.assertEqual(m["auctions_won_by_vulture"], 1)
        self.assertEqual(health_check._trait_metrics(SimpleNamespace(), trades), {})


if __name__ == "__main__":
    unittest.main()
