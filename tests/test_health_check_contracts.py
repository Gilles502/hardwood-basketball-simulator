"""Health report: what happened to stars' contracts and to free agency bidding in a season."""
import unittest

from scripts.health_check import contract_metrics, signing_lines

OUTCOMES = [
    {"player": "Vantreese", "team": "Sixers", "ovr": 95, "outcome": "walks"},
    {"player": "Kobe", "team": "Lakers", "ovr": 97, "outcome": "extended"},
    {"player": "Mason", "team": "Hornets", "ovr": 86, "outcome": "refused"},
    {"player": "Bench", "team": "Hornets", "ovr": 72, "outcome": "not_offered"},
]
SIGNINGS = [
    {"player": "Vantreese", "ovr": 95, "team": "Knicks", "previous_team": "Sixers", "salary": 24.5, "years": 4,
     "raised": 1, "beat": [{"team": "Heat", "salary": 23.0, "years": 4, "raised": 2}]},
    {"player": "Mason", "ovr": 86, "team": "Hornets", "previous_team": "Hornets", "salary": 12.0, "years": 3,
     "raised": 0, "beat": []},
    {"player": "Bench", "ovr": 72, "team": "Suns", "previous_team": "Hornets", "salary": 2.0, "years": 1,
     "raised": 0, "beat": []},
]


class ContractMetricsTests(unittest.TestCase):
    def test_counts_star_outcomes_moves_and_bidding_wars(self):
        m = contract_metrics(OUTCOMES, SIGNINGS, star_line=85)
        self.assertEqual(m["star_outcomes"], {"walks": 1, "extended": 1, "refused": 1})
        self.assertEqual(m["star_signings"], {"stayed": 1, "moved": 1})
        self.assertEqual(m["bidding_wars"], 1)
        self.assertEqual(m["max_raises"], 2)

    def test_empty_season(self):
        self.assertEqual(contract_metrics([], [], star_line=85),
                         {"star_outcomes": {}, "star_signings": {"stayed": 0, "moved": 0}, "bidding_wars": 0,
                          "max_raises": 0})

    def test_signing_lines_list_76_plus_only(self):
        lines = signing_lines(3, SIGNINGS)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "[Season 3] Vantreese (95) Sixers -> Knicks, 4y $24.5M · raises 1 · beat Heat")
        self.assertEqual(lines[1], "[Season 3] Mason (86) Hornets -> Hornets, 3y $12.0M · raises 0 · beat -")


if __name__ == "__main__":
    unittest.main()
