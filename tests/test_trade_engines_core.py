"""Core engines on wishes: star upgrade (with 2/3-for-1 and the 3-team rescue) and win-now for youth."""
from unittest import mock

from trades import engines
from trades.engines import star_upgrade, win_now_youth
from trades.trade_finder import TradeFinder
from tests.test_trade_engines_framework import (
    EngineTestCase, ABSORBER, league, player, real_salary_rule, wish_of)
from tests.trade_fixtures import finder, make_gm

# A contender with no starting PF (best PF 72); nobody outside its top 5 reaches the rotation line.
PF_HOLE = [("PG", 76), ("PG", 69), ("SG", 76), ("SG", 68), ("SF", 76), ("SF", 69), ("PF", 72), ("PF", 69),
           ("C", 76), ("C", 69), ("SG", 66), ("SF", 66), ("PF", 67)]
# The same hole, but with rotation players (71) behind the top 5: salary fillers.
PF_HOLE_DEPTH = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 68), ("SF", 76), ("SF", 71), ("PF", 72), ("PF", 69),
                 ("C", 76), ("C", 69), ("SG", 66), ("SF", 66), ("PF", 67)]
# A rebuilder with an 80 PF of 31 (and an 86 SF of 31).
SELLER = [("PG", 68), ("PG", 64), ("SG", 66), ("SG", 64), ("SF", 86), ("SF", 62), ("PF", 80), ("PF", 62),
          ("C", 66), ("C", 62), ("SG", 60), ("SF", 60), ("PF", 60)]
# A contender with no hole and no star: WANT_STAR only for a STAR_CHASER... plus its own CONTENDER want.
NO_HOLE = [("PG", 77), ("PG", 72), ("SG", 77), ("SG", 72), ("SF", 77), ("SF", 72), ("PF", 77), ("PF", 72),
           ("C", 77), ("C", 72), ("SG", 68), ("SF", 68), ("PF", 67)]


def old(p, age, pot=None):
    p.eta = age
    if pot is not None:
        p.potenziale = pot
    return p


class StarUpgradeTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.t, self.teams = league({"C": PF_HOLE, "R": SELLER}, {"C": "CONTENDER", "R": "REBUILDER"})
        self.f = finder(self.t)
        self.c, self.r = self.teams["C"], self.teams["R"]
        self.target = old(player(self.r, "PF", 80), 31)
        self.target._test_value = 24.0
        self.young = old(player(self.c, "SG", 68), 24, 80)
        self.young._test_value = 25.0

    def test_contender_with_a_pf_hole_gets_the_80_pf_for_a_first_and_a_young_player(self):
        wish = wish_of(self.f, self.c, "NEED_STARTER", "PF")
        self.assertTrue(star_upgrade.run(self.f, self.c, wish))
        self.assertIn(self.target, self.c.roster)
        self.assertIn(self.young, self.r.roster)
        rec = self.t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "starter_upgrade")
        self.assertEqual(rec["team_count"], 2)
        self.assertEqual(rec["motives"][0]["wish_kind"], "NEED_STARTER")
        self.assertIn(rec["motives"][1]["wish_kind"], star_upgrade.PARTNER_KINDS)
        r1_sent = [k for y, o in self.t.pick_ownership.items() for k, v in o.items() if k.startswith("R1") and v == "R"]
        self.assertTrue(any(k.startswith("R1-C") for k in r1_sent))

    def test_star_upgrade_sees_a_partners_untouchable_other_views_do_not(self):
        self.target.is_untouchable = True
        wish = wish_of(self.f, self.c, "NEED_STARTER", "PF")
        self.assertIn(self.target, star_upgrade._targets(self.f, self.c, self.r, wish))
        self.assertNotIn(self.target, self.f.get_tradeable_players(self.r, allow_stars=True))
        self.assertIn(self.target, self.f.get_tradeable_players(self.r, allow_stars=True, include_untouchables=True))

    def test_star_upgrade_pays_the_premium_for_an_untouchable(self):
        self.target.is_untouchable = True
        wish = wish_of(self.f, self.c, "NEED_STARTER", "PF")
        young_to_r = {"value": 26.0}   # what the rebuilder thinks of the young player; the buyer keeps its own 25
        patch = mock.patch.object(TradeFinder, "get_strategic_value", lambda f, a, tm, pp=None: (
            1.0 if isinstance(a, str) else young_to_r["value"] if (a is self.young and tm is self.r)
            else a._test_value))
        patch.start()
        self.addCleanup(patch.stop)
        self.assertFalse(star_upgrade.run(self.f, self.c, wish))   # fair for a normal seller, not exceptional
        self.assertIn(self.target, self.r.roster)
        young_to_r["value"] = 45.0   # exceptional for the seller (a rebuilder in love with youth), fair for the buyer
        self.assertTrue(star_upgrade.run(self.f, self.c, wish))
        self.assertIn(self.target, self.c.roster)

    def test_star_chaser_gets_a_star_without_a_hole(self):
        t, teams = league({"C": NO_HOLE, "R": SELLER}, {"C": "PLAYOFF", "R": "REBUILDER"})
        t.front_office.gms.clear()
        gm = make_gm("g1", traits=["STAR_CHASER"])
        gm.team = "C"
        t.front_office.gms["g1"] = gm
        t.front_office.seats["C"] = "g1"
        f = finder(t)
        c, r = teams["C"], teams["R"]
        star = old(player(r, "SF", 86), 31)
        star._test_value = 30.0
        young = old(player(c, "SG", 68), 24, 80)
        young._test_value = 30.0
        wish = wish_of(f, c, "WANT_STAR")
        self.assertTrue(star_upgrade.run(f, c, wish))
        self.assertIn(star, c.roster)
        self.assertEqual(t.trade_analytics_history[-1]["motives"][0]["wish_kind"], "WANT_STAR")

    def stuck_league(self, c_spec, c_salary):
        specs = {"C": c_spec, "R": SELLER}
        t, teams = league(specs, {"C": "CONTENDER", "R": "REBUILDER"})
        c, r = teams["C"], teams["R"]
        real_salary_rule(c, 50.0)
        real_salary_rule(r, 50.0)
        target = old(player(r, "PF", 80), 31)
        target.contract.salario_annuale = 9.0
        target._test_value = 24.0
        young = old(player(c, "SG", 68), 24, 80)
        young.contract.salario_annuale = c_salary
        young._test_value = 25.0
        return t, finder(t), c, r, target, young

    def test_two_for_one_closes_when_one_filler_cannot_match_the_salary(self):
        t, f, c, r, target, young = self.stuck_league(PF_HOLE_DEPTH, 1.0)
        target._test_value = 25.5   # the young player and the fillers (salary only) cover it
        for p in c.roster:
            p.contract.salario_annuale = 3.5
            p._test_value = 1.0
        young.contract.salario_annuale = 1.0
        young._test_value = 25.0
        self.assertTrue(star_upgrade.run(f, c, wish_of(f, c, "NEED_STARTER", "PF")))
        self.assertIn(target, c.roster)
        sent = [p for p in r.roster if p.nome.startswith("C-")]
        self.assertGreaterEqual(len(sent), 3)   # the young player and at least two contracts
        self.assertEqual(t.trade_analytics_history[-1]["trade_type"], "starter_upgrade")
        self.assertEqual(t.trade_analytics_history[-1]["team_count"], 2)

    def test_salary_stuck_upgrade_closes_as_facilitated_3team(self):
        specs = {"C": PF_HOLE, "R": SELLER, "X": ABSORBER}
        t, teams = league(specs, {"C": "CONTENDER", "R": "REBUILDER", "X": "MIDDLE"})
        f = finder(t)
        c, r, x = teams["C"], teams["R"], teams["X"]
        real_salary_rule(c, 50.0)
        real_salary_rule(r, 50.0)
        real_salary_rule(x, 30.0)
        target = old(player(r, "PF", 80), 31)
        target.contract.salario_annuale = 9.0
        target._test_value = 26.0
        player(c, "PF", 67)._test_value = 1.0   # the cheapest contract C can send to the absorbing team
        young = old(player(c, "SG", 68), 24, 80)
        young._test_value = 25.0
        self.assertTrue(star_upgrade.run(f, c, wish_of(f, c, "NEED_STARTER", "PF")))
        self.assertIn(target, c.roster)
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "facilitated_3team")
        self.assertEqual(rec["team_count"], 3)
        self.assertIn("ABSORB_SALARY", [m["wish_kind"] for m in rec["motives"]])

    def test_no_deal_when_the_would_be_seller_is_a_contender(self):
        t, teams = league({"C": PF_HOLE, "S": SELLER}, {"C": "CONTENDER", "S": "CONTENDER"})
        f = finder(t)
        c, s = teams["C"], teams["S"]
        old(player(s, "PF", 80), 28)
        self.assertEqual(f.wishes_for(s) and [w.kind for w in f.wishes_for(s) if w.kind in star_upgrade.PARTNER_KINDS], [])
        self.assertFalse(star_upgrade.run(f, c, wish_of(f, c, "NEED_STARTER", "PF")))
        self.assertEqual(t.trade_analytics_history, [])

    def test_a_contender_shedding_tax_still_will_not_sell_its_best_player(self):
        t, teams = league({"C": PF_HOLE, "S": SELLER}, {"C": "CONTENDER", "S": "CONTENDER"})
        f = finder(t)
        c, s = teams["C"], teams["S"]
        player(s, "SF", 86).valutazione = 70   # the target is the seller's best player
        target = old(player(s, "PF", 80), 28)
        target._test_value = 24.0
        target.contract.salario_annuale = 9.0
        s.payroll = 80.0   # over the tax line: SHED_TAX
        young = old(player(c, "SG", 68), 24, 80)
        young._test_value = 25.0
        self.assertIn("SHED_TAX", [w.kind for w in f.wishes_for(s)])
        with mock.patch.object(TradeFinder, "execute_deal", wraps=f.execute_deal) as ex:
            self.assertFalse(star_upgrade.run(f, c, wish_of(f, c, "NEED_STARTER", "PF")))
        ex.assert_not_called()
        self.assertIn(target, s.roster)

    def test_other_wish_kinds_are_not_served(self):
        wish = next(w for w in self.f.wishes_for(self.r) if w.kind == "WANT_PICKS")
        self.assertFalse(star_upgrade.run(self.f, self.r, wish))


class WinNowYouthTests(EngineTestCase):
    def build(self, partner_plan="REBUILDER", gms=None):
        t, teams = league({"C": PF_HOLE, "R": SELLER}, {"C": "CONTENDER", "R": partner_plan})
        if gms:
            for team, gm in gms.items():
                gm.team = team
                t.front_office.gms[gm.gm_id] = gm
                t.front_office.seats[team] = gm.gm_id
        f = finder(t)
        c, r = teams["C"], teams["R"]
        player(r, "SF", 86).valutazione = 70   # the veteran is the seller's best player
        vet = old(player(r, "PF", 80), 29)
        vet._test_value = 20.0
        prospect = old(player(c, "SG", 68), 24, 84)
        prospect._test_value = 20.0
        return t, f, c, r, vet, prospect

    def test_closes_prospect_for_prime_vet(self):
        t, f, c, r, vet, prospect = self.build()
        self.assertTrue(win_now_youth.run(f, c, wish_of(f, c, "NEED_STARTER", "PF")))
        self.assertIn(vet, c.roster)
        self.assertIn(prospect, r.roster)
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "win_now_youth")
        self.assertEqual([m["wish_kind"] for m in rec["motives"]], ["NEED_STARTER", "WANT_YOUTH"])

    def test_no_deal_when_the_vets_team_is_a_contender(self):
        t, f, c, r, vet, prospect = self.build(partner_plan="CONTENDER", gms={"R": make_gm("yf", traits=["YOUTH_FIRST"])})
        self.assertIn("WANT_YOUTH", [w.kind for w in f.wishes_for(r)])
        self.assertFalse(win_now_youth.run(f, c, wish_of(f, c, "NEED_STARTER", "PF")))
        self.assertIn(vet, r.roster)

    def test_no_deal_without_a_prospect(self):
        t, f, c, r, vet, prospect = self.build()
        prospect.potenziale = 70
        self.assertFalse(win_now_youth.run(f, c, wish_of(f, c, "NEED_STARTER", "PF")))

    def test_vet_outside_prime_ages_is_not_taken(self):
        t, f, c, r, vet, prospect = self.build()
        vet.eta = 35
        self.assertFalse(win_now_youth.run(f, c, wish_of(f, c, "NEED_STARTER", "PF")))


class RegistryTests(EngineTestCase):
    def test_both_engines_resolve(self):
        names = {e.name: e for e in engines.ENGINES["NEED_STARTER"]}
        self.assertIs(names["star_upgrade"].load(), star_upgrade.run)
        self.assertIs(names["win_now_youth"].load(), win_now_youth.run)
        self.assertEqual([e.name for e in engines.ENGINES["WANT_STAR"]], ["star_upgrade"])


if __name__ == "__main__":
    import unittest
    unittest.main()
