"""Expected wins and the season record per team: the yardstick the owners and the GM market judge by.

The expectation is fixed at the season start (`mark_season_start`) so a mid-season trade spree does not
move the goalposts; `close_season` writes the row once the season is over: the plan the season started with
(`plan_start`; `plan` is the plan at its end), whether the coach changed, and the top 8 at the end (`top8_end`).
"""
from typing import List

from core.config import CONFIG
from core.front_office.state import current_year


def _top8(team) -> list:
    return sorted(getattr(team, "roster", []) or [], key=lambda p: p.ovr, reverse=True)[:8]


def league_avg_ovr(torneo) -> float:
    """Average OVR of every rostered player in the league."""
    players = [p for s in torneo.squadre for p in (getattr(s, "roster", []) or [])]
    return sum(p.ovr for p in players) / len(players) if players else 0.0


def expected_wins(team, league_avg: float) -> float:
    """Wins a team should get from the talent of its top 8 against the league average."""
    cfg = CONFIG.FRONT_OFFICE
    top8 = _top8(team)
    if not top8:
        return float(cfg.EXPECTED_WINS_EMPTY_ROSTER)
    avg = sum(p.ovr for p in top8) / len(top8)
    low, high = cfg.EXPECTED_WINS_RANGE
    return max(low, min(high, cfg.EXPECTED_WINS_BASE + (avg - league_avg) * cfg.EXPECTED_WINS_PER_OVR))


def _mark(fo, team, year: int, league_avg: float, last_wins) -> dict:
    return {
        "year": year,
        "expected": expected_wins(team, league_avg),
        "last_wins": last_wins,
        "top8": [p.nome for p in _top8(team)],
        "plan": getattr(fo.plans.get(team.nome), "state", None),
    }


def mark_season_start(torneo, fo) -> None:
    """Freezes every team's expectation, its core, its plan and last season's wins (still on the team here)."""
    league_avg = league_avg_ovr(torneo)
    year = current_year(torneo)
    for team in torneo.squadre:
        fo.season_marks[team.nome] = _mark(fo, team, year, league_avg, int(getattr(team, "vittorie", 0)))


def ensure_season_marks(torneo, fo) -> None:
    """A new league, or an old save loaded mid-season: teams without a mark for this year get one now. Last
    season's wins come from its record row (None without one). Existing marks are never touched."""
    year = current_year(torneo)
    missing = [t for t in torneo.squadre if (fo.season_marks.get(t.nome) or {}).get("year") != year]
    if not missing:
        return
    league_avg = league_avg_ovr(torneo)
    for team in missing:
        last = next((r for r in reversed(fo.records.get(team.nome, [])) if r.get("year") == year - 1), None)
        fo.season_marks[team.nome] = _mark(fo, team, year, league_avg,
                                           int(last["wins"]) if last and "wins" in last else None)


def mark_coach_change(torneo, fo, team_name: str) -> None:
    """A coach left during the season (mid-season firing): the season's record row will say so."""
    mark = fo.season_marks.get(team_name)
    if mark and mark.get("year") == current_year(torneo):
        mark["coach_fired"] = True


def mark_season_end(torneo, fo) -> None:
    """Snapshots every team's end-of-season top 8 before offseason progression strips retiring and expiring players."""
    year = current_year(torneo)
    for team in torneo.squadre:
        mark = fo.season_marks.get(team.nome)
        if mark and mark.get("year") == year:
            mark["top8_end"] = [p.nome for p in _top8(team)]


def close_season(torneo, fo) -> None:
    """Appends the season just played to each team's records and to its seated GM's career. Once per team and year."""
    year = current_year(torneo)
    league_avg = league_avg_ovr(torneo)
    playoff_names = {t.nome for conf in (getattr(torneo, "playoff_teams", None) or {}).values() for t in conf}
    champion = getattr(torneo, "campione", None)
    champion_name = getattr(champion, "nome", None)
    keep = CONFIG.FRONT_OFFICE.RECORDS_KEEP_PER_TEAM
    for team in torneo.squadre:
        rows = fo.records.setdefault(team.nome, [])
        if any(r.get("year") == year for r in rows):
            continue
        mark = fo.season_marks.get(team.nome)
        if not (mark and mark.get("year") == year):
            mark = None
        expected = mark["expected"] if mark else expected_wins(team, league_avg)
        wins, losses = int(getattr(team, "vittorie", 0)), int(getattr(team, "sconfitte", 0))
        made_playoffs = team.nome in playoff_names
        is_champion = team.nome == champion_name
        top8_end = mark.get("top8_end") if mark else None
        rows.append({"year": year, "wins": wins, "losses": losses, "expected": expected,
                     "playoffs": made_playoffs, "champion": is_champion,
                     "plan": getattr(fo.plans.get(team.nome), "state", None),
                     "plan_start": mark.get("plan") if mark else None,
                     "gm_id": fo.seats.get(team.nome),
                     "coach_fired": bool(mark.get("coach_fired", False)) if mark else False,
                     "top8_end": list(top8_end) if top8_end is not None else [p.nome for p in _top8(team)]})
        del rows[:-keep]
        gm = fo.seated_gm(team.nome)
        entry = next((e for e in reversed(gm.career) if e.get("to_year") is None), None) if gm else None
        if entry is not None:
            entry["wins"] += wins
            entry["losses"] += losses
            entry["playoffs"] += int(made_playoffs)
            entry["titles"] += int(is_champion)


def last_records(fo, team: str, n: int) -> List[dict]:
    """The team's last n season rows, newest last."""
    return list(fo.records.get(team, []))[-n:] if n > 0 else []
