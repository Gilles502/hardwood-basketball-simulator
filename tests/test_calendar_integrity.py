"""ensure_calendar_integrity must only regenerate a calendar that is really stale, never one mid-season."""
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


def day(index, played):
    games = [SimpleNamespace(played=played[i]) for i in range(len(played))]
    return SimpleNamespace(day_index=index, games=games)


def tournament(days, current_day):
    t = SimpleNamespace(calendario=days, _current_gameday=current_day, anno_corrente=2013, season_number=12)
    t.genera_calendario = mock.Mock()
    t.imposta_rotazioni_stagione = mock.Mock()
    return t


class EnsureCalendarIntegrityTests(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(server, "LEAGUE_STATE", "PRE_SEASON"),
            mock.patch.object(server, "auto_save_active_game"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.out = contextlib.redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_first_half_in_progress_keeps_its_results(self):
        """Day 0 is played and the season is on day 1: this is the normal state after one Sim Day."""
        t = tournament([day(0, [True, True]), day(1, [False, False]), day(2, [False, False])], current_day=1)
        server.ensure_calendar_integrity(t)
        t.genera_calendario.assert_not_called()

    def test_fully_played_calendar_left_from_a_previous_season_is_regenerated(self):
        t = tournament([day(0, [True, True]), day(1, [True, True])], current_day=0)
        server.ensure_calendar_integrity(t)
        t.genera_calendario.assert_called_once()

    def test_current_day_past_the_end_is_regenerated(self):
        t = tournament([day(0, [True]), day(1, [False])], current_day=2)
        server.ensure_calendar_integrity(t)
        t.genera_calendario.assert_called_once()

    def test_missing_calendar_is_generated(self):
        t = tournament([], current_day=0)
        server.ensure_calendar_integrity(t)
        t.genera_calendario.assert_called_once()


if __name__ == "__main__":
    unittest.main()
