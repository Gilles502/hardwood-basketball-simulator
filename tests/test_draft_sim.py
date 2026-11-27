"""The draft's "Sim to my pick" / "Sim to end": CPU picks run on to the user's turn or the last pick, through CPU trades."""
import unittest
from types import SimpleNamespace
from unittest import mock

from offseason.draft import Draft

TRADE = {"team_on_clock": "Nuggets", "partner": "Kings", "player_involved": "x", "player_ovr": 0,
         "pick_given": 1, "pick_received": 5, "description": "d"}


def make_draft(user="Raptors", order=("Nuggets", "Raptors", "Kings"), rounds=2):
    order = list(order)
    torneo = SimpleNamespace(pick_ownership={1: {}}, offseason_log_data={}, draft_pick_corrente=0)
    d = Draft.__new__(Draft)
    d.torneo, d.squadre = torneo, [SimpleNamespace(nome=n) for n in order]
    d.squadra_giocatore = SimpleNamespace(nome=user)
    d.ordine_originale, d.scelte_totali, d.pick_corrente = order, len(order) * rounds, 0
    d.risultati_draft, d.draft_class = [], []
    return d


class SimToUserTests(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch("offseason.draft.scouted_prospects", return_value=[]),
                      mock.patch("trades.trade_finder.TradeFinder"),
                      mock.patch("trades.engines.draft_night.run_on_the_clock", return_value=TRADE),
                      mock.patch.object(Draft, "_esegui_scelta_IA")):
            patch.start()
            self.addCleanup(patch.stop)

    def test_a_cpu_trade_does_not_stop_the_sim_before_the_user_pick(self):
        d = make_draft()
        state = d.simula_fino_utente()
        self.assertEqual(d.pick_corrente, 1)
        self.assertTrue(state["is_user_turn"])

    def test_with_no_picks_left_the_sim_runs_to_the_end(self):
        d = make_draft(user="Lakers")
        state = d.simula_fino_utente()
        self.assertEqual(d.pick_corrente, 6)
        self.assertEqual(state["status"], "COMPLETED")
        self.assertEqual(len(state["trades"]), 3)  # first-round trades stay on the draft wire


if __name__ == "__main__":
    unittest.main()
