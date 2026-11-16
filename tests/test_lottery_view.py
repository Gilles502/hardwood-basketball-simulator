"""Lottery night data: odds from the draw's own weights, exact 'still in the hunt' odds after every envelope, real pick
owners (after protections) and the full draft order."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.lottery_view import (annotate_owners, complete_details, full_draft_order, hunt_steps, lottery_preview, lottery_weights,
                               odds_table, pick_owner, pick_protection)


def total(rows, key):
    return sum(r[key] for r in rows)


class OddsTests(unittest.TestCase):
    def test_weights_pad_for_extra_teams(self):
        self.assertEqual(len(lottery_weights(16)), 16)
        self.assertEqual(lottery_weights(16)[-1], 0.1)
        self.assertEqual(lottery_weights(13)[0], 14.0)
        self.assertEqual(len(lottery_weights(13)), 13)

    def test_first_pick_odds_are_weight_shares(self):
        table = odds_table(lottery_weights(14))
        self.assertEqual(table[0]["odds_first"], 14.0)
        self.assertEqual(table[13]["odds_first"], 0.5)
        self.assertAlmostEqual(total(table, "odds_first"), 100.0, delta=0.2)

    def test_top_odds_sum_to_drawn_picks(self):
        for n in (14, 13):
            self.assertAlmostEqual(total(odds_table(lottery_weights(n)), "odds_top"), 400.0, delta=0.5)


class HuntTests(unittest.TestCase):
    def setUp(self):
        self.w = lottery_weights(14)
        self.order = [3, 0, 1, 2] + list(range(4, 14))

    def test_step_zero_equals_pre_draw_odds(self):
        step0 = {e["seed"]: e["odds_first"] for e in hunt_steps(self.w, self.order)[0]}
        for seed, row in enumerate(odds_table(self.w)):
            self.assertAlmostEqual(step0[seed], row["odds_first"], delta=0.06)

    def test_after_tail_revealed_odds_are_conditional(self):
        step10 = {e["seed"]: e["odds_first"] for e in hunt_steps(self.w, self.order)[10]}
        self.assertEqual(set(step10), {0, 1, 2, 3})
        self.assertEqual(step10, {0: 25.2, 1: 25.2, 2: 25.2, 3: 24.3})  # checked against a separate brute force
        self.assertAlmostEqual(sum(step10.values()), 100.0, delta=0.2)
        self.assertGreater(step10[0], step10[3])

    def test_revealed_seeds_leave_the_hunt(self):
        steps = hunt_steps(self.w, self.order)
        self.assertNotIn(13, {e["seed"] for e in steps[1]})  # pick 14 went to seed 13
        self.assertEqual({e["seed"] for e in steps[13]}, {3})  # only the #1 is still sealed
        self.assertAlmostEqual(steps[13][0]["odds_first"], 100.0)

    def test_last_step_is_empty_and_length_follows_team_count(self):
        w13 = lottery_weights(13)
        steps = hunt_steps(w13, [2, 0, 1, 3] + list(range(4, 13)))
        self.assertEqual(len(steps), 14)
        self.assertEqual(steps[-1], [])


def tournament(ownership=None, protections=None, order=(), wins=None):
    teams = [SimpleNamespace(nome=n, vittorie=(wins or {}).get(n, 20), sconfitte=62 - (wins or {}).get(n, 20)) for n in order]
    return SimpleNamespace(pick_ownership={1: dict(ownership or {})}, pick_protections={1: dict(protections or {})},
                           draft_lottery_order=list(order), squadre=teams)


class PayloadTests(unittest.TestCase):
    def test_preview_tells_how_many_picks_are_drawn(self):
        t = tournament(order=("A", "B", "C"))
        t.get_playoff_teams = lambda teams: []
        self.assertEqual(lottery_preview(t)["drawn_picks"], CONFIG.OFFSEASON.LOTTERY_DRAWN_PICKS)

    def test_details_saved_before_owners_existed_are_completed(self):
        t = tournament(ownership={"R1-Memphis": "Detroit"}, order=("Memphis", "Denver"))
        old = {"picks": [{"pick": 1, "team": "Memphis", "projected": 2, "delta": 1},
                         {"pick": 2, "team": "Denver", "projected": 1, "delta": -1}]}
        done = complete_details(old, t)
        self.assertEqual(done["picks"][0]["owner"], "Detroit")
        self.assertEqual(done["picks"][0]["owner_before"], "Detroit")
        self.assertEqual(done["picks"][1]["protection"], "Unprotected")
        self.assertFalse(done["picks"][1]["protection_triggered"])
        self.assertEqual(len(done["hunt_steps"]), 3)
        self.assertEqual(done["drawn_picks"], CONFIG.OFFSEASON.LOTTERY_DRAWN_PICKS)
        self.assertEqual(len(done["full_order"]), 2 * CONFIG.OFFSEASON.DRAFT_ROUNDS)
        self.assertNotIn("owner", old["picks"][0])  # the stored details are not changed

    def test_complete_details_keeps_what_is_there(self):
        t = tournament(order=("Memphis",))
        stored = {"picks": [{"pick": 1, "team": "Memphis", "projected": 1, "delta": 0, "owner": "Utah", "owner_before": "Utah",
                             "protection": "Top 3", "protection_triggered": False}], "hunt_steps": [["kept"]]}
        done = complete_details(stored, t)
        self.assertEqual(done["picks"][0]["owner"], "Utah")
        self.assertEqual(done["hunt_steps"], [["kept"]])


class OwnerTests(unittest.TestCase):
    def test_owner_defaults_to_the_team(self):
        t = tournament(ownership={"R1-Memphis": "Detroit"})
        self.assertEqual(pick_owner(t, 1, "Memphis"), "Detroit")
        self.assertEqual(pick_owner(t, 1, "Denver"), "Denver")
        self.assertEqual(pick_protection(t, "Denver"), "Unprotected")

    def test_protection_triggered_keeps_pick_with_original_team(self):
        t = tournament(ownership={"R1-Memphis": "Memphis"}, protections={"R1-Memphis": "Top 5"})
        picks = [{"pick": 2, "team": "Memphis"}]
        annotate_owners(picks, {"Memphis": "Detroit"}, t)
        self.assertEqual(picks[0]["owner"], "Memphis")
        self.assertEqual(picks[0]["owner_before"], "Detroit")
        self.assertEqual(picks[0]["protection"], "Top 5")
        self.assertTrue(picks[0]["protection_triggered"])

    def test_untouched_pick_is_not_flagged(self):
        t = tournament(ownership={"R1-Memphis": "Detroit"}, protections={"R1-Memphis": "Top 3"})
        picks = [{"pick": 6, "team": "Memphis"}]
        annotate_owners(picks, {"Memphis": "Detroit"}, t)
        self.assertEqual(picks[0]["owner"], "Detroit")
        self.assertFalse(picks[0]["protection_triggered"])

    def test_full_order_uses_current_owner_and_every_round(self):
        t = tournament(ownership={"R2-Bulls": "Raptors"}, order=("Nuggets", "Bulls", "Lakers"), wins={"Nuggets": 17})
        lottery = [{"pick": 1, "team": "Nuggets", "projected": 2, "delta": 1}]
        order = full_draft_order(t, lottery)
        rounds = CONFIG.OFFSEASON.DRAFT_ROUNDS
        self.assertEqual(len(order), 3 * rounds)
        self.assertEqual([p["overall"] for p in order], list(range(1, 3 * rounds + 1)))
        self.assertEqual(order[0]["delta"], 1)
        self.assertEqual(order[0]["record"], "17-45")
        r2_bulls = next(p for p in order if p["round"] == 2 and p["team"] == "Bulls")
        self.assertEqual(r2_bulls["owner"], "Raptors")
        self.assertEqual(r2_bulls["pick"], 2)
        self.assertEqual(r2_bulls["delta"], 0)


if __name__ == '__main__':
    unittest.main()
