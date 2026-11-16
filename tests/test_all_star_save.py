"""The All-Star weekend is saved by name and must come back after a load; the season history keeps the whole snapshot."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.save_manager import restore_all_star
from main import _all_star_premi


def tournament(*names, fa=()):
    roster = [SimpleNamespace(nome=n) for n in names]
    return SimpleNamespace(squadre=[SimpleNamespace(roster=roster)],
                           free_agents_pool=[SimpleNamespace(nome=n) for n in fa])


SNAPSHOT = {'host': 'Toronto', 'game': {'east_score': 150, 'west_score': 148}, 'mvp': 'A'}


class RestoreAllStarTests(unittest.TestCase):
    def test_round_trip(self):
        t = tournament('A', 'B', 'C', fa=['Free'])
        restore_all_star(t, {
            'weekend': SNAPSHOT, 'all_star_weekend_complete': True,
            'last_season_rookies': ['B'], 'hosts': ['Toronto'],
            'all_star_starters': {'east': ['A', 'Gone'], 'west': ['Free']},
            'all_star_reserves': {'east': ['C'], 'west': []},
            'all_star_rosters': {'east': ['A', 'C'], 'west': ['Free']},
            'all_star_mvp': 'A',
            'all_star_game_log': SNAPSHOT['game'],
            'three_point_contest': {'participants': ['A', 'Gone'], 'results': [], 'winner': 'A'},
        })
        self.assertEqual(t.all_star_weekend, SNAPSHOT)
        self.assertTrue(t.all_star_weekend_complete)
        self.assertEqual(t.all_star_starters['east'], [t.squadre[0].roster[0]])
        self.assertIs(t.all_star_starters['west'][0], t.free_agents_pool[0])
        self.assertEqual(t.all_star_reserves['east'], [t.squadre[0].roster[2]])
        self.assertEqual(len(t.all_star_rosters['east']), 2)
        self.assertEqual(t.all_star_mvp, 'A')
        self.assertEqual(t.all_star_game_log, SNAPSHOT['game'])
        self.assertEqual(t.three_point_contest['participants'], [t.squadre[0].roster[0]])
        self.assertEqual(t.three_point_contest['winner'], 'A')
        self.assertEqual(t.last_season_rookies, ['B'])
        self.assertEqual(t.all_star_hosts, ['Toronto'])

    def test_old_save_without_new_keys(self):
        t = tournament('A')
        old_log = {'east_score': 140, 'west_score': 139, 'east_stats': [{'nome': 'A', 'punti': 30}]}
        restore_all_star(t, {'all_star_starters': {'east': ['A'], 'west': []},
                             'all_star_game_log': old_log, 'all_star_mvp': 'A',
                             'all_star_weekend_complete': True})
        self.assertIsNone(t.all_star_weekend)
        self.assertTrue(t.all_star_weekend_complete)
        self.assertEqual(t.all_star_game_log, old_log)
        self.assertEqual(t.all_star_hosts, [])
        self.assertEqual(t.last_season_rookies, [])

    def test_missing_state(self):
        for state in (None, {}):
            t = tournament('A')
            restore_all_star(t, state)
            self.assertIsNone(t.all_star_weekend)
            self.assertFalse(t.all_star_weekend_complete)
            self.assertEqual(t.all_star_starters, {'east': [], 'west': []})
            self.assertIsNone(t.all_star_mvp)


class HistoryTests(unittest.TestCase):
    def test_history_entry_carries_weekend(self):
        p = SimpleNamespace(nome='A')
        t = SimpleNamespace(all_star_starters={'east': [p], 'west': []}, all_star_reserves={'east': [], 'west': []},
                            all_star_mvp='A', three_point_contest={'winner': 'A'}, dunk_contest={'winner': 'B'},
                            all_star_weekend=SNAPSHOT)
        premi = _all_star_premi(t)
        self.assertEqual(premi['all_star_weekend'], SNAPSHOT)
        self.assertEqual(premi['all_star_starters']['east'], ['A'])
        self.assertEqual(premi['all_star_mvp'], 'A')
        self.assertEqual(premi['three_point_contest'], 'A')
        self.assertEqual(premi['dunk_contest'], 'B')

    def test_history_without_weekend(self):
        premi = _all_star_premi(SimpleNamespace())
        self.assertIsNone(premi['all_star_weekend'])
        self.assertEqual(premi['all_star_mvp'], 'N/A')


if __name__ == "__main__":
    unittest.main()
