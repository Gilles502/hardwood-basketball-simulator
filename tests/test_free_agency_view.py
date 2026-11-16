"""Free agency as the page shows it: the interest score and its parts, tonight's bar, the offers on the table.
The market rules must not change, so the first test pins today's scores."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office.contracts import loyalty
from offseason.free_agency import FreeAgency


def player(name="Hale", ovr=82, age=27, role="SG", morale=70, ask=10.0):
    return SimpleNamespace(nome=name, ovr=ovr, eta=age, ruolo=role, morale=morale, potenziale=ovr + 2, ask=ask)


def team(name, roster=(), state="Playoff Team"):
    return SimpleNamespace(nome=name, roster=list(roster), state=state)


def market(day=1, user=None, previous=None):
    fa = FreeAgency.__new__(FreeAgency)
    fa.current_day = day
    fa.torneo = SimpleNamespace(min_salary=1.1)
    fa._get_cached_salary_request = lambda p: p.ask
    fa._get_cached_team_state = lambda t: t.state
    fa.squadre_precedenti = dict(previous or {})
    fa.user_offers = {}
    fa.ai_offers = {}
    fa.squadra_giocatore = user
    return fa


def roster_player(name, ovr, role, age=28, pot=None):
    return SimpleNamespace(nome=name, ovr=ovr, ruolo=role, eta=age, potenziale=pot or ovr)


CASES = {
    # name: (player, team, offer, option)
    "normal": (player(), team("Raptors", [roster_player("Pryor", 71, "SG")], "Contender"), 10.0, "None"),
    "lowball": (player(ovr=86), team("Raptors"), 6.0, "None"),
    "balloon": (player(), team("Raptors"), 13.0, "None"),
    "superteam_veteran": (player(age=31, ovr=80), team("Lakers", [roster_player("A", 90, "C"), roster_player("B", 88, "SF")],
                                                       "Defending Champion"), 9.0, "PO"),
    "congestion": (player(ovr=83, age=26), team("Suns", [roster_player("Star", 89, "SG")], "Mediocre"), 10.0, "TO"),
    "rebuilding": (player(ovr=86, age=25), team("Hornets", [roster_player("Kid", 70, "PG", age=21, pot=88)], "Rebuilding"), 10.0, "None"),
}

# Totals of _calcola_punteggio_accettazione_cached before the refactor (day 1).
EXPECTED_TOTALS = {"normal": 83.0, "lowball": 0.0, "balloon": 100.0, "superteam_veteran": 100.0,
                   "congestion": 21.545454545454547, "rebuilding": 50.5}


class ScoreUnchangedTests(unittest.TestCase):
    def test_totals_unchanged(self):
        fa = market()
        for name, (p, t, offer, option) in CASES.items():
            with self.subTest(case=name):
                self.assertAlmostEqual(fa._calcola_punteggio_accettazione_cached(p, t, offer, option_type=option),
                                       EXPECTED_TOTALS[name], places=6)


class ScorePartsTests(unittest.TestCase):
    def test_parts_add_up_to_raw_and_total_is_clamped(self):
        fa = market()
        for name, (p, t, offer, option) in CASES.items():
            if name == "lowball":
                continue
            with self.subTest(case=name):
                d = fa.dettaglio_punteggio(p, t, offer, option_type=option)
                self.assertIsNone(d["rejected"])
                self.assertAlmostEqual(sum(part["value"] for part in d["parts"]), d["raw"], places=6)
                self.assertAlmostEqual(d["total"], max(0, min(100, d["raw"])), places=6)
                self.assertAlmostEqual(d["total"], EXPECTED_TOTALS[name], places=6)
                self.assertEqual([part["key"] for part in d["parts"]],
                                 ["base", "money", "money_bonus", "morale", "stars", "role", "team_state", "age", "market_day"])

    def test_value_is_the_option_adjusted_market_value(self):
        fa = market()
        p, t, offer, _ = CASES["normal"]
        self.assertAlmostEqual(fa.dettaglio_punteggio(p, t, offer, option_type="TO")["value"], 11.0)

    def test_lowball_is_a_reject_not_parts(self):
        p, t, offer, option = CASES["lowball"]
        d = market().dettaglio_punteggio(p, t, offer, option_type=option)
        self.assertEqual(d["rejected"], {"below_pct": 75})
        self.assertEqual(d["total"], 0)


def offer(team_name, salary, years=2, option="None"):
    return {"team": team_name, "salary": salary, "years": years, "option_type": option}


class BarTests(unittest.TestCase):
    def test_bar_matches_formula(self):
        self.assertAlmostEqual(market().soglia_firma(player(ovr=86, morale=75), 1), 80.0)
        self.assertAlmostEqual(market().soglia_firma(player(ovr=70, morale=65), 4), 46.5)
        self.assertAlmostEqual(market().soglia_firma(player(ovr=70, morale=0), 12), 10.0)


class RaceTests(unittest.TestCase):
    def setUp(self):
        self.p = player(ask=10.0)
        self.raptors = team("Raptors", [roster_player("Pryor", 71, "SG")], "Contender")
        self.suns = team("Suns", [], "Mediocre")

    def race_market(self, day=1, previous=None):
        fa = market(day=day, user=self.raptors, previous=previous)
        fa.squadre = [self.raptors, self.suns]
        return fa

    def test_offers_sorted_and_user_flagged(self):
        fa = self.race_market()
        fa.user_offers[self.p.nome] = offer("Raptors", 10.0)
        fa.ai_offers[self.p.nome] = [offer("Suns", 10.0)]
        race = fa.classifica_offerte(self.p)
        self.assertEqual([o["team"] for o in race["offers"]], ["Raptors", "Suns"])
        self.assertTrue(race["offers"][0]["is_user"])
        self.assertEqual(race["leader"], "Raptors")
        self.assertAlmostEqual(race["bar_tonight"], fa.soglia_firma(self.p, 1))
        self.assertAlmostEqual(race["bar_tomorrow"], fa.soglia_firma(self.p, 2))

    def test_previous_team_bonus_only_on_leader(self):
        fa = self.race_market(previous={self.p.nome: self.suns})
        fa.user_offers[self.p.nome] = offer("Raptors", 10.0)
        fa.ai_offers[self.p.nome] = [offer("Suns", 10.0)]
        self.p.anni_nella_squadra, self.p.morale = 4, 70   # loyalty 16 (4 seasons x LOYALTY_PER_YEAR)
        race = fa.classifica_offerte(self.p)
        self.assertEqual(race["leader"], "Raptors")  # Suns are behind without the bonus: no loyalty for them
        self.assertFalse(any(o["previous_team_bonus"] for o in race["offers"]))
        self.assertTrue(all(o["loyalty_bonus"] == 0.0 for o in race["offers"]))
        fa.user_offers.clear()
        race = fa.classifica_offerte(self.p)
        self.assertEqual(race["leader"], "Suns")
        self.assertTrue(race["offers"][0]["previous_team_bonus"])
        self.assertAlmostEqual(race["offers"][0]["loyalty_bonus"], loyalty(self.p, self.suns))
        self.assertAlmostEqual(race["leader_score"], race["offers"][0]["score"] + loyalty(self.p, self.suns))

    def test_a_walker_refuses_his_old_team(self):
        fa = self.race_market(previous={self.p.nome: self.suns})
        fa.is_rfa = lambda p: False
        self.p.walks_away = "hopeless team"
        d = fa.dettaglio_punteggio(self.p, self.suns, 10.0)
        self.assertEqual(d["rejected"], {"walks": "hopeless team"})
        self.assertEqual(d["total"], 0.0)
        self.assertIsNone(fa.dettaglio_punteggio(self.p, self.raptors, 10.0)["rejected"])

    def test_an_rfa_cannot_walk(self):
        fa = self.race_market(previous={self.p.nome: self.suns})
        fa.is_rfa = lambda p: True
        self.p.walks_away = "hopeless team"
        self.assertIsNone(fa.dettaglio_punteggio(self.p, self.suns, 10.0)["rejected"])

    def test_would_sign_only_at_or_above_bar(self):
        fa = self.race_market()
        fa.ai_offers[self.p.nome] = [offer("Suns", 10.0)]
        race = fa.classifica_offerte(self.p)
        self.assertEqual(race["would_sign_with"] is not None, race["leader_score"] >= race["bar_tonight"])
        fa.user_offers[self.p.nome] = offer("Raptors", 10.0)
        race = fa.classifica_offerte(self.p)
        self.assertEqual(race["would_sign_with"], "Raptors")  # 83 vs a bar of 75

    def test_last_day_has_no_tomorrow(self):
        race = self.race_market(day=CONFIG.OFFSEASON.FREE_AGENCY_DAYS).classifica_offerte(self.p)
        self.assertIsNone(race["bar_tomorrow"])
        self.assertIsNone(race["leader"])
        self.assertEqual(race["offers"], [])

    def test_extra_offer_replaces_user_offer(self):
        fa = self.race_market()
        fa.user_offers[self.p.nome] = offer("Raptors", 2.0)
        race = fa.classifica_offerte(self.p, extra_offer=offer("Raptors", 12.0))
        self.assertEqual(len(race["offers"]), 1)
        self.assertEqual(race["offers"][0]["salary"], 12.0)
        self.assertEqual(fa.user_offers[self.p.nome]["salary"], 2.0)


class SigningAndPreviewTests(unittest.TestCase):
    def setUp(self):
        self.p = player(ask=10.0)
        self.raptors = team("Raptors", [roster_player("Pryor", 71, "SG")], "Contender")
        self.raptors.salary_cap_space = 50.0
        self.raptors.payroll = 100.0
        self.raptors.is_hard_capped = False
        self.suns = team("Suns", [], "Mediocre")
        for t in (self.raptors, self.suns):
            t.log_financial_event = lambda *args: None
        fa = market(user=self.raptors)
        fa.torneo = SimpleNamespace(min_salary=1.1, salary_cap=155.0, first_apron=195.0)
        fa.squadre = [self.raptors, self.suns]
        fa.unrestricted_free_agents = [self.p]
        fa.signings_log, fa.log_fa, fa.signings = [], [], []
        fa.pending_rfa_match = None
        fa.is_rfa = lambda pl: False
        fa._invalidate_team_cache = lambda t: None
        fa._get_role_need = lambda t, role: True
        self.fa = fa

    def test_signing_records_beaten_offers(self):
        self.fa.user_offers[self.p.nome] = {"team": "Raptors", "salary": 10.0, "years": 2, "tool": "CAP_SPACE", "option_type": "None"}
        self.fa.ai_offers[self.p.nome] = [{"team": "Suns", "salary": 9.0, "years": 3, "tool": "CAP_SPACE", "option_type": "None"}]
        self.fa._resolve_offers_for_day()
        self.assertEqual(self.fa.signings, [{
            "player": "Hale", "role": "SG", "ovr": 82, "team": "Raptors", "salary": 10.0, "years": 2, "option_type": "None",
            "day": 1, "beat": [{"team": "Suns", "salary": 9.0, "years": 3, "raised": 0}],
            "previous_team": None, "raised": 0, "pileup": False,
        }])

    def test_preview_does_not_touch_offers(self):
        self.fa.ai_offers[self.p.nome] = [{"team": "Suns", "salary": 9.0, "years": 3, "tool": "CAP_SPACE", "option_type": "None"}]
        before = (dict(self.fa.user_offers), {k: list(v) for k, v in self.fa.ai_offers.items()})
        preview = self.fa.anteprima_offerta("Hale", 12.0, 3, "None", 0.05)
        self.assertEqual((self.fa.user_offers, self.fa.ai_offers), before)
        self.assertTrue(preview["allowed"])
        self.assertEqual(preview["tool"], "CAP_SPACE")
        self.assertIsNone(preview["reason"])
        self.assertAlmostEqual(preview["total_value"], 37.83, places=2)
        self.assertEqual(preview["race"]["offers"][0]["team"], "Raptors")
        self.assertEqual(preview["race"]["offers"][0]["salary"], 12.0)
        self.assertGreater(preview["score"]["total"], 0)

    def test_preview_reports_reason_when_not_allowed(self):
        self.raptors.roster = [roster_player(f"P{i}", 70, "SF") for i in range(CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT)]
        preview = self.fa.anteprima_offerta("Hale", 12.0, 3, "None", 0.05)
        self.assertFalse(preview["allowed"])
        self.assertIsNone(preview["tool"])
        self.assertTrue(preview["reason"].startswith("Roster full"))


class BitExactTests(unittest.TestCase):
    def test_balloon_offer_total_is_bit_exact(self):
        # A 1.39x offer gets the balloon bonus; the old code added it after the money term, and so must the new one.
        fa = market(day=3)
        p = player(ovr=70, age=30, role="SF", morale=45, ask=9.4)
        t = team("Hornets", [], "Rebuilding")
        self.assertEqual(fa._calcola_punteggio_accettazione_cached(p, t, 13.1), 65.0936170212766)


class RaceJsonTests(unittest.TestCase):
    def test_race_json_keeps_the_bidding_fields(self):
        import server
        offer = {"team": "Knicks", "salary": 13.0, "years": 3, "tool": "CAP_SPACE"}
        race = {"offers": [{"team": "Knicks", "salary": 13.0, "years": 3, "option_type": "None", "score": 70.0,
                            "is_user": False, "previous_team_bonus": False, "loyalty_bonus": 0.0, "offer": offer,
                            "first": {"day": 1, "salary": 12.0}, "history": [{"day": 3, "salary": 13.0}]}],
                "leader": "Knicks", "leader_score": 70.0, "bar_tonight": 75.0, "bar_tomorrow": 70.0,
                "would_sign_with": None,
                "withdrawn": [{"team": "Sixers", "salary": 12.5, "years": 3, "day": 2, "reason": "over budget"}]}
        out = server._fa_race_json(race)
        o = out["offers"][0]
        self.assertNotIn("offer", o)
        self.assertEqual(o["first"], {"day": 1, "salary": 12.0})
        self.assertEqual(o["history"], [{"day": 3, "salary": 13.0}])
        self.assertEqual(o["loyalty_bonus"], 0.0)
        self.assertEqual(out["withdrawn"][0]["reason"], "over budget")

    def test_state_sends_tonights_moves(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server.py"),
                   encoding="utf-8").read()
        self.assertTrue('"night_moves": list(getattr(ACTIVE_FREE_AGENCY_INSTANCE, \'night_moves\', []))' in src)


class FinalMarketTests(unittest.TestCase):
    """Once the market closes the server drops it; the page must still get the last state (recap + Signed list)."""

    def test_state_serves_the_closed_market(self):
        import server
        final = {"success": True, "completed": True, "current_day": 12, "days_total": 12, "signings": [{"player": "A"}],
                 "players": [], "pending_rfa_match": None, "user_offers": {}, "user_team": {"nome": "Raptors"}}
        saved = (server.ACTIVE_FREE_AGENCY_INSTANCE, server.SIMULATION_TOURNAMENT)
        try:
            server.ACTIVE_FREE_AGENCY_INSTANCE = None
            server.SIMULATION_TOURNAMENT = SimpleNamespace(offseason_log_data={"fa_final": final}, squadra_giocatore=None)
            response = server.app.test_client().get('/api/offseason/free_agency/state')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["signings"], [{"player": "A"}])
            self.assertTrue(response.get_json()["completed"])
            server.SIMULATION_TOURNAMENT = SimpleNamespace(offseason_log_data={}, squadra_giocatore=None)
            self.assertEqual(server.app.test_client().get('/api/offseason/free_agency/state').status_code, 400)
        finally:
            server.ACTIVE_FREE_AGENCY_INSTANCE, server.SIMULATION_TOURNAMENT = saved


if __name__ == '__main__':
    fa = market()
    for name, (p, t, offer, option) in CASES.items():
        print(name, fa._calcola_punteggio_accettazione_cached(p, t, offer, option_type=option))
