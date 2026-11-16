"""core/save_store: a slot commit is all or nothing and keeps the replaced files as the one backup."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import save_store


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class SaveStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.slot = os.path.join(self.root, "slot")
        _write(os.path.join(self.slot, "a.json"), "1")
        _write(os.path.join(self.slot, "b.json"), "1")

    def _src(self, name, text):
        path = os.path.join(self.root, "src", name)
        _write(path, text)
        return path

    def _live(self, name):
        return _read(os.path.join(self.slot, name))

    def _backup(self, name):
        return _read(os.path.join(self.slot, save_store.BACKUP_DIR, name))

    def test_commit_replaces_files_and_backs_up_old(self):
        save_store.commit(self.slot, {"a.json": self._src("a.json", "2")})
        self.assertEqual("2", self._live("a.json"))
        self.assertEqual("1", self._live("b.json"))
        self.assertEqual("1", self._backup("a.json"))
        self.assertFalse(os.path.exists(os.path.join(self.slot, save_store.PENDING_DIR)))

    def test_commit_keeps_the_source_file(self):
        src = self._src("a.json", "2")
        save_store.commit(self.slot, {"a.json": src})
        self.assertTrue(os.path.exists(src))

    def test_backup_holds_only_last_commit(self):
        save_store.commit(self.slot, {"a.json": self._src("a.json", "2")})
        save_store.commit(self.slot, {"b.json": self._src("b.json", "2")})
        self.assertEqual(["b.json"], os.listdir(os.path.join(self.slot, save_store.BACKUP_DIR)))
        self.assertTrue(save_store.restore_backup(self.slot))
        self.assertEqual("2", self._live("a.json"))
        self.assertEqual("1", self._live("b.json"))

    def test_restore_backup_without_backup(self):
        self.assertFalse(save_store.restore_backup(self.slot))

    def test_crash_before_marker_keeps_previous_save(self):
        _write(os.path.join(self.slot, save_store.PENDING_DIR, "a.json"), "2")
        self.assertFalse(save_store.roll_forward(self.slot))
        self.assertEqual("1", self._live("a.json"))
        self.assertFalse(os.path.exists(os.path.join(self.slot, save_store.PENDING_DIR)))

    def test_crash_after_marker_rolls_forward_at_every_step(self):
        files = {"a.json": "2", "b.json": "2", "c.json": "new"}
        real_move = save_store._move
        for k in range(0, 12):
            with self.subTest(interrupt_after=k):
                slot = os.path.join(self.root, f"slot{k}")
                _write(os.path.join(slot, "a.json"), "1")
                _write(os.path.join(slot, "b.json"), "1")
                srcs = {n: self._src(f"{k}_{n}", t) for n, t in files.items()}
                calls = {"n": 0}

                def flaky(src, dst):
                    if calls["n"] >= k:
                        raise OSError("killed")
                    calls["n"] += 1
                    real_move(src, dst)

                with mock.patch.object(save_store, "_move", side_effect=flaky):
                    try:
                        save_store.commit(slot, srcs)
                        finished = True
                    except OSError:
                        finished = False
                marker_written = os.path.exists(
                    os.path.join(slot, save_store.PENDING_DIR, save_store.COMMIT_MARKER))
                save_store.roll_forward(slot)
                if finished or marker_written:
                    for name, text in files.items():
                        self.assertEqual(text, _read(os.path.join(slot, name)), (k, name))
                    bdir = os.path.join(slot, save_store.BACKUP_DIR)
                    self.assertEqual("1", _read(os.path.join(bdir, "a.json")))
                    self.assertEqual("1", _read(os.path.join(bdir, "b.json")))
                else:  # killed before the commit point: the previous save, untouched
                    self.assertEqual("1", _read(os.path.join(slot, "a.json")))
                    self.assertEqual("1", _read(os.path.join(slot, "b.json")))
                    self.assertFalse(os.path.exists(os.path.join(slot, "c.json")))
                self.assertFalse(os.path.exists(os.path.join(slot, save_store.PENDING_DIR)))
                self.assertFalse(os.path.exists(os.path.join(slot, save_store.BACKUP_NEW_DIR)))

    def test_commit_into_empty_slot(self):
        slot = os.path.join(self.root, "fresh")
        save_store.commit(slot, {"a.json": self._src("x.json", "9")})
        self.assertEqual("9", _read(os.path.join(slot, "a.json")))

    def test_file_digest(self):
        self.assertIsNone(save_store.file_digest(os.path.join(self.root, "missing")))
        self.assertEqual(save_store.file_digest(os.path.join(self.slot, "a.json")),
                         save_store.file_digest(os.path.join(self.slot, "b.json")))


if __name__ == "__main__":
    unittest.main()
