"""Tax dump (catalog #10): a team over the tax, or stuck with a long heavy contract, hands the contract to a team
with room under the tax and pays for it with its own picks.

Price: `TAX_DUMP_R2_COUNT` second-rounders for an ordinary contract (a first only with `TAX_DUMP_R1_FALLBACK`), a
first-rounder for a high long one
(`era.is_high_contract`). An expiring (1 year) player in band starter or better is never dumped. A tax cut sends bench money: never one of the
team's `TAX_DUMP_KEEP_TOP` best by OVR. A projected top-5 pick is never the price.
"""
from typing import List, Optional, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish
from trades.engines import common
from trades.execution import Deal

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

TRADE_TYPE = "tax_dump"
INITIATOR_KINDS = ("SHED_TAX", "CLEAR_LONG_CONTRACT")
PARTNER_KINDS = ("ABSORB_SALARY",)


def _years(p) -> int:
    return int(p.contract.anni_rimanenti)


def _salary(p) -> float:
    return float(p.contract.salario_annuale)


def _candidates(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> list:
    """The contracts to hand over, best first: the wish's player, or the biggest salaries for a tax cut."""
    era = finder.era()
    pool = [p for p in finder.get_tradeable_players(team) if getattr(p, 'contract', None) is not None
            and not (_years(p) <= 1 and p.ovr >= era.starter)]
    if wish.kind == "CLEAR_LONG_CONTRACT":
        return [p for p in pool if p.nome == wish.player]
    best = {id(p) for p in sorted(team.roster, key=lambda p: -int(p.ovr))[:CONFIG.TRADES.TAX_DUMP_KEEP_TOP]}
    return sorted((p for p in pool if id(p) not in best), key=lambda p: -_salary(p))


def _prices(finder: 'TradeFinder', team: 'Squadra', player) -> List[List[str]]:
    """What the team can pay for this contract, as lists of picks (finder keys), cheapest option first."""
    t = CONFIG.TRADES
    picks = [f"{year}:{key}" for year, key in finder._collect_team_picks(team)   # cheapest first
             if not finder._is_top5_pick(f"{year}:{key}")]
    firsts = [k for k in picks if ":R1-" in k]
    seconds = [k for k in picks if ":R2-" in k]
    if t.TAX_DUMP_R1_IF_HIGH_CONTRACT and finder.era().is_high_contract(_salary(player), _years(player)):
        return [[k] for k in firsts]
    options = []
    if len(seconds) >= t.TAX_DUMP_R2_COUNT:
        options.append(seconds[:t.TAX_DUMP_R2_COUNT])
    if t.TAX_DUMP_R1_FALLBACK:
        options.extend([k] for k in firsts)   # a team without enough seconds pays with a first
    return options


def _deal(team: 'Squadra', partner: 'Squadra', player, picks: List[str]) -> Deal:
    return Deal([team, partner], [(team.nome, partner.nome, a) for a in [player, *picks]])


def run(finder: 'TradeFinder', team: 'Squadra', wish: Wish) -> bool:
    if wish.kind not in INITIATOR_KINDS:
        return False
    era = finder.era()
    if wish.kind == "SHED_TAX" and (era.no_cap or float(team.payroll) <= era.shed_line):
        return False
    candidates = _candidates(finder, team, wish)
    if not candidates:
        return False
    prices = {id(p): _prices(finder, team, p) for p in candidates}   # once per player, not per partner
    for partner, p_wish in common.partners_with(finder, PARTNER_KINDS, exclude=[team], vultures_first=True):
        for player in candidates:
            if not era.no_cap and float(partner.payroll) + _salary(player) > era.tax:
                continue   # the partner has to stay under the tax after absorbing
            for picks in prices[id(player)]:
                deal = _deal(team, partner, player, picks)
                if not (common.wish_fulfilled(finder, team, wish, deal.receives(team.nome), deal.gives(team.nome))
                        and common.wish_fulfilled(finder, partner, p_wish, deal.receives(partner.nome),
                                                  deal.gives(partner.nome))):
                    continue
                if common.close_deal(finder, deal, TRADE_TYPE, {team.nome: wish, partner.nome: p_wish},
                                     price_waived=[team.nome]):
                    return True
    return False
