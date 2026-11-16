"""All-Star Weekend engine wiring: one entry point on Tournament, no real league load."""
import os
import random
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
import main
from main import Tournament
from core.calendar_generator import CalendarDay



def setUpModule():
    main.main_log.disabled = True


def tearDownModule():
    main.main_log.disabled = False


ROLES = ('PG', 'SG', 'SF', 'PF', 'C')


def make_player(name, team, role, ppg, age=26, rookie=False, gp=40):
    stats = SimpleNamespace(partite_giocate=gp, punti=round(ppg * gp), rimbalzi=gp * 5, assist=gp * 3,
                            tiri_fatti_3=gp, tiri_tentati_3=gp * 3)
    ab = SimpleNamespace(three_point_shot_rating=70, dunk_rating=60, vertical=70, speed=60, acceleration=50)
    return SimpleNamespace(nome=name, ruolo=role, eta=age, valutazione=75, ovr=75, is_rookie=rookie,
                           squadra=team, season_stats=stats, abilita=ab)


def make_team(name, city, conf, idx):
    team = SimpleNamespace(nome=name, city=city, conference=conf, roster=[])
    for i in range(13):
        rookie = i >= 11
        team.roster.append(make_player(f'{name} P{i}', team, ROLES[i % 5], ppg=5 + i * 1.3 + idx * 0.1,
                                       age=20 if rookie else 22 + i, rookie=rookie))
    return team


class FakePodcast:
    def __init__(self):
        self.calls = []

    def log_all_star(self, data):
        self.calls.append(data)


class UntouchableRng:
    """Any use of this rng fails the test."""
    def __getattr__(self, name):
        raise AssertionError(f'rng.{name} used on a finished weekend')


def make_tournament():
    east_cities = ('Boston', 'Toronto', 'Miami', 'Chicago')
    west_cities = ('Denver', 'Phoenix', 'Dallas', 'Houston')
    t = object.__new__(Tournament)
    t.squadre_est = [make_team(f'East{i}', c, 'East', i) for i, c in enumerate(east_cities)]
    t.squadre_ovest = [make_team(f'West{i}', c, 'West', i) for i, c in enumerate(west_cities)]
    t.squadre = t.squadre_est + t.squadre_ovest
    t.free_agents_pool = []
    t.season_number = 3
    t.podcast_logger = FakePodcast()
    t.all_star_hosts = []
    t.last_season_rookies = []
    t.reset_all_star_weekend()
    return t


def selected_names(snap, conf):
    sel = snap['selections'][conf]
    return {x['name'] for x in sel['starters'] + sel['reserves']}


class AllStarEngineTests(unittest.TestCase):
    def test_run_twice_plays_once(self):
        t = make_tournament()
        snap = t.run_all_star_weekend(rng=random.Random(1))
        self.assertTrue(t.all_star_weekend_complete)
        self.assertIs(t.run_all_star_weekend(rng=UntouchableRng()), snap)
        self.assertEqual(len(t.podcast_logger.calls), 1)
        self.assertEqual(len(t.all_star_hosts), 1)

    def test_left_out_excludes_selected(self):
        t = make_tournament()
        snap = t.run_all_star_weekend(rng=random.Random(3))
        for conf in ('east', 'west'):
            left = [x['name'] for x in snap['selections'][conf]['left_out']]
            self.assertEqual(len(left), CONFIG.ALL_STAR.LEFT_OUT_SHOWN)
            self.assertFalse(set(left) & selected_names(snap, conf))
            self.assertEqual(len(selected_names(snap, conf)), 12)

    def test_host_from_team_cities_and_recorded(self):
        t = make_tournament()
        cities = {s.city for s in t.squadre}
        hosts = []
        for seed in range(CONFIG.ALL_STAR.HOST_NO_REPEAT):
            snap = t.run_all_star_weekend(rng=random.Random(seed))
            self.assertIn(snap['host'], cities)
            self.assertEqual(t.all_star_hosts[-1], snap['host'])
            hosts.append(snap['host'])
            t.reset_all_star_weekend()
        self.assertEqual(len(set(hosts)), len(hosts))
        self.assertEqual(t.all_star_hosts, hosts)

    def test_host_skips_teams_with_unknown_city(self):
        t = make_tournament()
        for s in t.squadre:
            s.city = 'Atlantis'
        t.squadre[0].city = 'Boston'
        self.assertEqual(t.run_all_star_weekend(rng=random.Random(0))['host'], 'Boston')

    def test_legacy_fields_set(self):
        t = make_tournament()
        snap = t.run_all_star_weekend(rng=random.Random(5))
        self.assertIs(t.all_star_weekend, snap)
        self.assertEqual(t.all_star_mvp, snap['game']['mvp']['name'])
        self.assertIs(t.all_star_game_log, snap['game'])
        self.assertEqual(t.three_point_contest['winner'], snap['three_point']['winner'])
        self.assertEqual(t.dunk_contest['winner'], snap['dunk']['winner'])
        self.assertEqual([p.nome for p in t.all_star_rosters['east']],
                         [x['name'] for x in snap['selections']['east']['starters'] +
                          snap['selections']['east']['reserves']])
        logged = t.podcast_logger.calls[0]
        self.assertEqual(logged['mvp'], t.all_star_mvp)
        self.assertEqual(logged['three_pt_winner'], snap['three_point']['winner'])

    def test_rookie_challenge_uses_rookies_and_last_year_rookies(self):
        t = make_tournament()
        sophomore = t.squadre[0].roster[0]
        t.last_season_rookies = [sophomore.nome]
        snap = t.run_all_star_weekend(rng=random.Random(7))
        rookies = snap['rookie_challenge']['rookies']
        self.assertEqual(len(rookies), CONFIG.ALL_STAR.ROOKIE_CHALLENGE_SIZE)
        rookie_names = {p.nome for s in t.squadre for p in s.roster if p.is_rookie}
        self.assertTrue({x['name'] for x in rookies} <= rookie_names)
        ppgs = [x['ppg'] for x in rookies]
        self.assertEqual(ppgs, sorted(ppgs, reverse=True))
        sophs = snap['rookie_challenge']['sophomores']
        self.assertEqual(sophs[0]['name'], sophomore.nome)
        self.assertFalse({x['name'] for x in sophs} & rookie_names)
        self.assertIsNotNone(snap['rookie_challenge']['game'])

    def test_old_instance_without_new_attributes(self):
        t = make_tournament()
        del t.all_star_hosts
        del t.last_season_rookies
        snap = t.run_all_star_weekend(rng=random.Random(9))
        self.assertEqual(t.all_star_hosts, [snap['host']])

    def test_reset_keeps_history(self):
        t = make_tournament()
        t.last_season_rookies = ['X']
        t.run_all_star_weekend(rng=random.Random(4))
        hosts = list(t.all_star_hosts)
        t.reset_all_star_weekend()
        self.assertIsNone(t.all_star_weekend)
        self.assertFalse(t.all_star_weekend_complete)
        self.assertIsNone(t.all_star_mvp)
        self.assertEqual(t.all_star_rosters, {'east': [], 'west': []})
        self.assertEqual(t.all_star_hosts, hosts)
        self.assertEqual(t.last_season_rookies, ['X'])

    def test_rookie_list_kept_before_reset(self):
        t = make_tournament()
        fa = make_player('FA Rookie', None, 'PG', 4.0, age=19, rookie=True)
        t.free_agents_pool = [fa]
        expected = {p.nome for s in t.squadre for p in s.roster if p.is_rookie} | {'FA Rookie'}
        t._remember_rookies()
        self.assertEqual(set(t.last_season_rookies), expected)


BREAK_START, GAME_DAY, BREAK_END, CALENDAR_DAYS = 5, 7, 9, 12


class SimTournament(Tournament):
    """Tournament with a tiny calendar of game-less days and the daily routines stubbed."""
    def _noop(self, *args, **kwargs):
        pass

    _inizializza_inizio_giornata = check_and_generate_trade_block_offer = avanza_scouting_giornata = _noop
    aggiorna_draft_stock_giornata = aggiorna_job_security_giornata = avanza_cooldown_scambi_giornata = _noop
    _gestisci_finestra_estensioni = trade_period_midseason = _gestisci_licenziamenti_midseason = _noop
    _concludi_regular_season = _noop


def make_calendar():
    days = []
    for i in range(CALENDAR_DAYS):
        phase = 'ALL_STAR_BREAK' if BREAK_START <= i <= BREAK_END else 'REGULAR_SEASON'
        events = {BREAK_START: ['RISING_STARS'], BREAK_START + 1: ['ALL_STAR_SATURDAY'],
                  GAME_DAY: ['ALL_STAR_GAME']}.get(i, [])
        # Real CalendarDay: a day with no games is falsy (len 0), as every break day is.
        days.append(CalendarDay(day_index=i, date=f'2003-02-{i + 1:02d}', phase=phase, events=events, games=[]))
    return days


def make_sim_tournament():
    t = make_tournament()
    sim = object.__new__(SimTournament)
    sim.__dict__.update(t.__dict__)
    sim.calendario = make_calendar()
    sim._current_gameday = 0
    sim._trade_deadline_completed = True
    sim._last_played_day = {}
    sim.team_map = {s.nome: s for s in sim.squadre}
    return sim


class AllStarBreakPathTests(unittest.TestCase):
    def test_sim_until_stops_after_game_day_and_plays_once(self):
        t = make_sim_tournament()
        days = t.simula_fino_a_giornata(CALENDAR_DAYS)
        self.assertEqual(t._current_gameday, GAME_DAY + 1)
        self.assertEqual(days[-1].events, ['ALL_STAR_GAME'])
        self.assertTrue(t.all_star_weekend_complete)
        self.assertEqual(len(t.podcast_logger.calls), 1)

    def test_sim_until_from_break_with_weekend_played_still_reaches_game_day(self):
        t = make_sim_tournament()
        t.simula_first_half()
        self.assertEqual(t._current_gameday, BREAK_START)
        t.run_all_star_weekend()  # the server break hook
        t.simula_fino_a_giornata(CALENDAR_DAYS)
        self.assertEqual(t._current_gameday, GAME_DAY + 1)
        self.assertEqual(len(t.podcast_logger.calls), 1)

    def test_sim_until_after_game_day_runs_to_target(self):
        t = make_sim_tournament()
        t.simula_fino_a_giornata(CALENDAR_DAYS)
        t.simula_fino_a_giornata(CALENDAR_DAYS)
        self.assertEqual(t._current_gameday, CALENDAR_DAYS)
        self.assertEqual(len(t.podcast_logger.calls), 1)

    def test_day_by_day_plays_on_game_day(self):
        t = make_sim_tournament()
        while t._current_gameday < GAME_DAY:
            t.simula_giornata()
            self.assertFalse(t.all_star_weekend_complete)
        t.simula_giornata()
        self.assertTrue(t.all_star_weekend_complete)
        while t._current_gameday < CALENDAR_DAYS:
            t.simula_giornata()
        self.assertEqual(len(t.podcast_logger.calls), 1)

    def test_sim_week_returns_game_less_days(self):
        t = make_sim_tournament()
        days = t.simula_settimana()
        self.assertEqual([d.day_index for d in days], list(range(min(7, CALENDAR_DAYS))))

    def test_simula_regular_season_plays_once(self):
        t = make_sim_tournament()
        t.simula_regular_season()
        self.assertEqual(t._current_gameday, CALENDAR_DAYS)
        self.assertTrue(t.all_star_weekend_complete)
        self.assertEqual(len(t.podcast_logger.calls), 1)

    def test_host_no_repeat_zero_allows_any_city(self):
        t = make_tournament()
        history = [s.city for s in t.squadre if s.city != 'Boston']
        cfg = CONFIG.ALL_STAR
        saved = cfg.HOST_NO_REPEAT
        object.__setattr__(cfg, 'HOST_NO_REPEAT', 0)
        try:
            seen = set()
            for seed in range(40):
                t.reset_all_star_weekend()
                t.all_star_hosts = list(history)
                seen.add(t.run_all_star_weekend(rng=random.Random(seed))['host'])
        finally:
            object.__setattr__(cfg, 'HOST_NO_REPEAT', saved)
        self.assertGreater(len(seen), 1)

if __name__ == '__main__':
    unittest.main()
