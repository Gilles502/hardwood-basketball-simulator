"""Coach of the Year and GM of the Year: who beat the expectation, and who rebuilt the roster to do it."""
from typing import Callable, Optional

from core.config import CONFIG
from core.front_office.seasons import _top8, expected_wins, league_avg_ovr
from core.front_office.state import current_year, user_gm_name, user_team_name


def _mark_values(torneo, fo, team, league_avg: float):
    """(expected wins, last season's wins or None, the core to measure turnover against or None).
    The core is last season's end-of-season top 8, so a summer rebuild counts; without that row, the
    season-start top 8."""
    year = current_year(torneo)
    last_row = next((r for r in reversed(fo.records.get(team.nome, [])) if r.get("year") == year - 1), None)
    last_core = last_row.get("top8_end") if last_row else None
    mark = fo.season_marks.get(team.nome)
    if mark and mark.get("year") == year:
        return mark["expected"], mark.get("last_wins"), last_core if last_core is not None else mark.get("top8")
    return expected_wins(team, league_avg), None, last_core


def _best(torneo, fo, name_of: Callable, score_of: Callable) -> Optional[dict]:
    league_avg = league_avg_ovr(torneo)
    best, best_score = None, None
    for team in torneo.squadre:
        name = name_of(team)
        if not name:
            continue
        expected, last_wins, core = _mark_values(torneo, fo, team, league_avg)
        wins, losses = int(getattr(team, "vittorie", 0)), int(getattr(team, "sconfitte", 0))
        jump = (wins - last_wins) if last_wins is not None else 0
        score = score_of(team, wins, expected, jump, core)
        if best_score is None or score > best_score:
            best_score = score
            best = {"nome": name, "squadra": team.nome, "wins": wins, "losses": losses,
                    "expected": round(expected, 1), "last_wins": last_wins}
    return best


def coach_of_the_year(torneo, fo) -> Optional[dict]:
    """The coach who won the most beyond expectation, with a bonus for the jump from last season."""
    weight = CONFIG.FRONT_OFFICE.COY_JUMP_WEIGHT

    def coach_name(team):
        name = getattr(getattr(team, "coach", None), "nome", None)
        return None if not name or str(name).startswith("Interim") else name

    return _best(torneo, fo, coach_name,
                 lambda team, wins, expected, jump, core: wins - expected + weight * jump)


def gm_of_the_year(torneo, fo) -> Optional[dict]:
    """The GM whose team jumped and beat expectation, most of all after rebuilding the core."""
    cfg = CONFIG.FRONT_OFFICE
    user_team = user_team_name(torneo)

    def gm_name(team):
        if team.nome == user_team:
            return user_gm_name(torneo)
        gm = fo.seated_gm(team.nome)
        return gm.name if gm else None

    def score(team, wins, expected, jump, core):
        base = jump * cfg.GMOY_JUMP_WEIGHT + (wins - expected) * cfg.GMOY_EXPECTED_WEIGHT
        top8 = [p.nome for p in _top8(team)]
        if base <= 0:
            return base  # turnover rewards a rebuild that worked, it never deepens a bad season
        turnover = sum(1 for n in top8 if n not in core) / len(top8) if (core is not None and top8) else 0.0
        return base * (1 + cfg.GMOY_TURNOVER_WEIGHT * turnover)

    return _best(torneo, fo, gm_name, score)


def record_gm_award(torneo, fo, winner: Optional[dict]) -> None:
    """A CPU GM's open career entry remembers the award; the user's GM has no CPU career."""
    if not winner or winner["squadra"] == user_team_name(torneo):
        return
    gm = fo.seated_gm(winner["squadra"])
    entry = next((e for e in reversed(gm.career) if e.get("to_year") is None), None) if gm else None
    if entry is None:
        return
    label = f"GM of the Year {current_year(torneo)}"
    awards = entry.setdefault("awards", [])
    if label not in awards:
        awards.append(label)
