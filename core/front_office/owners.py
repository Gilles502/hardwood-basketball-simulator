"""The owner's verdict on the GM: seasons of failure (after a coaching change, or a long run) get him fired.

Each season is judged by the plan it started with (`plan_start`, older rows: `plan`): a win-now season below
expectations is a failure even when the team collapsed into a rebuild at the deadline; rebuild seasons only count
for the stalled-rebuild rule."""
from typing import List, Optional

from core.config import CONFIG, normalize_owner_personality
from core.front_office.plans import rebuild_on_schedule, team_plan_state
from core.front_office.state import user_team_name

WIN_NOW_PLANS = ("CONTENDER", "PLAYOFF")


def _below(row: dict) -> bool:
    return row.get("expected", 0) - row.get("wins", 0) >= CONFIG.FRONT_OFFICE.GM_FIRE_BELOW_BY


def _start_plan(row: dict) -> Optional[str]:
    return row.get("plan_start") or row.get("plan")


def _failed(row: dict) -> bool:
    """A win-now season (by its season-start plan) well below expectations."""
    return _start_plan(row) in WIN_NOW_PLANS and _below(row)


def _won_title(torneo, team, rows: List[dict]) -> bool:
    champion = getattr(getattr(torneo, "campione", None), "nome", None)
    return champion == team.nome or bool(rows and rows[-1].get("champion"))


def _seasons(n: int) -> str:
    return f"{n} season" if n == 1 else f"{n} seasons"


def _after_coach_change(rows: List[dict], seasons: int) -> Optional[str]:
    for i, row in enumerate(rows):
        tail = rows[i + 1:]
        if row.get("coach_fired") and len(tail) >= seasons and all(_failed(r) for r in tail):
            return f"{_seasons(len(tail))} below expectations after the coaching change"
    return None


def _long_run(rows: List[dict], seasons: int) -> Optional[str]:
    if len(rows) >= seasons and all(_failed(r) for r in rows[-seasons:]):
        return f"{seasons} straight {'season' if seasons == 1 else 'seasons'} well below expectations"
    return None


def gm_fire_reason(torneo, fo, team, gm, coach_only_user_team: bool) -> Optional[str]:
    """A readable reason when the owner wants this GM out, None to keep him. The caller rolls `fire_gm_roll`."""
    cfg = CONFIG.FRONT_OFFICE
    if gm.interim or gm.tenure < cfg.GM_FIRE_MIN_TENURE or team.nome == user_team_name(torneo):
        return None
    rows = [r for r in fo.records.get(team.nome, []) if r.get("gm_id") == gm.gm_id]
    if _won_title(torneo, team, rows):
        return None

    owner = normalize_owner_personality(getattr(team, "personalita_proprietario", None))
    shift = cfg.GM_FIRE_PATIENCE_SHIFT.get(owner, 0)

    long_run = _long_run(rows, max(1, cfg.GM_FIRE_LONG_RUN + shift))
    if coach_only_user_team:
        return long_run
    reason = _after_coach_change(rows, max(1, cfg.GM_FIRE_AFTER_COACH_SEASONS + shift)) or long_run
    if reason:
        return reason

    recent = rows[-3:]
    if (len(recent) == 3 and all(_start_plan(r) == "REBUILDER" for r in recent)
            and team_plan_state(torneo, team) == "REBUILDER"
            and not rebuild_on_schedule(fo.plans.get(team.nome))
            and recent[-1].get("wins", 0) <= recent[0].get("wins", 0)):
        return "The rebuild has run past its schedule and the wins are not climbing"
    return None


def fire_gm_roll(reason: Optional[str], rng) -> bool:
    """With a reason, the owner acts GM_FIRE_CHANCE of the time: not every case is automatic."""
    return reason is not None and rng.random() < CONFIG.FRONT_OFFICE.GM_FIRE_CHANCE
