"""Tests for core.paths: the game root (read-only) and the user root (writable)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

from core import paths

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(paths.__file__)))


def _env_without_user_dir():
    env = dict(os.environ)
    env.pop("HARDWOOD_USER_DIR", None)
    return env


class TestPaths(unittest.TestCase):
    def test_dev_roots_are_the_project_folder(self):
        with mock.patch.dict(os.environ, _env_without_user_dir(), clear=True), \
                mock.patch.object(sys, "frozen", False, create=True):
            self.assertFalse(paths.is_frozen())
            self.assertEqual(os.path.normcase(paths.game_root()), os.path.normcase(PROJECT_DIR))
            self.assertEqual(os.path.normcase(paths.user_root()), os.path.normcase(PROJECT_DIR))

    def test_env_overrides_user_root(self):
        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HARDWOOD_USER_DIR": tmp}):
            self.assertEqual(paths.user_root(), tmp)
            self.assertEqual(os.path.normcase(paths.game_root()), os.path.normcase(PROJECT_DIR))
            self.assertEqual(paths.user_path("saves", "x"), os.path.join(tmp, "saves", "x"))

    def test_frozen_roots(self):
        tmp_a, tmp_b = tempfile.mkdtemp(), tempfile.mkdtemp()
        with mock.patch.dict(os.environ, _env_without_user_dir(), clear=True), \
                mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "_MEIPASS", tmp_a, create=True), \
                mock.patch.object(paths, "documents_dir", return_value=tmp_b):
            self.assertTrue(paths.is_frozen())
            self.assertEqual(paths.game_root(), tmp_a)
            self.assertEqual(paths.user_root(), os.path.join(tmp_b, "Hardwood"))
            self.assertEqual(paths.game_path("data", "a.db"), os.path.join(tmp_a, "data", "a.db"))

    def test_frozen_root_moves_the_old_nbasim_folder(self):
        docs = tempfile.mkdtemp()
        os.makedirs(os.path.join(docs, "NBASIM", "saves", "Washington"))
        self.assertEqual(paths._frozen_user_root(docs), os.path.join(docs, "Hardwood"))
        self.assertTrue(os.path.isdir(os.path.join(docs, "Hardwood", "saves", "Washington")))
        self.assertFalse(os.path.exists(os.path.join(docs, "NBASIM")))

    def test_frozen_root_keeps_the_old_folder_when_it_cannot_move(self):
        docs = tempfile.mkdtemp()
        os.makedirs(os.path.join(docs, "NBASIM"))
        with mock.patch.object(paths.os, "rename", side_effect=OSError("in use")):
            self.assertEqual(paths._frozen_user_root(docs), os.path.join(docs, "NBASIM"))

    def test_frozen_root_never_merges_into_an_existing_folder(self):
        docs = tempfile.mkdtemp()
        os.makedirs(os.path.join(docs, "NBASIM"))
        os.makedirs(os.path.join(docs, "Hardwood"))
        self.assertEqual(paths._frozen_user_root(docs), os.path.join(docs, "Hardwood"))
        self.assertTrue(os.path.isdir(os.path.join(docs, "NBASIM")))

    def test_documents_fallback(self):
        home = os.path.expanduser("~")
        with mock.patch.object(paths, "_known_documents_folder", side_effect=OSError("no shell")):
            with mock.patch.object(paths.os.path, "isdir", return_value=True):
                self.assertEqual(paths.documents_dir(), os.path.join(home, "Documents"))
            with mock.patch.object(paths.os.path, "isdir", return_value=False):
                self.assertEqual(paths.documents_dir(), home)

    def test_ensure_user_dirs_creates_folders_only(self):
        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HARDWOOD_USER_DIR": tmp}):
            self.assertEqual(paths.ensure_user_dirs(), tmp)
        for folder in ("saves", os.path.join("data", "leagues"), "mods", "scratch", "logs"):
            self.assertTrue(os.path.isdir(os.path.join(tmp, folder)), folder)
        files = [f for _, _, names in os.walk(tmp) for f in names]
        self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()
