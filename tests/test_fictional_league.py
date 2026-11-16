"""The built-in fictional 2002 league (data/leagues/fictional_2002/league.json), invented staff names and the
rookie name uniqueness check. The fictional league is the real one with display data renamed."""
import glob
import json
import os
import random
import unittest
from types import SimpleNamespace

from core.config import CONFIG
from core.league.registry import FranchiseRegistry, get_active_registry, set_active_registry
from core.league.schema import league_from_dict, load_league, validate_league

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICTIONAL = os.path.join(ROOT, "data", "leagues", "fictional_2002", "league.json")
REAL = os.path.join(ROOT, "mods", "Real Names 2002", "league.json")

# Binding table of the spec (section "Team nicknames (style A)").
SPEC_NAMES = {
    "ATL": "Atlanta Firebirds", "BOS": "Boston Minutemen", "CHA": "Charlotte Monarchs",
    "CHI": "Chicago Gales", "CLE": "Cleveland Riveters", "DAL": "Dallas Wranglers",
    "DEN": "Denver Peaks", "DET": "Detroit Dynamos", "GSW": "Golden State Surge",
    "HOU": "Houston Launch", "IND": "Indiana Lightning", "LAC": "LA Breakers",
    "LAL": "Los Angeles Legends", "MEM": "Memphis Blues", "MIA": "Miami Tide",
    "MIL": "Milwaukee Hounds", "MIN": "Minnesota Blizzard", "NJN": "New Jersey Sentinels",
    "NOH": "New Orleans Krewe", "NYK": "New York Skyliners", "ORL": "Orlando Citrus",
    "PHI": "Philadelphia Liberty", "PHO": "Phoenix Scorpions", "POR": "Portland Lumberjacks",
    "SAC": "Sacramento Prospectors", "SAS": "San Antonio Vaqueros", "SEA": "Seattle Evergreens",
    "TOR": "Toronto Northmen", "UTA": "Utah Summit", "WAS": "Washington Admirals",
}

# Arenas the real 2002 teams played in (the real league file holds today's names): a local file next to the
# Real Names mod, never in the public repo.
DENYLIST = os.path.join(ROOT, "mods", "Real Names 2002", "denylist.json")


def real_arenas_2002():
    return set(_read(DENYLIST)["arenas_2002"]) if os.path.isfile(DENYLIST) else set()


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _all_players(raw):
    out = [p for plist in raw["players"].values() for p in plist]
    return out + list(raw.get("free_agents", []))


def real_player_names():
    """Every real full name the fictional file must avoid: the real league, its draft classes and the
    career-stats reference file."""
    real = _read(REAL)
    names = {p["name"] for p in _all_players(real)}
    for path in glob.glob(os.path.join(os.path.dirname(REAL), "draft_classes", "*.json")):
        names |= {p.get("name") or p.get("nome") for p in _read(path)}
    stats = os.path.join(ROOT, "data", "nba_real_career_stats.json")
    if os.path.isfile(stats):
        names |= {v.get("name") for v in _read(stats).values()}
    names.discard(None)
    return names


def filler_names():
    return {p["nome"] for p in _read(os.path.join(ROOT, "data", "filler_players.json"))}


@unittest.skipUnless(os.path.isfile(REAL), "Real Names 2002 mod not installed")
class FictionalLeagueFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fic = _read(FICTIONAL)
        cls.real = _read(REAL)

    def test_fictional_league_validates(self):
        self.assertEqual(validate_league(self.fic), [])
        data = load_league(FICTIONAL)
        self.assertEqual(data.meta, {"name": "Fictional League 2002", "era": "2002", "start_year": 2002})

    def test_same_players_by_id(self):
        real = {p["id"]: p for p in _all_players(self.real)}
        fic = {p["id"]: p for p in _all_players(self.fic)}
        self.assertEqual(set(real), set(fic))
        for pid, rp in real.items():
            fp = fic[pid]
            for key in ("role", "age", "overall", "potential", "abilities", "tendencies", "provenance",
                        "pedigree", "morale", "fvs", "is_untouchable", "years_on_team", "teams_drafted"):
                self.assertEqual(fp[key], rp[key], f"{pid} {key}")
        # Same team for every player, same order.
        self.assertEqual({t: [p["id"] for p in pl] for t, pl in self.fic["players"].items()},
                         {t: [p["id"] for p in pl] for t, pl in self.real["players"].items()})

    def test_same_franchise_facts_by_id(self):
        real = {f["id"]: f for f in self.real["franchises"]}
        for f in self.fic["franchises"]:
            r = real[f["id"]]
            for key in ("abbreviation", "conference", "division", "geo_city", "established", "market_weight",
                        "owner_personality", "display_city"):
                self.assertEqual(f.get(key), r.get(key), f"{f['id']} {key}")
            self.assertNotEqual((f["primary"], f["secondary"]), (r["primary"], r["secondary"]), f["id"])
        self.assertEqual(self.fic["rivalries"], self.real["rivalries"])
        self.assertEqual(self.fic["marquee_hosts"], self.real["marquee_hosts"])

    def test_gms_are_the_real_leagues_parody_gms(self):
        self.assertEqual(self.fic["staff"]["gms"]["starting"], self.real["staff"]["gms"]["starting"])
        self.assertEqual(self.fic["staff"]["gms"]["arrivals"], self.real["staff"]["gms"]["arrivals"])

    def test_nicknames_match_spec_table(self):
        names = {f["id"]: f["name"] for f in self.fic["franchises"]}
        self.assertEqual(names, SPEC_NAMES)
        for f in self.fic["franchises"]:
            self.assertEqual(f"{f['city']} {f['nickname']}", f["name"])

    def test_no_real_names(self):
        real_players = real_player_names()
        found = [p["name"] for p in _all_players(self.fic) if p["name"] in real_players]
        self.assertEqual(found, [])
        real_teams = {f["name"] for f in self.real["franchises"]} | set(CONFIG.LEAGUE.LEGACY_TEAM_IDS)
        real_nicks = {f["nickname"] for f in self.real["franchises"]}
        real_arenas = {f["arena"] for f in self.real["franchises"]} | real_arenas_2002()
        for f in self.fic["franchises"]:
            self.assertNotIn(f["name"], real_teams)
            self.assertNotIn(f["nickname"], real_nicks)
            self.assertNotIn(f["arena"], real_arenas)
            for nick in real_nicks:
                self.assertNotIn(nick, f["name"].split(), f["id"])
        real_staff = set(self.real["staff"]["coach_names"]) | set(self.real["staff"]["owner_names"])
        staff = self.fic["staff"]
        self.assertEqual(set(staff["coach_names"]) & real_staff, set())
        self.assertEqual(set(staff["owner_names"]) & real_staff, set())
        self.assertEqual(set(staff["coach_names"]) & real_players, set())
        # Player ids never carry a name.
        for p in _all_players(self.fic):
            self.assertRegex(p["id"], r"^p\d{4}$")

    def test_unique_player_names_and_no_filler_clash(self):
        names = [p["name"] for p in _all_players(self.fic)]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names) & filler_names(), set())
        for n in names:
            self.assertEqual(len(n.split()), 2, n)
        self.assertEqual(len({f["arena"] for f in self.fic["franchises"]}), 30)

    @unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "scripts", "make_fictional_league.py")),
                         "the generator script is local only (it reads the real league)")
    def test_script_output_matches_committed_file(self):
        from scripts import make_fictional_league as mk
        self.assertEqual(mk.build_fictional(self.real, mk.forbidden_names()), self.fic)


class StaffNamesTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(set_active_registry, get_active_registry())

    @unittest.skipUnless(os.path.isfile(REAL), "Real Names 2002 mod not installed")
    def test_config_staff_lists_are_invented(self):
        real = _read(REAL)["staff"]
        real_staff = set(real["coach_names"]) | set(real["owner_names"])
        self.assertEqual(set(CONFIG.COACHINGSTYLES.COACH_NAMES) & real_staff, set())
        self.assertEqual(set(CONFIG.ECONOMY.OWNER_NAMES) & real_staff, set())
        self.assertGreaterEqual(len(CONFIG.COACHINGSTYLES.COACH_NAMES), 40)
        self.assertGreaterEqual(len(CONFIG.ECONOMY.OWNER_NAMES), 30)

    def _registry_with_staff(self, coaches, owners):
        from tests.test_league_schema import make_league_dict
        raw = make_league_dict()
        raw["staff"]["coach_names"] = coaches
        raw["staff"]["owner_names"] = owners
        reg = FranchiseRegistry.from_league(league_from_dict(raw))
        set_active_registry(reg)
        return reg

    def test_registry_keeps_staff_through_save_round_trip(self):
        reg = self._registry_with_staff(["Coach One"], ["Owner One"])
        back = FranchiseRegistry.from_dict(reg.to_dict())
        self.assertEqual(back.staff["coach_names"], ["Coach One"])
        self.assertEqual(back.staff["owner_names"], ["Owner One"])
        # A registry saved without staff (older Phase 3 saves) loads with none.
        d = reg.to_dict()
        del d["staff"]
        self.assertEqual(FranchiseRegistry.from_dict(d).staff, {})

    def test_owner_names_come_from_the_active_league(self):
        from core import board_engine
        from core.models import Squadra
        self._registry_with_staff(["Coach One"], ["Owner Only"])
        team = Squadra(nome="City0 Nick0", roster=[])
        self.assertEqual(board_engine.init_board_profile_for_team(team, force_reset=True).owner_name, "Owner Only")
        set_active_registry(FranchiseRegistry([], [], {}))
        name = board_engine.init_board_profile_for_team(team, force_reset=True).owner_name
        self.assertIn(name, CONFIG.ECONOMY.OWNER_NAMES)
        self.assertFalse(hasattr(board_engine, "OWNER_NAMES_POOL"))

    def test_coach_names_come_from_the_active_league(self):
        import main
        from core.models import Squadra
        pool = [f"Coach{i} Surname{i}" for i in range(40)]
        self._registry_with_staff(pool, ["Owner One"])
        teams = [Squadra(nome=f"Team {i}", roster=[]) for i in range(30)]
        main.genera_e_assegna_coach_iniziali(teams)
        names = [t.coach.nome for t in teams]
        self.assertTrue(set(names) <= set(pool), names)
        self.assertEqual(len(names), len(set(names)))

        t = main.Tournament.__new__(main.Tournament)
        t.squadre = teams
        t.unemployed_coaches = []
        cand = t._generate_coach_candidate()
        parts = {w for n in pool for w in n.split()}
        self.assertTrue(set(cand.nome.split()) <= parts, cand.nome)
        self.assertNotIn(cand.nome, names)  # a free name of the pool before any mix

    def test_coach_candidate_falls_back_to_config(self):
        import main
        set_active_registry(FranchiseRegistry([], [], {}))
        t = main.Tournament.__new__(main.Tournament)
        t.squadre = []
        t.unemployed_coaches = []
        cand = t._generate_coach_candidate()
        parts = {w for n in CONFIG.COACHINGSTYLES.COACH_NAMES for w in n.split()}
        self.assertTrue(set(cand.nome.split()) <= parts, cand.nome)


class FrontOfficeFromLeagueTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(set_active_registry, get_active_registry())

    def _torneo(self, registry, starting_year=2002):
        teams = [SimpleNamespace(nome=f.name, team_id=f.id, roster=[]) for f in registry.franchises]
        t = SimpleNamespace(squadre=teams, squadra_giocatore=None, user_role="spectator", is_spectator=True,
                            season_number=1, starting_year=starting_year, anno_corrente=starting_year,
                            league_settings={}, franchise_registry=registry)
        t._determina_stato_squadra = lambda s: "Rebuilding"
        return t

    def test_fictional_league_seats_its_staff_gms_by_team_id(self):
        from core.front_office.state import build_front_office
        data = load_league(FICTIONAL)
        reg = FranchiseRegistry.from_league(data)
        set_active_registry(FranchiseRegistry([], [], {}))  # the torneo's own registry is the one read
        fo = build_front_office(self._torneo(reg))
        by_team = {g["team"]: g["gm_id"] for g in data.staff["gms"]["starting"]}
        self.assertEqual(len(fo.seats), 30)
        for f in reg.franchises:
            self.assertEqual(fo.seats[f.name], by_team[f.id], f.name)

    def test_other_era_gets_generated_gms(self):
        from core.front_office.state import build_front_office
        reg = FranchiseRegistry.from_league(load_league(FICTIONAL))
        fo = build_front_office(self._torneo(reg, starting_year=2025))
        self.assertTrue(all(fo.gms[g].gm_id.startswith("gen_") for g in fo.seats.values()))


class RookieNameTests(unittest.TestCase):
    def _draft(self, league_names):
        from offseason.draft import Draft
        d = Draft.__new__(Draft)
        players = [SimpleNamespace(nome=n) for n in league_names]
        d.torneo = SimpleNamespace(squadre=[SimpleNamespace(roster=players)], free_agents_pool=[], draft_class=[])
        return d

    def test_generated_rookies_never_reuse_a_league_name(self):
        random.seed(77)
        first_50 = [g.nome for g in self._draft([])._genera_giocatori_mancanti(50, [])]
        league_names = set(first_50)
        random.seed(77)
        rookies = [g.nome for g in self._draft(sorted(league_names))._genera_giocatori_mancanti(200, [])]
        self.assertEqual(len(rookies), len(set(rookies)))
        self.assertEqual(set(rookies) & league_names, set())
        self.assertEqual(set(rookies) & filler_names(), set())

    def test_generated_rookies_avoid_filler_names(self):
        fillers = sorted(filler_names())
        from offseason import draft as draft_module
        self.assertTrue(set(fillers) <= draft_module.filler_player_names())


if __name__ == "__main__":
    unittest.main()
