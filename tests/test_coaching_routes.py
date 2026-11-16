"""Coaching page routes: fire, hire (also "fire & hire" in one step) and the salary floor on a new hire."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from core.models import Coach


def coach(name, off=80, deff=80, salary=4.0, years=2):
    return Coach(nome=name, stile_gioco="Balanced Offense", ovr_offensivo=off, ovr_difensivo=deff, eta=50,
                 potenziale=90, salario=salary, contratto_anni_rimanenti=years, contratto_totale_anni=years)


class CoachingRouteTests(unittest.TestCase):
    def setUp(self):
        self._saved = server.SIMULATION_TOURNAMENT
        self.current = coach("Old Coach", salary=4.0, years=2)
        self.candidate = coach("New Coach", off=84, deff=82, salary=5.0)  # ovr 81 -> asks 7.2, floor 5.4
        self.team = SimpleNamespace(nome="Alpha", coach=self.current, intesa=70, vittorie=10, sconfitte=5,
                                    roster=[SimpleNamespace(morale=80) for _ in range(3)])
        self.t = SimpleNamespace(squadra_giocatore=self.team, squadre=[self.team], season_number=2,
                                 unemployed_coaches=[self.candidate])
        server.SIMULATION_TOURNAMENT = self.t
        news = mock.patch('core.news_generator.add_news')
        news.start()
        self.addCleanup(news.stop)
        self.client = server.app.test_client()

    def tearDown(self):
        server.SIMULATION_TOURNAMENT = self._saved

    def hire(self, **body):
        return self.client.post('/api/coaching/hire', json=dict(coach_name="New Coach", years=3, **body))

    def test_hire_with_a_coach_on_the_bench_needs_replace_current(self):
        res = self.hire(salary=6.0)
        self.assertEqual(res.status_code, 400)
        self.assertIs(self.team.coach, self.current)

    def test_fire_and_hire_in_one_step(self):
        res = self.hire(salary=6.0, replace_current=True)
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertIs(self.team.coach, self.candidate)
        self.assertEqual(self.candidate.salario, 6.0)
        self.assertIn(self.current, self.t.unemployed_coaches)
        self.assertNotIn(self.candidate, self.t.unemployed_coaches)
        self.assertEqual(self.team.intesa, 70 - 8 + 5)
        self.assertIn("Old Coach was fired", res.get_json()["message"])

    def test_lowball_offer_is_refused_and_nobody_is_fired(self):
        res = self.hire(salary=1.0, replace_current=True)
        self.assertEqual(res.status_code, 400)
        self.assertIn("at least $5.4M", res.get_json()["error"])
        self.assertIs(self.team.coach, self.current)
        self.assertNotIn(self.current, self.t.unemployed_coaches)

    def test_unknown_candidate_does_not_fire_the_coach(self):
        res = self.client.post('/api/coaching/hire', json={"coach_name": "Nobody", "replace_current": True})
        self.assertEqual(res.status_code, 400)
        self.assertIs(self.team.coach, self.current)

    def test_fire_route_still_empties_the_bench(self):
        res = self.client.post('/api/coaching/fire')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(self.team.coach)
        self.assertIn(self.current, self.t.unemployed_coaches)
        self.assertEqual([p.morale for p in self.team.roster], [77, 77, 77])

    def test_state_carries_the_extension_ask_and_market_floor(self):
        self.t._generate_coach_candidate = lambda: coach("Filler")
        with mock.patch.object(Coach, 'calcola_roster_fit', return_value={"fit_score": 70, "rating": "Good"}):
            data = self.client.get('/api/coaching/state').get_json()
        self.assertEqual(data["current_coach"]["extension_ask"], server._coach_salary_ask(self.current))
        cand = next(c for c in data["unemployed_coaches"] if c["nome"] == "New Coach")
        self.assertEqual(cand["min_salary"], 5.4)
        self.assertEqual(cand["years_with_current_team"], 1)


class CoachProgressionOncePerOffseasonTests(unittest.TestCase):
    """The end of free agency already ages coaches and ticks their contracts; the roster cuts must not do it again."""

    def setUp(self):
        self._saved = (server.SIMULATION_TOURNAMENT, server.LEAGUE_STATE)
        self.t = mock.Mock(squadra_giocatore=None)
        server.SIMULATION_TOURNAMENT = self.t
        server.LEAGUE_STATE = "OFFSEASON_CUTDOWN_START"
        payload = mock.patch.object(server, 'get_lean_league_data_payload', return_value={})
        payload.start()
        self.addCleanup(payload.stop)

    def tearDown(self):
        server.SIMULATION_TOURNAMENT, server.LEAGUE_STATE = self._saved

    def test_roster_cuts_do_not_run_coach_progression(self):
        res = server.app.test_client().post('/api/run_roster_cuts', json={})
        self.assertEqual(res.status_code, 200)
        self.t._gestisci_fase_tagli_roster.assert_called_once()
        self.t._gestisci_progressione_coach.assert_not_called()
        self.assertEqual(server.LEAGUE_STATE, "OFFSEASON_COMPLETE")


if __name__ == '__main__':
    unittest.main()
