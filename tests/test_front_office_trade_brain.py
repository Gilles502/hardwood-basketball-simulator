"""AI GM layer 2a: the pure trade brain (core/front_office/trade_brain.py)."""
import dataclasses
import os
import random
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office import trade_brain as tb
from core.front_office.models import CpuGM
from core.models import Abilita

FO = CONFIG.FRONT_OFFICE
DEF_ATTRS = FO.PROFILE_ATTRIBUTES["DEFENSE"]


def abilities(value=60, **over):
    names = {a for attrs in FO.COACH_STYLE_ATTRIBUTES.values() for a in attrs}
    names |= {a for attrs in FO.PROFILE_ATTRIBUTES.values() for a in attrs}
    values = {n: value for n in names}
    values.update(over)
    return SimpleNamespace(**values)


def player(ovr=75, age=27, salary=5.0, years=2, team_years=1, abil=None):
    return SimpleNamespace(ovr=ovr, eta=age, abilita=abil if abil is not None else abilities(),
                           contract=SimpleNamespace(salario_annuale=salary, anni_rimanenti=years),
                           anni_nella_squadra=team_years)


def gm(traits=(), trade=60):
    return CpuGM(gm_id="g", name="G", age=45, years_as_gm=3, traits=list(traits),
                 skills={"trade": trade, "contracts": 60, "draft": 60})


def league_2002_like(top=None):
    """428 players: 32 at 85-95, 33 at 80-84, the rest 60-79 (the 2002 start)."""
    stars = top if top is not None else [85 + (i % 11) for i in range(32)]
    core = [84 - (i % 5) for i in range(33)]
    rest = [60 + (i % 20) for i in range(428 - len(stars) - len(core))]
    return [player(ovr=o) for o in stars + core + rest]


LINES = {"DEFENSE": 70.0, "OFFENSE": 70.0, **{style: 70.0 for style in FO.COACH_STYLE_ATTRIBUTES}}


def tags(asset, own=False, star_line=85, cap=100.0):
    return tb.asset_tags(asset, own=own, star_line=star_line, cap=cap, lines=LINES)


class ConfigTests(unittest.TestCase):
    def test_config_covers_every_trait_and_style(self):
        self.assertEqual(set(FO.TRAIT_VALUE), set(FO.TRAITS))
        self.assertEqual(set(FO.COACH_STYLE_ATTRIBUTES), set(FO.COACH_STYLE_TARGETS))
        fields = {f.name for f in dataclasses.fields(Abilita)}
        for attrs in list(FO.COACH_STYLE_ATTRIBUTES.values()) + list(FO.PROFILE_ATTRIBUTES.values()):
            for a in attrs:
                self.assertIn(a, fields)


class LineTests(unittest.TestCase):
    def test_lines_match_today_on_a_2002_like_league(self):
        self.assertEqual(tb.protection_lines(league_2002_like()), (85, 80))

    def test_lines_rise_with_inflation(self):
        star, _ = tb.protection_lines(league_2002_like(top=[87 + (i % 8) for i in range(50)]))
        self.assertGreaterEqual(star, 87)

    def test_lines_floor_and_empty_league(self):
        self.assertEqual(tb.protection_lines([]), (85, 80))
        self.assertEqual(tb.protection_lines([player(ovr=70) for _ in range(10)]), (85, 80))
        self.assertEqual(tb.profile_lines([])["DEFENSE"], float("inf"))

    def test_profile_lines_top_quarter(self):
        players = [player(abil=abilities(**{a: v for a in DEF_ATTRS})) for v in range(1, 101)]
        self.assertEqual(tb.profile_lines(players)["DEFENSE"], 76)
        bare = SimpleNamespace(ovr=70, eta=25, abilita=None)
        self.assertIsNone(tb.profile_score(bare, DEF_ATTRS))
        self.assertEqual(tb.profile_lines([bare])["DEFENSE"], float("inf"))


class TagTests(unittest.TestCase):
    def test_asset_tags(self):
        self.assertEqual(tags("2:R1-Boston Minutemen"), {"pick_r1"})
        self.assertEqual(tags("R2-X"), {"pick_r2"})
        vet = tags(player(ovr=78, age=31, years=1))
        self.assertTrue({"player_30_plus", "player_29_plus_75", "expiring"} <= vet)
        young = tags(player(ovr=74, age=23, team_years=5), own=True)
        self.assertTrue({"own_young", "own_long_tenure", "player_24_minus"} <= young)
        self.assertIn("long_heavy", tags(player(ovr=82, salary=25.0, years=3)))
        self.assertNotIn("long_heavy", tags(player(ovr=86, salary=25.0, years=3)))
        self.assertIn("player_star", tags(player(ovr=86)))
        self.assertIn("defender", tags(player(abil=abilities(**{a: 80 for a in DEF_ATTRS}))))
        self.assertNotIn("own_young", tags(player(age=23)))


class MultiplierTests(unittest.TestCase):
    def test_trait_multiplier_values(self):
        self.assertAlmostEqual(tb.trait_multiplier(gm(["PICK_HOARDER"]), {"pick_r1"}), 1.20)
        self.assertAlmostEqual(tb.trait_multiplier(gm(["YOUTH_FIRST"]), {"player_30_plus"}), 0.88)
        self.assertEqual(tb.trait_multiplier(gm(["TRADE_HAPPY"]), {"pick_r1", "expiring"}), 1.0)

    def test_trait_product_clamped(self):
        values = dict(FO.TRAIT_VALUE, TRADE_HAPPY={"pick_r1": 1.30})
        patched = dataclasses.replace(CONFIG, FRONT_OFFICE=dataclasses.replace(FO, TRAIT_VALUE=values))
        with mock.patch.object(tb, "CONFIG", patched):
            self.assertEqual(tb.trait_multiplier(gm(["PICK_HOARDER", "PATIENT_BUILDER", "TRADE_HAPPY"]),
                                                 {"pick_r1"}), 1.40)
            self.assertAlmostEqual(tb.trait_multiplier(gm(["YOUTH_FIRST", "PICK_HOARDER"]),
                                                 {"player_30_plus"}), 0.8096)

    def test_no_gm_is_neutral(self):
        p = player()
        self.assertEqual(tb.trait_multiplier(None, {"pick_r1"}), 1.0)
        self.assertEqual(tb.skill_price_multiplier(None), 1.0)
        self.assertEqual(tb.user_squeeze(None), 0.0)
        self.assertEqual(tb.coach_fit_multiplier(None, p, LINES), 1.0)
        self.assertFalse(tb.has_trait(None, "PICK_HOARDER"))

    def test_unknown_trait_ignored(self):
        self.assertEqual(tb.trait_multiplier(gm(["NOT_A_TRAIT"]), {"pick_r1"}), 1.0)

    def test_skill_price_curve(self):
        self.assertAlmostEqual(tb.skill_price_multiplier(60), 1.00)
        self.assertAlmostEqual(tb.skill_price_multiplier(50), 0.97)
        self.assertAlmostEqual(tb.skill_price_multiplier(82), 1.05)
        self.assertAlmostEqual(tb.skill_price_multiplier(65), 1.0125)
        self.assertAlmostEqual(tb.skill_price_multiplier(10), 0.88)
        self.assertAlmostEqual(tb.skill_price_multiplier(99), 1.07)

    def test_user_squeeze(self):
        self.assertEqual(tb.user_squeeze(60), 0.0)
        self.assertEqual(tb.user_squeeze(40), 0.0)
        self.assertAlmostEqual(tb.user_squeeze(82), 0.044)
        self.assertAlmostEqual(tb.user_squeeze(100), 0.06)

    def test_disaster_only_below_35(self):
        rng = random.Random(1)
        self.assertTrue(all(tb.disaster_factor(45, rng) == 1.0 for _ in range(100)))
        self.assertEqual(tb.disaster_factor(None, rng), 1.0)
        draws = [tb.disaster_factor(20, rng) for _ in range(100)]
        self.assertTrue(all(0.82 - 1e-9 <= d <= 1.0 for d in draws))
        self.assertTrue(any(d < 0.95 for d in draws))

    def test_vulture(self):
        self.assertTrue(tb.is_vulture(gm(trade=70)))
        self.assertFalse(tb.is_vulture(gm(trade=69)))
        self.assertFalse(tb.is_vulture(None))

    def test_coach_fit(self):
        attrs = FO.COACH_STYLE_ATTRIBUTES["Twin Towers"]
        big = player(abil=abilities(**{a: 80 for a in attrs}))
        self.assertAlmostEqual(tb.coach_fit_multiplier("Twin Towers", big, LINES), FO.COACH_FIT_BONUS)
        self.assertEqual(tb.coach_fit_multiplier("Twin Towers", player(), LINES), 1.0)
        self.assertEqual(tb.coach_fit_multiplier("No Such Style", big, LINES), 1.0)
        self.assertEqual(tb.coach_fit_multiplier("Twin Towers", "1:R1-X", LINES), 1.0)


if __name__ == "__main__":
    unittest.main()
