"""Trade requests: the saved frustration meter and the request of an important player (core/front_office/trade_requests.py)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office import trade_requests as tr
from tests.trade_fixtures import era_of, make_player

ERA = era_of()
SINCE = "Season 2003"


def team_of(players, name="Team"):
    return SimpleNamespace(nome=name, roster=players, payroll=40.0)


def star(ovr=85, morale=40, age=27):
    p = make_player("Star", ovr=ovr, age=age, role="SF")
    p.morale = morale
    return p


def bad_ticks(p, team, n, plan="MIDDLE", win_pct=0.30, games=60):
    results = [tr.tick(p, team, era=ERA, plan=plan, win_pct=win_pct, games=games, since=SINCE) for _ in range(n)]
    return [r for r in results if r is not None]


class MeterTests(unittest.TestCase):
    def test_full_bad_season_requests(self):
        p = star()
        events = bad_ticks(p, team_of([p]), 24)
        self.assertEqual(events, ["requested"])
        self.assertTrue(p.trade_request)
        self.assertEqual(p.trade_request_since, SINCE)

    def test_half_season_does_not_request(self):
        p = star()
        self.assertEqual(bad_ticks(p, team_of([p]), 12), [])
        self.assertFalse(getattr(p, 'trade_request', False))
        self.assertEqual(p.frustration, 12 * CONFIG.TRADE_REQUESTS.RISE_PER_TICK)

    def test_short_win_streak_keeps_request(self):
        p = star()
        t = team_of([p])
        bad_ticks(p, t, 24)
        p.morale = 70
        self.assertEqual(bad_ticks(p, t, 5, win_pct=0.6), [])
        self.assertTrue(p.trade_request)

    def test_withdraw_below_threshold(self):
        p = star()
        t = team_of([p])
        bad_ticks(p, t, 24)
        p.morale = 70
        events = bad_ticks(p, t, 30, win_pct=0.6)
        self.assertEqual(events, ["withdrawn"])
        self.assertFalse(p.trade_request)
        self.assertEqual(p.trade_request_since, "")
        self.assertLess(p.frustration, CONFIG.TRADE_REQUESTS.WITHDRAW_BELOW)

    def test_under_line_never_requests(self):
        p = star(ovr=83)
        self.assertEqual(bad_ticks(p, team_of([p]), 30), [])
        self.assertFalse(getattr(p, 'trade_request', False))
        self.assertTrue(tr.fed_up(p))

    def test_young_future_blocks_rise(self):
        p = star()
        kids = [make_player(f"k{i}", ovr=60, age=21, pot=86) for i in range(2)]
        bad_ticks(p, team_of([p] + kids), 10)
        self.assertEqual(p.frustration, 0.0)

    def test_rebuilder_counts_as_losing(self):
        p = star()
        bad_ticks(p, team_of([p]), 3, plan="REBUILDER", win_pct=0.6)
        self.assertEqual(p.frustration, 3 * CONFIG.TRADE_REQUESTS.RISE_PER_TICK)

    def test_happy_player_does_not_rise(self):
        p = star(morale=60)
        bad_ticks(p, team_of([p]), 5)
        self.assertEqual(p.frustration, 0.0)

    def test_season_end_bumps(self):
        p = star()
        p.frustration = 90.0
        self.assertEqual(tr.season_end(p, team_of([p]), era=ERA, made_playoffs=False, since="Summer 2003"), "requested")
        self.assertEqual(p.frustration, 100.0)
        self.assertEqual(p.trade_request_since, "Summer 2003")
        q = star()
        q.frustration = 50.0
        self.assertIsNone(tr.season_end(q, team_of([q]), era=ERA, made_playoffs=True, since="Summer 2003"))
        self.assertEqual(q.frustration, 30.0)

    def test_request_sticky_when_ovr_drops(self):
        p = star()
        t = team_of([p])
        bad_ticks(p, t, 24)
        p.valutazione = 80
        p.morale = 55   # neither stuck nor happy: a small drift
        self.assertEqual(bad_ticks(p, t, 1, win_pct=0.5), [])
        self.assertTrue(p.trade_request)

    def test_missing_fields_default(self):
        p = star()
        for name in ("frustration", "trade_request", "trade_request_since"):
            self.assertNotIn(name, vars(p))   # built with Giocatore.__new__, like old objects
        self.assertIsNone(tr.tick(p, team_of([p]), era=ERA, plan="MIDDLE", win_pct=0.3, games=60, since=SINCE))
        self.assertEqual(p.frustration, CONFIG.TRADE_REQUESTS.RISE_PER_TICK)

    def test_can_request_follows_era(self):
        high = era_of(star=88, core=83)
        p = star(ovr=86)
        self.assertTrue(tr.can_request(p, ERA))
        self.assertFalse(tr.can_request(p, high))


def saveable(name="A", ovr=85):
    import dataclasses
    from core.models import Abilita
    p = make_player(name, ovr=ovr)
    p.abilita = Abilita(**{f.name: 60 for f in dataclasses.fields(Abilita)})
    return p


class PlayerStateTests(unittest.TestCase):
    def test_save_round_trip(self):
        from core.save_manager import deserialize_player, serialize_player
        p = saveable()
        p.frustration, p.trade_request, p.trade_request_since = 73.5, True, "Summer 2004"
        g = deserialize_player(serialize_player(p))
        self.assertEqual((g.frustration, g.trade_request, g.trade_request_since), (73.5, True, "Summer 2004"))

    def test_old_save_defaults(self):
        from core.save_manager import deserialize_player, serialize_player
        data = serialize_player(saveable())
        for key in ("frustration", "trade_request", "trade_request_since"):
            data.pop(key, None)
        g = deserialize_player(data)
        self.assertEqual((g.frustration, g.trade_request, g.trade_request_since), (0.0, False, ""))

    def test_reset_for_season_keeps_meter(self):
        p = saveable()
        p.frustration, p.trade_request, p.trade_request_since = 88.0, True, "Season 2003"
        p.morale = 30
        p.season_stats = SimpleNamespace(reset=lambda: None)
        p.playoff_stats = SimpleNamespace(reset=lambda: None)
        p.recupera_stamina_offseason = lambda: None
        p.reset_for_season()
        self.assertEqual(p.morale, 75)
        self.assertEqual((p.frustration, p.trade_request, p.trade_request_since), (88.0, True, "Season 2003"))

    def test_trade_clears_request(self):
        from trades.execution import _move_player
        p = star()
        p.frustration, p.trade_request, p.trade_request_since = 100.0, True, "Season 2003"
        p.on_trade_block = True
        src, dst = team_of([p], "Src"), team_of([], "Dst")
        _move_player(p, src, dst)
        self.assertEqual((p.frustration, p.trade_request, p.trade_request_since, p.on_trade_block),
                         (0.0, False, "", False))
        self.assertIn(p, dst.roster)


class RunnerTests(unittest.TestCase):
    """weekly_tick / end_of_season on a whole league (tests/trade_fixtures.make_torneo)."""

    def league(self, user_team=None, frustration=98.0):
        from tests.trade_fixtures import make_team, make_torneo
        losers, other = make_team("Losers", wins=10, losses=30), make_team("Other", wins=30, losses=10)
        p = make_player("Star", ovr=86, role="SF")
        p.morale, p.frustration = 30, frustration
        losers.roster.append(p)
        t = make_torneo([losers, other], user_team=user_team, plans={"Losers": "MIDDLE", "Other": "MIDDLE"})
        t.playoff_teams = {"east": [other], "west": []}
        return t, losers, p

    def run_patched(self, fn, torneo):
        from unittest import mock
        with mock.patch.object(tr, "era_lines_for", return_value=ERA), \
                mock.patch.object(tr, "add_news") as news:
            events = fn(torneo)
        return events, news

    def test_weekly_tick_requests_and_publishes(self):
        t, losers, p = self.league()
        events, news = self.run_patched(tr.weekly_tick, t)
        self.assertEqual([(e[0].nome, e[1].nome, e[2]) for e in events], [("Star", "Losers", "requested")])
        self.assertTrue(p.trade_request)
        self.assertEqual(p.trade_request_since, "Season 2003")
        self.assertEqual(news.call_count, 1)
        self.assertEqual(news.call_args.kwargs["players"], ["Star"])
        self.assertEqual(news.call_args.kwargs["teams"], ["Losers"])
        self.assertFalse(getattr(p, 'on_trade_block', False))   # a CPU player: his team shops him itself

    def test_user_player_goes_on_block(self):
        t, losers, p = self.league(user_team="Losers")
        t.is_spectator = False
        self.run_patched(tr.weekly_tick, t)
        self.assertTrue(p.trade_request)
        self.assertTrue(p.on_trade_block)

    def test_spectator_no_block_change(self):
        t, losers, p = self.league(user_team="Losers")
        t.is_spectator = True
        self.run_patched(tr.weekly_tick, t)
        self.assertTrue(p.trade_request)
        self.assertFalse(getattr(p, 'on_trade_block', False))

    def test_end_of_season_uses_playoff_teams(self):
        t, losers, p = self.league(frustration=90.0)
        p.morale = 75   # the summer check does not look at morale
        events, news = self.run_patched(tr.end_of_season, t)
        self.assertEqual([e[2] for e in events], ["requested"])
        self.assertEqual(p.trade_request_since, "Summer 2003")
        other_star = t.squadre[1].roster[0]
        self.assertEqual(other_star.frustration, 0.0)   # made the playoffs: relief, clamped at 0

    def test_news_failure_does_not_break_the_tick(self):
        from unittest import mock
        t, losers, p = self.league()
        with mock.patch.object(tr, "era_lines_for", return_value=ERA), \
                mock.patch.object(tr, "add_news", side_effect=RuntimeError("feed down")):
            tr.weekly_tick(t)
        self.assertTrue(p.trade_request)


class RequestPriceTests(unittest.TestCase):
    """A team getting a player who asked out may pay a starter plus more picks than in a swap of two starters."""

    def refusal(self, request):
        from unittest import mock
        from tests.trade_fixtures import finder, make_team, make_torneo
        from trades.trade_finder import TradeFinder
        star_in = make_player("Wanted", ovr=87, role="SF")
        star_in.trade_request = request
        starter_out = make_player("Starter", ovr=ERA.starter + 2, role="SF")
        f = finder(make_torneo([make_team("A"), make_team("B")]))
        with mock.patch.object(TradeFinder, "era", return_value=ERA):
            return f._pick_giving_refusal([star_in], [starter_out, "2004:R1-A", "2006:R1-A"])

    def test_two_firsts_with_a_starter_for_a_requester(self):
        self.assertEqual(self.refusal(True), "")

    def test_swap_rule_stays_for_everyone_else(self):
        self.assertIn("Starter Swap Rule", self.refusal(False))

    def test_a_requester_is_worth_less_to_his_own_team(self):
        from unittest import mock
        from tests.trade_fixtures import finder, make_team, make_torneo
        from trades.trade_finder import TradeFinder
        own, other = make_team("Own"), make_team("Other")
        p = make_player("Wanted", ovr=87, role="SF")
        own.roster.append(p)
        f = finder(make_torneo([own, other], plans={"Own": "MIDDLE", "Other": "MIDDLE"}))
        with mock.patch.object(TradeFinder, "era", return_value=ERA):
            before_own, before_other = f.get_strategic_value(p, own), f.get_strategic_value(p, other)
            p.trade_request = True
            after_own, after_other = f.get_strategic_value(p, own), f.get_strategic_value(p, other)
        self.assertAlmostEqual(after_own, before_own * CONFIG.TRADE_REQUESTS.OWN_VALUE_SHARE)
        self.assertAlmostEqual(after_other, before_other)


class ReviewFixTests(unittest.TestCase):
    """Findings of the final review: stale flags, free agency, fed-up players under the line."""

    def test_signing_in_free_agency_starts_clean(self):
        from tests.test_front_office_moves import HookTests, make_team as fo_team, make_torneo as fo_torneo
        a, b = fo_team("A"), fo_team("B")
        t = fo_torneo([a, b], fase="OFFSEASON")
        p = saveable("Walker", ovr=88)
        p.frustration, p.trade_request, p.trade_request_since = 100.0, True, "Season 2003"
        p._wants_out = True
        fa = HookTests.make_fa(None, t, [a, b], {"Walker": b})
        fa._firma_giocatore(a, p, 12.5, "CAP SPACE", 3)
        self.assertEqual((p.frustration, p.trade_request, p.trade_request_since, p._wants_out),
                         (0.0, False, "", False))

    def test_request_is_not_untouchable_after_a_reload(self):
        """_wants_out is a cache that a reload loses: the saved request must exempt him on its own."""
        from unittest import mock
        from tests.trade_fixtures import finder, make_team, make_torneo
        from trades.trade_finder import TradeFinder
        own, user = make_team("Own", ovrs=[72] * 12), make_team("User", ovrs=[86, 84] + [72] * 10)
        req = make_player("Req", ovr=87, role="SF")
        req.trade_request, req.is_untouchable, req._wants_out = True, True, False
        own.roster.append(req)
        t = make_torneo([own, user], user_team="User", plans={"Own": "MIDDLE", "User": "MIDDLE"})
        f = TradeFinder(t, t.squadre, user, manual=True)
        with mock.patch.object(TradeFinder, "era", return_value=ERA):
            ok, reason = f.would_accept_trade_with_reason(own, user.roster[:1], [req])   # an 86 for him
        self.assertEqual((ok, reason), (True, "Accepted"))

    def test_designa_intoccabili_skips_a_saved_request(self):
        from core.models import Squadra
        team = Squadra.__new__(Squadra)
        star = make_player("Face", ovr=90, age=27)
        star.trade_request, star.is_flight_risk = True, False
        team.nome, team.roster = "Own", [star, make_player("Other", ovr=70)]
        for q in team.roster:
            q.is_flight_risk = False
            q.get_tier = lambda: "Superstar"
        torneo = SimpleNamespace(campione=None, regular_season_mvp=None, all_nba_teams=[], front_office=None)
        team.designa_intoccabili(torneo)
        self.assertFalse(star.is_untouchable)

    def test_fed_up_walker_under_the_line_is_no_star_demand(self):
        from core.front_office.contracts import FED_UP
        from core.front_office.wishes import build_wishes
        from tests.test_wishes import ctx_of, roster_with, team_of as wish_team
        bench = make_player("Bench", ovr=70, role="SF")
        bench.walks_away = FED_UP
        wishes = build_wishes(wish_team(roster_with(bench)), ctx_of())
        self.assertNotIn("Bench", [w.player for w in wishes if w.kind == "STAR_WANTS_OUT"])


class MinorFixTests(unittest.TestCase):
    """Deferred minors done on 2026-11-19: price that falls with the wait, block flag, saved tick guards, news."""

    def own_value(self, weeks):
        from unittest import mock
        from tests.trade_fixtures import finder, make_team, make_torneo
        from trades.trade_finder import TradeFinder
        own = make_team("Own")
        p = make_player("Wanted", ovr=89, age=24, role="PF")
        own.roster.append(p)
        f = finder(make_torneo([own, make_team("Other")], plans={"Own": "REBUILDER", "Other": "MIDDLE"}))
        with mock.patch.object(TradeFinder, "era", return_value=ERA):
            base = f.get_strategic_value(p, own)
            p.trade_request, p.trade_request_weeks = True, weeks
            return f.get_strategic_value(p, own) / base

    def test_his_price_falls_the_longer_he_waits(self):
        c = CONFIG.TRADE_REQUESTS
        self.assertAlmostEqual(self.own_value(0), c.OWN_VALUE_SHARE)
        self.assertAlmostEqual(self.own_value(10), c.OWN_VALUE_SHARE - 10 * c.OWN_VALUE_DECAY_PER_WEEK)
        self.assertAlmostEqual(self.own_value(100), c.OWN_VALUE_FLOOR)

    def test_weeks_count_only_while_requesting(self):
        p = star()
        t = team_of([p])
        bad_ticks(p, t, 20)   # the request opens on the 20th tick
        self.assertEqual(p.trade_request_weeks, 0)
        bad_ticks(p, t, 3)
        self.assertEqual(p.trade_request_weeks, 3)
        p.morale = 70
        bad_ticks(p, t, 30, win_pct=0.6)   # withdrawn
        self.assertEqual(p.trade_request_weeks, 0)

    def test_withdrawal_takes_him_off_a_block_the_request_put_him_on(self):
        from tests.trade_fixtures import make_team, make_torneo
        from unittest import mock
        mine = make_team("Mine", wins=10, losses=30)
        p = make_player("Mine Star", ovr=86, role="SF")
        p.morale, p.frustration = 30, 98.0
        mine.roster.append(p)
        t = make_torneo([mine, make_team("Other")], user_team="Mine", plans={"Mine": "MIDDLE", "Other": "MIDDLE"})
        t.is_spectator = False
        with mock.patch.object(tr, "era_lines_for", return_value=ERA), mock.patch.object(tr, "add_news"):
            tr.weekly_tick(t)
            self.assertTrue(p.on_trade_block)
            p.morale, p.frustration = 80, 41.0
            mine.vittorie, mine.sconfitte = 40, 10
            tr.weekly_tick(t)
        self.assertFalse(p.trade_request)
        self.assertFalse(p.on_trade_block)

    def test_withdrawal_keeps_a_block_the_user_chose(self):
        p = star()
        p.on_trade_block = True   # the user put him there before he asked out
        t = team_of([p])
        bad_ticks(p, t, 24)
        self.assertFalse(getattr(p, 'trade_block_by_request', False))
        p.morale = 70
        bad_ticks(p, t, 30, win_pct=0.6)
        self.assertTrue(p.on_trade_block)

    def test_new_fields_round_trip(self):
        from core.save_manager import deserialize_player, serialize_player
        p = saveable()
        p.trade_request, p.trade_request_weeks, p.trade_block_by_request = True, 7, True
        g = deserialize_player(serialize_player(p))
        self.assertEqual((g.trade_request_weeks, g.trade_block_by_request), (7, True))
        data = serialize_player(saveable())
        data.pop("trade_request_weeks"), data.pop("trade_block_by_request")
        g = deserialize_player(data)
        self.assertEqual((g.trade_request_weeks, g.trade_block_by_request), (0, False))

    def test_tick_and_summer_run_once_even_after_a_reload(self):
        t = SimpleNamespace(season_number=2)
        self.assertTrue(tr.tick_due(t, 14))
        self.assertFalse(tr.tick_due(t, 14))
        self.assertTrue(tr.tick_due(t, 21))
        self.assertTrue(tr.summer_due(t))
        self.assertFalse(tr.summer_due(t))
        reloaded = SimpleNamespace(season_number=2, trade_requests_last_tick=t.trade_requests_last_tick,
                                   trade_requests_summer=t.trade_requests_summer)
        self.assertFalse(tr.tick_due(reloaded, 21))
        self.assertFalse(tr.summer_due(reloaded))

    def test_tick_guards_are_saved(self):
        from core import save_manager
        src = open(save_manager.__file__, encoding="utf-8").read()
        for key in ("trade_requests_last_tick", "trade_requests_summer"):
            self.assertIn(f'"{key}": getattr(tournament_instance, \'{key}\'', src)
            self.assertIn(f'tournament_instance.{key} = state_data.get("{key}"', src)


class FedUpNewsTests(unittest.TestCase):
    def run_walkers(self, ovr):
        from unittest import mock
        from core.front_office import contracts
        from offseason.contract_extensions import ContractExtensions
        from tests.test_wishes import ctx_of, roster_with, team_of as wish_team
        p = make_player("Fed", ovr=ovr, age=27, years=1, role="SF")
        p.frustration, p.is_flight_risk, p.is_untouchable, p.walks_away = 100.0, False, False, ""
        team = wish_team(roster_with(p), name="Team")
        team.vittorie, team.sconfitte = 30, 30
        torneo = SimpleNamespace(squadra_giocatore=None, squadre=[team], season_number=1)
        with mock.patch.object(contracts, "context_for", lambda torneo, team: ctx_of("MIDDLE", win_pct=0.5)), \
                mock.patch("offseason.contract_extensions.add_news") as news:
            ContractExtensions(torneo, [team]).mark_walkers()
        self.assertEqual(p.walks_away, contracts.FED_UP)
        return news

    def test_a_fed_up_bench_player_leaves_quietly(self):
        self.assertFalse(self.run_walkers(ERA.rotation - 1).called)

    def test_a_fed_up_rotation_player_is_news_but_not_breaking(self):
        news = self.run_walkers(ERA.starter)
        self.assertEqual(news.call_count, 1)
        self.assertFalse(news.call_args.kwargs["is_breaking"])


if __name__ == "__main__":
    unittest.main()
