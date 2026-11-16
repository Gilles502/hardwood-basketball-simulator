"""AI GM layer 1: the GM roster data file and its loader (core/front_office/roster.py)."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office.models import CpuGM
from core.front_office.roster import generated_gm, load_roster, roster_team_id
from core.league.registry import FranchiseRegistry
from core.league.schema import load_league

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_LEAGUE = os.path.join(ROOT, "mods", "Real Names 2002", "league.json")
FICTIONAL_LEAGUE = os.path.join(ROOT, "data", "leagues", "fictional_2002", "league.json")

# Real GM names that used to live in core/board_engine.py: a local file next to the Real Names mod, never in
# the public repo. The parody roster can never fall back to them.
DENYLIST = os.path.join(ROOT, "mods", "Real Names 2002", "denylist.json")


def real_gm_names():
    if not os.path.isfile(DENYLIST):
        return frozenset()
    with open(DENYLIST, encoding="utf-8") as fh:
        return frozenset(json.load(fh)["gms"])


def era_2002_team_names():
    con = sqlite3.connect(os.path.join(ROOT, "data", "nba_sim_2002.db"))
    try:
        return [row[0] for row in con.execute("SELECT name FROM teams")]
    finally:
        con.close()


@unittest.skipUnless(os.path.isfile(REAL_LEAGUE), "Real Names 2002 mod not installed")
class RosterFileTests(unittest.TestCase):
    """The GM roster is the league file's staff.gms (team = franchise id)."""

    def setUp(self):
        self.registry = FranchiseRegistry.from_league(load_league(REAL_LEAGUE))
        self.roster = load_roster(self.registry)
        self.fo = CONFIG.FRONT_OFFICE

    @unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "data", "nba_sim_2002.db")),
                         "the real 2002 DB is local only (opening a missing one would create an empty file)")
    def test_roster_covers_every_2002_team(self):
        teams = era_2002_team_names()
        self.assertEqual(len(teams), 30)
        starting_teams = [entry["team"] for entry in self.roster["starting"]]
        self.assertEqual(len(starting_teams), 30)
        for name in teams:
            self.assertEqual(starting_teams.count(roster_team_id(name, "", self.registry)), 1, name)

    def test_fictional_league_teams_match_by_id(self):
        fictional = FranchiseRegistry.from_league(load_league(FICTIONAL_LEAGUE))
        starting_teams = [entry["team"] for entry in load_roster(fictional)["starting"]]
        for f in fictional.franchises:
            self.assertEqual(starting_teams.count(roster_team_id(f.name, "", fictional)), 1, f.name)
            # The stored franchise id wins over the name.
            self.assertEqual(roster_team_id("Renamed Club", f.id, fictional), f.id)

    def test_entries_are_valid(self):
        entries = self.roster["starting"] + self.roster["arrivals"]
        ids = [e["gm_id"] for e in entries]
        self.assertEqual(len(ids), len(set(ids)))
        for e in entries:
            self.assertTrue(set(e["traits"]) <= set(self.fo.TRAITS), e["gm_id"])
            self.assertTrue(2 <= len(e["traits"]) <= 3, e["gm_id"])
            for skill in self.fo.SKILLS:
                self.assertIn(skill, e["skills"], e["gm_id"])
                self.assertGreaterEqual(e["skills"][skill], self.fo.SKILL_START_MIN, e["gm_id"])
                self.assertLessEqual(e["skills"][skill], self.fo.SKILL_START_MAX, e["gm_id"])
            gm = CpuGM.from_dict(e)
            self.assertEqual(CpuGM.from_dict(gm.to_dict()), gm)
        for e in self.roster["arrivals"]:
            self.assertGreater(e["available_from_year"], 2002, e["gm_id"])
        # Nobody may be past the retirement age on day one (he would be replaced before his first season).
        for e in self.roster["starting"]:
            self.assertLess(e["age"], self.fo.RETIREMENT_AGE, e["gm_id"])

    def test_no_real_names(self):
        for e in self.roster["starting"] + self.roster["arrivals"]:
            self.assertNotIn(e["name"], real_gm_names())


class GeneratedGMTests(unittest.TestCase):
    def test_generated_gm_is_deterministic(self):
        a = generated_gm("Boston Minutemen|2010", 2010)
        b = generated_gm("Boston Minutemen|2010", 2010)
        self.assertEqual(a, b)
        lo, hi = CONFIG.FRONT_OFFICE.GENERATED_SKILL_RANGE
        for skill in CONFIG.FRONT_OFFICE.SKILLS:
            self.assertTrue(lo <= a.skills[skill] <= hi)
        age_lo, age_hi = CONFIG.FRONT_OFFICE.GENERATED_AGE_RANGE
        self.assertTrue(age_lo <= a.age <= age_hi)
        self.assertEqual(len(a.traits), 2)
        self.assertNotEqual(a.gm_id, generated_gm("Boston Minutemen|2011", 2011).gm_id)

    def test_unknown_team_and_league_without_gms(self):
        empty = FranchiseRegistry([], [], {})
        self.assertEqual(roster_team_id("Nowhere Club", "", empty), "")
        self.assertEqual(load_roster(empty), {"starting": [], "arrivals": []})


if __name__ == "__main__":
    unittest.main()
