"""Every CONFIG.<SECTION>.<FIELD> used anywhere in the game code must exist in core/config.py.

Covers the direct form (CONFIG.COACHING.FOUL_OUT_LIMIT) and the common alias form
(cfg = CONFIG.PROGRESSION ... cfg.AGE_RETIREMENT_THRESHOLD), resolved per function.
"""
import ast
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import CONFIG

SCAN = ["core", "trades", "offseason", "tournament", "utils", "scripts"]
SCAN_FILES = ["main.py", "server.py"]


def _python_files():
    for folder in SCAN:
        for dirpath, _, names in os.walk(os.path.join(ROOT, folder)):
            for name in names:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)
    for name in SCAN_FILES:
        yield os.path.join(ROOT, name)


def _section_of(node):
    """CONFIG.<SECTION> -> SECTION, else None."""
    if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "CONFIG"):
        return node.attr
    return None


def find_unresolved_references(config, tree, label):
    problems = []

    def check(section_names, field_node):
        """A name may be re-bound to several sections inside one function: flag only if none has the field."""
        sections = [getattr(config, s, None) for s in section_names]
        if all(s is None for s in sections):
            problems.append(f"{label}:{field_node.lineno} CONFIG.{'/'.join(section_names)} does not exist")
        elif not any(s is not None and hasattr(s, field_node.attr) for s in sections):
            problems.append(f"{label}:{field_node.lineno} CONFIG.{'/'.join(section_names)}.{field_node.attr} does not exist")

    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for scope in scopes:
        aliases = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and _section_of(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases.setdefault(target.id, set()).add(_section_of(node.value))
        for node in ast.walk(scope):
            if isinstance(node, ast.Attribute):
                direct = _section_of(node.value)
                if direct:
                    check([direct], node)
                elif isinstance(node.value, ast.Name) and node.value.id in aliases:
                    check(sorted(aliases[node.value.id]), node)
    # the same node can be seen from nested scopes
    return sorted(set(problems))


class ConfigReferenceTests(unittest.TestCase):
    def test_every_config_reference_resolves(self):
        problems = []
        for path in _python_files():
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            problems += find_unresolved_references(CONFIG, tree, os.path.relpath(path, ROOT))
        self.assertEqual([], problems)

    def test_checker_catches_alias_references_to_missing_fields(self):
        tree = ast.parse("def f():\n    cfg = CONFIG.PROGRESSION\n    return cfg.NO_SUCH_FIELD\n")
        self.assertEqual(1, len(find_unresolved_references(CONFIG, tree, "snippet")))
        tree = ast.parse("def f():\n    return CONFIG.NO_SUCH_SECTION.X\n")
        self.assertEqual(1, len(find_unresolved_references(CONFIG, tree, "snippet")))


if __name__ == "__main__":
    unittest.main()
