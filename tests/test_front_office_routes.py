"""AI GM layer 1: front-office routes and the team-change hooks in server.py."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from core.front_office.state import user_team_name
from tests.test_front_office_view import league


def assert_one_gm_per_seat(test, torneo):
    fo = torneo.front_office
    seated = list(fo.seats.values())
    test.assertEqual(len(seated), len(set(seated)))
    for team, gm_id in fo.seats.items():
        test.assertEqual(fo.gms[gm_id].team, team)
    user = user_team_name(torneo)
    test.assertNotIn(user, fo.seats)
    test.assertEqual(len(fo.seats), 30 - (1 if user else 0))


class FrontOfficeRoutesTests(unittest.TestCase):
    def setUp(self):
        self._saved = server.SIMULATION_TOURNAMENT
        self._saved_name = server.ACTIVE_SAVE_NAME
        server.SIMULATION_TOURNAMENT = league()
        server.ACTIVE_SAVE_NAME = None
        self.client = server.app.test_client()

    def tearDown(self):
        server.SIMULATION_TOURNAMENT = self._saved
        server.ACTIVE_SAVE_NAME = self._saved_name

    def test_routes_return_payloads(self):
        table = self.client.get('/api/front_office/gms').get_json()
        self.assertEqual(len(table['rows']), 30)
        card = self.client.get('/api/front_office/gm?team=Boston%20Minutemen').get_json()
        self.assertEqual(card['gm']['name'], 'Chris Wallach')
        market = self.client.get('/api/front_office/market').get_json()
        self.assertEqual(market['year'], 2002)
        self.assertIn('glen_greenwood', {r['gm_id'] for r in market['unemployed']})

    def test_unknown_team_404(self):
        res = self.client.get('/api/front_office/gm?team=Nowhere%20Nomads')
        self.assertEqual(res.status_code, 404)
        self.assertIn('error', res.get_json())

    def test_no_league_500(self):
        server.SIMULATION_TOURNAMENT = None
        for url in ('/api/front_office/gms', '/api/front_office/gm?team=Boston%20Minutemen', '/api/front_office/market'):
            res = self.client.get(url)
            self.assertEqual(res.status_code, 500, url)
            self.assertEqual(res.get_json(), {'error': 'Simulation not initialized'})

    def test_switch_team_moves_gm(self):
        t = server.SIMULATION_TOURNAMENT
        boston_gm = t.front_office.seats['Boston Minutemen']

        def fake_switch(torneo, gm, target, offer):
            torneo.squadra_giocatore = next(s for s in torneo.squadre if s.nome == target)
            return {"success": True}

        with mock.patch.object(server, 'switch_user_franchise', fake_switch), \
                mock.patch.object(server, 'get_full_league_data_payload', lambda: {}):
            res = self.client.post('/api/board/switch_team', json={'target_team_name': 'Boston Minutemen'})
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(t.front_office.gms[boston_gm].team)
        self.assertIn('Toronto Northmen', t.front_office.seats)
        assert_one_gm_per_seat(self, t)

    def test_accept_job_offer_moves_gm(self):
        t = server.SIMULATION_TOURNAMENT
        t.user_gm_profile = SimpleNamespace(name='Alex Doe', teams_managed_history=[], contract=None,
                                            current_team_name='Toronto Northmen')
        with mock.patch.object(server, 'init_board_profile_for_team',
                               lambda team, force_reset=False: SimpleNamespace()), \
                mock.patch.object(server, 'generate_seasonal_objectives', lambda *a: None), \
                mock.patch.object(server, 'get_full_league_data_payload', lambda: {}):
            res = self.client.post('/api/board/accept_job_offer', json={'team_name': 'Utah Summit'})
        self.assertEqual(res.status_code, 200)
        self.assertNotIn('Utah Summit', t.front_office.seats)
        assert_one_gm_per_seat(self, t)

    def test_resign_leaves_no_empty_seat(self):
        t = server.SIMULATION_TOURNAMENT
        t.user_gm_profile = SimpleNamespace(name='Alex Doe', teams_managed_history=[])
        with mock.patch.object(server, 'generate_job_carousel_offers', lambda *a: []), \
                mock.patch.object(server, 'get_full_league_data_payload', lambda: {}):
            res = self.client.post('/api/board/resign')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Toronto Northmen', t.front_office.seats)
        assert_one_gm_per_seat(self, t)


if __name__ == "__main__":
    unittest.main()
