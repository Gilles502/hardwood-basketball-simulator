"""Team facts (divisions, cities, market weights, rivalries, branding, conferences, era) come from the active
franchise registry: no runtime table names a real team."""
import contextlib
import io
import json
import os
import random
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from core.config import CONFIG
from core.league.registry import FranchiseRegistry, current_league_era, get_active_registry, set_active_registry
from core.league.schema import LeagueData, load_league

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICTIONAL_LEAGUE = os.path.join(ROOT, "data", "leagues", "fictional_2002", "league.json")

RUNTIME_FILES = ("main.py", "core/calendar_generator.py", "core/config.py", "core/franchise_legacy.py",
                 "server.py", "core/news_generator.py")


def _base_league() -> LeagueData:
    return load_league(FICTIONAL_LEAGUE)


def _renamed_league() -> LeagueData:
    """The built-in league with every team renamed (BOS -> "Boston Minutemen", others "<city> Test<id>")."""
    data = _base_league()
    renamed = []
    for f in data.franchises:
        name = "Boston Minutemen" if f.id == "BOS" else f"{f.city} Test{f.id}"
        renamed.append(replace(f, name=name, nickname=name.split()[-1]))
    data.franchises = renamed
    return data


def _teams(registry):
    return [SimpleNamespace(nome=n, roster=[], conference=registry.conference_of(n)) for n in registry.names()]


class _ActiveRegistryCase(unittest.TestCase):
    league_factory = staticmethod(_base_league)

    def setUp(self):
        self._previous = get_active_registry()
        self.registry = FranchiseRegistry.from_league(self.league_factory())
        set_active_registry(self.registry)

    def tearDown(self):
        set_active_registry(self._previous)


class RenamedLeagueTests(_ActiveRegistryCase):
    league_factory = staticmethod(_renamed_league)

    def test_schedule_runs_with_renamed_teams(self):
        from core.calendar_generator import NBACalendarGenerator
        random.seed(3)
        gen = NBACalendarGenerator(_teams(self.registry), starting_year=2002, seed=3)
        self.assertEqual(gen.team_division["Boston Minutemen"], "Atlantic")
        self.assertEqual(gen.team_division["Utah TestUTA"], "Northwest")
        self.assertEqual(gen.team_division["Memphis TestMEM"], "Southwest")
        days = gen.generate_calendar()
        counts = {n: 0 for n in self.registry.names()}
        for d in days:
            for g in d.games:
                counts[g.home_team] += 1
                counts[g.away_team] += 1
        self.assertEqual(len(counts), 30)
        self.assertTrue(all(c == 82 for c in counts.values()), counts)

    def test_rivalries_follow_the_ids(self):
        self.assertIn(("Boston Minutemen", "Los Angeles TestLAL", 50.0), self.registry.rivalries())

    def test_division_rivalries_in_tournament(self):
        import main
        t = SimpleNamespace(squadre=[SimpleNamespace(nome=n) for n in self.registry.names()],
                            rivalry_tracker=mock.Mock(rivalries={}))
        t.rivalry_tracker.get_or_create_rivalry.side_effect = lambda *a, **k: SimpleNamespace(intensity=0.0)
        main.Tournament._initialize_division_rivalries(t)
        divisions = t.rivalry_tracker.initialize_division_rivalries.call_args[0][0]
        self.assertIn("Boston Minutemen", divisions["Atlantic"])
        self.assertEqual(sum(len(v) for v in divisions.values()), 30)
        pairs = {(c.args[0], c.args[1]) for c in t.rivalry_tracker.get_or_create_rivalry.call_args_list}
        self.assertIn(("Boston Minutemen", "Los Angeles TestLAL"), pairs)

    def _build_db(self, drop_franchise_column=False):
        from core.league.builder import build_league_db
        tmp = tempfile.mkdtemp(prefix="hardwood_regusage_")
        path = os.path.join(tmp, "league.db")
        data = self.league_factory()
        data.players = {f.id: [] for f in data.franchises}
        data.free_agents = []
        build_league_db(data, path)
        if drop_franchise_column:
            conn = sqlite3.connect(path)
            conn.execute("ALTER TABLE teams DROP COLUMN franchise_id")
            conn.commit()
            conn.close()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        return path

    def test_db_load_sets_team_id_and_conference(self):
        import main
        from core import db_manager
        path = self._build_db()
        with mock.patch.object(db_manager, "DB_NAME", path), contextlib.redirect_stdout(io.StringIO()):
            squadre, _fa = main.caricamento_squadre()
        by_name = {s.nome: s for s in squadre}
        self.assertEqual(by_name["Boston Minutemen"].team_id, "BOS")
        self.assertEqual(by_name["Boston Minutemen"].conference, "East")
        self.assertEqual(by_name["Utah TestUTA"].conference, "West")

    def test_db_without_franchise_column_still_loads(self):
        import main
        from core import db_manager
        path = self._build_db(drop_franchise_column=True)
        with mock.patch.object(db_manager, "DB_NAME", path), contextlib.redirect_stdout(io.StringIO()):
            squadre, _fa = main.caricamento_squadre()
        by_name = {s.nome: s for s in squadre}
        self.assertEqual(len(squadre), 30)
        self.assertEqual(by_name["Boston Minutemen"].team_id, "")
        self.assertEqual(by_name["Boston Minutemen"].conference, "East")

    def test_era_teams_conference_from_db_column(self):
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        path = self._build_db()
        # The 2002 era reads the active league's DB (core/league/catalog.py): point it at the test DB.
        with mock.patch.object(server.league_catalog, "ensure_active_league_db", lambda: path), \
                mock.patch.object(server.league_catalog, "active_league", lambda: None):
            resp = server.app.test_client().get("/api/era_teams?era=2002")
        body = resp.get_json()
        payload = json.dumps(body)
        self.assertIn("Boston Minutemen", payload)
        east = [t["name"] for t in body.get("east", [])]
        west = [t["name"] for t in body.get("west", [])]
        self.assertIn("Boston Minutemen", east)
        self.assertIn("Utah TestUTA", west)
        self.assertEqual(len(east), 15)


class UnknownTeamsTests(unittest.TestCase):
    def setUp(self):
        self._previous = get_active_registry()
        set_active_registry(FranchiseRegistry([], [], {}))

    def tearDown(self):
        set_active_registry(self._previous)

    def test_unknown_teams_do_not_crash_the_scheduler(self):
        from core.calendar_generator import NBACalendarGenerator
        teams = [SimpleNamespace(nome=f"Club {i}", roster=[], conference=None) for i in range(30)]
        gen = NBACalendarGenerator(teams, starting_year=2025, seed=2)
        self.assertEqual(sum(len(v) for v in gen.divisions.values()), 30)
        self.assertEqual(gen.get_team_city("Club 1"), "New York")


class SaveRestoreTeamIdTests(unittest.TestCase):
    def test_empty_saved_team_id_keeps_existing_id(self):
        from core import save_manager
        # The helper the restore loop uses for Squadra.team_id.
        self.assertEqual(save_manager._restored_team_id("", "BOS"), "BOS")
        self.assertEqual(save_manager._restored_team_id(None, "BOS"), "BOS")
        self.assertEqual(save_manager._restored_team_id("NYK", "BOS"), "NYK")
        self.assertEqual(save_manager._restored_team_id(None, ""), "")


class NoRealTeamNamesTests(unittest.TestCase):
    def test_no_real_team_name_in_runtime_tables(self):
        # The real team names old saves store: the keys of the one allowed table.
        names = sorted(CONFIG.LEAGUE.LEGACY_TEAM_IDS)
        found = []
        for rel in RUNTIME_FILES:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                text = fh.read()
            if rel == "core/config.py":
                # LEAGUE.LEGACY_TEAM_IDS maps the names stored in old saves to team ids (the one allowed table).
                start = text.find("LEGACY_TEAM_IDS: dict")
                end = text.find("})", start)
                if start != -1:
                    text = text[:start] + text[end:]
            for n in names:
                if n in text:
                    found.append(f"{rel}: {n}")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
