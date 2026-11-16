"""Draft fit: the CPU draft pick reads the roster (a hole is filled, a star or a young talent at the role blocks)."""
import unittest

from core.config import CONFIG
from core.front_office.draft_fit import (best_prospect, estimated_potential, move_up_slot, potential_weight,
                                        prospect_score, role_state)
from tests.trade_fixtures import make_gm
from core.front_office.era_lines import EraLines
from tests.trade_fixtures import make_player

ERA = EraLines(year=2003, cap=40.0, tax=49.0, minimum=0.5, mle=5.0, no_cap=False, star=85, core=80, starter=75,
               rotation=70, bench=65, salary_pcts={}, pick_scale=1.0)


def roster(*specs):
    return [make_player(f"P{i}", ovr=o, age=a, role=r, pot=pot) for i, (r, o, a, pot) in enumerate(specs)]


class RoleStateTests(unittest.TestCase):
    def test_no_starter_at_the_role_is_a_hole(self):
        self.assertEqual(role_state(roster(("C", 70, 28, 70)), "C", ERA), "hole")
        self.assertEqual(role_state([], "PG", ERA), "hole")

    def test_a_core_player_in_his_prime_blocks_the_role(self):
        self.assertEqual(role_state(roster(("PF", 84, 27, 84), ("PF", 72, 25, 72)), "PF", ERA), "blocked")

    def test_an_old_core_player_does_not_block(self):
        d = CONFIG.DRAFT_AI
        self.assertNotEqual(role_state(roster(("PF", 84, d.BLOCK_MAX_AGE + 1, 84), ("PF", 72, 25, 72)), "PF", ERA), "blocked")

    def test_a_young_talent_blocks_the_role(self):
        self.assertEqual(role_state(roster(("SG", 77, 22, 86), ("SG", 72, 28, 72)), "SG", ERA), "blocked")

    def test_one_starter_and_nobody_behind_him_is_depth_wanted(self):
        self.assertEqual(role_state(roster(("SF", 77, 28, 77)), "SF", ERA), "depth")

    def test_a_settled_role_is_ok(self):
        self.assertEqual(role_state(roster(("SF", 77, 28, 77), ("SF", 72, 28, 72)), "SF", ERA), "ok")


class BestProspectTests(unittest.TestCase):
    def test_a_hole_beats_a_slightly_better_prospect_at_a_blocked_role(self):
        team = roster(("PG", 86, 27, 86), ("PG", 72, 26, 72), ("C", 70, 28, 70))
        pg = make_player("PG-pro", ovr=62, pot=84, age=19, role="PG")
        c = make_player("C-pro", ovr=60, pot=80, age=19, role="C")
        self.assertIs(best_prospect([pg, c], team, ERA), c)   # the PG is the better prospect, but a star plays there

    def test_a_much_better_prospect_still_goes_to_a_blocked_role(self):
        team = roster(("PG", 86, 27, 86), ("PG", 72, 26, 72), ("C", 70, 28, 70))
        pg = make_player("PG-pro", ovr=70, pot=95, age=19, role="PG")
        c = make_player("C-pro", ovr=55, pot=76, age=19, role="C")
        self.assertIs(best_prospect([pg, c], team, ERA), pg)

    def test_a_rebuilder_cares_less_about_the_roster(self):
        team = roster(("PG", 86, 27, 86), ("PG", 72, 26, 72), ("C", 70, 28, 70))
        pg = make_player("PG-pro", ovr=62, pot=86, age=19, role="PG")
        c = make_player("C-pro", ovr=60, pot=78, age=19, role="C")
        self.assertIs(best_prospect([pg, c], team, ERA, "MIDDLE"), c)        # the star at PG weighs fully
        self.assertIs(best_prospect([pg, c], team, ERA, "REBUILDER"), pg)    # a rebuilder takes the better prospect

    def test_a_generational_talent_goes_to_a_top_pick_whatever_the_roster(self):
        team = roster(("PG", 86, 27, 86), ("C", 70, 28, 70))
        gen = make_player("Gen", ovr=75, pot=CONFIG.DRAFT_AI.GENERATIONAL_POTENTIAL, age=19, role="PG")
        c = make_player("C-pro", ovr=60, pot=80, age=19, role="C")
        self.assertIs(best_prospect([gen, c], team, ERA, pick_in_round=2), gen)

    def test_an_empty_board_is_none(self):
        self.assertIsNone(best_prospect([], [], ERA))



def gm_with(draft, traits=()):
    g = make_gm("gm-x", traits=list(traits))
    g.skills = {"trade": 60, "contracts": 60, "draft": draft}
    return g


class EstimateTests(unittest.TestCase):
    def test_no_gm_sees_the_true_potential(self):
        self.assertEqual(estimated_potential(make_player("P", pot=80)), 80.0)

    def test_a_perfect_scout_sees_it_too(self):
        self.assertEqual(estimated_potential(make_player("P", pot=80), gm_with(100), 2003), 80.0)

    def test_the_error_is_stable_and_shrinks_with_skill(self):
        players = [make_player(f"P{i}", pot=80) for i in range(200)]
        weak = [abs(estimated_potential(p, gm_with(20), 2003) - 80) for p in players]
        good = [abs(estimated_potential(p, gm_with(85), 2003) - 80) for p in players]
        self.assertGreater(sum(weak), 2 * sum(good))
        self.assertEqual(estimated_potential(players[0], gm_with(20), 2003), estimated_potential(players[0], gm_with(20), 2003))
        cap = 2 * CONFIG.DRAFT_AI.ESTIMATE_ERROR_MAX * 0.8
        self.assertLessEqual(max(weak), cap + 1e-9)


class PlanAndTraitTests(unittest.TestCase):
    def test_rebuilders_want_upside_contenders_readiness(self):
        self.assertGreater(potential_weight("REBUILDER"), potential_weight("MIDDLE"))
        self.assertLess(potential_weight("CONTENDER"), potential_weight("MIDDLE"))

    def test_youth_first_leans_to_upside(self):
        self.assertGreater(potential_weight("MIDDLE", gm_with(60, ["YOUTH_FIRST"])), potential_weight("MIDDLE", gm_with(60)))

    def test_a_contender_takes_the_ready_player(self):
        team = roster(("C", 70, 28, 70), ("PF", 70, 28, 70))
        ready = make_player("Ready", ovr=74, pot=78, age=22, role="C")
        raw = make_player("Raw", ovr=58, pot=83, age=19, role="PF")
        self.assertIs(best_prospect([raw, ready], team, ERA, "CONTENDER"), ready)
        self.assertIs(best_prospect([raw, ready], team, ERA, "REBUILDER"), raw)


class MoveUpTests(unittest.TestCase):
    def board(self):
        return ([make_player("Top", ovr=65, pot=90, age=19, role="C")]
                + [make_player(f"Mid{i}", ovr=60, pot=78, age=19, role="SF") for i in range(9)])

    def test_it_wants_the_slot_of_a_clearly_better_prospect_going_before_its_pick(self):
        self.assertEqual(move_up_slot(self.board(), 0, 6, roster(("C", 70, 28, 70)), ERA, "REBUILDER"), 1)

    def test_no_slot_when_its_man_is_still_there_at_its_pick(self):
        self.assertIsNone(move_up_slot(self.board(), 0, 1, roster(("C", 70, 28, 70)), ERA, "REBUILDER"))

    def test_no_slot_when_the_gain_is_small(self):
        flat = [make_player(f"P{i}", ovr=60, pot=80 - (i % 2), age=19, role="SF") for i in range(10)]
        self.assertIsNone(move_up_slot(flat, 0, 6, roster(("SF", 70, 28, 70)), ERA, "REBUILDER"))



class ProspectPickValueTests(unittest.TestCase):
    def league(self, made=0):
        from types import SimpleNamespace
        from trades.trade_finder import TradeFinder
        lebron = make_player("Lebron", ovr=80, pot=99, age=18, role="SF")
        wade = make_player("Wade", ovr=78, pot=95, age=21, role="SG")
        filler = make_player("Filler", ovr=60, pot=70, age=20, role="C")
        t = SimpleNamespace(draft_lottery_order=["A", "B", "C"], draft_class=[filler, wade, lebron],
                            draft_pick_corrente=made, fase_torneo="OFFSEASON")
        f = TradeFinder.__new__(TradeFinder)
        f.torneo = t
        return f, lebron, wade, filler

    def test_a_first_of_this_draft_is_worth_the_prospect_projected_there(self):
        f, lebron, wade, filler = self.league()
        self.assertAlmostEqual(f._prospect_pick_value("R1-A"), max(CONFIG.TRADES.PICK_R2_BASE_VALUE, lebron.trade_value))
        self.assertAlmostEqual(f._prospect_pick_value("R1-B"), max(CONFIG.TRADES.PICK_R2_BASE_VALUE, wade.trade_value))
        self.assertGreater(f._prospect_pick_value("R1-A"), f._prospect_pick_value("R1-B"))

    def test_picks_already_made_move_the_board(self):
        f, lebron, wade, filler = self.league(made=1)
        f.torneo.draft_class = [filler, wade]   # LeBron went first
        self.assertAlmostEqual(f._prospect_pick_value("R1-B"), max(CONFIG.TRADES.PICK_R2_BASE_VALUE, wade.trade_value))
        self.assertIsNone(f._prospect_pick_value("R1-A"))   # that slot is gone

    def test_during_the_season_the_old_order_is_not_read(self):
        f, *_ = self.league()
        f.torneo.fase_torneo = "SEASON"
        self.assertIsNone(f._prospect_pick_value("R1-A"))

    def test_unknown_slot_or_a_second_falls_back(self):
        f, *_ = self.league()
        self.assertIsNone(f._prospect_pick_value("R1-Z"))
        self.assertIsNone(f._prospect_pick_value("R2-A"))


if __name__ == "__main__":
    unittest.main()
