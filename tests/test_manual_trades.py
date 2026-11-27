"""The user's manual trades: a price instead of a flat no, real return packages, and multi-team deals that pay back."""
import unittest
from unittest import mock

from core.config import CONFIG
from trades.trade_finder import TradeFinder
from tests.trade_fixtures import era_of, make_player, make_torneo, roster_team

ERA = era_of()
T = CONFIG.TRADES
# Starters and depth everywhere: no wish a single player can fulfil.
SATISFIED = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 76), ("PF", 71),
             ("C", 76), ("C", 71), ("SG", 68), ("SF", 68), ("PF", 67)]
SELLER = [("PG", 80), ("PG", 72), ("SG", 80), ("SG", 72), ("SF", 79), ("SF", 72), ("PF", 75), ("PF", 71),
          ("C", 75), ("C", 71), ("SG", 68), ("SF", 68), ("PF", 67)]


def league(cpu, plans=None, user=SATISFIED, records=None):
    teams = [roster_team("U", user)] + [roster_team(name, spec) for name, spec in cpu.items()]
    t = make_torneo(teams, user_team="U", plans={n: "CONTENDER" for n in cpu} | (plans or {}))
    t.pick_ownership = {y: {f"R{r}-{x.nome}": x.nome for x in teams for r in (1, 2)} for y in range(1, 6)}
    t.pick_protections = {y: {} for y in range(1, 6)}
    for x in teams:
        x.vittorie, x.sconfitte = (records or {}).get(x.nome, (20, 20))
        x.get_starter_at_position = lambda role, team=x: max((p for p in team.roster if p.ruolo == role),
                                                             key=lambda p: p.ovr, default=None)
        for p in x.roster:
            p.squadra = x
    return t, {x.nome: x for x in teams}


def manual(t):
    return TradeFinder(t, t.squadre, t.squadra_giocatore, manual=True)


def cpu(t):
    return TradeFinder(t, t.squadre, t.squadra_giocatore)


def add(team, name, **kw):
    p = make_player(name, **kw)
    p.squadra = team
    team.roster.append(p)
    return p


class Case(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(TradeFinder, "era", return_value=ERA),
                  mock.patch("trades.trade_finder.random.uniform", return_value=0.0)):
            p.start()
            self.addCleanup(p.stop)


class FirstRoundValueTests(Case):
    def setUp(self):
        super().setUp()
        self.t, _ = league({"S": SATISFIED, "W": SATISFIED}, plans={"S": "CONTENDER", "W": "MIDDLE"},
                           records={"S": (35, 5), "W": (8, 32)})
        self.f = manual(self.t)

    def value(self, team, year):
        return self.f.get_pick_value(f"R1-{team}", year, on_curve=True)

    def test_cpu_to_cpu_deals_keep_their_own_pick_values(self):
        f = cpu(self.t)
        self.assertLess(f.get_pick_value("R1-S", 5, on_curve=True), f.get_pick_value("R1-S", 1, on_curve=True))

    def test_a_strong_teams_far_first_is_worth_more_than_its_next_one(self):
        self.assertGreater(self.value("S", 5), self.value("S", 1))

    def test_a_weak_teams_far_first_is_worth_less_than_its_next_one(self):
        self.assertLess(self.value("W", 5), self.value("W", 1))

    def test_the_farthest_firsts_of_strong_and_weak_teams_are_worth_the_same(self):
        self.assertAlmostEqual(self.value("S", 5), self.value("W", 5))

    def test_the_next_draft_still_follows_the_record(self):
        self.assertLess(self.value("S", 1), self.value("W", 1))


class ManualPriceTests(Case):
    def values(self, table):
        p = mock.patch.object(TradeFinder, "get_strategic_value",
                              lambda _s, a, _t, _pp=None: table.get(a if isinstance(a, str) else a.nome, 10.0))
        p.start()
        self.addCleanup(p.stop)

    def deal(self):
        t, teams = league({"C": SATISFIED})
        mine = add(teams["U"], "mine", ovr=74, role="SF", age=26)
        theirs = add(teams["C"], "theirs", ovr=74, role="SF", age=26)
        return t, teams["C"], mine, theirs

    def test_a_deal_outside_the_plan_is_refused_at_an_even_price(self):
        t, c, mine, theirs = self.deal()
        self.values({"mine": 100.0, "theirs": 100.0})
        ok, why = manual(t).would_accept_trade_with_reason(c, [mine], [theirs])
        self.assertFalse(ok)
        self.assertIn("Value mismatch", why)

    def test_a_deal_outside_the_plan_goes_through_at_a_premium(self):
        t, c, mine, theirs = self.deal()
        self.values({"mine": 100.0 * T.MANUAL_PLAN_PREMIUM * 1.05, "theirs": 100.0})
        self.assertTrue(manual(t).would_accept_trade_with_reason(c, [mine], [theirs])[0])

    def test_cpu_deals_keep_the_flat_refusal(self):
        t, c, mine, theirs = self.deal()
        self.values({"mine": 500.0, "theirs": 100.0})
        ok, why = cpu(t).would_accept_trade_with_reason(c, [mine], [theirs])
        self.assertFalse(ok)
        self.assertIn("no use for this deal", why)

    def test_a_manual_answer_does_not_change_between_two_clicks(self):
        t, c, mine, theirs = self.deal()
        self.values({"mine": 106.0, "theirs": 100.0})
        answers = set()
        for swing in (-0.02, 0.015):
            with mock.patch("trades.trade_finder.random.uniform", return_value=swing):
                answers.add(manual(t).would_accept_trade_with_reason(c, [mine], [theirs])[0])
        self.assertEqual(len(answers), 1)

    def test_a_hard_no_stays_a_no_at_any_price(self):
        t, teams = league({"R": SATISFIED}, plans={"R": "REBUILDER"})
        vet = add(teams["U"], "vet", ovr=80, age=33, years=3, role="SF")
        out = add(teams["R"], "out", ovr=70, age=29, role="SF")
        self.values({"vet": 900.0, "out": 10.0})
        ok, why = manual(t).would_accept_trade_with_reason(teams["R"], [vet], [out])
        self.assertFalse(ok)
        self.assertIn("rebuilding", why)

    def test_a_young_cornerstone_has_a_price_in_a_manual_trade(self):
        t, teams = league({"C": SATISFIED})
        kid = add(teams["C"], "kid", ovr=74, age=21, pot=86, role="SF")
        star = add(teams["U"], "star", ovr=84, age=27, role="C")
        self.values({"kid": 100.0, "star": 100.0 * T.MANUAL_PLAN_PREMIUM * T.MANUAL_CORNERSTONE_PREMIUM * 1.05})
        self.assertTrue(manual(t).would_accept_trade_with_reason(teams["C"], [star], [kid])[0])
        with mock.patch.object(TradeFinder, "plan_check", return_value=(True, "", None)):
            self.assertIn("Rookie Cornerstone", cpu(t).would_accept_trade_with_reason(teams["C"], [star], [kid])[1])


class ManualPickRulesTests(Case):
    def test_a_team_sending_starters_can_add_firsts_and_seconds(self):
        t, teams = league({"C": SELLER})
        star = add(teams["U"], "star", ovr=89, age=30, role="C")
        c = teams["C"]
        starters = [p for p in c.roster if p.ovr == 80]
        picks = ["1:R1-C", "2:R1-C", "1:R2-C", "2:R2-C"]
        self.assertNotIn("Starter Swap", manual(t).would_accept_trade_with_reason(c, [star], starters + picks)[1])
        self.assertIn("Starter Swap", cpu(t).would_accept_trade_with_reason(c, [star], starters + picks)[1])

    def test_a_second_is_worth_something_in_a_manual_trade(self):
        t, _ = league({"C": SATISFIED})
        self.assertGreater(manual(t).get_pick_value("R2-C", 1, on_curve=True),
                           cpu(t).get_pick_value("R2-C", 1, on_curve=True) * 4)


class ManualSearchTests(Case):
    def star(self, teams, salary=30.0):
        return add(teams["U"], "star", ovr=89, age=30, salary=salary, role="C")

    def test_a_star_brings_back_two_starters_and_firsts(self):
        t, teams = league({"C": SELLER})
        for p in teams["C"].roster:
            p.contract.salario_annuale = 12.0   # market contracts: no discount on the starters' value
        offers = manual(t).find_trades_for_package([self.star(teams)], [])
        self.assertTrue(any(sum(p["ovr"] >= 79 for p in o["receiving_players"]) >= 2
                            and sum("R1" in k for k in o["receiving_picks"]) >= 2 for o in offers), offers)

    def test_the_return_stays_below_the_market_value_of_what_is_given(self):
        t, teams = league({"C": SELLER}, plans={"C": "REBUILDER"})
        star = add(teams["U"], "young", ovr=84, age=24, salary=12.0, role="C")
        f = manual(t)
        market = star.trade_value
        for o in f.find_trades_for_package([star], []):
            back = sum(p["trade_value"] for p in o["receiving_players"]) + sum(
                f.get_pick_value(k.split(":")[1], int(k.split(":")[0]), on_curve=True) for k in o["receiving_picks"])
            self.assertLessEqual(back, market * T.MANUAL_RETURN_TARGET + 0.5)

    def test_every_team_is_searched(self):
        names = [f"T{i:02d}" for i in range(14)]
        t, teams = league({n: SELLER for n in names})
        offers = manual(t).find_trades_for_package([self.star(teams)], [])
        self.assertEqual({o["partner_team"] for o in offers}, set(names))

    def test_a_team_makes_a_limited_number_of_offers(self):
        t, teams = league({"C": SELLER})
        self.assertLessEqual(len(manual(t).find_trades_for_package([self.star(teams)], [])), T.MANUAL_OFFERS_PER_TEAM)

    def test_a_return_never_carries_more_than_two_seconds(self):
        t, teams = league({"C": SELLER})
        for o in manual(t).find_trades_for_package([self.star(teams)], []):
            self.assertLessEqual(sum("R2" in k for k in o["receiving_picks"]), T.MANUAL_MAX_RETURN_SECONDS)

    def test_offers_far_below_the_value_given_are_not_shown(self):
        t, teams = league({"C": [("PG", 66), ("SG", 66), ("SF", 66), ("PF", 66), ("C", 66), ("PG", 65), ("SG", 65),
                                 ("SF", 65), ("PF", 65), ("C", 65), ("SG", 64), ("SF", 64), ("PF", 64)]})
        t.pick_ownership = {y: {k: v for k, v in owned.items() if v != "C"} for y, owned in t.pick_ownership.items()}
        self.assertEqual(manual(t).find_trades_for_package([self.star(teams)], []), [])

    def test_a_cheap_star_is_matched_by_adding_a_contract_of_the_user(self):
        t, teams = league({"C": SELLER})
        star = self.star(teams, salary=10.0)
        for p in teams["C"].roster:
            p.contract.salario_annuale = 7.0
        teams["U"].check_trade_salary_match = lambda inc, out: (inc <= out * 1.25 + 0.1, "")
        offers = manual(t).find_trades_for_package([star], [])
        self.assertTrue(any(len(o["giving_players"]) > 1 for o in offers), offers)


class MultiTeamTests(Case):
    def deals(self):
        t, teams = league({"B": SELLER, "C": SELLER, "D": SELLER, "E": SELLER})
        star = add(teams["U"], "star", ovr=82, age=27, role="C")
        return manual(t), star

    def share(self, f, offer_value, star):
        return offer_value / f.get_strategic_value(star, f.squadra_giocatore)

    def test_three_team_deals_do_not_make_the_user_pay_the_other_teams(self):
        f, star = self.deals()
        offers = f.find_3_team_trades_for_package([star], [])
        self.assertTrue(offers)
        for o in offers:
            self.assertEqual(o["user_picks_to_c"], [])
            self.assertLessEqual(len(o["user_picks_to_b"]), T.MANUAL_MULTI_MAX_USER_PICKS)

    def test_three_team_deals_pay_back_a_fair_share(self):
        f, star = self.deals()
        for o in f.find_3_team_trades_for_package([star], []):
            given = f.get_strategic_value(star, f.squadra_giocatore) + sum(
                f.get_strategic_value(k, f.squadra_giocatore) for k in o["user_picks_to_b"])
            self.assertGreaterEqual((o["value_differential"] + given) / given, T.MANUAL_MIN_RETURN_SHARE)

    def test_four_team_deals_cap_the_users_picks_and_pay_back(self):
        f, star = self.deals()
        for o in f.find_multi_team_chain_trades([star], []):
            self.assertLessEqual(len(o["user_picks_giving"]), T.MANUAL_MULTI_MAX_USER_PICKS)
            given = f.get_strategic_value(star, f.squadra_giocatore) + sum(
                f.get_strategic_value(k, f.squadra_giocatore) for k in o["user_picks_giving"])
            self.assertGreaterEqual((o["value_differential"] + given) / given, T.MANUAL_MIN_RETURN_SHARE)


if __name__ == "__main__":
    unittest.main()
