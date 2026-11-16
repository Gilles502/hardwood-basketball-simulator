"""Save names: 'Team · era' display names, a new career never overwrites an existing slot, re-saving keeps the name."""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import save_manager


class SaveNamingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for p in (mock.patch.object(save_manager, "BASE_DIR", tmp.name),
                  mock.patch.object(save_manager, "SAVES_DIR", os.path.join(tmp.name, "saves")),
                  mock.patch.object(save_manager, "ACTIVE_SAVE_NAME", None),
                  mock.patch.object(save_manager, "_SESSION_OWNER", None)):
            p.start()
            self.addCleanup(p.stop)
        os.makedirs(os.path.join(tmp.name, "data"))
        with open(os.path.join(tmp.name, "data", "nba_sim.db"), "w") as f:
            f.write("db")

    def _fake_save(self, name):
        path = save_manager.get_save_path(name)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "save_metadata.json"), "w", encoding="utf-8") as f:
            f.write("{}")

    def test_default_name_is_team_and_era(self):
        self.assertEqual(save_manager.default_save_name("Toronto Northmen", "2002"), "Toronto Northmen · 2002")
        self.assertEqual(save_manager.default_save_name(None, "2002"), "League · 2002")
        self.assertEqual(save_manager.default_save_name("", "modern"), "League · Modern")

    def test_unique_name_adds_a_number_when_the_slot_exists(self):
        name = "Toronto Northmen · 2002"
        self.assertEqual(save_manager.unique_save_name(name), name)
        os.makedirs(save_manager.get_save_path(name))
        self.assertEqual(save_manager.unique_save_name(name), name)  # an empty leftover folder is not a save
        self._fake_save(name)
        self.assertEqual(save_manager.unique_save_name(name), "Toronto Northmen · 2002 (2)")
        self._fake_save("Toronto Northmen · 2002 (2)")
        self.assertEqual(save_manager.unique_save_name(name), "Toronto Northmen · 2002 (3)")

    def test_resaving_by_folder_name_keeps_the_display_name(self):
        tour = SimpleNamespace(squadra_giocatore=None, season_number=1)
        name = "Toronto Northmen · 2002"
        save_manager.set_active_save_name(name)
        with mock.patch.object(save_manager, "serialize_tournament_state", return_value={}):
            meta = save_manager.save_game(name, tour)
            folder = meta["save_name"]
            self.assertEqual(meta["display_name"], name)
            save_manager.set_active_save_name(folder)
            again = save_manager.save_game(folder, tour)
        self.assertEqual(again["display_name"], name)


if __name__ == "__main__":
    unittest.main()
