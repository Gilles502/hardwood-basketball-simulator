"""Veteran sale (catalog #7): a team selling veterans auctions them; it must get a pick or a young player back.

The seller's SELL_VETERANS wish is only fulfilled by a return of a pick or a young player, so a bid made of salary
fillers alone (the old "Ginobili" dump) closes nothing.
"""
from typing import TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish, asked_out
from trades.engines import auction

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "veteran_sale"
BIDDER_KINDS = ("NEED_STARTER", "RENT_VETERAN", "WANT_STAR")


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind != "SELL_VETERANS":
        return False
    era, t = finder.era(), CONFIG.TRADES
    tradeable = finder.get_tradeable_players(team)   # computed once; stars and players asking out are not dumped
    veterans = sorted(
        (p for p in tradeable if p.eta >= t.VETERAN_MIN_AGE and era.rotation <= p.ovr < era.star
         and not asked_out(p) and getattr(p, 'contract', None) is not None),
        key=lambda p: -p.ovr)
    return any(auction.run_auction(finder, team, vet, TRADE_TYPE, wish, BIDDER_KINDS) for vet in veterans)
