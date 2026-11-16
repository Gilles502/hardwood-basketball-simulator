"""Health check: trade rework metrics (pure function, hand-built trade lists)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import health_check


def side(team, wish="NEED_STARTER", given=10.0, received=10.0, skill=60, plan="MIDDLE"):
    return {"team": team, "plan": plan, "wish_kind": wish, "trade_skill": skill,
            "value_given": given, "value_received": received}


def trade(ttype="star_upgrade", season=1, period="deadline", teams=("A", "B"), sides=None, star=False,
          has_motive=True, team_count=2):
    sides = sides if sides is not None else [side(teams[0]), side(teams[1])]
    return {"season": season, "period": period, "teams": list(teams), "type": ttype, "team_count": team_count,
            "has_motive": has_motive, "star": star, "sides": sides}


WINDOWS = [{"season": 1, "period": "deadline"}, {"season": 1, "period": "predraft"}]


class TradeReworkMetricsTests(unittest.TestCase):
    def test_coverage_full_and_half(self):
        full = health_check.trade_rework_metrics([trade(), trade()], WINDOWS)
        self.assertEqual(full["motive_coverage"], 1.0)
        half = health_check.trade_rework_metrics([trade(), trade(has_motive=False)], WINDOWS)
        self.assertEqual(half["motive_coverage"], 0.5)

    def test_user_trades_do_not_count_as_cpu_trades(self):
        ts = [trade(), trade("user", has_motive=False)]
        m = health_check.trade_rework_metrics(ts, WINDOWS)
        self.assertEqual(m["motive_coverage"], 1.0)
        self.assertEqual(m["cpu_trades"], 1)

    def test_type_share_and_max(self):
        ts = [trade("star_upgrade"), trade("star_upgrade"), trade("tax_dump"), trade("bench_shuffle")]
        m = health_check.trade_rework_metrics(ts, WINDOWS)
        self.assertEqual(m["type_share"]["star_upgrade"], 0.5)
        self.assertEqual(m["max_type_share"], 0.5)
        self.assertEqual(m["max_type"], "star_upgrade")

    def test_trades_per_team_per_window(self):
        ts = [trade(teams=("A", "B")), trade(teams=("A", "C")), trade(teams=("A", "D"), period="predraft")]
        m = health_check.trade_rework_metrics(ts, WINDOWS)
        self.assertEqual(m["trades_per_team_per_window"]["max"], 2)       # A in the deadline window
        self.assertAlmostEqual(m["trades_per_team_per_window"]["mean"], 1.2, places=3)  # 6 team slots over 5 team-windows with a deal

    def test_star_trades_per_season(self):
        ts = [trade(star=True), trade(star=True, season=2), trade(star=True, season=2), trade()]
        windows = WINDOWS + [{"season": 2, "period": "deadline"}]
        self.assertEqual(health_check.trade_rework_metrics(ts, windows)["star_trades_per_season"], 1.5)

    def test_gifts_excluded_for_discounted_types_and_disaster_counted_apart(self):
        gift = trade(sides=[side("A", given=10, received=3), side("B", given=10, received=12)])
        disaster = trade(sides=[side("A", given=10, received=3, skill=20), side("B", given=10, received=12)])
        demand = trade("trade_demand", sides=[side("A", "STAR_WANTS_OUT", 10, 5), side("B")])
        dump = trade("tax_dump", sides=[side("A", "SHED_TAX", 10, 4), side("B", "ABSORB_SALARY")])
        fair = trade(sides=[side("A", given=10, received=6.0), side("B", given=10, received=10)])  # exactly the share
        m = health_check.trade_rework_metrics([gift, disaster, demand, dump, fair], WINDOWS)
        self.assertEqual(m["gift_trades"], 1)
        self.assertEqual(m["gift_trades_disaster"], 1)
        self.assertAlmostEqual(m["discounted_share"]["trade_demand"], 0.5)
        self.assertAlmostEqual(m["discounted_share"]["tax_dump"], 0.4)

    def test_team_count_mix(self):
        ts = [trade(), trade(), trade("facilitated_3team", teams=("A", "B", "C"), team_count=3,
                                      sides=[side("A"), side("B"), side("C")])]
        m = health_check.trade_rework_metrics(ts, WINDOWS)
        self.assertEqual(m["team_count_mix"], {2: 2 / 3, 3: 1 / 3})

    def test_type_mix_by_era_buckets_five_seasons(self):
        ts = [trade("star_upgrade", season=1), trade("tax_dump", season=5), trade("star_upgrade", season=6)]
        m = health_check.trade_rework_metrics(ts, WINDOWS)
        self.assertEqual(set(m["type_mix_by_era"]), {"1-5", "6-10"})
        self.assertEqual(m["type_mix_by_era"]["1-5"], {"star_upgrade": 0.5, "tax_dump": 0.5})
        self.assertEqual(m["type_mix_by_era"]["6-10"], {"star_upgrade": 1.0})

    def test_empty(self):
        m = health_check.trade_rework_metrics([], [])
        self.assertEqual(m["motive_coverage"], 1.0)
        self.assertEqual(m["max_type_share"], 0.0)


class RenderTests(unittest.TestCase):
    def test_report_has_trade_rework_section_and_compare_keys(self):
        ts = [trade(), trade("tax_dump", sides=[side("A", "SHED_TAX", 10, 4), side("B", "ABSORB_SALARY")])]
        season = {"season": 1, "sim_seconds": 1.0, "champion": "A",
                  "wins": {"max": 60, "min": 20, "stdev": 10.0, "teams_60_plus": 1, "teams_under_20": 0},
                  "payroll": {"cap": 1, "avg": 1, "max": 1, "min": 1, "over_tax": 0, "over_second_apron": 0, "under_cap": 0},
                  "rosters": {"min": 13, "max": 15}, "retired_this_season": 0, "log_errors": 0, "owner_personalities": {}, "talent": {
                      "avg_top8_ovr": 70, "players_90": 0, "players_85": 1},
                  "strategy": {"preseason_distribution": {}, "deadline_distribution": {}, "flips_preseason_to_deadline": 0,
                               "flips_vs_last_season": 0},
                  "trades": {"total": 2, "by_type": {"star_upgrade": 1, "tax_dump": 1}, "by_period": {"deadline": 2},
                             "max_per_team": 2, "teams_with_3_plus": 0, "list": ts, "windows": WINDOWS}}
        m = {"config": {"label": "x", "era": "2002"}, "status": "ok", "seasons": [season]}
        report = health_check.render_report(m)
        self.assertIn("## Trade rework", report)
        self.assertIn("Motive coverage", report)
        self.assertEqual(health_check.run_rework_metrics(m)["cpu_trades"], 2)


class TradeRecordTests(unittest.TestCase):
    def test_record_from_motive_and_deal(self):
        from types import SimpleNamespace
        from core.models import Giocatore
        from trades.execution import Deal
        from trades.motive import SideMotive, TradeMotive
        class Star(Giocatore):
            ovr = 85
        star = Star.__new__(Star)
        finder = SimpleNamespace(era=lambda: SimpleNamespace(star=80))
        a, b = SimpleNamespace(nome="A"), SimpleNamespace(nome="B")
        deal = Deal([a, b], [("A", "B", star)], reason="x")
        motive = TradeMotive("star_upgrade", sides=[
            SideMotive("A", plan="USER"), SideMotive("B", trade_skill=40, wish_kind="WANT_YOUTH", value_given=9.0, value_received=4.0)])
        rec = health_check._trade_record(finder, deal, motive, {"period": "deadline", "season": 3})
        self.assertEqual((rec["type"], rec["season"], rec["star"], rec["has_motive"]), ("star_upgrade", 3, True, True))
        self.assertEqual(rec["sides"][1]["value_given"], 9.0)
        legacy = health_check._trade_record(finder, Deal([a, b], [], reason="[BENCH SHUFFLE]"), None,
                                            {"period": "deadline", "season": 3})
        self.assertEqual((legacy["type"], legacy["has_motive"]), ("bench_shuffle", False))


class LegacyTypeTests(unittest.TestCase):
    def test_classify_trade_is_only_the_fallback(self):
        self.assertEqual(health_check.record_type(None, "[BENCH SHUFFLE] x"), "bench_shuffle")
        self.assertEqual(health_check.record_type({"trade_type": "tax_dump"}, "[BENCH SHUFFLE] x"), "tax_dump")


if __name__ == "__main__":
    unittest.main()
