"""Release guards: the shipped build holds no real-player data and one version string drives everything."""
import os
import re
import sqlite3
import unittest

from core import paths, version

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestShippedData(unittest.TestCase):
    def test_template_db_is_schema_only(self):
        conn = sqlite3.connect(paths.game_path("data", "nba_sim_template.db"))
        try:
            tables = [n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            filled = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        finally:
            conn.close()
        self.assertIn("players", tables)
        self.assertEqual({t: n for t, n in filled.items() if n}, {})

    def test_spec_bundles_no_real_player_db_or_mod(self):
        with open(os.path.join(ROOT, "Hardwood.spec"), encoding="utf-8") as fh:
            datas = fh.read().split("datas = [", 1)[1].split("]", 1)[0]
        for banned in ("nba_sim_modern.db", "nba_sim_2002.db", "nba_sim.db\"", "mods", "teams_data",
                       "nba_real_career_stats"):
            self.assertNotIn(banned, datas)


class TestVersion(unittest.TestCase):
    def test_version_is_semver(self):
        self.assertRegex(version.VERSION, r"^\d+\.\d+\.\d+(-dev)?$")  # dev builds carry -dev
        self.assertTrue(version.label().startswith(f"v{version.VERSION}"))

    def test_frontend_package_matches(self):
        with open(os.path.join(ROOT, "frontend", "package.json"), encoding="utf-8") as fh:
            self.assertEqual(re.search(r'"version":\s*"([^"]+)"', fh.read()).group(1), version.VERSION)


if __name__ == "__main__":
    unittest.main()
