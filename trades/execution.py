"""One executor for any trade: a Deal (2, 3 or 4 teams) is validated, carried out, logged and recorded here."""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from core.config import CONFIG
from core.models import Giocatore
from trades.motive import TradeMotive, log_line
from trades.trade_validator import TradeValidator

if TYPE_CHECKING:
    from core.models import Squadra

main_log = logging.getLogger('main_sim')

# Record "type" and news title per team count: the old labels, which the trade history still shows.
RECORD_TYPE = {2: "2-Team", 3: "3-Team Blockbuster"}
NEWS_TITLE = {2: "🔄 TRADE COMPLETED!", 3: "💥 MEGA 3-TEAM TRADE!"}
# The years a year-less pick key ("R1-Team", old saves) is looked up in, nearest first.
LEGACY_PICK_YEARS = range(1, 10)


@dataclass
class Deal:
    """Who sends what to whom. A move is (from team name, to team name, Giocatore or pick string)."""
    teams: List['Squadra']
    moves: List[Tuple[str, str, Any]] = field(default_factory=list)
    reason: str = ""   # the free-text reason of old engines; kept on the record and the legacy log line
    pick_protections: Optional[dict] = None   # the deal's pick terms (asset -> protection), when it names any

    def gives(self, name: str) -> list:
        return [asset for src, _dst, asset in self.moves if src == name]

    def receives(self, name: str) -> list:
        return [asset for _src, dst, asset in self.moves if dst == name]

    def team_names(self) -> List[str]:
        return [t.nome for t in self.teams]

    def with_team(self, team: 'Squadra', moves: List[Tuple[str, str, Any]]) -> 'Deal':
        return Deal(teams=list(self.teams) + [team], moves=list(self.moves) + list(moves), reason=self.reason,
                    pick_protections=self.pick_protections)

    def team(self, name: str) -> Optional['Squadra']:
        return next((t for t in self.teams if t.nome == name), None)


def _pick_protection(finder, asset: str, key: str, year: int, from_team, pick_protections: Optional[dict]) -> str:
    """What protection a pick carries after the trade. Only first-rounders can be protected."""
    if not key.startswith("R1"):
        return "Unprotected"
    if year == 1 and getattr(finder, 'window', None) in ("predraft", "draft"):
        return "Unprotected"   # the order of this draft is known: no "Top 3" on a pick that already has its number
    stored =getattr(finder.torneo, 'pick_protections', {}).get(year, {})
    if pick_protections is not None:
        for k in (asset, key, f"{year}:{key}"):
            if k in pick_protections:
                return pick_protections[k]
        return stored.get(key, "Unprotected")
    if key in stored:
        return stored[key]
    original_team = key.split("-", 1)[1] if "-" in key else ""
    if from_team.nome == original_team:
        return finder.get_cpu_pick_protection(from_team, key)
    return "Unprotected"


def transfer_pick(finder, asset: str, from_team, to_team, pick_protections: Optional[dict]) -> None:
    """Moves a pick ("Y:R1-Team", or year-less "R1-Team" from old saves) and settles its protection.

    Protection: the one named in `pick_protections` (the deal's terms) if any; else the one already stored;
    else, when nothing was named at all and the original team trades its own first-rounder, that CPU GM's choice.
    Unknown picks are ignored."""
    torneo = finder.torneo
    if ":" in asset:
        y_str, key = asset.split(":", 1)
        try:
            years = [int(y_str)]
        except ValueError:
            return
    elif asset.startswith("R1-") or asset.startswith("R2-"):
        key, years = asset, LEGACY_PICK_YEARS
    else:
        return
    for year in years:
        if key not in torneo.pick_ownership.get(year, {}):
            continue
        torneo.pick_ownership[year][key] = to_team.nome
        prot = _pick_protection(finder, asset, key, year, from_team, pick_protections)
        torneo.pick_protections.setdefault(year, {})[key] = prot
        return


def _players(assets: list) -> List[Giocatore]:
    return [a for a in assets if isinstance(a, Giocatore)]


def _picks(assets: list) -> List[str]:
    return [a for a in assets if isinstance(a, str)]


def validate_deal(finder, deal: Deal) -> Tuple[bool, str]:
    """TradeValidator on every team's two flows (what it sends, what it gets). Two teams: validate_trade as is."""
    names = deal.team_names()
    for src, dst, asset in deal.moves:
        if src not in names or dst not in names or src == dst:
            return False, f"Move {src} -> {dst} is not between two teams of the deal."
        if isinstance(asset, Giocatore) and asset not in deal.team(src).roster:
            return False, f"{asset.nome} is not on the {src} roster."
    torneo = finder.torneo
    if len(deal.teams) == 2:
        a, b = deal.teams
        return TradeValidator.validate_trade(a, b, deal.gives(a.nome), deal.gives(b.nome), torneo=torneo)

    all_players = _players([m[2] for m in deal.moves])
    reason = (TradeValidator._find_contractless(all_players)
              or TradeValidator._check_trade_cooldown(all_players)
              or TradeValidator._check_pick_not_drafted(_picks([m[2] for m in deal.moves])))
    if reason:
        return False, reason
    cba = getattr(torneo, 'cba_mode', 'realistic') if torneo else 'realistic'
    for team in deal.teams:
        out_p, in_p = _players(deal.gives(team.nome)), _players(deal.receives(team.nome))
        if cba != 'no_cap':
            ok, why = TradeValidator._check_salary_match(team, in_p, out_p)
            if not ok:
                return False, f"{team.nome} CBA salary violation: {why}"
        reason = TradeValidator._check_roster_after_trade(team, out_p, len(in_p))
        if reason:
            return False, reason
        r1_picks = [pk for pk in _picks(deal.gives(team.nome)) if "R1" in pk]
        if torneo and r1_picks:
            ok, why = TradeValidator.check_stepien_rule(torneo, team.nome, r1_picks)
            if not ok:
                return False, why
    return True, "Trade Valid"


def _roster_cuts(finder, deal: Deal) -> None:
    for team in deal.teams:
        out_p = _players(deal.gives(team.nome))
        in_p = _players(deal.receives(team.nome))
        needed = len(team.roster) + len(in_p) - len(out_p) - CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT
        if needed > 0:
            for m in TradeValidator.execute_roster_cuts(team, needed, out_p, finder.torneo):
                main_log.info(m)
                if getattr(finder, 'logscambi', None) is not None:
                    finder.logscambi.append(m)


def _move_player(p: Giocatore, src, dst) -> None:
    src.roster.remove(p)
    dst.roster.append(p)
    p.squadra = dst
    p.anni_nella_squadra = 0
    p.morale = 95  # fresh start morale boost
    p.on_trade_block = False
    p.giorni_cooldown_scambio = 30
    if hasattr(p, '_wants_out'):
        p._wants_out = False
    # Whatever he refused his old team (contracts.walk_reason), he starts fresh with the new one
    p.walks_away = ""
    p.is_flight_risk = False
    if hasattr(p, 'invalidate_trade_value_cache'):
        p.invalidate_trade_value_cache()


def _log_message(finder, deal: Deal, motive: Optional[TradeMotive], pick_protections: Optional[dict]) -> str:
    def fmt(assets):
        return ", ".join(finder._format_asset(a, pick_protections) for a in assets)

    if motive is not None:
        return log_line(motive, {n: fmt(deal.receives(n)) for n in deal.team_names()})
    if len(deal.teams) == 2:
        a, b = deal.team_names()
        return (f"TRADE: {a} sends [{fmt(deal.gives(a))}] <--> "
                f"{b} sends [{fmt(deal.gives(b))}]. Reason: {deal.reason}")
    flows: Dict[Tuple[str, str], list] = {}
    for src, dst, asset in deal.moves:
        flows.setdefault((src, dst), []).append(asset)
    parts = "; ".join(f"{src} sends [{fmt(assets)}] to {dst}" for (src, dst), assets in flows.items())
    return f"{len(deal.teams)}-TEAM TRADE: {parts}. Reason: {deal.reason}"


def _publish_news(finder, deal: Deal, msg: str, motive: Optional[TradeMotive] = None,
                  pick_protections: Optional[dict] = None) -> None:
    """The trade as a structured news item: headline on the best player moved, one entry per team with what
    it gets and (CPU trades) its GM's reasons."""
    try:
        from core.models import Giocatore
        from core.news_generator import add_news, trade_tier
        names = deal.team_names()
        moved = [(src, dst, a) for src, dst, a in deal.moves if isinstance(a, Giocatore)]
        best = max(moved, key=lambda m: m[2].ovr, default=None)
        if best is not None and len(names) == 2:
            title = f"{best[1]} acquire {best[2].nome} from {best[0]}"
        elif best is not None:
            title = f"{len(names)}-team trade sends {best[2].nome} to {best[1]}"
        else:
            title = f"{' and '.join(names[:2])} swap draft picks"
        motives = {side.team: side for side in (motive.sides if motive is not None else [])}
        sides = []
        for name in names:
            side = motives.get(name)
            sides.append({
                "team": name,
                "gets": [finder._format_asset(a, pick_protections) for a in deal.receives(name)],
                "gm": getattr(side, 'gm_name', None),
                "plan": getattr(side, 'plan', None),
                "reasons": list(getattr(side, 'reasons', []) or []),
            })
        why = (motive.why if motive is not None else "") or (deal.reason or "")
        add_news(category="trades", title=title, excerpt=why or msg, teams=names, is_breaking=True,
                 season=getattr(finder.torneo, 'season_number', 1), kind="trade",
                 tier=trade_tier(best[2].ovr if best is not None else None),
                 players=[m[2].nome for m in moved], details={"sides": sides, "line": msg})
    except Exception as ex:
        main_log.error(f"Failed to log trade news: {ex}")


def execute_deal(finder, deal: Deal, motive: Optional[TradeMotive] = None,
                 pick_protections: Optional[dict] = None) -> bool:
    """Validates and carries out the deal. Nothing changes when a rule fails."""
    if pick_protections is None:
        pick_protections = deal.pick_protections
    ok, why = validate_deal(finder, deal)
    if not ok:
        main_log.debug(f"Trade blocked [{' / '.join(deal.team_names())}]: {why}")
        return False
    try:
        _roster_cuts(finder, deal)
        for src, dst, asset in deal.moves:
            if isinstance(asset, Giocatore):
                _move_player(asset, deal.team(src), deal.team(dst))
            elif isinstance(asset, str):
                transfer_pick(finder, asset, deal.team(src), deal.team(dst), pick_protections)
        for team in deal.teams:
            team.scegli_quintetto_iniziale()

        msg = _log_message(finder, deal, motive, pick_protections)
        finder.logscambi.append(msg)
        finder._log_trade_to_file(msg)
        main_log.info(msg)
        sides = [{"team": t, "gives": deal.gives(t.nome), "receives": deal.receives(t.nome)} for t in deal.teams]
        try:
            finder._record_trade_analytics_snapshot(
                trade_type=RECORD_TYPE.get(len(deal.teams), f"{len(deal.teams)}-Team Mega-Blockbuster"),
                teams_data=sides, reason=deal.reason, motive=motive)
        except Exception as ex:
            main_log.error(f"Trade analytics record failed: {ex}", exc_info=True)
        _publish_news(finder, deal, msg, motive, pick_protections)
        finder._record_front_office_trade(sides)
        finder._clear_trade_caches(deal.team_names())
        return True
    except Exception as e:
        main_log.error(f"Trade execution crash: {e}", exc_info=True)
        return False
