"""What the draft room receives: scouted prospects (never the true ratings), roles on every pick, CPU trades kept in the
offseason log, and the results once the draft is over."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from offseason.draft import Draft, completed_draft_payload


def prospect(name, ovr=71, pot=86, progress=8.0):
    ratings = SimpleNamespace(close_shot_rating=82, mid_range_shot_rating=66, three_point_shot_rating=61, passing_vision=67,
                              interior_defense_rating=76, perimeter_defense_rating=58, defensive_rebound_rating=77, speed=60)
    return SimpleNamespace(nome=name, ruolo="PF", eta=22, provenance="Kansas", pedigree="Polished big", valutazione=ovr,
                           potenziale=pot, scouting_progress=progress, abilita=ratings)


def draft(user="Raptors", log=None):
    torneo = SimpleNamespace(pick_ownership={1: {}}, scouting_fog_of_war=True, scout_staff=[],
                             offseason_log_data=log if log is not None else {})
    d = Draft.__new__(Draft)
    d.torneo = torneo
    d.squadre = []
    d.squadra_giocatore = SimpleNamespace(nome=user)
    d.ordine_originale = ["Nuggets", "Raptors"]
    d.scelte_totali = 4
    d.pick_corrente = 0
    d.risultati_draft = []
    d.draft_class = [prospect("Hidden Guy")]
    return d


class DraftStateTests(unittest.TestCase):
    def test_prospects_are_the_scouted_view(self):
        p = draft().get_draft_state()["prospects"][0]
        self.assertEqual(p["name"], "Hidden Guy")
        self.assertEqual(p["ovr_display"], "55 - 80")
        for hidden in ("ovr", "pot", "abilita", "tendenze"):
            self.assertNotIn(hidden, p)

    def test_cpu_trades_come_from_the_offseason_log(self):
        d = draft()
        d._ricorda_scambio({"team_on_clock": "Suns", "partner": "Kings", "pick_given": 7, "pick_received": 12,
                            "player_involved": "Vet", "player_ovr": 74})
        trades = d.get_draft_state()["trades"]
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["partner"], "Kings")
        self.assertEqual(trades[0]["pick_index"], 0)
        self.assertIs(d.torneo.offseason_log_data["draft_trades"], trades)

    def test_every_pick_records_the_role(self):
        d = draft()
        team = SimpleNamespace(nome="Raptors", roster=[])
        d.squadre = [team]
        p = prospect("Rookie")
        d._registra_scelta(p, 1, 2, "Raptors", "Raptors")
        self.assertEqual(d.risultati_draft[0]["ruolo"], "PF")


class CompletedDraftTests(unittest.TestCase):
    def test_results_and_trades_after_the_draft(self):
        log = {"draft": [{"scelta": "R1 P1", "squadra": "Nuggets", "nome": "A"}], "draft_trades": [{"partner": "Kings"}]}
        payload = completed_draft_payload(log, "Raptors")
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["history"][0]["nome"], "A")
        self.assertEqual(payload["trades"][0]["partner"], "Kings")
        self.assertEqual(payload["user_team"], "Raptors")

    def test_no_results_means_not_started(self):
        self.assertIsNone(completed_draft_payload({"draft": []}, "Raptors"))
        self.assertIsNone(completed_draft_payload(None, "Raptors"))


if __name__ == '__main__':
    unittest.main()
