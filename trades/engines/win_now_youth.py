"""Win-now for youth (catalog #2): a team with NEED_STARTER sends a high-potential prospect for a prime veteran.

Initiator: a prospect (age <= YOUNG_MAX_AGE, potential >= era.ovr_at(80), OVR <= era.ovr_at(78)). Partner: a
WANT_YOUTH team holding a veteran in PRIME_VET_AGES, OVR era.ovr_at(78)..era.ovr_at(83), at the needed role.
Today's rule from TradeFinder.attempt_win_now_for_prospect_trade, on wishes.
"""
from typing import TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from core.roles import normalize_role
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "win_now_youth"
PARTNER_KINDS = ("WANT_YOUTH",)


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind != "NEED_STARTER" or not wish.role:
        return False
    t, era = CONFIG.TRADES, finder.era()
    prospects = sorted(
        (p for p in finder.get_tradeable_players(team)
         if p.eta <= t.YOUNG_MAX_AGE and p.potenziale >= era.ovr_at(t.WIN_NOW_PROSPECT_POT_OLD)
         and p.ovr <= era.ovr_at(t.WIN_NOW_PROSPECT_MAX_OVR_OLD) and getattr(p, 'contract', None) is not None),
        key=lambda p: -p.potenziale)
    if not prospects:
        return False
    lo, hi = (era.ovr_at(n) for n in t.WIN_NOW_VET_OVR_RANGE_OLD)
    age_lo, age_hi = t.PRIME_VET_AGES

    for partner, p_wish in common.partners_with(finder, PARTNER_KINDS, exclude=[team]):
        vets = sorted(
            (p for p in finder.get_tradeable_players(partner, allow_stars=True)
             if normalize_role(p.ruolo) == wish.role and age_lo <= p.eta <= age_hi and lo <= p.ovr <= hi
             and getattr(p, 'contract', None) is not None),
            key=lambda p: -p.ovr)
        for vet in vets:
            for prospect in prospects:
                if not (common.wish_fulfilled(finder, team, wish, [vet], [prospect])
                        and common.wish_fulfilled(finder, partner, p_wish, [prospect], [vet])):
                    continue
                deal = Deal([team, partner], [(team.nome, partner.nome, prospect), (partner.nome, team.nome, vet)])
                if common.close_deal(finder, deal, TRADE_TYPE, {team.nome: wish, partner.nome: p_wish}):
                    return True
    return False
