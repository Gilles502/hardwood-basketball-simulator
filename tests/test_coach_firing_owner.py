"""AI GM layer 3: coach firings follow the owner's patience and the team's saved plan."""
import dataclasses
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from core.config import CONFIG
from core.front_office.models import TeamPlan
from core.front_office.owners import gm_fire_reason
from core.front_office.seasons import close_season, mark_season_start
from core.front_office.state import build_front_office
from main import Tournament


def player(ovr=75):
    return SimpleNamespace(ovr=ovr, eta=27, nome="P")


def make_coach(years=3, deal=4):
    return SimpleNamespace(nome="Coach", job_security=75.0, years_with_current_team=years,
                           contratto_totale_anni=deal, championships=0, playoff_appearances=0)


def make_torneo(wins, owner="Bilanciato", plan="MIDDLE", held=2, user_role="spectator", user=False,
                years=3, losses=None, playoffs=False, plan_start=None):
    """Two teams: T is under test, Z is a filler (the champion, so it is immune)."""
    t = SimpleNamespace(nome="T", roster=[player()] * 8, vittorie=wins,
                        sconfitte=82 - wins if losses is None else losses, vittorie_attese=0,
                        personalita_proprietario=owner, coach=make_coach(years))
    z = SimpleNamespace(nome="Z", roster=[player()] * 8, vittorie=50, sconfitte=32, vittorie_attese=0,
                        personalita_proprietario="Bilanciato", coach=make_coach())
    torneo = SimpleNamespace(
        squadre=[t, z], season_number=3, starting_year=2002, anno_corrente=2004,
        user_role=user_role, squadra_giocatore=t if user else None, is_spectator=not user,
        campione=z, playoff_teams={"east": [t] if playoffs else [], "west": [z]},
        offseason_log_data={"ritiri_sviluppo": []}, unemployed_coaches=[],
    )
    states = {"CONTENDER": "Contender", "REBUILDER": "Rebuilding", "MIDDLE": "Mediocre", "PLAYOFF": "Playoff Team"}
    torneo._determina_stato_squadra = lambda s: states[plan]
    torneo.front_office = build_front_office(torneo)
    torneo.front_office.plans["T"] = TeamPlan(state=plan, since_year=2002, seasons_held=held, reason="t", history=[])
    torneo._calcola_vittorie_attese = lambda: None
    torneo._generate_coach_candidate = lambda: SimpleNamespace(nome="New", contratto_anni_rimanenti=0,
                                                               contratto_totale_anni=0)
    torneo.front_office.season_marks["T"] = {"year": 2004, "expected": 0, "last_wins": 0, "top8": []}
    if plan_start is not None:
        torneo.front_office.season_marks["T"]["plan"] = plan_start
    return torneo, t


def run_black_monday(torneo, expected):
    torneo.front_office.season_marks["T"]["expected"] = expected
    types.MethodType(Tournament._gestisci_fase_licenziamenti, torneo)()


class BlackMondayTests(unittest.TestCase):
    def test_rebuilder_on_schedule_keeps_coach(self):
        torneo, t = make_torneo(18, plan="REBUILDER", held=2)
        run_black_monday(torneo, 30)
        self.assertIsNotNone(t.coach)

    def test_contender_failing_fires_coach_and_flags_record(self):
        torneo, t = make_torneo(25, owner="Esigente", plan="CONTENDER")   # JSS 70 - 40.5 - 8 - 10 = 11.5
        run_black_monday(torneo, 52)
        self.assertIsNone(t.coach)
        self.assertIs(torneo.front_office.records["T"][-1]["coach_fired"], True)

    def test_esigente_less_patient_than_ricostruttore(self):
        scores = {}
        for owner in ("Esigente", "Ricostruttore"):
            torneo, t = make_torneo(40, owner=owner, plan="MIDDLE")   # 12 below expectations
            run_black_monday(torneo, 52)
            scores[owner] = t.coach.job_security if t.coach else None
        self.assertIsNotNone(scores["Esigente"])
        self.assertAlmostEqual(scores["Ricostruttore"] - scores["Esigente"], 20.0)

    def test_rebuild_patience_only_while_on_schedule(self):
        # Same season, same owner: 15 wins against 45 expected (JSS 7 without the rebuild patience, 32 with it).
        torneo, t = make_torneo(15, owner="Esigente", plan="REBUILDER", held=2)
        run_black_monday(torneo, 45)
        self.assertIsNotNone(t.coach)
        torneo, t = make_torneo(15, owner="Esigente", plan="REBUILDER", held=6)   # past 4 seasons + 1 grace
        run_black_monday(torneo, 45)
        self.assertIsNone(t.coach)

    def test_deadline_collapsed_contender_gets_no_rebuild_patience(self):
        # The deadline flipped the plan to a fresh REBUILDER (held 1); the season started as a contender.
        torneo, t = make_torneo(15, owner="Esigente", plan="REBUILDER", held=1, plan_start="CONTENDER")
        run_black_monday(torneo, 45)
        self.assertIsNone(t.coach)
        torneo, t = make_torneo(15, owner="Esigente", plan="REBUILDER", held=1, plan_start="REBUILDER")
        run_black_monday(torneo, 45)
        self.assertIsNotNone(t.coach)

    def test_catastrophe_fires_even_a_new_coach(self):
        # Year 1 of a 4-year deal (grace +20) and a patient owner: only the catastrophe rule fires him.
        torneo, t = make_torneo(19, owner="Ricostruttore", plan="MIDDLE", years=1)
        run_black_monday(torneo, 50)
        self.assertIsNone(t.coach)
        self.assertIs(torneo.front_office.records["T"][-1]["coach_fired"], True)
        torneo, t = make_torneo(19, owner="Ricostruttore", plan="MIDDLE", years=1)
        run_black_monday(torneo, 47)   # under 48 expected: not a catastrophe
        self.assertIsNotNone(t.coach)

    def test_user_coach_never_fired(self):
        for role in ("gm_coach", "only_coach"):
            torneo, t = make_torneo(10, plan="CONTENDER", user_role=role, user=True)
            run_black_monday(torneo, 55)
            self.assertIsNotNone(t.coach, role)


class MidSeasonTests(unittest.TestCase):
    def test_midseason_reads_saved_plan(self):
        torneo, t = make_torneo(10, losses=35, plan="REBUILDER")
        torneo._determina_stato_squadra = lambda s: "Contender"   # the roster says contender, the plan says no
        types.MethodType(Tournament._gestisci_licenziamenti_midseason, torneo)()
        self.assertIsNotNone(t.coach)
        self.assertFalse(t.coach.nome.startswith("Interim"))

    def test_midseason_fires_failing_planned_contender(self):
        torneo, t = make_torneo(10, losses=35, plan="CONTENDER")
        types.MethodType(Tournament._gestisci_licenziamenti_midseason, torneo)()
        self.assertTrue(t.coach.nome.startswith("Interim"))
        self.assertIs(torneo.front_office.season_marks["T"]["coach_fired"], True)

    def test_midseason_fires_contender_already_flipped_to_rebuilder_at_deadline(self):
        torneo, t = make_torneo(10, losses=35, plan="REBUILDER", plan_start="CONTENDER")
        types.MethodType(Tournament._gestisci_licenziamenti_midseason, torneo)()
        self.assertTrue(t.coach.nome.startswith("Interim"))
        self.assertIs(torneo.front_office.season_marks["T"]["coach_fired"], True)
        # A stale mark from a previous year falls back to the current plan (REBUILDER -> not fired).
        torneo, t = make_torneo(10, losses=35, plan="REBUILDER", plan_start="CONTENDER")
        torneo.front_office.season_marks["T"]["year"] = 2003
        types.MethodType(Tournament._gestisci_licenziamenti_midseason, torneo)()
        self.assertEqual(t.coach.nome, "Coach")


def front_office_config(**changes):
    return mock.patch.object(main, "CONFIG", dataclasses.replace(
        CONFIG, FRONT_OFFICE=dataclasses.replace(CONFIG.FRONT_OFFICE, **changes)))


class MidSeasonConfigTests(unittest.TestCase):
    def test_collapse_line_from_config(self):
        torneo, t = make_torneo(14, losses=28, plan="CONTENDER")   # 1/3 after 42 games
        with front_office_config(COACH_MIDSEASON_WIN_PCT=0.30):
            types.MethodType(Tournament._gestisci_licenziamenti_midseason, torneo)()
        self.assertEqual(t.coach.nome, "Coach")
        with front_office_config(COACH_MIDSEASON_WIN_PCT=0.40):
            types.MethodType(Tournament._gestisci_licenziamenti_midseason, torneo)()
        self.assertTrue(t.coach.nome.startswith("Interim"))


def drift_coach(security):
    return SimpleNamespace(nome="Coach", job_security=security, stile_gioco="Balanced Offense")


class DriftTests(unittest.TestCase):
    def drift(self, torneo):
        with mock.patch("core.news_generator.add_news"):
            types.MethodType(Tournament.aggiorna_job_security_giornata, torneo)()

    def test_drift_reads_the_season_start_expectation(self):
        moves = {}
        for expected in (70, 10):
            torneo, t = make_torneo(20, losses=20, plan="MIDDLE")   # .500 after 40 games
            torneo.front_office.season_marks["T"]["expected"] = expected
            t.coach = drift_coach(50.0)
            self.drift(torneo)
            moves[expected] = t.coach.job_security - 50.0
        self.assertLess(moves[70], 0)
        self.assertGreater(moves[10], 0)

    def test_drift_numbers_from_config(self):
        torneo, t = make_torneo(10, losses=30, plan="REBUILDER")
        torneo.front_office.season_marks["T"]["expected"] = 41   # .250 against .500
        t.coach = drift_coach(50.0)
        with front_office_config(COACH_DRIFT_PER_WIN_PCT=20.0, COACH_DRIFT_REBUILD_FALL=0.5):
            self.drift(torneo)
        self.assertAlmostEqual(t.coach.job_security, 50.0 - 0.25 * 20.0 * 0.5)

    def test_drift_never_fires_a_coach(self):
        """The daily drift only moves the hot-seat meter: a whole collapsing season (one call per day) keeps the
        same coach. CPU coaches are fired only by the judged checks (All-Star break, end of season); the old
        fire-at-zero rule replaced coaches and their interims every few weeks."""
        torneo, t = make_torneo(5, losses=35, plan="MIDDLE")
        torneo.front_office.season_marks["T"]["expected"] = 60
        t.coach = drift_coach(30.0)
        coach = t.coach
        for _ in range(120):
            self.drift(torneo)
        self.assertIs(t.coach, coach)
        self.assertEqual(t.coach.job_security, 0.0)
        self.assertNotEqual(torneo.front_office.season_marks["T"].get("coach_fired"), True)


def contract_coach(ovr=80):
    return SimpleNamespace(nome="Coach", eta=50, years_with_current_team=3, contratto_anni_rimanenti=1,
                           contratto_totale_anni=3, ovr_totale=ovr, potenziale=0, salario=3.0, job_security=75.0,
                           ovr_offensivo=ovr, ovr_difensivo=ovr, add_xp=lambda xp: None)


def run_progression(torneo):
    """The contract phase for T alone (the filler Z has no coach here)."""
    torneo.squadre[1].coach = None
    torneo._gestisci_fase_assunzioni = lambda: None
    types.MethodType(Tournament._gestisci_progressione_coach, torneo)()


class ContractExpiryTests(unittest.TestCase):
    def expire(self, wins, expected, ovr=80):
        torneo, t = make_torneo(wins, plan="CONTENDER")
        close_season(torneo, torneo.front_office)
        t.vittorie_attese = expected
        t.coach = contract_coach(ovr)
        run_progression(torneo)
        return torneo, t

    def test_not_renewed_for_results_counts_as_coach_change(self):
        torneo, t = self.expire(30, 45)
        self.assertIsNone(t.coach)
        self.assertIs(torneo.front_office.records["T"][-1]["coach_fired"], True)

    def test_not_renewed_for_rating_alone_is_no_coach_change(self):
        torneo, t = self.expire(45, 45, ovr=65)
        self.assertIsNone(t.coach)
        self.assertIs(torneo.front_office.records["T"][-1]["coach_fired"], False)

    def test_renewed_coach_no_change(self):
        torneo, t = self.expire(45, 45)
        self.assertIsNotNone(t.coach)
        self.assertIs(torneo.front_office.records["T"][-1]["coach_fired"], False)

    def test_no_record_row_is_harmless(self):
        torneo, t = make_torneo(30, plan="CONTENDER")
        t.vittorie_attese = 45
        t.coach = contract_coach()
        run_progression(torneo)
        self.assertIsNone(t.coach)
        self.assertEqual(torneo.front_office.records.get("T", []), [])


class CoachChangeToGmFiringScenario(unittest.TestCase):
    def test_coach_let_go_then_two_bad_seasons_fire_the_gm(self):
        torneo, t = make_torneo(40, plan="CONTENDER")
        fo = torneo.front_office
        gm = fo.seated_gm("T")
        gm.tenure = 5

        def season(year, wins, expected):
            torneo.anno_corrente = year
            mark_season_start(torneo, fo)
            fo.season_marks["T"]["expected"] = expected
            t.vittorie, t.sconfitte = wins, 82 - wins
            close_season(torneo, fo)

        season(2004, 40, 42)                      # a fair season, but the owner lets the coach's deal run out
        t.vittorie_attese = 50
        t.coach = contract_coach()
        run_progression(torneo)
        self.assertIsNone(t.coach)
        self.assertIsNone(gm_fire_reason(torneo, fo, t, gm, False))
        season(2005, 38, 48)
        self.assertIsNone(gm_fire_reason(torneo, fo, t, gm, False))
        season(2006, 37, 48)
        self.assertEqual(gm_fire_reason(torneo, fo, t, gm, False),
                         "2 seasons below expectations after the coaching change")


if __name__ == "__main__":
    unittest.main()
