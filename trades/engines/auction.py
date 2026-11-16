"""One player on the block: the teams that want him bid, the seller's best acceptable bid closes the deal.

Adapted from the old `TradeFinder.gestisci_asta_giocatore`: bids (`_build_bid_for_player`), the negotiation zone,
finalists and one raise (`_try_request_extra_asset`). What changed: only teams holding a wish the player fills sit at
the table (vultures keep their guaranteed seats), and the winner goes through `common.close_deal`, so both teams'
plan and price questions and the seller's own wish decide the deal.
"""
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Giocatore, Squadra
    from trades.trade_finder import TradeFinder

main_log = logging.getLogger('main_sim')

Seat = Tuple['Squadra', List[Wish]]


def seat_bidders(finder: 'TradeFinder', seller: 'Squadra', bidder_kinds: Iterable[str],
                 player: Optional['Giocatore'] = None) -> List[Seat]:
    """The table: CPU teams (not the seller) with a wish of `bidder_kinds`, vultures first, at most
    AUCTION_MAX_BIDDERS. With a `player`, a team sits only if one of those wishes is filled by getting him."""
    kinds = tuple(bidder_kinds)
    seats: List[Seat] = []
    for team, _top in common.partners_with(finder, kinds, exclude=[seller], vultures_first=True):
        wishes = [w for w in finder.wishes_for(team) if w.kind in kinds]
        if player is not None:
            wishes = [w for w in wishes if common.wish_fulfilled(finder, team, w, [player], [])]
        if wishes:
            seats.append((team, wishes))
    return seats[:CONFIG.TRADES.AUCTION_MAX_BIDDERS]


def minimum_value(finder: 'TradeFinder', seller: 'Squadra', player: 'Giocatore') -> float:
    """What the seller needs back: the player's value times a share set by its plan. A star it keeps costs more;
    one who asked out does not (the seller's acceptance is discounted the same way)."""
    t = CONFIG.TRADES
    share = t.AUCTION_SELLER_THRESHOLD.get(finder.get_team_strategy(seller), t.AUCTION_SELLER_THRESHOLD[None])
    if not getattr(player, '_wants_out', False):
        ovr_at = finder.era().ovr_at
        for old_ovr, mult in t.AUCTION_STAR_PRICE_OLD:
            if player.ovr >= ovr_at(old_ovr):
                share *= mult
                break
    return finder.get_strategic_value(player, seller) * share


def _names(assets: list) -> list:
    return [f"{a.nome} ({a.ovr})" if hasattr(a, 'nome') else str(a) for a in assets]


def _finalists(bids: List[Dict[str, Any]], minimum: float) -> List[Dict[str, Any]]:
    """Bids sorted best first. Close competitors (within the zone share of the best) all get a raise; a lone or
    under-the-minimum best bid gets one too."""
    if not bids:
        return []
    zone = CONFIG.TRADES.AUCTION_ZONE_SHARE
    best = bids[0]['value_to_seller']
    if len(bids) >= 2 and bids[1]['value_to_seller'] >= best * zone:
        return [b for b in bids if b['value_to_seller'] >= best * zone]
    if best < minimum or len(bids) == 1:
        return [bids[0]]
    return []


def _deal(seller: 'Squadra', bidder: 'Squadra', player: 'Giocatore', assets: list) -> Deal:
    return Deal([seller, bidder], [(bidder.nome, seller.nome, a) for a in assets]
                + [(seller.nome, bidder.nome, player)])


def run_auction(finder: 'TradeFinder', seller: 'Squadra', player: 'Giocatore', trade_type: str,
                seller_wish: Wish, bidder_kinds: Tuple[str, ...]) -> bool:
    """Auctions `player`; True when a deal closed. The seller's wish must be fulfilled by the winning bid."""
    zone = CONFIG.TRADES.AUCTION_ZONE_SHARE
    minimum = minimum_value(finder, seller, player)
    seats = {id(team): (team, wishes) for team, wishes in seat_bidders(finder, seller, bidder_kinds, player)}

    bids = []
    for team, _wishes in seats.values():
        bid = finder._build_bid_for_player(team, seller, player)
        if bid and bid['value_to_seller'] >= minimum * zone:
            bids.append(bid)
    bids.sort(key=lambda b: b['value_to_seller'], reverse=True)

    def serves_seller(bid) -> bool:
        return common.wish_fulfilled(finder, seller, seller_wish, bid['assets'], [player])

    raised = {id(b) for b in _finalists(bids, minimum)}
    for bid in bids:
        if id(bid) in raised or not serves_seller(bid):   # a bid that misses the seller's wish may still be sweetened
            assets, value = finder._try_request_extra_asset(bid['partner'], bid['assets'], seller, player)
            bid['assets'], bid['value_to_seller'] = assets, value
    bids.sort(key=lambda b: b['value_to_seller'], reverse=True)

    for bid in bids:
        bidder = bid['partner']
        _team, wishes = seats[id(bidder)]
        wish = next((w for w in wishes if common.wish_fulfilled(finder, bidder, w, [player], bid['assets'])), None)
        if wish is None or not serves_seller(bid):
            continue
        deal = _deal(seller, bidder, player, bid['assets'])
        if common.close_deal(finder, deal, trade_type, {seller.nome: seller_wish, bidder.nome: wish}):
            if trade_type == "trade_demand":
                main_log.warning(f"{player.nome} ({player.ovr}) forced his way out to {bidder.nome}")
            return True
    if main_log.isEnabledFor(logging.DEBUG):
        main_log.debug(f"Auction for {player.nome} ({trade_type}) from {seller.nome}: no deal; minimum {minimum:.1f}, "
                       f"bids {[(b['partner'].nome, _names(b['assets']), round(b['value_to_seller'], 1)) for b in bids]}")
    return False
