"""Pre-commit guard (.githooks/pre-commit): refuses staged files that must never be public.

    python scripts/check_commit.py

Refused: saves, databases other than the empty template, anything under mods/ except the guide, logs, private
notes. Then, when mods/Real Names 2002 is installed locally, runs scripts/check_real_names.py on the working tree.
Exits 1 with the reasons.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = {"data/nba_sim_template.db", "mods/README.md"}
BLOCKED_PREFIXES = ("saves/", "mods/", "logs/", "scratch/", "docs/", ".claude/", ".superpowers/", ".agents/")
BLOCKED_NAMES = {"AGENTS.md", "GEMINI.md", "CLAUDE.md"}
BLOCKED_SUFFIXES = (".db", ".log", ".zip")


def staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def refused(path):
    if path in ALLOWED:
        return None
    if path.startswith(BLOCKED_PREFIXES):
        return "private or local-only folder"
    if os.path.basename(path) in BLOCKED_NAMES:
        return "private notes"
    if path.endswith(BLOCKED_SUFFIXES):
        return "database, log or archive"
    return None


def main():
    problems = [f"{p}: {why}" for p in staged_files() if (why := refused(p))]
    # check_real_names.py reads the names to look for from this mod (kept local, never committed).
    if os.path.isfile(os.path.join(ROOT, "mods", "Real Names 2002", "league.json")):
        check = subprocess.run([sys.executable, os.path.join("scripts", "check_real_names.py")], cwd=ROOT,
                               capture_output=True, text=True)
        if check.returncode != 0:
            problems.append("real names found:\n" + check.stdout.strip())
    else:
        print("check_commit: no real-names mod in mods/, real-name scan skipped")
    if problems:
        print("Commit refused:\n  " + "\n  ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
