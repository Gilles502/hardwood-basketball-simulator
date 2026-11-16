"""Builds the packaged game with one command: dist/Hardwood/Hardwood.exe.

    python scripts/build_exe.py [--skip-frontend]

Steps: npm run build in frontend/, PyInstaller with Hardwood.spec, then scripts/smoke_exe.py.
Needs the build tools: python -m pip install -r requirements-build.txt
Exit code is non-zero if any step fails.
"""
import os
import subprocess
import sys

GAME_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def step(title, cmd, cwd, shell=False):
    print(f"\n=== {title} ===", flush=True)
    result = subprocess.run(cmd, cwd=cwd, shell=shell)
    if result.returncode != 0:
        print(f"FAILED: {title} (exit {result.returncode})")
        sys.exit(result.returncode or 1)


def main():
    if "--skip-frontend" not in sys.argv[1:]:
        step("Frontend build", "npm run build", os.path.join(GAME_ROOT, "frontend"), shell=True)
    if not os.path.isfile(os.path.join(GAME_ROOT, "frontend", "dist", "index.html")):
        print("FAILED: frontend/dist/index.html missing")
        return 1
    step("PyInstaller", [sys.executable, "-m", "PyInstaller", "Hardwood.spec", "--noconfirm", "--clean"], GAME_ROOT)
    step("Smoke test", [sys.executable, os.path.join("scripts", "smoke_exe.py")], GAME_ROOT)
    print(f"\nBuilt: {os.path.join(GAME_ROOT, 'dist', 'Hardwood', 'Hardwood.exe')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
