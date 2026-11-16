"""Player Database routes: careers file + live tournament -> the four views."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from tests.test_database_view import rec, star_games


def player(name, ovr=80, team=None):
    return SimpleNamespace(nome=name, ruolo='SG', eta=25, ovr=ovr, potenziale=85, squadra=team,
                           contract=SimpleNamespace(salario_annuale=12.5, anni_rimanenti=3))


class DatabaseRoutesTests(unittest.TestCase):
    def setUp(self):
        self._saved = server.SIMULATION_TOURNAMENT
        alpha = SimpleNamespace(nome='Alpha', conference='East', roster=[])
        alpha.roster = [player('Star', 90, alpha)]
        server.SIMULATION_TOURNAMENT = SimpleNamespace(
            box_scores=star_games(), squadra_giocatore=alpha, squadre=[alpha, SimpleNamespace(nome='B', roster=[])],
            free_agents_pool=[player('Free Guy', 70)], giocatori_ritirati=[player('Old Ret')],
            season_number=3, starting_year=2002)
        self.files = {'player_careers.json': {'star': [rec(1), rec(2, champion=True)],
                                              'old-guy': [rec(1, name='Old Guy', team='B')]},
                      'league_history.json': [{'stagione': 1, 'anno': 2002}, {'stagione': 2, 'anno': 2003}],
                      'retired_players_ids.json': ['old-guy']}
        patcher = mock.patch.object(server, '_read_historical_json', lambda name, default: self.files.get(name, default))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = server.app.test_client()

    def tearDown(self):
        server.SIMULATION_TOURNAMENT = self._saved

    def test_routes_return_payloads(self):
        d = self.client.get('/api/database/players?status=All&sort=name&desc=0').get_json()
        # 'Old Ret' is only in the retired list (no career, not live): nothing to show
        self.assertEqual([r['name'] for r in d['rows']], ['Free Guy', 'Old Guy', 'Star'])
        self.assertEqual(d['counts'], {'Active': 1, 'Free agent': 1, 'Retired': 1, 'Out of league': 0})
        star = self.client.get('/api/database/player/star').get_json()
        self.assertEqual((star['status'], star['salary'], star['years']), ('Active', 12.5, 3))
        self.assertEqual([ln['year'] for ln in star['rs']], [2002, 2003, 2004])
        self.assertTrue(star['current']['full'])
        old = self.client.get('/api/database/player/old-guy').get_json()
        self.assertEqual((old['status'], old['retired_year']), ('Retired', 2002))
        season = self.client.get('/api/database/season?season=2&kind=rs').get_json()
        self.assertEqual((season['year'], season['champion']), (2003, 'Alpha'))
        found = self.client.post('/api/database/finder', json={'team': '__user__', 'rank_by': 'pts_pg'}).get_json()
        self.assertEqual({r['line']['team'] for r in found['rows']}, {'Alpha'})
        presets = self.client.get('/api/database/presets').get_json()
        self.assertEqual(presets[0]['id'], 'best-22')

    def test_offseason_market_players_are_free_agents(self):
        """In the offseason the market lives in server.OFFSEASON_FA_POOL, not the tournament's pool."""
        with mock.patch.object(server, 'OFFSEASON_FA_POOL', [player('Market Guy', 75)]):
            d = self.client.get('/api/database/players?status=Free agent').get_json()
        self.assertEqual(sorted(r['name'] for r in d['rows']), ['Free Guy', 'Market Guy'])

    def test_shared_name_gets_no_full_line(self):
        t = server.SIMULATION_TOURNAMENT
        t.squadre[1].roster = [player('Star', 70, t.squadre[1])]
        star = self.client.get('/api/database/player/star').get_json()
        self.assertFalse(star['rs'][-1]['full'])

    def test_player_404(self):
        self.assertEqual(self.client.get('/api/database/player/nobody').status_code, 404)

    def test_offseason_season_not_counted_twice(self):
        self.files['player_careers.json']['star'].append(rec(3))
        star = self.client.get('/api/database/player/star').get_json()
        self.assertEqual([ln['year'] for ln in star['rs']], [2002, 2003, 2004])

    def test_empty_save(self):
        self.files = {}
        t = server.SIMULATION_TOURNAMENT
        t.box_scores, t.free_agents_pool, t.giocatori_ritirati, t.squadre = {}, [], [], []
        self.assertEqual(self.client.get('/api/database/players').get_json()['rows'], [])
        self.assertEqual(self.client.get('/api/database/season').get_json()['rows'], [])
        self.assertEqual(self.client.post('/api/database/finder', json={}).get_json()['rows'], [])

    def test_no_tournament(self):
        server.SIMULATION_TOURNAMENT = None
        self.assertEqual(self.client.get('/api/database/players').status_code, 500)


if __name__ == '__main__':
    unittest.main()
