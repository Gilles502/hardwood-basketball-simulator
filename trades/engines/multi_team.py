"""The 3/4-team extension: a two-team deal stuck on salaries takes in a third team, then a fourth.

A team joins only for a wish of its own. The rule, for a team whose salary check fails (it takes in too much
for what it sends): it sends one more contract (its least valuable tradeable player outside the deal) to a team
with real room, which sends nothing back; when that team's wish asks for picks (ABSORB_SALARY, WANT_PICKS) the
stuck team adds its cheapest pick that fulfils it. The extra team is taken only when the stuck team and the
extra team both pass their salary checks and the extra team's wish is fulfilled.
"""
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

# Wishes that let a team join a deal: room for salary, picks, depth or a starter.
EXTENSION_KINDS: Tuple[str, ...] = ("ABSORB_SALARY", "WANT_PICKS", "DEPTH_NEEDED", "NEED_STARTER")
# ...of which these are paid with a pick by the stuck team (the others are served by the contract itself).
PAID_KINDS: Tuple[str, ...] = ("ABSORB_SALARY", "WANT_PICKS")


def _dump_candidates(finder: 'TradeFinder', team: 'Squadra', deal: Deal) -> list:
    """The team's tradeable players outside the deal, least valuable to it first."""
    moving = {id(asset) for _src, _dst, asset in deal.moves}
    players = [p for p in finder.get_tradeable_players(team)
               if id(p) not in moving and getattr(p, 'contract', None) is not None]
    return sorted(players, key=lambda p: (finder.get_strategic_value(p, team), p.ovr))


def _payment_picks(finder: 'TradeFinder', team: 'Squadra', deal: Deal) -> List[str]:
    """The team's picks outside the deal ("N:R1-X", N relative), cheapest first."""
    moving = {asset for _src, _dst, asset in deal.moves if isinstance(asset, str)}
    return [f"{year}:{key}" for year, key in finder._collect_team_picks(team) if f"{year}:{key}" not in moving]


def _absorb(finder: 'TradeFinder', deal: Deal, stuck: 'Squadra') -> Optional[Tuple[Deal, 'Squadra', Wish]]:
    """One extra team that takes a contract off `stuck`'s hands for a wish of its own."""
    dumps = _dump_candidates(finder, stuck, deal)
    if not dumps:
        return None
    picks = _payment_picks(finder, stuck, deal)
    for team, _top in common.partners_with(finder, EXTENSION_KINDS, exclude=deal.teams):
        team_wishes = [w for w in finder.wishes_for(team) if w.kind in EXTENSION_KINDS]
        for player in dumps:
            trial = deal.with_team(team, [(stuck.nome, team.nome, player)])
            if not (common.salary_ok(stuck, trial) and common.salary_ok(team, trial)):
                continue
            for wish in team_wishes:
                for pick in [None] + (picks if wish.kind in PAID_KINDS else []):
                    paid = trial if pick is None else Deal(trial.teams, trial.moves + [(stuck.nome, team.nome, pick)],
                                                           reason=trial.reason)
                    if common.wish_fulfilled(finder, team, wish, paid.receives(team.nome), paid.gives(team.nome)):
                        return paid, team, wish
    return None


def extend(finder: 'TradeFinder', deal: Deal, wishes: Dict[str, Wish]) -> Optional[Deal]:
    """The deal with one or two extra teams whose salaries all match, or None.

    On success the extra teams' wishes are written into `wishes` (team name -> wish fulfilled). The user's
    own team never has a contract moved for it."""
    added: Dict[str, Wish] = {}
    current = deal
    while len(current.teams) < CONFIG.TRADES.MAX_DEAL_TEAMS:
        stuck = [t for t in common.failing_teams(current) if not finder._is_user_team(t)]
        if not stuck:
            break
        step = next((s for s in (_absorb(finder, current, t) for t in stuck) if s is not None), None)
        if step is None:
            return None
        current, team, wish = step
        added[team.nome] = wish
    if not added or common.failing_teams(current):
        return None
    wishes.update(added)
    return current
