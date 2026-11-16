"""League Records and All-Time Leaders payloads: saved names, real years, top N, no Flask."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import records_view
from core.config import CONFIG
from core.records_view import career_leaders_view, league_records_view

YEARS = {n: 2001 + n for n in range(1, 30)}


def old_season(n, team, name, ppg=20.0, gp=70, premi=(), champ=False, rpg=5.0, apg=4.0, spg=1.0, bpg=0.5):
    return {"stagione": n, "squadra": team, "nome": name, "gp": gp, "is_champion": champ, "premi": list(premi),
            "stats_rs": {"ppg": ppg, "rpg": rpg, "apg": apg, "spg": spg, "bpg": bpg}}


def new_season(n, team, name, pts, gp=80, premi=()):
    return {"stagione": n, "squadra": team, "nome": name, "gp": gp, "pts": pts, "reb": 400, "ast": 300, "stl": 80,
            "blk": 40, "premi": list(premi), "is_champion": False}


class CareerLeadersTest(unittest.TestCase):
    def test_names_from_nome(self):
        view = career_leaders_view({"lazlo-halvorsen": [old_season(1, "Cavs", "Lazlo Halvorsen")]}, None, YEARS, None)
        self.assertEqual(view["boards"]["points"][0]["name"], "Lazlo Halvorsen")

    def test_totals_old_and_new_format(self):
        careers = {"a": [old_season(1, "X", "A", ppg=20.0, gp=50), new_season(2, "X", "A", pts=1500)]}
        row = career_leaders_view(careers, None, YEARS, None)["boards"]["points"][0]
        self.assertEqual((row["value"], row["games"], row["seasons"], row["per_game"]), (2500, 130, 2, 19.2))

    def test_years_and_last_team(self):
        careers = {"a": [old_season(3, "Hawks", "A"), old_season(7, "Spurs", "A")]}
        row = career_leaders_view(careers, None, YEARS, None)["boards"]["points"][0]
        self.assertEqual((row["first_year"], row["last_year"], row["last_team"]), (2004, 2008, "Spurs"))

    def test_top_n_and_zero_dropped(self):
        careers = {f"p{i}": [old_season(1, "X", f"P{i}", ppg=10 + i)] for i in range(5)}
        with mock.patch.object(records_view, "CONFIG", mock.Mock(HISTORY=mock.Mock(LEADERS_TOP_N=3))):
            view = career_leaders_view(careers, None, YEARS, None)
        self.assertEqual([r["name"] for r in view["boards"]["points"]], ["P4", "P3", "P2"])
        self.assertEqual([r["rank"] for r in view["boards"]["points"]], [1, 2, 3])
        self.assertEqual(view["boards"]["mvp"], [])

    def test_honours_counted(self):
        careers = {"a": [old_season(1, "X", "A", premi=["MVP", "All-Star Starter", "All-NBA 1st"], champ=True),
                         old_season(2, "X", "A", premi=["Finals MVP", "All-Star", "DPOY", "All-NBA 3rd"])]}
        boards = career_leaders_view(careers, None, YEARS, None)["boards"]
        values = {k: boards[k][0]["value"] for k in ("titles", "mvp", "finals_mvp", "dpoy", "all_star", "all_league")}
        self.assertEqual(values, {"titles": 1, "mvp": 1, "finals_mvp": 1, "dpoy": 1, "all_star": 2,
                                  "all_league": 2})
        self.assertNotIn("per_game", boards["mvp"][0])

    def test_card_and_user_flag(self):
        careers = {"a": [old_season(1, "Raptors", "A", ppg=30.0), old_season(2, "Spurs", "A", ppg=20.0)]}
        row = career_leaders_view(careers, "Raptors", YEARS, None)["boards"]["points"][0]
        self.assertTrue(row["played_for_user"])
        self.assertEqual((row["card"]["ppg"], row["card"]["peak_ppg"]), (25.0, 30.0))

    def test_empty(self):
        view = career_leaders_view({}, None, {}, None)
        self.assertEqual(view["total_players"], 0)
        self.assertTrue(all(rows == [] for rows in view["boards"].values()))


class LeagueRecordsTest(unittest.TestCase):
    def test_single_game_year_not_date(self):
        records = {"points_single_game": {"value": 67, "player_name": "Yusuf Grisby", "team_name": "Orlando Citrus",
                                          "opponent_name": "Portland", "season": 2, "date": "2026-10-11"}}
        row = league_records_view(records, {}, "Orlando Citrus", YEARS, None)["single_game"][0]
        self.assertEqual(row, {"stat": "points", "value": 67, "player": "Yusuf Grisby", "team": "Orlando Citrus",
                               "opponent": "Portland", "season": 2, "year": 2003, "is_user_team": True})

    def test_single_season_min_games(self):
        careers = {"a": [old_season(4, "X", "Short", ppg=40.0, gp=49)],
                   "b": [old_season(5, "Y", "Long", ppg=30.04, gp=50)]}
        rows = league_records_view({}, careers, None, YEARS, None)["single_season"]
        ppg = next(r for r in rows if r["stat"] == "ppg")
        self.assertEqual(ppg, {"stat": "ppg", "value": 30.0, "player": "Long", "team": "Y", "season": 5,
                               "year": 2006, "is_user_team": False})
        self.assertEqual([r["stat"] for r in rows], ["ppg", "rpg", "apg", "spg", "bpg"])

    def test_single_season_new_format(self):
        rows = league_records_view({}, {"a": [new_season(1, "X", "A", pts=2400, gp=80)]}, None, YEARS, None)
        self.assertEqual(rows["single_season"][0]["value"], 30.0)

    def test_triple_doubles(self):
        records = {"triple_doubles_leaders": [{"player_name": "Russ", "count": 274}, {"player_name": "Luka",
                                                                                       "count": 125}]}
        careers = {"russ": [old_season(1, "Raptors", "Russ")]}
        rows = league_records_view(records, careers, "Raptors", YEARS, None)["triple_doubles"]
        self.assertEqual(rows, [{"player": "Russ", "count": 274, "played_for_user": True},
                                {"player": "Luka", "count": 125, "played_for_user": False}])

    def test_empty(self):
        self.assertEqual(league_records_view({}, {}, None, {}, None),
                         {"single_game": [], "single_season": [], "triple_doubles": []})


if __name__ == "__main__":
    unittest.main()
