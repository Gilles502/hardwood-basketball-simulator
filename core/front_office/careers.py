"""GM careers: skills grow with experience and results, decline with age, and the GM finally retires."""
from typing import List, Optional

from core.config import CONFIG
from core.front_office.models import CpuGM
from core.front_office.state import _unseat, current_year


def _years_multiplier(years_as_gm: int) -> float:
    for lower, mult in reversed(CONFIG.FRONT_OFFICE.GROWTH_BY_YEARS):
        if years_as_gm >= lower:
            return mult
    return 0.0


def _result_bonus(last: Optional[dict]) -> int:
    cfg = CONFIG.FRONT_OFFICE
    if not last:
        return 0
    bonus = 0
    if last.get("wins", 0) >= last.get("expected", 0) + cfg.GROWTH_RESULT_BEAT_EXPECTED_BY:
        bonus += cfg.GROWTH_RESULT_BEAT_EXPECTED
    if last.get("playoffs"):
        bonus += cfg.GROWTH_RESULT_PLAYOFFS
    if last.get("champion"):
        bonus += cfg.GROWTH_RESULT_TITLE
    return bonus


def grow_skills(gm: CpuGM, last: Optional[dict], rng) -> None:
    """One season of experience for a seated GM; `last` is his team's record row for the season just played."""
    cfg = CONFIG.FRONT_OFFICE
    bonus = _result_bonus(last)
    base = cfg.GROWTH_BASE * _years_multiplier(gm.years_as_gm)
    whole, fraction = int(base), base - int(base)
    for skill in list(gm.skills):
        delta = 0
        if gm.age < cfg.GROWTH_STOP_AGE:
            delta += whole + (1 if fraction > 0 and rng.random() < fraction else 0) + bonus
        if gm.age >= cfg.DECLINE_AGE and rng.random() < cfg.DECLINE_CHANCE:
            delta -= 1
        gm.skills[skill] = max(cfg.SKILL_FLOOR, min(cfg.SKILL_CEILING, gm.skills[skill] + delta))


def retirement_chance(gm: CpuGM) -> float:
    """Chance to retire this offseason: 0 below the first age of RETIRE_CHANCE_POINTS, rising along the points,
    the last chance from the last age."""
    points = CONFIG.FRONT_OFFICE.RETIRE_CHANCE_POINTS
    age = gm.age
    if age < points[0][0]:
        return 0.0
    if age >= points[-1][0]:
        return float(points[-1][1])
    for (a0, p0), (a1, p1) in zip(points, points[1:]):
        if a0 <= age <= a1:
            return p0 + (p1 - p0) * (age - a0) / (a1 - a0)
    return float(points[0][1])


def _idle_since(gm: CpuGM) -> Optional[int]:
    """The year a GM off the market's seats became free: his last job's end, else when he entered the market."""
    last_end = gm.career[-1].get("to_year") if gm.career else None
    return last_end if last_end is not None else gm.available_from_year


def retire_gms(torneo, fo, rng) -> List[CpuGM]:
    """Retires GMs by age (seated or on the market) and market GMs left idle too long; returns who retired.
    The GM of this year's champion stays. A seated GM who retires leaves his seat empty."""
    cfg = CONFIG.FRONT_OFFICE
    year = current_year(torneo)
    champion = getattr(getattr(torneo, "campione", None), "nome", None)
    champion_gm = fo.seats.get(champion) if champion else None
    retired = []
    for gm_id in sorted(fo.gms):
        gm = fo.gms[gm_id]
        if gm.retired_year is not None or gm_id == champion_gm:
            continue
        seated = gm.team is not None and fo.seats.get(gm.team) == gm_id
        idle_since = _idle_since(gm)
        idle = (not seated and not gm.historical and idle_since is not None
                and year - idle_since >= cfg.MARKET_IDLE_RETIRE_YEARS)
        if not idle and not rng.random() < retirement_chance(gm):
            continue
        if seated:
            _unseat(fo, gm.team, year, "retired")
        gm.retired_year = year
        retired.append(gm)
    return retired
