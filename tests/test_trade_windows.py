"""The season's two CPU trade windows (main.Tournament) run on wishes: trades/windows.run_trade_window."""
import types
import unittest
from types import SimpleNamespace
from unittest import mock

import main
from core.config import CONFIG
from trades import windows
from trades.trade_finder import TradeFinder
from tests import test_trade_engines_framework as fw

# Old random engines and volume knobs that are gone: every CPU trade is born from a wish.
REMOVED = ("attempt_upgrade_trade", "gestisci_asta_giocatore", "attempt_dump_trade", "attempt_star_trade_demand",
           "resolve_roster_congestion", "attempt_3_team_blockbuster", "_attempt_3_team_star_facilitator",
           "_attempt_3_team_positional_swap", "_attempt_3_team_win_now_rebuild", "attempt_4_team_blockbuster",
           "attempt_cap_relief_trade", "attempt_pick_for_pick_trade", "attempt_bench_shuffle_trade",
           "attempt_positional_swap_trade", "attempt_win_now_for_prospect_trade",
           "attempt_multi_player_package_trade", "simulate_cpu_to_cpu_draft_trade", "deal_limit_bonus",
           "_aggressive_rebuild_chance")


class Podcast:
    def __init__(self):
        self.logged = []

    def log_trade(self, trade, period):
        self.logged.append((trade, period))


def fake_window(lines):
    """A run_trade_window stand-in: records the window asked for and returns a finder whose log is `lines`."""
    asked = []

    def run(torneo, window):
        asked.append((torneo, window))
        return len(lines), SimpleNamespace(logscambi=list(lines))
    return run, asked


class WindowSwitchTests(unittest.TestCase):
    def _torneo(self):
        t, _ = fw.league({"A": fw.SF_RICH, "B": fw.C_RICH}, {"A": "CONTENDER", "B": "PLAYOFF"})
        t.podcast_logger = Podcast()
        return t

    def test_deadline_runs_the_deadline_window(self):
        t = self._torneo()
        run, asked = fake_window(["trade one", "trade two"])
        with mock.patch.object(main, "run_trade_window", side_effect=run):
            main.Tournament.trade_period_midseason(t)
        self.assertEqual(asked, [(t, "deadline")])
        self.assertEqual(t.offseason_log_data["scambi_midseason"], ["trade one", "trade two"])
        self.assertEqual(t.podcast_logger.logged, [("trade one", "mid_season"), ("trade two", "mid_season")])

    def test_predraft_runs_the_predraft_window(self):
        t = self._torneo()
        run, asked = fake_window(["pre one"])
        with mock.patch.object(main, "run_trade_window", side_effect=run):
            main.Tournament.trade_period_predraft(t)
        self.assertEqual(asked, [(t, "predraft")])
        self.assertEqual(t.offseason_log_data["scambi"], ["pre one"])
        self.assertEqual(t.podcast_logger.logged, [("pre one", "offseason")])

    def test_trade_difficulty_sets_no_volume_cap(self):
        for diff in ("easy", "realistic", "hardcore"):
            t = self._torneo()
            t.trade_difficulty = diff
            run, asked = fake_window([f"t{i}" for i in range(40)])
            with mock.patch.object(main, "run_trade_window", side_effect=run):
                main.Tournament.trade_period_midseason(t)
            self.assertEqual(len(t.offseason_log_data["scambi_midseason"]), 40, diff)


class RealWindowTests(fw.EngineTestCase):
    """The deadline on a two-team fixture league, real runner and engines: a crossed positional swap closes."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(TradeFinder, "get_strategic_value",
                              lambda self, a, tm, pp=None: 1.0 if isinstance(a, str) else (10.0 if a in tm.roster else 12.0))
        p.start()
        self.addCleanup(p.stop)

    def test_deadline_trades_reach_the_ui_log(self):
        t, teams = fw.league({"A": fw.SF_RICH, "B": fw.C_RICH}, {"A": "CONTENDER", "B": "PLAYOFF"})
        t.podcast_logger = Podcast()
        seen = []

        def spy(torneo, window):
            count, f = windows.run_trade_window(torneo, window)
            seen.append((count, list(f.logscambi)))
            return count, f

        with mock.patch.object(main, "run_trade_window", side_effect=spy):
            main.Tournament.trade_period_midseason(t)
        count, lines = seen[0]
        self.assertGreaterEqual(count, 1)
        self.assertEqual(t.offseason_log_data["scambi_midseason"], lines)
        self.assertEqual(len(t.podcast_logger.logged), len(lines))
        self.assertIn("positional_swap", [r["trade_type"] for r in t.trade_analytics_history])


class RemovedEnginesTests(unittest.TestCase):
    def test_old_random_engines_are_gone(self):
        present = [name for name in REMOVED if hasattr(TradeFinder, name)]
        self.assertEqual(present, [])

    def test_old_volume_knobs_are_gone(self):
        for name in ("BENCH_SHUFFLE_PER_WINDOW", "TRADE_HAPPY_EXTRA_DEALS"):
            self.assertFalse(hasattr(CONFIG.FRONT_OFFICE, name), name)

    def test_user_side_and_engine_helpers_stay(self):
        kept = ("find_trades_for_package", "find_trades_for_player", "find_trades_for_pick",
                "find_trades_for_target_player", "generate_live_draft_offers", "get_tradeable_players",
                "_build_bid_for_player", "_try_request_extra_asset", "_collect_team_picks", "get_strategic_value",
                "_get_pick_position", "_is_top5_pick", "_vultures_first", "_draft_prospects", "wishes_for",
                "plan_check", "_wish_asset", "execute_deal", "would_accept_trade_with_reason", "begin_window",
                "era", "_bench", "_get_team_positional_needs", "execute_trade", "execute_3_team_trade",
                "execute_4_team_trade")
        self.assertEqual([n for n in kept if not hasattr(TradeFinder, n)], [])



class UntouchableRefreshTests(unittest.TestCase):
    """Stale untouchable flags (draft night, an old core) are recomputed before every window: in one long session
    they used to pile up until 82% of the league could not be traded."""

    def setUp(self):
        from core.models import Squadra
        self.t, self.teams = fw.league({"A": fw.SF_RICH, "B": fw.C_RICH}, {"A": "CONTENDER", "B": "PLAYOFF"})
        for team in self.teams.values():   # the real rule on the fixture's team doubles
            team.designa_intoccabili = types.MethodType(Squadra.designa_intoccabili, team)
            team._limit_veteran_untouchables = types.MethodType(Squadra._limit_veteran_untouchables, team)

    def test_window_clears_a_stale_flag(self):
        t, teams = self.t, self.teams
        bench = min(teams["B"].roster, key=lambda p: p.ovr)
        bench.eta = 33
        bench.is_untouchable = True
        with mock.patch.object(windows.engines, "engines_for", return_value=[]):
            windows.run_trade_window(t, "deadline")
        self.assertFalse(bench.is_untouchable)

    def test_refresh_keeps_the_franchise_player(self):
        t, teams = self.t, self.teams
        star = max(teams["A"].roster, key=lambda p: p.ovr)
        star.valutazione = 88
        star.is_untouchable = False
        windows.refresh_untouchables(t)
        self.assertTrue(star.is_untouchable)


if __name__ == "__main__":
    unittest.main()
