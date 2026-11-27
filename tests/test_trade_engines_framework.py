"""Engine framework: partners, closing a deal (with the 3/4-team extension), the window runner, positional swap."""
import unittest
from unittest import mock

from core.config import CONFIG
from core.front_office.wishes import KINDS
from trades import engines, windows
from trades.engines import common, multi_team, positional_swap
from trades.execution import Deal
from trades.salary_rules import salary_match_ok
from trades.trade_finder import TradeFinder
from tests.trade_fixtures import make_torneo, finder, era_of, pin_difficulty, roster_team

ERA_2002 = era_of()

# A contender without a starting C (best C 72 < starter line 75): NEED_STARTER C.
NO_STARTING_C = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 76), ("PF", 71),
                 ("C", 72), ("C", 71), ("SG", 68), ("SF", 68), ("PF", 67)]
# A MIDDLE team with three starting Cs: ROLE_CONGESTION C, ABSORB_SALARY.
THREE_CENTERS = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 76), ("PF", 71),
                 ("C", 78), ("C", 77), ("C", 76), ("SG", 66), ("SF", 66)]
# A MIDDLE team with one starting C: ABSORB_SALARY only (nothing a C-for-SG swap fulfils).
ONE_CENTER = [("PG", 76), ("PG", 71), ("SG", 76), ("SG", 71), ("SF", 76), ("SF", 71), ("PF", 76), ("PF", 71),
              ("C", 77), ("C", 71), ("SG", 68), ("SF", 68), ("PF", 67)]
# A MIDDLE team of 70s: ABSORB_SALARY.
ABSORBER = [("PG", 72), ("PG", 70), ("SG", 72), ("SG", 70), ("SF", 72), ("SF", 70), ("PF", 72), ("PF", 70),
            ("C", 72), ("C", 70), ("SG", 66), ("SF", 66), ("PF", 66)]
# A balanced contender: WANT_STAR, none of the extension kinds.
BALANCED = [("PG", 77), ("PG", 72), ("SG", 77), ("SG", 72), ("SF", 77), ("SF", 72), ("PF", 77), ("PF", 72),
            ("C", 77), ("C", 72), ("SG", 68), ("SF", 68), ("PF", 67)]


def player(team, role, ovr):
    return next(p for p in team.roster if p.ruolo == role and p.ovr == ovr)


def real_salary_rule(team, payroll):
    """The 2002 salary match (125% + 0.1 over the cap) on this team's payroll."""
    team.payroll = payroll
    team.check_trade_salary_match = lambda incoming, outgoing: salary_match_ok(
        payroll=team.payroll, incoming=incoming, outgoing=outgoing, cap=ERA_2002.cap, second_apron=9999.0,
        year=2003, cba_mode="realistic")


def league(specs, plans, user_team=None, role=None):
    teams = [roster_team(name, spec) for name, spec in specs.items()]
    t = make_torneo(teams, user_team=user_team, plans=plans, role=role)
    t.trade_analytics_history = []
    names = list(specs)
    t.pick_ownership = {y: {f"R{r}-{n}": n for n in names for r in (1, 2)} for y in range(1, 6)}
    t.pick_protections = {y: {} for y in range(1, 6)}
    return t, {team.nome: team for team in teams}


def wish_of(f, team, kind, role=None):
    return next(w for w in f.wishes_for(team) if w.kind == kind and (role is None or w.role == role))


def engine_wish_config():
    """CONFIG with the pre-2026-11-03 wish triggers (a mid owner sheds 10% of the cap over the tax, no look-ahead): the engine tests build small leagues around them; the new triggers have their
    own tests."""
    import dataclasses
    return dataclasses.replace(CONFIG, TRADES=dataclasses.replace(
        CONFIG.TRADES, SHED_TAX_OVER_SHARE_BY_TIER={"low": 0.0, "mid": 0.10, "high": None}, SHED_TAX_LOOK_AHEAD=False))


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        import core.front_office.wishes as wishes_module
        patches = [
            mock.patch.object(wishes_module, "CONFIG", engine_wish_config()),
            mock.patch.object(TradeFinder, "_log_trade_to_file"),
            mock.patch("core.news_generator.add_news"),
            mock.patch.object(TradeFinder, "era", return_value=ERA_2002),
            # A player's `_test_value`, or `_test_value_for[team name]` when the two teams value him differently.
            mock.patch.object(TradeFinder, "get_strategic_value",
                              lambda self, a, tm, pp=None: 1.0 if isinstance(a, str) else
                              (getattr(a, "_test_value_for", None) or {}).get(tm.nome, getattr(a, "_test_value", 10.0))),
            mock.patch("trades.trade_finder.random.uniform", return_value=0.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        pin_difficulty(self)


class PartnersTests(EngineTestCase):
    def test_pairs_each_cpu_team_with_its_top_wish_of_the_kinds(self):
        t, teams = league({"C": NO_STARTING_C, "S": THREE_CENTERS, "A": ABSORBER},
                          {"C": "CONTENDER", "S": "MIDDLE", "A": "MIDDLE"})
        f = finder(t)
        pairs = common.partners_with(f, ("ABSORB_SALARY", "ROLE_CONGESTION"), exclude=[teams["C"]])
        self.assertEqual(sorted((team.nome, w.kind) for team, w in pairs),
                         [("A", "ABSORB_SALARY"), ("S", "ROLE_CONGESTION")])

    def test_user_team_is_a_partner_only_without_a_user_gm(self):
        specs = {"C": NO_STARTING_C, "U": ABSORBER}
        t, _ = league(specs, {"C": "CONTENDER", "U": "MIDDLE"}, user_team="U")
        self.assertEqual(common.partners_with(finder(t), ("ABSORB_SALARY",)), [])
        t, _ = league(specs, {"C": "CONTENDER", "U": "MIDDLE"}, user_team="U", role="only_coach")
        self.assertEqual([team.nome for team, _ in common.partners_with(finder(t), ("ABSORB_SALARY",))], ["U"])


class PingPongTests(EngineTestCase):
    """A team never gets back, in the same season, what it traded away (the GSW/TOR pick ping-pong)."""

    def test_an_asset_traded_away_cannot_come_back_this_season(self):
        t, teams = league({"C": NO_STARTING_C, "S": ONE_CENTER}, {"C": "CONTENDER", "S": "MIDDLE"})
        t.season_number = 1
        f = finder(t)
        c, s = teams["C"], teams["S"]
        first = Deal([c, s], [("S", "C", "1:R1-S"), ("C", "S", "1:R1-C"), ("C", "S", "2:R2-C")])
        self.assertIsNone(common.gives_back(f, first))
        common.remember_moves(f, first)
        back = Deal([c, s], [("C", "S", "1:R1-S"), ("S", "C", "1:R1-C"), ("S", "C", "2:R2-C")])
        self.assertIn("S would get back", common.gives_back(f, back))
        other = Deal([c, s], [("S", "C", "3:R1-S"), ("C", "S", "3:R1-C")])
        self.assertIsNone(common.gives_back(f, other))
        t.season_number = 2   # a new season forgets
        self.assertIsNone(common.gives_back(f, back))

    def test_close_deal_refuses_the_reverse_deal(self):
        t, teams = league({"C": NO_STARTING_C, "S": ONE_CENTER}, {"C": "CONTENDER", "S": "MIDDLE"})
        f = finder(t)
        c, s = teams["C"], teams["S"]
        common.remember_moves(f, Deal([c, s], [("S", "C", "1:R1-S")]))
        deal = Deal([c, s], [("C", "S", "1:R1-S")])
        with mock.patch.object(TradeFinder, "execute_deal") as ex:
            self.assertFalse(common.close_deal(f, deal, "pick_trade_up", {}))
        ex.assert_not_called()


class CloseDealTests(EngineTestCase):
    def swap(self, partner_spec):
        t, teams = league({"C": NO_STARTING_C, "S": partner_spec}, {"C": "CONTENDER", "S": "MIDDLE"})
        f = finder(t)
        c, s = teams["C"], teams["S"]
        center, sg = player(s, "C", 77), player(c, "SG", 71)
        deal = Deal([c, s], [("C", "S", sg), ("S", "C", center)])
        return t, f, c, s, center, sg, deal

    def test_refuses_when_the_partner_has_no_fulfilled_wish(self):
        t, f, c, s, center, sg, deal = self.swap(ONE_CENTER)
        wishes = {"C": wish_of(f, c, "NEED_STARTER", "C"), "S": f.wishes_for(s)[0]}
        with mock.patch.object(TradeFinder, "execute_deal", wraps=f.execute_deal) as ex:
            self.assertFalse(common.close_deal(f, deal, "positional_swap", wishes))
        ex.assert_not_called()
        self.assertIn(center, s.roster)
        self.assertIn(sg, c.roster)
        self.assertEqual(t.trade_analytics_history, [])

    def test_refuses_when_a_listed_wish_is_not_the_one_fulfilled(self):
        t, f, c, s, center, sg, deal = self.swap(THREE_CENTERS)
        wishes = {"C": wish_of(f, c, "NEED_STARTER", "C"), "S": wish_of(f, s, "ABSORB_SALARY")}
        self.assertFalse(common.close_deal(f, deal, "positional_swap", wishes))
        self.assertIn(center, s.roster)

    def test_executes_and_records_both_wishes(self):
        t, f, c, s, center, sg, deal = self.swap(THREE_CENTERS)
        wishes = {"C": wish_of(f, c, "NEED_STARTER", "C"), "S": wish_of(f, s, "ROLE_CONGESTION", "C")}
        with mock.patch.object(TradeFinder, "execute_deal", wraps=f.execute_deal) as ex:
            self.assertTrue(common.close_deal(f, deal, "positional_swap", wishes))
        ex.assert_called_once()
        self.assertIn(center, c.roster)
        self.assertIn(sg, s.roster)
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "positional_swap")
        self.assertEqual(rec["team_count"], 2)
        self.assertEqual([(m["team"], m["wish_kind"], m["need"]) for m in rec["motives"]],
                         [("C", "NEED_STARTER", "C"), ("S", "ROLE_CONGESTION", "C")])
        self.assertTrue(all(m["reasons"] for m in rec["motives"]))
        self.assertIn("C needed a starting C", rec["why"])
        self.assertEqual(f.logscambi[-1].count("Why:"), 1)

    # ---- price_waived: only the value comparison is waived
    def test_a_waived_team_still_refuses_on_a_plan_hard_no(self):
        t, teams = league({"C": NO_STARTING_C, "S": THREE_CENTERS}, {"C": "CONTENDER", "S": "REBUILDER"})
        f = finder(t)
        c, s = teams["C"], teams["S"]
        vet, center = player(c, "SG", 71), player(s, "C", 77)
        vet.eta, vet.contract.anni_rimanenti = 32, 3   # a rebuilder won't take a 30+ veteran on a long deal
        deal = Deal([c, s], [("C", "S", vet), ("S", "C", center)])
        wishes = {"C": wish_of(f, c, "NEED_STARTER", "C"), "S": wish_of(f, s, "ROLE_CONGESTION", "C")}
        self.assertFalse(common.close_deal(f, deal, "positional_swap", wishes, price_waived=["S"]))
        self.assertIn(center, s.roster)

    def test_a_waived_team_still_refuses_when_its_wish_is_not_fulfilled(self):
        t, f, c, s, center, sg, deal = self.swap(THREE_CENTERS)
        wishes = {"C": wish_of(f, c, "NEED_STARTER", "C"), "S": wish_of(f, s, "ABSORB_SALARY")}
        self.assertFalse(common.close_deal(f, deal, "positional_swap", wishes, price_waived=["C", "S"]))
        self.assertIn(center, s.roster)

    def test_the_waiver_skips_only_the_waived_teams_price(self):
        t, f, c, s, center, sg, deal = self.swap(THREE_CENTERS)
        wishes = {"C": wish_of(f, c, "NEED_STARTER", "C"), "S": wish_of(f, s, "ROLE_CONGESTION", "C")}
        sg._test_value, center._test_value = 1.0, 20.0   # S gives 20 and gets 1: it fails the price question
        self.assertFalse(common.close_deal(f, deal, "positional_swap", wishes))
        self.assertFalse(common.close_deal(f, deal, "positional_swap", wishes, price_waived=["C"]))   # S is not waived
        self.assertIn(center, s.roster)
        self.assertTrue(common.close_deal(f, deal, "positional_swap", wishes, price_waived=["S"]))
        self.assertIn(center, c.roster)


class ExtensionTests(EngineTestCase):
    def stuck(self, third_spec, third_plan="MIDDLE"):
        """C wants S's 9.0M center for a 5.0M guard: over the cap, C can't take the salary back."""
        t, teams = league({"C": NO_STARTING_C, "S": THREE_CENTERS, "X": third_spec},
                          {"C": "CONTENDER", "S": "MIDDLE", "X": third_plan})
        f = finder(t)
        c, s, x = teams["C"], teams["S"], teams["X"]
        real_salary_rule(c, 50.0)
        real_salary_rule(s, 50.0)
        real_salary_rule(x, 30.0)
        center, sg = player(s, "C", 77), player(c, "SG", 71)
        center.contract.salario_annuale = 9.0
        center._test_value, sg._test_value = 60.0, 60.0
        player(c, "PF", 67)._test_value = 1.0   # the cheapest player C can send away
        deal = Deal([c, s], [("C", "S", sg), ("S", "C", center)])
        wishes = {"C": wish_of(f, c, "NEED_STARTER", "C"), "S": wish_of(f, s, "ROLE_CONGESTION", "C")}
        self.assertFalse(c.check_trade_salary_match(9.0, 5.0)[0])
        return t, f, (c, s, x), deal, wishes

    def test_salary_stuck_deal_closes_through_an_absorbing_team(self):
        t, f, (c, s, x), deal, wishes = self.stuck(ABSORBER)
        self.assertTrue(common.close_deal(f, deal, "positional_swap", wishes))
        dumped = player(x, "PF", 67)
        self.assertEqual(dumped.nome, "C-PF12")
        self.assertNotIn(dumped, c.roster)
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["team_count"], 3)
        self.assertEqual(rec["trade_type"], "positional_swap")
        self.assertEqual([(m["team"], m["wish_kind"]) for m in rec["motives"]],
                         [("C", "NEED_STARTER"), ("S", "ROLE_CONGESTION"), ("X", "ABSORB_SALARY")])
        x_picks = [k for y, owned in t.pick_ownership.items() for k, owner in owned.items() if owner == "X"]
        self.assertIn("R2-C", x_picks)   # paid with a pick
        self.assertNotIn("X", wishes)    # the caller's dict is left alone

    def test_extended_star_upgrade_is_a_facilitated_3team(self):
        t, f, _, deal, wishes = self.stuck(ABSORBER)
        self.assertTrue(common.close_deal(f, deal, "star_upgrade", wishes))
        self.assertEqual(t.trade_analytics_history[-1]["trade_type"], "facilitated_3team")
        self.assertEqual(t.trade_analytics_history[-1]["team_count"], 3)

    def test_extend_adds_the_new_teams_wish(self):
        t, f, (c, s, x), deal, wishes = self.stuck(ABSORBER)
        bigger = multi_team.extend(f, deal, wishes)
        self.assertEqual(bigger.team_names(), ["C", "S", "X"])
        self.assertEqual(wishes["X"].kind, "ABSORB_SALARY")
        for team in bigger.teams:
            ins = sum(p.contract.salario_annuale for p in bigger.receives(team.nome) if not isinstance(p, str))
            outs = sum(p.contract.salario_annuale for p in bigger.gives(team.nome) if not isinstance(p, str))
            self.assertTrue(team.check_trade_salary_match(ins, outs)[0], team.nome)

    def test_extend_returns_none_without_a_matching_third_team(self):
        t, f, (c, s, x), deal, wishes = self.stuck(BALANCED, third_plan="CONTENDER")
        self.assertEqual(common.partners_with(f, multi_team.EXTENSION_KINDS, exclude=deal.teams), [])
        self.assertIsNone(multi_team.extend(f, deal, dict(wishes)))
        self.assertFalse(common.close_deal(f, deal, "positional_swap", wishes))
        self.assertEqual(t.trade_analytics_history, [])

    def test_a_small_contract_is_never_paid_with_a_first(self):
        t, f, (c, s, x), deal, wishes = self.stuck(ABSORBER)
        for owned in t.pick_ownership.values():   # C has only its firsts left
            for key in [k for k, owner in owned.items() if owner == "C" and k.startswith("R2-")]:
                owned[key] = "S"
        bigger = multi_team.extend(f, deal, dict(wishes))
        firsts = [a for _src, dst, a in (bigger.moves if bigger else []) if isinstance(a, str) and ":R1-" in a]
        self.assertEqual(firsts, [])

    def test_a_team_that_only_sends_gets_salary_relief_in_the_log(self):
        from trades.motive import log_line
        motive = mock.Mock(why="")
        self.assertEqual(log_line(motive, {"A": "Hale (80, $9.0M)", "B": ""}),
                         "A get Hale (80, $9.0M); B get salary relief")

    def test_extend_returns_none_when_the_absorber_has_no_room(self):
        t, f, (c, s, x), deal, wishes = self.stuck(ABSORBER)
        real_salary_rule(x, 50.0)   # over the cap: it can't take a contract without sending one back
        self.assertIsNone(multi_team.extend(f, deal, dict(wishes)))


class RegistryTests(unittest.TestCase):
    def test_kinds_and_order(self):
        order = {kind: [e.name for e in lst] for kind, lst in engines.ENGINES.items()}
        self.assertEqual(order["NEED_STARTER"], ["positional_swap", "win_now_youth", "star_upgrade"])
        self.assertEqual(order["CLEAR_LONG_CONTRACT"], ["expiring_for_long", "tax_dump"])
        self.assertEqual(order["MOVE_UP_DRAFT"], ["pick_trade_up"])
        self.assertTrue(set(order) <= set(KINDS))

    def test_missing_engines_are_skipped(self):
        swap, *rest = engines.ENGINES["NEED_STARTER"]
        self.assertTrue(swap.available())
        self.assertIs(swap.load(), positional_swap.run)
        missing = engines.LazyEngine("no_such_engine_here")
        self.assertFalse(missing.available())
        self.assertFalse(missing(None, None, None))


class WindowTests(EngineTestCase):
    def stub_league(self, user_team=None, role=None):
        specs = {"C": NO_STARTING_C, "S": THREE_CENTERS, "U": ABSORBER}
        return league(specs, {"C": "CONTENDER", "S": "MIDDLE", "U": "MIDDLE"}, user_team=user_team, role=role)

    def run_with_stub(self, t, stub):
        with mock.patch.dict(engines.ENGINES, {kind: [stub] for kind in KINDS}, clear=True):
            return windows.run_trade_window(t, "deadline")

    def test_each_wish_is_tried_once(self):
        t, teams = self.stub_league()
        calls = []

        def stub(f, team, wish):
            calls.append(wish)
            return False

        count, f = self.run_with_stub(t, stub)
        self.assertEqual(count, 0)
        self.assertEqual(f.window, "deadline")
        every = [w for team in teams.values() for w in f.wishes_for(team)]
        self.assertEqual(sorted(calls, key=repr), sorted(every, key=repr))
        self.assertEqual([w.priority for w in calls], sorted((w.priority for w in calls), reverse=True))

    def test_engines_run_in_order_until_one_closes(self):
        t, teams = self.stub_league()
        seen = []
        first = lambda f, team, wish: seen.append("first") or False
        second = lambda f, team, wish: seen.append("second") or True
        third = lambda f, team, wish: seen.append("third") or False
        with mock.patch.dict(engines.ENGINES, {"NEED_STARTER": [first, second, third]}, clear=True):
            count, _ = windows.run_trade_window(t, "deadline")
        self.assertEqual((count, seen), (1, ["first", "second"]))

    def test_a_wish_gone_after_a_trade_is_skipped(self):
        bench = [("PG", 76), ("PG", 72), ("SG", 76), ("SG", 72), ("SF", 76), ("SF", 72), ("PF", 76), ("PF", 72),
                 ("C", 76), ("C", 60), ("C", 61), ("SG", 62), ("SF", 63)]
        t, teams = league({"B": bench}, {"B": "MIDDLE"})
        calls, traded = [], []

        def stub(f, team, wish):
            calls.append(wish.player)
            if len(calls) == 1:   # the first wish "trades" away another weak bench player
                victim = next(p for p in team.roster if p.ovr < 65 and p.nome != wish.player)
                team.roster.remove(victim)
                traded.append(victim.nome)
                f._clear_trade_caches([team.nome])
                return True
            return False

        with mock.patch.dict(engines.ENGINES, {"BENCH_HOLE": [stub]}, clear=True):
            count, _ = windows.run_trade_window(t, "predraft")
        self.assertEqual(count, 1)
        self.assertEqual(len(calls), 3)   # four BENCH_HOLE wishes, one gone with its player: three tries, once each
        self.assertEqual(len(set(calls)), 3)
        self.assertNotIn(traded[0], calls)

    def test_an_engine_that_raises_is_logged_and_the_next_one_runs(self):
        t, _ = self.stub_league()
        seen = []

        def raiser(f, team, wish):
            seen.append("raiser")
            raise RuntimeError("engine bug")

        closer = lambda f, team, wish: seen.append("closer") or True
        with mock.patch.dict(engines.ENGINES, {"NEED_STARTER": [raiser, closer]}, clear=True), \
                self.assertLogs("main_sim", level="ERROR") as logs:
            count, _ = windows.run_trade_window(t, "deadline")
        self.assertEqual((count, seen), (1, ["raiser", "closer"]))
        self.assertTrue(any("engine bug" in line for line in logs.output))

    def test_a_raising_engine_counts_no_trade_and_other_wishes_still_run(self):
        t, teams = self.stub_league()
        tried = []

        def raiser(f, team, wish):
            tried.append(wish)
            raise RuntimeError("engine bug")

        with mock.patch.dict(engines.ENGINES, {kind: [raiser] for kind in KINDS}, clear=True), \
                self.assertLogs("main_sim", level="ERROR"):
            count, f = windows.run_trade_window(t, "deadline")
        self.assertEqual(count, 0)
        self.assertEqual(len(tried), sum(len(f.wishes_for(team)) for team in teams.values()))

    def test_a_broken_engine_module_is_logged_and_skipped(self):
        t, _ = self.stub_league()
        broken = engines.LazyEngine("broken_engine_for_test")
        seen = []
        closer = lambda f, team, wish: seen.append("closer") or True
        with mock.patch("trades.engines.importlib.import_module", side_effect=SyntaxError("bad engine file")), \
                mock.patch.dict(engines.ENGINES, {"NEED_STARTER": [broken, closer]}, clear=True), \
                self.assertLogs("main_sim", level="ERROR") as logs:
            count, _ = windows.run_trade_window(t, "deadline")
        self.assertEqual((count, seen), (1, ["closer"]))
        self.assertTrue(any("broken_engine_for_test" in line for line in logs.output))

    def test_a_missing_engine_module_is_not_an_error(self):
        t, _ = self.stub_league()
        with mock.patch.dict(engines.ENGINES, {"NEED_STARTER": [engines.LazyEngine("no_such_engine_here")]},
                             clear=True), self.assertNoLogs("main_sim", level="ERROR"):
            self.assertEqual(windows.run_trade_window(t, "deadline")[0], 0)

    def test_user_team_runs_only_without_a_user_gm(self):
        for role, expected in (("gm_coach", False), ("only_coach", True)):
            t, _ = self.stub_league(user_team="U", role=role)
            teams_called = set()
            self.run_with_stub(t, lambda f, team, wish: teams_called.add(team.nome) or False)
            self.assertEqual("U" in teams_called, expected, role)
            self.assertTrue({"C", "S"} <= teams_called)


# A contender with three starting SFs and no starting C.
SF_RICH = [("PG", 77), ("PG", 71), ("SG", 77), ("SG", 71), ("SF", 80), ("SF", 79), ("SF", 78), ("PF", 77),
           ("PF", 71), ("C", 72), ("C", 71), ("SG", 68), ("PF", 67)]
# A playoff team with three starting Cs and no starting SF.
C_RICH = [("PG", 77), ("PG", 71), ("SG", 77), ("SG", 71), ("SF", 72), ("SF", 71), ("PF", 77), ("PF", 71),
          ("C", 80), ("C", 79), ("C", 78), ("SG", 68), ("PF", 67)]
# The same playoff team with a starting SF: still three Cs, but no need at SF.
C_RICH_NO_HOLE = [("PG", 77), ("PG", 71), ("SG", 77), ("SG", 71), ("SF", 77), ("SF", 71), ("PF", 77), ("PF", 71),
                  ("C", 80), ("C", 79), ("C", 78), ("SG", 68), ("PF", 67)]


class PositionalSwapTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        # A player at a role the team lacks is worth a bit more to it than its own surplus player.
        p = mock.patch.object(TradeFinder, "get_strategic_value",
                              lambda self, a, tm, pp=None: 1.0 if isinstance(a, str) else (10.0 if a in tm.roster else 12.0))
        p.start()
        self.addCleanup(p.stop)

    def test_closes_between_two_crossed_teams(self):
        t, teams = league({"A": SF_RICH, "B": C_RICH}, {"A": "CONTENDER", "B": "PLAYOFF"})
        f = finder(t)
        a, b = teams["A"], teams["B"]
        self.assertTrue(positional_swap.run(f, a, wish_of(f, a, "NEED_STARTER", "C")))
        got_c = [p for p in a.roster if p.ruolo == "C" and p.nome.startswith("B-")]
        got_sf = [p for p in b.roster if p.ruolo == "SF" and p.nome.startswith("A-")]
        self.assertEqual(len(got_c), 1)
        self.assertEqual(len(got_sf), 1)
        self.assertLessEqual(abs(got_c[0].ovr - got_sf[0].ovr), CONFIG.TRADES.POSITIONAL_SWAP_MAX_GAP)
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "positional_swap")
        self.assertEqual([(m["wish_kind"], m["need"]) for m in rec["motives"]], [("NEED_STARTER", "C"), ("NEED_STARTER", "SF")])

    def test_no_swap_when_only_one_team_has_the_need(self):
        t, teams = league({"A": SF_RICH, "B": C_RICH_NO_HOLE}, {"A": "CONTENDER", "B": "PLAYOFF"})
        f = finder(t)
        a = teams["A"]
        rosters = {n: list(x.roster) for n, x in teams.items()}
        self.assertFalse(positional_swap.run(f, a, wish_of(f, a, "NEED_STARTER", "C")))
        self.assertEqual({n: x.roster for n, x in teams.items()}, rosters)

    def test_other_wish_kinds_are_not_served(self):
        t, teams = league({"A": SF_RICH, "B": C_RICH}, {"A": "CONTENDER", "B": "PLAYOFF"})
        f = finder(t)
        self.assertFalse(positional_swap.run(f, teams["A"], wish_of(f, teams["A"], "ROLE_CONGESTION", "SF")))


if __name__ == "__main__":
    unittest.main()
