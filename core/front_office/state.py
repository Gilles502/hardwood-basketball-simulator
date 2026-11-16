"""League front-office state: every GM (seated or not), which GM sits at which team, team plans and move logs.

Kept on `torneo.front_office`, saved under "front_office". Old saves without it get it built on load,
deterministically from the teams and the season, so a reload never rerolls the GMs.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.config import CONFIG
from core.front_office.models import CpuGM, TeamPlan
from core.front_office.roster import generated_gm, load_roster, roster_team_id


@dataclass
class FrontOfficeState:
    gms: Dict[str, CpuGM] = field(default_factory=dict)
    seats: Dict[str, str] = field(default_factory=dict)      # team name -> gm_id
    plans: Dict[str, Any] = field(default_factory=dict)      # team name -> TeamPlan
    moves: Dict[str, List[dict]] = field(default_factory=dict)
    records: Dict[str, List[dict]] = field(default_factory=dict)      # team -> season rows
    season_marks: Dict[str, dict] = field(default_factory=dict)       # team -> season-start expectations
    version: int = 2

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "gms": {gm_id: gm.to_dict() for gm_id, gm in self.gms.items()},
            "seats": dict(self.seats),
            "plans": {team: plan.to_dict() for team, plan in self.plans.items()},
            "moves": {team: [dict(m) for m in log] for team, log in self.moves.items()},
            "records": {team: [dict(r) for r in rows] for team, rows in self.records.items()},
            "season_marks": {team: {**m, "top8": list(m.get("top8", []))} for team, m in self.season_marks.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FrontOfficeState":
        return cls(
            gms={gm_id: CpuGM.from_dict(g) for gm_id, g in dict(d.get("gms", {})).items()},
            seats=dict(d.get("seats", {})),
            plans={team: TeamPlan.from_dict(p) for team, p in dict(d.get("plans", {})).items()},
            moves={team: [dict(m) for m in log] for team, log in dict(d.get("moves", {})).items()},
            records={team: [dict(r) for r in rows] for team, rows in dict(d.get("records", {})).items()},
            season_marks={team: {**m, "top8": list(m.get("top8", []))}
                          for team, m in dict(d.get("season_marks", {})).items()},
            version=int(d.get("version", 1)),
        )

    def seated_gm(self, team: str) -> Optional[CpuGM]:
        gm_id = self.seats.get(team)
        return self.gms.get(gm_id) if gm_id else None


def start_job(gm: CpuGM, team: str, year: int) -> None:
    """The GM takes a job: opens a career entry and starts the tenure count."""
    gm.career.append({"team": team, "from_year": year, "to_year": None, "end": None,
                      "wins": 0, "losses": 0, "playoffs": 0, "titles": 0})
    gm.team = team
    gm.tenure = 0


def end_job(gm: CpuGM, year: int, end: str) -> None:
    """The GM leaves his job: closes the open career entry with the reason."""
    for entry in reversed(gm.career):
        if entry.get("to_year") is None and entry.get("end") is None:
            entry["to_year"] = year
            entry["end"] = end
            break
    gm.team = None
    gm.tenure = 0
    gm.interim = False


def fill_careers(fo: FrontOfficeState, year: int) -> None:
    """Old saves: every seated GM without a career gets the job he holds now as an open entry."""
    for team, gm_id in fo.seats.items():
        gm = fo.gms.get(gm_id)
        if gm is not None and not gm.career:
            tenure = gm.tenure
            start_job(gm, team, year - tenure)
            gm.tenure = tenure


def current_year(torneo) -> int:
    year = getattr(torneo, "anno_corrente", None)
    if year is None:
        year = getattr(torneo, "starting_year", 2025) + getattr(torneo, "season_number", 1) - 1
    return int(year)


def user_gm_name(torneo) -> str:
    """The name the user's GM goes by in the front-office pages and awards."""
    return getattr(getattr(torneo, "user_gm_profile", None), "name", None) or "You"


# Roles where the user is not the GM: every team, the user's included, is run by a CPU GM.
NO_USER_GM_ROLES = ("spectator", "only_coach")


def user_team_name(torneo) -> Optional[str]:
    """The team run by the user as GM; None in spectator and coach-only modes."""
    if getattr(torneo, "user_role", "gm_coach") in NO_USER_GM_ROLES:
        return None
    team = getattr(torneo, "squadra_giocatore", None)
    return getattr(team, "nome", None) if team is not None else None


def _era(torneo) -> str:
    return "2002" if int(getattr(torneo, "starting_year", 2025)) == 2002 else "modern"


def _league_registry(torneo):
    """The franchise registry of the league this tournament runs: its own, else the active one."""
    registry = getattr(torneo, "franchise_registry", None)
    if registry is None:
        from core.league.registry import get_active_registry
        registry = get_active_registry()
    return registry


def build_front_office(torneo) -> FrontOfficeState:
    """GMs for every team, from the league's GM roster (`staff.gms`) aged by the seasons played (deep-save
    catch-up). A league of another era than the tournament's brings no GMs: every seat gets a generated one."""
    fo_cfg = CONFIG.FRONT_OFFICE
    year = current_year(torneo)
    played = max(0, int(getattr(torneo, "season_number", 1)) - 1)
    registry = _league_registry(torneo)
    if str(registry.meta.get("era") or "") == _era(torneo):
        roster = load_roster(registry)
    else:
        roster = {"starting": [], "arrivals": []}
    user_team = user_team_name(torneo)
    state = FrontOfficeState()

    def aged(entry: dict, in_office: bool) -> CpuGM:
        gm = CpuGM.from_dict(entry)
        gm.age += played
        if in_office:
            gm.years_as_gm += played
        return gm

    originals = {entry["team"]: entry for entry in roster["starting"]}
    # Arrivals past the retirement age by now retired without ever being hired.
    free_arrivals = [gm for gm in (aged(e, False) for e in roster["arrivals"]) if gm.age < fo_cfg.RETIREMENT_AGE]
    for gm in free_arrivals:
        gm.team = None
        state.gms[gm.gm_id] = gm

    team_ids = {getattr(s, "nome", ""): getattr(s, "team_id", "") or "" for s in getattr(torneo, "squadre", [])}
    for team in sorted(team_ids):
        entry = originals.get(roster_team_id(team, team_ids[team], registry))
        original = aged(entry, True) if entry else None
        if original is not None and original.age >= fo_cfg.RETIREMENT_AGE:
            original = None  # retired before this save was opened: replaced below
        if team == user_team:
            if original is not None:  # the user took his job: he waits on the GM market
                original.team = None
                original.available_from_year = None
                state.gms[original.gm_id] = original
            continue
        if original is not None:
            gm = original
        else:
            gm = next((a for a in free_arrivals if a.team is None and a.available_from_year is not None
                       and a.available_from_year <= year), None)
            if gm is None:
                gm = generated_gm(f"{team}|{year}", year)
        start_job(gm, team, year - (played if original is not None else 0))
        if original is not None:
            gm.tenure = played
        state.gms[gm.gm_id] = gm
        state.seats[team] = gm.gm_id

    from core.front_office.plans import seed_missing_plans  # plans.py builds on this module
    seed_missing_plans(torneo, state)
    return state


def ensure_front_office(torneo) -> FrontOfficeState:
    fo = getattr(torneo, "front_office", None)
    if fo is None:
        fo = build_front_office(torneo)
        torneo.front_office = fo
    return fo


def _unseat(fo: FrontOfficeState, team: str, year: int, end: str) -> None:
    gm_id = fo.seats.pop(team, None)
    if gm_id and gm_id in fo.gms:
        end_job(fo.gms[gm_id], year, end)


def _seat_generated(fo: FrontOfficeState, team: str, year: int, interim: bool = True) -> None:
    gm = generated_gm(f"{team}|{year}", year)
    if gm.gm_id in fo.gms:
        # The same made-up GM left this seat earlier this year (seeds are per team and year): hire him again.
        gm = fo.gms[gm.gm_id]
    start_job(gm, team, year)
    gm.interim = interim
    fo.gms[gm.gm_id] = gm
    fo.seats[team] = gm.gm_id


def sync_user_seat(torneo) -> None:
    """Keep the seats right after the user's team changes (switch, job offer, resignation, firing):
    no CPU GM at the user's team, a GM at every other team (a generated one where a seat is empty)."""
    fo = ensure_front_office(torneo)
    year = current_year(torneo)
    user_team = user_team_name(torneo)
    if user_team in fo.seats:
        _unseat(fo, user_team, year, "user_took_over")
    for team in sorted(getattr(s, "nome", "") for s in getattr(torneo, "squadre", [])):
        if team != user_team and team not in fo.seats:
            _seat_generated(fo, team, year)


def user_moves_team(torneo, old_team: Optional[str], new_team: str) -> None:
    """The user takes over `new_team`: its CPU GM goes to the market; `old_team` gets a generated GM."""
    fo = ensure_front_office(torneo)
    year = current_year(torneo)
    _unseat(fo, new_team, year, "user_took_over")
    if old_team and old_team != new_team and old_team not in fo.seats:
        _seat_generated(fo, old_team, year)
