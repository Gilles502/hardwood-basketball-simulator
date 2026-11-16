"""Trophy Room payload: reshapes core/franchise_legacy.py's output for the History page.

Pure functions, no Flask. franchise_legacy keeps its old "Season N" strings and Italian playoff labels (they are in
the saves); here they become season numbers, years and English. The franchise's single-game records are checked
against the league records, which are tracked separately and can be higher.
"""
import re

from core.config import CONFIG
from core.history_view import FINALS_LABEL, parse_season, playoff_label, season_years, year_for

SINGLE_GAME_STATS = ("points", "rebounds", "assists", "three_pointers", "steals", "blocks")
SINGLE_SEASON_STATS = ("ppg", "points", "rpg", "rebounds", "assists", "three_pointers")
LEADER_STATS = ("points", "rebounds", "assists", "three_pointers", "games")
AWARDS = ("finals_mvp", "mvp", "dpoy", "roy", "sixth_man")
PLACEHOLDER_PLAYERS = {"Waiting for games", "In progress", "", None}
NOT_PLAYOFFS = {"Lottery", "Play-In", "In Progress"}


def _season_numbers(text):
    return [int(n) for n in re.findall(r"\d+", str(text or ""))]


def _player(value):
    return None if not value or str(value).strip().upper() == "N/A" else value


def _finals(history):
    """Season number -> (champion, runner-up) from league_history; runner-up None if no "Finals" standing."""
    out = {}
    for item in history or []:
        if not isinstance(item, dict) or not item.get("stagione"):
            continue
        runner = next((s.get("team") for s in item.get("standings") or []
                       if str(s.get("playoff_round", "")).startswith(FINALS_LABEL)), None)
        out[item["stagione"]] = (item.get("campione"), runner)
    return out


def _champion_row(history_item, team):
    return next((s for s in (history_item or {}).get("standings") or [] if s.get("team") == team), None)


def _single_game(legacy, league_records, team, year):
    rows = []
    stored = legacy.get("single_game_records") or {}
    for stat in SINGLE_GAME_STATS:
        rec = stored.get(stat) or {}
        best = None
        if rec.get("player") not in PLACEHOLDER_PLAYERS and (rec.get("value") or 0) > 0:
            season = parse_season(rec.get("year"))
            best = {"stat": stat, "value": rec["value"], "player": rec["player"], "opponent": rec.get("opponent"),
                    "season": season, "year": year(season)}
        league = (league_records or {}).get(f"{stat}_single_game") or {}
        if league.get("team_name") == team and (league.get("value") or 0) > (best["value"] if best else 0):
            season = league.get("season")
            best = {"stat": stat, "value": league["value"], "player": league.get("player_name"),
                    "opponent": league.get("opponent_name"), "season": season, "year": year(season)}
        if best:
            rows.append(best)
    return rows


def _single_season(legacy, year):
    rows = []
    stored = legacy.get("single_season_records") or {}
    for stat in SINGLE_SEASON_STATS:
        rec = stored.get(stat) or {}
        if rec.get("player") in PLACEHOLDER_PLAYERS or not rec.get("value"):
            continue
        season = parse_season(rec.get("year"))
        rows.append({"stat": stat, "value": rec["value"], "player": rec["player"], "season": season,
                     "year": year(season)})
    return rows


def _leaders(legacy, year):
    out = {}
    for stat in LEADER_STATS:
        rows = []
        for row in (legacy.get("all_time_leaders") or {}).get(stat) or []:
            if not row.get("value"):
                continue
            seasons = _season_numbers(row.get("era"))
            rows.append({"name": row.get("name"), "value": row["value"],
                         "first_year": year(min(seasons)) if seasons else None,
                         "last_year": year(max(seasons)) if seasons else None})
        out[stat] = rows[:CONFIG.HISTORY.FRANCHISE_LEADERS_TOP_N]
    return out


def _jerseys(legacy, year):
    rows = []
    for j in legacy.get("retired_jerseys") or []:
        seasons = _season_numbers(j.get("era"))
        first, last = (min(seasons), max(seasons)) if seasons else (None, None)
        rows.append(({"number": j.get("number"), "player": j.get("player"), "first_year": year(first),
                      "last_year": year(last)}, (last - first) if seasons else -1))
    rows.sort(key=lambda r: -r[1])
    return [r[0] for r in rows]


def _seasons(standings_history, year):
    by_number = {s["season"]: s for s in standings_history or [] if isinstance(s, dict) and s.get("season")}
    if not by_number:
        return []
    out = []
    for number in range(min(by_number), max(by_number) + 1):
        s = by_number.get(number)
        if s is None:
            out.append({"season": number, "year": year(number), "missing": True})
            continue
        raw = s.get("playoff_round")
        result = "Champions" if s.get("is_champion") else playoff_label(raw)
        out.append({"season": number, "year": s.get("year") or year(number), "wins": s.get("wins", 0),
                    "losses": s.get("losses", 0), "conf_seed": s.get("conf_seed"), "result": result})
    return out


def trophy_room_view(legacy, history, league_records, user_team, starting_year):
    """One franchise's Trophy Room: banners, cabinet, jerseys, leaders, records and seasons, with real years."""
    legacy = legacy or {}
    team = legacy.get("team_name")
    years = {s["season"]: s["year"] for s in legacy.get("standings_history") or []
             if isinstance(s, dict) and s.get("season") and isinstance(s.get("year"), int)}
    years.update(season_years(history))

    def year(season):
        return year_for(season, years, starting_year)

    history_by_season = {h["stagione"]: h for h in history or [] if isinstance(h, dict) and h.get("stagione")}
    finals = _finals(history)

    banners = []
    for b in legacy.get("banners") or []:
        season = parse_season(b.get("year"))
        row = _champion_row(history_by_season.get(season), team) or {}
        banners.append({"season": season, "year": year(season), "finals_mvp": _player(b.get("finals_mvp")),
                        "runner_up": finals.get(season, (None, None))[1],
                        "wins": row.get("wins"), "losses": row.get("losses")})
    banners.sort(key=lambda b: b["season"] or 0)

    seasons = _seasons(legacy.get("standings_history"), year)
    lost = {n: champ for n, (champ, runner) in finals.items() if runner == team and champ != team}
    for s in seasons:
        if s.get("result") == "Lost Finals" and s["season"] not in lost:
            lost[s["season"]] = finals.get(s["season"], (None, None))[0]

    cabinet_in = legacy.get("trophy_cabinet") or {}
    cabinet = {"titles": [{"season": b["season"], "year": b["year"]} for b in banners],
               "lost_finals": [{"season": n, "year": year(n), "winner": lost[n]} for n in sorted(lost)]}
    for award in AWARDS:
        cabinet[award] = [{"player": e.get("player"), "season": parse_season(e.get("year")),
                           "year": year(parse_season(e.get("year")))}
                          for e in cabinet_in.get(award) or [] if _player(e.get("player"))]

    played = [s for s in seasons if not s.get("missing")]
    wins = sum(s["wins"] for s in played)
    losses = sum(s["losses"] for s in played)
    return {
        "team_name": team,
        "abbreviation": legacy.get("abbreviation"),
        "arena": legacy.get("arena"),
        "city": legacy.get("city"),
        "established": legacy.get("established"),
        "colors": legacy.get("colors"),
        "is_user_team": bool(user_team) and team == user_team,
        "summary": {"titles": len(banners), "finals": len(banners) + len(lost),
                    "playoff_seasons": sum(1 for s in played if s["result"] not in NOT_PLAYOFFS),
                    "wins": wins, "losses": losses,
                    "win_pct": round(wins / (wins + losses), 3) if wins + losses else 0.0},
        "banners": banners,
        "cabinet": cabinet,
        "retired_jerseys": _jerseys(legacy, year),
        "leaders": _leaders(legacy, year),
        "records": {"single_game": _single_game(legacy, league_records, team, year),
                    "single_season": _single_season(legacy, year)},
        "seasons": seasons,
        # Full rows for the team profile popup's chart (ppg, rank, …), labels in English.
        "standings_history": [dict(s, playoff_round="Champions" if s.get("is_champion")
                                   else playoff_label(s.get("playoff_round")))
                              for s in legacy.get("standings_history") or [] if isinstance(s, dict)],
    }


def franchise_list(summary, user_team):
    """The team picker: the user's team first, then most titles, then name."""
    teams = [dict(t, is_user_team=bool(user_team) and t.get("team_name") == user_team) for t in summary or []]
    teams.sort(key=lambda t: (not t["is_user_team"], -(t.get("championships_count") or 0), t.get("team_name") or ""))
    return teams
