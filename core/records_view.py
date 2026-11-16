"""League Records and All-Time Leaders payloads for the History page.

Pure functions, no Flask. Careers come from player_careers.json: each season is either the old format (per-game
numbers in `stats_rs`) or the new one (season totals `pts`, `reb`, …). Names come from the saved `nome`.
"""
from core.config import CONFIG
from core.franchise_legacy import career_name
from core.history_view import year_for

SINGLE_GAME_STATS = ("points", "rebounds", "assists", "three_pointers", "steals", "blocks")
# Single-season per-game records: stat -> (new-format total key, old-format per-game key).
PER_GAME = {"ppg": ("pts", "ppg"), "rpg": ("reb", "rpg"), "apg": ("ast", "apg"), "spg": ("stl", "spg"),
            "bpg": ("blk", "bpg")}
TOTALS = {"points": "ppg", "rebounds": "rpg", "assists": "apg", "steals": "spg", "blocks": "bpg"}
HONOURS = ("titles", "mvp", "finals_mvp", "dpoy", "all_star", "all_league")
ALL_LEAGUE = ("All-NBA 1st", "All-NBA 2nd", "All-NBA 3rd")


def _games(season):
    return season.get("gp") or season.get("partite_giocate_rs") or 0


def _per_game(season, stat):
    """A season's per-game number for ppg/rpg/…, from totals (new format) or stats_rs (old)."""
    total_key, old_key = PER_GAME[stat]
    if "pts" in season:
        games = _games(season)
        return season.get(total_key, 0) / games if games else 0.0
    return (season.get("stats_rs") or {}).get(old_key, 0) or 0.0


def _seasons(raw):
    return [s for s in raw or [] if isinstance(s, dict)]


def _career(slug, seasons, user_team, year):
    totals = dict.fromkeys(TOTALS, 0.0)
    honours = dict.fromkeys(HONOURS, 0)
    games = 0
    peak = {"ppg": 0.0}
    for s in seasons:
        g = _games(s)
        games += g
        for stat, per_game in TOTALS.items():
            totals[stat] += _per_game(s, per_game) * g
        peak["ppg"] = max(peak["ppg"], _per_game(s, "ppg"))
        awards = s.get("premi") or s.get("awards") or []
        honours["titles"] += 1 if s.get("is_champion") else 0
        honours["mvp"] += 1 if "MVP" in awards else 0
        honours["finals_mvp"] += 1 if "Finals MVP" in awards else 0
        honours["dpoy"] += 1 if "DPOY" in awards else 0
        honours["all_star"] += 1 if ("All-Star" in awards or "All-Star Starter" in awards) else 0
        honours["all_league"] += 1 if any(a in awards for a in ALL_LEAGUE) else 0
    numbers = [s["stagione"] for s in seasons if s.get("stagione")]
    totals = {k: int(round(v)) for k, v in totals.items()}

    def avg(stat):
        return round(totals[stat] / games, 1) if games else 0.0

    return {
        "name": career_name(slug, seasons), "games": games, "seasons": len(seasons),
        "first_year": year(min(numbers)) if numbers else None, "last_year": year(max(numbers)) if numbers else None,
        "last_team": seasons[-1].get("squadra"),
        "played_for_user": bool(user_team) and any(s.get("squadra") == user_team for s in seasons),
        "totals": totals, "honours": honours,
        "card": dict({"ppg": avg("points"), "rpg": avg("rebounds"), "apg": avg("assists"),
                      "peak_ppg": round(peak["ppg"], 1)}, **honours),
    }


def _board(players, value_of, per_game_of=None):
    rows = [(value_of(p), p) for p in players if value_of(p) > 0]
    rows.sort(key=lambda r: (-r[0], r[1]["name"]))
    out = []
    for rank, (value, p) in enumerate(rows[:CONFIG.HISTORY.LEADERS_TOP_N], start=1):
        row = {"rank": rank, "name": p["name"], "value": value, "games": p["games"], "seasons": p["seasons"],
               "first_year": p["first_year"], "last_year": p["last_year"], "last_team": p["last_team"],
               "played_for_user": p["played_for_user"], "card": p["card"]}
        if per_game_of:
            row["per_game"] = per_game_of(p)
        out.append(row)
    return out


def career_leaders_view(careers, user_team, years, starting_year):
    """Career boards: totals (points … blocks) and honours (titles … all_league), top CONFIG.HISTORY.LEADERS_TOP_N."""
    def year(season):
        return year_for(season, years, starting_year)

    players = [_career(slug, _seasons(raw), user_team, year) for slug, raw in (careers or {}).items() if _seasons(raw)]
    boards = {}
    for stat in TOTALS:
        boards[stat] = _board(players, lambda p, s=stat: p["totals"][s],
                              lambda p, s=stat: round(p["totals"][s] / p["games"], 1) if p["games"] else 0.0)
    for honour in HONOURS:
        boards[honour] = _board(players, lambda p, h=honour: p["honours"][h])
    return {"total_players": len(players), "boards": boards}


def league_records_view(records, careers, user_team, years, starting_year):
    """Single-game records (tracked live), single-season per-game bests (from careers), triple-doubles ladder."""
    def year(season):
        return year_for(season, years, starting_year)

    records = records or {}
    single_game = []
    for stat in SINGLE_GAME_STATS:
        rec = records.get(f"{stat}_single_game")
        if not rec:
            continue
        single_game.append({"stat": stat, "value": rec.get("value"), "player": rec.get("player_name"),
                            "team": rec.get("team_name"), "opponent": rec.get("opponent_name"),
                            "season": rec.get("season"), "year": year(rec.get("season")),
                            "is_user_team": bool(user_team) and rec.get("team_name") == user_team})

    best = {}
    user_players = set()
    for slug, raw in (careers or {}).items():
        seasons = _seasons(raw)
        name = career_name(slug, seasons) if seasons else None
        if user_team and any(s.get("squadra") == user_team for s in seasons):
            user_players.add(name)
        for s in seasons:
            if _games(s) < CONFIG.HISTORY.SEASON_RECORD_MIN_GAMES:
                continue
            for stat in PER_GAME:
                value = round(_per_game(s, stat), 1)
                if value > 0 and (stat not in best or value > best[stat]["value"]):
                    best[stat] = {"stat": stat, "value": value, "player": name, "team": s.get("squadra"),
                                  "season": s.get("stagione"), "year": year(s.get("stagione")),
                                  "is_user_team": bool(user_team) and s.get("squadra") == user_team}

    triple = [{"player": t.get("player_name"), "count": t.get("count", 0),
               "played_for_user": t.get("player_name") in user_players}
              for t in (records.get("triple_doubles_leaders") or [])[:CONFIG.HISTORY.TRIPLE_DOUBLES_TOP_N]]
    return {"single_game": single_game, "single_season": [best[s] for s in PER_GAME if s in best],
            "triple_doubles": triple}
