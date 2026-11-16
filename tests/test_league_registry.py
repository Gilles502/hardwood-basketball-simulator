# tests/test_league_registry.py
import copy
import os
import unittest
from dataclasses import asdict
from unittest import mock

import core.league.registry as registry_module
from core import save_manager
from core.league.registry import FranchiseRegistry, get_active_registry, reset_active_registry, set_active_registry
from core.league.schema import league_from_dict, load_league
from tests.test_league_schema import make_league_dict

BASE_LEAGUE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "leagues", "fictional_2002", "league.json")


def small_registry():
    raw = make_league_dict()
    raw["franchises"][1]["division"] = "Central"  # swapped with team 5: every division keeps 5 teams
    raw["franchises"][5]["division"] = "Atlantic"
    raw["franchises"][2]["market_weight"] = 9.0
    raw["franchises"][2]["geo_city"] = "Chicago"
    return FranchiseRegistry.from_league(league_from_dict(raw))


class RegistryTests(unittest.TestCase):
    def test_lookups(self):
        reg = small_registry()
        self.assertEqual(reg.by_id("T00").name, "City0 Nick0")
        self.assertIsNone(reg.by_id("nope"))
        self.assertEqual(reg.by_name("City2 Nick2").id, "T02")
        self.assertEqual(len(reg.names()), 30)
        self.assertEqual(reg.conference_of("City0 Nick0"), "East")
        self.assertEqual(reg.conference_of("City20 Nick20"), "West")
        self.assertIsNone(reg.conference_of("Nobody"))
        self.assertEqual(reg.market_weight("City2 Nick2", 1.0), 9.0)
        self.assertEqual(reg.market_weight("Nobody", 1.5), 1.5)
        self.assertEqual(reg.geo_city("City2 Nick2"), "Chicago")
        self.assertEqual(reg.geo_city("Nobody"), "New York")
        self.assertEqual(reg.rivalries(), [("City0 Nick0", "City1 Nick1", 10.0)])
        self.assertEqual(reg.marquee_hosts("mlk_day"), ["City0 Nick0", "City1 Nick1"])
        self.assertEqual(reg.marquee_hosts("none"), [])
        b = reg.branding("City0 Nick0")
        self.assertEqual(set(b), {"abbreviation", "arena", "city", "established", "primary", "secondary"})
        self.assertEqual(b["arena"], "Arena 0")

    def test_divisions_by_display_name(self):
        reg = small_registry()
        divs = reg.divisions()
        self.assertIn("City1 Nick1", divs["Central"])
        self.assertNotIn("City1 Nick1", divs["Atlantic"])
        self.assertIn("City0 Nick0", divs["Atlantic"])
        self.assertEqual(reg.division_of("City1 Nick1"), "Central")

    def test_unknown_name_branding_matches_old_fallback(self):
        reg = small_registry()
        b = reg.branding("Nowhere Club")
        self.assertEqual(b["abbreviation"], "NC")
        self.assertEqual(b["arena"], "Nowhere Club Arena")
        self.assertEqual(b["city"], "NBA City")
        self.assertEqual(b["established"], 2000)
        self.assertEqual(reg.branding("Solo")["abbreviation"], "SOL")

    def test_round_trip_to_dict(self):
        reg = small_registry()
        reg.meta = {"name": "Test League", "era": "2002", "start_year": 2002}
        back = FranchiseRegistry.from_dict(reg.to_dict())
        self.assertEqual(back.to_dict(), reg.to_dict())
        self.assertEqual(back.names(), reg.names())
        self.assertEqual(back.meta["name"], "Test League")

    def test_renamed_league_same_divisions(self):
        real = FranchiseRegistry.from_league(load_league(BASE_LEAGUE))
        raw = {"franchises": [asdict(f) for f in real.franchises]}
        for i, fr in enumerate(raw["franchises"]):
            fr["name"] = f"Renamed {i}"
        renamed = FranchiseRegistry.from_dict(raw)
        for a, b in zip(real.franchises, renamed.franchises):
            self.assertEqual(a.id, b.id)
            self.assertEqual(real.division_of(a.name), renamed.division_of(b.name))

    def test_active_registry_set_and_default(self):
        old = registry_module._active
        try:
            reg = small_registry()
            set_active_registry(reg)
            self.assertIs(get_active_registry(), reg)
            registry_module._active = None
            self.assertGreaterEqual(len(get_active_registry().names()), 0)
        finally:
            registry_module._active = old


class _Team:
    def __init__(self, nome, team_id):
        self.nome = nome
        self.team_id = team_id
        self.roster = []


def _bare_tournament(cls):
    t = cls.__new__(cls)
    t.league_settings = {}
    t.league_meta = {}
    t.franchise_registry = None
    t.squadre = []
    return t


class SaveRoundTripTests(unittest.TestCase):
    def test_save_round_trip_keeps_league_and_team_id(self):
        from main import Tournament
        old = registry_module._active
        try:
            reg = small_registry()
            reg.meta = {"name": "Test League", "era": "2002", "start_year": 2002}
            t = _bare_tournament(Tournament)
            t.league_meta = dict(reg.meta)
            t.franchise_registry = reg
            t.squadre = [_Team("City0 Nick0", "T00")]
            state = save_manager.serialize_tournament_state(t)
            self.assertEqual(state["squadre_data"][0]["team_id"], "T00")
            self.assertEqual(state["league"]["meta"]["name"], "Test League")

            fresh = _bare_tournament(Tournament)
            registry_module._active = None
            save_manager.restore_tournament_state(fresh, copy.deepcopy(state))
            self.assertEqual(fresh.league_meta, reg.meta)
            self.assertEqual(fresh.franchise_registry.to_dict(), reg.to_dict())
            self.assertIs(get_active_registry(), fresh.franchise_registry)

            legacy = {k: v for k, v in state.items() if k != "league"}
            old_t = _bare_tournament(Tournament)
            save_manager.restore_tournament_state(old_t, legacy)
            self.assertEqual(old_t.league_meta, {})
        finally:
            registry_module._active = old


    def test_old_save_without_league_resets_registry(self):
        # A save with no "league" block must not keep the registry of the career played before: it gets the
        # legacy registry (here no league file anywhere, so an empty one).
        import tempfile
        from core.league import draft_source
        from main import Tournament
        old = registry_module._active
        try:
            legacy = save_manager.serialize_tournament_state(_bare_tournament(Tournament))
            legacy.pop("league", None)
            set_active_registry(small_registry())
            with tempfile.TemporaryDirectory() as empty_root,                     mock.patch.object(draft_source, "GAME_ROOT", empty_root):
                save_manager.restore_tournament_state(_bare_tournament(Tournament), legacy)
                self.assertEqual(get_active_registry().names(), [])
        finally:
            registry_module._active = old


class ResetRegistryTests(unittest.TestCase):
    def test_reset_returns_to_lazy_default(self):
        old = registry_module._active
        try:
            set_active_registry(small_registry())
            reset_active_registry()
            self.assertIsNone(registry_module._active)
            with mock.patch.object(registry_module, "_DEFAULT_LEAGUE_PATHS", ()):
                self.assertEqual(get_active_registry().names(), [])
        finally:
            registry_module._active = old

if __name__ == "__main__":
    unittest.main()
