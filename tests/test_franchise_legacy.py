"""Franchise legacy: retired jerseys are kept in the save, names come from the save, not from player ids."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import franchise_legacy

TEAM = "Toronto Northmen"


def legend_seasons(name="Lazlo Halvorsen", team=TEAM, count=6):
    return [{"stagione": n, "squadra": team, "nome": name, "gp": 70, "pts": 2000, "reb": 500, "ast": 400,
             "is_champion": False, "premi": []} for n in range(1, count + 1)]


class FranchiseLegacyFilesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        patcher = mock.patch.object(franchise_legacy, "get_historical_file_path",
                                    lambda name: os.path.join(self.dir, name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)
        # No sqlite: point BASE_DIR at the temp dir so data/nba_sim.db is absent.
        base = mock.patch.object(franchise_legacy, "BASE_DIR", self.dir)
        base.start()
        self.addCleanup(base.stop)

    def write(self, name, data):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as f:
            return json.load(f)

    def hof(self, name="Lazlo Halvorsen"):
        self.write("hall_of_fame.json", {"classes": [{"stagione_elezione": 7, "inductees": [{"nome": name}]}]})

    def test_new_jersey_saved_next_to_old_ones(self):
        self.write("player_careers.json", {"lazlo-halvorsen": legend_seasons()})
        self.hof()
        self.write("franchise_records.json", {"single_game_records": {}, "retired_jerseys": {
            TEAM: [{"number": "15", "player": "Benedikt Iverley", "era": "Seasons 1-8", "role": "Legend"}]}})
        franchise_legacy.get_franchise_retired_jerseys(TEAM)
        self.assertEqual(len(self.read("franchise_records.json")["retired_jerseys"][TEAM]), 2)

    def test_retired_jersey_uses_saved_name(self):
        self.write("player_careers.json", {"lazlo-halvorsen": legend_seasons()})
        self.hof()
        jerseys = franchise_legacy.get_franchise_retired_jerseys(TEAM)
        self.assertEqual([j["player"] for j in jerseys], ["Lazlo Halvorsen"])

    def test_old_id_cased_jersey_not_duplicated(self):
        self.write("player_careers.json", {"lazlo-halvorsen": legend_seasons()})
        self.hof()
        self.write("franchise_records.json", {"single_game_records": {}, "retired_jerseys": {
            TEAM: [{"number": "23", "player": "Lazlo Halvorsen", "era": "Seasons 1-6", "role": "Hall of Fame Icon"}]}})
        self.assertEqual(len(franchise_legacy.get_franchise_retired_jerseys(TEAM)), 1)

    def test_franchise_leaders_use_saved_name(self):
        self.write("player_careers.json", {"lazlo-halvorsen": legend_seasons()})
        leaders = franchise_legacy.get_franchise_all_time_leaders(TEAM)
        self.assertEqual(leaders["points"][0]["name"], "Lazlo Halvorsen")

    def test_season_records_use_saved_name(self):
        self.write("player_careers.json", {"lazlo-halvorsen": legend_seasons()})
        _, season = franchise_legacy.get_franchise_records(TEAM)
        self.assertEqual(season["points"]["player"], "Lazlo Halvorsen")


if __name__ == "__main__":
    unittest.main()
