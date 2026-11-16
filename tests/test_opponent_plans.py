"""Per-team defensive plans: matchups and double-teams apply only against the team they were set for."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import Squadra, TacticalPlan
from core.save_manager import deserialize_tactical_plan, serialize_tactical_plan

POSITIONS = ["PG", "SG", "SF", "PF", "C"]


def team(name, players, on_floor=None):
    """A Squadra-like object: players by position, all on the floor unless on_floor says otherwise."""
    on_floor = players if on_floor is None else on_floor
    t = SimpleNamespace(nome=name, roster=list(players), posizione_in_campo=dict(zip(POSITIONS, players)))
    t.giocatori_in_campo = lambda: list(on_floor)
    for p in players:
        p.squadra = t
    return t


def player(name, role):
    # Low touch tendency keeps the engine's automatic star shadowing out of these tests.
    return SimpleNamespace(nome=name, ruolo=role, tendenze=SimpleNamespace(touch_tendency=50))


def my_team(plan):
    mine = [player(n, r) for n, r in zip(["Ruiz", "Vale", "Banks", "Ferro", "Pratt"], POSITIONS)]
    t = team("Toronto", mine)
    t.tactical_plan = plan
    return t


def their_team(name="Bay", on_floor_names=None):
    theirs = [player(n, r) for n, r in zip(["Mallory", "Okafor", "Hale", "Brandt", "Okoye"], POSITIONS)]
    on_floor = None if on_floor_names is None else [p for p in theirs if p.nome in on_floor_names]
    return team(name, theirs, on_floor), {p.nome: p for p in theirs}


def defender_of(defense, attacker):
    return Squadra.scegli_difensore(defense, attacker).nome


class PlanVsTests(unittest.TestCase):
    def test_plan_vs_empty_for_unknown_team(self):
        self.assertEqual(TacticalPlan().plan_vs("X"), {"matchups": {}, "double_teams": []})


class DefenderChoiceTests(unittest.TestCase):
    def plan(self):
        return TacticalPlan(opponent_plans={"Bay": {"matchups": {"Hale": "Vale"}, "double_teams": []}})

    def test_direct_assignment_only_vs_that_team(self):
        mine = my_team(self.plan())
        _, bay = their_team("Bay")
        _, other = their_team("Other")
        self.assertEqual(defender_of(mine, bay["Hale"]), "Vale")
        self.assertEqual(defender_of(mine, other["Hale"]), "Banks")

    def test_freed_defender_takes_the_moved_defenders_man(self):
        mine = my_team(self.plan())
        _, bay = their_team("Bay")
        self.assertEqual(defender_of(mine, bay["Okafor"]), "Banks")

    def test_swap_only_when_target_on_floor(self):
        mine = my_team(self.plan())
        _, bay = their_team("Bay", on_floor_names=["Mallory", "Okafor", "Brandt", "Okoye"])
        self.assertEqual(defender_of(mine, bay["Okafor"]), "Vale")

    def test_unknown_names_are_ignored(self):
        mine = my_team(TacticalPlan(opponent_plans={"Bay": {"matchups": {"Ghost": "Nobody"}, "double_teams": []}}))
        _, bay = their_team("Bay")
        self.assertEqual(defender_of(mine, bay["Hale"]), "Banks")


class SaveRoundTripTests(unittest.TestCase):
    def test_round_trip_and_old_saves(self):
        tp = TacticalPlan(opponent_plans={"Bay": {"matchups": {"Hale": "Vale"}, "double_teams": ["Okoye"]}})
        self.assertEqual(deserialize_tactical_plan(serialize_tactical_plan(tp)).opponent_plans, tp.opponent_plans)
        self.assertEqual(deserialize_tactical_plan({"defensive_scheme": "PRESS_FULL_COURT"}).opponent_plans, {})


if __name__ == "__main__":
    unittest.main()
