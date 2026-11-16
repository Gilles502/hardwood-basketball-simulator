"""Pick trade-up (catalog #6): a team that wants a prospect projected above its pick pays for a higher first of the
same draft.

Initiator: MOVE_UP_DRAFT (a team with a prospect in mind: the wish carries his projected slot, and the first received
must be at or above it). A first of this draft is worth the prospect projected there (CONFIG.DRAFT_AI.
PICK_VALUE_FROM_PROSPECT), so the price grows with the jump and with the gap between the prospects.

1. Picks: its first plus one later first (MOVE_DOWN_DRAFT or WANT_PICKS partner).
2. A player: its first plus one player (at most PICK_PAY_MAX_AGE, at least a starter), cheapest first, alone or with a
   later first; the seller sends salary back if the cap needs it. Any partner whose wish the player serves (WANT_YOUTH,
   WANT_STAR) or that just wants picks. The buyer pays on purpose (its own value check is waived, like a tax dump),
   but never more than MOVE_UP_MAX_OVERPAY x the pick; the seller's value check, the top-5 rule (an 88+ back) and
   every plan rule still apply.
"""
from typing import TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "pick_trade_up"
PARTNER_KINDS = ("MOVE_DOWN_DRAFT", "WANT_PICKS")
PLAYER_PARTNER_KINDS = ("MOVE_DOWN_DRAFT", "WANT_PICKS", "WANT_YOUTH", "WANT_STAR")
_UNPROTECTED = "Unprotected"   # price of moving up: no protection


def _targets(finder: 'TradeFinder', partner: 'Squadra', my_pos: int, wish: Wish):
    """The partner's firsts of this draft above `my_pos` and at or above the wish's slot."""
    return [(k, pos) for k, pos in common.this_year_firsts(finder, partner)
            if pos < my_pos and pos <= wish.get("slot", pos)]


def _with_picks(finder, team, wish, mine, sweeteners) -> bool:
    for partner, p_wish in common.partners_with(finder, PARTNER_KINDS, exclude=[team], vultures_first=True):
        for given, my_pos in mine:
            for target, _pos in _targets(finder, partner, my_pos, wish):
                for extra in sweeteners[given]:
                    deal = Deal([team, partner], [(team.nome, partner.nome, a) for a in (given, extra)]
                                + [(partner.nome, team.nome, target)],
                                pick_protections={a: _UNPROTECTED for a in (given, extra, target)})
                    if common.close_deal(finder, deal, TRADE_TYPE, {team.nome: wish, partner.nome: p_wish}):
                        return True
    return False


def _payers(finder: 'TradeFinder', team: 'Squadra') -> list:
    era, d = finder.era(), CONFIG.DRAFT_AI
    players = [p for p in team.roster if p.eta <= d.PICK_PAY_MAX_AGE and int(p.ovr) >= era.starter
               and not getattr(p, 'is_untouchable', False)]
    return sorted(players, key=lambda p: finder.get_strategic_value(p, team))


def _partner_wish(finder, partner, receives, gives):
    for w in finder.wishes_for(partner):
        if w.kind in PLAYER_PARTNER_KINDS and common.wish_fulfilled(finder, partner, w, receives, gives):
            return w
    return None


def _with_a_player(finder, team, wish, mine, sweeteners) -> bool:
    payers = _payers(finder, team)
    if not payers:
        return False
    for partner in common.cpu_teams(finder):
        if partner is team:
            continue
        fillers = [p for p in partner.roster]
        for given, my_pos in mine:
            for target, _pos in _targets(finder, partner, my_pos, wish):
                cap = finder.get_strategic_value(target, team) * CONFIG.DRAFT_AI.MOVE_UP_MAX_OVERPAY
                for player in payers:
                    if finder.get_strategic_value(player, team) > cap:
                        break   # cheapest first: every next one costs more
                    for extra in [None] + sweeteners[given][:1]:
                        sent = [given, player] + ([extra] if extra else [])
                        moves = [(team.nome, partner.nome, a) for a in sent] + [(partner.nome, team.nome, target)]
                        for deal in common.matched_by_fillers(partner, team, moves, fillers):
                            deal = Deal([team, partner], deal.moves,
                                        pick_protections={a: _UNPROTECTED for a in sent + [target] if isinstance(a, str)})
                            p_wish = _partner_wish(finder, partner, deal.receives(partner.nome), deal.gives(partner.nome))
                            if p_wish is None:
                                break
                            if common.close_deal(finder, deal, TRADE_TYPE, {team.nome: wish, partner.nome: p_wish},
                                                 price_waived=[team.nome]):
                                return True
                            break   # one salary match per package: the next costs the seller more players
    return False


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind != "MOVE_UP_DRAFT":
        return False
    mine = common.this_year_firsts(finder, team)
    if not mine:
        return False
    sweeteners = {given: common.sweeteners(finder, team, given) for given, _ in mine}   # once per pick, not per partner
    return _with_picks(finder, team, wish, mine, sweeteners) or _with_a_player(finder, team, wish, mine, sweeteners)
