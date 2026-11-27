"""Fixes from the engine and save audit of 2026-11-26 (docs/audits/ENGINE_AND_SAVE_AUDIT_2026-11-26.md):
offensive options picked again, aging stars keep their usage, DPOY with team defense and voter fatigue."""
import random
import unittest
from types import SimpleNamespace
from unittest import mock

from core.config import CONFIG
from core.models import CumulativeStats, Squadra, TacticalPlan


def _prospects(count=60, seed=5):
    from offseason.draft import Draft
    random.seed(seed)
    d = object.__new__(Draft)
    d.torneo = SimpleNamespace(anno_corrente=2002, squadre=[], free_agents_pool=[], draft_class=[])
    return d._genera_giocatori_mancanti(count, [])


def _league(teams=4):
    from main import Tournament
    players = _prospects(teams * 13)
    squadre = []
    for i in range(teams):
        roster = players[i * 13:(i + 1) * 13]
        for j, p in enumerate(roster):
            p.eta = 27
            p.valutazione = 90 - j * 2
            p.infortunato = False
            p.is_resting_today = False
        squadra = Squadra(nome=f"Team {i}", roster=roster)
        squadra.tactical_plan = TacticalPlan()
        for p in roster:
            p.squadra = squadra
        squadre.append(squadra)
    torneo = object.__new__(Tournament)
    torneo.squadre = squadre
    torneo.squadra_giocatore = None
    torneo.campione = None
    torneo.playoff_state = None
    return torneo


class OffensiveOptions(unittest.TestCase):
    def test_cpu_team_drops_options_of_players_who_left(self):
        torneo = _league()
        team = torneo.squadre[1]
        team.tactical_plan.offensive_first_option = "Retired Star"
        team.tactical_plan.offensive_second_option = "Traded Guard"
        team.tactical_plan.offensive_third_option = "Gone Forward"
        torneo.imposta_rotazioni_stagione_per_squadra(team)
        names = {p.nome for p in team.roster}
        tp = team.tactical_plan
        for option in (tp.offensive_first_option, tp.offensive_second_option, tp.offensive_third_option):
            self.assertIn(option, names)

    def test_cpu_team_gives_the_first_option_to_a_new_star(self):
        torneo = _league()
        team = torneo.squadre[1]
        torneo.imposta_rotazioni_stagione_per_squadra(team)
        newcomer = torneo.squadre[2].roster[0]
        torneo.squadre[2].roster.remove(newcomer)
        newcomer.valutazione = 99
        newcomer.tendenze.touch_tendency = 90
        team.roster.append(newcomer)
        newcomer.squadra = team
        torneo.imposta_rotazioni_stagione_per_squadra(team)
        self.assertEqual(team.tactical_plan.offensive_first_option, newcomer.nome)

    def test_user_team_keeps_its_choices_and_loses_only_stale_names(self):
        torneo = _league()
        team = torneo.squadre[0]
        torneo.squadra_giocatore = team
        torneo.check_and_adjust_user_rotations = lambda s: False
        pick = team.roster[6].nome
        team.tactical_plan.offensive_first_option = pick
        team.tactical_plan.offensive_second_option = "Traded Guard"
        torneo.imposta_rotazioni_stagione()
        self.assertEqual(team.tactical_plan.offensive_first_option, pick)
        self.assertIsNone(team.tactical_plan.offensive_second_option)


class AgingStarUsage(unittest.TestCase):
    def _veteran(self, holds):
        player = _prospects(1)[0]
        player.eta = 34
        player.tendenze.touch_tendency = 80
        player.tendenze.hero_ball_tendency = 70
        player.tendenze.shot_tendency = 75
        player._distribuisci_cambio_abilita(-1, star_holds=holds)
        return player

    def test_a_star_who_holds_keeps_his_touches(self):
        star = self._veteran(holds=True)
        self.assertEqual(star.tendenze.touch_tendency, 80)
        self.assertEqual(star.tendenze.hero_ball_tendency, 70)
        self.assertEqual(star.tendenze.shot_tendency, 75)

    def test_other_veterans_still_lose_them(self):
        vet = self._veteran(holds=False)
        self.assertLess(vet.tendenze.touch_tendency, 80)

    def test_veteran_touch_ages_from_config(self):
        self.assertEqual(CONFIG.SIM.VETERAN_TOUCH_START_AGE, 33)
        self.assertEqual(CONFIG.SIM.VETERAN_TOUCH_START_AGE_ELITE, 35)


class DefensivePlayerOfTheYear(unittest.TestCase):
    def _setup(self, history):
        torneo = _league()
        torneo.season_number = 5
        for i, team in enumerate(torneo.squadre):
            team.vittorie, team.sconfitte = 41, 41
            team.punti_subiti_stagione = 100 * 82
            for p in team.roster:
                p.season_stats = CumulativeStats(partite_giocate=70, rimbalzi=70 * 4, steals=70, blocks=35)
                p.premi = []
        center = torneo.squadre[0].roster[0]
        center.season_stats = CumulativeStats(partite_giocate=80, rimbalzi=80 * 15, steals=80 * 1.3, blocks=80 * 3.8)
        wing = torneo.squadre[1].roster[0]
        wing.season_stats = CumulativeStats(partite_giocate=80, rimbalzi=80 * 7, steals=80 * 2.0, blocks=80 * 1.8)
        for p in (center, wing):
            p.abilita.defensive_iq_rating = 95
            p.abilita.interior_defense_rating = 95
        torneo._award_winner_history = lambda key, label, players: history(center)
        return torneo, center, wing

    def test_a_center_on_a_500_team_loses_to_the_wing_of_the_best_defense(self):
        torneo, center, wing = self._setup(lambda c: (None, None, {}))
        torneo.squadre[1].vittorie, torneo.squadre[1].sconfitte = 63, 19
        torneo.squadre[1].punti_subiti_stagione = 94 * 82
        torneo._calcola_defensive_player_of_the_year()
        self.assertIs(torneo.defensive_player_of_the_year, wing)

    def test_the_same_center_wins_when_teams_are_level(self):
        torneo, center, wing = self._setup(lambda c: (None, None, {}))
        torneo._calcola_defensive_player_of_the_year()
        self.assertIs(torneo.defensive_player_of_the_year, center)

    def test_voter_fatigue_on_a_repeat_winner(self):
        torneo, center, wing = self._setup(lambda c: (c.nome, c.nome, {c.nome: 4}))
        torneo.squadre[1].vittorie, torneo.squadre[1].sconfitte = 52, 30
        torneo._calcola_defensive_player_of_the_year()
        self.assertIs(torneo.defensive_player_of_the_year, wing)
        torneo._award_winner_history = lambda key, label, players: (None, None, {})
        torneo._calcola_defensive_player_of_the_year()
        self.assertIs(torneo.defensive_player_of_the_year, center)

    def test_four_blocks_beat_two_and_a_half_steals_on_level_teams(self):
        # League_2002_5: a 4-block, 16-rebound center never won in 25 seasons (steals were worth 1.5 blocks)
        torneo, center, wing = self._setup(lambda c: (None, None, {}))
        center.season_stats = CumulativeStats(partite_giocate=80, rimbalzi=80 * 16, oreb=80 * 4, steals=80 * 1.2,
                                              blocks=80 * 4.0)
        wing.season_stats = CumulativeStats(partite_giocate=80, rimbalzi=80 * 9, oreb=80 * 2, steals=80 * 2.5,
                                            blocks=80 * 2.6)
        torneo._calcola_defensive_player_of_the_year()
        self.assertIs(torneo.defensive_player_of_the_year, center)

    def test_the_season_mvp_gets_a_discount(self):
        torneo, center, wing = self._setup(lambda c: (None, None, {}))
        wing.season_stats = CumulativeStats(partite_giocate=80, rimbalzi=80 * 11, steals=80 * 2.0, blocks=80 * 3.7)
        torneo._calcola_defensive_player_of_the_year()
        self.assertIs(torneo.defensive_player_of_the_year, wing)
        torneo.regular_season_mvp = wing
        torneo._calcola_defensive_player_of_the_year()
        self.assertIs(torneo.defensive_player_of_the_year, center)


if __name__ == "__main__":
    unittest.main()
