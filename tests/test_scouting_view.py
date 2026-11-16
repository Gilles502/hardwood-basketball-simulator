"""The scouted view of the draft class: the same masking the Scouting page uses, shared with the draft room."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scouting_view import grade, scouted_prospects


def prospect(name, ovr=71, pot=86, progress=95.0):
    ratings = SimpleNamespace(close_shot_rating=82, mid_range_shot_rating=66, three_point_shot_rating=61, passing_vision=67,
                              interior_defense_rating=76, perimeter_defense_rating=58, defensive_rebound_rating=77, speed=60)
    return SimpleNamespace(nome=name, ruolo="PF", eta=22, provenance="Kansas", pedigree="Polished big", valutazione=ovr,
                           potenziale=pot, scouting_progress=progress, abilita=ratings)


def view(p, fog=True):
    return scouted_prospects([p], fog, [])[0]


class ScoutedProspectsTests(unittest.TestCase):
    def test_well_scouted_shows_exact_ovr_and_grade(self):
        v = view(prospect("A", progress=95))
        self.assertEqual(v["ovr_display"], "71")
        self.assertEqual(v["pot_display"], "A-")
        self.assertEqual(v["attributes"]["Close Shot"], "B+")
        self.assertEqual(v["archetype"], "Polished big")

    def test_partly_scouted_shows_ranges(self):
        v = view(prospect("A", progress=65))
        self.assertEqual(v["ovr_display"], "69 - 73")
        self.assertEqual(v["pot_display"], "B+ to A-")

    def test_little_scouted_flat_attributes(self):
        v = view(prospect("A", progress=35))
        self.assertEqual(v["ovr_display"], "66 - 76")
        self.assertTrue(all(a == "C to B" for a in v["attributes"].values()))

    def test_unscouted_hides_everything(self):
        v = view(prospect("A", progress=8))
        self.assertEqual(v["ovr_display"], "55 - 80")
        self.assertEqual(v["pot_display"], "D to A+")
        self.assertEqual(v["archetype"], "?")
        self.assertTrue(all(a == "?" for a in v["attributes"].values()))
        self.assertNotIn("71", [v["ovr_display"], v["pot_display"]])

    def test_no_fog_means_fully_scouted(self):
        v = view(prospect("A", progress=8), fog=False)
        self.assertEqual(v["scouting_progress"], 100.0)
        self.assertEqual(v["ovr_display"], "71")

    def test_sorted_by_mock_rank(self):
        board = scouted_prospects([prospect("Low", pot=78), prospect("High", pot=92), prospect("Mid", pot=85)], True, [])
        self.assertEqual([p["name"] for p in board], ["High", "Mid", "Low"])
        self.assertEqual([p["pos"] for p in board], [1, 2, 3])

    def test_assigned_scout_is_named(self):
        board = scouted_prospects([prospect("A")], True, [{"name": "Scout One", "assigned_to": "A"}])
        self.assertEqual(board[0]["assigned_scout"], "Scout One")

    def test_projection_labels_are_english(self):
        board = scouted_prospects([prospect(f"P{i}", pot=99 - i) for i in range(12)], True, [])
        self.assertEqual(board[10]["projection"], "Lottery")

    def test_grade_bands(self):
        self.assertEqual(grade(95), "A+")
        self.assertEqual(grade(84), "B+")
        self.assertEqual(grade(49), "D")


if __name__ == '__main__':
    unittest.main()
