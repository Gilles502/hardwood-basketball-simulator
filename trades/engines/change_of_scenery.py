"""Change of scenery (catalog #14): two unhappy players swap teams, 1-for-1, at about the same value.

Initiator: UNHAPPY_PLAYER. Partner: UNHAPPY_PLAYER too, for a player whose value is within
BENCH_SHUFFLE_VALUE_GAP of the one he gets (each team values the player it receives).
"""
from typing import TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "change_of_scenery"
PARTNER_KINDS = ("UNHAPPY_PLAYER",)


def _named(finder: 'TradeFinder', team: 'Squadra', name: str):
    return next((p for p in finder.get_tradeable_players(team)
                 if p.nome == name and getattr(p, 'contract', None) is not None), None)


def _close_in_value(finder: 'TradeFinder', team: 'Squadra', mine, partner: 'Squadra', theirs) -> bool:
    """The player each side receives is worth about the same to the side that gets him."""
    v_mine = finder.get_strategic_value(mine, partner)
    v_theirs = finder.get_strategic_value(theirs, team)
    return abs(v_mine - v_theirs) <= CONFIG.FRONT_OFFICE.BENCH_SHUFFLE_VALUE_GAP * max(v_mine, v_theirs)


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind != "UNHAPPY_PLAYER" or not wish.player:
        return False
    mine = _named(finder, team, wish.player)
    if mine is None:
        return False
    for partner, _top in common.partners_with(finder, PARTNER_KINDS, exclude=[team]):
        for p_wish in [w for w in finder.wishes_for(partner) if w.kind in PARTNER_KINDS]:
            theirs = _named(finder, partner, p_wish.player) if p_wish.player else None
            if theirs is None or not _close_in_value(finder, team, mine, partner, theirs):
                continue
            deal = Deal([team, partner], [(team.nome, partner.nome, mine), (partner.nome, team.nome, theirs)])
            if (not common.failing_teams(deal)
                    and common.wish_fulfilled(finder, team, wish, [theirs], [mine])
                    and common.wish_fulfilled(finder, partner, p_wish, [mine], [theirs])
                    and common.close_deal(finder, deal, TRADE_TYPE, {team.nome: wish, partner.nome: p_wish})):
                return True
    return False
