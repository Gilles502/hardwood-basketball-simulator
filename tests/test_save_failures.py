"""Save/load must fail loudly: a half-written save must never look like a good one."""
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import save_manager


class SaveFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patches = [
            mock.patch.object(save_manager, "BASE_DIR", self.tmp.name),
            mock.patch.object(save_manager, "SAVES_DIR", os.path.join(self.tmp.name, "saves")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.tournament = SimpleNamespace(squadra_giocatore=None, season_number=3)

    def _state_path(self):
        return os.path.join(save_manager.get_save_path("slot"), "tournament_state.json")

    def _meta_path(self):
        return os.path.join(save_manager.get_save_path("slot"), "save_metadata.json")

    def _good_save(self):
        with mock.patch.object(save_manager, "serialize_tournament_state", return_value={"season": 3}):
            return save_manager.save_game("slot", self.tournament)

    def test_save_fails_loudly_when_state_serialization_raises(self):
        self._good_save()
        with open(self._state_path(), "rb") as f:
            before = f.read()
        with open(self._meta_path(), "rb") as f:
            meta_before = f.read()

        with mock.patch.object(save_manager, "serialize_tournament_state", side_effect=RuntimeError("boom")):
            with self.assertRaises(save_manager.SaveError):
                save_manager.save_game("slot", self.tournament)

        with open(self._state_path(), "rb") as f:
            self.assertEqual(before, f.read())
        with open(self._meta_path(), "rb") as f:
            self.assertEqual(meta_before, f.read(), "metadata must not advertise a failed save")

    def test_save_fails_loudly_when_state_write_raises(self):
        real_write = save_manager.atomic_write_json

        def failing_write(path, data, indent=4):
            if path.endswith("tournament_state.json"):
                raise OSError("disk full")
            return real_write(path, data, indent)

        with mock.patch.object(save_manager, "serialize_tournament_state", return_value={"season": 3}), \
                mock.patch.object(save_manager, "atomic_write_json", side_effect=failing_write):
            with self.assertRaises(save_manager.SaveError):
                save_manager.save_game("slot", self.tournament)
        self.assertFalse(os.path.exists(self._meta_path()))

    def test_load_raises_on_corrupt_state_file(self):
        self._good_save()
        with open(self._state_path(), "w", encoding="utf-8") as f:
            f.write("{")
        with self.assertRaises(save_manager.SaveError):
            save_manager.load_game("slot")

    def test_load_missing_state_file_is_a_legacy_save(self):
        self._good_save()
        os.remove(self._state_path())
        loaded = save_manager.load_game("slot")
        self.assertEqual({}, loaded["state_data"])

    def test_roundtrip_returns_saved_state(self):
        self._good_save()
        loaded = save_manager.load_game("slot")
        self.assertEqual({"season": 3}, loaded["state_data"])


if __name__ == "__main__":
    unittest.main()
