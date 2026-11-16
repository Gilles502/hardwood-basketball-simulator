"""Contracts with a brain: earned loyalty, stars who walk away from hopeless teams, renewals by the GM's plan.

Pure rules on players, teams and a WishContext (core/front_office/wishes.py); every number is CONFIG.CONTRACTS.
Used by offseason/contract_extensions.py and offseason/free_agency.py.
"""
import random
from typing import NamedTuple, Optional

from core.config import CONFIG
from core.front_office.wishes import WishContext, wants_out, young_future

ASKED_OUT = "asked out"
HOPELESS = "hopeless team"


def loyalty(player, team=None) -> float:
    """What staying with his team is worth to the player (score points): seasons with the team and morale.
    `team` is accepted for callers that have it; the value only depends on the player today."""
    c = CONFIG.CONTRACTS
    years = getattr(player, 'anni_nella_squadra', 0) or 0
    morale = getattr(player, 'morale', c.LOYALTY_MORALE_PIVOT)
    value = c.LOYALTY_PER_YEAR * min(years, c.LOYALTY_MAX_YEARS) + (morale - c.LOYALTY_MORALE_PIVOT) * c.LOYALTY_MORALE_WEIGHT
    return max(c.LOYALTY_MIN, min(c.LOYALTY_MAX, value))


def _hopeless(team, ctx: WishContext) -> bool:
    c = CONFIG.CONTRACTS
    losing = ctx.games >= c.WALK_MIN_GAMES and ctx.win_pct < c.WALK_HOPELESS_WIN_PCT
    return (ctx.plan == "REBUILDER" or losing) and not young_future(team, ctx.era)


def walk_reason(player, team, ctx: WishContext) -> str:
    """Why the player will not re-sign with his team ("asked out" / "hopeless team"), or "" when he would listen."""
    if wants_out(player, team, ctx):
        return ASKED_OUT
    if int(player.ovr) >= ctx.era.star and player.eta >= CONFIG.CONTRACTS.WALK_MIN_AGE and _hopeless(team, ctx):
        return HOPELESS
    return ""


class Renewal(NamedTuple):
    salary_mult: float   # times the player's market value
    years: int


def _years(age: int) -> int:
    return 4 if age <= 28 else (3 if age <= 31 else (2 if age <= 34 else 1))


def renewal_offer(player, ctx: WishContext, rng=random) -> Optional[Renewal]:
    """What the CPU GM offers a player in his contract year, by its plan; None lets him walk."""
    c, t, era = CONFIG.CONTRACTS, CONFIG.TRADES, ctx.era
    ovr, age, plan = int(player.ovr), player.eta, ctx.plan
    rebuilder = plan == "REBUILDER"
    young = age <= t.REBUILDER_KEEP_YOUNG_MAX_AGE
    veteran = age >= t.REBUILDER_VET_AGE
    if ovr >= era.star:
        keep = not rebuilder or young
        mult = c.RENEW_STAR_MULT.get(plan, 1.0)
    elif ovr >= era.starter:
        keep = (not rebuilder) or young or (not veteran and rng.random() < c.REBUILDER_PRIME_RENEW_CHANCE)
        mult = 1.0
    else:
        prospect = age <= t.YOUNG_MAX_AGE and player.potenziale >= era.starter
        keep = prospect or (not (rebuilder and veteran) and rng.random() < c.RENEW_BENCH_CHANCE)
        mult = 1.0
    return Renewal(mult, _years(age)) if keep else None


def context_for(torneo, team) -> WishContext:
    """The team's WishContext (plan, record, era lines) as the trade system reads it."""
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(torneo, torneo.squadre, getattr(torneo, 'squadra_giocatore', None))
    finder.begin_window("contracts")
    return finder.wish_context(team)
