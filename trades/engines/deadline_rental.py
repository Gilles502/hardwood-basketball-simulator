"""Deadline rental (catalog #11): a title chaser rents an expiring veteran from a team going nowhere.

Initiator: RENT_VETERAN, only in the `deadline` window. Partner: SELL_EXPIRING for that very player. The initiator
pays with a second-round pick or a young player (the SELL_EXPIRING wish asks for exactly that), plus salary
fillers when the salaries need them: real surplus only (`_fillers`: CONFIG.TRADES.RENT_FILLER_*), never a player as
good as the rental or a young one.
"""
from typing import Iterator, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "deadline_rental"
WINDOW = "deadline"
PARTNER_KINDS = ("SELL_EXPIRING",)
SECOND_ROUND = "R2"


def _payments(finder: 'TradeFinder', team: 'Squadra') -> list:
    """What the initiator pays with: its second-round picks. Every rental includes a draft pick (salary fillers are
    added on top, never instead), and no young player is the price."""
    return [f"{year}:{key}" for year, key in finder._collect_team_picks(team) if key.startswith(SECOND_ROUND)]


def _fillers(finder: 'TradeFinder', team: 'Squadra') -> list:
    """The initiator's salary fillers, biggest salary first: outside its top players, at or under RENT_FILLER_MAX_OVR,
    not young, on an expiring contract (RENT_FILLER_EXPIRING_ONLY)."""
    t = CONFIG.TRADES
    line = finder.era().ovr_at(t.RENT_FILLER_MAX_OVR)
    top = common.top_kept_ids(team)
    found = [p for p in finder.get_tradeable_players(team)
             if id(p) not in top and getattr(p, 'contract', None) is not None and p.ovr <= line
             and p.eta > t.YOUNG_MAX_AGE
             and (not t.RENT_FILLER_EXPIRING_ONLY or int(p.contract.anni_rimanenti) <= 1)]
    return sorted(found, key=lambda p: -p.contract.salario_annuale)


def _deals(team: 'Squadra', partner: 'Squadra', target, payments: list, fillers: list) -> Iterator[Deal]:
    for payment in payments:
        moves = [(team.nome, partner.nome, payment), (partner.nome, team.nome, target)]
        yield from common.matched_by_fillers(team, partner, moves, fillers)


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind != "RENT_VETERAN" or finder.window != WINDOW:
        return False
    payments = _payments(finder, team)
    if not payments:
        return False
    fillers = _fillers(finder, team)
    for partner, _top in common.partners_with(finder, PARTNER_KINDS, exclude=[team], vultures_first=True):
        tradeable = {id(p) for p in finder.get_tradeable_players(partner)}
        for p_wish in [w for w in finder.wishes_for(partner) if w.kind in PARTNER_KINDS]:
            target = next((p for p in partner.roster if p.nome == p_wish.player and id(p) in tradeable
                           and getattr(p, 'contract', None) is not None), None)
            if target is None or not common.wish_fulfilled(finder, team, wish, [target], []):
                continue
            # an expiring vet leaves for free in the summer: the cheap price, up to RENT_WAIVE_MAX_OVR
            waived = [partner.nome] if int(target.ovr) <= finder.era().ovr_at(CONFIG.TRADES.RENT_WAIVE_MAX_OVR) else []
            weaker = [p for p in fillers if int(p.ovr) <= int(target.ovr) - CONFIG.TRADES.RENT_PAY_FILLER_GAP]
            for deal in _deals(team, partner, target, payments, weaker):
                if (common.wish_fulfilled(finder, partner, p_wish, deal.receives(partner.nome), deal.gives(partner.nome))
                        and common.close_deal(finder, deal, TRADE_TYPE, {team.nome: wish, partner.nome: p_wish},
                                              price_waived=waived)):
                    return True
    return False
