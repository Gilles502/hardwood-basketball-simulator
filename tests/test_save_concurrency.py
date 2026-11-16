"""One save at a time, autosave after the key game moments, and a close that waits for running work."""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server


class SaveLockTests(unittest.TestCase):
    def test_saves_never_overlap(self):
        events = []

        def slow_save(*_a, **_k):
            events.append("enter")
            time.sleep(0.05)
            events.append("exit")

        with mock.patch.object(server, "save_game", side_effect=slow_save), \
                mock.patch.object(server, "SIMULATION_TOURNAMENT", mock.Mock()):
            threads = [threading.Thread(target=server.save_current_game, args=("slot",)) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(["enter", "exit"] * 3, events)


class IdleWaitTests(unittest.TestCase):
    def test_wait_for_idle_follows_running_requests(self):
        server._request_started()
        self.assertFalse(server.wait_for_idle(0.05))
        server._request_finished()
        self.assertTrue(server.wait_for_idle(0.05))


class KeyMomentAutosaveTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(server, "auto_save_active_game")
        self.autosave = p.start()
        self.addCleanup(p.stop)

    def test_key_routes_are_listed(self):
        for path in ("/api/offseason/hub_step", "/api/offseason/free_agency/simulate_day",
                     "/api/execute-user-trade", "/api/simula_playoff_turno"):
            self.assertIn(path, server.AUTOSAVE_AFTER_ROUTES)

    def _after(self, path, status, method="POST"):
        with server.app.test_request_context(path, method=method):
            server._autosave_after_key_route(server.app.response_class("{}", status=status))

    def test_successful_key_route_autosaves(self):
        self._after("/api/offseason/hub_step", 200)
        self.autosave.assert_called_once()

    def test_failed_key_route_does_not_autosave(self):
        self._after("/api/offseason/hub_step", 400)
        self.autosave.assert_not_called()

    def test_other_routes_do_not_autosave(self):
        self._after("/api/trade-finder", 200)
        self._after("/api/offseason/hub_step", 200, method="GET")
        self.autosave.assert_not_called()


if __name__ == "__main__":
    unittest.main()
