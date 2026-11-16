"""A save made during the playoffs must load back in the playoffs, not as PRE_SEASON (which wiped the calendar)."""
import contextlib
import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with contextlib.redirect_stdout(io.StringIO()):
    import server


class SavePhaseTests(unittest.TestCase):
    def test_save_writes_the_live_phase_onto_the_tournament(self):
        t = SimpleNamespace(league_state="PRE_SEASON")
        with mock.patch.object(server, "SIMULATION_TOURNAMENT", t), \
                mock.patch.object(server, "LEAGUE_STATE", "PLAYOFFS_IN_PROGRESS"), \
                mock.patch.object(server, "save_game") as save_game:
            server.save_current_game("Career")
        self.assertEqual(t.league_state, "PLAYOFFS_IN_PROGRESS")
        save_game.assert_called_once_with("Career", t, extra_metadata={"phase": "PLAYOFFS_IN_PROGRESS"})

    def test_load_trusts_the_metadata_phase_over_a_stale_state_file(self):
        """Saves written before the fix carry PRE_SEASON in the state file but the real phase in the metadata."""
        t = SimpleNamespace(league_state="PRE_SEASON")
        self.assertEqual(server.loaded_phase({"phase": "PLAYOFFS_IN_PROGRESS"}, t), "PLAYOFFS_IN_PROGRESS")

    def test_load_without_metadata_phase_falls_back_to_the_state_file(self):
        t = SimpleNamespace(league_state="ALL_STAR_BREAK")
        self.assertEqual(server.loaded_phase({}, t), "ALL_STAR_BREAK")


if __name__ == "__main__":
    unittest.main()
