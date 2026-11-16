# scripts/trade_lab.py
"""
Trade lab: run ONE CPU trade window on a frozen league, many times, in seconds - for tuning trade numbers
without simulating seasons.

Two steps, both inside an isolated sandbox copy of the project (the real data/, saves/ and logs are never touched):

  1. make   - simulate one season of a fresh league (all CPU, ~4 min) and freeze the league right before the
              deadline window and right before the pre-draft window (pickled to scratch/trade_lab/<name>_<window>.pkl).
     from-save - freeze an existing save instead (copied into the sandbox; its window is "deadline").
  2. run    - load a frozen league, run the window once per seed and print every trade plus a count by type.

Usage (from VERSION2.0/):
  python scripts/trade_lab.py make --seed 42 --name s42
  python scripts/trade_lab.py from-save --save <SaveFolder> --name myfix
  python scripts/trade_lab.py from-save --save <SaveFolder> --name myfix2 --play-season
  python scripts/trade_lab.py run --fixture s42_deadline --seeds 1-10
  python scripts/trade_lab.py run --fixture s42_predraft --seeds 1-5 --with-draft
  python scripts/trade_lab.py run --fixture clippers_deadline --seeds 1-5 --quiet   (counts only)

`run` uses the CODE in the working tree (fresh sandbox each time), so: edit config/code -> run again.
"""

import argparse
import os
import pickle
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
FIXTURE_DIR = os.path.join(PROJECT_ROOT, "scratch", "trade_lab")
LAB_SAVE = "TRADELAB"


class _Stop(Exception):
    """Raised once both windows are frozen: the rest of the season is not needed."""


# ===================================================================== outer: sandbox + subprocess
def _outer(argv, seed_for_hash: int) -> int:
    from scripts.health_check import build_sandbox

    sandbox = tempfile.mkdtemp(prefix="hardwood_tradelab_")
    try:
        build_sandbox(sandbox)
        shutil.copy2(os.path.abspath(__file__), os.path.join(sandbox, "scripts", "trade_lab.py"))
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONHASHSEED=str(seed_for_hash))
        cmd = [sys.executable, "-u", os.path.join(sandbox, "scripts", "trade_lab.py"), "--inner", *argv]
        return subprocess.call(cmd, cwd=sandbox, env=env)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


# ===================================================================== inner helpers
def _quiet_logs():
    import logging
    mlog = logging.getLogger('main_sim')
    for h in list(mlog.handlers):
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            mlog.removeHandler(h)


def _dump(torneo, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(torneo, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[lab] frozen -> {path} ({os.path.getsize(path) // 1024} KB)", flush=True)


def _bind(torneo):
    """A loaded league becomes the active one (modules read it through these globals)."""
    import main as sim
    import core.models as models
    models.ACTIVE_TOURNAMENT = torneo
    sim.ACTIVE_TOURNAMENT = torneo


def _inner_make(args):
    import shutil as _sh
    _sh.copyfile(os.path.join("data", "nba_sim_2002.db"), os.path.join("data", "nba_sim.db"))
    random.seed(args.seed)
    import main as sim
    from core import save_manager
    _quiet_logs()
    save_manager.set_active_save_name(LAB_SAVE)
    torneo = sim.setup_simulation(league_settings={"trade_difficulty": "realistic"})
    torneo.era_name = "2002 Era"
    torneo.squadra_giocatore = None
    torneo.is_spectator = True
    torneo.active_save_name = LAB_SAVE
    _bind(torneo)

    out = args.fixture_dir
    orig_mid, orig_pre = sim.Tournament.trade_period_midseason, sim.Tournament.trade_period_predraft

    def mid(self):
        _dump(self, os.path.join(out, f"{args.name}_deadline.pkl"))
        return orig_mid(self)

    def pre(self):
        _dump(self, os.path.join(out, f"{args.name}_predraft.pkl"))
        raise _Stop()

    sim.Tournament.trade_period_midseason = mid
    sim.Tournament.trade_period_predraft = pre
    t0 = time.time()
    try:
        sim.run_full_season_cycle(torneo)
    except _Stop:
        pass
    print(f"[lab] done in {time.time() - t0:.0f}s", flush=True)
    return 0


def _inner_from_save(args):
    import main as sim
    from core import save_manager
    _quiet_logs()
    src = os.path.join(args.project_root, "saves", args.save)
    shutil.copytree(src, os.path.join("saves", args.save))
    loaded = save_manager.load_game(args.save)   # copies the save's DB into the sandbox data/
    meta = loaded.get("metadata", {})
    save_manager.set_active_save_name(args.save)
    torneo = sim.setup_simulation()
    torneo.era_name = meta.get("era") or getattr(torneo, "era_name", None)
    save_manager.restore_tournament_state(torneo, loaded.get("state_data", {}))
    if args.cpu_all:
        torneo.squadra_giocatore = None
        torneo.is_spectator = True
    for s in torneo.squadre:
        s.designa_intoccabili(torneo)
    if not args.play_season:
        _dump(torneo, os.path.join(args.fixture_dir, f"{args.name}_deadline.pkl"))
        return 0
    _bind(torneo)
    _freeze_season(sim, torneo, args)
    return 0


def _freeze_season(sim, torneo, args):
    """Plays the league's season (user team on autopilot) and freezes it before the deadline and pre-draft windows."""
    out = args.fixture_dir
    orig_mid = sim.Tournament.trade_period_midseason

    def mid(self):
        _dump(self, os.path.join(out, f"{args.name}_deadline.pkl"))
        return orig_mid(self)

    def pre(self):
        _dump(self, os.path.join(out, f"{args.name}_predraft.pkl"))
        raise _Stop()

    sim.Tournament.trade_period_midseason = mid
    sim.Tournament.trade_period_predraft = pre
    t0 = time.time()
    try:
        sim.run_full_season_cycle(torneo)
    except _Stop:
        pass
    print(f"[lab] done in {time.time() - t0:.0f}s", flush=True)


def _fmt_asset(finder, a) -> str:
    if isinstance(a, str):
        try:
            return finder._format_asset(a)
        except Exception:
            return a
    return f"{a.nome} ({int(a.ovr)}, ${float(a.contract.salario_annuale):.1f}M)"


def _seeds(text: str):
    out = []
    for part in text.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            out.extend(range(int(lo), int(hi) + 1))
        elif part:
            out.append(int(part))
    return out


def _inner_run(args):
    import main as sim  # noqa: F401  (registers the game's modules)
    from trades.trade_finder import TradeFinder
    from trades.windows import run_trade_window
    _quiet_logs()

    path = os.path.join(args.fixture_dir, f"{args.fixture}.pkl")
    window = "predraft" if args.fixture.endswith("_predraft") else "deadline"
    captured = []
    nl_ = chr(10)
    original = TradeFinder.execute_deal

    def execute_deal(self, deal, motive=None, pick_protections=None):
        lines = []
        for team in deal.team_names():
            gets = [_fmt_asset(self, a) for a in deal.receives(team)]
            lines.append(f"{team} get {', '.join(gets) or '-'}")
        ok = original(self, deal, motive, pick_protections)
        if ok:
            sides = " | ".join(f"{s.team} {s.plan} {s.value_given:.0f}->{s.value_received:.0f}"
                               for s in (getattr(motive, "sides", None) or []))
            captured.append((getattr(motive, "trade_type", "?") if motive else "?",
                             "; ".join(lines), (getattr(motive, "why", "") if motive else "") + (
                                 f"{nl_}      value (own GM, given->received): {sides}" if sides else "")))
        return ok

    TradeFinder.execute_deal = execute_deal

    refusals = Counter()
    if args.refusals:
        import re
        from trades.engines import common as _common
        _orig_refuse = _common._refuse

        def _refuse(deal, why):
            key = re.sub(r"\d+(\.\d+)?", "#", why.split(": ", 1)[-1])[:110]
            refusals[key] += 1
            return _orig_refuse(deal, why)
        _common._refuse = _refuse

    totals, per_seed = Counter(), []
    t_all = time.time()
    for seed in _seeds(args.seeds):
        with open(path, "rb") as f:
            torneo = pickle.load(f)
        _bind(torneo)
        for _team in torneo.squadre:   # frozen flags predate the veteran limit: apply it
            _team._limit_veteran_untouchables(torneo)
        random.seed(seed)
        captured.clear()
        t0 = time.time()
        run_trade_window(torneo, window)
        if args.with_draft and window == "predraft":
            from offseason.draft import Draft
            Draft(torneo, torneo.squadre, None).esegui_o_continua_draft()
        counts = Counter(t for t, _, _ in captured)
        totals.update(counts)
        per_seed.append(len(captured))
        print(f"\n=== seed {seed}: {len(captured)} trades ({time.time() - t0:.1f}s) "
              f"{dict(counts.most_common())}", flush=True)
        if not args.quiet:
            for ttype, text, why in captured:
                print(f"  [{ttype}] {text}\n      why: {why}")
    n = max(1, len(per_seed))
    print(f"\n##### {args.fixture} ({window}) over {len(per_seed)} seeds, {time.time() - t_all:.0f}s: "
          f"{sum(per_seed) / n:.1f} trades/window (min {min(per_seed, default=0)}, max {max(per_seed, default=0)})")
    for ttype, c in totals.most_common():
        print(f"  {ttype:22s} {c / n:5.2f}/window  {100 * c / max(1, sum(totals.values())):4.0f}%")
    for why, c in refusals.most_common(15):
        print(f"  refused x{c / n:7.1f}/window  {why}")
    return 0


# ===================================================================== CLI
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    argv = sys.argv[1:]
    inner = bool(argv) and argv[0] == "--inner"
    if inner:
        argv = argv[1:]
        sys.path.insert(0, os.getcwd())

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("make", "from-save", "run"):
        p = sub.add_parser(name)
        p.add_argument("--fixture-dir", default=FIXTURE_DIR)
        p.add_argument("--project-root", default=PROJECT_ROOT)
        if name == "make":
            p.add_argument("--seed", type=int, default=42)
            p.add_argument("--name", required=True)
        elif name == "from-save":
            p.add_argument("--save", required=True)
            p.add_argument("--name", required=True)
            p.add_argument("--cpu-all", action="store_true", help="the user's team trades like a CPU team")
            p.add_argument("--play-season", action="store_true",
                           help="play the save's season and freeze its deadline + pre-draft windows (~2-4 min)")
        else:
            p.add_argument("--fixture", required=True, help="e.g. s42_deadline, s42_predraft, clippers_deadline")
            p.add_argument("--seeds", default="1-5")
            p.add_argument("--with-draft", action="store_true", help="predraft: also run the draft (draft-night trades)")
            p.add_argument("--quiet", action="store_true")
            p.add_argument("--refusals", action="store_true", help="count why deals were not closed (top reasons)")
    args = ap.parse_args(argv)

    if not inner:
        if args.cmd == "run" and not os.path.exists(os.path.join(args.fixture_dir, f"{args.fixture}.pkl")):
            print(f"No fixture {args.fixture}.pkl in {args.fixture_dir}")
            return 1
        extra = [] if any(a.startswith("--fixture-dir") for a in argv) else ["--fixture-dir", args.fixture_dir]
        extra += [] if any(a.startswith("--project-root") for a in argv) else ["--project-root", args.project_root]
        return _outer([*argv, *extra], getattr(args, "seed", 0))
    return {"make": _inner_make, "from-save": _inner_from_save, "run": _inner_run}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
