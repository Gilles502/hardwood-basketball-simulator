"""One executor for any deal (trades/execution.py): players, picks, validation, log and the motive record."""
import unittest
from unittest import mock

from trades.execution import Deal, execute_deal, transfer_pick
from trades.motive import SideMotive, TradeMotive, user_side_motive
from trades.trade_finder import TradeFinder
from tests.trade_fixtures import make_team, make_torneo, finder


def league(*names, user_team=None, fase="SEASON"):
    teams = [make_team(n) for n in names]
    t = make_torneo(teams, user_team=user_team)
    t.fase_torneo = fase
    t.trade_analytics_history = []
    # Every team owns its own picks for five drafts, so the Stepien rule never gets in the way.
    t.pick_ownership = {y: {f"R{r}-{n}": n for n in names for r in (1, 2)} for y in range(1, 6)}
    t.pick_protections = {y: {} for y in range(1, 6)}
    return t, teams


class ExecutionTestCase(unittest.TestCase):
    def setUp(self):
        # No writes to the real trades_history.txt or the news feed.
        patches = [mock.patch.object(TradeFinder, "_log_trade_to_file"), mock.patch("core.news_generator.add_news")]
        self.log_file, self.news = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)


class DealTests(unittest.TestCase):
    def test_gives_receives_and_with_team(self):
        a, b, c = make_team("A"), make_team("B"), make_team("C")
        pa, pb = a.roster[0], b.roster[0]
        deal = Deal(teams=[a, b], moves=[("A", "B", pa), ("B", "A", pb), ("B", "A", "1:R1-B")])
        self.assertEqual(deal.team_names(), ["A", "B"])
        self.assertEqual(deal.gives("A"), [pa])
        self.assertEqual(deal.receives("A"), [pb, "1:R1-B"])
        bigger = deal.with_team(c, [("C", "A", c.roster[0])])
        self.assertEqual(bigger.team_names(), ["A", "B", "C"])
        self.assertEqual(bigger.receives("A"), [pb, "1:R1-B", c.roster[0]])
        self.assertEqual(deal.team_names(), ["A", "B"])  # the original deal is untouched
        self.assertEqual(len(deal.moves), 3)


class TwoTeamTests(ExecutionTestCase):
    def test_swap_moves_players_and_resets_them(self):
        t, (a, b) = league("A", "B")
        pa, pb = a.roster[0], b.roster[0]
        pa._wants_out = True
        pa.on_trade_block = True
        ok = execute_deal(finder(t), Deal([a, b], [("A", "B", pa), ("B", "A", pb)]), None)
        self.assertTrue(ok)
        self.assertIn(pa, b.roster)
        self.assertNotIn(pa, a.roster)
        self.assertIn(pb, a.roster)
        self.assertIs(pa.squadra, b)
        self.assertIs(pb.squadra, a)
        for p in (pa, pb):
            self.assertEqual(p.morale, 95)
            self.assertEqual(p.giorni_cooldown_scambio, 30)
            self.assertEqual(p.anni_nella_squadra, 0)
            self.assertFalse(p.on_trade_block)
        self.assertFalse(pa._wants_out)

    def test_execute_trade_goes_through_execute_deal(self):
        t, (a, b) = league("A", "B")
        tf = finder(t)
        with mock.patch.object(TradeFinder, "execute_deal", return_value=True) as ex:
            self.assertTrue(tf.execute_trade(a, b, [a.roster[0]], [b.roster[0]], reason="r"))
        deal = ex.call_args[0][0]
        self.assertEqual(deal.team_names(), ["A", "B"])
        self.assertEqual(deal.reason, "r")

    def test_validator_failure_changes_nothing(self):
        t, (a, b) = league("A", "B")
        pa, pb = a.roster[0], b.roster[0]
        pb.giorni_cooldown_scambio = 5
        ok = finder(t).execute_trade(a, b, [pa, "2:R1-A"], [pb])
        self.assertFalse(ok)
        self.assertIn(pa, a.roster)
        self.assertIn(pb, b.roster)
        self.assertEqual(t.pick_ownership[2]["R1-A"], "A")
        self.assertEqual(t.trade_analytics_history, [])


class PickTests(ExecutionTestCase):
    def test_year_key_changes_owner_and_keeps_protection(self):
        t, (a, b) = league("A", "B")
        t.pick_ownership[2003] = {"R1-B": "B"}
        t.pick_protections[2003] = {"R1-B": "Top 5"}
        transfer_pick(finder(t), "2003:R1-B", b, a, None)
        self.assertEqual(t.pick_ownership[2003]["R1-B"], "A")
        self.assertEqual(t.pick_protections[2003]["R1-B"], "Top 5")

    def test_legacy_key_moves(self):
        t, (a, b) = league("A", "B")
        transfer_pick(finder(t), "R1-B", b, a, None)
        self.assertEqual(t.pick_ownership[1]["R1-B"], "A")  # the first year that holds it
        self.assertEqual(t.pick_ownership[2]["R1-B"], "B")

    def test_protection_from_the_deal_wins(self):
        t, (a, b) = league("A", "B")
        t.pick_protections[2]["R1-B"] = "Top 5"
        transfer_pick(finder(t), "2:R1-B", b, a, {"2:R1-B": "Top 10"})
        self.assertEqual(t.pick_protections[2]["R1-B"], "Top 10")
        transfer_pick(finder(t), "R1-A", a, b, {"R1-A": "Top 3"})
        self.assertEqual(t.pick_protections[1]["R1-A"], "Top 3")

    def test_given_protections_without_this_pick_keep_the_stored_one(self):
        t, (a, b) = league("A", "B")
        t.pick_protections[2]["R1-B"] = "Top 5"
        transfer_pick(finder(t), "2:R1-B", b, a, {})
        self.assertEqual(t.pick_protections[2]["R1-B"], "Top 5")
        transfer_pick(finder(t), "3:R1-B", b, a, {})
        self.assertEqual(t.pick_protections[3]["R1-B"], "Unprotected")

    def test_original_cpu_team_sets_its_own_protection(self):
        t, (a, b) = league("A", "B")
        tf = finder(t)
        with mock.patch.object(TradeFinder, "get_cpu_pick_protection", return_value="Top 3") as cpu:
            transfer_pick(tf, "2:R1-B", b, a, None)   # B is the original owner: B chooses
            transfer_pick(tf, "2:R1-B", a, b, None)   # now stored: kept
        cpu.assert_called_once_with(b, "R1-B")
        self.assertEqual(t.pick_protections[2]["R1-B"], "Top 3")

    def test_not_original_team_and_second_rounders_are_unprotected(self):
        t, (a, b) = league("A", "B")
        t.pick_ownership[2]["R1-B"] = "A"
        transfer_pick(finder(t), "2:R1-B", a, b, None)
        self.assertEqual(t.pick_protections[2]["R1-B"], "Unprotected")
        transfer_pick(finder(t), "2:R2-B", b, a, {"2:R2-B": "Top 5"})
        self.assertEqual(t.pick_ownership[2]["R2-B"], "A")
        self.assertEqual(t.pick_protections[2]["R2-B"], "Unprotected")

    def test_unknown_picks_are_ignored(self):
        t, (a, b) = league("A", "B")
        before = {y: dict(v) for y, v in t.pick_ownership.items()}
        tf = finder(t)
        for asset in ("9:R1-B", "x:R1-B", "R1-Nobody", "Some Name"):
            transfer_pick(tf, asset, b, a, None)
        self.assertEqual(t.pick_ownership, before)

    def test_deal_moves_picks(self):
        t, (a, b) = league("A", "B")
        pa, pb = a.roster[0], b.roster[0]
        ok = finder(t).execute_trade(a, b, [pa], [pb, "2:R1-B", "R2-B"], pick_protections={"2:R1-B": "Top 10"})
        self.assertTrue(ok)
        self.assertEqual(t.pick_ownership[2]["R1-B"], "A")
        self.assertEqual(t.pick_protections[2]["R1-B"], "Top 10")
        self.assertEqual(t.pick_ownership[1]["R2-B"], "A")


class MultiTeamTests(ExecutionTestCase):
    def triangle(self):
        t, (a, b, c) = league("A", "B", "C")
        pa, pb, pc = a.roster[0], b.roster[0], c.roster[0]
        deal = Deal([a, b, c], [("A", "B", pa), ("B", "C", pb), ("C", "A", pc), ("C", "A", "2:R1-C")])
        return t, (a, b, c), (pa, pb, pc), deal

    def test_three_team_moves_everything(self):
        t, (a, b, c), (pa, pb, pc), deal = self.triangle()
        self.assertTrue(execute_deal(finder(t), deal, None))
        self.assertIn(pa, b.roster)
        self.assertIn(pb, c.roster)
        self.assertIn(pc, a.roster)
        self.assertEqual([len(x.roster) for x in (a, b, c)], [13, 13, 13])
        self.assertEqual(t.pick_ownership[2]["R1-C"], "A")
        self.assertEqual(t.trade_analytics_history[-1]["team_count"], 3)

    def test_three_team_validator_failure_leaves_everything(self):
        t, (a, b, c), (pa, pb, pc), deal = self.triangle()
        pc.giorni_cooldown_scambio = 7
        rosters = [list(x.roster) for x in (a, b, c)]
        self.assertFalse(execute_deal(finder(t), deal, None))
        self.assertEqual([x.roster for x in (a, b, c)], rosters)
        self.assertEqual(pa.morale, 80)
        self.assertEqual(t.pick_ownership[2]["R1-C"], "C")
        self.assertEqual(t.trade_analytics_history, [])

    def test_three_team_salary_is_checked_per_team(self):
        t, (a, b, c), _, deal = self.triangle()
        b.check_trade_salary_match = lambda incoming, outgoing: (False, "too much")
        self.assertFalse(execute_deal(finder(t), deal, None))

    def test_player_not_on_the_giving_roster_is_refused(self):
        t, (a, b, c), (pa, pb, pc), deal = self.triangle()
        a.roster.remove(pa)
        self.assertFalse(execute_deal(finder(t), deal, None))
        self.assertNotIn(pa, b.roster)

    def test_execute_3_team_trade_wrapper(self):
        t, (a, b, c) = league("A", "B", "C")
        pa, pb, pc = a.roster[0], b.roster[0], c.roster[0]
        data = {"team_a": {"gives_to_b": [pa], "gives_to_c": []},
                "team_b": {"gives_to_a": [], "gives_to_c": [pb.nome]},   # names resolve to the player
                "team_c": {"gives_to_a": [pc, "2:R1-C"], "gives_to_b": []}}
        tf = finder(t)
        with mock.patch.object(TradeFinder, "execute_deal", wraps=tf.execute_deal) as ex:
            self.assertTrue(tf.execute_3_team_trade(a, b, c, data, pick_protections={"2:R1-C": "Top 3"}))
        ex.assert_called_once()
        self.assertIn(pa, b.roster)
        self.assertIn(pb, c.roster)
        self.assertIn(pc, a.roster)
        self.assertEqual(t.pick_protections[2]["R1-C"], "Top 3")
        self.assertEqual(t.trade_analytics_history[-1]["type"], "3-Team Blockbuster")

    def test_execute_4_team_trade_wrapper(self):
        t, teams = league("A", "B", "C", "D")
        a, b, c, d = teams
        players = [x.roster[0] for x in teams]
        flow = [{"from": "a", "to": "B", "players": [players[0]], "picks": ["2:R1-A"]},
                {"from": "B", "to": "C", "players": [players[1].nome], "picks": []},
                {"from": "C", "to": "D", "players": [players[2]], "picks": []},
                {"from": "D", "to": "A", "players": [players[3]], "picks": []}]
        tf = finder(t)
        with mock.patch.object(TradeFinder, "execute_deal", wraps=tf.execute_deal) as ex:
            self.assertTrue(tf.execute_4_team_trade(a, b, c, d, flow, reason="four"))
        ex.assert_called_once()
        for p, dest in zip(players, (b, c, d, a)):
            self.assertIn(p, dest.roster)
        self.assertEqual(t.pick_ownership[2]["R1-A"], "B")
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["team_count"], 4)
        self.assertEqual(rec["reason"], "four")

    def test_execute_4_team_trade_unknown_team(self):
        t, teams = league("A", "B", "C", "D")
        flow = [{"from": "A", "to": "Z", "players": [], "picks": []}]
        self.assertFalse(finder(t).execute_4_team_trade(*teams, flow))


class RecordTests(ExecutionTestCase):
    def motive(self):
        return TradeMotive("veteran_sale", "A turns a veteran into the future",
                           [SideMotive(team="A", gm_name="Pat", trade_skill=60, plan="REBUILDER",
                                       wish_kind="SELL_VETERANS", reasons=["x"], value_given=12.0,
                                       value_received=14.0),
                            SideMotive(team="B", plan="CONTENDER", wish_kind="RENT_VETERAN",
                                       value_given=9.0, value_received=8.0)], 2)

    def test_record_in_offseason_with_motive(self):
        t, (a, b) = league("A", "B", fase="OFFSEASON")
        pb = b.roster[0]
        deal = Deal([a, b], [("A", "B", a.roster[0]), ("B", "A", pb), ("B", "A", "2:R1-B")])
        self.assertTrue(execute_deal(finder(t), deal, self.motive()))
        self.assertEqual(len(t.trade_analytics_history), 1)
        rec = t.trade_analytics_history[0]
        self.assertEqual(rec["trade_type"], "veteran_sale")
        self.assertEqual(rec["why"], "A turns a veteran into the future")
        self.assertEqual(rec["phase"], "OFFSEASON")
        self.assertEqual(rec["team_count"], 2)
        self.assertEqual([m["value_given"] for m in rec["motives"]], [12.0, 9.0])
        self.assertEqual(rec["motives"][0]["gm_name"], "Pat")
        # the old fields are still there for the trade history and the season-end archive
        for key in ("id", "season", "game_day", "type", "reason", "teams", "date_recorded"):
            self.assertIn(key, rec)
        self.assertEqual(rec["type"], "2-Team")
        self.assertEqual(rec["teams"][1]["picks_sent"], ["2:R1-B"])
        self.assertEqual(rec["teams"][0]["players_received"][0]["name"], pb.nome)

    def test_log_line_comes_from_the_motive(self):
        t, (a, b) = league("A", "B")
        tf = finder(t)
        deal = Deal([a, b], [("A", "B", a.roster[0]), ("B", "A", b.roster[0])])
        execute_deal(tf, deal, self.motive())
        line = self.log_file.call_args[0][0]
        self.assertIn("Why: A turns a veteran into the future", line)
        self.assertIn("A get ", line)
        self.assertEqual(tf.logscambi[-1], line)
        # The news carries the why as its body and the full log line in its details.
        self.assertEqual(self.news.call_args.kwargs["excerpt"], "A turns a veteran into the future")
        self.assertEqual(self.news.call_args.kwargs["details"]["line"], line)
        self.assertEqual(self.news.call_args.kwargs["kind"], "trade")

    def test_execute_trade_without_motive_is_legacy(self):
        t, (a, b) = league("A", "B")
        tf = finder(t)
        self.assertTrue(tf.execute_trade(a, b, [a.roster[0]], [b.roster[0]], reason="Strategic Fit"))
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "legacy")
        self.assertEqual(rec["motives"], [])
        self.assertEqual(rec["why"], "")
        self.assertEqual(rec["reason"], "Strategic Fit")
        line = self.log_file.call_args[0][0]
        self.assertTrue(line.startswith("TRADE: A sends ["), line)   # the legacy line, parsed by old tools
        self.assertIn("<-->", line)
        self.assertTrue(line.endswith("Reason: Strategic Fit"), line)

    def test_user_trade_without_motive(self):
        t, (a, b) = league("A", "B", user_team="A")
        self.assertTrue(finder(t).execute_trade(a, b, [a.roster[0]], [b.roster[0]], reason="User Trade"))
        self.assertEqual(t.trade_analytics_history[-1]["trade_type"], "user")

    def test_execute_trade_passes_the_motive(self):
        t, (a, b) = league("A", "B", user_team="A")
        m = TradeMotive("user", "", [user_side_motive("A"), SideMotive(team="B", value_given=3.0)], 2)
        self.assertTrue(finder(t).execute_trade(a, b, [a.roster[0]], [b.roster[0]], motive=m))
        rec = t.trade_analytics_history[-1]
        self.assertEqual(rec["trade_type"], "user")
        self.assertEqual(rec["motives"][1]["value_given"], 3.0)

    def test_front_office_moves_logged(self):
        t, (a, b) = league("A", "B")
        pa, pb = a.roster[0], b.roster[0]
        self.assertTrue(finder(t).execute_trade(a, b, [pa], [pb]))
        self.assertEqual(t.front_office.moves["A"][0]["text"], f"Got {pb.nome} for {pa.nome}")


class CacheTests(ExecutionTestCase):
    def test_clear_only_named_teams(self):
        t, (a, b, c) = league("A", "B", "C")
        tf = finder(t)
        tf._needs_cache = {"A": ["PG"], "B": ["C"], "C": ["SF"]}
        tf._clear_trade_caches(["A", "B"])
        self.assertEqual(tf._needs_cache, {"C": ["SF"]})
        tf._clear_trade_caches()
        self.assertEqual(tf._needs_cache, {})

    def test_deal_clears_its_teams(self):
        t, (a, b, c) = league("A", "B", "C")
        tf = finder(t)
        tf._needs_cache = {"A": ["PG"], "B": ["C"], "C": ["SF"]}
        tf.execute_trade(a, b, [a.roster[0]], [b.roster[0]])
        self.assertEqual(tf._needs_cache, {"C": ["SF"]})


if __name__ == "__main__":
    unittest.main()
