"""The packaged-build launcher: free port, one instance, safe std streams, autosave on close. No real window."""
import os
import shutil
import socket
import sys
import tempfile
import types
import unittest
from unittest import mock

import launcher


class LauncherCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.dict(os.environ, {"HARDWOOD_USER_DIR": self.tmp})
        p.start()
        self.addCleanup(p.stop)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)


class TestLauncherHelpers(LauncherCase):
    def test_free_port_is_bindable(self):
        port = launcher.find_free_port()
        self.assertNotEqual(port, 5000)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))

    def test_second_instance_is_refused(self):
        lock = os.path.join(self.tmp, "hardwood.lock")
        first = launcher.acquire_single_instance(lock)
        self.assertIsNotNone(first)
        self.assertIsNone(launcher.acquire_single_instance(lock))
        first.close()
        again = launcher.acquire_single_instance(lock)
        self.assertIsNotNone(again)
        again.close()

    def test_redirect_when_streams_are_none(self):
        log = os.path.join(self.tmp, "logs", "server.log")
        out, err = sys.stdout, sys.stderr
        try:
            sys.stdout = None
            sys.stderr = None
            launcher.redirect_std_streams(log)
            print("x", flush=True)
            sys.stdout.close()
            if sys.stderr is not sys.stdout:
                sys.stderr.close()
        finally:
            sys.stdout, sys.stderr = out, err
        with open(log, encoding="utf-8") as fh:
            self.assertIn("x", fh.read())

    def test_prepare_environment_chdirs_into_user_root(self):
        self.assertEqual(launcher.prepare_environment(), self.tmp)
        self.assertEqual(os.path.normcase(os.getcwd()), os.path.normcase(self.tmp))
        for folder in ("saves", os.path.join("data", "leagues"), "mods", "scratch", "logs"):
            self.assertTrue(os.path.isdir(os.path.join(self.tmp, folder)), folder)


class TestUnblockDownloadedFiles(unittest.TestCase):
    def test_removes_the_downloaded_mark_and_keeps_the_file(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "runtime"))
        dll = os.path.join(root, "runtime", "Python.Runtime.dll")
        with open(dll, "wb") as fh:
            fh.write(b"dll")
        try:
            with open(dll + ":Zone.Identifier", "w") as fh:
                fh.write("[ZoneTransfer]\nZoneId=3\n")
        except OSError:
            self.skipTest("file system without alternate data streams")
        with open(os.path.join(root, "plain.txt"), "w") as fh:
            fh.write("x")

        self.assertEqual(launcher.unblock_downloaded_files(root), 1)
        self.assertFalse(os.path.exists(dll + ":Zone.Identifier"))
        with open(dll, "rb") as fh:
            self.assertEqual(fh.read(), b"dll")
        self.assertEqual(launcher.unblock_downloaded_files(root), 0)


class TestWindowClose(LauncherCase):
    def test_close_autosaves_then_shuts_down(self):
        import server
        parent = mock.Mock()
        srv = parent.srv
        with mock.patch.object(server, "auto_save_active_game", parent.autosave):
            launcher.on_window_closed(srv)
        self.assertEqual([c[0] for c in parent.mock_calls], ["autosave", "srv.shutdown"])

    def test_close_still_shuts_down_when_save_fails(self):
        import server
        srv = mock.Mock()
        with mock.patch.object(server, "auto_save_active_game", side_effect=RuntimeError("disk")):
            launcher.on_window_closed(srv)
        srv.shutdown.assert_called_once()

    def test_close_does_not_hang_on_a_stuck_save(self):
        import server
        import threading
        import time
        from types import SimpleNamespace
        from core.config import Saves
        release = threading.Event()
        srv = mock.Mock()
        fast = SimpleNamespace(SAVES=Saves(CLOSE_WAIT_TIMEOUT_S=0.05, CLOSE_SAVE_TIMEOUT_S=0.1))
        with mock.patch.object(server, "auto_save_active_game", side_effect=lambda: release.wait(5)), \
                mock.patch("core.config.CONFIG", fast), \
                mock.patch.object(server, "wait_for_idle", return_value=False):
            start = time.perf_counter()
            launcher.on_window_closed(srv)
            elapsed = time.perf_counter() - start
        release.set()
        self.assertLess(elapsed, 2.0)
        srv.shutdown.assert_called_once()

    def test_close_waits_for_running_request_before_saving(self):
        import server
        parent = mock.Mock()
        parent.wait.return_value = True
        with mock.patch.object(server, "wait_for_idle", parent.wait), \
                mock.patch.object(server, "auto_save_active_game", parent.autosave):
            launcher.on_window_closed(parent.srv)
        self.assertEqual([c[0] for c in parent.mock_calls], ["wait", "autosave", "srv.shutdown"])


class TestMain(LauncherCase):
    def test_main_refuses_second_instance(self):
        held = launcher.acquire_single_instance(os.path.join(self.tmp, "hardwood.lock"))
        self.addCleanup(held.close)
        with mock.patch.object(launcher, "show_error") as show_error, \
                mock.patch.object(launcher, "start_server") as start_server:
            self.assertEqual(launcher.main([]), 1)
        show_error.assert_called_once_with("Hardwood Basketball Simulator is already running.")
        start_server.assert_not_called()

    def test_environment_set_before_server_import(self):
        parent = mock.Mock()
        parent.prepare_environment.return_value = self.tmp
        parent.wait_until_ready.return_value = True
        fake_webview = types.ModuleType("webview")
        fake_webview.create_window = parent.create_window
        fake_webview.start = parent.start
        with mock.patch.dict(sys.modules, {"webview": fake_webview}), \
                mock.patch.object(launcher, "prepare_environment", parent.prepare_environment), \
                mock.patch.object(launcher, "start_server", parent.start_server), \
                mock.patch.object(launcher, "wait_until_ready", parent.wait_until_ready), \
                mock.patch.object(launcher, "on_window_closed", parent.on_window_closed), \
                mock.patch.object(launcher, "redirect_std_streams"):
            self.assertEqual(launcher.main([]), 0)
        names = [c[0] for c in parent.mock_calls]
        self.assertLess(names.index("prepare_environment"), names.index("start_server"))
        self.assertLess(names.index("start"), names.index("on_window_closed"))


if __name__ == "__main__":
    unittest.main()
