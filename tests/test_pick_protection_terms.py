"""The protection the user names on a pick of a manual trade: who can set it, and what the trade routes do with it."""
import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest import mock

from trades.execution import can_set_pick_protection, settle_pick_terms, transfer_pick
from trades.trade_finder import TradeFinder
from tests.test_user_trades_wishes import NO_STARTING_C, UserToolsCase, valued


def torneo(**over):
    base = dict(fase_torneo="SEASON", draft_lottery_order=[],
                pick_ownership={1: {"R1-U": "U", "R2-U": "U", "R1-X": "U"}, 2: {"R1-U": "U", "R1-C": "C"}},
                pick_protections={1: {}, 2: {}})
    return SimpleNamespace(**(base | over))


class WhoCanSetAProtectionTests(unittest.TestCase):
    def test_a_team_can_protect_its_own_first(self):
        self.assertTrue(can_set_pick_protection(torneo(), "2:R1-U", "U"))

    def test_a_second_cannot_be_protected(self):
        self.assertFalse(can_set_pick_protection(torneo(), "1:R2-U", "U"))

    def test_a_first_from_another_team_cannot_be_protected_because_it_would_go_back_to_that_team(self):
        self.assertFalse(can_set_pick_protection(torneo(), "1:R1-X", "U"))

    def test_a_protected_pick_keeps_its_terms(self):
        self.assertFalse(can_set_pick_protection(torneo(pick_protections={1: {}, 2: {"R1-U": "Top 3"}}), "2:R1-U", "U"))

    def test_a_pick_of_this_draft_cannot_be_protected_once_the_lottery_is_drawn(self):
        drawn = torneo(fase_torneo="OFFSEASON", draft_lottery_order=["U", "C"])
        self.assertFalse(can_set_pick_protection(drawn, "1:R1-U", "U"))
        self.assertTrue(can_set_pick_protection(drawn, "2:R1-U", "U"))

    def test_last_years_lottery_order_does_not_count_during_the_season(self):
        self.assertTrue(can_set_pick_protection(torneo(draft_lottery_order=["U", "C"]), "1:R1-U", "U"))


class SettledTermsTests(unittest.TestCase):
    def settle(self, t, asset, requested):
        return settle_pick_terms(t, [("U", [asset], requested)])[asset]

    def test_the_named_protection_is_kept(self):
        self.assertEqual(self.settle(torneo(), "2:R1-U", {"2:R1-U": "Top 5"}), "Top 5")

    def test_an_unknown_protection_is_ignored(self):
        self.assertEqual(self.settle(torneo(), "2:R1-U", {"2:R1-U": "Top 29"}), "Unprotected")

    def test_a_protected_pick_keeps_its_terms_whatever_is_asked(self):
        t = torneo(pick_protections={1: {}, 2: {"R1-U": "Top 3"}})
        self.assertEqual(self.settle(t, "2:R1-U", {"2:R1-U": "Unprotected"}), "Top 3")
        self.assertEqual(self.settle(t, "2:R1-U", {}), "Top 3")

    def test_two_years_of_the_same_pick_keep_their_own_terms(self):
        t = torneo(pick_ownership={1: {"R1-U": "U"}, 2: {"R1-U": "U"}})
        terms = settle_pick_terms(t, [("U", ["1:R1-U", "2:R1-U"], {"1:R1-U": "Top 3", "2:R1-U": "Lottery"})])
        self.assertEqual(terms, {"1:R1-U": "Top 3", "2:R1-U": "Lottery"})

    def test_the_settled_protection_is_stored_with_the_pick(self):
        t = torneo()
        finder = SimpleNamespace(torneo=t, window="user")
        terms = settle_pick_terms(t, [("U", ["2:R1-U"], {"2:R1-U": "Top 5"})])
        transfer_pick(finder, "2:R1-U", SimpleNamespace(nome="U"), SimpleNamespace(nome="C"), terms)
        self.assertEqual((t.pick_ownership[2]["R1-U"], t.pick_protections[2]["R1-U"]), ("C", "Top 5"))


class RouteTermsTests(UserToolsCase):
    def call(self, t, url, body):
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        with mock.patch.object(server, "SIMULATION_TOURNAMENT", t), \
                mock.patch.object(server, "LEAGUE_STATE", "OFFSEASON_TRADES_START"), \
                mock.patch.object(server, "generate_trade_news"), \
                mock.patch.object(server, "update_approval_rating"), \
                mock.patch("trades.trade_validator.TradeValidator.validate_trade", return_value=(True, "ok")):
            return server.app.test_client().post(url, json=body)

    def deal(self):
        t, teams, _f = self.league({"C": NO_STARTING_C})
        center = self.user_center(teams)
        return t, teams, {"partner_team": "C", "giving_players": [center.nome], "giving_picks": ["2:R1-U"],
                          "receiving_players": [teams[1].roster[3].nome]}

    def test_an_executed_trade_carries_the_named_protection(self):
        t, _teams, body = self.deal()
        with mock.patch.object(TradeFinder, "execute_trade", return_value=True) as execute:
            resp = self.call(t, "/api/execute-user-trade", body | {"giving_pick_protections": {"2:R1-U": "Top 5"}})
        self.assertEqual(resp.status_code, 200, resp.get_json())
        self.assertEqual(execute.call_args.kwargs["pick_protections"], {"2:R1-U": "Top 5"})

    def test_an_offer_accepted_from_the_search_keeps_the_terms_of_a_protected_pick(self):
        t, _teams, body = self.deal()
        t.pick_protections[2]["R1-U"] = "Top 3"
        with mock.patch.object(TradeFinder, "execute_trade", return_value=True) as execute:
            self.call(t, "/api/execute-user-trade", body | {"giving_pick_protections": {}})
        self.assertEqual(execute.call_args.kwargs["pick_protections"], {"2:R1-U": "Top 3"})

    def test_the_cpu_judges_the_deal_with_the_named_protection(self):
        t, _teams, body = self.deal()
        with mock.patch.object(TradeFinder, "would_accept_trade_with_reason", return_value=(False, "no")) as judge:
            self.call(t, "/api/validate-user-trade", body | {"giving_pick_protections": {"2:R1-U": "Lottery"}})
        self.assertEqual(judge.call_args.kwargs["pick_protections"], {"2:R1-U": "Lottery"})

    def test_a_counter_never_asks_to_remove_terms_that_cannot_change(self):
        t, teams, _body = self.deal()
        t.pick_protections[2]["R1-U"] = "Top 3"
        f = TradeFinder(t, t.squadre, teams[0], manual=True)
        center = self.user_center(teams)
        wanted = valued(teams[1].roster[3], 500.0)
        counter = f.generate_counter_offer(teams[1], teams[0], [center, "2:R1-U"], [wanted], {"2:R1-U": "Top 3"})
        self.assertEqual(counter["modified_protections"], {})


if __name__ == "__main__":
    unittest.main()
