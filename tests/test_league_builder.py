"""Deterministic league JSON -> DB builder (Task 2)."""
import copy
import os
import sqlite3
import tempfile
import unittest

from core.league.builder import build_league_db
from core.league.schema import ABILITY_KEYS, TENDENCY_KEYS, league_from_dict, load_league
from tests.test_league_schema import make_league_dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_LEAGUE = os.path.join(ROOT, "mods", "Real Names 2002", "league.json")
DB_2002 = os.path.join(ROOT, "data", "nba_sim_2002.db")


def dump(path):
    conn = sqlite3.connect(path)
    try:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
                for t in ("teams", "players", "abilities", "tendencies", "contracts", "coaches")}
    finally:
        conn.close()


class LeagueBuilderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def _real(self):
        if not os.path.exists(REAL_LEAGUE):
            self.skipTest("Real Names 2002 mod folder is not installed")
        if not os.path.exists(DB_2002):
            self.skipTest("data/nba_sim_2002.db is not present")
        return load_league(REAL_LEAGUE)

    def test_build_real_league_matches_2002_db(self):
        data = self._real()
        dest = os.path.join(self.dir, "real.db")
        build_league_db(data, dest)
        built, ref = sqlite3.connect(dest), sqlite3.connect(
            "file:" + DB_2002.replace("\\", "/") + "?mode=ro", uri=True)
        try:
            cols = ("role, age, overall, potential, years_on_team, teams_drafted, " + ", ".join(
                f"(SELECT {c} FROM abilities a WHERE a.player_id = p.id)" for c in ABILITY_KEYS) + ", " + ", ".join(
                f"(SELECT {c} FROM tendencies t WHERE t.player_id = p.id)" for c in TENDENCY_KEYS))
            q = f"SELECT name, {cols} FROM players p ORDER BY name"
            got, want = built.execute(q).fetchall(), ref.execute(q).fetchall()
            self.assertEqual(len(got), 428)
            self.assertEqual(got, want)
            tq = "SELECT name, conference, owner_personality FROM teams ORDER BY name"
            self.assertEqual(built.execute(tq).fetchall(), ref.execute(tq).fetchall())
        finally:
            built.close()
            ref.close()

    def test_build_is_deterministic(self):
        data = self._real()
        a, b = os.path.join(self.dir, "a.db"), os.path.join(self.dir, "b.db")
        build_league_db(data, a)
        build_league_db(data, b)
        self.assertEqual(dump(a), dump(b))

    def test_teams_have_franchise_id(self):
        data = league_from_dict(make_league_dict())
        dest = os.path.join(self.dir, "t.db")
        build_league_db(data, dest)
        conn = sqlite3.connect(dest)
        try:
            rows = conn.execute("SELECT name, franchise_id FROM teams ORDER BY id").fetchall()
        finally:
            conn.close()
        self.assertEqual(rows, [(fr.name, fr.id) for fr in data.franchises])

    def test_failed_build_leaves_existing_dest_untouched(self):
        data = league_from_dict(make_league_dict())
        dest = os.path.join(self.dir, "keep.db")
        with open(dest, "wb") as fh:
            fh.write(b"existing database bytes")
        bad = copy.deepcopy(data)
        del bad.players["T03"][0]["abilities"]
        with self.assertRaises(Exception):
            build_league_db(bad, dest)
        with open(dest, "rb") as fh:
            self.assertEqual(fh.read(), b"existing database bytes")
        self.assertFalse(os.path.exists(dest + ".tmp"))


if __name__ == "__main__":
    unittest.main()
