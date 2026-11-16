"""TradeValidator behaviour that must not depend on the Flask server module."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import runtime_state
from core.models import Giocatore
from trades.trade_validator import TradeValidator


def make_player(name, salary=5.0, with_contract=True):
    p = Giocatore.__new__(Giocatore)
    p.nome = name
    p.eta = 25
    p.giorni_cooldown_scambio = 0
    p.contract = SimpleNamespace(salario_annuale=salary, anni_rimanenti=2) if with_contract else None
    return p


def make_team(name, n_players=13):
    team = SimpleNamespace(nome=name, roster=[], check_trade_salary_match=lambda inc, out: (True, "ok"))
    team.roster = [make_player(f"{name}-{i}") for i in range(n_players)]
    return team


class FakeDraft:
    """Minimal stand-in for offseason.draft.Draft: pick R1-X (index 2) is already made."""
    pick_corrente = 5

    def get_draft_state(self):
        return {"ordine": [{"round": 1, "original_owner": "X", "pick_index": 2}]}


class TradeValidatorTests(unittest.TestCase):
    def tearDown(self):
        runtime_state.register()  # back to "no server"

    def test_validate_trade_rejects_player_without_contract_gracefully(self):
        a, b = make_team("A"), make_team("B")
        ghost = make_player("Ghost", with_contract=False)
        ok, reason = TradeValidator.validate_trade(a, b, [ghost], [b.roster[0]])
        self.assertFalse(ok)
        self.assertIn("Ghost", reason)

    def test_three_team_trade_rejects_already_drafted_pick(self):
        runtime_state.register(active_draft=lambda: FakeDraft())
        a, b, c = make_team("A"), make_team("B"), make_team("C")
        data = {
            "team_a": {"gives_to_b": ["1:R1-X"]},
            "team_b": {"gives_to_c": [b.roster[0]]},
            "team_c": {"gives_to_a": [c.roster[0]]},
        }
        ok, reason, _ = TradeValidator.validate_3_team_trade(a, b, c, data, torneo=None)
        self.assertFalse(ok)
        self.assertIn("R1-X", reason)

    def test_stepien_uses_runtime_state_not_server_module(self):
        torneo = SimpleNamespace(pick_ownership={
            1: {"R1-A": "A"}, 3: {"R1-C": "A"}, 5: {"R1-E": "A"},
        })
        # Normal period: trading the year-1 R1 leaves years 1 and 2 empty -> Stepien violation.
        ok, _ = TradeValidator.check_stepien_rule(torneo, "A", ["1:R1-A"])
        self.assertFalse(ok)
        # During the draft year 1 is the pick being made, so it is exempt from the rule.
        runtime_state.register(league_state=lambda: "DRAFT_IN_PROGRESS")
        ok, _ = TradeValidator.check_stepien_rule(torneo, "A", ["1:R1-A"])
        self.assertTrue(ok)

    def test_roster_minimum_is_enforced_for_both_two_and_three_team_trades(self):
        a, b, c = make_team("A", 10), make_team("B"), make_team("C")
        ok, reason = TradeValidator.validate_trade(a, b, [a.roster[0]], [])
        self.assertFalse(ok)
        self.assertIn("too small", reason)
        data = {
            "team_a": {"gives_to_b": [a.roster[0]]},
            "team_b": {"gives_to_c": [b.roster[0]]},
            "team_c": {"gives_to_b": [c.roster[0]]},
        }
        ok, reason, _ = TradeValidator.validate_3_team_trade(a, b, c, data, torneo=None)
        self.assertFalse(ok)
        self.assertIn("too small", reason)


if __name__ == "__main__":
    unittest.main()
