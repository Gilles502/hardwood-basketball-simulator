"""Trophy Room payload: years instead of "Season N", English labels, finals opponents, records reconciled."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.trophy_room_view import franchise_list, trophy_room_view

TEAM = "Toronto Northmen"


def standing(team, wins, rnd):
    return {"team": team, "wins": wins, "losses": 82 - wins, "conf_seed": 1, "playoff_round": rnd}


def history_season(number, champion, runner_up, team_round=None, team_wins=60):
    rows = [standing(champion, 63, "Campione NBA 🏆"), standing(runner_up, 58, "Finali NBA")]
    if team_round:
        rows.append(standing(TEAM, team_wins, team_round))
    return {"stagione": number, "anno": 2001 + number, "campione": champion, "standings": rows}


def legacy(**over):
    base = {
        "team_name": TEAM, "abbreviation": "TOR", "arena": "Northern Lights Arena", "city": "Toronto, ON",
        "established": 1995, "colors": {"primary": "#CE1141", "secondary": "#000000"},
        "banners": [], "trophy_cabinet": {"larry_obrien": 0, "finals_mvp": [], "mvp": [], "dpoy": [], "roy": [],
                                          "sixth_man": []},
        "retired_jerseys": [], "all_time_leaders": {}, "single_game_records": {}, "single_season_records": {},
        "standings_history": [],
    }
    base.update(over)
    return base


def team_season(number, wins, rnd):
    return {"season": number, "year": 2001 + number, "wins": wins, "losses": 82 - wins, "conf_seed": 2,
            "playoff_round": rnd, "is_champion": rnd.startswith("Campione")}


class TrophyRoomViewTest(unittest.TestCase):
    def test_banner_has_year_and_runner_up(self):
        lg = legacy(banners=[{"year": "Season 5", "finals_mvp": "Ivo Corrigan", "opponent": "Playoff"}])
        view = trophy_room_view(lg, [history_season(5, TEAM, "San Antonio Vaqueros")], {}, None, None)
        self.assertEqual(view["banners"], [{"season": 5, "year": 2006, "finals_mvp": "Ivo Corrigan",
                                            "runner_up": "San Antonio Vaqueros", "wins": 63, "losses": 19}])
        self.assertEqual(view["cabinet"]["titles"], [{"season": 5, "year": 2006}])

    def test_banner_without_history_row(self):
        lg = legacy(banners=[{"year": "Season 3", "finals_mvp": "N/A"}])
        banner = trophy_room_view(lg, [], {}, None, 2002)["banners"][0]
        self.assertEqual((banner["year"], banner["runner_up"], banner["finals_mvp"]), (2004, None, None))

    def test_lost_finals_listed(self):
        hist = [history_season(3, "Detroit Dynamos", TEAM)]
        self.assertEqual(trophy_room_view(legacy(), hist, {}, None, None)["cabinet"]["lost_finals"],
                         [{"season": 3, "year": 2004, "winner": "Detroit Dynamos"}])

    def test_cabinet_awards_have_years(self):
        cab = {"larry_obrien": 0, "finals_mvp": [], "mvp": [{"player": "Jalon Jarrow", "year": "Season 15"}],
               "dpoy": [], "roy": [], "sixth_man": []}
        view = trophy_room_view(legacy(trophy_cabinet=cab), [], {}, None, 2002)
        self.assertEqual(view["cabinet"]["mvp"], [{"player": "Jalon Jarrow", "season": 15, "year": 2016}])

    def test_franchise_record_takes_league_record(self):
        lg = legacy(single_game_records={"rebounds": {"value": 29, "player": "Soren Harcourt", "opponent": "Minnesota",
                                                      "year": "Season 15"}})
        league = {"rebounds_single_game": {"value": 32, "player_name": "Soren Harcourt", "team_name": TEAM,
                                           "opponent_name": "Chicago Gales", "season": 14}}
        rows = trophy_room_view(lg, [], league, None, 2002)["records"]["single_game"]
        self.assertEqual(rows, [{"stat": "rebounds", "value": 32, "player": "Soren Harcourt", "opponent": "Chicago Gales",
                                 "season": 14, "year": 2015}])

    def test_other_team_league_record_ignored(self):
        lg = legacy(single_game_records={"points": {"value": 58, "player": "Zane Castellane", "opponent": "MIN",
                                                    "year": "Season 23"}})
        league = {"points_single_game": {"value": 67, "player_name": "Yusuf Grisby", "team_name": "Orlando Citrus",
                                         "opponent_name": "Portland", "season": 2}}
        rows = trophy_room_view(lg, [], league, None, 2002)["records"]["single_game"]
        self.assertEqual((rows[0]["value"], rows[0]["player"]), (58, "Zane Castellane"))

    def test_placeholders_dropped(self):
        lg = legacy(single_game_records={"points": {"value": 0, "player": "Waiting for games", "opponent": "-",
                                                    "year": "-"}},
                    single_season_records={"three_pointers": {"value": 0, "player": "In progress", "year": "-"},
                                           "ppg": {"value": 33.1, "player": "Kiran Everly", "year": "Season 20"}})
        records = trophy_room_view(lg, [], {}, None, 2002)["records"]
        self.assertEqual(records["single_game"], [])
        self.assertEqual(records["single_season"], [{"stat": "ppg", "value": 33.1, "player": "Kiran Everly",
                                                     "season": 20, "year": 2021}])

    def test_jerseys_years_and_order(self):
        lg = legacy(retired_jerseys=[{"number": "60", "player": "Ivo Corrigan", "era": "Seasons 2-7", "role": "x"},
                                     {"number": "79", "player": "Jalon Jarrow", "era": "Seasons 2-20", "role": "x"},
                                     {"number": "11", "player": "One Year", "era": "Season 4", "role": "x"}])
        jerseys = trophy_room_view(lg, [], {}, None, 2002)["retired_jerseys"]
        self.assertEqual(jerseys[0], {"number": "79", "player": "Jalon Jarrow", "first_year": 2003, "last_year": 2021})
        self.assertEqual(jerseys[2], {"number": "11", "player": "One Year", "first_year": 2005, "last_year": 2005})

    def test_leaders_years_top_n_and_zero_dropped(self):
        rows = [{"name": f"P{i}", "value": 100 - i, "era": "Seasons 1-3, Season 5"} for i in range(15)]
        rows.append({"name": "Zero", "value": 0, "era": "Current Roster"})
        view = trophy_room_view(legacy(all_time_leaders={"points": rows}), [], {}, None, 2002)
        points = view["leaders"]["points"]
        self.assertEqual(len(points), 10)
        self.assertEqual(points[0], {"name": "P0", "value": 100, "first_year": 2002, "last_year": 2006})

    def test_seasons_english_and_gap(self):
        lg = legacy(standings_history=[team_season(21, 62, "Finali NBA"), team_season(22, 64, "Playoffs"),
                                       team_season(24, 57, "Campione NBA 🏆")])
        seasons = trophy_room_view(lg, [], {}, None, 2002)["seasons"]
        self.assertEqual([s.get("result") for s in seasons], ["Lost Finals", "Playoffs", None, "Champions"])
        self.assertEqual(seasons[2], {"season": 23, "year": 2024, "missing": True})

    def test_standings_history_kept_for_team_popup(self):
        row = dict(team_season(4, 63, "Campione NBA 🏆"), ppg=110.2, league_rank=2)
        kept = trophy_room_view(legacy(standings_history=[row]), [], {}, None, None)["standings_history"]
        self.assertEqual(kept, [dict(row, playoff_round="Champions")])

    def test_summary_counts(self):
        lg = legacy(standings_history=[team_season(1, 21, "Lottery"), team_season(2, 42, "Playoffs"),
                                       team_season(3, 70, "Finali NBA"), team_season(4, 63, "Campione NBA 🏆")],
                    banners=[{"year": "Season 4", "finals_mvp": "X"}])
        summary = trophy_room_view(lg, [], {}, None, 2002)["summary"]
        self.assertEqual(summary, {"titles": 1, "finals": 2, "playoff_seasons": 3, "wins": 196, "losses": 132,
                                   "win_pct": 0.598})

    def test_user_team_flag(self):
        self.assertTrue(trophy_room_view(legacy(), [], {}, TEAM, None)["is_user_team"])
        self.assertFalse(trophy_room_view(legacy(), [], {}, "Other", None)["is_user_team"])

    def test_empty_legacy(self):
        view = trophy_room_view(legacy(), [], {}, None, None)
        self.assertEqual((view["banners"], view["retired_jerseys"], view["seasons"]), ([], [], []))
        self.assertEqual(view["records"], {"single_game": [], "single_season": []})
        self.assertEqual(view["summary"]["win_pct"], 0.0)


class FranchiseListTest(unittest.TestCase):
    def test_user_first_then_titles_then_name(self):
        teams = [{"team_name": "B", "championships_count": 1}, {"team_name": "A", "championships_count": 1},
                 {"team_name": "C", "championships_count": 4}, {"team_name": "Mine", "championships_count": 0}]
        self.assertEqual([t["team_name"] for t in franchise_list(teams, "Mine")], ["Mine", "C", "A", "B"])
        self.assertTrue(franchise_list(teams, "Mine")[0]["is_user_team"])


if __name__ == "__main__":
    unittest.main()
