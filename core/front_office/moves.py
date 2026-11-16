"""Each CPU team's log of the moves made for its plan: trades, signings, players let go, draft picks.

Thin hooks in the trade, free-agency and draft code call these once the move is final.
"""
from typing import Any, Iterable, List

from core.config import CONFIG
from core.front_office.state import user_team_name

KINDS = ("trade", "signing", "let_walk", "draft")


def _window(torneo, kind: str) -> str:
    if kind == "draft":
        return "Draft"
    if kind in ("signing", "let_walk"):
        return "FA"
    if getattr(torneo, "_deadline_window", False):
        return "Deadline"
    return "Offseason" if getattr(torneo, "fase_torneo", "SEASON") == "OFFSEASON" else "Season"


def record_move(torneo, team_name: str, kind: str, text: str) -> None:
    """Append a move to a CPU team's log (no-op for the user's team or before the front office exists)."""
    fo = getattr(torneo, "front_office", None)
    if fo is None or kind not in KINDS or team_name == user_team_name(torneo):
        return
    plan = fo.plans.get(team_name)
    log = fo.moves.setdefault(team_name, [])
    log.append({
        "season": int(getattr(torneo, "season_number", 1)),
        "year": int(getattr(torneo, "anno_corrente", 0) or 0),
        "window": _window(torneo, kind),
        "kind": kind,
        "text": text,
        "plan": plan.state if plan is not None else None,
    })
    keep = CONFIG.FRONT_OFFICE.MOVES_KEEP_PER_TEAM
    if len(log) > keep:
        del log[:-keep]


def asset_label(torneo, asset: Any, team_name: str) -> str:
    """A player's name, or a pick as "2004 R1" (own pick) / "2004 R1 (Team Name)" (another team's)."""
    name = getattr(asset, "nome", None)
    if name is not None:
        return name
    text = str(asset)
    pick_key, draft_year = text, None
    if ":" in text:
        year_str, pick_key = text.split(":", 1)
        try:
            draft_year = (int(getattr(torneo, "starting_year", 2025)) + int(getattr(torneo, "season_number", 1))
                          + int(year_str) - 1)
        except ValueError:
            return text
    if not (pick_key.startswith("R1-") or pick_key.startswith("R2-")):
        return text
    round_code, origin = pick_key.split("-", 1)
    label = f"{draft_year} {round_code}" if draft_year else round_code
    return label if origin == team_name else f"{label} ({origin})"


def _labels(torneo, assets: Iterable[Any], team_name: str) -> str:
    return ", ".join(asset_label(torneo, a, team_name) for a in assets) or "nothing"


def record_trade(torneo, sides: List[dict]) -> None:
    """One "trade" move per team: sides = [{"team": Squadra, "gives": [...], "receives": [...]}]."""
    for side in sides:
        name = side["team"].nome
        got = _labels(torneo, side.get("receives", []), name)
        gave = _labels(torneo, side.get("gives", []), name)
        record_move(torneo, name, "trade", f"Got {got} for {gave}")


def record_signing(torneo, team, player, salary: float, years: int, tipo: str, previous_team=None) -> None:
    """A free-agent signing, and "let walk" for the team he left. Roster-saver signings are not logged."""
    if str(tipo).upper().startswith("ROSTER SAVER"):
        return
    record_move(torneo, team.nome, "signing",
                f"Signed {player.nome} ({player.eta}, {player.ovr} OVR) for {years} yrs at ${salary:.1f}M")
    if previous_team is not None and previous_team.nome != team.nome:
        record_move(torneo, previous_team.nome, "let_walk", f"Let {player.nome} ({player.eta}) walk")


def record_draft_pick(torneo, team_name: str, player, overall_pick: int) -> None:
    record_move(torneo, team_name, "draft", f"Drafted {player.nome} at #{overall_pick}")
