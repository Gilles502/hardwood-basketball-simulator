"""A save made after the Finals stores the Finals MVP by name; loading it must give back the player, not the string
(the league payload reads finals_mvp.playoff_stats and crashed on a str)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.save_manager import restore_finals_mvp


def tournament(*names, fa=()):
    roster = [SimpleNamespace(nome=n) for n in names]
    return SimpleNamespace(squadre=[SimpleNamespace(roster=roster)], free_agents_pool=[SimpleNamespace(nome=n) for n in fa])


class RestoreFinalsMvpTests(unittest.TestCase):
    def test_name_becomes_the_player(self):
        t = tournament("Teodor Yardley", "Other")
        restore_finals_mvp(t, "Teodor Yardley")
        self.assertIs(t.finals_mvp, t.squadre[0].roster[0])

    def test_free_agent_is_found_too(self):
        t = tournament("Other", fa=["Free Guy"])
        restore_finals_mvp(t, "Free Guy")
        self.assertEqual(t.finals_mvp.nome, "Free Guy")

    def test_unknown_or_empty_name_gives_none(self):
        t = tournament("Other")
        restore_finals_mvp(t, "Retired Star")
        self.assertIsNone(t.finals_mvp)
        restore_finals_mvp(t, None)
        self.assertIsNone(t.finals_mvp)


if __name__ == "__main__":
    unittest.main()
