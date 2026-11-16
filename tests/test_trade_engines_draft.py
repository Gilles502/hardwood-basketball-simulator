"""Draft engines: pick trade-up (MOVE_UP_DRAFT) and draft night."""
import unittest
from types import SimpleNamespace
from unittest import mock

from core.config import CONFIG
from offseason.draft import Draft
from trades import engines, windows
from trades.engines import draft_night, pick_trade_up
from trades.trade_finder import TradeFinder
from tests.test_trade_engines_framework import ABSORBER, EngineTestCase, wish_of
from tests.trade_fixtures import finder, make_gm, make_player, make_torneo, pin_difficulty, roster_team

FILLERS = [f"F{i}" for i in range(1, 7)]   # six other teams ahead in the lottery order: no pick of ours is top 5


def owners(torneo, key, year=1):
    return torneo.pick_ownership[year][key]


def pick_league(order, plans=None, gms=None):
    """R (rebuilding, wants a higher pick) and H (a hoarder, happy to move down) with the draft order `order`."""
    specs = {"R": ABSORBER, "H": ABSORBER}
    teams = [roster_team(n, s) for n, s in specs.items()]
    t = make_torneo(teams, plans=plans or {"R": "REBUILDER", "H": "MIDDLE"}, gms=gms if gms is not None else {"H": make_gm("gm-h", traits=["PICK_HOARDER"])})
    t.trade_analytics_history = []
    t.pick_ownership = {y: {f"R{r}-{n}": n for n in specs for r in (1, 2)} for y in range(1, 6)}
    t.pick_protections = {y: {} for y in range(1, 6)}
    t.draft_lottery_order = order
    return t, {team.nome: team for team in teams}


def pick_worths(self, asset, team, protections=None):
    """Test values (declared override): this year's firsts by slot, a second or a later first 0.6 (so a first and either one equal the higher first)."""
    if not isinstance(asset, str):
        return getattr(asset, "_test_value", 10.0)
    return {"1:R1-H": 3.1, "1:R1-R": 2.5}.get(asset, 0.6)


class PickTradeUpTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        for patch in (mock.patch.object(TradeFinder, "get_strategic_value", pick_worths),
                      mock.patch.object(TradeFinder, "_move_up_slot", side_effect=lambda team: self.slot)):
            patch.start()
            self.addCleanup(patch.stop)
        self.slot = 7   # R wants the prospect projected 7th
        self.t, self.teams = pick_league(FILLERS + ["H", "R"])   # H picks 7th, R 8th
        self.f = finder(self.t)
        self.f.begin_window("predraft")

    def test_a_rebuilder_moves_up_with_a_hoarder_for_two_firsts(self):
        r_wish = wish_of(self.f, self.teams["R"], "MOVE_UP_DRAFT")
        self.assertTrue(pick_trade_up.run(self.f, self.teams["R"], r_wish))
        self.assertEqual(owners(self.t, "R1-H"), "R")
        self.assertEqual(owners(self.t, "R1-R"), "H")
        h_seconds = sum(1 for y in self.t.pick_ownership.values() for k, o in y.items() if k.startswith("R2") and o == "H")
        self.assertEqual(h_seconds, 5)   # its own five: seconds never sweeten a deal
        rec = self.t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "pick_trade_up")
        self.assertEqual(rec["motives"][0]["wish_kind"], "MOVE_UP_DRAFT")
        self.assertIn(rec["motives"][1]["wish_kind"], ("MOVE_DOWN_DRAFT", "WANT_PICKS"))

    def test_without_a_second_it_pays_with_a_future_first_too(self):
        for y, owned in self.t.pick_ownership.items():
            owned["R2-R"] = "H"
        self.assertTrue(pick_trade_up.run(self.f, self.teams["R"], wish_of(self.f, self.teams["R"], "MOVE_UP_DRAFT")))
        self.assertEqual(owners(self.t, "R1-H"), "R")
        self.assertEqual([y for y in range(2, 6) if owners(self.t, "R1-R", y) == "H"].__len__(), 1)

    def test_the_first_received_must_be_higher_than_the_one_sent(self):
        self.t.draft_lottery_order = FILLERS + ["R", "H"]   # now R picks 7th and H 8th: H's first is lower
        f = finder(self.t)
        f.begin_window("predraft")
        wish = wish_of(f, self.teams["R"], "MOVE_UP_DRAFT")   # the wish alone is met by any first this year
        self.assertFalse(pick_trade_up.run(f, self.teams["R"], wish))
        self.assertEqual(owners(self.t, "R1-H"), "H")
        self.assertEqual(self.t.trade_analytics_history, [])

    def test_it_does_not_buy_a_first_below_the_prospect_it_wants(self):
        self.slot = 6   # its man is projected 6th: H's 7th is too late for him
        f = finder(self.t)
        f.begin_window("predraft")
        self.assertFalse(pick_trade_up.run(f, self.teams["R"], wish_of(f, self.teams["R"], "MOVE_UP_DRAFT")))
        self.assertEqual(owners(self.t, "R1-H"), "H")

    def test_no_prospect_in_mind_no_wish_to_move_up(self):
        self.slot = None
        f = finder(self.t)
        f.begin_window("predraft")
        self.assertNotIn("MOVE_UP_DRAFT", [w.kind for w in f.wishes_for(self.teams["R"])])

    def test_a_partner_with_no_wish_to_move_down_or_collect_picks_does_not_trade(self):
        t, teams = pick_league(FILLERS + ["H", "R"], gms={})   # H: MIDDLE, no traits
        f = finder(t)
        f.begin_window("predraft")
        self.assertEqual([w.kind for w in f.wishes_for(teams["H"]) if w.kind in ("MOVE_DOWN_DRAFT", "WANT_PICKS")], [])
        self.assertFalse(pick_trade_up.run(f, teams["R"], wish_of(f, teams["R"], "MOVE_UP_DRAFT")))
        self.assertEqual(owners(t, "R1-H"), "H")
        self.assertEqual(t.trade_analytics_history, [])

    def test_a_top_5_first_can_be_bought_when_the_price_is_paid(self):
        t, teams = pick_league(["H"] + FILLERS + ["R"])   # H holds the first pick: no lock, only the price
        self.slot = 1
        f = finder(t)
        f.begin_window("predraft")
        self.assertTrue(pick_trade_up.run(f, teams["R"], wish_of(f, teams["R"], "MOVE_UP_DRAFT")))
        self.assertEqual(owners(t, "R1-H"), "R")

    def _payer(self, age):
        young = make_player("R-young", ovr=78, age=age, role="SF", pot=85)
        young._test_value = 3.5   # worth more than the first it buys, under MOVE_UP_MAX_OVERPAY x 3.1
        self.teams["R"].roster.append(young)
        return young

    def test_it_can_pay_with_a_young_player_when_picks_are_not_enough(self):
        young = self._payer(age=24)
        with mock.patch.object(pick_trade_up, "_with_picks", return_value=False):
            self.assertTrue(pick_trade_up.run(self.f, self.teams["R"], wish_of(self.f, self.teams["R"], "MOVE_UP_DRAFT")))
        self.assertEqual(owners(self.t, "R1-H"), "R")
        self.assertIn(young, self.teams["H"].roster)

    def test_a_29_year_old_does_not_buy_a_pick(self):
        self._payer(age=CONFIG.DRAFT_AI.PICK_PAY_MAX_AGE + 1)
        with mock.patch.object(pick_trade_up, "_with_picks", return_value=False):
            self.assertFalse(pick_trade_up.run(self.f, self.teams["R"], wish_of(self.f, self.teams["R"], "MOVE_UP_DRAFT")))
        self.assertEqual(owners(self.t, "R1-H"), "H")

    def test_other_wish_kinds_are_not_served(self):
        self.assertFalse(pick_trade_up.run(self.f, self.teams["R"], wish_of(self.f, self.teams["R"], "WANT_PICKS")))

    def test_registered_for_move_up_draft(self):
        self.assertIn("pick_trade_up", [e.name for e in engines.engines_for("MOVE_UP_DRAFT")])


def bench_league(specs, happy=("T", "P")):
    teams = [roster_team(n, s) for n, s in specs.items()]
    gms = {n: make_gm(f"gm-{n}", traits=["TRADE_HAPPY"]) for n in happy}
    t = make_torneo(teams, plans={n: "MIDDLE" for n in specs}, gms=gms)
    t.trade_analytics_history = []
    t.pick_ownership = {y: {f"R{r}-{n}": n for n in specs for r in (1, 2)} for y in range(1, 6)}
    t.pick_protections = {y: {} for y in range(1, 6)}
    return t, {team.nome: team for team in teams}


HOLE = [("PG", 72), ("PG", 70), ("SG", 72), ("SG", 70), ("SF", 72), ("SF", 70), ("PF", 72), ("PF", 70),
        ("C", 72), ("C", 70), ("SG", 60), ("SF", 66), ("PF", 66)]   # a 60 at the end of the bench: BENCH_HOLE


# Two rosters a bench swap helps both ways: T is long at C and short at PG, P the other way round.
LONG_C = [("PG", 72), ("PG", 70), ("SG", 72), ("SG", 70), ("SF", 72), ("SF", 70), ("PF", 72), ("PF", 70),
          ("C", 72), ("C", 70), ("C", 66), ("SF", 66), ("PF", 66)]
LONG_PG = [("PG", 72), ("PG", 70), ("SG", 72), ("SG", 70), ("SF", 72), ("SF", 70), ("PF", 72), ("PF", 70),
           ("C", 72), ("C", 70), ("PG", 66), ("SF", 66), ("PF", 66)]


BOARD = [("PG", 90), ("SG", 88), ("C", 86), ("SF", 84)]   # (role, potential), best first


def night_league(order, c_plan="MIDDLE", p_plan="REBUILDER", c_gm=True, p_gm=False, made=2):
    """C is on the clock; P (a rebuilder) has a later first. `made`: picks already made."""
    specs = {"C": ABSORBER, "P": ABSORBER}
    teams = [roster_team(n, s) for n, s in specs.items()]
    gms = {}
    if c_gm:
        gms["C"] = make_gm("gm-c", traits=["PICK_HOARDER"])
    if p_gm:
        gms["P"] = make_gm("gm-p", traits=["PICK_HOARDER"])
    t = make_torneo(teams, plans={"C": c_plan, "P": p_plan}, gms=gms)
    t.trade_analytics_history = []
    t.pick_ownership = {y: {f"R{r}-{n}": n for n in specs for r in (1, 2)} for y in range(1, 6)}
    t.pick_protections = {y: {} for y in range(1, 6)}
    t.draft_lottery_order = order
    t.draft_pick_corrente = made
    t.draft_class = [make_player(f"Pr{i}", ovr=55, age=19, role=role, pot=pot) for i, (role, pot) in enumerate(BOARD)]
    return t, {team.nome: team for team in teams}


ORDER = ["F1", "F2", "C", "P", "F3", "F4"]   # C picks 3rd, P 4th
FAR_ORDER = ["F1", "F2", "C", "F3", "F4", "P"]   # C picks 3rd, P 6th


class DraftNightTests(unittest.TestCase):
    """Real strategic values: no overrides."""
    def setUp(self):
        patches = [
            mock.patch.object(TradeFinder, "_log_trade_to_file"),
            mock.patch("core.news_generator.add_news"),
            mock.patch("trades.trade_finder.random.uniform", return_value=0.0),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        pin_difficulty(self)   # real values, priced at the calibration these slot distances were measured on
        for p in (mock.patch.object(TradeFinder, "_move_up_slot", return_value=3),   # P (a rebuilder) wants the man at #3
                  mock.patch.object(TradeFinder, "_prospect_pick_value", return_value=None)):   # the slot price these
            p.start()                                                                          # distances were measured on
            self.addCleanup(p.stop)

    def test_a_hoarder_on_the_clock_moves_down_with_a_rebuilder_and_the_dict_keeps_its_shape(self):
        t, teams = night_league(ORDER)
        f = finder(t)
        res = draft_night.run_on_the_clock(f, teams["C"], 3, "R1-C")
        self.assertIsNotNone(res)
        self.assertEqual(f.window, "draft")
        for key in ("team_on_clock", "partner", "player_involved", "player_ovr", "pick_given", "pick_received", "description"):
            self.assertIn(key, res)
        self.assertEqual((res["team_on_clock"], res["partner"], res["pick_given"], res["pick_received"]), ("C", "P", 3, 4))
        self.assertEqual(owners(t, "R1-C"), "P")   # draft.py reads this to see who picks now
        self.assertEqual(owners(t, "R1-P"), "C")
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "draft_night")
        self.assertEqual(rec["motives"][0]["wish_kind"], "MOVE_DOWN_DRAFT")
        self.assertIn(rec["motives"][1]["wish_kind"], ("MOVE_UP_DRAFT", "TARGET_PROSPECT"))

    def test_with_real_values_three_to_six_closes_with_a_future_first(self):
        # Documents what the real values say (picks on the player curve): #6 plus a future first covers the #3.
        t, teams = night_league(FAR_ORDER)
        self.assertIsNotNone(draft_night.run_on_the_clock(finder(t), teams["C"], 3, "R1-C"))
        self.assertEqual(owners(t, "R1-C"), "P")

    @mock.patch.object(TradeFinder, "_move_up_slot", return_value=None)   # P has no prospect in mind
    def test_nobody_with_a_draft_wish_means_none(self, _slot):
        t, teams = night_league(ORDER, p_plan="MIDDLE")
        f = finder(t)
        self.assertEqual([w.kind for w in f.wishes_for(teams["P"]) if w.kind in ("MOVE_UP_DRAFT", "TARGET_PROSPECT")], [])
        self.assertIsNone(draft_night.run_on_the_clock(f, teams["C"], 3, "R1-C"))
        self.assertEqual(owners(t, "R1-C"), "C")
        self.assertEqual(t.trade_analytics_history, [])

    def test_a_team_on_the_clock_with_no_reason_to_move_down_does_not_trade(self):
        t, teams = night_league(ORDER, c_gm=False)   # not a hoarder: no MOVE_DOWN_DRAFT
        f = finder(t)
        self.assertNotIn("MOVE_DOWN_DRAFT", [w.kind for w in f.wishes_for(teams["C"])])
        with mock.patch.object(TradeFinder, "_get_team_positional_needs", return_value=["PG", "SG", "SF", "PF", "C"]):
            self.assertIsNone(draft_night.run_on_the_clock(f, teams["C"], 3, "R1-C"))   # its PG is the top of the board
        self.assertEqual(t.trade_analytics_history, [])

    def test_a_team_whose_pick_is_down_the_board_drops_and_is_recorded_as_moving_down(self):
        t, teams = night_league(ORDER, c_gm=False)   # not a hoarder: no MOVE_DOWN_DRAFT wish of its own
        f = finder(t)
        self.assertNotIn("MOVE_DOWN_DRAFT", [w.kind for w in f.wishes_for(teams["C"])])
        wanted = t.draft_class[1]   # the draft room's own choice for C is the second prospect, not the top one
        with mock.patch("trades.engines.draft_night.best_prospect", return_value=wanted):
            res = draft_night.run_on_the_clock(f, teams["C"], 3, "R1-C")
        self.assertIsNotNone(res)
        self.assertEqual(t.trade_analytics_history[-1]["motives"][0]["wish_kind"], "MOVE_DOWN_DRAFT")

    def test_a_top_pick_does_not_drop_past_a_generational_talent(self):
        t, teams = night_league(ORDER, c_gm=False)
        t.draft_class[0].potenziale = CONFIG.DRAFT_AI.GENERATIONAL_POTENTIAL
        f = finder(t)
        with mock.patch("core.front_office.draft_fit.prospect_score",
                        side_effect=lambda p, *a, **k: 100.0 if p is t.draft_class[1] else 0.0):   # the fit prefers #2
            self.assertEqual(draft_night._slide_limit(f, teams["C"], t.draft_class, 3), (None, None))
            self.assertIsNotNone(draft_night._slide_limit(f, teams["C"], t.draft_class, 30)[1])   # a late pick ignores him

    def test_the_partner_needs_a_later_first(self):
        t, teams = night_league(["F1", "F2", "P", "F3", "F4", "C"], made=2)   # P picks 3rd, C 6th... C is on the clock at 3
        f = finder(t)
        self.assertIsNone(draft_night.run_on_the_clock(f, teams["C"], 3, "R1-C"))

    def test_the_window_is_opened_once(self):
        t, teams = night_league(ORDER)
        f = finder(t)
        with mock.patch.object(TradeFinder, "begin_window", wraps=f.begin_window) as bw:
            draft_night.run_on_the_clock(f, teams["C"], 3, "R1-C")
            draft_night.run_on_the_clock(f, teams["C"], 3, "R1-C")
        self.assertEqual(bw.call_count, 1)


class DraftWiringTests(unittest.TestCase):
    def test_the_draft_calls_the_draft_night_engine(self):
        torneo = SimpleNamespace(pick_ownership={1: {"R1-Nuggets": "Nuggets", "R1-Raptors": "Raptors"}},
                                 offseason_log_data={}, draft_pick_corrente=0)
        d = Draft.__new__(Draft)
        d.torneo, d.squadre = torneo, [SimpleNamespace(nome="Nuggets")]
        d.squadra_giocatore = SimpleNamespace(nome="Raptors")
        d.ordine_originale, d.scelte_totali, d.pick_corrente, d.risultati_draft, d.draft_class = ["Nuggets", "Raptors"], 4, 0, [], []
        result = {"team_on_clock": "Nuggets", "partner": "Kings", "player_involved": "x", "player_ovr": 0,
                  "pick_given": 1, "pick_received": 5, "description": "d"}
        with mock.patch("trades.trade_finder.TradeFinder"), \
                mock.patch("trades.engines.draft_night.run_on_the_clock", return_value=result) as run, \
                mock.patch.object(Draft, "_esegui_scelta_IA"):
            d.simula_singolo_pick()
        run.assert_called_once()
        self.assertEqual(run.call_args.args[2:], (1, "R1-Nuggets"))
        self.assertEqual(d.ultimo_scambio, result)


if __name__ == "__main__":
    unittest.main()
