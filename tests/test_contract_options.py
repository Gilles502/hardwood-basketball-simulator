"""Contract options at the start of the offseason (Tournament._resolve_contract_options): the user's team-option
choice is honoured, and every resolved option is logged for the New season summary."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import Tournament


def player(name, team_option=False, player_option=False, po_decision="ACCEPT", to_decision="PICKUP"):
    contract = SimpleNamespace(anni_rimanenti=1, salario_annuale=10.0, team_option=team_option,
                               player_option=player_option)
    return SimpleNamespace(nome=name, ovr=75, eta=27, valutazione=75, contract=contract,
                           _calcola_valore_di_mercato=lambda: 9.0,
                           valuta_player_option=lambda squadra, torneo: (po_decision, "reason"),
                           valuta_team_option=lambda squadra, torneo: (to_decision, "reason"))


def tournament(user_roster, cpu_roster):
    user = SimpleNamespace(nome="Toronto Northmen", roster=user_roster)
    cpu = SimpleNamespace(nome="Boston Minutemen", roster=cpu_roster)
    return SimpleNamespace(squadre=[user, cpu], squadra_giocatore=user, offseason_log_data={})


class ContractOptionsTest(unittest.TestCase):
    def test_user_decline_is_honoured(self):
        p = player("Vaughn Kettering", team_option=True)
        t = tournament([p], [])
        Tournament._resolve_contract_options(t, {"Vaughn Kettering": "DECLINE"})
        self.assertEqual(p.contract.anni_rimanenti, 1)  # not extended: expires into free agency

    def test_user_pickup_is_honoured(self):
        p = player("Reuben Brisco", team_option=True)
        t = tournament([p], [])
        Tournament._resolve_contract_options(t, {"Reuben Brisco": "PICKUP"})
        self.assertEqual(p.contract.anni_rimanenti, 2)

    def test_options_are_logged(self):
        mine = player("Vaughn Kettering", team_option=True)
        theirs = player("Maceo Jessup", player_option=True, po_decision="DECLINE")
        t = tournament([mine], [theirs])
        Tournament._resolve_contract_options(t, {"Vaughn Kettering": "DECLINE"})
        self.assertEqual(t.offseason_log_data["options"], [
            {"name": "Vaughn Kettering", "team": "Toronto Northmen", "kind": "team", "decision": "out"},
            {"name": "Maceo Jessup", "team": "Boston Minutemen", "kind": "player", "decision": "out"}])


if __name__ == "__main__":
    unittest.main()
