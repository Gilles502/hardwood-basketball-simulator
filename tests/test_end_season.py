"""End of Season Hub phase engine: server state + saved marker -> current hub phase. No Flask needed."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.end_season import PHASES, clamp_hub_step, current_phase, end_season_status, remember_market, league_snapshot, restore_previous_teams, roster_snapshot


class CurrentPhaseTests(unittest.TestCase):
    def test_each_state_maps_to_its_first_phase(self):
        self.assertEqual(current_phase("PLAYOFFS_END", None), 0)
        self.assertEqual(current_phase("OFFSEASON_OPTIONS_DECISION", None), 1)
        self.assertEqual(current_phase("OFFSEASON_COACH_HIRING_START", None), 2)
        self.assertEqual(current_phase("OFFSEASON_TRADES_START", None), 3)
        self.assertEqual(current_phase("DRAFT_USER_PICK", None), 5)
        self.assertEqual(current_phase("OFFSEASON_COMPLETE", None), 8)

    def test_marker_survives_within_state_range(self):
        self.assertEqual(current_phase("OFFSEASON_COACH_HIRING_START", 3), 3)
        self.assertEqual(current_phase("OFFSEASON_TRADES_START", 4), 4)

    def test_marker_is_clamped_to_the_state(self):
        self.assertEqual(current_phase("OFFSEASON_TRADES_START", 2), 3)
        self.assertEqual(current_phase("OFFSEASON_TRADES_START", 7), 4)
        self.assertEqual(clamp_hub_step("OFFSEASON_DRAFT_START", 0), 5)

    def test_missing_marker_uses_first_phase_of_state(self):
        self.assertEqual(current_phase("OFFSEASON_CUTDOWN_START", None), 7)

    def test_after_the_last_pick_the_hub_stays_on_draft(self):
        self.assertEqual(current_phase("OFFSEASON_UFA_START", None), 5)
        self.assertEqual(current_phase("OFFSEASON_UFA_START", 4), 5)   # marker left by "Next" on phase 3
        self.assertEqual(current_phase("OFFSEASON_UFA_START", 6), 6)
        self.assertEqual(end_season_status("OFFSEASON_UFA_START", {"hub_step": 6}),
                         {"open": True, "phase": 6, "first": 5, "last": 6})

    def test_closed_outside_the_offseason(self):
        for state in ("REGULAR_SEASON", "PRE_SEASON", "PLAYOFFS_IN_PROGRESS"):
            self.assertIsNone(current_phase(state, None))
        self.assertIsNone(clamp_hub_step("PRE_SEASON", 3))
        self.assertFalse(end_season_status("PRE_SEASON", {})["open"])

    def test_status_reads_marker_from_log(self):
        self.assertEqual(end_season_status("OFFSEASON_COACH_HIRING_START", {"hub_step": 3}),
                         {"open": True, "phase": 3, "first": 2, "last": 3})

    def test_status_tolerates_missing_log(self):
        self.assertEqual(end_season_status("OFFSEASON_UFA_START", None)["phase"], 5)

    def test_nine_phases_in_spec_order(self):
        self.assertEqual(len(PHASES), 9)
        self.assertEqual(PHASES[0], "Season recap")
        self.assertEqual(PHASES[2], "Development & retirements")
        self.assertEqual(PHASES[8], "New season")


class RosterSnapshotTests(unittest.TestCase):
    def test_roster_snapshot(self):
        team = SimpleNamespace(roster=[
            SimpleNamespace(nome="Star", ruolo="PG", ovr=88, eta=27, contract=SimpleNamespace(salario_annuale=30.5)),
            SimpleNamespace(nome="Camp", ruolo="C", ovr=60, eta=22, contract=None),
        ])
        snap = roster_snapshot(team)
        self.assertEqual(snap["payroll"], 30.5)
        self.assertEqual([p["name"] for p in snap["players"]], ["Star", "Camp"])
        self.assertEqual(snap["players"][0], {"name": "Star", "role": "PG", "ovr": 88, "salary": 30.5, "age": 27})
        self.assertEqual(snap["players"][1]["salary"], 0.0)

    def test_league_snapshot(self):
        teams = [SimpleNamespace(nome="A", roster=[SimpleNamespace(ovr=o) for o in (80, 70)]),
                 SimpleNamespace(nome="B", roster=[SimpleNamespace(ovr=o) for o in (90, 88)])]
        self.assertEqual(league_snapshot(teams), {"B": {"strength": 89.0, "rank": 1}, "A": {"strength": 75.0, "rank": 2}})


class MarketPersistenceTests(unittest.TestCase):
    """The free-agent market built when the options are confirmed must survive a save/load."""

    def test_remember_market_keeps_players_and_previous_team_names(self):
        raptors = SimpleNamespace(nome="Raptors")
        fa1, fa2 = SimpleNamespace(nome="Free One"), SimpleNamespace(nome="Free Two")
        torneo = SimpleNamespace(offseason_log_data={"hub_step": 2})
        remember_market(torneo, [fa1, fa2], {"Free One": raptors})
        self.assertEqual(torneo.nuovi_free_agents, [fa1, fa2])
        self.assertEqual(torneo.offseason_log_data["previous_teams"], {"Free One": "Raptors"})
        self.assertEqual(torneo.offseason_log_data["hub_step"], 2)

    def test_restore_previous_teams_maps_names_back_to_teams(self):
        raptors, bulls = SimpleNamespace(nome="Raptors"), SimpleNamespace(nome="Bulls")
        torneo = SimpleNamespace(squadre=[raptors, bulls],
                                 offseason_log_data={"previous_teams": {"Free One": "Raptors", "Gone": "Folded Team"}})
        self.assertEqual(restore_previous_teams(torneo), {"Free One": raptors})

    def test_restore_previous_teams_without_data(self):
        self.assertEqual(restore_previous_teams(SimpleNamespace(squadre=[], offseason_log_data=None)), {})


if __name__ == "__main__":
    unittest.main()
