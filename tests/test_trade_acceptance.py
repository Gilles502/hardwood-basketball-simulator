"""Two-question acceptance: is the price right, and does the deal move the team toward its plan.

Thresholds of the acceptance path follow the league's era lines (core/front_office/era_lines.py).
"""
import unittest
from unittest import mock

from core.config import CONFIG
from trades.execution import Deal
from trades.trade_finder import TradeFinder
from tests.trade_fixtures import make_player, make_team, make_torneo, finder, era_of, pin_difficulty, roster_team

T = CONFIG.TRADES

ERA_2002 = era_of()
ERA_INFLATED = era_of(star=89, core=84, starter=79, rotation=74, bench=69)


def valued(player, value):
    player._test_value = value
    return player


# A balanced contender without a starting C (best C 72 < starter line 75): NEED_STARTER C, WANT_STAR.
NO_STARTING_C = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 76), ("PF", 71),
                 ("C", 72), ("C", 71), ("SG", 68), ("SF", 68), ("PF", 67)]


def middle_with_star(star_ovr):
    """A MIDDLE team with an SF star and a 60 OVR end of the bench (its only fulfillable wish: BENCH_HOLE)."""
    return [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", star_ovr), ("SF", 71), ("PF", 76), ("PF", 71),
            ("C", 76), ("C", 71), ("SG", 66), ("SF", 66), ("PG", 60)]


class AcceptanceTestCase(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(TradeFinder, "get_strategic_value",
                                     lambda self, a, tm, pp=None: getattr(a, "_test_value", 10.0)),
                   mock.patch("trades.trade_finder.random.uniform", return_value=0.0)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def league(self, spec, plan, era=ERA_2002, user_team=None, name="C"):
        teams = [roster_team(name, spec), make_team("O")]
        if user_team and user_team not in (name, "O"):
            teams.append(make_team(user_team))
        t = make_torneo(teams, user_team=user_team, plans={name: plan, "O": "MIDDLE"})
        f = finder(t)
        patch = mock.patch.object(TradeFinder, "era", return_value=era)
        patch.start()
        self.addCleanup(patch.stop)
        return f, teams[0]

    def player(self, team, role, ovr):
        return next(p for p in team.roster if p.ruolo == role and p.ovr == ovr)


class PlanQuestionTests(AcceptanceTestCase):
    def test_accepts_a_fair_deal_that_fills_need_starter(self):
        f, c = self.league(NO_STARTING_C, "CONTENDER")
        self.assertIn("NEED_STARTER", [w.kind for w in f.wishes_for(c)])
        center = valued(make_player("center", ovr=77, role="C"), 100.0)
        out = valued(self.player(c, "SG", 71), 100.0)
        ok, why, wish = f.plan_check(c, [center], [out])
        self.assertTrue(ok)
        self.assertEqual((wish.kind, wish.role), ("NEED_STARTER", "C"))
        self.assertEqual(f.would_accept_trade_with_reason(c, [center], [out]), (True, "Accepted"))

    def test_refuses_the_same_value_without_a_wish(self):
        f, c = self.league(NO_STARTING_C, "CONTENDER")
        wing = valued(make_player("wing", ovr=72, role="SF"), 100.0)
        out = valued(self.player(c, "SG", 71), 100.0)
        ok, why = f.would_accept_trade_with_reason(c, [wing], [out])
        self.assertFalse(ok)
        self.assertEqual(why, "C has no use for this deal right now")
        self.assertIn("has no use for this deal", why)

    def test_rebuild_hard_no_even_when_overpaid(self):
        f, r = self.league(NO_STARTING_C, "REBUILDER", name="R")
        vet = valued(make_player("vet", ovr=78, age=31, years=3, role="C"), 200.0)
        out = valued(self.player(r, "SG", 71), 100.0)
        ok, why = f.would_accept_trade_with_reason(r, [vet], [out])
        self.assertFalse(ok)
        self.assertEqual(why, f"R is rebuilding: they won't take on {T.VETERAN_MIN_AGE}+ veterans")

    def test_user_team_is_never_plan_checked(self):
        f, u = self.league(NO_STARTING_C, "CONTENDER", user_team="C")
        wing = valued(make_player("wing", ovr=72, role="SF"), 100.0)
        out = valued(self.player(u, "SG", 71), 100.0)
        self.assertEqual(f.plan_check(u, [wing], [out]), (True, "", None))
        with mock.patch.object(TradeFinder, "wishes_for", side_effect=AssertionError("plan-checked")):
            self.assertEqual(f.would_accept_trade_with_reason(u, [wing], [out]), (True, "Accepted"))

    def test_no_user_team_in_only_coach(self):
        teams = [roster_team("C", NO_STARTING_C), make_team("O")]
        t = make_torneo(teams, user_team="C", role="only_coach", plans={"C": "CONTENDER", "O": "MIDDLE"})
        f = finder(t)
        wing = make_player("wing", ovr=72, role="SF")
        with mock.patch.object(TradeFinder, "era", return_value=ERA_2002):
            ok, why, _ = f.plan_check(teams[0], [wing], [self.player(teams[0], "SG", 71)])
        self.assertFalse(ok)   # the coach's own team still answers the plan question (its GM is the CPU)
        self.assertEqual(why, "C has no use for this deal right now")


class WishCacheTests(unittest.TestCase):
    def _league(self):
        names = ("C", "B")
        teams = [make_team(n) for n in names]
        t = make_torneo(teams, plans={"C": "CONTENDER", "B": "MIDDLE"})
        t.fase_torneo, t.trade_analytics_history = "SEASON", []
        t.pick_ownership = {y: {f"R{r}-{n}": n for n in names for r in (1, 2)} for y in range(1, 6)}
        t.pick_protections = {y: {} for y in range(1, 6)}
        return t, teams

    def test_wishes_without_begin_window(self):
        t, (c, _b) = self._league()
        f = finder(t)
        self.assertEqual(f.window, "user")
        needs = {w.role for w in f.wishes_for(c) if w.kind == "NEED_STARTER"}
        self.assertEqual(needs, {"PG", "SF", "PF", "C"})   # an all-SG roster
        self.assertEqual(f.wish_context(c).window, "user")

    def test_wishes_recomputed_after_a_deal(self):
        t, (c, b) = self._league()
        f = finder(t)
        center = make_player("big", ovr=90, role="C")
        b.roster.append(center)
        self.assertIn("C", {w.role for w in f.wishes_for(c) if w.kind == "NEED_STARTER"})
        with mock.patch.object(TradeFinder, "_log_trade_to_file"), mock.patch("core.news_generator.add_news"):
            self.assertTrue(f.execute_deal(Deal([c, b], [("C", "B", c.roster[0]), ("B", "C", center)])))
        self.assertNotIn("C", {w.role for w in f.wishes_for(c) if w.kind == "NEED_STARTER"})

    def test_begin_window_resets_caches(self):
        t, (c, _b) = self._league()
        f = finder(t)
        first_era, first = f.era(), f.wishes_for(c)
        self.assertIs(f.era(), first_era)
        self.assertIs(f.wishes_for(c), first)
        f.begin_window("deadline")
        self.assertEqual(f.window, "deadline")
        self.assertIsNot(f.era(), first_era)
        self.assertEqual(f.wish_context(c).window, "deadline")
        self.assertIsNot(f.wishes_for(c), first)
        self.assertEqual(f.league_lines()["star"], f.era().star)

    def test_clear_all_caches(self):
        t, (c, b) = self._league()
        f = finder(t)
        first_c, first_b = f.wishes_for(c), f.wishes_for(b)
        f._clear_trade_caches(["B"])
        self.assertIs(f.wishes_for(c), first_c)
        self.assertIsNot(f.wishes_for(b), first_b)
        f._clear_trade_caches()
        self.assertIsNot(f.wishes_for(c), first_c)


class DraftWindowTests(unittest.TestCase):
    def test_prospects_and_target_prospect_in_the_draft_window(self):
        teams = [make_team(n) for n in ("X", "Y", "A")]   # all-SG rosters: thin at C and PG
        t = make_torneo(teams, plans={"X": "MIDDLE", "Y": "MIDDLE", "A": "MIDDLE"})
        t.pick_ownership = {1: {f"R1-{n}": n for n in ("X", "Y", "A")}, 2: {}}
        t.draft_lottery_order = ["X", "Y", "A"]
        t.draft_class = [make_player("kidpg", ovr=60, age=19, pot=80, role="PG"),
                         make_player("kidc", ovr=60, age=19, pot=90, role="C"),
                         make_player("kidsf", ovr=60, age=19, pot=70, role="SF")]
        f = finder(t)
        a = teams[2]
        self.assertEqual(f.wish_context(a).prospects, ())   # only in the draft window
        f.begin_window("draft")
        ctx = f.wish_context(a)
        year = f.era().year
        self.assertTrue(ctx.has_r1_this_year)
        self.assertEqual(ctx.prospects, (("C", f"{year}:R1-X"), ("PG", f"{year}:R1-Y")))   # board by potential
        target = [w for w in f.wishes_for(a) if w.kind == "TARGET_PROSPECT"]
        self.assertEqual(target[0].get("pick"), f"{year}:R1-X")
        ok, _, wish = f.plan_check(a, ["1:R1-X"], ["1:R1-A", "2:R2-A"])
        self.assertTrue(ok)
        self.assertEqual(wish.kind, "TARGET_PROSPECT")


class RegressionAt2002Tests(AcceptanceTestCase):
    """Main piece, quality and star premium give today's answers at a 2002-like league (star 85, core 80).

    The expected answers were produced by the pre-rework code (commit 1e752ec) on the same deals, at its difficulty
    multipliers (pinned: the gate tunes CONFIG.TRADES.DIFFICULTY)."""

    def setUp(self):
        super().setUp()
        pin_difficulty(self)

    def _main_piece_deal(self, era):
        f, m = self.league(middle_with_star(87), "MIDDLE", era=era, name="M")
        star = valued(self.player(m, "SF", 87), 300.0)
        incoming = [valued(make_player(f"in{i}", ovr=72, role=r), 120.0) for i, r in enumerate(("C", "PG", "SG"))]
        return f.would_accept_trade_with_reason(m, incoming, [star])

    def _quality_deal(self, era):
        f, m = self.league(middle_with_star(90), "MIDDLE", era=era, name="M")
        star = valued(self.player(m, "SF", 90), 300.0)
        wing = valued(make_player("wing", ovr=74, role="SF"), 250.0)
        return f.would_accept_trade_with_reason(m, [wing], [star])

    def _star_premium_deal(self, era, back_ovr=80):
        f, m = self.league(middle_with_star(87), "MIDDLE", era=era, name="M")
        star = valued(self.player(m, "SF", 87), 100.0)
        wing = valued(make_player("wing", ovr=back_ovr, role="SF"), 100.0)
        return f.would_accept_trade_with_reason(m, [wing], [star])

    def test_main_piece_rule(self):
        self.assertEqual(self._main_piece_deal(ERA_2002),
                         (False, "Main Piece Rule: Best asset received (120.0) < 42% of best asset given (300.0)"))

    def test_quality_rule(self):
        self.assertEqual(self._quality_deal(ERA_2002),
                         (False, "Quality Rule: Need a solid starter, young prospect, or 1st-round pick "
                                 "for a top superstar (90+)"))

    def test_star_premium(self):
        self.assertEqual(self._star_premium_deal(ERA_2002),
                         (False, "Value mismatch: Offer 100.0 < Required 103.6 (Threshold: 1.04)"))

    # (difficulty, star given, OVR back) -> the pre-rework answer for a 100-for-100 swap of SFs
    DIFFICULTY_TABLE = {
        ("easy", 87, 80): (True, "Accepted"),
        ("easy", 93, 80): (True, "Accepted"),
        # (a star sold for a role player: the Star Sale Rule comes after every price question, even on easy)
        ("easy", 85, 70): (False, "Star Sale Rule: the M won't sell M-SF4 for role players: "
                                  "a first-round pick or a 79+ OVR player has to come back"),
        ("realistic", 87, 80): (False, "Value mismatch: Offer 100.0 < Required 103.6 (Threshold: 1.04)"),
        ("realistic", 93, 80): (False, "Value mismatch: Offer 100.0 < Required 111.2 (Threshold: 1.11)"),
        ("realistic", 85, 70): (False, "Value mismatch: Offer 100.0 < Required 110.8 (Threshold: 1.11)"),
        ("hardcore", 87, 80): (False, "Value mismatch: Offer 100.0 < Required 146.8 (Threshold: 1.47)"),
        ("hardcore", 93, 80): (False, "Value mismatch: Offer 100.0 < Required 161.8 (Threshold: 1.62)"),
        ("hardcore", 85, 70): (False, "Quality Rule: Need 76+ player, 1st-round pick, or young talent "
                                      "for an All-Star (85+)"),
    }

    def test_difficulty_and_star_premium_tables(self):
        for (diff, star_ovr, back), expected in self.DIFFICULTY_TABLE.items():
            with self.subTest(diff=diff, star=star_ovr, back=back):
                f, m = self.league(middle_with_star(star_ovr), "MIDDLE", name="M")
                f.torneo.trade_difficulty = diff
                star = valued(self.player(m, "SF", star_ovr), 100.0)
                wing = valued(make_player("wing", ovr=back, role="SF"), 100.0)
                self.assertEqual(f.would_accept_trade_with_reason(m, [wing], [star]), expected)

    def test_inflated_league_87_is_no_star(self):
        # an 90 back is a star-level return (Star Sale Rule), so only the price question is left
        self.assertEqual(self._star_premium_deal(ERA_INFLATED, back_ovr=90), (True, "Accepted"))


class UntouchablePremiumTests(AcceptanceTestCase):
    """An untouchable who does not ask out moves only for an exceptional price AND a fulfilled wish."""

    def setUp(self):
        super().setUp()
        pin_difficulty(self)

    def deal(self, back_value, back_ovr=80, untouchable=True, wants_out=False, **kw):
        f, m = self.league(middle_with_star(87), "MIDDLE", name="M")
        star = valued(self.player(m, "SF", 87), 100.0)
        star.is_untouchable, star._wants_out = untouchable, wants_out
        wing = valued(make_player("wing", ovr=back_ovr, role="SF"), back_value)
        return f.would_accept_trade_with_reason(m, [wing], [star], **kw)

    def test_the_normal_price_is_not_enough_for_an_untouchable(self):
        self.assertEqual(self.deal(100.0, untouchable=False)[0], False)   # 104 asked at this price
        self.assertEqual(self.deal(110.0, untouchable=False), (True, "Accepted"))
        ok, why = self.deal(110.0)
        self.assertFalse(ok)
        self.assertTrue(why.startswith("Untouchable Cornerstone: M-SF"))
        self.assertTrue(why.endswith("is the face of the M: only an exceptional offer moves him."))
        self.assertNotIn("Value mismatch", why)   # no price numbers

    def test_an_exceptional_price_with_a_fulfilled_wish_moves_him(self):
        self.assertEqual(self.deal(110.0 * T.UNTOUCHABLE_PREMIUM + 10.0), (True, "Accepted"))

    def test_a_big_surplus_does_not_buy_a_refused_plan(self):
        ok, why = self.deal(1000.0, back_ovr=55)   # a 55 fulfils no wish of M
        self.assertFalse(ok)
        self.assertEqual(why, "M has no use for this deal right now")

    def test_a_star_who_asks_out_pays_no_premium(self):
        self.assertEqual(self.deal(110.0, wants_out=True), (True, "Accepted"))

    def test_a_tax_dump_never_gives_an_untouchable(self):
        ok, why = self.deal(1.0, waive_price=True)
        self.assertFalse(ok)
        self.assertIn("only an exceptional offer moves him", why)
        self.assertEqual(self.deal(1.0, untouchable=False, waive_price=True), (True, "Accepted"))

    def test_the_premium_applies_once_for_two_untouchables(self):
        f, m = self.league(middle_with_star(87), "MIDDLE", name="M")
        star = valued(self.player(m, "SF", 87), 100.0)
        other = valued(self.player(m, "PG", 76), 0.0)
        star.is_untouchable = other.is_untouchable = True
        wing = valued(make_player("wing", ovr=80, role="SF"), 135.0 + 1.0)
        # 100 given for a 1.04 threshold and one 1.30 premium: 135.2 asked (twice would be 175.8)
        self.assertEqual(f.would_accept_trade_with_reason(m, [wing], [star, other]), (True, "Accepted"))


class EraValueTests(unittest.TestCase):
    def _value(self, era, fn, plan="MIDDLE"):
        teams = [make_team("R"), make_team("O")]
        t = make_torneo(teams, plans={"R": plan, "O": "MIDDLE"})
        with mock.patch.object(TradeFinder, "era", return_value=era):
            return fn(finder(t), teams[0])

    def test_pick_value_scales_with_the_era(self):
        pick = lambda f, _team: f.get_pick_value("R2-O", 1)
        self.assertAlmostEqual(self._value(era_of(pick_scale=1.5), pick), self._value(era_of(pick_scale=1.0), pick) * 1.5)

    def test_heavy_contract_uses_era_money(self):
        heavy = make_player("heavy", ovr=75, age=27, salary=12.0, years=3)
        value = lambda f, team: f.get_strategic_value(heavy, team)
        small_cap = self._value(era_of(cap=100.0), value, plan="REBUILDER")        # money(15) = 9.7: 12 is heavy
        ref_cap = self._value(era_of(cap=T.REFERENCE_CAP), value, plan="REBUILDER")  # money(15) = 15: 12 is not
        self.assertAlmostEqual(small_cap / ref_cap, 0.80)

    def test_rebuild_star_discount_follows_the_star_line(self):
        vet = make_player("vet", ovr=87, age=29)
        value = lambda f, team: f.get_strategic_value(vet, team)
        self.assertAlmostEqual(self._value(ERA_2002, value, plan="REBUILDER")
                               / self._value(ERA_INFLATED, value, plan="REBUILDER"),
                               CONFIG.TRADES.REBUILDER_STAR_SHARE / CONFIG.TRADES.REBUILDER_VET_SHARE)   # 2 years left: a keeper


class TradeDemandTests(unittest.TestCase):
    def test_tradeable_players_flags_demands_with_wants_out(self):
        team = make_team("R", ovrs=[70] * 12)
        star = make_player("star", ovr=87, age=31, role="SF")
        star.morale = 40
        team.roster.append(star)
        t = make_torneo([team, make_team("O")], plans={"R": "REBUILDER", "O": "MIDDLE"})
        for era, expected in ((ERA_2002, True), (ERA_INFLATED, False)):
            with mock.patch.object(TradeFinder, "era", return_value=era):
                finder(t).get_tradeable_players(team)
            self.assertEqual(star._wants_out, expected)


if __name__ == "__main__":
    unittest.main()
