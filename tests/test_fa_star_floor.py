"""Free agency fixes of 2026-11-07: a star wants real money early at any age, a walked-away star goes back to his old
team when nobody else can pay him, no piling up of cheap veterans, CPU extensions keep their salaries on reload,
and the signing tweets read the right name."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.models import Contract
from offseason.contract_extensions import ContractExtensions
from offseason.free_agency import FreeAgency


def player(name="Dirk", ovr=93, age=33, role="PF", morale=70, ask=19.0, walks=""):
    return SimpleNamespace(nome=name, ovr=ovr, eta=age, ruolo=role, morale=morale, potenziale=ovr, ask=ask,
                           walks_away=walks)


def team(name, roster=(), state="Contender", cap_space=0.0, payroll=80.0):
    return SimpleNamespace(nome=name, roster=list(roster), state=state, salary_cap_space=cap_space, payroll=payroll,
                           ha_usato_mle=False, ha_usato_bae=False, is_hard_capped=False)


def market(day=1, teams=(), previous=None):
    fa = FreeAgency.__new__(FreeAgency)
    fa.current_day = day
    fa.torneo = SimpleNamespace(min_salary=1.1, mle_value=5.0)
    fa._get_cached_salary_request = lambda p: p.ask
    fa._get_cached_team_state = lambda t: t.state
    fa.squadre = list(teams)
    fa.squadre_precedenti = dict(previous or {})
    fa.user_offers, fa.ai_offers, fa.signings = {}, {}, []
    fa.squadra_giocatore = None
    return fa


class EarlyFloorTests(unittest.TestCase):
    def test_a_33_year_old_star_turns_down_the_minimum_on_day_one(self):
        fa = market()
        d = fa.dettaglio_punteggio(player(), team("Raptors"), 1.3)
        self.assertEqual(d["rejected"], {"below_pct": 70})

    def test_after_the_early_days_the_old_rules_hold(self):
        fa = market(day=CONFIG.CONTRACTS.FA_EARLY_FLOOR_DAYS + 1)
        self.assertIsNone(fa.dettaglio_punteggio(player(), team("Raptors"), 1.3)["rejected"])

    def test_an_old_ring_chasing_star_asks_only_a_full_mle(self):
        fa = market()
        kg = player("KG", ovr=87, age=35, ask=16.0)
        self.assertIsNone(fa.dettaglio_punteggio(kg, team("Raptors"), 5.0)["rejected"])   # the full MLE
        self.assertIsNotNone(fa.dettaglio_punteggio(kg, team("Raptors"), 1.6)["rejected"])

    def test_the_mle_relief_needs_a_ring_chase(self):
        fa = market()
        kg = player("KG", ovr=87, age=35, ask=16.0)
        self.assertIsNotNone(fa.dettaglio_punteggio(kg, team("Bobcats", state="Mediocre"), 5.0)["rejected"])

    def test_a_rotation_veteran_still_ring_chases_at_the_minimum(self):
        fa = market()
        vet = player("Vet", ovr=78, age=34, ask=4.0)
        self.assertIsNone(fa.dettaglio_punteggio(vet, team("Raptors"), 1.1)["rejected"])


class WalkVetoTests(unittest.TestCase):
    def setUp(self):
        self.old = team("Mavericks", state="Mediocre")
        self.star = player(walks="hopeless team")

    def fa(self, day, others):
        fa = market(day=day, teams=[self.old] + others, previous={self.star.nome: self.old})
        fa.is_rfa = lambda p: False
        fa._get_signing_tool = lambda s, ask, p: ("CAP_SPACE", s.salary_cap_space)
        return fa

    def test_the_veto_holds_in_the_first_days(self):
        fa = self.fa(CONFIG.CONTRACTS.FA_WALK_LIFT_DAY - 1, [team("Bulls", cap_space=2.0)])
        self.assertTrue(fa._refused_by(self.old, self.star))

    def test_the_veto_falls_when_nobody_else_can_pay_him(self):
        fa = self.fa(CONFIG.CONTRACTS.FA_WALK_LIFT_DAY, [team("Bulls", cap_space=2.0)])
        self.assertFalse(fa._refused_by(self.old, self.star))

    def test_the_veto_holds_when_a_team_can_pay_him(self):
        fa = self.fa(CONFIG.CONTRACTS.FA_WALK_LIFT_DAY, [team("Bulls", cap_space=15.0)])
        self.assertTrue(fa._refused_by(self.old, self.star))


class PileupTests(unittest.TestCase):
    def test_one_cheap_veteran_per_summer_over_the_cap(self):
        raptors = team("Raptors")
        fa = market(teams=[raptors])
        kg = player("KG", ovr=87, age=35)
        self.assertFalse(fa._pileup_blocked(raptors, kg, "MINIMUM"))
        fa.signings.append({"team": "Raptors", "player": "Dirk", "pileup": True})
        self.assertTrue(fa._pileup_blocked(raptors, kg, "MINIMUM"))
        self.assertTrue(fa._pileup_blocked(raptors, kg, "FULL_MLE"))
        self.assertFalse(fa._pileup_blocked(raptors, kg, "CAP_SPACE"))
        self.assertFalse(fa._pileup_blocked(raptors, player("Young", ovr=87, age=26), "MINIMUM"))
        self.assertFalse(fa._pileup_blocked(team("Bulls"), kg, "MINIMUM"))

    def test_blocked_offers_leave_the_race(self):
        raptors, bulls = team("Raptors"), team("Bulls")
        fa = market(day=CONFIG.CONTRACTS.FA_EARLY_FLOOR_DAYS + 1, teams=[raptors, bulls])
        fa.soglia_firma = lambda p, d: 50.0
        kg = player("KG", ovr=87, age=35, ask=5.0)
        fa.signings.append({"team": "Raptors", "player": "Dirk", "pileup": True})
        fa.ai_offers["KG"] = [{"team": "Raptors", "salary": 1.1, "years": 1, "tool": "MINIMUM"},
                              {"team": "Bulls", "salary": 1.1, "years": 1, "tool": "MINIMUM"}]
        race = fa.classifica_offerte(kg)
        self.assertEqual([o["team"] for o in race["offers"]], ["Bulls"])


class ExtensionSalaryTests(unittest.TestCase):
    def test_the_extension_survives_a_reload(self):
        p = SimpleNamespace(nome="Deron", ovr=84, eta=22, morale=70, is_flight_risk=False, walks_away="",
                            contract=Contract(anni_rimanenti=1, salario_annuale=3.94))
        t = SimpleNamespace(nome="Jazz", payroll=30.0, personalita_proprietario="Normale")
        e = ContractExtensions.__new__(ContractExtensions)
        e.torneo, e.log = SimpleNamespace(season_number=1, second_apron=70.0, luxury_tax_threshold=55.0,
                                          first_apron=60.0), []
        e._outcome = lambda *a: None
        e._max_contract = lambda: 30.0
        e.compute_player_market_request = lambda pl, option_type="None": 15.0
        renewal = SimpleNamespace(years=4, salary_mult=1.0)
        with mock.patch("offseason.contract_extensions.contracts.renewal_offer", return_value=renewal), \
                mock.patch("offseason.contract_extensions.contracts.context_for",
                           return_value=SimpleNamespace(era=SimpleNamespace(star=84), plan="PLAYOFF")), \
                mock.patch.object(ContractExtensions, "calculate_extension_score", return_value=(100.0, "ok")), \
                mock.patch("offseason.contract_extensions.add_news"), \
                mock.patch("offseason.contract_extensions.random.random", return_value=0.9):
            self.assertTrue(e._attempt_extension(t, p))
        c = p.contract
        self.assertEqual(c.anni_rimanenti, 5)
        self.assertEqual(len(c.salari_per_anno), 5)
        self.assertAlmostEqual(c.salario_annuale, 3.94)          # this season: the rookie deal
        self.assertAlmostEqual(c.salari_per_anno[1], 15.0)       # the extension, from next season
        reloaded = Contract(anni_rimanenti=c.anni_rimanenti, salario_annuale=c.salario_annuale,
                            salari_per_anno=list(c.salari_per_anno))
        reloaded.salari_per_anno.pop(0)                          # the season turns
        reloaded = Contract(anni_rimanenti=4, salario_annuale=0.0, salari_per_anno=reloaded.salari_per_anno)
        self.assertAlmostEqual(reloaded.salario_annuale, 15.0)


if __name__ == "__main__":
    unittest.main()
