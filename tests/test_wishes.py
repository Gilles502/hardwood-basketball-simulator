import dataclasses
import random
import unittest
from types import SimpleNamespace
from unittest import mock

from core.config import CONFIG
from core.front_office.era_lines import EraLines
from core.front_office.wishes import (KINDS, Wish, WishContext, build_wishes, fulfils, plan_hard_no, wants_out)
from tests.trade_fixtures import make_gm, make_player
from trades.motive import REASON_TEMPLATES, TRAIT_REASONS, WHY_PHRASES

ERA = EraLines(year=2003, cap=40.0, tax=49.0, minimum=0.5, mle=5.0, no_cap=False, star=85, core=80, starter=75,
               rotation=70, bench=62, salary_pcts={0.9: 15.0, 0.6: 5.0}, pick_scale=1.0)
ERA_NO_CAP = EraLines(year=2003, cap=9999.0, tax=9999.0, minimum=0.5, mle=5.0, no_cap=True, star=85, core=80,
                      starter=75, rotation=70, bench=62, salary_pcts={0.9: 15.0, 0.6: 5.0}, pick_scale=1.0)
ROLES = ["PG", "SG", "SF", "PF", "C"]


def balanced(prefix="B", ovr=77, n=10):
    """A roster with 2 starters-level players per role: no NEED_STARTER, no DEPTH_NEEDED, no congestion."""
    return [make_player(f"{prefix}{i}", ovr=ovr - (i // 5), age=27, salary=3.0, years=2, role=ROLES[i % 5])
            for i in range(n)]


def team_of(players, payroll=40.0, name="Team"):
    return SimpleNamespace(nome=name, roster=players, payroll=payroll)


def ctx_of(plan="MIDDLE", gm=None, era=ERA, owner="Normale", window="user", win_pct=0.5, games=60, r1=False, **kw):
    return WishContext(era=era, plan=plan, gm=gm, owner=owner, window=window, win_pct=win_pct, games=games,
                       has_r1_this_year=r1, **kw)


def kinds(wishes):
    return {w.kind for w in wishes}


def roster_with(*extra, base=None):
    return (base if base is not None else balanced()) + list(extra)


def tuned(**trades):
    """CONFIG.TRADES with these numbers changed, as core.front_office.wishes sees it."""
    import core.front_office.wishes as wishes_module
    config = dataclasses.replace(CONFIG, TRADES=dataclasses.replace(CONFIG.TRADES, **trades))
    return mock.patch.object(wishes_module, "CONFIG", config)


class BuildWishesTests(unittest.TestCase):
    def test_need_starter(self):
        weak = [p for p in balanced() if p.ruolo != "C"] + [make_player("c1", ovr=60, role="C"), make_player("c2", ovr=72, role="C")]
        w = [x for x in build_wishes(team_of(weak), ctx_of("CONTENDER")) if x.kind == "NEED_STARTER"]
        self.assertEqual([x.role for x in w], ["C"])
        self.assertNotIn("NEED_STARTER", kinds(build_wishes(team_of(weak), ctx_of("MIDDLE"))))
        self.assertNotIn("NEED_STARTER", kinds(build_wishes(team_of(balanced()), ctx_of("CONTENDER"))))

    def test_want_star(self):
        t = team_of(balanced())
        self.assertIn("WANT_STAR", kinds(build_wishes(t, ctx_of("CONTENDER"))))
        self.assertNotIn("WANT_STAR", kinds(build_wishes(t, ctx_of("PLAYOFF"))))
        chaser = ctx_of("PLAYOFF", gm=make_gm("g", ["STAR_CHASER"]))
        self.assertIn("WANT_STAR", kinds(build_wishes(t, chaser)))
        starred = team_of(roster_with(make_player("S", ovr=90, role="PG")))
        self.assertNotIn("WANT_STAR", kinds(build_wishes(starred, ctx_of("CONTENDER"))))
        self.assertNotIn("WANT_STAR", kinds(build_wishes(t, ctx_of("REBUILDER", gm=make_gm("g", ["STAR_CHASER"])))))

    def test_star_wants_out(self):
        star = make_player("Star", ovr=86, age=31, role="SF")
        star.trade_request = True   # an open request (core/front_office/trade_requests.py)
        t = team_of(roster_with(star))
        w = [x for x in build_wishes(t, ctx_of("REBUILDER")) if x.kind == "STAR_WANTS_OUT"]
        self.assertEqual([x.player for x in w], ["Star"])
        star.trade_request = False
        self.assertNotIn("STAR_WANTS_OUT", kinds(build_wishes(t, ctx_of("REBUILDER"))))

    def test_sell_veterans(self):
        vet = make_player("Vet", ovr=75, age=33, role="SF")
        t = team_of(roster_with(vet))
        self.assertIn("SELL_VETERANS", kinds(build_wishes(t, ctx_of("REBUILDER"))))
        self.assertNotIn("SELL_VETERANS", kinds(build_wishes(t, ctx_of("MIDDLE"))))
        self.assertNotIn("SELL_VETERANS", kinds(build_wishes(team_of(balanced()), ctx_of("REBUILDER"))))

    def test_sell_veterans_pick_hoarder_chance_uses_rng(self):
        vet = make_player("Vet", ovr=75, age=33, role="SF")
        t = team_of(roster_with(vet))
        ctx = ctx_of("MIDDLE", gm=make_gm("g", ["PICK_HOARDER"]))
        always = SimpleNamespace(random=lambda: 0.0)
        never = SimpleNamespace(random=lambda: 0.99)
        self.assertIn("SELL_VETERANS", kinds(build_wishes(t, ctx, rng=always)))
        self.assertNotIn("SELL_VETERANS", kinds(build_wishes(t, ctx, rng=never)))

    def test_want_picks_and_youth(self):
        t = team_of(balanced())
        self.assertIn("WANT_PICKS", kinds(build_wishes(t, ctx_of("REBUILDER"))))
        self.assertIn("WANT_PICKS", kinds(build_wishes(t, ctx_of("CONTENDER", gm=make_gm("g", ["PICK_HOARDER"])))))
        self.assertNotIn("WANT_PICKS", kinds(build_wishes(t, ctx_of("CONTENDER"))))
        self.assertIn("WANT_YOUTH", kinds(build_wishes(t, ctx_of("MIDDLE", gm=make_gm("g", ["YOUTH_FIRST"])))))
        self.assertNotIn("WANT_YOUTH", kinds(build_wishes(t, ctx_of("MIDDLE"))))

    def test_shed_tax(self):
        over = team_of(balanced(), payroll=60.0)
        with tuned(SHED_TAX_OVER_SHARE_BY_TIER={"low": 0.0, "mid": 0.0, "high": None}, SHED_TAX_LOOK_AHEAD=False):
            self.assertIn("SHED_TAX", kinds(build_wishes(over, ctx_of())))
            self.assertNotIn("SHED_TAX", kinds(build_wishes(team_of(balanced(), payroll=40.0), ctx_of())))
            self.assertNotIn("SHED_TAX", kinds(build_wishes(over, ctx_of(era=ERA_NO_CAP))))

    def test_before_the_aprons_only_a_team_far_over_the_tax_sheds(self):
        # 2002 defaults: a mid owner sheds only 40% of the cap over the tax (49 + 16 = 65).
        far = [make_player(f"F{i}", ovr=77, salary=7.0, years=3, role=ROLES[i % 5]) for i in range(10)]   # 70 next year
        self.assertNotIn("SHED_TAX", kinds(build_wishes(team_of(far, payroll=60.0), ctx_of())))
        self.assertIn("SHED_TAX", kinds(build_wishes(team_of(far, payroll=70.0), ctx_of())))
        self.assertNotIn("SHED_TAX", kinds(build_wishes(team_of(far, payroll=70.0), ctx_of(owner="Spendaccione"))))

    def test_a_team_that_gets_under_by_itself_next_season_waits(self):
        # 70 this season, but 7 of the 10 contracts expire: 21 next season.
        roster = [make_player(f"F{i}", ovr=77, salary=7.0, years=3 if i < 3 else 1, role=ROLES[i % 5])
                  for i in range(10)]
        self.assertNotIn("SHED_TAX", kinds(build_wishes(team_of(roster, payroll=70.0), ctx_of(window="deadline"))))
        with tuned(SHED_TAX_LOOK_AHEAD=False):
            self.assertIn("SHED_TAX", kinds(build_wishes(team_of(roster, payroll=70.0), ctx_of(window="deadline"))))

    def test_with_aprons_every_owner_sheds_down_to_the_second_apron(self):
        aprons = dataclasses.replace(ERA, second_apron=60.0)
        far = [make_player(f"F{i}", ovr=77, salary=6.5, years=3, role=ROLES[i % 5]) for i in range(10)]   # 65
        spender = ctx_of(era=aprons, owner="Spendaccione")
        self.assertIn("SHED_TAX", kinds(build_wishes(team_of(far, payroll=65.0), spender)))
        self.assertNotIn("SHED_TAX", kinds(build_wishes(team_of(far, payroll=59.0), spender)))   # over the tax only
        w = Wish("SHED_TAX", "Team", 0.0, "")
        big = make_player("Big", ovr=70, salary=5.0)
        self.assertTrue(fulfils(w, [], [big], team_of(far, payroll=65.0), aprons))       # 65 - 5 = 60: under
        self.assertFalse(fulfils(w, [], [big], team_of(far, payroll=66.0), aprons))

    def test_shed_tax_priority_up_with_saver_owner_and_guardian(self):
        over = team_of(balanced(), payroll=60.0)
        prio = lambda c: next(w.priority for w in build_wishes(over, c) if w.kind == "SHED_TAX")
        with tuned(SHED_TAX_OVER_SHARE_BY_TIER={"low": 0.0, "mid": 0.0, "high": None}, SHED_TAX_LOOK_AHEAD=False):
            base = prio(ctx_of())
            self.assertGreater(prio(ctx_of(owner="Risparmiatore")), base)
            self.assertGreater(prio(ctx_of(gm=make_gm("g", ["CAP_GUARDIAN"]))), base)

    def test_clear_long_contract(self):
        heavy = make_player("Heavy", ovr=72, salary=20.0, years=4, role="SF")
        t = team_of(roster_with(heavy))
        w = [x for x in build_wishes(t, ctx_of("REBUILDER")) if x.kind == "CLEAR_LONG_CONTRACT"]
        self.assertEqual([x.player for x in w], ["Heavy"])
        self.assertIn("CLEAR_LONG_CONTRACT", kinds(build_wishes(t, ctx_of("MIDDLE", gm=make_gm("g", ["CAP_GUARDIAN"])))))
        self.assertNotIn("CLEAR_LONG_CONTRACT", kinds(build_wishes(t, ctx_of("MIDDLE"))))
        heavy.contract.anni_rimanenti = 2
        self.assertNotIn("CLEAR_LONG_CONTRACT", kinds(build_wishes(t, ctx_of("REBUILDER"))))
        star = make_player("Star", ovr=88, salary=25.0, years=5, role="SF")
        self.assertNotIn("CLEAR_LONG_CONTRACT", kinds(build_wishes(team_of(roster_with(star)), ctx_of("REBUILDER"))))

    def test_a_core_player_or_a_young_one_is_no_bad_contract(self):
        # Bibby (83, 24 years old) or Ilgauskas (84) on a big deal are not contracts to pay a first to get rid of.
        clears = lambda p: "CLEAR_LONG_CONTRACT" in kinds(build_wishes(team_of(roster_with(p)), ctx_of("REBUILDER")))
        self.assertFalse(clears(make_player("Core", ovr=ERA.core, age=29, salary=20.0, years=4, role="SF")))
        self.assertFalse(clears(make_player("Starter", ovr=ERA.starter, age=29, salary=20.0, years=4, role="SF")))   # a 79: no
        self.assertTrue(clears(make_player("Rotation", ovr=ERA.starter - 1, age=29, salary=20.0, years=4, role="SF")))
        self.assertFalse(clears(make_player("Young", ovr=72, age=24, salary=20.0, years=4, role="SF")))

    def test_absorb_salary_and_no_cap(self):
        t = team_of(balanced(), payroll=40.0)
        self.assertIn("ABSORB_SALARY", kinds(build_wishes(t, ctx_of("MIDDLE"))))
        self.assertIn("ABSORB_SALARY", kinds(build_wishes(t, ctx_of("CONTENDER", gm=make_gm("g", ["PICK_HOARDER"])))))
        self.assertNotIn("ABSORB_SALARY", kinds(build_wishes(t, ctx_of("CONTENDER"))))
        self.assertNotIn("ABSORB_SALARY", kinds(build_wishes(team_of(balanced(), payroll=60.0), ctx_of("MIDDLE"))))
        no_cap = build_wishes(team_of(balanced(), payroll=5000.0), ctx_of("MIDDLE", era=ERA_NO_CAP))
        self.assertIn("ABSORB_SALARY", kinds(no_cap))
        self.assertNotIn("SHED_TAX", kinds(no_cap))

    def test_role_congestion(self):
        pgs = [make_player(f"pg{i}", ovr=78, role="PG") for i in range(3)]
        t = team_of(balanced() + pgs)
        w = [x for x in build_wishes(t, ctx_of()) if x.kind == "ROLE_CONGESTION"]
        self.assertTrue(w and all(x.role == "PG" for x in w))
        self.assertNotIn("ROLE_CONGESTION", kinds(build_wishes(team_of(balanced()), ctx_of())))

    def test_depth_needed(self):
        no_c = [p for p in balanced() if p.ruolo != "C"]
        w = [x for x in build_wishes(team_of(no_c), ctx_of()) if x.kind == "DEPTH_NEEDED"]
        self.assertEqual([x.role for x in w], ["C"])
        self.assertNotIn("DEPTH_NEEDED", kinds(build_wishes(team_of(balanced()), ctx_of())))

    def test_rent_veteran(self):
        t = team_of(balanced())
        self.assertIn("RENT_VETERAN", kinds(build_wishes(t, ctx_of("CONTENDER", window="deadline"))))
        self.assertNotIn("RENT_VETERAN", kinds(build_wishes(t, ctx_of("CONTENDER", window="predraft"))))
        self.assertNotIn("RENT_VETERAN", kinds(build_wishes(t, ctx_of("MIDDLE", window="deadline"))))

    def test_sell_expiring(self):
        exp = make_player("Exp", ovr=74, age=31, years=1, role="SF")
        t = team_of(roster_with(exp))
        w = build_wishes(t, ctx_of("REBUILDER", window="deadline"))
        self.assertEqual([x.player for x in w if x.kind == "SELL_EXPIRING"], ["Exp"])
        out_of_race = ctx_of("MIDDLE", window="deadline", win_pct=0.30, games=60)
        self.assertIn("SELL_EXPIRING", kinds(build_wishes(t, out_of_race)))
        early = ctx_of("MIDDLE", window="deadline", win_pct=0.30, games=10)
        self.assertNotIn("SELL_EXPIRING", kinds(build_wishes(t, early)))
        self.assertNotIn("SELL_EXPIRING", kinds(build_wishes(t, ctx_of("REBUILDER", window="user"))))

    def test_unhappy_player_not_when_wants_out(self):
        sad = make_player("Sad", ovr=ERA.core, role="SF")
        sad.morale = 40
        t = team_of(roster_with(sad))
        self.assertEqual([x.player for x in build_wishes(t, ctx_of()) if x.kind == "UNHAPPY_PLAYER"], ["Sad"])
        star = make_player("Star", ovr=86, age=31, role="PG")
        star.morale, star.trade_request = 30, True
        w = build_wishes(team_of(roster_with(star)), ctx_of("REBUILDER"))
        self.assertIn("STAR_WANTS_OUT", kinds(w))
        self.assertNotIn("UNHAPPY_PLAYER", kinds(w))

    def test_unhappy_player_needs_the_min_band(self):
        def unhappy(ovr, band):
            sad = make_player("Sad", ovr=ovr, role="SF")
            sad.morale = 10
            with tuned(UNHAPPY_MIN_BAND=band):
                return [x.player for x in build_wishes(team_of(roster_with(sad)), ctx_of()) if x.kind == "UNHAPPY_PLAYER"]
        self.assertEqual(unhappy(ERA.starter, "starter"), ["Sad"])
        self.assertEqual(unhappy(ERA.starter - 1, "starter"), [])
        self.assertEqual(unhappy(ERA.bench - 1, "fringe"), ["Sad"])

    def test_unknown_unhappy_band_is_a_clear_error(self):
        with tuned(UNHAPPY_MIN_BAND="corr"), self.assertRaisesRegex(ValueError, "UNHAPPY_MIN_BAND.*'corr'"):
            build_wishes(team_of(balanced()), ctx_of())

    def test_shed_tax_margin_by_owner_spending_tier(self):
        margin = 0.1 * ERA.cap
        just_over = team_of(balanced(), payroll=ERA.tax + margin - 0.5)
        well_over = team_of(balanced(), payroll=ERA.tax + margin + 0.5)
        sheds = lambda team, **kw: "SHED_TAX" in kinds(build_wishes(team, ctx_of(**kw)))
        with tuned(SHED_TAX_OVER_SHARE_BY_TIER={"low": 0.0, "mid": 0.1, "high": None}, SHED_TAX_LOOK_AHEAD=False):
            self.assertFalse(sheds(just_over))                            # "Normale": a mid owner
            self.assertTrue(sheds(well_over))
            self.assertTrue(sheds(just_over, owner="Risparmiatore"))      # a saver sheds any amount over the tax
            self.assertFalse(sheds(well_over, owner="Spendaccione"))      # a spender pays the tax
            self.assertTrue(sheds(just_over, owner="Spendaccione", gm=make_gm("g", ["CAP_GUARDIAN"])))   # GM as saver
            self.assertFalse(sheds(team_of(balanced(), payroll=ERA.tax - 0.5), owner="Risparmiatore"))

    def test_bench_hole(self):
        t = team_of(balanced())
        scrub = make_player("Scrub", ovr=50, role="SG")
        holey = team_of(roster_with(scrub))
        self.assertEqual([x.player for x in build_wishes(holey, ctx_of()) if x.kind == "BENCH_HOLE"], ["Scrub"])
        self.assertNotIn("BENCH_HOLE", kinds(build_wishes(t, ctx_of())))

    def test_draft_wishes(self):
        t = team_of(balanced())
        hoarder = make_gm("g", ["PICK_HOARDER"])
        self.assertIn("MOVE_UP_DRAFT", kinds(build_wishes(t, ctx_of("REBUILDER", window="predraft", r1=True, move_up_slot=4))))
        self.assertNotIn("MOVE_UP_DRAFT", kinds(build_wishes(t, ctx_of("REBUILDER", window="predraft", r1=True))))   # no prospect in mind
        self.assertNotIn("MOVE_UP_DRAFT", kinds(build_wishes(t, ctx_of("MIDDLE", gm=hoarder, window="predraft", r1=True,
                                                                       move_up_slot=4))))   # a hoarder only moves down
        w = next(x for x in build_wishes(t, ctx_of("REBUILDER", window="predraft", r1=True, move_up_slot=4)) if x.kind == "MOVE_UP_DRAFT")
        self.assertEqual(w.get("slot"), 4)
        self.assertNotIn("MOVE_UP_DRAFT", kinds(build_wishes(t, ctx_of("REBUILDER", window="predraft", r1=False))))
        self.assertNotIn("MOVE_UP_DRAFT", kinds(build_wishes(t, ctx_of("REBUILDER", window="deadline", r1=True))))
        self.assertNotIn("MOVE_UP_DRAFT", kinds(build_wishes(t, ctx_of("MIDDLE", window="draft", r1=True))))
        self.assertIn("MOVE_DOWN_DRAFT", kinds(build_wishes(t, ctx_of("MIDDLE", gm=hoarder, window="draft", r1=True))))
        self.assertNotIn("MOVE_DOWN_DRAFT", kinds(build_wishes(t, ctx_of("REBUILDER", window="draft", r1=True))))

    def test_target_prospect(self):
        t = team_of(balanced())
        ctx = ctx_of("MIDDLE", window="draft", prospects=(("C", "2003:R1-Team"),), move_up_slot=3,
                     move_up_pick="2003:R1-Team")
        w = [x for x in build_wishes(t, ctx) if x.kind == "TARGET_PROSPECT"]
        self.assertEqual([(x.role, x.get("pick")) for x in w], [("C", "2003:R1-Team")])
        self.assertNotIn("TARGET_PROSPECT", kinds(build_wishes(t, ctx_of("MIDDLE", window="draft",
                                                                         prospects=(("C", "2003:R1-Team"),)))))   # no target
        self.assertNotIn("TARGET_PROSPECT", kinds(build_wishes(t, ctx_of("MIDDLE", window="predraft", move_up_slot=3,
                                                                         move_up_pick="2003:R1-Team"))))

    def test_a_rebuilder_gives_a_young_player_only_for_the_prospect_it_wants(self):
        young = make_player("Kid", ovr=82, age=23, role="SF")
        t = team_of(balanced() + [young])
        plain = ctx_of("REBUILDER", window="predraft", r1=True)
        self.assertIsNotNone(plan_hard_no(t, plain, ["2003:R1-Team"], [young]))
        his_man = ctx_of("REBUILDER", window="predraft", r1=True, move_up_slot=1, move_up_pick="2003:R1-Team")
        self.assertIsNone(plan_hard_no(t, his_man, ["2003:R1-Team"], [young]))

    def test_every_built_kind_is_known(self):
        star = make_player("Star", ovr=86, age=31, role="SF")
        star.morale = 30
        t = team_of(balanced() + [star, make_player("Scrub", ovr=50)], payroll=60.0)
        ctx = ctx_of("REBUILDER", gm=make_gm("g", ["PICK_HOARDER", "TRADE_HAPPY"]), window="draft", r1=True,
                     owner="Risparmiatore")
        self.assertTrue(kinds(build_wishes(t, ctx)) <= set(KINDS))

    def test_sorted_by_priority(self):
        star = make_player("Star", ovr=86, age=31, role="SF")
        star.morale = 30
        t = team_of(balanced() + [star, make_player("Scrub", ovr=50)], payroll=60.0)
        ws = build_wishes(t, ctx_of("REBUILDER", gm=make_gm("g", ["TRADE_HAPPY"])))
        self.assertGreater(len(ws), 3)
        self.assertEqual([w.priority for w in ws], sorted((w.priority for w in ws), reverse=True))

    def test_no_front_office_gm_none(self):
        ws = build_wishes(team_of(balanced()), ctx_of("REBUILDER", gm=None))
        self.assertIn("WANT_PICKS", kinds(ws))

    def test_small_and_empty_rosters(self):
        for roster in (balanced(n=5), []):
            for plan in ("CONTENDER", "REBUILDER", "MIDDLE", "PLAYOFF"):
                ws = build_wishes(team_of(roster), ctx_of(plan, gm=make_gm("g", ["TRADE_HAPPY"]), window="deadline"))
                self.assertIsInstance(ws, list)

    def test_deterministic(self):
        t = team_of(balanced())
        c = ctx_of("REBUILDER")
        self.assertEqual(build_wishes(t, c), build_wishes(t, c))


class FulfilsTests(unittest.TestCase):
    def setUp(self):
        self.t = team_of(balanced(), payroll=40.0)

    def W(self, kind, **kw):
        return Wish(kind, "Team", 1.0, "r", **kw)

    def f(self, wish, receives=(), gives=(), team=None):
        return fulfils(wish, list(receives), list(gives), team or self.t, ERA)

    def test_need_starter(self):
        w = self.W("NEED_STARTER", role="C")
        self.assertTrue(self.f(w, [make_player("n", ovr=80, role="C")]))
        self.assertFalse(self.f(w, [make_player("n", ovr=80, role="PG")]))
        self.assertFalse(self.f(w, [make_player("n", ovr=70, role="C")]))
        self.assertFalse(self.f(w, [make_player("n", ovr=75, role="C")]))   # not better than the current 77/76 C

    def test_want_star(self):
        w = self.W("WANT_STAR")
        self.assertTrue(self.f(w, [make_player("s", ovr=85)]))
        self.assertFalse(self.f(w, [make_player("s", ovr=84)]))

    def test_star_wants_out_and_unhappy(self):
        for kind in ("STAR_WANTS_OUT", "UNHAPPY_PLAYER"):
            w = self.W(kind, player="B0")
            self.assertTrue(self.f(w, gives=[self.t.roster[0]]))
            self.assertFalse(self.f(w, gives=[self.t.roster[1]]))

    def test_sell_veterans(self):
        vet = make_player("v", ovr=75, age=33)
        w = self.W("SELL_VETERANS")
        self.assertTrue(self.f(w, ["2003:R1-X"], [vet]))
        self.assertTrue(self.f(w, [make_player("y", age=22)], [vet]))
        self.assertFalse(self.f(w, [make_player("y", age=28)], [vet]))
        self.assertFalse(self.f(w, ["2003:R1-X"], [make_player("young", ovr=75, age=25)]))
        self.assertFalse(self.f(w, ["2003:R1-X"], [make_player("scrub", ovr=60, age=33)]))

    def test_want_picks(self):
        w = self.W("WANT_PICKS")
        self.assertTrue(self.f(w, ["2003:R1-X"], ["2003:R2-Team"]))
        self.assertFalse(self.f(w, ["2003:R2-X"], ["2003:R1-Team"]))
        self.assertFalse(self.f(w, [], []))

    def test_want_youth(self):
        w = self.W("WANT_YOUTH")
        self.assertTrue(self.f(w, [make_player("y", ovr=60, age=21, pot=78)]))
        self.assertFalse(self.f(w, [make_player("y", ovr=60, age=21, pot=70)]))
        self.assertFalse(self.f(w, [make_player("y", ovr=78, age=27, pot=78)]))

    def test_shed_tax(self):
        over = team_of(balanced(), payroll=60.0)
        w = self.W("SHED_TAX")
        big = make_player("big", salary=12.0)
        self.assertTrue(self.f(w, [], [big], over))      # needs min(11, 0.05*40=2) = 2
        self.assertFalse(self.f(w, [make_player("in", salary=11.0)], [big], over))
        self.assertFalse(self.f(w, [], [], over))

    def test_clear_long_contract(self):
        w = self.W("CLEAR_LONG_CONTRACT", player="B0")
        gone = self.t.roster[0]
        self.assertTrue(self.f(w, [make_player("s", years=1)], [gone]))
        self.assertFalse(self.f(w, [make_player("s", years=3)], [gone]))
        self.assertFalse(self.f(w, [], [self.t.roster[1]]))

    def test_absorb_salary(self):
        w = self.W("ABSORB_SALARY")
        self.assertTrue(self.f(w, ["2003:R2-X", make_player("a", salary=5.0)], []))
        self.assertFalse(self.f(w, [make_player("a", salary=5.0)], []))
        self.assertFalse(self.f(w, ["2003:R2-X", make_player("a", salary=15.0)], []))   # 40 + 15 > 49
        self.assertTrue(fulfils(w, ["2003:R2-X", make_player("a", salary=900.0)], [], team_of([], 40.0), ERA_NO_CAP))

    def test_role_congestion(self):
        w = self.W("ROLE_CONGESTION", role="PG")
        self.assertTrue(self.f(w, [], [make_player("x", role="PG")]))
        self.assertFalse(self.f(w, [], [make_player("x", role="C")]))

    def test_depth_needed(self):
        w = self.W("DEPTH_NEEDED", role="C")
        self.assertTrue(self.f(w, [make_player("x", ovr=71, role="C")]))
        self.assertFalse(self.f(w, [make_player("x", ovr=65, role="C")]))
        self.assertFalse(self.f(w, [make_player("x", ovr=75, role="PG")]))

    def test_rent_veteran(self):
        w = self.W("RENT_VETERAN")
        self.assertTrue(self.f(w, [make_player("r", ovr=72, age=31, years=1)]))
        self.assertFalse(self.f(w, [make_player("r", ovr=72, age=31, years=2)]))
        self.assertFalse(self.f(w, [make_player("r", ovr=72, age=26, years=1)]))
        self.assertFalse(self.f(w, [make_player("r", ovr=60, age=31, years=1)]))

    def test_sell_expiring(self):
        w = self.W("SELL_EXPIRING", player="B0")
        gone = self.t.roster[0]
        self.assertTrue(self.f(w, ["2003:R2-X"], [gone]))
        self.assertTrue(self.f(w, [make_player("y", age=21)], [gone]))
        self.assertFalse(self.f(w, [make_player("y", age=29)], [gone]))
        self.assertFalse(self.f(w, ["2003:R2-X"], [self.t.roster[1]]))

    def test_bench_hole(self):
        w = self.W("BENCH_HOLE", player="scrub", data=(("ovr", 50),))
        self.assertTrue(self.f(w, [make_player("x", ovr=55)]))
        self.assertFalse(self.f(w, [make_player("x", ovr=50)]))

    def test_move_up_draft(self):
        w = self.W("MOVE_UP_DRAFT")
        self.assertTrue(self.f(w, ["2003:R1-X"], ["2003:R2-Team", "2004:R1-Team"]))
        self.assertFalse(self.f(w, ["2004:R1-X"], ["2003:R2-Team"]))
        self.assertFalse(self.f(w, ["2003:R1-X"], []))

    def test_move_down_draft(self):
        w = self.W("MOVE_DOWN_DRAFT")
        self.assertTrue(self.f(w, ["2003:R2-X", "2004:R1-X"], ["2003:R1-Team"]))
        self.assertFalse(self.f(w, ["2003:R2-X"], ["2003:R1-Team"]))
        self.assertFalse(self.f(w, ["2003:R2-X", "2004:R1-X"], ["2003:R2-Team"]))

    def test_target_prospect(self):
        w = self.W("TARGET_PROSPECT", role="C", data=(("pick", "2003:R1-X"),))
        self.assertTrue(self.f(w, ["2003:R1-X"]))
        self.assertFalse(self.f(w, ["2003:R1-Y"]))

    def test_unknown_kind_false(self):
        self.assertFalse(self.f(self.W("NOPE")))


class HardNoTests(unittest.TestCase):
    def test_rebuilder_vs_old_veteran(self):
        t = team_of(balanced(), name="Reb")
        ctx = ctx_of("REBUILDER")
        old = make_player("Old", ovr=75, age=32, years=3)
        msg = plan_hard_no(t, ctx, [old], [])
        self.assertEqual(msg, "Reb is rebuilding: they won't take on 30+ veterans")
        self.assertIsNone(plan_hard_no(t, ctx, [make_player("Old", age=32, years=1)], []))
        self.assertIsNone(plan_hard_no(t, ctx, [make_player("Young", age=25, years=4)], []))
        self.assertIsNone(plan_hard_no(t, ctx_of("MIDDLE"), [old], []))
        self.assertIsNone(plan_hard_no(t, ctx, [old, "2003:R2-X"], []))   # absorbs salary for a pick

    def test_rebuilder_old_veteran_over_tax_is_refused_even_with_pick(self):
        t = team_of(balanced(), payroll=48.0, name="Reb")
        old = make_player("Old", age=32, years=3, salary=5.0)
        self.assertIsNotNone(plan_hard_no(t, ctx_of("REBUILDER"), [old, "2003:R2-X"], []))

    def test_contender_best_player(self):
        star = make_player("Star", ovr=90, role="SF")
        t = team_of(roster_with(star), name="Con")
        ctx = ctx_of("CONTENDER")
        self.assertEqual(plan_hard_no(t, ctx, [make_player("Meh", ovr=78)], [star]),
                         "Con is going for the title: they won't give up their best player")
        self.assertIsNone(plan_hard_no(t, ctx, [make_player("Star2", ovr=89)], [star]))
        self.assertIsNone(plan_hard_no(t, ctx, [make_player("Meh", ovr=60)], [t.roster[0]]))
        self.assertIsNone(plan_hard_no(t, ctx_of("MIDDLE"), [make_player("Meh", ovr=60)], [star]))

    def test_cap_guardian_tax(self):
        gm = make_gm("g", ["CAP_GUARDIAN"])
        t = team_of(balanced(), payroll=47.0, name="Cap")
        big = make_player("Big", salary=5.0)
        self.assertEqual(plan_hard_no(t, ctx_of(gm=gm), [big], []), "Cap's GM won't go over the tax")
        self.assertIsNone(plan_hard_no(t, ctx_of(gm=gm), [big], [make_player("Out", salary=4.0)]))
        self.assertIsNone(plan_hard_no(t, ctx_of(), [big], []))
        over = team_of(balanced(), payroll=55.0)
        self.assertIsNone(plan_hard_no(over, ctx_of(gm=gm), [big], []))   # was already above
        self.assertIsNone(plan_hard_no(t, ctx_of(gm=gm, era=ERA_NO_CAP), [big], []))

    def test_role_congestion(self):
        pgs = [make_player(f"pg{i}", ovr=78, role="PG") for i in range(3)]
        t = team_of(balanced() + pgs, name="Cong")
        self.assertEqual(plan_hard_no(t, ctx_of(), [make_player("n", ovr=70, role="PG")], []),
                         "Cong already has too many PGs")
        self.assertIsNone(plan_hard_no(t, ctx_of(), [make_player("n", role="C")], []))
        self.assertIsNone(plan_hard_no(t, ctx_of(), [make_player("n", role="PG")], [pgs[0]]))


class WantsOutTests(unittest.TestCase):
    def test_wants_out_is_the_request(self):
        star = make_player("Star", ovr=86, age=31, role="SF")
        star.morale = 10
        t = team_of(roster_with(star))
        self.assertFalse(wants_out(star, t, ctx_of("REBUILDER", win_pct=0.2)))   # miserable, but never asked
        star.morale, star.trade_request = 90, True
        self.assertTrue(wants_out(star, t, ctx_of("CONTENDER", win_pct=0.7)))
        w = [x for x in build_wishes(t, ctx_of("CONTENDER")) if x.kind == "STAR_WANTS_OUT"]
        self.assertEqual([x.player for x in w], ["Star"])


class TextTablesTests(unittest.TestCase):
    def test_every_kind_has_template_and_phrase(self):
        for k in KINDS:
            self.assertIn(k, REASON_TEMPLATES, k)
            self.assertIn(k, WHY_PHRASES, k)
        self.assertEqual(len(KINDS), 18)
        self.assertEqual(set(KINDS), set(REASON_TEMPLATES))

    def test_every_kind_has_priority(self):
        self.assertEqual(set(CONFIG.TRADES.WISH_PRIORITY), set(KINDS))


if __name__ == "__main__":
    unittest.main()
