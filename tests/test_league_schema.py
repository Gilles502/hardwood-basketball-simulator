"""League JSON schema, validator and the real league export (Task 1)."""
import os
import sqlite3
import tempfile
import unittest

from core.league.schema import (
    ABILITY_KEYS, TENDENCY_KEYS, SCHEMA_VERSION, LeagueError,
    league_from_dict, league_to_dict, load_league, validate_league,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_LEAGUE = os.path.join(ROOT, "mods", "Real Names 2002", "league.json")
DB_2002 = os.path.join(ROOT, "data", "nba_sim_2002.db")


def make_player(pid, name, role="PG"):
    return {
        "id": pid, "name": name, "role": role, "age": 25, "overall": 70, "potential": 72,
        "provenance": "Test", "pedigree": "Veteran", "morale": 75, "fvs": 70, "is_untouchable": 0,
        "years_on_team": 1, "teams_drafted": "",
        "abilities": {k: 60 for k in ABILITY_KEYS},
        "tendencies": {k: 50 for k in TENDENCY_KEYS},
    }


# Six divisions of five, three per conference (teams 0-14 East, 15-29 West).
TEST_DIVISIONS = ("Atlantic", "Central", "Southeast", "Northwest", "Pacific", "Southwest")


def make_league_dict(n_teams=30):
    """A valid 30-team league: team i's first player is "Player <i+1>", then bench players up to the
    minimum roster (CONFIG.LEAGUE.MIN_ROSTER_SIZE)."""
    from core.config import CONFIG
    ids = [f"T{i:02d}" for i in range(n_teams)]
    franchises, players, gms = [], {}, []
    n = 0
    for i, tid in enumerate(ids):
        franchises.append({
            "id": tid, "name": f"City{i} Nick{i}", "city": f"City{i}", "nickname": f"Nick{i}",
            "abbreviation": tid, "conference": "East" if i < 15 else "West",
            "division": TEST_DIVISIONS[min(i // 5, len(TEST_DIVISIONS) - 1)],
            "geo_city": "New York", "primary": "#111111", "secondary": "#EEEEEE", "arena": f"Arena {i}",
            "established": 1970, "market_weight": 5.0, "owner_personality": "Bilanciato",
        })
        n += 1
        players[tid] = [make_player(f"p{n:04d}", f"Player {n}")] + [
            make_player(f"p{n:04d}b{k}", f"Bench {n}-{k}", role=("SG", "SF", "PF", "C")[k % 4])
            for k in range(1, CONFIG.LEAGUE.MIN_ROSTER_SIZE)]
        gms.append({"gm_id": f"gm{i}", "name": f"GM {i}", "team": tid})
    return {
        "schema_version": SCHEMA_VERSION,
        "meta": {"name": "Test League", "era": "2002", "start_year": 2002},
        "franchises": franchises, "players": players, "free_agents": [],
        "rivalries": [[ids[0], ids[1], 10.0]], "marquee_hosts": {"mlk_day": [ids[0], ids[1]]},
        "staff": {"coach_names": ["Coach A"], "owner_names": ["Owner A"], "gms": {"starting": gms, "arrivals": []}},
    }


class LeagueSchemaTests(unittest.TestCase):
    def test_valid_minimal_league_has_no_errors(self):
        self.assertEqual(validate_league(make_league_dict()), [])

    def test_rejects_wrong_team_count(self):
        raw = make_league_dict()
        raw["franchises"].pop()
        errs = validate_league(raw)
        self.assertTrue(any("30 teams" in e for e in errs), errs)

    def test_rejects_duplicate_player_names(self):
        raw = make_league_dict()
        raw["players"]["T01"][0]["name"] = raw["players"]["T00"][0]["name"]
        errs = validate_league(raw)
        self.assertTrue(any("Player 1" in e and "duplicate" in e for e in errs), errs)

    def test_rejects_unknown_role(self):
        raw = make_league_dict()
        raw["players"]["T00"][0]["role"] = "QB"
        errs = validate_league(raw)
        self.assertTrue(any("QB" in e and "Player 1" in e for e in errs), errs)

    def test_rejects_missing_abilities(self):
        raw = make_league_dict()
        del raw["players"]["T00"][0]["abilities"]
        self.assertTrue(any("abilities" in e for e in validate_league(raw)))
        raw = make_league_dict()
        del raw["players"]["T00"][0]["abilities"]["speed"]
        self.assertTrue(any("speed" in e for e in validate_league(raw)))

    def test_rejects_wrong_schema_version(self):
        raw = make_league_dict()
        raw["schema_version"] = 99
        self.assertTrue(any("schema_version" in e for e in validate_league(raw)))

    def test_rejects_unknown_rivalry_team_id(self):
        raw = make_league_dict()
        raw["rivalries"].append(["T00", "ZZZ", 5.0])
        self.assertTrue(any("ZZZ" in e for e in validate_league(raw)))

    def test_conference_sizes_15_15(self):
        raw = make_league_dict()
        raw["franchises"][0]["conference"] = "West"
        self.assertTrue(any("15 teams" in e for e in validate_league(raw)))

    def test_rejects_non_numeric_franchise_and_player_values(self):
        raw = make_league_dict()
        raw["franchises"][0]["established"] = "1970"
        raw["franchises"][1]["market_weight"] = True
        p = raw["players"]["T02"][0]
        p["morale"] = "high"
        p["fvs"] = None
        p["years_on_team"] = True
        errs = validate_league(raw)
        self.assertTrue(any("T00" in e and "established" in e for e in errs), errs)
        self.assertTrue(any("T01" in e and "market_weight" in e for e in errs), errs)
        for key in ("morale", "fvs", "years_on_team"):
            self.assertTrue(any("Player 3" in e and key in e for e in errs), (key, errs))

    def test_rejects_non_numeric_ability_and_tendency_values(self):
        raw = make_league_dict()
        raw["players"]["T00"][0]["abilities"]["speed"] = "fast"
        raw["players"]["T00"][0]["tendencies"]["foul_tendency"] = True
        errs = validate_league(raw)
        self.assertTrue(any("Player 1" in e and "abilities.speed" in e for e in errs), errs)
        self.assertTrue(any("Player 1" in e and "tendencies.foul_tendency" in e for e in errs), errs)

    # --- Final review: ranges, rosters, divisions, cities, rivalries (CONFIG.LEAGUE) ---

    def test_rejects_overall_and_potential_out_of_range(self):
        raw = make_league_dict()
        raw["players"]["T00"][0]["overall"] = 120
        raw["players"]["T01"][0]["potential"] = 0
        errs = validate_league(raw)
        self.assertTrue(any("Player 1" in e and "overall" in e and "1-99" in e for e in errs), errs)
        self.assertTrue(any("Player 2" in e and "potential" in e and "1-99" in e for e in errs), errs)

    def test_rejects_ability_and_tendency_out_of_range(self):
        raw = make_league_dict()
        raw["players"]["T00"][0]["abilities"]["speed"] = 140
        raw["players"]["T00"][0]["tendencies"]["foul_tendency"] = -5
        errs = validate_league(raw)
        self.assertTrue(any("Player 1" in e and "abilities.speed" in e and "0-100" in e for e in errs), errs)
        self.assertTrue(any("Player 1" in e and "tendencies.foul_tendency" in e for e in errs), errs)

    def test_rejects_age_out_of_range(self):
        raw = make_league_dict()
        raw["players"]["T02"][0]["age"] = 9
        raw["players"]["T03"][0]["age"] = 60
        errs = validate_league(raw)
        self.assertTrue(any("Player 3" in e and "age" in e and "15-50" in e for e in errs), errs)
        self.assertTrue(any("Player 4" in e and "age" in e for e in errs), errs)

    def test_range_limits_come_from_config(self):
        from core.config import CONFIG
        raw = make_league_dict()
        raw["players"]["T00"][0]["overall"] = CONFIG.LEAGUE.PLAYER_RATING_RANGE[1]
        raw["players"]["T00"][0]["age"] = CONFIG.LEAGUE.PLAYER_AGE_RANGE[0]
        raw["players"]["T00"][0]["abilities"]["speed"] = CONFIG.LEAGUE.PLAYER_SKILL_RANGE[1]
        self.assertEqual(validate_league(raw), [])

    def test_free_agent_ranges_are_checked(self):
        raw = make_league_dict()
        fa = make_player("fa01", "Free Guy")
        fa["overall"] = 100
        raw["free_agents"] = [fa]
        self.assertTrue(any("free agents" in e and "Free Guy" in e and "overall" in e
                            for e in validate_league(raw)))

    def test_rejects_short_roster(self):
        from core.config import CONFIG
        raw = make_league_dict()
        raw["players"]["T05"] = raw["players"]["T05"][:4]
        errs = validate_league(raw)
        self.assertTrue(any("City5 Nick5" in e and "4 players" in e and str(CONFIG.LEAGUE.MIN_ROSTER_SIZE) in e
                            for e in errs), errs)

    def test_rejects_division_with_both_conferences(self):
        raw = make_league_dict()
        raw["franchises"][0]["division"] = "Pacific"     # East team in a West division
        raw["franchises"][20]["division"] = "Atlantic"   # keeps the sizes 5/5
        errs = validate_league(raw)
        self.assertTrue(any("Pacific" in e and "East" in e and "West" in e for e in errs), errs)
        self.assertTrue(any("Atlantic" in e and "East" in e and "West" in e for e in errs), errs)

    def test_rejects_divisions_of_different_sizes(self):
        raw = make_league_dict()
        raw["franchises"][1]["division"] = "Central"     # Atlantic 4, Central 6
        errs = validate_league(raw)
        self.assertTrue(any("same number of teams" in e and "Atlantic 4" in e and "Central 6" in e
                            for e in errs), errs)

    def test_rejects_unknown_geo_city(self):
        raw = make_league_dict()
        raw["franchises"][3]["geo_city"] = "Atlantis"
        errs = validate_league(raw)
        self.assertTrue(any("T03" in e and "Atlantis" in e and "geo_city" in e for e in errs), errs)

    def test_rejects_self_rivalry_and_duplicate_pairs(self):
        raw = make_league_dict()
        raw["rivalries"] = [["T00", "T01", 10.0], ["T01", "T00", 5.0], ["T02", "T02", 3.0]]
        errs = validate_league(raw)
        self.assertTrue(any("T02" in e and "itself" in e for e in errs), errs)
        self.assertTrue(any("T00" in e and "T01" in e and "more than once" in e for e in errs), errs)

    def test_shipped_league_files_still_validate(self):
        paths = [os.path.join(ROOT, "data", "leagues", "fictional_2002", "league.json"), REAL_LEAGUE]
        for path in paths:
            if os.path.exists(path):
                load_league(path)  # raises LeagueError with the problems

    def test_round_trip_league_to_dict(self):
        raw = make_league_dict()
        self.assertEqual(league_to_dict(league_from_dict(raw)), raw)

    def test_load_league_raises_league_error_on_invalid_json_text(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "league.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{bad")
            with self.assertRaises(LeagueError) as ctx:
                load_league(path)
            self.assertTrue(ctx.exception.errors)

    def test_real_league_file_is_valid_and_matches_2002_db(self):
        if not os.path.exists(REAL_LEAGUE):
            self.skipTest("Real Names 2002 mod folder is not installed")
        if not os.path.exists(DB_2002):  # sqlite3.connect would create an empty file
            self.skipTest("data/nba_sim_2002.db is not present")
        data = load_league(REAL_LEAGUE)
        conn = sqlite3.connect(DB_2002)
        try:
            for fr in data.franchises:
                rows = conn.execute(
                    "SELECT p.name, p.overall, p.age, p.potential FROM players p JOIN teams t ON t.id = p.team_id "
                    "WHERE t.name = ?", (fr.name,)).fetchall()
                got = sorted((p["name"], p["overall"], p["age"], p["potential"]) for p in data.players[fr.id])
                self.assertEqual(got, sorted(rows), fr.name)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
