"""End of Season Hub: which of the 9 offseason phases the user is in.

The server state (LEAGUE_STATE) fixes a range of hub phases; some phases share a state (Development & retirements
and Staff & lottery both run in OFFSEASON_COACH_HIRING_START), so a saved marker, offseason_log_data["hub_step"],
says where the user is inside that range. Pure: no Flask, testable on its own.
"""
from typing import Dict, Optional, Tuple

PHASES: Tuple[str, ...] = (
    "Season recap",
    "Contract options",
    "Development & retirements",
    "Staff & lottery",
    "Pre-draft trades",
    "Draft",
    "Free agency",
    "Roster cuts",
    "New season",
)

# Server state -> (first, last) hub phase index it can show.
STATE_PHASES: Dict[str, Tuple[int, int]] = {
    "PLAYOFFS_END": (0, 0),
    "OFFSEASON_OPTIONS_DECISION": (1, 1),
    "OFFSEASON_COACH_HIRING_START": (2, 3),
    "OFFSEASON_TRADES_START": (3, 4),
    "OFFSEASON_DRAFT_START": (5, 5),
    "DRAFT_USER_PICK": (5, 5),
    # The last pick moves the server to free agency, but the user stays on Draft (results) until Next.
    "OFFSEASON_UFA_START": (5, 6),
    "OFFSEASON_CUTDOWN_START": (7, 7),
    "OFFSEASON_COMPLETE": (8, 8),
}


def clamp_hub_step(league_state: str, step: Optional[int]) -> Optional[int]:
    """The marker brought inside the phases this state allows; None when the hub is closed."""
    span = STATE_PHASES.get(league_state)
    if span is None:
        return None
    first, last = span
    if step is None:
        return first
    return max(first, min(last, int(step)))


def current_phase(league_state: str, hub_step: Optional[int]) -> Optional[int]:
    return clamp_hub_step(league_state, hub_step)


def end_season_status(league_state: str, log: Optional[Dict]) -> Dict:
    span = STATE_PHASES.get(league_state)
    if span is None:
        return {"open": False, "phase": None, "first": None, "last": None}
    return {"open": True, "phase": current_phase(league_state, (log or {}).get("hub_step")), "first": span[0], "last": span[1]}


def roster_snapshot(team) -> Dict:
    """The user's roster as it stands when the offseason opens, for the New season summary."""
    players = []
    for p in team.roster:
        salary = round(p.contract.salario_annuale, 2) if getattr(p, 'contract', None) else 0.0
        players.append({"name": p.nome, "role": p.ruolo, "ovr": p.ovr, "salary": salary, "age": getattr(p, 'eta', None)})
    return {"payroll": round(sum(p["salary"] for p in players), 2), "players": players}


def league_snapshot(teams) -> Dict:
    """Every team's roster strength and rank when the offseason opens, for the New season power rankings."""
    from core.end_season_views import team_strength
    strength = {t.nome: team_strength([p.ovr for p in t.roster]) for t in teams}
    ranked = sorted(strength, key=lambda name: (-strength[name], name))
    return {name: {"strength": strength[name], "rank": i + 1} for i, name in enumerate(ranked)}


def remember_market(torneo, free_agents, previous_teams) -> None:
    """Keep the offseason free-agent market on the tournament so saves carry it (it used to live only in a server
    global, so a save made between the options and the end of free agency reloaded with an empty market)."""
    torneo.nuovi_free_agents = list(free_agents)
    if not isinstance(getattr(torneo, 'offseason_log_data', None), dict):
        torneo.offseason_log_data = {}
    torneo.offseason_log_data["previous_teams"] = {name: team.nome for name, team in (previous_teams or {}).items() if team}


def restore_previous_teams(torneo) -> Dict:
    """Player name -> team object they left, rebuilt from the saved names (teams that no longer exist are skipped)."""
    names = (getattr(torneo, 'offseason_log_data', None) or {}).get("previous_teams") or {}
    teams = {t.nome: t for t in getattr(torneo, 'squadre', [])}
    return {player: teams[team] for player, team in names.items() if team in teams}
