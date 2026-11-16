"""League catalogue routes and the new-career wiring (Task 5). Flask test client, temp game root and cwd."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from core import save_manager
from core.league import catalog, draft_source, registry
from tests.test_league_schema import make_league_dict


def prospect_rows(names):
    """Draft-class JSON rows the draft loader accepts (every ability and tendency present)."""
    from dataclasses import fields
    from core.models import Abilita, Tendenze
    abilities = {f.name: 60 for f in fields(Abilita)}
    tendencies = {f.name: 50 for f in fields(Tendenze)}
    return [{"name": n, "role": "SF", "age": 19, "overall": 60, "potential": 90,
             "abilities": abilities, "tendencies": tendencies} for n in names]


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


class LeagueRoutesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        league = make_league_dict()
        league["meta"]["name"] = "Fiction 2002"
        write_json(os.path.join(self.root, "data", "leagues", "fictional_2002", "league.json"), league)
        patcher = mock.patch.object(catalog, "GAME_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        saved_registry = registry._active
        self.addCleanup(setattr, registry, "_active", saved_registry)
        self.client = server.app.test_client()

    def test_get_leagues_lists_builtin(self):
        res = self.client.get("/api/leagues")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["active"], catalog.BUILTIN_LEAGUE_ID)
        self.assertEqual([(e["id"], e["source"], e["name"]) for e in body["leagues"]],
                         [(catalog.BUILTIN_LEAGUE_ID, "builtin", "Fiction 2002")])

    def test_build_broken_mod_returns_400_with_errors(self):
        path = os.path.join(self.root, "mods", "Broken", "league.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        res = self.client.post("/api/leagues/build", json={"league_id": "Broken"})
        self.assertEqual(res.status_code, 400)
        body = res.get_json()
        self.assertFalse(body["ok"])
        self.assertTrue(body["errors"])
        self.assertEqual(self.client.get("/api/leagues").get_json()["active"], catalog.BUILTIN_LEAGUE_ID)
        self.assertEqual(self.client.post("/api/leagues/build", json={}).status_code, 400)

    def test_build_valid_mod_activates_it(self):
        other = make_league_dict()
        other["meta"]["name"] = "Other League"
        write_json(os.path.join(self.root, "mods", "Other", "league.json"), other)
        res = self.client.post("/api/leagues/build", json={"league_id": "Other"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {"ok": True, "errors": []})
        self.assertEqual(self.client.get("/api/leagues").get_json()["active"], "Other")

    def test_era_teams_2002_reads_active_league_db(self):
        body = self.client.get("/api/era_teams?era=2002").get_json()
        self.assertEqual(len(body["teams"]), 30)
        self.assertIn("City0 Nick0", {t["name"] for t in body["teams"]})
        self.assertEqual(body["league"], {"id": catalog.BUILTIN_LEAGUE_ID, "name": "Fiction 2002"})

    def test_era_teams_2002_build_failure_is_json(self):
        def boom():
            raise OSError("disk full")
        with mock.patch.object(catalog, "ensure_active_league_db", boom):
            res = self.client.get("/api/era_teams?era=2002")
        self.assertEqual(res.status_code, 500)
        self.assertIn("disk full", res.get_json()["error"])


class NewCareerFromActiveLeagueTests(unittest.TestCase):
    """init_simulation with start_era 2002: the active league's DB, registry, meta and draft classes."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.join(tmp.name, "game")
        self.cwd = os.path.join(tmp.name, "cwd")
        os.makedirs(os.path.join(self.cwd, "data"))
        league = make_league_dict()
        league["meta"]["name"] = "Draft Mod"
        mod = os.path.join(self.root, "mods", "Draft Mod")
        write_json(os.path.join(mod, "league.json"), league)
        write_json(os.path.join(mod, "draft_classes", "DRAFT_2003.json"), prospect_rows(["Rookie One"]))

        saved = {k: getattr(server, k) for k in ("SIMULATION_TOURNAMENT", "ACTIVE_SAVE_NAME", "LEAGUE_STATE")}
        self.addCleanup(lambda: [setattr(server, k, v) for k, v in saved.items()])
        saved_active_save = save_manager.get_active_save_name()
        self.addCleanup(save_manager.set_active_save_name, saved_active_save)
        saved_registry = registry._active
        self.addCleanup(setattr, registry, "_active", saved_registry)
        old_cwd = os.getcwd()
        os.chdir(self.cwd)  # the route writes data/nba_sim.db relative to the working directory
        self.addCleanup(os.chdir, old_cwd)

        self.seen_at_setup = {}

        def fake_setup(league_settings=None, league_meta=None, franchise_registry=None):
            reg = registry.get_active_registry()
            self.seen_at_setup["names"] = reg.names()
            torneo = SimpleNamespace(squadre=[], season_number=1, starting_year=2002, squadra_giocatore=None,
                                     resolve_play_in=lambda: None, league_meta=dict(league_meta or {}),
                                     franchise_registry=franchise_registry)
            # The real season-1 draft-class read, as setup_simulation does it (save copy / mod / generated).
            server.simulation_logic.inizializza_scouting_e_classe_draft(torneo)
            self.seen_at_setup["prospects"] = {p.nome for p in torneo.draft_class}
            return torneo

        self._patch(catalog, "GAME_ROOT", self.root)
        self._patch(draft_source, "GAME_ROOT", self.root)
        self._patch(server.simulation_logic, "setup_simulation", fake_setup)
        self._patch(server, "build_front_office", lambda t: None)
        self._patch(server, "ensure_season_marks", lambda t, fo: None)
        self._patch(server, "clear_records", lambda: None)
        self._patch(server, "save_current_game", lambda name: None)
        self._patch(server, "get_full_league_data_payload", lambda: {"ok": True})
        self.client = server.app.test_client()

    def _patch(self, target, name, value):
        p = mock.patch.object(target, name, value)
        p.start()
        self.addCleanup(p.stop)

    def test_new_2002_career_uses_active_league(self):
        save_name = "Test_League_Career_Task5"
        save_dir = save_manager.get_save_path(save_name)
        self.assertTrue(save_dir.startswith(save_manager.get_saves_dir()))
        os.makedirs(os.path.join(save_dir, "draft_classes"), exist_ok=True)
        write_json(os.path.join(save_dir, "draft_classes", "DRAFT_1999.json"), [])  # stale, from an older career

        res = self.client.post("/api/init_simulation", json={
            "start_era": "2002", "save_name": save_name, "user_role": "spectator"})
        self.assertEqual(res.status_code, 200, res.get_json())

        names = [f"City{i} Nick{i}" for i in range(30)]
        self.assertEqual(self.seen_at_setup["names"], names)  # registry installed before setup
        torneo = server.SIMULATION_TOURNAMENT
        self.assertEqual(torneo.league_meta, {"id": "Draft Mod", "name": "Draft Mod", "era": "2002"})
        self.assertEqual(torneo.franchise_registry.names(), names)
        self.assertIs(registry.get_active_registry(), torneo.franchise_registry)

        conn = sqlite3.connect(os.path.join(self.cwd, "data", "nba_sim.db"))
        try:
            got = sorted(r[0] for r in conn.execute("SELECT name FROM teams"))
        finally:
            conn.close()
        self.assertEqual(got, sorted(names))
        self.assertEqual(sorted(os.listdir(os.path.join(save_dir, "draft_classes"))), ["DRAFT_2003.json"])

    @unittest.skipUnless(os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                  "data", "nba_sim_modern.db")),
                         "the modern era database is not shipped (modern era hidden in v0.1)")
    def test_modern_career_after_2002_career_uses_default_registry(self):
        res = self.client.post("/api/init_simulation", json={
            "start_era": "2002", "save_name": "Era2002_Task5", "user_role": "spectator"})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(len(registry.get_active_registry().names()), 30)
        sqlite3.connect(os.path.join(self.cwd, "data", "nba_sim_modern.db")).close()  # modern template
        with mock.patch.object(registry, "_DEFAULT_LEAGUE_PATHS", ()):
            res = self.client.post("/api/init_simulation", json={
                "start_era": "modern", "save_name": "Modern_Task5", "user_role": "spectator"})
            self.assertEqual(res.status_code, 200, res.get_json())
            self.assertEqual(self.seen_at_setup["names"], [])  # the lazy default, not the 2002 league

    def test_invalid_active_league_returns_400_with_its_errors(self):
        path = os.path.join(self.root, "mods", "Draft Mod", "league.json")
        self.assertTrue(catalog.build_and_activate("Draft Mod")["ok"])
        bad = make_league_dict()
        bad["franchises"] = bad["franchises"][:29]
        write_json(path, bad)
        res = self.client.post("/api/init_simulation", json={"start_era": "2002", "save_name": "Bad_Task5"})
        self.assertEqual(res.status_code, 400)
        self.assertTrue(any("30 teams" in e for e in res.get_json()["errors"]))

    def test_no_playable_league_returns_400_before_any_change(self):
        os.remove(os.path.join(self.root, "mods", "Draft Mod", "league.json"))
        before = server.ACTIVE_SAVE_NAME
        res = self.client.post("/api/init_simulation", json={"start_era": "2002", "save_name": "X_Task5"})
        self.assertEqual(res.status_code, 400)
        self.assertTrue(res.get_json()["errors"])
        self.assertEqual(server.ACTIVE_SAVE_NAME, before)
        self.assertFalse(os.path.exists(os.path.join(self.cwd, "data", "nba_sim.db")))


    # --- Final review: the draft class a new career reads during setup ---

    def _install_real_names_mod(self, names):
        mod = os.path.join(self.root, "mods", "Real Names 2002")
        league = make_league_dict()
        league["meta"]["name"] = "Real Names 2002"
        write_json(os.path.join(mod, "league.json"), league)
        write_json(os.path.join(mod, "draft_classes", "DRAFT_2003.json"), prospect_rows(names))

    def test_fictional_career_never_drafts_the_mod_class(self):
        mod_names = [f"Real Prospect {i}" for i in range(10)]
        self._install_real_names_mod(mod_names)
        shutil.rmtree(os.path.join(self.root, "mods", "Draft Mod"))
        builtin = make_league_dict()
        builtin["meta"]["name"] = "Fiction 2002"
        write_json(os.path.join(self.root, catalog.BUILTIN_LEAGUE_FILE), builtin)  # no draft_classes/
        self.assertEqual(catalog.active_league()["id"], catalog.BUILTIN_LEAGUE_ID)

        res = self.client.post("/api/init_simulation", json={
            "start_era": "2002", "save_name": "Fiction_Draft_Final", "user_role": "spectator"})
        self.assertEqual(res.status_code, 200, res.get_json())
        prospects = self.seen_at_setup["prospects"]
        self.assertTrue(prospects)
        self.assertFalse(prospects & set(mod_names), "a fictional career read the Real Names 2002 class")
        self.assertEqual(server.SIMULATION_TOURNAMENT.league_meta["id"], catalog.BUILTIN_LEAGUE_ID)

    def test_real_names_career_drafts_the_mod_class(self):
        mod_names = [f"Real Prospect {i}" for i in range(10)]
        self._install_real_names_mod(mod_names)
        self.assertTrue(catalog.build_and_activate("Real Names 2002")["ok"])
        save_name = "Real_Draft_Final"
        res = self.client.post("/api/init_simulation", json={
            "start_era": "2002", "save_name": save_name, "user_role": "spectator"})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertTrue(set(mod_names) <= self.seen_at_setup["prospects"])
        own = os.path.join(save_manager.get_save_path(save_name), "draft_classes", "DRAFT_2003.json")
        self.assertTrue(os.path.isfile(own))

    def test_reused_save_folder_reads_the_new_league_class_not_the_stale_one(self):
        save_name = "Reused_Draft_Final"
        stale = [f"Stale Prospect {i}" for i in range(10)]
        write_json(os.path.join(save_manager.get_save_path(save_name), "draft_classes", "DRAFT_2003.json"),
                   prospect_rows(stale))
        # Draft Mod (active) brings its own 2003 class: the fresh copy replaces the stale one before setup.
        res = self.client.post("/api/init_simulation", json={
            "start_era": "2002", "save_name": save_name, "user_role": "spectator"})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertFalse(self.seen_at_setup["prospects"] & set(stale))
        self.assertIn("Rookie One", self.seen_at_setup["prospects"])

    def test_reused_save_folder_with_a_league_without_classes_drops_the_stale_ones(self):
        save_name = "Reused_None_Final"
        stale = [f"Stale Prospect {i}" for i in range(10)]
        stale_dir = os.path.join(save_manager.get_save_path(save_name), "draft_classes")
        write_json(os.path.join(stale_dir, "DRAFT_2003.json"), prospect_rows(stale))
        shutil.rmtree(os.path.join(self.root, "mods", "Draft Mod", "draft_classes"))
        res = self.client.post("/api/init_simulation", json={
            "start_era": "2002", "save_name": save_name, "user_role": "spectator"})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertFalse(self.seen_at_setup["prospects"] & set(stale))
        self.assertFalse(os.path.exists(stale_dir))


class SetupSimulationLeagueMetaTests(unittest.TestCase):
    """setup_simulation puts league_meta and the registry on the Tournament before the draft-class read."""

    def test_league_meta_is_set_before_the_draft_class_read(self):
        import main

        class Stop(Exception):
            pass

        class FakeTournament:
            def __init__(self, squadre, league_settings=None):
                self.squadre = squadre
                self.league_meta = {}
                self.franchise_registry = None

            def imposta_rotazioni_stagione(self):
                pass

        seen = {}

        def record(torneo):
            seen["meta"] = dict(torneo.league_meta)
            seen["registry"] = torneo.franchise_registry
            raise Stop()

        reg = object()
        with mock.patch.object(main, "caricamento_squadre", lambda: ([], [])), \
                mock.patch.object(main, "Tournament", FakeTournament), \
                mock.patch.object(main, "inizializza_scouting_e_classe_draft", record):
            with self.assertRaises(Stop):
                main.setup_simulation(league_meta={"id": "fictional_2002"}, franchise_registry=reg)
        self.assertEqual(seen["meta"], {"id": "fictional_2002"})
        self.assertIs(seen["registry"], reg)


class LoadSaveSetupMetaTests(unittest.TestCase):
    """Loading a save: setup_simulation gets the save's own league_meta and registry."""

    def test_load_passes_the_saved_meta_to_setup(self):
        seen = {}

        class Done(Exception):
            pass

        def fake_setup(league_settings=None, league_meta=None, franchise_registry=None):
            seen["meta"] = league_meta
            seen["registry"] = franchise_registry
            raise Done()

        reg_dict = registry.FranchiseRegistry([], [], {}, {"era": "2002"}).to_dict()
        state = {"league": {"meta": {"id": "fictional_2002", "name": "F", "era": "2002"}, "registry": reg_dict}}
        saved = {k: getattr(server, k) for k in ("SIMULATION_TOURNAMENT", "ACTIVE_SAVE_NAME")}
        self.addCleanup(lambda: [setattr(server, k, v) for k, v in saved.items()])
        self.addCleanup(save_manager.set_active_save_name, save_manager.get_active_save_name())
        self.addCleanup(setattr, registry, "_active", registry._active)
        with mock.patch.object(server.simulation_logic, "setup_simulation", fake_setup):
            with self.assertRaises(Done):
                server.apply_loaded_save_state("Load_Meta_Final", {"metadata": {}, "state_data": state})
        self.assertEqual(seen["meta"], {"id": "fictional_2002", "name": "F", "era": "2002"})
        self.assertIsNotNone(seen["registry"])


if __name__ == "__main__":
    unittest.main()
