"""End of Season Hub phase views: the payload each phase page renders.

Pure functions over plain dicts and lists (no Flask, no engine objects); server.py gathers the inputs. Saved data
keeps Italian keys and labels (stagione, premi, "Campione…"); they are read only here, the pages get English.
"""
from core.history_view import CHAMPION_LABEL, FINALS_LABEL

# --- Season recap -------------------------------------------------------------------------------------------------

ROUNDS = (("play_in", "Play-In"), ("qf", "Round 1"), ("sf", "Second round"), ("cf", "Conference finals"))
OUT_IN = {"Play-In": "Out in the play-in", "Round 1": "Out in the first round",
          "Second round": "Out in the second round", "Conference finals": "Out in the conference finals",
          "Finals": "Lost in the Finals"}
TROPHIES = (("mvp", "MVP", "mvp"), ("dpoy", "Defensive Player", "dpoy"), ("roy", "Rookie of the Year", "roy"),
            ("sixth_man", "Sixth Man", "sesto_uomo"), ("mip", "Most Improved", "mip"),
            ("all_star_mvp", "All-Star MVP", "all_star_mvp"))
HONOUR_TEAMS = (("all_league_1st", "All-League 1st", "all_nba_1st"), ("all_league_2nd", "All-League 2nd", "all_nba_2nd"),
                ("all_league_3rd", "All-League 3rd", "all_nba_3rd"), ("all_defense", "All-Defense", "all_defensive"),
                ("all_rookie", "All-Rookie", "all_rookie"))
CONFERENCE_FINALS_LABEL = "Finali Conference"
SAVED_ROUND_VERDICT = ((CONFERENCE_FINALS_LABEL, "Out in the conference finals"), (FINALS_LABEL, "Lost in the Finals"),
                       (CHAMPION_LABEL, "Champions"), ("Playoff", "Out in the playoffs"),
                       ("Play-In", "Out in the play-in"))


def _winner(value):
    """A saved award winner, or None for "N/A" / empty."""
    if not value or not isinstance(value, str) or value.strip().upper() == "N/A":
        return None
    return value


def _series_list(bracket):
    """(round label, series) in playing order, skipping empty play-in slots."""
    out = []
    for key, label in ROUNDS:
        for conf in ("east", "west"):
            for s in ((bracket or {}).get(conf) or {}).get(key) or []:
                if isinstance(s, dict) and s.get("s1_nome"):
                    out.append((label, s))
    for s in (bracket or {}).get("finals") or []:
        if isinstance(s, dict) and s.get("s1_nome"):
            out.append(("Finals", s))
    return out


def _run(bracket, team):
    rows = []
    for label, s in _series_list(bracket):
        if team not in (s["s1_nome"], s["s2_nome"]):
            continue
        mine, other = ("s1", "s2") if s["s1_nome"] == team else ("s2", "s1")
        seed = s.get(f"{other}_seed")
        rows.append({"round": label, "opponent": s[f"{other}_nome"], "opponent_seed": seed if seed not in ("", None) else None,
                     "won": s.get(f"{mine}_vittorie", 0), "lost": s.get(f"{other}_vittorie", 0),
                     "result": "won" if s.get("winner_nome") == team else "lost"})
    return rows


def _verdict_from_run(rows):
    if not rows:
        return None
    last = rows[-1]
    if last["result"] == "won":
        return "Champions" if last["round"] == "Finals" else None
    return OUT_IN[last["round"]]


def _verdict_from_saved(playoff_round):
    text = str(playoff_round or "")
    for prefix, verdict in SAVED_ROUND_VERDICT:
        if text.startswith(prefix):
            return verdict
    return "Missed the playoffs"


def _lost_finals(playoff_round):
    """The Finals loser's saved label ("Finali NBA"), not the conference finals ("Finali Conference")."""
    text = str(playoff_round or "")
    return text.startswith(FINALS_LABEL) and not text.startswith(CONFERENCE_FINALS_LABEL)


def _rank(rows, key, reverse):
    ordered = sorted((r for r in rows if r.get(key) is not None), key=lambda r: r[key], reverse=reverse)
    return {r["team"]: i + 1 for i, r in enumerate(ordered)}


def _player_honours(premi, roster_names):
    honours = {}
    for _key, label, saved in HONOUR_TEAMS:
        for name in premi.get(saved) or []:
            if name in roster_names:
                honours.setdefault(name, []).append(label)
    stars = premi.get("all_star_starters") or {}, premi.get("all_star_reserves") or {}
    for group in stars:
        for names in group.values():
            for name in names or []:
                if name in roster_names and "All-Star" not in honours.get(name, []):
                    honours.setdefault(name, []).append("All-Star")
    for _key, label, saved in TROPHIES:
        if _winner(premi.get(saved)) in roster_names:
            honours.setdefault(premi[saved], []).append(label)
    return [{"player": p, "honours": h} for p, h in honours.items()]


def _leaders(lines):
    out = {}
    for key, stat in (("points", "ppg"), ("rebounds", "rpg"), ("assists", "apg")):
        best = max((l for l in lines or [] if l.get(stat) is not None), key=lambda l: l[stat], default=None)
        out[key] = {"player": best["name"], "value": best[stat]} if best else None
    return out


def season_recap_view(entry, bracket, user_team, roster_lines, player_teams):
    """Your season (record, ratings, playoff run, honours, leaders) and the league's (champion, trophies, teams)."""
    entry = entry or {}
    premi = entry.get("premi") or {}
    standings = {s["team"]: s for s in entry.get("standings") or [] if s.get("team")}
    stats = entry.get("team_stats") or []
    champion_name = entry.get("campione")
    champion = standings.get(champion_name) or {}
    runner_up = next((s["team"] for s in standings.values() if _lost_finals(s.get("playoff_round"))), None)
    roster_names = {l["name"] for l in roster_lines or []}

    yours = None
    mine = standings.get(user_team) if user_team else None
    if mine:
        run = _run(bracket, user_team) if bracket else []
        verdict = (_verdict_from_run(run) if run else None) or (
            "Missed the playoffs" if bracket else _verdict_from_saved(mine.get("playoff_round")))
        if mine.get("league_rank") == 1 and verdict != "Champions":
            verdict = "Best record, " + verdict[0].lower() + verdict[1:]
        beaten_by = next((r["opponent"] for r in reversed(run) if r["result"] == "lost"), None)
        # Ratings of 0 mean the season's points were not kept (e.g. counters lost on a reload): unknown, not zero.
        stats = [s for s in stats if s.get("off_rating")]
        own_stats = next((s for s in stats if s.get("team") == user_team), {})
        yours = {
            "team": user_team, "wins": mine.get("wins", 0), "losses": mine.get("losses", 0),
            "seed": mine.get("conf_seed"), "conference": mine.get("conference"), "league_rank": mine.get("league_rank"),
            "off_rating": own_stats.get("off_rating"), "off_rank": _rank(stats, "off_rating", True).get(user_team),
            "def_rating": own_stats.get("def_rating"), "def_rank": _rank(stats, "def_rating", False).get(user_team),
            "margin": own_stats.get("diff"), "verdict": verdict, "run": run, "beaten_by": beaten_by,
            "beaten_by_result": (_verdict_from_run(_run(bracket, beaten_by)) or "Out in the playoffs") if beaten_by else None,
            "honours": _player_honours(premi, roster_names),
            "leaders": _leaders(roster_lines),
        }

    def trophy(key, label, saved):
        name = _winner(premi.get(saved))
        return {"key": key, "label": label, "winner": name, "team": (player_teams or {}).get(name) if name else None}

    return {
        "season": entry.get("stagione"),
        "year": entry.get("anno"),
        "yours": yours,
        "league": {
            "champion": {"team": champion_name, "wins": champion.get("wins"), "losses": champion.get("losses"),
                         "seed": champion.get("conf_seed"), "conference": champion.get("conference")},
            "runner_up": runner_up,
            "finals_mvp": _winner(entry.get("mvp_finali")),
            "trophies": [trophy(*t) for t in TROPHIES],
            "all_star_extra": {"three_point": _winner(premi.get("three_point_contest")),
                               "dunk": _winner(premi.get("dunk_contest"))},
            "honour_teams": [{"key": key, "label": label,
                              "players": [{"name": n, "yours": n in roster_names} for n in premi.get(saved) or []]}
                             for key, label, saved in HONOUR_TEAMS],
        },
    }


# --- Contract options ---------------------------------------------------------------------------------------------

def option_take(salary, market, mpg):
    """One line on a team option: salary against what the open market would pay him, and his role."""
    role = "starter" if mpg >= 28 else "rotation player" if mpg >= 15 else "backup"
    gap = round(salary - market, 1)
    if gap >= 1.0:
        return f"Solid {role}, but ${gap:.1f}M more than he'd get elsewhere."
    if gap <= -1.0:
        return "Cheap for what he gives."
    return "Paid about what he's worth."


def options_money(guaranteed, lines):
    """Inputs of the next-season ledger: guaranteed payroll, the CBA lines, and which signing exception a payroll
    leaves (the page takes the last one whose `above` is below its payroll). No cap era: no lines, no exceptions."""
    cap, tax = lines.get("salary_cap"), lines.get("luxury_tax")
    apron1, apron2 = lines.get("first_apron"), lines.get("second_apron")
    exceptions = []
    if cap is not None:
        exceptions = [{"above": None, "label": "Cap space"}, {"above": cap, "label": "Full MLE"}]
        if apron1 is not None:
            exceptions.append({"above": apron1, "label": "Taxpayer MLE"})
        if apron2 is not None:
            exceptions.append({"above": apron2, "label": "No exception"})
    return {"guaranteed": round(guaranteed, 1), "cap": cap, "tax": tax, "apron1": apron1, "apron2": apron2,
            "no_cap": cap is None, "exceptions": exceptions}


# --- Development & retirements ------------------------------------------------------------------------------------

def _career_summary(seasons):
    seasons = [s for s in seasons or [] if isinstance(s, dict)]
    awards = [s.get("premi") or s.get("awards") or [] for s in seasons]
    mvps = sum(1 for a in awards if "MVP" in a)
    stars = sum(1 for a in awards if "All-Star" in a or "All-Star Starter" in a)
    titles = sum(1 for s in seasons if s.get("is_champion"))
    games = sum(s.get("gp") or 0 for s in seasons)
    points = sum(((s.get("stats_rs") or {}).get("ppg") or 0) * (s.get("gp") or 0) for s in seasons)
    return {"mvps": mvps, "stars": stars, "titles": titles, "ppg": round(points / games, 1) if games else None}


def _honour_line(summary):
    if not summary:
        return None
    if summary["mvps"]:
        return "MVP" if summary["mvps"] == 1 else f"{summary['mvps']}× MVP"
    if summary["stars"] >= 3:
        return f"{summary['stars']}× All-Star"
    if summary["titles"]:
        return "Ring" if summary["titles"] == 1 else f"{summary['titles']} rings"
    return f"{summary['ppg']} ppg" if summary["ppg"] else None


def development_view(development, retirements, careers, user_team, roster):
    """Your whole roster before → after (unchanged players included), the league's biggest risers and drops,
    and who retired with one honour line each."""
    from core.config import CONFIG
    from core.franchise_legacy import career_name
    rows = CONFIG.END_SEASON.DEV_LEAGUE_ROWS
    changed = {d["name"]: d for d in development or [] if d.get("team") == user_team}
    yours = []
    for p in roster or []:
        d = changed.get(p["name"])
        before, after = (d["ovr_before"], d["ovr_after"]) if d else (p["ovr"], p["ovr"])
        yours.append({"name": p["name"], "age": p.get("age"), "position": p.get("position"),
                      "before": before, "after": after, "delta": after - before})
    yours.sort(key=lambda y: (-y["delta"], -y["after"]))
    others = [{"name": d["name"], "team": d["team"], "age": d.get("age"), "delta": d["ovr_after"] - d["ovr_before"]}
              for d in development or [] if d.get("team") != user_team]

    summaries = {}
    for slug, seasons in (careers or {}).items():
        if seasons:
            summaries[career_name(slug, seasons)] = _career_summary(seasons)
    retired = []
    for r in retirements or []:
        summary = summaries.get(r.get("name"))
        retired.append({"name": r.get("name"), "team": r.get("team"), "age": r.get("age"), "ovr": r.get("ovr"),
                        "honour": _honour_line(summary), "yours": bool(user_team) and r.get("team") == user_team,
                        "_weight": (summary["mvps"] * 100 + summary["stars"] * 10 + summary["titles"] * 5) if summary else 0})
    retired.sort(key=lambda r: (not r["yours"], -r["_weight"], -(r["ovr"] or 0)))
    for r in retired:
        del r["_weight"]
    return {
        "yours": yours,
        "net": {"total": sum(y["delta"] for y in yours), "up": sum(1 for y in yours if y["delta"] > 0),
                "down": sum(1 for y in yours if y["delta"] < 0), "same": sum(1 for y in yours if y["delta"] == 0)},
        "risers": sorted((o for o in others if o["delta"] > 0), key=lambda o: -o["delta"])[:rows],
        "drops": sorted((o for o in others if o["delta"] < 0), key=lambda o: o["delta"])[:rows],
        "retired": retired,
    }


# --- Pre-draft trades ---------------------------------------------------------------------------------------------

def trade_summary(text, team_names):
    """A trade from the engine's log (free text, Italian) as "Trade: A, B, C" from the team names it mentions, in
    order of appearance; None when no two known teams appear (the raw line is never shown)."""
    if not isinstance(text, str):
        return None
    found = sorted((text.find(t), t) for t in team_names or [] if t in text)
    names = list(dict.fromkeys(t for _pos, t in found))
    return "Trade: " + ", ".join(names) if len(names) >= 2 else None


def pick_label(asset, draft_year, draft_order):
    """A pick asset from the trade engine ("1:R1-Team Name": draft 1 = the coming one) as year, round,
    original team and, for the coming draft once the order is set, its slot."""
    try:
        rel, key = str(asset).split(":", 1)
        rnd, original = key.split("-", 1)
        rel, rnd = int(rel), int(rnd.lstrip("Rr"))
    except ValueError:
        return {"label": asset}
    order = list(draft_order or [])
    slot = None
    if rel == 1 and original in order:
        slot = order.index(original) + 1 + (rnd - 1) * len(order)
    return {"year": draft_year + rel - 1 if draft_year else None, "round": rnd, "original": original, "slot": slot}


def _best_slot(picks):
    slots = [p["slot"] for p in picks if p.get("slot")]
    return min(slots) if slots else None


def _offer_card(o, draft_year, draft_order):
    from core.config import CONFIG
    cfg = CONFIG.END_SEASON
    give = {"players": o.get("receiving_players") or [],
            "picks": [pick_label(a, draft_year, draft_order) for a in o.get("receiving_picks") or []]}
    get = {"players": o.get("giving_players") or [],
           "picks": [pick_label(a, draft_year, draft_order) for a in o.get("giving_picks") or []]}
    value = verdict = None
    if o.get("value_for_user") is not None:
        value = round(o["value_for_user"] / max(o.get("value_given") or 0, 1.0), 2)
        verdict = "good" if value >= cfg.TRADE_VALUE_GOOD else "bad" if value <= cfg.TRADE_VALUE_BAD else "fair"
    cap_change = round(sum(p.get("salary") or 0 for p in give["players"]) - sum(p.get("salary") or 0 for p in get["players"]), 1)
    given_slot, got_slot = _best_slot(give["picks"]), _best_slot(get["picks"])
    slot_change = given_slot - got_slot if given_slot and got_slot else None
    if verdict == "bad" and give["players"]:
        best = max(give["players"], key=lambda p: p.get("ovr") or 0)
        summary = f"gives up {best['name']} ({best['ovr']})"
    else:
        parts = []
        if cap_change:
            parts.append(f"+${cap_change:.1f}M space" if cap_change > 0 else f"adds ${-cap_change:.1f}M payroll")
        if slot_change:
            parts.append(f"move {'up' if slot_change > 0 else 'down'} {abs(slot_change)} spots")
        summary = " · ".join(parts)
    return {"id": o.get("id"), "team": o.get("offering_team"), "why": o.get("why"), "reason": o.get("reason"), "give": give, "get": get,
            "value": value, "verdict": verdict, "cap_change": cap_change, "slot_change": slot_change, "summary": summary}


def trade_desk_view(offers, user_team, draft_year, draft_order, payroll, owned_picks, block, wire, team_names=None):
    """Offer cards (you give → you get, a value read, money and draft-slot effect), your picks, your trade block
    with offer counts, and the league's trade wire."""
    cards = [_offer_card(o, draft_year, draft_order) for o in offers or []]
    counts = {}
    for c in cards:
        for p in c["give"]["players"]:
            counts[p["name"]] = counts.get(p["name"], 0) + 1
    return {
        "team": user_team,
        "payroll": payroll,
        "offers": cards,
        "picks": [pick_label(a, draft_year, draft_order) for a in owned_picks or []],
        "block": [dict(b, offers=counts.get(b["name"], 0)) for b in block or []],
        "wire": [line for line in (trade_summary(w, team_names) for w in wire or []) if line],
    }


# --- Roster cuts --------------------------------------------------------------------------------------------------

def cut_sheet_view(rows, engine_picks, target, league):
    """Your roster in cut order with the engine's own picks marked (the default the page starts from), the size to
    reach, and the best players other teams will release."""
    picks = set(engine_picks or [])
    rows = [dict(r, engine_pick=r["name"] in picks) for r in rows or []]
    return {
        "target": target,
        "size": len(rows),
        "to_release": max(0, len(rows) - target),
        "payroll": round(sum(r.get("salary") or 0 for r in rows), 1),
        "rows": rows,
        "league": sorted(league or [], key=lambda p: -(p.get("ovr") or 0)),
    }


# --- New season ---------------------------------------------------------------------------------------------------

def team_strength(ovrs, n=None):
    """Roster strength: mean OVR of the best n players (CONFIG.END_SEASON.TOP_N_STRENGTH), one decimal."""
    from core.config import CONFIG
    n = n or CONFIG.END_SEASON.TOP_N_STRENGTH
    best = sorted(ovrs or [], reverse=True)[:n]
    return round(sum(best) / len(best), 1) if best else 0.0


def grade(delta):
    """Letter for a change in team strength, from CONFIG.END_SEASON.GRADE_STEPS; below the last step "D"."""
    from core.config import CONFIG
    for minimum, letter in CONFIG.END_SEASON.GRADE_STEPS:
        if delta >= minimum:
            return letter
    return "D"


GRADE_LINES = {"A": "Big summer.", "A-": "Big summer.", "B+": "Better than you started.", "B": "Better than you started.",
               "C+": "About the same.", "C": "About the same.", "D": "A step back."}


def _abbr(team):
    from core.franchise_legacy import get_team_branding
    return get_team_branding(team)["abbreviation"] if team else ""


def _draft_overall(pick, size):
    try:
        rnd, num = str(pick).replace("R", "").replace("P", "").split()
        return (int(rnd) - 1) * size + int(num)
    except ValueError:
        return None


def new_season_view(before, league_before, roster_now, teams_now, rosters_now, logs, user_team, roster_limit):
    """Your offseason report card (before → after, who came and went and how, a grade) and the league's preseason
    power rankings with places moved since the offseason opened, plus the summer's biggest moves."""
    from core.config import CONFIG
    cfg = CONFIG.END_SEASON
    logs = {key: ([e for e in value if isinstance(e, (dict, str))] if isinstance(value, list) else value)
            for key, value in (logs or {}).items()}
    draft_rows = [d for d in logs.get("draft") or [] if isinstance(d, dict)]
    size = logs.get("draft_size") or 30
    signings = [x for x in logs.get("fa_signings") or [] if isinstance(x, dict)]
    strength_now = {team: team_strength(ovrs) for team, ovrs in (teams_now or {}).items()}
    ranked = sorted(strength_now, key=lambda t: (-strength_now[t], t))
    rankings = [{"rank": i + 1, "team": t, "strength": strength_now[t],
                 "moved": (league_before[t]["rank"] - (i + 1)) if league_before and t in league_before else None,
                 "yours": bool(user_team) and t == user_team} for i, t in enumerate(ranked)]

    report = None
    if user_team and before:
        before_players = before.get("players") or []
        before_names = {p["name"] for p in before_players}
        now_names = {p["name"] for p in roster_now or []}
        drafted = {d.get("nome"): d for d in draft_rows if d.get("squadra") == user_team}
        signed = {s["player"]: s for s in signings}
        retired = {r.get("name") for r in logs.get("retirements") or [] if isinstance(r, dict)}
        released = set(logs.get("user_releases") or [])
        options_out = {o["name"]: o["kind"] for o in logs.get("options") or [] if isinstance(o, dict)
                       and o.get("team") == user_team and o.get("decision") == "out"}
        team_of = {name: team for team, names in (rosters_now or {}).items() for name in names}

        def arrival_how(name):
            if name in drafted:
                overall = _draft_overall(drafted[name].get("scelta"), size)
                return f"Draft #{overall}" if overall else "Draft"
            if name in signed and signed[name].get("team") == user_team:
                return f"FA · {signed[name].get('years')} yr"
            return "Trade"

        def departure_how(name):
            if name in retired:
                return "Retired"
            if name in released:
                return "Cut"
            if name in options_out:
                return "Opted out" if options_out[name] == "player" else "Option declined"
            if name in signed and signed[name].get("team") != user_team:
                return f"Signed with {_abbr(signed[name].get('team'))}"
            if team_of.get(name) and team_of[name] != user_team:
                return f"Trade {_abbr(team_of[name])}"
            return "Left in FA"

        arrivals = [{"name": p["name"], "position": p.get("position"), "age": p.get("age"), "ovr": p.get("ovr"),
                     "how": arrival_how(p["name"])} for p in roster_now or [] if p["name"] not in before_names]
        departures = [{"name": p["name"], "position": p.get("role"), "age": p.get("age"), "ovr": p.get("ovr"),
                       "how": departure_how(p["name"])} for p in before_players if p["name"] not in now_names]
        arrivals.sort(key=lambda p: -(p["ovr"] or 0))
        departures.sort(key=lambda p: -(p["ovr"] or 0))
        strength_before = (league_before or {}).get(user_team, {}).get("strength") or team_strength(
            [p.get("ovr") or 0 for p in before_players])
        strength_after = strength_now.get(user_team, team_strength([p.get("ovr") or 0 for p in roster_now or []]))
        ages_before = [p["age"] for p in before_players if p.get("age") is not None]
        ages_now = [p["age"] for p in roster_now or [] if p.get("age") is not None]
        letter = grade(round(strength_after - strength_before, 1))
        note = []
        if arrivals:
            note.append(f"{arrivals[0]['name']} is the biggest addition")
        if departures:
            note.append(f"losing {departures[0]['name']} hurts most")
        report = {
            "tiles": {
                "strength": {"before": strength_before, "after": strength_after},
                "payroll": {"before": round(before.get("payroll") or 0, 1),
                            "after": round(sum(p.get("salary") or 0 for p in roster_now or []), 1)},
                "age": {"before": round(sum(ages_before) / len(ages_before), 1) if ages_before else None,
                        "after": round(sum(ages_now) / len(ages_now), 1) if ages_now else None},
                "roster": {"size": len(roster_now or []), "limit": roster_limit},
            },
            "arrivals": arrivals, "departures": departures, "grade": letter, "grade_line": GRADE_LINES[letter],
            "grade_note": "; ".join(note) + "." if note else "",
        }

    moves = [f"{s['player']} signs with {s['team']} · {s.get('years')} yr ${round((s.get('salary') or 0) * (s.get('years') or 0))}M"
             for s in sorted(signings, key=lambda s: -((s.get("salary") or 0) * (s.get("years") or 0)))[:2]]
    first = next((d for d in draft_rows if _draft_overall(d.get("scelta"), size) == 1), None)
    if first:
        moves.append(f"#1 pick {first.get('nome')} to {first.get('squadra')}")
    top_retired = sorted((r for r in logs.get("retirements") or [] if isinstance(r, dict)), key=lambda r: -(r.get("ovr") or 0))[:3]
    if top_retired:
        moves.append(", ".join(r["name"] for r in top_retired) + " retired")
    moves.extend(line for line in (trade_summary(w, list(teams_now or {})) for w in logs.get("scambi") or []) if line)
    return {"report": report, "rankings": rankings, "moves": moves[:cfg.LEAGUE_MOVES]}
