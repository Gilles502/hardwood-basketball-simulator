"""AI GM layer 2a: CPU trades go through the GM (trades/trade_finder.py + core/front_office/trade_brain.py)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office.models import CpuGM, TeamPlan
from core.front_office.state import FrontOfficeState
from core.models import Giocatore
from trades.trade_finder import TradeFinder

FO = CONFIG.FRONT_OFFICE


from tests.trade_fixtures import (  # noqa: E402
    PINNED_DIFFICULTY, abilities, make_player, make_team, make_gm, make_torneo, finder, pin_difficulty)


def team(torneo, name):
    return next(t for t in torneo.squadre if t.nome == name)


class StrategyTests(unittest.TestCase):
    def test_strategy_reads_the_plan(self):
        t = make_torneo([make_team("A", wins=30, losses=5)], plans={"A": "REBUILDER"}, statuses={"A": "Contender"})
        self.assertEqual(finder(t).get_team_strategy(team(t, "A")), "REBUILDER")

    def test_strategy_does_not_flip_midseason(self):
        t = make_torneo([make_team("A", wins=5, losses=25)], plans={"A": "CONTENDER"}, statuses={"A": "Contender"})
        self.assertEqual(finder(t).get_team_strategy(team(t, "A")), "CONTENDER")

    def test_summit_still_overrides_for_user_team(self):
        t = make_torneo([make_team("U"), make_team("B")], user_team="U", plans={"U": "CONTENDER"})
        team(t, "U").front_office_summit = {"completed": True, "agreed_goal": "TANKING"}
        self.assertEqual(finder(t).get_team_strategy(team(t, "U")), "REBUILDER")

    def test_strategy_falls_back_without_plan(self):
        t = make_torneo([make_team("A")], statuses={"A": "Contender"}, with_fo=False)
        self.assertEqual(finder(t).get_team_strategy(team(t, "A")), "CONTENDER")
        t2 = make_torneo([make_team("A")], statuses={"A": "Rebuilding"})  # front office, but no plan
        self.assertEqual(finder(t2).get_team_strategy(team(t2, "A")), "REBUILDER")

    def test_user_team_has_no_gm(self):
        t = make_torneo([make_team("U"), make_team("B")], user_team="U", gms={"B": make_gm("b")})
        f = finder(t)
        self.assertIsNone(f.get_gm(team(t, "U")))
        self.assertEqual(f.get_gm(team(t, "B")).gm_id, "b")
        coach = make_torneo([make_team("U")], user_team="U", role="only_coach", gms={"U": make_gm("u")})
        self.assertEqual(finder(coach).get_gm(team(coach, "U")).gm_id, "u")
        self.assertIsNone(finder(make_torneo([make_team("A")], with_fo=False)).get_gm(make_team("A")))


class ProtectionLineTests(unittest.TestCase):
    def _names(self, f, tm):
        return {p.nome for p in f.get_tradeable_players(tm)}

    def test_tradeable_uses_relative_star_line(self):
        t = make_torneo([make_team("A", ovrs=[88, 87, 86, 85, 70], wins=15, losses=15),
                         make_team("W", ovrs=[88, 87, 86, 85, 70], wins=21, losses=9)])
        f = finder(t)
        with mock.patch.object(TradeFinder, "league_lines", lambda self: {"star": 88, "core": 86, "cap": 100.0,
                                                                          "profiles": {}}):
            self.assertEqual(self._names(f, team(t, "A")), {"A-1", "A-2", "A-3", "A-4"})
            self.assertEqual(self._names(f, team(t, "W")), {"W-3", "W-4"})

    def test_tradeable_matches_today_on_floor_lines(self):
        t = make_torneo([make_team("A", ovrs=[85, 82, 70], wins=15, losses=15),
                         make_team("W", ovrs=[85, 82, 70], wins=21, losses=9)]
                        + [make_team(f"F{i}") for i in range(3)])  # 45 players: lines at the floors
        f = finder(t)
        self.assertEqual(f.league_lines()["star"], 85)
        self.assertEqual(f.league_lines()["core"], 80)
        self.assertEqual(self._names(f, team(t, "A")), {"A-1", "A-2"})
        self.assertEqual(self._names(f, team(t, "W")), {"W-2"})


def value_of(f, asset, tm):
    return f.get_strategic_value(asset, tm)


class ValuationTests(unittest.TestCase):
    def _league(self, gms, user_team=None, extra=()):
        teams = [make_team(n) for n in ("H", "N", "U")] + list(extra)
        return make_torneo(teams, user_team=user_team, gms=gms,
                           plans={t.nome: "MIDDLE" for t in teams})

    def test_pick_hoarder_values_picks_more(self):
        t = self._league({"H": make_gm("h", ["PICK_HOARDER"]), "N": make_gm("n")})
        f = finder(t)
        ratio = value_of(f, "1:R1-U", team(t, "H")) / value_of(f, "1:R1-U", team(t, "N"))
        self.assertAlmostEqual(ratio, 1.20, places=3)

    def test_youth_vs_veteran_split(self):
        t = self._league({"H": make_gm("v", ["VETERAN_LOVER"]), "N": make_gm("y", ["YOUTH_FIRST"])})
        f = finder(t)
        vet, kid = make_player("vet", ovr=78, age=31), make_player("kid", ovr=74, age=22)
        self.assertGreater(value_of(f, vet, team(t, "H")), value_of(f, vet, team(t, "N")))
        self.assertGreater(value_of(f, kid, team(t, "N")), value_of(f, kid, team(t, "H")))

    def test_loyalist_holds_own_long_tenure(self):
        t = self._league({"H": make_gm("l", ["LOYALIST"]), "N": make_gm("l2", ["LOYALIST"]),
                          "U": make_gm("u")})
        f = finder(t)
        mine = make_player("mine", ovr=74, team_years=5)
        team(t, "H").roster.append(mine)
        self.assertAlmostEqual(value_of(f, mine, team(t, "H")) / value_of(f, mine, team(t, "U")), 1.15, places=3)
        self.assertAlmostEqual(value_of(f, mine, team(t, "N")) / value_of(f, mine, team(t, "U")), 1.0, places=3)

    def test_coach_fit_bonus_applies(self):
        towers = make_team("T", style="Twin Towers")
        space = make_team("S", style="Pace & Space")
        t = make_torneo([towers, space, make_team("X")], gms={"T": make_gm("t"), "S": make_gm("s")},
                        plans={"T": "MIDDLE", "S": "MIDDLE", "X": "MIDDLE"})
        attrs = FO.COACH_STYLE_ATTRIBUTES["Twin Towers"]
        big = make_player("big", ovr=74, abil=abilities(40, **{a: 80 for a in attrs}))
        f = finder(t)
        self.assertAlmostEqual(value_of(f, big, towers) / value_of(f, big, space), FO.COACH_FIT_BONUS, places=3)

    def test_user_team_has_no_gm_effects(self):
        t = self._league({"U": make_gm("stale", ["PICK_HOARDER"]), "N": make_gm("n")}, user_team="U")
        f = finder(t)
        self.assertAlmostEqual(value_of(f, "1:R1-H", team(t, "U")), value_of(f, "1:R1-H", team(t, "N")))


def valued(name, value, ovr=70):
    p = make_player(name, ovr=ovr)
    p._test_value = value
    return p


class PriceTests(unittest.TestCase):
    """1-for-1 deals of 70-OVR players with fixed values: only the threshold decides."""

    def setUp(self):
        values = mock.patch.object(TradeFinder, "get_strategic_value",
                                   lambda self, a, tm, pp=None: getattr(a, "_test_value", 10.0))
        noise = mock.patch("trades.trade_finder.random.uniform", return_value=0.0)
        values.start()
        noise.start()
        self.addCleanup(values.stop)
        self.addCleanup(noise.stop)
        pin_difficulty(self)   # skill and squeeze ratios below are set against this calibration

    def _accepts(self, skill, ratio, user=False, role=None, traits=()):
        teams = [make_team("C"), make_team("U"), make_team("O")]
        t = make_torneo(teams, user_team="U" if (user or role) else None, role=role,
                        gms={"C": make_gm("c", traits, trade=skill)}, plans={n.nome: "MIDDLE" for n in teams})
        source = team(t, "U") if (user or role) else team(t, "O")
        incoming = valued("in", 100.0 * ratio)
        source.roster.append(incoming)
        outgoing = valued("out", 100.0)
        team(t, "C").roster.append(outgoing)
        return finder(t).would_accept_trade(team(t, "C"), [incoming], [outgoing])

    def test_skill_moves_the_threshold(self):
        self.assertTrue(self._accepts(50, 1.00))
        self.assertFalse(self._accepts(82, 1.00))

    def test_user_counterpart_pays_squeeze(self):
        self.assertTrue(self._accepts(82, 1.03))
        self.assertFalse(self._accepts(82, 1.03, user=True))

    def test_user_pick_counts_as_user_side(self):
        teams = [make_team("C"), make_team("U")]
        t = make_torneo(teams, user_team="U", gms={"C": make_gm("c", trade=82)},
                        plans={"C": "MIDDLE", "U": "MIDDLE"})
        f = finder(t)
        t.pick_ownership[1]["R1-U"] = "U"
        self.assertTrue(f._comes_from_user(["1:R1-U"]))
        t.pick_ownership[1]["R1-U"] = "C"
        self.assertFalse(f._comes_from_user(["1:R1-U"]))
        self.assertTrue(f._comes_from_user([team(t, "U").roster[0]]))
        self.assertFalse(f._comes_from_user([team(t, "C").roster[0]]))

    def test_trade_happy_deals_a_little_cheaper(self):
        # MIDDLE on realistic: 1.02 x the realistic multiplier; trade happy x TRADE_HAPPY_THRESHOLD_MULT on top
        plain = 1.02 * PINNED_DIFFICULTY["realistic"][0]
        between = plain * (1.0 + CONFIG.FRONT_OFFICE.TRADE_HAPPY_THRESHOLD_MULT) / 2
        self.assertFalse(self._accepts(60, between))
        self.assertTrue(self._accepts(60, between, traits=["TRADE_HAPPY"]))

    def test_no_squeeze_in_spectator(self):
        self.assertTrue(self._accepts(82, 1.03, role="spectator"))

    def test_disaster_bypasses_floor_only_below_35(self):
        factor = lambda skill, rng: 0.85 if skill is not None and skill < 35 else 1.0
        with mock.patch("core.front_office.trade_brain.disaster_factor", side_effect=factor):
            self.assertTrue(self._accepts(20, 0.75))
            self.assertFalse(self._accepts(45, 0.75))



# ---------------------------------------------------------------- deals on wishes (Task 14 rewrite)
# The old random entry points (TradeFinder.attempt_* and gestisci_asta_giocatore) are gone: the same GM scenarios
# now go through the wish engines (trades/engines) and the window runner (trades/windows.py).
from core.front_office.wishes import KINDS  # noqa: E402
from trades import engines, windows  # noqa: E402
from trades.engines import auction, common, pick_trade_up, star_upgrade, tax_dump, veteran_sale  # noqa: E402
from tests.test_trade_engines_framework import EngineTestCase, ABSORBER, league, player, wish_of  # noqa: E402

# A rebuilder with an 86 SF and an 80 PF.
SELLER = [("PG", 68), ("PG", 64), ("SG", 66), ("SG", 64), ("SF", 86), ("SF", 62), ("PF", 80), ("PF", 62),
          ("C", 66), ("C", 62), ("SG", 60), ("SF", 60), ("PF", 60)]
# Contenders with no starting SF / PF / SG (best 72 at that role).
SF_HOLE = [("PG", 76), ("PG", 69), ("SG", 76), ("SG", 68), ("SF", 72), ("SF", 69), ("PF", 76), ("PF", 69),
           ("C", 76), ("C", 69), ("SG", 66), ("SF", 66), ("PF", 67)]
PF_HOLE = [("PG", 76), ("PG", 69), ("SG", 76), ("SG", 68), ("SF", 76), ("SF", 69), ("PF", 72), ("PF", 69),
           ("C", 76), ("C", 69), ("SG", 66), ("SF", 66), ("PF", 67)]
SG_HOLE = [("PG", 76), ("PG", 69), ("SG", 72), ("SG", 68), ("SF", 76), ("SF", 69), ("PF", 76), ("PF", 69),
           ("C", 76), ("C", 69), ("SG", 66), ("SF", 66), ("PF", 67)]
# A playoff team without a starting PG (best PG 72) and no star.
PG_HOLE = [("PG", 72), ("PG", 69), ("SG", 77), ("SG", 72), ("SF", 77), ("SF", 72), ("PF", 77), ("PF", 72),
           ("C", 77), ("C", 72), ("SG", 68), ("SF", 68), ("PF", 67)]

NEED_KINDS = ("NEED_STARTER", "WANT_STAR")


def no_shuffle():
    return mock.patch("trades.engines.common.random.shuffle", lambda seq: None)


def seat_gm(torneo, team_name, gm):
    gm.team = team_name
    torneo.front_office.gms[gm.gm_id] = gm
    torneo.front_office.seats[team_name] = gm.gm_id


def kinds_of(f, tm):
    return [w.kind for w in f.wishes_for(tm)]


def aged(p, age, pot=None):
    p.eta = age
    if pot is not None:
        p.potenziale = pot
    return p


def values_by_team(table, default=10.0):
    """get_strategic_value stand-in: table[(team name, asset name)], else `default` (picks too)."""
    def value(self, asset, tm, pp=None):
        return table.get((tm.nome, getattr(asset, "nome", asset)), default)
    return mock.patch.object(TradeFinder, "get_strategic_value", value)


class WishEntryTests(EngineTestCase):
    """Who sits at a deal: was decided by the old attempt_* entry rules, now by wishes (vultures keep their seats)."""

    def _auction_league(self, vultures=("B11",)):
        specs = {"Seller": SELLER, **{f"B{i}": SF_HOLE for i in range(12)}}
        plans = {"Seller": "REBUILDER", **{f"B{i}": "CONTENDER" for i in range(12)}}
        t, teams = league(specs, plans)
        for name in vultures:
            seat_gm(t, name, make_gm(f"v-{name}", trade=75))
        return t, teams

    def _seats(self, t, teams, kinds=NEED_KINDS, target=None):
        with no_shuffle():
            return [tm.nome for tm, _ in auction.seat_bidders(finder(t), teams["Seller"], kinds, target)]

    def test_vultures_first_in_auction(self):
        t, teams = self._auction_league()
        self.assertEqual(self._seats(t, teams)[0], "B11")

    def test_vultures_capped_in_auction(self):
        names = [f"B{i}" for i in range(7, 12)]
        t, teams = self._auction_league(vultures=names)
        seats = self._seats(t, teams)
        slots = FO.VULTURE_GUARANTEED_SLOTS
        self.assertEqual(seats[:slots], names[:slots])
        self.assertEqual(sum(1 for n in seats[:CONFIG.TRADES.AUCTION_MAX_BIDDERS] if n in names), slots)

    def test_pick_hoarder_bids_on_a_veteran_only_with_a_need(self):
        # was test_pick_hoarder_skips_veteran_dump_auction: the trait no longer bars a bidder, his wishes decide
        t, teams = league({"Seller": SELLER, "H": ABSORBER, "HC": PF_HOLE},
                          {"Seller": "REBUILDER", "H": "MIDDLE", "HC": "CONTENDER"})
        seat_gm(t, "H", make_gm("h", ["PICK_HOARDER"]))
        seat_gm(t, "HC", make_gm("hc", ["PICK_HOARDER"]))
        vet = aged(player(teams["Seller"], "PF", 80), 33)
        self.assertEqual(self._seats(t, teams, veteran_sale.BIDDER_KINDS, vet), ["HC"])

    def _dump_partners(self, hoarder_payroll=30.0):
        """The absorbers a team over the tax asks, in order (every deal refused so all are asked)."""
        t, teams = league({"D": ABSORBER, "Rich": ABSORBER, "V": ABSORBER, "H": ABSORBER},
                          {"D": "CONTENDER", "Rich": "REBUILDER", "V": "REBUILDER", "H": "PLAYOFF"})
        seat_gm(t, "V", make_gm("v", trade=75))
        seat_gm(t, "H", make_gm("h", ["PICK_HOARDER"]))
        teams["D"].payroll = 65.0   # over the 60.0 tax line of the test era: SHED_TAX
        teams["Rich"].payroll = teams["V"].payroll = 30.0
        teams["H"].payroll = hoarder_payroll
        asked = []

        def refuse(f_, deal, trade_type, wishes, **kwargs):
            asked.append(deal.teams[1].nome)
            return False

        f = finder(t)
        with no_shuffle(), mock.patch.object(common, "close_deal", side_effect=refuse):
            self.assertFalse(tax_dump.run(f, teams["D"], wish_of(f, teams["D"], "SHED_TAX")))
        return list(dict.fromkeys(asked)), f, teams

    def test_vultures_first_in_tax_dump(self):
        # was test_vultures_first_in_cap_relief (attempt_cap_relief_trade)
        self.assertEqual(self._dump_partners()[0][0], "V")

    def test_pick_hoarder_absorbs_salary_on_any_plan(self):
        asked, f, teams = self._dump_partners(30.0)
        self.assertIn("ABSORB_SALARY", kinds_of(f, teams["H"]))   # a PLAYOFF plan, but a hoarder
        self.assertIn("H", asked)
        asked, f, teams = self._dump_partners(61.0)              # over the tax: nothing to absorb with
        self.assertNotIn("ABSORB_SALARY", kinds_of(f, teams["H"]))
        self.assertNotIn("H", asked)

    def test_a_pick_hoarder_does_not_trade_up(self):
        t, teams = league({"H": ABSORBER, "N": ABSORBER}, {"H": "MIDDLE", "N": "MIDDLE"})
        seat_gm(t, "H", make_gm("h", ["PICK_HOARDER"]))
        seat_gm(t, "N", make_gm("n"))
        f = finder(t)
        with mock.patch.object(TradeFinder, "_move_up_slot", return_value=1):
            f.begin_window("predraft")
            self.assertNotIn("MOVE_UP_DRAFT", kinds_of(f, teams["H"]))   # moving up is a rebuilder's, for a prospect
            self.assertIn("MOVE_DOWN_DRAFT", kinds_of(f, teams["H"]))

    def test_pick_hoarder_sells_30_plus_vets(self):
        t, teams = league({"H": ABSORBER, "N": ABSORBER}, {"H": "MIDDLE", "N": "MIDDLE"})
        seat_gm(t, "H", make_gm("h", ["PICK_HOARDER"]))
        for tm in teams.values():
            aged(tm.roster[0], FO.PICK_HOARDER_SELL_MIN_AGE + 1)   # a 72 PG, over the 70 rotation line
        with mock.patch("core.front_office.wishes.random.random", return_value=0.9):   # roll above the chance
            self.assertNotIn("SELL_VETERANS", kinds_of(finder(t), teams["H"]))
        with mock.patch("core.front_office.wishes.random.random", return_value=0.1):
            f = finder(t)
            self.assertIn("SELL_VETERANS", kinds_of(f, teams["H"]))
            self.assertNotIn("SELL_VETERANS", kinds_of(f, teams["N"]))
        sold = []
        with mock.patch.object(auction, "run_auction", side_effect=lambda f_, seller, p, *a: sold.append(p) or False):
            veteran_sale.run(f, teams["H"], wish_of(f, teams["H"], "SELL_VETERANS"))
        self.assertTrue(sold)
        self.assertTrue(all(p.eta >= FO.PICK_HOARDER_SELL_MIN_AGE for p in sold))

    def test_a_rebuilder_sells_whatever_the_gm_trait(self):
        # was test_aggressive_rebuild_chance_by_trait: no random "package picks for a young star" branch any more
        t, teams = league({n: ABSORBER for n in "SNP"}, {n: "REBUILDER" for n in "SNP"})
        seat_gm(t, "S", make_gm("s", ["STAR_CHASER"]))
        seat_gm(t, "N", make_gm("n"))
        seat_gm(t, "P", make_gm("p", ["PATIENT_BUILDER"]))
        for tm in teams.values():
            aged(tm.roster[0], 31)
        f = finder(t)
        for name in "SNP":
            kinds = kinds_of(f, teams[name])
            self.assertNotIn("WANT_STAR", kinds, name)
            self.assertIn("SELL_VETERANS", kinds, name)
            self.assertIn("WANT_PICKS", kinds, name)


class StarTargetTests(EngineTestCase):
    """star_upgrade (was attempt_upgrade_trade): which target a buyer ends up with, and who sells."""

    def test_target_is_the_one_he_values_most(self):
        t, teams = league({"Buyer": SG_HOLE, "Seller": ABSORBER}, {"Buyer": "CONTENDER", "Seller": "REBUILDER"})
        seat_gm(t, "Buyer", make_gm("b", ["YOUTH_FIRST"]))
        buyer, seller = teams["Buyer"], teams["Seller"]
        old82 = aged(make_player("old82", ovr=82, role="SG"), 31)
        kid81 = aged(make_player("kid81", ovr=81, role="SG"), 27, 81)   # 27: a rebuilder keeps a good player under 27
        seller.roster += [old82, kid81]
        # The better OVR is tried first, but he values old82 below any price the seller takes: he ends with the kid.
        table = {("Buyer", "old82"): 12.0, ("Buyer", "kid81"): 100.0,
                 ("Seller", "old82"): 15.0, ("Seller", "kid81"): 9.0}
        f = finder(t)
        with values_by_team(table):
            self.assertTrue(star_upgrade.run(f, buyer, wish_of(f, buyer, "NEED_STARTER", "SG")))
        self.assertIn(kid81, buyer.roster)
        self.assertIn(old82, seller.roster)

    def _chaser_league(self, traits, seller_plan="REBUILDER", seller_payroll=50.0):
        t, teams = league({"Buyer": PG_HOLE, "Seller": SELLER}, {"Buyer": "PLAYOFF", "Seller": seller_plan})
        seat_gm(t, "Buyer", make_gm("b", traits))
        teams["Seller"].payroll = seller_payroll
        star = aged(player(teams["Seller"], "SF", 86), 29)
        young = aged(player(teams["Buyer"], "SG", 68), 24, 80)   # to pay with: two firsts would break Stepien
        young.contract.salario_annuale = 1.0   # a cheap contract: the over-the-tax seller still sheds salary
        table = {("Buyer", star.nome): 30.0, ("Seller", star.nome): 15.0}
        return t, teams, star, values_by_team(table)

    def test_star_chaser_ignores_position_need(self):
        t, teams, star, values = self._chaser_league(["STAR_CHASER"])
        f = finder(t)
        with values:
            self.assertTrue(star_upgrade.run(f, teams["Buyer"], wish_of(f, teams["Buyer"], "WANT_STAR")))
        self.assertIn(star, teams["Buyer"].roster)
        t, teams, star, values = self._chaser_league([])
        f = finder(t)
        self.assertNotIn("WANT_STAR", kinds_of(f, teams["Buyer"]))   # a playoff team, already without a star
        with values:
            star_upgrade.run(f, teams["Buyer"], wish_of(f, teams["Buyer"], "NEED_STARTER", "PG"))
        self.assertIn(star, teams["Seller"].roster)

    def test_star_chaser_calls_playoff_teams(self):
        # A playoff team sells only with a selling wish: here SHED_TAX once over the 60.0 tax line by more than its
        # (mid-tier) owner's margin, CONFIG.TRADES.SHED_TAX_OVER_SHARE_BY_TIER["mid"] of the cap.
        t, teams, star, values = self._chaser_league(["STAR_CHASER"], "PLAYOFF", 50.0)
        f = finder(t)
        with values:
            self.assertFalse(star_upgrade.run(f, teams["Buyer"], wish_of(f, teams["Buyer"], "WANT_STAR")))
        over = 60.0 + CONFIG.TRADES.SHED_TAX_OVER_SHARE_BY_TIER["mid"] * 40.27 + 0.5
        t, teams, star, values = self._chaser_league(["STAR_CHASER"], "PLAYOFF", over)
        star.contract.salario_annuale = 8.0   # the cut (8 out, 1 back) brings the seller back to the tax line
        f = finder(t)
        with values:
            self.assertTrue(star_upgrade.run(f, teams["Buyer"], wish_of(f, teams["Buyer"], "WANT_STAR")))
        self.assertIn(star, teams["Buyer"].roster)


def bench_league(traits, other=("TRADE_HAPPY",)):
    ovrs = list(range(80, 67, -1))  # 13 players, 80 down to 68
    teams = [make_team("Happy", ovrs=ovrs), make_team("Other", ovrs=ovrs)]
    for tm, role in zip(teams, ("C", "PG")):   # each bench long at a role the other is short at: a reason to swap
        for p in tm.roster[9:]:
            p.ruolo = role
    t = make_torneo(teams, gms={"Happy": make_gm("h", traits), "Other": make_gm("o", other)},
                    plans={"Happy": "MIDDLE", "Other": "MIDDLE"})
    t.trade_analytics_history = []
    return t, {tm.nome: tm for tm in teams}


class WindowTests(EngineTestCase):
    """trades/windows.run_trade_window with every engine stubbed: no per-team or per-type limit is left."""

    def _run(self, window, t, closes):
        stub = lambda f, team, wish: closes(team, wish)
        with mock.patch.dict(engines.ENGINES, {kind: [stub] for kind in KINDS}, clear=True):
            return windows.run_trade_window(t, window)

    def test_a_trade_happy_rebuilder_has_no_deal_limit(self):
        # was test_trade_happy_rebuilder_limit_at_deadline (2 + 1 rebuilder + 1 trade happy) and
        # test_trade_happy_gets_extra_deal (deal_limit_bonus): every wish of his is tried, and each may close
        teams = [make_team("X")] + [make_team(f"F{i}") for i in range(5)]
        t = make_torneo(teams, gms={"X": make_gm("x", ["TRADE_HAPPY"])},
                        plans={"X": "REBUILDER", **{f"F{i}": "MIDDLE" for i in range(5)}})
        t.trade_analytics_history = []
        count, f = self._run("deadline", t, lambda team, wish: team.nome == "X")
        self.assertEqual(count, len(f.wishes_for(team(t, "X"))))
        self.assertGreater(count, 2 + 1 + 1)

if __name__ == "__main__":
    unittest.main()
