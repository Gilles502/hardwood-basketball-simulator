"""History files live in a session copy during play and only reach the slot through a save."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import save_manager


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class SaveSessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        saves = os.path.join(tmp.name, "saves")
        for p in (mock.patch.object(save_manager, "BASE_DIR", tmp.name),
                  mock.patch.object(save_manager, "SAVES_DIR", saves),
                  mock.patch.object(save_manager, "ACTIVE_SAVE_NAME", None),
                  mock.patch.object(save_manager, "_SESSION_OWNER", None)):
            p.start()
            self.addCleanup(p.stop)
        for name in ("A", "B"):
            _write_json(os.path.join(saves, name, "league_history.json"), [name])
            _write_json(os.path.join(saves, name, "save_metadata.json"), {"display_name": name})

    def _slot_history(self, name):
        return _read_json(os.path.join(save_manager.get_save_path(name), "league_history.json"))

    def _hist_path(self):
        return save_manager.get_historical_file_path("league_history.json")

    def test_history_writes_go_to_session_not_slot(self):
        save_manager.set_active_save_name("A")
        self.assertEqual(["A"], _read_json(self._hist_path()))
        _write_json(self._hist_path(), ["A", 2])
        self.assertEqual(["A"], self._slot_history("A"))
        self.assertTrue(self._hist_path().startswith(save_manager.get_session_dir()))

    def test_switching_save_never_leaks_history(self):
        save_manager.set_active_save_name("A")
        _write_json(self._hist_path(), ["A", "unsaved"])
        save_manager.set_active_save_name("B")
        self.assertEqual(["B"], _read_json(self._hist_path()))
        save_manager.set_active_save_name("A")
        self.assertEqual(["A"], _read_json(self._hist_path()))

    def test_load_refreshes_session_of_same_save(self):
        save_manager.set_active_save_name("A")
        _write_json(self._hist_path(), ["A", "unsaved"])
        save_manager.load_game("A")
        self.assertEqual(["A"], _read_json(self._hist_path()))

    def test_new_career_name_starts_with_empty_session(self):
        save_manager.set_active_save_name("A")
        save_manager.set_active_save_name("Brand_New")
        self.assertFalse(os.path.exists(self._hist_path()))

    def test_saves_list_skips_session_folder(self):
        save_manager.set_active_save_name("A")
        names = [m["save_name"] for m in save_manager.get_all_saves_metadata()]
        self.assertEqual(["A", "B"], sorted(names))

    def test_rename_active_save_keeps_session(self):
        save_manager.set_active_save_name("A")
        _write_json(self._hist_path(), ["A", "unsaved"])
        save_manager.rename_save("A", "Renamed")
        save_manager.set_active_save_name("Renamed")
        self.assertEqual(["A", "unsaved"], _read_json(self._hist_path()))

    def test_delete_active_save_empties_session(self):
        save_manager.set_active_save_name("A")
        _write_json(self._hist_path(), ["A", "unsaved"])
        save_manager.delete_save("A")
        self.assertFalse(os.path.exists(save_manager.get_session_dir()))


if __name__ == "__main__":
    unittest.main()
