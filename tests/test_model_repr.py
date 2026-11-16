"""Team and player reprs must stay short: the generated dataclass repr dumped the whole roster,
every career log and the tournament, and after many simulated seasons it ran out of memory."""
import os
import sys
import unittest
import dataclasses

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import Abilita, Giocatore, Squadra, Tendenze
from core.calendar_generator import NBACalendarGenerator


def flat(cls, value):
    return cls(**{f.name: value for f in dataclasses.fields(cls) if f.init})


def player(name, team):
    p = Giocatore(nome=name, ruolo="PG", eta=25, potenziale=80, abilita=flat(Abilita, 60),
                  tendenze=flat(Tendenze, 50), valutazione=75, squadra=team)
    p.career_log = [{"season": s, "notes": "x" * 1000} for s in range(50)]
    p.ovr_history = [{"season": s, "ovr": 75} for s in range(50)]
    return p


class ModelReprTests(unittest.TestCase):
    def test_reprs_do_not_grow_with_history(self):
        team = Squadra(nome="Toronto Northmen")
        team.roster = [player(f"Player {i}", team) for i in range(15)]
        team.standings_history = [{"season": s} for s in range(50)]
        self.assertLess(len(repr(team)), 200)
        self.assertLess(len(repr(team.roster[0])), 200)
        self.assertIn("Toronto Northmen", repr(team))
        self.assertIn("Player 0", repr(team.roster[0]))

    def test_calendar_generator_does_not_stringify_named_teams(self):
        class Team:
            def __init__(self, nome):
                self.nome = nome
                self.conference = "East"

            def __repr__(self):
                raise AssertionError("repr must not be called for a team that has a name")

        gen = NBACalendarGenerator(teams=[Team("Toronto Northmen"), Team("Boston Minutemen")], starting_year=2020)
        self.assertEqual(gen.team_names, ["Toronto Northmen", "Boston Minutemen"])


if __name__ == "__main__":
    unittest.main()
