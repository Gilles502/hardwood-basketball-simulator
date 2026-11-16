"""save_game/load_game: versioned, all-or-nothing, history committed with the state, backup fallback."""
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import save_manager, save_store


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class SaveTransactionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = tmp.name
        for p in (mock.patch.object(save_manager, "BASE_DIR", tmp.name),
                  mock.patch.object(save_manager, "SAVES_DIR", os.path.join(tmp.name, "saves")),
                  mock.patch.object(save_manager, "ACTIVE_SAVE_NAME", None),
                  mock.patch.object(save_manager, "_SESSION_OWNER", None)):
            p.start()
            self.addCleanup(p.stop)
        self.db = os.path.join(tmp.name, "data", "nba_sim.db")
        os.makedirs(os.path.dirname(self.db))
        self.tournament = SimpleNamespace(squadra_giocatore=None, season_number=3)
        save_manager.set_active_save_name("slot")

    def _save(self, day):
        """One save where state, DB and history all say `day`."""
        with open(self.db, "w", encoding="utf-8") as f:
            f.write(f"db{day}")
        _write_json(save_manager.get_historical_file_path("league_history.json"), [day])
        with mock.patch.object(save_manager, "serialize_tournament_state", return_value={"day": day}):
            return save_manager.save_game("slot", self.tournament)

    def _loaded(self):
        loaded = save_manager.load_game("slot")
        with open(self.db, encoding="utf-8") as f:
            db = f.read()
        hist = _read_json(save_manager.get_historical_file_path("league_history.json"))
        return loaded["state_data"].get("day"), db, hist, loaded

    def _slot(self, name=""):
        return os.path.join(save_manager.get_save_path("slot"), name)

    def test_save_then_load_round_trip_has_version_and_same_state(self):
        meta = self._save(1)
        self.assertEqual(save_store.SAVE_VERSION, meta["save_version"])
        day, db, hist, loaded = self._loaded()
        self.assertEqual((1, "db1", [1]), (day, db, hist))
        self.assertFalse(loaded.get("recovered_from_backup"))

    def test_state_file_is_compact(self):
        self._save(1)
        with open(self._slot("tournament_state.json"), encoding="utf-8") as f:
            self.assertNotIn("\n", f.read())

    def test_kill_at_every_step_never_mixes(self):
        real_move = save_store._move
        for k in range(0, 15):
            with self.subTest(interrupt_after=k):
                self._save(1)
                calls = {"n": 0}

                def flaky(src, dst):
                    if calls["n"] >= k:
                        raise OSError("killed")
                    calls["n"] += 1
                    real_move(src, dst)

                with mock.patch.object(save_store, "_move", side_effect=flaky):
                    try:
                        self._save(2)
                    except (OSError, save_manager.SaveError):
                        pass
                day, db, hist, _ = self._loaded()
                self.assertIn(day, (1, 2))
                self.assertEqual((f"db{day}", [day]), (db, hist), f"mixed save after {k} moves")

    def test_unsaved_history_is_not_in_the_slot(self):
        self._save(1)
        _write_json(save_manager.get_historical_file_path("league_history.json"), [1, "unsaved"])
        self.assertEqual([1], _read_json(self._slot("league_history.json")))

    def test_unchanged_history_not_rewritten(self):
        self._save(1)
        hof = self._slot("hall_of_fame.json")
        before = os.stat(hof).st_mtime_ns
        os.utime(hof, ns=(before - 10**9, before - 10**9))
        before = os.stat(hof).st_mtime_ns
        self._save(2)
        self.assertEqual(before, os.stat(hof).st_mtime_ns)
        self.assertEqual([2], _read_json(self._slot("league_history.json")))

    def test_newer_version_refused_and_flagged_in_list(self):
        self._save(1)
        meta = _read_json(self._slot("save_metadata.json"))
        meta["save_version"] = save_store.SAVE_VERSION + 1
        _write_json(self._slot("save_metadata.json"), meta)
        with self.assertRaises(save_manager.SaveError) as cm:
            save_manager.load_game("slot")
        self.assertIn("newer version", str(cm.exception))
        listed = [m for m in save_manager.get_all_saves_metadata() if m["save_name"] == "slot"]
        self.assertTrue(listed[0]["incompatible"])

    def test_corrupt_state_falls_back_to_backup(self):
        self._save(1)
        self._save(2)
        with open(self._slot("tournament_state.json"), "w", encoding="utf-8") as f:
            f.write("{")
        day, db, hist, loaded = self._loaded()
        self.assertEqual((1, "db1", [1]), (day, db, hist))
        self.assertTrue(loaded["recovered_from_backup"])

    def test_old_save_without_version_loads(self):
        slot = self._slot()
        os.makedirs(slot, exist_ok=True)
        _write_json(os.path.join(slot, "save_metadata.json"), {"display_name": "slot", "season": 3})
        _write_json(os.path.join(slot, "tournament_state.json"), {"day": 7})
        _write_json(os.path.join(slot, "league_history.json"), ["old"])
        with open(self.db, "w", encoding="utf-8") as f:
            f.write("active")
        day, _db, hist, _ = self._loaded()
        self.assertEqual((7, ["old"]), (day, hist))


if __name__ == "__main__":
    unittest.main()
