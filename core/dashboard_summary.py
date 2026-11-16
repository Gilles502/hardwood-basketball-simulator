"""Pure computations behind /api/dashboard/summary: results, form, standings, next game.

Everything here reads plain attributes (calendar days with .games, teams with .nome/.vittorie/.sconfitte)
so it can be tested without the Flask server. Thresholds come from CONFIG.DASHBOARD.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class GameResult:
    day_index: int
    date: str
    opponent: str
    is_home: bool
    won: bool
    points_for: int
    points_against: int


def _results_by_team(calendar) -> Dict[str, List[GameResult]]:
    """One pass over the calendar: played games grouped per team, oldest first."""
    by_team: Dict[str, List[GameResult]] = {}
    for day in calendar or []:
        for g in day.games:
            if not g.played:
                continue
            home_won = g.home_score > g.away_score
            by_team.setdefault(g.home_team, []).append(
                GameResult(g.day_index, g.date, g.away_team, True, home_won, g.home_score, g.away_score))
            by_team.setdefault(g.away_team, []).append(
                GameResult(g.day_index, g.date, g.home_team, False, not home_won, g.away_score, g.home_score))
    for results in by_team.values():
        results.sort(key=lambda r: r.day_index)
    return by_team


def team_results(calendar, team_name: str) -> List[GameResult]:
    """Played games of one team, oldest first."""
    return _results_by_team(calendar).get(team_name, [])


def _record(results: List[GameResult]) -> str:
    wins = sum(1 for r in results if r.won)
    return f"{wins}-{len(results) - wins}"


def form_from_results(results: List[GameResult], cfg) -> dict:
    """Streak, last-10, home/away splits and the hot/cold tag for one team."""
    streak_type: Optional[str] = None
    streak_len = 0
    for r in reversed(results):
        kind = "W" if r.won else "L"
        if streak_type is None:
            streak_type = kind
        if kind != streak_type:
            break
        streak_len += 1

    last10 = results[-10:]
    l10_wins = sum(1 for r in last10 if r.won)

    tag = None
    if streak_type == "W" and streak_len >= cfg.HOT_STREAK_MIN:
        tag = "hot"
    elif streak_type == "L" and streak_len >= cfg.COLD_STREAK_MIN:
        tag = "cold"
    elif len(last10) >= 10:
        if l10_wins >= cfg.HOT_L10_WINS_MIN:
            tag = "hot"
        elif l10_wins <= cfg.COLD_L10_WINS_MAX:
            tag = "cold"

    return {
        "streak": f"{streak_type}{streak_len}" if streak_type else "",
        "streak_len": streak_len,
        "streak_type": streak_type,
        "l10": _record(last10),
        "l10_wins": l10_wins,
        "home": _record([r for r in results if r.is_home]),
        "away": _record([r for r in results if not r.is_home]),
        "tag": tag,
    }


def _zone(pos: int, play_in_enabled: bool, cfg) -> str:
    if not play_in_enabled:
        return "playoff" if pos <= cfg.PLAYOFF_SEEDS_WITHOUT_PLAY_IN else "out"
    if pos <= cfg.PLAYOFF_SEEDS:
        return "playoff"
    if pos <= cfg.PLAY_IN_LAST_SEED:
        return "play_in"
    return "out"


def _conference_rows(teams, by_team, play_in_enabled: bool, cfg) -> List[dict]:
    def pct(t) -> float:
        games = t.vittorie + t.sconfitte
        return t.vittorie / games if games else 0.0

    ordered = sorted(teams, key=lambda t: (-pct(t), -t.vittorie, t.nome))
    if not ordered:
        return []
    leader = ordered[0]
    rows = []
    for pos, t in enumerate(ordered, start=1):
        form = form_from_results(by_team.get(t.nome, []), cfg)
        rows.append({
            "pos": pos,
            "nome": t.nome,
            "v": t.vittorie,
            "s": t.sconfitte,
            "pct": round(pct(t), 3),
            "gb": ((leader.vittorie - t.vittorie) + (t.sconfitte - leader.sconfitte)) / 2,
            "home": form["home"],
            "away": form["away"],
            "l10": form["l10"],
            "streak": form["streak"],
            "tag": form["tag"],
            "zone": _zone(pos, play_in_enabled, cfg),
        })
    return rows


def build_standings(tournament, cfg) -> dict:
    """{"west": [row, ...], "east": [row, ...]} ordered by pct, then wins, then name."""
    by_team = _results_by_team(getattr(tournament, "calendario", None))
    play_in = getattr(tournament, "enable_play_in", True)
    return {
        "west": _conference_rows(tournament.squadre_ovest, by_team, play_in, cfg),
        "east": _conference_rows(tournament.squadre_est, by_team, play_in, cfg),
    }


def next_game(calendar, current_day: int, team_name: str) -> Optional[dict]:
    """First unplayed game of the team on or after the current day, or None."""
    for day in calendar or []:
        if day.day_index < current_day:
            continue
        for g in day.games:
            if g.played or team_name not in (g.home_team, g.away_team):
                continue
            is_home = g.home_team == team_name
            return {
                "game_id": g.game_id,
                "date": g.date,
                "day_index": g.day_index,
                "opponent": g.away_team if is_home else g.home_team,
                "is_home": is_home,
            }
    return None


def last_result(results: List[GameResult]) -> Optional[dict]:
    """The most recent played game of a team, or None."""
    if not results:
        return None
    r = results[-1]
    return {
        "opponent": r.opponent, "date": r.date, "is_home": r.is_home, "won": r.won,
        "points_for": r.points_for, "points_against": r.points_against,
    }


def _find_row(standings: dict, team_name: str):
    """(conference label, row) of a team in the standings, or (None, None)."""
    for key, label in (("west", "West"), ("east", "East")):
        for row in standings[key]:
            if row["nome"] == team_name:
                return label, row
    return None, None


def _injuries(team) -> List[dict]:
    hurt = [p for p in getattr(team, "roster", []) if getattr(p, "infortunato", False)]
    hurt.sort(key=lambda p: p.ovr, reverse=True)
    return [{"name": p.nome, "days": p.giorni_infortunio_rimanenti, "ovr": p.ovr} for p in hurt]


def build_summary(tournament, league_state: str, cfg, trade_offers: int, board_concern: bool) -> dict:
    """Everything the sidebar and Dashboard need in one light, read-only payload."""
    import time

    calendar = getattr(tournament, "calendario", None) or []
    current_day = getattr(tournament, "_current_gameday", 0)
    if calendar:
        date = calendar[min(current_day, len(calendar) - 1)].date
    else:
        date = None

    standings = build_standings(tournament, cfg)
    user_team = getattr(tournament, "squadra_giocatore", None)

    team = next_info = last = form = None
    injuries: List[dict] = []
    if user_team is not None:
        results = team_results(calendar, user_team.nome)
        conference, row = _find_row(standings, user_team.nome)
        team = {
            "name": user_team.nome,
            "record": f"{user_team.vittorie}-{user_team.sconfitte}",
            "conference": conference,
            "conf_rank": row["pos"] if row else None,
        }
        next_info = next_game(calendar, current_day, user_team.nome)
        if next_info:
            opp_conf, opp_row = _find_row(standings, next_info["opponent"])
            next_info["opponent_record"] = f"{opp_row['v']}-{opp_row['s']}" if opp_row else None
            next_info["opponent_rank"] = opp_row["pos"] if opp_row else None
            next_info["opponent_conference"] = opp_conf
        last = last_result(results)
        form = form_from_results(results, cfg)
        injuries = _injuries(user_team)

    return {
        "date": date,
        "day_index": current_day,
        "total_days": len(calendar),
        "team": team,
        "next_game": next_info,
        "last_result": last,
        "form": form,
        "standings": standings,
        "attention": {
            "injuries": injuries,
            "trade_offers": trade_offers,
            "board_concern": board_concern,
            "pending_step": league_state,
        },
        "updated_at": int(time.time()),
    }
