"""Smoke test of the packaged build: start Hardwood.exe headless on a temp user root and check it serves the game.

    python scripts/smoke_exe.py [--exe dist/Hardwood/Hardwood.exe]

Checks: the exe starts and writes its port, GET / is the built SPA, GET /api/saves is JSON, an unknown API path
is a 404, and the exe folder is unchanged afterwards (nothing written next to the exe). Prints SMOKE OK, exit 0.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

GAME_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXE = os.path.join(GAME_ROOT, "dist", "Hardwood", "Hardwood.exe")
PORT_TIMEOUT_S = 90
SPA_MARKER = '<div id="root">'


def folder_listing(folder):
    out = {}
    for d, _, files in os.walk(folder):
        for f in files:
            path = os.path.join(d, f)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, folder)] = hashlib.sha1(fh.read()).hexdigest()
    return out


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def run(exe):
    if not os.path.isfile(exe):
        return f"exe not found: {exe} (build it with python scripts/build_exe.py)"
    exe_dir = os.path.dirname(exe)
    before = folder_listing(exe_dir)
    user = tempfile.mkdtemp(prefix="hardwood_smoke_")
    env = dict(os.environ, HARDWOOD_USER_DIR=user)
    env.pop("HARDWOOD_SAVES_DIR", None)
    proc = subprocess.Popen([exe, "--headless"], env=env, cwd=user)
    try:
        port_file = os.path.join(user, "logs", "port.txt")
        deadline = time.monotonic() + PORT_TIMEOUT_S
        while not os.path.isfile(port_file):
            if proc.poll() is not None:
                return f"exe exited early with code {proc.returncode}; see {user}\\logs"
            if time.monotonic() > deadline:
                return f"no port after {PORT_TIMEOUT_S}s; see {user}\\logs"
            time.sleep(0.5)
        time.sleep(0.2)
        with open(port_file, encoding="utf-8") as fh:
            base = f"http://127.0.0.1:{fh.read().strip()}"
        status, body = get(base + "/")
        if status != 200 or SPA_MARKER.encode() not in body:
            return f"GET / -> {status}, SPA marker missing"
        status, body = get(base + "/api/saves")
        if status != 200 or "saves" not in json.loads(body):
            return f"GET /api/saves -> {status} {body[:200]!r}"
        status, _ = get(base + "/api/does-not-exist")
        if status != 404:
            return f"GET /api/does-not-exist -> {status}, expected 404"
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait(timeout=30)
    after = folder_listing(exe_dir)
    if after != before:
        changed = sorted(set(after.items()) ^ set(before.items()))
        return f"exe folder changed: {[c[0] for c in changed][:10]}"
    shutil.rmtree(user, ignore_errors=True)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exe", default=DEFAULT_EXE)
    args = parser.parse_args()
    error = run(os.path.abspath(args.exe))
    if error:
        print(f"SMOKE FAILED: {error}")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
