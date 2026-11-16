"""History page views (championships, Hall of Fame) must not depend on Flask."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.history_view import (championship_history, hall_of_fame_view, parse_season, playoff_label, season_years,
                               year_for)

CHAMP = "Campione NBA 🏆"
FINALS = "Finali NBA"


def standing(team, rank, wins, conference="East", seed=1, rnd="Playoffs"):
    return {"team": team, "conference": conference, "conf_seed": seed, "league_rank": rank,
            "wins": wins, "losses": 82 - wins, "playoff_round": rnd}


def season(number, champion, runner_up="Memphis Blues", champ_rank=1, mvp="Luka", fmvp="Ben"):
    teams = [standing(f"Team {r}", r, 70 - r) for r in range(1, 12)]
    teams[champ_rank - 1] = standing(champion, champ_rank, 70 - champ_rank, "East", 3, CHAMP)
    runner_rank = 2 if champ_rank != 2 else 1
    teams[runner_rank - 1] = standing(runner_up, runner_rank, 70 - runner_rank, "West", 2, FINALS)
    return {"stagione": number, "anno": 2001 + number, "campione": champion, "mvp_finali": fmvp,
            "premi": {"mvp": mvp, "dpoy": "Draymond", "roy": "Cooper", "sesto_uomo": "Russ", "mip": "Jabari",
                      "all_nba_1st": ["A", "B", "C", "D", "E"], "all_nba_2nd": [], "all_nba_3rd": []},
            "standings": teams}


class ChampionshipHistoryTest(unittest.TestCase):
    def test_runner_up_seed_and_records(self):
        entry = championship_history([season(1, "Toronto Northmen")], None)[0]
        self.assertEqual(entry["champion"], {"team": "Toronto Northmen", "wins": 69, "losses": 13,
                                             "conference": "East", "seed": 3, "league_rank": 1})
        self.assertEqual(entry["runner_up"]["team"], "Memphis Blues")
        self.assertEqual(entry["runner_up"]["seed"], 2)
        self.assertEqual(entry["finals_mvp"], "Ben")
        self.assertEqual(entry["all_league"]["first"], ["A", "B", "C", "D", "E"])
        self.assertEqual(entry["awards"]["sixth_man"], "Russ")

    def test_missing_season_becomes_placeholder(self):
        out = championship_history([season(1, "X"), season(2, "X"), season(4, "X")], None)
        self.assertEqual([e["season"] for e in out], [4, 3, 2, 1])
        self.assertEqual(out[1], {"season": 3, "year": 2004, "missing": True})

    def test_na_awards_are_null(self):
        entry = championship_history([season(1, "X", mvp="N/A", fmvp="N/A")], None)[0]
        self.assertIsNone(entry["awards"]["mvp"])
        self.assertIsNone(entry["finals_mvp"])

    def test_champion_appended_below_top(self):
        entry = championship_history([season(1, "Toronto Northmen", champ_rank=9)], None)[0]
        rows = entry["top_standings"]
        self.assertEqual([r["rank"] for r in rows], [1, 2, 3, 9])
        self.assertEqual(rows[-1]["tag"], "champion")
        self.assertEqual(rows[1]["tag"], "finals")
        self.assertEqual(len(rows) - 1, CONFIG.HISTORY.TOP_STANDINGS)

    def test_title_number_and_run(self):
        out = championship_history([season(1, "X"), season(2, "Y"), season(3, "X"), season(4, "X")], None)
        by_season = {e["season"]: e for e in out}
        self.assertEqual(by_season[4]["franchise_title_no"], 3)
        self.assertEqual(by_season[4]["run"], 3)
        self.assertEqual(by_season[1]["run"], 1)
        self.assertEqual((by_season[4]["run_window"], by_season[1]["run_window"]), (CONFIG.HISTORY.RUN_WINDOW, 1))
        self.assertEqual(by_season[2]["franchise_title_no"], 1)

    def test_is_user_team(self):
        out = championship_history([season(1, "X"), season(2, "Y")], "Y")
        self.assertEqual([e["is_user_team"] for e in out], [True, False])


def inductee(name, score, titles=0, mvp=0, list_style=False):
    if list_style:
        highlights = ["Champion"]
    else:
        highlights = {"accolades": {"titoli": titles, "mvp": mvp, "finals_mvp": 0, "dpoy": 0, "all_nba_1st": 0,
                                    "all_nba_total": 0, "all_star": 0},
                      "stats": {"career_ppg": 20.0, "career_rpg": 5.0, "career_apg": 3.0, "peak_ppg": 28.0}}
    return {"id": name.lower().replace(" ", "-"), "nome": name, "score": score, "highlights": highlights}


class HallOfFameViewTest(unittest.TestCase):
    def test_filter_and_rank(self):
        classes = [{"stagione_elezione": 3, "inductees": [inductee("A", 1554), inductee("E", 299)]},
                   {"stagione_elezione": 5, "inductees": [inductee("B", 909), inductee("C", 650),
                                                          inductee("D", 610), inductee("F", 310)]}]
        view = hall_of_fame_view(classes, {}, None)
        self.assertEqual((view["total_inductees"], view["shown"], view["min_score"]), (6, 5, 300))
        self.assertEqual([p["name"] for p in view["podium"]], ["A", "B", "C"])
        self.assertEqual([p["rank"] for p in view["podium"]], [1, 2, 3])
        tiers = {t["name"]: [p["name"] for p in t["players"]] for t in view["tiers"]}
        self.assertEqual(tiers, {"Legends": ["D"], "Hall of Famers": ["F"]})
        self.assertEqual(view["tiers"][1]["players"][0]["rank"], 5)
        self.assertEqual(view["latest_class"], {"season": 5, "names": ["B", "C", "D", "F"]})

    def test_tie_break_titles_then_name(self):
        classes = [{"stagione_elezione": 1, "inductees": [inductee("Zed", 400, titles=1), inductee("Bob", 400),
                                                          inductee("Al", 400)]}]
        view = hall_of_fame_view(classes, {}, None)
        self.assertEqual([p["name"] for p in view["podium"]], ["Zed", "Al", "Bob"])

    def test_list_highlights(self):
        view = hall_of_fame_view([{"stagione_elezione": 1, "inductees": [inductee("A", 500, list_style=True)]}],
                                 {}, None)
        player = view["podium"][0]
        self.assertEqual(set(player["accolades"].values()), {0})
        self.assertIsNone(player["stats"])

    def test_career_lookup(self):
        careers = {"a": [{"squadra": "Spurs", "ruolo": "PF"}, {"squadra": "Spurs", "ruolo": "C"},
                         {"squadra": "Raptors", "ruolo": "PF"}]}
        classes = [{"stagione_elezione": 1, "inductees": [inductee("A", 500), inductee("B", 400)]}]
        a, b = hall_of_fame_view(classes, careers, "Raptors")["podium"]
        self.assertEqual((a["position"], a["main_team"], a["played_for_user"]), ("PF", "Spurs", True))
        self.assertEqual((b["position"], b["main_team"], b["played_for_user"]), (None, None, False))

    def test_latest_class_only_shown(self):
        classes = [{"stagione_elezione": 1, "inductees": [inductee("A", 500)]},
                   {"stagione_elezione": 2, "inductees": [inductee("B", 100)]}]
        self.assertEqual(hall_of_fame_view(classes, {}, None)["latest_class"], {"season": 1, "names": ["A"]})

    def test_empty(self):
        view = hall_of_fame_view([{"stagione_elezione": 1, "inductees": [inductee("A", 10)]}], {}, None)
        self.assertEqual(view["podium"], [])
        self.assertTrue(all(not t["players"] for t in view["tiers"]))
        self.assertIsNone(view["latest_class"])
        self.assertEqual(view["shown"], 0)


class SeasonHelpersTest(unittest.TestCase):
    def test_season_years(self):
        self.assertEqual(season_years([{"stagione": 1, "anno": 2002}, {"stagione": 2}, "junk"]), {1: 2002})

    def test_year_for_exact(self):
        self.assertEqual(year_for(1, {1: 2002}, None), 2002)

    def test_year_for_gap(self):
        self.assertEqual(year_for(23, {22: 2022, 24: 2024}, None), 2023)

    def test_year_for_no_history(self):
        self.assertEqual(year_for(5, {}, 2002), 2006)
        self.assertIsNone(year_for(5, {}, None))
        self.assertIsNone(year_for(None, {1: 2002}, 2002))

    def test_parse_season(self):
        self.assertEqual(parse_season("Season 5"), 5)
        self.assertEqual(parse_season(5), 5)
        self.assertIsNone(parse_season("-"))
        self.assertIsNone(parse_season(None))

    def test_playoff_label(self):
        self.assertEqual(playoff_label("Campione NBA 🏆"), "Champions")
        self.assertEqual(playoff_label("Finali NBA"), "Lost Finals")
        self.assertEqual(playoff_label("Playoff"), "Playoffs")
        self.assertEqual(playoff_label("Playoffs"), "Playoffs")
        self.assertEqual(playoff_label("Play-In"), "Play-In")
        self.assertEqual(playoff_label("Lottery"), "Lottery")
        self.assertEqual(playoff_label("In Progress"), "In Progress")
        self.assertEqual(playoff_label(None), "Playoffs")


if __name__ == "__main__":
    unittest.main()
