"""
Contract Extensions Module (Aligned with Free Agency System v12.0)

Handles early contract extensions for players in their contract year before full Free Agency:
- Full alignment with FA valuation, salary cap scaling, and awards bonuses
- Unified acceptance & willingness scoring (Superteams, Contenders, Starter opportunity, Morale, Bird/Loyalty +20)
- Strict low-ball offer rejections and financial option trade-offs (PO 10% discount, TO 10% premium)
- Owner spending profile & luxury tax hard apron respect
- Automatic flight-risk tagging for stars who refuse extensions
"""
import logging
import random
from typing import List, Dict, Tuple, TYPE_CHECKING
from core.config import CONFIG, owner_spending_tier
from core.front_office import contracts
from core.front_office import trade_requests
from core.news_generator import add_news

if TYPE_CHECKING:
    from core.models import Squadra, Giocatore
    from tournament.season_manager import Tournament

main_log = logging.getLogger('main_sim')


class ContractExtensions:
    """
    Handles mid-season contract extensions for both CPU and User teams.
    """
    
    def __init__(self, torneo: 'Tournament', squadre: List['Squadra']):
        self.torneo = torneo
        self.squadre = squadre
        self.log = []
        self.outcomes: List[Dict] = []   # {player, team, ovr, outcome: extended | refused | not_offered | walks}

    @property
    def _min_salary(self) -> float:
        return getattr(self.torneo, 'min_salary', 3.5)

    def process_extensions(self) -> List[str]:
        """Main method to check all AI teams and eligible expiring players for extensions."""
        count = 0
        main_log.info("\n--- START OF THE MID-SEASON CONTRACT EXTENSION WINDOW ---")
        self.mark_walkers()

        for squadra in self.squadre:
            # Skip user's team from automated AI extension decisions
            if hasattr(self.torneo, 'squadra_giocatore') and squadra == self.torneo.squadra_giocatore:
                continue

            eligible_players = [
                p for p in squadra.roster
                if p.contract and p.contract.anni_rimanenti == 1 and p.ovr >= 72 and not getattr(p, 'walks_away', '')
            ]
            
            # Sort eligible players by OVR descending (prioritize stars)
            eligible_players.sort(key=lambda p: p.ovr, reverse=True)
            
            for player in eligible_players:
                if self._attempt_extension(squadra, player):
                    count += 1
                    
        main_log.info(f"--- EXTENSION WINDOW COMPLETED: {count} renewals made ---")
        return self.log

    def _outcome(self, team, player, outcome: str) -> None:
        if not hasattr(self, 'outcomes'):
            self.outcomes = []
        self.outcomes.append({"player": player.nome, "team": team.nome, "ovr": int(player.ovr), "outcome": outcome})

    def mark_walkers(self) -> List[str]:
        """Players in their contract year who will not re-sign (contracts.walk_reason), on every team (the user's
        too): flagged `walks_away`, no longer untouchable (his team may trade him at the deadline: he wants out),
        a flight risk, one news item each. Returns their names."""
        walkers = []
        for squadra in self.squadre:
            expiring = [p for p in squadra.roster if p.contract and p.contract.anni_rimanenti == 1]
            if not expiring:
                continue
            ctx = contracts.context_for(self.torneo, squadra)
            for p in expiring:
                reason = contracts.walk_reason(p, squadra, ctx)
                p.walks_away = reason
                if not reason:
                    continue
                p.is_untouchable = False
                p.is_flight_risk = True
                walkers.append(p.nome)
                self._outcome(squadra, p, "walks")
                main_log.info(f"WALKS AWAY: {p.nome} ({p.ovr}) will not re-sign with the {squadra.nome}: {reason}.")
                fed_up = reason == contracts.FED_UP
                if fed_up and int(p.ovr) < ctx.era.rotation:
                    continue   # a fed-up bench player just leaves in the summer: no story
                add_news(
                    category="signings",
                    title=f"🚪 {p.nome} will not re-sign with the {squadra.nome}",
                    excerpt=(f"{p.nome} (OVR {p.ovr}) has told the {squadra.nome} he will not negotiate a new deal "
                             f"({reason}). He becomes a free agent in the summer unless he is traded first."),
                    teams=[squadra.nome], is_breaking=not fed_up, season=getattr(self.torneo, 'season_number', 0))
        return walkers

    def _max_contract(self) -> float:
        """The max contract: 40% of the era's cap before 2023, 35% after."""
        raw_cap = getattr(self.torneo, 'salary_cap', 155.0) if self.torneo else 155.0
        anno = getattr(self.torneo, 'anno_corrente', 2025) if self.torneo else 2025
        is_no_cap = (self.torneo and getattr(self.torneo, 'cba_mode', '') == 'no_cap') or (raw_cap >= 9000.0)
        cap = CONFIG.ECONOMY.get_cap_for_year(anno, raw_cap, is_no_cap)
        return cap * (0.40 if anno < 2023 else 0.35)

    def compute_player_market_request(self, player: 'Giocatore', option_type: str = "None") -> float:
        """
        Computes the target salary request of a player based on deterministic FA tiering,
        era cap scaling, awards bonuses, and option trade-offs.
        """
        raw_cap = getattr(self.torneo, 'salary_cap', 155.0) if self.torneo else 155.0
        anno = getattr(self.torneo, 'anno_corrente', 2025) if self.torneo else 2025
        is_no_cap = (self.torneo and getattr(self.torneo, 'cba_mode', '') == 'no_cap') or (raw_cap >= 9000.0)

        cap = CONFIG.ECONOMY.get_cap_for_year(anno, raw_cap, is_no_cap)
        is_historical = (anno < 2023)
        negotiation_ovr = getattr(player, 'effective_ovr', player.ovr)

        # Realistic NBA salary tiers calibrated by percentage of the Salary Cap
        if is_historical:
            # Classic Era / Pre-Apron (2002-2022)
            if negotiation_ovr >= 93:
                tier_pct = (0.32, 0.38)   # Franchise Supermax
            elif negotiation_ovr >= 88:
                tier_pct = (0.26, 0.32)   # All-Star Max
            elif negotiation_ovr >= 84:
                tier_pct = (0.20, 0.26)   # All-Star / High-End Starter (20% - 26%)
            elif negotiation_ovr >= 80:
                tier_pct = (0.15, 0.20)   # Solid Starter (15% - 20%)
            elif negotiation_ovr >= 76:
                tier_pct = (0.09, 0.14)   # 6th Man / Key Rotation (9% - 14%)
            elif negotiation_ovr >= 72:
                tier_pct = (0.05, 0.085)  # Rotation Bench (5.0% - 8.5%)
            elif negotiation_ovr >= 68:
                tier_pct = (0.028, 0.048) # Deep Bench (2.8% - 4.8%)
            else:
                tier_pct = (0.015, 0.026) # Salary Minimum
        else:
            # Modern Era (2023+ CBA with Aprons)
            if negotiation_ovr >= 93:
                tier_pct = (0.30, 0.35)   # Modern supermax (30% - 35%)
            elif negotiation_ovr >= 88:
                tier_pct = (0.25, 0.30)   # Max Player (25% - 30%)
            elif negotiation_ovr >= 84:
                tier_pct = (0.20, 0.25)   # Star / Borderline All-Star (20% - 25%)
            elif negotiation_ovr >= 80:
                tier_pct = (0.15, 0.20)   # Starter (15% - 20%)
            elif negotiation_ovr >= 76:
                tier_pct = (0.09, 0.14)   # 6th Man / Key Rotation (9% - 14%)
            elif negotiation_ovr >= 72:
                tier_pct = (0.05, 0.085)  # Bench (5.0% - 8.5%)
            elif negotiation_ovr >= 68:
                tier_pct = (0.028, 0.048) # Deep Bench (2.8% - 4.8%)
            else:
                tier_pct = (0.015, 0.024) # Deep Bench / Minimo

        min_pct, max_pct = tier_pct
        
        # Continuous grading within the OVR tier (avoids identical contracts by default)
        tier_bounds = {
            93: (93, 99),
            88: (88, 92),
            84: (84, 87),
            80: (80, 83),
            76: (76, 79),
            72: (72, 75),
            68: (68, 71),
            0: (50, 67)
        }
        target_pct = min_pct + (max_pct - min_pct) * 0.5
        for min_ovr, (b_low, b_high) in tier_bounds.items():
            if negotiation_ovr >= min_ovr:
                prog = (negotiation_ovr - b_low) / max(1, (b_high - b_low))
                target_pct = min_pct + (max_pct - min_pct) * (0.25 + 0.50 * prog + random.uniform(-0.06, 0.06))
                target_pct = max(min_pct, min(max_pct, target_pct))
                break

        salario_base = cap * target_pct

        if player.eta <= 24 and player.potenziale > player.ovr + 5:
            salario_base *= 1.05
        elif player.eta >= 34 and player.ovr < 85:
            salario_base *= 0.80

        # Market elasticity if the league is under cap strain
        teams = getattr(self.torneo, 'squadre', []) if self.torneo else []
        if teams and len(teams) >= 20 and not is_no_cap:
            over_cap_count = sum(1 for s in teams if getattr(s, 'salary_cap_space', 0.0) <= 0.5)
            if (over_cap_count / len(teams)) >= 0.70 and negotiation_ovr < 89:
                salario_base *= 0.88

        # Awards bonus
        cfg_eco = CONFIG.ECONOMY
        careers_data = getattr(self.torneo, '_careers_cache', {})
        player_id = player.nome.replace(" ", "-").lower()
        player_career = careers_data.get(player_id, [])
        player_awards = []
        if player_career:
            try:
                last_season_data = max(player_career, key=lambda s: s.get('stagione', 0))
                if last_season_data.get('stagione') == self.torneo.season_number:
                    player_awards = last_season_data.get("premi", [])
            except Exception:
                main_log.warning("Ignored error in compute_player_market_request()", exc_info=True)
                
        bonus_totale = sum(cfg_eco.AWARD_SALARY_BONUSES.get(award, 0.0) for award in player_awards)
        bonus_applicato = min(3.5, bonus_totale * 0.35)
        salario_base += bonus_applicato

        # Financial trade-off for contract option types
        if option_type == "PO":
            salario_base *= 0.90  # Player grants 10% discount for player option leverage
        elif option_type == "TO":
            salario_base *= 1.10  # Player demands 10% premium for team option risk

        min_allowed = self._min_salary if self._min_salary < 9000 else round(1.5 * (cap / 155.0), 1)
        salario_finale = max(min_allowed, salario_base)
        salario_finale = min(self._max_contract(), salario_finale)
        return round(salario_finale, 1)

    def calculate_extension_score(self, player: 'Giocatore', team: 'Squadra', 
                                   offer_salary: float, option_type: str = "None",
                                   raise_pct: float = 0.05) -> Tuple[float, str]:
        """
        Full FA-aligned acceptance scoring system for contract extensions.
        Returns (score, feedback_reason).
        """
        if getattr(player, 'walks_away', ''):
            return 0.0, f"{player.nome} will not negotiate: {player.walks_away}."
        valore_mercato = self.compute_player_market_request(player, option_type)
        ratio_offerta = offer_salary / max(1.0, valore_mercato)
        
        goal_squadra = self.torneo._determina_stato_squadra(team)
        superstars = [p for p in team.roster if p.ovr >= 87 and p.nome != player.nome]
        stars = [p for p in team.roster if 82 <= p.ovr < 87 and p.nome != player.nome]
        is_superteam = (len(superstars) >= 2) or (len(superstars) >= 1 and len(stars) >= 2)
        has_star_partner = (len(superstars) >= 1) or (len(stars) >= 2)
        is_ring_chase = (is_superteam or goal_squadra in ["Contender", "Defending Champion"])

        # Hard block: Instant rejection for low-ball offers unless veteran ring chasing
        if not (is_ring_chase and player.eta >= 29):
            if player.eta < 33:
                if player.ovr >= 84 and ratio_offerta < 0.75:
                    return 0.0, f"Unacceptable low-ball offer: {player.nome} categorically refuses an amount below 75% of his value (${valore_mercato:.1f}M)."
                elif player.ovr >= 76 and ratio_offerta < 0.65:
                    return 0.0, f"Inadequate offer: {player.nome} considers the offer (${offer_salary:.1f}M) insulting for his status (${valore_mercato:.1f}M)."
                elif player.ovr >= 72 and ratio_offerta < 0.50:
                    return 0.0, f"Offer too low: {player.nome} does not intend to sign for less than 50% of his market value."

        # Base score
        punteggio = 50.0

        # 1. Economic Factor
        punteggio += (ratio_offerta - 1.0) * 60.0
        if ratio_offerta >= 1.20:
            punteggio += min(30.0, (ratio_offerta - 1.0) * 35.0)

        # 2. Raise Percentage Factor (CBA 5% is standard, 8% is Bird Max bonus, 0% or negative is penalized)
        punteggio += (raise_pct - 0.05) * 150.0

        # 2. Loyalty to his team: earned with seasons and morale (core/front_office/contracts.py)
        punteggio += contracts.loyalty(player, team)

        # 3. Morale Factor
        punteggio += (player.morale - 70) * 0.4

        # 4. Superteam & Star Partnership Allure
        if is_superteam:
            punteggio += 30.0 if (player.ovr >= 80 or player.eta >= 29) else 15.0
        elif has_star_partner:
            punteggio += 15.0 if (player.ovr >= 80 or player.eta >= 28) else 8.0

        # 5. Role & Starting Opportunity
        same_role_players = [p for p in team.roster if p.ruolo == player.ruolo and p.nome != player.nome]
        best_same_role = max([p.ovr for p in same_role_players], default=0)
        
        if (not same_role_players or best_same_role <= 76) and player.ovr >= 77:
            punteggio += 18.0
        elif best_same_role >= 87 and player.ovr >= 80 and player.eta < 34:
            punteggio -= 28.0

        # 6. Team Success Factor
        is_star = player.ovr >= 85
        win_mult = 2.5 if is_star else 1.0
        
        if goal_squadra == "Defending Champion":
            punteggio += 25 * win_mult
        elif goal_squadra == "Contender":
            punteggio += 15 * win_mult
        elif goal_squadra == "Playoff Team":
            punteggio += 8
        elif goal_squadra == "Rising Star":
            punteggio += 5
        elif goal_squadra == "Rebuilding":
            young_prospects = [p for p in team.roster if p.eta < 24 and p.potenziale >= 84]
            has_young_future = len(young_prospects) >= 2 or any(p.eta < 23 and p.potenziale >= 87 for p in team.roster)
            penalty = 3 if has_young_future else 15
            punteggio -= penalty * win_mult
        elif goal_squadra == "Mediocre":
            punteggio -= 10 * win_mult

        # 7. Ambition / Age Factor
        if player.eta < 28 and player.ovr >= 85:
            punteggio -= 10
        elif player.eta > 32:
            punteggio += 10

        punteggio = max(0.0, min(100.0, punteggio))

        # Determine descriptive feedback string
        if punteggio >= 70.0:
            reason = f"{player.nome} is excited about the project and accepts the renewal offer with pride."
        elif punteggio >= 55.0:
            reason = f"{player.nome} finds the financial deal satisfactory and chooses stability with the {team.nome}."
        elif punteggio < 35.0:
            reason = f"{player.nome} is unhappy with the technical and financial situation and intends to test the market."
        else:
            reason = f"{player.nome} prefers to explore Free Agency options to maximize his opportunities."

        return punteggio, reason

    def evaluate_realtime_offer(self, player: 'Giocatore', team: 'Squadra', 
                                offer_salary: float, years: int, 
                                option_type: str = "None", mode: str = "extension",
                                raise_pct: float = 0.05) -> Dict:
        """
        Real-time evaluation of the offer for the new Live Interest Meter.
        Returns the exact approval (0-100), tier, agent reaction,
        factor breakdown and a customized scaled contract projection (raise_pct).
        """
        valore_mercato = self.compute_player_market_request(player, option_type)
        ratio_offerta = offer_salary / max(1.0, valore_mercato)
        goal_squadra = self.torneo._determina_stato_squadra(team)
        
        factors = []
        
        # 1. Economic Factor
        econ_impact = (ratio_offerta - 1.0) * 60.0
        if ratio_offerta >= 1.20:
            econ_impact += min(30.0, (ratio_offerta - 1.0) * 35.0)
            
        diff_pct = (ratio_offerta - 1.0) * 100
        factors.append({
            "name": "economic",
            "label": "Salary Offer",
            "value": f"${offer_salary:.1f}M vs Value ${valore_mercato:.1f}M ({diff_pct:+.0f}%)",
            "score_impact": round(econ_impact, 1),
            "type": "positive" if ratio_offerta >= 0.98 else ("neutral" if ratio_offerta >= 0.88 else "negative")
        })

        # 2. Loyalty (extension or his own team): earned with seasons and morale
        own = mode == "extension" or getattr(player, 'squadra', None) == team
        loyalty_impact = contracts.loyalty(player, team) if own else 0.0
        if loyalty_impact > 0:
            factors.append({
                "name": "loyalty",
                "label": f"Loyalty ({getattr(player, 'anni_nella_squadra', 0)} yrs, morale {player.morale})",
                "value": f"Seasons with the franchise and morale (+{loyalty_impact:.0f} pts)",
                "score_impact": loyalty_impact,
                "type": "positive"
            })
            
        # 3. Team Status / Contender
        superstars = [p for p in team.roster if p.ovr >= 87 and p.nome != player.nome]
        stars = [p for p in team.roster if 82 <= p.ovr < 87 and p.nome != player.nome]
        is_superteam = (len(superstars) >= 2) or (len(superstars) >= 1 and len(stars) >= 2)
        
        team_impact = 0.0
        if goal_squadra == "Defending Champion":
            team_impact = 25.0
        elif goal_squadra == "Contender" or is_superteam:
            team_impact = 18.0
        elif goal_squadra == "Playoff Team":
            team_impact = 8.0
        elif goal_squadra == "Rebuilding":
            team_impact = -12.0
            
        factors.append({
            "name": "contender",
            "label": "Team Competitiveness",
            "value": f"{team.nome} ({goal_squadra})",
            "score_impact": team_impact,
            "type": "positive" if team_impact > 0 else ("neutral" if team_impact == 0 else "negative")
        })

        # 4. Role & Minutes Space
        same_role_players = [p for p in team.roster if p.ruolo == player.ruolo and p.nome != player.nome]
        best_same_role = max([p.ovr for p in same_role_players], default=0)
        role_impact = 0.0
        role_desc = "Guaranteed Starter"
        if best_same_role <= 76 and player.ovr >= 77:
            role_impact = 18.0
            role_desc = "Undisputed Starter (+18 pts)"
        elif best_same_role >= 86 and player.ovr >= 80 and player.eta < 34:
            role_impact = -25.0
            role_desc = "Strong Competition at the Position (-25 pts)"
            
        factors.append({
            "name": "role",
            "label": "Space & Technical Role",
            "value": role_desc,
            "score_impact": role_impact,
            "type": "positive" if role_impact > 0 else ("neutral" if role_impact == 0 else "negative")
        })

        # 5. Contract Duration & Option
        option_impact = 0.0
        if option_type == "PO":
            option_impact = 10.0
            factors.append({
                "name": "option",
                "label": "Player Option Clause",
                "value": "Welcome control over the future (+10 pts)",
                "score_impact": option_impact,
                "type": "positive"
            })
        elif option_type == "TO":
            option_impact = -12.0
            factors.append({
                "name": "option",
                "label": "Team Option Clause",
                "value": "Unwelcome contract risk (-12 pts)",
                "score_impact": option_impact,
                "type": "negative"
            })

        # Duration logic
        years_impact = 0.0
        if years >= 4 and player.eta <= 27:
            years_impact = 8.0
        elif years == 1 and player.eta < 32 and ratio_offerta < 1.15:
            years_impact = -10.0
            
        if years_impact != 0:
            factors.append({
                "name": "duration",
                "label": "Contract Length",
                "value": f"{years} guaranteed years",
                "score_impact": years_impact,
                "type": "positive" if years_impact > 0 else "negative"
            })

        # 6. Raise Percentage Factor (Incremento salariale annuo)
        raise_impact = (raise_pct - 0.05) * 150.0
        raise_label = f"{raise_pct * 100:+.0f}% per year"
        if raise_pct >= 0.08:
            raise_label += " (Bird Max)"
        elif abs(raise_pct - 0.05) < 0.001:
            raise_label += " (Standard CBA)"
        elif abs(raise_pct) < 0.001:
            raise_label += " (Flat Salary)"
        elif raise_pct < 0.0:
            raise_label += " (Decrescente / Front-Loaded)"

        factors.append({
            "name": "raise_pct",
            "label": "Salary Raises",
            "value": raise_label,
            "score_impact": round(raise_impact, 1),
            "type": "positive" if raise_pct > 0.05 else ("neutral" if raise_pct >= 0.0 else "negative")
        })

        # Check hard low-ball rejections
        is_ring_chase = (is_superteam or goal_squadra in ["Contender", "Defending Champion"]) and player.eta >= 29
        is_hard_rejection = False
        rejection_reason = ""
        
        if not is_ring_chase and player.eta < 33:
            if player.ovr >= 84 and ratio_offerta < 0.75:
                is_hard_rejection = True
                rejection_reason = f"Unacceptable offer: {player.nome} and his agent refuse amounts below 75% of market value (${valore_mercato:.1f}M)."
            elif player.ovr >= 76 and ratio_offerta < 0.65:
                is_hard_rejection = True
                rejection_reason = f"Inadequate offer: {player.nome}'s agent considers the offer (${offer_salary:.1f}M) insulting for his status."
            elif player.ovr >= 72 and ratio_offerta < 0.50:
                is_hard_rejection = True
                rejection_reason = f"Offer too low: {player.nome} does not intend to sign for less than half of his value."

        walks = getattr(player, 'walks_away', '')
        if walks:
            punteggio = 0.0
            tier = "Won't negotiate"
            agent_reaction = f"{player.nome} will not negotiate: {walks}."
            is_hard_rejection = True
        elif is_hard_rejection:
            punteggio = 5.0
            tier = "Rejected"
            agent_reaction = rejection_reason
        else:
            base_score = 50.0
            punteggio = base_score + econ_impact + loyalty_impact + team_impact + role_impact + option_impact + years_impact + raise_impact
            punteggio = max(0.0, min(100.0, punteggio))
            
            if punteggio >= 75.0:
                tier = "Very High"
                agent_reaction = f"The agent confirms: {player.nome} is thrilled with the proposal and ready to sign right away with the {team.nome}!"
            elif punteggio >= 60.0:
                tier = "High"
                agent_reaction = f"{player.nome} finds the financial and technical deal very advantageous. Excellent chances of closing."
            elif punteggio >= 45.0:
                tier = "Medium"
                agent_reaction = f"Talks are open. The agent asks for a small financial tweak (around ${valore_mercato:.1f}M) or a Player Option to guarantee the signing."
            elif punteggio >= 25.0:
                tier = "Low"
                agent_reaction = f"{player.nome} is skeptical. The offer is below expectations and he prefers to evaluate other opportunities."
            else:
                tier = "Rejected"
                agent_reaction = f"{player.nome} prefers to test the summer market as a Free Agent rather than accept these terms."

        # Projected escalating salaries
        projected_salaries = []
        cur_sal = offer_salary
        for _ in range(years):
            projected_salaries.append(round(cur_sal, 2))
            cur_sal *= (1.0 + raise_pct)
        total_value = round(sum(projected_salaries), 2)

        return {
            "player_name": player.nome,
            "team_name": team.nome,
            "offer_salary": offer_salary,
            "years": years,
            "option_type": option_type,
            "raise_pct": round(raise_pct, 3),
            "market_value": round(valore_mercato, 2),
            "ratio_offer": round(ratio_offerta, 2),
            "willingness_score": round(punteggio, 1),
            "tier": tier,
            "agent_reaction": agent_reaction,
            "factors": factors,
            "projected_salaries": projected_salaries,
            "total_value": total_value,
            "can_accept": punteggio >= 55.0 and not is_hard_rejection
        }

    def _attempt_extension(self, team: 'Squadra', player: 'Giocatore') -> bool:
        # 1. The GM's decision, by its plan (contracts.renewal_offer), then the owner's money
        ctx = contracts.context_for(self.torneo, team)
        renewal = contracts.renewal_offer(player, ctx)

        max_spesa = self.torneo.second_apron + 20.0
        tier = owner_spending_tier(team.personalita_proprietario)
        if tier == "low":
            max_spesa = self.torneo.luxury_tax_threshold + CONFIG.ECONOMY.LOW_OWNER_OVER_TAX_SHARE * self.torneo.salary_cap
        elif tier == "mid":
            max_spesa = self.torneo.first_apron + 10.0

        market_val = self.compute_player_market_request(player)
        star_on_a_winner = int(player.ovr) >= ctx.era.star and ctx.plan in ("CONTENDER", "PLAYOFF")
        if renewal is not None and (team.payroll + market_val) > max_spesa and not star_on_a_winner:
            renewal = None   # over budget: the owner forbids it (a winning team still pays its star)
        wants_to_renew = renewal is not None

        if not wants_to_renew:
            main_log.info(f"Extension NOT Offered: {team.nome} lets {player.nome} test Free Agency.")
            self._outcome(team, player, "not_offered")
            if player.ovr >= 80:
                add_news(
                    category="signings",
                    title=f"💔 {team.nome} let {player.nome} go",
                    excerpt=f"The {team.nome} front office has decided not to offer a preventive contract extension to {player.nome}. The player will test Free Agency at the end of the year.",
                    teams=[team.nome],
                    season=self.torneo.season_number
                )
            return False

        # 2. Options selection
        years = renewal.years
        option_type = "None"
        if player.ovr >= 90 and years >= 3 and random.random() < 0.35:
            option_type = "PO"
        elif player.eta >= 34 or player.ovr < 74:
            option_type = "TO"

        offer_salary = round(min(market_val * renewal.salary_mult, self._max_contract()), 1)   # never over the max

        # 3. Acceptance Score
        score, reason = self.calculate_extension_score(player, team, offer_salary, option_type)
        
        # Acceptance Threshold for extensions (around 52.0 given the +20 loyalty bonus)
        acceptance_threshold = 52.0
        if player.ovr >= 88:
            acceptance_threshold += 4.0

        if score < acceptance_threshold:
            # Refused! Player becomes flight risk
            player.is_flight_risk = True
            self._outcome(team, player, "refused")
            main_log.info(f"Extension Refused: {player.nome} wants to test Free Agency (Score: {score:.1f}). Reason: {reason}")
            is_star = player.ovr >= 83
            add_news(
                category="signings",
                title=f"🚨 MARKET: {player.nome} refuses the renewal!" if is_star else f"{player.nome} will test Free Agency",
                excerpt=f"No preventive extension deal between the {team.nome} and {player.nome} (OVR {player.ovr}). The player prefers to test the market as a free agent at the end of the season.",
                teams=[team.nome],
                is_breaking=is_star,
                season=self.torneo.season_number
            )
            return False

        # 4. Sign the Extension!
        player_opt = (option_type == "PO")
        team_opt = (option_type == "TO")
        
        # The year-by-year salaries carry the new deal (Contract.__post_init__ reads salari_per_anno[0] on load, and
        # the yearly aging pops it): the years left at the current salary, then the extension with standard raises.
        c = player.contract
        current = list((getattr(c, "salari_per_anno", None) or [])[:c.anni_rimanenti])
        while len(current) < c.anni_rimanenti:
            current.append(round(c.salario_annuale, 2))
        cur = round(offer_salary, 1)
        for _ in range(years):
            current.append(round(cur, 2))
            cur *= (1.0 + CONFIG.CONTRACTS.EXTENSION_RAISE_PCT)
        c.salari_per_anno = current
        c.anni_rimanenti = len(current)
        c.salario_annuale = round(current[0], 2)
        player.contract.player_option = player_opt
        player.contract.team_option = team_opt
        player.is_flight_risk = False
        player.walks_away = ""
        trade_requests.clear_request(player)   # he signed on: the request is over
        player.morale = min(100, player.morale + 5)
        
        opt_str = " [Player Opt]" if player_opt else (" [Team Opt]" if team_opt else "")
        msg = f"EXTENSION: {team.nome} signs {player.nome} ({player.ovr}) to {years}yr extension (${offer_salary:.1f}M/yr){opt_str}."
        self.log.append(msg)
        self._outcome(team, player, "extended")
        main_log.info(msg)
        
        is_star = player.ovr >= 83
        opt_label = " (Player Option)" if player_opt else (" (Team Option)" if team_opt else "")
        add_news(
            category="signings",
            title=f"✍️ EXTENSION: {player.nome} signs with the {team.nome}!" if is_star else f"{player.nome} extends with the {team.nome}",
            excerpt=f"The {team.nome} lock up their core: agreement reached with {player.nome} for a {years}-year contract extension at ${offer_salary:.1f}M per year{opt_label}.",
            teams=[team.nome],
            is_breaking=is_star,
            season=self.torneo.season_number
        )
        return True
