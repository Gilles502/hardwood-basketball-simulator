"""Team plans with memory. Evaluated only at two checkpoints: the start of a season and the trade deadline.

Layer 2a: the trade AI reads it (TradeFinder.get_team_strategy returns the plan state), so a team's
trade strategy changes only here, always with a reason.
"""
import random
from typing import Optional, Tuple

from core.config import CONFIG
from core.front_office.careers import grow_skills
from core.front_office.models import TeamPlan
from core.front_office.seasons import last_records, mark_season_start
from core.front_office.state import current_year, ensure_front_office, user_team_name

__all__ = ["TeamPlan", "suggest_plan", "seed_missing_plans", "checkpoint_new_season", "checkpoint_deadline",
           "team_plan_state", "rebuild_on_schedule", "new_gm_plan", "gm_lean"]

EXTREMES = {"CONTENDER", "REBUILDER"}


def _top8(team) -> list:
    return sorted(getattr(team, "roster", []) or [], key=lambda p: p.ovr, reverse=True)[:8]


def _avg(values, default: float) -> float:
    values = list(values)
    return sum(values) / len(values) if values else default


def _league_top8(torneo) -> float:
    return _avg((_avg((p.ovr for p in _top8(s)), 0.0) for s in torneo.squadre if getattr(s, "roster", None)), 80.0)


def suggest_plan(team, torneo) -> Tuple[str, str]:
    """(plan state, reason) from the roster alone (no win rate), via Tournament._determina_stato_squadra."""
    status = torneo._determina_stato_squadra(team)
    top8 = _top8(team)
    rating = _avg((p.ovr for p in top8), 0.0)
    core_age = _avg((p.eta for p in top8[:5]), 30.0)
    gap = rating - _league_top8(torneo)

    if status == "Defending Champion":
        return "CONTENDER", "Defending champions: the window is open, run it back"
    if status == "Contender":
        return "CONTENDER", f"Top-8 rating {rating:.1f}, {gap:+.1f} over the league: a title window"
    if status == "Aging Core":
        return "PLAYOFF", f"Playoff roster with a core aged {core_age:.1f}: win now while it lasts"
    if status == "Playoff Team":
        return "PLAYOFF", f"Top-8 rating {rating:.1f} ({gap:+.1f} vs the league): a playoff roster"
    if status == "Rising Star":
        if gap >= -CONFIG.FRONT_OFFICE.PLAN_RISING_STAR_MARGIN:
            return "PLAYOFF", f"Young core aged {core_age:.1f} already near the top: push for the playoffs"
        return "REBUILDER", f"Young core aged {core_age:.1f}, still {abs(gap):.1f} below the league: let it grow"
    if status == "Rebuilding":
        return "REBUILDER", f"Top-8 rating {abs(gap):.1f} below the league: time to rebuild"
    return "MIDDLE", f"Top-8 rating {rating:.1f} ({gap:+.1f} vs the league): stuck in the middle"


def _summit_plan(team) -> Optional[Tuple[str, str]]:
    summit = getattr(team, "front_office_summit", None)
    if isinstance(summit, dict) and summit.get("completed"):
        goal = summit.get("agreed_goal")
        state = CONFIG.FRONT_OFFICE.SUMMIT_GOAL_PLANS.get(goal)
        if state:
            return state, f"Agreed at the pre-season summit: {str(goal).replace('_', ' ').lower()}"
    return None


def _change(plan: TeamPlan, state: str, reason: str, year: int, checkpoint: str) -> None:
    plan.history.append({"year": year, "from": plan.state, "to": state, "reason": reason, "checkpoint": checkpoint})
    plan.state = state
    plan.reason = reason
    plan.since_year = year
    plan.seasons_held = 1


def _new_plan(state: str, reason: str, year: int) -> TeamPlan:
    return TeamPlan(state=state, since_year=year, seasons_held=1, reason=reason,
                    history=[{"year": year, "from": None, "to": state, "reason": reason, "checkpoint": "start"}])


def seed_missing_plans(torneo, fo=None) -> None:
    """Every team gets a plan as soon as the GMs exist (new leagues and old saves alike)."""
    fo = fo if fo is not None else ensure_front_office(torneo)
    year = current_year(torneo)
    user_team = user_team_name(torneo)
    for team in getattr(torneo, "squadre", []):
        if team.nome in fo.plans:
            continue
        chosen = _summit_plan(team) if team.nome == user_team else None
        fo.plans[team.nome] = _new_plan(*(chosen or suggest_plan(team, torneo)), year)


def checkpoint_new_season(torneo, rng=None) -> None:
    """Start of a season: seated GMs grow, every GM ages a year; each plan is kept unless it has run its course
    or the roster jumped."""
    fo = ensure_front_office(torneo)
    rng = rng if rng is not None else random.Random()
    year = current_year(torneo)
    user_team = user_team_name(torneo)
    min_seasons = CONFIG.FRONT_OFFICE.PLAN_MIN_SEASONS

    for gm in fo.gms.values():
        if gm.team is not None:
            rows = last_records(fo, gm.team, 1)
            # Only his own season counts: a GM hired this offseason does not inherit his predecessor's results.
            mine = rows[0] if rows and rows[0].get("gm_id") == gm.gm_id else None
            grow_skills(gm, mine, rng)
        gm.age += 1
        if gm.team is not None:
            gm.years_as_gm += 1
            gm.tenure += 1

    for team in getattr(torneo, "squadre", []):
        summit = _summit_plan(team) if team.nome == user_team else None
        plan = fo.plans.get(team.nome)
        if plan is None:
            fo.plans[team.nome] = _new_plan(*(summit or suggest_plan(team, torneo)), year)
            continue
        if summit is not None:
            if summit[0] != plan.state:
                _change(plan, summit[0], summit[1], year, "new_season")
            else:
                plan.seasons_held += 1
            continue
        state, reason = suggest_plan(team, torneo)
        if state == "MIDDLE" and gm_lean(fo.seated_gm(team.nome)) == plan.state:
            state = plan.state  # a middling roster is the GM's call: his lean keeps the plan
        extreme_jump = {state, plan.state} == EXTREMES
        if state != plan.state and (plan.seasons_held >= min_seasons or extreme_jump):
            _change(plan, state, reason, year, "new_season")
        else:
            plan.seasons_held += 1
    mark_season_start(torneo, fo)


LEAN_REASONS = {"REBUILDER": "a builder, he starts the rebuild",
                "PLAYOFF": "a win-now GM, he pushes for the playoffs"}


def gm_lean(gm) -> Optional[str]:
    """Where a GM's philosophy tips a MIDDLE roster: "REBUILDER", "PLAYOFF" or None (no clear lean)."""
    if gm is None:
        return None
    cfg = CONFIG.FRONT_OFFICE
    build = sum(1 for t in gm.traits if t in cfg.HIRING_BUILD_TRAITS)
    win_now = sum(1 for t in gm.traits if t in cfg.HIRING_WIN_NOW_TRAITS)
    if build >= cfg.NEW_GM_LEAN_TRAITS and build > win_now:
        return "REBUILDER"
    if win_now >= cfg.NEW_GM_LEAN_TRAITS and win_now > build:
        return "PLAYOFF"
    return None


def new_gm_plan(torneo, team, gm, year: int) -> None:
    """A GM hired in the offseason brings his read of the roster: the plan is re-chosen at once (a MIDDLE read
    leans on his philosophy), with a reason that names him. Never called for the user's team."""
    fo = ensure_front_office(torneo)
    if team.nome == user_team_name(torneo):
        return
    state, reason = suggest_plan(team, torneo)
    lean = gm_lean(gm) if state == "MIDDLE" else None
    if lean is not None:
        state, reason = lean, f"{reason}; {LEAN_REASONS[lean]}"
    plan = fo.plans.get(team.nome)
    if plan is None:
        plan = fo.plans[team.nome] = _new_plan(state, reason, year)
    _change(plan, state, f"New GM {gm.name}: {reason}", year, "new_gm")
    plan.seasons_held = 0  # hired in the offseason: the coming season-start checkpoint counts his first season


def checkpoint_deadline(torneo) -> None:
    """Trade deadline: only a collapsed or a surprise season changes a plan, and only after enough games."""
    fo = ensure_front_office(torneo)
    cfg = CONFIG.FRONT_OFFICE
    year = current_year(torneo)
    user_team = user_team_name(torneo)
    for team in getattr(torneo, "squadre", []):
        plan = fo.plans.get(team.nome)
        if plan is None or (team.nome == user_team and _summit_plan(team) is not None):
            continue
        wins, losses = int(getattr(team, "vittorie", 0)), int(getattr(team, "sconfitte", 0))
        games = wins + losses
        if games < cfg.PLAN_DEADLINE_MIN_GAMES:
            continue
        win_pct = wins / games
        if plan.state in ("CONTENDER", "PLAYOFF") and win_pct < cfg.PLAN_COLLAPSE_WIN_PCT:
            _change(plan, "REBUILDER", f"Season collapsed ({wins}-{losses}) at the deadline", year, "deadline")
        elif plan.state in ("MIDDLE", "REBUILDER") and win_pct > cfg.PLAN_SURPRISE_WIN_PCT:
            _change(plan, "PLAYOFF", f"Surprise season ({wins}-{losses}): buying at the deadline", year, "deadline")


_ROSTER_STATE_TO_PLAN = {"Contender": "CONTENDER", "Defending Champion": "CONTENDER",
                         "Rebuilding": "REBUILDER", "Rising Star": "REBUILDER"}


def team_plan_state(torneo, team) -> str:
    """The saved plan state of a team (CONTENDER/PLAYOFF/MIDDLE/REBUILDER); without a plan, the roster read."""
    plan = ensure_front_office(torneo).plans.get(team.nome)
    if plan is not None:
        return plan.state
    return _ROSTER_STATE_TO_PLAN.get(torneo._determina_stato_squadra(team), "MIDDLE")


def rebuild_on_schedule(plan) -> bool:
    """A rebuild still inside the usual length of the plan (plus a grace season): owners and coaches stay patient."""
    cfg = CONFIG.FRONT_OFFICE
    return (plan is not None and plan.state == "REBUILDER"
            and plan.seasons_held <= cfg.PLAN_EXPECTED_SEASONS["REBUILDER"] + cfg.COACH_REBUILD_GRACE)
