"""Money engines: tax dump (SHED_TAX / CLEAR_LONG_CONTRACT) and expiring for long contract."""
import dataclasses
import unittest
from unittest import mock

from core.config import CONFIG
from trades import engines
from trades.engines import expiring_for_long, tax_dump
from trades.trade_finder import TradeFinder
from tests.test_trade_engines_framework import (
    EngineTestCase, ABSORBER, league, player, real_salary_rule, wish_of)
from tests.trade_fixtures import era_of, finder

TAX = 48.0   # 2002: cap 40.27, tax about 48

# A team with a spread of mid players: the dumper.
DUMPER = [("PG", 72), ("PG", 66), ("SG", 76), ("SG", 66), ("SF", 72), ("SF", 66), ("PF", 72), ("PF", 66),
          ("C", 72), ("C", 66), ("SG", 62), ("SF", 62), ("PF", 62)]
# A contender with no starting PF (best PF 72): NEED_STARTER PF.
PF_HOLE = [("PG", 76), ("PG", 69), ("SG", 76), ("SG", 68), ("SF", 76), ("SF", 69), ("PF", 72), ("PF", 69),
           ("C", 76), ("C", 69), ("SG", 66), ("SF", 66), ("PF", 67)]
# A rebuilder holding a 73 PF (a rotation player: CLEAR_LONG_MAX_BAND) on a long heavy contract.
LONG_HOLDER = [("PG", 68), ("PG", 64), ("SG", 66), ("SG", 64), ("SF", 70), ("SF", 62), ("PF", 78), ("PF", 62),
               ("C", 66), ("C", 62), ("SG", 60), ("SF", 60), ("PF", 60)]


def contract(p, salary, years):
    p.contract.salario_annuale, p.contract.anni_rimanenti = salary, years
    return p


def owner_of(torneo, key):
    return {owners[key] for owners in torneo.pick_ownership.values()}


class MoneyTestCase(EngineTestCase):
    """The engines, not the wish thresholds: any owner sheds as soon as it is over the tax, now (no look-ahead)."""
    def setUp(self):
        super().setUp()
        self.era = era_of(tax=TAX)
        import core.front_office.wishes as wishes_module
        config = dataclasses.replace(CONFIG, TRADES=dataclasses.replace(
            CONFIG.TRADES, SHED_TAX_OVER_SHARE_BY_TIER={"low": 0.0, "mid": 0.0, "high": None},
            SHED_TAX_LOOK_AHEAD=False))
        for patch in (mock.patch.object(TradeFinder, "era", return_value=self.era),
                      mock.patch.object(wishes_module, "CONFIG", config)):
            patch.start()
            self.addCleanup(patch.stop)


class TaxDumpTests(MoneyTestCase):
    def build(self, dumper_payroll=54.0, dumper_big=None):
        """D (over the tax) and a rebuilder P with room. `dumper_big`: (role, ovr, salary, years) of D's big contract."""
        self.t, self.teams = league({"D": DUMPER, "P": ABSORBER}, {"D": "MIDDLE", "P": "REBUILDER"})
        self.d, self.p = self.teams["D"], self.teams["P"]
        real_salary_rule(self.d, dumper_payroll)
        real_salary_rule(self.p, 25.0)
        for q in self.d.roster + self.p.roster:
            q._test_value = 1.0
        role, ovr, salary, years = dumper_big or ("SG", 66, 9.0, 2)
        self.big = contract(player(self.d, role, ovr), salary, years)
        self.f = finder(self.t)

    def test_a_45m_payroll_holds_no_shed_tax_and_makes_no_dump(self):
        self.build(dumper_payroll=45.0)
        self.assertNotIn("SHED_TAX", [w.kind for w in self.f.wishes_for(self.d)])
        for wish in self.f.wishes_for(self.d):
            for engine in engines.engines_for(wish.kind):
                if engine.name == "tax_dump":
                    engine(self.f, self.d, wish)
        self.assertEqual(self.t.trade_analytics_history, [])
        self.assertIn(self.big, self.d.roster)

    def test_the_engine_itself_refuses_a_shed_tax_under_the_line(self):
        self.build(dumper_payroll=45.0)
        fake = dataclasses.replace(wish_of(self.f, self.p, "ABSORB_SALARY"), team="D", kind="SHED_TAX")
        self.assertFalse(tax_dump.run(self.f, self.d, fake))
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_54m_dumps_a_non_expiring_contract_to_the_rebuilder_for_a_second(self):
        self.build()
        wish = wish_of(self.f, self.d, "SHED_TAX")
        self.assertTrue(tax_dump.run(self.f, self.d, wish))
        self.assertIn(self.big, self.p.roster)
        rec = self.t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "tax_dump")
        self.assertEqual(rec["motives"][0]["wish_kind"], "SHED_TAX")
        self.assertEqual(rec["motives"][1]["wish_kind"], "ABSORB_SALARY")
        self.assertIn("P", owner_of(self.t, "R2-D"))
        self.assertEqual(owner_of(self.t, "R1-D"), {"D"})

    def test_a_high_long_contract_costs_a_first(self):
        self.build(dumper_big=("SG", 66, 9.0, 4))
        self.assertTrue(self.era.is_high_contract(9.0, 4))
        self.assertTrue(tax_dump.run(self.f, self.d, wish_of(self.f, self.d, "SHED_TAX")))
        self.assertIn(self.big, self.p.roster)
        self.assertIn("P", owner_of(self.t, "R1-D"))
        self.assertEqual(owner_of(self.t, "R2-D"), {"D"})

    def test_an_expiring_starter_is_never_dumped(self):
        self.build(dumper_big=("SG", 76, 9.0, 1))
        for q in self.d.roster:
            if q is not self.big:
                contract(q, 1.0, 2)   # nothing else is big enough to cut the tax bill
        self.assertFalse(tax_dump.run(self.f, self.d, wish_of(self.f, self.d, "SHED_TAX")))
        self.assertIn(self.big, self.d.roster)
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_an_expiring_starter_stays_while_another_contract_goes(self):
        self.build(dumper_big=("SG", 76, 9.0, 1))
        contract(player(self.d, "SF", 66), 7.0, 2)
        self.assertTrue(tax_dump.run(self.f, self.d, wish_of(self.f, self.d, "SHED_TAX")))
        self.assertIn(self.big, self.d.roster)

    def test_no_cap_has_no_shed_tax_and_no_dump(self):
        self.build()
        self.era = dataclasses.replace(self.era, no_cap=True)
        with mock.patch.object(TradeFinder, "era", return_value=self.era):
            f = finder(self.t)
            self.assertNotIn("SHED_TAX", [w.kind for w in f.wishes_for(self.d)])
            fake = dataclasses.replace(wish_of(f, self.p, "ABSORB_SALARY"), team="D", kind="SHED_TAX")
            self.assertFalse(tax_dump.run(f, self.d, fake))
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_clear_long_contract_dumps_that_player(self):
        self.t, self.teams = league({"L": LONG_HOLDER, "P": ABSORBER}, {"L": "REBUILDER", "P": "MIDDLE"})
        l, p = self.teams["L"], self.teams["P"]
        real_salary_rule(l, 30.0)
        real_salary_rule(p, 25.0)
        for q in l.roster + p.roster:
            q._test_value = 1.0
        import core.front_office.wishes as wishes_module   # the holder is a 78: a CLEAR_LONG player only in the old starter band
        config = dataclasses.replace(wishes_module.CONFIG, TRADES=dataclasses.replace(
            wishes_module.CONFIG.TRADES, CLEAR_LONG_MAX_BAND="starter"))
        patch = mock.patch.object(wishes_module, "CONFIG", config)
        patch.start()
        self.addCleanup(patch.stop)
        long = contract(player(l, "PF", 78), 9.0, 4)
        f = finder(self.t)
        wish = wish_of(f, l, "CLEAR_LONG_CONTRACT")
        self.assertEqual(wish.player, long.nome)
        self.assertTrue(tax_dump.run(f, l, wish))
        self.assertIn(long, p.roster)
        self.assertEqual(self.t.trade_analytics_history[-1]["trade_type"], "tax_dump")

    def test_an_absorber_that_would_go_over_the_tax_is_not_used(self):
        self.build()
        self.p.payroll = 44.0   # 44 + 9 > 48
        self.assertFalse(tax_dump.run(self.f, self.d, wish_of(self.f, self.d, "SHED_TAX")))
        self.assertIn(self.big, self.d.roster)

    def test_a_protected_top_5_first_is_not_given_in_a_dump(self):
        self.build(dumper_big=("SG", 66, 9.0, 4))   # a high long contract: priced with a first
        for q in self.d.roster:
            if q is not self.big:
                contract(q, 1.0, 2)   # nothing else is big enough to cut the tax bill
        with mock.patch.object(TradeFinder, "_is_top5_pick", return_value=True):
            self.assertFalse(tax_dump.run(self.f, self.d, wish_of(self.f, self.d, "SHED_TAX")))
        self.assertIn(self.big, self.d.roster)
        self.assertEqual(owner_of(self.t, "R1-D"), {"D"})
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_the_other_wish_kinds_are_not_served(self):
        self.build()
        self.assertFalse(tax_dump.run(self.f, self.d, wish_of(self.f, self.p, "ABSORB_SALARY")))

    def test_registered_for_both_initiator_wishes(self):
        for kind in ("SHED_TAX", "CLEAR_LONG_CONTRACT"):
            self.assertIn("tax_dump", [e.name for e in engines.engines_for(kind)])


def starter_band_clear_long(test):
    """expiring_for_long needs a seller whose player is a starter for the partner: the engine is tested with the old
    CLEAR_LONG_MAX_BAND (starter). In the default config (rotation) a CLEAR_LONG player cannot be a starter."""
    old = CONFIG.TRADES.CLEAR_LONG_MAX_BAND
    object.__setattr__(CONFIG.TRADES, "CLEAR_LONG_MAX_BAND", "starter")
    test.addCleanup(object.__setattr__, CONFIG.TRADES, "CLEAR_LONG_MAX_BAND", old)


class ExpiringForLongTests(MoneyTestCase):
    def setUp(self):
        starter_band_clear_long(self)
        super().setUp()
        self.t, self.teams = league({"L": LONG_HOLDER, "C": PF_HOLE}, {"L": "REBUILDER", "C": "CONTENDER"})
        self.l, self.c = self.teams["L"], self.teams["C"]
        real_salary_rule(self.l, 50.0)
        real_salary_rule(self.c, 50.0)
        for q in self.l.roster + self.c.roster:
            q._test_value = 1.0
        self.long = contract(player(self.l, "PF", 78), 9.0, 4)
        self.long._test_value = 10.0
        self.exp = [contract(player(self.c, "SG", 66), 4.5, 1), contract(player(self.c, "SF", 66), 4.5, 1)]
        self.long._test_value_for = {"L": 7.5, "C": 9.0}   # a burden to the rebuilder, a starter to the contender
        for p, v in zip(self.exp, (7.0, 1.0)):
            p._test_value = v   # the rebuilder's price question: the second player counts at RECEIVED_PLAYER_SHARES[1]
        self.f = finder(self.t)

    def test_a_four_year_contract_for_two_expirings_and_a_second(self):
        wish = wish_of(self.f, self.l, "CLEAR_LONG_CONTRACT")
        self.assertTrue(expiring_for_long.run(self.f, self.l, wish))
        self.assertIn(self.long, self.c.roster)
        for p in self.exp:
            self.assertIn(p, self.l.roster)
        self.assertIn("L", owner_of(self.t, "R2-C"))
        rec = self.t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "expiring_for_long")
        self.assertEqual(rec["motives"][0]["wish_kind"], "CLEAR_LONG_CONTRACT")
        self.assertIn(rec["motives"][1]["wish_kind"], ("NEED_STARTER", "WANT_STAR"))

    def test_a_partner_that_does_not_want_him_now_means_no_trade(self):
        t, teams = league({"L": LONG_HOLDER, "A": ABSORBER}, {"L": "REBUILDER", "A": "MIDDLE"})
        real_salary_rule(teams["L"], 50.0)
        real_salary_rule(teams["A"], 50.0)
        f = finder(t)
        long = contract(player(teams["L"], "PF", 78), 9.0, 4)
        wish = wish_of(f, teams["L"], "CLEAR_LONG_CONTRACT")
        self.assertFalse(expiring_for_long.run(f, teams["L"], wish))
        self.assertIn(long, teams["L"].roster)

    def test_other_wish_kinds_are_not_served(self):
        self.assertFalse(expiring_for_long.run(self.f, self.l, wish_of(self.f, self.l, "WANT_PICKS")))

    def test_registered_for_clear_long_contract_first(self):
        names = [e.name for e in engines.engines_for("CLEAR_LONG_CONTRACT")]
        self.assertEqual(names[:2], ["expiring_for_long", "tax_dump"])


class ExpiringForLongRotationTests(MoneyTestCase):
    """The default config wishes CLEAR_LONG_CONTRACT only for a player below the starter band: the partner who wants
    him is a team thin at his role (DEPTH_NEEDED), not one looking for a starter."""
    def test_a_rotation_player_on_a_long_deal_goes_to_a_team_thin_at_his_role(self):
        holder = [(r, 73 if (r, o) == ("PF", 78) else o) for r, o in LONG_HOLDER]
        t, teams = league({"L": holder, "C": PF_HOLE}, {"L": "REBUILDER", "C": "CONTENDER"})
        l, c = teams["L"], teams["C"]
        real_salary_rule(l, 50.0)
        real_salary_rule(c, 50.0)
        for q in l.roster + c.roster:
            q._test_value = 1.0
        long = contract(player(l, "PF", 73), 9.0, 4)
        long._test_value = 10.0
        exp = [contract(player(c, "SG", 66), 4.5, 1), contract(player(c, "SF", 66), 4.5, 1)]
        long._test_value_for = {"L": 7.5, "C": 9.0}
        for p, v in zip(exp, (7.0, 1.0)):
            p._test_value = v
        f = finder(t)
        wish = wish_of(f, l, "CLEAR_LONG_CONTRACT")
        self.assertTrue(expiring_for_long.run(f, l, wish))
        self.assertIn(long, c.roster)
        self.assertEqual(t.trade_analytics_history[-1]["motives"][1]["wish_kind"], "DEPTH_NEEDED")


class ExpiringForLongRealValueTests(unittest.TestCase):
    """No `_test_value` overrides: the real strategic values decide, as in a league."""
    def setUp(self):
        starter_band_clear_long(self)
        patches = [
            mock.patch.object(TradeFinder, "_log_trade_to_file"),
            mock.patch("core.news_generator.add_news"),
            mock.patch.object(TradeFinder, "era", return_value=era_of(tax=TAX)),
            mock.patch("trades.trade_finder.random.uniform", return_value=0.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.t, self.teams = league({"L": LONG_HOLDER, "C": PF_HOLE}, {"L": "REBUILDER", "C": "CONTENDER"})
        self.l, self.c = self.teams["L"], self.teams["C"]
        real_salary_rule(self.l, 50.0)
        real_salary_rule(self.c, 50.0)
        self.long = contract(player(self.l, "PF", 78), 9.0, 4)   # a 31-year-old starter on a high 4-year deal
        self.long.eta = 31
        self.exp = [contract(player(self.c, "SG", 66), 4.5, 1), contract(player(self.c, "SF", 66), 4.5, 1)]
        self.f = finder(self.t)

    def test_with_real_values_nobody_pays_a_first_for_a_78_on_a_long_deal(self):
        # FIRST_PICK_MIN_OVR: the contender won't add a first for a player under 80, and two 66s and a second
        # don't cover the 78 for the rebuilder: the contract stays (a tax dump, paid by the rebuilder, can move it).
        wish = wish_of(self.f, self.l, "CLEAR_LONG_CONTRACT")
        self.assertFalse(expiring_for_long.run(self.f, self.l, wish))
        self.assertIn(self.long, self.l.roster)

    def test_with_real_values_fringe_expirings_do_not_change_it(self):
        for p in self.exp:
            p.valutazione = 35
        wish = wish_of(self.f, self.l, "CLEAR_LONG_CONTRACT")
        self.assertFalse(expiring_for_long.run(self.f, self.l, wish))
