"""The owner's season-start letter lands once, even when the objectives are regenerated right after the profile."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.board_engine import add_board_message, generate_seasonal_objectives, init_board_profile_for_team

LETTER_TITLE = "Official Directive Letter from the Presidency"


def fake_team(season=1):
    roster = [SimpleNamespace(nome=f"Player {i}", ovr=70 + i, eta=21 + i) for i in range(8)]
    return SimpleNamespace(nome="Test Team", roster=roster, torneo=SimpleNamespace(season_number=season), payroll=40.0,
                           personalita_proprietario="Risparmiatore", board_profile=None)


class SeasonLetterTest(unittest.TestCase):
    def test_profile_then_objectives_sends_one_letter(self):
        team = fake_team()
        profile = init_board_profile_for_team(team, force_reset=True)
        generate_seasonal_objectives(team, profile)  # what server.py does on a new career / team switch
        letters = [m for m in profile.board_messages if m["title"] == LETTER_TITLE]
        self.assertEqual(len(letters), 1)

    def test_next_season_with_the_same_target_keeps_its_letter(self):
        team = fake_team(season=1)
        profile = init_board_profile_for_team(team, force_reset=True)
        team.torneo.season_number = 2  # new season, same roster: same expected wins and the same text
        generate_seasonal_objectives(team, profile)
        generate_seasonal_objectives(team, profile)  # a repeat inside the same season still lands once
        letters = [m for m in profile.board_messages if m["title"] == LETTER_TITLE]
        self.assertEqual([m["date"] for m in letters], ["Season 2 Start", "Season 1 Start"])
        self.assertEqual(letters[0]["content"], letters[1]["content"])

    def test_a_different_message_is_still_added(self):
        team = fake_team()
        profile = init_board_profile_for_team(team, force_reset=True)
        before = len(profile.board_messages)
        self.assertTrue(add_board_message(profile, {"date": "Season Start", "title": LETTER_TITLE,
                                                    "content": "Another season, other expectations.", "type": "info"}))
        self.assertEqual(len(profile.board_messages), before + 1)

    def test_objective_titles_are_english(self):
        team = fake_team()
        profile = init_board_profile_for_team(team, force_reset=True)
        titles = [o.title for o in profile.objectives]
        self.assertIn("Avoid the Luxury Tax", titles)
        for word in ("Evitare", "Capitale"):
            self.assertFalse(any(word in t for t in titles), titles)


if __name__ == '__main__':
    unittest.main()
