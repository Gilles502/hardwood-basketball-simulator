"""AI GM layer 1: team plans with memory, changed only at two checkpoints (core/front_office/plans.py)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office.plans import (TeamPlan, checkpoint_deadline, checkpoint_new_season, suggest_plan)
from core.front_office.state import FrontOfficeState, build_front_office

FO = CONFIG.FRONT_OFFICE


def player(ovr, age=27):
    return SimpleNamespace(ovr=ovr, eta=age, nome="P")


def make_torneo(statuses, user_team=None, season=3):
    """`statuses`: team name -> what Tournament._determina_stato_squadra answers for it."""
    squadre = [SimpleNamespace(nome=name, roster=[player(75)] * 8, vittorie=0, sconfitte=0)
               for name in statuses]
    torneo = SimpleNamespace(
        squadre=squadre, season_number=season, starting_year=2002, anno_corrente=2002 + season - 1,
        user_role="spectator" if user_team is None else "gm_coach",
        squadra_giocatore=next((s for s in squadre if s.nome == user_team), None),
    )
    torneo._determina_stato_squadra = lambda s: statuses[s.nome]
    torneo.front_office = build_front_office(torneo)
    return torneo


def team(torneo, name):
    return next(s for s in torneo.squadre if s.nome == name)


def set_plan(torneo, name, state, held):
    torneo.front_office.plans[name] = TeamPlan(state=state, since_year=2000, seasons_held=held,
                                               reason="test", history=[])


class SuggestTests(unittest.TestCase):
    def test_suggest_maps_roster_state(self):
        t = make_torneo({"A": "Contender", "B": "Aging Core", "C": "Rebuilding", "D": "Mediocre",
                         "E": "Defending Champion"})
        self.assertEqual(suggest_plan(team(t, "A"), t)[0], "CONTENDER")
        self.assertEqual(suggest_plan(team(t, "B"), t)[0], "PLAYOFF")
        self.assertEqual(suggest_plan(team(t, "C"), t)[0], "REBUILDER")
        self.assertEqual(suggest_plan(team(t, "D"), t)[0], "MIDDLE")
        self.assertEqual(suggest_plan(team(t, "E"), t)[0], "CONTENDER")
        for name in "ABCDE":
            self.assertTrue(suggest_plan(team(t, name), t)[1])

    def test_rising_star_depends_on_rating(self):
        t = make_torneo({"Young": "Rising Star", "Other": "Mediocre"})
        team(t, "Young").roster = [player(74, 23)] * 8   # league top-8 average 74.5: within 1
        team(t, "Other").roster = [player(75)] * 8
        self.assertEqual(suggest_plan(team(t, "Young"), t)[0], "PLAYOFF")
        team(t, "Young").roster = [player(70, 23)] * 8   # average 72.5: 2.5 below
        self.assertEqual(suggest_plan(team(t, "Young"), t)[0], "REBUILDER")

    def test_plans_exist_from_the_start(self):
        t = make_torneo({"A": "Contender", "B": "Rebuilding"})
        self.assertEqual(t.front_office.plans["A"].state, "CONTENDER")
        self.assertEqual(t.front_office.plans["B"].state, "REBUILDER")
        self.assertEqual(t.front_office.plans["A"].seasons_held, 1)

    def test_plans_survive_save_round_trip(self):
        t = make_torneo({"A": "Contender"})
        again = FrontOfficeState.from_dict(t.front_office.to_dict())
        self.assertIsInstance(again.plans["A"], TeamPlan)
        self.assertEqual(again.to_dict(), t.front_office.to_dict())


class NewSeasonTests(unittest.TestCase):
    def test_plan_holds_for_min_seasons(self):
        statuses = {"A": "Playoff Team"}
        t = make_torneo(statuses)
        t.front_office.seated_gm("A").traits = []   # no win-now lean holding the plan on a MIDDLE roster
        self.assertEqual(t.front_office.plans["A"].state, "PLAYOFF")
        statuses["A"] = "Mediocre"
        checkpoint_new_season(t)
        self.assertEqual(t.front_office.plans["A"].state, "PLAYOFF")
        self.assertEqual(t.front_office.plans["A"].seasons_held, 2)
        checkpoint_new_season(t)
        plan = t.front_office.plans["A"]
        self.assertEqual(plan.state, "MIDDLE")
        self.assertEqual(plan.seasons_held, 1)
        self.assertEqual(plan.history[-1]["from"], "PLAYOFF")
        self.assertEqual(plan.history[-1]["to"], "MIDDLE")
        self.assertEqual(plan.history[-1]["checkpoint"], "new_season")
        self.assertTrue(plan.history[-1]["reason"])

    def test_extreme_jump_changes_at_once(self):
        statuses = {"A": "Contender"}
        t = make_torneo(statuses)
        statuses["A"] = "Rebuilding"
        checkpoint_new_season(t)
        self.assertEqual(t.front_office.plans["A"].state, "REBUILDER")

    def test_user_summit_goal_wins(self):
        statuses = {"Mine": "Rebuilding", "B": "Mediocre"}
        t = make_torneo(statuses, user_team="Mine")
        team(t, "Mine").front_office_summit = {"completed": True, "agreed_goal": "CHAMPIONSHIP"}
        checkpoint_new_season(t)
        self.assertEqual(t.front_office.plans["Mine"].state, "CONTENDER")
        self.assertIn("summit", t.front_office.plans["Mine"].reason.lower())

    def test_gms_age_each_season(self):
        t = make_torneo({"A": "Mediocre", "B": "Mediocre"})
        fo = t.front_office
        before = {gid: (gm.age, gm.tenure, gm.years_as_gm, gm.team) for gid, gm in fo.gms.items()}
        checkpoint_new_season(t)
        for gid, (age, tenure, years, seat) in before.items():
            gm = fo.gms[gid]
            self.assertEqual(gm.age, age + 1)
            if seat is not None:
                self.assertEqual(gm.tenure, tenure + 1)
                self.assertEqual(gm.years_as_gm, years + 1)
            else:
                self.assertEqual(gm.tenure, tenure)
                self.assertEqual(gm.years_as_gm, years)


class DeadlineTests(unittest.TestCase):
    def record(self, t, name, wins, losses):
        team(t, name).vittorie, team(t, name).sconfitte = wins, losses

    def test_deadline_needs_min_games(self):
        t = make_torneo({"A": "Contender", "B": "Contender"})
        self.record(t, "A", 4, 35)   # 39 games at 0.10
        self.record(t, "B", 0, 0)
        checkpoint_deadline(t)
        self.assertEqual(t.front_office.plans["A"].state, "CONTENDER")
        self.assertEqual(t.front_office.plans["B"].state, "CONTENDER")

    def test_deadline_collapse_and_surprise(self):
        t = make_torneo({"A": "Contender", "B": "Rebuilding"})
        self.record(t, "A", 11, 34)  # 45 games at 0.244
        self.record(t, "B", 32, 13)  # 45 games at 0.711
        checkpoint_deadline(t)
        a, b = t.front_office.plans["A"], t.front_office.plans["B"]
        self.assertEqual(a.state, "REBUILDER")
        self.assertEqual(a.reason, "Season collapsed (11-34) at the deadline")
        self.assertEqual(a.history[-1]["checkpoint"], "deadline")
        self.assertEqual(b.state, "PLAYOFF")
        self.assertEqual(b.reason, "Surprise season (32-13): buying at the deadline")


if __name__ == "__main__":
    unittest.main()
