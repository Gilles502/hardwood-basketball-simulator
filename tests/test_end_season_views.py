"""End of Season Hub phase views (core/end_season_views.py): pure functions over plain data, no Flask."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.franchise_legacy import get_team_branding
from core.end_season_views import trade_summary, cut_sheet_view, development_view, grade, new_season_view, team_strength, option_take, pick_label, trade_desk_view, options_money, season_recap_view

TOR = "Toronto Northmen"


def series(a, a_seed, a_wins, b, b_seed, b_wins):
    return {"s1_nome": a, "s1_seed": a_seed, "s1_vittorie": a_wins, "s2_nome": b, "s2_seed": b_seed,
            "s2_vittorie": b_wins, "winner_nome": a if a_wins > b_wins else b, "games": []}


def entry(user_rank=1, user_round="Playoffs", premi=None):
    teams = [(TOR, "East", 1, user_rank, 64, 116.9, 103.9, 13.2, user_round),
             ("Boston Minutemen", "East", 4, 6, 54, 112.0, 104.5, 6.0, "Finali Conference"),
             ("Memphis Blues", "West", 3, 3, 55, 115.0, 103.0, 8.0, "Campione NBA 🏆"),
             ("Chicago Gales", "East", 2, 2, 58, 110.0, 102.0, 7.0, "Finali NBA")]
    return {
        "stagione": 25, "anno": 2026, "campione": "Memphis Blues", "mvp_finali": "Emeka Lindqvist",
        "premi": premi if premi is not None else {
            "mvp": "Rafe Aldane", "dpoy": "Calder Galloway", "sesto_uomo": "Wendell Ravenhill",
            "roy": "Orrin Calloway", "mip": "N/A",
            "all_nba_1st": ["Rafe Aldane"], "all_nba_2nd": ["Zane Castellane"], "all_nba_3rd": ["Mekhi Northcott"],
            "all_defensive": [], "all_rookie": ["Orrin Calloway"],
            "all_star_starters": {"east": [], "west": []}, "all_star_reserves": {"east": ["Zane Castellane"], "west": []},
            "all_star_mvp": "Tavi Quillfeather", "three_point_contest": "Bastian Underhill", "dunk_contest": "Oswin Mabry"},
        "standings": [{"team": t, "conference": c, "conf_seed": s, "league_rank": r, "wins": w, "losses": 82 - w,
                       "playoff_round": pr} for t, c, s, r, w, _o, _d, _m, pr in teams],
        "team_stats": [{"team": t, "off_rating": o, "def_rating": d, "diff": m} for t, _c, _s, _r, _w, o, d, m, _p in teams],
    }


def bracket_second_round_loss():
    return {"east": {"play_in": [None, None, None], "qf": [series(TOR, 1, 4, "Orlando Citrus", 8, 1)],
                     "sf": [series("Boston Minutemen", 4, 4, TOR, 1, 2)],
                     "cf": [series("Chicago Gales", 2, 4, "Boston Minutemen", 4, 1)]},
            "west": {"play_in": [], "qf": [], "sf": [], "cf": []},
            "finals": [series("Memphis Blues", 3, 4, "Chicago Gales", 2, 2)]}


LINES = [{"name": "Zane Castellane", "ppg": 27.4, "rpg": 4.1, "apg": 5.0, "gp": 78},
         {"name": "Mekhi Northcott", "ppg": 15.0, "rpg": 9.8, "apg": 8.9, "gp": 70}]
TEAMS = {"Rafe Aldane": "Sacramento Prospectors", "Calder Galloway": "Miami Tide"}


def recap(e=None, b="default", user=TOR, lines=LINES):
    return season_recap_view(e or entry(), bracket_second_round_loss() if b == "default" else b, user, lines, TEAMS)


class SeasonRecapViewTest(unittest.TestCase):
    def test_verdict_lost_second_round(self):
        yours = recap()["yours"]
        self.assertEqual(yours["verdict"], "Best record, out in the second round")
        self.assertEqual(yours["run"], [
            {"round": "Round 1", "opponent": "Orlando Citrus", "opponent_seed": 8, "won": 4, "lost": 1, "result": "won"},
            {"round": "Second round", "opponent": "Boston Minutemen", "opponent_seed": 4, "won": 2, "lost": 4,
             "result": "lost"}])
        self.assertEqual(yours["beaten_by"], "Boston Minutemen")
        self.assertEqual(yours["beaten_by_result"], "Out in the conference finals")

    def test_empty_seed_is_none(self):
        b = bracket_second_round_loss()
        b["east"]["sf"] = [series("Boston Minutemen", "", 4, TOR, "", 2)]
        self.assertIsNone(recap(b=b)["yours"]["run"][1]["opponent_seed"])

    def test_verdict_champion(self):
        e = entry(user_rank=3, user_round="Campione NBA 🏆")
        b = bracket_second_round_loss()
        b["east"]["sf"] = [series(TOR, 1, 4, "Boston Minutemen", 4, 2)]
        b["east"]["cf"] = [series(TOR, 1, 4, "Chicago Gales", 2, 1)]
        b["finals"] = [series(TOR, 1, 4, "Memphis Blues", 3, 3)]
        self.assertEqual(recap(e, b)["yours"]["verdict"], "Champions")

    def test_verdict_missed_playoffs(self):
        b = {"east": {"play_in": [], "qf": [], "sf": [], "cf": []}, "west": {"play_in": [], "qf": [], "sf": [], "cf": []},
             "finals": []}
        yours = recap(entry(user_rank=20, user_round="Lottery"), b)["yours"]
        self.assertEqual((yours["verdict"], yours["run"]), ("Missed the playoffs", []))

    def test_play_in_row(self):
        b = bracket_second_round_loss()
        b["east"]["qf"] = []
        b["east"]["sf"] = []
        b["east"]["play_in"] = [series("Orlando Citrus", 7, 1, TOR, 8, 0), None, None]
        yours = recap(entry(user_rank=12), b)["yours"]
        self.assertEqual(yours["run"][0]["round"], "Play-In")
        self.assertEqual(yours["verdict"], "Out in the play-in")

    def test_ratings_ranks(self):
        yours = recap()["yours"]
        self.assertEqual((yours["off_rating"], yours["off_rank"], yours["def_rating"], yours["def_rank"], yours["margin"]),
                         (116.9, 1, 103.9, 3, 13.2))
        self.assertEqual((yours["wins"], yours["losses"], yours["seed"], yours["conference"]), (64, 18, 1, "East"))

    def test_zero_ratings_are_unknown(self):
        e = entry()
        for row in e["team_stats"]:
            row.update(off_rating=0.0, def_rating=0.0, diff=0.0)
        yours = recap(e)["yours"]
        self.assertEqual((yours["off_rating"], yours["off_rank"], yours["def_rating"], yours["def_rank"], yours["margin"]),
                         (None, None, None, None, None))

    def test_user_honours(self):
        honours = {h["player"]: h["honours"] for h in recap()["yours"]["honours"]}
        self.assertEqual(honours, {"Zane Castellane": ["All-League 2nd", "All-Star"], "Mekhi Northcott": ["All-League 3rd"]})

    def test_honour_team_marks_yours(self):
        teams = {t["key"]: t for t in recap()["league"]["honour_teams"]}
        self.assertEqual(teams["all_league_2nd"]["label"], "All-League 2nd")
        self.assertEqual(teams["all_league_2nd"]["players"], [{"name": "Zane Castellane", "yours": True}])
        self.assertEqual(teams["all_league_1st"]["players"], [{"name": "Rafe Aldane", "yours": False}])

    def test_trophies_and_missing_award(self):
        league = recap()["league"]
        trophies = {t["key"]: t for t in league["trophies"]}
        self.assertEqual([t["key"] for t in league["trophies"]],
                         ["mvp", "dpoy", "roy", "sixth_man", "mip", "all_star_mvp"])
        self.assertEqual(trophies["mvp"], {"key": "mvp", "label": "MVP", "winner": "Rafe Aldane",
                                           "team": "Sacramento Prospectors"})
        self.assertIsNone(trophies["mip"]["winner"])
        self.assertEqual(league["all_star_extra"], {"three_point": "Bastian Underhill", "dunk": "Oswin Mabry"})
        self.assertEqual(league["champion"]["team"], "Memphis Blues")
        self.assertEqual((league["runner_up"], league["finals_mvp"]), ("Chicago Gales", "Emeka Lindqvist"))

    def test_leaders_from_roster_lines(self):
        leaders = recap()["yours"]["leaders"]
        self.assertEqual(leaders["points"], {"player": "Zane Castellane", "value": 27.4})
        self.assertEqual(leaders["rebounds"], {"player": "Mekhi Northcott", "value": 9.8})

    def test_spectator_has_no_yours(self):
        view = recap(user=None)
        self.assertIsNone(view["yours"])
        self.assertEqual(view["year"], 2026)

    def test_recap_without_bracket(self):
        cases = {"Campione NBA 🏆": "Champions", "Finali NBA": "Lost in the Finals",
                 "Finali Conference": "Out in the conference finals", "Playoffs": "Out in the playoffs",
                 "Play-In": "Out in the play-in", "Lottery": "Missed the playoffs"}
        for saved, verdict in cases.items():
            yours = recap(entry(user_rank=5, user_round=saved), None)["yours"]
            self.assertEqual((yours["verdict"], yours["run"]), (verdict, []), saved)


LINES_CBA = {"salary_cap": 155.0, "luxury_tax": 185.0, "first_apron": 195.0, "second_apron": 205.0, "no_cap": False}


class ContractOptionsViewTest(unittest.TestCase):
    def test_option_take_over_market(self):
        self.assertEqual(option_take(12.4, 9.8, 18.0), "Solid rotation player, but $2.6M more than he'd get elsewhere.")

    def test_option_take_cheap(self):
        self.assertEqual(option_take(4.2, 6.0, 14.0), "Cheap for what he gives.")

    def test_option_take_fair(self):
        self.assertEqual(option_take(10.0, 10.5, 30.0), "Paid about what he's worth.")

    def test_option_take_roles(self):
        self.assertTrue(option_take(20.0, 10.0, 30.0).startswith("Solid starter"))
        self.assertTrue(option_take(20.0, 10.0, 5.0).startswith("Solid backup"))

    def test_money_exceptions_order(self):
        money = options_money(161.2, LINES_CBA)
        self.assertEqual((money["guaranteed"], money["cap"], money["tax"], money["apron1"], money["apron2"]),
                         (161.2, 155.0, 185.0, 195.0, 205.0))
        self.assertEqual(money["exceptions"], [{"above": None, "label": "Cap space"}, {"above": 155.0, "label": "Full MLE"},
                                               {"above": 195.0, "label": "Taxpayer MLE"},
                                               {"above": 205.0, "label": "No exception"}])
        self.assertFalse(money["no_cap"])

    def test_money_no_cap(self):
        money = options_money(80.0, {"salary_cap": None, "luxury_tax": None, "first_apron": None,
                                     "second_apron": None, "no_cap": True})
        self.assertTrue(money["no_cap"])
        self.assertEqual(money["exceptions"], [])


def dev(name, team, before, after, age=25, position="SF"):
    return {"name": name, "team": team, "age": age, "position": position, "ovr_before": before, "ovr_after": after}


def career(name, seasons=15, mvps=0, all_stars=0, titles=0, ppg=20.0):
    out = []
    for i in range(seasons):
        premi = (["MVP"] if i < mvps else []) + (["All-Star"] if i < all_stars else [])
        out.append({"stagione": i + 1, "nome": name, "squadra": "X", "gp": 70, "is_champion": i < titles,
                    "premi": premi, "stats_rs": {"ppg": ppg}})
    return out


ROSTER = [{"name": "Alaric Benthall", "age": 21, "position": "C", "ovr": 93},
          {"name": "Zane Castellane", "age": 25, "position": "SG", "ovr": 89},
          {"name": "Mekhi Northcott", "age": 29, "position": "PG", "ovr": 86}]
DEV = [dev("Alaric Benthall", TOR, 90, 93, 21, "C"), dev("Mekhi Northcott", TOR, 88, 86, 29, "PG"),
       dev("Thaddeus Okafor-Lyle", "Dallas Wranglers", 82, 88, 20), dev("Anselm Brightwater", "Boston Minutemen", 81, 75, 37),
       dev("Lucan Stroud", "San Antonio Vaqueros", 80, 85, 21)]


class DevelopmentViewTest(unittest.TestCase):
    def test_dev_yours_includes_unchanged(self):
        yours = development_view(DEV, [], {}, TOR, ROSTER)["yours"]
        self.assertEqual([(y["name"], y["before"], y["after"], y["delta"]) for y in yours],
                         [("Alaric Benthall", 90, 93, 3), ("Zane Castellane", 89, 89, 0), ("Mekhi Northcott", 88, 86, -2)])
        self.assertEqual(yours[0]["position"], "C")

    def test_dev_net_counts(self):
        self.assertEqual(development_view(DEV, [], {}, TOR, ROSTER)["net"], {"total": 1, "up": 1, "down": 1, "same": 1})

    def test_dev_league_top_n(self):
        view = development_view(DEV, [], {}, TOR, ROSTER)
        self.assertEqual([r["name"] for r in view["risers"]], ["Thaddeus Okafor-Lyle", "Lucan Stroud"])
        self.assertEqual(view["risers"][0], {"name": "Thaddeus Okafor-Lyle", "team": "Dallas Wranglers", "age": 20, "delta": 6})
        self.assertEqual([r["name"] for r in view["drops"]], ["Anselm Brightwater"])

    def test_retiree_honour_lines(self):
        careers = {"russ": career("Wendell Ravenhill", mvps=3, all_stars=14, titles=1),
                   "kd": career("Anselm Brightwater", all_stars=11), "ring": career("Role Guy", titles=1, ppg=6.0),
                   "rings": career("Two Rings", titles=2, ppg=6.0), "plain": career("Plain Guy", ppg=9.4)}
        retired = [{"name": n, "team": "X", "age": 37, "ovr": 70} for n in
                   ("Plain Guy", "Role Guy", "Two Rings", "Anselm Brightwater", "Wendell Ravenhill", "Nobody")]
        honours = {r["name"]: r["honour"] for r in development_view([], retired, careers, TOR, [])["retired"]}
        self.assertEqual(honours, {"Wendell Ravenhill": "3× MVP", "Anselm Brightwater": "11× All-Star", "Role Guy": "Ring",
                                   "Two Rings": "2 rings", "Plain Guy": "9.4 ppg", "Nobody": None})

    def test_retired_sort_yours_first(self):
        careers = {"russ": career("Wendell Ravenhill", mvps=3)}
        retired = [{"name": "Wendell Ravenhill", "team": "Milwaukee Hounds", "age": 37, "ovr": 77},
                   {"name": "Bench Guy", "team": TOR, "age": 36, "ovr": 60}]
        rows = development_view([], retired, careers, TOR, [])["retired"]
        self.assertEqual([(r["name"], r["yours"]) for r in rows], [("Bench Guy", True), ("Wendell Ravenhill", False)])


ORDER = [f"Team {i}" for i in range(1, 30)] + [TOR]


def offer(give_players=(), give_picks=(), get_players=(), get_picks=(), value=None, given=None):
    o = {"id": "o1", "offering_team": "Dallas Wranglers", "reason": "Dallas Wranglers strategy is WIN_NOW.",
         "receiving_players": list(give_players), "receiving_picks": list(give_picks),
         "giving_players": list(get_players), "giving_picks": list(get_picks)}
    if value is not None:
        o["value_for_user"], o["value_given"] = value, given
    return o


def pl(name, ovr, salary, age=27, pos="C"):
    return {"name": name, "ovr": ovr, "salary": salary, "age": age, "position": pos}


def desk(offers, block=()):
    return trade_desk_view(offers, TOR, 2026, ORDER, 188.8, ["1:R1-Toronto Northmen", "3:R1-Toronto Northmen"],
                           list(block), ["Chicago trade #12 to Utah"])


class TradeDeskViewTest(unittest.TestCase):
    def test_pick_label_this_draft(self):
        self.assertEqual(pick_label("1:R1-Toronto Northmen", 2026, ORDER),
                         {"year": 2026, "round": 1, "original": TOR, "slot": 30})
        self.assertEqual(pick_label("1:R2-Toronto Northmen", 2026, ORDER)["slot"], 60)

    def test_pick_label_future_year(self):
        self.assertEqual(pick_label("3:R1-Team 4", 2026, ORDER), {"year": 2028, "round": 1, "original": "Team 4", "slot": None})

    def test_pick_label_unparseable(self):
        self.assertEqual(pick_label("junk", 2026, ORDER), {"label": "junk"})

    def test_offer_verdict_good_bad(self):
        good = desk([offer(value=30.0, given=100.0)])["offers"][0]
        bad = desk([offer(value=-20.0, given=100.0)])["offers"][0]
        fair = desk([offer(value=5.0, given=100.0)])["offers"][0]
        self.assertEqual((good["verdict"], bad["verdict"], fair["verdict"]), ("good", "bad", "fair"))
        self.assertEqual(good["value"], 0.3)

    def test_offer_without_value(self):
        o = desk([offer()])["offers"][0]
        self.assertEqual((o["value"], o["verdict"]), (None, None))

    def test_cap_and_slot_change(self):
        o = desk([offer(give_players=[pl("Vaughn Kettering", 77, 12.4)], give_picks=["1:R1-Toronto Northmen"],
                        get_players=[pl("Marek Oyelaran", 74, 8.0, 36, "SG")], get_picks=["1:R1-Team 18"],
                        value=30.0, given=100.0)])["offers"][0]
        self.assertEqual((o["cap_change"], o["slot_change"]), (4.4, 12))
        self.assertEqual(o["summary"], "+$4.4M space · move up 12 spots")
        self.assertEqual(o["give"]["picks"][0]["slot"], 30)
        self.assertEqual(o["team"], "Dallas Wranglers")

    def test_bad_summary_names_best_given(self):
        o = desk([offer(give_players=[pl("Nico Fairbanks", 82, 3.6, 20, "SF")], get_picks=["1:R1-Team 22"],
                        value=-30.0, given=100.0)])["offers"][0]
        self.assertEqual(o["summary"], "gives up Nico Fairbanks (82)")

    def test_desk_side_lists(self):
        view = desk([offer(give_players=[pl("Vaughn Kettering", 77, 12.4)])],
                    block=[{"name": "Vaughn Kettering", "position": "C", "ovr": 77}])
        self.assertEqual([p.get("slot") for p in view["picks"]], [30, None])
        self.assertEqual(view["block"], [{"name": "Vaughn Kettering", "position": "C", "ovr": 77, "offers": 1}])
        self.assertEqual(view["wire"], [])  # no known team names in the line: dropped


def row(name, ovr, salary=2.0, position="SF", protected=False, new=False):
    return {"name": name, "position": position, "age": 22, "ovr": ovr, "potential": ovr + 5, "salary": salary,
            "protected": protected, "new": new}


class CutSheetViewTest(unittest.TestCase):
    def test_cut_sheet_marks(self):
        rows = [row("Janko Nielsen", 59, 1.9), row("Silas Dalton", 63, 1.2, "C"), row("Ansel Vossberg", 68, 2.9, "PF", True, True)]
        view = cut_sheet_view(rows, ["Janko Nielsen", "Silas Dalton"], 1,
                              [{"team": "Lakers", "name": "Bojan", "ovr": 74, "age": 36},
                               {"team": "Nuggets", "name": "Idris Kinsella", "ovr": 76, "age": 32}])
        self.assertEqual((view["target"], view["size"], view["to_release"]), (1, 3, 2))
        self.assertEqual([r["engine_pick"] for r in view["rows"]], [True, True, False])
        self.assertTrue(view["rows"][2]["protected"] and view["rows"][2]["new"])
        self.assertEqual([p["name"] for p in view["league"]], ["Idris Kinsella", "Bojan"])
        self.assertEqual(view["payroll"], 6.0)

    def test_cut_sheet_within_limit(self):
        view = cut_sheet_view([row("A", 70)], [], 17, [])
        self.assertEqual(view["to_release"], 0)


def snap_player(name, ovr, salary=5.0, age=25, role="SF"):
    return {"name": name, "role": role, "ovr": ovr, "salary": salary, "age": age}


def now_player(name, ovr, salary=5.0, age=25, position="SF"):
    return {"name": name, "position": position, "ovr": ovr, "salary": salary, "age": age}


BEFORE = {"payroll": 20.0, "players": [snap_player("Keeper", 90), snap_player("Cyrus Farrow", 81, 18.0, 26),
                                       snap_player("Vaughn Kettering", 77, 12.4, 28, "C"), snap_player("Janko Nielsen", 59),
                                       snap_player("Old Guy", 60, 1.0, 37)]}
NOW = [now_player("Keeper", 91), now_player("Ansel Vossberg", 68, 2.9, 19, "PF"), now_player("Marek Oyelaran", 74, 8.0, 36, "SG"),
       now_player("Dashiell Marrow", 71, 9.0, 26, "C")]
LOGS = {"draft": [{"scelta": "R1 P30", "squadra": TOR, "nome": "Ansel Vossberg"}], "draft_size": 30,
        "fa_signings": [{"player": "Dashiell Marrow", "team": TOR, "salary": 9.0, "years": 2},
                        {"player": "Cyrus Farrow", "team": "Memphis Blues", "salary": 24.0, "years": 4}],
        "retirements": [{"name": "Old Guy", "team": TOR, "age": 37, "ovr": 60}],
        "user_releases": ["Janko Nielsen"], "options": [{"name": "Cyrus Farrow", "team": TOR, "kind": "player", "decision": "out"}],
        "scambi": ["Dallas Wranglers invia [X] a Memphis Blues"]}
TEAMS_NOW = {TOR: [91, 74, 71, 68], "Dallas Wranglers": [80, 79, 77], "Memphis Blues": [85, 81]}
ROSTERS_NOW = {"Dallas Wranglers": ["Vaughn Kettering"], "Memphis Blues": ["Cyrus Farrow"]}
LEAGUE_BEFORE = {TOR: {"strength": 76.0, "rank": 2}, "Dallas Wranglers": {"strength": 80.0, "rank": 1},
                 "Memphis Blues": {"strength": 70.0, "rank": 3}}


def season_view(before=BEFORE, league_before=LEAGUE_BEFORE, user=TOR):
    return new_season_view(before, league_before, NOW, TEAMS_NOW, ROSTERS_NOW, LOGS, user, 18)


class NewSeasonViewTest(unittest.TestCase):
    def test_team_strength_top_n(self):
        self.assertEqual(team_strength([90, 80, 70, 60], 3), 80.0)
        self.assertEqual(team_strength([], 8), 0.0)

    def test_grade_steps(self):
        self.assertEqual([grade(d) for d in (2.1, 0.6, 0.0, -0.7, -2.0)], ["A", "B+", "B", "C", "D"])

    def test_how_tags_arrivals(self):
        arrivals = {a["name"]: a["how"] for a in season_view()["report"]["arrivals"]}
        self.assertEqual(arrivals, {"Ansel Vossberg": "Draft #30", "Dashiell Marrow": "FA · 2 yr", "Marek Oyelaran": "Trade"})

    def test_how_tags_departures(self):
        departures = {d["name"]: d["how"] for d in season_view()["report"]["departures"]}
        dal = get_team_branding("Dallas Wranglers")["abbreviation"]  # depends on the league installed
        self.assertEqual(departures, {"Cyrus Farrow": "Opted out", "Vaughn Kettering": f"Trade {dal}",
                                      "Janko Nielsen": "Cut", "Old Guy": "Retired"})

    def test_tiles(self):
        tiles = season_view()["report"]["tiles"]
        self.assertEqual(tiles["payroll"], {"before": 20.0, "after": 24.9})
        self.assertEqual(tiles["roster"], {"size": 4, "limit": 18})
        self.assertEqual(tiles["strength"]["after"], 76.0)  # (91+74+71+68)/4

    def test_grade_note_keeps_names(self):
        self.assertEqual(season_view()["report"]["grade_note"],
                         "Marek Oyelaran is the biggest addition; losing Cyrus Farrow hurts most.")

    def test_rankings_moved(self):
        rankings = season_view()["rankings"]
        self.assertEqual([(r["team"], r["rank"], r["moved"], r["yours"]) for r in rankings],
                         [("Memphis Blues", 1, 2, False), ("Dallas Wranglers", 2, -1, False), (TOR, 3, -1, True)])

    def test_moves_order(self):
        moves = season_view()["moves"]
        self.assertEqual(moves[0], "Cyrus Farrow signs with Memphis Blues · 4 yr $96M")
        self.assertIn("Trade: Dallas Wranglers, Memphis Blues", moves)

    def test_new_season_old_save(self):
        view = season_view(before=None, league_before=None)
        self.assertIsNone(view["report"])
        self.assertTrue(all(r["moved"] is None for r in view["rankings"]))

    def test_text_logs_do_not_break(self):
        logs = {"draft": ["Pick 1: someone"], "retirements": ["RETIREMENT: x"], "options": ["text"], "fa_signings": ["text"]}
        view = new_season_view(BEFORE, LEAGUE_BEFORE, NOW, TEAMS_NOW, ROSTERS_NOW, logs, TOR, 18)
        self.assertEqual({a["name"]: a["how"] for a in view["report"]["arrivals"]}["Ansel Vossberg"], "Trade")

    def test_spectator(self):
        view = season_view(user=None)
        self.assertIsNone(view["report"])
        self.assertFalse(any(r["yours"] for r in view["rankings"]))


class TradeSummaryTest(unittest.TestCase):
    TEAMS = ["New York Skyliners", "New Jersey Sentinels", "Sacramento Prospectors", "Utah Summit"]

    def test_teams_in_order_of_appearance(self):
        text = ("[BLOCKBUSTER 3-SQUADRE] New York Skyliners invia [Silas Ingram-Vale] a New Jersey Sentinels; "
                "New Jersey Sentinels invia [Bram Quarles] a Sacramento Prospectors")
        self.assertEqual(trade_summary(text, self.TEAMS), "Trade: New York Skyliners, New Jersey Sentinels, Sacramento Prospectors")

    def test_unreadable_line_is_dropped(self):
        self.assertIsNone(trade_summary("something happened", self.TEAMS))
        self.assertIsNone(trade_summary({"x": 1}, self.TEAMS))


if __name__ == "__main__":
    unittest.main()
