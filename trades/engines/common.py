"""What every engine shares: the CPU teams, partners by wish, salary checks, and closing a deal with its motive."""
import logging
import random
from itertools import combinations
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple, TYPE_CHECKING

from core.config import CONFIG
from core.front_office.wishes import Wish, fulfils
from trades.execution import Deal
from trades.motive import SideMotive, TradeMotive, reasons_for, user_side_motive, why_line

if TYPE_CHECKING:
    from core.models import Squadra
    from trades.trade_finder import TradeFinder

main_log = logging.getLogger('main_sim')

# A star or starter upgrade that needed a third team is recorded as its own type (spec: catalog #8).
FACILITATED_BASE = ("star_upgrade", "starter_upgrade")
FACILITATED_TYPE = "facilitated_3team"


# ---------------------------------------------------------------- teams and partners
def cpu_teams(finder: 'TradeFinder') -> List['Squadra']:
    """Every team the CPU runs: all of them except the user's, and all of them when the user is no GM."""
    return [t for t in finder.squadre if not finder._is_user_team(t)]


def partners_with(finder: 'TradeFinder', kinds: Iterable[str], exclude: Iterable[Any] = (),
                  vultures_first: bool = False) -> List[Tuple['Squadra', Wish]]:
    """CPU teams holding a wish of one of `kinds`, shuffled, each with its highest-priority such wish.

    `exclude`: teams (or team names) left out. `vultures_first`: skilled traders get the first seats
    (`finder._vultures_first`)."""
    kinds = tuple(kinds)
    excluded = {t if isinstance(t, str) else t.nome for t in exclude}
    pairs = []
    for team in cpu_teams(finder):
        if team.nome in excluded:
            continue
        wish = next((w for w in finder.wishes_for(team) if w.kind in kinds), None)
        if wish is not None:
            pairs.append((team, wish))
    random.shuffle(pairs)
    if vultures_first:
        by_team = {id(team): (team, wish) for team, wish in pairs}
        pairs = [by_team[id(team)] for team in finder._vultures_first([team for team, _ in pairs])]
    return pairs


# ---------------------------------------------------------------- what a team can send
def top_kept_ids(team: 'Squadra') -> set:
    """`id`s of the players a team keeps out of filler packages: its best by OVR."""
    return {id(p) for p in sorted(team.roster, key=lambda p: -p.ovr)[:CONFIG.TRADES.TOP_KEPT_BY_OVR]}


def rotation_fillers(finder: 'TradeFinder', team: 'Squadra', taken: list = ()) -> list:
    """Rotation contracts outside the team's top players by OVR, biggest salary first."""
    era = finder.era()
    top = top_kept_ids(team)
    used = {id(a) for a in taken if not isinstance(a, str)}
    found = [p for p in finder.get_tradeable_players(team)
             if id(p) not in top and id(p) not in used and p.ovr >= era.rotation
             and getattr(p, 'contract', None) is not None]
    return sorted(found, key=lambda p: -p.contract.salario_annuale)


# ---------------------------------------------------------------- draft picks
THIS_DRAFT = 1   # finder pick keys count years from now: "1:R1-X" is this draft's first


def this_year_firsts(finder: 'TradeFinder', team: 'Squadra', skip_top5: bool = False) -> List[Tuple[str, int]]:
    """(finder key, projected draft position) of the team's firsts of this draft, best first. A pick without a known
    position is left out (nobody can tell whether it is higher); `skip_top5` also leaves out the top-5 picks."""
    found = []
    for year, key in finder._collect_team_picks(team):
        asset = f"{year}:{key}"
        if year != THIS_DRAFT or not key.startswith("R1") or (skip_top5 and finder._is_top5_pick(asset)):
            continue
        pos = finder._get_pick_position(key)
        if pos > 0:
            found.append((asset, pos))
    return sorted(found, key=lambda x: x[1])


def sweeteners(finder: 'TradeFinder', team: 'Squadra', taken: str) -> List[str]:
    """What a team adds to a first it moves: its firsts of later years, cheapest first (seconds are worth next to
    nothing and never sweeten a deal)."""
    picks = [f"{year}:{key}" for year, key in finder._collect_team_picks(team)]   # cheapest first
    return [k for k in picks if ":R1-" in k and k != taken and not k.startswith(f"{THIS_DRAFT}:")]


# ---------------------------------------------------------------- deal checks
def _salary(assets: list) -> float:
    return sum(float(a.contract.salario_annuale) for a in assets if not isinstance(a, str))


def salary_ok(team: 'Squadra', deal: Deal) -> bool:
    """The team's own salary-match rule (era rules, no-cap mode) on its side of the deal; picks carry no salary."""
    ok, _ = team.check_trade_salary_match(_salary(deal.receives(team.nome)), _salary(deal.gives(team.nome)))
    return bool(ok)


def failing_teams(deal: Deal) -> List['Squadra']:
    return [team for team in deal.teams if not salary_ok(team, deal)]


def matched_by_fillers(team: 'Squadra', partner: 'Squadra', moves: list, fillers: list) -> Iterator[Deal]:
    """`moves` (team, partner, asset) as they are when both salaries match, else with 1..STAR_UPGRADE_MAX_FILLERS of
    `team`'s `fillers` added to what it sends; smaller salary packages first. Only deals that match are yielded."""
    plain = Deal([team, partner], moves)
    if not failing_teams(plain):
        yield plain
        return
    moved = {id(m[2]) for m in moves}
    fillers = [p for p in fillers if id(p) not in moved]
    for size in range(1, CONFIG.TRADES.STAR_UPGRADE_MAX_FILLERS + 1):
        for combo in sorted(combinations(fillers, size), key=lambda c: sum(p.contract.salario_annuale for p in c)):
            deal = Deal([team, partner], moves + [(team.nome, partner.nome, p) for p in combo])
            if not failing_teams(deal):
                yield deal


def wish_fulfilled(finder: 'TradeFinder', team: 'Squadra', wish: Wish, receives: list, gives: list) -> bool:
    """`wishes.fulfils` on deal assets: finder picks ("N:R1-X") are translated to the wishes' format first."""
    r = [finder._wish_asset(a) for a in receives]
    g = [finder._wish_asset(a) for a in gives]
    return fulfils(wish, r, g, team, finder.era())


# ---------------------------------------------------------------- motive
def _label(finder: 'TradeFinder', asset: Any) -> str:
    """A player's name or a pick as the trade log writes it ("2004 R1-Team"): no OVR, salary or value."""
    return finder._format_asset(asset) if isinstance(asset, str) else asset.nome


def side_motive(finder: 'TradeFinder', team: 'Squadra', wish: Optional[Wish], deal: Deal) -> SideMotive:
    """One team's side of the motive: GM, plan, the wish served, English reasons, and the values (never shown)."""
    if finder._is_user_team(team):
        return user_side_motive(team.nome)
    name = team.nome
    receives, gives = deal.receives(name), deal.gives(name)
    gm = finder.get_gm(team)
    traits = list(getattr(gm, 'traits', None) or [])
    plan = finder.get_team_strategy(team)
    kind = wish.kind if wish is not None else None
    need = wish.role if wish is not None else None
    return SideMotive(
        team=name, gm_name=getattr(gm, 'name', None),
        trade_skill=(gm.skills.get("trade") if gm is not None else None),
        plan=plan, traits=traits, wish_kind=kind, need=need,
        reasons=reasons_for(kind, team=name, plan=plan, traits=traits,
                            gets=[_label(finder, a) for a in receives], gives=[_label(finder, a) for a in gives],
                            need=need),
        value_given=round(sum(finder.get_strategic_value(a, team) for a in gives), 1),
        value_received=round(sum(finder.get_strategic_value(a, team) for a in receives), 1))


def build_motive(finder: 'TradeFinder', deal: Deal, trade_type: str, wishes: Dict[str, Wish]) -> TradeMotive:
    sides = [side_motive(finder, team, wishes.get(team.nome), deal) for team in deal.teams]
    return TradeMotive(trade_type=trade_type, why=why_line(trade_type, sides), sides=sides,
                       team_count=len(deal.teams))


# ---------------------------------------------------------------- closing
def _asset_id(finder: 'TradeFinder', asset: Any) -> str:
    """A name for an asset that stays the same across windows: a player's name, a pick with its draft year."""
    return finder._wish_asset(asset) if isinstance(asset, str) else f"player:{asset.nome}"


def _season_book(finder: 'TradeFinder') -> dict:
    """This season's CPU deal book, kept on the league: "moves" = (team, asset id) of everything a team sent away,
    "picks_in" = (team, pick id) of every pick a team got."""
    torneo = finder.torneo
    season = getattr(torneo, 'season_number', 0)
    book = getattr(torneo, '_cpu_traded_away', None)
    if not book or book.get("season") != season:
        book = {"season": season, "moves": set(), "picks_in": set()}
        torneo._cpu_traded_away = book
    book.setdefault("picks_in", set())   # a book from before the flip rule
    return book


def _traded_away(finder: 'TradeFinder') -> set:
    return _season_book(finder)["moves"]


def gives_back(finder: 'TradeFinder', deal: Deal) -> Optional[str]:
    """Why the deal sends a team something it traded away earlier this season (the pick ping-pong), or None."""
    away = _traded_away(finder)
    for _src, dst, asset in deal.moves:
        if (dst, _asset_id(finder, asset)) in away:
            return f"{dst} would get back {finder._format_asset(asset) if isinstance(asset, str) else asset.nome}, traded away this season"
    return None


def flips_a_pick(finder: 'TradeFinder', deal: Deal) -> Optional[str]:
    """Why the deal has a team trade away a pick it got by a CPU deal this season (bought to move up, then sold
    for more picks), or None."""
    picks_in = _season_book(finder)["picks_in"]
    for src, _dst, asset in deal.moves:
        if isinstance(asset, str) and (src, _asset_id(finder, asset)) in picks_in:
            return f"{src} would flip {finder._format_asset(asset)}, acquired this season"
    return None


def remember_moves(finder: 'TradeFinder', deal: Deal) -> None:
    book = _season_book(finder)
    for src, dst, asset in deal.moves:
        book["moves"].add((src, _asset_id(finder, asset)))
        if isinstance(asset, str):
            book["picks_in"].add((dst, _asset_id(finder, asset)))


def _refuse(deal: Deal, why: str) -> bool:
    main_log.debug(f"Deal not closed [{' / '.join(deal.team_names())}]: {why}")
    return False


def close_deal(finder: 'TradeFinder', deal: Deal, trade_type: str, wishes: Dict[str, Wish],
               price_waived: Iterable[str] = ()) -> bool:
    """Closes an engine's deal: salaries (with the 3/4-team extension), both questions for every CPU team, the
    motive, then `finder.execute_deal`.

    Every CPU team's served wish is closed for the rest of the window (`finder.close_wishes`).

    `wishes`: team name -> the wish the deal serves for that team. A listed wish the deal does not fulfil refuses
    the deal; a CPU team that is not listed is recorded with the wish its plan question found. The dict is not
    changed.

    `price_waived`: names of teams that pay on purpose to get rid of a contract (a tax dump): they still answer the
    plan question and every blocking rule, but not the value comparison, since receiving less than they give is
    the point of the deal."""
    from trades.engines import multi_team

    wishes = dict(wishes)
    waived = set(price_waived)
    extended = False
    if failing_teams(deal):
        bigger = multi_team.extend(finder, deal, wishes)
        if bigger is None:
            return _refuse(deal, "salaries don't match and no extra team fixes them")
        deal, extended = bigger, True
    back = gives_back(finder, deal) or flips_a_pick(finder, deal)
    if back:
        return _refuse(deal, back)

    served: Dict[str, Wish] = {}
    for team in deal.teams:
        if finder._is_user_team(team):
            continue
        name = team.nome
        receives, gives = deal.receives(name), deal.gives(name)
        wish = wishes.get(name)
        if wish is not None and not wish_fulfilled(finder, team, wish, receives, gives):
            return _refuse(deal, f"{name}: the deal does not fulfil {wish.kind}")
        if name in waived:
            ok, why = finder.would_accept_trade_with_reason(team, receives, gives, waive_price=True)
        else:
            ok, why = finder.would_accept_trade_with_reason(team, receives, gives)
        if not ok:
            return _refuse(deal, f"{name}: {why}")
        if wish is None:
            wish = finder.plan_check(team, receives, gives)[2]
        served[name] = wish

    record_type = FACILITATED_TYPE if extended and trade_type in FACILITATED_BASE else trade_type
    motive = build_motive(finder, deal, record_type, served)
    if not deal.reason:
        deal = Deal(teams=deal.teams, moves=deal.moves, reason=motive.why, pick_protections=deal.pick_protections)
    if not finder.execute_deal(deal, motive):
        return False
    remember_moves(finder, deal)
    finder.close_wishes(served.values())   # each wish closes when fulfilled: once per window
    return True
