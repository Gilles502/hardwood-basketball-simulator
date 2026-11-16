"""Writes go to the user root, shipped data is read from the game root (packaged build, Phase 4.2)."""
import importlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

from core import paths
from core.league import builder, catalog

REAL_GAME_ROOT = paths.game_root()
REAL_LEAGUE = os.path.join(REAL_GAME_ROOT, "data", "leagues", "fictional_2002", "league.json")


def _listing(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)


class TwoRootsCase(unittest.TestCase):
    def setUp(self):
        self.game = tempfile.mkdtemp()
        self.user = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.game, True)
        self.addCleanup(shutil.rmtree, self.user, True)
        builtin = os.path.join(self.game, "data", "leagues", "fictional_2002")
        os.makedirs(builtin)
        shutil.copyfile(REAL_LEAGUE, os.path.join(builtin, "league.json"))
        for name, root in (("game_root", self.game), ("user_root", self.user)):
            p = mock.patch.object(paths, name, return_value=root)
            p.start()
            self.addCleanup(p.stop)


class TestCatalogRoots(TwoRootsCase):
    def test_catalog_reads_builtin_from_game_root_and_mods_from_user_root(self):
        mod = os.path.join(self.user, "mods", "X")
        os.makedirs(mod)
        shutil.copyfile(REAL_LEAGUE, os.path.join(mod, "league.json"))
        ids = {e["id"] for e in catalog.list_leagues()}
        self.assertEqual(ids, {"fictional_2002", "X"})

    def test_catalog_builds_into_user_root(self):
        before = _listing(self.game)
        result = catalog.build_and_activate("fictional_2002")
        self.assertTrue(result["ok"], result)
        self.assertTrue(os.path.isfile(os.path.join(self.user, "data", "leagues", "active.json")))
        built = os.listdir(os.path.join(self.user, "data", "leagues", "built"))
        self.assertEqual(len([b for b in built if b.endswith(".db")]), 1)
        self.assertEqual(_listing(self.game), before)


class TestDraftSourceAndRegistryRoots(TwoRootsCase):
    def test_real_names_mod_is_read_from_user_root(self):
        from core.league import draft_source
        self.assertEqual(draft_source._mod_dir(), os.path.join(self.user, "mods", "Real Names 2002"))

    def test_registry_defaults_split_roots(self):
        from core.league import registry
        self.assertEqual(registry._default_league_paths(), (
            os.path.join(self.user, "mods", "Real Names 2002", "league.json"),
            os.path.join(self.game, "data", "leagues", "fictional_2002", "league.json"),
        ))


class TestModuleConstants(unittest.TestCase):
    def test_builder_template_from_game_root(self):
        self.assertEqual(builder.TEMPLATE_DB, paths.game_path("data", "nba_sim_template.db"))

    def test_saves_dir_default_is_user_root(self):
        import core.save_manager as save_manager
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        saved = dict(os.environ)

        def restore():
            os.environ.clear()
            os.environ.update(saved)
            importlib.reload(save_manager)
        self.addCleanup(restore)
        os.environ.pop("HARDWOOD_SAVES_DIR", None)
        os.environ["HARDWOOD_USER_DIR"] = tmp
        importlib.reload(save_manager)
        self.assertEqual(save_manager.SAVES_DIR, os.path.join(tmp, "saves"))
        self.assertEqual(save_manager.BASE_DIR, tmp)

    def test_trade_finder_root_log_in_user_root(self):
        from trades import trade_finder
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        with mock.patch.dict(os.environ, {"HARDWOOD_USER_DIR": tmp}):
            self.assertEqual(trade_finder._root_trade_log_path(), os.path.join(tmp, "trades_history.txt"))

    def test_main_log_dir_in_user_root(self):
        import main
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        with mock.patch.dict(os.environ, {"HARDWOOD_USER_DIR": tmp}):
            self.assertEqual(main._log_dir(), os.path.join(tmp, "scratch"))


if __name__ == "__main__":
    unittest.main()
