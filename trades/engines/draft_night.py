"""Draft night (catalog #9): the team on the clock drops down with a team that wants to move up.

Called from the draft, pick by pick (`run_on_the_clock`), not from a wish: it is no initiator-kind engine. The team
on the clock gives its pick; the partner gives a later first of this draft and a second (or a later year's first).

The team on the clock trades only with a MOVE_DOWN_DRAFT wish, or when the prospect it needs is not the top of the
board (today's notion: it still gets its man a few slots down, at most `DRAFT_NIGHT_DROP_BONUS` adjusted by its plan).
The partner trades only with a MOVE_UP_DRAFT or TARGET_PROSPECT wish.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.draft_fit import best_prospect
from core.front_office.wishes import Wish
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

main_log = logging.getLogger('main_sim')

TRADE_TYPE = "draft_night"
PARTNER_KINDS = ("MOVE_UP_DRAFT", "TARGET_PROSPECT")


def _slide_limit(finder: 'TradeFinder', team: 'Squadra', prospects: list,
                 pick_pos: int = 99) -> Tuple[Optional[Any], Optional[int]]:
    """(the team's MOVE_DOWN_DRAFT wish, how many slots it will drop); (None, None) when it will not move down.

    With the wish it drops as far as a partner pays for (no limit). Without it, only when the prospect it would take
    (`draft_fit.best_prospect`, the draft room's own choice) is on the board but not at the top: it drops that many
    slots, adjusted by its plan."""
    wish = next((w for w in finder.wishes_for(team) if w.kind == "MOVE_DOWN_DRAFT"), None)
    if wish is not None:
        return wish, len(finder.torneo.draft_lottery_order or []) or len(prospects)
    board = prospects[:CONFIG.DRAFT_AI.BOARD_SIZE]
    choice = best_prospect(board, team.roster, finder.era(), finder.get_team_strategy(team), pick_pos,
                           gm=finder.get_gm(team), year=finder.era().year)   # the draft room's own pick
    # (pick_pos: a top pick never drops past a generational talent)
    index = board.index(choice) if choice in board else -1
    if index <= 0:
        return None, None
    t = CONFIG.TRADES
    return None, max(t.DRAFT_NIGHT_MIN_DROP, index + t.DRAFT_NIGHT_DROP_BONUS.get(finder.get_team_strategy(team), 0))


def _later_firsts(finder: 'TradeFinder', partner: 'Squadra', pick_pos: int, max_drop: int) -> List[Tuple[str, int]]:
    """The partner's firsts of this draft that come after `pick_pos` within `max_drop` slots, closest first."""
    return [(key, pos) for key, pos in common.this_year_firsts(finder, partner) if pick_pos < pos <= pick_pos + max_drop]


def _news(finder: 'TradeFinder', team: 'Squadra', partner: 'Squadra', pick_pos: int, later_pos: int, extra: str) -> None:
    try:
        from core.news_generator import add_news
        add_news(
            category="draft",
            title=f"🚨 DRAFT TRADE: Trade between {team.nome} and {partner.nome}!",
            excerpt=(f"The {team.nome} trade pick #{pick_pos} to drop down to #{later_pos}, getting "
                     f"{finder._format_asset(extra)}. The {partner.nome} move up!"),
            teams=[team.nome, partner.nome],
            season=finder.torneo.season_number)
    except Exception:
        main_log.warning("Ignored error in draft_night news", exc_info=True)


def run_on_the_clock(finder: 'TradeFinder', team_on_clock: 'Squadra', pick_pos: int,
                     pick_key: str) -> Optional[Dict[str, Any]]:
    """A CPU-to-CPU trade for the pick the team is on the clock with ("R1-Team", at overall `pick_pos`), or None.

    The dict is what `offseason/draft.py` keeps and the draft room shows (same shape as the old
    `simulate_cpu_to_cpu_draft_trade`); `player_involved` names the extra pick the team received, `player_ovr` is 0."""
    prospects = list(getattr(finder.torneo, 'draft_class', None) or [])
    if not prospects:
        return None
    if finder.window != "draft":
        finder.begin_window("draft")   # the draft wishes (TARGET_PROSPECT) exist only in this window
    down_wish, max_drop = _slide_limit(finder, team_on_clock, prospects, pick_pos)
    if max_drop is None:
        return None
    given = f"{common.THIS_DRAFT}:{pick_key}"
    for partner, p_wish in common.partners_with(finder, PARTNER_KINDS, exclude=[team_on_clock]):
        if p_wish.kind == "MOVE_UP_DRAFT" and pick_pos > p_wish.get("slot", pick_pos):
            continue   # not high enough for the prospect it wants
        for later, later_pos in _later_firsts(finder, partner, pick_pos, max_drop):
            for extra in common.sweeteners(finder, partner, later):
                deal = Deal([team_on_clock, partner], [(team_on_clock.nome, partner.nome, given),
                                                       (partner.nome, team_on_clock.nome, later),
                                                       (partner.nome, team_on_clock.nome, extra)],
                            pick_protections={a: "Unprotected" for a in (given, later, extra)})
                # The team on the clock moves DOWN: its wish is the move-down one (a real one, or the prospect it
                # still gets a few slots later), never "move up" or "take salary" because it receives a first.
                wishes = {partner.nome: p_wish,
                          team_on_clock.nome: down_wish or Wish("MOVE_DOWN_DRAFT", team_on_clock.nome, 0.0,
                                                                "The prospect it wants is still there a few slots down.")}
                if not common.close_deal(finder, deal, TRADE_TYPE, wishes):
                    continue
                _news(finder, team_on_clock, partner, pick_pos, later_pos, extra)
                return {
                    "team_on_clock": team_on_clock.nome,
                    "partner": partner.nome,
                    "player_involved": finder._format_asset(extra),
                    "player_ovr": 0,
                    "pick_given": pick_pos,
                    "pick_received": later_pos,
                    "description": (f"The **{team_on_clock.nome}** trade pick **#{pick_pos}** with the **{partner.nome}** "
                                    f"to drop down to **#{later_pos}**, and get {finder._format_asset(extra)} as well!"),
                }
    return None
