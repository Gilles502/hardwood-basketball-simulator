"""League catalogue: built-in league + mods, build-and-activate, the active league's DB (Task 5)."""
import json
import os
import shutil
import tempfile
import unittest

from core.league import catalog
from tests.test_league_schema import make_league_dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_MOD = os.path.join(ROOT, "mods", "Real Names 2002")


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


def small_league(name="Fiction 2002"):
    d = make_league_dict()
    d["meta"]["name"] = name
    return d


def bump_mtime(path, seconds):
    st = os.stat(path)
    os.utime(path, (st.st_atime + seconds, st.st_mtime + seconds))


class LeagueCatalogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.builtin_json = os.path.join(self.root, "data", "leagues", "fictional_2002", "league.json")

    def add_builtin(self, data=None):
        write_json(self.builtin_json, data or small_league())

    def add_mod(self, folder, data=None, raw_text=None, draft=False):
        path = os.path.join(self.root, "mods", folder, "league.json")
        if raw_text is not None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(raw_text)
        else:
            write_json(path, data or small_league(folder))
        if draft:
            write_json(os.path.join(self.root, "mods", folder, "draft_classes", "DRAFT_2003.json"), [])
        return path

    def add_real_mod(self):
        if not os.path.exists(os.path.join(REAL_MOD, "league.json")):
            self.skipTest("Real Names 2002 mod folder is not installed")
        dest = os.path.join(self.root, "mods", "Real Names 2002")
        os.makedirs(os.path.join(dest, "draft_classes"))
        shutil.copyfile(os.path.join(REAL_MOD, "league.json"), os.path.join(dest, "league.json"))
        shutil.copyfile(os.path.join(REAL_MOD, "draft_classes", "DRAFT_2003.json"),
                        os.path.join(dest, "draft_classes", "DRAFT_2003.json"))

    def by_id(self):
        return {e["id"]: e for e in catalog.list_leagues(root=self.root)}

    def test_lists_builtin_and_mods(self):
        self.add_builtin()
        self.add_real_mod()
        os.makedirs(os.path.join(self.root, "mods", "not a league"))  # no league.json: not listed
        leagues = self.by_id()
        self.assertEqual(set(leagues), {catalog.BUILTIN_LEAGUE_ID, "Real Names 2002"})
        b, m = leagues[catalog.BUILTIN_LEAGUE_ID], leagues["Real Names 2002"]
        self.assertEqual((b["source"], b["name"], b["era"], b["team_count"]), ("builtin", "Fiction 2002", "2002", 30))
        self.assertEqual((m["source"], m["name"], m["era"], m["team_count"]), ("mod", "Real Names 2002", "2002", 30))
        self.assertFalse(b["has_draft_classes"])
        self.assertTrue(m["has_draft_classes"])
        self.assertEqual((b["errors"], m["errors"]), ([], []))
        self.assertFalse(b["built"] or m["built"])
        self.assertTrue(b["active"])
        self.assertFalse(m["active"])

    def test_mod_folder_with_spaces_and_accents(self):
        self.add_builtin()
        self.add_mod("Lega Città 2002")
        self.assertIn("Lega Città 2002", self.by_id())
        res = catalog.build_and_activate("Lega Città 2002", root=self.root)
        self.assertEqual(res, {"ok": True, "errors": []})
        entry = self.by_id()["Lega Città 2002"]
        self.assertTrue(entry["built"] and entry["active"])
        db = catalog.ensure_active_league_db(root=self.root)
        self.assertTrue(os.path.exists(db))
        self.assertTrue(os.path.basename(db).isascii())
        self.assertNotIn(" ", os.path.basename(db))
        self.assertEqual(catalog.active_league(root=self.root)["id"], "Lega Città 2002")

    def test_invalid_mod_listed_with_errors(self):
        self.add_builtin()
        self.add_mod("Broken", raw_text="{ not json")
        bad = small_league()
        bad["franchises"] = bad["franchises"][:29]
        self.add_mod("Short", bad)
        leagues = self.by_id()
        self.assertTrue(leagues["Broken"]["errors"])
        self.assertTrue(any("30 teams" in e for e in leagues["Short"]["errors"]))
        self.assertEqual(leagues["Short"]["team_count"], 29)
        self.assertFalse(leagues["Broken"]["active"] or leagues["Short"]["active"])

    def test_build_and_activate_switches_active(self):
        self.add_builtin()
        self.add_mod("Other", draft=True)
        self.assertEqual(catalog.active_league(root=self.root)["id"], catalog.BUILTIN_LEAGUE_ID)
        self.assertIsNone(catalog.active_draft_dir(root=self.root))
        self.assertEqual(catalog.build_and_activate("Other", root=self.root), {"ok": True, "errors": []})
        self.assertEqual(catalog.active_league(root=self.root)["id"], "Other")
        with open(os.path.join(self.root, "data", "leagues", "active.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"league_id": "Other"})
        self.assertEqual(catalog.active_draft_dir(root=self.root),
                         os.path.join(self.root, "mods", "Other", "draft_classes"))
        unknown = catalog.build_and_activate("Nope", root=self.root)
        self.assertFalse(unknown["ok"])
        self.assertTrue(unknown["errors"])

    def test_failed_build_keeps_previous_active_and_db(self):
        self.add_builtin()
        self.add_mod("Good")
        self.assertTrue(catalog.build_and_activate("Good", root=self.root)["ok"])
        good_db = catalog.ensure_active_league_db(root=self.root)
        with open(good_db, "rb") as fh:
            good_bytes = fh.read()
        built_dir = os.path.join(self.root, "data", "leagues", "built")
        before = sorted(os.listdir(built_dir))

        self.add_mod("Broken", raw_text="{ not json")
        bad = small_league()
        bad["franchises"] = bad["franchises"][:29]
        self.add_mod("Short", bad)
        for league_id in ("Broken", "Short"):
            res = catalog.build_and_activate(league_id, root=self.root)
            self.assertFalse(res["ok"])
            self.assertTrue(res["errors"])
            self.assertEqual(catalog.active_league(root=self.root)["id"], "Good")
        self.assertEqual(sorted(os.listdir(built_dir)), before)
        with open(good_db, "rb") as fh:
            self.assertEqual(fh.read(), good_bytes)

    def test_ensure_db_rebuilds_when_missing(self):
        self.add_builtin()
        db = catalog.ensure_active_league_db(root=self.root)
        self.assertTrue(os.path.exists(db))
        self.assertTrue(self.by_id()[catalog.BUILTIN_LEAGUE_ID]["built"])
        os.remove(db)
        self.assertFalse(self.by_id()[catalog.BUILTIN_LEAGUE_ID]["built"])
        self.assertEqual(catalog.ensure_active_league_db(root=self.root), db)
        self.assertTrue(os.path.exists(db))

    def test_ensure_db_rebuilds_when_json_newer(self):
        self.add_builtin()
        db = catalog.ensure_active_league_db(root=self.root)
        bump_mtime(self.builtin_json, -200)
        bump_mtime(db, -100)
        old_mtime = os.path.getmtime(db)
        self.assertTrue(self.by_id()[catalog.BUILTIN_LEAGUE_ID]["built"])
        bump_mtime(self.builtin_json, 150)  # edited after the build (still in the past)
        self.assertFalse(self.by_id()[catalog.BUILTIN_LEAGUE_ID]["built"])
        catalog.ensure_active_league_db(root=self.root)
        self.assertGreater(os.path.getmtime(db), old_mtime)
        self.assertTrue(self.by_id()[catalog.BUILTIN_LEAGUE_ID]["built"])

    def test_default_active_is_builtin(self):
        self.add_mod("Aaa First")
        self.add_builtin()
        self.assertFalse(os.path.exists(os.path.join(self.root, "data", "leagues", "active.json")))
        self.assertEqual(catalog.active_league(root=self.root)["id"], catalog.BUILTIN_LEAGUE_ID)

    def test_default_active_without_builtin_is_first_valid_mod(self):
        # Until the built-in league ships (Task 7) new careers run on the first valid mod.
        self.add_mod("Aaa Broken", raw_text="{ not json")
        self.add_mod("Zzz Mod")
        self.add_mod("Bbb Mod")
        ids = [e["id"] for e in catalog.list_leagues(root=self.root)]
        self.assertNotIn(catalog.BUILTIN_LEAGUE_ID, ids)
        self.assertEqual(catalog.active_league(root=self.root)["id"], "Bbb Mod")
        self.assertTrue(os.path.exists(catalog.ensure_active_league_db(root=self.root)))

    def test_active_pointer_to_missing_league_falls_back_to_default(self):
        self.add_builtin()
        write_json(os.path.join(self.root, "data", "leagues", "active.json"), {"league_id": "Gone"})
        self.assertEqual(catalog.active_league(root=self.root)["id"], catalog.BUILTIN_LEAGUE_ID)

    def test_active_pointer_to_now_invalid_league_stays_active_with_errors(self):
        self.add_builtin()
        path = self.add_mod("Mine")
        self.assertTrue(catalog.build_and_activate("Mine", root=self.root)["ok"])
        bad = small_league("Mine")
        bad["franchises"] = bad["franchises"][:29]
        write_json(path, bad)  # edited by hand after the build, now broken
        active = catalog.active_league(root=self.root)
        self.assertEqual(active["id"], "Mine")
        self.assertTrue(any("30 teams" in e for e in active["errors"]))
        self.assertFalse(self.by_id()[catalog.BUILTIN_LEAGUE_ID]["active"])
        with self.assertRaises(catalog.LeagueError) as ctx:
            catalog.ensure_active_league_db(root=self.root)
        self.assertEqual(ctx.exception.errors, active["errors"])

    def test_active_pointer_to_deleted_league_falls_back(self):
        self.add_builtin()
        path = self.add_mod("Mine")
        self.assertTrue(catalog.build_and_activate("Mine", root=self.root)["ok"])
        shutil.rmtree(os.path.dirname(path))
        self.assertEqual(catalog.active_league(root=self.root)["id"], catalog.BUILTIN_LEAGUE_ID)
        self.assertTrue(os.path.exists(catalog.ensure_active_league_db(root=self.root)))

    def test_no_league_at_all(self):
        self.assertIsNone(catalog.active_league(root=self.root))
        with self.assertRaises(catalog.LeagueError):
            catalog.ensure_active_league_db(root=self.root)


if __name__ == "__main__":
    unittest.main()
