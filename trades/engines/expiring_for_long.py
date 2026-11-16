"""Expiring for long (catalog #12): a team stuck with a long contract trades him to a team that wants him now.

The partner (NEED_STARTER / WANT_STAR, or DEPTH_NEEDED for a rotation player: CLEAR_LONG_CONTRACT is only
wished for players below the starter band) sends expiring contracts (1 year) for the salary match, plus an asset to
the initiator: a pick, or a young player.
"""
from itertools import combinations
from typing import Iterator, List, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "expiring_for_long"
PARTNER_KINDS = ("NEED_STARTER", "WANT_STAR", "DEPTH_NEEDED")


def _salary(p) -> float:
    return float(p.contract.salario_annuale)


def _expirings(finder: 'TradeFinder', partner: 'Squadra') -> list:
    top = {id(p) for p in sorted(partner.roster, key=lambda p: -p.ovr)[:CONFIG.TRADES.TOP_KEPT_BY_OVR]}
    found = [p for p in finder.get_tradeable_players(partner) if id(p) not in top
             and getattr(p, 'contract', None) is not None and int(p.contract.anni_rimanenti) <= 1]
    return sorted(found, key=lambda p: -_salary(p))


def _assets(finder: 'TradeFinder', partner: 'Squadra') -> list:
    """What the partner can add for the initiator: its picks (cheapest first), then its young players."""
    era, t = finder.era(), CONFIG.TRADES
    picks = [f"{year}:{key}" for year, key in finder._collect_team_picks(partner)]
    youths = [p for p in finder.get_tradeable_players(partner)
              if p.eta <= t.YOUNG_MAX_AGE and p.potenziale >= era.starter and getattr(p, 'contract', None) is not None
              and int(p.contract.anni_rimanenti) > 1]
    youths.sort(key=lambda p: finder.get_strategic_value(p, partner))
    return picks + youths


def _deals(team: 'Squadra', partner: 'Squadra', long, expirings: list, assets: list) -> Iterator[Deal]:
    """Salary-matched packages: the fewest expirings first, the smaller salary first, each with every asset."""
    for size in range(1, CONFIG.TRADES.STAR_UPGRADE_MAX_FILLERS + 1):
        for combo in sorted(combinations(expirings, size), key=lambda c: sum(_salary(p) for p in c)):
            base = [(team.nome, partner.nome, long)] + [(partner.nome, team.nome, p) for p in combo]
            if common.failing_teams(Deal([team, partner], base)):
                continue
            for asset in assets:
                yield Deal([team, partner], base + [(partner.nome, team.nome, asset)])


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind != "CLEAR_LONG_CONTRACT" or not wish.player:
        return False
    long = next((p for p in team.roster if p.nome == wish.player and getattr(p, 'contract', None) is not None), None)
    if long is None:
        return False
    for partner, _top in common.partners_with(finder, PARTNER_KINDS, exclude=[team], vultures_first=True):
        p_wish = next((w for w in finder.wishes_for(partner) if w.kind in PARTNER_KINDS
                       and common.wish_fulfilled(finder, partner, w, [long], [])), None)
        if p_wish is None:
            continue   # he must be what the partner wants right now
        expirings = _expirings(finder, partner)
        assets = _assets(finder, partner)
        if not expirings or not assets:
            continue
        for deal in _deals(team, partner, long, expirings, assets):
            if (common.wish_fulfilled(finder, team, wish, deal.receives(team.nome), deal.gives(team.nome))
                    and common.close_deal(finder, deal, TRADE_TYPE, {team.nome: wish, partner.nome: p_wish})):
                return True
    return False
