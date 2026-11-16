"""Where a save's draft classes come from (core/league/draft_source.py): the save's own copy, else (old saves
only) the Real Names 2002 mod, else none (generated rookies)."""
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from core import save_manager
from core.league import draft_source


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("[]")


class DraftClassFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hardwood_draft_source_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.saves = os.path.join(self.tmp, "saves")
        self.root = os.path.join(self.tmp, "game")
        self.mod_file = os.path.join(self.root, "mods", "Real Names 2002", "draft_classes", "DRAFT_2003.json")
        _touch(self.mod_file)
        os.makedirs(os.path.join(self.saves, "Career"), exist_ok=True)
        self.save_file = os.path.join(self.saves, "Career", "draft_classes", "DRAFT_2003.json")
        patches = [mock.patch.object(save_manager, "SAVES_DIR", self.saves),
                   mock.patch.object(draft_source, "GAME_ROOT", self.root)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        previous = save_manager.get_active_save_name()
        save_manager.set_active_save_name("Career")
        self.addCleanup(save_manager.set_active_save_name, previous)
        self.new_save = SimpleNamespace(league_meta={"id": "fictional_2002", "name": "Fictional", "era": "2002"})
        self.old_save = SimpleNamespace(league_meta={})

    def test_new_save_reads_its_own_copy(self):
        _touch(self.save_file)
        self.assertEqual(os.path.normcase(draft_source.draft_class_file(self.new_save, 2003)),
                         os.path.normcase(self.save_file))

    def test_new_save_without_copied_classes_is_generated(self):
        # The mod has a 2003 class, but a new save never reads outside its own folder.
        self.assertIsNone(draft_source.draft_class_file(self.new_save, 2003))

    def test_legacy_save_reads_the_mod(self):
        self.assertEqual(os.path.normcase(draft_source.draft_class_file(self.old_save, 2003)),
                         os.path.normcase(self.mod_file))

    def test_legacy_save_prefers_its_own_copy(self):
        _touch(self.save_file)
        self.assertEqual(os.path.normcase(draft_source.draft_class_file(self.old_save, 2003)),
                         os.path.normcase(self.save_file))

    def test_legacy_save_without_mod_file_is_generated(self):
        self.assertIsNone(draft_source.draft_class_file(self.old_save, 2010))

    def test_no_active_save_falls_back_like_a_legacy_save(self):
        save_manager.set_active_save_name(None)
        self.assertIsNone(draft_source.draft_class_file(self.new_save, 2003))
        self.assertEqual(os.path.normcase(draft_source.draft_class_file(self.old_save, 2003)),
                         os.path.normcase(self.mod_file))

    def test_tournament_without_league_meta_is_legacy(self):
        self.assertEqual(os.path.normcase(draft_source.draft_class_file(SimpleNamespace(), 2003)),
                         os.path.normcase(self.mod_file))


class DraftReadSitesTests(unittest.TestCase):
    def test_no_hard_coded_draft_folder_in_runtime_code(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        found = []
        for rel in ("main.py", "offseason/draft.py"):
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if '"draft_classes"' in line or '"Draft_Classes"' in line:
                        found.append(f"{rel}:{i}")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
