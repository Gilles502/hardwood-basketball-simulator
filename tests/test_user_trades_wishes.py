"""The user's trade tools follow the same wishes as the CPU engines, and say why the CPU side would do the deal."""
import unittest
from unittest import mock

from trades.motive import TradeMotive
from trades.trade_block_manager import TradeBlockManager
from trades.trade_finder import TradeFinder
from tests.test_trade_execution import ExecutionTestCase
from tests.trade_fixtures import era_of, finder, make_gm, make_player, make_team, make_torneo, roster_team

ERA = era_of()

# A balanced roster without a starting C (best C 72 < starter line 75): a CONTENDER wants NEED_STARTER C.
NO_STARTING_C = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 76), ("PF", 71),
                 ("C", 72), ("C", 71), ("SG", 68), ("SF", 68), ("PF", 67)]
# Full of starters, depth and bench: no wish a single player can fulfil.
SATISFIED = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 76), ("PF", 71),
             ("C", 76), ("C", 71), ("SG", 68), ("SF", 68), ("PF", 67)]
# The user's roster: a surplus 77 C to offer and a 72 wing nobody has a use for.
USER_ROSTER = SATISFIED + [("C", 77)]


PICK_VALUE = {}   # pick key -> what the patched valuation says (picks are worth 10 otherwise)


def valued(player, value):
    player._test_value = value
    return player


class UserToolsCase(unittest.TestCase):
    def setUp(self):
        PICK_VALUE.clear()
        patches = [mock.patch.object(TradeFinder, "get_strategic_value",
                                     lambda self, a, tm, pp=None: PICK_VALUE.get(a, 10.0) if isinstance(a, str)
                                     else getattr(a, "_test_value", 10.0)),
                   mock.patch("trades.trade_finder.random.uniform", return_value=0.0),
                   mock.patch.object(TradeFinder, "era", return_value=ERA)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def league(self, cpu_specs, user_spec=USER_ROSTER, plans=None, gms=None):
        """The user team "U" and CPU teams {name: roster spec}; every team owns its own picks."""
        teams = [roster_team("U", user_spec)] + [roster_team(n, spec) for n, spec in cpu_specs.items()]
        t = make_torneo(teams, user_team="U", plans={n: "CONTENDER" for n in cpu_specs} | (plans or {}), gms=gms)
        t.pick_ownership = {y: {f"R{r}-{x.nome}": x.nome for x in teams for r in (1, 2)} for y in range(1, 6)}
        t.pick_protections = {y: {} for y in range(1, 6)}
        t.draft_lottery_order = [x.nome for x in teams]
        for x in teams:
            for p in x.roster:
                p.squadra = x
        return t, teams, finder(t)

    def user_center(self, teams):
        c = next(p for p in teams[0].roster if p.ruolo == "C" and p.ovr == 77)
        return valued(c, 100.0)


class PackageSearchTests(UserToolsCase):
    def test_a_package_no_cpu_team_wants_finds_no_partner(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        wing = valued(next(p for p in teams[0].roster if p.ruolo == "SF" and p.ovr == 71), 100.0)
        # price is not the reason: the package is worth far more than anything C could send
        self.assertEqual(f.plan_check(teams[1], [wing], [teams[1].roster[0]])[0], False)
        self.assertEqual(f.find_trades_for_package([wing], []), [])

    def test_a_team_with_the_matching_wish_answers_with_a_why(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        results = f.find_trades_for_package([self.user_center(teams)], [])
        self.assertTrue(results)
        self.assertEqual({r["partner_team"] for r in results}, {"C"})
        self.assertEqual({r["why"] for r in results}, {"C needed a starting C"})

    def test_player_search_carries_the_why(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        results = f.find_trades_for_player(self.user_center(teams))
        self.assertTrue(results)
        self.assertTrue(all(r["why"] == "C needed a starting C" for r in results))

    def test_player_search_drops_a_team_that_would_refuse(self):
        t, teams, f = self.league({"C": NO_STARTING_C, "S": SATISFIED})
        results = f.find_trades_for_player(self.user_center(teams))
        self.assertEqual({r["partner_team"] for r in results}, {"C"})

    def test_pick_search_goes_to_a_team_that_wants_picks(self):
        t, teams, f = self.league({"R": SATISFIED, "C": NO_STARTING_C}, plans={"R": "REBUILDER"})
        self.assertIn("WANT_PICKS", [w.kind for w in f.wishes_for(teams[1])])
        results = f.find_trades_for_pick("1:R1-U")
        self.assertTrue(results)
        self.assertEqual({r["partner_team"] for r in results}, {"R"})
        self.assertTrue(all(r["why"] for r in results))

    def test_target_search_asks_the_owner_with_a_wish(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        self.user_center(teams)
        target = teams[1].roster[3]
        results = f.find_trades_for_target_player(target)
        self.assertTrue(results)
        self.assertTrue(all(r["why"] == "C needed a starting C" for r in results))

    def test_target_search_returns_nothing_for_a_team_without_a_wish(self):
        t, teams, f = self.league({"S": SATISFIED})
        self.user_center(teams)
        self.assertEqual(f.find_trades_for_target_player(teams[1].roster[3]), [])


class MultiTeamSearchTests(UserToolsCase):
    # B (NO_STARTING_C) lacks a starting C and owns a PG 76; D lacks a starting PG and owns two SF 76.
    d_spec = [("PG", 72), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 76), ("PF", 76), ("PF", 71),
              ("C", 76), ("C", 71), ("SG", 68), ("SF", 68), ("PF", 67)]

    def three(self, d_spec):
        t, teams, f = self.league({"B": NO_STARTING_C, "D": d_spec})
        center = self.user_center(teams)
        b = teams[1]
        valued(next(p for p in b.roster if p.ruolo == "PG" and p.ovr == 76), 100.0)
        for p in teams[2].roster:
            valued(p, 100.0)
        return f, center

    def test_three_team_deal_needs_a_wish_on_every_cpu_team(self):
        f, center = self.three(self.d_spec)
        results = f.find_3_team_trades_for_package([center], [], target_position="SF")
        self.assertTrue(results)
        self.assertTrue(all("needed a starting" in r["why"] for r in results))
        self.assertTrue(all(r["why"].count("needed") == 2 for r in results))

    def test_three_team_deal_without_a_wish_for_the_third_team_is_dropped(self):
        f, center = self.three(SATISFIED)
        self.assertEqual(f.find_3_team_trades_for_package([center], [], target_position="SF"), [])

    def test_chain_needs_every_cpu_team_to_have_a_wish(self):
        t, teams, f = self.league({"B": NO_STARTING_C, "D": SATISFIED, "E": SATISFIED})
        center = self.user_center(teams)
        self.assertEqual(f.find_multi_team_chain_trades([center], []), [])


class TradeBlockTests(UserToolsCase):
    def test_offers_come_only_from_teams_with_a_matching_wish(self):
        t, teams, f = self.league({"C": NO_STARTING_C, "S": SATISFIED})
        self.user_center(teams).on_trade_block = True
        offers = TradeBlockManager.generate_offers(t, teams[0])
        self.assertTrue(offers)
        self.assertEqual({o["offering_team"] for o in offers}, {"C"})
        self.assertTrue(all(o["why"] == "C needed a starting C" for o in offers))

    def test_the_single_simulated_offer_has_a_why_too(self):
        t, teams, f = self.league({"C": NO_STARTING_C, "S": SATISFIED})
        self.user_center(teams).on_trade_block = True
        offer = TradeBlockManager.generate_offer_for_simulation(t, teams[0])
        self.assertEqual(offer["offering_team"], "C")
        self.assertEqual(offer["why"], "C needed a starting C")


class DraftOfferTests(UserToolsCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(TradeFinder, "_move_up_slot", return_value=1)   # H wants the prospect going 1st
        p.start()
        self.addCleanup(p.stop)

    def draft_league(self, plan):
        gms = {"H": make_gm("gm-h", traits=["PICK_HOARDER"])}
        t, teams, f = self.league({"H": SATISFIED}, plans={"H": plan}, gms=gms)
        t.draft_lottery_order = ["U", "H"]   # the user picks first, H second
        t.pick_ownership[1] = {"R1-U": "U", "R1-H": "H", "R2-U": "U", "R2-H": "H"}
        return t, teams, f

    def test_only_a_team_with_a_draft_wish_makes_an_offer(self):
        t, teams, f = self.draft_league("REBUILDER")
        for p in teams[1].roster:
            valued(p, 60.0)
        PICK_VALUE["1:R1-U"] = 200.0
        offers = f.generate_live_draft_offers(teams[0], 1, "R1-U")
        self.assertTrue(offers)
        self.assertEqual({o["partner"] for o in offers}, {"H"})
        self.assertTrue(all(o["why"] == "H targeted a prospect" for o in offers))   # the man at #1 is its target

    def test_a_team_without_a_draft_wish_makes_no_offer(self):
        t, teams, f = self.league({"S": SATISFIED})
        t.draft_lottery_order = ["U", "S"]
        t.pick_ownership[1] = {"R1-U": "U", "R1-S": "S"}
        self.assertEqual(f.generate_live_draft_offers(teams[0], 1, "R1-U"), [])


class AskingPriceTests(UserToolsCase):
    def test_the_asking_price_asks_for_what_fulfils_the_wish(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        self.user_center(teams)
        result = f.calculate_what_would_it_take(teams[1].roster[3])
        self.assertTrue(result["attainable"])
        # the salary-first package starts with a PG; the C the owner needs is what it asks to be added
        asked = [p for p in teams[0].roster if p.nome in result["players_needed"]]
        self.assertTrue(any(p.ruolo == "C" and p.ovr >= ERA.starter for p in asked))
        self.assertEqual(result["why"], "C needed a starting C")

    def test_an_untouchable_is_not_flatly_unattainable(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        self.user_center(teams)
        target = teams[1].roster[3]
        target.is_untouchable = True
        result = f.calculate_what_would_it_take(target)
        self.assertNotEqual(result.get("reason"), "Invalid data")
        self.assertIn("players_needed", result)   # a package was built; acceptance decides
        if not result["attainable"]:
            self.assertIn("only an exceptional offer moves him", result["reason"])

    def test_the_package_for_an_untouchable_is_built_to_clear_the_premium(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        self.user_center(teams)
        target = valued(teams[1].roster[3], 24.0)
        for year in range(1, 6):
            for key in ("R1-U", "R2-U"):
                PICK_VALUE[f"{year}:{key}"] = 12.0
        plain = f.calculate_what_would_it_take(target)
        target.is_untouchable = True
        result = f.calculate_what_would_it_take(target)
        self.assertTrue(plain["attainable"])
        self.assertTrue(result["attainable"], result["reason"])   # the picks reach the premium; acceptance said yes
        self.assertGreater(len(result["picks_needed"]), len(plain["picks_needed"]))
        self.assertEqual(result["why"], "C needed a starting C")

    def test_a_team_without_a_wish_refuses_with_the_plan_sentence(self):
        t, teams, f = self.league({"S": SATISFIED})
        self.user_center(teams)
        result = f.calculate_what_would_it_take(teams[1].roster[3])
        self.assertFalse(result["attainable"])
        self.assertEqual(result["reason"], "S has no use for this deal right now")


class CounterOfferTests(UserToolsCase):
    def test_the_counter_asks_for_the_asset_that_fulfils_the_top_wish(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        self.user_center(teams)
        asked = teams[1].roster[3]
        counter = f.generate_counter_offer(teams[1], teams[0], [], [asked])
        self.assertTrue(counter["has_counter"])
        added = [p for p in teams[0].roster if p.nome in counter["add_user_players"]]
        self.assertEqual([(p.ruolo, p.ovr >= ERA.starter) for p in added], [("C", True)])
        self.assertEqual(counter["why"], "C needed a starting C")

    def test_the_counter_refuses_with_the_plan_sentence_when_nothing_fulfils_a_wish(self):
        t, teams, f = self.league({"S": SATISFIED}, user_spec=SATISFIED)
        for p in teams[0].roster:
            valued(p, 100.0)
        counter = f.generate_counter_offer(teams[1], teams[0], [], [teams[1].roster[3]])
        self.assertFalse(counter["has_counter"])
        self.assertIn("S has no use for this deal right now", counter["message"])

    def test_a_deal_the_cpu_already_accepts_is_accepted_as_it_stands(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        center = self.user_center(teams)
        counter = f.generate_counter_offer(teams[1], teams[0], [center], [teams[1].roster[3]])
        self.assertTrue(counter["accepted_as_is"])


class MotiveOfAUserTradeTests(ExecutionTestCase, UserToolsCase):
    def setUp(self):
        ExecutionTestCase.setUp(self)
        UserToolsCase.setUp(self)

    def test_an_executed_user_trade_records_one_cpu_side_motive(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        t.fase_torneo = "SEASON"
        t.trade_analytics_history = []
        center, target = self.user_center(teams), teams[1].roster[3]
        deal = f.pair_deal(teams[0], teams[1], [center], [target])
        motive = f.user_motive(deal)
        self.assertIsInstance(motive, TradeMotive)
        self.assertEqual(motive.trade_type, "user")
        self.assertEqual([s.plan for s in motive.sides], [f.get_team_strategy(teams[1]), "USER"])
        self.assertEqual(motive.sides[0].wish_kind, "NEED_STARTER")
        self.assertEqual(motive.why, "C needed a starting C")
        self.assertTrue(f.execute_trade(teams[0], teams[1], [center], [target], reason="User Trade", motive=motive))
        record = t.trade_analytics_history[-1]
        self.assertEqual(record["trade_type"], "user")
        self.assertEqual(record["why"], "C needed a starting C")
        self.assertEqual(sum(1 for m in record["motives"] if m["plan"] != "USER"), 1)
        self.assertEqual(record["motives"][0]["wish_kind"], "NEED_STARTER")


class RouteTests(UserToolsCase):
    """The server's user-trade routes: the CPU's own sentence on a refusal, the motive on an executed trade."""

    def call(self, t, url, body):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        with mock.patch.object(server, "SIMULATION_TOURNAMENT", t),                 mock.patch.object(server, "LEAGUE_STATE", "OFFSEASON_TRADES_START"),                 mock.patch.object(server, "generate_trade_news"),                 mock.patch.object(server, "update_approval_rating"),                 mock.patch("trades.trade_validator.TradeValidator.validate_trade", return_value=(True, "ok")):
            return server.app.test_client().post(url, json=body)

    def body(self, give, get):
        return {"partner_team": "C", "giving_players": [give.nome], "receiving_players": [get.nome]}

    def test_a_proposal_the_cpu_has_no_need_for_is_refused_at_an_even_price(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        wing = valued(next(p for p in teams[0].roster if p.ruolo == "SF" and p.ovr == 71), 10.0)
        resp = self.call(t, "/api/execute-user-trade", self.body(wing, teams[1].roster[3]))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("The partner team rejects the trade: Value mismatch", resp.get_json()["error"])

    def test_the_validation_says_why_when_the_cpu_agrees(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        resp = self.call(t, "/api/validate-user-trade", self.body(self.user_center(teams), teams[1].roster[3]))
        body = resp.get_json()
        self.assertTrue(body["ai_accepted"])
        self.assertEqual(body["why"], "C needed a starting C")

    def test_an_executed_route_trade_carries_the_user_motive(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        with mock.patch.object(TradeFinder, "execute_trade", return_value=True) as execute:
            resp = self.call(t, "/api/execute-user-trade", self.body(self.user_center(teams), teams[1].roster[3]))
        self.assertEqual(resp.status_code, 200)
        motive = execute.call_args.kwargs["motive"]
        self.assertEqual((motive.trade_type, motive.why), ("user", "C needed a starting C"))
        self.assertEqual(sum(1 for s in motive.sides if s.plan != "USER"), 1)

    def test_a_four_team_flow_is_refused_when_a_cpu_team_is_not_paid_for_a_deal_it_does_not_need(self):
        t, teams, f = self.league({"B": NO_STARTING_C, "D": SATISFIED, "E": SATISFIED})
        u, b, d, e = teams
        flow = [{"from": "U", "to": "B", "players": [self.user_center(teams).nome]},
                {"from": "B", "to": "D", "players": [b.roster[0].nome]},
                {"from": "D", "to": "E", "players": [d.roster[0].nome]},
                {"from": "E", "to": "U", "players": [e.roster[0].nome]}]
        with mock.patch.object(TradeFinder, "execute_4_team_trade", return_value=True) as execute:
            resp = self.call(t, "/api/trades/execute-4-team", {"flow": flow})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("D rejects the trade: Value mismatch", resp.get_json()["error"])
        execute.assert_not_called()

    @mock.patch.object(TradeFinder, "_move_up_slot", return_value=1)
    def test_a_draft_night_proposal_is_judged_on_the_draft_wishes(self, _slot):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        gms = {"H": make_gm("gm-h", traits=["PICK_HOARDER"])}
        t, teams, f = self.league({"H": SATISFIED}, plans={"H": "REBUILDER"}, gms=gms)
        t.draft_lottery_order = ["U", "H"]
        t.pick_ownership[1] = {"R1-U": "U", "R1-H": "H", "R2-U": "U", "R2-H": "H"}
        PICK_VALUE["1:R1-U"] = 200.0
        body = {"partner": "H", "user_gives_picks": ["1:R1-U"], "cpu_gives_picks": ["1:R2-H"]}
        draft = mock.Mock(get_draft_state=mock.Mock(return_value={}))
        with mock.patch.object(server, "SIMULATION_TOURNAMENT", t), mock.patch.object(server, "ACTIVE_DRAFT_INSTANCE", draft),                 mock.patch("trades.trade_validator.TradeValidator.validate_trade", return_value=(True, "ok")),                 mock.patch.object(TradeFinder, "execute_trade", return_value=True) as execute:
            resp = server.app.test_client().post("/api/draft/propose_custom_trade", json=body)
        self.assertEqual(resp.status_code, 200)
        motive = execute.call_args.kwargs["motive"]
        self.assertEqual((motive.trade_type, motive.why), ("user", "H targeted a prospect"))

    def test_a_rebuilder_with_no_prospect_in_mind_makes_no_offer(self):
        gms = {"H": make_gm("gm-h", traits=["PICK_HOARDER"])}
        t, teams, f = self.league({"H": SATISFIED}, plans={"H": "REBUILDER"}, gms=gms)
        t.draft_lottery_order = ["U", "H"]
        t.pick_ownership[1] = {"R1-U": "U", "R1-H": "H", "R2-U": "U", "R2-H": "H"}
        PICK_VALUE["1:R1-U"] = 200.0
        with mock.patch.object(TradeFinder, "_move_up_slot", return_value=None):
            self.assertEqual(f.generate_live_draft_offers(teams[0], 1, "R1-U"), [])


class BlockRespondTests(ExecutionTestCase, RouteTests):
    """/api/trade-block/respond: the one executor with a user motive, and a stale offer is refused."""

    def setUp(self):
        ExecutionTestCase.setUp(self)
        RouteTests.setUp(self)

    def block_league(self):
        t, teams, f = self.league({"C": NO_STARTING_C})
        t.fase_torneo, t.trade_analytics_history = "SEASON", []
        center, target = self.user_center(teams), teams[1].roster[3]
        t.pending_trade_block_offers = [{
            "id": "block-offer-c-1", "offering_team": "C",
            "giving_players": [{"name": target.nome}], "receiving_players": [{"name": center.nome}],
            "giving_picks": [], "receiving_picks": []}]
        return t, teams, center, target

    def respond(self, t):
        import server
        with mock.patch.object(server, "get_full_league_data_payload", return_value={}):
            return self.call(t, "/api/trade-block/respond", {"offer_id": "block-offer-c-1", "action": "ACCEPT"})

    def test_accepting_an_offer_executes_it_with_the_user_motive(self):
        t, teams, center, target = self.block_league()
        resp = self.respond(t)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(center, teams[1].roster)
        self.assertIn(target, teams[0].roster)
        self.assertEqual(t.pending_trade_block_offers, [])
        record = t.trade_analytics_history[-1]
        self.assertEqual((record["trade_type"], record["why"]), ("user", "C needed a starting C"))
        self.assertEqual(sum(1 for m in record["motives"] if m["plan"] != "USER"), 1)

    def test_a_stale_offer_is_refused_and_nothing_executes(self):
        t, teams, center, target = self.block_league()
        # the CPU team filled its hole since the offer was made: no wish is fulfilled any more
        teams[1].roster.append(make_player("C-new", ovr=80, role="C"))
        teams[1].roster[-1].squadra = teams[1]
        f = finder(t)
        self.assertFalse(f.plan_check(teams[1], [center], [target])[0])
        with mock.patch("trades.trade_finder.execution.execute_deal") as execute:
            resp = self.respond(t)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "The partner team rejects the trade: C has no use for this deal right now")
        execute.assert_not_called()
        self.assertIn(center, teams[0].roster)
        self.assertEqual(len(t.pending_trade_block_offers), 1)


if __name__ == "__main__":
    unittest.main()
