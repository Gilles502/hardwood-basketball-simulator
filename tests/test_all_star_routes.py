"""All-Star route: GET /api/allstar for the current season and past ones; the old run routes are gone."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from tests.test_all_star_view import PREMI_2024, PREMI_2025, snapshot


def live_snapshot(*args):
    return dict(snapshot(*args), season=4)


def day(phase, date, events=()):
    return SimpleNamespace(phase=phase, date=date, events=list(events))


class AllStarRouteTests(unittest.TestCase):
    def setUp(self):
        self._saved = server.SIMULATION_TOURNAMENT
        self.t = SimpleNamespace(
            season_number=4, starting_year=2002, all_star_weekend=None, all_star_weekend_complete=False,
            squadra_giocatore=SimpleNamespace(nome='Alpha'),
            calendario=[day('REGULAR_SEASON', '2005-02-10'), day('ALL_STAR_BREAK', '2005-02-11'),
                        day('ALL_STAR_BREAK', '2005-02-12', ['ALL_STAR_GAME']), day('REGULAR_SEASON', '2005-02-15')],
            _current_gameday=0)
        state = mock.patch.object(server, 'LEAGUE_STATE', 'PRE_SEASON')
        state.start()
        self.addCleanup(state.stop)
        server.SIMULATION_TOURNAMENT = self.t
        played = dict(PREMI_2024, all_star_weekend=snapshot('Benedikt Iverley', 'Toronto Northmen'))
        self.files = {
            'league_history.json': [{'stagione': 1, 'anno': 2002, 'premi': PREMI_2024},
                                    {'stagione': 2, 'anno': 2003, 'premi': PREMI_2025},
                                    {'stagione': 3, 'anno': 2004, 'premi': played}],
            'player_careers.json': {'quincy-ashgrove': [{'stagione': 1, 'squadra': 'Minnesota Blizzard',
                                                       'nome': 'Quincy Ashgrove'}]},
        }
        patcher = mock.patch.object(server, '_read_historical_json', lambda name, default: self.files.get(name, default))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = server.app.test_client()

    def tearDown(self):
        server.SIMULATION_TOURNAMENT = self._saved

    def test_get_current_and_past_season(self):
        cur = self.client.get('/api/allstar').get_json()
        self.assertEqual((cur['season'], cur['label'], cur['status'], cur['is_current']),
                         (4, '2005-06', 'upcoming', True))
        self.assertEqual(cur['break'], {'day': 1, 'date': '2005-02-11'})
        self.assertEqual([s['season'] for s in cur['seasons']], [4, 3, 2, 1])

        self.t.all_star_weekend = live_snapshot('Quincy Ashgrove', 'Minnesota Blizzard')
        self.t.all_star_weekend_complete = True
        live = self.client.get('/api/allstar?season=4').get_json()
        self.assertEqual(live['status'], 'played')
        self.assertEqual(live['events'][1]['summary'], '24 All-Stars · 2 yours')
        # season 1 MVP team comes from the careers file
        self.assertEqual(live['game']['mvp']['fact'], "Quincy Ashgrove's 2nd All-Star MVP")

        past = self.client.get('/api/allstar?season=3').get_json()
        self.assertEqual((past['status'], past['label'], past['is_current'], past['break']),
                         ('played', '2004-05', False, None))
        self.assertEqual(past['game']['mvp']['fact'], 'First All-Star MVP for the Toronto Northmen')

        legacy = self.client.get('/api/allstar?season=1').get_json()
        self.assertEqual(legacy['status'], 'played')
        self.assertEqual(legacy['three_point']['winner'], 'Pax Thackery')
        self.assertEqual(self.client.get('/api/allstar?season=2').get_json()['status'], 'not_recorded')

        missing = self.client.get('/api/allstar?season=9')
        self.assertEqual(missing.status_code, 404)
        self.assertIn('error', missing.get_json())
        bad = self.client.get('/api/allstar?season=abc')
        self.assertEqual(bad.status_code, 400)
        self.assertIn('error', bad.get_json())

    def test_break_already_passed_without_a_weekend_is_not_upcoming(self):
        # before the break: upcoming, with the break day
        self.t._current_gameday = 1
        d = self.client.get('/api/allstar').get_json()
        self.assertEqual((d['status'], d['break']), ('upcoming', {'day': 1, 'date': '2005-02-11'}))
        # the game day was simulated, the complete flag lost (old save): nothing recorded
        self.t._current_gameday = 3
        d = self.client.get('/api/allstar').get_json()
        self.assertEqual((d['status'], d['break']), ('not_recorded', None))
        # flagged complete
        self.t._current_gameday, self.t.all_star_weekend_complete = 0, True
        self.assertEqual(self.client.get('/api/allstar').get_json()['status'], 'not_recorded')
        # past the regular season
        self.t.all_star_weekend_complete = False
        with mock.patch.object(server, 'LEAGUE_STATE', 'PLAYOFFS_IN_PROGRESS'):
            self.assertEqual(self.client.get('/api/allstar').get_json()['status'], 'not_recorded')

    def test_past_mvps_keep_unknown_team_and_text_career_seasons(self):
        # Season 2's MVP has no team anywhere: still counted. Old careers store "Season 1" as text.
        self.files['league_history.json'][1]['premi'] = dict(PREMI_2025, all_star_mvp='Xavi Zellner')
        self.files['player_careers.json'] = {'quincy-ashgrove': [{'stagione': 'Season 1', 'nome': 'Quincy Ashgrove',
                                                                'squadra': 'Minnesota Blizzard'}]}
        self.t.all_star_weekend_complete = True
        self.t.all_star_weekend = live_snapshot('Xavi Zellner', 'San Antonio Vaqueros')
        self.assertEqual(self.client.get('/api/allstar').get_json()['game']['mvp']['fact'],
                         "Xavi Zellner's 2nd All-Star MVP")
        # a new MVP from Minnesota: season 1's KG (team from the "Season 1" career row) was one already
        self.t.all_star_weekend = live_snapshot('Caspian Pembrook', 'Minnesota Blizzard')
        self.assertIsNone(self.client.get('/api/allstar').get_json()['game']['mvp']['fact'])

    def test_spectator_mode_has_no_user_team(self):
        self.t.is_spectator = True
        self.t.all_star_weekend = live_snapshot()
        d = self.client.get('/api/allstar').get_json()
        self.assertIsNone(d['you'])
        self.assertEqual(d['events'][1]['summary'], '24 All-Stars')

    def test_post_routes_gone(self):
        for path in ('select', '3pt', 'dunk', 'game'):
            self.assertIn(self.client.post(f'/api/allstar/{path}').status_code, (404, 405))
        self.assertEqual(self.client.post('/api/allstar').status_code, 405)


class BreakTransitionTests(unittest.TestCase):
    """Day-by-day sims hand back real CalendarDay objects; a break day has no games, so it is falsy."""

    def setUp(self):
        from core.calendar_generator import CalendarDay
        self._saved = server.SIMULATION_TOURNAMENT
        self.days = [CalendarDay(day_index=i, date=f'2005-02-{10 + i}', phase=phase, events=events, games=[])
                     for i, (phase, events) in enumerate([('REGULAR_SEASON', []), ('ALL_STAR_BREAK', ['RISING_STARS']),
                                                          ('ALL_STAR_BREAK', ['ALL_STAR_GAME'])])]
        server.SIMULATION_TOURNAMENT = SimpleNamespace(calendario=self.days * 3, _current_gameday=2)
        state = mock.patch.object(server, 'LEAGUE_STATE', 'PRE_SEASON')
        state.start()
        self.addCleanup(state.stop)
        self.hook = mock.patch.object(server, '_on_all_star_break_reached')
        self.hook_mock = self.hook.start()
        self.addCleanup(self.hook.stop)

    def tearDown(self):
        server.SIMULATION_TOURNAMENT = self._saved

    def test_game_less_break_day_enters_the_break(self):
        server._apply_calendar_state_transitions([self.days[1]])
        self.assertEqual(server.LEAGUE_STATE, 'ALL_STAR_BREAK')
        self.hook_mock.assert_called_once()


class LoadAtTheBreakTests(unittest.TestCase):
    """An old save made at the break, before the weekend was played: loading it plays the weekend."""

    def setUp(self):
        self.t = SimpleNamespace(squadre=[], all_star_weekend_complete=False, run_all_star_weekend=mock.Mock())
        for name, value in (('SIMULATION_TOURNAMENT', None), ('LEAGUE_STATE', 'PRE_SEASON'),
                            ('ACTIVE_SAVE_NAME', None), ('OFFSEASON_FA_POOL', None)) + tuple(
                (g, getattr(server, g, None)) for g in ('NEGOTIATION_ATTEMPTS', 'ACTIVE_FREE_AGENCY_INSTANCE', 'DRAFT_INSTANCE',
                                                  'PLAYOFF_CURRENT_GAME', 'PLAYOFF_GAMEBYGAME_MODE', 'PLAYOFF_SERIES')):
            p = mock.patch.object(server, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)
        for name, value in (('restore_tournament_state', lambda t, data: None),
                            ('set_active_save_name', lambda name: None),
                            ('ensure_calendar_integrity', lambda t: None),
                            ('get_full_league_data_payload', lambda: {})):
            p = mock.patch.object(server, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(server.simulation_logic, 'setup_simulation', lambda **kw: self.t)
        p.start()
        self.addCleanup(p.stop)
        import core.models
        p = mock.patch.object(core.models, 'ACTIVE_TOURNAMENT', None)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(server.simulation_logic, 'ACTIVE_TOURNAMENT', None, create=True)
        p.start()
        self.addCleanup(p.stop)
        self.client = server.app.test_client()

    def load(self, phase):
        loaded = {'metadata': {'save_name': 'Test', 'phase': phase}, 'state_data': {}}
        with mock.patch.object(server, 'load_game', lambda name: loaded):
            return self.client.post('/api/saves/load', json={'save_name': 'Test'})

    def test_break_save_plays_the_weekend(self):
        self.assertEqual(self.load('ALL_STAR_BREAK').status_code, 200)
        self.t.run_all_star_weekend.assert_called_once_with()

    def test_other_phases_or_played_weekend_leave_it(self):
        self.assertEqual(self.load('REGULAR_SEASON').status_code, 200)
        self.t.all_star_weekend_complete = True
        self.assertEqual(self.load('ALL_STAR_BREAK').status_code, 200)
        self.t.run_all_star_weekend.assert_not_called()


if __name__ == '__main__':
    unittest.main()
