"""The retired list holds each player once (a 25-season save had 504 copies), also for saves written before."""
import unittest
from types import SimpleNamespace

from core.models import add_retired_player, unique_retired_players


def player(name, age=36, ovr=70, pot=70, db_id=None):
    return SimpleNamespace(nome=name, eta=age, valutazione=ovr, potenziale=pot, db_id=db_id)


class RetiredListTests(unittest.TestCase):
    def test_the_same_player_is_added_once(self):
        t = SimpleNamespace(giocatori_ritirati=[])
        p = player("Doug Hale")
        self.assertTrue(add_retired_player(t, p))
        self.assertFalse(add_retired_player(t, p))
        self.assertFalse(add_retired_player(t, player("Doug Hale")))   # a reloaded copy of him
        self.assertEqual(len(t.giocatori_ritirati), 1)

    def test_a_namesake_is_another_player(self):
        t = SimpleNamespace(giocatori_ritirati=[])
        add_retired_player(t, player("Marcus Williams", age=35, ovr=68))
        add_retired_player(t, player("Marcus Williams", age=24, ovr=58))
        self.assertEqual(len(t.giocatori_ritirati), 2)

    def test_old_saves_drop_their_copies(self):
        a, b = player("A"), player("B")
        self.assertEqual(unique_retired_players([a, player("A"), b, player("A")]), [a, b])

    def test_a_league_without_the_list_is_left_alone(self):
        self.assertFalse(add_retired_player(SimpleNamespace(), player("A")))


if __name__ == "__main__":
    unittest.main()
