"""AI GM layer 1: league front-office state, seats, save/load (core/front_office/state.py)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office.models import CpuGM
from core.front_office.seasons import ensure_season_marks
from core.front_office.state import (FrontOfficeState, build_front_office, ensure_front_office,
                                     fill_careers, user_moves_team)
from core.league.registry import FranchiseRegistry
from core.league.schema import load_league
from core.save_manager import restore_tournament_state, serialize_tournament_state

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


FICTIONAL_LEAGUE = os.path.join(ROOT, "data", "leagues", "fictional_2002", "league.json")
_REGISTRY = []


def fictional_registry():
    """The built-in fictional 2002 league (teams, GMs by franchise id), loaded once."""
    if not _REGISTRY:
        _REGISTRY.append(FranchiseRegistry.from_league(load_league(FICTIONAL_LEAGUE)))
    return _REGISTRY[0]


def team_names_2002():
    return sorted(fictional_registry().names())


def fake_torneo(user_team="Toronto Northmen", role="gm_coach", season=1, starting_year=2002):
    squadre = [SimpleNamespace(nome=name, roster=[]) for name in team_names_2002()]
    user = next((s for s in squadre if s.nome == user_team), None) if role != "spectator" else None
    torneo = SimpleNamespace(
        squadre=squadre, squadra_giocatore=user, user_role=role, is_spectator=user is None,
        season_number=season, starting_year=starting_year, anno_corrente=starting_year + season - 1,
        league_settings={"user_role": role}, franchise_registry=fictional_registry(),
    )
    torneo._determina_stato_squadra = lambda s: "Rebuilding"  # every GM comes with a team plan
    return torneo


def seated_ids(fo):
    return list(fo.seats.values())


class SeatTests(unittest.TestCase):
    def test_new_league_seats_all_but_user(self):
        fo = build_front_office(fake_torneo())
        self.assertEqual(len(fo.seats), 29)
        self.assertNotIn("Toronto Northmen", fo.seats)
        for team, gm_id in fo.seats.items():
            self.assertEqual(fo.gms[gm_id].team, team)
        spec = build_front_office(fake_torneo(role="spectator"))
        self.assertEqual(len(spec.seats), 30)
        # Coach-only user: a CPU GM runs the user's team (the trade AI already does).
        coach_only = build_front_office(fake_torneo(role="only_coach"))
        self.assertEqual(len(coach_only.seats), 30)
        self.assertEqual(coach_only.gms[coach_only.seats["Toronto Northmen"]].gm_id, "glen_greenwood")
        # The historical GMs of 2002 sit at their own teams.
        self.assertEqual(spec.gms[spec.seats["LA Breakers"]].gm_id, "elton_taylor")

    def test_round_trip(self):
        fo = build_front_office(fake_torneo(season=5))
        again = FrontOfficeState.from_dict(fo.to_dict())
        self.assertEqual(again.to_dict(), fo.to_dict())

    def test_ensure_builds_once(self):
        t = fake_torneo()
        fo = ensure_front_office(t)
        self.assertIs(ensure_front_office(t), fo)


class SaveTests(unittest.TestCase):
    def state_dict(self, season):
        return {"season_number": season, "starting_year": 2002, "anno_corrente": 2002 + season - 1,
                "player_team_name": "Toronto Northmen", "is_spectator": False,
                "league_settings": {"user_role": "gm_coach"}}

    def test_old_save_builds_same_gms_twice(self):
        outs = []
        for _ in range(2):
            t = fake_torneo(season=1)
            t.front_office = build_front_office(fake_torneo(role="spectator"))  # what setup_simulation leaves behind
            restore_tournament_state(t, self.state_dict(9))
            outs.append(t.front_office.to_dict())
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(len(outs[0]["seats"]), 29)
        self.assertNotIn("Toronto Northmen", outs[0]["seats"])

    def test_saved_state_is_restored(self):
        t = fake_torneo(season=3)
        t.front_office = build_front_office(t)
        t.front_office.gms[t.front_office.seats["Boston Minutemen"]].name = "Edited Name"
        ensure_season_marks(t, t.front_office)  # a save made by today's game has this season's marks
        saved = serialize_tournament_state(t)
        self.assertIn("front_office", saved)
        fresh = fake_torneo(season=1)
        restore_tournament_state(fresh, saved)
        self.assertEqual(fresh.front_office.to_dict(), t.front_office.to_dict())

    def test_deep_save_replaces_retired_originals(self):
        fo = build_front_office(fake_torneo(season=17))
        seated = [fo.gms[g] for g in seated_ids(fo)]
        self.assertTrue(all(gm.age < CONFIG.FRONT_OFFICE.RETIREMENT_AGE for gm in seated))
        arrivals = [gm for gm in seated if gm.available_from_year is not None and gm.historical]
        self.assertTrue(arrivals)
        self.assertTrue(all(gm.available_from_year <= 2018 for gm in arrivals))
        # Arrivals were never in office before: no made-up years as GM.
        self.assertTrue(all(gm.years_as_gm == 0 for gm in arrivals))
        self.assertEqual(len(seated_ids(fo)), len(set(seated_ids(fo))))


class UserMoveTests(unittest.TestCase):
    def test_user_moves_team(self):
        t = fake_torneo()
        t.front_office = build_front_office(t)
        boston_gm = t.front_office.seats["Boston Minutemen"]
        user_moves_team(t, "Toronto Northmen", "Boston Minutemen")
        fo = t.front_office
        self.assertNotIn("Boston Minutemen", fo.seats)
        self.assertIsNone(fo.gms[boston_gm].team)
        self.assertIn("Toronto Northmen", fo.seats)
        self.assertFalse(fo.gms[fo.seats["Toronto Northmen"]].historical)
        self.assertEqual(len(seated_ids(fo)), len(set(seated_ids(fo))))
        # Back and forth in the same year: still one GM per seat, no duplicate ids.
        user_moves_team(t, "Boston Minutemen", "Toronto Northmen")
        user_moves_team(t, "Toronto Northmen", "Boston Minutemen")
        self.assertEqual(len(seated_ids(fo)), len(set(seated_ids(fo))))
        self.assertEqual(len(fo.seats), 29)
        for team, gm_id in fo.seats.items():
            self.assertEqual(fo.gms[gm_id].team, team)


class CareerStateTests(unittest.TestCase):
    def test_gm_career_round_trip(self):
        gm = CpuGM(gm_id="x", name="X Y", age=50, years_as_gm=3, traits=[], skills={"trading": 50}, team="A",
                   career=[{"team": "A", "from_year": 2005, "to_year": None, "end": None, "wins": 10, "losses": 5,
                            "playoffs": 1, "titles": 0}],
                   interim=True, retired_year=2010,
                   hiring_notes=[{"year": 2009, "kind": "turned_down", "team": "B", "names": ["Z"]}])
        again = CpuGM.from_dict(gm.to_dict())
        self.assertEqual(again.career, gm.career)
        self.assertTrue(again.interim)
        self.assertEqual(again.retired_year, 2010)
        self.assertEqual(again.hiring_notes, gm.hiring_notes)

    def test_old_gm_dict_defaults(self):
        gm = CpuGM.from_dict({"gm_id": "x", "name": "X Y", "age": 50, "years_as_gm": 3, "traits": [],
                              "skills": {}, "team": "A", "tenure": 2})
        self.assertEqual(gm.career, [])
        self.assertIs(gm.interim, False)
        self.assertIsNone(gm.retired_year)
        self.assertEqual(gm.hiring_notes, [])

    def test_state_records_round_trip(self):
        fo = FrontOfficeState()
        fo.records = {"A": [{"year": 2002, "wins": 50, "losses": 32, "expected": 45, "playoffs": True,
                             "champion": False, "plan": "Contending", "gm_id": "x", "coach_fired": False}]}
        fo.season_marks = {"A": {"year": 2003, "expected": 44, "last_wins": 50, "top8": ["P1", "P2"]}}
        again = FrontOfficeState.from_dict(fo.to_dict())
        self.assertEqual(again.records, fo.records)
        self.assertEqual(again.season_marks, fo.season_marks)
        old = FrontOfficeState.from_dict({"version": 1, "gms": {}, "seats": {}})
        self.assertEqual(old.records, {})
        self.assertEqual(old.season_marks, {})
        self.assertEqual(FrontOfficeState().version, 2)

    def test_fill_careers_opens_current_job(self):
        fo = FrontOfficeState()
        gm = CpuGM(gm_id="x", name="X Y", age=50, years_as_gm=3, traits=[], skills={}, team="A", tenure=3)
        fo.gms["x"] = gm
        fo.seats["A"] = "x"
        fill_careers(fo, 2008)
        self.assertEqual(len(gm.career), 1)
        self.assertEqual(gm.career[0]["from_year"], 2005)
        self.assertIsNone(gm.career[0]["to_year"])
        self.assertIsNone(gm.career[0]["end"])
        self.assertEqual(gm.tenure, 3)
        fill_careers(fo, 2008)
        self.assertEqual(len(gm.career), 1)

    def test_user_takeover_closes_career_and_seats_interim(self):
        t = fake_torneo()
        t.front_office = build_front_office(t)
        fo = t.front_office
        new_gm = fo.gms[fo.seats["Boston Minutemen"]]
        user_moves_team(t, "Toronto Northmen", "Boston Minutemen")
        self.assertEqual(new_gm.career[-1]["end"], "user_took_over")
        self.assertEqual(new_gm.career[-1]["to_year"], t.anno_corrente)
        self.assertIsNone(new_gm.team)
        old_gm = fo.gms[fo.seats["Toronto Northmen"]]
        self.assertTrue(old_gm.interim)
        self.assertEqual(old_gm.career[-1]["team"], "Toronto Northmen")
        self.assertIsNone(old_gm.career[-1]["to_year"])


if __name__ == "__main__":
    unittest.main()
