"""GET /api/trade-requests: the league-wide list of players who asked to be traded."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from core.front_office import trade_requests as tr
from tests.trade_fixtures import make_player, make_team, make_torneo


def requester(name, ovr, since="Season 2003"):
    p = make_player(name, ovr=ovr, age=27, salary=12.0, years=3, role="SF")
    p.trade_request, p.trade_request_since = True, since
    return p


class TradeRequestsRouteTests(unittest.TestCase):
    def setUp(self):
        self._saved = server.SIMULATION_TOURNAMENT
        mine, other = make_team("Mine"), make_team("Other")
        mine.roster.append(requester("Mine Star", 86))
        other.roster += [requester("Big Star", 90, "Summer 2003"), make_player("Happy", ovr=88)]
        self.torneo = make_torneo([mine, other], user_team="Mine")
        self.client = server.app.test_client()

    def tearDown(self):
        server.SIMULATION_TOURNAMENT = self._saved

    def test_request_list_rows(self):
        rows = tr.request_list(self.torneo)
        self.assertEqual([r["player"] for r in rows], ["Big Star", "Mine Star"])   # best first
        self.assertEqual(rows[0], {"player": "Big Star", "team": "Other", "role": "SF", "ovr": 90, "age": 27,
                                   "salary": 12.0, "years": 3, "since": "Summer 2003", "is_user_team": False})
        self.assertTrue(rows[1]["is_user_team"])

    def test_route_returns_the_list(self):
        server.SIMULATION_TOURNAMENT = self.torneo
        data = self.client.get('/api/trade-requests').get_json()
        self.assertEqual([r["player"] for r in data["requests"]], ["Big Star", "Mine Star"])

    def test_route_without_a_league(self):
        server.SIMULATION_TOURNAMENT = None
        self.assertEqual(self.client.get('/api/trade-requests').get_json(), {"requests": []})


if __name__ == "__main__":
    unittest.main()
