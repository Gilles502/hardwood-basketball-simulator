"""Deadline rental and change of scenery."""
import unittest
from unittest import mock

from trades import engines
from trades.engines import change_of_scenery, deadline_rental
from tests.test_trade_engines_framework import (
    EngineTestCase, BALANCED, NO_STARTING_C, ABSORBER, league, player, real_salary_rule, wish_of)
from core.config import CONFIG
from tests.trade_fixtures import finder
from trades.trade_finder import TradeFinder
from tests.test_trade_engines_framework import ERA_2002


def any_band_unhappy(test):
    """The engine at any OVR: CONFIG.TRADES.UNHAPPY_MIN_BAND (tested in test_wishes) set to the lowest band."""
    import dataclasses
    import core.front_office.wishes as wishes_module
    from core.config import CONFIG
    config = dataclasses.replace(CONFIG, TRADES=dataclasses.replace(CONFIG.TRADES, UNHAPPY_MIN_BAND="fringe"))
    patch = mock.patch.object(wishes_module, "CONFIG", config)
    patch.start()
    test.addCleanup(patch.stop)


def owner_of(torneo, key):
    return {owners[key] for owners in torneo.pick_ownership.values()}


def last_record(torneo):
    return torneo.trade_analytics_history[-1]


# ---------------------------------------------------------------- deadline rental
class DeadlineRentalTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.t, self.teams = league({"R": BALANCED, "S": ABSORBER}, {"R": "CONTENDER", "S": "REBUILDER"})
        self.r, self.s = self.teams["R"], self.teams["S"]
        self.rental = player(self.s, "SF", 72)
        self.rental.eta, self.rental.contract.anni_rimanenti = 30, 1
        self.rental._test_value = 1.0   # a 30-year-old on an expiring deal for a rebuilder: worth about a second
        self.f = finder(self.t)
        self.f.begin_window("deadline")

    def test_the_contender_rents_an_expiring_veteran_for_a_second(self):
        wish = wish_of(self.f, self.r, "RENT_VETERAN")
        self.assertTrue(deadline_rental.run(self.f, self.r, wish))
        self.assertIn(self.rental, self.r.roster)
        self.assertIn("S", owner_of(self.t, "R2-R"))
        self.assertEqual(owner_of(self.t, "R1-R"), {"R"})
        rec = last_record(self.t)
        self.assertEqual(rec["trade_type"], "deadline_rental")
        self.assertEqual([m["wish_kind"] for m in rec["motives"]], ["RENT_VETERAN", "SELL_EXPIRING"])

    def test_without_seconds_there_is_no_rental(self):
        # every rental includes a draft pick: a young player alone is not the price
        for year in self.t.pick_ownership:
            self.t.pick_ownership[year]["R2-R"] = "S"
        kid = player(self.r, "SG", 68)
        kid.eta = 22
        kid._test_value = 1.0
        wish = wish_of(self.f, self.r, "RENT_VETERAN")
        self.assertFalse(deadline_rental.run(self.f, self.r, wish))
        self.assertIn(kid, self.r.roster)

    def test_a_first_round_pick_is_never_the_payment(self):
        for year in self.t.pick_ownership:
            self.t.pick_ownership[year]["R2-R"] = "S"
        wish = wish_of(self.f, self.r, "RENT_VETERAN")
        self.assertFalse(deadline_rental.run(self.f, self.r, wish))
        self.assertEqual(owner_of(self.t, "R1-R"), {"R"})
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_salaries_are_matched_with_a_filler_outside_the_top_five(self):
        self.rental.contract.salario_annuale = 5.0
        for p in self.r.roster:
            p._test_value = 0.1   # the renter fillers are worth next to nothing
            if p.ovr <= 70:
                p.eta, p.contract.anni_rimanenti = 29, 1   # real surplus: older, expiring, under RENT_FILLER_MAX_OVR
        real_salary_rule(self.r, 50.0)
        real_salary_rule(self.s, 50.0)
        wish = wish_of(self.f, self.r, "RENT_VETERAN")
        self.assertTrue(deadline_rental.run(self.f, self.r, wish))
        sent = [p for p in self.s.roster if p.nome.startswith("R-")]
        self.assertTrue(sent)
        top5_floor = sorted((o for _, o in BALANCED), reverse=True)[4]
        self.assertTrue(all(p.ovr < top5_floor for p in sent))
        self.assertTrue(all(p.ovr <= 70 and p.contract.anni_rimanenti <= 1 for p in sent))

    def test_a_player_as_good_as_the_rental_is_never_a_filler(self):
        self.rental.contract.salario_annuale = 5.0
        for p in self.r.roster:
            p._test_value = 0.1   # fillers priced at nothing, but none of them is surplus (2 years left)
        real_salary_rule(self.r, 50.0)
        real_salary_rule(self.s, 50.0)
        self.assertFalse(deadline_rental.run(self.f, self.r, wish_of(self.f, self.r, "RENT_VETERAN")))

    def test_never_in_the_predraft_window(self):
        wish = wish_of(self.f, self.r, "RENT_VETERAN")
        self.f.begin_window("predraft")
        self.assertFalse(deadline_rental.run(self.f, self.r, wish))
        self.assertIn(self.rental, self.s.roster)
        self.assertEqual(self.t.trade_analytics_history, [])
        self.assertNotIn("RENT_VETERAN", [w.kind for w in self.f.wishes_for(self.r)])

    def test_a_seller_in_the_race_has_no_wish_and_no_deal(self):
        t, teams = league({"R": BALANCED, "S": ABSORBER}, {"R": "CONTENDER", "S": "MIDDLE"})
        rental = player(teams["S"], "SF", 72)
        rental.eta, rental.contract.anni_rimanenti = 30, 1
        f = finder(t)
        f.begin_window("deadline")
        self.assertNotIn("SELL_EXPIRING", [w.kind for w in f.wishes_for(teams["S"])])
        self.assertFalse(deadline_rental.run(f, teams["R"], wish_of(f, teams["R"], "RENT_VETERAN")))
        self.assertIn(rental, teams["S"].roster)

    def test_other_wish_kinds_are_not_served(self):
        self.assertFalse(deadline_rental.run(self.f, self.r, wish_of(self.f, self.s, "SELL_EXPIRING")))

    def test_registered(self):
        self.assertEqual([e.name for e in engines.engines_for("RENT_VETERAN")], ["deadline_rental"])


# Thin at C (no rotation C at all): DEPTH_NEEDED C. Holds a 76 SG.
THIN_AT_C = [("PG", 72), ("PG", 70), ("SG", 76), ("SG", 72), ("SF", 72), ("SF", 70), ("PF", 72), ("PF", 70),
             ("C", 66), ("C", 62), ("SG", 66), ("SF", 66), ("PF", 66)]
# Thin at PG, with a starting C 77 to give.
THIN_AT_PG = [("PG", 66), ("PG", 62), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 76), ("PF", 71),
              ("C", 78), ("C", 77), ("C", 76), ("SG", 66), ("SF", 66)]
# Deep (10 rotation players) but no rotation-band C: the band players outside the top 5 are PG, SG, SF, PF.
NO_ROTATION_C = [("PG", 77), ("PG", 72), ("SG", 77), ("SG", 72), ("SF", 77), ("SF", 72), ("PF", 77), ("PF", 72),
                 ("C", 77), ("C", 66), ("SG", 70), ("SF", 68), ("PF", 67)]


class ChangeOfSceneryTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        any_band_unhappy(self)
        self.t, self.teams = league({"A": ABSORBER, "B": ABSORBER}, {"A": "MIDDLE", "B": "MIDDLE"})
        self.a, self.b = self.teams["A"], self.teams["B"]
        self.pa, self.pb = player(self.a, "SF", 70), player(self.b, "SG", 70)
        self.pa.morale = self.pb.morale = 40
        self.f = finder(self.t)

    def test_two_unhappy_players_swap(self):
        self.assertTrue(change_of_scenery.run(self.f, self.a, wish_of(self.f, self.a, "UNHAPPY_PLAYER")))
        self.assertIn(self.pb, self.a.roster)
        self.assertIn(self.pa, self.b.roster)
        rec = last_record(self.t)
        self.assertEqual(rec["trade_type"], "change_of_scenery")
        self.assertEqual([m["wish_kind"] for m in rec["motives"]], ["UNHAPPY_PLAYER", "UNHAPPY_PLAYER"])

    def test_a_happy_player_is_not_swapped(self):
        self.pb.morale = 80
        self.assertEqual([w.kind for w in self.f.wishes_for(self.b) if w.kind == "UNHAPPY_PLAYER"], [])
        self.assertFalse(change_of_scenery.run(self.f, self.a, wish_of(self.f, self.a, "UNHAPPY_PLAYER")))
        self.assertIn(self.pa, self.a.roster)
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_values_further_apart_than_the_gap_mean_no_swap(self):
        self.pa._test_value, self.pb._test_value = 10.0, 14.0
        self.assertFalse(change_of_scenery.run(self.f, self.a, wish_of(self.f, self.a, "UNHAPPY_PLAYER")))
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_values_inside_the_gap_swap(self):
        self.pa._test_value, self.pb._test_value = 10.0, 10.3
        self.assertTrue(change_of_scenery.run(self.f, self.a, wish_of(self.f, self.a, "UNHAPPY_PLAYER")))

    def test_other_wish_kinds_are_not_served(self):
        self.assertFalse(change_of_scenery.run(self.f, self.a, wish_of(self.f, self.a, "ABSORB_SALARY")))

    def test_registered(self):
        self.assertEqual([e.name for e in engines.engines_for("UNHAPPY_PLAYER")], ["change_of_scenery"])


class RealValueTests(unittest.TestCase):
    """No `_test_value` overrides: the real strategic values decide the price question, as in a league."""
    def setUp(self):
        patches = [
            mock.patch.object(TradeFinder, "_log_trade_to_file"),
            mock.patch("core.news_generator.add_news"),
            mock.patch.object(TradeFinder, "era", return_value=ERA_2002),
            mock.patch("trades.trade_finder.random.uniform", return_value=0.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def rental_league(self, ovr=72):
        t, teams = league({"R": BALANCED, "S": ABSORBER}, {"R": "CONTENDER", "S": "REBUILDER"})
        if ovr == 72:
            rental = player(teams["S"], "SF", ovr)
        else:
            from tests.trade_fixtures import make_player
            rental = make_player("S-old", ovr=ovr, age=31, role="SF", years=1)
            teams["S"].roster.append(rental)
        rental.eta, rental.contract.anni_rimanenti = 30, 1
        f = finder(t)
        f.begin_window("deadline")
        return t, teams, rental, f

    def test_a_second_buys_a_72_rental_from_a_team_going_nowhere(self):
        # an expiring veteran leaves for free in the summer: the seller's price is waived, the second is enough
        t, teams, rental, f = self.rental_league()
        self.assertTrue(deadline_rental.run(f, teams["R"], wish_of(f, teams["R"], "RENT_VETERAN")))
        self.assertIn(rental, teams["R"].roster)

    def test_a_second_does_not_buy_a_rental_above_the_waive_line(self):
        # RENT_WAIVE_MAX_OVR: a better veteran is priced in full, a second is no price for him
        line = ERA_2002.ovr_at(CONFIG.TRADES.RENT_WAIVE_MAX_OVR)
        t, teams, rental, f = self.rental_league(ovr=line + 4)
        self.assertFalse(deadline_rental.run(f, teams["R"], wish_of(f, teams["R"], "RENT_VETERAN")))
        self.assertIn(rental, teams["S"].roster)

    def test_a_useful_prospect_is_not_the_price_of_a_rental(self):
        t, teams, rental, f = self.rental_league()
        kid = player(teams["R"], "SG", 68)
        kid.eta, kid.potenziale = 22, 74
        self.assertTrue(deadline_rental.run(f, teams["R"], wish_of(f, teams["R"], "RENT_VETERAN")))
        self.assertIn(kid, teams["R"].roster)   # starter potential: he stays
        self.assertIn(rental, teams["R"].roster)

    def test_two_unhappy_equals_swap(self):
        any_band_unhappy(self)
        t, teams = league({"A": ABSORBER, "B": ABSORBER}, {"A": "MIDDLE", "B": "MIDDLE"})
        player(teams["A"], "SF", 70).morale = 40
        player(teams["B"], "SG", 70).morale = 40
        f = finder(t)
        self.assertTrue(change_of_scenery.run(f, teams["A"], wish_of(f, teams["A"], "UNHAPPY_PLAYER")))
        self.assertEqual(last_record(t)["trade_type"], "change_of_scenery")


if __name__ == "__main__":
    unittest.main()
