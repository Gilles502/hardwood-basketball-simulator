"""Variable potential: a young player's ceiling moves each offseason (CONFIG.PROGRESSION POT_*)."""
import random
import unittest
from unittest import mock

from core.config import CONFIG
from tests.trade_fixtures import make_player


class VariablePotentialTests(unittest.TestCase):
    def test_a_veteran_ceiling_does_not_move(self):
        p = make_player("Vet", ovr=80, age=CONFIG.PROGRESSION.POT_DRIFT_MAX_AGE + 1, pot=85)
        self.assertEqual(p._evolvi_potenziale(5.0, 30.0), 0)
        self.assertEqual(p.potenziale, 85)

    def test_a_breakout_raises_the_ceiling(self):
        p = make_player("Kid", ovr=70, age=20, pot=78)
        with mock.patch("core.models.random.random", return_value=0.0):
            change = p._evolvi_potenziale(0.0, 30.0)
        lo, hi = CONFIG.PROGRESSION.POT_BREAKOUT_RANGE
        self.assertTrue(lo <= change <= hi)

    def test_a_setback_never_drops_under_the_rating(self):
        p = make_player("Kid", ovr=74, age=21, pot=75)
        cfg = CONFIG.PROGRESSION
        with mock.patch("core.models.random.random", return_value=cfg.POT_BREAKOUT_CHANCE + 0.001):
            p._evolvi_potenziale(0.0, 10.0)
        self.assertEqual(p.potenziale, 74)

    def test_the_drift_is_about_neutral(self):
        random.seed(3)
        total = 0
        for i in range(4000):
            p = make_player(f"K{i}", ovr=65, age=20, pot=80)
            total += p._evolvi_potenziale(0.0, 20.0)
        self.assertLess(abs(total / 4000), 0.6)


if __name__ == "__main__":
    unittest.main()
