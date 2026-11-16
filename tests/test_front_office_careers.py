"""AI GM layer 3: GM growth, decline and retirement (core/front_office/careers.py)."""
import os
import random
import sys
import dataclasses
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office import careers
from core.front_office.careers import grow_skills, retire_gms, retirement_chance
from core.front_office.models import CpuGM
from core.front_office.state import FrontOfficeState, start_job

FO = CONFIG.FRONT_OFFICE


class Always:
    """Stub rng: random() is a fixed number."""
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def make_gm(gm_id="g1", age=45, years=0, **kw):
    return CpuGM(gm_id=gm_id, name=gm_id, age=age, years_as_gm=years, traits=[],
                 skills={"trade": 60, "contracts": 60, "draft": 60}, **kw)


def total(gm):
    return sum(gm.skills.values())


class GrowthTests(unittest.TestCase):
    def test_young_gm_grows_more_than_veteran(self):
        rookie, veteran = make_gm(years=0), make_gm(years=12)
        grow_skills(rookie, None, Always(0.99))
        grow_skills(veteran, None, Always(0.99))
        self.assertEqual(rookie.skills["trade"], 62)   # x2.0
        self.assertEqual(veteran.skills["trade"], 60)  # x0.5: the half point missed
        v2 = make_gm(years=12)
        grow_skills(v2, None, Always(0.0))
        self.assertEqual(v2.skills["trade"], 61)       # the half point landed

    def test_no_growth_after_55(self):
        gm = make_gm(age=55, years=0)
        grow_skills(gm, {"wins": 70, "expected": 40, "playoffs": True, "champion": True}, Always(0.99))
        self.assertEqual(gm.skills, {"trade": 60, "contracts": 60, "draft": 60})

    def test_title_season_bonus(self):
        plain, champ = make_gm(years=6), make_gm(years=6)
        grow_skills(plain, {"wins": 41, "expected": 41, "playoffs": False, "champion": False}, Always(0.99))
        grow_skills(champ, {"wins": 60, "expected": 41, "playoffs": True, "champion": True}, Always(0.99))
        # beat expected +1, playoffs +1, title +2 on top of the base point
        self.assertEqual(champ.skills["trade"] - plain.skills["trade"], 4)

    def test_decline_after_58(self):
        gm = make_gm(age=59, years=20)
        grow_skills(gm, None, Always(0.0))
        self.assertEqual(gm.skills["trade"], 59)
        gm = make_gm(age=59, years=20)
        grow_skills(gm, None, Always(0.99))
        self.assertEqual(gm.skills["trade"], 60)

    def test_skills_clamped(self):
        gm = make_gm(years=0)
        gm.skills = {"trade": 94, "contracts": 95, "draft": 20}
        grow_skills(gm, {"wins": 70, "expected": 40, "playoffs": True, "champion": True}, Always(0.99))
        self.assertEqual(gm.skills["trade"], FO.SKILL_CEILING)
        old = make_gm(age=70)
        old.skills = {"trade": 20}
        grow_skills(old, None, Always(0.0))
        self.assertEqual(old.skills["trade"], FO.SKILL_FLOOR)


class CheckpointTests(unittest.TestCase):
    def test_new_season_grows_seated_gms_only_then_ages(self):
        from core.front_office.plans import checkpoint_new_season
        torneo = SimpleNamespace(squadre=[], season_number=3, starting_year=2002, anno_corrente=2004,
                                 user_role="spectator", squadra_giocatore=None)
        fo = FrontOfficeState()
        seated, free = make_gm("s", age=40), make_gm("f", age=40)
        start_job(seated, "A", 2002)
        for gm in (seated, free):
            fo.gms[gm.gm_id] = gm
        torneo.front_office = fo
        checkpoint_new_season(torneo, Always(0.99))
        self.assertEqual(seated.skills["trade"], 62)
        self.assertEqual(free.skills["trade"], 60)
        self.assertEqual((seated.age, free.age), (41, 41))

    def test_new_gm_does_not_inherit_predecessor_season(self):
        from core.front_office.plans import checkpoint_new_season
        torneo = SimpleNamespace(squadre=[], season_number=3, starting_year=2002, anno_corrente=2004,
                                 user_role="spectator", squadra_giocatore=None)
        fo = FrontOfficeState()
        title = {"year": 2003, "wins": 65, "expected": 45, "playoffs": True, "champion": True}
        heir, owner_of_row = make_gm("heir", age=40, years=6), make_gm("champ", age=40, years=6)
        start_job(heir, "A", 2004)
        start_job(owner_of_row, "B", 2002)
        fo.records = {"A": [dict(title, gm_id="old")], "B": [dict(title, gm_id="champ")]}
        for gm in (heir, owner_of_row):
            fo.gms[gm.gm_id] = gm
        torneo.front_office = fo
        checkpoint_new_season(torneo, Always(0.99))
        self.assertEqual(heir.skills["trade"], 61)          # base point only
        self.assertEqual(owner_of_row.skills["trade"], 65)  # + beat expected, playoffs, title


class RetirementTests(unittest.TestCase):
    def test_retirement_ages_come_from_the_curve(self):
        points = ((60, 0.10), (66, 1.0))
        with mock.patch.object(careers, "CONFIG", dataclasses.replace(
                CONFIG, FRONT_OFFICE=dataclasses.replace(FO, RETIRE_CHANCE_POINTS=points))):
            self.assertEqual(retirement_chance(make_gm(age=59)), 0.0)
            self.assertAlmostEqual(retirement_chance(make_gm(age=60)), 0.10)
            self.assertAlmostEqual(retirement_chance(make_gm(age=63)), 0.55)
            self.assertEqual(retirement_chance(make_gm(age=66)), 1.0)
        self.assertFalse(hasattr(FO, "RETIRE_MIN_AGE") or hasattr(FO, "RETIRE_MAX_AGE"))

    def test_retirement_chance_curve(self):
        chances = [retirement_chance(make_gm(age=a)) for a in range(50, 76)]
        self.assertEqual(retirement_chance(make_gm(age=57)), 0.0)
        self.assertEqual(retirement_chance(make_gm(age=70)), 1.0)
        self.assertEqual(retirement_chance(make_gm(age=75)), 1.0)
        self.assertEqual(chances, sorted(chances))
        self.assertAlmostEqual(retirement_chance(make_gm(age=65)), 0.30)

    def seated(self, **kw):
        torneo = SimpleNamespace(anno_corrente=2010, starting_year=2002, season_number=9, campione=None)
        fo = FrontOfficeState()
        gm = make_gm(**kw)
        start_job(gm, "A", 2005)
        fo.gms[gm.gm_id] = gm
        fo.seats["A"] = gm.gm_id
        return torneo, fo, gm

    def test_seated_gm_retires_and_leaves_the_seat(self):
        torneo, fo, gm = self.seated(age=69)
        retired = retire_gms(torneo, fo, Always(0.0))
        self.assertEqual(retired, [gm])
        self.assertEqual(gm.retired_year, 2010)
        self.assertNotIn("A", fo.seats)
        self.assertEqual(gm.career[-1]["end"], "retired")

    def test_young_gm_stays(self):
        torneo, fo, gm = self.seated(age=45)
        self.assertEqual(retire_gms(torneo, fo, Always(0.0)), [])
        self.assertIsNone(gm.retired_year)

    def test_champion_gm_not_retired(self):
        torneo, fo, gm = self.seated(age=69)
        torneo.campione = SimpleNamespace(nome="A")
        self.assertEqual(retire_gms(torneo, fo, Always(0.0)), [])
        self.assertEqual(fo.seats["A"], gm.gm_id)

    def test_idle_market_gm_retires(self):
        torneo = SimpleNamespace(anno_corrente=2010, campione=None)
        fo = FrontOfficeState()
        idle = make_gm("idle", age=40, available_from_year=2006)
        recent = make_gm("recent", age=40, available_from_year=2008)
        historical = make_gm("hist", age=40, available_from_year=2000, historical=True)
        for gm in (idle, recent, historical):
            fo.gms[gm.gm_id] = gm
        retired = retire_gms(torneo, fo, Always(0.99))
        self.assertEqual(retired, [idle])
        self.assertEqual(idle.retired_year, 2010)

    def test_idle_years_count_from_his_last_job(self):
        # A made-up GM, generated years ago, fired last offseason: idle for one year, not since 2004.
        torneo = SimpleNamespace(anno_corrente=2010, campione=None)
        fo = FrontOfficeState()
        fired = make_gm("fired", age=40, available_from_year=2004)
        fired.career = [{"team": "A", "from_year": 2004, "to_year": 2009, "end": "fired"}]
        long_gone = make_gm("gone", age=40, available_from_year=2002)
        long_gone.career = [{"team": "B", "from_year": 2002, "to_year": 2010 - FO.MARKET_IDLE_RETIRE_YEARS,
                             "end": "fired"}]
        for gm in (fired, long_gone):
            fo.gms[gm.gm_id] = gm
        self.assertEqual(retire_gms(torneo, fo, Always(0.99)), [long_gone])

    def test_market_gm_retires_by_age(self):
        torneo = SimpleNamespace(anno_corrente=2010, campione=None)
        fo = FrontOfficeState()
        old = make_gm("old", age=70, available_from_year=2009, historical=True)
        fo.gms["old"] = old
        self.assertEqual(retire_gms(torneo, fo, random.Random(1)), [old])


if __name__ == "__main__":
    unittest.main()
