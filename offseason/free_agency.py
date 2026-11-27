"""
Free Agency Module (OPTIMIZED v12.0 - Stateful & Turn-Based)

Handles the NBA Free Agency process including:
- Stateful 12-day progression
- Restricted Free Agency (RFA) with matching prompt
- Unrestricted Free Agency (UFA)
- Mid-Level Exception (MLE) & Biannual Exception (BAE) signings
- Salary negotiations and willingness scoring
- Day 8+ AI roster cuts & upgrades (roster optimization)
- Last Resort forced signings on Day 12
"""
import random
import logging
from typing import List, Dict, Optional, TYPE_CHECKING, Tuple

from core.config import CONFIG, owner_spending_tier
from core.front_office.contracts import loyalty
from core.front_office import trade_requests
from core.models import Contract
from core.front_office.moves import record_signing

if TYPE_CHECKING:
    from core.models import Squadra, Giocatore
    from tournament.season_manager import Tournament

main_log = logging.getLogger('main_sim')


class FreeAgency:
    """
    Reworked stateful 12-day Free Agency negotiation system.
    Provides day-by-day progression endpoints for interactive UI,
    along with single-shot automated execution for CLI autoplays.
    """
    def __init__(self, torneo: 'Tournament', squadre: List['Squadra'], free_agents: List['Giocatore'], 
                 squadre_precedenti: Dict[str, 'Squadra'], squadra_giocatore: Optional['Squadra']):
        self.torneo = torneo
        self.unrestricted_free_agents = sorted(free_agents, key=lambda g: g.performance_scores.total, reverse=True)
        self.squadre = squadre
        self.squadre_precedenti = squadre_precedenti
        self.squadra_giocatore = squadra_giocatore
        self.log_fa = []
        self.market_desperation_factor = 1.0
        
        # --- STATEFUL TRACKERS ---
        self.current_day = 1
        self.user_offers = {}        # player_name -> {salary, years, is_mle, is_bae, is_min}
        self.ai_offers = {}          # player_name -> list of {team, salary, years, tool}
        self.signings_log = []       # list of transaction log strings
        self.signings = []           # the same signings as records for the page (who, where, contract, offers beaten)
        self.pending_rfa_match = None # None or {player, team, salary, years}
        self.night_moves = []        # tonight's raises, pull-outs and signings: {type, team, player, salary?, day}
        self.completed = False
        
        # --- OPTIMIZATION CACHES ---
        self._team_state_cache: Dict[str, str] = {}
        self._market_value_cache: Dict[str, float] = {}
        self._salary_request_cache: Dict[str, float] = {}
        self._role_needs_cache: Dict[str, Dict[str, bool]] = {}
        self._starter_cache: Dict[str, Dict[str, Optional['Giocatore']]] = {}
        self._role_rankings_cache: Dict[str, List[str]] = {}

    @property
    def _min_salary(self) -> float:
        """Dynamic minimum salary scaled by era cap ratio."""
        return getattr(self.torneo, 'min_salary', 3.5)

    def _build_caches(self):
        """Pre-computes all team and player values to avoid heavy redundant calculations."""
        main_log.info("FA OPTIMIZER: Pre-computing caches...")
        
        self._ensure_careers_cache()
        
        for squadra in self.squadre:
            self._team_state_cache[squadra.nome] = self.torneo._determina_stato_squadra(squadra)
        
        for player in self.unrestricted_free_agents:
            self._cache_player_values(player)
        
        all_roles = ['PG', 'SG', 'SF', 'PF', 'C']
        for squadra in self.squadre:
            self._role_needs_cache[squadra.nome] = {}
            self._starter_cache[squadra.nome] = {}
            for ruolo in all_roles:
                self._role_needs_cache[squadra.nome][ruolo] = squadra.ha_bisogno_di_ruolo(ruolo)
                self._starter_cache[squadra.nome][ruolo] = squadra.get_starter_at_position(ruolo)
            self._role_rankings_cache[squadra.nome] = squadra.analizza_roster_per_upgrade()
        
        main_log.info(f"FA OPTIMIZER: Cached {len(self._market_value_cache)} player values, {len(self._team_state_cache)} team states")

    def _ensure_careers_cache(self):
        """Loads player_careers.json once into tournament cache."""
        if not hasattr(self.torneo, '_careers_cache'):
            import json
            from core.save_manager import get_historical_file_path
            try:
                career_file = get_historical_file_path("player_careers.json")
                with open(career_file, 'r', encoding='utf-8') as f:
                    self.torneo._careers_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self.torneo._careers_cache = {}

    def _cache_player_values(self, player: 'Giocatore'):
        market_val = self._compute_market_value_deterministic(player)
        self._market_value_cache[player.nome] = market_val
        self._salary_request_cache[player.nome] = self._compute_salary_request_base(player, market_val)

    def _compute_market_value_deterministic(self, player: 'Giocatore') -> float:
        raw_cap = getattr(self.torneo, 'salary_cap', 155.0) if self.torneo else 155.0
        anno = getattr(self.torneo, 'anno_corrente', 2025) if self.torneo else 2025
        is_no_cap = (self.torneo and getattr(self.torneo, 'cba_mode', '') == 'no_cap') or (raw_cap >= 9000.0)

        cap = CONFIG.ECONOMY.get_cap_for_year(anno, raw_cap, is_no_cap)
        is_historical = (anno < 2023)
        negotiation_ovr = player.effective_ovr

        # Realistic NBA salary tiers calibrated by percentage of the Salary Cap
        if is_historical:
            # Classic Era / Pre-Apron (2002-2022)
            if negotiation_ovr >= 93:
                tier_pct = (0.32, 0.38)   # Franchise Supermax (Shaq, Duncan, Garnett, Kobe, LeBron)
            elif negotiation_ovr >= 88:
                tier_pct = (0.26, 0.32)   # All-Star Max (T-Mac, Iverson, Wade, Dirk, Durant, Harden)
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
        target_pct = random.uniform(min_pct, max_pct)
        for min_ovr, (b_low, b_high) in tier_bounds.items():
            if negotiation_ovr >= min_ovr:
                prog = (negotiation_ovr - b_low) / max(1, (b_high - b_low))
                target_pct = min_pct + (max_pct - min_pct) * (0.25 + 0.50 * prog + random.uniform(-0.10, 0.10))
                target_pct = max(min_pct, min(max_pct, target_pct))
                break

        salario_base = cap * target_pct

        if player.eta <= 24 and player.potenziale > player.ovr + 5:
            salario_base *= 1.05
        elif player.eta >= 34 and player.ovr < 85:
            salario_base *= 0.80

        # Market elasticity: if more than 70% of the league is above the Salary Cap
        teams = getattr(self.torneo, 'squadre', [])
        if teams and len(teams) >= 20 and not is_no_cap:
            over_cap_count = sum(1 for s in teams if getattr(s, 'salary_cap_space', 0.0) <= 0.5)
            if (over_cap_count / len(teams)) >= 0.70 and negotiation_ovr < 89:
                salario_base *= 0.88

        min_allowed = self._min_salary if self._min_salary < 9000 else round(1.5 * (cap / 155.0), 1)
        salario_finale = max(min_allowed, salario_base)
        salario_finale = min(cap * CONFIG.ECONOMY.MAX_CONTRACT_CAP_PCT, salario_finale)

        return round(salario_finale, 1)

    def _compute_salary_request_base(self, player: 'Giocatore', market_value: float) -> float:
        salario_base = market_value
        cfg_eco = CONFIG.ECONOMY

        player_awards = self._get_player_awards_cached(player.nome)
        bonus_totale = sum(cfg_eco.AWARD_SALARY_BONUSES.get(award, 0.0) for award in player_awards)
        # Cumulative cap on award bonuses to avoid the exponential loop of winning teams
        bonus_applicato = min(3.5, bonus_totale * 0.35)
        salario_base += bonus_applicato

        return round(salario_base, 1)

    def _get_player_awards_cached(self, player_name: str) -> List[str]:
        careers_data = getattr(self.torneo, '_careers_cache', {})
        if not careers_data:
            return []
        
        player_id = player_name.replace(" ", "-").lower()
        player_career = careers_data.get(player_id)
        if not player_career:
            return []
        
        try:
            last_season_data = max(player_career, key=lambda s: s['stagione'])
            if last_season_data['stagione'] == self.torneo.season_number:
                return last_season_data.get("premi", [])
        except (ValueError, KeyError):
            pass
        
        return []

    def _get_cached_team_state(self, squadra: 'Squadra') -> str:
        if squadra.nome not in self._team_state_cache:
            self._team_state_cache[squadra.nome] = self.torneo._determina_stato_squadra(squadra)
        return self._team_state_cache[squadra.nome]

    def _get_cached_market_value(self, player: 'Giocatore') -> float:
        if player.nome not in self._market_value_cache:
            self._cache_player_values(player)
        return self._market_value_cache[player.nome]

    def _get_cached_salary_request(self, player: 'Giocatore') -> float:
        if player.nome not in self._salary_request_cache:
            self._cache_player_values(player)
        return self._salary_request_cache[player.nome]

    def _invalidate_team_cache(self, squadra: 'Squadra'):
        self._team_state_cache.pop(squadra.nome, None)
        self._role_needs_cache.pop(squadra.nome, None)
        self._starter_cache.pop(squadra.nome, None)
        self._role_rankings_cache.pop(squadra.nome, None)

    def _get_role_rankings(self, squadra: 'Squadra') -> List[str]:
        if squadra.nome not in self._role_rankings_cache:
            self._role_rankings_cache[squadra.nome] = squadra.analizza_roster_per_upgrade()
        return self._role_rankings_cache[squadra.nome]

    def _get_role_need(self, squadra: 'Squadra', ruolo: str) -> bool:
        if squadra.nome not in self._role_needs_cache:
            self._role_needs_cache[squadra.nome] = {}
        if ruolo not in self._role_needs_cache[squadra.nome]:
            self._role_needs_cache[squadra.nome][ruolo] = squadra.ha_bisogno_di_ruolo(ruolo)
        return self._role_needs_cache[squadra.nome][ruolo]

    def _get_starter_at_position(self, squadra: 'Squadra', ruolo: str) -> Optional['Giocatore']:
        if squadra.nome not in self._starter_cache:
            self._starter_cache[squadra.nome] = {}
        if ruolo not in self._starter_cache[squadra.nome]:
            self._starter_cache[squadra.nome][ruolo] = squadra.get_starter_at_position(ruolo)
        return self._starter_cache[squadra.nome][ruolo]

    def _get_signing_tool(self, squadra: 'Squadra', salary_request: float, giocatore: Optional['Giocatore'] = None) -> Tuple[str, float]:
        cap_space = squadra.salary_cap_space
        cfg_eco = CONFIG.ECONOMY
        full_mle = self.torneo.mle_value
        taxpayer_mle = round(full_mle * 0.41, 1)
        bae = cfg_eco.BAE_VALUE
        
        # Hard cap check for AI team
        hard_cap_ceiling = getattr(squadra, 'hard_cap_limit', None) if getattr(squadra, 'is_hard_capped', False) else None
        
        # Bird Rights check: if the bidding team is the previous team, they can exceed the cap
        if giocatore and self.squadre_precedenti.get(giocatore.nome) == squadra:
            max_spesa = self._determina_limite_spesa_owner(squadra)
            if hard_cap_ceiling:
                max_spesa = min(max_spesa, hard_cap_ceiling)
            if (squadra.payroll + salary_request) <= max_spesa:
                return "BIRD_RIGHTS", salary_request
            elif (squadra.payroll + self._min_salary) <= max_spesa:
                max_possible = max_spesa - squadra.payroll
                return "BIRD_RIGHTS", max(self._min_salary, round(max_possible, 1))

        # Cap Space
        if cap_space >= salary_request:
            if not hard_cap_ceiling or (squadra.payroll + salary_request) <= hard_cap_ceiling:
                return "CAP_SPACE", salary_request
        if cap_space > self._min_salary:
            possible_cap = cap_space
            if hard_cap_ceiling:
                possible_cap = min(possible_cap, hard_cap_ceiling - squadra.payroll)
            if possible_cap >= self._min_salary:
                return "CAP_SPACE", round(possible_cap, 1)
        
        # 1. Under 1st Apron: Full MLE and BAE available (triggers 1st Apron Hard Cap)
        if squadra.payroll < self.torneo.first_apron:
            if not squadra.ha_usato_mle and (squadra.payroll + full_mle) <= self.torneo.first_apron:
                if not hard_cap_ceiling or (squadra.payroll + full_mle) <= hard_cap_ceiling:
                    if salary_request <= full_mle * 1.15:
                        return "FULL_MLE", full_mle
            if not squadra.ha_usato_bae and (squadra.payroll + bae) <= self.torneo.first_apron:
                if not hard_cap_ceiling or (squadra.payroll + bae) <= hard_cap_ceiling:
                    if salary_request <= bae * 1.25:
                        return "BAE", bae
        
        # 2. Between 1st and 2nd Apron: Only Taxpayer MLE available (triggers 2nd Apron Hard Cap)
        elif squadra.payroll < self.torneo.second_apron:
            if not squadra.ha_usato_mle and (squadra.payroll + taxpayer_mle) <= self.torneo.second_apron:
                if not hard_cap_ceiling or (squadra.payroll + taxpayer_mle) <= hard_cap_ceiling:
                    if salary_request <= taxpayer_mle * 1.15:
                        return "TAXPAYER_MLE", taxpayer_mle
        
        # 3. Above 2nd Apron or no exceptions left: Minimum only
        return "MINIMUM", self._min_salary

    def _is_valid_target(self, squadra: 'Squadra', target: 'Giocatore', round_num: int) -> Tuple[bool, float]:
        role_rankings = self._get_role_rankings(squadra)
        role_priority = role_rankings.index(target.ruolo) if target.ruolo in role_rankings else 4
        stato_squadra = self._get_cached_team_state(squadra)

        # Rebuilding teams: focus heavily on youth and avoid aging role-players
        if stato_squadra in ["Rebuilding", "Rising Star"]:
            if target.eta > 32 and target.ovr < 84:
                if round_num < 8:
                    return False, 1.0
            if target.eta <= 25 and target.potenziale >= 80:
                return True, 1.35

        # Contenders: prioritize high OVRs and seasoned veterans
        if stato_squadra in ["Contender", "Defending Champion"]:
            if target.ovr >= 82:
                return True, 1.3
            if target.ovr >= 76 and target.eta >= 28:
                return True, 1.15

        if target.ovr >= 88:
            starter = self._get_starter_at_position(squadra, target.ruolo)
            if starter and starter.ovr >= 88:
                return False, 1.0
            bonus = 1.3
            if role_priority == 0: bonus = 1.45
            elif role_priority >= 3: bonus = 1.1
            return True, bonus
            
        if role_priority == 0:
            return True, 1.25
        elif role_priority == 1:
            return True, 1.15
        elif role_priority >= 3:
            team_at_pos = [p for p in squadra.roster if p.ruolo == target.ruolo]
            if team_at_pos:
                worst_at_pos = min(team_at_pos, key=lambda p: p.ovr)
                if target.ovr > worst_at_pos.ovr + 3:
                    return True, 0.9
            return False, 1.0
        
        if target.ovr >= 78:
            return True, 1.1
        
        team_at_pos = [p for p in squadra.roster if p.ruolo == target.ruolo]
        if team_at_pos:
            worst_at_pos = min(team_at_pos, key=lambda p: p.ovr)
            if target.ovr > worst_at_pos.ovr + 1:
                return True, 1.0
        
        if len(squadra.roster) < 15 and target.ovr >= 68:
            return True, 0.95
        
        if target.potenziale >= 82 and target.eta <= 27:
            return True, 1.05
        
        if round_num >= 3 and target.ovr >= 72:
            return True, 0.9
        
        return False, 1.0

    def is_rfa(self, player: 'Giocatore') -> bool:
        """
        Determines if a free agent is Restricted (RFA).
        In accordance with NBA CBA rules, RFA ONLY applies to young players completing
        their rookie-scale contract (age <= 24, or NBA service <= 4 years) who have a previous team.
        Veterans and established superstars (age 25+) are Unrestricted Free Agents (UFA) and cannot be matched.
        """
        if player.nome not in self.squadre_precedenti:
            return False
        # RFA is strictly for young players finishing their rookie contract (<= 24 years old)
        return player.eta <= 24 and getattr(player, 'years_in_nba', 3) <= 4

    def check_user_offer_validity(self, player_name: str, salary: float, years: int) -> Tuple[bool, str]:
        """Validates contract offering budget, hard cap, CBA exceptions and the veteran limit for the user team."""
        ok, tool = self._check_user_offer_cba(player_name, salary, years)
        player = next((p for p in self.unrestricted_free_agents if p.nome == player_name), None)
        if ok and player is not None and self._pileup_blocked(self.squadra_giocatore, player, tool):
            c = CONFIG.CONTRACTS
            return False, (f"Veteran limit: over the cap you can sign only {c.FA_PILEUP_MAX} veteran "
                           f"(OVR {c.FA_PILEUP_OVR}+, age {c.FA_PILEUP_AGE}+) with an exception or the minimum per summer.")
        return ok, tool

    def _check_user_offer_cba(self, player_name: str, salary: float, years: int) -> Tuple[bool, str]:
        """Validates contract offering budget, hard cap, and CBA exceptions availability for the user team."""
        user_team = self.squadra_giocatore
        if not user_team:
            return False, "No user team selected."
            
        if len(user_team.roster) >= CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
            return False, f"Roster full ({CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT} players)."
            
        if years < 1:
            return False, "The minimum length must be at least 1 year."
            
        if salary < self._min_salary:
            return False, f"Minimum salary: ${self._min_salary:.1f}M."
            
        max_limit = self._max_contract()
        if salary > max_limit + 0.05:
            return False, f"Maximum salary allowed for a single player: ${max_limit:.1f}M."

        # Hard cap verification if team was hard-capped earlier
        if getattr(user_team, 'is_hard_capped', False):
            hard_cap = getattr(user_team, 'hard_cap_limit', self.torneo.first_apron)
            if (user_team.payroll + salary) > hard_cap:
                return False, f"Hard Cap violation: the payroll would exceed the impassable ceiling of ${hard_cap:.1f}M."

        # Deduct other active user offers using cap space
        other_cap_offers = sum(o["salary"] for name, o in self.user_offers.items() if name != player_name and o.get("tool") == "CAP_SPACE")
        available_cap = user_team.salary_cap_space - other_cap_offers
        
        is_own_free_agent = (self.squadre_precedenti.get(player_name) == user_team)
        is_min = (salary <= round(self._min_salary * 1.05, 1))

        # 1. Cap Space
        if available_cap >= salary:
            if years > 4:
                return False, "Contracts signed with cap space cannot exceed 4 years."
            return True, "CAP_SPACE"

        # 2. Bird Rights (own FA)
        if is_own_free_agent:
            max_spesa = self._determina_limite_spesa_owner(user_team)
            if (user_team.payroll + salary) > max_spesa:
                return False, f"The ownership is holding back spending: maximum allowed payroll ${max_spesa:.1f}M."
            if years > 5:
                return False, "Renewals using Bird Rights can last at most 5 years."
            return True, "BIRD_RIGHTS"

        # 3. Minimum Salary Exception
        if is_min:
            if years > 2:
                return False, "Minimum-salary contracts can last at most 2 years."
            return True, "MINIMUM"

        full_mle_val = self.torneo.mle_value
        taxpayer_mle_val = round(full_mle_val * 0.41, 1)
        bae_val = CONFIG.ECONOMY.BAE_VALUE

        # 4. Under 1st Apron: Full MLE or BAE
        if user_team.payroll < self.torneo.first_apron:
            if salary <= full_mle_val and not user_team.ha_usato_mle:
                other_mle = any(o.get("tool") in ["MLE", "FULL_MLE", "TAXPAYER_MLE"] for name, o in self.user_offers.items() if name != player_name)
                if other_mle:
                    return False, "You already have an active offer using the Mid-Level Exception."
                if (user_team.payroll + salary) > self.torneo.first_apron:
                    return False, f"Using the Full MLE ties you to the 1st Apron Hard Cap (${self.torneo.first_apron:.1f}M). Post-signing payroll: ${(user_team.payroll + salary):.1f}M."
                if years > 4:
                    return False, "The Full MLE can last at most 4 years."
                return True, "FULL_MLE"
            elif salary <= bae_val and not user_team.ha_usato_bae:
                other_bae = any(o.get("tool") == "BAE" for name, o in self.user_offers.items() if name != player_name)
                if other_bae:
                    return False, "You already have an active offer using the Biannual Exception."
                if (user_team.payroll + salary) > self.torneo.first_apron:
                    return False, f"Using the BAE ties you to the 1st Apron Hard Cap (${self.torneo.first_apron:.1f}M). Post-signing payroll: ${(user_team.payroll + salary):.1f}M."
                if years > 2:
                    return False, "The Biannual Exception can last at most 2 years."
                return True, "BAE"
            else:
                return False, f"Insufficient cap space (${available_cap:.1f}M left) and salary above the Full MLE (${full_mle_val:.1f}M) or BAE (${bae_val:.1f}M)."

        # 5. Between 1st and 2nd Apron: Taxpayer MLE only
        elif user_team.payroll < self.torneo.second_apron:
            if salary <= taxpayer_mle_val and not user_team.ha_usato_mle:
                other_mle = any(o.get("tool") in ["MLE", "FULL_MLE", "TAXPAYER_MLE"] for name, o in self.user_offers.items() if name != player_name)
                if other_mle:
                    return False, "You already have an active offer using the Mid-Level Exception."
                if (user_team.payroll + salary) > self.torneo.second_apron:
                    return False, f"Using the Taxpayer MLE ties you to the 2nd Apron Hard Cap (${self.torneo.second_apron:.1f}M). Post-signing payroll: ${(user_team.payroll + salary):.1f}M."
                if years > 2:
                    return False, "The Taxpayer MLE can last at most 2 years."
                return True, "TAXPAYER_MLE"
            else:
                return False, f"Team above the 1st Apron (${self.torneo.first_apron:.1f}M). Full MLE and BAE are prohibited. Only the Taxpayer MLE is available, up to ${taxpayer_mle_val:.1f}M (max 2 years)."

        # 6. Above 2nd Apron: No Exceptions!
        else:
            return False, f"Team beyond the 2nd Apron (${self.torneo.second_apron:.1f}M). Any salary exception (MLE/BAE) is prohibited. Only minimum-salary contracts (${self._min_salary:.1f}M) or Bird renewals are allowed."

    _PLAN_OF_STATE = {"Contender": "CONTENDER", "Defending Champion": "CONTENDER", "Playoff Team": "PLAYOFF",
                      "Rebuilding": "REBUILDER", "Rising Star": "REBUILDER"}

    def _team_plan(self, squadra: 'Squadra') -> str:
        """The GM's plan (front office), else read from the team state."""
        fo = getattr(self.torneo, 'front_office', None)
        plan = getattr((getattr(fo, 'plans', None) or {}).get(squadra.nome), 'state', None) if fo is not None else None
        return plan or self._PLAN_OF_STATE.get(self._get_cached_team_state(squadra), "MIDDLE")

    def _refused_by(self, squadra: 'Squadra', giocatore: 'Giocatore') -> bool:
        """He walked away from this team (contracts.walk_reason) and will not go back; an RFA cannot walk."""
        return (bool(getattr(giocatore, 'walks_away', ''))
                and squadra is (self.squadre_precedenti or {}).get(giocatore.nome)
                and not self.is_rfa(giocatore)
                and not self._walk_veto_lifted(giocatore))

    def _walk_veto_lifted(self, giocatore: 'Giocatore') -> bool:
        """A veteran star who walked away goes back to his old team after all (CONFIG.CONTRACTS FA_WALK_LIFT_*) when,
        from FA_WALK_LIFT_DAY on, no other team can pay him FA_WALK_LIFT_MARKET_PCT of his asking price."""
        c = CONFIG.CONTRACTS
        if (self.current_day < c.FA_WALK_LIFT_DAY or giocatore.ovr < c.FA_WALK_LIFT_OVR
                or giocatore.eta < c.FA_WALK_LIFT_AGE):
            return False
        if not hasattr(self, '_walk_lift_cache'):
            self._walk_lift_cache = {}
        key = (giocatore.nome, self.current_day, len(getattr(self, 'signings', []) or []))
        if key not in self._walk_lift_cache:
            ask = self._get_cached_salary_request(giocatore)
            need = ask * c.FA_WALK_LIFT_MARKET_PCT
            prev = (self.squadre_precedenti or {}).get(giocatore.nome)
            market = False
            for s in self.squadre:
                if s is prev or len(s.roster) >= CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
                    continue
                _tool, money = self._get_signing_tool(s, ask, giocatore)
                if money >= need:
                    market = True
                    break
            self._walk_lift_cache[key] = not market
        return self._walk_lift_cache[key]

    def _is_ring_chase(self, squadra: 'Squadra', giocatore: 'Giocatore') -> bool:
        """A contender or a superteam (as dettaglio_punteggio reads them)."""
        superstars = [p for p in squadra.roster if p.ovr >= 87 and p.nome != giocatore.nome]
        stars = [p for p in squadra.roster if 82 <= p.ovr < 87 and p.nome != giocatore.nome]
        is_superteam = (len(superstars) >= 2) or (len(superstars) >= 1 and len(stars) >= 2)
        return is_superteam or self._get_cached_team_state(squadra) in ["Contender", "Defending Champion"]

    def _early_floor(self, giocatore: 'Giocatore', squadra: 'Squadra', value: float) -> Optional[float]:
        """The lowest salary he takes from this team in the first days of the market (CONFIG.CONTRACTS
        FA_EARLY_FLOOR*), at any age; None when no floor applies."""
        c = CONFIG.CONTRACTS
        if self.current_day > c.FA_EARLY_FLOOR_DAYS:
            return None
        pct = next((p for ovr, p in sorted(c.FA_EARLY_FLOOR.items(), reverse=True) if giocatore.ovr >= ovr), None)
        if pct is None:
            return None
        floor = value * pct
        if giocatore.eta >= c.FA_EARLY_FLOOR_RING_AGE and self._is_ring_chase(squadra, giocatore):
            floor = min(floor, self.torneo.mle_value)
        return floor

    _PILEUP_TOOLS = ("MLE", "FULL_MLE", "TAXPAYER_MLE", "BAE", "MINIMUM")

    def _is_pileup_vet(self, giocatore: 'Giocatore') -> bool:
        c = CONFIG.CONTRACTS
        return giocatore.ovr >= c.FA_PILEUP_OVR and giocatore.eta >= c.FA_PILEUP_AGE

    def _pileup_blocked(self, squadra: 'Squadra', giocatore: 'Giocatore', tool: Optional[str]) -> bool:
        """This team already signed FA_PILEUP_MAX veterans with an exception or the minimum this summer."""
        if tool not in self._PILEUP_TOOLS or not self._is_pileup_vet(giocatore):
            return False
        logs = getattr(self.torneo, 'offseason_log_data', None)
        records = logs.get('fa_signings') if isinstance(logs, dict) and 'fa_signings' in logs else self.signings
        done = sum(1 for r in records or [] if isinstance(r, dict) and r.get("team") == squadra.nome and r.get("pileup"))
        return done >= CONFIG.CONTRACTS.FA_PILEUP_MAX

    def _raise_or_withdraw(self, day: int):
        """CPU teams that really want a player and are not leading his race raise their offer (CONFIG.CONTRACTS
        FA_RAISE_STEP) up to their ceiling (first offer x FA_RAISE_CEILING[plan], and what their money allows); a team
        that cannot go higher pulls out. Offers without the bidding keys (old offers) are left alone."""
        c = CONFIG.CONTRACTS
        if not hasattr(self, 'night_moves'):
            self.night_moves = []
        for player in list(self.unrestricted_free_agents):
            offers = [o for o in self.ai_offers.get(player.nome, []) if o.get("wanted") and not o.get("withdrawn")]
            if not offers:
                continue
            leader = self.classifica_offerte(player)["leader"]
            ask = self._calcola_richiesta_salariale(player)
            for o in offers:
                if o["team"] == leader:
                    continue
                squadra = next((s for s in self.squadre if s.nome == o["team"]), None)
                if squadra is None or self._refused_by(squadra, player):
                    continue
                first = (o.get("first") or {}).get("salary", o["salary"])
                ceiling = min(first * c.FA_RAISE_CEILING.get(self._team_plan(squadra), 1.0), self._max_contract())
                wished = min(o["salary"] + ask * c.FA_RAISE_STEP, ceiling)
                _tool, money = self._get_signing_tool(squadra, wished, player)
                target = round(min(wished, money), 2)
                if target > o["salary"] + 0.05:
                    o["salary"] = target
                    o.setdefault("history", []).append({"day": day, "salary": target})
                    self.night_moves.append({"type": "raise", "team": o["team"], "player": player.nome,
                                             "salary": target, "day": day})
                else:
                    reason = "over budget" if money < wished else "price too high"
                    o["withdrawn"] = {"day": day, "reason": reason}
                    self.night_moves.append({"type": "out", "team": o["team"], "player": player.nome,
                                             "reason": reason, "day": day})

    def _night_auction(self, day: int):
        """Tonight's bidding before the players choose: outbid teams that want the player raise round after round
        until nobody raises any more (each one stops at its ceiling or pulls out)."""
        if not hasattr(self, 'night_moves'):
            self.night_moves = []
        for _ in range(CONFIG.CONTRACTS.FA_NIGHT_MAX_ROUNDS):
            before = len(self.night_moves)
            self._raise_or_withdraw(day)
            if len(self.night_moves) == before:
                break

    def generate_ai_offers_for_day(self, day: int):
        """Generates appropriate competing offers for AI teams on a simulated day."""
        # Filter existing AI offers to exclude signed players
        self.ai_offers = {name: o_list for name, o_list in self.ai_offers.items() if any(p.nome == name for p in self.unrestricted_free_agents)}
        self._raise_or_withdraw(day)
        
        # Max active offers per team increases as day progresses
        max_active = 2 + (day // 3)
        
        for squadra in self.squadre:
            if squadra == self.squadra_giocatore:
                continue
            if len(squadra.roster) >= CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
                continue
                
            active_count = sum(1 for o_list in self.ai_offers.values() for o in o_list
                               if o["team"] == squadra.nome and not o.get("withdrawn"))
            if active_count >= max_active:
                continue
                
            potential_targets = []
            for player in self.unrestricted_free_agents:
                # Day filters
                if day <= 3 and player.ovr < 82:
                    continue
                if 4 <= day <= 7 and player.ovr < 74:
                    continue
                    
                # Skip if already bid by this team
                if any(o["team"] == squadra.nome for o in self.ai_offers.get(player.nome, [])):
                    continue
                    
                is_valid, bonus_fit = self._is_valid_target(squadra, player, day)
                is_prev_team = (self.squadre_precedenti.get(player.nome) == squadra)
                if self._refused_by(squadra, player):
                    continue   # he walked away from this team: it does not bid
                if is_prev_team:
                    is_valid = True
                    bonus_fit = max(1.0, bonus_fit)
                    
                if is_valid:
                    potential_targets.append((player, bonus_fit))
                    
            # Sort potential targets by OVR
            potential_targets.sort(key=lambda x: x[0].ovr, reverse=True)
            
            for player, bonus_fit in potential_targets:
                if active_count >= max_active:
                    break
                
                richiesta = self._calcola_richiesta_salariale(player)
                tool, max_salary = self._get_signing_tool(squadra, richiesta, player)
                
                if tool in ["MLE", "FULL_MLE", "TAXPAYER_MLE"] and squadra.ha_usato_mle:
                    tool, max_salary = "MINIMUM", self._min_salary
                if tool == "BAE" and squadra.ha_usato_bae:
                    tool, max_salary = "MINIMUM", self._min_salary
                if self._pileup_blocked(squadra, player, tool):
                    continue   # it already brought in its cheap veteran this summer
                floor = self._early_floor(player, squadra, self._get_cached_salary_request(player))
                if floor is not None and max_salary < floor:
                    continue   # the early market: he would turn it down

                # Filter out low-ball offers before they are made.
                # Stars and starters in their prime won't accept low-ball bids.
                if player.ovr >= 84 and player.eta < 33:
                    if max_salary < richiesta * 0.80:
                        continue
                elif player.ovr >= 76 and player.eta < 33:
                    if max_salary < richiesta * 0.70:
                        continue
                elif player.ovr >= 72 and player.eta < 30:
                    if max_salary < richiesta * 0.55:
                        continue
                    
                salario = min(max_salary, richiesta)
                salario = max(self._min_salary, salario)
                
                # Rebuilder willingness & Salary Floor Pressure
                stato_squadra = self._get_cached_team_state(squadra)
                cap = self.torneo.salary_cap
                floor_deficit = getattr(squadra, 'salary_floor_deficit', 0.0)
                
                if stato_squadra in ["Rebuilding", "Rising Star"] and squadra.salary_cap_space > cap * 0.25:
                    salario *= 1.15
                elif floor_deficit > 0:
                    salario *= 1.10
                    
                salario = round(salario * bonus_fit, 1)
                
                # Contract length based on team direction and player age
                if stato_squadra in ["Rebuilding", "Rising Star"]:
                    if player.eta >= 32:
                        years = 1 if player.eta >= 34 else 2
                    else:
                        years = min(4, max(2, 4 if player.potenziale >= 82 else 3))
                else:
                    years = 2 if player.eta > 32 else (random.randint(2, 3) if player.eta > 29 else random.randint(3, 4))
                
                # Exceptions year limitations (CBA: Taxpayer MLE, BAE, and Minimum cannot exceed 2 years)
                if tool in ["TAXPAYER_MLE", "BAE", "MINIMUM"]:
                    years = min(2, years)

                option_type = "None"
                
                if day >= 8 and getattr(squadra, 'is_below_salary_floor', False) and tool == "CAP_SPACE" and player.ovr >= 74:
                    balloon_target = min(squadra.salary_cap_space, max(salario * 1.25, min(floor_deficit, cap * 0.16)))
                    if balloon_target > salario:
                        salario = round(balloon_target, 1)
                        years = 1 if player.eta >= 30 else 2
                        option_type = "TO" if years == 2 else "None"
                
                # Clamp to budget limits
                if tool == "CAP_SPACE":
                    salario = min(squadra.salary_cap_space, salario)
                else:
                    salario = min(max_salary, salario)
                salario = max(self._min_salary, min(salario, self._max_contract()))
                
                if option_type == "None":
                    if player.ovr >= 90 and years >= 3 and random.random() < 0.3:
                        option_type = "PO"
                    elif player.eta >= 34 or player.ovr < 72:
                        option_type = "TO"

                if player.nome not in self.ai_offers:
                    self.ai_offers[player.nome] = []
                    
                self.ai_offers[player.nome].append({
                    "team": squadra.nome,
                    "salary": salario,
                    "years": years,
                    "tool": tool,
                    "option_type": option_type,
                    # bidding (_raise_or_withdraw): the first offer, its raises, and whether the team really wants him
                    "first": {"day": day, "salary": salario},
                    "history": [],
                    "wanted": bonus_fit >= CONFIG.CONTRACTS.FA_WANT_FIT,
                })
                active_count += 1

    def process_ai_cuts_and_upgrades(self, day: int):
        """Starting Day 8, full AI teams cut immunities-violators to acquire a free agent with +5 OVR."""
        if day < 8:
            return
            
        for squadra in self.squadre:
            if squadra == self.squadra_giocatore:
                continue
            if len(squadra.roster) < 15:
                continue
                
            # Roster cut candidates
            cut_candidates = [
                p for p in squadra.roster
                if not p.is_untouchable
                and p.ovr < 76
                and p.potenziale < 80
            ]
            if not cut_candidates:
                continue
                
            cut_candidates.sort(key=lambda p: p.ovr)
            worst_player = cut_candidates[0]
            
            # Find better FAs at same position
            better_fas = [
                fa for fa in self.unrestricted_free_agents
                if fa.ruolo == worst_player.ruolo
                and fa.ovr >= worst_player.ovr + 5
            ]
            if not better_fas:
                continue
                
            better_fas.sort(key=lambda fa: fa.ovr, reverse=True)
            
            target_fa = None
            target_tool = None
            target_salary = None
            
            for fa in better_fas:
                richiesta = self._calcola_richiesta_salariale(fa)
                tool, max_salary = self._get_signing_tool(squadra, richiesta, fa)
                
                if tool in ["MLE", "FULL_MLE", "TAXPAYER_MLE"] and squadra.ha_usato_mle:
                    tool, max_salary = "MINIMUM", self._min_salary
                if tool == "BAE" and squadra.ha_usato_bae:
                    tool, max_salary = "MINIMUM", self._min_salary
                    
                salario = min(max_salary, richiesta)
                
                if tool == "CAP_SPACE" and (squadra.salary_cap_space + worst_player.contract.salario_annuale) < salario:
                    continue
                    
                target_fa = fa
                target_tool = tool
                target_salary = salario
                break
                
            if target_fa and target_salary:
                # Execute cut!
                squadra.roster.remove(worst_player)
                worst_player.squadra = None
                worst_player.contract = None
                self.unrestricted_free_agents.append(worst_player)
                
                cut_msg = f"CUT: {squadra.nome} cut {worst_player.nome} ({worst_player.ovr} OVR) to make room for {target_fa.nome}."
                self.signings_log.append(cut_msg)
                main_log.info(cut_msg)
                
                years = 2 if target_fa.eta > 32 else (random.randint(2, 3) if target_fa.eta > 29 else random.randint(3, 4))
                option_type = "None"
                if target_fa.ovr >= 90 and years >= 3 and random.random() < 0.3:
                    option_type = "PO"
                elif target_fa.eta >= 34 or target_fa.ovr < 72:
                    option_type = "TO"

                if target_fa.nome not in self.ai_offers:
                    self.ai_offers[target_fa.nome] = []
                    
                self.ai_offers[target_fa.nome].append({
                    "team": squadra.nome,
                    "salary": target_salary,
                    "years": years,
                    "tool": target_tool,
                    "option_type": option_type
                })
                
                self._invalidate_team_cache(squadra)
                # Keep loop going, only one cut attempt per team per day

    def _resolve_offers_for_day(self) -> Optional[dict]:
        """Iterates over all offers, matches acceptances, and handles RFA sheets."""
        # Compile names of FAs that have offers
        all_bid_names = set(list(self.user_offers.keys()) + list(self.ai_offers.keys()))
        
        for player_name in list(all_bid_names):
            player = next((p for p in self.unrestricted_free_agents if p.nome == player_name), None)
            if not player:
                continue
                
            # Collect all active offers
            offers = []
            if player_name in self.user_offers:
                offers.append(self.user_offers[player_name])
            if player_name in self.ai_offers:
                offers.extend(self.ai_offers[player_name])
                
            if not offers:
                continue
                
            # Score all offers, pick the leader and tonight's bar (the same ranking the page shows)
            race = self.classifica_offerte(player)
            if not race["offers"]:   # every offer was withdrawn
                continue
            best_offer = race["offers"][0]["offer"]
            best_score = race["leader_score"]
            soglia = race["bar_tonight"]

            if best_score >= soglia:
                # Accept! Check RFA
                if self.is_rfa(player):
                    prev_team = self.squadre_precedenti[player.nome]
                    
                    # 1. RFA belongs to User, accepted AI offer sheet
                    if prev_team == self.squadra_giocatore and best_offer["team"] != prev_team.nome:
                        self.pending_rfa_match = {
                            "player": player.nome,
                            "team": best_offer["team"],
                            "salary": best_offer["salary"],
                            "years": best_offer["years"],
                            "option_type": best_offer.get("option_type", "None")
                        }
                        # Pause day simulation and prompt match/walk
                        return {"status": "PENDING_RFA_MATCH", "match_info": self.pending_rfa_match}
                        
                    # 2. RFA belongs to AI, accepted User or other AI offer sheet
                    elif prev_team != self.squadra_giocatore and best_offer["team"] != prev_team.nome:
                        # AI decides to match
                        match_success = False
                        # If AI previous team has cap space or Bird rights (RFA allows exceeding cap)
                        # and has roster space, it matches superstar contracts
                        if len(prev_team.roster) < CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
                            max_spesa = self.torneo.second_apron + 20.0
                            is_valuable = player.ovr >= 78 or player.potenziale >= 82
                            tax_burden = (prev_team.payroll + best_offer["salary"]) > getattr(self.torneo, 'luxury_tax_threshold', self.torneo.salary_cap * 1.2)
                            match_prob = 0.80 if (is_valuable and not tax_burden) else (0.50 if is_valuable else 0.25)
                            if (prev_team.payroll + best_offer["salary"]) <= max_spesa and random.random() < match_prob:
                                match_success = True
                                
                        if match_success:
                            # matched!
                            opt_type = best_offer.get("option_type", "None")
                            player_opt = (opt_type == "PO")
                            team_opt = (opt_type == "TO")
                            r_pct = best_offer.get("raise_pct", 0.05)
                            self._firma_giocatore(prev_team, player, best_offer["salary"], "RFA MATCH RENEWAL", best_offer["years"], player_option=player_opt, team_option=team_opt, raise_pct=r_pct)
                            msg = f"RFA MATCH: {prev_team.nome} match the offer from {best_offer['team']} and re-sign {player.nome} for {best_offer['years']} years / ${best_offer['salary']:.1f}M."
                            self.signings_log.append(msg)
                            self.user_offers.pop(player.nome, None)
                            self.ai_offers.pop(player.nome, None)
                            continue
                            
                # Normal signing or matched previous team
                sign_team = next(s for s in self.squadre if s.nome == best_offer["team"])
                tool = best_offer.get("tool", "CAP_SPACE")
                
                if tool in ["MLE", "FULL_MLE"]:
                    sign_team.ha_usato_mle = True
                    tipo = "FULL MLE SIGNING"
                    sign_team.is_hard_capped = True
                    sign_team.hard_cap_limit = self.torneo.first_apron
                elif tool == "TAXPAYER_MLE":
                    sign_team.ha_usato_mle = True
                    tipo = "FIRMA TAXPAYER MLE"
                    sign_team.is_hard_capped = True
                    sign_team.hard_cap_limit = self.torneo.second_apron
                elif tool == "BAE":
                    sign_team.ha_usato_bae = True
                    tipo = "BAE SIGNING"
                    sign_team.is_hard_capped = True
                    sign_team.hard_cap_limit = self.torneo.first_apron
                elif tool == "MINIMUM":
                    tipo = "MINIMUM SIGNING"
                elif tool == "BIRD_RIGHTS":
                    tipo = "BIRD RENEWAL"
                else:
                    tipo = "UFA SIGNING"
                    
                opt_type = best_offer.get("option_type", "None")
                player_opt = (opt_type == "PO")
                team_opt = (opt_type == "TO")
                r_pct = best_offer.get("raise_pct", 0.05)
                beaten = [{"team": o["team"], "salary": o["salary"], "years": o["years"],
                           "raised": len(o["offer"].get("history", []))} for o in race["offers"][1:]]
                self._firma_giocatore(sign_team, player, best_offer["salary"], tipo, best_offer["years"], player_option=player_opt, team_option=team_opt, raise_pct=r_pct, beat=beaten,
                                      raised=len(best_offer.get("history", [])), tool=tool)
                
                # Log transaction
                log_msg = f"{tipo}: {sign_team.nome} sign {player.nome} ({player.ovr} OVR) for {best_offer['years']} years / ${best_offer['salary']:.1f}M."
                self.signings_log.append(log_msg)
                
                # Clear active offers
                self.user_offers.pop(player.nome, None)
                self.ai_offers.pop(player.nome, None)
                
        return None

    def simulate_day(self) -> dict:
        """Simulates one complete day of negotiations."""
        if self.completed:
            return {"status": "SUCCESS", "day": self.current_day, "completed": True}
            
        self.night_moves = []
        # 1. AI Teams raise or pull out, then generate offers
        self.generate_ai_offers_for_day(self.current_day)
        
        # 2. AI Teams optimize rosters (Day 8+)
        self.process_ai_cuts_and_upgrades(self.current_day)

        # 2b. Tonight's bidding: outbid teams raise until nobody does, then the players choose
        self._night_auction(self.current_day)
        
        # 3. Resolve day transactions
        res = self._resolve_offers_for_day()
        if res:
            # Paused due to pending RFA match sheet
            return res
            
        # 4. Check Day 12 completion
        if self.current_day == CONFIG.OFFSEASON.FREE_AGENCY_DAYS:
            self._esegui_fase_salvaroster()
            self.completed = True
            # Pool cleanup
            self.torneo._pulizia_post_free_agency(self.unrestricted_free_agents)
            
        # Update desperation decay
        self.market_desperation_factor *= 0.95
        
        day_simulated = self.current_day
        if not self.completed:
            self.current_day += 1
            
        # Clear user offers for signed players
        self.user_offers = {name: o for name, o in self.user_offers.items() if any(p.nome == name for p in self.unrestricted_free_agents)}
        
        return {
            "status": "SUCCESS", 
            "day": day_simulated, 
            "next_day": self.current_day,
            "completed": self.completed,
            "signings": self.signings_log
        }

    def resolve_rfa_match(self, match: bool):
        """Resolves the user's decision to match or decline their RFA offer sheet."""
        if not self.pending_rfa_match:
            return
            
        player_name = self.pending_rfa_match["player"]
        player = next((p for p in self.unrestricted_free_agents if p.nome == player_name), None)
        if not player:
            self.pending_rfa_match = None
            return
            
        prev_team = self.squadre_precedenti[player.nome]
        offering_team = next(s for s in self.squadre if s.nome == self.pending_rfa_match["team"])
        salary = self.pending_rfa_match["salary"]
        years = self.pending_rfa_match["years"]
        
        opt_type = self.pending_rfa_match.get("option_type", "None")
        player_opt = (opt_type == "PO")
        team_opt = (opt_type == "TO")
        
        if match:
            # User matches!
            self._firma_giocatore(prev_team, player, salary, "RFA MATCH RENEWAL", years, player_option=player_opt, team_option=team_opt)
            msg = f"RFA MATCH: {prev_team.nome} match the offer from {offering_team.nome} and re-sign {player.nome} for {years} years / ${salary:.1f}M."
            if player_opt: msg += " [Player Opt]"
            if team_opt: msg += " [Team Opt]"
            self.signings_log.append(msg)
        else:
            # User declines, offering team signs
            tool, _ = self._get_signing_tool(offering_team, salary, player)
            if tool == "MLE": offering_team.ha_usato_mle = True
            elif tool == "BAE": offering_team.ha_usato_bae = True
            
            self._firma_giocatore(offering_team, player, salary, f"FIRMA {tool}", years, player_option=player_opt, team_option=team_opt)
            msg = f"RFA SIGNING (MATCH DECLINED): {player.nome} signs with {offering_team.nome} for {years} years / ${salary:.1f}M."
            if player_opt: msg += " [Player Opt]"
            if team_opt: msg += " [Team Opt]"
            self.signings_log.append(msg)
            
        self.user_offers.pop(player_name, None)
        self.ai_offers.pop(player_name, None)
        self.pending_rfa_match = None

    def esegui_free_agency(self) -> List[Dict]:
        """
        Automated fallback loop representing the entire 12-day Free Agency.
        Called in autoplay seasons and CLI tests (such as verify_offseason.py).
        """
        self._build_caches()
        main_log.info("\n--- INIZIO FREE AGENCY (Automated 12-Day Simulation) ---")
        
        while not self.completed:
            res = self.simulate_day()
            if res.get("status") == "PENDING_RFA_MATCH":
                # Automated match decision: AI previous team matches if they have cap space or Bird rights
                match_info = res["match_info"]
                player_name = match_info["player"]
                player = next(p for p in self.unrestricted_free_agents if p.nome == player_name)
                prev_team = self.squadre_precedenti[player.nome]
                
                # Check match criteria
                match = False
                max_spesa = self.torneo.second_apron + 20.0
                if len(prev_team.roster) < CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT:
                    if (prev_team.payroll + match_info["salary"]) <= max_spesa:
                        match = True
                        
                self.resolve_rfa_match(match)
                
        return self.log_fa

    # --- HELPER & LEGACY METHODS ---

    def _esegui_fase_salvaroster(self):
        """Final emergency fill on Day 12 to ensure all teams have at least 15 players and meet the salary floor."""
        main_log.info("\n-- Final Phase: Roster Saver & Floor Compliance --")
        
        fa_by_value = sorted(
            [(p, self._get_cached_market_value(p)) for p in self.unrestricted_free_agents],
            key=lambda x: x[1],
            reverse=True
        )
        
        cap = getattr(self.torneo, 'salary_cap', 155.0)
        is_no_cap = cap >= 9000
        ref_cap = 155.0 if is_no_cap else cap

        for squadra in self.squadre:
            while len(squadra.roster) < CONFIG.OFFSEASON.ROSTER_SIZE_MIN and self.unrestricted_free_agents:
                candidato = next((p for p, val in fa_by_value if p in self.unrestricted_free_agents), None)
                if not candidato: 
                    break
                
                needed_spots = CONFIG.OFFSEASON.ROSTER_SIZE_MIN - len(squadra.roster)
                salario = self._min_salary
                
                # If the team has cap space and the player is a valid veteran/rotation player (>= 74 OVR)
                if squadra.salary_cap_space > self._min_salary and candidato.ovr >= 74:
                    mkt_val = self._get_cached_market_value(candidato)
                    if getattr(squadra, 'is_below_salary_floor', False):
                        floor_deficit = getattr(squadra, 'salary_floor_deficit', 0.0)
                        per_player_allowance = floor_deficit / max(1, needed_spots)
                        target_sal = max(mkt_val * 0.75, per_player_allowance)
                    else:
                        per_spot_space = squadra.salary_cap_space / max(1, needed_spots)
                        target_sal = min(mkt_val * 0.70, per_spot_space)
                    
                    max_cap_limit = max(ref_cap * 0.25, floor_deficit) if getattr(squadra, 'is_below_salary_floor', False) else ref_cap * 0.15
                    salario = min(squadra.salary_cap_space, max(self._min_salary, min(target_sal, max_cap_limit)))
                    salario = round(salario, 1)
                
                tipo_firma = "ROSTER SAVER SIGNING (FLOOR COMPLIANCE)" if getattr(squadra, 'is_below_salary_floor', False) and salario > self._min_salary else ("ROSTER SAVER SIGNING (CAP)" if salario > self._min_salary else "ROSTER SAVER SIGNING")
                main_log.info(f"{tipo_firma}: {squadra.nome} sign {candidato.nome} ({candidato.ovr} OVR) at ${salario:.1f}M to reach the roster min/floor.")
                self._firma_giocatore(squadra, candidato, salario, tipo_firma, 1)

    def _max_contract(self) -> float:
        """The most one player can earn in year 1: CONFIG.ECONOMY.MAX_CONTRACT_CAP_PCT of the cap the asks use."""
        raw_cap = getattr(self.torneo, 'salary_cap', 155.0) if self.torneo else 155.0
        anno = getattr(self.torneo, 'anno_corrente', 2025) if self.torneo else 2025
        is_no_cap = (self.torneo and getattr(self.torneo, 'cba_mode', '') == 'no_cap') or (raw_cap >= 9000.0)
        cap = CONFIG.ECONOMY.get_cap_for_year(anno, raw_cap, is_no_cap)
        return round(cap * CONFIG.ECONOMY.MAX_CONTRACT_CAP_PCT, 2)

    def _calcola_richiesta_salariale(self, giocatore: 'Giocatore', premi: bool = True) -> float:
        if premi:
            richiesta_base = self._get_cached_salary_request(giocatore)
        else:
            richiesta_base = self._get_cached_market_value(giocatore)
        return round(richiesta_base * self.market_desperation_factor, 1)

    def _firma_giocatore(self, squadra: 'Squadra', giocatore: 'Giocatore', salario: float, tipo: str, anni: Optional[int] = None, player_option: Optional[bool] = None, team_option: Optional[bool] = None, raise_pct: float = 0.05, beat: Optional[list] = None, raised: int = 0, tool: Optional[str] = None):
        giocatore.walks_away = ""   # a new contract: whatever he refused, he signed
        trade_requests.clear_request(giocatore)   # ...and whatever he asked of his old team is over
        prev = (self.squadre_precedenti or {}).get(giocatore.nome)
        if prev is not None and prev is not squadra:
            giocatore.anni_nella_squadra = 0   # a new team: his loyalty years start again
        if anni is None:
            anni = 2 if giocatore.eta > 32 else (random.randint(2, 3) if giocatore.eta > 29 else random.randint(3, 4))
        
        salario = min(salario, self._max_contract())   # no path signs over the max (raises once went to 55%)
        salari = []
        cur = salario
        for _ in range(anni):
            salari.append(round(cur, 2))
            cur *= (1.0 + raise_pct)

        # Replace or create the contract
        giocatore.contract = Contract(
            salario_annuale=salario,
            anni_rimanenti=anni,
            player_option=(player_option if player_option is not None else False),
            team_option=(team_option if team_option is not None else False),
            salari_per_anno=salari
        )
        giocatore.squadra = squadra
        squadra.roster.append(giocatore)
        
        # Invalidate the team cache after the signing
        self._invalidate_team_cache(squadra)
        
        if giocatore in self.unrestricted_free_agents:
            self.unrestricted_free_agents.remove(giocatore)
            
        # Check if the team's need for the signed player's role is now satisfied.
        ruolo_firmato = giocatore.ruolo
        if not self._get_role_need(squadra, ruolo_firmato):
            for other_player in self.unrestricted_free_agents:
                if other_player.ruolo == ruolo_firmato and other_player.nome in self.ai_offers:
                    original_offers = self.ai_offers[other_player.nome]
                    updated_offers = [o for o in original_offers if o["team"] != squadra.nome]
                    if len(updated_offers) < len(original_offers):
                        self.ai_offers[other_player.nome] = updated_offers
                        main_log.info(f"FA RECONSIDER: {squadra.nome} withdraws offer to {other_player.nome} because their need for {ruolo_firmato} is met.")

        opt_str = " (PO)" if giocatore.contract.player_option else (" (TO)" if giocatore.contract.team_option else "")
        log_msg = f"FA SIGNING: {giocatore.nome} ({giocatore.ovr} OVR, {giocatore.ruolo}) signs with {squadra.nome} for {anni} years at ${salario:.1f}M/year{opt_str} [{tipo}]."
        self.signings_log.append(log_msg)
        
        self.log_fa.append({"giocatore": giocatore.nome, "nuova_squadra": squadra.nome, "contratto": f"${salario:.1f}M / {anni} anni"})
        if not hasattr(self, 'signings'):
            self.signings = []
        self.signings.append({
            "player": giocatore.nome, "role": giocatore.ruolo, "ovr": giocatore.ovr, "team": squadra.nome,
            "salary": salario, "years": anni,
            "option_type": "PO" if giocatore.contract.player_option else ("TO" if giocatore.contract.team_option else "None"),
            "day": self.current_day, "beat": list(beat or []),
            "previous_team": getattr((self.squadre_precedenti or {}).get(giocatore.nome), 'nome', None),
            "raised": raised,
            "pileup": tool in self._PILEUP_TOOLS and self._is_pileup_vet(giocatore),
        })
        if not hasattr(self, 'night_moves'):
            self.night_moves = []
        if self.signings[-1]["pileup"]:
            # his cheap veteran is in: the team's other exception/minimum offers to veterans go away
            for name, o_list in self.ai_offers.items():
                vet = next((p for p in self.unrestricted_free_agents if p.nome == name), None)
                for o in o_list:
                    if (o["team"] == squadra.nome and not o.get("withdrawn") and vet is not None
                            and self._pileup_blocked(squadra, vet, o.get("tool"))):
                        o["withdrawn"] = {"day": self.current_day, "reason": "veteran limit"}
        self.night_moves.append({"type": "signed", "team": squadra.nome, "player": giocatore.nome,
                                 "salary": salario, "day": self.current_day})
        # Kept on the tournament too, so the New season summary has them after a reload (this instance is not saved).
        if isinstance(getattr(self.torneo, 'offseason_log_data', None), dict):
            self.torneo.offseason_log_data.setdefault('fa_signings', []).append(self.signings[-1])
        main_log.info(log_msg)
        squadra.log_financial_event(
            tipo,
            salario,
            f"Signed {giocatore.nome} ({giocatore.ovr} OVR)"
        )
        record_signing(self.torneo, squadra, giocatore, salario, anni, tipo,
                       previous_team=(self.squadre_precedenti or {}).get(giocatore.nome))

    def _calcola_punteggio_accettazione_cached(self, giocatore: 'Giocatore', squadra: 'Squadra', offerta_salariale: float, option_type: str = "None") -> float:
        return self.dettaglio_punteggio(giocatore, squadra, offerta_salariale, option_type)["total"]

    def dettaglio_punteggio(self, giocatore: 'Giocatore', squadra: 'Squadra', offerta_salariale: float, option_type: str = "None") -> dict:
        """How much a player wants an offer (0-100), part by part, so the page can show why.

        Returns {"rejected": None | {"below_pct"}, "value", "parts": [{"key", "value"}], "raw", "total"}: the parts add up
        to "raw", "total" is raw clamped to 0-100 (0 when the offer is an instant low-ball reject)."""
        valore_mercato_base = self._get_cached_salary_request(giocatore)
        if valore_mercato_base <= 0: valore_mercato_base = self._min_salary

        # Apply financial trade-off for contract option types
        if option_type == "PO":
            valore_mercato_base *= 0.90
        elif option_type == "TO":
            valore_mercato_base *= 1.10

        # A player who walks away (contracts.walk_reason, set at the deadline) will not go back to his old team; an RFA
        # cannot walk (his team keeps the right to match)
        if self._refused_by(squadra, giocatore):
            return {"rejected": {"walks": giocatore.walks_away}, "value": valore_mercato_base, "parts": [], "raw": 0.0, "total": 0.0}

        # 1. Economic Factor
        ratio_offerta = offerta_salariale / valore_mercato_base

        # Contextual analysis for superteams and contenders
        goal_squadra = self._get_cached_team_state(squadra)
        superstars = [p for p in squadra.roster if p.ovr >= 87 and p.nome != giocatore.nome]
        stars = [p for p in squadra.roster if 82 <= p.ovr < 87 and p.nome != giocatore.nome]
        is_superteam = (len(superstars) >= 2) or (len(superstars) >= 1 and len(stars) >= 2)
        has_star_partner = (len(superstars) >= 1) or (len(stars) >= 2)
        is_ring_chase = (is_superteam or goal_squadra in ["Contender", "Defending Champion"])

        # Hard block: If the offer is way too low compared to market value.
        # Ring chasers & veteran free agents (29+ yrs) joining Contenders/Superteams can accept discounts.
        rifiuto = None
        if not (is_ring_chase and giocatore.eta >= 29):
            if giocatore.eta < 33:
                if giocatore.ovr >= 84 and ratio_offerta < 0.75:
                    rifiuto = 75
                elif giocatore.ovr >= 76 and ratio_offerta < 0.65:
                    rifiuto = 65
                elif giocatore.ovr >= 72 and ratio_offerta < 0.50:
                    rifiuto = 50
        if rifiuto is None:
            # The first days of the market: a star wants real money at any age (CONFIG.CONTRACTS FA_EARLY_FLOOR*)
            floor = self._early_floor(giocatore, squadra, valore_mercato_base)
            if floor is not None and offerta_salariale < floor - 0.05:
                rifiuto = int(round(floor / valore_mercato_base * 100))
        if rifiuto is not None:
            main_log.info(f"FA DEBUG - Player {giocatore.nome} instantly rejects low-ball offer of ${offerta_salariale}M (Asking: ${valore_mercato_base}M)")
            return {"rejected": {"below_pct": rifiuto}, "value": valore_mercato_base, "parts": [], "raw": 0.0, "total": 0.0}

        soldi = (ratio_offerta - 1.0) * 60
        # Oversized balloon contract excitement
        pallone = 0.0
        if ratio_offerta >= 1.25:
            pallone = min(30.0, (ratio_offerta - 1.0) * 35.0)

        # 2. Morale Factor
        morale = (giocatore.morale - 70) * 0.4

        # 3. Superteam & Star Partnership Allure
        stelle = 0.0
        if is_superteam:
            stelle = 30.0 if (giocatore.ovr >= 80 or giocatore.eta >= 29) else 15.0
        elif has_star_partner:
            stelle = 15.0 if (giocatore.ovr >= 80 or giocatore.eta >= 28) else 8.0

        # 4. Role & Starting Opportunity vs Position Congestion
        ruolo = 0.0
        same_role_players = [p for p in squadra.roster if p.ruolo == giocatore.ruolo and p.nome != giocatore.nome]
        best_same_role = max([p.ovr for p in same_role_players], default=0)
        # Starter spot open/upgrade bonus
        if (not same_role_players or best_same_role <= 76) and giocatore.ovr >= 77:
            ruolo = 18.0
        # Position congestion penalty
        elif best_same_role >= 87 and giocatore.ovr >= 80 and giocatore.eta < 34:
            ruolo = -28.0

        # 5. Team Success Factor
        successo = 0.0
        is_star = giocatore.ovr >= 85
        win_mult = 2.5 if is_star else 1.0
        if goal_squadra == "Defending Champion": successo = 25 * win_mult
        elif goal_squadra == "Contender": successo = 15 * win_mult
        elif goal_squadra == "Playoff Team": successo = 8
        elif goal_squadra == "Rising Star": successo = 5
        elif goal_squadra == "Rebuilding":
            # Rebuilding penalty is mitigated if they have a promising young core
            young_prospects = [p for p in squadra.roster if p.eta < 24 and p.potenziale >= 84]
            has_young_future = len(young_prospects) >= 2 or any(p.eta < 23 and p.potenziale >= 87 for p in squadra.roster)
            penalty = 3 if has_young_future else 15
            successo = -penalty * win_mult
        elif goal_squadra == "Mediocre": successo = -10 * win_mult

        # 6. Ambition/Age Factor
        eta = 0.0
        if giocatore.eta < 28 and giocatore.ovr >= 85: eta = -10
        elif giocatore.eta > 32: eta = 10

        # 7. Desperation Factor (Linear controlled curve, max +15 at day 12)
        disperazione = min(15.0, (self.current_day - 1) * 1.35)

        # Summed in the same order as before, so the floating-point total is unchanged
        parti = [("base", 50.0), ("money", soldi), ("money_bonus", pallone), ("morale", morale), ("stars", stelle), ("role", ruolo),
                 ("team_state", successo), ("age", eta), ("market_day", disperazione)]
        grezzo = 0.0
        for _, valore in parti:
            grezzo += valore
        return {"rejected": None, "value": valore_mercato_base, "parts": [{"key": k, "value": v} for k, v in parti],
                "raw": grezzo, "total": max(0, min(100, grezzo))}

    def anteprima_offerta(self, player_name: str, salary: float, years: int, option_type: str = "None", raise_pct: float = 0.05) -> dict:
        """What an offer from the user would do, without making it: allowed or why not, the player's score for it and
        the race it would join."""
        giocatore = next((p for p in self.unrestricted_free_agents if p.nome == player_name), None)
        if giocatore is None:
            return {"allowed": False, "tool": None, "reason": f"{player_name} is no longer on the market.", "total_value": 0.0,
                    "score": None, "race": None}
        allowed, tool_or_reason = self.check_user_offer_validity(player_name, salary, years)
        total, cur = 0.0, salary
        for _ in range(max(1, years)):
            total += round(cur, 2)
            cur *= (1.0 + raise_pct)
        user_team = self.squadra_giocatore
        offer = {"team": user_team.nome, "salary": salary, "years": years, "option_type": option_type, "raise_pct": raise_pct}
        return {
            "allowed": allowed,
            "tool": tool_or_reason if allowed else None,
            "reason": None if allowed else tool_or_reason,
            "total_value": round(total, 2),
            "score": self.dettaglio_punteggio(giocatore, user_team, salary, option_type),
            "race": self.classifica_offerte(giocatore, extra_offer=offer),
        }

    def soglia_firma(self, giocatore: 'Giocatore', day: int) -> float:
        """The score an offer needs on a given night for the player to sign (the bar decays day by day)."""
        soglia = max(15.0, 75.0 - (day - 1) * 5.5)
        if giocatore.ovr > 85:
            soglia += 5
        elif giocatore.ovr < 75:
            soglia -= 10
        soglia -= (75 - giocatore.morale) * 0.2
        return max(10.0, soglia)

    def classifica_offerte(self, giocatore: 'Giocatore', extra_offer: Optional[dict] = None) -> dict:
        """The offers on the table for a player, scored as tonight's resolution scores them.

        extra_offer stands in for the user's offer (a preview); nothing is stored."""
        offerte = []
        user_name = self.squadra_giocatore.nome if self.squadra_giocatore else None
        user_offer = extra_offer if extra_offer is not None else self.user_offers.get(giocatore.nome)
        if user_offer:
            offerte.append(user_offer)
        ritirate = [o for o in self.ai_offers.get(giocatore.nome, []) if o.get("withdrawn")]
        offerte.extend(o for o in self.ai_offers.get(giocatore.nome, []) if not o.get("withdrawn"))
        offerte = [o for o in offerte if not self._pileup_blocked(self._team_by_name(o["team"]), giocatore, o.get("tool"))]

        scored = []
        for o in offerte:
            team_obj = next(s for s in self.squadre if s.nome == o["team"])
            score = self._calcola_punteggio_accettazione_cached(giocatore, team_obj, o["salary"], option_type=o.get("option_type", "None"))
            scored.append({"team": o["team"], "salary": o["salary"], "years": o.get("years"),
                           "option_type": o.get("option_type", "None"), "score": score, "is_user": o["team"] == user_name,
                           "previous_team_bonus": False, "loyalty_bonus": 0.0, "offer": o,
                           **({"first": o["first"]} if o.get("first") else {}),
                           **({"history": list(o["history"])} if o.get("history") else {})})
        scored.sort(key=lambda x: (x["score"], x["salary"]), reverse=True)   # same score (e.g. capped at 100): more money leads

        day = self.current_day
        race = {"offers": scored, "leader": None, "leader_score": 0.0, "bar_tonight": self.soglia_firma(giocatore, day),
                "bar_tomorrow": self.soglia_firma(giocatore, day + 1) if day < CONFIG.OFFSEASON.FREE_AGENCY_DAYS else None,
                "would_sign_with": None,
                "withdrawn": [{"team": o["team"], "salary": o["salary"], "years": o.get("years"),
                               "day": o["withdrawn"]["day"], "reason": o["withdrawn"]["reason"]} for o in ritirate]}
        if scored:
            best = scored[0]
            leader_score = best["score"]
            # The old team's loyalty (contracts.loyalty, earned with seasons and morale): only on the offer that
            # already leads, as the resolution applies it
            prev_team = self.squadre_precedenti.get(giocatore.nome)
            if prev_team and best["team"] == prev_team.nome:
                bonus = loyalty(giocatore, prev_team)
                leader_score += bonus
                best["previous_team_bonus"] = True
                best["loyalty_bonus"] = bonus
            race.update(leader=best["team"], leader_score=leader_score,
                        would_sign_with=best["team"] if leader_score >= race["bar_tonight"] else None)
        return race

    def _team_by_name(self, nome: str) -> 'Squadra':
        return next(s for s in self.squadre if s.nome == nome)

    def _determina_limite_spesa_owner(self, squadra: 'Squadra') -> float:
        tier = owner_spending_tier(squadra.personalita_proprietario)
        if tier == "low":
            return self.torneo.luxury_tax_threshold + CONFIG.ECONOMY.LOW_OWNER_OVER_TAX_SHARE * self.torneo.salary_cap
        elif tier == "mid":
            return self.torneo.first_apron + 30
        else:
            return self.torneo.second_apron + 50

