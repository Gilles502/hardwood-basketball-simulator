"""AI GM layer 3: expected wins at the season start and one record row per team (core/front_office/seasons.py)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office.seasons import (close_season, ensure_season_marks, expected_wins, last_records,
                                       league_avg_ovr, mark_coach_change, mark_season_end, mark_season_start)
from core.front_office.state import build_front_office, current_year
from core.save_manager import restore_tournament_state, serialize_tournament_state

FO = CONFIG.FRONT_OFFICE


def player(ovr, name="P"):
    return SimpleNamespace(ovr=ovr, nome=name, eta=27)


def make_team(name, ovr, wins=0, losses=0):
    return SimpleNamespace(nome=name, roster=[player(ovr, f"{name}{i}") for i in range(10)],
                           vittorie=wins, sconfitte=losses)


def make_torneo():
    squadre = [make_team("A", 70, 50, 32), make_team("B", 70, 30, 52), make_team("C", 70, 41, 41)]
    torneo = SimpleNamespace(
        squadre=squadre, season_number=3, starting_year=2002, anno_corrente=2004,
        user_role="spectator", squadra_giocatore=None,
        campione=None, playoff_teams={"east": [], "west": []})
    torneo._determina_stato_squadra = lambda s: "Mediocre"
    torneo.front_office = build_front_office(torneo)
    return torneo


class ExpectedWinsTests(unittest.TestCase):
    def test_expected_wins_formula_and_clamp(self):
        self.assertAlmostEqual(expected_wins(make_team("X", 72), 70.0), 44.0)
        self.assertEqual(expected_wins(make_team("X", 100), 70.0), 65)
        self.assertEqual(expected_wins(make_team("X", 40), 70.0), 15)

    def test_league_avg_ovr(self):
        t = make_torneo()
        self.assertEqual(league_avg_ovr(t), 70.0)


class SeasonBookkeepingTests(unittest.TestCase):
    def test_mark_season_start_reads_last_wins(self):
        t = make_torneo()
        mark_season_start(t, t.front_office)
        mark = t.front_office.season_marks["A"]
        self.assertEqual(mark["last_wins"], 50)
        self.assertEqual(len(mark["top8"]), 8)
        self.assertEqual(mark["year"], current_year(t))

    def test_close_season_uses_preseason_expectation(self):
        t = make_torneo()
        mark_season_start(t, t.front_office)
        t.front_office.season_marks["A"]["expected"] = 30
        for p in t.squadre[0].roster:
            p.ovr = 95
        close_season(t, t.front_office)
        self.assertEqual(last_records(t.front_office, "A", 1)[0]["expected"], 30)

    def test_close_season_fallback_and_idempotent(self):
        t = make_torneo()
        close_season(t, t.front_office)
        close_season(t, t.front_office)
        rows = t.front_office.records["A"]
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["expected"], FO.EXPECTED_WINS_BASE)
        self.assertEqual(rows[0]["wins"], 50)

    def test_close_season_updates_career(self):
        t = make_torneo()
        a = t.squadre[0]
        t.campione = a
        t.playoff_teams = {"east": [a], "west": []}
        close_season(t, t.front_office)
        close_season(t, t.front_office)
        entry = t.front_office.seated_gm("A").career[-1]
        self.assertEqual((entry["titles"], entry["playoffs"], entry["wins"], entry["losses"]), (1, 1, 50, 32))
        row = last_records(t.front_office, "A", 1)[0]
        self.assertTrue(row["champion"] and row["playoffs"])
        other = t.front_office.seated_gm("B").career[-1]
        self.assertEqual((other["titles"], other["playoffs"], other["wins"]), (0, 0, 30))

    def test_close_season_row_has_plan_gm_and_coach_flag(self):
        t = make_torneo()
        t.front_office.seats.pop("B")
        close_season(t, t.front_office)
        row_a = last_records(t.front_office, "A", 1)[0]
        self.assertEqual(row_a["gm_id"], t.front_office.seats["A"])
        self.assertEqual(row_a["plan"], t.front_office.plans["A"].state)
        self.assertIs(row_a["coach_fired"], False)
        self.assertIsNone(last_records(t.front_office, "B", 1)[0]["gm_id"])

    def test_records_trimmed_to_keep_limit(self):
        t = make_torneo()
        t.front_office.records["A"] = [{"year": 1900 + i} for i in range(FO.RECORDS_KEEP_PER_TEAM)]
        close_season(t, t.front_office)
        rows = t.front_office.records["A"]
        self.assertEqual(len(rows), FO.RECORDS_KEEP_PER_TEAM)
        self.assertEqual(rows[-1]["year"], current_year(t))
        self.assertEqual(rows[0]["year"], 1901)

    def test_row_keeps_season_start_plan_coach_change_and_end_core(self):
        t = make_torneo()
        fo = t.front_office
        fo.plans["A"].state = "CONTENDER"
        mark_season_start(t, fo)
        self.assertEqual(fo.season_marks["A"]["plan"], "CONTENDER")
        fo.plans["A"].state = "REBUILDER"          # flipped at the deadline
        mark_coach_change(t, fo, "A")              # the coach went mid-season
        t.squadre[0].roster[0].ovr = 99
        close_season(t, fo)
        row = last_records(fo, "A", 1)[0]
        self.assertEqual((row["plan_start"], row["plan"], row["coach_fired"]), ("CONTENDER", "REBUILDER", True))
        self.assertEqual(row["top8_end"][0], "A0")
        self.assertEqual(len(row["top8_end"]), 8)
        self.assertIs(last_records(fo, "B", 1)[0]["coach_fired"], False)

    def test_mark_season_end_snapshots_top8_before_offseason_strips_roster(self):
        t = make_torneo()
        fo = t.front_office
        mark_season_start(t, fo)
        mark_season_end(t, fo)
        self.assertEqual(fo.season_marks["A"]["top8_end"], [f"A{i}" for i in range(8)])
        t.squadre[0].roster = t.squadre[0].roster[4:]   # expiring and retiring players leave in progression
        close_season(t, fo)
        self.assertEqual(last_records(fo, "A", 1)[0]["top8_end"], [f"A{i}" for i in range(8)])

    def test_stale_mark_gives_no_plan_start_and_no_coach_flag(self):
        t = make_torneo()
        fo = t.front_office
        mark_season_start(t, fo)
        mark_coach_change(t, fo, "A")
        t.anno_corrente += 1                       # the mark is last year's
        mark_coach_change(t, fo, "B")              # ignored: no mark for this year
        close_season(t, fo)
        row = last_records(fo, "A", 1)[0]
        self.assertIsNone(row["plan_start"])
        self.assertIs(row["coach_fired"], False)
        self.assertNotIn("coach_fired", fo.season_marks["B"])

    def test_ensure_season_marks_fills_only_missing_teams(self):
        t = make_torneo()
        fo = t.front_office
        year = current_year(t)
        fo.records["A"] = [{"year": year - 1, "wins": 33}]
        fo.season_marks["C"] = {"year": year, "expected": 12.0, "last_wins": 7, "top8": ["x"], "plan": "MIDDLE"}
        ensure_season_marks(t, fo)
        self.assertEqual(fo.season_marks["A"]["last_wins"], 33)        # last season's row
        self.assertIsNone(fo.season_marks["B"]["last_wins"])            # no last season: no jump
        self.assertEqual(fo.season_marks["B"]["year"], year)
        self.assertEqual(fo.season_marks["B"]["plan"], fo.plans["B"].state)
        self.assertEqual(fo.season_marks["C"]["expected"], 12.0)        # an existing mark is never touched
        before = {k: dict(v) for k, v in fo.season_marks.items()}
        ensure_season_marks(t, fo)
        self.assertEqual(fo.season_marks, before)

    def test_load_fills_missing_marks_and_keeps_saved_ones(self):
        old = make_torneo()                       # a save from before the marks: none for this year
        fresh = make_torneo()
        restore_tournament_state(fresh, serialize_tournament_state(old))
        self.assertEqual(sorted(fresh.front_office.season_marks), ["A", "B", "C"])
        self.assertEqual(fresh.front_office.season_marks["A"]["year"], current_year(fresh))

        saved = make_torneo()
        mark_season_start(saved, saved.front_office)
        saved.front_office.season_marks["A"]["expected"] = 12.5
        state = serialize_tournament_state(saved)
        for p in saved.squadre[0].roster:          # the rosters move after the mark: a reload must not re-mark
            p.ovr = 90
        reloaded = make_torneo()
        restore_tournament_state(reloaded, state)
        self.assertEqual(reloaded.front_office.season_marks, saved.front_office.season_marks)


if __name__ == "__main__":
    unittest.main()
