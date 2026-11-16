"""scripts/check_real_names.py: the release check that shipped files hold no real-league names."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "check_real_names.py")

LEAGUE = {
    "franchises": [{"id": "AAA", "name": "Fake City Foxes", "city": "Fake City", "nickname": "Foxes",
                    "arena": "Fake Garden"}],
    "players": {"AAA": [{"id": "p1", "name": "Corwin Draycott"}]},
    "free_agents": [],
    "staff": {"coach_names": ["Phil Master"], "owner_names": ["Jerry Owner"], "gms": {"starting": [], "arrivals": []}},
}


class CheckRealNamesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        mod = os.path.join(self.root, "mods", "Real Names 2002")
        os.makedirs(os.path.join(mod, "draft_classes"))
        with open(os.path.join(mod, "league.json"), "w", encoding="utf-8") as fh:
            json.dump(LEAGUE, fh)
        with open(os.path.join(mod, "draft_classes", "DRAFT_2003.json"), "w", encoding="utf-8") as fh:
            json.dump([{"name": "Rookie Star"}], fh)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _run(self):
        return subprocess.run([sys.executable, SCRIPT, "--root", self.root], capture_output=True, text=True)

    def test_name_in_shipped_file_fails(self):
        self._write("core/x.py", "# like Corwin Draycott\n")
        r = self._run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("core/x.py:1: Corwin Draycott", r.stdout.replace("\\", "/"))

    def test_other_name_kinds_fail(self):
        self._write("trades/a.py", "x = 'Fake Garden'\n")
        self._write("main.py", "y = 'Rookie Star'\n")
        self._write("offseason/b.py", "z = 'Fake City Foxes'\n")
        out = self._run().stdout
        for name in ("Fake Garden", "Rookie Star", "Fake City Foxes"):
            self.assertIn(name, out)

    def test_name_under_tests_passes(self):
        self._write("tests/t.py", "# Corwin Draycott\n")
        self._write("docs/d.md", "Corwin Draycott\n")
        self.assertEqual(self._run().returncode, 0)

    def test_single_nickname_is_not_a_hit(self):
        self._write("core/x.py", "# the Foxes won\n")
        self.assertEqual(self._run().returncode, 0)

    def test_legacy_field_is_whitelisted(self):
        self._write("core/config.py",
                    'LEGACY_TEAM_IDS: dict = field(default_factory=lambda: {\n'
                    '    "Fake City Foxes": "AAA",\n'
                    '})\n')
        self.assertEqual(self._run().returncode, 0)

    def test_word_boundaries(self):
        self._write("core/x.py", "s = 'XKobe BryantY'\n")
        self.assertEqual(self._run().returncode, 0)


if __name__ == "__main__":
    unittest.main()
