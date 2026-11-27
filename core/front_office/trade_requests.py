"""Trade requests: frustration that builds up over time, and the request of an important player.

Every player carries a saved meter (`frustration`, 0-100) that the new season does not reset. It rises each week a
player is stuck (low morale on a team going nowhere) and falls when things get better. At CONFIG.TRADE_REQUESTS.
REQUEST_AT an important player (OVR >= era.ovr_at(REQUEST_MIN_OVR_OLD)) asks to be traded (`trade_request`). The
request holds until he is traded or the meter falls back under WITHDRAW_BELOW. `wishes.wants_out` reads it.
A frustrated player under the line does not ask out: he refuses to re-sign (`contracts.walk_reason`).
"""
import logging
from typing import List, Optional, Tuple

from core.config import CONFIG
from core.front_office.era_lines import EraLines, era_lines_for
from core.front_office.wishes import young_future
from core.news_generator import add_news
from core.roles import normalize_role

__all__ = ["can_request", "is_stuck", "tick", "season_end", "fed_up", "clear_request", "weekly_tick", "end_of_season",
           "tick_due", "summer_due", "own_value_share",
           "request_list", "REQUESTED", "WITHDRAWN"]

log = logging.getLogger(__name__)
main_log = logging.getLogger('main_sim')

REQUESTED = "requested"
WITHDRAWN = "withdrawn"


def can_request(player, era: EraLines) -> bool:
    """Important enough to ask out: OVR at or above the era-mapped request line."""
    return int(player.ovr) >= era.ovr_at(CONFIG.TRADE_REQUESTS.REQUEST_MIN_OVR_OLD)


def is_stuck(player, team, *, era: EraLines, plan: str, win_pct: float, games: int) -> bool:
    """Unhappy on a team going nowhere: low morale, a losing (or rebuilding) team, no young core to wait for."""
    c = CONFIG.TRADE_REQUESTS
    if player.morale >= c.UNHAPPY_MORALE:
        return False
    losing = plan == "REBUILDER" or (games >= c.MIN_GAMES and win_pct < c.LOSING_WIN_PCT)
    return losing and not young_future(team, era)


def clear_request(player) -> None:
    """A fresh start (a trade, a new contract): no request, an empty meter, no cached demand."""
    player.frustration, player.trade_request, player.trade_request_since = 0.0, False, ""
    player.trade_request_weeks, player.trade_block_by_request = 0, False
    player._wants_out = False


def own_value_share(player) -> float:
    """What a player who asked out is worth to his own team: OWN_VALUE_SHARE, lower each week he waits."""
    c = CONFIG.TRADE_REQUESTS
    weeks = int(getattr(player, 'trade_request_weeks', 0) or 0)
    return max(c.OWN_VALUE_FLOOR, c.OWN_VALUE_SHARE - c.OWN_VALUE_DECAY_PER_WEEK * weeks)


def fed_up(player) -> bool:
    return float(getattr(player, 'frustration', 0.0)) >= CONFIG.TRADE_REQUESTS.WALK_FRUSTRATION


def _add(player, delta: float) -> None:
    player.frustration = max(0.0, min(100.0, float(getattr(player, 'frustration', 0.0)) + delta))


def _settle(player, era: EraLines, since: str) -> Optional[str]:
    """Opens or withdraws the request after the meter moved."""
    c = CONFIG.TRADE_REQUESTS
    requesting = bool(getattr(player, 'trade_request', False))
    if not requesting and player.frustration >= c.REQUEST_AT and can_request(player, era):
        player.trade_request, player.trade_request_since = True, since
        return REQUESTED
    if requesting and player.frustration < c.WITHDRAW_BELOW:
        player.trade_request, player.trade_request_since, player.trade_request_weeks = False, "", 0
        if getattr(player, 'trade_block_by_request', False):   # the request put him on the block, not the user
            player.on_trade_block, player.trade_block_by_request = False, False
        return WITHDRAWN
    return None


def tick(player, team, *, era: EraLines, plan: str, win_pct: float, games: int, since: str) -> Optional[str]:
    """One weekly check in the regular season. Returns REQUESTED, WITHDRAWN or None."""
    c = CONFIG.TRADE_REQUESTS
    if is_stuck(player, team, era=era, plan=plan, win_pct=win_pct, games=games):
        _add(player, c.RISE_PER_TICK)
    elif player.morale >= c.HAPPY_MORALE or (games >= c.MIN_GAMES and win_pct >= c.WINNING_WIN_PCT):
        _add(player, -c.FALL_PER_TICK)
    else:
        _add(player, -c.DRIFT_PER_TICK)
    result = _settle(player, era, since)
    if result is None and getattr(player, 'trade_request', False):   # one more week on the block: his price falls
        player.trade_request_weeks = int(getattr(player, 'trade_request_weeks', 0) or 0) + 1
    return result


def season_end(player, team, *, era: EraLines, made_playoffs: bool, since: str) -> Optional[str]:
    """The end-of-season check: missing the playoffs adds, making them relieves."""
    c = CONFIG.TRADE_REQUESTS
    _add(player, -c.PLAYOFFS_RELIEF if made_playoffs else c.MISSED_PLAYOFFS_BUMP)
    return _settle(player, era, since)


# ---------------------------------------------------------------- the league
Event = Tuple[object, object, str]   # (player, team, REQUESTED | WITHDRAWN)


def _plan(torneo, team) -> str:
    fo = getattr(torneo, 'front_office', None)
    plan = fo.plans.get(team.nome) if fo is not None else None
    return getattr(plan, 'state', None) or "MIDDLE"


def _user_team(torneo):
    return None if getattr(torneo, 'is_spectator', False) else getattr(torneo, 'squadra_giocatore', None)


def _announce(torneo, player, team) -> None:
    """News of a new request; a user player also goes on the trade block so the league makes offers."""
    user = _user_team(torneo)
    if user is not None and user.nome == team.nome and not getattr(player, 'on_trade_block', False):
        player.on_trade_block, player.trade_block_by_request = True, True
    years = getattr(getattr(player, 'contract', None), 'anni_rimanenti', None)
    record = f"{team.vittorie}-{team.sconfitte}"
    tail = (" He is in the last year of his contract." if years is not None and years <= 1
            else f" He has {years} years left on his contract." if years else "")
    body = f"{player.nome} has asked the {team.nome} ({record}) to trade him.{tail}"
    try:   # news never break the simulation
        add_news("rumor", f"{player.nome} asks the {team.nome} for a trade", body, teams=[team.nome],
                 season=getattr(torneo, 'season_number', None), kind="rumor", tier=3, players=[player.nome],
                 details={"trade_request": True})
    except Exception as exc:
        log.warning("trade request news failed: %s", exc)


def _run(torneo, step) -> List[Event]:
    era = era_lines_for(torneo)
    events: List[Event] = []
    for team in getattr(torneo, 'squadre', []):
        for player in list(team.roster):
            result = step(player, team, era)
            if result is None:
                continue
            events.append((player, team, result))
            main_log.warning(f"TRADE REQUEST {result}: {player.nome} ({int(player.ovr)}, {player.eta}) at "
                             f"{team.nome} {team.vittorie}-{team.sconfitte}")
            if result == REQUESTED:
                _announce(torneo, player, team)
    return events


def tick_due(torneo, day_index: int) -> bool:
    """True once per (season, day): the weekly check never runs twice for one day, even after a reload."""
    key = f"{getattr(torneo, 'season_number', 0)}:{day_index}"
    if getattr(torneo, 'trade_requests_last_tick', None) == key:
        return False
    torneo.trade_requests_last_tick = key
    return True


def summer_due(torneo) -> bool:
    """True once per season for the summer check (saved with the league)."""
    season = getattr(torneo, 'season_number', 0)
    if getattr(torneo, 'trade_requests_summer', None) == season:
        return False
    torneo.trade_requests_summer = season
    return True


def weekly_tick(torneo) -> List[Event]:
    """The weekly regular-season check for every player of every team (user team included)."""
    since = f"Season {torneo.anno_corrente}"

    def step(player, team, era):
        games = team.vittorie + team.sconfitte
        win_pct = team.vittorie / games if games else 0.5
        return tick(player, team, era=era, plan=_plan(torneo, team), win_pct=win_pct, games=games, since=since)
    return _run(torneo, step)


def end_of_season(torneo) -> List[Event]:
    """The summer check: teams in `torneo.playoff_teams` get relief, the others a bump."""
    playoff = {t.nome for conf in (getattr(torneo, 'playoff_teams', None) or {}).values() for t in conf}
    since = f"Summer {torneo.anno_corrente}"
    return _run(torneo, lambda player, team, era: season_end(
        player, team, era=era, made_playoffs=team.nome in playoff, since=since))


def request_list(torneo) -> list:
    """Every player with an open trade request, best first (GET /api/trade-requests)."""
    user = _user_team(torneo)
    rows = []
    for team in getattr(torneo, 'squadre', []):
        for p in team.roster:
            if not getattr(p, 'trade_request', False):
                continue
            contract = getattr(p, 'contract', None)
            rows.append({"player": p.nome, "team": team.nome, "role": normalize_role(getattr(p, 'ruolo', '')),
                         "ovr": int(p.ovr), "age": int(p.eta),
                         "salary": round(float(contract.salario_annuale), 2) if contract else 0.0,
                         "years": int(contract.anni_rimanenti) if contract else 0,
                         "since": getattr(p, 'trade_request_since', ''),
                         "is_user_team": user is not None and user.nome == team.nome})
    rows.sort(key=lambda r: (-r["ovr"], r["player"]))
    return rows
