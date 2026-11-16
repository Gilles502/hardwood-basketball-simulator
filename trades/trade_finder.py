from typing import Iterable, List, Optional, Tuple, Dict, Any, TYPE_CHECKING
import random
import logging
from core import runtime_state
from core.config import CONFIG
from core import paths
from core.save_manager import get_active_save_name, get_save_path, get_historical_file_path
from core.models import Giocatore, Squadra
from trades.trade_validator import TradeValidator
from trades import execution
from trades.execution import Deal
from trades.motive import TradeMotive
from core.front_office import trade_brain
from core.front_office.era_lines import EraLines, era_lines_for
from core.front_office.state import user_team_name
from core.front_office.wishes import Wish, WishContext, build_wishes, fulfils, plan_hard_no
from core.front_office.wishes import wants_out as wants_out_of

if TYPE_CHECKING:
    from main import Tournament

main_log = logging.getLogger('main_sim')

PLAN_REFUSAL = "{team} has no use for this deal right now"   # the plan question's refusal (user-facing)
# The wishes behind the offers the user gets for the pick on the clock.
DRAFT_WISH_KINDS = ("MOVE_UP_DRAFT", "TARGET_PROSPECT", "MOVE_DOWN_DRAFT")

from core.roles import normalize_role  # English standard (PG/SG/SF/PF/C)


def _star_tier(tiers, ovr: int, star_line: int) -> float:
    """First (offset from the star line, value) tier the OVR reaches; offset None matches any OVR."""
    for offset, value in tiers:
        if offset is None or ovr >= star_line + offset:
            return value
    return tiers[-1][1]


def _root_trade_log_path() -> str:
    """The league-wide trade log, in the user root (the project folder in dev)."""
    return paths.user_path("trades_history.txt")


class TradeFinder:
    """
    Advanced Trade System v4.0 - Needs & Rules Based
    """
    
    def __init__(self, torneo: 'Tournament', squadre: List['Squadra'], squadra_giocatore: Optional['Squadra'] = None):
        self.torneo = torneo
        self.squadre = squadre
        user_role = getattr(torneo, 'user_role', 'gm_coach')
        # In 'only_coach' mode, the user is the Head Coach: the AI General Manager actively runs front office trades!
        if user_role == 'only_coach':
            self.squadra_giocatore = None
        else:
            self.squadra_giocatore = squadra_giocatore
        self.logscambi = []
        self.window = "user"          # "deadline" | "predraft" | "draft" | "user" (a user trade, any day)
        self._league_lines = None
        self._era: Optional[EraLines] = None
        self._wishes: Dict[str, List[Wish]] = {}
        self._wish_contexts: Dict[str, WishContext] = {}
        self._closed_wishes: set = set()   # wishes fulfilled by a deal in this window (see close_wishes)

    # ========================================================================
    # ERA LINES, WINDOW AND WISHES
    # ========================================================================

    def era(self) -> EraLines:
        """The league's era lines (core/front_office/era_lines.py), read once per finder / window."""
        if self._era is None:
            self._era = era_lines_for(self.torneo)
        return self._era

    def begin_window(self, window: str) -> None:
        """A new trade window: the era lines and every team's wishes are read afresh."""
        self.window = window
        self._era = None
        self._league_lines = None
        self._wishes.clear()
        self._wish_contexts.clear()
        self._closed_wishes.clear()

    def _is_user_team(self, team: 'Squadra') -> bool:
        return bool(self.squadra_giocatore) and team.nome == self.squadra_giocatore.nome

    def _owns_r1_this_year(self, team: 'Squadra') -> bool:
        ownership = (getattr(self.torneo, 'pick_ownership', None) or {}).get(1, {})
        return any(key.startswith("R1") and owner == team.nome for key, owner in ownership.items())

    def _draft_prospects(self, team: 'Squadra') -> Tuple[Tuple[str, str], ...]:
        """Draft window: (role, pick) of the prospects projected to go before this team's first pick.

        The board is the remaining draft class by potential; prospect i goes at overall pick
        draft_pick_corrente + i + 1 of the first round (draft_lottery_order). Picks are in wish format."""
        order = list(getattr(self.torneo, 'draft_lottery_order', None) or [])
        board = sorted(getattr(self.torneo, 'draft_class', None) or [], key=lambda p: p.potenziale, reverse=True)
        if not order or not board:
            return ()
        made = int(getattr(self.torneo, 'draft_pick_corrente', 0) or 0)
        ownership = (getattr(self.torneo, 'pick_ownership', None) or {}).get(1, {})
        own = [order.index(key.split("-", 1)[1]) + 1 for key, owner in ownership.items()
               if owner == team.nome and key.startswith("R1-") and key.split("-", 1)[1] in order]
        own_pick = min((pos for pos in own if pos > made), default=len(order) + 1)
        year = self.era().year
        prospects = []
        for i, prospect in enumerate(board):
            pos = made + i + 1
            if pos >= own_pick or pos > len(order):
                break
            prospects.append((normalize_role(prospect.ruolo), f"{year}:R1-{order[pos - 1]}"))
        return tuple(prospects)

    def _move_up_slot(self, team: 'Squadra'):
        """Predraft and draft windows: the overall slot this team would move up to for a prospect it wants
        (draft_fit.move_up_slot on the same board as _draft_prospects), else None."""
        from core.front_office.draft_fit import move_up_slot
        order = list(getattr(self.torneo, 'draft_lottery_order', None) or [])
        if not order:
            return None
        made = int(getattr(self.torneo, 'draft_pick_corrente', 0) or 0)
        board = sorted(getattr(self.torneo, 'draft_class', None) or [], key=lambda p: p.potenziale, reverse=True)
        ownership = (getattr(self.torneo, 'pick_ownership', None) or {}).get(1, {})
        own = [order.index(key.split("-", 1)[1]) + 1 for key, owner in ownership.items()
               if owner == team.nome and key.startswith("R1-") and key.split("-", 1)[1] in order]
        own_pick = min((pos for pos in own if pos > made), default=None)
        if not board or own_pick is None:
            return None
        return move_up_slot(board, made, own_pick, team.roster, self.era(), self.get_team_strategy(team),
                            gm=self.get_gm(team), year=self.era().year)

    def wish_context(self, team: 'Squadra') -> WishContext:
        ctx = self._wish_contexts.get(team.nome)
        if ctx is None:
            games = team.vittorie + team.sconfitte
            ctx = WishContext(
                era=self.era(), plan=self.get_team_strategy(team), gm=self.get_gm(team),
                owner=self.get_manager_personality(team), window=self.window,
                win_pct=(team.vittorie / games) if games > 0 else 0.5, games=games,
                has_r1_this_year=self._owns_r1_this_year(team),
                prospects=self._draft_prospects(team) if self.window == "draft" else (),
                move_up_slot=self._move_up_slot(team) if self.window in ("predraft", "draft") else None)
            order = list(getattr(self.torneo, 'draft_lottery_order', None) or [])
            if ctx.move_up_slot is not None and 0 < ctx.move_up_slot <= len(order):
                ctx.move_up_pick = f"{self.era().year}:R1-{order[ctx.move_up_slot - 1]}"
            self._wish_contexts[team.nome] = ctx
        return ctx

    def wishes_for(self, team: 'Squadra') -> List[Wish]:
        """The team's open wishes in this window, highest priority first (cached until it trades). A wish a deal
        already fulfilled in this window is closed (`close_wishes`) and left out even when the team still has it."""
        wishes = self._wishes.get(team.nome)
        if wishes is None:
            wishes = [w for w in build_wishes(team, self.wish_context(team)) if w not in self._closed_wishes]
            self._wishes[team.nome] = wishes
        return wishes

    def close_wishes(self, wishes: Iterable[Optional[Wish]]) -> None:
        """Wishes a deal just fulfilled (initiator's and partners'): closed until the next `begin_window`, so a
        wish that does not go away with the trade (a trade-happy GM, room under the tax, wanting picks) is not
        served again in the same window, as initiator or as partner."""
        closed = [w for w in wishes if w is not None]
        self._closed_wishes.update(closed)
        self._clear_trade_caches({w.team for w in closed})

    def _wish_asset(self, asset: Any) -> Any:
        """A deal asset in the wishes' format: a finder pick "N:R1-Team" (N = 1 for this year's draft) becomes
        "<era year + N - 1>:R1-Team"; players and legacy keys pass through."""
        if isinstance(asset, str) and ":" in asset:
            n, key = asset.split(":", 1)
            if n.isdigit():
                return f"{self.era().year + int(n) - 1}:{key}"
        return asset

    def plan_check(self, team: 'Squadra', receives: list, gives: list) -> Tuple[bool, str, Optional[Wish]]:
        """The plan question: does the deal fulfil one of the team's wishes and break none of its hard no's?

        The user's own team is never asked. Returns (yes, refusal sentence, the wish fulfilled)."""
        if self._is_user_team(team):
            return True, "", None
        r = [self._wish_asset(a) for a in receives]
        g = [self._wish_asset(a) for a in gives]
        hard_no = plan_hard_no(team, self.wish_context(team), r, g)
        if hard_no:
            return False, hard_no, None
        era = self.era()
        for wish in self.wishes_for(team):
            if fulfils(wish, r, g, team, era):
                return True, "", wish
        return False, PLAN_REFUSAL.format(team=team.nome), None

    # ========================================================================
    # THE USER'S TOOLS: the same wishes, and the CPU side's reason
    # ========================================================================

    def pair_deal(self, team_a: 'Squadra', team_b: 'Squadra', a_gives: list, b_gives: list, reason: str = "") -> Deal:
        moves = ([(team_a.nome, team_b.nome, a) for a in a_gives] + [(team_b.nome, team_a.nome, a) for a in b_gives])
        return Deal([team_a, team_b], moves, reason=reason)

    def three_team_deal(self, team_a: 'Squadra', team_b: 'Squadra', team_c: 'Squadra', trade_data: dict,
                        reason: str = "") -> Deal:
        """trade_data {"team_a": {"gives_to_b": [...], ...}, ...} (a player may be given by name) as a Deal."""
        teams_map = {"team_a": team_a, "team_b": team_b, "team_c": team_c}
        moves = []
        for src_key, src_team in teams_map.items():
            for dest_key, assets in trade_data.get(src_key, {}).items():
                dest_team = teams_map.get("team_" + dest_key.split("_")[-1] if dest_key.startswith("gives_to_") else dest_key)
                if not dest_team:
                    continue
                for a in assets:
                    if isinstance(a, str) and ":" not in a:
                        a = next((p for p in src_team.roster if p.nome.lower() == a.lower()), a)
                    moves.append((src_team.nome, dest_team.nome, a))
        return Deal([team_a, team_b, team_c], moves, reason=reason)

    def four_team_deal(self, teams: List['Squadra'], flow: List[Dict], reason: str = "") -> Optional[Deal]:
        """A 4-team flow (steps from/to/players/picks, names in any case) as a Deal; None when a team is unknown."""
        teams_map = {t.nome.lower(): t for t in teams}
        moves = []
        for step in flow:
            from_t = teams_map.get(step["from"].lower())
            to_t = teams_map.get(step["to"].lower())
            if not from_t or not to_t:
                return None
            for p in step.get("players", []):
                if isinstance(p, str):
                    p = next((x for x in from_t.roster if x.nome.lower() == p.lower()), None)
                if isinstance(p, Giocatore):
                    moves.append((from_t.nome, to_t.nome, p))
            moves.extend((from_t.nome, to_t.nome, pk) for pk in step.get("picks", []))
        return Deal(list(teams), moves, reason=reason)

    def user_motive(self, deal: Deal, wishes: Optional[Dict[str, Wish]] = None) -> TradeMotive:
        """The motive of a deal the user is in: type "user", a side per team (the CPU sides first, each with the wish
        its plan question found, or the one given in `wishes`) and the CPU sides' why line."""
        from trades.engines.common import build_motive
        wishes = dict(wishes or {})
        for team in deal.teams:
            if not self._is_user_team(team) and team.nome not in wishes:
                wish = self.plan_check(team, deal.receives(team.nome), deal.gives(team.nome))[2]
                if wish is not None:
                    wishes[team.nome] = wish
        motive = build_motive(self, deal, "user", wishes)
        motive.sides.sort(key=lambda s: s.plan == "USER")
        return motive

    def asset_for_wish(self, cpu: 'Squadra', user: 'Squadra', gets: list, gives: list) -> Optional[Tuple[Any, Wish]]:
        """One more asset of the user's that fulfils the CPU team's highest-priority wish the user's roster can satisfy
        (`gets`: what the CPU team already receives; `gives`: what it sends), with that wish, or None.
        Cheapest assets first: the players the CPU team values least, then the user's picks."""
        from trades.engines.common import wish_fulfilled
        taken = {id(a) for a in gets if not isinstance(a, str)}
        players = sorted((p for p in self.get_tradeable_players(user) if id(p) not in taken and p.contract),
                         key=lambda p: self.get_strategic_value(p, cpu))
        picks = [f"{year}:{key}" for year, key in self._collect_team_picks(user) if f"{year}:{key}" not in gets]
        for wish in self.wishes_for(cpu):
            for asset in players + picks:
                if wish_fulfilled(self, cpu, wish, gets + [asset], gives):
                    return asset, wish
        return None
    
    # ========================================================================
    # STRATEGY & PERSONALITY
    # ========================================================================
    
    def get_team_strategy(self, team: 'Squadra') -> str:
        """
        Determines whether a team is Buyer (Contender), Seller (Rebuilder) or Middle
        using the simulator's new advanced states and the mid-season record.
        """
        if not self.torneo: return "MIDDLE"

        # Priority: if a formal goal was agreed at the GM/Coach Summit
        summit = getattr(team, 'front_office_summit', None)
        if isinstance(summit, dict) and summit.get('completed'):
            agreed_goal = summit.get('agreed_goal')
            if agreed_goal in ["TANKING", "ASSET_GROWTH"]:
                return "REBUILDER"
            elif agreed_goal in ["CHAMPIONSHIP", "DOMINANCE"]:
                return "CONTENDER"
            elif agreed_goal in ["PLAYOFFS", "SUSTAINABLE_CONTENDER"]:
                return "PLAYOFF"
            elif agreed_goal in ["PLAY_IN", "PLAYOFF_HUNT"]:
                return "MIDDLE"

        # AI GM: the team's saved plan (changed only at the season start or a deadline emergency, with a reason)
        fo = getattr(self.torneo, 'front_office', None)
        plan = fo.plans.get(team.nome) if fo is not None else None
        if plan is not None:
            return plan.state

        # Fallback without a front office: recomputed from the roster and the record
        stato_squadra = self.torneo._determina_stato_squadra(team)
        win_rate = 0.5
        game_played = team.vittorie + team.sconfitte
        if game_played > 0:
            win_rate = team.vittorie / game_played
            
        # Mid-season logic: if the season is well underway, the record weighs heavily
        is_mid_season = game_played >= 25
        
        if is_mid_season:
            # A contender that is terrible panics and rebuilds/sells
            if stato_squadra in ["Defending Champion", "Contender", "Playoff Team", "Aging Core"] and win_rate < 0.30:
                return "REBUILDER"
                
            # A mediocre team that is overperforming goes for it
            if stato_squadra in ["Mediocre", "Playoff Team"] and win_rate > 0.60:
                return "CONTENDER"
        
        # Base logic
        if stato_squadra in ["Defending Champion", "Contender"]:
            return "CONTENDER"
        elif stato_squadra in ["Playoff Team", "Aging Core"]:
            return "PLAYOFF"   # Playoff-caliber but not title favorites
        elif stato_squadra == "Rising Star":
            # If the team is young but already has a high overall, it behaves like a PLAYOFF team
            top_8 = sorted(team.roster, key=lambda p: p.ovr, reverse=True)[:8]
            media_ovr_top_8 = sum(p.ovr for p in top_8) / len(top_8) if top_8 else 0
            
            # Compute avg_top8
            total_top8_sum = 0
            teams_count = 0
            for s in self.squadre:
                if s.roster:
                    s_top8 = sorted(s.roster, key=lambda p: p.ovr, reverse=True)[:8]
                    total_top8_sum += sum(p.ovr for p in s_top8) / len(s_top8)
                    teams_count += 1
            avg_top8 = (total_top8_sum / teams_count) if teams_count > 0 else 80.0
            
            if media_ovr_top_8 >= max(80.0, avg_top8 - 1.0):
                return "PLAYOFF"
            return "REBUILDER"
        elif stato_squadra == "Rebuilding":
            return "REBUILDER"
        else:
            return "MIDDLE"

    def get_manager_personality(self, team: 'Squadra') -> str:
        """The owner's personality: how much may be spent. What the GM wants is `get_gm(team).traits`."""
        return getattr(team, 'personalita_proprietario', 'Bilanciato')

    def get_gm(self, team: 'Squadra'):
        """The CPU GM seated at this team; None without a front office or at the team the user runs as GM."""
        fo = getattr(self.torneo, 'front_office', None)
        if fo is None or team is None or team.nome == user_team_name(self.torneo):
            return None
        return fo.seated_gm(team.nome)

    def _vultures_first(self, teams: list) -> list:
        """AI GM: skilled traders spot a dump first. The first VULTURE_GUARANTEED_SLOTS vultures (in their
        shuffled order) move to the front; everybody else, other vultures included, keeps the shuffled order."""
        slots = CONFIG.FRONT_OFFICE.VULTURE_GUARANTEED_SLOTS
        head = [t for t in teams if trade_brain.is_vulture(self.get_gm(t))][:slots]
        return head + [t for t in teams if not any(t is h for h in head)]

    def league_lines(self) -> Dict[str, Any]:
        """League-relative lines for this trade window: star/core protection, cap (from `era()`), profile lines."""
        if self._league_lines is None:
            players = [p for t in self.squadre for p in (getattr(t, 'roster', None) or [])]
            era = self.era()
            self._league_lines = {
                "star": era.star, "core": era.core, "cap": era.cap,
                "profiles": trade_brain.profile_lines(players),
            }
        return self._league_lines

    def get_cpu_pick_protection(self, team: 'Squadra', pick_key: str) -> str:
        # Only first round picks can be protected
        if not pick_key.startswith("R1"):
            return "Unprotected"
            
        # Check if the team is the original owner of the pick
        orig_owner = pick_key.split("-", 1)[1] if "-" in pick_key else ""
        if team.nome != orig_owner:
            return "Unprotected"
            
        strategy = self.get_team_strategy(team)
        win_rate = 0.5
        games = team.vittorie + team.sconfitte
        if games > 0: 
            win_rate = team.vittorie / games

        # Rebuilders or bottom teams protect their picks moderately
        if strategy == "REBUILDER" or win_rate < 0.35:
            if win_rate < 0.25:
                return "Top 5"
            else:
                return "Top 3"
                
        # Middle-tier teams protect their picks lightly (only if they are struggling)
        elif strategy == "MIDDLE" or win_rate < 0.45:
            if win_rate < 0.38:
                return "Top 3"
            else:
                return "Unprotected"
                
        # Playoff-caliber teams, contenders, and champions do not protect their picks
        return "Unprotected"

    # ========================================================================
    # STRATEGIC VALUATION
    # ========================================================================
    
    def get_strategic_value(self, asset: Any, team: 'Squadra', pick_protections: Optional[Dict[str, str]] = None) -> float:
        """
        Value for a *specific* team based on its strategy.
        """
        strategy = self.get_team_strategy(team)
        from core.models import Giocatore
        era = self.era()

        base_value = 0
        if isinstance(asset, Giocatore):
            base_value = float(asset.trade_value) # Uses the new internal trade_value property
            
            if strategy in ["CONTENDER", "PLAYOFF"]:
                if asset.eta >= 28: base_value *= 1.08 # Moderated from 1.15
            elif strategy == "REBUILDER":   # CONFIG.TRADES.REBUILDER_*: what a player is worth to a rebuild
                rb = CONFIG.TRADES
                if asset.eta <= 24:
                    base_value *= rb.REBUILDER_YOUTH_MULT
                elif asset.ovr >= era.star:
                    base_value *= rb.REBUILDER_STAR_SHARE
                elif asset.eta >= rb.REBUILDER_VET_AGE:
                    c = getattr(asset, 'contract', None)
                    years = int(getattr(c, 'anni_rimanenti', 0) or 0)
                    dump = c is not None and (years <= 1 or era.is_high_contract(float(c.salario_annuale), years))
                    base_value *= rb.REBUILDER_DUMP_VET_SHARE if dump else rb.REBUILDER_VET_SHARE
                else:
                    base_value *= rb.REBUILDER_PRIME_SHARE
                
        elif isinstance(asset, str): # Pick
            pick_year = 1
            p_key = asset
            if ":" in asset:
                try:
                    y_str, p_key = asset.split(":", 1)
                    pick_year = int(y_str)
                except ValueError:
                    pass
                    
            # Get pick protection
            prot = "Unprotected"
            if pick_protections is not None:
                if asset in pick_protections:
                    prot = pick_protections[asset]
                elif p_key in pick_protections:
                    prot = pick_protections[p_key]
                elif f"{pick_year}:{p_key}" in pick_protections:
                    prot = pick_protections[f"{pick_year}:{p_key}"]
                elif self.torneo and hasattr(self.torneo, 'pick_protections') and p_key in self.torneo.pick_protections.get(pick_year, {}):
                    prot = self.torneo.pick_protections[pick_year][p_key]
                else:
                    prot = "Unprotected"
            elif self.torneo and hasattr(self.torneo, 'pick_protections') and p_key in self.torneo.pick_protections.get(pick_year, {}):
                prot = self.torneo.pick_protections[pick_year][p_key]
            else:
                # Default CPU heuristic only if no protection was ever established
                current_owner_name = self.torneo.pick_ownership.get(pick_year, {}).get(p_key) if self.torneo else None
                if not current_owner_name:
                    current_owner_name = p_key.split("-", 1)[1] if "-" in p_key else ""
                owner_team = next((t for t in self.squadre if t.nome == current_owner_name), None)
                if owner_team:
                    prot = self.get_cpu_pick_protection(owner_team, p_key)
                else:
                    prot = "Unprotected"
                
            base_value = self.get_pick_value(p_key, pick_year, protection=prot, on_curve=True)
                
            if strategy == "REBUILDER": base_value *= 1.15 # Moderated from 1.30
            elif strategy in ["CONTENDER", "PLAYOFF"]: base_value *= 0.92 # Moderated from 0.85
            
        if strategy == "REBUILDER" or self.get_manager_personality(team) == "Risparmiatore":
            # A player with only 1 year left on his contract (Expiring) is worth MORE to me,
            # because he frees up cap space in the summer.
            if isinstance(asset, Giocatore) and asset.contract.anni_rimanenti == 1:
                base_value *= 1.15 # Moderated from 1.40
            
            # A player with 3+ years of heavy contract ($15M at the reference cap) is worth much LESS to me
            if isinstance(asset, Giocatore) and asset.contract.anni_rimanenti >= 3 and asset.contract.salario_annuale > era.money(15.0):
                if asset.ovr < era.star: # The TRUE STARS are worth their max contract, they are not a burden
                    base_value *= 0.80 # Moderated from 0.60
        return base_value * self._gm_value_multiplier(asset, team)

    def _gm_value_multiplier(self, asset: Any, team: 'Squadra') -> float:
        """AI GM: what this team's GM is willing to pay for the asset (philosophy and coach fit). 1.0 without a GM."""
        gm = self.get_gm(team)
        if gm is None:
            return 1.0
        lines = self.league_lines()
        own = isinstance(asset, Giocatore) and any(p is asset for p in (getattr(team, 'roster', None) or []))
        tags = trade_brain.asset_tags(asset, own=own, star_line=lines["star"], cap=lines["cap"],
                                      lines=lines["profiles"])
        style = getattr(getattr(team, 'coach', None), 'stile_gioco', None)
        return (trade_brain.trait_multiplier(gm, tags)
                * trade_brain.coach_fit_multiplier(style, asset, lines["profiles"]))

    def _comes_from_user(self, assets: list) -> bool:
        """True when any asset is a player on the user's team or a pick the user owns (the user is the GM)."""
        user = user_team_name(self.torneo)
        if user is None:
            return False
        team = next((t for t in self.squadre if t.nome == user), None)
        roster = getattr(team, 'roster', None) or []
        ownership = getattr(self.torneo, 'pick_ownership', None) or {}
        for asset in assets:
            if isinstance(asset, str):
                year, key = (asset.split(":", 1) if ":" in asset else (None, asset))
                years = [int(year)] if year is not None and year.isdigit() else list(ownership)
                if any(ownership.get(y, {}).get(key) == user for y in years):
                    return True
            elif any(p is asset for p in roster):
                return True
        return False

    def _prospect_pick_value(self, pick_key: str) -> Optional[float]:
        """CONFIG.DRAFT_AI.PICK_VALUE_FROM_PROSPECT: a first of this draft with a known slot is worth the trade value of
        the prospect projected there (draft_fit.projected_prospect); None when the slot or the class is unknown, or
        during the season (the lottery of this draft is not drawn yet)."""
        if not CONFIG.DRAFT_AI.PICK_VALUE_FROM_PROSPECT or not pick_key.startswith("R1"):
            return None
        if getattr(self.torneo, 'fase_torneo', 'OFFSEASON') != "OFFSEASON":   # an order left from last year's draft
            return None
        order = list(getattr(self.torneo, 'draft_lottery_order', None) or [])
        team = pick_key.split("-", 1)[1] if "-" in pick_key else ""
        if team not in order:
            return None
        from core.front_office.draft_fit import projected_prospect
        prospect = projected_prospect(self.torneo, order.index(team) + 1)
        if prospect is None:
            return None
        try:
            return max(CONFIG.TRADES.PICK_R2_BASE_VALUE, float(prospect.trade_value))
        except Exception:
            return None

    def get_pick_value(self, pick_key: str, year: int = 1, protection: str = "Unprotected",
                       on_curve: bool = False) -> float:
        """A pick's worth. Raw (default): the old 40-150 first-round scale the rule lines are written in.
        `on_curve`: the trade value, in the same units as a player's trade_value (CONFIG.TRADES.PICK_CURVE_POINTS)."""
        if pick_key.startswith("R1"):
            base = 45.0
            # If we are in year 1 and the lottery has already been generated, we can know the EXACT value
            if year == 1 and hasattr(self.torneo, 'draft_lottery_order') and getattr(self.torneo, 'draft_lottery_order', None):
                # pick_key format is "R1-TeamName"
                parts = pick_key.split("-")
                if len(parts) > 1:
                    original_team = parts[1]
                    if original_team in self.torneo.draft_lottery_order:
                        pick_num = self.torneo.draft_lottery_order.index(original_team) + 1
                        if pick_num == 1: base = 150.0  # Generational
                        elif pick_num == 2: base = 135.0
                        elif pick_num == 3: base = 125.0
                        elif pick_num <= 10:
                            # scale from 115 (pick 4) to 90 (pick 10)
                            base = 115.0 - (pick_num - 4) * 4.16
                        elif pick_num <= 14:
                            # scale from 85 (pick 11) to 75 (pick 14)
                            base = 85.0 - (pick_num - 11) * 3.33
                        elif pick_num <= 20:
                            # scale from 70 (pick 15) to 55 (pick 20)
                            base = 70.0 - (pick_num - 15) * 3.0
                        else:
                            # scale from 50 (pick 21) to 40 (pick 30)
                            base = 50.0 - (pick_num - 21) * 1.11
            else:
                # Projection based on the original team's record and strategy
                parts = pick_key.split("-")
                if len(parts) > 1:
                    original_team_name = parts[1]
                    original_team = next((t for t in self.squadre if t.nome == original_team_name), None)
                    if original_team:
                        win_rate = 0.5
                        games = original_team.vittorie + original_team.sconfitte
                        if games > 0: win_rate = original_team.vittorie / games
                        
                        strategy = self.get_team_strategy(original_team)
                        if strategy == "REBUILDER" or win_rate < 0.35:
                            base = 90.0  # Projected High Lottery
                        elif win_rate < 0.45:
                            base = 70.0  # Projected Lottery
                        elif win_rate > 0.60:
                            base = 50.0  # Projected Late 1st
                        else:
                            base = 55.0  # Middle of the pack
        else:
            base = CONFIG.TRADES.PICK_R2_BASE_VALUE if on_curve and CONFIG.TRADES.VALUE_CURVE_SCALE > 0 else 22.0
        prospect_value = self._prospect_pick_value(pick_key) if on_curve and year == 1 else None
        if prospect_value is not None:
            base = prospect_value / max(self.era().pick_scale, 1e-6)   # already in player units: no curve, no scale
        elif on_curve and pick_key.startswith("R1") and CONFIG.TRADES.VALUE_CURVE_SCALE > 0:
            from core.models import trade_curve_value
            (b0, o0), (b1, o1) = CONFIG.TRADES.PICK_CURVE_POINTS
            base = max(CONFIG.TRADES.PICK_R2_BASE_VALUE, trade_curve_value(o0 + (base - b0) * (o1 - o0) / (b1 - b0)))

        base *= (0.85 ** (year - 1)) # Depreciate the future picks
        
        # Apply protection discounts
        if protection == "Top 3":
            base *= 0.85
        elif protection == "Top 5":
            base *= 0.75
        elif protection == "Lottery":
            base *= 0.60

        return base * self.era().pick_scale  # picks are worth more in a league whose players are worth more
    
    def _format_asset(self, asset: Any, pick_protections: Optional[Dict[str, str]] = None) -> str:
        from core.models import Giocatore
        if isinstance(asset, Giocatore):
            return f"{asset.nome} ({asset.ovr}, ${asset.contract.salario_annuale}M)"
        if isinstance(asset, str):
            if ":" in asset:
                try:
                    y_str, pick_key = asset.split(":", 1)
                    pick_year = int(y_str)
                    season_num = getattr(self.torneo, 'season_number', 1)
                    starting_year = getattr(self.torneo, 'starting_year', 2025)
                    draft_year = starting_year + season_num + pick_year - 1
                    
                    # Resolve protection
                    prot = "Unprotected"
                    if pick_protections and (asset in pick_protections or pick_key in pick_protections or f"{pick_year}:{pick_key}" in pick_protections):
                        prot = pick_protections.get(asset, pick_protections.get(pick_key, pick_protections.get(f"{pick_year}:{pick_key}", "Unprotected")))
                    elif self.torneo and hasattr(self.torneo, 'pick_protections'):
                        prot = self.torneo.pick_protections.get(pick_year, {}).get(pick_key, "Unprotected")
                    
                    prot_suffix = f" ({prot})" if prot != "Unprotected" else ""
                    return f"{draft_year} {pick_key}{prot_suffix}"
                except ValueError:
                    pass
            # Legacy fallback
            if asset.startswith("R1-") or asset.startswith("R2-"):
                season_num = getattr(self.torneo, 'season_number', 1)
                starting_year = getattr(self.torneo, 'starting_year', 2025)
                base_year = starting_year + season_num - 1
                for pick_year in range(1, 10):
                    if asset in self.torneo.pick_ownership.get(pick_year, {}):
                        # Resolve protection
                        prot = "Unprotected"
                        if pick_protections and (asset in pick_protections or f"{pick_year}:{asset}" in pick_protections):
                            prot = pick_protections.get(asset, pick_protections.get(f"{pick_year}:{asset}", "Unprotected"))
                        elif self.torneo and hasattr(self.torneo, 'pick_protections'):
                            prot = self.torneo.pick_protections.get(pick_year, {}).get(asset, "Unprotected")
                        
                        prot_suffix = f" ({prot})" if prot != "Unprotected" else ""
                        return f"{base_year + pick_year} {asset}{prot_suffix}"
                return f"{base_year + 1} {asset}"
        return str(asset)

    def _get_pick_draft_position_from_asset(self, pick_asset: str) -> int:
        """Returns the projected draft position for a pick asset string (e.g. '1:R1-TeamName'). 0 = unknown."""
        pick_key = pick_asset
        if ":" in pick_asset:
            try:
                y_str, pick_key = pick_asset.split(":", 1)
            except ValueError:
                return 0
        return self._get_pick_position(pick_key)

    def _is_top5_pick(self, pick_asset: str) -> bool:
        """Returns True if this pick is a known top-5 pick OR has top-5 projected value (>=120.0)."""
        pos = self._get_pick_draft_position_from_asset(pick_asset)
        if 0 < pos <= 5:
            return True
        # Fallback: check by value (covers projected picks without lottery order)
        if ":" in pick_asset:
            try:
                y_str, pk = pick_asset.split(":", 1)
                val = self.get_pick_value(pk, int(y_str))
            except ValueError:
                val = 0
        elif pick_asset.startswith("R1"):
            val = self.get_pick_value(pick_asset, 1)
        else:
            return False
        return val >= 120.0 * self.era().pick_scale

    def _multi_first_bonus(self, num_firsts: int) -> float:
        """
        Returns the escalating bonus multiplier for multi-first-round-pick packages.
        IRL blockbuster trades with multiple firsts carry extra weight.
        """
        if num_firsts >= 4: return 1.45
        if num_firsts >= 3: return 1.30
        if num_firsts >= 2: return 1.15
        return 1.0

    def _collect_team_picks(self, team: 'Squadra') -> list:
        """
        Collects all picks owned by a team, deduplicated by pick_key.
        Returns list of (year, pick_key) tuples sorted by value (lowest first).
        """
        raw_picks = []
        active_draft = runtime_state.get_active_draft()
            
        for year in range(1, 6):
            for pick_key, owner in self.torneo.pick_ownership.get(year, {}).items():
                if owner == team.nome:
                    if active_draft and getattr(active_draft, 'pick_corrente', 0) > 0 and year == 1:
                        # Skip pick if already chosen in active draft
                        already_picked = False
                        for item in active_draft.get_draft_state().get("ordine", []):
                            item_key = f"R{item['round']}-{item['original_owner']}"
                            if item_key == pick_key and item['pick_index'] < active_draft.pick_corrente:
                                already_picked = True
                                break
                        if already_picked:
                            continue
                    raw_picks.append((year, pick_key))
        
        return sorted(raw_picks, key=lambda x: self.get_pick_value(x[1], x[0]))


    # ========================================================================
    # IMPROVED ACCEPTANCE LOGIC
    # ========================================================================
    
    def _received_player_value(self, team: 'Squadra', player: 'Giocatore',
                               pick_protections: Optional[Dict[str, str]] = None) -> float:
        """A player's worth to the team that receives him: its strategic value, and a rebuilder barely values a
        veteran role player (CONFIG.TRADES.REBUILDER_RECEIVED_VET_*)."""
        trades_cfg = CONFIG.TRADES
        v = self.get_strategic_value(player, team, pick_protections)
        if (self.get_team_strategy(team) == "REBUILDER" and player.eta >= trades_cfg.REBUILDER_VET_AGE
                and player.ovr < self.era().star):
            v *= trades_cfg.REBUILDER_RECEIVED_VET_SHARE
        return v

    def received_value(self, team: 'Squadra', assets: list, pick_protections: Optional[Dict[str, str]] = None) -> float:
        """What a package is worth to the team that receives it (the price question, before the multi-first bonus):
        players best first at CONFIG.TRADES.RECEIVED_PLAYER_SHARES (a roster spot has a cost; a young second player
        with POT >= the old 82 line counts in full), picks at their strategic value."""
        from core.models import Giocatore
        shares = CONFIG.TRADES.RECEIVED_PLAYER_SHARES
        players = sorted(((self._received_player_value(team, a, pick_protections), a) for a in assets
                          if isinstance(a, Giocatore)), key=lambda x: -x[0])
        total = 0.0
        for i, (value, p) in enumerate(players):
            share = shares[min(i, len(shares) - 1)]
            if i == 1 and p.eta <= 24 and p.potenziale >= self.era().ovr_at(82):
                share = 1.0
            total += value * share
        return total + sum(self.get_strategic_value(a, team, pick_protections) for a in assets if isinstance(a, str))

    def _pick_giving_refusal(self, receiving_assets: list, giving_assets: list) -> str:
        """Why a CPU team won't give these picks, or "": a first only for a player at or above
        CONFIG.TRADES.FIRST_PICK_MIN_OVR (or for another first), and a team sending a starter adds at most
        STARTER_SWAP_MAX_PICKS picks."""
        from core.models import Giocatore
        pick_cfg, era = CONFIG.TRADES, self.era()
        given_picks = [a for a in giving_assets if isinstance(a, str)]
        if not given_picks:
            return ""
        first_line, old_line = era.ovr_at(pick_cfg.FIRST_PICK_MIN_OVR), era.ovr_at(pick_cfg.FIRST_PICK_OLD_MIN_OVR)
        # a player between the two lines earns a first only while he is young enough (no first for an old 78)
        best_in = max((a.ovr for a in receiving_assets if isinstance(a, Giocatore)
                       and (a.ovr >= old_line or a.eta <= pick_cfg.FIRST_PICK_MAX_AGE_BELOW)), default=0)
        gets_first = any(isinstance(a, str) and "R1" in a for a in receiving_assets)
        if any("R1" in a for a in given_picks) and not gets_first and best_in < first_line:
            return (f"First-Round Pick Rule: a first-round pick goes only for a {first_line}+ OVR player "
                    f"({old_line}+ if older than {pick_cfg.FIRST_PICK_MAX_AGE_BELOW}) or another first")
        if (any(isinstance(a, Giocatore) and a.ovr >= era.starter for a in giving_assets)
                and len(given_picks) > pick_cfg.STARTER_SWAP_MAX_PICKS):
            return (f"Starter Swap Rule: a team sending a starter adds at most "
                    f"{pick_cfg.STARTER_SWAP_MAX_PICKS} pick(s)")
        return ""

    def would_accept_trade(self, receiving_team: 'Squadra', receiving_assets: list, giving_assets: list, pick_protections: Optional[Dict[str, str]] = None) -> bool:
        accepted, _ = self.would_accept_trade_with_reason(receiving_team, receiving_assets, giving_assets, pick_protections)
        return accepted

    def would_accept_trade_with_reason(self, receiving_team: 'Squadra', receiving_assets: list, giving_assets: list, pick_protections: Optional[Dict[str, str]] = None, waive_price: bool = False) -> Tuple[bool, str]:
        """
        Two questions for a CPU team (spec section 1.4): does the deal move it toward its plan (`plan_check`:
        a wish fulfilled, no hard no), and is the price right (strategic value and the blocking rules below).
        No overpay buys a yes on the plan question. The user's own team only answers the price question.
        Every OVR line is the era's (`era().ovr_at(old 2002 number)`), pick lines scale with `era().pick_scale`.
        `waive_price`: a team paying on purpose (a tax dump) skips only the value comparisons (main piece and
        threshold); the plan question and every blocking rule still apply.
        Returns (accepted: bool, reason: str).
        """
        era = self.era()
        ovr_at = era.ovr_at
        trade_cfg = CONFIG.TRADES
        is_user_team = self._is_user_team(receiving_team)
        untouchable_given = None   # the untouchable this CPU team gives without asking out (it raises the price)
        if not is_user_team:
            # ======== THE PLAN QUESTION ========
            plan_ok, plan_reason, _wish = self.plan_check(receiving_team, receiving_assets, giving_assets)
            if not plan_ok:
                return False, plan_reason

            # ======== SUPERSTAR PACKAGING RESTRICTION ========
            # A CPU team does not package a superstar WITH a first-round pick unless it receives a
            # high-caliber player back (stops stars + picks being used to trade up/down for other picks).
            superstar, high_caliber = ovr_at(88), ovr_at(80)
            giving_superstar = any(isinstance(a, Giocatore) and a.ovr >= superstar for a in giving_assets)
            giving_first_round_pick = any(isinstance(a, str) and "R1" in a for a in giving_assets)
            if giving_superstar and giving_first_round_pick:
                receiving_high_caliber_player = any(isinstance(a, Giocatore) and a.ovr >= high_caliber for a in receiving_assets)
                if not receiving_high_caliber_player:
                    return False, f"Superstar Packaging: Cannot package a superstar ({superstar}+ OVR) and a first-round pick unless receiving a high-caliber player ({high_caliber}+ OVR) in return"

            # ======== UNTOUCHABLE & ROOKIE CORNERSTONE PROTECTION ========
            # An untouchable who does not ask out moves only for an exceptional price (UNTOUCHABLE_PREMIUM, applied
            # once to the final threshold below) and only when the deal fulfils a wish (the plan question above).
            # A team paying on purpose (waive_price) never gives one. Promising young rookies (<= 23 years, high
            # potential) are refused for anything short of a superstar.
            for a in giving_assets:
                if isinstance(a, Giocatore):
                    if getattr(a, 'is_untouchable', False) and not getattr(a, '_wants_out', False):
                        untouchable_given = a
                    if a.eta <= 23 and a.potenziale >= ovr_at(80) and not getattr(a, '_wants_out', False):
                        best_rec_ovr = max([r.ovr for r in receiving_assets if isinstance(r, Giocatore)], default=0)
                        if best_rec_ovr < ovr_at(88):
                            return False, f"Rookie Cornerstone: The {receiving_team.nome} consider {a.nome} the future of the franchise and categorically refuse to give him up for non-superstar veterans."
            if untouchable_given is not None and waive_price:
                return False, self._untouchable_reason(receiving_team, untouchable_given)
            if not waive_price:
                pick_rule = self._pick_giving_refusal(receiving_assets, giving_assets)
                if pick_rule:
                    return False, pick_rule

        # ======== TOP-5 PICK PROTECTION ========
        # If this team is giving away a top-5 pick, they MUST receive a superstar (88+ on a 2002 scale)
        # OR another high-value pick (pick-for-pick swaps like trade-up/trade-down are fine).
        # This prevents teams from dumping lottery gold for nothing.
        giving_top5 = any(isinstance(a, str) and "R1" in a and self._is_top5_pick(a) for a in giving_assets)
        if giving_top5:
            best_receiving_ovr_check = max([a.ovr for a in receiving_assets if isinstance(a, Giocatore)], default=0)
            
            receiving_has_high_pick = False
            
            for a in receiving_assets:
                if isinstance(a, str) and "R1" in a:
                    if ":" in a:
                        try:
                            y, p = a.split(":", 1)
                            # Resolve protection for the receiving pick
                            prot = "Unprotected"
                            if pick_protections and (a in pick_protections or p in pick_protections):
                                prot = pick_protections.get(a, pick_protections.get(p, "Unprotected"))
                            elif self.torneo and hasattr(self.torneo, 'pick_protections'):
                                prot = self.torneo.pick_protections.get(int(y), {}).get(p, "Unprotected")
                            pv = self.get_pick_value(p, int(y), protection=prot)
                        except ValueError:
                            pv = self.get_pick_value(a, 1)
                    else:
                        # Resolve protection for the receiving pick (legacy key format)
                        prot = "Unprotected"
                        if pick_protections and a in pick_protections:
                            prot = pick_protections[a]
                        elif self.torneo and hasattr(self.torneo, 'pick_protections'):
                            for pick_year in range(1, 10):
                                if a in self.torneo.pick_ownership.get(pick_year, {}):
                                    prot = self.torneo.pick_protections.get(pick_year, {}).get(a, "Unprotected")
                                    break
                        pv = self.get_pick_value(a, 1, protection=prot)
                    if pv >= 65.0 * era.pick_scale: # Lowered from 80 to 65 to allow trade-downs with mid-lottery picks
                        receiving_has_high_pick = True
                        break
            
            if best_receiving_ovr_check < ovr_at(88) and not receiving_has_high_pick:
                return False, f"Top-5 Pick Protection: The {receiving_team.nome} cannot give up a top-5 pick without receiving a superstar ({ovr_at(88)}+ OVR) or a high-caliber pick in return."
            
        # ======== DRAFT PICK INTEGRITY RULE ========
        # An NBA team will NEVER give away a 1st-round pick (R1) exclusively for 2nd-round picks (R2).
        giving_r1 = any(isinstance(a, str) and "R1" in a for a in giving_assets)
        receiving_only_r2 = bool(receiving_assets) and all(isinstance(a, str) and "R2" in a for a in receiving_assets)
        if giving_r1 and receiving_only_r2:
            return False, "Draft Pick Integrity: Cannot trade a 1st-round pick exclusively for 2nd-round picks"

        rec_val = self.received_value(receiving_team, receiving_assets, pick_protections)
        _received_value = lambda p: self._received_player_value(receiving_team, p, pick_protections)

        give_val = sum(self.get_strategic_value(a, receiving_team, pick_protections) for a in giving_assets)
        
        # ======== MULTI-FIRST BONUS ========
        receiving_firsts = [a for a in receiving_assets if isinstance(a, str) and "R1" in a]
        if len(receiving_firsts) >= 2:
            raw_pick_value = 0
            for a in receiving_firsts:
                if ":" in a:
                    try:
                        y, p = a.split(":", 1)
                        raw_pick_value += self.get_pick_value(p, int(y), on_curve=True)
                    except ValueError: raw_pick_value += self.get_pick_value(a, 1, on_curve=True)
                else: raw_pick_value += self.get_pick_value(a, 1, on_curve=True)
            
            bonus = self._multi_first_bonus(len(receiving_firsts))
            bonus_value = raw_pick_value * (bonus - 1.0)
            rec_val += bonus_value
        
        if give_val <= 0: return True, "Free stuff"
        
        # QUALITY OVER QUANTITY RULE REVAMP
        # For the purpose of "Main Piece" rule, draft picks are evaluated collectively as a single asset bundle.
        giving_players_val = [self.get_strategic_value(a, receiving_team, pick_protections) for a in giving_assets if isinstance(a, Giocatore)]
        giving_picks_val = sum(self.get_strategic_value(a, receiving_team, pick_protections) for a in giving_assets if isinstance(a, str))
        best_giving_val = max(giving_players_val + [giving_picks_val], default=0)

        receiving_players_val = [_received_value(a) for a in receiving_assets if isinstance(a, Giocatore)]
        receiving_picks_val = sum(self.get_strategic_value(a, receiving_team, pick_protections) for a in receiving_assets if isinstance(a, str))
        best_receiving_val = max(receiving_players_val + [receiving_picks_val], default=0)

        # QUALITY RULE FOR OVRs
        best_giving_ovr = max([a.ovr for a in giving_assets if isinstance(a, Giocatore)], default=0)
        best_receiving_ovr = max([a.ovr for a in receiving_assets if isinstance(a, Giocatore)], default=0)

        # FRANCHISE PLAYER PROTECTION / TRADE DEMAND
        giving_stars = [a for a in giving_assets if isinstance(a, Giocatore) and a.ovr >= era.star]
        star_demanding_out = any(getattr(p, '_wants_out', False) for p in giving_stars)

        trade_diff = getattr(self.torneo, 'trade_difficulty', 'realistic') if self.torneo else 'realistic'

        # Threshold and Main Piece calculation
        strategy = self.get_team_strategy(receiving_team)
        
        # The "main piece" I receive must be worth a certain % of the main piece I give up
        # (CONFIG.TRADES.MAIN_PIECE: tiers by OVR above/below the era star line; unknown difficulty = 'hardcore')
        diff_key = trade_diff if trade_diff in trade_cfg.MAIN_PIECE else 'hardcore'
        if star_demanding_out or strategy == "REBUILDER":
            main_piece_threshold = trade_cfg.MAIN_PIECE_SELLER[diff_key]
        else:
            main_piece_threshold = _star_tier(trade_cfg.MAIN_PIECE[diff_key], best_giving_ovr, era.star)
            
        if not waive_price and best_giving_val > 0 and (best_receiving_val / best_giving_val) < main_piece_threshold:
            return False, f"Main Piece Rule: Best asset received ({best_receiving_val:.1f}) < {int(main_piece_threshold*100)}% of best asset given ({best_giving_val:.1f})"
        
        has_any_first = any(isinstance(a, str) and ("R1" in a) for a in receiving_assets)
        num_firsts = sum(1 for a in receiving_assets if isinstance(a, str) and "R1" in a)
        
        def _get_base_pick_val(a):
            if not isinstance(a, str) or "R1" not in a: return 0.0
            if ":" in a:
                try:
                    y, p = a.split(":", 1)
                    return self.get_pick_value(p, int(y))
                except ValueError: return self.get_pick_value(a, 1)
            return self.get_pick_value(a, 1)

        has_high_pick = any(_get_base_pick_val(a) >= 60.0 * era.pick_scale for a in receiving_assets)
        has_blue_chip = any(isinstance(a, Giocatore) and a.eta <= 24 and a.potenziale >= ovr_at(80) for a in receiving_assets)
        has_solid_starter = any(isinstance(a, Giocatore) and a.ovr >= ovr_at(76) for a in receiving_assets)

        # Quality Rule by Difficulty (OVR lines on the era's scale; the old 2002 numbers in ovr_at):
        if trade_diff == 'hardcore':
            if best_giving_ovr >= ovr_at(88):
                if best_receiving_ovr < ovr_at(78) and not (has_high_pick or has_any_first or (has_blue_chip and best_receiving_ovr >= ovr_at(75))):
                    return False, f"Quality Rule: Need {ovr_at(78)}+ player, 1st-round pick, or blue-chip prospect for a Superstar ({ovr_at(88)}+)"
            elif best_giving_ovr >= ovr_at(85):
                if best_receiving_ovr < ovr_at(76) and not (has_high_pick or has_any_first or (has_blue_chip and best_receiving_ovr >= ovr_at(74))):
                    return False, f"Quality Rule: Need {ovr_at(76)}+ player, 1st-round pick, or young talent for an All-Star ({ovr_at(85)}+)"
            elif best_giving_ovr >= ovr_at(80):
                if best_receiving_ovr < ovr_at(72) and not (has_any_first or num_firsts >= 1):
                    return False, f"Quality Rule: Need {ovr_at(72)}+ player or 1st-round pick for a quality veteran ({ovr_at(80)}+)"
        elif trade_diff == 'realistic':
            # Realistic is flexible: allow quality multi-player, blue-chip or pick packages
            if best_giving_ovr >= ovr_at(90):
                if best_receiving_ovr < ovr_at(75) and not (has_any_first or has_blue_chip or has_solid_starter):
                    return False, f"Quality Rule: Need a solid starter, young prospect, or 1st-round pick for a top superstar ({ovr_at(90)}+)"
            elif best_giving_ovr >= ovr_at(86):
                if best_receiving_ovr < ovr_at(72) and not (has_any_first or has_blue_chip or has_solid_starter):
                    return False, f"Quality Rule: Need a rotation player or pick for an All-Star ({ovr_at(86)}+)"
        # On 'easy': Quality rule is bypassed as long as total value and CBA math check out!

        # Threshold calculation: Strategy based
        if strategy == "CONTENDER": 
            threshold = 0.96
        elif strategy == "REBUILDER": 
            threshold = 1.05
        elif strategy == "PLAYOFF": 
            threshold = 1.00
        else: # MIDDLE 
            threshold = 1.02
             
        # POSITIONAL FIT & NEED PENALTY (Scales with difficulty)
        fit_penalty = 1.03 if trade_diff == 'easy' else (1.07 if trade_diff == 'realistic' else 1.12)
        for g in giving_assets:
            if isinstance(g, Giocatore) and g.ovr >= ovr_at(78):
                if receiving_team.ha_bisogno_di_ruolo(g.ruolo):
                    threshold *= fit_penalty
                    break 

        # KEY STARTER HOLE PENALTY
        giving_starters = [g for g in giving_assets if isinstance(g, Giocatore) and g.ovr >= ovr_at(79)]
        if giving_starters and strategy != "REBUILDER":
            top_giving_p = max(giving_starters, key=lambda x: x.ovr)
            pos_players = [p for p in receiving_team.roster if p.ruolo == top_giving_p.ruolo]
            is_pos_leader = (pos_players and max(pos_players, key=lambda x: x.ovr) == top_giving_p)
            has_pos_replacement = any(isinstance(r, Giocatore) and r.ruolo == top_giving_p.ruolo and r.ovr >= ovr_at(75) for r in receiving_assets)
            if is_pos_leader and not has_pos_replacement and not has_any_first:
                threshold *= fit_penalty
                    
        # STAR PREMIUM (CONFIG.TRADES.STAR_PREMIUM: tiers by OVR above the era star line)
        if best_giving_ovr >= era.star and not star_demanding_out and strategy != "REBUILDER":
            if best_receiving_ovr < best_giving_ovr - trade_cfg.STAR_PREMIUM_MATCH_GAP:
                threshold *= _star_tier(trade_cfg.STAR_PREMIUM[diff_key], best_giving_ovr, era.star)

        # Trade difficulty modifier from League Settings: (threshold multiplier, minimum allowed threshold)
        diff_mult, min_allowed = trade_cfg.DIFFICULTY.get(trade_diff, trade_cfg.DIFFICULTY['realistic'])
        threshold *= diff_mult

        # AI GM: trade skill sets the price (a strong GM asks more, a weak one accepts less), a strong GM
        # squeezes the user harder, and only a very weak one can misjudge a deal badly (still inside the rules).
        cpu_gm = self.get_gm(receiving_team)
        skill = cpu_gm.skills.get("trade") if cpu_gm is not None else None
        threshold *= trade_brain.skill_price_multiplier(skill)
        if trade_brain.has_trait(cpu_gm, "TRADE_HAPPY"):
            threshold *= CONFIG.FRONT_OFFICE.TRADE_HAPPY_THRESHOLD_MULT
        if skill is not None and self._comes_from_user(receiving_assets):
            threshold *= 1.0 + trade_brain.user_squeeze(skill)
        misjudgement = trade_brain.disaster_factor(skill, random)
        threshold *= misjudgement
        min_allowed *= misjudgement
        if untouchable_given is not None:   # once per deal, not once per untouchable
            threshold *= trade_cfg.UNTOUCHABLE_PREMIUM
            min_allowed *= trade_cfg.UNTOUCHABLE_PREMIUM

        # Natural GM valuation tolerance (+/- 2% organic variation) to avoid hard rigid rejection boundaries
        gm_flexibility = random.uniform(-0.02, 0.015)
        effective_threshold = max(min_allowed, threshold + gm_flexibility)
        
        accepted = waive_price or rec_val >= (give_val * effective_threshold)
        if not accepted and untouchable_given is not None:
            return False, self._untouchable_reason(receiving_team, untouchable_given)
        if not accepted:
            return False, f"Value mismatch: Offer {rec_val:.1f} < Required {give_val * effective_threshold:.1f} (Threshold: {effective_threshold:.2f})"

        # A CPU team that sells a star is not paid with role players, however the sum adds up: a first or a star-level
        # player has to come back (CONFIG.TRADES.STAR_SALE_MIN_OVR / STAR_RETURN_MIN_OVR). Not for a player who asked out.
        if not is_user_team:
            sold = [a for a in giving_assets if isinstance(a, Giocatore) and a.ovr >= ovr_at(trade_cfg.STAR_SALE_MIN_OVR)
                    and not getattr(a, '_wants_out', False)]
            return_line = ovr_at(trade_cfg.STAR_RETURN_MIN_OVR)
            if sold and not (any(isinstance(a, str) and "R1" in a for a in receiving_assets)
                             or any(isinstance(a, Giocatore) and a.ovr >= return_line for a in receiving_assets)):
                return False, (f"Star Sale Rule: the {receiving_team.nome} won't sell {sold[0].nome} for role players: "
                               f"a first-round pick or a {return_line}+ OVR player has to come back")

        return True, "Accepted"
        
    @staticmethod
    def _untouchable_reason(team: 'Squadra', player: 'Giocatore') -> str:
        return f"Untouchable Cornerstone: {player.nome} is the face of the {team.nome}: only an exceptional offer moves him."

    # ========================================================================
    # TRADE EXECUTION
    # ========================================================================
    
    def get_tradeable_players(self, team: 'Squadra', allow_stars: bool = False, include_untouchables: bool = False) -> List['Giocatore']:
        """
        Returns players that can be traded. Protects:
        - Untouchables (explicit flag) - unless they ask out, or `include_untouchables` is True (an engine that
          pursues stars: acceptance then asks an exceptional price, CONFIG.TRADES.UNTOUCHABLE_PREMIUM)
        - Stars (the league's star line) - unless they demand a trade (or allow_stars is True)
        - Young Prospects (under 24 with high potential)
        OVR/potential lines are the era's (`era().ovr_at(old 2002 number)`).
        """
        tradeable = []
        trade_diff = getattr(self.torneo, 'trade_difficulty', 'realistic') if self.torneo else 'realistic'
        lines = self.league_lines()
        star_line, core_line = lines["star"], lines["core"]
        ovr_at = self.era().ovr_at
        demand_ctx = self.wish_context(team)

        # Calculate win rate for the core-starter protection
        win_rate = 0.5
        if self.torneo and (team.vittorie + team.sconfitte) > 20:
            win_rate = team.vittorie / (team.vittorie + team.sconfitte)

        for p in team.roster:
            # SUPERSTAR TRADE DEMAND: an unhappy star asks out (core/front_office/wishes.py `wants_out`,
            # the one source of truth, also behind the STAR_WANTS_OUT wish).
            wants_out = wants_out_of(p, team, demand_ctx) or bool(getattr(p, 'walks_away', ''))   # he will not re-sign

            # The flag mirrors the CURRENT situation: a star whose morale recovered (or whose
            # team improved) no longer demands a trade. Set it before any 'continue' below.
            p._wants_out = wants_out

            # Skip explicitly untouchable, unless he asks out (designa_intoccabili and acceptance exempt him too)
            if getattr(p, 'is_untouchable', False) and not (wants_out or include_untouchables):
                continue

            # Skip if on trade cooldown (cannot be traded immediately)
            if getattr(p, 'giorni_cooldown_scambio', 0) > 0:
                continue

            # REBUILDER TIMELINE PROTECTION
            is_rebuilder = self.get_team_strategy(team) == "REBUILDER"
            if is_rebuilder:
                # Rebuilders NEVER trade young talent and building blocks
                if (p.eta <= 23 and (p.potenziale >= ovr_at(78) or p.ovr >= ovr_at(72))) or p.eta <= 21:
                    if not (wants_out or allow_stars):
                        continue
                if p.eta <= 24 and p.potenziale >= ovr_at(82):
                    if not (wants_out or allow_stars):
                        continue
                # Rebuilders actively trade older players (27+) for draft picks/assets
                if p.eta >= 27:
                    if p.ovr >= star_line and not (wants_out or allow_stars or p.eta >= 31):
                        continue
                    tradeable.append(p)
                    continue

            # Protect stars (the league's top share) unless they demand a trade or allow_stars is True
            if p.ovr >= star_line and not wants_out and not allow_stars:
                continue
            
            # CORE STARTER PROTECTION (between the league's core and star lines; 80-84 on a 2002 start)
            if core_line <= p.ovr < star_line and not wants_out and not allow_stars:
                if trade_diff == 'hardcore':
                    if win_rate >= 0.50 and not is_rebuilder:
                        continue
                elif trade_diff == 'realistic':
                    if win_rate >= 0.68 and not is_rebuilder:
                        continue
                # On 'easy', 80-84 players are available for trading!
                
            # Protect young prospects
            if p.eta <= 23 and p.potenziale >= ovr_at(80):
                if trade_diff == 'hardcore':
                    if not (p.ovr >= star_line and allow_stars):
                        continue
                elif trade_diff == 'realistic':
                    if p.potenziale >= ovr_at(87) and not (p.ovr >= star_line and allow_stars):
                        continue
                # On 'easy', prospects are available for trade discussions!
                
            # Record want out status so we can format it in logs
            if wants_out:
                p._wants_out = True 
                
            tradeable.append(p)
        return tradeable

    def _record_front_office_trade(self, sides: List[Dict]):
        """The CPU teams' move logs (AI GM). The trade is already done: a failure here is logged, never undone."""
        try:
            from core.front_office.moves import record_trade
            record_trade(self.torneo, sides)
        except Exception as ex:
            main_log.error(f"Front office move log failed for a trade: {ex}", exc_info=True)

    def _clear_trade_caches(self, team_names: Optional[Iterable[str]] = None) -> None:
        """Drops what a trade makes stale (positional needs, wishes and their context): the given teams' entries,
        or everything when no team is named. The era lines stay until the next `begin_window`."""
        caches = [c for c in (getattr(self, name, None) for name in ('_needs_cache', '_wishes', '_wish_contexts')) if c]
        for cache in caches:
            if team_names is None:
                cache.clear()
            else:
                for name in team_names:
                    cache.pop(name, None)

    def execute_deal(self, deal: Deal, motive: Optional[TradeMotive] = None,
                     pick_protections: Optional[Dict[str, str]] = None) -> bool:
        """The one door every trade goes through (trades/execution.py)."""
        return execution.execute_deal(self, deal, motive, pick_protections)

    def execute_trade(self, team_a: 'Squadra', team_b: 'Squadra', assets_a_gives: List[Any], assets_b_gives: List[Any],
                      reason: str = "Strategic Fit", pick_protections: Optional[Dict[str, str]] = None,
                      motive: Optional[TradeMotive] = None) -> bool:
        moves = ([(team_a.nome, team_b.nome, a) for a in assets_a_gives]
                 + [(team_b.nome, team_a.nome, a) for a in assets_b_gives])
        return self.execute_deal(Deal([team_a, team_b], moves, reason=reason), motive=motive,
                                 pick_protections=pick_protections)

    def _record_trade_analytics_snapshot(self, trade_type: str, teams_data: List[Dict], reason: str = "",
                                         motive: Optional[TradeMotive] = None):
        """
        Records a structured snapshot of the trade and pre-trade team performance
        into torneo.trade_analytics_history for the Trade Delta Analytics Engine, in every phase.
        `trade_type` is the old label ("2-Team", ...) kept in "type"; the motive fills "trade_type", "why" and
        "motives" (without one: "user" when the user's team is in the deal, else "legacy").
        """
        import time

        fase = getattr(self.torneo, 'fase_torneo', 'SEASON') if self.torneo else 'SEASON'

        season_num = getattr(self.torneo, 'season_number', 1)
        game_day = getattr(self.torneo, 'giorno_corrente', 1)
        
        structured_teams = []
        for t_entry in teams_data:
            team = t_entry['team']
            gives = t_entry.get('gives', [])
            receives = t_entry.get('receives', [])
            
            w = team.vittorie
            losses = team.sconfitte
            gp = w + losses
            win_pct = round(w / gp, 3) if gp > 0 else 0.5
            
            stats = getattr(team, 'statistiche_squadra', None)
            ppg = round(stats.punti_fatti / gp, 1) if stats and gp > 0 else (round(stats.punti_fatti, 1) if stats else 100.0)
            opp_ppg = round(stats.punti_subiti / gp, 1) if stats and gp > 0 else (round(stats.punti_subiti, 1) if stats else 100.0)
            
            off_rtg = round(getattr(team, 'offensive_rating', 105.0), 1)
            def_rtg = round(getattr(team, 'defensive_rating', 105.0), 1)
            net_rtg = round(off_rtg - def_rtg, 1)
            
            players_out = []
            picks_out = []
            for a in gives:
                if isinstance(a, Giocatore):
                    players_out.append({
                        "name": a.nome,
                        "ovr": a.ovr,
                        "ruolo": a.ruolo,
                        "eta": a.eta,
                        "salary": a.contract.salario_annuale if a.contract else 0.0,
                        "trade_value": round(float(a.trade_value), 1) if hasattr(a, 'trade_value') else a.ovr
                    })
                elif isinstance(a, str):
                    picks_out.append(a)
                    
            players_in = []
            picks_in = []
            for a in receives:
                if isinstance(a, Giocatore):
                    players_in.append({
                        "name": a.nome,
                        "ovr": a.ovr,
                        "ruolo": a.ruolo,
                        "eta": a.eta,
                        "salary": a.contract.salario_annuale if a.contract else 0.0,
                        "trade_value": round(float(a.trade_value), 1) if hasattr(a, 'trade_value') else a.ovr
                    })
                elif isinstance(a, str):
                    picks_in.append(a)

            structured_teams.append({
                "team_name": team.nome,
                "wins_pre": w,
                "losses_pre": losses,
                "win_pct_pre": win_pct,
                "ppg_pre": ppg,
                "opp_ppg_pre": opp_ppg,
                "off_rtg_pre": off_rtg,
                "def_rtg_pre": def_rtg,
                "net_rtg_pre": net_rtg,
                "players_sent": players_out,
                "picks_sent": picks_out,
                "players_received": players_in,
                "picks_received": picks_in
            })
            
        history = getattr(self.torneo, 'trade_analytics_history', None)
        if history is None:  # a new career has no list until its first save/load
            history = self.torneo.trade_analytics_history = []
        if motive is not None:
            new_type, why, motives = motive.trade_type, motive.why, [s.to_dict(public=False) for s in motive.sides]
        else:
            user = user_team_name(self.torneo)
            new_type = "user" if user and any(e['team'].nome == user for e in teams_data) else "legacy"
            why, motives = "", []
        record = {
            "id": f"trade_{int(time.time()*1000)}_{len(history)+1}",
            "season": season_num,
            "game_day": game_day,
            "type": trade_type,
            "reason": reason,
            "teams": structured_teams,
            "date_recorded": time.strftime("%Y-%m-%d %H:%M:%S"),
            "trade_type": new_type,
            "why": why,
            "phase": fase,
            "team_count": len(structured_teams),
            "motives": motives,
        }
        history.append(record)

    def _log_trade_to_file(self, msg: str):
        try:
            import os
            root_log = _root_trade_log_path()
            
            season_num = getattr(self.torneo, 'season_number', 1) if self.torneo else 1
            fase = getattr(self.torneo, 'fase_torneo', 'SEASON') if self.torneo else 'SEASON'
            entry = f"[Season {season_num} | {fase}] {msg}\n"

            # 1. ALWAYS write directly to root trades_history.txt
            with open(root_log, "a", encoding="utf-8") as f:
                f.write(entry)
                f.flush()

            # 2. Also write to the active save's log (its session copy, committed by the next save)
            save_log = None
            if get_active_save_name():
                save_log = get_historical_file_path("trades_history.txt")
            elif getattr(self.torneo, 'active_save_name', None):
                save_dir = get_save_path(self.torneo.active_save_name)
                if os.path.exists(save_dir):
                    save_log = os.path.join(save_dir, "trades_history.txt")
            if save_log:
                with open(save_log, "a", encoding="utf-8") as f:
                    f.write(entry)
                    f.flush()
        except Exception as e:
            main_log.error(f"Failed to log trade to file: {e}")

    def execute_3_team_trade(self, team_a: 'Squadra', team_b: 'Squadra', team_c: 'Squadra',
                             trade_data: dict, pick_protections: dict = None,
                             reason: str = "3-Team Blockbuster Trade", motive: Optional[TradeMotive] = None) -> bool:
        """
        Executes a triangular 3-team trade atomically.
        trade_data format (a player may be given by name):
        {
            "team_a": {"gives_to_b": [...], "gives_to_c": [...]},
            "team_b": {"gives_to_a": [...], "gives_to_c": [...]},
            "team_c": {"gives_to_a": [...], "gives_to_b": [...]},
        }
        """
        deal = self.three_team_deal(team_a, team_b, team_c, trade_data, reason=reason)
        return self.execute_deal(deal, motive=motive, pick_protections=pick_protections)

    def execute_4_team_trade(self, team_a: 'Squadra', team_b: 'Squadra', team_c: 'Squadra', team_d: 'Squadra',
                             flow: List[Dict], reason: str = "4-Team Mega-Blockbuster",
                             motive: Optional[TradeMotive] = None) -> bool:
        """
        Executes a 4-team trade atomically.
        flow is a list of steps (team names in any case; players as Giocatore or name):
        [
            {"from": team_a.nome, "to": team_b.nome, "players": [p_a], "picks": [pk_a]},
            {"from": team_b.nome, "to": team_c.nome, "players": [p_b], "picks": [pk_b]},
            {"from": team_c.nome, "to": team_d.nome, "players": [p_c], "picks": [pk_c]},
            {"from": team_d.nome, "to": team_a.nome, "players": [p_d], "picks": [pk_d]},
        ]
        """
        deal = self.four_team_deal([team_a, team_b, team_c, team_d], flow, reason=reason)
        return bool(deal) and self.execute_deal(deal, motive=motive)

    # ========================================================================
    # AUCTION BIDS (trades/engines/auction.py) AND ENGINE HELPERS
    # ========================================================================
    
    def _build_bid_for_player(self, partner: 'Squadra', seller: 'Squadra', player: 'Giocatore') -> Optional[Dict]:
        """
        Builds a bid package from a partner team for any target player of the seller.
        Returns a bid dict {partner, assets, value_to_seller, pick_count} or None.
        """
        from core.config import CONFIG
        
        player_salary = player.contract.salario_annuale if player.contract else 5.0
        player_value = self.get_strategic_value(player, seller)
        
        # Roster Congestion Prevention: Do not bid if it causes/worsens congestion (>= 3 players with OVR >= 78)
        if player.ovr >= 78:
            is_user_team = self.squadra_giocatore and partner.nome == self.squadra_giocatore.nome
            if not is_user_team:
                current_count = sum(1 for p in partner.roster if p.ruolo == player.ruolo and p.ovr >= 78)
                if 2 <= current_count < 5:
                    return None
                    
        partner_tradeables = self.get_tradeable_players(partner)
        
        # Identify low-OVR fillers (salary-first). Protect young developing prospects from being used as garbage fillers!
        filler_limit = player.ovr - 5 if player.ovr >= 80 else player.ovr - 2
        fillers = sorted(
            [p for p in partner_tradeables if p.ovr < filler_limit and p.contract 
             and not (p.eta <= 24 and p.potenziale >= 75)], 
            key=lambda x: (-x.contract.salario_annuale, x.ovr)
        )
        
        package_filler = []
        salary_filler = 0
        math_works = False
        
        # 1. Test 0-filler if both teams are financially compatible directly (e.g. Cap Space absorption)
        valid_a_0, _ = seller.check_trade_salary_match(0.0, player_salary)
        valid_b_0, _ = partner.check_trade_salary_match(player_salary, 0.0)
        if valid_a_0 and valid_b_0:
            math_works = True
            package_filler = []
            salary_filler = 0.0
        else:
            # 2. Test single filler swaps
            for f in fillers:
                valid_a, _ = seller.check_trade_salary_match(f.contract.salario_annuale, player_salary)
                valid_b, _ = partner.check_trade_salary_match(player_salary, f.contract.salario_annuale)
                if valid_a and valid_b:
                    package_filler = [f]
                    salary_filler = f.contract.salario_annuale
                    math_works = True
                    break
            
            # 3. Test multi-filler combinations if single filler was not enough
            if not math_works and len(fillers) >= 2:
                for i in range(len(fillers)):
                    temp_f = [fillers[i]]
                    temp_sal = fillers[i].contract.salario_annuale
                    for j in range(i + 1, len(fillers)):
                        temp_f.append(fillers[j])
                        temp_sal += fillers[j].contract.salario_annuale
                        valid_a, _ = seller.check_trade_salary_match(temp_sal, player_salary)
                        valid_b, _ = partner.check_trade_salary_match(player_salary, temp_sal)
                        if valid_a and valid_b:
                            package_filler = temp_f
                            salary_filler = temp_sal
                            math_works = True
                            break
                        if len(temp_f) >= 3:
                            break
                    if math_works:
                        break
        
        if not math_works: 
            return None
        
        # Calculate current package value
        package_value = self.received_value(seller, package_filler)   # counted as the seller's price question does
        assets = package_filler.copy()
        
        # Collect potential compensation assets (picks and young prospects)
        prospects = [
            p for p in partner_tradeables 
            if p.eta <= 24 and p.potenziale >= 80 and p.ovr < (player.ovr - 3) and p not in package_filler and p.contract
        ]
        prospects = sorted(prospects, key=lambda x: self.get_strategic_value(x, seller), reverse=True)
        
        partner_picks = self._collect_team_picks(partner)
        
        # Tiered player classification:
        # Franchise superstars: 88+
        # All-Stars: 85+
        # High-caliber starters: 82+
        # Solid starters: 78-81
        # Role players / Aging bench vets: <= 77
        is_franchise = player.ovr >= 88
        is_mega_star = player.ovr >= 85
        is_star = player.ovr >= 82
        is_role_player = player.ovr < 78
        
        firsts_added = 0
        prospects_added = 0
        pick_count = 0
        
        target_multiplier = 1.20 if is_franchise else (1.15 if is_mega_star else (1.10 if is_star else 1.05))
        
        # Combine prospects and picks
        compensation_options = []
        for p in prospects:
            compensation_options.append(('PROSPECT', p))
        for py, pk in partner_picks:
            if pk.startswith("R1"):   # seconds are worth next to nothing and never sweeten a player package
                compensation_options.append(('PICK', (py, pk)))

        def sort_comp_key(opt):
            if opt[0] == 'PICK':
                py, pk = opt[1]
                val = self.get_pick_value(pk, py)
                if pk.startswith("R1"):
                    return (1 if is_role_player else 3, val)
                return (2 if is_role_player else 1, val)
            else:
                val = self.get_strategic_value(opt[1], seller)
                return (2, val)
                
        compensation_options.sort(key=sort_comp_key, reverse=True)
        
        for opt_type, opt_val in compensation_options:
            if len(assets) >= 4:
                break
                
            if package_value >= player_value * target_multiplier:
                if is_mega_star and firsts_added + prospects_added < 1:
                    pass
                elif is_franchise and firsts_added + prospects_added < 2:
                    pass
                elif is_star and firsts_added + prospects_added + pick_count < 1 and any(f.ovr < player.ovr - 3 for f in package_filler if hasattr(f, 'ovr')):
                    pass
                else:
                    break
            
            if opt_type == 'PROSPECT':
                prospect = opt_val
                new_salary_filler = salary_filler + prospect.contract.salario_annuale
                valid_a, _ = seller.check_trade_salary_match(new_salary_filler, player_salary)
                valid_b, _ = partner.check_trade_salary_match(player_salary, new_salary_filler)
                if valid_a and valid_b and (len(seller.roster) + len(assets) - len(package_filler) + 1 <= CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2):
                    assets.append(prospect)
                    salary_filler = new_salary_filler
                    package_value = self.received_value(seller, assets)
                    prospects_added += 1
                    
            elif opt_type == 'PICK':
                py, pk = opt_val
                pick_asset = f"{py}:{pk}"
                
                # STRICT NBA RULE: Role players (under 78 OVR) can NEVER command 1st round picks in auctions
                if pk.startswith("R1") and is_role_player:
                    continue
                
                # Starters (78-81) can receive at most ONE 1st round pick
                if pk.startswith("R1") and not is_star and firsts_added >= 1:
                    continue

                if pk.startswith("R1"):
                    valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, partner.nome, [a for a in assets if isinstance(a, str)] + [pick_asset])
                    if not valid_s:
                        continue
                        
                if pk.startswith("R1") and self._is_top5_pick(pick_asset) and player.ovr < 88:
                    continue
                    
                current_picks_count = sum(1 for a in assets if isinstance(a, str))
                if current_picks_count >= 3:
                    continue
                if not pk.startswith("R1") and sum(1 for a in assets if isinstance(a, str) and "R2" in a) >= 2:
                    continue
                        
                assets.append(pick_asset)
                pick_count += 1
                package_value = self.received_value(seller, assets)
                if pk.startswith("R1"):
                    firsts_added += 1

        # Enforce strict minimum quality for Stars (85+) and Superstars (88+)
        if is_mega_star or is_franchise:
            has_first = any(isinstance(a, str) and "R1" in a for a in assets)
            has_quality_player = any(
                hasattr(a, 'ovr') and (a.ovr >= 78 or (a.eta <= 24 and getattr(a, 'potenziale', 0) >= 82))
                for a in assets
            )
            # Mega star (85-87): Must have at least 1 First-Round Pick OR a quality young player (78+ OVR / high POT)
            if not (has_first or has_quality_player):
                return None
            # Franchise Superstar (88+): Must have at least 1 First-Round Pick AND a quality prospect, OR 2+ First-Round Picks
            if is_franchise:
                num_firsts = sum(1 for a in assets if isinstance(a, str) and "R1" in a)
                if num_firsts < 2 and not (num_firsts >= 1 and has_quality_player):
                    return None

        if package_value < player_value * 0.80:
            return None
            
        return {
            'partner': partner,
            'assets': assets,
            'value_to_seller': package_value,
            'pick_count': pick_count
        }

    def _try_request_extra_asset(self, partner: 'Squadra', current_assets: List[Any], seller: 'Squadra', player: 'Giocatore') -> Tuple[List[Any], float]:
        """
        Tries to request an extra minor asset from the partner team to sweeten the deal.
        Returns a tuple (updated_assets_list, new_package_value).
        """
        from core.models import Giocatore
        from core.config import CONFIG
        
        player_salary = player.contract.salario_annuale if player.contract else 5.0
        
        def validate_updated_package(new_assets):
            new_players = [a for a in new_assets if isinstance(a, Giocatore)]
            new_salary_filler = sum(p.contract.salario_annuale for p in new_players)
            
            valid_a, _ = seller.check_trade_salary_match(new_salary_filler, player_salary)
            valid_b, _ = partner.check_trade_salary_match(player_salary, new_salary_filler)
            if not (valid_a and valid_b):
                return False
                
            net_change_seller = len(new_players) - 1
            if len(seller.roster) + net_change_seller > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2:
                return False
                
            net_change_partner = 1 - len(new_players)
            if len(partner.roster) + net_change_partner > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2:
                return False
                
            return True
            
        partner_picks = self._collect_team_picks(partner)
        partner_tradeables = self.get_tradeable_players(partner)
        
        # Option A: Add an R2 pick if not already offered
        r2_picks_owned = [(py, pk) for py, pk in partner_picks if pk.startswith("R2")]
        for py, pk in r2_picks_owned:
            pick_asset = f"{py}:{pk}"
            if pick_asset not in current_assets:
                test_assets = current_assets + [pick_asset]
                if sum(1 for a in test_assets if isinstance(a, str)) <= 3:
                    if validate_updated_package(test_assets):
                        new_val = sum(self.get_strategic_value(a, seller) for a in test_assets)
                        if self.would_accept_trade(partner, [player], test_assets):
                            return test_assets, new_val
                            
        # Option B: Add a minor prospect (OVR <= 73, Potential >= 78) if not already offered
        prospects = [
            p for p in partner_tradeables 
            if p.eta <= 24 and p.ovr <= 73 and p.potenziale >= 78 and p not in current_assets and p.contract
        ]
        prospects = sorted(prospects, key=lambda x: self.get_strategic_value(x, seller), reverse=True)
        for prospect in prospects:
            test_assets = current_assets + [prospect]
            if len([a for a in test_assets if isinstance(a, Giocatore)]) <= 3:
                if validate_updated_package(test_assets):
                    new_val = sum(self.get_strategic_value(a, seller) for a in test_assets)
                    if self.would_accept_trade(partner, [player], test_assets):
                        return test_assets, new_val
                        
        # Option C: Upgrade an R2 pick to an R1 pick — ONLY for true starters and stars (78+ OVR)
        r2_in_assets = [a for a in current_assets if isinstance(a, str) and "R2" in a]
        if r2_in_assets and player.ovr >= 78:
            r1_picks_owned = [f"{py}:{pk}" for py, pk in partner_picks if pk.startswith("R1")]
            r1_available = [p for p in r1_picks_owned if p not in current_assets]
            
            if r1_available:
                r2_to_replace = r2_in_assets[0]
                r1_available_sorted = sorted(r1_available, key=lambda x: self.get_strategic_value(x, seller))
                
                for r1_pick in r1_available_sorted:
                    r1_picks_traded = [a for a in current_assets if isinstance(a, str) and "R1" in a and a != r2_to_replace] + [r1_pick]
                    valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, partner.nome, r1_picks_traded)
                    if not valid_s:
                        continue
                        
                    if self._is_top5_pick(r1_pick) and player.ovr < 88:
                        continue
                        
                    test_assets = [a for a in current_assets if a != r2_to_replace] + [r1_pick]
                    if validate_updated_package(test_assets):
                        new_val = sum(self.get_strategic_value(a, seller) for a in test_assets)
                        if self.would_accept_trade(partner, [player], test_assets):
                            return test_assets, new_val
                            
        original_val = sum(self.get_strategic_value(a, seller) for a in current_assets)
        return current_assets, original_val

    def _get_pick_position(self, pick_key: str) -> int:
        """Returns the projected draft position for a pick based on lottery order. 0 = unknown."""
        if not hasattr(self.torneo, 'draft_lottery_order') or not self.torneo.draft_lottery_order:
            return 0
        parts = pick_key.split("-")
        if len(parts) > 1:
            original_team = parts[1]
            if original_team in self.torneo.draft_lottery_order:
                return self.torneo.draft_lottery_order.index(original_team) + 1
        return 0

    def _bench(self, team: 'Squadra') -> List['Giocatore']:
        """Tradeable players outside the team's top BENCH_SHUFFLE_TOP_KEEP by OVR, lowest first."""
        keep = sorted(team.roster, key=lambda p: p.ovr, reverse=True)[:CONFIG.FRONT_OFFICE.BENCH_SHUFFLE_TOP_KEEP]
        bench = [p for p in self.get_tradeable_players(team) if not any(p is k for k in keep)]
        return sorted(bench, key=lambda p: p.ovr)

    def find_trades_for_package(self, giving_players: List['Giocatore'], giving_picks: List[str], user_pick_protections: dict = None) -> List[Dict]:
        """
        Find all possible trades for a customized user package (1-3 players + 0-3 picks).
        Returns up to 25 balanced CPU trade offers.
        """
        from trades.trade_validator import TradeValidator
        import itertools

        if not self.squadra_giocatore:
            return []
            
        team = self.squadra_giocatore
        total_giving_salary = sum(p.contract.salario_annuale for p in giving_players if p.contract)
        total_giving_val = sum(self.get_strategic_value(p, team) for p in giving_players) + \
                           sum(self.get_strategic_value(pk, team) for pk in giving_picks)
        
        possible_trades = []
        filler_pay = self.era().money(8.0)

        def serialize_players(players_list):
            return [{
                "name": p.nome,
                "team": p.squadra.nome if p.squadra else "",
                "position": p.ruolo,
                "ovr": p.ovr,
                "potential": p.potenziale,
                "salary": p.contract.salario_annuale if p.contract else getattr(p, 'salario', 0),
                "contract_years": p.contract.anni_rimanenti if p.contract else getattr(p, 'contract_years', 1),
                "trade_value": round(float(p.trade_value), 1)
            } for p in players_list]

        for partner in self.squadre:
            if partner == team or partner.nome == team.nome:
                continue
                
            if not self.wishes_for(partner):
                continue   # a team with nothing on its wish list has no use for any package
            partner_tradeables = self.get_tradeable_players(partner, allow_stars=(total_giving_val >= 90))
            if not partner_tradeables:
                continue

            partner_picks = self._collect_team_picks(partner)
            partner_fillers = [p for p in partner_tradeables if p.contract and p.contract.salario_annuale < filler_pay]
            partner_fillers.sort(key=lambda x: x.contract.salario_annuale)
            
            # Iterate through target players on partner team
            for target in partner_tradeables:
                if not target.contract:
                    continue
                    
                t_sal = target.contract.salario_annuale
                r_combos = [[target]]
                
                # Only test adding fillers if target alone does not match salary, or 1 small filler
                valid_team_0, _ = team.check_trade_salary_match(t_sal, total_giving_salary)
                valid_partner_0, _ = partner.check_trade_salary_match(total_giving_salary, t_sal)
                
                if not (valid_team_0 and valid_partner_0):
                    for f in partner_fillers[:4]:
                        if f != target:
                            r_combos.append([target, f])
                    if len(partner_fillers) >= 2:
                        for f1, f2 in itertools.combinations(partner_fillers[:3], 2):
                            if f1 != target and f2 != target:
                                r_combos.append([target, f1, f2])
                else:
                    for f in partner_fillers[:2]:
                        if f != target:
                            r_combos.append([target, f])
                    
                for return_players in r_combos:
                    salary_r = sum(p.contract.salario_annuale for p in return_players)
                    salary_g = total_giving_salary
                    
                    # Check CBA salary match
                    valid_team, _ = team.check_trade_salary_match(salary_r, salary_g)
                    if not valid_team:
                        continue
                    valid_partner, _ = partner.check_trade_salary_match(salary_g, salary_r)
                    if not valid_partner:
                        continue
                        
                    # Roster limits
                    net_team = len(return_players) - len(giving_players)
                    net_partner = len(giving_players) - len(return_players)
                    if len(team.roster) + net_team < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE or len(team.roster) + net_team > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
                        continue
                    if len(partner.roster) + net_partner < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE or len(partner.roster) + net_partner > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
                        continue
                        
                    # Check acceptance & balance with picks if needed
                    return_picks = []
                    cand_giving_assets = giving_players + giving_picks
                    cand_receiving_assets = return_players + return_picks
                    
                    accepts, reason = self.would_accept_trade_with_reason(
                        partner, cand_giving_assets, cand_receiving_assets, pick_protections=user_pick_protections
                    )
                    
                    # If user is giving more value than receiving, partner adds picks
                    if accepts:
                        val_user_gives = sum(self.get_strategic_value(p, partner) for p in cand_giving_assets)
                        val_partner_gives = sum(self.get_strategic_value(p, partner) for p in return_players)
                        
                        if val_user_gives > val_partner_gives * 1.15:
                            for py, pk in partner_picks:
                                if len(return_picks) >= 2:
                                    break
                                pk_asset = f"{py}:{pk}"
                                if "R1" in pk:
                                    valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, partner.nome, [pk_asset])
                                    if not valid_s:
                                        continue
                                still_accepts, _ = self.would_accept_trade_with_reason(
                                    partner, cand_giving_assets, return_players + return_picks + [pk_asset],
                                    pick_protections=user_pick_protections)
                                if not still_accepts:
                                    break
                                return_picks.append(pk_asset)

                        val_rec = sum(self.get_strategic_value(p, team) for p in return_players) + \
                                  sum(self.get_strategic_value(pk, team) for pk in return_picks)
                        val_give = sum(self.get_strategic_value(p, team) for p in giving_players) + \
                                   sum(self.get_strategic_value(pk, team) for pk in giving_picks)
                        val_diff = val_rec - val_give
                        
                        possible_trades.append({
                            "partner_team": partner.nome,
                            "partner_strategy": self.get_team_strategy(partner),
                            "giving_players": serialize_players(giving_players),
                            "giving_picks": giving_picks,
                            "receiving_players": serialize_players(return_players),
                            "receiving_picks": return_picks,
                            "value_differential": round(val_diff, 1),
                            "is_fair": True,
                            "likelihood": "High",
                            "why": self.user_motive(self.pair_deal(
                                team, partner, cand_giving_assets, return_players + return_picks)).why
})
                        break # Found valid deal for this target, move to next target

                if len(possible_trades) >= 30:
                    break
            if len(possible_trades) >= 30:
                break

        # Sort by best fit / highest target OVR
        possible_trades.sort(key=lambda x: (max([p["ovr"] for p in x["receiving_players"]], default=0), x["value_differential"]), reverse=True)
        return possible_trades[:25]

    def find_trades_for_player(self, player: 'Giocatore') -> List[Dict]:
        """
        Find all possible trades for a specific player.
        Returns list of dicts with trade possibilities for the Trade Finder UI.
        """
        from trades.trade_validator import TradeValidator
        import itertools
        
        if not player or not player.squadra:
            return []
        
        team = player.squadra
        era = self.era()
        star_line, filler_pay = era.ovr_at(85), era.money(8.0)
        player_salary = player.contract.salario_annuale if player.contract else 5.0

        # Other tradeable players on player's team (to be used as cheap fillers if needed)
        team_others = [p for p in self.get_tradeable_players(team) if p != player and p.contract]
        # Sort fillers by salary ascending (cheapest first)
        team_others.sort(key=lambda x: x.contract.salario_annuale)
        # Limit to cheap fillers (< $8M) to be realistic
        team_fillers = [p for p in team_others if p.contract.salario_annuale < filler_pay]
        
        possible_trades = []
        
        # Deduplicated team picks (we sort them by get_pick_value)
        team_picks = self._collect_team_picks(team)
        
        for partner in self.squadre:
            if len(possible_trades) >= 30:
                break
            if partner == team:
                continue
            if self.squadra_giocatore and (partner == self.squadra_giocatore or partner.nome == self.squadra_giocatore.nome):
                continue
                
            if not self.wishes_for(partner):
                continue   # a team with nothing on its wish list has no use for any package
            partner_tradeables = self.get_tradeable_players(partner, allow_stars=(player.ovr >= star_line))
            if not partner_tradeables:
                continue
                
            partner_picks = self._collect_team_picks(partner)
            
            # Filter partner others (fillers)
            partner_others = [p for p in partner_tradeables if p.contract]
            partner_others.sort(key=lambda x: x.contract.salario_annuale)
            partner_fillers = [p for p in partner_others if p.contract.salario_annuale < filler_pay]
            
            # Iterate through all tradeable players on partner team as target stars
            for target in partner_tradeables:
                if len(possible_trades) >= 30:
                    break
                if not target.contract:
                    continue
                    
                target_salary = target.contract.salario_annuale
                
                # Check 1-on-1 swap or filler combinations
                # We want to find a valid player package:
                # - giving: [player] + up to 1 team filler
                # - receiving: [target] + up to 2 partner fillers
                
                found_package = False
                giving_players = []
                receiving_players = []
                
                # 1. First test 1-on-1 direct swap (most common & fastest)
                salary_g = player_salary
                salary_r = target_salary
                valid_team, _ = team.check_trade_salary_match(salary_r, salary_g)
                valid_partner, _ = partner.check_trade_salary_match(salary_g, salary_r)
                if valid_team and valid_partner:
                    giving_players = [player]
                    receiving_players = [target]
                    found_package = True
                else:
                    # 2. Need fillers: Stage combinations intelligently
                    avail_p_fillers = [f for f in partner_fillers if f != target][:4]
                    avail_t_fillers = team_fillers[:3]
                    
                    combos_to_try = []
                    # Try single filler first
                    for pf in avail_p_fillers:
                        combos_to_try.append(([], [pf]))
                    for tf in avail_t_fillers:
                        combos_to_try.append(([tf], []))
                    # Try 1 team filler + 1 partner filler
                    for tf in avail_t_fillers:
                        for pf in avail_p_fillers:
                            combos_to_try.append(([tf], [pf]))
                    # Try 2 partner fillers
                    for pf1, pf2 in itertools.combinations(avail_p_fillers[:3], 2):
                        combos_to_try.append(([], [pf1, pf2]))
                        
                    for g_f, r_f in combos_to_try:
                        gp = [player] + g_f
                        rp = [target] + r_f
                        
                        s_g = sum(p.contract.salario_annuale for p in gp)
                        s_r = sum(p.contract.salario_annuale for p in rp)
                        
                        valid_t, _ = team.check_trade_salary_match(s_r, s_g)
                        valid_p, _ = partner.check_trade_salary_match(s_g, s_r)
                        if not valid_t or not valid_p:
                            continue
                            
                        net_team = len(rp) - len(gp)
                        net_partner = len(gp) - len(rp)
                        if len(team.roster) + net_team < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE or len(team.roster) + net_team > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
                            continue
                        if len(partner.roster) + net_partner < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE or len(partner.roster) + net_partner > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
                            continue
                            
                        giving_players = gp
                        receiving_players = rp
                        found_package = True
                        break
                        
                if not found_package:
                    continue
                
                # We have a player package. Now balance strategic value using picks.
                giving_picks = []
                receiving_picks = []
                
                # Helper to evaluate if partner accepts and why
                def check_acceptance(partner=partner, giving_players=giving_players, giving_picks=giving_picks,
                                        receiving_players=receiving_players, receiving_picks=receiving_picks):
                    return self.would_accept_trade_with_reason(
                        partner, 
                        giving_players + giving_picks, 
                        receiving_players + receiving_picks
                    )
                
                partner_accepts, _ = check_acceptance()
                
                # Case A: Partner needs more value to accept
                if not partner_accepts:
                    for py, pk in team_picks:
                        if len(giving_picks) >= 3:
                            break
                        if "R2" in pk and sum(1 for p in giving_picks if "R2" in p) >= 2:
                            continue
                            
                        pick_asset = f"{py}:{pk}"
                        # Check Stepien rule if we add this R1 pick
                        if "R1" in pk:
                            valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, team.nome, giving_picks + [pick_asset])
                            if not valid_s:
                                continue
                        
                        giving_picks.append(pick_asset)
                        partner_accepts, _ = check_acceptance()
                        if partner_accepts:
                            break
                            
                # Case B: Partner gets too much value (user is overpaying), so partner gives picks
                else:
                    val_user_gives = sum(self.get_strategic_value(p, partner) for p in giving_players + giving_picks)
                    val_partner_gives = sum(self.get_strategic_value(p, partner) for p in receiving_players)
                    
                    if val_user_gives > val_partner_gives * 1.15:
                        for py, pk in partner_picks:
                            if len(receiving_picks) >= 3:
                                break
                            if "R2" in pk and sum(1 for p in receiving_picks if "R2" in p) >= 2:
                                continue
                                
                            pick_asset = f"{py}:{pk}"
                            if "R1" in pk:
                                valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, partner.nome, receiving_picks + [pick_asset])
                                if not valid_s:
                                    continue
                            
                            # Check if partner still accepts after adding this pick to their giving side
                            still_accepts, _ = self.would_accept_trade_with_reason(
                                partner, 
                                giving_players + giving_picks, 
                                receiving_players + receiving_picks + [pick_asset]
                            )
                            if still_accepts:
                                receiving_picks.append(pick_asset)
                                # Update total given
                                val_partner_gives = sum(self.get_strategic_value(p, partner) for p in receiving_players + receiving_picks)
                                if val_user_gives <= val_partner_gives * 1.1:
                                    break
                            else:
                                break
                
                # Perform final validation check using TradeValidator
                is_valid, _ = TradeValidator.validate_trade(
                    team, partner, 
                    giving_players + giving_picks, 
                    receiving_players + receiving_picks, 
                    torneo=self.torneo
                )
                if not is_valid:
                    continue
                    
                # Re-evaluate final acceptability and likelihood
                partner_accepts, partner_reason = check_acceptance()
                team_accepts, _ = self.would_accept_trade_with_reason(
                    team, 
                    receiving_players + receiving_picks, 
                    giving_players + giving_picks
                )
                
                # Roster check ensures roster sizes are valid
                if not partner_accepts:
                    continue   # only deals the CPU side would do (it has a wish the deal fulfils) are shown
                trade_likelihood = "High" if team_accepts else "Medium"

                # Value differential from user's perspective
                user_receives_val = sum(self.get_strategic_value(p, team) for p in receiving_players + receiving_picks)
                user_gives_val = sum(self.get_strategic_value(p, team) for p in giving_players + giving_picks)
                val_diff = user_receives_val - user_gives_val
                
                # Format compat objects for old UI
                def serialize_players(plist):
                    return [{
                        "name": p.nome,
                        "ovr": p.ovr,
                        "position": p.ruolo,
                        "age": p.eta,
                        "salary": p.contract.salario_annuale if p.contract else 0,
                        "contract_years": p.contract.anni_rimanenti if p.contract else 0
                    } for p in plist]
                    
                comp_received = {
                    "name": " + ".join(p.nome for p in receiving_players),
                    "ovr": sum(p.ovr for p in receiving_players) // len(receiving_players) if receiving_players else 0,
                    "position": "/".join(p.ruolo for p in receiving_players),
                    "age": sum(p.eta for p in receiving_players) // len(receiving_players) if receiving_players else 0,
                    "salary": sum(p.contract.salario_annuale for p in receiving_players if p.contract),
                    "contract_years": min((p.contract.anni_rimanenti for p in receiving_players if p.contract), default=0)
                }
                
                comp_given = {
                    "name": " + ".join(p.nome for p in giving_players),
                    "ovr": sum(p.ovr for p in giving_players) // len(giving_players) if giving_players else 0,
                    "position": "/".join(p.ruolo for p in giving_players),
                    "age": sum(p.eta for p in giving_players) // len(giving_players) if giving_players else 0,
                    "salary": sum(p.contract.salario_annuale for p in giving_players if p.contract)
                }
                
                possible_trades.append({
                    "partner_team": partner.nome,
                    "player_received": comp_received,
                    "player_given": comp_given,
                    "giving_players": serialize_players(giving_players),
                    "receiving_players": serialize_players(receiving_players),
                    "giving_picks": giving_picks,
                    "receiving_picks": receiving_picks,
                    "value_differential": round(val_diff, 1),
                    "is_fair": abs(val_diff) < 25,
                    "likelihood": trade_likelihood,
                    "why": self.user_motive(self.pair_deal(
                        team, partner, giving_players + giving_picks, receiving_players + receiving_picks)).why,
                    "partner_strategy": self.get_team_strategy(partner),
"is_package": len(receiving_players) > 1 or len(giving_players) > 1 or len(giving_picks) > 0 or len(receiving_picks) > 0
                })
                
        # Sort by likelihood and value
        likelihood_order = {"High": 0, "Medium": 1, "Low": 2}
        possible_trades.sort(key=lambda x: (likelihood_order.get(x["likelihood"], 3), -x["value_differential"]))
        
        return possible_trades[:20]  # Return top 20 options

    def find_trades_for_pick(self, pick_asset: str) -> List[Dict]:
        """
        Find all possible trades where the user trades away a specific draft pick.
        Returns list of dicts with trade possibilities for the Trade Finder UI.
        """
        from trades.trade_validator import TradeValidator
        import itertools

        if not self.squadra_giocatore or not pick_asset:
            return []
        
        team = self.squadra_giocatore
        filler_pay = self.era().money(8.0)

        # Check if the user team actually owns this pick
        # pick_asset format: "1:R1-TeamName"
        if ":" not in pick_asset:
            return []
            
        try:
            y_str, p_key = pick_asset.split(":", 1)
            pick_year = int(y_str)
        except ValueError:
            return []
            
        if self.torneo.pick_ownership.get(pick_year, {}).get(p_key) != team.nome:
            return []
            
        # Get pick projected value
        
        # User tradeable players (fillers to match salary if user team is over the cap)
        team_others = [p for p in self.get_tradeable_players(team) if p.contract]
        team_others.sort(key=lambda x: x.contract.salario_annuale)
        team_fillers = [p for p in team_others if p.contract.salario_annuale < filler_pay]
        
        # Deduplicated team picks (excluding the searched pick)
        team_picks = [p for p in self._collect_team_picks(team) if f"{p[0]}:{p[1]}" != pick_asset]
        
        possible_trades = []
        
        for partner in self.squadre:
            if len(possible_trades) >= 30:
                break
            if partner == team:
                continue
            if self.squadra_giocatore and (partner == self.squadra_giocatore or partner.nome == self.squadra_giocatore.nome):
                continue
                
            if not self.wishes_for(partner):
                continue   # a team with nothing on its wish list has no use for the pick
            partner_tradeables = self.get_tradeable_players(partner)
            if not partner_tradeables:
                continue

            partner_picks = self._collect_team_picks(partner)
            partner_others = [p for p in partner_tradeables if p.contract]
            partner_others.sort(key=lambda x: x.contract.salario_annuale)
            partner_fillers = [p for p in partner_others if p.contract.salario_annuale < filler_pay]
            
            # Iterate through all tradeable players on partner team as target stars
            for target in partner_tradeables:
                if len(possible_trades) >= 30:
                    break
                if not target.contract:
                    continue
                    
                target_salary = target.contract.salario_annuale
                
                found_package = False
                giving_players = []
                receiving_players = []
                
                # Check 0-player swap (absorb into cap/exception)
                salary_r = target_salary
                valid_team, _ = team.check_trade_salary_match(salary_r, 0.0)
                valid_partner, _ = partner.check_trade_salary_match(0.0, salary_r)
                if valid_team and valid_partner:
                    if 10 <= len(team.roster) + 1 <= CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2 and 10 <= len(partner.roster) - 1 <= CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2:
                        giving_players = []
                        receiving_players = [target]
                        found_package = True
                else:
                    avail_t_fillers = team_fillers[:4]
                    avail_p_fillers = [f for f in partner_fillers if f != target][:3]
                    
                    combos_to_try = []
                    # 1 team filler
                    for tf in avail_t_fillers:
                        combos_to_try.append(([tf], []))
                    # 2 team fillers
                    for tf1, tf2 in itertools.combinations(avail_t_fillers[:3], 2):
                        combos_to_try.append(([tf1, tf2], []))
                    # 1 team filler + 1 partner filler
                    for tf in avail_t_fillers[:2]:
                        for pf in avail_p_fillers:
                            combos_to_try.append(([tf], [pf]))
                            
                    for g_f, r_f in combos_to_try:
                        gp = g_f
                        rp = [target] + r_f
                        
                        salary_g = sum(p.contract.salario_annuale for p in gp)
                        salary_r = sum(p.contract.salario_annuale for p in rp)
                        
                        valid_team, _ = team.check_trade_salary_match(salary_r, salary_g)
                        valid_partner, _ = partner.check_trade_salary_match(salary_g, salary_r)
                        if not valid_team or not valid_partner:
                            continue
                            
                        net_team = len(rp) - len(gp)
                        net_partner = len(gp) - len(rp)
                        if len(team.roster) + net_team < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE or len(team.roster) + net_team > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2:
                            continue
                        if len(partner.roster) + net_partner < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE or len(partner.roster) + net_partner > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2:
                            continue
                            
                        giving_players = gp
                        receiving_players = rp
                        found_package = True
                        break
                        
                if not found_package:
                    continue
                    
                giving_picks = [pick_asset]
                receiving_picks = []
                
                def check_acceptance(partner=partner, giving_players=giving_players, giving_picks=giving_picks,
                                        receiving_players=receiving_players, receiving_picks=receiving_picks):
                    return self.would_accept_trade_with_reason(
                        partner,
                        giving_players + giving_picks,
                        receiving_players + receiving_picks
                    )
                    
                partner_accepts, _ = check_acceptance()
                
                # Case A: Partner needs more value
                if not partner_accepts:
                    for py, pk in team_picks:
                        if len(giving_picks) >= 3:
                            break
                        if "R2" in pk and sum(1 for p in giving_picks if "R2" in p) >= 2:
                            continue
                            
                        p_asset = f"{py}:{pk}"
                        if "R1" in pk:
                            valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, team.nome, giving_picks + [p_asset])
                            if not valid_s:
                                continue
                        giving_picks.append(p_asset)
                        partner_accepts, _ = check_acceptance()
                        if partner_accepts:
                            break
                            
                # Case B: Partner gets too much value, they add picks
                else:
                    val_user_gives = sum(self.get_strategic_value(p, partner) for p in giving_players + giving_picks)
                    val_partner_gives = sum(self.get_strategic_value(p, partner) for p in receiving_players)
                    if val_user_gives > val_partner_gives * 1.15:
                        for py, pk in partner_picks:
                            if len(receiving_picks) >= 3:
                                break
                            if "R2" in pk and sum(1 for p in receiving_picks if "R2" in p) >= 2:
                                continue
                                
                            p_asset = f"{py}:{pk}"
                            if "R1" in pk:
                                valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, partner.nome, receiving_picks + [p_asset])
                                if not valid_s:
                                    continue
                            still_accepts, _ = self.would_accept_trade_with_reason(
                                partner,
                                giving_players + giving_picks,
                                receiving_players + receiving_picks + [p_asset]
                            )
                            if still_accepts:
                                receiving_picks.append(p_asset)
                                val_partner_gives = sum(self.get_strategic_value(p, partner) for p in receiving_players + receiving_picks)
                                if val_user_gives <= val_partner_gives * 1.1:
                                    break
                            else:
                                break
                                
                # Validate trade
                is_valid, _ = TradeValidator.validate_trade(
                    team, partner,
                    giving_players + giving_picks,
                    receiving_players + receiving_picks,
                    torneo=self.torneo
                )
                if not is_valid:
                    continue
                    
                partner_accepts, partner_reason = check_acceptance()
                team_accepts, _ = self.would_accept_trade_with_reason(
                    team,
                    receiving_players + receiving_picks,
                    giving_players + giving_picks
                )
                
                if not partner_accepts:
                    continue   # only deals the CPU side would do (it has a wish the deal fulfils) are shown
                trade_likelihood = "High" if team_accepts else "Medium"

                user_receives_val = sum(self.get_strategic_value(p, team) for p in receiving_players + receiving_picks)
                user_gives_val = sum(self.get_strategic_value(p, team) for p in giving_players + giving_picks)
                val_diff = user_receives_val - user_gives_val
                
                def serialize_players(plist):
                    return [{
                        "name": p.nome,
                        "ovr": p.ovr,
                        "position": p.ruolo,
                        "age": p.eta,
                        "salary": p.contract.salario_annuale if p.contract else 0,
                        "contract_years": p.contract.anni_rimanenti if p.contract else 0
                    } for p in plist]
                    
                comp_received = {
                    "name": " + ".join(p.nome for p in receiving_players),
                    "ovr": sum(p.ovr for p in receiving_players) // len(receiving_players) if receiving_players else 0,
                    "position": "/".join(p.ruolo for p in receiving_players),
                    "age": sum(p.eta for p in receiving_players) // len(receiving_players) if receiving_players else 0,
                    "salary": sum(p.contract.salario_annuale for p in receiving_players if p.contract),
                    "contract_years": min((p.contract.anni_rimanenti for p in receiving_players if p.contract), default=0)
                }
                
                comp_given = {
                    "name": " + ".join(p.nome for p in giving_players) if giving_players else "Pick",
                    "ovr": sum(p.ovr for p in giving_players) // len(giving_players) if giving_players else 0,
                    "position": "/".join(p.ruolo for p in giving_players) if giving_players else "Pick",
                    "age": sum(p.eta for p in giving_players) // len(giving_players) if giving_players else 0,
                    "salary": sum(p.contract.salario_annuale for p in giving_players if p.contract)
                }
                
                possible_trades.append({
                    "partner_team": partner.nome,
                    "player_received": comp_received,
                    "player_given": comp_given,
                    "giving_players": serialize_players(giving_players),
                    "receiving_players": serialize_players(receiving_players),
                    "giving_picks": giving_picks,
                    "receiving_picks": receiving_picks,
                    "value_differential": round(val_diff, 1),
                    "is_fair": abs(val_diff) < 25,
                    "likelihood": trade_likelihood,
                    "why": self.user_motive(self.pair_deal(
                        team, partner, giving_players + giving_picks, receiving_players + receiving_picks)).why,
                    "partner_strategy": self.get_team_strategy(partner),
"is_package": len(receiving_players) > 1 or len(giving_players) > 0 or len(giving_picks) > 1 or len(receiving_picks) > 0
                })
                
        # Sort by likelihood and value
        likelihood_order = {"High": 0, "Medium": 1, "Low": 2}
        possible_trades.sort(key=lambda x: (likelihood_order.get(x["likelihood"], 3), -x["value_differential"]))
        
        return possible_trades[:20]

    def find_trades_for_target_player(self, target: 'Giocatore') -> List[Dict]:
        """
        Reverse Trade Finder: Find what package of user assets (players and/or picks)
        the target player's team would accept to trade him away.
        """
        from trades.trade_validator import TradeValidator
        import itertools

        if not self.squadra_giocatore or not target or not target.squadra:
            return []
            
        team = self.squadra_giocatore
        partner = target.squadra
        
        if partner == team or not self.wishes_for(partner):
            return []   # a team with nothing on its wish list has no use for any package

        era = self.era()
        # User tradeable assets
        team_tradeables = self.get_tradeable_players(team, allow_stars=(target.ovr >= era.ovr_at(85)))
        team_picks = self._collect_team_picks(team)
        
        partner_tradeables = self.get_tradeable_players(partner)
        partner_fillers = [p for p in partner_tradeables if p != target and p.contract and p.contract.salario_annuale < era.money(8.0)]
        partner_fillers.sort(key=lambda x: x.contract.salario_annuale)
        
        possible_trades = []
        
        # We search combinations of user assets to match target:
        # User gives: `giving_players` (combinations of 0, 1, or 2 players from team_tradeables)
        # Partner gives: `[target]` + up to 1 partner filler
        # We also try combinations of user picks
        
        # Let's generate user player combinations:
        g_combos = [[]]
        for p in team_tradeables:
            g_combos.append([p])
        for p1, p2 in itertools.combinations(team_tradeables, 2):
            g_combos.append([p1, p2])
            
        # Partner filler combinations:
        r_combos = [[]]
        for f in partner_fillers:
            r_combos.append([f])
            
        for g_players in g_combos:
            for r_fillers in r_combos:
                receiving_players = [target] + r_fillers
                giving_players = g_players
                
                salary_g = sum(p.contract.salario_annuale for p in giving_players)
                salary_r = sum(p.contract.salario_annuale for p in receiving_players)
                
                # Check CBA salary match
                valid_team, _ = team.check_trade_salary_match(salary_r, salary_g)
                valid_partner, _ = partner.check_trade_salary_match(salary_g, salary_r)
                if not valid_team or not valid_partner:
                    continue
                    
                # Check roster limits
                net_team = len(receiving_players) - len(giving_players)
                net_partner = len(giving_players) - len(receiving_players)
                if len(team.roster) + net_team < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE or len(team.roster) + net_team > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2:
                    continue
                if len(partner.roster) + net_partner < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE or len(partner.roster) + net_partner > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT + 2:
                    continue
                    
                # Now, find what picks (if any) we need to attach for the partner to accept
                giving_picks = []
                receiving_picks = []
                
                def check_acceptance(partner=partner, giving_players=giving_players, giving_picks=giving_picks,
                                        receiving_players=receiving_players, receiving_picks=receiving_picks):
                    return self.would_accept_trade_with_reason(
                        partner,
                        giving_players + giving_picks,
                        receiving_players + receiving_picks
                    )
                    
                partner_accepts, _ = check_acceptance()
                
                # Case A: Partner needs more value (add user picks)
                if not partner_accepts:
                    for py, pk in team_picks:
                        if len(giving_picks) >= 3:
                            break
                        if "R2" in pk and sum(1 for p in giving_picks if "R2" in p) >= 2:
                            continue
                            
                        p_asset = f"{py}:{pk}"
                        if "R1" in pk:
                            valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, team.nome, giving_picks + [p_asset])
                            if not valid_s:
                                continue
                        giving_picks.append(p_asset)
                        partner_accepts, _ = check_acceptance()
                        if partner_accepts:
                            break
                            
                # Case B: User is overpaying, so partner gives picks
                else:
                    val_user_gives = sum(self.get_strategic_value(p, partner) for p in giving_players + giving_picks)
                    val_partner_gives = sum(self.get_strategic_value(p, partner) for p in receiving_players)
                    if val_user_gives > val_partner_gives * 1.15:
                        partner_picks = self._collect_team_picks(partner)
                        for py, pk in partner_picks:
                            if len(receiving_picks) >= 3:
                                break
                            if "R2" in pk and sum(1 for p in receiving_picks if "R2" in p) >= 2:
                                continue
                                
                            p_asset = f"{py}:{pk}"
                            if "R1" in pk:
                                valid_s, _ = TradeValidator.check_stepien_rule(self.torneo, partner.nome, receiving_picks + [p_asset])
                                if not valid_s:
                                    continue
                            still_accepts, _ = self.would_accept_trade_with_reason(
                                partner,
                                giving_players + giving_picks,
                                receiving_players + receiving_picks + [p_asset]
                            )
                            if still_accepts:
                                receiving_picks.append(p_asset)
                                val_partner_gives = sum(self.get_strategic_value(p, partner) for p in receiving_players + receiving_picks)
                                if val_user_gives <= val_partner_gives * 1.1:
                                    break
                            else:
                                break
                                
                # Verify final validity
                is_valid, _ = TradeValidator.validate_trade(
                    team, partner,
                    giving_players + giving_picks,
                    receiving_players + receiving_picks,
                    torneo=self.torneo
                )
                if not is_valid:
                    continue
                    
                partner_accepts, partner_reason = check_acceptance()
                team_accepts, _ = self.would_accept_trade_with_reason(
                    team,
                    receiving_players + receiving_picks,
                    giving_players + giving_picks
                )
                
                trade_likelihood = "High" if (team_accepts and partner_accepts) else ("Medium" if partner_accepts else "Low")
                
                # We only show offers that the partner team is actually willing to accept (High or Medium likelihood)
                # This makes the "Get Offers" function act as a real set of options the CPU team accepts
                if not partner_accepts:
                    continue
                    
                user_receives_val = sum(self.get_strategic_value(p, team) for p in receiving_players + receiving_picks)
                user_gives_val = sum(self.get_strategic_value(p, team) for p in giving_players + giving_picks)
                val_diff = user_receives_val - user_gives_val
                
                def serialize_players(plist):
                    return [{
                        "name": p.nome,
                        "ovr": p.ovr,
                        "position": p.ruolo,
                        "age": p.eta,
                        "salary": p.contract.salario_annuale if p.contract else 0,
                        "contract_years": p.contract.anni_rimanenti if p.contract else 0
                    } for p in plist]
                    
                comp_received = {
                    "name": " + ".join(p.nome for p in receiving_players),
                    "ovr": sum(p.ovr for p in receiving_players) // len(receiving_players) if receiving_players else 0,
                    "position": "/".join(p.ruolo for p in receiving_players),
                    "age": sum(p.eta for p in receiving_players) // len(receiving_players) if receiving_players else 0,
                    "salary": sum(p.contract.salario_annuale for p in receiving_players if p.contract),
                    "contract_years": min((p.contract.anni_rimanenti for p in receiving_players if p.contract), default=0)
                }
                
                comp_given = {
                    "name": " + ".join(p.nome for p in giving_players) if giving_players else "Picks",
                    "ovr": sum(p.ovr for p in giving_players) // len(giving_players) if giving_players else 0,
                    "position": "/".join(p.ruolo for p in giving_players) if giving_players else "Picks",
                    "age": sum(p.eta for p in giving_players) // len(giving_players) if giving_players else 0,
                    "salary": sum(p.contract.salario_annuale for p in giving_players if p.contract)
                }
                
                possible_trades.append({
                    "partner_team": partner.nome,
                    "player_received": comp_received,
                    "player_given": comp_given,
                    "giving_players": serialize_players(giving_players),
                    "receiving_players": serialize_players(receiving_players),
                    "giving_picks": giving_picks,
                    "receiving_picks": receiving_picks,
                    "value_differential": round(val_diff, 1),
                    "is_fair": abs(val_diff) < 25,
                    "likelihood": trade_likelihood,
                    "why": self.user_motive(self.pair_deal(
                        team, partner, giving_players + giving_picks, receiving_players + receiving_picks)).why,
                    "partner_strategy": self.get_team_strategy(partner),
"is_package": len(receiving_players) > 1 or len(giving_players) > 0 or len(giving_picks) > 0 or len(receiving_picks) > 0
                })
                
        # Sort by value differential or length of package (favoring simpler packages first)
        possible_trades.sort(key=lambda x: (len(x["giving_players"]) + len(x["giving_picks"]), -x["value_differential"]))
        
        return possible_trades[:20]

    def _draft_candidates(self, partner: 'Squadra', user_team: 'Squadra', pick_key: str, pick_pos: int,
                          high_pick_value: float) -> List[Tuple[str, list, str]]:
        """What `partner` could send for the user's pick on the clock, as (type, assets it sends, description):
        a lower pick with a rotation player, a star, or its future picks. Only what is worth about the pick to the user."""
        era, cfg = self.era(), CONFIG.TRADES
        year = getattr(self.torneo, 'starting_year', 2025)
        found = []

        lower = next(((pk, self._get_pick_position(pk)) for pk, owner in self.torneo.pick_ownership.get(1, {}).items()
                      if owner == partner.nome and pk.startswith("R1") and self._get_pick_position(pk) > pick_pos), None)
        tradeable = self.get_tradeable_players(partner)
        mid = [p for p in tradeable if era.ovr_at(74) <= p.ovr <= era.ovr_at(82) and p.eta >= 22]
        if lower and mid:
            best = max(mid, key=lambda p: p.ovr)
            worth = self.get_strategic_value(best, user_team) + self.get_pick_value(lower[0], 1, on_curve=True)
            if worth >= high_pick_value * cfg.DRAFT_OFFER_PICK_SHARE and user_team.check_trade_salary_match(best.contract.salario_annuale, 0)[0]:
                found.append(("TRADE_DOWN", [best, f"1:{lower[0]}"],
                              f"The {partner.nome} offer {best.nome} ({best.ovr}) and pick #{lower[1]} in exchange for your pick #{pick_pos}."))
        stars = [p for p in tradeable if p.ovr >= era.ovr_at(82) and p.eta >= 24]
        if stars:
            star = max(stars, key=lambda p: p.ovr)
            if (self.get_strategic_value(star, user_team) >= high_pick_value * cfg.DRAFT_OFFER_STAR_SHARE
                    and user_team.check_trade_salary_match(star.contract.salario_annuale, 0)[0]):
                found.append(("STAR_FOR_PICK", [star],
                              f"The {partner.nome} offer star {star.nome} ({star.ovr}) in exchange for your pick #{pick_pos}."))
        future = [f"2:R1-{partner.nome}", f"3:R2-{partner.nome}"]
        if (all(self.torneo.pick_ownership.get(int(k[0]), {}).get(k[2:]) == partner.nome for k in future)
                and sum(self.get_pick_value(k[2:], int(k[0]), on_curve=True) for k in future) >= high_pick_value * cfg.DRAFT_OFFER_PICK_SHARE):
            found.append(("PICKS_PACKAGE", future,
                          f"The {partner.nome} offer their {year + 1} R1 pick and {year + 2} R2 pick in exchange for your pick #{pick_pos}."))
        return found

    def generate_live_draft_offers(self, user_team: 'Squadra', pick_pos: int, pick_key: str) -> List[Dict[str, Any]]:
        """
        CPU offers for the user's pick on the clock (up to 3). A team offers only when a draft wish of its own
        (MOVE_UP_DRAFT, TARGET_PROSPECT, MOVE_DOWN_DRAFT) is fulfilled by the deal and it passes both acceptance
        questions; the offer carries the `why` of that wish.
        """
        from trades.engines.common import partners_with, wish_fulfilled
        self.begin_window("draft")
        year = getattr(self.torneo, 'starting_year', 2025)
        user_pick = f"1:{pick_key}"
        high_pick_value = self.get_pick_value(pick_key, 1, on_curve=True)
        by_type: Dict[str, list] = {"TRADE_DOWN": [], "STAR_FOR_PICK": [], "PICKS_PACKAGE": []}

        for partner, _top in partners_with(self, DRAFT_WISH_KINDS):
            wishes = [w for w in self.wishes_for(partner) if w.kind in DRAFT_WISH_KINDS
                      and not (w.kind == "MOVE_UP_DRAFT" and pick_pos > w.get("slot", pick_pos))]   # high enough for his man
            for offer_type, cpu_assets, description in self._draft_candidates(partner, user_team, pick_key, pick_pos, high_pick_value):
                wish = next((w for w in wishes if wish_fulfilled(self, partner, w, [user_pick], cpu_assets)), None)
                if wish is None or not self.would_accept_trade_with_reason(partner, [user_pick], cpu_assets)[0]:
                    continue
                players = [a for a in cpu_assets if not isinstance(a, str)]
                motive = self.user_motive(self.pair_deal(user_team, partner, [user_pick], cpu_assets), {partner.nome: wish})
                by_type[offer_type].append({
                    "id": f"{offer_type.lower()}_{partner.nome}_{'_'.join(p.nome for p in players)}".rstrip("_").replace(" ", "_"),
                    "partner": partner.nome,
                    "type": offer_type,
                    "cpu_gives_players": [p.nome for p in players],
                    "cpu_gives_players_ovr": [p.ovr for p in players],
                    "cpu_gives_picks": [self._draft_pick_label(a, year, pick_pos) for a in cpu_assets if isinstance(a, str)],
                    "user_gives_picks": [f"Pick #{pick_pos} ({year})"],
                    "cpu_gives_assets": cpu_assets,
                    "user_gives_assets": [user_pick],
                    "description": description,
                    "why": motive.why,
                    "motive": motive,
                })
        return (by_type["TRADE_DOWN"][:2] + by_type["STAR_FOR_PICK"] + by_type["PICKS_PACKAGE"])[:3]

    def _draft_pick_label(self, asset: str, year: int, user_pick_pos: int) -> str:
        """A CPU pick in an offer as the draft desk shows it: "Pick #12 (2002)", or "R1 2003" for a later draft."""
        n, key = asset.split(":", 1)
        if int(n) == 1:
            return f"Pick #{self._get_pick_position(key)} ({year})"
        return f"{key.split('-')[0]} pick {year + int(n) - 1}"

    def _get_team_positional_needs(self, team: 'Squadra') -> list:
        """Determines a team's positional needs, ordered from most to least urgent."""
        if not team or not team.roster:
            return ['PG', 'SG', 'SF', 'PF', 'C']

        if hasattr(self, '_needs_cache') and self._needs_cache and team.nome in self._needs_cache:
            return self._needs_cache[team.nome]

        position_scores = {'PG': 0.0, 'SG': 0.0, 'SF': 0.0, 'PF': 0.0, 'C': 0.0}
        for player in team.roster:
            score = player.ovr + player.potenziale
            if player.eta < 25:
                score *= 1.5
            elif player.eta > 30:
                score *= 0.5
            
            p_role_norm = normalize_role(player.ruolo)
            if hasattr(player, 'valutazioni_posizionali') and player.valutazioni_posizionali:
                for pos, val_pos in player.valutazioni_posizionali.items():
                    norm_pos = normalize_role(pos)
                    if norm_pos in position_scores:
                        base_pos_score = (val_pos / 99.0) * score
                        multiplier = 2.0 if p_role_norm == norm_pos else 1.0
                        position_scores[norm_pos] += base_pos_score * multiplier
            else:
                if p_role_norm in position_scores:
                    position_scores[p_role_norm] += score * 2.0

        res = sorted(position_scores, key=position_scores.get)
        if not hasattr(self, '_needs_cache') or self._needs_cache is None:
            self._needs_cache = {}
        self._needs_cache[team.nome] = res
        return res

    def generate_counter_offer(
        self,
        partner_team: 'Squadra',
        user_team: 'Squadra',
        giving_assets: list,
        receiving_assets: list,
        pick_protections: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        A CPU counter to a user trade it would refuse, on the same two questions as every CPU answer.
        Plan question first: the CPU asks for the asset of the user's that fulfils its highest-priority wish the user's
        roster can satisfy; with none it refuses with the plan sentence (no overpay buys a yes). Price second: missing
        value is bridged with pick protections, a pick or a player. The counter is only offered when the CPU
        would really accept it. `why` is the CPU's reason for the deal as countered.
        """
        def answer(has_counter: bool, message: str, players=(), picks=(), protections=None, as_is=False, deal_gives=None) -> Dict[str, Any]:
            why = self.user_motive(self.pair_deal(user_team, partner_team, deal_gives, receiving_assets)).why if has_counter else ""
            return {"has_counter": has_counter, "message": message, "add_user_players": list(players),
                    "add_user_picks": list(picks), "modified_protections": dict(protections or {}),
                    "accepted_as_is": as_is, "why": why}

        accepted, refusal = self.would_accept_trade_with_reason(partner_team, giving_assets, receiving_assets, pick_protections)
        if accepted:
            return answer(True, f"The {partner_team.nome} are already ready to accept the deal as it stands!",
                          as_is=True, deal_gives=giving_assets)

        giving = list(giving_assets)
        add_players: list = []
        add_picks: list = []
        modified_protections: Dict[str, str] = {}

        # 1. The plan question: ask for the asset that fulfils the CPU's wish
        plan_ok, plan_reason, _wish = self.plan_check(partner_team, giving, receiving_assets)
        if not plan_ok:
            asked = self.asset_for_wish(partner_team, user_team, giving, receiving_assets)
            if asked is None or not self.plan_check(partner_team, giving + [asked[0]], receiving_assets)[0]:
                return answer(False, plan_reason)
            giving.append(asked[0])
            (add_picks if isinstance(asked[0], str) else add_players).append(asked[0] if isinstance(asked[0], str) else asked[0].nome)

        # 2. The price
        rec_val = sum(self.get_strategic_value(a, partner_team, pick_protections) for a in giving)
        give_val = sum(self.get_strategic_value(a, partner_team, pick_protections) for a in receiving_assets)
        deficit = give_val - rec_val

        current_user_players = {id(a) for a in giving if not isinstance(a, str)}
        current_user_picks = {a for a in giving if isinstance(a, str)}
        available_picks = [f"{y}:{k}" for (y, k) in self._collect_team_picks(user_team) if f"{y}:{k}" not in current_user_picks]
        max_ovr = self.era().ovr_at(84)
        available_players = [p for p in user_team.roster if id(p) not in current_user_players and p.ovr <= max_ovr and getattr(p, 'contract', None)]

        if pick_protections:
            for pk_key, prot in pick_protections.items():
                if pk_key in current_user_picks and prot != "Unprotected":
                    unprotected_val = self.get_strategic_value(pk_key, partner_team, {pk_key: "Unprotected"})
                    protected_val = self.get_strategic_value(pk_key, partner_team, {pk_key: prot})
                    val_gain = unprotected_val - protected_val
                    if val_gain > 5.0:
                        modified_protections[pk_key] = "Unprotected"
                        deficit -= val_gain
                        if deficit <= 5.0:
                            break

        if deficit > 5.0 and available_picks:
            best_pick = min(available_picks, key=lambda pk: abs(self.get_strategic_value(pk, partner_team) - deficit))
            add_picks.append(best_pick)
            giving.append(best_pick)
            deficit -= self.get_strategic_value(best_pick, partner_team)

        if deficit > 8.0 and available_players:
            valued = [(p, self.get_strategic_value(p, partner_team)) for p in available_players]
            valued = [(p, v) for p, v in valued if v > 0]
            if valued:
                best_player = min(valued, key=lambda pv: abs(pv[1] - deficit))[0]
                add_players.append(best_player.nome)
                giving.append(best_player)

        if not (add_players or add_picks or modified_protections):
            return answer(False, f"The {partner_team.nome} do not intend to proceed: the value gap is too large and they don't see enough resources on your roster.")

        # 3. Only a counter the CPU would really accept is offered
        protections = {**(pick_protections or {}), **modified_protections}
        if not self.would_accept_trade_with_reason(partner_team, giving, receiving_assets, protections)[0]:
            return answer(False, f"The {partner_team.nome} do not intend to proceed: nothing on your roster closes the gap.")

        parts = []
        if add_players:
            parts.append(f"the player **{', '.join(add_players)}**")
        if add_picks:
            parts.append(f"the pick **{', '.join(self._format_asset(pk) for pk in add_picks)}**")
        if modified_protections:
            parts.append("removing the protections from the offered picks")
        message = (f"The **{partner_team.nome}** reject the base offer, but are willing to close the deal "
                   f"if you include {' and '.join(parts)} in the trade.")
        return answer(True, message, add_players, add_picks, modified_protections, deal_gives=giving)

    def find_3_team_trades_for_package(self, giving_players: List['Giocatore'], giving_picks: List[str],
                                        user_pick_protections: dict = None, target_position: str = None) -> List[Dict]:
        """
        ### REWORKED (v23.0 - Need-Triangle 3-Team Trade Finder) ###
        Generates 3-team trades based on complementary technical needs WITHOUT passive facilitators.
        Flow:
        - Team User -> Sends giving_players (+ opt picks) to Team B
        - Team B -> Sends player_b to Team C
        - Team C -> Sends target_c to Team User
        - Automatic compensation through Draft picks if the OVRs have a value gap.
        """
        from trades.trade_validator import TradeValidator

        if not self.squadra_giocatore or not giving_players:
            return []

        team = self.squadra_giocatore
        total_giving_salary = sum(p.contract.salario_annuale for p in giving_players if p.contract)
        total_giving_val = sum(self.get_strategic_value(p, team) for p in giving_players) + \
                           sum(self.get_strategic_value(pk, team) for pk in giving_picks)

        user_picks = self._collect_team_picks(team)
        three_team_trades = []
        starter_line = self.era().ovr_at(75)

        def serialize_players(players_list):
            return [{
                "name": p.nome,
                "team": p.squadra.nome if p.squadra else "",
                "position": p.ruolo,
                "ovr": p.ovr,
                "potential": p.potenziale,
                "salary": p.contract.salario_annuale if p.contract else getattr(p, 'salario', 0),
                "contract_years": p.contract.anni_rimanenti if p.contract else getattr(p, 'contract_years', 1),
                "trade_value": round(float(getattr(p, 'trade_value', p.ovr)), 1)
            } for p in players_list]

        user_roles = [normalize_role(p.ruolo) for p in giving_players]
        if not target_position:
            role_ovrs = {}
            for r in ['PG', 'SG', 'SF', 'PF', 'C']:
                starter = team.get_starter_at_position(r)
                role_ovrs[r] = starter.ovr if starter else 65
            sorted_needs = sorted(role_ovrs.items(), key=lambda x: x[1])
            target_positions = [r for r, ovr in sorted_needs if r not in user_roles][:3]
            if not target_positions:
                target_positions = ['SF', 'C', 'PF', 'SG', 'PG']
        else:
            target_norm = normalize_role(target_position)
            target_positions = [target_norm]

        # A team joins the deal only with a wish of its own that the deal fulfils (multi_team.extend's rule).
        candidate_b = [t for t in self.squadre if not self._is_user_team(t) and self.wishes_for(t)]
        random.shuffle(candidate_b)
        candidate_b = candidate_b[:12]

        for team_b in candidate_b:
            b_tradeables = self.get_tradeable_players(team_b, allow_stars=(total_giving_val >= 85))
            if not b_tradeables:
                continue

            for team_c in candidate_b:
                if team_c == team_b or team_c.nome == team_b.nome:
                    continue

                c_tradeables = self.get_tradeable_players(team_c, allow_stars=(total_giving_val >= 85))
                if not c_tradeables:
                    continue

                c_targets = [p for p in c_tradeables if (normalize_role(p.ruolo) in target_positions or not target_position) and p.contract]
                if not c_targets:
                    c_targets = [p for p in c_tradeables if p.contract and p.ovr >= starter_line]
                if not c_targets:
                    continue

                for target_c in c_targets[:3]:
                    b_candidates = [p for p in b_tradeables if p.contract and p != target_c and normalize_role(p.ruolo) != normalize_role(target_c.ruolo)]
                    if not b_candidates:
                        b_candidates = [p for p in b_tradeables if p.contract and p != target_c]
                    
                    for player_b in b_candidates[:3]:
                        # 1. CBA salary check for all three franchises
                        valid_u, _ = team.check_trade_salary_match(target_c.contract.salario_annuale, total_giving_salary)
                        if not valid_u:
                            continue

                        valid_b, _ = team_b.check_trade_salary_match(total_giving_salary, player_b.contract.salario_annuale)
                        if not valid_b:
                            continue

                        valid_c, _ = team_c.check_trade_salary_match(player_b.contract.salario_annuale, target_c.contract.salario_annuale)
                        if not valid_c:
                            continue

                        # 2. Roster limits check
                        if len(team.roster) + (1 - len(giving_players)) > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT or len(team.roster) + (1 - len(giving_players)) < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE:
                            continue
                        if len(team_b.roster) + (len(giving_players) - 1) > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT or len(team_b.roster) + (len(giving_players) - 1) < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE:
                            continue

                        # 3. Balancing and acceptance with Draft Picks
                        user_picks_to_b = list(giving_picks) if giving_picks else []
                        user_picks_to_c = []
                        
                        cand_in_b = giving_players + user_picks_to_b
                        cand_out_b = [player_b]
                        accepts_b, _ = self.would_accept_trade_with_reason(team_b, cand_in_b, cand_out_b)
                        if not accepts_b:
                            for py, pk in user_picks:
                                pk_asset = f"{py}:{pk}"
                                if pk_asset not in user_picks_to_b and pk_asset not in user_picks_to_c:
                                    user_picks_to_b.append(pk_asset)
                                    cand_in_b = giving_players + user_picks_to_b
                                    accepts_b, _ = self.would_accept_trade_with_reason(team_b, cand_in_b, cand_out_b)
                                    if accepts_b:
                                        break
                        if not accepts_b:
                            continue

                        cand_in_c = [player_b] + user_picks_to_c
                        cand_out_c = [target_c]
                        accepts_c, _ = self.would_accept_trade_with_reason(team_c, cand_in_c, cand_out_c)
                        if not accepts_c:
                            for py, pk in user_picks:
                                pk_asset = f"{py}:{pk}"
                                if pk_asset not in user_picks_to_b and pk_asset not in user_picks_to_c:
                                    user_picks_to_c.append(pk_asset)
                                    cand_in_c = [player_b] + user_picks_to_c
                                    accepts_c, _ = self.would_accept_trade_with_reason(team_c, cand_in_c, cand_out_c)
                                    if accepts_c:
                                        break
                        if not accepts_c:
                            continue

                        # 4. Formal CBA validation through TradeValidator.validate_3_team_trade
                        trade_data_dict = {
                            "team_a": {"gives_to_b": giving_players + user_picks_to_b, "gives_to_c": user_picks_to_c},
                            "team_b": {"gives_to_a": [], "gives_to_c": [player_b]},
                            "team_c": {"gives_to_a": [target_c], "gives_to_b": []}
                        }

                        is_valid_cba, cba_reason, _ = TradeValidator.validate_3_team_trade(
                            team, team_b, team_c, trade_data_dict, self.torneo
                        )
                        if not is_valid_cba:
                            continue

                        total_user_giving_val = sum(self.get_strategic_value(p, team) for p in giving_players) + \
                                                sum(self.get_strategic_value(pk, team) for pk in user_picks_to_b + user_picks_to_c)
                        val_diff = self.get_strategic_value(target_c, team) - total_user_giving_val

                        three_team_trades.append({
                            "trade_type": "3-team",
                            "partner_team": team_b.nome,
                            "third_team": team_c.nome,
                            "partner_strategy": self.get_team_strategy(team_b),
                            "third_strategy": self.get_team_strategy(team_c),
                            "user_gives_to_b": serialize_players(giving_players),
                            "user_picks_to_b": user_picks_to_b,
                            "user_picks_to_c": user_picks_to_c,
                            "user_receives": serialize_players([target_c]),
                            "b_gives_to_c": serialize_players([player_b]),
                            "b_receives": serialize_players(giving_players) + [f"Pick: {p}" for p in user_picks_to_b],
                            "c_gives_to_user": serialize_players([target_c]),
                            "c_receives": serialize_players([player_b]) + [f"Pick: {p}" for p in user_picks_to_c],
                            "value_differential": round(val_diff, 1),
                            "why": self.user_motive(self.three_team_deal(team, team_b, team_c, trade_data_dict)).why,
                            "fit_description": f"{team_b.nome} gets {giving_players[0].ruolo}, {team_c.nome} reinforces {player_b.ruolo}, and you receive {target_c.nome} ({target_c.ruolo} {target_c.ovr} OVR)!",
                            "raw_trade_data": {
                                "team_a": {"gives_to_b": [p.nome for p in giving_players] + user_picks_to_b, "gives_to_c": user_picks_to_c},
                                "team_b": {"gives_to_a": [], "gives_to_c": [player_b.nome]},
                                "team_c": {"gives_to_a": [target_c.nome], "gives_to_b": []}
                            }
                        })
                        break

                    if len(three_team_trades) >= 15:
                        break
                if len(three_team_trades) >= 15:
                    break
            if len(three_team_trades) >= 15:
                break

        three_team_trades.sort(key=lambda x: (max([p["ovr"] for p in x["user_receives"]], default=0), x["value_differential"]), reverse=True)
        return three_team_trades[:15]

    def find_multi_team_chain_trades(self, giving_players: List['Giocatore'] = None, giving_picks: List[str] = None) -> List[Dict]:
        """
        ### REWORKED (v24.0 - User-Package Driven 4-Team Mega-Deal Finder) ###
        Builds realistic 4-franchise trades starting from the package selected by the user!
        Checks strategic acceptance (would_accept_trade), complementary needs and CBA salary match.
        """
        if not self.squadra_giocatore:
            return []
            
        team = self.squadra_giocatore
        if not giving_players:
            user_tradeables = self.get_tradeable_players(team)
            if not user_tradeables:
                return []
            giving_players = [user_tradeables[0]]
        if giving_picks is None:
            giving_picks = []

        total_giving_salary = sum(p.contract.salario_annuale for p in giving_players if p.contract)
        total_giving_val = sum(self.get_strategic_value(p, team) for p in giving_players) + \
                           sum(self.get_strategic_value(pk, team) for pk in giving_picks)
        user_picks = self._collect_team_picks(team)

        chain_deals = []

        def serialize_players(players_list):
            return [{
                "name": p.nome,
                "team": p.squadra.nome if p.squadra else "",
                "position": p.ruolo,
                "ovr": p.ovr,
                "potential": p.potenziale,
                "salary": p.contract.salario_annuale if p.contract else getattr(p, 'salario', 0),
                "contract_years": p.contract.anni_rimanenti if p.contract else getattr(p, 'contract_years', 1),
                "trade_value": round(float(getattr(p, 'trade_value', p.ovr)), 1)
            } for p in players_list]

        # A team joins the chain only with a wish of its own that the deal fulfils (multi_team.extend's rule).
        other_teams = [t for t in self.squadre if not self._is_user_team(t) and self.wishes_for(t)]
        random.shuffle(other_teams)
        candidate_teams = other_teams[:8]
        
        for t2 in candidate_teams:
            t2_tradeables = self.get_tradeable_players(t2, allow_stars=(total_giving_val >= 85))
            if not t2_tradeables: continue

            for t3 in candidate_teams:
                if t3 == t2: continue
                t3_tradeables = self.get_tradeable_players(t3, allow_stars=(total_giving_val >= 85))
                if not t3_tradeables: continue

                for t4 in candidate_teams:
                    if t4 in [t2, t3]: continue
                    t4_tradeables = self.get_tradeable_players(t4, allow_stars=(total_giving_val >= 85))
                    if not t4_tradeables: continue

                    # Search players that fit salary & strategic acceptance
                    for p2 in t2_tradeables[:3]:
                        if not p2.contract: continue
                        for p3 in t3_tradeables[:3]:
                            if not p3.contract: continue
                            for p4 in t4_tradeables[:3]:
                                if not p4.contract: continue

                                # 1. CBA Salary Matching
                                v1, _ = team.check_trade_salary_match(p4.contract.salario_annuale, total_giving_salary)
                                v2, _ = t2.check_trade_salary_match(total_giving_salary, p2.contract.salario_annuale)
                                v3, _ = t3.check_trade_salary_match(p2.contract.salario_annuale, p3.contract.salario_annuale)
                                v4, _ = t4.check_trade_salary_match(p3.contract.salario_annuale, p4.contract.salario_annuale)

                                if not (v1 and v2 and v3 and v4):
                                    continue

                                # 2. Roster limits
                                if len(team.roster) + (1 - len(giving_players)) > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT or len(team.roster) + (1 - len(giving_players)) < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE:
                                    continue
                                if len(t2.roster) + (len(giving_players) - 1) > CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT or len(t2.roster) + (len(giving_players) - 1) < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE:
                                    continue

                                # 3. Strategic acceptance
                                user_pks_to_t2 = list(giving_picks) if giving_picks else []
                                t2_pks_to_t3 = []
                                t3_pks_to_t4 = []

                                acc2, _ = self.would_accept_trade_with_reason(t2, giving_players + user_pks_to_t2, [p2])
                                if not acc2:
                                    for py, pk in user_picks:
                                        pk_asset = f"{py}:{pk}"
                                        if pk_asset not in user_pks_to_t2:
                                            user_pks_to_t2.append(pk_asset)
                                            acc2, _ = self.would_accept_trade_with_reason(t2, giving_players + user_pks_to_t2, [p2])
                                            if acc2: break
                                if not acc2: continue

                                acc3, _ = self.would_accept_trade_with_reason(t3, [p2] + t2_pks_to_t3, [p3])
                                if not acc3: continue

                                acc4, _ = self.would_accept_trade_with_reason(t4, [p3] + t3_pks_to_t4, [p4])
                                if not acc4: continue

                                acc1, _ = self.would_accept_trade_with_reason(team, [p4], giving_players + user_pks_to_t2)
                                
                                total_user_giving_val = sum(self.get_strategic_value(p, team) for p in giving_players) + \
                                                        sum(self.get_strategic_value(pk, team) for pk in user_pks_to_t2)
                                val_diff = self.get_strategic_value(p4, team) - total_user_giving_val

                                flow_steps = [
                                    {"from": team.nome, "to": t2.nome, "player": ", ".join(p.nome for p in giving_players) + (f" + {', '.join(user_pks_to_t2)}" if user_pks_to_t2 else ""), "role": "/".join(p.ruolo for p in giving_players), "ovr": round(sum(p.ovr for p in giving_players)/len(giving_players)), "salary": total_giving_salary},
                                    {"from": t2.nome, "to": t3.nome, "player": p2.nome, "role": p2.ruolo, "ovr": p2.ovr, "salary": p2.contract.salario_annuale},
                                    {"from": t3.nome, "to": t4.nome, "player": p3.nome, "role": p3.ruolo, "ovr": p3.ovr, "salary": p3.contract.salario_annuale},
                                    {"from": t4.nome, "to": team.nome, "player": p4.nome, "role": p4.ruolo, "ovr": p4.ovr, "salary": p4.contract.salario_annuale}
                                ]

                                raw_flow = [
                                    {"from": team.nome, "to": t2.nome, "players": [p.nome for p in giving_players], "picks": user_pks_to_t2},
                                    {"from": t2.nome, "to": t3.nome, "players": [p2.nome], "picks": t2_pks_to_t3},
                                    {"from": t3.nome, "to": t4.nome, "players": [p3.nome], "picks": t3_pks_to_t4},
                                    {"from": t4.nome, "to": team.nome, "players": [p4.nome], "picks": []}
                                ]
                                chain_deals.append({
                                    "chain_length": 4,
                                    "trade_type": "multi-team",
                                    "teams": [team.nome, t2.nome, t3.nome, t4.nome],
                                    "user_gives": serialize_players(giving_players),
                                    "user_picks_giving": user_pks_to_t2,
                                    "user_receives": serialize_players([p4]),
                                    "flow": flow_steps,
                                    "value_differential": round(val_diff, 1),
                                    "why": self.user_motive(self.four_team_deal([team, t2, t3, t4], raw_flow)).why,
                                    "summary": f"4-Team Mega-Blockbuster: You receive {p4.nome} ({p4.ruolo} {p4.ovr} OVR) from {t4.nome} by sending {', '.join(p.nome for p in giving_players)} to {t2.nome}!",
                                    "raw_trade_data": {
                                        "team_a": team.nome,
                                        "team_b": t2.nome,
                                        "team_c": t3.nome,
                                        "team_d": t4.nome,
                                        "flow": raw_flow
}
                                })
                                if len(chain_deals) >= 8:
                                    return chain_deals
        return chain_deals

    def find_trades_by_need(self, target_position: str, min_ovr: int = 76, archetype: str = None) -> Dict[str, List]:
        """
        Active search by positional need: finds 2- and 3-team trades to bring home
        a player at the target_position with at least min_ovr.
        """
        if not self.squadra_giocatore:
            return {"two_team": [], "three_team": []}
            
        team = self.squadra_giocatore
        user_tradeables = self.get_tradeable_players(team)
        
        norm_target = normalize_role(target_position)
        surplus_candidates = [p for p in user_tradeables if normalize_role(p.ruolo) != norm_target]
        if not surplus_candidates:
            surplus_candidates = user_tradeables[:3]
            
        two_team_results = []
        three_team_results = []
        
        for cand in surplus_candidates[:3]:
            t2 = self.find_trades_for_package([cand], [])
            for deal in t2:
                for rec_p in deal.get("receiving_players", []):
                    if normalize_role(rec_p.get("position")) == norm_target and rec_p.get("ovr", 0) >= min_ovr:
                        two_team_results.append(deal)
                        break
                        
            t3 = self.find_3_team_trades_for_package([cand], [], target_position=norm_target)
            for deal in t3:
                for rec_p in deal.get("user_receives", []):
                    if normalize_role(rec_p.get("position")) == norm_target and rec_p.get("ovr", 0) >= min_ovr:
                        three_team_results.append(deal)
                        break
                        
        return {
            "two_team": two_team_results[:10],
            "three_team": three_team_results[:10]
        }

    def calculate_what_would_it_take(self, target_player: Any) -> Dict:
        """
        What it takes to convince the owning team to give target_player to the user: a package that fulfils one of
        the owner's wishes (the asset it asks for comes first) and a price it likes. With no wish the user's roster
        can satisfy, the answer is the plan sentence. `why` is the owner's reason when it would do the deal.
        """
        if isinstance(target_player, str):
            found = None
            for sq in self.squadre:
                for p in sq.roster:
                    if p.nome.lower() == target_player.lower():
                        found = p
                        break
                if found:
                    break
            target_player = found

        if not self.squadra_giocatore or not target_player or not target_player.squadra:
            return {"attainable": False, "reason": "Invalid data"}

        owner = target_player.squadra
        team = self.squadra_giocatore
        era = self.era()

        user_tradeables = self.get_tradeable_players(team)
        user_picks = self._collect_team_picks(team)

        target_val = self.get_strategic_value(target_player, owner)
        # An untouchable who does not ask out costs the premium: aim the package there (acceptance still decides).
        stop_val = target_val * 1.05
        if getattr(target_player, 'is_untouchable', False) and not getattr(target_player, '_wants_out', False):
            stop_val *= CONFIG.TRADES.UNTOUCHABLE_PREMIUM
        target_sal = target_player.contract.salario_annuale if target_player.contract else 5.0

        package_players = []
        package_picks = []
        cur_salary = 0.0

        sorted_user_players = sorted(user_tradeables, key=lambda p: (abs(p.contract.salario_annuale - target_sal) if p.contract else 999))
        for p in sorted_user_players:
            if not p.contract: continue
            package_players.append(p)
            cur_salary += p.contract.salario_annuale
            valid, _ = owner.check_trade_salary_match(cur_salary, target_sal)
            if valid:
                break
            if len(package_players) >= 3:
                break

        # The plan question: when the package does not fulfil a wish of the owner, ask for the asset that does.
        if not self.plan_check(owner, package_players, [target_player])[0]:
            asked = self.asset_for_wish(owner, team, package_players, [target_player])
            if asked is not None:
                (package_picks if isinstance(asked[0], str) else package_players).append(asked[0])

        cur_val = sum(self.get_strategic_value(a, owner) for a in package_players + package_picks)
        if cur_val < target_val:
            for py, pk in user_picks:
                if len(package_picks) >= 3:
                    break
                pk_asset = f"{py}:{pk}"
                if pk_asset in package_picks:
                    continue
                if pk.startswith("R1") and self._is_top5_pick(pk_asset) and target_player.ovr < era.ovr_at(88):
                    continue
                if "R1" in pk:
                    valid_stepien, _ = TradeValidator.check_stepien_rule(self.torneo, team.nome, package_picks + [pk_asset])
                    if not valid_stepien:
                        continue
                package_picks.append(pk_asset)
                cur_val += self.get_strategic_value(pk_asset, owner)
                if cur_val >= stop_val:
                    break

        accepts, reason = self.would_accept_trade_with_reason(owner, package_players + package_picks, [target_player])
        if accepts:
            is_valid_cba, cba_msg = TradeValidator.validate_trade(team, owner, package_players + package_picks, [target_player], torneo=self.torneo)
            if not is_valid_cba:
                accepts = False
                reason = f"CBA/Roster Rules: {cba_msg}"

        why = self.user_motive(self.pair_deal(team, owner, package_players + package_picks, [target_player])).why if accepts else ""
        return {
            "attainable": accepts,
            "target": {"name": target_player.nome, "team": owner.nome, "ovr": target_player.ovr, "salary": target_sal},
            "players_needed": [p.nome for p in package_players],
            "picks_needed": package_picks,
            "message": f"The {owner.nome} would be willing to trade {target_player.nome} if you offer: {', '.join([p.nome for p in package_players])}" + (f" and the picks {', '.join(package_picks)}" if package_picks else "") + ".",
            "accepts": accepts,
            "reason": reason,
            "why": why
        }
