"""Trade demand (catalog #3): a star who asked out is auctioned among the teams that want a starter or a star."""
from typing import TYPE_CHECKING

from core.front_office.wishes import Wish
from trades.engines import auction

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "trade_demand"
BIDDER_KINDS = ("NEED_STARTER", "WANT_STAR")


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind != "STAR_WANTS_OUT" or not wish.player:
        return False
    star = next((p for p in team.roster if p.nome == wish.player), None)
    if star is None or getattr(star, 'contract', None) is None:
        return False
    finder.get_tradeable_players(team, allow_stars=True)   # flags the player as wanting out, which acceptance reads
    return auction.run_auction(finder, team, star, TRADE_TYPE, wish, BIDDER_KINDS)
