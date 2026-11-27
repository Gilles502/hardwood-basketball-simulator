"""Top-5 pick protection: only this draft's pick has a lottery slot; a future first of the same team does not."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.trade_fixtures import era_of, finder, make_team, make_torneo
from trades.trade_finder import TradeFinder

ERA = era_of()


class Top5PickYearTests(unittest.TestCase):
    def setUp(self):
        self.teams = [make_team(n, wins=w, losses=82 - w) for n, w in (("Bad", 15), ("Mid", 41), ("Good", 60))]
        self.t = make_torneo(self.teams, plans={t.nome: "MIDDLE" for t in self.teams})
        self.t.draft_lottery_order = ["Bad", "Mid", "Good"]
        self.t.pick_ownership = {y: {f"R1-{t.nome}": t.nome for t in self.teams} for y in range(1, 6)}
        self.t.pick_protections = {y: {} for y in range(1, 6)}

    def top5(self, asset, manual=False):
        f = finder(self.t)
        f.manual = manual
        with mock.patch.object(TradeFinder, "era", return_value=ERA):
            return f._is_top5_pick(asset)

    def test_this_drafts_lottery_pick_is_top5(self):
        self.assertTrue(self.top5("1:R1-Bad"))
        self.assertTrue(self.top5("R1-Bad"))   # legacy key without a year: this draft

    def test_future_firsts_of_a_lottery_team_are_not_top5(self):
        for year in range(2, 6):
            for manual in (False, True):
                with self.subTest(year=year, manual=manual):
                    self.assertFalse(self.top5(f"{year}:R1-Bad", manual=manual))


if __name__ == "__main__":
    unittest.main()
