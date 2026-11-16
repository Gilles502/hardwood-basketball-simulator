"""Trade quality rules (2026-11-04): a roster spot has a cost, rebuilders don't buy veterans, seconds are worth next to
nothing, and the marginal engines (consolidation, bench shuffle, roster congestion) are gone."""
import unittest
from unittest import mock

from core.config import CONFIG
from core.models import Squadra
from core.front_office.wishes import KINDS, Wish, fulfils
from trades import engines
from trades.engines import common
from trades.trade_finder import TradeFinder
from tests.test_trade_engines_framework import ABSORBER, BALANCED, ERA_2002, EngineTestCase, league
from tests.trade_fixtures import finder, make_player


class ReceivedValueTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.t, teams = league({"K": BALANCED, "R": ABSORBER}, {"K": "CONTENDER", "R": "REBUILDER"})
        self.k, self.r = teams["K"], teams["R"]
        self.f = finder(self.t)

    def role_players(self, team, n, value, age=26):
        found = []
        for i in range(n):
            p = make_player(f"{team.nome}-role{i}-{age}", ovr=74, age=age, role="SG")
            p._test_value = value
            team.roster.append(p)
            found.append(p)
        return found

    def test_three_role_players_count_less_than_their_sum(self):
        three = self.role_players(self.r, 3, 10.0)
        shares = CONFIG.TRADES.RECEIVED_PLAYER_SHARES
        self.assertAlmostEqual(self.f.received_value(self.k, three), 10.0 * (shares[0] + shares[1] + shares[2]))
        self.assertLess(self.f.received_value(self.k, three), 30.0 * 0.6)

    def test_three_role_players_do_not_buy_a_starter_worth_less_than_their_sum(self):
        starter = make_player("K-starter", ovr=80, role="SG")
        starter._test_value = 20.0
        self.k.roster.append(starter)
        three = self.role_players(self.r, 3, 9.0)   # 27 in all, but 9 + 4.5 + 2.25 to the team that receives them
        with mock.patch.object(TradeFinder, "plan_check", return_value=(True, "", None)):
            ok, why = self.f.would_accept_trade_with_reason(self.k, three, [starter])
        self.assertFalse(ok)
        self.assertIn("Value mismatch", why)

    def test_a_rebuilder_barely_values_a_veteran_role_player_it_receives(self):
        vet, = self.role_players(self.k, 1, 10.0, age=CONFIG.TRADES.REBUILDER_VET_AGE)
        kid, = self.role_players(self.k, 1, 10.0, age=22)
        share = CONFIG.TRADES.REBUILDER_RECEIVED_VET_SHARE
        self.assertAlmostEqual(self.f.received_value(self.r, [vet]), 10.0 * share)
        self.assertAlmostEqual(self.f.received_value(self.r, [kid]), 10.0)
        self.assertAlmostEqual(self.f.received_value(self.k, [vet]), 10.0)   # a contender pays him in full


class RebuilderVeteranTests(unittest.TestCase):
    """Real strategic values: a rebuilder does not give a good veteran away, but sells one it wants gone."""
    def setUp(self):
        p = mock.patch.object(TradeFinder, "era", return_value=ERA_2002)
        p.start()
        self.addCleanup(p.stop)
        self.t, teams = league({"R": ABSORBER, "M": ABSORBER}, {"R": "REBUILDER", "M": "MIDDLE"})
        self.r, self.m = teams["R"], teams["M"]
        self.f = finder(self.t)

    def share(self, years):
        vet = make_player(f"vet{years}", ovr=78, age=31, salary=3.0, years=years)
        return self.f.get_strategic_value(vet, self.r) / self.f.get_strategic_value(vet, self.m)

    def test_a_veteran_with_years_left_keeps_most_of_his_value(self):
        self.assertAlmostEqual(self.share(2), CONFIG.TRADES.REBUILDER_VET_SHARE)

    def test_an_expiring_veteran_is_cheap(self):
        # the rebuilder's +15% for an expiring contract still applies on top
        self.assertAlmostEqual(self.share(1), CONFIG.TRADES.REBUILDER_DUMP_VET_SHARE * 1.15)
        self.assertLess(self.share(1), self.share(2))


class SecondsTests(unittest.TestCase):
    def test_seconds_are_not_more_picks_nor_the_future(self):
        t, teams = league({"R": ABSORBER}, {"R": "REBUILDER"})
        team = teams["R"]
        vet = make_player("R-vet", ovr=75, age=33, role="SF")
        team.roster.append(vet)
        want_picks, sell = Wish("WANT_PICKS", "R", 0.0, ""), Wish("SELL_VETERANS", "R", 0.0, "")
        self.assertFalse(fulfils(want_picks, ["2003:R2-X", "2004:R2-X"], [], team, ERA_2002))
        self.assertTrue(fulfils(want_picks, ["2003:R1-X"], [], team, ERA_2002))
        self.assertFalse(fulfils(sell, ["2003:R2-X"], [vet], team, ERA_2002))
        self.assertTrue(fulfils(sell, ["2003:R1-X"], [vet], team, ERA_2002))

    def test_a_second_is_worth_next_to_nothing(self):
        t, _teams = league({"R": ABSORBER}, {"R": "REBUILDER"})
        with mock.patch.object(TradeFinder, "era", return_value=ERA_2002):
            f = finder(t)
            self.assertLessEqual(f.get_pick_value("R2-R", 1, on_curve=True), CONFIG.TRADES.PICK_R2_BASE_VALUE * 1.6)
            self.assertGreater(f.get_pick_value("R1-R", 1, on_curve=True), 10 * f.get_pick_value("R2-R", 1, on_curve=True))

    def test_sweeteners_are_later_firsts_only(self):
        t, teams = league({"R": ABSORBER}, {"R": "REBUILDER"})
        f = finder(t)
        extra = common.sweeteners(f, teams["R"], "1:R1-R")
        self.assertTrue(extra)
        self.assertTrue(all(":R1-" in k and not k.startswith("1:") for k in extra), extra)


class PickRulesTests(EngineTestCase):
    """FIRST_PICK_MIN_OVR, STARTER_SWAP_MAX_PICKS and no flip of a pick bought this season."""
    def setUp(self):
        super().setUp()
        self.t, teams = league({"K": BALANCED, "R": ABSORBER}, {"K": "CONTENDER", "R": "REBUILDER"})
        self.k, self.r = teams["K"], teams["R"]
        self.f = finder(self.t)

    def why(self, receives, gives):
        with mock.patch.object(TradeFinder, "plan_check", return_value=(True, "", None)):
            return self.f.would_accept_trade_with_reason(self.k, receives, gives)[1]

    def test_a_first_goes_only_for_an_80_or_better(self):
        line = ERA_2002.ovr_at(CONFIG.TRADES.FIRST_PICK_MIN_OVR)
        self.assertIn("First-Round Pick Rule", self.why([make_player("r78", ovr=line - 2)], ["1:R1-K"]))
        self.assertNotIn("First-Round Pick Rule", self.why([make_player("r80", ovr=line)], ["1:R1-K"]))
        self.assertNotIn("First-Round Pick Rule", self.why(["1:R1-R"], ["2:R1-K"]))   # a pick swap
        self.assertNotIn("First-Round Pick Rule", self.why([make_player("r78", ovr=line - 2)], ["1:R2-K"]))

    def test_a_starter_swap_is_evened_out_with_one_pick(self):
        mine = make_player("K-81", ovr=81)
        self.k.roster.append(mine)
        theirs = make_player("R-84", ovr=84)
        self.assertIn("Starter Swap Rule", self.why([theirs], [mine, "1:R1-K", "2:R1-K"]))
        self.assertNotIn("Starter Swap Rule", self.why([theirs], [mine, "1:R1-K"]))

    def test_a_pick_bought_this_season_is_not_flipped(self):
        from trades.execution import Deal
        common.remember_moves(self.f, Deal([self.k, self.r], [("K", "R", "1:R1-K")]))
        self.assertIsNotNone(common.flips_a_pick(self.f, Deal([self.r, self.k], [("R", "K", "1:R1-K")])))
        self.assertIsNone(common.flips_a_pick(self.f, Deal([self.r, self.k], [("R", "K", "2:R1-R")])))
        self.t.season_number = getattr(self.t, 'season_number', 0) + 1   # a new season: he may trade it
        self.assertIsNone(common.flips_a_pick(self.f, Deal([self.r, self.k], [("R", "K", "1:R1-K")])))


class ThirdRoundRulesTests(EngineTestCase):
    """2026-11-04 round 3: a rebuilder keeps its good youngsters, a star is not sold for role players, a rental is not
    paid with useful youth, a trade-up carries no protection."""
    def setUp(self):
        super().setUp()
        self.t, teams = league({"K": BALANCED, "R": ABSORBER}, {"K": "CONTENDER", "R": "REBUILDER"})
        self.k, self.r = teams["K"], teams["R"]
        self.f = finder(self.t)

    def hard_no(self, team, receives, gives):
        from core.front_office.wishes import plan_hard_no
        return plan_hard_no(team, self.f.wish_context(team), receives, gives)

    def test_a_rebuilder_keeps_a_young_good_player(self):
        kid = make_player("R-kid", ovr=81, age=25)
        self.assertIn("is the future", self.hard_no(self.r, [], [kid]) or "")
        self.assertIsNone(self.hard_no(self.r, [], [make_player("R-27", ovr=81, age=27)]))
        self.assertIsNone(self.hard_no(self.r, [], [make_player("R-weak", ovr=70, age=25)]))
        kid._wants_out = True
        self.assertIsNone(self.hard_no(self.r, [], [kid]))   # he asked out: he goes

    def test_a_star_is_not_sold_for_role_players(self):
        star = make_player("K-star", ovr=85, age=29)
        role = [make_player(f"R-{i}", ovr=74, age=28) for i in range(3)]
        with mock.patch.object(TradeFinder, "plan_check", return_value=(True, "", None)):
            star._test_value = 5.0   # price is no obstacle: the rule alone decides
            for p in role:
                p._test_value = 50.0
            ok, why = self.f.would_accept_trade_with_reason(self.k, role, [star])
            self.assertFalse(ok)
            self.assertIn("Star Sale Rule", why)
            ok, why = self.f.would_accept_trade_with_reason(self.k, role + ["1:R1-R"], [star])
            self.assertNotIn("Star Sale Rule", why)

    def test_a_trade_up_pick_is_unprotected(self):
        from trades.execution import Deal, execute_deal
        self.f.window = "predraft"
        self.t.pick_protections.setdefault(1, {})["R1-R"] = "Top 3"
        self.t.pick_ownership.setdefault(1, {})["R1-R"] = "R"
        deal = Deal([self.k, self.r], [("R", "K", "1:R1-R")], pick_protections={"1:R1-R": "Unprotected"})
        with mock.patch("trades.execution.validate_deal", return_value=(True, "")), \
                mock.patch.object(TradeFinder, "_log_trade_to_file"), \
                mock.patch.object(TradeFinder, "_record_trade_analytics_snapshot"), \
                mock.patch("trades.execution._publish_news"):
            execute_deal(self.f, deal, None)
        self.assertEqual(self.t.pick_protections[1]["R1-R"], "Unprotected")


class VeteranUntouchableTests(EngineTestCase):
    """Above UNTOUCHABLE_FREE_AGE only a real franchise player stays untouchable (88+, or 86+ on a contender)."""
    def setUp(self):
        super().setUp()
        self.t, teams = league({"K": BALANCED, "R": ABSORBER}, {"K": "CONTENDER", "R": "MIDDLE"})
        self.k, self.r = teams["K"], teams["R"]

    def best(self, team, ovr, age):
        star = make_player(f"{team.nome}-star", ovr=ovr, age=age)
        star.is_untouchable = True   # whatever rule of designa_intoccabili flagged him (best player, award...)
        team.roster.append(star)
        Squadra._limit_veteran_untouchables(team, self.t)
        return star

    def test_a_non_contender_veteran_needs_88(self):
        self.assertFalse(self.best(self.r, 87, 30).is_untouchable)
        self.assertTrue(self.best(self.r, 88, 30).is_untouchable)

    def test_a_contender_veteran_needs_86(self):
        self.assertFalse(self.best(self.k, 85, 30).is_untouchable)
        self.assertTrue(self.best(self.k, 86, 30).is_untouchable)

    def test_a_player_up_to_26_keeps_the_old_rule(self):
        self.assertTrue(self.best(self.r, 84, CONFIG.TRADES.UNTOUCHABLE_FREE_AGE).is_untouchable)


class FirstPickAgeTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.t, teams = league({"K": BALANCED, "R": ABSORBER}, {"K": "CONTENDER", "R": "REBUILDER"})
        self.k = teams["K"]
        self.f = finder(self.t)

    def why(self, player):
        with mock.patch.object(TradeFinder, "plan_check", return_value=(True, "", None)):
            return self.f.would_accept_trade_with_reason(self.k, [player], ["1:R1-K"])[1]

    def test_a_78_earns_a_first_only_while_young(self):
        t = CONFIG.TRADES
        young = make_player("y78", ovr=ERA_2002.ovr_at(t.FIRST_PICK_MIN_OVR), age=t.FIRST_PICK_MAX_AGE_BELOW)
        old = make_player("o78", ovr=ERA_2002.ovr_at(t.FIRST_PICK_MIN_OVR), age=t.FIRST_PICK_MAX_AGE_BELOW + 1)
        great_old = make_player("o80", ovr=ERA_2002.ovr_at(t.FIRST_PICK_OLD_MIN_OVR), age=34)
        self.assertNotIn("First-Round Pick Rule", self.why(young))
        self.assertIn("First-Round Pick Rule", self.why(old))
        self.assertNotIn("First-Round Pick Rule", self.why(great_old))


class RemovedEnginesTests(unittest.TestCase):
    def test_the_marginal_engines_and_their_wishes_are_gone(self):
        names = {e.name for lst in engines.ENGINES.values() for e in lst}
        self.assertFalse(names & {"consolidation", "bench_shuffle", "roster_congestion"})
        self.assertNotIn("CONSOLIDATE", KINDS)
        self.assertNotIn("SHUFFLE_BENCH", KINDS)
        self.assertIn("ROLE_CONGESTION", KINDS)   # still a positional_swap trigger


if __name__ == "__main__":
    unittest.main()
