"""Dashboard summary maths (form, streaks, standings, next game) must not depend on Flask."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.dashboard_summary import (
    GameResult, build_standings, build_summary, form_from_results, last_result, next_game, team_results,
)

CFG = CONFIG.DASHBOARD


def game(day, home, away, home_score, away_score, played=True):
    return SimpleNamespace(
        game_id=f"g{day}-{home}-{away}", home_team=home, away_team=away, played=played,
        home_score=home_score, away_score=away_score, day_index=day, date=f"2003-01-{day + 1:02d}",
    )


def calendar_of(*games):
    """One CalendarDay-like object per day_index, in order."""
    days = {}
    for g in games:
        days.setdefault(g.day_index, []).append(g)
    return [SimpleNamespace(day_index=d, date=gs[0].date, games=gs) for d, gs in sorted(days.items())]


def results(outcomes, home_flags=None):
    """GameResult list from a string like 'WWL' (oldest first)."""
    out = []
    for i, ch in enumerate(outcomes):
        is_home = True if home_flags is None else home_flags[i]
        out.append(GameResult(i, f"2003-01-{i + 1:02d}", "Opp", is_home, ch == "W", 100, 90 if ch == "W" else 110))
    return out


class TeamResultsTests(unittest.TestCase):
    def test_returns_only_played_games_of_the_team_with_correct_perspective(self):
        cal = calendar_of(
            game(0, "Kings", "Wolves", 104, 98),
            game(1, "Bears", "Kings", 90, 95),
            game(2, "Kings", "Suns", 0, 0, played=False),
            game(3, "Bears", "Suns", 100, 99),
        )
        res = team_results(cal, "Kings")
        self.assertEqual([r.opponent for r in res], ["Wolves", "Bears"])
        self.assertEqual([r.is_home for r in res], [True, False])
        self.assertEqual([r.won for r in res], [True, True])
        self.assertEqual((res[1].points_for, res[1].points_against), (95, 90))

    def test_ordered_by_day_index_even_if_calendar_is_shuffled(self):
        cal = calendar_of(game(5, "Kings", "Wolves", 90, 100), game(1, "Kings", "Bears", 100, 90))
        self.assertEqual([r.day_index for r in team_results(cal, "Kings")], [1, 5])


class FormTests(unittest.TestCase):
    def test_five_wins_is_a_hot_w5_streak(self):
        f = form_from_results(results("LLWWWWW"), CFG)
        self.assertEqual((f["streak"], f["streak_len"], f["streak_type"], f["tag"]), ("W5", 5, "W", "hot"))

    def test_four_losses_is_a_cold_l4_streak(self):
        f = form_from_results(results("WWLLLL"), CFG)
        self.assertEqual((f["streak"], f["tag"]), ("L4", "cold"))

    def test_two_and_eight_last_ten_is_cold_even_with_a_w1_streak(self):
        f = form_from_results(results("LLLLLLLLWL" + "W")[-10:], CFG)  # last ten: LLLLLLLWLW -> 2 wins
        self.assertEqual(f["l10_wins"], 2)
        self.assertEqual(f["streak"], "W1")
        self.assertEqual(f["tag"], "cold")

    def test_eight_and_two_last_ten_is_hot_even_with_an_l1_streak(self):
        f = form_from_results(results("WWWWLWWWWL"), CFG)
        self.assertEqual((f["l10"], f["streak"], f["tag"]), ("8-2", "L1", "hot"))

    def test_no_games_gives_empty_form(self):
        f = form_from_results([], CFG)
        self.assertEqual((f["streak"], f["streak_len"], f["streak_type"], f["l10"], f["tag"]), ("", 0, None, "0-0", None))
        self.assertEqual((f["home"], f["away"]), ("0-0", "0-0"))

    def test_alternating_results_end_in_a_streak_of_one(self):
        f = form_from_results(results("WLWLW"), CFG)
        self.assertEqual((f["streak"], f["tag"]), ("W1", None))

    def test_home_and_away_splits(self):
        f = form_from_results(results("WWLLW", home_flags=[True, True, True, False, False]), CFG)
        self.assertEqual((f["home"], f["away"]), ("2-1", "1-1"))

    def test_l10_only_counts_the_last_ten_games(self):
        f = form_from_results(results("LLLLL" + "WWWWWWWWWW"), CFG)
        self.assertEqual(f["l10"], "10-0")


def team(name, wins, losses):
    return SimpleNamespace(nome=name, vittorie=wins, sconfitte=losses)


def tournament(west, east=(), cal=None, enable_play_in=True):
    return SimpleNamespace(squadre_ovest=list(west), squadre_est=list(east), calendario=cal or [], enable_play_in=enable_play_in)


class StandingsTests(unittest.TestCase):
    def test_orders_by_pct_then_wins_then_name(self):
        west = [team("Zed", 10, 10), team("Alpha", 10, 10), team("Big", 20, 20), team("Top", 15, 5)]
        rows = build_standings(tournament(west), CFG)["west"]
        self.assertEqual([r["nome"] for r in rows], ["Top", "Big", "Alpha", "Zed"])
        self.assertEqual([r["pos"] for r in rows], [1, 2, 3, 4])

    def test_games_back_uses_wins_and_losses_difference(self):
        west = [team("Lead", 28, 14), team("Chase", 24, 18)]
        rows = build_standings(tournament(west), CFG)["west"]
        self.assertEqual(rows[0]["gb"], 0.0)
        self.assertEqual(rows[1]["gb"], 4.0)

    def test_zones_with_play_in(self):
        west = [team(f"T{i:02d}", 40 - i, i + 1) for i in range(12)]
        rows = build_standings(tournament(west), CFG)["west"]
        self.assertEqual(rows[5]["zone"], "playoff")   # 6th
        self.assertEqual(rows[6]["zone"], "play_in")   # 7th
        self.assertEqual(rows[9]["zone"], "play_in")   # 10th
        self.assertEqual(rows[10]["zone"], "out")      # 11th

    def test_zones_without_play_in(self):
        west = [team(f"T{i:02d}", 40 - i, i + 1) for i in range(12)]
        rows = build_standings(tournament(west, enable_play_in=False), CFG)["west"]
        self.assertEqual(rows[7]["zone"], "playoff")   # 8th
        self.assertEqual(rows[8]["zone"], "out")       # 9th

    def test_rows_carry_form_from_the_calendar(self):
        cal = calendar_of(*[game(d, "Kings", "Wolves", 100, 90) for d in range(5)])
        t = tournament([team("Kings", 5, 0), team("Wolves", 0, 5)], cal=cal)
        rows = {r["nome"]: r for r in build_standings(t, CFG)["west"]}
        self.assertEqual((rows["Kings"]["streak"], rows["Kings"]["tag"]), ("W5", "hot"))
        self.assertEqual((rows["Wolves"]["streak"], rows["Wolves"]["tag"]), ("L5", "cold"))
        self.assertEqual(rows["Kings"]["home"], "5-0")

    def test_team_with_no_games_has_zero_pct_and_no_error(self):
        rows = build_standings(tournament([team("Fresh", 0, 0), team("Also", 0, 0)]), CFG)["west"]
        self.assertEqual(rows[0]["pct"], 0.0)
        self.assertEqual((rows[0]["streak"], rows[0]["tag"], rows[0]["l10"]), ("", None, "0-0"))
        self.assertEqual(rows[0]["gb"], 0.0)

    def test_both_conferences_are_returned(self):
        res = build_standings(tournament([team("W1", 1, 0)], east=[team("E1", 0, 1)]), CFG)
        self.assertEqual([r["nome"] for r in res["west"]], ["W1"])
        self.assertEqual([r["nome"] for r in res["east"]], ["E1"])


class NextGameAndLastResultTests(unittest.TestCase):
    def setUp(self):
        self.cal = calendar_of(
            game(0, "Kings", "Wolves", 104, 98),
            game(1, "Bears", "Kings", 90, 95),
            game(2, "Kings", "Suns", 0, 0, played=False),
            game(3, "Wolves", "Kings", 0, 0, played=False),
        )

    def test_next_game_is_first_unplayed_game_from_current_day(self):
        ng = next_game(self.cal, 2, "Kings")
        self.assertEqual((ng["opponent"], ng["is_home"], ng["day_index"]), ("Suns", True, 2))
        self.assertEqual(ng["date"], "2003-01-03")

    def test_next_game_respects_current_day(self):
        ng = next_game(self.cal, 3, "Kings")
        self.assertEqual((ng["opponent"], ng["is_home"]), ("Wolves", False))

    def test_next_game_is_none_when_everything_is_played_or_calendar_empty(self):
        self.assertIsNone(next_game(self.cal, 4, "Kings"))
        self.assertIsNone(next_game([], 0, "Kings"))

    def test_last_result_is_the_most_recent_played_game(self):
        lr = last_result(team_results(self.cal, "Kings"))
        self.assertEqual((lr["opponent"], lr["is_home"], lr["won"], lr["points_for"], lr["points_against"]),
                         ("Bears", False, True, 95, 90))

    def test_last_result_of_no_games_is_none(self):
        self.assertIsNone(last_result([]))


def player(name, ovr, injured=False, days=0):
    return SimpleNamespace(nome=name, ovr=ovr, infortunato=injured, giorni_infortunio_rimanenti=days)


def full_tournament(user_name="Kings", cal=None, spectator=False):
    kings = SimpleNamespace(nome="Kings", vittorie=24, sconfitte=18,
                            roster=[player("Healthy", 80), player("Hurt Low", 60, True, 5), player("Hurt Star", 88, True, 14)])
    wolves = team("Wolves", 22, 20)
    suns = team("Suns", 30, 12)
    cal = cal if cal is not None else calendar_of(
        game(0, "Kings", "Wolves", 104, 98), game(1, "Kings", "Suns", 0, 0, played=False))
    t = tournament([kings, wolves], east=[suns], cal=cal)
    t.squadra_giocatore = None if spectator else kings
    t._current_gameday = 1
    t.is_spectator = spectator
    return t


class BuildSummaryTests(unittest.TestCase):
    def test_summary_has_the_documented_keys_and_values(self):
        s = build_summary(full_tournament(), "REGULAR_SEASON", CFG, trade_offers=2, board_concern=True)
        for key in ("date", "day_index", "total_days", "team", "next_game", "last_result", "form", "standings", "attention", "updated_at"):
            self.assertIn(key, s)
        self.assertEqual(s["date"], "2003-01-02")
        self.assertEqual((s["day_index"], s["total_days"]), (1, 2))
        self.assertEqual(s["team"], {"name": "Kings", "record": "24-18", "conference": "West", "conf_rank": 1})
        self.assertEqual(s["next_game"]["opponent"], "Suns")
        self.assertEqual(s["next_game"]["opponent_record"], "30-12")
        self.assertEqual(s["next_game"]["opponent_conference"], "East")
        self.assertEqual(s["next_game"]["opponent_rank"], 1)
        self.assertEqual(s["last_result"]["opponent"], "Wolves")
        self.assertEqual(s["form"]["streak"], "W1")
        self.assertEqual(s["attention"]["trade_offers"], 2)
        self.assertTrue(s["attention"]["board_concern"])
        self.assertEqual(s["attention"]["pending_step"], "REGULAR_SEASON")
        self.assertIsInstance(s["updated_at"], int)

    def test_injuries_are_only_injured_players_sorted_by_ovr(self):
        s = build_summary(full_tournament(), "REGULAR_SEASON", CFG, 0, False)
        self.assertEqual(s["attention"]["injuries"], [
            {"name": "Hurt Star", "days": 14, "ovr": 88},
            {"name": "Hurt Low", "days": 5, "ovr": 60},
        ])

    def test_spectator_has_no_team_specific_data(self):
        s = build_summary(full_tournament(spectator=True), "REGULAR_SEASON", CFG, 0, False)
        self.assertIsNone(s["team"])
        self.assertIsNone(s["next_game"])
        self.assertIsNone(s["last_result"])
        self.assertEqual(s["attention"]["injuries"], [])
        self.assertIn("west", s["standings"])

    def test_empty_calendar_does_not_raise(self):
        s = build_summary(full_tournament(cal=[]), "PRE_SEASON", CFG, 0, False)
        self.assertIsNone(s["date"])
        self.assertEqual(s["total_days"], 0)
        self.assertIsNone(s["next_game"])
        self.assertIsNone(s["last_result"])
        self.assertEqual(s["team"]["name"], "Kings")


if __name__ == "__main__":
    unittest.main()
