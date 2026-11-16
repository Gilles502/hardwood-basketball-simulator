"""Live simulation runs: quiet lean sim days, the run lock on other game routes, one save at run end, milestones."""
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from core.config import CONFIG


def cal_day(phase='REGULAR_SEASON', events=()):
    return SimpleNamespace(phase=phase, events=list(events), games=[])


class LiveSimRouteTests(unittest.TestCase):
    def setUp(self):
        self._saved = server.SIMULATION_TOURNAMENT
        server._SIM_RUN_LAST_DAY = None
        self.t = SimpleNamespace(calendario=[cal_day() for _ in range(5)], _current_gameday=1,
                                 _trade_deadline_completed=False)

        def sim_day():
            self.t._current_gameday += 1
            return SimpleNamespace(to_dict=lambda: {'games': []})
        self.t.simula_giornata = sim_day
        server.SIMULATION_TOURNAMENT = self.t
        self.save = mock.MagicMock()
        for target, value in (('auto_save_active_game', self.save),
                              ('get_full_league_data_payload', lambda: {'kind': 'full'}),
                              ('get_lean_league_data_payload', lambda: {'kind': 'lean'}),
                              ('ensure_calendar_integrity', lambda t: None),
                              ('_apply_calendar_state_transitions', lambda days: None),
                              ('LEAGUE_STATE', 'PRE_SEASON')):
            p = mock.patch.object(server, target, value)
            p.start()
            self.addCleanup(p.stop)
        self.client = server.app.test_client()

    def tearDown(self):
        server.SIMULATION_TOURNAMENT = self._saved
        server._SIM_RUN_LAST_DAY = None

    def quiet_day(self):
        return self.client.post('/api/calendar/simulate_day', json={'autosave': False, 'lean': True})

    def test_default_day_saves_and_sends_full(self):
        body = self.client.post('/api/calendar/simulate_day').get_json()
        self.assertEqual(self.save.call_count, 1)
        self.assertEqual(body['league_data'], {'kind': 'full'})
        self.assertFalse(server.sim_run_active())

    def test_quiet_lean_day_skips_save_and_marks_run(self):
        body = self.quiet_day().get_json()
        self.assertEqual(self.save.call_count, 0)
        self.assertEqual(body['league_data'], {'kind': 'lean'})
        self.assertTrue(server.sim_run_active())

    def test_run_blocks_other_posts(self):
        self.quiet_day()
        res = self.client.post('/api/trades/execute', json={})
        self.assertEqual(res.status_code, 409)
        self.assertTrue(res.get_json()['sim_running'])
        self.assertNotEqual(self.client.get('/api/calendar').status_code, 409)

    def test_run_lets_read_only_posts_through(self):
        self.quiet_day()
        for path in ('/api/news/seen', '/api/database/finder'):
            self.assertNotEqual(self.client.post(path, json={}).status_code, 409, path)

    def test_run_end_saves_once_and_unlocks(self):
        self.quiet_day()
        res = self.client.post('/api/calendar/sim_run_end')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.save.call_count, 1)
        self.assertEqual(res.get_json()['league_data'], {'kind': 'full'})
        self.assertFalse(server.sim_run_active())
        self.assertNotEqual(self.client.post('/api/trades/execute', json={}).status_code, 409)

    def test_run_end_in_any_state(self):
        self.quiet_day()
        with mock.patch.object(server, 'LEAGUE_STATE', 'REGULAR_SEASON_END'):
            res = self.client.post('/api/calendar/sim_run_end')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.save.call_count, 1)

    def test_stale_run_unlocks(self):
        server._SIM_RUN_LAST_DAY = time.monotonic() - CONFIG.LIVE_SIM.RUN_STALE_S - 1
        self.assertFalse(server.sim_run_active())

    def test_all_star_break_runs_midseason_firings_once(self):
        """Day-by-day runs reach the break without simula_first_half: the CPU mid-season firings still run, once."""
        t = SimpleNamespace(_first_half_complete=False, squadra_giocatore=None, season_number=1,
                            run_all_star_weekend=lambda: None, _gestisci_licenziamenti_midseason=mock.MagicMock())
        with mock.patch.object(server, 'SIMULATION_TOURNAMENT', t), \
                mock.patch.object(server, 'generate_regular_season_news'), \
                mock.patch.object(server, '_generate_power_rankings'), \
                mock.patch.object(server, 'generate_trade_deadline_news'):
            server._on_all_star_break_reached()
            server._on_all_star_break_reached()
        t._gestisci_licenziamenti_midseason.assert_called_once_with()
        self.assertTrue(t._first_half_complete)

    def test_milestones(self):
        t = SimpleNamespace(calendario=[cal_day(), cal_day(), cal_day(events=['TRADE_DEADLINE']), cal_day(),
                                        cal_day('ALL_STAR_BREAK'), cal_day('ALL_STAR_BREAK')],
                            _trade_deadline_completed=False)
        self.assertEqual(server._sim_milestones(t),
                         {'trade_deadline_day': 2, 'trade_deadline_done': False, 'all_star_day': 4})
        empty = SimpleNamespace(calendario=[], _trade_deadline_completed=True)
        self.assertEqual(server._sim_milestones(empty),
                         {'trade_deadline_day': None, 'trade_deadline_done': True, 'all_star_day': None})


if __name__ == '__main__':
    unittest.main()
