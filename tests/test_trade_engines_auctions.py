"""Auction engines: trade demand, roster congestion and veteran sale. Bids come only from teams that want the player."""
from unittest import mock

from core.config import CONFIG
from trades import engines
from trades.engines import auction, trade_demand, veteran_sale
from trades.trade_finder import TradeFinder
from tests.test_trade_engines_framework import (
    EngineTestCase, ABSORBER, league, player, real_salary_rule, wish_of)
from tests.trade_fixtures import finder, make_gm

# A contender with no starting SF (best SF 72) and no star: NEED_STARTER SF.
SF_HOLE = [("PG", 76), ("PG", 69), ("SG", 76), ("SG", 68), ("SF", 72), ("SF", 69), ("PF", 76), ("PF", 69),
           ("C", 76), ("C", 69), ("SG", 66), ("SF", 66), ("PF", 67)]
# A contender with no starting PF (best PF 72): NEED_STARTER PF.
PF_HOLE = [("PG", 76), ("PG", 69), ("SG", 76), ("SG", 68), ("SF", 76), ("SF", 69), ("PF", 72), ("PF", 69),
           ("C", 76), ("C", 69), ("SG", 66), ("SF", 66), ("PF", 67)]
# A rebuilder with an 86 SF and an 80 PF.
SELLER = [("PG", 68), ("PG", 64), ("SG", 66), ("SG", 64), ("SF", 86), ("SF", 62), ("PF", 80), ("PF", 62),
          ("C", 66), ("C", 62), ("SG", 60), ("SF", 60), ("PF", 60)]
# A middle team with three starting PFs.
THREE_PF = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 78), ("PF", 77),
            ("PF", 76), ("C", 72), ("C", 70), ("SG", 66), ("SF", 66)]

NEED_KINDS = ("NEED_STARTER", "WANT_STAR")


def aged(p, age):
    p.eta = age
    return p


class TradeDemandTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.t, self.teams = league({"R": SELLER, "A": SF_HOLE, "B": ABSORBER},
                                    {"R": "REBUILDER", "A": "CONTENDER", "B": "MIDDLE"})
        self.f = finder(self.t)
        self.r, self.a, self.b = (self.teams[n] for n in "RAB")
        self.star = aged(player(self.r, "SF", 86), 31)
        self.star.morale = 40
        self.star._test_value = 3.0

    def test_star_wanting_out_goes_to_the_bidder_with_a_matching_wish(self):
        wish = wish_of(self.f, self.r, "STAR_WANTS_OUT")
        self.assertEqual(wish.player, self.star.nome)
        asked = []
        real = TradeFinder._build_bid_for_player

        def spy(finder_, partner, seller, p):
            asked.append(partner.nome)
            return real(finder_, partner, seller, p)

        with mock.patch.object(TradeFinder, "_build_bid_for_player", spy):
            self.assertTrue(trade_demand.run(self.f, self.r, wish))
        self.assertIn(self.star, self.a.roster)
        self.assertNotIn(self.star, self.r.roster)
        self.assertEqual(asked, ["A"])   # B has no wish this player fills: it never bids
        rec = self.t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "trade_demand")
        self.assertEqual(rec["motives"][0]["wish_kind"], "STAR_WANTS_OUT")
        self.assertIn(rec["motives"][1]["wish_kind"], NEED_KINDS)

    def test_an_untouchable_star_who_asks_out_is_still_sold(self):
        # designa_intoccabili flags every team's best player; a star asking out is exempt (acceptance reads
        # _wants_out), so the flag must not hide him from the tradeable list before _wants_out is set.
        self.star.is_untouchable = True
        self.star._wants_out = False   # stale flag from before he asked out
        self.assertIn(self.star, self.f.get_tradeable_players(self.r, allow_stars=True))
        self.assertTrue(self.star._wants_out)
        self.assertTrue(trade_demand.run(self.f, self.r, wish_of(self.f, self.r, "STAR_WANTS_OUT")))
        self.assertIn(self.star, self.a.roster)

    def test_an_untouchable_who_does_not_ask_out_stays_hidden(self):
        self.star.morale = 90
        self.star.is_untouchable = True
        self.assertNotIn(self.star, self.f.get_tradeable_players(self.r, allow_stars=True))

    def test_no_bidder_with_a_wish_means_no_trade(self):
        t, teams = league({"R": SELLER, "B": ABSORBER}, {"R": "REBUILDER", "B": "MIDDLE"})
        f = finder(t)
        star = aged(player(teams["R"], "SF", 86), 31)
        star.morale = 40
        star._test_value = 3.0
        self.assertFalse(trade_demand.run(f, teams["R"], wish_of(f, teams["R"], "STAR_WANTS_OUT")))
        self.assertIn(star, teams["R"].roster)
        self.assertEqual(t.trade_analytics_history, [])

    def test_the_engines_are_registered_and_resolve(self):
        for kind, name in (("STAR_WANTS_OUT", "trade_demand"), ("SELL_VETERANS", "veteran_sale")):
            self.assertIn(name, [e.name for e in engines.engines_for(kind)])

    def test_other_wish_kinds_are_not_served(self):
        self.assertFalse(trade_demand.run(self.f, self.r, wish_of(self.f, self.r, "SELL_VETERANS")))


class SeatsTests(EngineTestCase):
    def test_a_vulture_is_in_the_first_seats(self):
        specs = {"R": SELLER}
        specs.update({f"T{i}": SF_HOLE for i in range(12)})
        plans = {"R": "REBUILDER"}
        plans.update({f"T{i}": "CONTENDER" for i in range(12)})
        t, teams = league(specs, plans)
        gm = make_gm("vulture", trade=CONFIG.FRONT_OFFICE.VULTURE_SKILL + 10)
        gm.team = "T7"
        t.front_office.gms["vulture"] = gm
        t.front_office.seats["T7"] = "vulture"
        f = finder(t)
        for _ in range(20):
            seats = auction.seat_bidders(f, teams["R"], NEED_KINDS)
            names = [team.nome for team, _ in seats]
            self.assertLessEqual(len(names), CONFIG.TRADES.AUCTION_MAX_BIDDERS)
            self.assertIn("T7", names[:CONFIG.FRONT_OFFICE.VULTURE_GUARANTEED_SLOTS])
            self.assertNotIn("R", names)


class VeteranSaleTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.t, self.teams = league({"R": SELLER, "C": PF_HOLE}, {"R": "REBUILDER", "C": "CONTENDER"})
        self.f = finder(self.t)
        self.r, self.c = self.teams["R"], self.teams["C"]
        real_salary_rule(self.r, 50.0)
        real_salary_rule(self.c, 50.0)
        self.vet = aged(player(self.r, "PF", 80), 33)
        self.vet.contract.salario_annuale = 9.0
        self.vet._test_value = 1.5
        self.vet._test_value_for = {"C": 4.0}   # the contender values him more than the rebuilder selling him
        for p in self.c.roster:
            p._test_value = 1.0   # salary fillers: two 5.0M contracts match the 9.0M salary

    def own_no_picks(self, team):
        for owners in self.t.pick_ownership.values():
            for key in list(owners):
                if owners[key] == team.nome:
                    owners[key] = "R"

    def test_only_fillers_offered_is_no_trade(self):
        self.own_no_picks(self.c)
        wish = wish_of(self.f, self.r, "SELL_VETERANS")
        with mock.patch.object(TradeFinder, "execute_deal", wraps=self.f.execute_deal) as ex:
            self.assertFalse(veteran_sale.run(self.f, self.r, wish))
        ex.assert_not_called()
        self.assertIn(self.vet, self.r.roster)
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_a_pick_back_closes_as_veteran_sale(self):
        wish = wish_of(self.f, self.r, "SELL_VETERANS")
        self.assertTrue(veteran_sale.run(self.f, self.r, wish))
        self.assertIn(self.vet, self.c.roster)
        rec = self.t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "veteran_sale")
        self.assertEqual(rec["motives"][0]["wish_kind"], "SELL_VETERANS")
        self.assertIn(rec["motives"][1]["wish_kind"], veteran_sale.BIDDER_KINDS)
        got_pick = any(v == "R" and k.endswith("-C") for owners in self.t.pick_ownership.values()
                       for k, v in owners.items())
        self.assertTrue(got_pick)

