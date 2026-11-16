"""League Analytics routes: the four views served from the tournament's saved box scores."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from tests.test_analytics_view import game, line, scores


class AnalyticsRoutesTests(unittest.TestCase):
    def setUp(self):
        self._saved = server.SIMULATION_TOURNAMENT
        bs = scores(game('g1', 1, '2027-10-23', 'Alpha', 'Beta', [line('Star', pts=30, fga=20, fgm=12)],
                         [line('Rival', pts=20, fga=18, fgm=8)]))
        roster = [SimpleNamespace(nome='Star')]
        server.SIMULATION_TOURNAMENT = SimpleNamespace(
            box_scores=bs, squadra_giocatore=None,
            squadre=[SimpleNamespace(nome='Alpha', conference='East', roster=roster),
                     SimpleNamespace(nome='Beta', conference='West', roster=[])])
        self.client = server.app.test_client()

    def tearDown(self):
        server.SIMULATION_TOURNAMENT = self._saved

    def test_views_return_their_payloads(self):
        players = self.client.get('/api/analytics/players').get_json()
        self.assertEqual({p['name']: p['in_league'] for p in players['players']}, {'Star': True, 'Rival': False})
        teams = self.client.get('/api/analytics/teams').get_json()
        self.assertEqual({t['name']: t['conference'] for t in teams['teams']}, {'Alpha': 'East', 'Beta': 'West'})
        league = self.client.get('/api/analytics/league').get_json()
        self.assertIn('baseline', league)
        splits = self.client.get('/api/analytics/splits?player=Star').get_json()
        self.assertEqual(splits['kind'], 'player')
        team = self.client.get('/api/analytics/splits?team=Alpha').get_json()
        self.assertEqual(team['kind'], 'team')

    def test_players_and_teams_have_a_playoff_view(self):
        po = game('PO-QF-Beta@Alpha-G1', 0, '', 'Alpha', 'Beta', [line('Star', pts=40, fga=25, fgm=16)],
                  [line('Rival', pts=10, fga=12, fgm=4)])
        server.SIMULATION_TOURNAMENT.playoff_bracket_data = {
            'east': {'qf': [{'games': [{'game_num': 1, 'result_sheet': po}]}]}, 'west': {}, 'finals': []}
        players = self.client.get('/api/analytics/players?kind=po').get_json()
        self.assertEqual({p['name']: p['s']['pts_pg'] for p in players['players']}, {'Star': 40.0, 'Rival': 10.0})
        self.assertEqual(players['meta']['kind'], 'po')
        teams = self.client.get('/api/analytics/teams?kind=po').get_json()
        self.assertEqual({t['name']: t['gp'] for t in teams['teams']}, {'Alpha': 1, 'Beta': 1})
        regular = self.client.get('/api/analytics/players').get_json()
        self.assertEqual({p['name']: p['s']['pts_pg'] for p in regular['players']}, {'Star': 30.0, 'Rival': 20.0})
        self.assertEqual(regular['meta']['kind'], 'rs')

    def test_playoff_view_without_playoffs_is_empty(self):
        players = self.client.get('/api/analytics/players?kind=po').get_json()
        self.assertEqual((players['meta']['games'], players['players']), (0, []))

    def test_splits_errors(self):
        self.assertEqual(self.client.get('/api/analytics/splits').status_code, 400)
        self.assertEqual(self.client.get('/api/analytics/splits?player=Nobody').status_code, 404)

    def test_old_routes_are_gone(self):
        for path in ('/api/analytics/full', '/api/analytics/leaders', '/api/analytics/legacy_summary'):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_trade_history_still_grades_trades(self):
        """Trade Center's history reused the old analytics route; it must keep working without it."""
        def team(name, w, l):
            return {"team_name": name, "wins_pre": w, "losses_pre": l, "win_pct_pre": round(w / (w + l), 3),
                    "ppg_pre": 100.0, "opp_ppg_pre": 100.0, "off_rtg_pre": 105.0, "def_rtg_pre": 105.0,
                    "net_rtg_pre": 0.0, "players_sent": [{"name": "Star", "ovr": 80, "ruolo": "PG", "eta": 27,
                                                          "salary": 10.0, "trade_value": 70.0}],
                    "picks_sent": [], "players_received": [], "picks_received": []}
        t = server.SIMULATION_TOURNAMENT
        for s, (w, l) in zip(t.squadre, [(30, 20), (20, 30)]):
            s.vittorie, s.sconfitte, s.punti_fatti_stagione, s.punti_subiti_stagione = w, l, 5000, 5000
        t.season_number = 26
        t.trade_analytics_history = [{"id": "trade_1", "season": 26, "game_day": 10, "type": "2-Team", "reason": "test",
                                      "teams": [team('Alpha', 30, 20), team('Beta', 20, 30)],
                                      "date_recorded": "2027-12-01 10:00:00"}]
        data = self.client.get('/api/trade-history').get_json()
        self.assertNotIn('error', data)
        self.assertEqual(data['current_season'], 26)
        graded = next(tr for tr in data['trades'] if tr['id'] == 'trade_1')   # file-logged trades are merged in too
        self.assertEqual(len(graded['teams']), 2)

    def _record(self, tid, season=26, **extra):
        def team(name, w, l):
            return {"team_name": name, "wins_pre": w, "losses_pre": l, "win_pct_pre": round(w / (w + l), 3),
                    "ppg_pre": 100.0, "opp_ppg_pre": 100.0, "off_rtg_pre": 105.0, "def_rtg_pre": 105.0,
                    "net_rtg_pre": 0.0, "players_sent": [{"name": "Star" + tid, "ovr": 80, "ruolo": "PG", "eta": 27,
                                                          "salary": 10.0, "trade_value": 70.0}],
                    "picks_sent": [], "players_received": [], "picks_received": []}
        rec = {"id": tid, "season": season, "game_day": 10, "type": "2-Team", "reason": "test",
               "teams": [team('Alpha', 30, 20), team('Beta', 20, 30)], "date_recorded": "2027-12-01 10:00:00"}
        rec.update(extra)
        return rec

    def _history(self, records):
        t = server.SIMULATION_TOURNAMENT
        for s, (w, l) in zip(t.squadre, [(30, 20), (20, 30)]):
            s.vittorie, s.sconfitte, s.punti_fatti_stagione, s.punti_subiti_stagione = w, l, 5000, 5000
        t.season_number = 26
        t.trade_analytics_history = records
        data = self.client.get('/api/trade-history').get_json()
        self.assertNotIn('error', data)
        return {tr['id']: tr for tr in data['trades']}

    def test_trade_history_passes_public_motives(self):
        side = {"team": "Alpha", "gm_name": "Jeff Petrov", "trade_skill": 78, "plan": "CONTENDER",
                "traits": ["TRADE_HAPPY"], "wish_kind": "NEED_STARTER", "need": "PF",
                "reasons": ["The starting PF spot is a hole."], "value_given": 88.0, "value_received": 112.0}
        by_id = self._history([self._record("m1", trade_type="deal", why="Alpha needed a starting PF", phase="REGULAR",
                                            team_count=2, motives=[side, dict(side, team="Beta", plan="USER")])])
        tr = by_id["m1"]
        self.assertEqual((tr["why"], tr["trade_type"], tr["phase"]), ("Alpha needed a starting PF", "deal", "REGULAR"))
        self.assertEqual([m["team"] for m in tr["motives"]], ["Alpha", "Beta"])
        self.assertEqual(tr["motives"][0]["gm_name"], "Jeff Petrov")
        for m in tr["motives"]:
            self.assertNotIn("value_given", m)
            self.assertNotIn("value_received", m)

    def test_trade_history_old_record_is_unchanged(self):
        by_id = self._history([self._record("old1"), self._record("old2", trade_type="legacy", why="", motives=[])])
        for tid in ("old1", "old2"):
            for key in ("why", "trade_type", "phase", "motives"):
                self.assertNotIn(key, by_id[tid])

    def test_trade_history_includes_offseason_records(self):
        side = {"team": "Alpha", "plan": "REBUILD", "reasons": []}
        by_id = self._history([self._record("off1", phase="OFFSEASON", why="Alpha cut salary", trade_type="tax_dump",
                                            motives=[side])])
        self.assertEqual(by_id["off1"]["phase"], "OFFSEASON")
        self.assertEqual(by_id["off1"]["motives"][0]["team"], "Alpha")

    def test_no_simulation(self):
        server.SIMULATION_TOURNAMENT = None
        self.assertEqual(self.client.get('/api/analytics/players').status_code, 500)


if __name__ == '__main__':
    unittest.main()
