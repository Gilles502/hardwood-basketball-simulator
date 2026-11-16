"""AI GM layer 1: each CPU team keeps a log of its moves (core/front_office/moves.py and the engine hooks)."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office.models import TeamPlan
from core.front_office.moves import record_move
from core.front_office.state import FrontOfficeState
from core.models import Giocatore
from offseason.draft import Draft
from offseason.free_agency import FreeAgency
from trades.trade_finder import TradeFinder
from trades.trade_validator import TradeValidator


def make_player(name, ovr=70, age=27, salary=5.0):
    p = Giocatore.__new__(Giocatore)
    p.nome, p.valutazione, p.eta, p.ruolo = name, ovr, age, "SG"  # ovr is an alias of valutazione
    p.contract = SimpleNamespace(salario_annuale=salary, anni_rimanenti=2, player_option=False, team_option=False)
    return p


def make_team(name, n=13):
    team = SimpleNamespace(nome=name, roster=[make_player(f"{name}-{i}") for i in range(n)],
                           scegli_quintetto_iniziale=lambda: None,
                           log_financial_event=lambda *a, **k: None, payroll=0.0, vittorie=0, sconfitte=0)
    return team


def make_torneo(teams, user_team=None, plans=None, fase="SEASON"):
    fo = FrontOfficeState()
    for name, state in (plans or {}).items():
        fo.plans[name] = TeamPlan(state=state, since_year=2002, seasons_held=1, reason="", history=[])
    torneo = SimpleNamespace(
        squadre=teams, season_number=2, starting_year=2002, anno_corrente=2003, fase_torneo=fase,
        user_role="gm_coach" if user_team else "spectator",
        squadra_giocatore=next((t for t in teams if t.nome == user_team), None),
        front_office=fo, pick_ownership={1: {"R1-B": "B"}, 2: {}}, pick_protections={1: {}, 2: {}},
        offseason_log_data={},
    )
    torneo._determina_stato_squadra = lambda s: "Mediocre"  # the trade's pick protection asks for it
    return torneo


class RecordMoveTests(unittest.TestCase):
    def test_record_move_fields_and_cap(self):
        t = make_torneo([make_team("A")], plans={"A": "REBUILDER"})
        for i in range(45):
            if i == 44:
                t.front_office.plans["A"].state = "PLAYOFF"
            record_move(t, "A", "trade", f"move {i}")
        log = t.front_office.moves["A"]
        self.assertEqual(len(log), CONFIG.FRONT_OFFICE.MOVES_KEEP_PER_TEAM)
        self.assertEqual(log[-1]["text"], "move 44")
        self.assertEqual(log[-1]["plan"], "PLAYOFF")
        self.assertEqual(log[0]["plan"], "REBUILDER")
        self.assertEqual(log[-1]["season"], 2)
        self.assertEqual(log[-1]["year"], 2003)
        self.assertEqual(log[-1]["kind"], "trade")
        self.assertEqual(log[-1]["window"], "Season")

    def test_windows(self):
        t = make_torneo([make_team("A")])
        t._deadline_window = True
        record_move(t, "A", "trade", "x")
        t._deadline_window = False
        t.fase_torneo = "OFFSEASON"
        record_move(t, "A", "trade", "x")
        record_move(t, "A", "draft", "x")
        record_move(t, "A", "signing", "x")
        self.assertEqual([m["window"] for m in t.front_office.moves["A"]], ["Deadline", "Offseason", "Draft", "FA"])

    def test_user_team_not_logged(self):
        t = make_torneo([make_team("Mine"), make_team("B")], user_team="Mine")
        record_move(t, "Mine", "trade", "x")
        self.assertNotIn("Mine", t.front_office.moves)
        record_move(SimpleNamespace(), "B", "trade", "x")  # no front office: no-op, no crash


class HookTests(unittest.TestCase):
    def test_trade_logs_both_sides(self):
        a, b = make_team("A"), make_team("B")
        t = make_torneo([a, b], plans={"A": "CONTENDER", "B": "REBUILDER"})
        tf = TradeFinder.__new__(TradeFinder)
        tf.torneo, tf.squadre, tf.squadra_giocatore, tf.logscambi = t, [a, b], None, []
        star, bench = a.roster[0], b.roster[0]
        with mock.patch.object(TradeValidator, "validate_trade", return_value=(True, "")), \
                mock.patch.object(TradeFinder, "_log_trade_to_file"), \
                mock.patch.object(TradeFinder, "_record_trade_analytics_snapshot"), \
                mock.patch("core.news_generator.add_news"):
            ok = tf.execute_trade(a, b, [star], [bench, "1:R1-B"])
        self.assertTrue(ok)
        a_log, b_log = t.front_office.moves["A"], t.front_office.moves["B"]
        self.assertEqual(len(a_log), 1)
        self.assertEqual(len(b_log), 1)
        self.assertEqual(a_log[0]["text"], f"Got {bench.nome}, 2004 R1 (B) for {star.nome}")
        self.assertEqual(b_log[0]["text"], f"Got {star.nome} for {bench.nome}, 2004 R1")
        self.assertEqual(a_log[0]["plan"], "CONTENDER")

    def make_fa(self, t, teams, previous):
        fa = FreeAgency.__new__(FreeAgency)
        fa.torneo, fa.squadre, fa.squadra_giocatore = t, teams, None
        fa.squadre_precedenti = previous
        fa.unrestricted_free_agents, fa.ai_offers = [], {}
        fa.signings_log, fa.log_fa, fa.signings, fa.current_day = [], [], [], 3
        fa._invalidate_team_cache = lambda s: None
        fa._get_role_need = lambda s, r: True
        return fa

    def test_signing_and_let_walk(self):
        a, b = make_team("A"), make_team("B")
        t = make_torneo([a, b], fase="OFFSEASON")
        walker = make_player("Old Guard", ovr=78, age=31)
        walker.anni_nella_squadra = 10
        fa = self.make_fa(t, [a, b], {"Old Guard": b})
        fa._firma_giocatore(a, walker, 12.5, "CAP SPACE", 3)
        self.assertEqual(walker.anni_nella_squadra, 0)   # a new team: loyalty starts again
        self.assertEqual(t.front_office.moves["A"][0]["kind"], "signing")
        self.assertEqual(t.front_office.moves["A"][0]["text"], "Signed Old Guard (31, 78 OVR) for 3 yrs at $12.5M")
        self.assertEqual(t.front_office.moves["B"][0]["kind"], "let_walk")
        self.assertEqual(t.front_office.moves["B"][0]["text"], "Let Old Guard (31) walk")
        # Roster savers are not the GM's plan: nothing logged.
        filler = make_player("Filler", ovr=55)
        fa._firma_giocatore(a, filler, 1.1, "ROSTER SAVER SIGNING", 1)
        self.assertEqual(len(t.front_office.moves["A"]), 1)
        # Re-signing with his own team is no "walk".
        stay = make_player("Stays", ovr=70)
        fa.squadre_precedenti["Stays"] = a
        stay.anni_nella_squadra = 6
        fa._firma_giocatore(a, stay, 4.0, "BIRD RIGHTS", 2)
        self.assertEqual(stay.anni_nella_squadra, 6)
        self.assertEqual([m["kind"] for m in t.front_office.moves["A"]], ["signing", "signing"])
        self.assertEqual(len(t.front_office.moves["B"]), 1)

    def test_draft_pick_logged(self):
        a = make_team("A")
        t = make_torneo([a], fase="OFFSEASON")
        d = Draft.__new__(Draft)
        d.torneo, d.squadre, d.risultati_draft = t, [a] + [make_team(f"T{i}") for i in range(29)], []
        rookie = make_player("Kid", ovr=68, age=19)
        rookie.potenziale, rookie.provenance, rookie.pedigree = 82, "College", 3
        with mock.patch("core.models.ACTIVE_TOURNAMENT", None):
            d._registra_scelta(rookie, 2, 5, "A", "A")
        self.assertEqual(t.front_office.moves["A"][0]["text"], "Drafted Kid at #35")
        self.assertEqual(t.front_office.moves["A"][0]["window"], "Draft")


if __name__ == "__main__":
    unittest.main()
