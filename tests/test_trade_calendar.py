"""Trade calendar: no user trades between the deadline and the offseason."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.save_manager import restore_tournament_state, serialize_tournament_state
from main import Tournament
from tests.test_front_office_state import fake_torneo
from trades.calendar import deadline_passed, user_trade_window


def calendar_with_deadline(deadline_day=100, length=177):
    days = [SimpleNamespace(events=[]) for _ in range(length)]
    days[deadline_day].events.append("TRADE_DEADLINE")
    return days


def torneo(gameday=0, completed=False):
    return SimpleNamespace(calendario=calendar_with_deadline(), _current_gameday=gameday,
                           _trade_deadline_completed=completed)


class WindowTests(unittest.TestCase):
    def test_open_in_preseason_day_zero(self):
        self.assertEqual(user_trade_window(torneo(0), "PRE_SEASON"), (True, ""))

    def test_closed_in_all_star_break_after_deadline_day(self):
        ok, msg = user_trade_window(torneo(101), "ALL_STAR_BREAK")
        self.assertFalse(ok)
        self.assertEqual(msg, "The trade deadline has passed")

    def test_open_on_deadline_day_itself(self):
        self.assertFalse(deadline_passed(torneo(100)))

    def test_flag_alone_closes_the_window(self):
        self.assertTrue(deadline_passed(torneo(5, completed=True)))
        self.assertFalse(user_trade_window(torneo(5, completed=True), "PRE_SEASON")[0])

    def test_open_again_in_offseason_with_flag_set(self):
        self.assertEqual(user_trade_window(torneo(176, completed=True), "OFFSEASON_TRADES_START"), (True, ""))

    def test_closed_in_playoffs(self):
        self.assertEqual(user_trade_window(torneo(0), "PLAYOFFS"),
                         (False, "The trade window is closed (PLAYOFFS)"))

    def test_closed_message_replaces_underscores(self):
        self.assertEqual(user_trade_window(torneo(0), "PLAYOFFS_IN_PROGRESS")[1],
                         "The trade window is closed (PLAYOFFS IN PROGRESS)")


class SaveTests(unittest.TestCase):
    def test_flag_survives_round_trip(self):
        t = fake_torneo()
        t._trade_deadline_completed = True
        t._current_gameday = 120
        fresh = fake_torneo()
        restore_tournament_state(fresh, serialize_tournament_state(t))
        self.assertTrue(fresh._trade_deadline_completed)

    def test_old_save_without_flag_loads_false(self):
        fresh = fake_torneo()
        fresh._trade_deadline_completed = True
        restore_tournament_state(fresh, {"season_number": 1, "_current_gameday": 3})
        self.assertFalse(fresh._trade_deadline_completed)


class TradeBlockTests(unittest.TestCase):
    def make(self, gameday, completed):
        t = SimpleNamespace(squadra_giocatore=object(), calendario=calendar_with_deadline(),
                            _current_gameday=gameday, _trade_deadline_completed=completed,
                            pending_trade_block_offers=[], trade_difficulty="easy")
        return t

    def test_no_offer_after_the_deadline(self):
        t = self.make(150, True)
        with mock.patch("trades.trade_block_manager.TradeBlockManager.generate_offer_for_simulation",
                        return_value={"offering_team": "X"}) as gen:
            Tournament.check_and_generate_trade_block_offer(t, force=True)
        gen.assert_not_called()
        self.assertEqual(t.pending_trade_block_offers, [])

    def test_offer_before_the_deadline(self):
        t = self.make(10, False)
        with mock.patch("trades.trade_block_manager.TradeBlockManager.generate_offer_for_simulation",
                        return_value={"offering_team": "X"}):
            Tournament.check_and_generate_trade_block_offer(t, force=True)
        self.assertEqual(len(t.pending_trade_block_offers), 1)


class RouteTests(unittest.TestCase):
    ROUTES = [("post", "/api/trade-finder"), ("post", "/api/validate-user-trade"),
              ("post", "/api/execute-user-trade"), ("post", "/api/counter-offer-trade"),
              ("post", "/api/validate-3-team-trade"), ("post", "/api/execute-3-team-trade"),
              ("post", "/api/trades/execute-4-team"), ("post", "/api/trades/search-by-need"),
              ("post", "/api/trades/what-would-it-take"), ("get", "/api/trades/multi-team-chains"),
              ("post", "/api/trade-block/generate"), ("post", "/api/trade-block/respond")]

    def test_every_user_trade_route_refuses_after_the_deadline(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        t = torneo(150, completed=True)
        with mock.patch.object(server, "SIMULATION_TOURNAMENT", t),                 mock.patch.object(server, "LEAGUE_STATE", "ALL_STAR_BREAK"):
            client = server.app.test_client()
            for method, url in self.ROUTES:
                resp = getattr(client, method)(url, json={})
                self.assertEqual(resp.status_code, 400, url)
                self.assertEqual(resp.get_json()["error"], "The trade deadline has passed", url)

    def info(self, t):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        t.squadra_giocatore = SimpleNamespace(nome="Me", roster=[])
        t.squadre = [t.squadra_giocatore]
        t.pick_ownership, t.pick_protections = {}, {}
        with mock.patch.object(server, "SIMULATION_TOURNAMENT", t),                 mock.patch.object(server, "LEAGUE_STATE", "ALL_STAR_BREAK"):
            resp = server.app.test_client().get("/api/user-trade-info")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def test_info_route_closed_after_deadline(self):
        body = self.info(torneo(150, completed=True))
        self.assertFalse(body["trade_window_open"])
        self.assertEqual(body["trade_window_message"], "The trade deadline has passed")

    def test_info_route_open_before_deadline(self):
        body = self.info(torneo(10))
        self.assertTrue(body["trade_window_open"])
        self.assertEqual(body["trade_window_message"], "")


class NewSeasonTests(unittest.TestCase):
    def test_new_season_reopens_the_window(self):
        import main
        import inspect
        src = inspect.getsource(main)
        self.assertIn("torneo._current_gameday = 0\n    torneo._trade_deadline_completed = False", src)

    def test_server_new_season_resets_flag(self):
        import inspect
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        self.assertIn("_trade_deadline_completed = False", inspect.getsource(server))


if __name__ == "__main__":
    unittest.main()
