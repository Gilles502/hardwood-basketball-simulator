"""A CPU trade window: every CPU GM's wishes, highest priority first, each handed to its engines once."""
import logging
import random
from typing import Tuple, TYPE_CHECKING

from trades import engines
from trades.engines import common
from trades.trade_finder import TradeFinder

if TYPE_CHECKING:
    from core.tournament import Tournament

main_log = logging.getLogger('main_sim')


def refresh_untouchables(torneo: 'Tournament') -> None:
    """Recomputes every team's untouchables (Squadra.designa_intoccabili). The flag is saved on each player and
    was set only at league setup, on load and on draft night, so in one long session it piled up (a 25-season
    save had 82% of the league untouchable and trades died out). Run before each window and at a new season."""
    for team in getattr(torneo, 'squadre', []):
        refresh = getattr(team, 'designa_intoccabili', None)   # test doubles of a team may not have it
        if refresh is not None:
            refresh(torneo)


def run_trade_window(torneo: 'Tournament', window: str) -> Tuple[int, TradeFinder]:
    """Runs the CPU trades of one window ("deadline" | "predraft" | "draft").

    Wishes of every CPU team (the user's too when the user is no GM) are shuffled, then stably sorted by priority.
    Each wish is tried once: its engines in order until one closes a deal. A team that traded has its wishes
    rebuilt (the trade clears its cache); a wish no longer among them is skipped. Returns (trades completed,
    the finder) - the finder's `logscambi` feeds the window's UI and podcast logging."""
    refresh_untouchables(torneo)
    finder = TradeFinder(torneo, torneo.squadre, getattr(torneo, 'squadra_giocatore', None))
    finder.begin_window(window)
    teams = {team.nome: team for team in common.cpu_teams(finder)}
    queue = [wish for team in teams.values() for wish in finder.wishes_for(team)]
    random.shuffle(queue)
    queue.sort(key=lambda w: -w.priority)

    done = 0
    for wish in queue:
        runners = engines.engines_for(wish.kind)
        team = teams.get(wish.team)
        if not runners or team is None:
            continue
        if wish not in finder.wishes_for(team):   # the team traded and this wish is gone
            continue
        for engine in runners:
            try:
                closed = engine(finder, team, wish)
            except Exception as ex:
                main_log.error(f"Trade engine {getattr(engine, 'name', engine)} failed on {wish.kind} "
                               f"({team.nome}): {ex}", exc_info=True)
                closed = False
            if closed:
                done += 1
                break
    main_log.info(f"Trade window '{window}': {done} CPU trades")
    return done, finder
