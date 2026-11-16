"""Star upgrade (catalog #1): a buyer with NEED_STARTER or WANT_STAR takes a better player from a seller.

Recorded as `star_upgrade` for WANT_STAR and `starter_upgrade` for NEED_STARTER.

Partners are teams with a selling wish (SELL_VETERANS, WANT_PICKS, WANT_YOUTH, SHED_TAX) that hold a target: a
starter at the needed role (`era.starter`), or a star (`era.star`) for WANT_STAR. The buyer pays with what the
seller's wish asks for (picks, young players), then matches salaries with fillers: first the plain package, then
up to STAR_UPGRADE_MAX_FILLERS rotation contracts outside the buyer's top 5 by OVR. A package stuck on salaries goes to
`close_deal`, whose 3/4-team extension can still rescue it (recorded as facilitated_3team).
"""
from itertools import combinations, zip_longest
from typing import Iterator, List, Optional, Tuple, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from core.roles import normalize_role
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "star_upgrade"
STARTER_TYPE = "starter_upgrade"
BUYER_KINDS = ("NEED_STARTER", "WANT_STAR")
PARTNER_KINDS = ("SELL_VETERANS", "WANT_PICKS", "WANT_YOUTH", "SHED_TAX")
YOUTH_KINDS = ("WANT_YOUTH",)   # the partner wishes that are asked for young players before picks


def _targets(finder: 'TradeFinder', team: 'Squadra', partner: 'Squadra', wish: Wish) -> list:
    """The partner's players that would fulfil the buyer's wish, best first."""
    era = finder.era()
    if wish.kind == "WANT_STAR":
        ok = lambda p: p.ovr >= era.star
    else:
        best = max((p.ovr for p in team.roster if normalize_role(p.ruolo) == wish.role), default=0)
        ok = lambda p: (normalize_role(p.ruolo) == wish.role and p.ovr >= era.starter
                      and p.ovr >= best + CONFIG.TRADES.STAR_UPGRADE_MIN_GAP)
    found = [p for p in finder.get_tradeable_players(partner, allow_stars=True, include_untouchables=True)
             if getattr(p, 'contract', None) is not None and ok(p)]
    return sorted(found, key=lambda p: -p.ovr)


def _sweetener_lists(finder: 'TradeFinder', team: 'Squadra', partner_wish: Wish) -> List[list]:
    """Ordered offers (firsts and young players) the buyer can make, cheapest first and richest first.

    What the partner's wish asks for comes first, alternating with the other kind. Seconds are never offered."""
    era, t = finder.era(), CONFIG.TRADES
    picks = [f"{year}:{key}" for year, key in finder._collect_team_picks(team)]   # cheapest first
    picks = [k for k in picks if ":R1-" in k]
    youths = [p for p in finder.get_tradeable_players(team)
              if p.eta <= t.YOUNG_MAX_AGE and p.potenziale >= era.starter and getattr(p, 'contract', None) is not None]
    youths.sort(key=lambda p: finder.get_strategic_value(p, team))
    lists = []
    for flip in (False, True):
        pool_picks = (list(reversed(picks)) if flip else picks)
        pool_youths = (list(reversed(youths)) if flip else youths)
        first, second = (pool_youths, pool_picks) if partner_wish.kind in YOUTH_KINDS else (pool_picks, pool_youths)
        lists.append([a for pair in zip_longest(first, second) for a in pair if a is not None])
    return lists


def _packages(finder: 'TradeFinder', team: 'Squadra', partner_wish: Wish) -> Iterator[list]:
    seen = set()
    for offers in _sweetener_lists(finder, team, partner_wish):
        for size in range(1, CONFIG.TRADES.STAR_UPGRADE_MAX_SWEETENERS + 1):
            package = offers[:size]
            key = frozenset(a if isinstance(a, str) else id(a) for a in package)
            if len(package) == size and key not in seen:
                seen.add(key)
                yield package


def _fillers(finder: 'TradeFinder', team: 'Squadra', taken: list) -> list:
    """Rotation contracts outside the buyer's top 5 by OVR, biggest salary first."""
    return common.rotation_fillers(finder, team, taken)


def _deal(team: 'Squadra', partner: 'Squadra', target, assets: list) -> Deal:
    return Deal([team, partner], [(team.nome, partner.nome, a) for a in assets] + [(partner.nome, team.nome, target)])


def _matching(finder: 'TradeFinder', team: 'Squadra', partner: 'Squadra', target, package: list) -> Iterator[Deal]:
    """The package as is when salaries match, else with 1, 2 or 3 filler contracts that make them match."""
    moves = [(team.nome, partner.nome, a) for a in package] + [(partner.nome, team.nome, target)]
    yield from common.matched_by_fillers(team, partner, moves, _fillers(finder, team, package))


def _fulfils_both(finder, team, wish, partner, p_wish, deal: Deal) -> bool:
    return (common.wish_fulfilled(finder, team, wish, deal.receives(team.nome), deal.gives(team.nome))
            and common.wish_fulfilled(finder, partner, p_wish, deal.receives(partner.nome), deal.gives(partner.nome)))


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind not in BUYER_KINDS or (wish.kind == "NEED_STARTER" and not wish.role):
        return False
    trade_type = STARTER_TYPE if wish.kind == "NEED_STARTER" else TRADE_TYPE
    for partner, _top in common.partners_with(finder, PARTNER_KINDS, exclude=[team]):
        targets = _targets(finder, team, partner, wish)
        if not targets:
            continue
        stuck: List[Tuple[Deal, Wish]] = []
        for p_wish in [w for w in finder.wishes_for(partner) if w.kind in PARTNER_KINDS]:
            packages = list(_packages(finder, team, p_wish))   # depends on the buyer and the wish only
            for target in targets:
                for package in packages:
                    plain = _deal(team, partner, target, package)
                    if not _fulfils_both(finder, team, wish, partner, p_wish, plain):
                        continue
                    if common.failing_teams(plain):
                        stuck.append((plain, p_wish))
                    for deal in _matching(finder, team, partner, target, package):
                        if _fulfils_both(finder, team, wish, partner, p_wish, deal) and common.close_deal(
                                finder, deal, trade_type, {team.nome: wish, partner.nome: p_wish}):
                            return True
        # Nothing matched on its own: the plain packages that are stuck on salaries may get a third team.
        for deal, p_wish in stuck:
            if common.close_deal(finder, deal, trade_type, {team.nome: wish, partner.nome: p_wish}):
                return True
    return False
