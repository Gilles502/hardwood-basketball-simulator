"""AI GM layer 3: the GM market, the offseason hiring round and the new GM's plan (core/front_office/hiring.py)."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office import hiring
from core.front_office.hiring import (add_market_newcomers, available_candidates, reputation, run_hiring_round,
                                      team_appeal)
from core.front_office.models import CpuGM, TeamPlan
from core.front_office.offseason import front_office_offseason
from core.front_office.plans import new_gm_plan
from core.front_office.state import FrontOfficeState, _seat_generated, start_job

FO = CONFIG.FRONT_OFFICE
YEAR = 2006


class Stub:
    """Stub rng: no noise, random() a fixed number."""
    def __init__(self, value=0.99):
        self.value = value

    def random(self):
        return self.value

    def uniform(self, a, b):
        return 0.0


def player(ovr, age=27):
    return SimpleNamespace(ovr=ovr, eta=age, nome="P")


def make_league(teams, user_role="spectator", user_team=None):
    """`teams`: name -> (roster status, wins, top-8 OVR, owner type)."""
    squadre = [SimpleNamespace(nome=name, roster=[player(ovr)] * 8, vittorie=wins, sconfitte=82 - wins,
                               personalita_proprietario=owner)
               for name, (_, wins, ovr, owner) in teams.items()]
    torneo = SimpleNamespace(squadre=squadre, season_number=5, starting_year=2002, anno_corrente=YEAR,
                             user_role=user_role, campione=None,
                             squadra_giocatore=next((s for s in squadre if s.nome == user_team), None),
                             offseason_log_data={"ritiri_sviluppo": []})
    torneo._determina_stato_squadra = lambda s: teams[s.nome][0]
    fo = FrontOfficeState()
    for name in teams:
        fo.plans[name] = TeamPlan(state="MIDDLE", since_year=2004, seasons_held=2, reason="t", history=[])
    torneo.front_office = fo
    return torneo, fo


def team(torneo, name):
    return next(s for s in torneo.squadre if s.nome == name)


def make_gm(gm_id, skill=60, age=45, years=0, traits=(), **kw):
    kw.setdefault("available_from_year", 2002)
    return CpuGM(gm_id=gm_id, name=f"GM {gm_id}", age=age, years_as_gm=years, traits=list(traits),
                 skills={"trade": skill, "contracts": skill, "draft": skill}, **kw)


def add(fo, *gms):
    for gm in gms:
        fo.gms[gm.gm_id] = gm


def notes(gm, kind):
    return [n for n in gm.hiring_notes if n["kind"] == kind]


class MarketTests(unittest.TestCase):
    def test_newcomers_added_once_per_year(self):
        fo = FrontOfficeState()
        add_market_newcomers(fo, YEAR)
        add_market_newcomers(fo, YEAR)
        self.assertEqual(len(fo.gms), FO.MARKET_NEWCOMERS_PER_YEAR)
        for gm in fo.gms.values():
            self.assertTrue(FO.MARKET_NEWCOMER_AGE[0] <= gm.age <= FO.MARKET_NEWCOMER_AGE[1])
            for value in gm.skills.values():
                self.assertTrue(FO.MARKET_NEWCOMER_SKILLS[0] <= value <= FO.MARKET_NEWCOMER_SKILLS[1])
            self.assertEqual(gm.available_from_year, YEAR)
        add_market_newcomers(fo, YEAR + 1)
        self.assertEqual(len(fo.gms), 2 * FO.MARKET_NEWCOMERS_PER_YEAR)

    def test_historical_arrival_hired_only_from_year(self):
        fo = FrontOfficeState()
        add(fo, make_gm("arr", historical=True, available_from_year=2007))
        self.assertNotIn("arr", [g.gm_id for g in available_candidates(fo, 2005)])
        self.assertIn("arr", [g.gm_id for g in available_candidates(fo, 2007)])

    def test_seated_and_retired_not_candidates(self):
        fo = FrontOfficeState()
        seated, retired, free = make_gm("s"), make_gm("r", retired_year=2005), make_gm("f")
        add(fo, seated, retired, free)
        start_job(seated, "A", 2004)
        fo.seats["A"] = "s"
        self.assertEqual([g.gm_id for g in available_candidates(fo, YEAR)], ["f"])

    def test_reputation_counts_record(self):
        plain = make_gm("p", skill=60)
        self.assertEqual(reputation(plain), 60)
        veteran = make_gm("v", skill=60, years=30)
        veteran.career = [{"team": "A", "playoffs": 4, "titles": 1}]
        expected = 60 + FO.REP_PER_YEAR * FO.REP_YEARS_CAP + 4 * FO.REP_PER_PLAYOFF + FO.REP_PER_TITLE
        self.assertAlmostEqual(reputation(veteran), expected)

    def test_team_appeal_reads_wins_talent_and_owner(self):
        torneo, _ = make_league({"Good": ("Contender", 60, 80, "Spendaccione"),
                                 "Bad": ("Rebuilding", 20, 70, "Risparmiatore")})
        good, bad = team_appeal(torneo, team(torneo, "Good")), team_appeal(torneo, team(torneo, "Bad"))
        self.assertAlmostEqual(good, 50 + 19 + 5 * 3.0 + 5)
        self.assertAlmostEqual(bad, 50 - 21 - 5 * 3.0 - 5)


class HiringRoundTests(unittest.TestCase):
    def test_every_vacancy_filled_no_double_seat(self):
        names = ["A", "B", "C", "D", "E"]
        torneo, fo = make_league({n: ("Mediocre", 41, 75, "Bilanciato") for n in names})
        add(fo, make_gm("x"), make_gm("y"))
        hires = run_hiring_round(torneo, fo, names, Stub())
        self.assertEqual(sorted(hires), names)
        self.assertEqual(len(set(hires.values())), 5)
        self.assertEqual(sum(1 for gm_id in hires.values() if gm_id.startswith("gen_")), 3)
        for name, gm_id in hires.items():
            self.assertEqual(fo.seats[name], gm_id)
            gm = fo.gms[gm_id]
            self.assertEqual((gm.team, gm.interim), (name, False))
            self.assertEqual(gm.career[-1]["from_year"], YEAR)

    def test_failed_contender_prefers_win_now(self):
        torneo, fo = make_league({"A": ("Contender", 45, 80, "Bilanciato"), "B": ("Mediocre", 41, 75, "Bilanciato")})
        add(fo, make_gm("builder", traits=["PICK_HOARDER"]), make_gm("star", traits=["STAR_CHASER"]))
        self.assertEqual(run_hiring_round(torneo, fo, ["A"], Stub()), {"A": "star"})

    def test_ricostruttore_takes_young_gm(self):
        for owner, winner in (("Ricostruttore", "young"), ("Esigente", "veteran")):
            torneo, fo = make_league({"A": ("Mediocre", 41, 75, owner)})
            add(fo, make_gm("veteran", skill=60, age=50, years=5), make_gm("young", skill=59, age=32))
            self.assertEqual(run_hiring_round(torneo, fo, ["A"], Stub()), {"A": winner}, owner)

    def test_wanted_gm_turns_down_bad_team(self):
        torneo, fo = make_league({"Strong": ("Contender", 60, 80, "Bilanciato"),
                                  "Hopeless": ("Rebuilding", 15, 70, "Bilanciato")})
        star = make_gm("star", skill=85, years=10)
        add(fo, star, make_gm("other", skill=50))
        self.assertGreaterEqual(reputation(star), FO.HIRING_WANTED_REP)
        hires = run_hiring_round(torneo, fo, ["Hopeless", "Strong"], Stub())
        self.assertEqual(hires, {"Strong": "star", "Hopeless": "other"})
        self.assertEqual([n["team"] for n in notes(star, "turned_down")], ["Hopeless"])
        self.assertEqual(sorted(notes(star, "chased_by")[0]["names"]), ["Hopeless", "Strong"])
        self.assertEqual(notes(star, "chosen_over")[0]["names"], ["GM other"])

    def test_wanted_gm_refuses_lone_hopeless_offer_while_others_open(self):
        torneo, fo = make_league({"Strong": ("Contender", 60, 80, "Bilanciato"),
                                  "Hopeless": ("Rebuilding", 15, 70, "Bilanciato")})
        star, other = make_gm("star", skill=85, years=10), make_gm("other", skill=50)
        add(fo, star, other)
        # Strong's owner wants "other" most, Hopeless wants the star: the star says no and waits.
        prefs = {("Strong", "other"): 10, ("Strong", "star"): 5, ("Hopeless", "star"): 10, ("Hopeless", "other"): 5}
        with mock.patch.object(hiring, "owner_score", lambda t, gm, wanted, rng: prefs[(t.nome, gm.gm_id)]):
            hires = run_hiring_round(torneo, fo, ["Hopeless", "Strong"], Stub())
        self.assertEqual(hires["Strong"], "other")
        self.assertTrue(hires["Hopeless"].startswith("gen_"))   # down its list: a made-up GM gets his chance
        self.assertIsNone(star.team)                              # the star waits for a better offer
        self.assertEqual([n["team"] for n in notes(star, "turned_down")], ["Hopeless"])

    def test_wanted_gm_takes_the_last_open_seat(self):
        torneo, fo = make_league({"Hopeless": ("Rebuilding", 15, 70, "Bilanciato")})
        add(fo, make_gm("star", skill=85, years=10))
        self.assertEqual(run_hiring_round(torneo, fo, ["Hopeless"], Stub()), {"Hopeless": "star"})

    def test_interim_replaced_in_offseason(self):
        torneo, fo = make_league({"A": ("Mediocre", 41, 75, "Ricostruttore")})
        _seat_generated(fo, "A", YEAR - 1)
        interim = fo.seated_gm("A")
        self.assertIn(interim.gm_id, [g.gm_id for g in available_candidates(fo, YEAR)])
        add(fo, make_gm("better", skill=90, age=35))
        self.assertEqual(run_hiring_round(torneo, fo, ["A"], Stub()), {"A": "better"})
        self.assertEqual(interim.career[-1]["end"], "interim_end")
        self.assertIsNone(interim.team)
        self.assertIn(interim.gm_id, [g.gm_id for g in available_candidates(fo, YEAR)])

    def test_interim_confirmed_keeps_his_job(self):
        torneo, fo = make_league({"A": ("Mediocre", 41, 75, "Bilanciato")})
        _seat_generated(fo, "A", YEAR - 1)
        interim = fo.seated_gm("A")
        self.assertEqual(run_hiring_round(torneo, fo, ["A"], Stub()), {"A": interim.gm_id})
        self.assertFalse(interim.interim)
        self.assertEqual(len(interim.career), 1)
        self.assertIsNone(interim.career[0]["end"])

    def test_hiring_notes_keep_only_the_newest(self):
        gm = make_gm("busy")
        for i in range(FO.HIRING_NOTES_KEEP + 5):
            hiring._note(gm, 2000 + i, "turned_down", "A", [])
        self.assertEqual(len(gm.hiring_notes), FO.HIRING_NOTES_KEEP)
        self.assertEqual(gm.hiring_notes[-1]["year"], 2000 + FO.HIRING_NOTES_KEEP + 4)
        self.assertEqual(gm.hiring_notes[0]["year"], 2005)

    def test_wanted_profile_reads_config(self):
        torneo, fo = make_league({"A": ("Rebuilding", 20, 70, "Bilanciato")})
        self.assertEqual(hiring.wanted_profile(torneo, team(torneo, "A")), FO.HIRING_WANTED_BY_PLAN["REBUILDER"])

    def test_team_never_rehires_the_gm_it_fired(self):
        torneo, fo = make_league({"A": ("Mediocre", 41, 75, "Bilanciato")})
        fired = make_gm("fired", skill=90)
        fired.career = [{"team": "A", "from_year": 2002, "to_year": YEAR, "end": "fired"}]
        add(fo, fired, make_gm("plain", skill=50))
        self.assertEqual(run_hiring_round(torneo, fo, ["A"], Stub()), {"A": "plain"})


class NewGmPlanTests(unittest.TestCase):
    def test_new_gm_plan_reason_names_him(self):
        torneo, fo = make_league({"A": ("Contender", 50, 80, "Bilanciato")})
        gm = make_gm("g")
        new_gm_plan(torneo, team(torneo, "A"), gm, YEAR)
        last = fo.plans["A"].history[-1]
        self.assertEqual(last["checkpoint"], "new_gm")
        self.assertTrue(last["reason"].startswith("New GM "))
        self.assertIn(gm.name, last["reason"])
        self.assertEqual(fo.plans["A"].state, "CONTENDER")

    def test_middle_read_leans_on_his_philosophy(self):
        for traits, state in ((["PICK_HOARDER", "YOUTH_FIRST"], "REBUILDER"),
                              (["STAR_CHASER", "VETERAN_LOVER"], "PLAYOFF"),
                              (["PICK_HOARDER", "STAR_CHASER"], "MIDDLE")):
            torneo, fo = make_league({"A": ("Mediocre", 41, 75, "Bilanciato")})
            new_gm_plan(torneo, team(torneo, "A"), make_gm("g", traits=traits), YEAR)
            self.assertEqual(fo.plans["A"].state, state, traits)
            self.assertEqual(fo.plans["A"].history[-1]["checkpoint"], "new_gm")


    def hire_and_run_seasons(self, status, traits, seasons=3):
        from core.front_office.plans import checkpoint_new_season
        torneo, fo = make_league({"A": (status, 41, 75, "Bilanciato")})
        gm = make_gm("g", traits=traits)
        add(fo, gm)
        start_job(gm, "A", YEAR)
        fo.seats["A"] = "g"
        new_gm_plan(torneo, team(torneo, "A"), gm, YEAR)
        held = []
        for _ in range(seasons):
            checkpoint_new_season(torneo, Stub())
            torneo.anno_corrente += 1
            held.append((fo.plans["A"].state, fo.plans["A"].seasons_held))
        return fo, held

    def test_lean_plan_sticks_on_a_middle_roster(self):
        fo, held = self.hire_and_run_seasons("Mediocre", ["PICK_HOARDER", "YOUTH_FIRST"])
        self.assertEqual(held, [("REBUILDER", 1), ("REBUILDER", 2), ("REBUILDER", 3)])
        self.assertEqual([h["checkpoint"] for h in fo.plans["A"].history], ["new_gm"])

    def test_lean_does_not_override_a_clear_roster_read(self):
        # A rebuilding roster: a win-now GM gets no lean, the normal rules hold the REBUILDER plan.
        fo, held = self.hire_and_run_seasons("Rebuilding", ["STAR_CHASER", "VETERAN_LOVER"])
        self.assertEqual(held, [("REBUILDER", 1), ("REBUILDER", 2), ("REBUILDER", 3)])
        # The roster turns into a contender: an extreme jump still changes the plan at once.
        from core.front_office.plans import checkpoint_new_season
        torneo, fo = make_league({"A": ("Rebuilding", 41, 75, "Bilanciato")})
        gm = make_gm("g", traits=["PICK_HOARDER", "YOUTH_FIRST"])
        add(fo, gm)
        start_job(gm, "A", YEAR)
        fo.seats["A"] = "g"
        new_gm_plan(torneo, team(torneo, "A"), gm, YEAR)
        torneo._determina_stato_squadra = lambda s: "Contender"
        checkpoint_new_season(torneo, Stub())
        self.assertEqual(fo.plans["A"].state, "CONTENDER")


class OffseasonTests(unittest.TestCase):
    def failing_league(self):
        torneo, fo = make_league({"A": ("Contender", 30, 75, "Bilanciato"), "B": ("Mediocre", 41, 75, "Bilanciato")})
        fo.plans["A"] = TeamPlan(state="CONTENDER", since_year=2002, seasons_held=4, reason="t", history=[])
        for name, gm_id in (("A", "bad"), ("B", "fine")):
            gm = make_gm(gm_id, age=45)
            add(fo, gm)
            start_job(gm, name, 2002)
            gm.tenure = 4
            fo.seats[name] = gm_id
        fo.records["A"] = [{"year": 2002 + i, "wins": 30, "losses": 52, "expected": 45, "playoffs": False,
                            "champion": False, "plan": "CONTENDER", "gm_id": "bad", "coach_fired": False}
                           for i in range(4)]
        return torneo, fo

    def test_offseason_returns_events(self):
        torneo, fo = self.failing_league()
        events = front_office_offseason(torneo, Stub(0.0))
        self.assertEqual([(e["team"], e["gm"]) for e in events["fired"]], [("A", "GM bad")])
        self.assertIn("straight seasons", events["fired"][0]["reason"])
        self.assertEqual([e["team"] for e in events["hired"]], ["A"])
        self.assertNotEqual(fo.seats["A"], "bad")
        self.assertEqual(fo.seats["B"], "fine")
        self.assertEqual(fo.gms["bad"].career[-1]["end"], "fired")
        self.assertEqual(fo.plans["A"].history[-1]["checkpoint"], "new_gm")
        self.assertEqual(events["retired"], [])
        log = torneo.offseason_log_data["ritiri_sviluppo"]
        self.assertTrue(any("fired GM" in line for line in log))
        self.assertTrue(any("hired" in line for line in log))

    def test_confirmed_interim_keeps_the_plan(self):
        torneo, fo = make_league({"A": ("Contender", 41, 75, "Bilanciato")})
        fo.plans["A"] = TeamPlan(state="REBUILDER", since_year=2005, seasons_held=2, reason="kept", history=[])
        _seat_generated(fo, "A", YEAR - 1)
        interim = fo.seated_gm("A")
        with mock.patch.object(hiring, "owner_score", lambda t, gm, wanted, rng: 100.0 if gm is interim else 0.0):
            events = front_office_offseason(torneo, Stub(0.99))
        self.assertEqual(events["hired"][0]["gm_id"], interim.gm_id)
        self.assertEqual((fo.plans["A"].state, fo.plans["A"].reason, fo.plans["A"].history), ("REBUILDER", "kept", []))

    def test_user_team_never_judged_nor_filled(self):
        torneo, fo = self.failing_league()
        torneo.user_role, torneo.squadra_giocatore = "gm_coach", team(torneo, "A")
        fo.seats.pop("A")
        fo.gms["bad"].team = None
        events = front_office_offseason(torneo, Stub(0.0))
        self.assertEqual((events["fired"], events["hired"]), ([], []))
        self.assertNotIn("A", fo.seats)


if __name__ == "__main__":
    unittest.main()
