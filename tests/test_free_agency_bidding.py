"""Free agency bidding: CPU teams that really want a player raise when outbid, up to a ceiling, then pull out."""
import unittest
from types import SimpleNamespace

from core.config import CONFIG
from offseason.free_agency import FreeAgency

C = CONFIG.CONTRACTS


def market(teams, ask=10.0, budget=None, plans=None):
    fa = FreeAgency.__new__(FreeAgency)
    fa.current_day, fa.squadre, fa.squadra_giocatore = 3, teams, None
    fa.torneo = SimpleNamespace(min_salary=1.0)
    fa.squadre_precedenti, fa.user_offers, fa.ai_offers, fa.night_moves = {}, {}, {}, []
    fa.player = SimpleNamespace(nome="Hale", ovr=86, eta=28, ruolo="SG", morale=70, anni_nella_squadra=0)
    fa.unrestricted_free_agents = [fa.player]
    fa._calcola_richiesta_salariale = lambda p, premi=True: ask
    fa._get_cached_team_state = lambda t: (plans or {}).get(t.nome, "Mediocre")
    # The player's score grows with the money: the richest offer leads
    fa._calcola_punteggio_accettazione_cached = lambda p, t, salary, option_type="None": salary * 5
    budget = budget or {}
    fa._get_signing_tool = lambda t, request, p=None: ("CAP_SPACE", min(request, budget.get(t.nome, 99.0)))
    fa.soglia_firma = lambda p, day: 99.0   # nobody signs tonight
    return fa


def cpu_offer(team, salary, wanted=True, day=1, **extra):
    o = {"team": team, "salary": salary, "years": 3, "tool": "CAP_SPACE", "option_type": "None",
         "first": {"day": day, "salary": salary}, "history": [], "wanted": wanted}
    o.update(extra)
    return o


def teams(*names):
    return [SimpleNamespace(nome=n, roster=[]) for n in names]


class RaiseTests(unittest.TestCase):
    def test_an_outbid_team_that_wants_him_raises(self):
        fa = market(teams("Knicks", "Sixers"))
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", 12.0), cpu_offer("Sixers", 13.0)]
        fa._raise_or_withdraw(3)
        knicks = fa.ai_offers["Hale"][0]
        self.assertAlmostEqual(knicks["salary"], 12.0 + 10.0 * C.FA_RAISE_STEP)
        self.assertEqual(knicks["history"], [{"day": 3, "salary": knicks["salary"]}])
        self.assertEqual([m["type"] for m in fa.night_moves], ["raise"])
        self.assertEqual(fa.ai_offers["Hale"][1]["salary"], 13.0)   # the leader does not raise

    def test_a_team_that_does_not_want_him_does_not_raise(self):
        fa = market(teams("Knicks", "Sixers"))
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", 12.0, wanted=False), cpu_offer("Sixers", 13.0)]
        fa._raise_or_withdraw(3)
        self.assertEqual(fa.ai_offers["Hale"][0]["salary"], 12.0)
        self.assertNotIn("withdrawn", fa.ai_offers["Hale"][0])

    def test_the_ceiling_stops_raises_then_it_pulls_out(self):
        fa = market(teams("Knicks", "Sixers"))
        ceiling = 12.0 * C.FA_RAISE_CEILING["MIDDLE"]   # a "Mediocre" team is a MIDDLE plan
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", ceiling, first={"day": 1, "salary": 12.0}), cpu_offer("Sixers", 20.0)]
        fa._raise_or_withdraw(3)
        knicks = fa.ai_offers["Hale"][0]
        self.assertEqual(knicks["withdrawn"], {"day": 3, "reason": "price too high"})
        self.assertAlmostEqual(knicks["salary"], ceiling)
        self.assertEqual([m["type"] for m in fa.night_moves], ["out"])

    def test_money_limit_pulls_out_over_budget(self):
        fa = market(teams("Knicks", "Sixers"), budget={"Knicks": 11.0})   # cap space shrank under its offer
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", 12.0), cpu_offer("Sixers", 13.0)]
        fa._raise_or_withdraw(3)
        knicks = fa.ai_offers["Hale"][0]
        self.assertEqual(knicks["withdrawn"]["reason"], "over budget")
        self.assertEqual(knicks["salary"], 12.0)   # never lowered

    def test_a_contender_has_more_room(self):
        self.assertGreater(C.FA_RAISE_CEILING["CONTENDER"], C.FA_RAISE_CEILING["REBUILDER"])
        fa = market(teams("Knicks", "Sixers"), plans={"Knicks": "Contender"})
        self.assertEqual(fa._team_plan(fa.squadre[0]), "CONTENDER")
        self.assertEqual(fa._team_plan(fa.squadre[1]), "MIDDLE")


class NightAuctionTests(unittest.TestCase):
    """A star would sign the first night with the first good offer: the outbid teams bid again that same night,
    round after round, until nobody raises (each team stops at its ceiling or pulls out)."""
    def test_the_night_auction_runs_until_nobody_raises(self):
        fa = market(teams("Knicks", "Sixers"), plans={"Knicks": "Contender", "Sixers": "Contender"})
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", 12.0), cpu_offer("Sixers", 12.5)]
        fa._night_auction(1)
        knicks, sixers = fa.ai_offers["Hale"]
        live = [o for o in (knicks, sixers) if not o.get("withdrawn")]
        self.assertEqual(len(live), 1)                                    # one team is left standing
        self.assertTrue(any(len(o["history"]) >= 2 for o in (knicks, sixers)))   # several raises in one night
        self.assertLessEqual(knicks["salary"], 12.0 * C.FA_RAISE_CEILING["CONTENDER"] + 1e-9)
        self.assertLessEqual(sixers["salary"], 12.5 * C.FA_RAISE_CEILING["CONTENDER"] + 1e-9)

    def test_at_the_score_cap_the_richer_offer_leads(self):
        fa = market(teams("Knicks", "Sixers"))
        fa._calcola_punteggio_accettazione_cached = lambda p, t, salary, option_type="None": 100.0   # both capped
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", 12.0), cpu_offer("Sixers", 13.0)]
        self.assertEqual(fa.classifica_offerte(fa.player)["leader"], "Sixers")

    def test_simulate_day_holds_the_auction_before_the_player_chooses(self):
        import inspect
        src = inspect.getsource(FreeAgency.simulate_day)
        self.assertLess(src.index("self._night_auction("), src.index("self._resolve_offers_for_day()"))


class RaceTests(unittest.TestCase):
    def test_withdrawn_offers_are_out_of_the_race(self):
        fa = market(teams("Knicks", "Sixers"))
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", 30.0, withdrawn={"day": 2, "reason": "over budget"}),
                                cpu_offer("Sixers", 13.0)]
        race = fa.classifica_offerte(fa.player)
        self.assertEqual([o["team"] for o in race["offers"]], ["Sixers"])
        self.assertEqual(race["leader"], "Sixers")
        self.assertEqual(race["withdrawn"], [{"team": "Knicks", "salary": 30.0, "years": 3, "day": 2,
                                              "reason": "over budget"}])

    def test_a_player_with_only_withdrawn_offers_does_not_crash_the_night(self):
        fa = market(teams("Knicks"))
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", 30.0, withdrawn={"day": 2, "reason": "over budget"})]
        self.assertIsNone(fa._resolve_offers_for_day())

    def test_old_offers_without_history_still_work(self):
        fa = market(teams("Knicks", "Sixers"))
        fa.ai_offers["Hale"] = [{"team": "Knicks", "salary": 12.0, "years": 2, "tool": "CAP_SPACE"},
                                {"team": "Sixers", "salary": 13.0, "years": 2, "tool": "CAP_SPACE"}]
        fa._raise_or_withdraw(3)
        race = fa.classifica_offerte(fa.player)
        self.assertEqual(race["leader"], "Sixers")
        self.assertEqual(fa.ai_offers["Hale"][0]["salary"], 12.0)
        self.assertEqual(race["withdrawn"], [])


class SigningTests(unittest.TestCase):
    def test_signing_records_previous_team_and_raises(self):
        knicks, sixers = teams("Knicks", "Sixers")
        fa = market([knicks, sixers])
        fa.squadre_precedenti = {"Hale": sixers}
        fa.signings_log, fa.log_fa = [], []
        p = fa.player
        p.walks_away = "hopeless team"
        p.contract = None
        p.squadra = None
        knicks.payroll, knicks.salary_cap_space = 50.0, 20.0
        knicks.log_financial_event = lambda *a, **k: None
        fa._get_role_need = lambda t, role: True
        from unittest import mock
        with mock.patch("offseason.free_agency.record_signing"), \
                mock.patch.object(FreeAgency, "_invalidate_team_cache", lambda self, t: None):
            fa._firma_giocatore(knicks, p, 13.0, "UFA SIGNING", 3, raised=2)
        s = fa.signings[-1]
        self.assertEqual(s["previous_team"], "Sixers")
        self.assertEqual(s["raised"], 2)
        self.assertEqual(p.walks_away, "")

    def test_signing_never_goes_over_the_max_contract(self):
        knicks, = teams("Knicks")
        fa = market([knicks])
        fa.signings_log, fa.log_fa = [], []
        p = fa.player
        p.contract, p.squadra = None, None
        knicks.payroll, knicks.salary_cap_space = 50.0, 90.0
        knicks.log_financial_event = lambda *a, **k: None
        fa._get_role_need = lambda t, role: True
        from unittest import mock
        with mock.patch("offseason.free_agency.record_signing"),                 mock.patch.object(FreeAgency, "_invalidate_team_cache", lambda self, t: None):
            fa._firma_giocatore(knicks, p, 84.2, "UFA SIGNING", 3)
        self.assertAlmostEqual(p.contract.salario_annuale, 155.0 * CONFIG.ECONOMY.MAX_CONTRACT_CAP_PCT, places=1)


class MaxContractTests(unittest.TestCase):
    """A 25-season save had CPU raises reach 55% of the cap (Jokic $84.2M on a $151.6M cap)."""

    def test_raises_stop_at_the_max_contract(self):
        fa = market(teams("Knicks", "Sixers"), ask=50.0, plans={"Knicks": "CONTENDER"})
        top = 155.0 * CONFIG.ECONOMY.MAX_CONTRACT_CAP_PCT
        fa.ai_offers["Hale"] = [cpu_offer("Knicks", 50.0), cpu_offer("Sixers", top)]
        for day in range(3, 10):
            fa._raise_or_withdraw(day)
        self.assertLessEqual(fa.ai_offers["Hale"][0]["salary"], top + 0.01)


class OwnerLimitTests(unittest.TestCase):
    def test_a_saver_owner_stops_just_over_the_tax(self):
        fa = FreeAgency.__new__(FreeAgency)
        fa.torneo = SimpleNamespace(salary_cap=151.6, luxury_tax_threshold=180.9, first_apron=190.7, second_apron=200.4)
        saver = SimpleNamespace(personalita_proprietario="Risparmiatore")
        limit = fa._determina_limite_spesa_owner(saver)
        self.assertAlmostEqual(limit, 180.9 + CONFIG.ECONOMY.LOW_OWNER_OVER_TAX_SHARE * 151.6)
        self.assertLess(limit, 190.7)   # under the first apron (a 25-season save had savers over the second)


if __name__ == "__main__":
    unittest.main()
