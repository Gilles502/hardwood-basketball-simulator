"""Opponent scouting maths: threat skills, matchup gaps, danger ranking and the one-click fix."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.scouting_matchups import badge, build_report, defense_vs, series_opponent, skills_of

CFG = CONFIG.SCOUTING_MATCHUPS


def p(name, role, minutes=30, three=50, speed=50, handle=50, close=50, post=40, strength=50,
      per_d=50, int_d=50, t3=70, tdrive=50, tpost=30, injured=False):
    return SimpleNamespace(
        nome=name, ruolo=role, minuti_target=minutes, infortunato=injured,
        abilita=SimpleNamespace(
            three_point_shot_rating=three, speed=speed, ball_handling=handle, close_shot_rating=close,
            post_control_rating=post, strength=strength,
            perimeter_defense_rating=per_d, interior_defense_rating=int_d,
        ),
        tendenze=SimpleNamespace(three_point_shot_tendency=t3, drive_to_basket_tendency=tdrive, post_up_tendency=tpost),
    )


def row(report, name):
    return next(r for r in report if r["name"] == name)


class SkillTests(unittest.TestCase):
    def test_skills_and_defense(self):
        guy = p("A", "SG", three=94, speed=80, handle=70, close=60, post=40, strength=50, per_d=77, int_d=33)
        self.assertEqual(skills_of(guy), {"3PT": 94, "DRIVE": 70, "POST": 50})
        self.assertEqual(defense_vs(guy, "3PT"), 77)
        self.assertEqual(defense_vs(guy, "DRIVE"), 77)
        self.assertEqual(defense_vs(guy, "POST"), 33)

    def test_badge_boundaries(self):
        self.assertEqual(badge(-20, CFG), "bad")
        self.assertEqual(badge(-19, CFG), "watch")
        self.assertEqual(badge(-10, CFG), "watch")
        self.assertEqual(badge(-9, CFG), "fine")


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.star = p("Star", "SG", minutes=38, three=94, t3=80)
        self.shooter = p("Shooter", "SF", minutes=30, three=85, t3=70)
        self.my_sg = p("Wall", "SG", per_d=96)
        self.my_sf = p("Sieve", "SF", per_d=60)
        self.mine = [self.my_sg, self.my_sf]
        self.positions = {"SG": self.my_sg, "SF": self.my_sf}
        self.their = [(self.star, "SG"), (self.shooter, "SF")]

    def test_covered_star_ranks_below_uncovered_shooter(self):
        report = build_report(self.their, self.mine, self.positions, {"matchups": {}, "double_teams": []}, CFG)
        self.assertEqual([r["name"] for r in report], ["Shooter", "Star"])
        self.assertEqual(row(report, "Shooter")["badge"], "bad")
        self.assertEqual(row(report, "Shooter")["gap"], -25)
        self.assertTrue(row(report, "Star")["auto"])

    def test_plan_overrides_auto_defender(self):
        report = build_report(self.their, self.mine, self.positions, {"matchups": {"Star": "Sieve"}, "double_teams": []}, CFG)
        star = row(report, "Star")
        self.assertEqual((star["defender"], star["auto"], star["defense"]), ("Sieve", False, 60))

    def test_injured_plan_defender_falls_back_to_auto(self):
        self.my_sf.infortunato = True
        report = build_report(self.their, self.mine, self.positions, {"matchups": {"Star": "Sieve"}, "double_teams": []}, CFG)
        self.assertEqual((row(report, "Star")["defender"], row(report, "Star")["auto"]), ("Wall", True))

    def test_no_fix_when_fine(self):
        report = build_report(self.their, self.mine, self.positions, {"matchups": {}, "double_teams": []}, CFG)
        self.assertIsNone(row(report, "Star")["fix"])

    def test_fix_skips_auto_defender_of_bigger_threat(self):
        # Wall already guards the Star (auto); moving him would leave the Star to Sieve, so suggest Mid instead
        mid = p("Mid", "PF", minutes=20, per_d=75)
        report = build_report(self.their, self.mine + [mid], dict(self.positions, PF=mid), {"matchups": {}, "double_teams": []}, CFG)
        self.assertEqual(row(report, "Shooter")["fix"], "Mid")

    def test_fix_skips_defender_taken_by_bigger_threat(self):
        a = p("A", "SG", minutes=36, three=95)
        b = p("B", "SF", minutes=34, three=90)
        lock = p("Lock", "PF", minutes=30, per_d=92)
        second = p("Second", "C", minutes=20, per_d=80)
        weak_sg, weak_sf = p("WeakSG", "SG", per_d=55), p("WeakSF", "SF", per_d=58)
        mine = [weak_sg, weak_sf, lock, second]
        positions = {"SG": weak_sg, "SF": weak_sf, "PF": lock, "C": second}
        report = build_report([(a, "SG"), (b, "SF")], mine, positions, {"matchups": {"A": "Lock"}, "double_teams": []}, CFG)
        self.assertEqual(row(report, "A")["badge"], "fine")
        self.assertEqual(row(report, "B")["fix"], "Second")


class SeriesOpponentTests(unittest.TestCase):
    """The user's unfinished playoff series, wherever the playoff mode keeps it."""

    def test_game_by_game_series_from_the_playoffs_page(self):
        series = {"E_0": {"team1_name": "Bay", "team2_name": "Toronto", "wins1": 2, "wins2": 1, "round": "CONF_SEMIS", "complete": False}}
        self.assertEqual(series_opponent("Toronto", series, [], None),
                         {"opponent": "Bay", "round": "CONF_SEMIS", "user_wins": 1, "opp_wins": 2})

    def test_finished_series_is_skipped(self):
        series = {"E_0": {"team1_name": "Bay", "team2_name": "Toronto", "wins1": 4, "wins2": 1, "round": "R1", "complete": True}}
        self.assertIsNone(series_opponent("Toronto", series, [], None))

    def test_tournament_series_list(self):
        t, b = SimpleNamespace(nome="Toronto"), SimpleNamespace(nome="Bay")
        active = [{"s1": t, "s2": b, "vittorie": {"Toronto": 3, "Bay": 0}, "winner_nome": None, "round": "QF"}]
        self.assertEqual(series_opponent("Toronto", {}, active, None),
                         {"opponent": "Bay", "round": "QF", "user_wins": 3, "opp_wins": 0})

    def test_bracket_fallback(self):
        bracket = {"east": {"sf": [{"s1_nome": "Bay", "s2_nome": "Toronto", "s1_vittorie": 1, "s2_vittorie": 2, "winner_nome": None}]}}
        self.assertEqual(series_opponent("Toronto", {}, [], bracket),
                         {"opponent": "Bay", "round": "SF", "user_wins": 2, "opp_wins": 1})

    def test_no_series(self):
        self.assertIsNone(series_opponent("Toronto", {}, [], None))


if __name__ == "__main__":
    unittest.main()
