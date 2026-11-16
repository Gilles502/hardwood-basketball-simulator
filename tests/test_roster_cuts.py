"""Roster cut-down: the same choice for the engine and for the End of Season Hub preview."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.roster_cuts import cut_order, cut_target, is_protected, pick_cuts, validate_releases

CFG = CONFIG.OFFSEASON


def player(name, ovr, age=28, pot=None, untouchable=False, trade_value=None):
    return SimpleNamespace(nome=name, ovr=ovr, eta=age, potenziale=pot if pot is not None else ovr,
                           is_untouchable=untouchable, trade_value=trade_value if trade_value is not None else ovr)


class PickCutsTests(unittest.TestCase):
    def test_target_is_engine_limit(self):
        self.assertEqual(cut_target(CFG), CFG.ROSTER_SIZE_LIMIT - 1)

    def test_no_cuts_at_or_under_limit(self):
        roster = [player(f"P{i}", 70) for i in range(5)]
        self.assertEqual(pick_cuts(roster, 5, CFG), [])

    def test_cuts_lowest_score_first(self):
        roster = [player(f"P{i}", 72) for i in range(4)] + [player("Worst", 55, 33), player("Bad", 60, 31)]
        self.assertEqual([p.nome for p in pick_cuts(roster, 4, CFG)], ["Worst", "Bad"])

    def test_young_high_potential_is_protected(self):
        kid = player("Kid", 62, age=21, pot=CFG.CUT_POTENTIAL_IMMUNITY_THRESHOLD)
        vet = player("Vet", 62, age=30)
        roster = [player(f"P{i}", 74) for i in range(3)] + [kid, vet]
        self.assertEqual([p.nome for p in pick_cuts(roster, 4, CFG)], ["Vet"])

    def test_untouchables_fallback_by_trade_value(self):
        roster = [player("A", 80, untouchable=True, trade_value=50), player("B", 80, untouchable=True, trade_value=10),
                  player("C", 80, untouchable=True, trade_value=30)]
        self.assertEqual([p.nome for p in pick_cuts(roster, 2, CFG)], ["B"])

    def test_does_not_mutate_roster(self):
        roster = [player(f"P{i}", 60 + i) for i in range(6)]
        pick_cuts(roster, 3, CFG)
        self.assertEqual(len(roster), 6)


class CutSheetRulesTests(unittest.TestCase):
    def test_cut_order_lowest_first(self):
        roster = [player("Good", 74), player("Worst", 55, 33), player("Star", 90, untouchable=True), player("Bad", 60, 31)]
        self.assertEqual([p.nome for p in cut_order(roster, CFG)], ["Worst", "Bad", "Good", "Star"])

    def test_is_protected(self):
        self.assertTrue(is_protected(player("Star", CFG.CUT_OVR_IMMUNITY_THRESHOLD), CFG))
        self.assertTrue(is_protected(player("Kid", 62, age=21, pot=CFG.CUT_POTENTIAL_IMMUNITY_THRESHOLD), CFG))
        self.assertTrue(is_protected(player("Untouchable", 60, untouchable=True), CFG))
        self.assertFalse(is_protected(player("Vet", 62, age=30), CFG))

    def test_validate_releases_ok(self):
        self.assertIsNone(validate_releases(["A", "B", "C"], ["C"], 2))

    def test_validate_releases_too_few(self):
        self.assertEqual(validate_releases(["A", "B", "C", "D"], ["D"], 2), "Release 1 more to reach 2")

    def test_release_unknown_rejected(self):
        self.assertEqual(validate_releases(["A", "B"], ["Zed"], 2), "Zed is not on your roster")

    def test_release_protected_allowed(self):
        # Protection only binds the AI: the user may release anyone on his own roster.
        self.assertIsNone(validate_releases(["Star", "B", "C"], ["Star"], 2))

    def test_extra_releases_allowed(self):
        self.assertIsNone(validate_releases(["A", "B", "C"], ["B", "C"], 2))


class ReleasePlayersTests(unittest.TestCase):
    def _tournament(self, roster):
        from main import Tournament
        team = SimpleNamespace(nome="Toronto Northmen", roster=roster)
        t = SimpleNamespace(free_agents_pool=[], giocatori_ritirati=[], offseason_log_data={}, season_number=25,
                            squadre=[team], squadra_giocatore=team)
        t._taglia_giocatore = lambda *args: Tournament._taglia_giocatore(t, *args)
        return Tournament, t, team

    def test_release_players_to_fa_and_log(self):
        young = SimpleNamespace(nome="Silas Dalton", ovr=63, eta=20, squadra="Toronto Northmen", contract=object())
        old = SimpleNamespace(nome="Old Guy", ovr=60, eta=36, squadra="Toronto Northmen", contract=object())
        keep = SimpleNamespace(nome="Keeper", ovr=80, eta=27, squadra="Toronto Northmen", contract=object())
        Tournament, t, team = self._tournament([young, old, keep])
        released = Tournament.release_players(t, team, ["Silas Dalton", "Old Guy"])
        self.assertEqual([p.nome for p in released], ["Silas Dalton", "Old Guy"])
        self.assertEqual([p.nome for p in team.roster], ["Keeper"])
        self.assertEqual([p.nome for p in t.free_agents_pool], ["Silas Dalton"])
        self.assertEqual([p.nome for p in t.giocatori_ritirati], ["Old Guy"])  # past 34 and under 76: retires
        self.assertIsNone(young.contract)
        self.assertEqual(t.offseason_log_data["user_releases"], ["Silas Dalton", "Old Guy"])
        self.assertEqual(len(t.offseason_log_data["tagli_roster"]), 2)

    def test_engine_cuts_nobody_else_after_user_release(self):
        roster = [player(f"P{i}", 60 + i) for i in range(cut_target(CFG))]
        self.assertEqual(pick_cuts(roster, cut_target(CFG), CFG), [])


if __name__ == "__main__":
    unittest.main()
