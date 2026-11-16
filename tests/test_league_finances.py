"""Finances & CBA maths (CBA lines, payroll status, contract lists) must not depend on Flask."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.league_finances import build_economy, contract_lists, payroll_status, season_lines, team_outlook

CFG = CONFIG.ECONOMY
NO_LINE = 9999.0


def tournament(cap=123.65, floor=111.3, tax=147.6, apron1=NO_LINE, apron2=NO_LINE, teams=()):
    return SimpleNamespace(anno_corrente=2022, salary_cap=cap, salary_floor=floor, luxury_tax_threshold=tax,
                           first_apron=apron1, second_apron=apron2, mle_value=10.0, min_salary=2.8, squadre=list(teams))


def player(name, salary, score):
    return SimpleNamespace(nome=name, contract=SimpleNamespace(salario_annuale=salary),
                           performance_scores=SimpleNamespace(total=score))


def team(name, salaries, next_payroll, expiring=0.0, next_cap=136.02):
    roster = [player(f"{name} {i}", s, 70) for i, s in enumerate(salaries)]
    projection = [
        {"total_payroll": sum(salaries)},
        {"calendar_year": 2023, "total_payroll": next_payroll, "salary_cap": next_cap, "luxury_tax": 162.3,
         "first_apron": 171.1, "second_apron": 180.0, "expiring_salary_freed": expiring},
    ]
    return SimpleNamespace(nome=name, roster=roster, payroll=sum(salaries), personalita_proprietario="Bilanciato",
                           get_multi_year_financial_projection=lambda num_years=4: projection)


class SeasonLinesTests(unittest.TestCase):
    def test_missing_aprons_become_none_instead_of_9999(self):
        lines = season_lines(tournament(), CFG)
        self.assertIsNone(lines["first_apron"])
        self.assertIsNone(lines["second_apron"])
        self.assertEqual(lines["luxury_tax"], 147.6)
        self.assertFalse(lines["no_cap"])

    def test_no_cap_mode_has_no_lines(self):
        lines = season_lines(tournament(cap=NO_LINE, floor=0.0, tax=NO_LINE), CFG)
        self.assertTrue(lines["no_cap"])
        self.assertIsNone(lines["salary_cap"])
        self.assertIsNone(lines["salary_floor"])
        self.assertIsNone(lines["luxury_tax"])


class PayrollStatusTests(unittest.TestCase):
    def setUp(self):
        self.lines = season_lines(tournament(apron1=171.1, apron2=180.0), CFG)

    def test_each_band(self):
        self.assertEqual(payroll_status(100.0, self.lines), "under_floor")
        self.assertEqual(payroll_status(115.0, self.lines), "under_cap")
        self.assertEqual(payroll_status(130.0, self.lines), "over_cap")
        self.assertEqual(payroll_status(150.0, self.lines), "tax")
        self.assertEqual(payroll_status(175.0, self.lines), "first_apron")
        self.assertEqual(payroll_status(190.0, self.lines), "second_apron")

    def test_without_aprons_big_payrolls_are_just_taxpayers(self):
        self.assertEqual(payroll_status(250.0, season_lines(tournament(), CFG)), "tax")

    def test_no_cap(self):
        lines = season_lines(tournament(cap=NO_LINE, floor=0.0, tax=NO_LINE), CFG)
        self.assertEqual(payroll_status(250.0, lines), "no_cap")


class ContractListsTests(unittest.TestCase):
    def test_star_paid_like_a_star_is_not_an_overpay(self):
        contracts = [
            {"name": "Star", "team": "A", "salary": 40.0, "score": 95},
            {"name": "Vet", "team": "B", "salary": 30.0, "score": 60},
            {"name": "Kid", "team": "C", "salary": 4.0, "score": 90},
            {"name": "Bench", "team": "D", "salary": 3.0, "score": 50},
        ]
        lists = contract_lists(contracts, 5)
        self.assertEqual([c["name"] for c in lists["highest"]], ["Star", "Vet", "Kid", "Bench"])
        self.assertNotIn("Star", [c["name"] for c in lists["overpays"]])
        self.assertEqual(lists["overpays"][0]["name"], "Vet")   # 3rd best player, 2nd biggest salary
        self.assertEqual(lists["overpays"][0]["fair_salary"], 4.0)
        self.assertEqual(lists["bargains"][0]["name"], "Kid")   # 2nd best player, paid like the 3rd

    def test_size_and_empty(self):
        contracts = [{"name": str(i), "team": "A", "salary": float(i), "score": float(-i)} for i in range(10)]
        self.assertEqual(len(contract_lists(contracts, 3)["highest"]), 3)
        self.assertEqual(contract_lists([], 5), {"highest": [], "bargains": [], "overpays": []})


class BuildEconomyTests(unittest.TestCase):
    def test_teams_league_and_next_season(self):
        torneo = tournament(teams=[team("Kings", [60.0, 50.0, 45.0], 150.0, expiring=10.0),
                                   team("Bears", [40.0, 30.0], 50.0, expiring=20.0)])
        data = build_economy(torneo, CFG)
        self.assertEqual([t["name"] for t in data["teams"]], ["Kings", "Bears"])
        kings, bears = data["teams"]
        self.assertEqual(kings["status"], "tax")
        self.assertEqual(bears["status"], "under_floor")
        self.assertAlmostEqual(bears["cap_space"], 53.65)
        self.assertAlmostEqual(bears["next_cap_space"], 86.02)
        self.assertEqual(bears["expiring_salary"], 20.0)
        self.assertEqual(data["league"]["taxpayers"], 1)
        self.assertEqual(data["league"]["under_floor"], 1)
        self.assertEqual(data["next_season"]["year"], 2023)
        self.assertEqual(data["next_season"]["first_apron"], 171.1)
        self.assertEqual(len(data["contracts"]["highest"]), 5)
        self.assertEqual(data["market_watch"], ["Bears"])  # Kings have no room next summer (150 > 136.02)


class TeamOutlookTests(unittest.TestCase):
    def test_floor_status_and_free_agent_gaps(self):
        def year(cal, cap, tax, apron, payroll, salaries, expiring=()):
            return {"calendar_year": cal, "salary_cap": cap, "luxury_tax": tax, "first_apron": apron, "second_apron": apron + 9,
                    "total_payroll": payroll, "expiring_players": list(expiring), "expiring_salary_freed": 5.0 if expiring else 0.0,
                    "player_salaries": [{"name": n, "role": "PG", "ovr": 80, "age": 25, "salary": s, "years_left": y} for n, s, y in salaries]}
        projection = [
            year(2022, 123.65, 147.6, NO_LINE, 100.0, [("Star", 60.0, 3), ("Vet", 40.0, 1)]),
            year(2023, 136.02, 162.3, 171.1, 63.0, [("Star", 63.0, 2)], expiring=["Vet"]),
        ]
        squadra = SimpleNamespace(nome="Kings", get_multi_year_financial_projection=lambda num_years=4: projection)
        data = team_outlook(squadra, tournament(), CFG)
        now, nxt = data["seasons"]
        self.assertEqual(now["status"], "under_floor")          # 100 < 111.3 floor, the engine called it "Under Cap"
        self.assertEqual(now["salary_floor"], 111.3)
        self.assertIsNone(now["first_apron"])
        self.assertAlmostEqual(nxt["salary_floor"], round(136.02 * CFG.SALARY_FLOOR_RATIO, 2))
        self.assertEqual(nxt["first_apron"], 171.1)
        self.assertEqual(nxt["expiring_players"], ["Vet"])
        self.assertEqual([p["salaries"] for p in data["players"]], [[60.0, 63.0], [40.0, None]])


if __name__ == "__main__":
    unittest.main()
