"""Positional swap (catalog #4): two teams with crossed hole and surplus trade one player each.

Initiator: NEED_STARTER at role X, with surplus at role Y (a ROLE_CONGESTION wish, or enough good players there).
Partner: NEED_STARTER or DEPTH_NEEDED at Y, with surplus at X. 1-for-1, both players in the swap band, OVR gap
at most POSITIONAL_SWAP_MAX_GAP (today's rule from TradeFinder.attempt_positional_swap_trade, on era lines).
"""
from typing import Dict, List, Set, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from core.roles import normalize_role
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "positional_swap"
PARTNER_KINDS = ("NEED_STARTER", "DEPTH_NEEDED")


def surplus_roles(finder: 'TradeFinder', team: 'Squadra') -> Set[str]:
    """Roles the team can spare a player at: a ROLE_CONGESTION wish, or enough players at the surplus line."""
    t = CONFIG.TRADES
    line = finder.era().ovr_at(t.POSITIONAL_SWAP_SURPLUS_OVR_OLD)
    roles = {w.role for w in finder.wishes_for(team) if w.kind == "ROLE_CONGESTION"}
    for role in t.WISH_ROLES:
        if sum(1 for p in team.roster if normalize_role(p.ruolo) == role and p.ovr >= line) >= t.POSITIONAL_SWAP_SURPLUS_COUNT:
            roles.add(role)
    return roles


def _swappable(finder: 'TradeFinder', team: 'Squadra', roles: Set[str]) -> Dict[str, List]:
    """Tradeable players in the swap band at these roles, best first."""
    lo, hi = (finder.era().ovr_at(n) for n in CONFIG.TRADES.POSITIONAL_SWAP_OVR_RANGE_OLD)
    out: Dict[str, List] = {role: [] for role in roles}
    for p in finder.get_tradeable_players(team, allow_stars=True):
        role = normalize_role(p.ruolo)
        if role in out and lo <= p.ovr <= hi and getattr(p, 'contract', None) is not None:
            out[role].append(p)
    for players in out.values():
        players.sort(key=lambda p: -p.ovr)
    return out


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind != "NEED_STARTER" or not wish.role:
        return False
    need = wish.role
    spare = surplus_roles(finder, team) - {need}
    mine = _swappable(finder, team, spare)
    if not any(mine.values()):
        return False
    gap = CONFIG.TRADES.POSITIONAL_SWAP_MAX_GAP

    for partner, _top in common.partners_with(finder, PARTNER_KINDS, exclude=[team]):
        if need not in surplus_roles(finder, partner):
            continue
        theirs = _swappable(finder, partner, {need})[need]
        if not theirs:
            continue
        deal = None
        for p_wish in finder.wishes_for(partner):
            if p_wish.kind not in PARTNER_KINDS or p_wish.role not in spare:
                continue
            for out in mine[p_wish.role]:
                for back in sorted(theirs, key=lambda p: abs(p.ovr - out.ovr)):
                    if abs(back.ovr - out.ovr) > gap:
                        break
                    if (common.wish_fulfilled(finder, team, wish, [back], [out])
                            and common.wish_fulfilled(finder, partner, p_wish, [out], [back])):
                        deal = (Deal([team, partner], [(team.nome, partner.nome, out), (partner.nome, team.nome, back)]),
                                p_wish)
                        break
                if deal:
                    break
            if deal:
                break
        # One offer per partner: the best crossed pair; the price question decides.
        if deal and common.close_deal(finder, deal[0], TRADE_TYPE, {team.nome: wish, partner.nome: deal[1]}):
            return True
    return False
