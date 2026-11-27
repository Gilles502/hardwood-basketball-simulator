import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from core import runtime_state
from core.config import CONFIG

if TYPE_CHECKING:
    from core.models import Squadra, Giocatore

main_log = logging.getLogger('main_sim')

# League phases during which year 1 of the pick table is the draft being run right now.
_CURRENT_DRAFT_PHASES = ("DRAFT_USER_PICK", "OFFSEASON_DRAFT_START", "OFFSEASON_TRADES_START", "DRAFT_IN_PROGRESS")


class TradeValidator:
    """
    Validates NBA-style trades: salary rules, roster limits, the Stepien rule and asset restrictions.
    """

    @staticmethod
    def check_stepien_rule(torneo, team_name: str, r1_picks_being_traded: List[str]) -> Tuple[bool, str]:
        """
        Stepien Rule: After a trade, a team must still own at least one R1 pick
        in every pair of consecutive future years (1-2, 2-3, 3-4).

        r1_picks_being_traded: list of pick assets like "1:R1-TeamName", "2:R1-TeamName", or "R1-TeamName"
        """
        if not r1_picks_being_traded:
            return True, "No R1 picks traded"

        # The rule only applies to FUTURE drafts: while a draft is being run, year 1 is that draft.
        is_current_draft_period = (
            runtime_state.get_league_state() in _CURRENT_DRAFT_PHASES
            or runtime_state.get_active_draft() is not None
        )
        start_year = 2 if is_current_draft_period else 1

        r1_owned_by_year = {}
        for year in range(start_year, 6):
            count = 0
            for pk, owner in torneo.pick_ownership.get(year, {}).items():
                if owner == team_name and pk.startswith("R1"):
                    # Check if this specific pick is being traded away (matches "Y:R1-Team" or "R1-Team")
                    pick_asset = f"{year}:{pk}"
                    if pick_asset not in r1_picks_being_traded and pk not in r1_picks_being_traded:
                        count += 1
            r1_owned_by_year[year] = count

        # Check consecutive year pairs
        for y in range(start_year, 5):
            if r1_owned_by_year.get(y, 0) == 0 and r1_owned_by_year.get(y + 1, 0) == 0:
                return False, f"Stepien Rule: {team_name} would have no R1 picks in years {y} and {y+1}"

        return True, "OK"

    @staticmethod
    def execute_roster_cuts(team, needed_cuts: int, players_giving: List, torneo) -> List[str]:
        """
        Cuts the lowest-value disposable players from the team's roster to make room for a trade.
        Returns a list of messages describing the cuts.
        """
        cut_messages = []

        # Candidate players to cut: not being traded away and not untouchable
        candidates = [
            p for p in team.roster
            if p not in players_giving
            and not getattr(p, 'is_untouchable', False)
        ]

        # Sort candidates: lowest OVR first, then older age first to sacrifice
        candidates_sorted = sorted(candidates, key=lambda x: (x.ovr, -x.eta))

        for i in range(min(needed_cuts, len(candidates_sorted))):
            p_to_cut = candidates_sorted[i]
            team.roster.remove(p_to_cut)
            p_to_cut.squadra = None
            p_to_cut.contract = None

            # Send to free agents pool or retirement
            if torneo:
                if p_to_cut.ovr >= 72:
                    try:
                        from core.news_generator import add_news
                        add_news(
                            category="signings",
                            title=f"CUT: {team.nome} waive {p_to_cut.nome}",
                            excerpt=f"To make room after a trade, the {team.nome} waive {p_to_cut.nome} ({p_to_cut.ovr} OVR), who enters the free agent market.",
                            teams=[team.nome],
                            season=torneo.season_number
                        )
                    except Exception:
                        main_log.warning("Could not publish the waiver news for %s", p_to_cut.nome, exc_info=True)
                if p_to_cut.eta > 34 and p_to_cut.ovr < 76:
                    from core.models import add_retired_player
                    add_retired_player(torneo, p_to_cut)
                    cut_messages.append(f"CUT/RETIREMENT: {team.nome} cut {p_to_cut.nome} ({p_to_cut.ovr} OVR), who retires.")
                else:
                    if hasattr(torneo, 'free_agents_pool'):
                        torneo.free_agents_pool.append(p_to_cut)
                    cut_messages.append(f"CUT: {team.nome} cut {p_to_cut.nome} ({p_to_cut.ovr} OVR) to make roster room.")
            else:
                cut_messages.append(f"CUT: {team.nome} cut {p_to_cut.nome} ({p_to_cut.ovr} OVR).")

        return cut_messages

    @staticmethod
    def _check_trade_cooldown(players: List['Giocatore']) -> Optional[str]:
        """Returns a rejection reason if a player was traded too recently (prevents veteran-dump loops)."""
        for p in players:
            if getattr(p, 'giorni_cooldown_scambio', 0) > 0:
                return f"{p.nome} cannot be traded yet: trade cooldown active ({p.giorni_cooldown_scambio} games remaining)."
        return None

    @staticmethod
    def _check_pick_not_drafted(pick_keys: List[str]) -> Optional[str]:
        """Returns a rejection reason if a traded current-year pick was already used in the running draft."""
        active_draft = runtime_state.get_active_draft()
        if not active_draft or getattr(active_draft, 'pick_corrente', 0) <= 0:
            return None
        draft_order = active_draft.get_draft_state().get("ordine", [])
        for pk in pick_keys:
            if not pk.startswith("1:"):
                continue
            lookup_key = pk.split(":", 1)[1]
            for item in draft_order:
                item_key = f"R{item['round']}-{item['original_owner']}"
                if item_key == lookup_key and item['pick_index'] < active_draft.pick_corrente:
                    return f"Pick {lookup_key} has already been used in the Draft and can no longer be traded."
        return None

    @staticmethod
    def _check_roster_after_trade(team, outgoing: List['Giocatore'], incoming_count: int) -> Optional[str]:
        """Roster size rules after a trade: enough bodies, and enough waivable players to get under the limit."""
        limit = CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT
        net_change = incoming_count - len(outgoing)
        needed_cuts = len(team.roster) + net_change - limit
        if needed_cuts > 0:
            waivable = [p for p in team.roster if p not in outgoing and not getattr(p, 'is_untouchable', False)]
            if len(waivable) < needed_cuts:
                return f"{team.nome} would exceed the roster limit ({limit}) by {needed_cuts} and doesn't have enough waivable players to cut."
        if len(team.roster) + net_change < CONFIG.OFFSEASON.TRADE_ROSTER_MIN_SIZE:
            return f"{team.nome} roster too small after trade ({len(team.roster)} + {net_change})"
        return None

    @staticmethod
    def _check_salary_match(team, incoming: List['Giocatore'], outgoing: List['Giocatore']) -> Tuple[bool, str]:
        """Delegates to the team's CBA check (which itself honors the no-cap mode)."""
        salary_in = sum(p.contract.salario_annuale for p in incoming)
        salary_out = sum(p.contract.salario_annuale for p in outgoing)
        return team.check_trade_salary_match(salary_in, salary_out)

    @staticmethod
    def _find_contractless(players: List['Giocatore']) -> Optional[str]:
        """Returns a rejection reason for a player that has no contract (cannot be priced or moved)."""
        for p in players:
            if getattr(p, 'contract', None) is None:
                return f"{p.nome} has no contract and cannot be traded."
        return None

    @staticmethod
    def validate_trade(team_a: 'Squadra', team_b: 'Squadra',
                       assets_a_gives: List, assets_b_gives: List,
                       torneo=None) -> Tuple[bool, str]:

        from core.models import Giocatore

        # 1. Split players and picks
        players_a = [a for a in assets_a_gives if isinstance(a, Giocatore)]
        players_b = [a for a in assets_b_gives if isinstance(a, Giocatore)]
        pick_keys_a = [a for a in assets_a_gives if isinstance(a, str)]
        pick_keys_b = [a for a in assets_b_gives if isinstance(a, str)]

        reason = (TradeValidator._find_contractless(players_a + players_b)
                  or TradeValidator._check_trade_cooldown(players_a + players_b)
                  or TradeValidator._check_pick_not_drafted(pick_keys_a + pick_keys_b))
        if reason:
            return False, reason

        # 2. Salary rules (the team method returns True in no-cap mode)
        cba = getattr(torneo, 'cba_mode', 'realistic') if torneo else 'realistic'
        if cba != 'no_cap':
            valid_a, reason_a = TradeValidator._check_salary_match(team_a, players_b, players_a)
            if not valid_a:
                return False, f"{team_a.nome} cannot afford trade: {reason_a}"
            valid_b, reason_b = TradeValidator._check_salary_match(team_b, players_a, players_b)
            if not valid_b:
                return False, f"{team_b.nome} cannot afford trade: {reason_b}"

        # 3. Roster limits
        reason = (TradeValidator._check_roster_after_trade(team_a, players_a, len(players_b))
                  or TradeValidator._check_roster_after_trade(team_b, players_b, len(players_a)))
        if reason:
            return False, reason

        # 4. Stepien Rule
        if torneo:
            for team, pick_keys in ((team_a, pick_keys_a), (team_b, pick_keys_b)):
                r1_picks = [pk for pk in pick_keys if "R1" in pk]
                if r1_picks:
                    valid_s, reason_s = TradeValidator.check_stepien_rule(torneo, team.nome, r1_picks)
                    if not valid_s:
                        return False, reason_s

        return True, "Trade Valid"

    @staticmethod
    def validate_3_team_trade(team_a: 'Squadra', team_b: 'Squadra', team_c: 'Squadra',
                              trade_data: dict, torneo=None) -> Tuple[bool, str, dict]:
        """
        Validates a 3-team triangular trade.
        trade_data format:
        {
            "team_a": {"gives_to_b": [assets...], "gives_to_c": [assets...]},
            "team_b": {"gives_to_a": [assets...], "gives_to_c": [assets...]},
            "team_c": {"gives_to_a": [assets...], "gives_to_b": [assets...]}
        }
        Returns: (is_valid, validation_message, team_status_dict)
        """
        from core.models import Giocatore

        teams = {"team_a": team_a, "team_b": team_b, "team_c": team_c}
        status = {}

        incoming_players = {"team_a": [], "team_b": [], "team_c": []}
        outgoing_players = {"team_a": [], "team_b": [], "team_c": []}
        outgoing_picks = {"team_a": [], "team_b": [], "team_c": []}

        for t_key, t_obj in teams.items():
            t_data = trade_data.get(t_key, {})
            for dest_key, assets in t_data.items():
                dest_team_key = "team_" + dest_key.split("_")[-1] if dest_key.startswith("gives_to_") else dest_key
                for a in assets:
                    if isinstance(a, Giocatore):
                        outgoing_players[t_key].append(a)
                        if dest_team_key in incoming_players:
                            incoming_players[dest_team_key].append(a)
                    elif isinstance(a, str):
                        if ":" in a:
                            outgoing_picks[t_key].append(a)
                        else:
                            found_p = next((p for p in t_obj.roster if p.nome.lower() == a.lower()), None)
                            if found_p:
                                outgoing_players[t_key].append(found_p)
                                if dest_team_key in incoming_players:
                                    incoming_players[dest_team_key].append(found_p)
                            else:
                                outgoing_picks[t_key].append(a)

        all_outgoing = sum(outgoing_players.values(), [])
        all_picks = sum(outgoing_picks.values(), [])
        reason = (TradeValidator._find_contractless(all_outgoing)
                  or TradeValidator._check_trade_cooldown(all_outgoing)
                  or TradeValidator._check_pick_not_drafted(all_picks))
        if reason:
            return False, reason, {}

        cba = getattr(torneo, 'cba_mode', 'realistic') if torneo else 'realistic'

        # Verify each team
        for t_key, t_obj in teams.items():
            out_p = outgoing_players[t_key]
            in_p = incoming_players[t_key]
            out_pk = outgoing_picks[t_key]

            if cba != 'no_cap':
                valid_sal, reason_sal = TradeValidator._check_salary_match(t_obj, in_p, out_p)
                if not valid_sal:
                    return False, f"{t_obj.nome} CBA salary violation: {reason_sal}", status

            reason = TradeValidator._check_roster_after_trade(t_obj, out_p, len(in_p))
            if reason:
                return False, reason, status

            # Stepien Rule
            if torneo:
                r1_picks = [pk for pk in out_pk if "R1" in pk]
                if r1_picks:
                    valid_s, reason_s = TradeValidator.check_stepien_rule(torneo, t_obj.nome, r1_picks)
                    if not valid_s:
                        return False, reason_s, status

            salary_in = sum(p.contract.salario_annuale for p in in_p)
            salary_out = sum(p.contract.salario_annuale for p in out_p)
            status[t_key] = {
                "team_name": t_obj.nome,
                "salary_in": round(salary_in, 1),
                "salary_out": round(salary_out, 1),
                "net_salary": round(salary_in - salary_out, 1),
                "players_in": [p.nome for p in in_p],
                "players_out": [p.nome for p in out_p]
            }

        return True, "3-team trade is CBA compliant!", status
