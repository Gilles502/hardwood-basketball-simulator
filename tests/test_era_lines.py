"""Era lines: every OVR and money threshold of the trade system follows the league (core/front_office/era_lines.py)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office.era_lines import build_era_lines, era_lines_for
from tests.trade_fixtures import make_player, make_team, make_torneo

T = CONFIG.TRADES


def pl(ovr, tv=None, salary=5.0, years=2):
    return SimpleNamespace(ovr=ovr, trade_value=tv if tv is not None else T.PICK_VALUE_REFERENCE_AVG,
                           contract=SimpleNamespace(salario_annuale=salary, anni_rimanenti=years))


def league(top, tv=None):
    return [pl(o, tv, salary=0.5 + i * 0.1) for i, o in enumerate(top)]


def lines_for(players, cap=40.27, no_cap=False, year=2002):
    return build_era_lines(players, year=year, cap=cap, tax=48.0, minimum=0.9, mle=3.2, no_cap=no_cap)


class EraLinesTests(unittest.TestCase):
    def test_2002_like_league_maps_old_thresholds_to_themselves(self):
        lines = lines_for(league([90, 88, 86] + [80] * 40 + [74] * 300))
        self.assertEqual((lines.star, lines.core), (85, 80))
        for n in (72, 76, 78, 80, 83, 85, 88, 90, 95):
            self.assertEqual(lines.ovr_at(n), n)

    def test_inflated_league_moves_thresholds_up(self):
        lines = lines_for(league([95] * 30 + [88] * 40 + [82] * 300))
        self.assertGreater(lines.star, 85)
        self.assertEqual(lines.ovr_at(88), lines.star + 3)
        self.assertEqual(lines.ovr_at(78), lines.core - 2)

    def test_money_scales_on_the_cap(self):
        lines = lines_for(league([80] * 10))
        self.assertAlmostEqual(lines.money(15.0), 15.0 * 40.27 / 155.0, places=3)

    def test_no_cap_mode_money_is_unchanged(self):
        self.assertEqual(lines_for(league([80] * 10), no_cap=True).money(15.0), 15.0)

    def test_bands_are_ordered(self):
        lines = lines_for(league([95] * 30 + [88] * 40 + [82] * 100 + [70] * 200))
        self.assertGreaterEqual(lines.star, lines.core)
        self.assertGreaterEqual(lines.core, lines.starter)
        self.assertGreaterEqual(lines.starter, lines.rotation)
        self.assertGreaterEqual(lines.rotation, lines.bench)

    def test_band_of(self):
        lines = lines_for(league(list(range(95, 55, -1)) * 10))   # a spread-out league: all lines differ
        self.assertEqual(lines.band_of(lines.star), "star")
        self.assertEqual(lines.band_of(lines.core), "core")
        self.assertEqual(lines.band_of(lines.bench), "bench")
        self.assertEqual(lines.band_of(lines.bench - 1), "fringe")

    def test_high_contract_needs_salary_and_years(self):
        lines = lines_for(league([80] * 100))
        high = lines.salary_pcts[T.HIGH_SALARY_PCT]
        self.assertTrue(lines.is_high_contract(high, T.LONG_CONTRACT_YEARS))
        self.assertFalse(lines.is_high_contract(high, T.LONG_CONTRACT_YEARS - 1))
        self.assertFalse(lines.is_high_contract(high - 0.01, T.LONG_CONTRACT_YEARS))

    def test_empty_league_returns_floors_and_scale_1(self):
        lines = lines_for([])
        self.assertEqual((lines.star, lines.core, lines.pick_scale), (85, 80, 1.0))

    def test_pick_scale_is_clamped(self):
        lo, hi = T.PICK_SCALE_RANGE
        self.assertEqual(lines_for(league([80] * 10, tv=1.0)).pick_scale, lo)
        self.assertEqual(lines_for(league([80] * 10, tv=10000.0)).pick_scale, hi)
        self.assertAlmostEqual(lines_for(league([80] * 10)).pick_scale, 1.0)

    def test_era_lines_for_reads_the_tournament(self):
        team = make_team("A", ovrs=[70] * 13)
        torneo = make_torneo([team])
        torneo.salary_cap, torneo.luxury_tax_threshold = 40.27, 48.0
        torneo.min_salary, torneo.mle_value, torneo.cba_mode = 0.9, 3.2, "realistic"
        lines = era_lines_for(torneo)
        self.assertEqual(lines.year, torneo.anno_corrente)
        self.assertEqual(lines.cap, 40.27)
        self.assertFalse(lines.no_cap)


if __name__ == "__main__":
    unittest.main()
