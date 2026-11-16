"""AI GM layer 1: what the Front Office page shows (core/front_office/view.py)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.board_engine import get_or_create_summit_data
from core.config import CONFIG
from core.front_office.models import CpuGM
from core.front_office.moves import record_move
from core.front_office.state import build_front_office
from core.front_office.view import gm_card, gm_market, league_table
from tests.test_front_office_state import fake_torneo


def league(user_team="Toronto Northmen", role="gm_coach", season=1):
    t = fake_torneo(user_team=user_team, role=role, season=season)
    for s in t.squadre:
        s.coach = SimpleNamespace(nome=f"Coach {s.nome}", stile_gioco="Grit & Grind")
        s.personalita_proprietario = "Spendaccione"
    t.user_gm_profile = SimpleNamespace(name="Alex Doe")
    t.front_office = build_front_office(t)
    return t


class TableTests(unittest.TestCase):
    def test_table_has_30_rows_and_user_row(self):
        table = league_table(league())
        self.assertEqual(len(table["rows"]), 30)
        self.assertEqual(table["year"], 2002)
        mine = [r for r in table["rows"] if r["is_user"]]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["team"], mine[0]["name"], mine[0]["skills"], mine[0]["gm_id"]),
                         ("Toronto Northmen", "Alex Doe", None, None))
        boston = next(r for r in table["rows"] if r["team"] == "Boston Minutemen")
        self.assertEqual(boston["name"], "Chris Wallach")
        self.assertEqual(set(boston["skills"]), set(CONFIG.FRONT_OFFICE.SKILLS))
        self.assertEqual(boston["plan"], "REBUILDER")
        self.assertEqual(boston["plan_label"], CONFIG.FRONT_OFFICE.PLAN_LABELS["REBUILDER"])
        self.assertEqual(boston["seasons_held"], 1)
        self.assertTrue(all(label in CONFIG.FRONT_OFFICE.TRAITS.values() for label in boston["traits"]))

    def test_spectator_has_no_user_row(self):
        table = league_table(league(role="spectator"))
        self.assertFalse(any(r["is_user"] for r in table["rows"]))


class CardTests(unittest.TestCase):
    def test_card_fields(self):
        t = league()
        t.fase_torneo = "SEASON"
        record_move(t, "Boston Minutemen", "trade", "first")
        t._deadline_window = True
        record_move(t, "Boston Minutemen", "trade", "second")
        card = gm_card(t, "Boston Minutemen")
        self.assertFalse(card["is_user"])
        self.assertEqual(card["gm"]["name"], "Chris Wallach")
        self.assertEqual(card["gm"]["traits"][0]["label"], CONFIG.FRONT_OFFICE.TRAITS[card["gm"]["traits"][0]["code"]])
        plan = card["plan"]
        self.assertEqual((plan["state"], plan["label"], plan["seasons_held"]), ("REBUILDER", "Rebuild", 1))
        self.assertEqual(plan["expected_seasons"], CONFIG.FRONT_OFFICE.PLAN_EXPECTED_SEASONS["REBUILDER"])
        self.assertTrue(plan["reason"])
        self.assertEqual(card["coach"], {"name": "Coach Boston Minutemen", "style": "Grit & Grind",
                                         "wants": CONFIG.FRONT_OFFICE.COACH_STYLE_TARGETS["Grit & Grind"]})
        self.assertEqual(card["owner"]["personality"], "Spendaccione")
        self.assertEqual(card["owner"]["patience"], CONFIG.ECONOMY.OWNER_BOARD_PATIENCE["Spendaccione"])
        self.assertEqual(card["owner"]["spending"], CONFIG.ECONOMY.OWNER_BOARD_SPENDING["Spendaccione"])
        self.assertEqual([m["text"] for m in card["moves"]], ["second", "first"])
        self.assertEqual(card["moves"][0]["when"], "Deadline 2003")
        self.assertEqual(card["moves"][1]["when"], "Season 2002")

    def test_user_card_and_unknown_team(self):
        t = league()
        mine = gm_card(t, "Toronto Northmen")
        self.assertTrue(mine["is_user"])
        self.assertIsNone(mine["gm"])
        self.assertEqual(mine["user_name"], "Alex Doe")
        self.assertIsNone(gm_card(t, "Nowhere Nomads"))

    def test_card_career_newest_first_with_labels(self):
        t = league()
        gm = t.front_office.seated_gm("Boston Minutemen")
        gm.career = [
            {"team": "Utah Summit", "from_year": 1999, "to_year": 2001, "end": "fired", "wins": 40, "losses": 60,
             "playoffs": 1, "titles": 0},
            {"team": "Miami Tide", "from_year": 2001, "to_year": 2001, "end": "interim_end", "wins": 5, "losses": 5,
             "playoffs": 0, "titles": 0},
            {"team": "Boston Minutemen", "from_year": 2002, "to_year": None, "end": None, "wins": 50, "losses": 32,
             "playoffs": 1, "titles": 1, "awards": ["GM of the Year 2002"]},
        ]
        gm.interim = True
        card = gm_card(t, "Boston Minutemen")
        career = card["gm"]["career"]
        self.assertEqual([c["team"] for c in career], ["Boston Minutemen", "Miami Tide", "Utah Summit"])
        self.assertEqual([c["end_label"] for c in career], ["Current", "Interim", "Fired"])
        self.assertEqual(career[0]["awards"], ["GM of the Year 2002"])
        self.assertEqual(career[2]["awards"], [])
        self.assertEqual((career[0]["wins"], career[0]["losses"], career[0]["titles"]), (50, 32, 1))
        self.assertTrue(card["gm"]["interim"])
        gm.career[0].update(end="retired")
        self.assertEqual(gm_card(t, "Boston Minutemen")["gm"]["career"][2]["end_label"], "Retired")
        gm.career[0].update(end="user_took_over")
        self.assertEqual(gm_card(t, "Boston Minutemen")["gm"]["career"][2]["end_label"], "Left: user took over")

    def test_card_hiring_notes_text(self):
        t = league()
        gm = t.front_office.seated_gm("Boston Minutemen")
        gm.hiring_notes = [
            {"year": 2008, "kind": "turned_down", "team": "Utah Summit", "names": []},
            {"year": 2009, "kind": "chased_by", "team": "Boston Minutemen", "names": ["Utah Summit", "Miami Tide"]},
            {"year": 2009, "kind": "chosen_over", "team": "Boston Minutemen", "names": ["Ann Lee", "Bo Ray"]},
        ]
        texts = [n["text"] for n in gm_card(t, "Boston Minutemen")["gm"]["hiring_notes"]]
        self.assertEqual(texts, ["Chosen over Ann Lee, Bo Ray (2009)", "Chased by Utah Summit, Miami Tide (2009)",
                                 "Turned down the Utah Summit (2008)"])

    def test_every_coach_style_has_a_target(self):
        targets = CONFIG.FRONT_OFFICE.COACH_STYLE_TARGETS
        for style in CONFIG.COACHINGSTYLES.STYLES:
            self.assertTrue(targets.get(style), style)


class MarketTests(unittest.TestCase):
    def test_market_hides_future_arrivals(self):
        t = league(season=2)  # 2003
        future = CpuGM(gm_id="future_gm", name="Future Guy", age=30, years_as_gm=0, traits=["PICK_HOARDER", "LOYALIST"],
                       skills={"trade": 60, "contracts": 60, "draft": 60}, team=None, historical=True,
                       available_from_year=2007)
        t.front_office.gms[future.gm_id] = future
        self.assertNotIn("future_gm", {r["gm_id"] for r in gm_market(t)["unemployed"]})
        t.anno_corrente = 2007
        self.assertIn("future_gm", {r["gm_id"] for r in gm_market(t)["unemployed"]})
        # The user's team's original GM waits on the market from day one.
        self.assertIn("glen_greenwood", {r["gm_id"] for r in gm_market(league())["unemployed"]})


    def test_market_excludes_retired(self):
        t = league()
        retired = CpuGM(gm_id="old_timer", name="Old Timer", age=70, years_as_gm=30, traits=["LOYALIST"],
                        skills={"trade": 90, "contracts": 90, "draft": 90}, team=None, retired_year=2001,
                        career=[{"team": "Utah Summit", "from_year": 1980, "to_year": 2001, "end": "retired",
                                 "wins": 900, "losses": 700, "playoffs": 15, "titles": 2}])
        t.front_office.gms[retired.gm_id] = retired
        rows = {r["gm_id"]: r for r in gm_market(t)["unemployed"]}
        self.assertNotIn("old_timer", rows)
        gm = next(g for g in t.front_office.gms.values() if g.team is None and g.gm_id in rows)
        gm.career = [{"team": "Utah Summit", "from_year": 1999, "to_year": 2001, "end": "fired", "wins": 1, "losses": 1,
                      "playoffs": 2, "titles": 1}]
        row = next(r for r in gm_market(t)["unemployed"] if r["gm_id"] == gm.gm_id)
        self.assertEqual((row["jobs"], row["titles"], row["playoffs"]), (1, 1, 2))


class TableFlagTests(unittest.TestCase):
    def test_table_flags_new_and_interim(self):
        t = league()
        boston = t.front_office.seated_gm("Boston Minutemen")
        boston.career = [{"team": "Boston Minutemen", "from_year": 2002, "to_year": None, "end": None, "wins": 0,
                          "losses": 0, "playoffs": 0, "titles": 0}]
        boston.interim = True
        miami = t.front_office.seated_gm("Miami Tide")
        miami.career = [{"team": "Miami Tide", "from_year": 1999, "to_year": None, "end": None, "wins": 0,
                         "losses": 0, "playoffs": 0, "titles": 0}]
        rows = {r["team"]: r for r in league_table(t)["rows"]}
        self.assertEqual((rows["Boston Minutemen"]["new_this_year"], rows["Boston Minutemen"]["interim"]), (True, True))
        self.assertEqual((rows["Miami Tide"]["new_this_year"], rows["Miami Tide"]["interim"]), (False, False))
        self.assertEqual((rows["Toronto Northmen"]["new_this_year"], rows["Toronto Northmen"]["interim"]), (False, False))

    def test_offseason_hire_is_new_in_his_first_season(self):
        t = league(season=2)  # 2003
        gm = t.front_office.seated_gm("Boston Minutemen")
        job = {"team": "Boston Minutemen", "from_year": 2002, "to_year": None, "end": None, "wins": 0, "losses": 0,
               "playoffs": 0, "titles": 0}
        flag = lambda: next(r for r in league_table(t)["rows"] if r["team"] == "Boston Minutemen")["new_this_year"]
        gm.career = [dict(job)]
        self.assertTrue(flag())
        gm.career = [dict(job, from_year=2001)]
        self.assertFalse(flag())
        gm.career = [dict(job, to_year=2002, end="fired")]
        self.assertFalse(flag())


class SummitTests(unittest.TestCase):
    def test_summit_uses_user_gm_name(self):
        players = [SimpleNamespace(nome=f"P{i}", ovr=80 - i, eta=26, potenziale=82) for i in range(10)]
        team = SimpleNamespace(nome="Toronto Northmen", roster=players, front_office_summit=None)
        torneo = SimpleNamespace(season_number=1, user_gm_profile=SimpleNamespace(name="Alex Doe"),
                                 enable_play_in=True, start_era="2002")
        data = get_or_create_summit_data(team, torneo)
        self.assertEqual(data["proposal"]["gm_name"], "Alex Doe")
        torneo.user_gm_profile = None
        self.assertEqual(get_or_create_summit_data(team, torneo)["proposal"]["gm_name"], "General Manager")

    def test_coach_only_summit_meets_the_cpu_gm(self):
        t = league(role="only_coach")
        t.squadra_giocatore = next(s for s in t.squadre if s.nome == "Toronto Northmen")
        t.front_office = build_front_office(t)
        t.season_number, t.enable_play_in = 1, True
        team = t.squadra_giocatore
        team.roster = [SimpleNamespace(nome=f"P{i}", ovr=80 - i, eta=26, potenziale=82) for i in range(10)]
        team.front_office_summit = None
        self.assertEqual(get_or_create_summit_data(team, t)["proposal"]["gm_name"], "Glen Greenwood")
        row = next(r for r in league_table(t)["rows"] if r["team"] == "Toronto Northmen")
        self.assertEqual((row["is_user"], row["name"]), (False, "Glen Greenwood"))


if __name__ == "__main__":
    unittest.main()
