"""Flask serves the built frontend (SPA fallback) and one start-up function prepares the game state."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

import server


class TestSpaServing(unittest.TestCase):
    def setUp(self):
        self.dist = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dist, True)
        os.makedirs(os.path.join(self.dist, "assets"))
        with open(os.path.join(self.dist, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("<html>app</html>")
        with open(os.path.join(self.dist, "assets", "app.js"), "w", encoding="utf-8") as fh:
            fh.write("console.log(1)")
        p = mock.patch.object(server, "FRONTEND_DIST", self.dist)
        p.start()
        self.addCleanup(p.stop)
        self.client = server.app.test_client()

    def test_root_serves_index(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"app", r.data)
        r.close()

    def test_client_route_falls_back_to_index(self):
        r = self.client.get("/team/roster")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"app", r.data)
        r.close()

    def test_asset_is_served(self):
        r = self.client.get("/assets/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, b"console.log(1)")
        r.close()

    def test_unknown_api_is_json_404(self):
        r = self.client.get("/api/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Not found")

    def test_existing_api_route_still_wins(self):
        with mock.patch.object(server, "get_all_saves_metadata", return_value=[]):
            r = self.client.get("/api/saves")
        self.assertEqual(r.status_code, 200)
        self.assertIn("saves", r.get_json())

    def test_missing_build_message(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        with mock.patch.object(server, "FRONTEND_DIST", empty):
            r = self.client.get("/")
        self.assertEqual(r.status_code, 404)
        self.assertIn(b"npm run build", r.data)


class TestInitGameState(unittest.TestCase):
    def setUp(self):
        names = ("SIMULATION_TOURNAMENT", "LEAGUE_STATE", "ACTIVE_SAVE_NAME")
        saved = {n: getattr(server, n, None) for n in names}

        def restore():
            for n, v in saved.items():
                setattr(server, n, v)
        self.addCleanup(restore)

    def test_init_game_state_without_saves_seeds_from_active_league(self):
        sentinel = mock.Mock(season_number=1, squadre=[])
        with mock.patch.object(server, "migrate_legacy_files", return_value=None), \
                mock.patch.object(server, "get_all_saves_metadata", return_value=[]), \
                mock.patch.object(server.league_catalog, "ensure_active_league_db",
                                  return_value="built/fictional_2002.db"), \
                mock.patch.object(server.shutil, "copyfile") as copyfile, \
                mock.patch.object(server.simulation_logic, "setup_simulation", return_value=sentinel):
            server.init_game_state()
        copyfile.assert_called_once_with("built/fictional_2002.db", os.path.join("data", "nba_sim.db"))
        self.assertIs(server.SIMULATION_TOURNAMENT, sentinel)
        self.assertEqual(server.LEAGUE_STATE, "PRE_SEASON")


if __name__ == "__main__":
    unittest.main()
