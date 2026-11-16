"""Dashboard stat leaders: who qualifies, from the first games of the season on (not only past 40 games)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from main import stat_leader_pool


def player(name, gp):
    return SimpleNamespace(nome=name, season_stats=SimpleNamespace(partite_giocate=gp))


class StatLeaderPoolTests(unittest.TestCase):
    def test_early_season_players_qualify(self):
        pool = stat_leader_pool([player('A', 3), player('B', 2), player('C', 1), player('D', 0)])
        self.assertEqual([p.nome for p in pool], ['A', 'B'])  # at least half of the most games played (3)

    def test_share_comes_from_config(self):
        self.assertEqual(CONFIG.DASHBOARD.LEADERS_MIN_GP_SHARE, 0.5)
        pool = stat_leader_pool([player('A', 60), player('B', 30), player('C', 29)])
        self.assertEqual([p.nome for p in pool], ['A', 'B'])

    def test_no_games_no_leaders(self):
        self.assertEqual(stat_leader_pool([player('A', 0)]), [])
        self.assertEqual(stat_leader_pool([]), [])


if __name__ == '__main__':
    unittest.main()
