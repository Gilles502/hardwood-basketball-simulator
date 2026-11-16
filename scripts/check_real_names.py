"""Release check: shipped files must not contain real-league names.

    python scripts/check_real_names.py [--root .]     (from VERSION2.0/)

Names come from `mods/Real Names 2002/league.json` and its draft classes: players, franchise names, arenas, coach
and owner names (GMs are parody names already). Shipped code and data are scanned (core/, offseason/, trades/, main.py, server.py,
data/leagues/fictional_2002/, data/filler_players.json, frontend/src/). Tests, docs, scripts, mods and saves are
skipped. The one allowed real-name table is `CONFIG.LEGACY_TEAM_IDS` (old saves store team names). Matches are
whole names, case-sensitive; single words (a nickname alone) never match. Prints `path:line: name`, exits 1 on a hit.
"""
import argparse
import glob
import json
import os
import re
import sys

SCAN = ["core", "offseason", "trades", "main.py", "server.py", os.path.join("data", "leagues", "fictional_2002"),
        os.path.join("data", "filler_players.json"), os.path.join("frontend", "src")]
EXTENSIONS = {".py", ".json", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".txt"}
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "dist"}
WHITELIST_START = "LEGACY_TEAM_IDS: dict"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def real_names(root: str) -> set:
    """Multi-word real names: players (league + draft classes), franchises, arenas, coaches, owners."""
    mod = os.path.join(root, "mods", "Real Names 2002")
    league = _read(os.path.join(mod, "league.json"))
    names = set()
    for plist in league.get("players", {}).values():
        names |= {p.get("name") for p in plist}
    names |= {p.get("name") for p in league.get("free_agents", [])}
    for fr in league.get("franchises", []):
        names |= {fr.get("name"), fr.get("arena")}
        if fr.get("city") and fr.get("nickname"):
            names.add(f"{fr['city']} {fr['nickname']}")
    staff = league.get("staff", {})
    names |= set(staff.get("coach_names", [])) | set(staff.get("owner_names", []))
    for path in sorted(glob.glob(os.path.join(mod, "draft_classes", "*.json"))):
        names |= {p.get("name") or p.get("nome") for p in _read(path)}
    return {n for n in names if n and " " in n.strip()}


def _files(root: str):
    for entry in SCAN:
        path = os.path.join(root, entry)
        if os.path.isfile(path):
            yield path
        for base, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if os.path.splitext(f)[1] in EXTENSIONS:
                    yield os.path.join(base, f)


def scan(root: str):
    names = sorted(real_names(root), key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in names) + r")(?!\w)")
    hits = []
    for path in _files(root):
        in_whitelist = False
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            for lineno, line in enumerate(fh, 1):
                if WHITELIST_START in line:
                    in_whitelist = True
                if in_whitelist:
                    if line.rstrip().endswith("})"):
                        in_whitelist = False
                    continue
                for m in pattern.finditer(line):
                    hits.append((os.path.relpath(path, root), lineno, m.group(1)))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = parser.parse_args()
    hits = scan(args.root)
    for path, lineno, name in hits:
        print(f"{path}:{lineno}: {name}")
    if hits:
        print(f"{len(hits)} real-name hit(s) in shipped files.")
        return 1
    print("No real names in shipped files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
