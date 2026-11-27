import random
from typing import Tuple, Optional, Dict, Any
from copy import copy

from .models import Squadra, Giocatore, Abilita, Tendenze
from .config import CONFIG

class Partita:
    # __init__ and the setup methods remain almost identical
    def __init__(self, squadra_casa: Squadra, squadra_ospite: Squadra, is_playoff: bool = False, enable_play_log: bool = False, rivalry_intensity: float = 0.0):
        self.squadra_casa = squadra_casa
        self.squadra_ospite = squadra_ospite
        self.is_playoff = is_playoff
        self.rivalry_intensity = rivalry_intensity
        
        # Ensure all rostered players point to the correct match team
        for p in self.squadra_casa.roster:
            p.squadra = self.squadra_casa
        for p in self.squadra_ospite.roster:
            p.squadra = self.squadra_ospite
            
        self.punteggio = {squadra_casa.nome: 0, squadra_ospite.nome: 0}
        self.punteggi_quarti = {squadra_casa.nome: [], squadra_ospite.nome: []}
        self.ultimo_evento = ""
        self.log = [] 
        self.tempo_rimanente_secondi: int = 0
        self.quarto_attuale: int = 0
        self.secondi_totali_giocati: int = 0
        self.secondi_dall_ultimo_check_sost: int = 0
        # NBA TV Play-by-Play logging
        self.enable_play_log = enable_play_log
        self.play_log = []  # Persistent log for all game events
        self.momentum: float = 50.0  # 0 to 100
        self.current_run_team: Optional[str] = None
        self.current_run_points: int = 0
        self.team_fouls_quarter: Dict[str, int] = {squadra_casa.nome: 0, squadra_ospite.nome: 0}

        
        # Precomputed cached simulation constants
        from .models import ACTIVE_TOURNAMENT
        self.pace_factor = ACTIVE_TOURNAMENT.get_era_pace_factor() if ACTIVE_TOURNAMENT else 1.0
        anno = ACTIVE_TOURNAMENT.anno_corrente if ACTIVE_TOURNAMENT else 2002
        self.anno_corrente = anno
        era = CONFIG.ERA
        ratio = min(1.0, max(0.0, (anno - era.START_YEAR) / (era.END_YEAR - era.START_YEAR)))
        lerp = lambda pair: pair[0] + (pair[1] - pair[0]) * ratio
        self._era_p_foul_chance = lerp(era.PERIMETER_FOUL_CHANCE)
        self._era_draw_mult = lerp(era.DRAW_FOUL_MULT)
        self._era_drive_foul_mult = lerp(era.DRIVE_FOUL_MULT)
        self._era_speed_foul_mult = lerp(era.SPEED_FOUL_MULT)
        three_make, close_make, ft_boost = era.THREE_MAKE_BASE, era.CLOSE_MAKE_BASE, era.FT_BOOST
        if ACTIVE_TOURNAMENT and ACTIVE_TOURNAMENT.is_modern_start():
            three_make = (three_make[0], era.MODERN_START_THREE_MAKE_END)
            close_make = (close_make[0], era.MODERN_START_CLOSE_MAKE_END)
            ft_boost = (ft_boost[0], era.MODERN_START_FT_BOOST_END)
        self._era_prob_3pt_base = lerp(three_make)
        self._era_prob_close_base = lerp(close_make)
        self._era_ft_boost = lerp(ft_boost)
        self._era_assist_base = lerp(era.ASSIST_BASE)
        self._era_center_focus_mult = lerp(era.CENTER_FOCUS_MULT)
        self._era_post_elite_mult = lerp(era.POST_UP_ELITE_MULT)
        self._era_post_sub_mult = lerp(era.POST_UP_SUB_MULT)
        self._era_center_reb_boost = lerp(era.CENTER_REBOUND_ERA_BOOST)
        self._era_steal_mult = lerp(era.STEAL_MULT)
        self._era_unforced_tov_mult = lerp(era.UNFORCED_TURNOVER_MULT)

        poe_casa = CONFIG.COACHINGTACTICS.POINTS_OF_EMPHASIS.get(getattr(squadra_casa, 'active_poe', 'Balanced Approach'), {})
        self.fatigue_mod_casa = poe_casa.get("logic_mods", {}).get("fatigue_increase_modifier", 1.0)
        poe_ospite = CONFIG.COACHINGTACTICS.POINTS_OF_EMPHASIS.get(getattr(squadra_ospite, 'active_poe', 'Balanced Approach'), {})
        self.fatigue_mod_ospite = poe_ospite.get("logic_mods", {}).get("fatigue_increase_modifier", 1.0)
        self._accumulated_bench_seconds = 0
        self._tempo_frazionario: float = 0.0

        # Coach Tactical System Fit tracking
        self.tactical_fit_casa = squadra_casa.coach.calcola_roster_fit(squadra_casa) if getattr(squadra_casa, 'coach', None) else {"net_rating_mod": 0.0, "fit_score": 70}
        self.tactical_fit_ospite = squadra_ospite.coach.calcola_roster_fit(squadra_ospite) if getattr(squadra_ospite, 'coach', None) else {"net_rating_mod": 0.0, "fit_score": 70}

        self._applica_effetti_coach()

    def _get_tactical_fit(self, squadra: Squadra) -> Dict[str, Any]:
        """Returns realistic tactical scheme fit metrics for a squad's head coach and roster."""
        if squadra == self.squadra_casa:
            return self.tactical_fit_casa
        return self.tactical_fit_ospite

    def _get_coach_mods(self, squadra: Squadra) -> Dict[str, Any]:
        """Compatibility accessor returning tactical fit data."""
        return self._get_tactical_fit(squadra)

    def _resetta_temp_valori_giocatore(self, giocatore: Giocatore):
        cfg_stamina = CONFIG.SYNTHETICSTAMINA
        STAT_HARD_CAP = 97
        
        giocatore.temp_abilita = Abilita(**vars(giocatore.abilita))
        giocatore.temp_tendenze = Tendenze(**vars(giocatore.tendenze))

        stamina = float(cfg_stamina.BASE_STAMINA)
        if giocatore.eta > cfg_stamina.AGE_PENALTY_THRESHOLD:
            stamina -= (giocatore.eta - cfg_stamina.AGE_PENALTY_THRESHOLD) * cfg_stamina.AGE_PENALTY_PER_YEAR
        stamina += cfg_stamina.ROLE_MODIFIER.get(giocatore.ruolo, 0)
        atletismo_medio = (giocatore.abilita.speed + giocatore.abilita.acceleration) / 2
        stamina += (atletismo_medio - 80) * cfg_stamina.ATHLETICISM_IMPACT_FACTOR
        giocatore.temp_abilita.stamina = int(max(60, min(99, stamina)))

        squadra = giocatore.squadra
        if squadra and squadra.coach:
            stile = CONFIG.COACHINGSTYLES.STYLES.get(squadra.coach.stile_gioco, {})
            mod_abilita = stile.get("abilita", {})
            for abilita, bonus in mod_abilita.items():
                valore_base = getattr(giocatore.temp_abilita, abilita)
                if bonus > 0:
                    if valore_base >= 92:
                        bonus_effettivo = max(1, round(bonus * 0.30))
                    elif valore_base >= 85:
                        bonus_effettivo = max(1, round(bonus * 0.50))
                    else:
                        bonus_effettivo = bonus
                else:
                    bonus_effettivo = bonus
                nuovo_valore = min(STAT_HARD_CAP, valore_base + bonus_effettivo)
                setattr(giocatore.temp_abilita, abilita, nuovo_valore)
            
            mod_tendenze = stile.get("tendenze", {})
            for tendenza, moltiplicatore in mod_tendenze.items():
                setattr(giocatore.temp_tendenze, tendenza, min(99, round(getattr(giocatore.temp_tendenze, tendenza) * moltiplicatore)))

            coach_badges = getattr(squadra.coach, 'badges', None)
            if coach_badges:
                for badge_name, badge_level in coach_badges.items():
                    if badge_level <= 0: continue
                    if badge_name == "Rookie Developer" and giocatore.eta <= 23:
                        giocatore.temp_abilita.offensive_iq_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.offensive_iq_rating + badge_level)
                        giocatore.temp_abilita.defensive_iq_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.defensive_iq_rating + badge_level)
                        giocatore.temp_abilita.shot_iq = min(STAT_HARD_CAP, giocatore.temp_abilita.shot_iq + badge_level)
                    elif badge_name == "Defense Guru":
                        giocatore.temp_abilita.interior_defense_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.interior_defense_rating + badge_level)
                        giocatore.temp_abilita.perimeter_defense_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.perimeter_defense_rating + badge_level)
                    elif badge_name == "Tactician":
                        giocatore.temp_abilita.three_point_shot_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.three_point_shot_rating + badge_level)
                        giocatore.temp_abilita.mid_range_shot_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.mid_range_shot_rating + badge_level)
                    elif badge_name == "Fitness Specialist":
                        giocatore.temp_abilita.stamina = min(99, giocatore.temp_abilita.stamina + (badge_level * 2))
                    elif badge_name == "Motivator":
                        giocatore.morale = min(100, giocatore.morale + (badge_level * 5))

            # Coach RPG System Modifiers Integration
            c_mods = self._get_coach_mods(squadra)
            off_delta = int(round(c_mods.get("off_rating_delta", 0.0)))
            def_delta = int(round(c_mods.get("def_rating_delta", 0.0)))
            if off_delta != 0:
                giocatore.temp_abilita.offensive_iq_rating = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.offensive_iq_rating + off_delta))
                giocatore.temp_abilita.shot_iq = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.shot_iq + off_delta))
            if def_delta != 0:
                giocatore.temp_abilita.defensive_iq_rating = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.defensive_iq_rating + def_delta))
                giocatore.temp_abilita.perimeter_defense_rating = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.perimeter_defense_rating + def_delta))
                giocatore.temp_abilita.interior_defense_rating = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.interior_defense_rating + def_delta))

            if c_mods.get("has_pace_space", False):
                giocatore.temp_abilita.three_point_shot_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.three_point_shot_rating + 2)
                giocatore.temp_abilita.speed = min(STAT_HARD_CAP, giocatore.temp_abilita.speed + 1)

        if squadra:
            intesa_val = getattr(squadra, 'intesa', 70)
            intesa_mod = 2 if intesa_val >= 85 else (1 if intesa_val >= 75 else (-3 if intesa_val <= 40 else (-1 if intesa_val <= 60 else 0)))
            morale_val = getattr(giocatore, 'morale', 50)
            morale_mod = 2 if morale_val >= 90 else (1 if morale_val >= 75 else (-2 if morale_val <= 25 else (-1 if morale_val <= 40 else 0)))

            tp = getattr(squadra, 'tactical_plan', None)
            if tp:
                if tp.offensive_focus == "HUNT_THREES":
                    giocatore.temp_abilita.three_point_shot_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.three_point_shot_rating + 3)
                elif tp.offensive_focus == "POUND_PAINT":
                    giocatore.temp_abilita.close_shot_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.close_shot_rating + 3)
                elif tp.offensive_focus == "PACE_AND_SPACE_5OUT":
                    giocatore.temp_abilita.speed = min(STAT_HARD_CAP, giocatore.temp_abilita.speed + 2)
                    giocatore.temp_abilita.three_point_shot_rating = min(STAT_HARD_CAP, giocatore.temp_abilita.three_point_shot_rating + 2)

            tot_iq_mod = intesa_mod + morale_mod
            if tot_iq_mod != 0:
                giocatore.temp_abilita.offensive_iq_rating = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.offensive_iq_rating + tot_iq_mod))
                giocatore.temp_abilita.defensive_iq_rating = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.defensive_iq_rating + tot_iq_mod))
                
            if intesa_mod != 0:
                giocatore.temp_abilita.passing_accuracy = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.passing_accuracy + intesa_mod))
                giocatore.temp_abilita.passing_vision = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.passing_vision + intesa_mod))

            if morale_mod != 0:
                giocatore.temp_abilita.shot_iq = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.shot_iq + morale_mod))
                giocatore.temp_abilita.free_throw_rating = max(40, min(STAT_HARD_CAP, giocatore.temp_abilita.free_throw_rating + morale_mod))
                giocatore.temp_abilita.three_point_shot_rating = max(25, min(STAT_HARD_CAP, giocatore.temp_abilita.three_point_shot_rating + morale_mod))
                giocatore.temp_abilita.mid_range_shot_rating = max(25, min(STAT_HARD_CAP, giocatore.temp_abilita.mid_range_shot_rating + morale_mod))
                giocatore.temp_abilita.close_shot_rating = max(25, min(STAT_HARD_CAP, giocatore.temp_abilita.close_shot_rating + morale_mod))
                giocatore.temp_abilita.perimeter_defense_rating = max(25, min(STAT_HARD_CAP, giocatore.temp_abilita.perimeter_defense_rating + morale_mod))
                giocatore.temp_abilita.interior_defense_rating = max(25, min(STAT_HARD_CAP, giocatore.temp_abilita.interior_defense_rating + morale_mod))

        # Rework v2.1: if the player takes the court with Day-to-Day status (infortunio_impatto > 0), he suffers an athletic/shooting handicap
        if getattr(giocatore, 'infortunio_impatto', 0.0) > 0:
            malus_factor = 1.0 - giocatore.infortunio_impatto
            for attr in ['speed', 'acceleration', 'vertical', 'close_shot_rating', 'mid_range_shot_rating', 'three_point_shot_rating', 'stamina']:
                val = getattr(giocatore.temp_abilita, attr, 75)
                setattr(giocatore.temp_abilita, attr, max(30, int(val * malus_factor)))

        # Precompute the base passive drain rate once per match (avoids exponentials ** 1.2 on every tick)
        stamina_effective = float(getattr(giocatore.temp_abilita, 'stamina', 75))
        stamina_modifier = max(0.5, (stamina_effective / 75.0) ** 1.2)
        base_drain = (1.5 / stamina_modifier) / 12.0
        if squadra:
            base_drain *= self._get_coach_mods(squadra).get("fatigue_preservation", 1.0)
        giocatore._base_passive_drain_rate = base_drain

    def _applica_effetti_coach(self):
        for squadra in [self.squadra_casa, self.squadra_ospite]:
            for giocatore in squadra.roster:
                self._resetta_temp_valori_giocatore(giocatore)

        if self.rivalry_intensity > 30:
            focus_boost = 1 if self.rivalry_intensity < 70 else 2
            for squadra in [self.squadra_casa, self.squadra_ospite]:
                for g in squadra.roster:
                    g.temp_abilita.shot_iq = min(98, g.temp_abilita.shot_iq + focus_boost)
                    g.temp_abilita.defensive_iq_rating = min(98, g.temp_abilita.defensive_iq_rating + focus_boost)

    def _generate_narrative_commentary(self, event_type: str, team: str, player: str, detail: str = "", assist_by: str = "", highlight_tag: str = None) -> str:
        """Generates rich contextual broadcast play-by-play commentary (TNT/ESPN/Sky style)."""
        score_diff = abs(self.punteggio[self.squadra_casa.nome] - self.punteggio[self.squadra_ospite.nome])
        is_clutch = (self.quarto_attuale >= 4 and self.tempo_rimanente_secondi <= 120 and score_diff <= 5)

        if highlight_tag == 'clutch_shot' or is_clutch and event_type == 'score':
            variants = [
                f"ICE IN HIS VEINS! {player} buries a cold-blooded bucket in the clutch!",
                f"CLUTCH BUCKET! {player} puts the team on his back and electrifies the crowd!",
                f"BIG TIME PLAY! {player} finds the bottom of the net under suffocating pressure!",
                f"CHAMPIONSHIP PEDIGREE! {player} delivers a dagger when it matters most!"
            ]
            return random.choice(variants)

        if highlight_tag == 'poster_dunk':
            variants = [
                f"POSTER TIME! {player} rises through traffic and throws down a thunderous slam!",
                f"WHAT A FLIGHT! {player} skies over the defense and brings down the house!",
                f"MONSTER JAM! {player} hammers it home with sheer power and authority!"
            ]
            return random.choice(variants)

        if highlight_tag == 'monster_block' or event_type == 'block':
            variants = [
                f"NOT IN MY HOUSE! Enormous rejection by {player} erasing the basket!",
                f"DEFENSIVE WALL! {player} protects the paint and sends that shot right back!",
                f"PAINT INTIMIDATION! {player} pins the ball against the glass with a spectacular swat!",
                f"REJECTION! {player} flies in from the weak side and rejects the shot!"
            ]
            return random.choice(variants)

        if event_type == 'score':
            assist_str = f" on a brilliant assist from {assist_by}" if assist_by else ""
            if '3PT' in detail or '3-pointer' in detail:
                variants = [
                    f"BANG! Quick catch-and-shoot triple from downtown for {player}{assist_str}!",
                    f"SPLASH! {player} finds daylight beyond the arc and punishes from the corner{assist_str}!",
                    f"NOTHING BUT NET! Pure three-point stroke by {player}{assist_str}!",
                    f"Daylight on the perimeter... {player} lets it fly and hits the bottom of the net{assist_str}!"
                ]
                return random.choice(variants)
            elif 'Free Throws' in detail:
                return f"{player} calm and steady at the charity stripe: {detail}."
            else:
                variants = [
                    f"Silky smooth pull-up jumper from mid-range by {player}{assist_str}.",
                    f"Aggressive drive to the cup by {player} for the easy finger roll{assist_str}.",
                    f"Textbook post pivot and soft touch finish by {player} in the paint{assist_str}.",
                    f"Two easy points in the books for {player}{assist_str}."
                ]
                return random.choice(variants)

        if event_type == 'steal':
            variants = [
                f"PICKPOCKET! {player} strips the ball and ignites the fastbreak!",
                f"STEAL! {player} jumps the passing lane and comes away with the rock!",
                f"Suffocating ball pressure by {player} forces the defensive takeaway!"
            ]
            return random.choice(variants)

        if event_type == 'turnover':
            variants = [
                f"Turnover by {player} under heavy defensive ball pressure.",
                f"Ball-handling miscue for {player}, possession lost for the {team}.",
                f"Errant pass by {player}, intercepted by the defense."
            ]
            return random.choice(variants)

        if event_type == 'rebound':
            return f"{player} pulls down the rebound for the {team}."

        if event_type == 'foul':
            return f"Whistle blows: personal foul called on {player} ({detail})."

        if event_type == 'miss':
            if '3PT' in detail or '3-pointer' in detail:
                return f"{player} attempts the three-pointer, but it rims in and out."
            return f"{player}'s shot falls off the mark, denied by the rim."

        return f"{player} ({team}): {detail}"

    def _log_play(self, event_type: str, team: str, player: str, detail: str = "", assist_by: str = "", highlight_override: str = None):
        """Log a rich play event for NBA TV play-by-play. Only active when enable_play_log is True."""
        if not self.enable_play_log:
            return
        
        # Format time as MM:SS
        minutes = self.tempo_rimanente_secondi // 60
        seconds = self.tempo_rimanente_secondi % 60
        time_str = f"{minutes}:{seconds:02d}"

        # Momentum calculation (0 = 100% Away, 50 = Neutral, 100 = 100% Home)
        is_home = (team == self.squadra_casa.nome)
        if event_type == 'score':
            pts = 2
            if '3PT' in detail or '3-pointer' in detail:
                pts = 3
            elif 'Free Throws' in detail:
                try:
                    pts = int(detail.split()[2].split('/')[0])
                except Exception:
                    pts = 1
            
            # Update scoring run
            if self.current_run_team == team:
                self.current_run_points += pts
            else:
                self.current_run_team = team
                self.current_run_points = pts

            if is_home:
                self.momentum = min(100.0, self.momentum + (pts * 2.2))
            else:
                self.momentum = max(0.0, self.momentum - (pts * 2.2))
        elif event_type in ['steal', 'block']:
            if is_home:
                self.momentum = min(100.0, self.momentum + 3.5)
            else:
                self.momentum = max(0.0, self.momentum - 3.5)
        else:
            # Gradual natural decay towards neutral 50
            self.momentum += (50.0 - self.momentum) * 0.04

        # Highlight detection
        highlight_tag = highlight_override
        if not highlight_tag:
            if event_type == 'score':
                score_diff = abs(self.punteggio[self.squadra_casa.nome] - self.punteggio[self.squadra_ospite.nome])
                if (self.quarto_attuale >= 4 or self.quarto_attuale > 4) and self.tempo_rimanente_secondi <= 120 and score_diff <= 5:
                    highlight_tag = 'clutch_shot'
                elif '3PT' in detail or '3-pointer' in detail:
                    if random.random() < 0.25:
                        highlight_tag = 'deep_three'
                elif 'Dunk' in detail or 'schiacciata' in detail.lower():
                    highlight_tag = 'poster_dunk'
                elif assist_by and random.random() < 0.25:
                    highlight_tag = 'fastbreak'
            elif event_type == 'block':
                highlight_tag = 'monster_block'

        # Narrative commentary generator
        commentary = self._generate_narrative_commentary(event_type, team, player, detail, assist_by, highlight_tag)

        play_event = {
            'quarter': self.quarto_attuale,
            'time': time_str,
            'event_type': event_type,  # 'score', 'miss', 'block', 'steal', 'rebound', 'turnover', 'foul'
            'team': team,
            'player': player,
            'detail': detail,
            'assist_by': assist_by,
            'highlight_tag': highlight_tag,
            'momentum': round(self.momentum, 1),
            'run_info': f"{self.current_run_points}-0 run for {team}" if self.current_run_points >= 6 else None,
            'commentary': commentary,
            'score': {
                self.squadra_casa.nome: self.punteggio[self.squadra_casa.nome],
                self.squadra_ospite.nome: self.punteggio[self.squadra_ospite.nome]
            }
        }
        self.play_log.append(play_event)

    def _get_player_team(self, giocatore: Optional[Giocatore]) -> Squadra:
        """Robustly returns the Squadra object for this player in the current match context."""
        if not giocatore:
            return self.squadra_casa
        sq = getattr(giocatore, 'squadra', None)
        if sq:
            if sq.nome == self.squadra_casa.nome:
                return self.squadra_casa
            if sq.nome == self.squadra_ospite.nome:
                return self.squadra_ospite
        if giocatore in self.squadra_ospite.roster or giocatore in getattr(self.squadra_ospite, 'in_campo', []):
            giocatore.squadra = self.squadra_ospite
            return self.squadra_ospite
        giocatore.squadra = self.squadra_casa
        return self.squadra_casa

    def squadra_avversaria(self, squadra: Optional[Squadra]) -> Squadra:
        if not squadra:
            return self.squadra_ospite
        return self.squadra_ospite if squadra.nome == self.squadra_casa.nome else self.squadra_casa


    def gioca(self) -> Tuple[int, int]:
        overtime_count = 0
        MAX_OVERTIMES = 5
        
        # Ensure strict synchronization of roster player team pointers
        for p in self.squadra_casa.roster:
            p.squadra = self.squadra_casa
        for p in self.squadra_ospite.roster:
            p.squadra = self.squadra_ospite
            
        self.squadra_casa.reset_for_game(); self.squadra_ospite.reset_for_game()
        self.starters = {
            self.squadra_casa.nome: set(p.nome for p in self.squadra_casa.quintetto),
            self.squadra_ospite.nome: set(p.nome for p in self.squadra_ospite.quintetto)
        }
        
        # Team-wide form modifiers representing collective momentum/shooting form/travel fatigue.
        # Introduces game-to-game variance (upset potentials and blowouts).
        team_casa_mod = random.choices(
            population=[-0.07, -0.03, 0.0, 0.03, 0.07],
            weights=[12, 18, 40, 18, 12],
            k=1
        )[0]
        team_ospite_mod = random.choices(
            population=[-0.07, -0.03, 0.0, 0.03, 0.07],
            weights=[12, 18, 40, 18, 12],
            k=1
        )[0]

        for g in self.squadra_casa.roster:
            p_factor = random.choices(
                population=[random.uniform(0.85, 0.93),  # Cold night
                            random.uniform(0.94, 1.05),  # Normal night
                            random.uniform(1.06, 1.12)], # Hot night
                weights=[20, 65, 15],
                k=1
            )[0]
            g.game_form_factor = max(0.70, min(1.25, p_factor + team_casa_mod))
            
            # Apply form impact to temporary in-game stats (Shot IQ, Defense IQ, Speed) to match hot/cold night hustle
            if g.game_form_factor >= 1.05:
                g.temp_abilita.shot_iq = min(97, g.temp_abilita.shot_iq + 2)
                g.temp_abilita.defensive_iq_rating = min(97, g.temp_abilita.defensive_iq_rating + 2)
                g.temp_abilita.speed = min(97, g.temp_abilita.speed + 1)
            elif g.game_form_factor <= 0.93:
                g.temp_abilita.shot_iq = max(50, g.temp_abilita.shot_iq - 2)
                g.temp_abilita.defensive_iq_rating = max(50, g.temp_abilita.defensive_iq_rating - 2)
                g.temp_abilita.speed = max(50, g.temp_abilita.speed - 1)

        for g in self.squadra_ospite.roster:
            p_factor = random.choices(
                population=[random.uniform(0.85, 0.93),  # Cold night
                            random.uniform(0.94, 1.05),  # Normal night
                            random.uniform(1.06, 1.12)], # Hot night
                weights=[20, 65, 15],
                k=1
            )[0]
            g.game_form_factor = max(0.70, min(1.25, p_factor + team_ospite_mod))
            
            # Apply form impact to temporary in-game stats
            if g.game_form_factor >= 1.05:
                g.temp_abilita.shot_iq = min(97, g.temp_abilita.shot_iq + 2)
                g.temp_abilita.defensive_iq_rating = min(97, g.temp_abilita.defensive_iq_rating + 2)
                g.temp_abilita.speed = min(97, g.temp_abilita.speed + 1)
            elif g.game_form_factor <= 0.93:
                g.temp_abilita.shot_iq = max(50, g.temp_abilita.shot_iq - 2)
                g.temp_abilita.defensive_iq_rating = max(50, g.temp_abilita.defensive_iq_rating - 2)
                g.temp_abilita.speed = max(50, g.temp_abilita.speed - 1)

        self.squadra_casa.partita = self; self.squadra_ospite.partita = self
        possesso_casa, punteggio_prec_casa, punteggio_prec_ospite = random.choice([True, False]), 0, 0
        
        for quarto in range(1, CONFIG.SIM.QUARTERS + 1):
            self.quarto_attuale = quarto
            self.tempo_rimanente_secondi = 12 * 60
            possesso_casa = self._simula_quarto(possesso_casa)
            self._recupero_fine_quarto()
            punti_q_casa = self.punteggio[self.squadra_casa.nome] - punteggio_prec_casa
            punti_q_ospite = self.punteggio[self.squadra_ospite.nome] - punteggio_prec_ospite
            self.punteggi_quarti[self.squadra_casa.nome].append(punti_q_casa)
            self.punteggi_quarti[self.squadra_ospite.nome].append(punti_q_ospite)
            punteggio_prec_casa, punteggio_prec_ospite = self.punteggio[self.squadra_casa.nome], self.punteggio[self.squadra_ospite.nome]
        
        while self.punteggio[self.squadra_casa.nome] == self.punteggio[self.squadra_ospite.nome] and overtime_count < MAX_OVERTIMES:
            self.quarto_attuale += 1
            overtime_count += 1
            self.log.append(f"--- START OF OVERTIME #{overtime_count} ---")
            
            self.tempo_rimanente_secondi = 5 * 60
            self._recupero_fine_quarto(is_overtime=True)
            possesso_casa = self._simula_quarto(possesso_casa)
            
            # Track overtime quarters
            punti_q_casa = self.punteggio[self.squadra_casa.nome] - punteggio_prec_casa
            punti_q_ospite = self.punteggio[self.squadra_ospite.nome] - punteggio_prec_ospite
            self.punteggi_quarti[self.squadra_casa.nome].append(punti_q_casa)
            self.punteggi_quarti[self.squadra_ospite.nome].append(punti_q_ospite)
            punteggio_prec_casa, punteggio_prec_ospite = self.punteggio[self.squadra_casa.nome], self.punteggio[self.squadra_ospite.nome]
        
        # If we leave the loop because of MAX_OVERTIMES, we must force a winner.
        if self.punteggio[self.squadra_casa.nome] == self.punteggio[self.squadra_ospite.nome]:
            self.log.append(f"WARNING: Game concluded due to maximum overtime limit ({MAX_OVERTIMES}). Victory awarded.")
            # Simple solution: the home team wins by one point.
            # You could also use the playoff seed, the season record, etc.
            self.punteggio[self.squadra_casa.nome] += 1
            # Add the point to the last quarter/overtime so the totals match
            self.punteggi_quarti[self.squadra_casa.nome][-1] += 1

        self._finalizza_partita()
        return self.punteggio[self.squadra_casa.nome], self.punteggio[self.squadra_ospite.nome]

    def _simula_quarto(self, possesso_casa: bool) -> bool:
        # Reset team fouls for the quarter (NBA bonus triggers after 4 team fouls in a quarter)
        self.team_fouls_quarter = {self.squadra_casa.nome: 0, self.squadra_ospite.nome: 0}
        while self.tempo_rimanente_secondi > 0:
            squadra_att, squadra_dif = (self.squadra_casa, self.squadra_ospite) if possesso_casa else (self.squadra_ospite, self.squadra_casa)
            
            if not squadra_att.giocatori_in_campo():
                possesso_casa = not possesso_casa
                continue

            mantiene_possesso = self._simula_possesso(squadra_att, squadra_dif)
            
            if not mantiene_possesso:
                possesso_casa = not possesso_casa
                
            if self.secondi_dall_ultimo_check_sost >= CONFIG.COACHING.SUBSTITUTION_CHECK_INTERVAL_SECONDS:
                # Garbage time check: 4th quarter, under 4 minutes remaining, >= 24 point blowout
                if self.quarto_attuale >= 4 and self.tempo_rimanente_secondi <= 240:
                    diff = abs(self.punteggio[self.squadra_casa.nome] - self.punteggio[self.squadra_ospite.nome])
                    if diff >= 24:
                        self.squadra_casa._gestisci_garbage_time()
                        self.squadra_ospite._gestisci_garbage_time()
                self._gestisci_sostituzioni()
                self.secondi_dall_ultimo_check_sost = 0 
            
        return possesso_casa

    def _applica_recupero_panchina(self):
        """Applies in batch the energy/fatigue recovery accumulated by the bench players during the game."""
        if getattr(self, '_accumulated_bench_seconds', 0) <= 0:
            return
        sec = self._accumulated_bench_seconds
        self._accumulated_bench_seconds = 0
        sec_div_12 = sec / 12.0
        sec_recovery = 0.5 * sec_div_12
        sec_fatigue_rec = 0.3 * sec_div_12
        for squad in (self.squadra_casa, self.squadra_ospite):
            for g in squad.panchina:
                g.secondi_in_panchina_consecutivi += sec
                g.energia = min(g.energia_iniziale, g.energia + sec_recovery)
                g.fatica = max(0, g.fatica - sec_fatigue_rec)
            for g in squad.quintetto:
                g.secondi_in_panchina_consecutivi = 0

    def _is_clutch_now(self) -> bool:
        """Clutch time for the stats (NBA definition, CONFIG.ANALYTICS): 4th quarter or overtime, last minutes, close score."""
        a = CONFIG.ANALYTICS
        if self.quarto_attuale < 4 or self.tempo_rimanente_secondi > a.CLUTCH_LAST_SECONDS:
            return False
        return abs(self.punteggio[self.squadra_casa.nome] - self.punteggio[self.squadra_ospite.nome]) <= a.CLUTCH_MARGIN

    def _aggiorna_tempo_possesso(self, secondi_consumati: int):
        if secondi_consumati <= 0: return

        # Scale the consumed time by the era's pace (pace_factor) with decimal accumulation
        if self.pace_factor > 0 and self.pace_factor != 1.0:
            tempo_effettivo = (secondi_consumati / self.pace_factor) + getattr(self, '_tempo_frazionario', 0.0)
            sec_da_consumare = int(tempo_effettivo)
            self._tempo_frazionario = tempo_effettivo - sec_da_consumare
            secondi_consumati = sec_da_consumare

        secondi_consumati = min(secondi_consumati, self.tempo_rimanente_secondi)
        if secondi_consumati <= 0: return

        clutch = self._is_clutch_now()  # the state these seconds were played in
        self.tempo_rimanente_secondi -= secondi_consumati
        self.secondi_totali_giocati += secondi_consumati
        self.secondi_dall_ultimo_check_sost += secondi_consumati
        self._accumulated_bench_seconds += secondi_consumati

        # Passive energy drain ONLY for the players on the court using the precomputed rate
        for squad, f_mod in ((self.squadra_casa, self.fatigue_mod_casa), (self.squadra_ospite, self.fatigue_mod_ospite)):
            for giocatore in squad.giocatori_in_campo():
                giocatore.game_stats.secondi_giocati += secondi_consumati
                if clutch:
                    giocatore.game_stats.clutch_sec += secondi_consumati
                drain_rate = getattr(giocatore, '_base_passive_drain_rate', 0.125)
                passive_drain = drain_rate * secondi_consumati * f_mod
                giocatore.energia = max(0, giocatore.energia - passive_drain)
                giocatore.fatica = min(100, giocatore.fatica + (passive_drain * 0.3))

    # --- Score-or-pass choices (CONFIG.PLAYMAKING): continuous weights of the player, no hard thresholds ---
    @staticmethod
    def _drive_dish_chance(p) -> float:
        """Chance (0-100) that a driver who beat his man with no help passes to a big or a cutter instead of finishing."""
        cfg = CONFIG.PLAYMAKING
        t, a = p.temp_tendenze, p.temp_abilita
        close_skill = max(getattr(a, 'close_shot_rating', 50), getattr(a, 'dunk_rating', 50))
        chance = (getattr(t, 'playmaking_tendency', 50) * cfg.DRIVE_DISH_PLAY
                  + getattr(t, 'dish_to_open_man_tendency', 50) * cfg.DRIVE_DISH_DISH
                  + (getattr(a, 'passing_vision', 50) - 50) * cfg.DRIVE_DISH_VISION
                  - getattr(t, 'hero_ball_tendency', 50) * cfg.DRIVE_DISH_HERO
                  - max(0.0, getattr(t, 'touch_tendency', 50) - cfg.DRIVE_DISH_TOUCH_FROM) * cfg.DRIVE_DISH_TOUCH
                  - max(0.0, close_skill - cfg.DRIVE_DISH_FINISHER_FROM) * cfg.DRIVE_DISH_FINISHER
                  - cfg.DRIVE_DISH_OFFSET)
        return max(0.0, min(cfg.DRIVE_DISH_MAX, chance))

    @staticmethod
    def _kickout_chance(p) -> float:
        """Chance (15-90) that a driver met by a help defender kicks it out instead of forcing it at the rim."""
        cfg = CONFIG.PLAYMAKING
        t, a = p.temp_tendenze, p.temp_abilita
        close_skill = max(getattr(a, 'close_shot_rating', 50), getattr(a, 'dunk_rating', 50))
        chance = (getattr(a, 'passing_vision', 50) * 0.35 + getattr(t, 'pass_out_of_shot_tendency', 50) * 0.35
                  + getattr(t, 'playmaking_tendency', 50) * 0.30)
        if close_skill >= 78:   # elite finishers (LeBron, Giannis, Wade) go all the way more often
            chance -= (close_skill - 75) * 1.1
        chance -= max(0.0, getattr(t, 'hero_ball_tendency', 50) - cfg.KICKOUT_HERO_FROM) * cfg.KICKOUT_HERO
        return max(15.0, min(90.0, chance))

    @staticmethod
    def _extra_pass_chance(p, open_look: bool) -> float:
        """Chance (0-100) that a perimeter player who just got the ball swings it on instead of shooting."""
        cfg = CONFIG.PLAYMAKING
        a = p.temp_abilita
        three, mid = getattr(a, 'three_point_shot_rating', 50), getattr(a, 'mid_range_shot_rating', 50)
        vision = getattr(a, 'passing_vision', 50)
        chance = 40 + vision * 0.15
        if three < 70 and mid < 72:
            chance += 15
        if open_look:
            best_shot = max(three, mid - 2)
            malus = min(cfg.EXTRA_PASS_MAX, max(0.0, best_shot - cfg.EXTRA_PASS_SHOOTER_FROM) * cfg.EXTRA_PASS_PER_POINT)
            relief = min(cfg.EXTRA_PASS_VISION_RELIEF_MAX,
                         max(0.0, vision - cfg.EXTRA_PASS_VISION_FROM) * cfg.EXTRA_PASS_VISION_RELIEF)
            chance -= malus * (1.0 - relief)
        return max(0.0, min(100.0, chance))

    @staticmethod
    def _drop_pull_up_share(handler) -> Optional[float]:
        """Share of DROP pick and rolls the handler keeps for a pull-up (the rest go to the roller); None when he is
        neither a shooter nor a playmaker (CONFIG.PLAYMAKING.DROP_SKILL_FLOOR)."""
        import math
        cfg = CONFIG.PLAYMAKING
        t, a = handler.temp_tendenze, handler.temp_abilita
        shot = max(getattr(a, 'three_point_shot_rating', 50), getattr(a, 'mid_range_shot_rating', 50))
        play = getattr(t, 'playmaking_tendency', 50)
        if shot < cfg.DROP_SKILL_FLOOR and play < cfg.DROP_SKILL_FLOOR:
            return None
        keep = shot + getattr(t, 'hero_ball_tendency', 50) * cfg.DROP_HERO
        give = play * cfg.DROP_PLAY + getattr(a, 'passing_vision', 50) * cfg.DROP_VISION
        share = 1.0 / (1.0 + math.exp(-(keep - give) / cfg.DROP_SCALE))
        return max(cfg.DROP_SHARE_MIN, min(cfg.DROP_SHARE_MAX, share))

    @staticmethod
    def _initiation_factor(p) -> float:
        """How much a player's skills (and, less, his PG/SG label) make him the one who starts a possession (>= 1)."""
        cfg = CONFIG.PLAYMAKING
        t, a = p.temp_tendenze, p.temp_abilita
        vision, handling = getattr(a, 'passing_vision', 50), getattr(a, 'ball_handling', 50)
        play = getattr(t, 'playmaking_tendency', 50)
        skill = vision * 0.40 + handling * 0.30 + getattr(a, 'shot_iq', 50) * 0.15 + play * 0.15
        creator = handling * 0.4 + vision * 0.4 + play * 0.2
        ramp = max(0.0, min(1.0, (creator - cfg.INIT_CREATOR_FROM) / (cfg.INIT_CREATOR_TO - cfg.INIT_CREATOR_FROM)))
        return (1.0 + skill / 130.0) * (1.0 + cfg.INIT_CREATOR_MAX * ramp) * cfg.INIT_LABEL.get(getattr(p, 'ruolo', ''), 1.0)

    @staticmethod
    def _volume_tax(fga: int, interior: bool) -> float:
        """Points of make chance a shooter loses for the shots he has already taken in this game (>= 0)."""
        cfg = CONFIG.PLAYMAKING
        tax = max(0, min(fga, cfg.VOLUME_TAX_HIGH_FROM) - cfg.VOLUME_TAX_FROM) * cfg.VOLUME_TAX_PER_FGA
        tax += max(0, fga - cfg.VOLUME_TAX_HIGH_FROM) * cfg.VOLUME_TAX_HIGH_PER_FGA
        tax = min(cfg.VOLUME_TAX_MAX, tax)
        return tax * cfg.VOLUME_TAX_INTERIOR_SHARE if interior else tax

    @staticmethod
    def _crowded_paint_malus(fga: int, shooter_ovr: float, mates_ovr: float) -> float:
        """Make chance a high-volume shooter loses at the rim when the defense can sag on him: weak teammates, or a
        lone star far above them (CONFIG.PLAYMAKING.CROWD_*). Any role: the post and the drive both draw help."""
        cfg = CONFIG.PLAYMAKING
        if fga < cfg.CROWD_FGA_FROM:
            return 0.0
        weakness = max(cfg.CROWD_MATES_OVR - mates_ovr, shooter_ovr - mates_ovr - cfg.CROWD_STAR_GAP)
        return max(0.0, min(cfg.CROWD_MAX, weakness * cfg.CROWD_PER_POINT))

    @staticmethod
    def _post_fade_chance(p) -> float:
        """Percent chance a post-up ends in a turnaround fadeaway (a mid-range jumper) instead of a shot at the rim
        (CONFIG.PLAYMAKING.POST_FADE_*): Dirk, Garnett and Webber fade, Shaq and Howard go to the rim."""
        cfg = CONFIG.PLAYMAKING
        skills = p.temp_abilita
        mid, tend = skills.mid_range_shot_rating, p.temp_tendenze.mid_range_shot_tendency
        if mid < cfg.POST_FADE_MID_FROM or tend < cfg.POST_FADE_TEND_FROM:
            return 0.0
        inside = max(getattr(skills, 'post_control_rating', 50), skills.close_shot_rating)
        chance = cfg.POST_FADE_BASE + (tend - cfg.POST_FADE_TEND_FROM) * cfg.POST_FADE_PER_TEND + (mid - inside) * cfg.POST_FADE_PER_EDGE
        return max(0.0, min(cfg.POST_FADE_MAX, chance))

    def _simula_possesso(self, squadra_att: Squadra, squadra_dif: Squadra) -> bool:
        """
        ### FRONT OFFICE REWORK v5.0: READ & REACT SYSTEM ###
        Priority: 1. Trigger (Scheme) -> 2. Advantage -> 3. Gravity and Help -> 4. Hero Ball/Ball Movement
        """
        giocatori_in_campo = squadra_att.giocatori_in_campo()
        # --- DYNAMIC STAR USAGE & HIERARCHY SELECTION (Tendenza Dinamica) ---
        # Calculates dynamic possession weights based on OVR, Touch Tendency, Tactical Plan, and Playmaking
        tp_att = getattr(squadra_att, 'tactical_plan', None)
        touch_mods = getattr(tp_att, 'player_touch_modifiers', {}) if tp_att else {}
        first_opt = getattr(tp_att, 'offensive_first_option', None) if tp_att else None

        pesi_possesso = []
        for p in giocatori_in_campo:
            ovr_val = max(50, getattr(p, 'ovr', 70))
            touch_val = max(30, getattr(p.temp_tendenze, 'touch_tendency', 60))
            
            # Apply the explicit tactical modifier
            pmod = touch_mods.get(p.nome) or touch_mods.get(getattr(p, 'id', ''), "STANDARD")
            touch_mod_multiplier = 1.0
            if pmod == "GO_TO_GUY":
                touch_mod_multiplier = 1.50
            elif pmod == "ROOKIE_FOCUS":
                touch_mod_multiplier = 1.35
            elif pmod == "SECONDARY":
                touch_mod_multiplier = 1.15
            elif pmod == "ROLE_PLAYER":
                touch_mod_multiplier = 0.70
            elif pmod == "DEFENSE_ONLY":
                touch_mod_multiplier = 0.40
                
            if first_opt and (p.nome == first_opt or getattr(p, 'id', '') == first_opt):
                touch_mod_multiplier *= 1.30

            # Star Priority exponent
            ovr_weight = (ovr_val - 45) ** 1.30
            
            # Touch Tendency weight with tactical modifier
            touch_weight = ((touch_val / 50.0) ** 1.10) * touch_mod_multiplier
            
            # Playmaking skill factor (orchestrators and point-forwards/centers get initiation priority)
            playmaking_factor = self._initiation_factor(p)
                
            # --- DYNAMIC VETERAN AGE & MORALE TOUCH MODIFIER ---
            # Prevents heavily aging role players and non-elite veterans from padding unrealistic touches,
            # while protecting elite stars in their prime (30-34 yo: Curry, Durant, Jordan, Kobe, LeBron)
            veteran_modifier = 1.0
            p_age = getattr(p, 'eta', 20)
            is_elite_scorer = p.is_star() or getattr(p, 'ovr', 70) >= CONFIG.SIM.VETERAN_TOUCH_ELITE_OVR or (first_opt and (p.nome == first_opt or getattr(p, 'id', '') == first_opt))
            start_age = CONFIG.SIM.VETERAN_TOUCH_START_AGE_ELITE if is_elite_scorer else CONFIG.SIM.VETERAN_TOUCH_START_AGE

            if p_age >= start_age:
                age_thresh = start_age - 1
                age_over = p_age - age_thresh
                decay_rate = 0.03 if is_elite_scorer else 0.04
                age_factor = max(0.60, 1.0 - (age_over * decay_rate))
                
                # Check team competitiveness & morale (only for non-stars; stars carry losing teams)
                team_comp_factor = 1.0
                if p.squadra and not is_elite_scorer:
                    tot_games = (p.squadra.vittorie + p.squadra.sconfitte) or 1
                    win_pct = p.squadra.vittorie / tot_games
                    if win_pct < 0.45:  # Non-competitive / rebuilding team
                        team_comp_factor = 0.85 + (win_pct * 0.2)
                        
                morale_val = getattr(p, 'morale', 50)
                morale_factor = 1.0
                if morale_val < 50:
                    morale_factor = max(0.75, morale_val / 50.0)
                    
                energy_factor = 1.0
                p_energy = getattr(p, 'energia', 100)
                if p_energy < 60:
                    energy_factor = max(0.70, p_energy / 60.0)
                    
                veteran_modifier = age_factor * team_comp_factor * morale_factor * energy_factor

            pesi_possesso.append(max(1.0, ovr_weight * touch_weight * playmaking_factor * veteran_modifier))
            
        orchestratore = random.choices(giocatori_in_campo, weights=pesi_possesso, k=1)[0]
        self.log.append(f"({orchestratore.nome} directs the offense for the {squadra_att.nome})")
        
        shot_clock = min(24, self.tempo_rimanente_secondi)
        vantaggio_offensivo = 0.0
        giocatore_con_palla = orchestratore
        schema_eseguito = False
        passatore_recente = None
        schema = "FREE_PLAY"
        attori = {}
        ha_attaccato_closeout = False
        
        # --- PACE FIX: TRANSITION TIME (NBA 2002-03 Target: 90-92 possessions, 78-82 FGA) ---
        stile = squadra_att.coach.stile_gioco if (squadra_att.coach) else "Balanced Offense"
        if stile in ["Pace & Space", "Run and Gun", "Fast Break Offense", "Point Guard Maestro"]:
            tempo_transizione = random.randint(2, 4) # Fast pace (era scaled)
        elif stile in ["Twin Towers", "Post Play Dominance", "Grit & Grind", "Triangle Offense", "Man-to-Man Lockdown"]:
            tempo_transizione = random.randint(4, 6) # Slow half-court pace
        else:
            tempo_transizione = random.randint(3, 5) # Balanced pace
        
        # Slow down the pace in the playoffs (more half-court play)
        if getattr(self, "is_playoff", False) and random.random() < CONFIG.SIM.PLAYOFF_EXTRA_SECOND_CHANCE:
            tempo_transizione += 1
            
        self._aggiorna_tempo_possesso(tempo_transizione)
        shot_clock -= tempo_transizione
        
        # TICK LOOP
        while shot_clock > 0 and self.tempo_rimanente_secondi > 0:
            
            # 1. Immediate turnover check on the dribble
            if self._risolvi_turnover_palleggio(giocatore_con_palla, squadra_dif):
                self._aggiorna_tempo_possesso(random.randint(1, 2))
                return False

            # 1B. Foul check on the perimeter (hand-check / holding)
            if random.uniform(0, 100) < self._era_p_foul_chance:
                difensore_palla = squadra_dif.scegli_difensore(giocatore_con_palla)
                if difensore_palla:
                    continua_p = self._risolvi_fallo_non_di_tiro(difensore_palla, giocatore_con_palla, squadra_att, squadra_dif, "away from the ball")
                    if not continua_p:
                        return False # Bonus FTs taken, possession over
                    continue

            # The advantage decays if they hesitate
            vantaggio_offensivo = max(0.0, vantaggio_offensivo - 0.03)

            difensore_palla = squadra_dif.scegli_difensore(giocatore_con_palla)
            contesto_palla = self._crea_contesto_difensivo(giocatore_con_palla, difensore_palla)
            
            # ---------------------------------------------------------
            # ---------------------------------------------------------
            # STATE 1: PANIC (Less than 3 seconds)
            # ---------------------------------------------------------
            if shot_clock <= 3:
                tempo_tiro = min(shot_clock, random.randint(1, 3))
                self._aggiorna_tempo_possesso(tempo_tiro)
                shot_clock -= tempo_tiro
                self.log.append(f"({giocatore_con_palla.nome} forces up a shot against the 24s shot clock!)")
                punti_tiro = self._scegli_tipo_tiro(giocatore_con_palla, vantaggio_offensivo, is_forced=True)
                is_jumpshot_forced = (punti_tiro == 2 and giocatore_con_palla.ruolo in ['PG', 'SG', 'SF'])
                return self._risolvi_tiro(giocatore_con_palla, difensore_palla, squadra_att, squadra_dif, 
                                          punti_tiro, passatore_recente, contesto_palla, 
                                          is_forced=True, vantaggio_offensivo=vantaggio_offensivo,
                                          is_jumpshot_2pt=is_jumpshot_forced)

            # ---------------------------------------------------------
            # STATE 2: TRIGGER (Scheme to Create Advantage - first seconds)
            # ---------------------------------------------------------
            if shot_clock >= 15 and not schema_eseguito:
                schema_eseguito = True
                giocatore_focus = squadra_att._determina_focus_offensivo()
                if not giocatore_focus: giocatore_focus = orchestratore
                schema, attori = self._scegli_schema_offensivo(squadra_att, orchestratore, giocatore_focus)
                
                self.log.append(f"({orchestratore.nome} calls play: {schema})")
                
                # The scheme consumes circulation and positioning time to create an advantage
                esito_schema, t_cons, v_offensivo, palla_a = self._esegui_schema_tick(schema, squadra_att, squadra_dif, attori)
                
                self._aggiorna_tempo_possesso(t_cons)
                shot_clock -= t_cons
                vantaggio_offensivo = min(1.0, vantaggio_offensivo + v_offensivo)
                
                # Track the TRUE last passer
                vecchio_handler = giocatore_con_palla
                giocatore_con_palla = palla_a
                passatore_recente = vecchio_handler if palla_a != vecchio_handler else None
                
                if esito_schema is not None:
                    return esito_schema
                continue # Back to the start of the loop to read the advantage just created

            # ---------------------------------------------------------
            # STATE 3: READ & REACT (Reading the Advantage)
            # ---------------------------------------------------------
            # A player is "open" to shoot if he is physically poorly guarded (is_open)
            # or if the team has created an offensive advantage through the scheme
            is_actually_open = contesto_palla.get('is_open', False) or (vantaggio_offensivo >= 0.28)
            is_post_executor = (schema == "POST_UP" and giocatore_con_palla == attori.get("esecutore"))

            if vantaggio_offensivo >= 0.22 or contesto_palla.get('is_open', False) or ha_attaccato_closeout or is_post_executor:
                
                # ### EXTRA PASS DISTRIBUTION ###
                # In the real NBA, ~40% of baskets come after an extra perimeter pass:
                is_perimeter_player = giocatore_con_palla.ruolo in ['PG', 'SG', 'SF']
                is_scoring_executor = (schema in ["POST_UP", "ISOLATION"] and giocatore_con_palla == attori.get("esecutore"))
                is_pnr_partner = (schema == "PICK_AND_ROLL" and giocatore_con_palla == attori.get("partner"))
                is_cutter = (schema == "CUT_TO_BASKET" and giocatore_con_palla == attori.get("tagliante"))
                
                if passatore_recente and shot_clock > 4 and is_perimeter_player and not is_scoring_executor and not is_pnr_partner and not is_cutter and not ha_attaccato_closeout:
                    extra_pass_prob = self._extra_pass_chance(
                        giocatore_con_palla, open_look=contesto_palla.get('is_open', False) or vantaggio_offensivo >= 0.35)
                    
                    if random.uniform(0, 100) < extra_pass_prob:
                        altri = [p for p in giocatori_in_campo if p != giocatore_con_palla]
                        if altri:
                            pesi_tiro = [max(1, p.temp_abilita.three_point_shot_rating + p.temp_abilita.mid_range_shot_rating + p.temp_abilita.shot_iq) for p in altri]
                            ricevitore_extra = random.choices(altri, weights=pesi_tiro, k=1)[0]
                            if not self._risolvi_turnover_passaggio(giocatore_con_palla, ricevitore_extra, squadra_dif):
                                self.log.append(f"({giocatore_con_palla.nome} makes the extra pass to {ricevitore_extra.nome}!)")
                                if not (passatore_recente and (passatore_recente.ruolo in ['PG'] or passatore_recente.temp_abilita.passing_vision >= 80)):
                                    passatore_recente = giocatore_con_palla
                                giocatore_con_palla = ricevitore_extra
                                ha_attaccato_closeout = False
                                difensore_palla = squadra_dif.scegli_difensore(giocatore_con_palla)
                                contesto_palla = self._crea_contesto_difensivo(giocatore_con_palla, difensore_palla)
                                is_actually_open = contesto_palla.get('is_open', False) or (vantaggio_offensivo >= 0.30)
                
                # 0A. POST-UP EXECUTION (direct resolution of low-post play for C and AG)
                if schema == "POST_UP" and giocatore_con_palla == attori.get("esecutore"):
                    self.log.append(f"({giocatore_con_palla.nome} backs down {difensore_palla.nome} in the low post!)")
                    tempo_post = min(shot_clock, random.randint(3, 5))
                    self._aggiorna_tempo_possesso(tempo_post)
                    shot_clock -= tempo_post

                    # Defensive double-team in the post
                    aiuto_difensivo = None
                    help_def_chance = self._calcola_help_def_chance(giocatore_con_palla, squadra_att, squadra_dif)
                    if random.uniform(0, 100) < help_def_chance:
                        aiuti = [p for p in squadra_dif.giocatori_in_campo() if p.ruolo in ['C', 'PF'] and p != difensore_palla]
                        if aiuti:
                            aiuto_difensivo = max(
                                aiuti,
                                key=lambda p: (
                                    p.temp_abilita.interior_defense_rating
                                    + p.temp_abilita.defensive_iq_rating
                                    - max(0, p.game_stats.falli_commessi - 2) * 35
                                ),
                            )
                            self.log.append(f"(Defense collapses into a double-team on {giocatore_con_palla.nome} in the post!)")

                    # Evaluation of the kick-out from the post
                    pass_vis = getattr(giocatore_con_palla.temp_abilita, 'passing_vision', 60)
                    dish_tend = getattr(giocatore_con_palla.temp_tendenze, 'dish_to_open_man_tendency', 50)
                    hero_ball = getattr(giocatore_con_palla.temp_tendenze, 'hero_ball_tendency', 50)
                    touch_tend = getattr(giocatore_con_palla.temp_tendenze, 'touch_tendency', 50)
                    strength_val = getattr(giocatore_con_palla.temp_abilita, 'strength', 75)
                    
                    prob_scarico = 0.0
                    if aiuto_difensivo:
                        prob_scarico = 35.0 + (pass_vis - 60) * 0.35 + (dish_tend - 50) * 0.25 - (hero_ball - 50) * 0.25 - (touch_tend - 70) * 0.30 - (strength_val - 85) * 0.20
                        prob_scarico = max(15.0, min(75.0, prob_scarico))
                    elif pass_vis >= 80 and dish_tend >= 75:
                        prob_scarico = 20.0

                    if random.uniform(0, 100) < prob_scarico:
                        compagni_aperti = [p for p in squadra_att.giocatori_in_campo() if p != giocatore_con_palla]
                        if compagni_aperti:
                            pesi_tiratori = [max(1.0, p.temp_abilita.three_point_shot_rating * 1.3 + p.temp_abilita.mid_range_shot_rating) for p in compagni_aperti]
                            ricevitore = random.choices(compagni_aperti, weights=pesi_tiratori, k=1)[0]
                            self.log.append(f"({giocatore_con_palla.nome} reads the double-team and kicks out to {ricevitore.nome}!)")
                            passatore_recente = giocatore_con_palla # Potential assist for the big man!
                            giocatore_con_palla = ricevitore
                            vantaggio_offensivo = 0.85
                            ha_attaccato_closeout = False
                            continue

                    # 1v1 finish from the post
                    dif_effettivo = aiuto_difensivo if aiuto_difensivo else difensore_palla
                    if random.uniform(0, 100) < self._post_fade_chance(giocatore_con_palla):
                        self.log.append(f"({giocatore_con_palla.nome} turns over the shoulder for the fadeaway jumper!)")
                        contesto_fade = self._crea_contesto_difensivo(giocatore_con_palla, dif_effettivo, is_interior=False)
                        return self._risolvi_tiro(
                            giocatore_con_palla, dif_effettivo, squadra_att, squadra_dif,
                            2, passatore_recente, contesto_fade,
                            is_forced=False, vantaggio_offensivo=vantaggio_offensivo,
                            is_jumpshot_2pt=True
                        )
                    contesto_post = self._crea_contesto_difensivo(giocatore_con_palla, dif_effettivo, is_interior=True)
                    contesto_post['is_post_up'] = True

                    punteggio_att = (giocatore_con_palla.temp_abilita.post_control_rating * 0.50 +
                                     giocatore_con_palla.temp_abilita.strength * 0.35 +
                                     giocatore_con_palla.temp_abilita.close_shot_rating * 0.15) + (vantaggio_offensivo * 15)
                    punteggio_dif = (dif_effettivo.temp_abilita.interior_defense_rating * 0.50 +
                                     dif_effettivo.temp_abilita.strength * 0.35 +
                                     dif_effettivo.temp_abilita.block_rating * 0.15)

                    is_forced = (punteggio_att < punteggio_dif - 8)
                    if is_forced:
                        self.log.append(f"({giocatore_con_palla.nome} hoists a difficult contested hook shot in the post!)")
                    else:
                        self.log.append(f"({giocatore_con_palla.nome} pivots off the defender and banks it home from the post!)")

                    return self._risolvi_tiro(
                        giocatore_con_palla, dif_effettivo, squadra_att, squadra_dif,
                        2, passatore_recente, contesto_post,
                        is_forced=is_forced, vantaggio_offensivo=vantaggio_offensivo,
                        is_jumpshot_2pt=False
                    )

                # 0B. PICK & ROLL PARTNER EXECUTION (Roll al ferro o Pick & Pop)
                if schema == "PICK_AND_ROLL" and giocatore_con_palla == attori.get("partner"):
                    partner = giocatore_con_palla
                    tempo_pnr = min(shot_clock, random.randint(2, 4))
                    self._aggiorna_tempo_possesso(tempo_pnr)
                    shot_clock -= tempo_pnr
                    
                    # Is it a Pick & Pop (outside/mid-range shooter) or a Roll to the rim?
                    is_pop_candidate = (
                        (partner.temp_abilita.three_point_shot_rating >= 76 and partner.temp_tendenze.three_point_shot_tendency >= 45) or
                        (partner.temp_abilita.mid_range_shot_rating >= 80 and partner.temp_tendenze.mid_range_shot_tendency >= 55)
                    )
                    
                    if is_pop_candidate and random.uniform(0, 100) < 60:
                        # PICK & POP
                        punti_pop = self._scegli_tipo_tiro(partner, vantaggio_offensivo)
                        self.log.append(f"({partner.nome} pops out off the pick & pop and lets it fly!)")
                        return self._risolvi_tiro(
                            partner, difensore_palla, squadra_att, squadra_dif,
                            punti_pop, passatore_recente, contesto_palla,
                            is_forced=False, vantaggio_offensivo=vantaggio_offensivo,
                            is_jumpshot_2pt=(punti_pop == 2)
                        )
                    else:
                        # ROLL TO THE RIM (Alley-oop, dunk or layup off the glass with momentum)
                        self.log.append(f"({partner.nome} rolls hard to the rim on the pick & roll!)")
                        contesto_roll = self._crea_contesto_difensivo(partner, difensore_palla, is_interior=True)
                        return self._risolvi_tiro(
                            partner, difensore_palla, squadra_att, squadra_dif,
                            2, passatore_recente, contesto_roll,
                            is_forced=False, vantaggio_offensivo=max(0.40, vantaggio_offensivo),
                            is_jumpshot_2pt=False
                        )

                # 0C. CUT TO BASKET EXECUTION (Taglio a canestro backdoor / linea di fondo)
                if schema == "CUT_TO_BASKET" and giocatore_con_palla == attori.get("tagliante"):
                    tagliante = giocatore_con_palla
                    tempo_cut = min(shot_clock, random.randint(2, 3))
                    self._aggiorna_tempo_possesso(tempo_cut)
                    shot_clock -= tempo_cut
                    self.log.append(f"({tagliante.nome} catches the backdoor cut in stride and attacks the rim!)")
                    contesto_cut = self._crea_contesto_difensivo(tagliante, difensore_palla, is_interior=True)
                    return self._risolvi_tiro(
                        tagliante, difensore_palla, squadra_att, squadra_dif,
                        2, passatore_recente, contesto_cut,
                        is_forced=False, vantaggio_offensivo=max(0.40, vantaggio_offensivo),
                        is_jumpshot_2pt=False
                    )

                # A. SHOOTER CHOICE (Catch & Shoot / Immediate Jump Shot)
                if is_actually_open and passatore_recente and not ha_attaccato_closeout:
                    tendenza_3 = giocatore_con_palla.temp_tendenze.three_point_shot_tendency
                    tendenza_mid = giocatore_con_palla.temp_tendenze.mid_range_shot_tendency
                    tendenza_spot = getattr(giocatore_con_palla.temp_tendenze, 'spot_up_shot_tendency', 50)
                    tendenza_drive = giocatore_con_palla.temp_tendenze.drive_to_basket_tendency
                    rating_3 = giocatore_con_palla.temp_abilita.three_point_shot_rating
                    rating_mid = giocatore_con_palla.temp_abilita.mid_range_shot_rating
                    
                    rating_jumpshot = max(rating_3, rating_mid)
                    tendenza_jumpshot = max(tendenza_3, tendenza_mid, tendenza_spot)
                    
                    prob_catch_and_shoot = tendenza_jumpshot + (rating_jumpshot * 0.6)
                    prob_drive_closeout = tendenza_drive * 0.75
                    
                    if prob_catch_and_shoot >= prob_drive_closeout and rating_jumpshot >= 60:
                        punti_cs = self._scegli_tipo_tiro(giocatore_con_palla, vantaggio_offensivo)
                        tempo_tiro = min(shot_clock, random.randint(1, 3))
                        self._aggiorna_tempo_possesso(tempo_tiro)
                        shot_clock -= tempo_tiro
                        self.log.append(f"({giocatore_con_palla.nome} sets his feet and fires from downtown!)")
                        return self._risolvi_tiro(giocatore_con_palla, difensore_palla, squadra_att, squadra_dif, 
                                                  punti_cs, passatore_recente, contesto_palla, 
                                                  is_forced=False, vantaggio_offensivo=vantaggio_offensivo, is_jumpshot_2pt=(punti_cs==2))
                    else:
                        # Slasher/Big: pump fake and attack the closeout!
                        self.log.append(f"({giocatore_con_palla.nome} pump fakes and attacks the reckless closeout!)")
                        vantaggio_offensivo = 0.65 
                        ha_attaccato_closeout = True
                        t_closeout = random.randint(1, 2)
                        self._aggiorna_tempo_possesso(t_closeout)
                        shot_clock -= t_closeout
                        continue # Skip to the next tick: the player will fall into the "B. DRIVE" branch
                
                # B. DRIVER CHOICE (Drive & Kick Logic)
                self.log.append(f"({giocatore_con_palla.nome} attacks the paint!)")
                tempo_drive = random.randint(3, 5)
                self._aggiorna_tempo_possesso(tempo_drive)
                shot_clock -= tempo_drive

                # Does the defense collapse? (Help Defense)
                aiuto_difensivo = None
                help_def_chance = self._calcola_help_def_chance(giocatore_con_palla, squadra_att, squadra_dif)
                if random.uniform(0, 100) < help_def_chance:
                    aiuti = [p for p in squadra_dif.giocatori_in_campo() if p.ruolo in ['C', 'PF'] and p != difensore_palla]
                    if aiuti:
                        aiuto_difensivo = max(
                            aiuti,
                            key=lambda p: (
                                p.temp_abilita.interior_defense_rating
                                + p.temp_abilita.defensive_iq_rating
                                - max(0, p.game_stats.falli_commessi - 2) * 35
                            ),
                        )
                        self.log.append(f"(The defense collapses! {aiuto_difensivo.nome} slides over in help defense.)")

                if aiuto_difensivo:
                    # THE HELP LEFT A MAN OPEN. Will the driver pass it to him?
                    playmaking_tend = getattr(giocatore_con_palla.temp_tendenze, 'playmaking_tendency', 50)
                    touch_val = getattr(giocatore_con_palla.temp_tendenze, 'touch_tendency', 50)
                    close_skill = max(giocatore_con_palla.temp_abilita.close_shot_rating, giocatore_con_palla.temp_abilita.dunk_rating)
                    
                    prob_scarico = self._kickout_chance(giocatore_con_palla)
                    
                    if random.uniform(0, 100) < prob_scarico:
                        # KICK OUT!
                        compagni_liberi = [p for p in squadra_att.giocatori_in_campo() if p != giocatore_con_palla]
                        if compagni_liberi:
                            pesi_ricevitori = []
                            for p in compagni_liberi:
                                shot_skill = max(p.temp_abilita.three_point_shot_rating, p.temp_abilita.mid_range_shot_rating)
                                spot_tend = getattr(p.temp_tendenze, 'spot_up_shot_tendency', 50)
                                touch_t = getattr(p.temp_tendenze, 'touch_tendency', 50)
                                three_bonus = 1.35 if p.temp_abilita.three_point_shot_rating >= 72 else 1.0
                                w = (shot_skill ** 1.3) * ((spot_tend / 50.0) ** 0.8) * ((touch_t / 50.0) ** 0.5) * three_bonus
                                pesi_ricevitori.append(max(1.0, w))
                            ricevitore = random.choices(compagni_liberi, weights=pesi_ricevitori, k=1)[0]
                            self.log.append(f"({giocatore_con_palla.nome} dishes out to {ricevitore.nome}!)")
                            passatore_recente = giocatore_con_palla
                            giocatore_con_palla = ricevitore
                            vantaggio_offensivo = 0.85 # Huge advantage for the receiver!
                            ha_attaccato_closeout = False
                            t_kick = random.randint(1, 2)
                            self._aggiorna_tempo_possesso(t_kick)
                            shot_clock -= t_kick
                            continue # Back to the loop, the receiver will shoot on the next tick
                    else:
                        # HERO BALL TO THE RIM
                        self.log.append(f"({giocatore_con_palla.nome} powers through the help defender at the rim!)")
                        contesto_tiro = self._crea_contesto_difensivo(giocatore_con_palla, aiuto_difensivo, is_interior=True)
                        return self._risolvi_tiro(giocatore_con_palla, aiuto_difensivo, squadra_att, squadra_dif, 
                                                  2, passatore_recente, contesto_tiro, 
                                                  is_forced=True, vantaggio_offensivo=0.0, is_jumpshot_2pt=False)
                else:
                    # No defensive help: if the driver has beaten his man and has a clear path, he finishes at the rim!
                    # Only the pure low-scoring Floor Generals (Kidd, Stockton, Rubio) look for kick-outs to an open basket
                    playmaking_tend = getattr(giocatore_con_palla.temp_tendenze, 'playmaking_tendency', 50)
                    dish_tend = getattr(giocatore_con_palla.temp_tendenze, 'dish_to_open_man_tendency', 50)
                    pass_vis = getattr(giocatore_con_palla.temp_abilita, 'passing_vision', 60)
                    touch_val = getattr(giocatore_con_palla.temp_tendenze, 'touch_tendency', 50)
                    close_skill = max(giocatore_con_palla.temp_abilita.close_shot_rating, giocatore_con_palla.temp_abilita.dunk_rating)
                    
                    prob_dish_pass_first = self._drive_dish_chance(giocatore_con_palla)
                    compagni = [p for p in squadra_att.giocatori_in_campo() if p != giocatore_con_palla]
                    if random.uniform(0, 100) < prob_dish_pass_first and compagni:
                        # Drop-off to the big man or the cutter
                        pesi_compagni = [max(1, p.temp_abilita.close_shot_rating * 0.5 + p.temp_abilita.mid_range_shot_rating * 0.3 + p.temp_abilita.three_point_shot_rating * 0.2 + (getattr(p.temp_tendenze, 'spot_up_shot_tendency', 50) * 0.2)) for p in compagni]
                        ricevitore = random.choices(compagni, weights=pesi_compagni, k=1)[0]
                        self.log.append(f"({giocatore_con_palla.nome} collapses the defense and feeds {ricevitore.nome}!)")
                        passatore_recente = giocatore_con_palla
                        giocatore_con_palla = ricevitore
                        vantaggio_offensivo = 0.88
                        ha_attaccato_closeout = False
                        t_pass = random.randint(1, 2)
                        self._aggiorna_tempo_possesso(t_pass)
                        shot_clock -= t_pass
                        continue
                    else:
                        # Basket at the rim
                        self.log.append(f"({giocatore_con_palla.nome} glides all the way to the rack uncontested!)")
                        return self._risolvi_tiro(giocatore_con_palla, difensore_palla, squadra_att, squadra_dif, 
                                                  2, passatore_recente, contesto_palla, 
                                                  is_forced=False, vantaggio_offensivo=vantaggio_offensivo, is_jumpshot_2pt=False)

            # ---------------------------------------------------------
            # STATE 4: STAGNATION (Ball Movement or Isolation)
            # ---------------------------------------------------------
            dish_tend = getattr(giocatore_con_palla.temp_tendenze, 'dish_to_open_man_tendency', 50)
            pass_vis = getattr(giocatore_con_palla.temp_abilita, 'passing_vision', 70)
            hero_ball = getattr(giocatore_con_palla.temp_tendenze, 'hero_ball_tendency', 40)
            touch = getattr(giocatore_con_palla.temp_tendenze, 'touch_tendency', 60)
            drive = getattr(giocatore_con_palla.temp_tendenze, 'drive_to_basket_tendency', 50)
            playmaking_tend = getattr(giocatore_con_palla.temp_tendenze, 'playmaking_tendency', 50)
            
            prob_iso = (touch * 0.35 + drive * 0.25 + hero_ball * 0.35) - (dish_tend * 0.25 + playmaking_tend * 0.30 + (pass_vis - 70) * 0.20)
            if orchestratore.temp_abilita.passing_vision < 75:
                prob_iso -= 15
            prob_iso = max(10.0, min(85.0, prob_iso))
                
            # If the shot clock drops below 12, 1v1 stars can go into isolation
            if random.uniform(0, 100) < prob_iso and shot_clock <= 12:
                esito_iso, t_cons, v_offensivo, palla_a = self._risolvi_isolamento_tick(
                    giocatore_con_palla, difensore_palla, squadra_att, squadra_dif, vantaggio_offensivo, passatore_recente)
                
                self._aggiorna_tempo_possesso(t_cons)
                shot_clock -= t_cons
                vantaggio_offensivo = min(1.0, v_offensivo)
                giocatore_con_palla = palla_a
                
                if esito_iso is not None:
                    return esito_iso
                continue

            # B. Ball recirculation (if he doesn't go ISO, he passes it)
            migliori_compagni = [p for p in giocatori_in_campo if p != giocatore_con_palla]
            if migliori_compagni:
                # Look for teammates, bonus for those with high IQ who haven't shot too much
                pesi = [(p.temp_abilita.shot_iq - (p.game_stats.tiri_tentati_2 + p.game_stats.tiri_tentati_3)*1.5) for p in migliori_compagni]
                ricevitore = random.choices(migliori_compagni, weights=[max(1, w) for w in pesi], k=1)[0]
                
                self.log.append(f"({giocatore_con_palla.nome} swings the ball over to {ricevitore.nome})")
                if self._risolvi_turnover_passaggio(giocatore_con_palla, ricevitore, squadra_dif):
                    self._aggiorna_tempo_possesso(2)
                    return False
                
                t_cons = random.randint(2, 4)
                self._aggiorna_tempo_possesso(t_cons)
                shot_clock -= t_cons
                passatore_recente = giocatore_con_palla
                giocatore_con_palla = ricevitore
                
                # Ball movement generates a moderate advantage
                vantaggio_offensivo = min(1.0, vantaggio_offensivo + 0.28)
                
                # If the shot clock is low (< 6s) after the recirculation, the receiver takes the shot immediately with an assist
                if shot_clock <= 6:
                    dif_ric = squadra_dif.scegli_difensore(ricevitore)
                    contesto_ric = self._crea_contesto_difensivo(ricevitore, dif_ric)
                    punti_shot = self._scegli_tipo_tiro(ricevitore, vantaggio_offensivo, is_forced=False)
                    tempo_t = min(shot_clock, random.randint(1, 2))
                    self._aggiorna_tempo_possesso(tempo_t)
                    shot_clock -= tempo_t
                    return self._risolvi_tiro(ricevitore, dif_ric, squadra_att, squadra_dif, punti_shot, passatore_recente, contesto_ric, is_forced=False, vantaggio_offensivo=vantaggio_offensivo, is_jumpshot_2pt=(punti_shot==2))

                continue
            else:
                tempo_tiro = min(shot_clock, random.randint(1, 3))
                self._aggiorna_tempo_possesso(tempo_tiro)
                shot_clock -= tempo_tiro
                return self._risolvi_tiro(giocatore_con_palla, difensore_palla, squadra_att, squadra_dif,
                                          2, passatore_recente, contesto_palla, is_forced=True)

        # SHOT CLOCK VIOLATION
        self.log.append("24-SECOND SHOT CLOCK VIOLATION! Team turnover.")
        return False
    
    def _scegli_tipo_tiro(self, tiratore: Giocatore, vantaggio: float = 0.0, is_forced: bool = False) -> int:
        """
        ### FIX: MODERN NBA SPACING & BIG MEN ###
        The decision to shoot a 3 is dictated by the TENDENCY, not just by the Rating.
        No absolute block for big men, everyone can shoot at the buzzer.
        """
        tiro_3_rating = tiratore.temp_abilita.three_point_shot_rating
        tendency_3pt = tiratore.temp_tendenze.three_point_shot_tendency

        # 1. STATE: FORCED SHOT (At the expiration of the 24s)
        if is_forced:
            # At the buzzer, anyone can launch the prayer from 3.
            # Those who can shoot do it often (35%), those who can't do it rarely (5% - the famous backboard prayers).
            chance_preghiera = 35 if (tiro_3_rating > 65 or tendency_3pt > 50) else 5
            return 3 if random.uniform(0, 100) < chance_preghiera else 2

        # 2. THE REAL GATE (Only for players who cannot shoot at all)
        # Only if you are TERRIBLE at shooting (rating < 45) AND don't want to (tendency < 15) you NEVER shoot from 3.
        if tiro_3_rating < 45 and tendency_3pt < 15:
            return 2

        # 3. NATURAL VOLUME CALCULATION
        prob_3pt = 16.0  # Starting base

        # Tendency is the primary factor in deciding whether a player shoots from outside
        prob_3pt += (tendency_3pt * 0.52) 

        # Rating adds a bonus (snipers know they are snipers and shoot more)
        if tiro_3_rating >= 80:
            prob_3pt += 24
        elif tiro_3_rating >= 70:
            prob_3pt += 14

        # The Mid-Range Master: if he loves the mid-range, the three-point % drops in favor of the 2
        if tiratore.temp_abilita.mid_range_shot_rating > 85 and tiratore.temp_tendenze.mid_range_shot_tendency > 70:
            prob_3pt -= 12

        # Handling of big men (Centers and Power Forwards)
        if tiratore.ruolo in ['C', 'PF']:
            # If he is a traditional big (low tendency), he prefers the 2-point shot
            if tendency_3pt < 45:
                prob_3pt -= 15
            # If he is a "Stretch Big" (a big man who shoots threes), NO PENALTY
            else:
                prob_3pt += 5 

        # Offensive Advantage: if you are completely open, you are encouraged to shoot a 3
        if vantaggio >= 0.5:
            prob_3pt += 12
        if vantaggio >= 0.8:  # Clean kick-out on a drive (Kick-out)
            prob_3pt += 8

        # Final safety clamp
        prob_3pt = max(2.0, min(80.0, prob_3pt))

        from core.models import ACTIVE_TOURNAMENT
        three_pt_mult = ACTIVE_TOURNAMENT.get_era_3pt_multiplier() if ACTIVE_TOURNAMENT else 1.0
        
        # Open specialists with a high tendency do not suffer the era's extreme cut
        if tiro_3_rating >= 80 and tendency_3pt >= 55:
            three_pt_mult = max(0.85, three_pt_mult)
            
        prob_3pt *= three_pt_mult

        # 4. OFFENSIVE AND DEFENSIVE TACTICAL INFLUENCE (Gameplan & POE Impact)
        squadra_att = getattr(tiratore, 'squadra', None)
        squadra_dif = (self.squadra_ospite if squadra_att == self.squadra_casa else self.squadra_casa) if squadra_att else None

        if squadra_att:
            tp_att = getattr(squadra_att, 'tactical_plan', None)
            poe_att = getattr(squadra_att, 'active_poe', 'Balanced Approach')
            if (tp_att and tp_att.offensive_focus == "HUNT_THREES") or poe_att == "Hunt for Threes":
                prob_3pt += 16.0
            elif (tp_att and tp_att.offensive_focus == "POUND_PAINT") or poe_att == "Pound the Paint":
                prob_3pt -= 18.0
            elif (tp_att and tp_att.offensive_focus == "PACE_AND_SPACE_5OUT"):
                prob_3pt += 10.0

        if squadra_dif:
            tp_dif = getattr(squadra_dif, 'tactical_plan', None)
            poe_dif = getattr(squadra_dif, 'active_poe', 'Balanced Approach')
            scheme_dif = getattr(tp_dif, 'defensive_scheme', 'MAN_TO_MAN') if tp_dif else 'MAN_TO_MAN'
            
            # If the defense closes the middle of the paint / Protect the Paint / Zone 2-3:
            # The offense is forced to shoot more from outside (threes or set shots), the paint is clogged
            if poe_dif == "Protect the Paint" or scheme_dif == "ZONE_2_3":
                prob_3pt += 14.0
            # If the defense presses hard on the perimeter / Run Shooters Off the Line / Zone 3-2 / Blitz:
            # The offense struggles to find clean threes and is pushed to drive or shoot from mid-range
            elif poe_dif == "Run Shooters Off the Line" or scheme_dif in ["ZONE_3_2", "FULL_PRESS"]:
                prob_3pt -= 16.0

        prob_3pt = max(1.5, min(85.0, prob_3pt))

        return 3 if random.uniform(0, 100) < prob_3pt else 2
        
    def _esegui_schema_tick(self, schema: str, squadra_att: Squadra, squadra_dif: Squadra, attori: Dict) -> Tuple[Optional[bool], int, float, Giocatore]:
        """Executes a scheme and returns Outcome (if concluded), Time consumed, Advantage Gained, Player with the ball"""
        handler = attori.get("orchestratore")
        esecutore = attori.get("esecutore", handler)
        
        tp_dif = getattr(squadra_dif, 'tactical_plan', None)
        pnr_cov = getattr(tp_dif, 'pnr_coverage', 'DROP') if tp_dif else 'DROP'
        # Double-teams are set per opponent on the Opponent tab
        double_targets = tp_dif.plan_vs(squadra_att.nome)["double_teams"] if hasattr(tp_dif, 'plan_vs') else []
        def_scheme = getattr(tp_dif, 'defensive_scheme', 'MAN_TO_MAN') if tp_dif else 'MAN_TO_MAN'

        # Pick & Roll: evaluated with the specific defensive coverage
        if schema == "PICK_AND_ROLL":
            roll_man = attori.get("partner")
            if not roll_man: return None, 5, 0.0, handler
            dif_handler = squadra_dif.scegli_difensore(handler)
            dif_roll = squadra_dif.scegli_difensore(roll_man)

            if pnr_cov == "DROP":
                # The big man drops back to protect the rim: concedes pull-ups from the perimeter or a pass for the roller
                share = self._drop_pull_up_share(handler)
                if share is None:   # neither a shooter nor a passer: a weak read
                    return None, random.randint(5, 7), 0.25, roll_man if random.random() < 0.6 else handler
                if random.random() < share:
                    return None, random.randint(5, 7), 0.50, handler
                return None, random.randint(5, 7), 0.52, roll_man

            elif pnr_cov == "SWITCH":
                # Systematic switch: dif_roll takes the handler
                mismatch_speed = dif_roll and (handler.temp_abilita.speed > dif_roll.temp_abilita.speed + 8)
                mismatch_post = dif_handler and (roll_man.temp_abilita.strength > dif_handler.temp_abilita.strength + 10)
                if mismatch_speed:
                    return None, random.randint(5, 8), 0.54, handler
                elif mismatch_post:
                    return None, random.randint(5, 8), 0.54, roll_man
                else:
                    return None, random.randint(4, 7), 0.10, handler

            elif pnr_cov == "BLITZ_TRAP":
                # Aggressive double-team: tests the handler's passing vision
                if handler.temp_abilita.passing_vision >= 76 and handler.temp_abilita.passing_accuracy >= 76:
                    return None, random.randint(4, 7), 0.62, roll_man
                else:
                    if random.random() < 0.35:
                        return False, 4, 0.0, handler
                    else:
                        return None, random.randint(5, 8), 0.05, handler

            else: # HEDGE o Standard
                vantaggio_creato = not dif_handler or (handler.temp_abilita.speed + handler.temp_abilita.ball_handling) > (dif_handler.temp_abilita.perimeter_defense_rating + random.randint(0, 10))
                if vantaggio_creato:
                    return None, random.randint(5, 8), 0.44, handler if random.random() < 0.5 else roll_man
                else:
                    return None, random.randint(5, 7), 0.0, handler

        # Isolation & Post-Up: evaluated with the targeted double-teams (POST_UP resolves its own double-team in 0A)
        if schema in ["ISOLATION", "POST_UP"]:
            dif_ese = squadra_dif.scegli_difensore(esecutore)
            is_double_team_target = esecutore.nome in double_targets or (def_scheme == "BOX_AND_ONE" and esecutore.is_star())

            if schema == "ISOLATION" and is_double_team_target and random.random() < 0.65:
                # Defensive double-team on perimeter isolation
                if esecutore.temp_abilita.passing_vision >= 72 and random.random() < 0.70:
                    libero = [p for p in squadra_att.giocatori_in_campo() if p != esecutore]
                    if libero:
                        pesi_libero = [max(1.0, (p.temp_abilita.three_point_shot_rating ** 1.25) * ((getattr(p.temp_tendenze, 'spot_up_shot_tendency', 50) / 50.0) ** 0.7)) for p in libero]
                        target_pass = random.choices(libero, weights=pesi_libero, k=1)[0]
                    else:
                        target_pass = handler
                    return None, random.randint(4, 7), 0.52, target_pass
                else:
                    return None, random.randint(5, 8), -0.20, esecutore

            if schema == "POST_UP" and dif_ese:
                punteggio_att = esecutore.temp_abilita.post_control_rating * 0.6 + esecutore.temp_abilita.strength * 0.4
                punteggio_dif = dif_ese.temp_abilita.interior_defense_rating * 0.6 + dif_ese.temp_abilita.strength * 0.4
                if def_scheme == "ZONE_2_3": punteggio_dif += 4
                if punteggio_att > punteggio_dif - 8:
                    return None, random.randint(4, 7), 0.48, esecutore
                else:
                    return None, random.randint(4, 7), 0.28, esecutore
            elif schema == "ISOLATION" and dif_ese:
                if esecutore.temp_abilita.ball_handling > dif_ese.temp_abilita.perimeter_defense_rating:
                    return None, random.randint(5, 8), 0.40, esecutore
                else:
                    return None, random.randint(4, 7), 0.0, esecutore
                
        # Quick exchanges (Cuts and Spot-ups)
        if schema in ["SPOT_UP_SHOT", "CUT_TO_BASKET"]:
            tiratore = attori.get("tiratore") or attori.get("tagliante")
            if not tiratore: return None, 4, 0.0, handler
            if self._risolvi_turnover_passaggio(handler, tiratore, squadra_dif):
                return False, 3, 0.0, handler
            dif_tir = squadra_dif.scegli_difensore(tiratore)
            
            # Influence of the defensive scheme
            bonus_schema = 0.0
            if schema == "SPOT_UP_SHOT" and def_scheme == "ZONE_2_3":
                bonus_schema = 0.12
            elif schema == "CUT_TO_BASKET" and def_scheme == "ZONE_3_2":
                bonus_schema = 0.12
            elif schema == "SPOT_UP_SHOT" and def_scheme == "ZONE_3_2":
                bonus_schema = -0.10

            if dif_tir and dif_tir.temp_abilita.defensive_iq_rating < 78 and random.random() < 0.4:
                return None, random.randint(4, 7), min(0.95, 0.58 + bonus_schema), tiratore
            return None, random.randint(4, 6), max(0.24, 0.44 + bonus_schema), tiratore

        if schema == "DHO":
            hub = attori.get("hub")
            ricevitore = attori.get("ricevitore")
            if hub and ricevitore:
                if self._risolvi_turnover_passaggio(hub, ricevitore, squadra_dif): return False, 3, 0.0, hub
                return None, random.randint(4, 7), 0.48, ricevitore

        return None, random.randint(4, 7), 0.0, handler

    def _risolvi_isolamento_tick(self, attaccante: Giocatore, difensore: Giocatore, squadra_att: Squadra, squadra_dif: Squadra, vantaggio_corrente: float, passatore: Optional[Giocatore] = None) -> Tuple[Optional[bool], int, float, Giocatore]:
        """
        Tries to break the defense 1v1.
        If he wins -> attempts a close shot (or draws a foul).
        If he loses -> advantage reset, the ball stays with the player.
        """
        if not difensore:
            return None, 3, min(1.0, vantaggio_corrente + 0.3), attaccante

        if attaccante.ruolo in ['C', 'PF']:
            punteggio_att = (attaccante.temp_abilita.post_control_rating * 0.6 + attaccante.temp_abilita.strength * 0.4) + (vantaggio_corrente * 20)
            punteggio_dif = (difensore.temp_abilita.interior_defense_rating * 0.7 + difensore.temp_abilita.strength * 0.3)
        else:
            punteggio_att = (attaccante.temp_abilita.speed * 0.4 + attaccante.temp_abilita.ball_handling * 0.6) + (vantaggio_corrente * 20)
            punteggio_dif = difensore.temp_abilita.perimeter_defense_rating
        
        t_cons = random.randint(4, 7)

        if punteggio_att > punteggio_dif + random.randint(0, 15):
            self.log.append(f"({attaccante.nome} blows past his man!)")
            
            # Defensive help
            difensore_finale = difensore
            help_def_chance = self._calcola_help_def_chance(attaccante, squadra_att, squadra_dif)
            if random.uniform(0, 100) < help_def_chance:
                aiuti = [p for p in squadra_dif.giocatori_in_campo() if p.ruolo in ['C', 'PF'] and p != difensore]
                if aiuti:
                    difensore_finale = max(
                        aiuti,
                        key=lambda p: (
                            p.temp_abilita.interior_defense_rating
                            + p.temp_abilita.vertical
                            + p.temp_abilita.defensive_iq_rating
                            - max(0, p.game_stats.falli_commessi - 2) * 35
                        ),
                    )
                    self.log.append(f"({difensore_finale.nome} steps up to contest!)")
            
            # Shot choice: drive to the rim, mid-range pull-up or step-back 3
            punti_iso = 2
            is_interior = True
            is_jumpshot_2pt = False

            can_stepback_3 = (
                attaccante.ruolo in ['PG', 'SG', 'SF'] and 
                attaccante.temp_abilita.three_point_shot_rating >= 76 and 
                attaccante.temp_tendenze.three_point_shot_tendency >= 45
            )
            can_pullup_mid = (
                attaccante.temp_abilita.mid_range_shot_rating >= 78 and
                attaccante.temp_tendenze.mid_range_shot_tendency >= 55
            )

            roll_shot = random.uniform(0, 100)
            if can_stepback_3 and roll_shot < (attaccante.temp_tendenze.three_point_shot_tendency * 0.35):
                punti_iso = 3
                is_interior = False
                self.log.append(f"({attaccante.nome} creates space with a step-back three!)")
            elif can_pullup_mid and roll_shot < 50:
                punti_iso = 2
                is_interior = False
                is_jumpshot_2pt = True
                self.log.append(f"({attaccante.nome} pull-up jumper from the elbow!)")

            contesto_tiro = self._crea_contesto_difensivo(attaccante, difensore_finale, is_interior=is_interior)
            esito = self._risolvi_tiro(attaccante, difensore_finale, squadra_att, squadra_dif, 
                                       punti_iso, passatore, contesto_tiro, is_forced=False, 
                                       vantaggio_offensivo=vantaggio_corrente, is_jumpshot_2pt=is_jumpshot_2pt)
            return esito, t_cons, 0.0, attaccante
        else:
            self.log.append(f"({difensore.nome} locks down the drive and stops {attaccante.nome})")
            # Advantage cancelled if stopped
            return None, t_cons, 0.0, attaccante

    def _scegli_schema_offensivo(self, squadra: Squadra, orchestratore: Giocatore, giocatore_focus: Giocatore) -> Tuple[str, Dict[str, Giocatore]]:
        """
        REVISED VERSION: Chooses the scheme and assigns the roles with an "Offensive Focus".

        This version no longer chooses a random scheme, but selects it based on:
        1. The coach's style (base probability).
        2. The possession's "giocatore_focus", increasing the probability of the schemes that suit him.
        3. Dynamically assigns the roles in the scheme to make sure the giocatore_focus is the finisher.

        Args:
            squadra (Squadra): The team on offense.
            orchestratore (Giocatore): The player who starts the possession (the ball handler).
            giocatore_focus (Giocatore): The player the team wants to serve on this possession.

        Returns:
            Tuple[str, Dict[str, Giocatore]]: The name of the chosen scheme and a dictionary of the "actors".
        """
        stile_name = squadra.coach.stile_gioco if (squadra.coach and squadra.coach.stile_gioco in CONFIG.COACHINGSTYLES.STYLES) else "Balanced Offense"
        stile = CONFIG.COACHINGSTYLES.STYLES.get(stile_name, CONFIG.COACHINGSTYLES.STYLES.get("Balanced Offense", {}))
        default_schemi = {"PICK_AND_ROLL": 30, "SPOT_UP_SHOT": 25, "ISOLATION": 20, "CUT_TO_BASKET": 15, "POST_UP": 10}
        prob_schemi_base = stile.get("schemi", default_schemi)

        schemi_possibili = list(prob_schemi_base.keys())
        pesi = list(prob_schemi_base.values())

        # --- PHASE 1: PLACE THE SCHEMES BASED ON THE FOCUS PLAYER ---
        # We increase the probability of the schemes in which the giocatore_focus excels.
        # This ensures that if the focus is on Embiid, a Post-Up is more likely.
        # If it is on Maxey, an Isolation or a P&R is more likely.
        for i, schema in enumerate(schemi_possibili):
            if schema == "POST_UP" and giocatore_focus.temp_tendenze.post_up_tendency > 65:
                if pesi[i] == 0:
                    pesi[i] = 12
                if giocatore_focus.temp_tendenze.post_up_tendency > 75:
                    pesi[i] *= self._era_post_elite_mult # Scales from 4.6x in 2002 down to 2.4x in 2025
                else:
                    pesi[i] *= self._era_post_sub_mult   # Scales from 2.6x in 2002 down to 1.5x in 2025
            if schema == "SPOT_UP_SHOT" and giocatore_focus.ruolo in ['C', 'PF'] and giocatore_focus.temp_tendenze.post_up_tendency >= 72 and giocatore_focus.temp_tendenze.three_point_shot_tendency < 30:
                pesi[i] *= 0.30
            if schema == "ISOLATION" and giocatore_focus.temp_abilita.ball_handling > 80:
                pesi[i] *= 1.1 # Reduced from 1.4 to favor team schemes
            if schema == "SPOT_UP_SHOT" and giocatore_focus.temp_abilita.three_point_shot_rating > 85:
                pesi[i] *= 1.5
            if schema == "CUT_TO_BASKET" and giocatore_focus.temp_abilita.speed > 85:
                pesi[i] *= 1.5
                
            # Tactical adaptation: without a real point guard they play "Motion Offense"
            if orchestratore.temp_abilita.passing_vision < 75:
                if schema == "PICK_AND_ROLL": pesi[i] *= 0.5
                elif schema in ["SPOT_UP_SHOT", "CUT_TO_BASKET", "DHO"]: pesi[i] *= 1.3
                
        # Choose the final scheme using the modified weights
        schema_scelto = random.choices(schemi_possibili, weights=[max(1, p) for p in pesi], k=1)[0]

        # --- PHASE 2: ASSIGN THE ROLES ("ACTORS") IN THE CHOSEN SCHEME ---
        attori = {"orchestratore": orchestratore}
        giocatori_disponibili = squadra.giocatori_in_campo()
        altri_giocatori = [p for p in giocatori_disponibili if p != orchestratore]

        # Handling the edge case where there are no other players
        if not altri_giocatori:
            attori["esecutore"] = orchestratore
            return "ISOLATION", attori

        # Assign the roles so that the giocatore_focus is the finisher.
        if schema_scelto in ["ISOLATION", "POST_UP"]:
            attori["esecutore"] = giocatore_focus

        elif schema_scelto == "SPOT_UP_SHOT":
            attori["tiratore"] = giocatore_focus
            attori["esecutore"] = giocatore_focus

        elif schema_scelto == "CUT_TO_BASKET":
            attori["tagliante"] = giocatore_focus
            attori["esecutore"] = giocatore_focus

        elif schema_scelto == "PICK_AND_ROLL":
            # The orchestrator is always the initial ball handler.
            # We must decide whether the focus is the ball handler or the roller.
            if giocatore_focus == orchestratore:
                # The focus is on the ball handler. We find the best roller to help him.
                partner = max(altri_giocatori, key=lambda p: (p.temp_abilita.vertical + p.temp_abilita.close_shot_rating))
                attori["partner"] = partner
            else:
                # The focus is on the roller. The orchestrator will serve him.
                attori["partner"] = giocatore_focus
            
            # In the P&R, the executor of the final decision (shoot or pass) is always whoever has the ball.
            attori["esecutore"] = orchestratore
            
        elif schema_scelto == "DHO":
            # In the DHO, there is a "hub" (usually a big man) and a "receiver" (a guard/wing).
            if giocatore_focus.ruolo in ['C', 'PF']:
                # Dominant low-post scorers (e.g. Shaq, Duncan, Yao) convert DHO focus into low-post execution unless they are elite passing hubs (Jokic, Sabonis)
                if (
                    giocatore_focus.temp_tendenze.post_up_tendency >= 72
                    and getattr(giocatore_focus.temp_tendenze, 'touch_tendency', 50) >= 74
                    and giocatore_focus.temp_abilita.passing_vision < 84
                ):
                    attori["esecutore"] = giocatore_focus
                    return "POST_UP", attori
                # The focus is the big man, who will act as the Hub. We find the best receiver.
                attori["hub"] = giocatore_focus
                ricevitori_possibili = [p for p in giocatori_disponibili if p != giocatore_focus]
                if ricevitori_possibili:
                    pesi_rec = [max(1.0, (p.temp_abilita.three_point_shot_rating * 0.6 + p.temp_abilita.speed * 0.4) ** 1.2) for p in ricevitori_possibili]
                    ricevitore = random.choices(ricevitori_possibili, weights=pesi_rec, k=1)[0]
                    attori["ricevitore"] = ricevitore
                    attori["esecutore"] = ricevitore
                else: # Fallback if there are no other players
                    attori["esecutore"] = giocatore_focus
                    return "ISOLATION", attori
            else:
                # The focus is the guard/wing, who will be the Receiver. We find the best big man to be the Hub.
                attori["ricevitore"] = giocatore_focus
                attori["esecutore"] = giocatore_focus
                hub_possibili = [p for p in giocatori_disponibili if p.ruolo in ['C', 'PF'] and p != giocatore_focus]
                if hub_possibili:
                    hub = max(hub_possibili, key=lambda p: p.temp_abilita.passing_vision + p.temp_abilita.passing_accuracy)
                    attori["hub"] = hub
                else:
                    # Fallback: if there are no big men, a DHO can't be run. It converts into a P&R.
                    partner = max(altri_giocatori, key=lambda p: (p.temp_abilita.vertical + p.temp_abilita.close_shot_rating))
                    attori["partner"] = partner
                    attori["esecutore"] = orchestratore
                    return "PICK_AND_ROLL", attori

        # Final fallback to ensure there is always an executor
        if "esecutore" not in attori:
            attori["esecutore"] = giocatore_focus

        return schema_scelto, attori

    def _check_for_shooting_foul(self, attaccante: Giocatore, difensore: Giocatore, action_type: str, shot_value: int = 2) -> bool:
        """
        Foul check on the shot with a probability calibrated for the 2002-03 NBA era.
        Returns True if a foul was called and resolved with free throws.
        """
        if not difensore:
            return False
            
        cfg_fouls = CONFIG.FOULS
        
        # 1. Base probability by type of shot
        prob_base = {
            'drive': cfg_fouls.BASE_CHANCE_DRIVE,
            'post_up': cfg_fouls.BASE_CHANCE_DRIVE * 1.15,
            'jumpshot': cfg_fouls.BASE_CHANCE_DRIVE / cfg_fouls.JUMP_SHOT_FOUL_DIVISOR
        }.get(action_type, 10.0)

        # 2. Attacker aggressiveness modifier (foul drawing / physicality)
        aggressiveness_modifier = (attaccante.temp_abilita.draw_foul_rating - 50) * self._era_draw_mult
        if action_type == 'drive':
            aggressiveness_modifier += (attaccante.temp_tendenze.drive_to_basket_tendency - 75) * self._era_drive_foul_mult
            aggressiveness_modifier += (attaccante.temp_abilita.speed - 80) * self._era_speed_foul_mult
        elif action_type == 'post_up':
            aggressiveness_modifier += (attaccante.temp_tendenze.post_up_tendency - 70) * 0.15
            aggressiveness_modifier += (attaccante.temp_abilita.strength - 85) * 0.12
        elif action_type == 'jumpshot':
            shooter_rating = attaccante.temp_abilita.three_point_shot_rating if shot_value == 3 else attaccante.temp_abilita.mid_range_shot_rating
            aggressiveness_modifier += (shooter_rating - 85) * 0.05

        # 3. Defender discipline
        defensive_skill_modifier = 0
        if action_type in ['drive', 'post_up']:
            defensive_skill_modifier = (difensore.temp_abilita.interior_defense_rating - 80) * 0.12
        else:
            defensive_skill_modifier = (difensore.temp_abilita.perimeter_defense_rating - 80) * 0.12

        foul_tendency_penalty = (difensore.temp_tendenze.foul_tendency - 50) * 0.10

        prob = prob_base + aggressiveness_modifier - defensive_skill_modifier + foul_tendency_penalty

        # 4. Referee skepticism (anti-spam) & foul discipline
        ft_attempted = attaccante.game_stats.tiri_liberi_tentati
        skepticism_penalty = 0.0
        if ft_attempted > 8:
            skepticism_penalty += (ft_attempted - 8) * 1.8
            self.log.append(f"(Referees let incidental contact go on {attaccante.nome}...)")

        defender_discipline = (difensore.temp_abilita.interior_defense_rating + difensore.temp_abilita.perimeter_defense_rating) / 2
        if defender_discipline > 88 and ft_attempted > 6:
            skepticism_penalty += 5.0

        if difensore.game_stats.falli_commessi >= 4:
            # The defender in foul trouble defends more carefully and avoids risky contact
            prob -= 6.0
            
        prob -= skepticism_penalty
        
        if self.is_playoff:
            prob *= 1.08
        if attaccante.squadra == self.squadra_casa:
            prob *= CONFIG.HOMECOURT.FOUL_CHANCE_MODIFIER

        prob = max(2.0, min(prob, 42.0))

        if random.uniform(0, 100) < prob:
            difensore.game_stats.falli_commessi += 1
            self.team_fouls_quarter[difensore.squadra.nome] = self.team_fouls_quarter.get(difensore.squadra.nome, 0) + 1
            self.log.append(f"PERSONAL FOUL by {difensore.nome} on {attaccante.nome}!")
            
            if difensore.has_fouled_out:
                self.log.append(f"FOUL OUT! {difensore.nome} has fouled out with {CONFIG.COACHING.FOUL_OUT_LIMIT} personal fouls!")
                difensore.squadra.gestisci_uscita_giocatore(difensore)
            
            num_tiri = 3 if shot_value == 3 else 2
            self._tiri_liberi(attaccante, num_tiri)
            return True

        return False

    def _risolvi_fallo_non_di_tiro(self, difensore: Giocatore, attaccante: Giocatore, squadra_att: Squadra, squadra_dif: Squadra, action_name: str = "on the dribble") -> bool:
        """
        Handles a dead-ball / non-shooting foul (reach-in, illegal screen, rebound contest).
        Increments the personal and team fouls in the quarter.
        If the opposing team is in the BONUS (> 4 fouls in the quarter), awards 2 free throws.
        Otherwise, the ball is put back in play from the sideline.
        Returns True if the possession continues with an inbound, False if the possession ends (e.g. free throws).
        """
        if not difensore: return True
        
        difensore.game_stats.falli_commessi += 1
        team_fouls = self.team_fouls_quarter.get(difensore.squadra.nome, 0) + 1
        self.team_fouls_quarter[difensore.squadra.nome] = team_fouls
        
        self.log.append(f"PERSONAL FOUL ({action_name}) on {difensore.nome} ({difensore.game_stats.falli_commessi} fouls, {team_fouls} team fouls this quarter)!")
        
        if difensore.has_fouled_out:
            self.log.append(f"FOUL OUT! {difensore.nome} has fouled out with {CONFIG.COACHING.FOUL_OUT_LIMIT} personal fouls!")
            difensore.squadra.gestisci_uscita_giocatore(difensore)
            
        # Controllo BONUS (nella NBA dopo il 4° fallo di squadra nel quarto si va in lunetta)
        if team_fouls > 4:
            self.log.append(f"({difensore.squadra.nome} in the BONUS: 2 free throws awarded to {attaccante.nome})")
            self._tiri_liberi(attaccante, 2)
            return False # Possession over
        else:
            # Sideline inbound: consumes 2-3 seconds and the game resumes
            tempo_rimessa = random.randint(2, 3)
            self._aggiorna_tempo_possesso(tempo_rimessa)
            return True # Possession kept with an inbound

    def _crea_contesto_difensivo(self, attaccante: Giocatore, difensore: Optional[Giocatore], is_interior: bool = False) -> Dict:
        """Creates a dictionary describing the defensive situation (open vs contested)."""
        if not difensore: return {'is_open': True, 'difensore': None, 'is_interior': is_interior}
        
        fga_att = attaccante.game_stats.tiri_tentati_2 + attaccante.game_stats.tiri_tentati_3
        if is_interior:
            vantaggio_att = attaccante.temp_abilita.speed + attaccante.temp_abilita.shot_iq
            vantaggio_dif = difensore.temp_abilita.interior_defense_rating + (difensore.temp_abilita.strength * 0.5) + (difensore.temp_abilita.speed * 0.5)
            is_open = vantaggio_att > vantaggio_dif + random.randint(5, 15)
        else:
            vantaggio_att = (
                attaccante.temp_abilita.speed * 0.70
                + attaccante.temp_abilita.ball_handling * 0.45
                + attaccante.temp_abilita.shot_iq * 0.75
            )
            if difensore.ruolo in ['C', 'PF']:
                eff_perim_def = max(difensore.temp_abilita.perimeter_defense_rating,
                                    (difensore.temp_abilita.defensive_iq_rating * 0.6 + difensore.temp_abilita.interior_defense_rating * 0.4))
            else:
                eff_perim_def = difensore.temp_abilita.perimeter_defense_rating
            vantaggio_dif = (
                eff_perim_def * 1.10
                + difensore.temp_abilita.defensive_iq_rating * 0.35
                + difensore.temp_abilita.speed * 0.65
            )
            if fga_att >= 14:
                vantaggio_dif += min(10.0, (fga_att - 13) * 1.2)
            is_open = vantaggio_att > vantaggio_dif + random.randint(8, 20)
        return {'is_open': is_open, 'difensore': difensore, 'is_interior': is_interior}

    def _calcola_help_def_chance(self, attaccante: Giocatore, squadra_att: Squadra, squadra_dif: Squadra) -> float:
        """Dynamically computes the probability of defensive help based on spacing and gravity."""
        help_def_chance = CONFIG.EVENTS.HELP_DEFENSE_CHANCE
        poe_data = CONFIG.COACHINGTACTICS.POINTS_OF_EMPHASIS.get(squadra_dif.active_poe, {})
        help_def_chance *= poe_data.get("logic_mods", {}).get("help_defense_chance_modifier", 1.0)
        
        tiratori = [p for p in squadra_att.giocatori_in_campo() if p.temp_abilita.three_point_shot_rating >= 82 and p.temp_tendenze.three_point_shot_tendency >= 60]
        if len(tiratori) >= 3:
            help_def_chance -= 15.0
            
        close_threat = max(attaccante.temp_abilita.close_shot_rating, attaccante.temp_abilita.dunk_rating)
        if close_threat >= 85 and attaccante.temp_tendenze.touch_tendency >= 75:
            help_def_chance += 20.0
            
        return max(15.0, min(85.0, help_def_chance))

    def _risolvi_tiro(self, attaccante, difensore, squadra_att, squadra_dif, punti, passatore, contesto, is_forced=False, vantaggio_offensivo=0.0, is_jumpshot_2pt=False) -> bool:
        """
        Resolves a shot attempt (3-pointer, mid-range jump shot, or shot at the rim/in the post).
        Includes shot at the rim with universal physics, defensive contest, blocks and assists.
        """
        cfg_shooting = CONFIG.SHOOTING
        is_jumpshot = (punti == 3 or is_jumpshot_2pt)
        is_post = contesto.get('is_post_up', False) if contesto else False

        if difensore:
            action_foul = 'jumpshot' if is_jumpshot else ('post_up' if is_post else 'drive')
            if self._check_for_shooting_foul(attaccante, difensore, action_type=action_foul, shot_value=punti):
                return False

        if punti == 2: attaccante.game_stats.tiri_tentati_2 += 1
        elif punti == 3: attaccante.game_stats.tiri_tentati_3 += 1
        # Stat-only counters: the shot's zone and clutch state, read again by _canestro_segnato on a make
        self._shot_zone = '3' if punti == 3 else ('mid' if is_jumpshot_2pt else 'rim')
        self._shot_clutch = self._is_clutch_now()
        if self._shot_zone == 'rim': attaccante.game_stats.rim_fga += 1
        elif self._shot_zone == 'mid': attaccante.game_stats.mid_fga += 1
        if self._shot_clutch: attaccante.game_stats.clutch_fga += 1

        if difensore:
            if punti == 3 and random.uniform(0, 100) < CONFIG.EVENTS.PERIMETER_BLOCK_CHANCE:
                if self._risolvi_stoppata_perimetrale(attaccante, difensore):
                    self.log.append(f"INCREDIBLE! 3-point rejection by {difensore.nome} on {attaccante.nome}!")
                    self._log_play('block', difensore.squadra.nome, difensore.nome, f"Blocked 3PT shot by {attaccante.nome}", difensore.nome)
                    return self._risolvi_rimbalzo(squadra_att, squadra_dif, attaccante, is_three_point=True)
            elif punti == 2:
                prob_tentativo = difensore.temp_abilita.block_rating * CONFIG.EVENTS.BLOCK_ATTEMPT_RATING_FACTOR
                if random.uniform(0, 100) < prob_tentativo:
                    if self._risolvi_stoppata(attaccante, difensore):
                        self.log.append(f"BLOCK by {difensore.nome} on {attaccante.nome}!")
                        self._log_play('block', difensore.squadra.nome, difensore.nome, f"Blocked 2PT shot by {attaccante.nome}", difensore.nome)
                        return self._risolvi_rimbalzo(squadra_att, squadra_dif, attaccante, is_three_point=False)

        # -------------------------------------------------------------
        # SHOT PROBABILITY CALCULATION
        # -------------------------------------------------------------
        # Offensive and defensive tactical influence on shooting efficiency
        tp_dif = getattr(squadra_dif, 'tactical_plan', None)
        poe_dif = getattr(squadra_dif, 'active_poe', 'Balanced Approach')
        scheme_dif = getattr(tp_dif, 'defensive_scheme', 'MAN_TO_MAN') if tp_dif else 'MAN_TO_MAN'

        tp_att = getattr(squadra_att, 'tactical_plan', None)
        poe_att = getattr(squadra_att, 'active_poe', 'Balanced Approach')

        is_double_teamed = bool(hasattr(tp_dif, 'plan_vs') and attaccante.nome in tp_dif.plan_vs(squadra_att.nome)["double_teams"])
        fga_att = attaccante.game_stats.tiri_tentati_2 + attaccante.game_stats.tiri_tentati_3
        compagni_campo = [p for p in squadra_att.giocatori_in_campo() if p != attaccante]
        avg_compagni_ovr = (sum(p.ovr for p in compagni_campo) / len(compagni_campo)) if compagni_campo else 75.0

        if punti == 3:
            prob = self._era_prob_3pt_base
            rating_tiro = attaccante.temp_abilita.three_point_shot_rating
            rating_difesa = (difensore.temp_abilita.perimeter_defense_rating * 0.70 + difensore.temp_abilita.defensive_iq_rating * 0.30) if difensore else 50
            if poe_dif == "Run Shooters Off the Line" or scheme_dif in ["ZONE_3_2", "FULL_PRESS"]:
                prob -= 4.5
            elif poe_dif == "Protect the Paint" or scheme_dif == "ZONE_2_3":
                prob += 3.5
            if poe_att == "Hunt for Threes" or (tp_att and tp_att.offensive_focus == "HUNT_THREES"):
                prob += 2.0
            if is_double_teamed:
                prob -= 5.0
        elif is_jumpshot_2pt:
            prob = 35.5 - (5.0 if is_forced else 0.0)
            rating_tiro = attaccante.temp_abilita.mid_range_shot_rating
            rating_difesa = (difensore.temp_abilita.perimeter_defense_rating * 0.70 + difensore.temp_abilita.defensive_iq_rating * 0.30) if difensore else 50
            if is_double_teamed:
                prob -= 4.5
            if is_forced:
                self.log.append("(Forced mid-range jumper!)")
            else:
                self.log.append("(Mid-range jump shot)")
        else:
            # CLOSE SHOT (AT THE RIM, DUNK, LAYUP, POST HOOK)
            # Universal close-shot physics for all players
            rating_tiro = max(attaccante.temp_abilita.close_shot_rating, attaccante.temp_abilita.dunk_rating)
            if is_post:
                rating_tiro = max(rating_tiro, getattr(attaccante.temp_abilita, 'post_control_rating', 50))
            
            # NBA close-shot base (~52.5% base calibrated 2002-03, ~53.8% modern)
            prob = self._era_prob_close_base
            
            # Size / strength bonus for powerful finishers (Shaq, Duncan, Malone, LeBron)
            phys_bonus = (attaccante.temp_abilita.strength - 75) * 0.12
            prob += phys_bonus
            
            if is_forced:
                prob -= 7.5
                
            if difensore:
                rating_difesa = (difensore.temp_abilita.interior_defense_rating * 0.70 + difensore.temp_abilita.strength * 0.30)
                if is_post:
                    rating_difesa = (difensore.temp_abilita.interior_defense_rating * 0.60 + difensore.temp_abilita.strength * 0.40)
            else:
                rating_difesa = 60

            # Offensive advantage reduces the defense
            if vantaggio_offensivo >= 0.25:
                rating_difesa *= max(0.40, 1.0 - (vantaggio_offensivo * 0.35))
                prob += (vantaggio_offensivo * 4.0)

            # Rating differential finisher vs defender
            fatigue_penalty = attaccante.fatica * cfg_shooting.FATIGUE_PENALTY_FACTOR
            eff_rating = (rating_tiro * attaccante.game_form_factor) - (fatigue_penalty * 0.5)
            delta_close = eff_rating - rating_difesa
            prob += delta_close * 0.21

            prob -= self._volume_tax(fga_att, interior=True)
            prob -= self._crowded_paint_malus(fga_att, attaccante.ovr, avg_compagni_ovr)

            # Defensive intimidation from rim protectors
            lunghi_avversari = [p for p in squadra_dif.giocatori_in_campo() if p.ruolo in ['C', 'PF']]
            if lunghi_avversari:
                miglior_intimidatore = max(lunghi_avversari, key=lambda p: p.temp_abilita.block_rating)
                if miglior_intimidatore.temp_abilita.block_rating >= 88 and miglior_intimidatore.temp_abilita.interior_defense_rating >= 88:
                    prob -= 4.0

            if contesto and contesto.get('is_open', False) and not is_forced:
                prob += 3.5

            # Tactical modifiers on interior shots
            if poe_dif == "Protect the Paint" or scheme_dif == "ZONE_2_3":
                prob -= 6.0
            elif poe_dif == "Run Shooters Off the Line" or scheme_dif in ["ZONE_3_2", "FULL_PRESS"]:
                prob += 3.5
            if poe_att == "Pound the Paint" or (tp_att and tp_att.offensive_focus == "POUND_PAINT"):
                prob += 2.5
            if is_double_teamed:
                prob -= 5.5

            if attaccante.serie_tiro >= cfg_shooting.GOOD_STREAK_LIMIT: prob += cfg_shooting.GOOD_STREAK_BONUS
            if attaccante.serie_errore >= cfg_shooting.BAD_STREAK_LIMIT: prob -= cfg_shooting.BAD_STREAK_PENALTY * 0.5
            if attaccante.squadra == self.squadra_casa: prob += CONFIG.HOMECOURT.SHOOTING_BONUS

            # Coach Tactical Scheme Fit for Close / Interior Shot
            att_fit = self._get_tactical_fit(squadra_att)
            def_fit = self._get_tactical_fit(squadra_dif)

            # Execution synergy lifts shot percentage slightly (+/- 1.2%); mismatch degrades it
            prob += (att_fit.get("net_rating_mod", 0.0) * 0.5)
            prob -= (def_fit.get("net_rating_mod", 0.0) * 0.5)

            prob_finale = max(26.0, min(73.0, prob))

            if random.uniform(0, 100) < prob_finale:
                self._canestro_segnato(attaccante, punti, passatore)
                return False
            else:
                self._log_play('miss', attaccante.squadra.nome, attaccante.nome, "Missed Close Shot")
                return self._risolvi_rimbalzo(squadra_att, squadra_dif, attaccante, is_three_point=False)

        # OUTSIDE SHOT HANDLING (3PT and 2PT JUMPSHOT)
        rating_difesa_eff = rating_difesa * max(0.40, 1.0 - (vantaggio_offensivo * 0.35))
        fatigue_penalty = attaccante.fatica * cfg_shooting.FATIGUE_PENALTY_FACTOR
        effective_shooting_rating = (rating_tiro * attaccante.game_form_factor) - fatigue_penalty
        delta = effective_shooting_rating - rating_difesa_eff
        prob += delta * 0.24
        prob += (vantaggio_offensivo * 3.5)

        # High-volume self-creation tax & defensive crowding on solo-carry stars with weak teammates
        prob -= self._volume_tax(fga_att, interior=False)
        if avg_compagni_ovr < 75.0 and (getattr(attaccante.temp_tendenze, 'touch_tendency', 50) >= 75 or attaccante.ovr >= 85):
            prob -= min(4.0, (75.0 - avg_compagni_ovr) * 0.85)

        if contesto and contesto.get('is_open', False) and not is_forced:
            prob += 3.5
            self.log.append("(Open look!)")
        elif not is_forced and difensore:
            def_skill = (difensore.temp_abilita.perimeter_defense_rating * 0.6 + difensore.temp_abilita.defensive_iq_rating * 0.4)
            contest_penalty = 3.0 + (def_skill / 100.0) * 3.5
            prob -= contest_penalty
            self.log.append("(Contested shot!)")

        if attaccante.serie_tiro >= cfg_shooting.GOOD_STREAK_LIMIT: prob += cfg_shooting.GOOD_STREAK_BONUS
        if attaccante.serie_errore >= cfg_shooting.BAD_STREAK_LIMIT: prob -= cfg_shooting.BAD_STREAK_PENALTY
        if attaccante.squadra == self.squadra_casa: prob += CONFIG.HOMECOURT.SHOOTING_BONUS

        # Coach Tactical Scheme Fit for External / Perimeter Shot
        att_fit = self._get_tactical_fit(squadra_att)
        def_fit = self._get_tactical_fit(squadra_dif)

        # Execution synergy lifts perimeter shot quality; mismatch reduces it
        prob += (att_fit.get("net_rating_mod", 0.0) * 0.5)
        prob -= (def_fit.get("net_rating_mod", 0.0) * 0.5)

        prob_finale = prob

        # HARD CAP 3PT FOR NON-SHOOTERS
        if punti == 3:
            tiro_3_base = attaccante.temp_abilita.three_point_shot_rating
            if tiro_3_base < 50: cap_3pt = 20.0
            elif tiro_3_base < 65: cap_3pt = 30.0
            elif tiro_3_base < 75: cap_3pt = 36.5
            elif tiro_3_base < 85: cap_3pt = 42.5
            else: cap_3pt = 49.0
            prob_finale = min(prob_finale, cap_3pt)

        prob_finale = max(10.0, min(50.0 if is_jumpshot_2pt else 48.0, prob_finale))

        if random.uniform(0, 100) < prob_finale:
            self._canestro_segnato(attaccante, punti, passatore)
            return False
        else:
            shot_type = "3-pointer" if punti == 3 else "Jumpshot"
            self._log_play('miss', attaccante.squadra.nome, attaccante.nome, f"Missed {shot_type}")
            return self._risolvi_rimbalzo(squadra_att, squadra_dif, attaccante, is_three_point=(punti == 3))
        
    def _gestisci_sostituzioni(self):
        # First apply the accumulated energy recovery for all bench players
        self._applica_recupero_panchina()
        
        # ### FIX v21.2: INJURY CHECK PER SUBSTITUTION INTERVAL ###
        # The injury check is done here, every ~180 game seconds (~16 times per game).
        for giocatore in self.squadra_casa.giocatori_in_campo() + self.squadra_ospite.giocatori_in_campo():
            self._risolvi_infortunio(giocatore)
        
        self.squadra_casa.decidi_sostituzioni()
        self.squadra_ospite.decidi_sostituzioni()
        self.squadra_casa._in_campo_cache = None
        self.squadra_ospite._in_campo_cache = None

    def _risolvi_turnover_palleggio(self, palleggiatore: Giocatore, squadra_dif: Squadra) -> bool:
        """
        ### FIX TURNOVERS (v4.1) ###
        Drastically reduced the base probability of an unforced turnover in the tick system.
        Players with high Ball Handling are almost immune to unforced turnovers.
        """
        cfg = CONFIG.EVENTS
        difensore_primario = squadra_dif.scegli_difensore(palleggiatore)
        if not difensore_primario: return False
        
        # Defensive help: chance that a second defender attempts the steal
        difensore_attivo = difensore_primario
        if random.uniform(0, 100) < 15.0:
            possibili_aiuti = [p for p in squadra_dif.giocatori_in_campo() if p != difensore_primario]
            if possibili_aiuti:
                difensore_attivo = max(possibili_aiuti, key=lambda p: p.temp_abilita.steal_rating)
        
        # Steal attempt (subject to the defense's POE modifiers, e.g. Full-Court Press)
        steal_chance = cfg.STEAL_ATTEMPT_BASE_CHANCE * 1.35 * self._era_steal_mult
        poe_data = CONFIG.COACHINGTACTICS.POINTS_OF_EMPHASIS.get(squadra_dif.active_poe, {})
        steal_chance *= poe_data.get("logic_mods", {}).get("steal_attempt_modifier", 1.0)
        if random.uniform(0, 100) < steal_chance:
            prob_successo = 46 + ((difensore_attivo.temp_abilita.steal_rating - palleggiatore.temp_abilita.ball_handling) / cfg.STEAL_ABILITY_FACTOR)
            max_steals = getattr(cfg, 'MAX_STEALS_PER_GAME', 999)
            if random.uniform(0, 100) < prob_successo and difensore_attivo.game_stats.steals < max_steals:
                palleggiatore.game_stats.turnover += 1; difensore_attivo.game_stats.steals += 1
                self.log.append(f"STEAL by {difensore_attivo.nome}!")
                self._log_play('steal', difensore_attivo.squadra.nome, difensore_attivo.nome, f"Stole ball from {palleggiatore.nome}")
                return True
            else:
                # Reach-in foul on a failed steal attempt
                foul_reach_prob = 12.0 + (difensore_attivo.temp_tendenze.foul_tendency - 50) * 0.15 - (difensore_attivo.temp_abilita.defensive_iq_rating - 60) * 0.10
                if random.uniform(0, 100) < max(4.0, min(35.0, foul_reach_prob)):
                    continua_gioco = self._risolvi_fallo_non_di_tiro(difensore_attivo, palleggiatore, palleggiatore.squadra, squadra_dif, "on a steal attempt")
                    if not continua_gioco:
                        return True # Bonus FTs taken, possession over
                    return False
        
        # --- UNFORCED TURNOVER (lost dribble / traveling violation / ball out of bounds) ---
        prob_errore_base = 4.2
        # Defensive modifier: defender pressure
        prob_errore = prob_errore_base + ((difensore_primario.temp_abilita.perimeter_defense_rating - palleggiatore.temp_abilita.ball_handling) / cfg.TURNOVER_MODIFIER_FACTOR)
        
        # --- IMMUNITY FOR ELITE BALL HANDLERS ---
        if palleggiatore.temp_abilita.ball_handling >= 88:
            prob_errore *= 0.38
        elif palleggiatore.temp_abilita.ball_handling >= 82:
            prob_errore *= 0.58
        elif palleggiatore.temp_abilita.ball_handling >= 75:
            prob_errore *= 0.78

        # Tactical scheme fit affects ball-handling comfort (broken schemes lead to unforced errors)
        fit_palleggio = self._get_tactical_fit(palleggiatore.squadra)
        if fit_palleggio.get("net_rating_mod", 0.0) >= 1.5:
            prob_errore *= 0.94
        elif fit_palleggio.get("net_rating_mod", 0.0) <= -1.2:
            prob_errore *= 1.10
        
        if random.uniform(0, 100) < prob_errore * self._era_unforced_tov_mult:
            palleggiatore.game_stats.turnover += 1
            self.log.append(f"Unforced turnover by {palleggiatore.nome}.")
            self._log_play('turnover', palleggiatore.squadra.nome, palleggiatore.nome, "Lost Ball Turnover")
            return True
        return False

    def _risolvi_turnover_passaggio(self, passatore: Giocatore, ricevitore: Giocatore, squadra_dif: Squadra) -> bool:
        """
        ### FIX TURNOVERS (v4.1) ###
        Pass interceptions calibrated to NBA standards.
        """
        cfg = CONFIG.EVENTS
        difensore = squadra_dif.scegli_difensore(ricevitore)
        if not difensore: return False
        
        # Base interception calibrated for 7-8 team steals per game
        prob_intercetto_base = 4.8
        prob_intercetto = prob_intercetto_base + (((difensore.temp_abilita.steal_rating + difensore.temp_abilita.defensive_iq_rating) / 2) - passatore.temp_abilita.passing_accuracy) / cfg.PASS_TURNOVER_ABILITY_FACTOR
        
        # --- RESISTANCE FOR ELITE PLAYMAKERS ---
        if passatore.temp_abilita.passing_vision >= 88:
            prob_intercetto *= 0.60
        elif passatore.temp_abilita.passing_vision >= 80:
            prob_intercetto *= 0.80

        # Tactical scheme fit: crisp passing lanes reduce intercepted passes
        fit_pass = self._get_tactical_fit(passatore.squadra)
        if fit_pass.get("net_rating_mod", 0.0) >= 1.5:
            prob_intercetto *= 0.94
        elif fit_pass.get("net_rating_mod", 0.0) <= -1.2:
            prob_intercetto *= 1.10
        
        if random.uniform(0, 100) < prob_intercetto * self._era_steal_mult and difensore.game_stats.steals < cfg.MAX_STEALS_PER_GAME:
            passatore.game_stats.turnover += 1; difensore.game_stats.steals += 1
            self.log.append(f"Pass from {passatore.nome} INTERCEPTED by {difensore.nome}!")
            self._log_play('steal', difensore.squadra.nome, difensore.nome, f"Intercepted pass from {passatore.nome}")
            return True
        return False

    def _risolvi_rimbalzo(self, squadra_att: Squadra, squadra_dif: Squadra, tiratore: Giocatore, is_three_point: bool = False) -> bool:
        """
        ### REWORKED (v21.5 - Interior vs Perimeter Multipliers) ###
        - Rebounds from 2PT / paint: Centers and Power Forwards clearly dominate the boards (3.15x / 2.10x).
        - Rebounds from 3PT: Long rebounds with dispersion on the perimeter, allowing athletic guards and wings
          (Westbrook, Doncic, Kidd) to grab long rebounds in the open court.
        """
        # Update the shooter's miss streak
        tiratore.serie_tiro = 0
        tiratore.serie_errore += 1
        self.log.append(f"Missed shot by {tiratore.nome}.")
        
        cfg = CONFIG.EVENTS
        
        # Determine whether the rebound is offensive or defensive with a defensive NBA box-out factor (~75-78% DREB%)
        potenziale_att = sum((p.temp_abilita.offensive_rebound_rating + p.temp_abilita.vertical * 0.5) for p in squadra_att.giocatori_in_campo())
        potenziale_dif = sum((p.temp_abilita.defensive_rebound_rating + p.temp_abilita.strength * 0.5) for p in squadra_dif.giocatori_in_campo()) * 2.7
        
        chance_rimbalzo_off = 0
        if (potenziale_att + potenziale_dif) > 0:
            chance_rimbalzo_off = (potenziale_att / (potenziale_att + potenziale_dif)) * 100
        
        is_offensive_final = random.uniform(0, 100) < chance_rimbalzo_off
        
        # Select the rebounder
        squadra_rimbalzo = squadra_att if is_offensive_final else squadra_dif
        tipo_rating = 'offensive_rebound_rating' if is_offensive_final else 'defensive_rebound_rating'
        
        giocatori_in_campo = squadra_rimbalzo.giocatori_in_campo()
        if not giocatori_in_campo:
            return not is_offensive_final # If a team has no players, the other one takes the rebound

        # Differentiated multipliers: perimeter (long rebounds) vs interior (paint)
        pesi = []
        if is_three_point:
            role_mults = getattr(cfg, 'REBOUND_ROLE_MULTIPLIER_PERIMETER', {'C': 1.25, 'PF': 1.18, 'SF': 1.00, 'SG': 0.85, 'PG': 0.78})
            for p in giocatori_in_campo:
                rating = getattr(p.temp_abilita, tipo_rating, 50)
                reb_tend = getattr(p.temp_tendenze, 'rebound_tendency', 50)
                tend_factor = 0.35 + (reb_tend / 100.0) * 0.95
                # On threes, verticality and speed help guards/wings get to the long rebounds first
                athletic_bonus = 1.0 + max(-0.15, min(0.25, (p.temp_abilita.vertical + p.temp_abilita.speed - 140) * 0.003))
                peso = (rating ** (cfg.REBOUND_RATING_EXPONENT * 0.92)) * tend_factor * role_mults.get(p.ruolo, 1.0) * athletic_bonus
                pesi.append(max(1.0, peso))
        else:
            role_mults = getattr(cfg, 'REBOUND_ROLE_MULTIPLIER_INTERIOR', {'C': 1.75, 'PF': 1.45, 'SF': 0.92, 'SG': 0.65, 'PG': 0.55})
            for p in giocatori_in_campo:
                rating = getattr(p.temp_abilita, tipo_rating, 50)
                reb_tend = getattr(p.temp_tendenze, 'rebound_tendency', 50)
                tend_factor = 0.35 + (reb_tend / 100.0) * 0.95
                phys_bonus = 1.0 + max(-0.15, min(0.25, (p.temp_abilita.strength + p.temp_abilita.vertical - 140) * 0.002))
                era_reb_mult = (
                    self._era_center_reb_boost
                    if p.ruolo == 'C'
                    else (1.0 + (self._era_center_reb_boost - 1.0) * 0.6 if p.ruolo == 'PF' else 1.0)
                )
                peso = (rating ** cfg.REBOUND_RATING_EXPONENT) * tend_factor * role_mults.get(p.ruolo, 1.0) * phys_bonus * era_reb_mult
                pesi.append(max(1.0, peso))
        
        if sum(pesi) == 0:
             return not is_offensive_final # Fallback
        
        rimbalzista = random.choices(giocatori_in_campo, weights=[max(1.0, p) for p in pesi], k=1)[0]
        rimbalzista.game_stats.rimbalzi += 1
        if is_offensive_final:
            rimbalzista.game_stats.oreb += 1
        self.log.append(f"{'Offensive' if is_offensive_final else 'Defensive'} rebound secured by {rimbalzista.nome}.")
        
        reb_type = "Offensive Rebound" if is_offensive_final else "Defensive Rebound"
        self._log_play('rebound', rimbalzista.squadra.nome, rimbalzista.nome, reb_type)
        
        # An offensive rebound consumes game time for the contest and the half-court repositioning
        if is_offensive_final:
            tempo_rimbalzo_off = random.randint(4, 6)
            self._aggiorna_tempo_possesso(tempo_rimbalzo_off)
        else:
            tempo_rimbalzo_def = random.randint(1, 2)
            self._aggiorna_tempo_possesso(tempo_rimbalzo_def)

        # Rebound foul (loose ball foul / over-the-back) ~4.2% probability, weighted across on-court players
        if random.uniform(0, 100) < 4.2:
            falloso_squad = squadra_dif if is_offensive_final else squadra_att
            subisce_squad = squadra_att if is_offensive_final else squadra_dif
            candidati_fallosi = falloso_squad.giocatori_in_campo()
            if candidati_fallosi:
                pesi_fallo = []
                for p in candidati_fallosi:
                    ftend = max(10, getattr(p.temp_tendenze, 'foul_tendency', 50))
                    role_w = 1.25 if p.ruolo in ['C', 'PF', 'SF'] else 0.75
                    foul_trouble_w = 0.30 if p.game_stats.falli_commessi >= 3 else 1.0
                    pesi_fallo.append(max(1.0, ftend * role_w * foul_trouble_w))
                falloso = random.choices(candidati_fallosi, weights=pesi_fallo, k=1)[0]
                self._risolvi_fallo_non_di_tiro(falloso, rimbalzista, subisce_squad, falloso_squad, "a rimbalzo")

        # PUTBACK TENDENCY
        if is_offensive_final and random.uniform(0, 100) < rimbalzista.temp_tendenze.putback_tendency:
            self.log.append(f"({rimbalzista.nome} crashes the offensive glass and scores on the putback!)")
            difensore_putback = squadra_dif.scegli_difensore(rimbalzista)
            contesto_putback = self._crea_contesto_difensivo(rimbalzista, difensore_putback, is_interior=True)
            self._aggiorna_tempo_possesso(random.randint(1, 2))
            self._risolvi_tiro(rimbalzista, difensore_putback, squadra_att, squadra_dif, 2, None, contesto_putback)
            return False # Possession ends after the putback shot

        return is_offensive_final
    
    def _risolvi_stoppata_perimetrale(self, att: Giocatore, dif: Giocatore) -> bool:
        """Resolves an attempted block on a three-point shot."""
        # If there is no defender, no block is possible
        if not dif:
            return False
        cfg = CONFIG.EVENTS
        if dif.game_stats.blocks >= cfg.BLOCKS_PER_GAME_CAP: return False
        
        # A perimeter block is a contest of agility, length and perimeter defense.
        punteggio_dif = (dif.temp_abilita.perimeter_defense_rating * 0.5 + 
                        dif.temp_abilita.vertical * 0.3 +
                        dif.temp_abilita.speed * 0.2)
        # The attacker counters with his shooting IQ (finding the space) and release quickness.
        punteggio_att = (att.temp_abilita.shot_iq * 0.6 + 
                        att.temp_abilita.acceleration * 0.4)
                        
        prob_successo = cfg.PERIMETER_BLOCK_CHANCE + ((punteggio_dif - punteggio_att) / cfg.PERIMETER_BLOCK_RATING_IMPACT)
        
        if random.uniform(0, 100) < prob_successo:
            dif.game_stats.blocks += 1
            return True
        return False

    def _risolvi_stoppata(self, att: Giocatore, dif: Giocatore) -> bool:
        """
        ### REWORKED (v20.0) ###
        The success probability now starts from a base tied to the defender's ability,
        creating much more separation between elite defenders and mediocre ones.
        """
        # If there is no defender, no block is possible
        if not dif:
            return False
            
        cfg = CONFIG.EVENTS
        if dif.game_stats.blocks >= cfg.BLOCKS_PER_GAME_CAP: return False
        
        # The base probability is now directly proportional to the defender's rating
        prob_base = dif.temp_abilita.block_rating * cfg.BLOCK_SUCCESS_BASE_MODIFIER
        
        # The ability contest is now a modifier on this base
        skill_diff = ((dif.temp_abilita.block_rating + dif.temp_abilita.vertical) - 
                      (att.temp_abilita.close_shot_rating + att.temp_abilita.strength))
                      
        prob_finale = prob_base + (skill_diff * cfg.BLOCK_SUCCESS_SKILL_DIFF_FACTOR)
        
        # Probability limits to keep a minimum of realism
        prob_finale = max(10.0, min(90.0, prob_finale))

        if random.uniform(0, 100) < prob_finale:
            dif.game_stats.blocks += 1
            return True
        return False

    def _risolvi_assist(self, assistman: Giocatore) -> bool:
        """
        ### CALIBRATED VERSION (v23.0 - Anti-Outlier Assist & Diminishing Returns) ###
        Assists are awarded on direct baskets. Base calibrated between 56% and 84%
        based on Passing Vision. Diminishing returns applied on high volumes in a
        single game to avoid anomalous season averages (e.g. 16+ APG).
        """
        if not assistman: return False
        cfg = CONFIG.ASSIST
        
        vision = getattr(assistman.temp_abilita, 'passing_vision', assistman.abilita.passing_vision)
        prob_assist = self._era_assist_base + (vision - 60) * 0.30
        prob_assist = max(68.0, min(95.0, prob_assist))
        
        # Diminishing returns per single game
        current_ast = assistman.game_stats.assist
        if current_ast >= 16:
            prob_assist *= 0.65
        elif current_ast >= 12:
            prob_assist *= 0.82
        
        if random.uniform(0, 100) < prob_assist:
            if assistman.game_stats.assist < cfg.MAX_PER_GAME:
                assistman.game_stats.assist += 1
                self.log.append(f"Assist by {assistman.nome}!")
                return True
        return False

    def _tiri_liberi(self, giocatore: Giocatore, numero_tiri: int):
        if numero_tiri <= 0: return
        clutch = self._is_clutch_now()
        giocatore.game_stats.tiri_liberi_tentati += numero_tiri
        # NBA free-throw curve with moderate fatigue impact calibrated by era
        prob_ft = (giocatore.temp_abilita.free_throw_rating + self._era_ft_boost) - (giocatore.fatica / 35.0)
        prob_ft = max(20.0, min(96.0, prob_ft))
        punti_segnati = sum(1 for _ in range(numero_tiri) if random.uniform(0, 100) < prob_ft)
        team = self._get_player_team(giocatore)
        if punti_segnati > 0:
            giocatore.game_stats.punti += punti_segnati; giocatore.game_stats.punti_liberi += punti_segnati
            if clutch:
                giocatore.game_stats.clutch_pts += punti_segnati
            self.punteggio[team.nome] += punti_segnati
        self.log.append(f"{giocatore.nome} converts {punti_segnati}/{numero_tiri} free throws.")
        self._log_play('score', team.nome, giocatore.nome, f"Free Throws {punti_segnati}/{numero_tiri}")

    def _canestro_segnato(self, attaccante: Giocatore, punti: int, passatore: Optional[Giocatore]):
        """
        ### REWORKED (v20.1) ###
        Correctly handles the shooting-streak logic after a basket.
        """
        # Update the player's shooting streak
        attaccante.serie_tiro += 1
        attaccante.serie_errore = 0

        team = self._get_player_team(attaccante)
        opp_team = self.squadra_avversaria(team)

        punteggio_prec_att = self.punteggio[team.nome]
        punteggio_prec_dif = self.punteggio[opp_team.nome]
        
        attaccante.game_stats.punti += punti
        self.punteggio[team.nome] += punti
        
        if punti == 2:
            attaccante.game_stats.tiri_fatti_2 += 1
        else: # punti == 3
            attaccante.game_stats.tiri_fatti_3 += 1
        zone = getattr(self, '_shot_zone', None)
        if zone == 'rim': attaccante.game_stats.rim_fgm += 1
        elif zone == 'mid': attaccante.game_stats.mid_fgm += 1
        if getattr(self, '_shot_clutch', False):
            attaccante.game_stats.clutch_fgm += 1
            attaccante.game_stats.clutch_pts += punti
        
        self.log.append(f"FIELD GOAL by {attaccante.nome} ({punti} PTS)!")
        
        # NBA TV Play-by-Play logging
        shot_type = "3-pointer" if punti == 3 else "basket"
        self._log_play(
            event_type='score',
            team=team.nome,
            player=attaccante.nome,
            detail=f"{punti}PT {shot_type}",
            assist_by=passatore.nome if passatore else ""
        )

        # Check whether it is a "game winner"
        if (self.quarto_attuale >= 4 and self.tempo_rimanente_secondi <= 60):
            punteggio_attuale_att = self.punteggio[team.nome]
            if punteggio_prec_att <= punteggio_prec_dif and punteggio_attuale_att > punteggio_prec_dif:
                self.ultimo_evento = f"GAME WINNER: {attaccante.nome} ({punti} points, {self.tempo_rimanente_secondi} sec remaining)"
        
        if passatore and self._risolvi_assist(passatore):
            attaccante.game_stats.ast_fgm += 1

    def _risolvi_infortunio(self, giocatore: Optional[Giocatore]):
        """Rework v6.0: Realistic NBA injuries with vulnerability by age, high minutes and a 5-tier medical catalog."""
        if not giocatore or giocatore.infortunato: 
            return

        from .models import ACTIVE_TOURNAMENT
        inj_freq = getattr(ACTIVE_TOURNAMENT, 'injury_frequency', 'realistic') if ACTIVE_TOURNAMENT else 'realistic'
        if inj_freq == 'off':
            return

        cfg = CONFIG.INJURIES
        prob = cfg.BASE_INJURY_CHANCE
        abilita = giocatore.temp_abilita or giocatore.abilita
        
        # Stamina and Fatigue impact
        prob += (100 - abilita.stamina) * cfg.STAMINA_IMPACT_FACTOR
        prob += giocatore.fatica * cfg.FATIGUE_IMPACT_FACTOR
        
        # Age-related vulnerability (veterans 31+ have a higher tendency to minor muscle injuries)
        if getattr(giocatore, 'eta', 25) >= 31:
            anni_extra = giocatore.eta - 30
            prob += anni_extra * 0.005
        
        # High minutes in a single game increase the risk of acute fatigue injury (>32 min)
        minuti_gara = getattr(giocatore.game_stats, 'secondi_giocati', 0) / 60.0
        if minuti_gara > 32:
            prob += (minuti_gara - 32) * 0.003
        
        # Anti-decimation protection: strongly reduces the risk if the team already has injured players
        compagni_infortunati = sum(1 for p in giocatore.squadra.roster if p.infortunato and p.giorni_infortunio_rimanenti > 0)
        if compagni_infortunati >= 3:
            prob_finale = prob * 0.20
        elif compagni_infortunati >= 2:
            prob_finale = prob * 0.45
        elif compagni_infortunati == 1:
            prob_finale = prob * 0.75
        else:
            prob_finale = prob
        
        if inj_freq == 'low':
            prob_finale *= 0.35

        if random.uniform(0, 100) < prob_finale:
            DTD_INJURIES = [
                ("Ankle sprain (Grade 1)", 1, 3),
                ("Knee contusion", 1, 2),
                ("Acute low back pain / Back spasms", 1, 3),
                ("Calf soreness", 1, 2),
                ("Hip contusion", 1, 3),
                ("Hyperextended elbow", 1, 2),
                ("Neck issue / Acute stiff neck", 1, 2),
                ("Jammed finger / Minor dislocation", 1, 2),
            ]
            MINOR_INJURIES = [
                ("Hamstring strain (Grade 1)", 3, 6),
                ("Ankle sprain (Grade 2)", 4, 7),
                ("Groin strain", 3, 6),
                ("Patellar tendon inflammation", 3, 6),
                ("Rib contusion", 3, 5),
                ("Hairline fracture in a finger", 4, 7),
            ]
            MODERATE_INJURIES = [
                ("Grade 2 muscle strain (Quadriceps)", 8, 16),
                ("Shoulder subluxation", 10, 18),
                ("Acute plantar fasciitis", 8, 15),
                ("Severe high ankle sprain (Syndesmosis)", 10, 18),
                ("Partial meniscus tear", 10, 18),
            ]
            SEVERE_INJURIES = [
                ("Stress fracture in the foot (Jones Fracture)", 18, 30),
                ("Severe shoulder dislocation with Bankart lesion", 18, 28),
                ("Grade 3 muscle tear with avulsion", 20, 32),
                ("Severe bone bruise with bone marrow edema in the knee", 16, 26),
            ]
            SEASON_ENDING_INJURIES = [
                ("Torn anterior cruciate ligament (ACL)", 45, 75),
                ("Torn Achilles tendon", 50, 75),
                ("Torn patellar tendon", 45, 70),
                ("Displaced tibia and fibula fracture", 45, 70),
            ]

            gravita_roll = random.uniform(0, 100)
            dtd_share, minor_share, moderate_share, severe_share = cfg.SEVERITY_SHARES
            if gravita_roll < dtd_share:
                # 72% Day-to-Day (1-3 games): minor ache, plays with a penalty or misses 1-2 games
                nome_inf, d_min, d_max = random.choice(DTD_INJURIES)
                durata = round(random.randint(d_min, d_max) * cfg.DAYS_PER_GAME)
                is_dtd = True
                impatto = 0.07  # 7% penalty if he takes the court with an ache
            elif gravita_roll < dtd_share + minor_share:
                # 19% Minor (3-7 games): out for 1-2 weeks
                nome_inf, d_min, d_max = random.choice(MINOR_INJURIES)
                durata = round(random.randint(d_min, d_max) * cfg.DAYS_PER_GAME)
                is_dtd = False
                impatto = 0.0
            elif gravita_roll < dtd_share + minor_share + moderate_share:
                # 6.5% Moderate (8-18 games): out for 2-4 weeks
                nome_inf, d_min, d_max = random.choice(MODERATE_INJURIES)
                durata = round(random.randint(d_min, d_max) * cfg.DAYS_PER_GAME)
                is_dtd = False
                impatto = 0.0
            elif gravita_roll < dtd_share + minor_share + moderate_share + severe_share:
                # 1.8% Severe (18-32 games): out for 1-2 months
                nome_inf, d_min, d_max = random.choice(SEVERE_INJURIES)
                durata = round(random.randint(d_min, d_max) * cfg.DAYS_PER_GAME)
                is_dtd = False
                impatto = 0.0
            else:
                # 0.7% Season-Ending (45-75 games): ligament/tendon tear (very rare event)
                nome_inf, d_min, d_max = random.choice(SEASON_ENDING_INJURIES)
                durata = round(random.randint(d_min, d_max) * cfg.DAYS_PER_GAME)
                is_dtd = False
                impatto = 0.0

            giocatore.infortunato = True
            giocatore.infortunio_nome = nome_inf
            giocatore.is_day_to_day = is_dtd
            giocatore.infortunio_impatto = impatto
            giocatore.giorni_infortunio_rimanenti = durata
            
            tipo_label = "DAY-TO-DAY" if is_dtd else "INJURY"
            self.log.append(f"{tipo_label}! {giocatore.nome}: {nome_inf} ({durata} days)")
            import logging
            team_nome = giocatore.squadra.nome if hasattr(giocatore, 'squadra') and giocatore.squadra else 'Free Agent'
            logging.getLogger('main_sim').info(f"{tipo_label}! {giocatore.nome} ({team_nome}): {nome_inf} ({durata} days)")
            
            # Records in the player's career history log
            if hasattr(giocatore, 'add_career_log'):
                icon_inf = '🩹' if is_dtd else ('⚠️' if durata < 40 else '🚨')
                torneo_log = (getattr(giocatore.squadra, 'torneo', None) if getattr(giocatore, 'squadra', None)
                              else None) or ACTIVE_TOURNAMENT
                giocatore.add_career_log(
                    event_type='injury',
                    title=f"{tipo_label}: {nome_inf}",
                    description=f"{nome_inf} (estimated absence of {durata} days).",
                    season=getattr(torneo_log, 'season_number', 1),
                    day=getattr(torneo_log, '_current_gameday', getattr(torneo_log, 'current_day', 0)),
                    icon=icon_inf,
                    team=team_nome
                )
            
            if giocatore in giocatore.squadra.quintetto:
                giocatore.squadra.gestisci_uscita_giocatore(giocatore)

    def _recupero_fine_quarto(self, is_overtime=False):
        cfg = CONFIG.FATIGUE
        for p in self.squadra_casa.roster + self.squadra_ospite.roster:
            if not p.infortunato:
                # The recovery is a % of the maximum energy, modified by stamina
                recupero_base = p.energia_iniziale * cfg.END_OF_QUARTER_RECOVERY_FACTOR
                stamina_bonus = p.temp_abilita.stamina / 75.0
                
                recupero_totale = recupero_base * stamina_bonus
                if is_overtime:
                    recupero_totale /= 2

                p.energia = min(p.energia_iniziale, p.energia + recupero_totale)
                p.fatica = max(0, p.fatica - (recupero_totale / 2))
                
    def _calcola_statistiche_avanzate(self):
        """
        ### CORRECTED VERSION ###
        Computes the advanced statistics with simpler and more robust formulas.
        """
        # 1. Compute the team totals
        totali_squadra_casa = {'fga': 0, 'fta': 0, 'tov': 0}
        totali_squadra_ospite = {'fga': 0, 'fta': 0, 'tov': 0}

        for p in self.squadra_casa.roster:
            totali_squadra_casa['fga'] += p.game_stats.tiri_tentati_2 + p.game_stats.tiri_tentati_3
            totali_squadra_casa['fta'] += p.game_stats.tiri_liberi_tentati
            totali_squadra_casa['tov'] += p.game_stats.turnover
        for p in self.squadra_ospite.roster:
            totali_squadra_ospite['fga'] += p.game_stats.tiri_tentati_2 + p.game_stats.tiri_tentati_3
            totali_squadra_ospite['fta'] += p.game_stats.tiri_liberi_tentati
            totali_squadra_ospite['tov'] += p.game_stats.turnover

        # 2. Iterate over every player and compute his stats
        for giocatore in self.squadra_casa.roster + self.squadra_ospite.roster:
            gs = giocatore.game_stats
            ags = giocatore.advanced_game_stats
            
            if gs.secondi_giocati == 0: continue

            # --- True Shooting Percentage (TS%) ---
            fga = gs.tiri_tentati_2 + gs.tiri_tentati_3
            fta = gs.tiri_liberi_tentati
            punti = gs.punti
            if (fga + 0.44 * fta) > 0:
                ags.true_shooting_percentage = round(punti / (2 * (fga + 0.44 * fta)) * 100, 1)

            # --- Usage Rate (USG%) - Standard NBA Minutes-Scaled Formula ---
            totali_squadra = totali_squadra_casa if giocatore.squadra == self.squadra_casa else totali_squadra_ospite
            
            possessi_usati_giocatore = fga + 0.44 * fta + gs.turnover
            possessi_totali_squadra = totali_squadra['fga'] + 0.44 * totali_squadra['fta'] + totali_squadra['tov']
            
            # Normalize for the fraction of the game played
            minuti_gara = max(48.0, (self.secondi_totali_giocati / 60.0) if self.secondi_totali_giocati > 0 else 48.0)
            fraction_game = (gs.secondi_giocati / 60.0) / minuti_gara
            if possessi_totali_squadra > 0 and fraction_game > 0:
                ags.usage_rate = round(min(60.0, max(5.0, (possessi_usati_giocatore / (possessi_totali_squadra * fraction_game)) * 100.0)), 1)

    def _finalizza_partita(self):
        """
        ### REWORKED (v20.3 - Finalization Hotfix) ###
        Fixes the order of operations: first compute ALL the final statistics
        (including minutes) and THEN save the "snapshot" of the box scores.
        """
        self._applica_recupero_panchina()
        p_casa = self.punteggio[self.squadra_casa.nome]
        p_ospite = self.punteggio[self.squadra_ospite.nome]
        
        # Compute the final plus-minus before anything else
        for p in self.squadra_casa.giocatori_in_campo():
            p.plus_minus += (p_casa - p._score_at_check_in) - (p_ospite - p._score_at_check_in_opp)
        for p in self.squadra_ospite.giocatori_in_campo():
            p.plus_minus += (p_ospite - p._score_at_check_in) - (p_casa - p._score_at_check_in_opp)

        self._calcola_statistiche_avanzate()
        
        vincitore = self.squadra_casa if p_casa > p_ospite else self.squadra_ospite
        
        # --- CORRECT ORDER: 1. COMPUTE FINAL STATS ---
        # Iterate only once over all the players to finalize their GameStats
        tutti_giocatori_partita = self.squadra_casa.roster + self.squadra_ospite.roster
        for g in tutti_giocatori_partita:
            if g.game_stats.secondi_giocati > 0:
                # Compute the MINUTES PLAYED
                g.game_stats.minuti_giocati = g.game_stats.secondi_giocati / 60.0
                
                # Compute the MVP points
                g.game_stats.mvp_points = g.calcola_punti_mvp_partita()
                if g.squadra == vincitore: 
                    g.game_stats.mvp_points *= CONFIG.SIM.MVP_WIN_BONUS
                
                # Aggregate the season/playoff statistics
                stats_container = g.playoff_stats if self.is_playoff else g.season_stats
                stats_container.aggregate(g.game_stats)

        # --- COACH RECORD UPDATE & BOARD CONCERN CHECK ---
        from .board_engine import check_board_concern_trigger
        from .models import ACTIVE_TOURNAMENT

        if vincitore and getattr(vincitore, 'coach', None):
            vincitore.coach.historical_wins += 1

        perdente = self.squadra_ospite if vincitore == self.squadra_casa else self.squadra_casa
        if perdente and getattr(perdente, 'coach', None):
            perdente.coach.historical_losses += 1

        # Evaluate Board triggers if User Franchise is underperforming
        if ACTIVE_TOURNAMENT and getattr(ACTIVE_TOURNAMENT, 'user_gm_profile', None):
            user_gm = ACTIVE_TOURNAMENT.user_gm_profile
            user_team_name = getattr(user_gm, 'current_team_name', None) or (getattr(ACTIVE_TOURNAMENT.squadra_giocatore, 'nome', None) if getattr(ACTIVE_TOURNAMENT, 'squadra_giocatore', None) else None)
            if user_team_name and perdente and perdente.nome == user_team_name:
                check_board_concern_trigger(perdente, ACTIVE_TOURNAMENT, user_gm)

        # --- CORRECT ORDER: 2. "SNAPSHOT" THE NOW-COMPLETE BOX SCORES ---
        self.final_box_scores = {
            self.squadra_casa.nome: [],
            self.squadra_ospite.nome: []
        }
        starters_casa = getattr(self, 'starters', {}).get(self.squadra_casa.nome, set())
        starters_ospite = getattr(self, 'starters', {}).get(self.squadra_ospite.nome, set())

        for p in self.squadra_casa.roster:
            if p.game_stats.secondi_giocati > 0:
                # Now p.game_stats.minuti_giocati has the correct value
                snapshot = {
                    'nome': p.nome,
                    'ruolo': getattr(p, 'ruolo', 'SG'),
                    'is_starter': p.nome in starters_casa,
                    'game_stats': copy(p.game_stats),
                    'plus_minus': p.plus_minus
                }
                self.final_box_scores[self.squadra_casa.nome].append(snapshot)
        
        for p in self.squadra_ospite.roster:
            if p.game_stats.secondi_giocati > 0:
                snapshot = {
                    'nome': p.nome,
                    'ruolo': getattr(p, 'ruolo', 'SG'),
                    'is_starter': p.nome in starters_ospite,
                    'game_stats': copy(p.game_stats),
                    'plus_minus': p.plus_minus
                }
                self.final_box_scores[self.squadra_ospite.nome].append(snapshot)