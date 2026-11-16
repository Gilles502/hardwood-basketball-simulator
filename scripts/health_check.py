# scripts/health_check.py
"""
Hardwood Basketball Simulator Health Check — headless multi-season simulation with a league health report.

Runs N full season cycles (regular season, deadline, playoffs, offseason, draft, FA) with
all 30 teams controlled by the CPU, inside an ISOLATED SANDBOX copy of the project, so the
real data/nba_sim.db, saves/ and root log files are never touched.

After every season it:
  * records trades (type, period, teams), team strategies, wins, payroll, rosters, picks
  * saves the league, reloads it into a fresh Tournament and diffs a state fingerprint
    (by default the simulation then CONTINUES FROM THE RELOADED STATE, like a real player)

Output (default: scratch/health/<timestamp>_<era>_<label>/):
  report.md      human-readable summary
  metrics.json   raw per-season metrics (for comparing runs)
  sim.log        full stdout/stderr of the simulation

League (2002 era): --league <id> picks the league file the run starts from, built through the league
catalogue (core/league/catalog.py) exactly as a new career does: the built-in fictional league by default
(what the public plays), "Real Names 2002" for the mod (compare with runs made before league files).

Usage (from VERSION2.0/):
  python scripts/health_check.py --seasons 10 --era 2002 --seed 42 --label baseline
  python scripts/health_check.py --seasons 10 --league "Real Names 2002" --label real_names
  python scripts/health_check.py --compare scratch/health/<runA>/metrics.json scratch/health/<runB>/metrics.json
"""

import argparse
import datetime
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter, defaultdict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# `python scripts/health_check.py` puts scripts/ on sys.path, not the project root: the report needs `core`.
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Files/dirs copied into the sandbox (code + game data only; no saves, no frontend). `data` holds the
# built-in league (data/leagues/); `mods` the Real Names 2002 league and its draft classes. The league DB is
# built inside the sandbox (data/leagues/built/), never in the real data/.
SANDBOX_DIRS = ["core", "offseason", "trades", "tournament", "utils", "data", "mods", "scripts"]
SANDBOX_FILES = ["main.py"]

ERAS = ("2002", "modern")
# The modern era starts from a fixed DB; the 2002 era from a league file (--league, prepare_league).
ERA_TEMPLATES = {"modern": "nba_sim_modern.db"}
SAVE_NAME = "HEALTHCHECK"

# Trade reason -> trade type. First match wins (order matters).
TRADE_TYPE_PATTERNS = [
    ("[DRAFT TRADE-UP]", "pick_swap"),
    ("Veteran Dump", "veteran_dump_auction"),
    ("Roster Congestion Relief", "congestion_auction"),
    ("TRADE DEMAND", "star_trade_demand"),
    ("[CAP RELIEF]", "cap_relief"),
    ("[MULTI-PLAYER PACKAGE]", "multi_player_package"),
    ("[2-FOR-2 DEPTH SWAP]", "depth_swap_2for2"),
    ("[POSITIONAL SWAP]", "positional_swap"),
    ("[WIN-NOW FOR YOUTH]", "win_now_for_youth"),
    ("[3-TEAM FACILITATED]", "3team_facilitated"),
    ("[3-TEAM BLOCKBUSTER]", "3team_star_facilitator"),
    ("[3-WAY POSITIONAL FIT]", "3team_positional"),
    ("[3-TEAM WIN-NOW/REBUILD]", "3team_winnow_rebuild"),
    ("[4-TEAM", "4team_circular"),
    ("packages picks for young star", "upgrade_young_star"),
    ("upgrades", "upgrade_star"),
    ("[BENCH SHUFFLE]", "bench_shuffle"),
    ("Auction Win", "auction_other"),
]


# Trade types that come out of an auction (trades/engines/auction.py).
AUCTION_TYPES = ("roster_congestion", "trade_demand", "veteran_sale")

# Types that give value away on purpose (priced by design): excluded from the gift count, reported on their own.
DISCOUNTED_TYPES = {"trade_demand": "STAR_WANTS_OUT", "tax_dump": "SHED_TAX"}


def classify_trade(reason: str) -> str:
    """Legacy fallback only: the type of a deal that carries no motive."""
    for pattern, ttype in TRADE_TYPE_PATTERNS:
        if pattern in (reason or ""):
            return ttype
    return "other"


def record_type(motive, reason: str) -> str:
    """The trade type code of a deal: the motive's, or the legacy classification of its reason text."""
    code = (motive or {}).get("trade_type") if isinstance(motive, dict) else getattr(motive, "trade_type", None)
    return code or classify_trade(reason)


ERA_BUCKET_SEASONS = 5


def _share(counter: Counter) -> dict:
    total = sum(counter.values())
    return {k: v / total for k, v in counter.items()} if total else {}


def trade_rework_metrics(trades: list, windows: list, gift_share: float = None, disaster_below: int = None) -> dict:
    """Trade rework gate numbers from the trades of one or more seasons (pure: plain dicts in, dict out).

    trade: {season, period, teams, type, team_count, has_motive, star, sides: [{team, plan, wish_kind, trade_skill,
            value_given, value_received}]}; window: {season, period}.
    User trades (type "user") are not CPU trades: they are left out of every number here.
    Mean trades per team per window is taken over the team-windows with at least one deal."""
    if gift_share is None or disaster_below is None:
        from core.config import CONFIG
        gift_share = CONFIG.TRADES.GIFT_SHARE if gift_share is None else gift_share
        disaster_below = CONFIG.FRONT_OFFICE.DISASTER_SKILL_BELOW if disaster_below is None else disaster_below
    cpu = [t for t in trades if t.get("type") != "user"]
    n = len(cpu)
    covered = sum(1 for t in cpu if t.get("has_motive"))
    types = Counter(t["type"] for t in cpu)
    type_share = _share(types)
    top = types.most_common(1)[0][0] if types else None

    per_team_window = Counter()
    for t in cpu:
        for name in set(t["teams"]):
            per_team_window[(t.get("season"), t.get("period"), name)] += 1
    seasons = {w.get("season") for w in windows} | {t.get("season") for t in cpu}
    seasons.discard(None)

    gifts = disaster_gifts = 0
    ratios = {kind: [] for kind in DISCOUNTED_TYPES}
    for t in cpu:
        for s in t.get("sides", []):
            if s.get("plan") == "USER" or not s.get("value_given"):
                continue
            ratio = s.get("value_received", 0.0) / s["value_given"]
            wish = DISCOUNTED_TYPES.get(t["type"])
            if wish is not None:
                if s.get("wish_kind") == wish:
                    ratios[t["type"]].append(ratio)
                continue
            if ratio < gift_share:
                skill = s.get("trade_skill")
                if skill is not None and skill < disaster_below:
                    disaster_gifts += 1
                else:
                    gifts += 1

    by_bucket = defaultdict(Counter)
    for t in cpu:
        start = ((t.get("season", 1) - 1) // ERA_BUCKET_SEASONS) * ERA_BUCKET_SEASONS + 1
        by_bucket[f"{start}-{start + ERA_BUCKET_SEASONS - 1}"][t["type"]] += 1

    return {
        "cpu_trades": n,
        "motive_coverage": covered / n if n else 1.0,
        "type_share": type_share,
        "max_type_share": type_share[top] if top else 0.0,
        "max_type": top,
        "trades_per_team_per_window": {
            "max": max(per_team_window.values()) if per_team_window else 0,
            "mean": statistics.mean(per_team_window.values()) if per_team_window else 0.0,
        },
        "star_trades_per_season": (sum(1 for t in cpu if t.get("star")) / len(seasons)) if seasons else 0.0,
        "gift_trades": gifts,
        "gift_trades_disaster": disaster_gifts,
        "discounted_share": {k: statistics.mean(v) for k, v in ratios.items() if v},
        "team_count_mix": _share(Counter(t.get("team_count", 2) for t in cpu)),
        "type_mix_by_era": {k: _share(c) for k, c in sorted(by_bucket.items(), key=lambda kv: int(kv[0].split("-")[0]))},
    }


# =====================================================================================
# OUTER PROCESS: sandbox + subprocess + report
# =====================================================================================

def build_sandbox(sandbox_dir: str):
    os.makedirs(sandbox_dir, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for d in SANDBOX_DIRS:
        src = os.path.join(PROJECT_ROOT, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(sandbox_dir, d), ignore=ignore, dirs_exist_ok=True)
    for f in SANDBOX_FILES:
        shutil.copy2(os.path.join(PROJECT_ROOT, f), os.path.join(sandbox_dir, f))
    os.makedirs(os.path.join(sandbox_dir, "scratch"), exist_ok=True)
    os.makedirs(os.path.join(sandbox_dir, "saves"), exist_ok=True)


def run_outer(args):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.abspath(args.out or os.path.join(PROJECT_ROOT, "scratch", "health", f"{stamp}_{args.era}_{args.label}"))
    os.makedirs(out_dir, exist_ok=True)

    sandbox_dir = tempfile.mkdtemp(prefix="hardwood_health_")
    print(f"[health] Sandbox: {sandbox_dir}")
    print(f"[health] Output:  {out_dir}")
    build_sandbox(sandbox_dir)

    metrics_path = os.path.join(out_dir, "metrics.json")
    log_path = os.path.join(out_dir, "sim.log")
    cmd = [
        sys.executable, "-u", os.path.join(sandbox_dir, "scripts", "health_check.py"), "--inner",
        "--seasons", str(args.seasons), "--era", args.era, "--seed", str(args.seed),
        "--difficulty", args.difficulty, "--metrics-out", metrics_path, "--label", args.label,
        "--league", args.league,
    ]
    if args.no_reload:
        cmd.append("--no-reload")

    # PYTHONHASHSEED pins string hashing (set/dict order), the last source of run-to-run drift: same seed => same league
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONHASHSEED=str(args.seed))
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as log_f:
        proc = subprocess.Popen(cmd, cwd=sandbox_dir, stdout=log_f, stderr=subprocess.STDOUT, env=env)
        last_print = 0.0
        while proc.poll() is None:
            time.sleep(5)
            if time.time() - last_print > 60:
                last_print = time.time()
                progress = _read_progress(metrics_path)
                print(f"[health] {int(time.time() - t0)}s elapsed — {progress}", flush=True)
    rc = proc.returncode
    print(f"[health] Simulation process exited with code {rc} after {time.time() - t0:.0f}s")

    if not os.path.exists(metrics_path):
        print(f"[health] No metrics produced. See {log_path}")
        return 1

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    report = render_report(metrics)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    trades_log = os.path.join(sandbox_dir, "trades_history.txt")   # the season's trade lines, next to the report
    if os.path.exists(trades_log):
        shutil.copyfile(trades_log, os.path.join(out_dir, "trades_history.txt"))
    print(report)

    if not args.keep_sandbox:
        shutil.rmtree(sandbox_dir, ignore_errors=True)
    return 0 if metrics.get("status") == "ok" else 2


def _read_progress(metrics_path: str) -> str:
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            m = json.load(f)
        return f"{len(m.get('seasons', []))}/{m.get('config', {}).get('seasons', '?')} seasons done"
    except Exception:
        return "season 1 in progress"


# =====================================================================================
# REPORT
# =====================================================================================

def _pct(n, d):
    return f"{(100.0 * n / d):.0f}%" if d else "-"


def contract_metrics(outcomes: list, signings: list, star_line: int) -> dict:
    """Stars' contracts and free-agency bidding in one season (pure: plain dicts in, dict out).

    outcomes: the extension window's {player, team, ovr, outcome}; signings: free agency's records
    {player, ovr, team, previous_team, raised, beat[{raised}]}."""
    star_outcomes = Counter(o["outcome"] for o in outcomes if o.get("ovr", 0) >= star_line)
    stars = [s for s in signings if s.get("ovr", 0) >= star_line and s.get("previous_team")]
    raised = [max([s.get("raised", 0)] + [b.get("raised", 0) for b in s.get("beat", [])]) for s in signings]
    return {
        "star_outcomes": dict(star_outcomes),
        "star_signings": {"stayed": sum(1 for s in stars if s["team"] == s["previous_team"]),
                          "moved": sum(1 for s in stars if s["team"] != s["previous_team"])},
        "bidding_wars": sum(1 for r in raised if r > 0),
        "max_raises": max(raised, default=0),
    }


def coach_change_count(before: dict, after: dict) -> int:
    """Teams whose head coach changed (any cause): team -> coach name before Black Monday vs the next season start."""
    return sum(1 for team, name in before.items() if after.get(team) != name)


def front_office_metrics(events: dict, fo) -> dict:
    """The front-office offseason of one season (pure).

    events: front_office_offseason's dict plus "teams" (the CPU-GM teams), "coach_fired" (seasons marked with a
    coaching change by Black Monday, incl. mid-season firings) and "coach_changes" (coach_change_count);
    fo: the front office after the offseason (seats, gms with skills)."""
    fired, retired, hired = events.get("fired", []), events.get("retired", []), events.get("hired", [])
    left = {}
    for e in retired:
        if e.get("team"):
            left[e["team"]] = (e["gm"], "retired")
    for e in fired:
        left[e["team"]] = (e["gm"], e["reason"])
    changes = [(h["team"], left.get(h["team"], ("-", "-"))[0], h["gm"], left.get(h["team"], ("-", "-"))[1])
               for h in hired]
    seated = [fo.gms[g] for g in fo.seats.values() if g in fo.gms]
    top = max(seated, key=lambda g: statistics.mean(g.skills.values()) if g.skills else 0, default=None)
    skill_avgs = [statistics.mean(g.skills.values()) for g in seated if g.skills]
    gm_ids = list(fo.seats.values())
    return {
        "gm_fired": len(fired), "gm_retired": len(retired), "gm_hired": len(hired),
        "historical_hired": sum(1 for h in hired if h.get("historical")),
        "coach_fired": events.get("coach_fired", 0),
        "coach_changes": events.get("coach_changes", 0),
        "seated_skill_avg": round(statistics.mean(skill_avgs), 1) if skill_avgs else None,
        "changes": changes,
        "top_gm": {"name": top.name, "average": round(statistics.mean(top.skills.values()), 1)} if top and top.skills else None,
        "empty_seats": sum(1 for t in events.get("teams", []) if t not in fo.seats),
        "double_seats": len(gm_ids) - len(set(gm_ids)),
    }


def signing_lines(season: int, signings: list, min_ovr: int = 76) -> list:
    """One line per free-agency signing of min_ovr+ (signings_history.txt), best first as signed."""
    lines = []
    for s in signings:
        if s.get("ovr", 0) < min_ovr:
            continue
        beat = ", ".join(b["team"] for b in s.get("beat", [])) or "-"
        lines.append(f"[Season {season}] {s['player']} ({s['ovr']}) {s.get('previous_team') or 'FA'} -> {s['team']}, "
                     f"{s['years']}y ${s['salary']:.1f}M · raises {s.get('raised', 0)} · beat {beat}")
    return lines


def render_report(m: dict) -> str:
    cfg = m.get("config", {})
    seasons = m.get("seasons", [])
    L = []
    L.append(f"# Hardwood Basketball Simulator Health Report — {cfg.get('label', '')}")
    L.append("")
    L.append(f"- Era: **{cfg.get('era')}** · Seeds: {cfg.get('seed')} · Difficulty: {cfg.get('difficulty')} · "
             f"Seasons requested: {cfg.get('seasons')} · completed: **{len(seasons)}**")
    L.append(f"- Status: **{m.get('status')}** · Resume from reloaded save: {not cfg.get('no_reload')}")
    if m.get("crash"):
        L.append("")
        L.append("## ❌ CRASH")
        L.append("```")
        L.append(m["crash"][-3000:])
        L.append("```")
    if not seasons:
        return "\n".join(L)

    # ---- Season table
    L.append("")
    L.append("## Per-season overview")
    L.append("")
    L.append("| S | sec | trades | max/team | champion | best W | worst W | W stdev | >tax | >2nd apron | under cap | roster min-max | retired | plan changes (deadline/new season) | log errors | reload diffs |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in seasons:
        w = s["wins"]
        pay = s["payroll"]
        L.append(
            f"| {s['season']} | {s['sim_seconds']:.0f} | {s['trades']['total']} | {s['trades']['max_per_team']} | "
            f"{s.get('champion') or '-'} | {w['max']} | {w['min']} | {w['stdev']:.1f} | {pay['over_tax']} | "
            f"{pay['over_second_apron']} | {pay['under_cap']} | {s['rosters']['min']}-{s['rosters']['max']} | "
            f"{s['retired_this_season']} | {_plan_cell(s)} | {s['log_errors']} | {len(s.get('reload_diffs', []))} |"
        )

    # ---- Trade mix
    total_types = Counter()
    total_periods = Counter()
    for s in seasons:
        total_types.update(s["trades"]["by_type"])
        total_periods.update(s["trades"]["by_period"])
    total = sum(total_types.values())
    L.append("")
    L.append(f"## Trade mix ({total} trades, {total / len(seasons):.1f}/season)")
    L.append("")
    L.append("| Type | Count | Share |")
    L.append("|---|---|---|")
    for t, c in total_types.most_common():
        L.append(f"| {t} | {c} | {_pct(c, total)} |")
    L.append("")
    L.append("By period: " + ", ".join(f"{p}: {c}" for p, c in total_periods.most_common()))
    top_share = (total_types.most_common(1)[0][1] / total) if total else 0
    L.append("")
    L.append(f"Dominant type share: **{top_share * 100:.0f}%** (target < 25%)")

    # ---- Trade rework (wishes-driven trades): the gate numbers
    rw = run_rework_metrics(m)
    L.append("")
    L.append("## Trade rework")
    L.append("")
    L.append(f"- Motive coverage (CPU trades with a wish on every CPU side): **{rw['motive_coverage'] * 100:.0f}%** (target 100%)")
    L.append(f"- Max type share: **{rw['max_type_share'] * 100:.0f}%**"
             f"{' (' + rw['max_type'] + ')' if rw['max_type'] else ''} (target <= ~30%, soft 25%)")
    tpw = rw["trades_per_team_per_window"]
    L.append(f"- Trades per team per window: max **{tpw['max']}**, mean {tpw['mean']:.2f} (over team-windows with a deal)")
    L.append(f"- Star trades per season: **{rw['star_trades_per_season']:.1f}** (target >= 2)")
    L.append(f"- Gift trades outside DISASTER GMs: **{rw['gift_trades']}** (target 0) · by DISASTER GMs: {rw['gift_trades_disaster']}")
    disc = rw["discounted_share"]
    L.append("- Discounted on purpose (average share of value the seller got back): "
             + (", ".join(f"{k} {v:.2f}" for k, v in disc.items()) or "none"))
    L.append("- Team count mix: " + ", ".join(f"{k}-team {v * 100:.0f}%" for k, v in sorted(rw["team_count_mix"].items())))
    if rw["type_mix_by_era"]:
        L.append("")
        L.append(f"Type mix by {ERA_BUCKET_SEASONS}-season bucket:")
        L.append("")
        kinds = sorted(rw["type_share"], key=lambda k: -rw["type_share"][k])
        L.append("| seasons | trades/season | " + " | ".join(kinds) + " |")
        L.append("|---|---|" + "---|" * len(kinds))
        for bucket, mix in rw["type_mix_by_era"].items():
            first, last_s = (int(x) for x in bucket.split("-"))
            in_bucket = [x for x in seasons if first <= x["season"] <= last_s]
            per = sum(x["trades"]["total"] for x in in_bucket) / len(in_bucket) if in_bucket else 0
            L.append(f"| {bucket} | {per:.1f} | " + " | ".join(f"{mix.get(k, 0) * 100:.0f}%" for k in kinds) + " |")

    # ---- Strategy stability
    flips = sum(s["strategy"]["flips_preseason_to_deadline"] for s in seasons)
    yoy = sum(s["strategy"].get("flips_vs_last_season", 0) for s in seasons)
    L.append("")
    L.append("## Team strategy")
    L.append("")
    L.append(f"- In-season flips (preseason → deadline), total: {flips} ({flips / len(seasons):.1f}/season)")
    L.append(f"- Season-to-season changes, total: {yoy}")
    last = seasons[-1]["strategy"]["preseason_distribution"]
    L.append(f"- Last season preseason distribution: {last}")

    # ---- Contracts and free agency (layer 2b)
    contracted = [s for s in seasons if s.get("contracts")]
    if contracted:
        L.append("")
        L.append("## Contracts and free agency")
        L.append("")
        L.append("| S | stars extended | refused | walked | not offered | stars re-signed in FA | stars moved in FA | "
                 "bidding wars | max raises |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for s in contracted:
            c = s["contracts"]
            o = c["star_outcomes"]
            L.append(f"| {s['season']} | {o.get('extended', 0)} | {o.get('refused', 0)} | {o.get('walks', 0)} | "
                     f"{o.get('not_offered', 0)} | {c['star_signings']['stayed']} | {c['star_signings']['moved']} | "
                     f"{c['bidding_wars']} | {c['max_raises']} |")

    # ---- Front office (layer 3: GM firings, retirements, hirings)
    staffed = [s for s in seasons if s.get("front_office")]
    if staffed:
        L.append("")
        L.append("## Front office")
        L.append("")
        L.append("| S | GMs fired | GMs retired | GMs hired | historical hired | coaches fired | coach changes | "
                 "empty seats | double seats | seated GM avg skill | top GM (skill avg) |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for s in staffed:
            f = s["front_office"]
            top = f["top_gm"]
            L.append(f"| {s['season']} | {f['gm_fired']} | {f['gm_retired']} | {f['gm_hired']} | "
                     f"{f['historical_hired']} | {f['coach_fired']} | {f.get('coach_changes', 0)} | "
                     f"{f['empty_seats']} | {f['double_seats']} | "
                     f"{f['seated_skill_avg'] if f.get('seated_skill_avg') is not None else '-'} | "
                     f"{top['name'] + ' (' + str(top['average']) + ')' if top else '-'} |")
        for s in staffed:
            for team, old, new, reason in s["front_office"]["changes"]:
                L.append(f"- [Season {s['season']}] {team}: {old} -> {new} ({reason})")

    # ---- AI GM team plans (saved, with memory; layer 1 drives nothing)
    planned = [s["plans"] for s in seasons if s.get("plans")]
    if planned:
        in_season = sum(p["in_season"] for p in planned)
        new_season = sum(p["new_season"] for p in planned)
        L.append("")
        L.append("## Team plans (AI GM)")
        L.append("")
        L.append(f"- In-season plan changes, total: {in_season} ({in_season / len(planned):.1f}/season, target < 1)")
        L.append(f"- Season-start plan changes, total: {new_season} ({new_season / len(planned):.1f}/season)")
        L.append(f"- Plans after the last season: {planned[-1]['distribution']}")

    # ---- AI GM philosophies (layer 2a: trades go through the GM)
    traited = [s["gm_traits"] for s in seasons if s.get("gm_traits")]
    if traited:
        L.append("")
        L.append("## Trades by GM philosophy (AI GM)")
        L.append("")
        L.append("| trait | GMs | trades/GM/season | picks/GM (last season) |")
        L.append("|---|---|---|---|")
        last = traited[-1]
        for trait in sorted(last["gms"], key=lambda t: (t == "ALL", t)):
            per_season = statistics.mean(m["trades_per_gm"].get(trait, 0.0) for m in traited)
            L.append(f"| {trait} | {last['gms'][trait]} | {per_season:.2f} | {last['picks_per_gm'].get(trait, 0.0):.1f} |")
        auctions = sum(m.get("auctions", 0) for m in traited)
        won = sum(m.get("auctions_won_by_vulture", 0) for m in traited)
        if auctions:
            from core.config import CONFIG
            L.append("")
            L.append(f"- Auctions won by a vulture (trade skill >= {CONFIG.FRONT_OFFICE.VULTURE_SKILL}): "
                     f"{won}/{auctions} ({100 * won / auctions:.0f}%)")

    # ---- League talent & economy trend
    L.append("")
    L.append("## Talent & economy trend")
    L.append("")
    L.append("| S | avg top-8 OVR | players 90+ | 85+ | cap | avg payroll | owner personalities |")
    L.append("|---|---|---|---|---|---|---|")
    for s in seasons:
        t = s["talent"]
        L.append(f"| {s['season']} | {t['avg_top8_ovr']:.1f} | {t['players_90']} | {t['players_85']} | "
                 f"{s['payroll']['cap']:.1f} | {s['payroll']['avg']:.1f} | {s['owner_personalities']} |")

    # ---- Sanity problems
    problems = []
    for s in seasons:
        for p in s.get("sanity", []):
            problems.append(f"S{s['season']}: {p}")
        for d in s.get("reload_diffs", []):
            problems.append(f"S{s['season']} reload: {d}")
        for e in s.get("log_error_samples", []):
            problems.append(f"S{s['season']} log error: {e}")
    L.append("")
    L.append(f"## Sanity / reload / error findings ({len(problems)})")
    L.append("")
    if problems:
        for p in problems[:120]:
            L.append(f"- {p}")
        if len(problems) > 120:
            L.append(f"- ... {len(problems) - 120} more (see metrics.json)")
    else:
        L.append("None 🎉")

    # ---- Champions & HoF
    champs = Counter(s.get("champion") for s in seasons if s.get("champion"))
    L.append("")
    L.append("## History")
    L.append("")
    L.append(f"- Champions: {dict(champs)}")
    L.append(f"- Hall of Fame size at end: {seasons[-1].get('hof_size')}")
    L.append(f"- Total sim time: {sum(s['sim_seconds'] for s in seasons):.0f}s "
             f"({statistics.mean(s['sim_seconds'] for s in seasons):.0f}s/season avg)")
    return "\n".join(L) + "\n"


def run_rework_metrics(m: dict) -> dict:
    """trade_rework_metrics over every season of a metrics.json (older runs without trade lists give zeros)."""
    trades, windows = [], []
    for s in m.get("seasons", []):
        trades.extend(s["trades"].get("list", []))
        windows.extend(s["trades"].get("windows", []))
        windows.append({"season": s["season"], "period": "season"})
    return trade_rework_metrics(trades, windows)


def _plan_cell(season: dict) -> str:
    plans = season.get("plans")
    return f"{plans['in_season']}/{plans['new_season']}" if plans else "-"


def compare_runs(path_a: str, path_b: str):
    with open(path_a, encoding="utf-8") as f:
        a = json.load(f)
    with open(path_b, encoding="utf-8") as f:
        b = json.load(f)

    def summary(m):
        seasons = m.get("seasons", [])
        types = Counter()
        for s in seasons:
            types.update(s["trades"]["by_type"])
        n = max(1, len(seasons))
        total = sum(types.values())
        rw = run_rework_metrics(m)
        return {
            "seasons": len(seasons),
            "status": m.get("status"),
            "trades/season": round(total / n, 1),
            "dominant type share %": round(100 * types.most_common(1)[0][1] / total, 1) if total else 0,
            "pick_trade_up %": round(100 * types.get("pick_trade_up", 0) / total, 1) if total else 0,
            "positional_swap": types.get("positional_swap", 0),
            "motive coverage %": round(100 * rw["motive_coverage"], 1),
            "max type share %": round(100 * rw["max_type_share"], 1),
            "max trades/team/window": rw["trades_per_team_per_window"]["max"],
            "mean trades/team/window": round(rw["trades_per_team_per_window"]["mean"], 2),
            "star trades/season": round(rw["star_trades_per_season"], 1),
            "gift trades (non-DISASTER)": rw["gift_trades"],
            "gift trades (DISASTER)": rw["gift_trades_disaster"],
            "trade_demand share back": round(rw["discounted_share"].get("trade_demand", 0), 2),
            "tax_dump share back": round(rw["discounted_share"].get("tax_dump", 0), 2),
            "3/4-team share %": round(100 * sum(v for k, v in rw["team_count_mix"].items() if k > 2), 1),
            "in-season strategy flips/season": round(sum(s["strategy"]["flips_preseason_to_deadline"] for s in seasons) / n, 1),
            "avg W stdev": round(statistics.mean(s["wins"]["stdev"] for s in seasons), 2) if seasons else 0,
            "reload diffs": sum(len(s.get("reload_diffs", [])) for s in seasons),
            "log errors": sum(s["log_errors"] for s in seasons),
            "sec/season": round(statistics.mean(s["sim_seconds"] for s in seasons), 1) if seasons else 0,
        }

    sa, sb = summary(a), summary(b)
    print(f"| metric | {a['config'].get('label')} | {b['config'].get('label')} |")
    print("|---|---|---|")
    for k in sa:
        print(f"| {k} | {sa[k]} | {sb[k]} |")


# =====================================================================================
# INNER PROCESS: runs inside the sandbox (cwd = sandbox)
# =====================================================================================

class _ErrorCounter:
    """logging.Handler that counts ERROR+ records on the 'main_sim' logger."""

    def __init__(self):
        import logging

        class H(logging.Handler):
            def __init__(self, outer):
                super().__init__(level=logging.ERROR)
                self.outer = outer

            def emit(self, record):
                self.outer.count += 1
                if len(self.outer.samples) < 8:
                    self.outer.samples.append(record.getMessage()[:300])

        self.count = 0
        self.samples = []
        self.handler = H(self)

    def reset(self):
        self.count = 0
        self.samples = []


def prepare_league(league_id: str, save_name: str, root: str = None):
    """Starts the run from a league file the way the server's init_simulation starts a 2002 career: builds the
    league's DB through the catalogue (and makes it active), copies it to <root>/data/nba_sim.db, installs its
    franchise registry and gives the save its own copy of the league's draft classes (none = generated).
    `root` is the game root (default: the working directory, i.e. the sandbox). Returns (league_meta,
    registry); raises LeagueError for an unknown or invalid league."""
    from core import save_manager
    from core.league import catalog
    from core.league.draft_source import copy_league_draft_classes
    from core.league.registry import FranchiseRegistry, set_active_registry
    from core.league.schema import LeagueError
    root = os.path.abspath(root or os.getcwd())
    result = catalog.build_and_activate(league_id, root)
    if not result["ok"]:
        raise LeagueError(result["errors"])
    shutil.copyfile(catalog.ensure_active_league_db(root), os.path.join(root, "data", "nba_sim.db"))
    entry = catalog.active_league(root)
    registry = FranchiseRegistry.from_league(catalog.active_league_data(root))
    set_active_registry(registry)
    copy_league_draft_classes(catalog.active_draft_dir(root), save_manager.get_save_path(save_name))
    return {"id": entry["id"], "name": entry["name"], "era": entry["era"]}, registry


def run_inner(args):
    import random
    sys.path.insert(0, os.getcwd())
    random.seed(args.seed)

    metrics = {
        "config": {"seasons": args.seasons, "era": args.era, "seed": args.seed, "difficulty": args.difficulty,
                   "label": args.label, "no_reload": args.no_reload,
                   "league": args.league if args.era == "2002" else None},
        "status": "running",
        "seasons": [],
    }

    def flush():
        tmp = args.metrics_out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=1, default=str)
        os.replace(tmp, args.metrics_out)

    try:
        # The sandbox's active DB BEFORE importing the game: the 2002 league built from its file (with its
        # registry and draft classes, as a new career gets them), or the modern template.
        league_meta = league_registry = None
        if args.era == "2002":
            league_meta, league_registry = prepare_league(args.league, SAVE_NAME)
            print(f"[health-inner] League: {league_meta['name']} ({league_meta['id']})", flush=True)
        else:
            template = os.path.join("data", ERA_TEMPLATES[args.era])
            shutil.copyfile(template, os.path.join("data", "nba_sim.db"))

        import logging
        import main as sim
        import core.models as models
        from core import save_manager
        from trades.trade_finder import TradeFinder
        from offseason.draft import Draft
        from offseason.free_agency import FreeAgency

        # Quieter console: the game logs INFO to stdout; keep file log, drop console noise.
        mlog = logging.getLogger('main_sim')
        for h in list(mlog.handlers):
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                mlog.removeHandler(h)
        errors = _ErrorCounter()
        mlog.addHandler(errors.handler)

        state = {"period": "other", "trades": [], "deadline_strategies": None}
        _instrument(sim, TradeFinder, Draft, FreeAgency, state)
        _instrument_contracts(FreeAgency, state)
        _instrument_front_office(sim, state)
        signings_path = os.path.join(os.path.dirname(args.metrics_out), "signings_history.txt")
        open(signings_path, "w", encoding="utf-8").close()

        save_manager.set_active_save_name(SAVE_NAME)
        torneo = sim.setup_simulation(league_settings={"trade_difficulty": args.difficulty},
                                      league_meta=league_meta, franchise_registry=league_registry)
        torneo.era_name = "2002 Era" if args.era == "2002" else "Modern Era"
        torneo.squadra_giocatore = None
        torneo.is_spectator = True
        torneo.active_save_name = SAVE_NAME

        prev_strategies = None
        retired_before = 0
        for season_idx in range(args.seasons):
            season_num = torneo.season_number
            print(f"\n[health-inner] ===== SEASON {season_num} ({season_idx + 1}/{args.seasons}) =====", flush=True)
            state["trades"] = []
            state["windows"] = []
            state["season"] = season_num
            state["deadline_strategies"] = None
            state["extension_outcomes"] = []
            state["fa_signings"] = []
            state["front_office_events"] = []
            errors.reset()
            pre_strategies = _strategies(TradeFinder, torneo)
            plan_changes_before = _plan_change_counts(torneo)
            retired_before = len(getattr(torneo, "giocatori_ritirati", []))

            t0 = time.time()
            # Snapshot wins/champion BEFORE the cycle resets records: capture via playoff hook.
            cycle_snapshot = {}
            _run_cycle_with_snapshot(sim, torneo, cycle_snapshot)
            sim_seconds = time.time() - t0

            season_metrics = _collect_season_metrics(
                torneo, season_num, sim_seconds, state, pre_strategies, prev_strategies,
                cycle_snapshot, retired_before, errors)
            season_metrics["plans"] = _plan_metrics(torneo, plan_changes_before)
            season_metrics["gm_traits"] = _trait_metrics(torneo, state["trades"])
            from core.front_office.era_lines import era_lines_for
            season_metrics["contracts"] = contract_metrics(state["extension_outcomes"], state["fa_signings"],
                                                           era_lines_for(torneo).star)
            fo_events = {"retired": [], "fired": [], "hired": [], "teams": [], "coach_fired": 0,
                         "coach_changes": coach_change_count(cycle_snapshot.get("coaches", {}), _coach_names(torneo))}
            for ev in state["front_office_events"]:
                for key in ("retired", "fired", "hired", "teams"):
                    fo_events[key].extend(ev[key])
                fo_events["coach_fired"] += ev["coach_fired"]
            season_metrics["front_office"] = front_office_metrics(fo_events, torneo.front_office)
            with open(signings_path, "a", encoding="utf-8") as f:
                for line in signing_lines(season_num, state["fa_signings"]):
                    f.write(line + "\n")
            prev_strategies = pre_strategies

            # ---- Save -> reload round trip
            reloaded, diffs = _round_trip(sim, models, save_manager, torneo)
            season_metrics["reload_diffs"] = diffs
            if not args.no_reload and reloaded is not None:
                torneo = reloaded

            season_metrics["hof_size"] = _hof_size(save_manager)
            metrics["seasons"].append(season_metrics)
            flush()

        metrics["status"] = "ok"
    except Exception:
        metrics["status"] = "crash"
        metrics["crash"] = traceback.format_exc()
        print(metrics["crash"], flush=True)
    flush()
    return 0 if metrics["status"] == "ok" else 2


def _instrument(sim, TradeFinder, Draft, FreeAgency, state):
    """Wrap trade execution and trade windows to record what happens."""
    # TradeFinder.execute_deal is the one door every executed deal goes through (execute_trade / _3_ / _4_team,
    # engines' close_deal and the server's user routes all end here), so each deal is counted exactly once.
    original_execute = TradeFinder.execute_deal

    def execute_deal(self, deal, motive=None, pick_protections=None):
        ok = original_execute(self, deal, motive, pick_protections)
        if ok:
            try:
                state["trades"].append(_trade_record(self, deal, motive, state))
            except Exception:
                traceback.print_exc()
        return ok

    TradeFinder.execute_deal = execute_deal

    def wrap_period(fn, name, before=None):
        def wrapper(self, *args, **kwargs):
            prev = state["period"]
            state["period"] = name
            state.setdefault("windows", []).append({"season": state.get("season"), "period": name})
            if before:
                before(self)
            try:
                return fn(self, *args, **kwargs)
            finally:
                state["period"] = prev
        return wrapper

    def snap_deadline(torneo):
        state["deadline_strategies"] = _strategies(TradeFinder, torneo)

    sim.Tournament.trade_period_midseason = wrap_period(sim.Tournament.trade_period_midseason, "deadline", snap_deadline)
    sim.Tournament.trade_period_predraft = wrap_period(sim.Tournament.trade_period_predraft, "predraft")
    Draft.esegui_o_continua_draft = wrap_period(Draft.esegui_o_continua_draft, "draft")
    FreeAgency.esegui_free_agency = wrap_period(FreeAgency.esegui_free_agency, "free_agency")


def _instrument_contracts(FreeAgency, state):
    """Keep the extension window's outcomes and the free agency signings of the season (the tournament's own logs are
    reset before the season metrics are read)."""
    from offseason.contract_extensions import ContractExtensions
    original_extensions = ContractExtensions.process_extensions
    original_fa = FreeAgency.esegui_free_agency

    def process_extensions(self, *a, **kw):
        try:
            return original_extensions(self, *a, **kw)
        finally:
            state.setdefault("extension_outcomes", []).extend(getattr(self, "outcomes", []))

    def esegui_free_agency(self, *a, **kw):
        try:
            return original_fa(self, *a, **kw)
        finally:
            state.setdefault("fa_signings", []).extend(getattr(self, "signings", []))

    ContractExtensions.process_extensions = process_extensions
    FreeAgency.esegui_free_agency = esegui_free_agency


def _instrument_front_office(sim, state):
    """Keep what the front-office offseason did (main.py calls it by name) and how many seasons were marked with a
    coaching change just before it (Black Monday and the mid-season firings mark the season row of each team)."""
    original = sim.front_office_offseason

    def front_office_offseason(torneo, *a, **kw):
        fo = getattr(torneo, "front_office", None)
        coaches = sum(1 for rows in (fo.records.values() if fo else []) if rows and rows[-1].get("coach_fired"))
        events = original(torneo, *a, **kw)
        state.setdefault("front_office_events", []).append(
            {**events, "coach_fired": coaches,
             "teams": [t.nome for t in torneo.squadre if t is not getattr(torneo, "squadra_giocatore", None)]})
        return events

    sim.front_office_offseason = front_office_offseason


def _trade_record(finder, deal, motive, state) -> dict:
    """One executed deal as a plain dict: type (motive's code, legacy classification as fallback), who, how big, and
    per side the GM's own value numbers (debug only: they never reach the game UI)."""
    from core.models import Giocatore
    sides = []
    for s in (motive.sides if motive is not None else []):
        sides.append({"team": s.team, "plan": s.plan, "wish_kind": s.wish_kind, "trade_skill": s.trade_skill,
                      "value_given": s.value_given, "value_received": s.value_received})
    cpu_sides = [s for s in sides if s["plan"] != "USER"]
    reason = (deal.reason or "")
    star_line = finder.era().star
    return {
        "season": state.get("season"), "period": state["period"], "teams": deal.team_names(),
        "type": record_type(motive, reason),
        "team_count": getattr(motive, "team_count", None) or len(deal.teams),
        "has_motive": motive is not None and bool(cpu_sides) and all(s["wish_kind"] for s in cpu_sides),
        "star": any(isinstance(a, Giocatore) and a.ovr >= star_line for _s, _d, a in deal.moves),
        "sides": sides, "reason": reason[:240],
    }


def _strategies(TradeFinder, torneo) -> dict:
    tf = TradeFinder(torneo, torneo.squadre, None)
    return {t.nome: tf.get_team_strategy(t) for t in torneo.squadre}


def _coach_names(torneo) -> dict:
    return {t.nome: getattr(getattr(t, "coach", None), "nome", None) for t in torneo.squadre}


def _run_cycle_with_snapshot(sim, torneo, snap):
    """run_full_season_cycle resets records/champion at the end; capture them right after playoffs."""
    original_progression = torneo.start_offseason_progression

    def hooked(*a, **kw):
        snap["wins"] = {t.nome: t.vittorie for t in torneo.squadre}
        snap["champion"] = torneo.campione.nome if getattr(torneo, "campione", None) else None
        snap["payroll_end_season"] = {t.nome: round(t.payroll, 1) for t in torneo.squadre}
        snap["coaches"] = _coach_names(torneo)  # before Black Monday
        return original_progression(*a, **kw)

    torneo.start_offseason_progression = hooked
    try:
        sim.run_full_season_cycle(torneo)
    finally:
        try:
            del torneo.start_offseason_progression
        except AttributeError:
            pass


def _collect_season_metrics(torneo, season_num, sim_seconds, state, pre_strat, prev_strat, snap, retired_before, errors):
    teams = torneo.squadre
    trades = state["trades"]
    per_team = Counter()
    for tr in trades:
        for name in set(tr["teams"]):
            per_team[name] += 1

    wins = list((snap.get("wins") or {}).values()) or [0]
    cap = float(getattr(torneo, "salary_cap", 0) or 0)
    tax = float(getattr(torneo, "luxury_tax_threshold", 0) or 0)
    apron2 = float(getattr(torneo, "second_apron", 0) or getattr(torneo, "second_apron_threshold", 0) or 0)
    payrolls = [t.payroll for t in teams]

    all_players = [p for t in teams for p in t.roster]
    top8 = []
    for t in teams:
        best = sorted((p.ovr for p in t.roster), reverse=True)[:8]
        if best:
            top8.append(sum(best) / len(best))

    deadline = state.get("deadline_strategies") or {}
    flips_in_season = sum(1 for n, s in pre_strat.items() if deadline.get(n) and deadline[n] != s)
    flips_yoy = sum(1 for n, s in pre_strat.items() if prev_strat and prev_strat.get(n) and prev_strat[n] != s)

    return {
        "season": season_num,
        "sim_seconds": sim_seconds,
        "champion": snap.get("champion"),
        "wins": {
            "max": max(wins), "min": min(wins),
            "stdev": statistics.pstdev(wins) if len(wins) > 1 else 0.0,
            "teams_60_plus": sum(1 for w in wins if w >= 60),
            "teams_under_20": sum(1 for w in wins if w < 20),
        },
        "trades": {
            "total": len(trades),
            "by_type": dict(Counter(tr["type"] for tr in trades)),
            "by_period": dict(Counter(tr["period"] for tr in trades)),
            "max_per_team": max(per_team.values()) if per_team else 0,
            "teams_with_3_plus": sum(1 for c in per_team.values() if c >= 3),
            "list": trades,
            "windows": list(state.get("windows", [])),
        },
        "strategy": {
            "preseason_distribution": dict(Counter(pre_strat.values())),
            "deadline_distribution": dict(Counter(deadline.values())),
            "flips_preseason_to_deadline": flips_in_season,
            "flips_vs_last_season": flips_yoy,
        },
        "payroll": {
            "cap": cap, "avg": statistics.mean(payrolls) if payrolls else 0,
            "max": max(payrolls) if payrolls else 0, "min": min(payrolls) if payrolls else 0,
            "over_tax": sum(1 for p in payrolls if tax and p > tax),
            "over_second_apron": sum(1 for p in payrolls if apron2 and p > apron2),
            "under_cap": sum(1 for p in payrolls if cap and p <= cap),
        },
        "rosters": {"min": min(len(t.roster) for t in teams), "max": max(len(t.roster) for t in teams)},
        "talent": {
            "avg_top8_ovr": statistics.mean(top8) if top8 else 0,
            "players_90": sum(1 for p in all_players if p.ovr >= 90),
            "players_85": sum(1 for p in all_players if p.ovr >= 85),
        },
        "owner_personalities": dict(Counter(getattr(t, "personalita_proprietario", None) for t in teams)),
        "retired_this_season": len(getattr(torneo, "giocatori_ritirati", [])) - retired_before,
        "log_errors": errors.count,
        "log_error_samples": list(errors.samples),
        "sanity": _sanity_checks(torneo),
    }


def _sanity_checks(torneo) -> list:
    from core.config import CONFIG
    max_roster = CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT - 1   # cut-down day target
    min_roster = 13                                       # NBA legal minimum
    problems = []
    team_names = {t.nome for t in torneo.squadre}
    seen = {}
    for t in torneo.squadre:
        if len(t.roster) < min_roster:
            problems.append(f"{t.nome} roster has only {len(t.roster)} players (< {min_roster})")
        if len(t.roster) > max_roster:
            problems.append(f"{t.nome} roster has {len(t.roster)} players (> {max_roster})")
        if not getattr(t, "coach", None):
            problems.append(f"{t.nome} has no head coach")
        for p in t.roster:
            key = id(p)  # names are not unique (two players can share a name)
            if key in seen:
                problems.append(f"player object {p.nome} on two teams: {seen[key]} and {t.nome}")
            seen[key] = t.nome
            if not getattr(p, "contract", None):
                problems.append(f"{p.nome} ({t.nome}) has no contract")
            elif p.contract.salario_annuale <= 0:
                problems.append(f"{p.nome} ({t.nome}) has salary {p.contract.salario_annuale}")
            if getattr(p, "squadra", None) is not t:
                problems.append(f"{p.nome} roster/team back-reference mismatch ({t.nome})")
    ownership = getattr(torneo, "pick_ownership", {}) or {}
    picks_per_team = Counter()
    for year, picks in ownership.items():
        for pk, owner in (picks or {}).items():
            if owner not in team_names:
                problems.append(f"pick {year}:{pk} owned by unknown team '{owner}'")
            picks_per_team[owner] += 1
    if picks_per_team:
        hoarder, n = picks_per_team.most_common(1)[0]
        if n > 18:
            problems.append(f"{hoarder} owns {n} picks (hoarding)")
    return problems


def _fingerprint(torneo) -> dict:
    fp = {
        "season_number": torneo.season_number,
        "starting_year": getattr(torneo, "starting_year", None),
        "salary_cap": round(float(getattr(torneo, "salary_cap", 0) or 0), 2),
        "pick_ownership": {str(y): dict(sorted((v or {}).items())) for y, v in (getattr(torneo, "pick_ownership", {}) or {}).items()},
        "pick_protections": {str(y): dict(sorted((v or {}).items())) for y, v in (getattr(torneo, "pick_protections", {}) or {}).items()},
        "free_agents": sorted(p.nome for p in getattr(torneo, "free_agents_pool", []) or []),
        "teams": {},
    }
    for t in torneo.squadre:
        coach = getattr(t, "coach", None) or getattr(t, "allenatore", None)
        fp["teams"][t.nome] = {
            "owner": getattr(t, "personalita_proprietario", None),
            "coach": getattr(coach, "nome", None),
            "payroll": round(t.payroll, 2),
            "roster": sorted(
                (p.nome, p.ovr, p.eta, p.potenziale, p.ruolo,
                 round(p.contract.salario_annuale, 2) if p.contract else None,
                 p.contract.anni_rimanenti if p.contract else None)
                for p in t.roster),
        }
    fo = getattr(torneo, "front_office", None)
    if fo is not None:
        fp["front_office"] = {"seats": dict(sorted(fo.seats.items())),
                              "plans": {team: plan.state for team, plan in sorted(fo.plans.items())}}
    return fp


def _plan_change_counts(torneo) -> dict:
    """Plan changes recorded so far, by checkpoint ("deadline", "new_season"); a team's first plan is not a change."""
    fo = getattr(torneo, "front_office", None)
    if fo is None:
        return {}
    return dict(Counter(h.get("checkpoint") for plan in fo.plans.values() for h in plan.history if h.get("from")))


def _plan_metrics(torneo, before: dict) -> dict:
    """Plan changes made during one season cycle (deadline = in-season; new_season = at the next season start)."""
    after = _plan_change_counts(torneo)
    fo = getattr(torneo, "front_office", None)
    return {
        "in_season": after.get("deadline", 0) - before.get("deadline", 0),
        "new_season": after.get("new_season", 0) - before.get("new_season", 0),
        "distribution": dict(Counter(plan.state for plan in fo.plans.values())) if fo is not None else {},
    }


def _trait_metrics(torneo, trades: list) -> dict:
    """AI GM layer 2a: trades and picks held per seated GM, by philosophy trait ("ALL" = every seated GM)."""
    fo = getattr(torneo, "front_office", None)
    if fo is None:
        return {}
    from core.front_office.trade_brain import is_vulture
    traits_by_team = {team: list(gm.traits) + (["VULTURE"] if is_vulture(gm) else []) + ["ALL"]
                      for team in fo.seats for gm in [fo.seated_gm(team)] if gm is not None}
    gms = Counter(t for traits in traits_by_team.values() for t in traits)
    deals = Counter(t for tr in trades for name in set(tr["teams"]) for t in traits_by_team.get(name, []))
    owned = Counter(owner for year in (getattr(torneo, "pick_ownership", None) or {}).values()
                    for owner in year.values())
    picks = Counter()
    for team, traits in traits_by_team.items():
        for t in traits:
            picks[t] += owned.get(team, 0)
    # Auctions (seller first, winning bidder second in the trade's team list) and how many a vulture won.
    auctions = [tr for tr in trades if tr.get("type") in AUCTION_TYPES and len(tr["teams"]) >= 2]
    return {
        "auctions": len(auctions),
        "auctions_won_by_vulture": sum(1 for tr in auctions if "VULTURE" in traits_by_team.get(tr["teams"][1], [])),
        "trades_per_gm": {t: round(deals[t] / n, 2) for t, n in gms.items()},
        "picks_per_gm": {t: round(picks[t] / n, 2) for t, n in gms.items()},
        "gms": dict(gms),
    }


def _diff(a, b, path="", out=None, limit=40):
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a:
                out.append(f"{path}/{k}: only after reload")
            elif k not in b:
                out.append(f"{path}/{k}: lost on reload")
            else:
                _diff(a[k], b[k], f"{path}/{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list) and a != b:
        sa, sb = set(map(repr, a)), set(map(repr, b))
        only_a, only_b = sorted(sa - sb)[:2], sorted(sb - sa)[:2]
        out.append(f"{path}: list differs (before-only {only_a}, after-only {only_b})")
    elif a != b:
        out.append(f"{path}: {a!r} -> {b!r}")
    return out


def _round_trip(sim, models, save_manager, torneo):
    """Save, reload into a fresh Tournament (same path as the server), diff fingerprints."""
    try:
        before = _fingerprint(torneo)
        save_manager.save_game(SAVE_NAME, torneo)
        loaded = save_manager.load_game(SAVE_NAME)
        # As the server's load: the save's registry and league_meta go in before setup reads a draft class.
        from core.league.registry import set_active_registry
        state_data = loaded.get("state_data", {})
        registry = save_manager.saved_league_registry(state_data)
        set_active_registry(registry)
        fresh = sim.setup_simulation(league_meta=(state_data.get("league") or {}).get("meta") or {},
                                     franchise_registry=registry)
        fresh.era_name = getattr(torneo, "era_name", None)
        save_manager.restore_tournament_state(fresh, loaded.get("state_data", {}))
        models.ACTIVE_TOURNAMENT = fresh
        sim.ACTIVE_TOURNAMENT = fresh
        fresh.squadra_giocatore = None
        fresh.is_spectator = True
        fresh.active_save_name = SAVE_NAME
        for s in fresh.squadre:
            s.designa_intoccabili(fresh)
        after = _fingerprint(fresh)
        return fresh, _diff(before, after)
    except Exception:
        return None, ["ROUND-TRIP CRASH: " + traceback.format_exc()[-1500:]]


def _hof_size(save_manager):
    try:
        path = save_manager.get_historical_file_path("hall_of_fame.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return len(data) if isinstance(data, (list, dict)) else None
    except Exception:
        return None


# =====================================================================================

def build_parser() -> argparse.ArgumentParser:
    from core.league.catalog import BUILTIN_LEAGUE_ID
    ap = argparse.ArgumentParser(description="Hardwood Basketball Simulator headless multi-season health check")
    ap.add_argument("--seasons", type=int, default=10)
    ap.add_argument("--era", choices=ERAS, default="2002")
    ap.add_argument("--league", default=BUILTIN_LEAGUE_ID,
                    help=f"2002 era: the league to start from, by catalogue id (default: the built-in "
                         f"fictional league '{BUILTIN_LEAGUE_ID}'; 'Real Names 2002' = the mod in mods/). "
                         f"Built inside the sandbox; ignored for --era modern")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--difficulty", choices=["easy", "realistic", "hardcore"], default="realistic")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", help="output directory")
    ap.add_argument("--no-reload", action="store_true",
                    help="keep simulating the original in-memory league instead of the reloaded save")
    ap.add_argument("--keep-sandbox", action="store_true")
    ap.add_argument("--compare", nargs=2, metavar=("METRICS_A", "METRICS_B"))
    ap.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--metrics-out", help=argparse.SUPPRESS)
    return ap


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = build_parser().parse_args()

    if args.compare:
        compare_runs(*args.compare)
        return 0
    if args.inner:
        return run_inner(args)
    return run_outer(args)


if __name__ == "__main__":
    sys.exit(main())
