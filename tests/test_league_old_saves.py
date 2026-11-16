"""Old saves (no "league" block) load as before: names and conferences from the save, a legacy franchise
registry (Real Names 2002 mod if installed, else the fictional league renamed by team id), nothing written."""
import json
import os
import shutil
import tempfile
import time
import unittest
from dataclasses import replace
from unittest import mock

from core import save_manager
from core.config import CONFIG
from core.league import draft_source
from core.league import registry as registry_module
from core.league.registry import FranchiseRegistry, get_active_registry, set_active_registry
from core.league.schema import league_to_dict, load_league

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_LEAGUE = os.path.join(ROOT, "mods", "Real Names 2002", "league.json")
TORONTO_SAVE = os.path.join(ROOT, "saves", "Carriera_2002_Toronto_Raptors")


def legacy_names(team_id):
    """The names old saves store for a franchise, from the one allowed table (CONFIG.LEAGUE.LEGACY_TEAM_IDS)."""
    return [name for name, tid in CONFIG.LEAGUE.LEGACY_TEAM_IDS.items() if tid == team_id]


TOR, PHO = legacy_names("TOR")[0], legacy_names("PHO")[0]
LAC, LAC_ALIAS = legacy_names("LAC")[:2]


def real_arena(team_id):
    return next(f.arena for f in load_league(REAL_LEAGUE).franchises if f.id == team_id)


def _write_league(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(league_to_dict(data), fh)


def _fictional_league():
    """The real league with fictional names and arenas, same ids/divisions (stand-in for the built-in file)."""
    data = load_league(REAL_LEAGUE)
    data.franchises = [replace(f, name=f"{f.city} Test{f.id}", nickname=f"Test{f.id}", arena=f"Test Arena {f.id}")
                       for f in data.franchises]
    return data


def _bare_tournament(teams):
    from main import Tournament
    t = Tournament.__new__(Tournament)
    t.league_settings = {}
    t.league_meta = {"stale": True}
    t.franchise_registry = None
    t.squadre = teams
    t.squadre_est = []
    t.squadre_ovest = []
    return t


@unittest.skipUnless(os.path.isfile(REAL_LEAGUE), "Real Names 2002 mod not installed")
class LegacyRestoreTests(unittest.TestCase):
    def setUp(self):
        from core.models import Squadra
        self.real = load_league(REAL_LEAGUE)
        self.tmp = tempfile.mkdtemp(prefix="hardwood_old_saves_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        _write_league(_fictional_league(), os.path.join(self.tmp, "data", "leagues", "fictional_2002", "league.json"))
        os.makedirs(os.path.join(self.tmp, "mods"))
        p = mock.patch.object(draft_source, "GAME_ROOT", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        previous = registry_module._active
        self.addCleanup(set_active_registry, previous)
        # A registry from another career, active before the load: it must not survive.
        set_active_registry(FranchiseRegistry([], [], {}, {"era": "modern"}))
        # setup_simulation ran with a registry that knew none of the names: no conference, no id.
        self.teams = [Squadra(nome=f.name, conference=None, team_id="") for f in self.real.franchises]
        self.state = {"squadre_data": [{"nome": f.name, "conference": f.conference, "division": "Atlantic",
                                        "vittorie": 3} for f in self.real.franchises],
                      "player_team_name": TOR}

    def _restore(self):
        t = _bare_tournament(self.teams)
        save_manager.restore_tournament_state(t, self.state)
        return t

    def _install_mod(self):
        _write_league(self.real, os.path.join(self.tmp, "mods", "Real Names 2002", "league.json"))

    def test_old_save_without_mod_keeps_names_and_divisions(self):
        t = self._restore()
        reg = get_active_registry()
        self.assertIs(reg, t.franchise_registry)
        self.assertEqual(t.league_meta, {})
        by_id = {f.id: f for f in self.real.franchises}
        self.assertEqual([s.nome for s in t.squadre], [f.name for f in self.real.franchises])
        for s in t.squadre:
            real = by_id[CONFIG.LEAGUE.LEGACY_TEAM_IDS[s.nome]]
            self.assertEqual(s.team_id, real.id)
            self.assertEqual(s.conference, real.conference)
            self.assertEqual(reg.division_of(s.nome), real.division)
            self.assertEqual(s.vittorie, 3)
        self.assertEqual(len(t.squadre_est), 15)
        self.assertEqual(len(t.squadre_ovest), 15)
        self.assertEqual(reg.branding(TOR)["arena"], "Test Arena TOR")
        self.assertEqual(reg.meta.get("era"), "2002")
        self.assertIs(t.squadra_giocatore, t.squadre[[f.id for f in self.real.franchises].index("TOR")])

    def test_old_save_with_mod_uses_real_branding(self):
        self._install_mod()
        t = self._restore()
        reg = get_active_registry()
        self.assertIs(reg, t.franchise_registry)
        self.assertEqual(reg.branding(TOR)["arena"], real_arena("TOR"))
        self.assertEqual(reg.division_of(TOR), self.real.franchises[
            [f.id for f in self.real.franchises].index("TOR")].division)

    def test_old_alias_name_matches_by_id(self):
        self._install_mod()
        lac = next(s for s in self.teams if s.nome == LAC)
        lac.nome = LAC_ALIAS
        next(d for d in self.state["squadre_data"] if d["nome"] == LAC)["nome"] = LAC_ALIAS
        t = self._restore()
        self.assertEqual(lac.team_id, "LAC")
        self.assertEqual(get_active_registry().division_of(LAC_ALIAS),
                         next(f.division for f in self.real.franchises if f.id == "LAC"))

    def test_unknown_old_team_name_logs_one_warning(self):
        self._install_mod()
        tor = next(s for s in self.teams if s.nome == TOR)
        tor.nome = "Toronto Old Name"  # renamed by the owner: not in CONFIG.LEAGUE.LEGACY_TEAM_IDS
        next(d for d in self.state["squadre_data"] if d["nome"] == TOR)["nome"] = "Toronto Old Name"
        with self.assertLogs("main_sim", level="WARNING") as logs:
            self._restore()
        hits = [m for m in logs.output if "Toronto Old Name" in m]
        self.assertEqual(len(hits), 1, logs.output)
        self.assertIn("LEGACY_TEAM_IDS", hits[0])
        self.assertEqual(tor.team_id, "")
        # Known names (all the others) log nothing.
        self.assertFalse([m for m in logs.output if "LEGACY_TEAM_IDS" in m and "Toronto Old Name" not in m])

    def test_no_league_anywhere_gives_an_empty_registry(self):
        os.remove(os.path.join(self.tmp, "data", "leagues", "fictional_2002", "league.json"))
        t = self._restore()
        self.assertEqual(get_active_registry().names(), [])
        self.assertEqual(t.squadre[0].conference, self.real.franchises[0].conference)

    def test_legacy_team_ids_cover_the_2002_league(self):
        ids = CONFIG.LEAGUE.LEGACY_TEAM_IDS
        for f in self.real.franchises:
            self.assertEqual(ids.get(f.name), f.id)
        self.assertEqual(ids[LAC_ALIAS], "LAC")
        self.assertEqual(ids[PHO], "PHO")


def _snapshot(folder):
    out = {}
    for base, dirs, files in os.walk(folder):
        for name in dirs + files:
            path = os.path.join(base, name)
            st = os.stat(path)
            out[os.path.relpath(path, folder)] = (st.st_mtime_ns, st.st_size if name in files else 0)
    st = os.stat(folder)
    out["."] = (st.st_mtime_ns, 0)
    return out


@unittest.skipUnless(os.path.isdir(TORONTO_SAVE), "the Toronto save is not on this machine")
class TorontoCopyTests(unittest.TestCase):
    def test_toronto_copy_loads(self):
        """Loads a COPY of the owner's dynasty through the server's load path (the original is read-only)."""
        import contextlib
        import io
        from core import db_manager
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        before = _snapshot(TORONTO_SAVE)
        tmp = tempfile.mkdtemp(prefix="hardwood_toronto_copy_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        saves = os.path.join(tmp, "saves")
        name = os.path.basename(TORONTO_SAVE)
        shutil.copytree(TORONTO_SAVE, os.path.join(saves, name))
        os.makedirs(os.path.join(tmp, "data"))
        live_db = os.path.join(tmp, "data", "nba_sim.db")

        previous_registry = registry_module._active
        previous_save = save_manager.get_active_save_name()
        server_globals = {k: getattr(server, k) for k in ("SIMULATION_TOURNAMENT", "LEAGUE_STATE", "ACTIVE_SAVE_NAME")}

        def _restore_globals():
            for k, v in server_globals.items():
                setattr(server, k, v)
            set_active_registry(previous_registry)
            save_manager.set_active_save_name(previous_save)
        self.addCleanup(_restore_globals)

        # A fictional career played before in this process must not leak into the old save.
        set_active_registry(FranchiseRegistry.from_league(_fictional_league()))
        started = time.time()
        with mock.patch.object(save_manager, "SAVES_DIR", saves), \
                mock.patch.object(save_manager, "BASE_DIR", tmp), \
                mock.patch.object(db_manager, "DB_NAME", live_db), \
                contextlib.redirect_stdout(io.StringIO()):
            loaded = save_manager.load_game(name)
            server.apply_loaded_save_state(name, loaded)
            t = server.SIMULATION_TOURNAMENT
        elapsed = time.time() - started
        print(f"\n[test_toronto_copy_loads] load took {elapsed:.1f}s")

        self.assertEqual(len(t.squadre), 30)
        self.assertEqual(t.squadra_giocatore.nome, TOR)
        self.assertEqual(t.squadra_giocatore.team_id, "TOR")
        self.assertEqual(t.league_meta, {})
        self.assertEqual(len(t.squadre_est), 15)
        self.assertEqual(len(t.squadre_ovest), 15)
        reg = get_active_registry()
        self.assertIs(reg, t.franchise_registry)
        if os.path.isfile(REAL_LEAGUE):
            self.assertEqual(reg.branding(TOR)["arena"], real_arena("TOR"))
        # Division and historic rivalries are built at setup: the save's registry was in place by then.
        self.assertGreater(len(t.rivalry_tracker.rivalries), 30)
        for s in t.squadre:
            self.assertTrue(s.team_id, s.nome)
            self.assertIsNotNone(reg.division_of(s.nome), s.nome)
        # The original folder is untouched (mtimes and sizes).
        self.assertEqual(_snapshot(TORONTO_SAVE), before)


if __name__ == "__main__":
    unittest.main()
