"""The news store (core/news_generator.py), its tier rules, the rumor generator and the /api/news routes."""
import unittest
from types import SimpleNamespace
from unittest import mock

from core import news_generator as news
from core.config import CONFIG
from core.models import Giocatore


class NewsCase(unittest.TestCase):
    def setUp(self):
        self._feed = list(news.NEWS_FEED)
        self._state = (news.NEWS_ID_COUNTER, news.LAST_SEEN_ID, news._CLOCK_PROVIDER, dict(news._CLOCK))
        news.reset_news()
        news.set_clock_provider(None)
        self.addCleanup(self._restore)

    def _restore(self):
        news.NEWS_FEED[:] = self._feed
        news.NEWS_ID_COUNTER, news.LAST_SEEN_ID, provider, clock = self._state
        news.set_clock_provider(provider)
        news._CLOCK.update(clock)


class TestStore(NewsCase):
    def test_legacy_call_gets_kind_tier_and_a_clean_title(self):
        item = news.add_news("trades", "🔄 TRADE COMPLETED!", "A sends X to B", teams=["A", "B"], is_breaking=True)
        self.assertEqual((item["kind"], item["tier"], item["title"]), ("trade", 2, "TRADE COMPLETED!"))
        self.assertEqual(item["body"], "A sends X to B")
        self.assertNotIn("author", item)
        self.assertEqual(news.add_news("general", "🚨 FIRED: The A fire coach Z", "")["kind"], "firing")
        self.assertEqual(news.add_news("signings", "CUT: A cut Z", "")["kind"], "cut")
        self.assertEqual(news.add_news("signings", "Z will not re-sign with the A", "")["kind"], "free_agency")
        self.assertEqual(news.add_news("signings", "Z extends with the A", "")["kind"], "extension")
        self.assertEqual(news.add_news("general", "OFFICIAL: Y is the new Head Coach of the A", "")["kind"], "hiring")
        self.assertEqual(news.add_news("highlights", "A lead the East", "", is_breaking=False)["tier"], 1)

    def test_structured_call_keeps_what_it_is_given(self):
        item = news.add_news("rumor", "Z unhappy", "body", teams=["A", ""], kind="rumor", tier=3, players=["Z"],
                             details={"morale": 40})
        self.assertEqual((item["kind"], item["tier"], item["teams"], item["players"]), ("rumor", 3, ["A"], ["Z"]))
        self.assertEqual(item["details"], {"morale": 40})

    def test_items_carry_the_game_clock(self):
        news.set_clock(season=4, day=46, date="2003-01-11", phase="Regular season")
        item = news.add_news("injuries", "Z out", "")
        self.assertEqual((item["season"], item["day"], item["date"], item["phase"]),
                         (4, 46, "2003-01-11", "Regular season"))
        news.set_clock_provider(lambda: {"season": 5, "day": None, "date": "", "phase": "Playoffs"})
        item = news.add_news("playoffs", "A eliminate B", "")
        self.assertEqual((item["season"], item["day"], item["phase"]), (5, None, "Playoffs"))
        self.assertEqual(news.add_news("trades", "t", "", season=9)["season"], 9)

    def test_a_failing_clock_provider_falls_back(self):
        news.set_clock(season=2, day=3)
        news.set_clock_provider(lambda: 1 / 0)
        self.assertEqual(news.add_news("trades", "t", "")["day"], 3)

    def test_feed_is_newest_first_and_capped(self):
        for i in range(CONFIG.NEWS.MAX_ITEMS + 5):
            news.add_news("trades", f"t{i}", "")
        self.assertEqual(len(news.NEWS_FEED), CONFIG.NEWS.MAX_ITEMS)
        self.assertEqual(news.NEWS_FEED[0]["title"], f"t{CONFIG.NEWS.MAX_ITEMS + 4}")

    def test_view_raises_the_user_team_and_marks_unread(self):
        seen = news.add_news("injuries", "old", "", teams=["A"], kind="injury", tier=2)
        news.mark_all_seen()
        fresh = news.add_news("injuries", "new", "", teams=["B"], kind="injury", tier=2)
        mine = news.view_item(seen, "A")
        self.assertEqual((mine["mine"], mine["tier"], mine["unread"]), (True, 3, False))
        other = news.view_item(fresh, "A")
        self.assertEqual((other["mine"], other["tier"], other["unread"]), (False, 2, True))
        self.assertEqual(seen["tier"], 2)  # the stored item is not changed

    def test_save_round_trip_keeps_items_and_last_seen(self):
        news.add_news("trades", "one", "", kind="trade", tier=3, players=["Z"], details={"sides": []})
        news.mark_all_seen()
        news.add_news("injuries", "two", "")
        saved = news.export_raw_news()
        news.reset_news()
        news.import_raw_news(saved)
        self.assertEqual([i["title"] for i in news.NEWS_FEED], ["two", "one"])
        self.assertEqual((news.get_last_seen_id(), news.NEWS_ID_COUNTER), (1, 2))
        self.assertEqual(news.add_news("trades", "three", "")["id"], 3)

    def test_old_social_save_loads_as_read_news(self):
        feed = news.NEWS_FEED
        news.import_raw_news([
            {"id": 7, "category": "user", "title": "my post", "excerpt": "hi"},
            {"id": 6, "category": "injuries", "title": "⚠️ INJURY: Z out for weeks", "excerpt": "Out 30 days.",
             "teams": ["A"], "is_breaking": True, "timestamp": "12:03", "season": 2,
             "author": {"name": "x"}, "stats": {"likes": 3}, "replies": [{"text": "wow"}]},
        ])
        self.assertIs(news.NEWS_FEED, feed)  # same list object: other modules hold it
        self.assertEqual(len(feed), 1)
        item = feed[0]
        self.assertEqual((item["kind"], item["tier"], item["title"], item["body"], item["day"]),
                         ("injury", 2, "INJURY: Z out for weeks", "Out 30 days.", None))
        self.assertNotIn("replies", item)
        self.assertFalse(news.view_item(item)["unread"])


class TestGenerators(NewsCase):
    def test_tier_rules(self):
        cfg = CONFIG.NEWS
        self.assertEqual([news.trade_tier(v) for v in (cfg.TRADE_BIG_OVR, cfg.TRADE_MEDIUM_OVR, 60, None)],
                         [3, 2, 1, 2])
        self.assertEqual(news.injury_tier(cfg.INJURY_LONG_DAYS, cfg.INJURY_STAR_OVR), 3)
        self.assertEqual(news.injury_tier(cfg.INJURY_LONG_DAYS, 70), 2)
        self.assertEqual(news.injury_tier(10, cfg.INJURY_STAR_OVR), 2)
        self.assertEqual(news.injury_tier(10, 70), 1)

    def test_injury_news(self):
        news.generate_injury_news("Z", "A", CONFIG.NEWS.INJURY_MIN_DAYS - 1, ovr=90)
        self.assertEqual(news.NEWS_FEED, [])
        news.generate_injury_news("Z", "A", 42, ovr=90, season=2)
        item = news.NEWS_FEED[0]
        self.assertEqual((item["kind"], item["tier"], item["players"], item["title"]),
                         ("injury", 3, ["Z"], "Z out about 6 weeks"))

    def test_an_injury_is_told_once(self):
        news.set_clock(season=2, day=10)
        news.generate_injury_news("Z", "A", 30, ovr=70, season=2)
        news.set_clock(season=2, day=25)   # still out (save reloaded): no second story
        news.generate_injury_news("Z", "A", 15, ovr=70, season=2)
        self.assertEqual(len(news.NEWS_FEED), 1)
        news.set_clock(season=2, day=45)   # healed since day 40: this is a new injury
        news.generate_injury_news("Z", "A", 15, ovr=70, season=2)
        news.generate_injury_news("Y", "A", 15, ovr=70, season=2)
        self.assertEqual(len(news.NEWS_FEED), 3)

    def test_one_rivalry_story_per_pair_per_season(self):
        heated = {"has_rivalry": True, "level": "heated"}
        for _ in range(4):
            news.generate_rivalry_postgame_news("A", "B", 101, 99, heated, season=3)
            news.generate_rivalry_postgame_news("B", "A", 130, 100, heated, season=3)
        news.generate_rivalry_postgame_news("A", "C", 101, 99, heated, season=3)
        news.generate_rivalry_postgame_news("A", "B", 101, 99, heated, season=4)
        self.assertEqual(len(news.NEWS_FEED), CONFIG.NEWS.RIVALRY_MAX_PER_PAIR_SEASON * 2 + 1)

    def test_front_office_news(self):
        news.generate_front_office_news("fired", "A", "GM", "Rick Choi", season=3)
        news.generate_front_office_news("hired", "A", "coach", "Sam Hale", season=3)
        news.generate_front_office_news("retired", "B", "GM", "Neal Oshay", season=3)
        self.assertEqual([(i["kind"], i["tier"], i["title"]) for i in reversed(news.NEWS_FEED)],
                         [("firing", 2, "A fire GM Rick Choi"), ("hiring", 2, "A hire Sam Hale as head coach"),
                          ("league", 1, "GM Neal Oshay retires")])

    def test_firing_tier(self):
        self.assertEqual((news.firing_tier("Phil Gustafson"), news.firing_tier("Interim Joe Brown")), (2, 1))

    def test_performance_news_only_for_rare_games(self):
        stats = SimpleNamespace(punti=41, rimbalzi=5, assist=4, steals=1, blocks=0)
        self.assertFalse(news.generate_game_performance_news(stats, "Z", "A", "B"))
        stats.punti = CONFIG.NEWS.PERF_BIG_POINTS + 1
        self.assertTrue(news.generate_game_performance_news(stats, "Z", "A", "B"))
        item = news.NEWS_FEED[0]
        self.assertEqual((item["kind"], item["tier"], item["teams"]), ("performance", 3, ["A", "B"]))
        self.assertEqual(item["details"]["line"]["pts"], stats.punti)

    def test_signing_and_draft_news(self):
        news.generate_signing_news("Z", "A", contract_info="$10M/3y", is_star=True)
        news.generate_signing_news("Y", "A", ovr=CONFIG.NEWS.SIGNING_BIG_OVR)
        news.generate_signing_news("X", "A")
        self.assertEqual([i["tier"] for i in news.NEWS_FEED], [1, 3, 2])
        news.reset_news()
        news.generate_draft_news([{"nome": "P1", "squadra": "A", "valutazione": 72, "potenziale": 88},
                                  {"nome": "P2", "squadra": "B", "ovr": 70, "pot": 80}])
        first = news.NEWS_FEED[1]
        self.assertEqual((first["title"], first["tier"], first["body"]),
                         ("A select P1 with the No. 1 pick", 3, "Overall 72, potential 88."))

    def _league(self, **player):
        base = dict(nome="Z", ovr=CONFIG.NEWS.RUMOR_BIG_OVR, morale=CONFIG.NEWS.RUMOR_MORALE_MAX,
                    contract=SimpleNamespace(anni_rimanenti=1))
        base.update(player)
        team = SimpleNamespace(nome="A", vittorie=14, sconfitte=25, roster=[
            SimpleNamespace(**base),
            SimpleNamespace(nome="Happy", ovr=90, morale=80, contract=SimpleNamespace(anni_rimanenti=3)),
            SimpleNamespace(nome="Bench", ovr=CONFIG.NEWS.RUMOR_MIN_OVR - 1, morale=10, contract=None),
        ])
        return SimpleNamespace(season_number=3, squadre=[team])

    def test_rumor_for_an_unhappy_player_once_per_season(self):
        always = SimpleNamespace(random=lambda: 0.0)
        league = self._league()
        self.assertEqual(news.generate_rumor_news(league, rng=always), 1)
        item = news.NEWS_FEED[0]
        self.assertEqual((item["kind"], item["tier"], item["players"], item["teams"]), ("rumor", 3, ["Z"], ["A"]))
        self.assertIn("free agency", item["body"])
        self.assertEqual(news.generate_rumor_news(league, rng=always), 0)
        league.season_number = 4
        self.assertEqual(news.generate_rumor_news(league, rng=always), 1)

    def test_rumor_only_about_the_best_unhappy_player_of_a_team(self):
        league = self._league()
        league.squadre[0].roster.append(SimpleNamespace(
            nome="Second", ovr=CONFIG.NEWS.RUMOR_MIN_OVR, morale=5, contract=SimpleNamespace(anni_rimanenti=2)))
        always = SimpleNamespace(random=lambda: 0.0)
        self.assertEqual(news.generate_rumor_news(league, rng=always), 1)
        self.assertEqual(news.NEWS_FEED[0]["players"], ["Z"])
        self.assertEqual(news.generate_rumor_news(league, rng=always), 1)  # next check: the next player
        self.assertEqual(news.NEWS_FEED[0]["players"], ["Second"])

    def test_rumor_needs_the_dice_and_mentions_a_trade_when_under_contract(self):
        never = SimpleNamespace(random=lambda: 0.99)
        self.assertEqual(news.generate_rumor_news(self._league(), rng=never), 0)
        league = self._league(ovr=CONFIG.NEWS.RUMOR_MIN_OVR, contract=SimpleNamespace(anni_rimanenti=3))
        news.generate_rumor_news(league, rng=SimpleNamespace(random=lambda: 0.0))
        self.assertEqual(news.NEWS_FEED[0]["tier"], 2)
        self.assertIn("trade", news.NEWS_FEED[0]["body"])


class TestTradeNews(NewsCase):
    def test_trade_item_has_sides_and_gm_reasons(self):
        from trades.execution import _publish_news
        from trades.motive import SideMotive, TradeMotive
        star = Giocatore.__new__(Giocatore)
        star.nome, star.valutazione = "Sam Carter", CONFIG.NEWS.TRADE_BIG_OVR
        role = Giocatore.__new__(Giocatore)
        role.nome, role.valutazione = "Saul Porter", 74
        moves = [("PHI", "DAL", star), ("DAL", "PHI", role), ("DAL", "PHI", "1:R1-DAL")]
        deal = SimpleNamespace(
            moves=moves, reason="fallback", team_names=lambda: ["DAL", "PHI"],
            receives=lambda name: [a for _, dst, a in moves if dst == name])
        finder = SimpleNamespace(torneo=SimpleNamespace(season_number=2),
                                 _format_asset=lambda a, prot=None: getattr(a, "nome", a))
        motive = TradeMotive(trade_type="star", why="DAL needed a second scorer", sides=[
            SideMotive(team="DAL", gm_name="GM One", plan="CONTENDER", reasons=["needed a second scorer"]),
            SideMotive(team="PHI", gm_name="GM Two", plan="REBUILDER", reasons=["wants picks"])])
        _publish_news(finder, deal, "log line", motive, None)
        item = news.NEWS_FEED[0]
        self.assertEqual((item["kind"], item["tier"], item["title"], item["body"]),
                         ("trade", 3, "DAL acquire Sam Carter from PHI", "DAL needed a second scorer"))
        self.assertEqual(item["players"], ["Sam Carter", "Saul Porter"])
        dal, phi = item["details"]["sides"]
        self.assertEqual((dal["gets"], dal["gm"], dal["reasons"]), (["Sam Carter"], "GM One", ["needed a second scorer"]))
        self.assertEqual(phi["gets"], ["Saul Porter", "1:R1-DAL"])


class TestNewsRoutes(NewsCase):
    def setUp(self):
        super().setUp()
        import server
        self.server = server
        self.client = server.app.test_client()
        league = SimpleNamespace(season_number=3, squadra_giocatore=SimpleNamespace(nome="A"), _current_gameday=4,
                                 calendario=[SimpleNamespace(date=f"2002-11-0{i + 1}") for i in range(6)])
        for name, value in (("SIMULATION_TOURNAMENT", league), ("LEAGUE_STATE", "PRE_SEASON")):
            patcher = mock.patch.object(server, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        news.set_clock_provider(server._news_clock)

    def test_clock_follows_the_league(self):
        self.assertEqual(news.get_clock(), {"season": 3, "day": 4, "date": "2002-11-05", "phase": "Regular season"})
        with mock.patch.object(self.server, "LEAGUE_STATE", "PLAYOFFS_IN_PROGRESS"):
            self.assertEqual(news.get_clock()["phase"], "Playoffs")
            self.assertIsNone(news.get_clock()["day"])
        with mock.patch.object(self.server, "LEAGUE_STATE", "OFFSEASON_UFA_START"):
            self.assertEqual(news.get_clock()["phase"], "Offseason")

    def test_feed_filters_and_seen(self):
        news.add_news("injuries", "mine", "", teams=["A"], kind="injury", tier=2)
        news.add_news("trades", "big", "", teams=["B", "C"], kind="trade", tier=3)
        news.add_news("signings", "small", "", teams=["B"], kind="signing", tier=1)

        data = self.client.get("/api/news").get_json()
        self.assertEqual([i["title"] for i in data["news"]], ["small", "big", "mine"])
        self.assertEqual((data["unread_big"], data["last_seen_id"], data["clock"]["day"]), (2, 0, 4))
        self.assertEqual(data["news"][2]["tier"], 3)  # the user's team story is raised

        get = lambda query: [i["title"] for i in self.client.get(f"/api/news?{query}").get_json()["news"]]
        self.assertEqual(get("min_tier=3"), ["big", "mine"])
        self.assertEqual(get("mine=1"), ["mine"])
        self.assertEqual(get("kind=trade,signing"), ["small", "big"])
        self.assertEqual(get("after_id=2"), ["small"])
        self.assertEqual(get("limit=1"), ["small"])
        self.assertEqual(get("season=2"), [])
        self.assertEqual(self.client.get("/api/news?limit=abc").status_code, 400)

        self.assertEqual(self.client.post("/api/news/seen").get_json(), {"last_seen_id": 3})
        self.assertEqual(self.client.get("/api/news").get_json()["unread_big"], 0)

    def test_social_routes_are_gone(self):
        for route in ("/api/news/post", "/api/news/reply", "/api/news/vote"):
            self.assertIn(self.client.post(route, json={}).status_code, (404, 405))


if __name__ == "__main__":
    unittest.main()
