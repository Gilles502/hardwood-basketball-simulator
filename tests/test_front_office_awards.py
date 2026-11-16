"""AI GM layer 3: Coach of the Year and GM of the Year (core/front_office/awards.py)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.front_office.awards import coach_of_the_year, gm_of_the_year, record_gm_award
from core.front_office.seasons import close_season, mark_season_end, mark_season_start
from core.front_office.state import build_front_office
from core.save_manager import restore_tournament_state, serialize_tournament_state

NAMES = ["Boston Minutemen", "Chicago Gales", "Miami Tide", "Utah Summit"]


def make_torneo(rows, user_team=None, season=3):
    """`rows`: team name -> dict(wins, last_wins, expected, core_kept: share of the season-start top 8 still here)."""
    squadre = []
    for name in NAMES:
        row = rows.get(name, dict(wins=41, last_wins=41, expected=41, core_kept=1.0))
        roster = [SimpleNamespace(nome=f"{name} P{i}", ovr=70 - i, eta=27) if i < round(8 * row["core_kept"])
                  else SimpleNamespace(nome=f"{name} New{i}", ovr=70 - i, eta=27) for i in range(8)]
        squadre.append(SimpleNamespace(nome=name, roster=roster, vittorie=row["wins"], sconfitte=82 - row["wins"],
                                       coach=SimpleNamespace(nome=f"Coach {name}")))
    torneo = SimpleNamespace(
        squadre=squadre, season_number=season, starting_year=2002, anno_corrente=2002 + season - 1,
        user_role="spectator" if user_team is None else "gm_coach",
        squadra_giocatore=next((s for s in squadre if s.nome == user_team), None),
    )
    torneo._determina_stato_squadra = lambda s: "Mediocre"
    fo = build_front_office(torneo)
    torneo.front_office = fo
    for team in squadre:
        row = rows.get(team.nome, dict(wins=41, last_wins=41, expected=41, core_kept=1.0))
        fo.season_marks[team.nome] = {"year": torneo.anno_corrente, "expected": row["expected"],
                                      "last_wins": row["last_wins"],
                                      "top8": [f"{team.nome} P{i}" for i in range(8)]}
    return torneo, fo


class AwardsTests(unittest.TestCase):
    def test_coy_rewards_wins_over_expected(self):
        torneo, fo = make_torneo({
            "Boston Minutemen": dict(wins=50, last_wins=45, expected=38, core_kept=1.0),
            "Chicago Gales": dict(wins=60, last_wins=58, expected=58, core_kept=1.0)})
        winner = coach_of_the_year(torneo, fo)
        self.assertEqual(winner["squadra"], "Boston Minutemen")
        self.assertEqual(winner["nome"], "Coach Boston Minutemen")
        self.assertEqual((winner["wins"], winner["losses"], winner["last_wins"]), (50, 32, 45))

    def test_coy_skips_interim_coaches(self):
        torneo, fo = make_torneo({"Boston Minutemen": dict(wins=70, last_wins=30, expected=30, core_kept=1.0)})
        torneo.squadre[0].coach.nome = "Interim Somebody"
        self.assertNotEqual(coach_of_the_year(torneo, fo)["squadra"], "Boston Minutemen")

    def test_gmoy_rewards_jump_and_turnover(self):
        same = dict(wins=52, last_wins=40, expected=44)
        torneo, fo = make_torneo({
            "Boston Minutemen": dict(same, core_kept=1.0),
            "Chicago Gales": dict(same, core_kept=0.5)})
        winner = gm_of_the_year(torneo, fo)
        self.assertEqual(winner["squadra"], "Chicago Gales")
        self.assertEqual(winner["nome"], fo.seated_gm("Chicago Gales").name)

    def test_gmoy_turnover_counts_the_summer_rebuild(self):
        # The season-start top 8 already holds the summer signings; last season's end shows who was replaced.
        same = dict(wins=52, last_wins=40, expected=44, core_kept=1.0)
        torneo, fo = make_torneo({"Boston Minutemen": same, "Chicago Gales": same})
        year = torneo.anno_corrente
        fo.records["Boston Minutemen"] = [{"year": year - 1, "top8_end": [f"Boston Minutemen P{i}" for i in range(8)]}]
        fo.records["Chicago Gales"] = [{"year": year - 1, "top8_end": [f"Old Bull {i}" for i in range(8)]}]
        self.assertEqual(gm_of_the_year(torneo, fo)["squadra"], "Chicago Gales")

    def test_gmoy_resigned_expiring_player_is_not_turnover(self):
        # Boston's star expires in offseason progression, leaves the roster before close_season, and re-signs in FA;
        # Chicago genuinely replaces one starter. Only Chicago gets turnover credit.
        same = dict(wins=52, last_wins=40, expected=44, core_kept=1.0)
        torneo, fo = make_torneo({"Boston Minutemen": same, "Chicago Gales": same}, season=2)
        boston = next(s for s in torneo.squadre if s.nome == "Boston Minutemen")
        chicago = next(s for s in torneo.squadre if s.nome == "Chicago Gales")
        chicago.roster[0].nome = "Old Bull 0"
        mark_season_start(torneo, fo)
        mark_season_end(torneo, fo)             # snapshot at the start of start_offseason_progression
        expiring_star = boston.roster.pop(0)    # progression strips the expiring player before close_season
        close_season(torneo, fo)
        boston.roster.insert(0, expiring_star)  # re-signed in free agency
        chicago.roster[0] = SimpleNamespace(nome="Chicago Gales P0", ovr=70, eta=27)
        torneo.season_number += 1
        torneo.anno_corrente += 1
        for team in (boston, chicago):
            fo.season_marks[team.nome] = {"year": torneo.anno_corrente, "expected": 44,
                                          "last_wins": 40, "top8": [p.nome for p in team.roster]}
        self.assertEqual(gm_of_the_year(torneo, fo)["squadra"], "Chicago Gales")

    def test_gmoy_turnover_never_deepens_a_bad_season(self):
        sunk = dict(wins=20, last_wins=41, expected=41, core_kept=1.0)
        torneo, fo = make_torneo({
            "Boston Minutemen": dict(wins=30, last_wins=40, expected=44, core_kept=0.5),   # base -17, half new
            "Chicago Gales": dict(wins=30, last_wins=41, expected=44, core_kept=1.0),    # base -18
            "Miami Tide": sunk, "Utah Summit": sunk})
        self.assertEqual(gm_of_the_year(torneo, fo)["squadra"], "Boston Minutemen")

    def test_user_team_can_win_with_user_name(self):
        torneo, fo = make_torneo({"Miami Tide": dict(wins=66, last_wins=30, expected=35, core_kept=0.5)},
                                 user_team="Miami Tide")
        torneo.user_gm_profile = SimpleNamespace(name="Tobin Delacroix Jr.")
        self.assertEqual(gm_of_the_year(torneo, fo)["nome"], "Tobin Delacroix Jr.")
        self.assertEqual(gm_of_the_year(torneo, fo)["squadra"], "Miami Tide")
        self.assertEqual(coach_of_the_year(torneo, fo)["squadra"], "Miami Tide")
        record_gm_award(torneo, fo, gm_of_the_year(torneo, fo))  # no CPU career for the user: no crash

    def test_no_marks_no_crash(self):
        torneo, fo = make_torneo({"Utah Summit": dict(wins=60, last_wins=60, expected=60, core_kept=1.0)})
        fo.season_marks.clear()
        for name in (coach_of_the_year, gm_of_the_year):
            winner = name(torneo, fo)
            self.assertIsNone(winner["last_wins"])
            self.assertIsNotNone(winner["expected"])
        # Equal rosters, so the team with the most wins beat its expectation the most.
        self.assertEqual(coach_of_the_year(torneo, fo)["squadra"], "Utah Summit")

    def test_winning_cpu_gm_career_gets_the_award(self):
        torneo, fo = make_torneo({"Chicago Gales": dict(wins=60, last_wins=30, expected=35, core_kept=0.5)})
        winner = gm_of_the_year(torneo, fo)
        record_gm_award(torneo, fo, winner)
        record_gm_award(torneo, fo, winner)  # once only
        entry = next(e for e in fo.seated_gm("Chicago Gales").career if e["to_year"] is None)
        self.assertEqual(entry["awards"], ["GM of the Year 2004"])

    def test_awards_survive_save_round_trip(self):
        torneo, fo = make_torneo({"Chicago Gales": dict(wins=60, last_wins=30, expected=35, core_kept=0.5)})
        torneo.coach_of_the_year = coach_of_the_year(torneo, fo)
        torneo.gm_of_the_year = gm_of_the_year(torneo, fo)
        saved = serialize_tournament_state(torneo)
        fresh, _ = make_torneo({})
        restore_tournament_state(fresh, saved)
        self.assertEqual(fresh.coach_of_the_year, torneo.coach_of_the_year)
        self.assertEqual(fresh.gm_of_the_year, torneo.gm_of_the_year)


if __name__ == "__main__":
    unittest.main()
