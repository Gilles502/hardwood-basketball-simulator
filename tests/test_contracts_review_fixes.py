"""Final review fixes (layer 2b): a traded walker starts fresh, an old team does not chase its own walker, a contender's
star renewal never goes over the max contract."""
import unittest
from types import SimpleNamespace
from unittest import mock

from core.front_office import contracts
from offseason.contract_extensions import ContractExtensions
from tests.test_free_agency_bidding import cpu_offer, market, teams
from tests.test_wishes import ctx_of, roster_with, team_of
from tests.trade_fixtures import make_player
from trades.execution import _move_player


class TradedWalkerTests(unittest.TestCase):
    def test_a_traded_walker_starts_fresh_with_his_new_team(self):
        p = make_player("Walker", ovr=90, age=29, years=1)
        p.walks_away, p.is_flight_risk = "hopeless team", True
        src, dst = SimpleNamespace(roster=[p]), SimpleNamespace(roster=[])
        _move_player(p, src, dst)
        self.assertEqual(p.walks_away, "")
        self.assertFalse(p.is_flight_risk)


class OldTeamWalkerTests(unittest.TestCase):
    def setUp(self):
        self.sixers, self.knicks = teams("Sixers", "Knicks")
        self.fa = market([self.sixers, self.knicks])
        self.fa.squadre_precedenti = {"Hale": self.sixers}
        self.fa.is_rfa = lambda p: False
        self.fa.player.walks_away = "hopeless team"

    def test_the_old_team_is_refused_by_its_walker(self):
        self.assertTrue(self.fa._refused_by(self.sixers, self.fa.player))
        self.assertFalse(self.fa._refused_by(self.knicks, self.fa.player))
        self.fa.is_rfa = lambda p: True
        self.assertFalse(self.fa._refused_by(self.sixers, self.fa.player))   # an RFA cannot walk

    def test_a_refused_old_team_does_not_raise(self):
        self.fa.ai_offers["Hale"] = [cpu_offer("Sixers", 12.0), cpu_offer("Knicks", 13.0)]
        self.fa._raise_or_withdraw(3)
        self.assertEqual(self.fa.ai_offers["Hale"][0]["salary"], 12.0)
        self.assertEqual(self.fa.night_moves, [])


class MaxContractTests(unittest.TestCase):
    def test_a_contender_star_renewal_stays_under_the_max(self):
        p = make_player("Star", ovr=95, age=28, years=1, role="SF", team_years=5)
        p.morale, p.is_flight_risk, p.walks_away = 70, False, ""
        team = team_of(roster_with(p), name="T", payroll=30.0)
        team.personalita_proprietario, team.vittorie = "Normale", 40
        torneo = SimpleNamespace(squadra_giocatore=None, squadre=[team], season_number=1, salary_cap=40.0,
                                 anno_corrente=2003, second_apron=70.0, luxury_tax_threshold=55.0, first_apron=60.0)
        e = ContractExtensions(torneo, [team])
        max_contract = e._max_contract()
        e.compute_player_market_request = lambda pl, option_type="None": max_contract   # already at the max
        with mock.patch.object(contracts, "context_for", lambda t, s: ctx_of("CONTENDER")), \
                mock.patch.object(ContractExtensions, "calculate_extension_score", return_value=(100.0, "ok")), \
                mock.patch("offseason.contract_extensions.add_news"), \
                mock.patch("offseason.contract_extensions.random.random", return_value=0.9):
            self.assertTrue(e._attempt_extension(team, p))
        self.assertLessEqual(p.contract.salario_annuale, max_contract)


if __name__ == "__main__":
    unittest.main()
