"""Era evolution: the Play-In start year rule and the pace / three-point curves read from CONFIG.ERA."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from main import Tournament

ERA = CONFIG.ERA


def league(year, settings=None, starting_year=2002):
    """A bare Tournament: only the fields the era helpers read (no database, no calendar)."""
    t = Tournament.__new__(Tournament)
    t.league_settings = settings if settings is not None else {}
    t.anno_corrente = year
    t.starting_year = starting_year
    t._era_pace_drift = 0.0
    t._era_3pt_drift = 0.0
    return t


class PlayInStartYear(unittest.TestCase):
    def resolved(self, year, settings):
        t = league(year, settings)
        t.resolve_play_in()
        return t.enable_play_in

    def test_start_year_turns_it_on_from_that_season(self):
        self.assertFalse(self.resolved(2009, {"play_in_start_year": 2010}))
        self.assertTrue(self.resolved(2010, {"play_in_start_year": 2010}))
        self.assertTrue(self.resolved(2030, {"play_in_start_year": 2010}))

    def test_start_year_none_means_never(self):
        self.assertFalse(self.resolved(2040, {"play_in_start_year": None}))

    def test_start_year_wins_over_a_legacy_flag(self):
        self.assertTrue(self.resolved(2021, {"play_in_start_year": 2020, "enable_play_in": False}))

    def test_legacy_flag_forces_it_both_ways(self):
        # Saves made before the start-year setting keep exactly what they had.
        self.assertFalse(self.resolved(2028, {"enable_play_in": False}))
        self.assertTrue(self.resolved(2002, {"enable_play_in": True}))

    def test_no_setting_uses_the_historical_default(self):
        default = ERA.PLAY_IN_DEFAULT_START_YEAR
        self.assertFalse(self.resolved(default - 1, {}))
        self.assertTrue(self.resolved(default, {}))


class EraCurves(unittest.TestCase):
    def test_pace_rises_from_2002_to_today(self):
        pace = [league(y).get_era_pace_factor() for y in (2002, 2010, 2016, 2020, 2025)]
        self.assertEqual(pace, sorted(pace))
        self.assertAlmostEqual(pace[0], 0.912, places=3)
        self.assertAlmostEqual(pace[-1], 1.024, places=3)

    def test_three_point_volume_reaches_modern_levels_in_a_2002_league(self):
        mult = {y: league(y).get_era_3pt_multiplier() for y in (2002, 2010, 2020, 2025)}
        self.assertLess(mult[2002], 0.9)
        self.assertGreater(mult[2020], 1.6)
        self.assertGreater(mult[2025], mult[2020])

    def test_modern_start_keeps_the_gentler_curve(self):
        modern = league(2025, starting_year=2025).get_era_3pt_multiplier()
        self.assertAlmostEqual(modern, 1.375, places=2)
        self.assertLess(modern, league(2025).get_era_3pt_multiplier())

    def test_curves_are_clamped(self):
        lo, hi = ERA.THREE_CLAMP
        self.assertLessEqual(league(2200).get_era_3pt_multiplier(), hi)
        self.assertGreaterEqual(league(1950).get_era_3pt_multiplier(), lo)


if __name__ == "__main__":
    unittest.main()
