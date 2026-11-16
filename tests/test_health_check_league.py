"""Health check --league: the run starts from a league file built through the catalogue, like a new career."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import save_manager
from core.league import catalog, registry
from core.league.schema import LeagueError
from scripts import health_check
from tests.test_league_routes import prospect_rows
from tests.test_league_schema import make_league_dict


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


class HealthCheckLeagueTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        builtin = make_league_dict()
        builtin["meta"]["name"] = "Fiction 2002"
        write_json(os.path.join(self.root, catalog.BUILTIN_LEAGUE_FILE), builtin)
        real = make_league_dict()
        real["meta"]["name"] = "Real Names 2002"
        for fr in real["franchises"]:
            fr["name"] = "Real " + fr["name"]
        mod = os.path.join(self.root, "mods", "Real Names 2002")
        write_json(os.path.join(mod, "league.json"), real)
        write_json(os.path.join(mod, "draft_classes", "DRAFT_2003.json"), prospect_rows(["Real Rookie"]))
        os.makedirs(os.path.join(self.root, "data"), exist_ok=True)
        self.addCleanup(setattr, registry, "_active", registry._active)
        self.save = "HC_League_Test"

    def _teams(self):
        conn = sqlite3.connect(os.path.join(self.root, "data", "nba_sim.db"))
        try:
            return {r[0] for r in conn.execute("SELECT name FROM teams")}
        finally:
            conn.close()

    def test_default_league_is_the_builtin_fictional_one(self):
        args = health_check.build_parser().parse_args([])
        self.assertEqual(args.league, catalog.BUILTIN_LEAGUE_ID)
        self.assertEqual(args.era, "2002")
        args = health_check.build_parser().parse_args(["--league", "Real Names 2002"])
        self.assertEqual(args.league, "Real Names 2002")

    def test_prepare_builtin_league(self):
        meta, reg = health_check.prepare_league(catalog.BUILTIN_LEAGUE_ID, self.save, root=self.root)
        self.assertEqual(meta, {"id": catalog.BUILTIN_LEAGUE_ID, "name": "Fiction 2002", "era": "2002"})
        self.assertIs(registry.get_active_registry(), reg)
        self.assertIn("City0 Nick0", self._teams())
        self.assertFalse(os.path.exists(os.path.join(save_manager.get_save_path(self.save), "draft_classes")))
        # Everything built lands under the given root (the sandbox), never in the real data/.
        self.assertTrue(os.listdir(os.path.join(self.root, catalog.BUILT_DIR)))

    def test_prepare_real_names_mod_copies_its_draft_classes(self):
        meta, reg = health_check.prepare_league("Real Names 2002", self.save, root=self.root)
        self.assertEqual(meta["id"], "Real Names 2002")
        self.assertIn("Real City0 Nick0", self._teams())
        self.assertIn("Real City0 Nick0", reg.names())
        own = os.path.join(save_manager.get_save_path(self.save), "draft_classes", "DRAFT_2003.json")
        self.assertTrue(os.path.isfile(own))

    def test_unknown_league_raises(self):
        with self.assertRaises(LeagueError):
            health_check.prepare_league("No Such League", self.save, root=self.root)

    def test_sandbox_copies_the_league_folders(self):
        self.assertIn("data", health_check.SANDBOX_DIRS)   # data/leagues/ (built-in league)
        self.assertIn("mods", health_check.SANDBOX_DIRS)


if __name__ == "__main__":
    unittest.main()
