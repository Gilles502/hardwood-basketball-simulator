"""
Draft Module

Handles the NBA Draft process including:
- Draft lottery simulation
- Custom draft class loading from JSON
- AI pick logic (BPA vs need)
- Draft class procedural generation
"""
import os
import json
import random
import logging
from typing import List, Tuple, Optional, TYPE_CHECKING

from core.config import CONFIG
from core.roles import normalize_role
from core.models import Giocatore, Abilita, Tendenze, Contract
from core.scouting_view import scouted_prospects
from core.front_office.moves import record_draft_pick
from core.front_office.draft_fit import best_prospect
from core.front_office.era_lines import era_lines_for
from core.league.draft_source import draft_class_file

if TYPE_CHECKING:
    from core.models import Squadra
    from tournament.season_manager import Tournament

main_log = logging.getLogger('main_sim')

_FILLER_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "filler_players.json")
_filler_names_cache: Optional[frozenset] = None


def filler_player_names() -> frozenset:
    """Names of the filler players (data/filler_players.json) that may join rosters: generated rookies avoid them."""
    global _filler_names_cache
    if _filler_names_cache is None:
        try:
            with open(_FILLER_FILE, 'r', encoding='utf-8') as fh:
                _filler_names_cache = frozenset(p.get("nome") or p.get("name") for p in json.load(fh)) - {None}
        except (OSError, ValueError):
            _filler_names_cache = frozenset()
    return _filler_names_cache



def completed_draft_payload(log_data: Optional[dict], user_team: Optional[str]) -> Optional[dict]:
    """The draft room after the last pick: results and CPU trades from the offseason log; None if there is no draft yet."""
    results = (log_data or {}).get('draft') or []
    if not results:
        return None
    return {"status": "COMPLETED", "history": results, "trades": (log_data or {}).get('draft_trades') or [], "user_team": user_team}


class Draft:
    """
    Handles the whole NBA Draft process, from the lottery to the player selection.
    v3.0 introduces support for custom draft classes loaded from JSON files.
    """
    def __init__(self, torneo: 'Tournament', squadre: List['Squadra'], squadra_giocatore: Optional['Squadra']):
        self.torneo = torneo
        self.squadre = squadre
        self.squadra_giocatore = squadra_giocatore
        
        # Check whether the draft class already exists to avoid re-inserting it
        if hasattr(self.torneo, 'draft_class') and self.torneo.draft_class:
            self.draft_class = self.torneo.draft_class
        else:
            self.draft_class = self._carica_o_genera_classe_draft()
            self.torneo.draft_class = self.draft_class
        
        # In the new logic, the draft lottery has already been executed by Tournament
        self.ordine_originale: List[str] = getattr(self.torneo, 'draft_lottery_order', [])
        if not self.ordine_originale:
            main_log.warning("draft_lottery_order not found! Falling back to the record-based order.")
            self.ordine_originale = [s.nome for s in sorted(self.squadre, key=lambda s: s.vittorie)]
            
        # Persist pick_corrente and risultati_draft to avoid duplicates
        if hasattr(self.torneo, 'draft_pick_corrente'):
            self.pick_corrente = self.torneo.draft_pick_corrente
        else:
            self.pick_corrente = 0
            self.torneo.draft_pick_corrente = 0
            
        if hasattr(self.torneo, 'draft_risultati'):
            self.risultati_draft = self.torneo.draft_risultati
        else:
            self.risultati_draft = []
            self.torneo.draft_risultati = self.risultati_draft
            
        self.scelte_totali = len(self.ordine_originale) * CONFIG.OFFSEASON.DRAFT_ROUNDS

    # --- MAIN METHODS OF THE NEW SYSTEM ---

    def _carica_o_genera_classe_draft(self) -> List[Giocatore]:
        """
        Orchestrator method. Uses the draft class pre-generated in the Tournament if present (Scouting Mode),
        otherwise looks for a custom or procedural draft class as a fallback.
        """
        if getattr(self.torneo, 'draft_class', None):
            main_log.info("Pre-generated draft class detected in the Tournament (Scouting Mode). Loading...")
            return sorted(self.torneo.draft_class, key=lambda g: g.potenziale, reverse=True)
            
        # Compute the draft year based on the tournament's season number
        starting_year = getattr(self.torneo, 'starting_year', 2025)
        anno_draft_corrente = starting_year + self.torneo.season_number
        # The save's own class, an old save's Real Names 2002 class, or None (generated)
        filepath = draft_class_file(self.torneo, anno_draft_corrente)
        
        giocatori_custom = []
        if filepath:
            main_log.info(f"Custom Draft Class found for year {anno_draft_corrente}! Loading from: {filepath}")
            giocatori_custom = self._carica_classe_da_file(filepath)
            
            num_giocatori_caricati = len(giocatori_custom)
            num_necessari = CONFIG.OFFSEASON.DRAFT_CLASS_SIZE
            
            # Handling of partial classes
            if 0 < num_giocatori_caricati < num_necessari:
                main_log.info(f"The class is partial ({num_giocatori_caricati}/{num_necessari}). Generating the remaining players...")
                giocatori_generati = self._genera_giocatori_mancanti(num_necessari - num_giocatori_caricati, giocatori_custom, is_filler=True)
                giocatori_custom.extend(giocatori_generati)
            
            # If the loaded class is complete (or has been completed), sort it and use it
            return sorted(giocatori_custom, key=lambda g: g.potenziale, reverse=True)
            
        else:
            main_log.info(f"No custom Draft Class found for {anno_draft_corrente}. Procedural generation in progress...")
            return self._genera_classe_draft_completa()

    def _carica_classe_da_file(self, filepath: str) -> List[Giocatore]:
        """Helper method to parse the JSON file of a draft class."""
        giocatori_caricati = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                rookie_data_list = json.load(f)
            
            for rookie_info in rookie_data_list:
                abilita_raw = rookie_info.get("abilities") or rookie_info.get("abilita", {})
                tendenze_raw = rookie_info.get("tendencies") or rookie_info.get("tendenze", {})
                abilita = Abilita(**abilita_raw)
                tendenze = Tendenze(**tendenze_raw)
                
                normalized_role = normalize_role(rookie_info.get("role") or rookie_info.get("ruolo")) or "SG"

                rookie = Giocatore(
                    nome=rookie_info.get("name") or rookie_info.get("nome", "Unknown Rookie"),
                    ruolo=normalized_role,
                    eta=rookie_info.get("age") or rookie_info.get("eta", 19),
                    valutazione=rookie_info.get("overall") or rookie_info.get("valutazione", 60),
                    potenziale=rookie_info.get("potential") or rookie_info.get("potenziale", 70),
                    abilita=abilita,
                    tendenze=tendenze,
                    squadra=None,
                    provenance=rookie_info.get("provenance", "N/A"),
                    pedigree=rookie_info.get("pedigree", "Custom Prospect")
                )
                giocatori_caricati.append(rookie)
        except Exception as e:
            main_log.error(f"Error while loading the draft class from {filepath}: {e}")
        return giocatori_caricati

    # --- PROCEDURAL GENERATION METHODS ---

    def _genera_classe_draft_completa(self) -> List[Giocatore]:
        """Original procedural generation logic."""
        rookies = self._genera_giocatori_mancanti(CONFIG.OFFSEASON.DRAFT_CLASS_SIZE, [])
        return sorted(rookies, key=lambda g: g.potenziale, reverse=True)

    def _genera_giocatori_mancanti(self, num_da_generare: int, giocatori_esistenti: List['Giocatore'], is_filler: bool = False) -> List['Giocatore']:
        """
        Generates a specified number of rookies, making sure there are no duplicate names.
        """
        rookies_generati = []
        # Names are lookup keys: never reuse one of the league (rosters, free agents, the current class)
        # or of the filler players that can join a roster later.
        nomi_gia_usati = {p.nome for p in giocatori_esistenti} | set(filler_player_names())
        if hasattr(self, 'torneo') and self.torneo:
            for s in getattr(self.torneo, 'squadre', []):
                for p in getattr(s, 'roster', []):
                    nomi_gia_usati.add(p.nome)
            for p in getattr(self.torneo, 'free_agents_pool', None) or []:
                nomi_gia_usati.add(p.nome)
            for p in getattr(self.torneo, 'draft_class', None) or []:
                nomi_gia_usati.add(p.nome)
        cfg = CONFIG.OFFSEASON
        cfg_rookie = CONFIG.ROOKIEGEN
        archetipi_per_ruolo = {
            'PG': ["Luka-Esque", "Floor General", "Tiratore dal Dribbling"],
            'SG': ["3&D Guard", "Mid-Range Specialist", "Slasher Puro"],
            'SF': ["Ala Rimbalzista", "Tiratrice Pura", "Two-Way Wing"],
            'PF': ["Difensore/Rimbalzista", "Scoring Forward", "Stretch Four"],
            'C': ["Centro Puro", "Unicorno", "Point Center"]
        }

        for _ in range(num_da_generare):
            # 1. Determine origin and name, avoiding duplicates
            provenance = random.choices(list(cfg_rookie.PROVENANCES.keys()), weights=list(cfg_rookie.PROVENANCES.values()), k=1)[0]
            primi_nomi, cognomi = cfg_rookie.NAMES_BY_PROVENANCE[provenance]
            while True:
                nome = f"{random.choice(primi_nomi)} {random.choice(cognomi)}"
                if nome not in nomi_gia_usati:
                    nomi_gia_usati.add(nome)
                    break

            if is_filler:
                # Fillers are generated with low OVR and low potential
                valutazione = random.randint(58, 65)
                potenziale = random.randint(valutazione + 1, max(valutazione + 2, random.randint(62, 70)))
                pedigree = "Solid Prospect"
            else:
                # 2. Variance logic (15/15/70)
                roll = random.uniform(0, 100)
                is_ready = roll < 15
                is_project = 15 <= roll < 30
                
                # Generate the base rating using a bell (triangular) distribution
                valutazione = int(random.triangular(cfg.ROOKIE_RATING_MIN, cfg.ROOKIE_RATING_MAX, (cfg.ROOKIE_RATING_MIN + cfg.ROOKIE_RATING_MAX) / 2))
                potenziale = int(random.triangular(cfg.ROOKIE_POTENTIAL_MIN, cfg.ROOKIE_POTENTIAL_MAX, (cfg.ROOKIE_POTENTIAL_MIN + cfg.ROOKIE_POTENTIAL_MAX) / 2))

                if is_ready:
                    # NBA Ready: high OVR, but not excessive, Potential close to the OVR
                    valutazione += random.randint(2, 5)
                    potenziale = min(potenziale, valutazione + random.randint(2, 4))
                elif is_project:
                    # Raw Project: low OVR, high Potential
                    valutazione -= random.randint(3, 6)
                    potenziale += random.randint(2, 6)
                
                # Apply a Hard Cap BEFORE the pedigrees. No normal player exceeds 94 POT or 79 base OVR.
                potenziale = min(94, potenziale)
                valutazione = min(79, valutazione)

                # 3. Assign Pedigree and apply modifiers
                pedigree = "Solid Prospect"
                for p_name, p_data in sorted(cfg_rookie.PEDIGREES.items(), key=lambda item: item[1]['chance']):
                    if random.uniform(0, 100) < p_data["chance"] and potenziale >= p_data["min_pot"]:
                        pedigree = p_name
                        valutazione += random.randint(*p_data["bonus_ovr"])
                        if p_name == "NBA Ready Prospect":
                            potenziale = min(83, potenziale) # Cap rigido per "Ready"
                        break
                
                if random.uniform(0, 100) < cfg.GENERATIONAL_TALENT_CHANCE:
                    potenziale, valutazione, pedigree = random.randint(95, 99), random.randint(79, 83), "Generational Talent"
                
                # Absolute Global Cap after the pedigree
                valutazione = max(58, min(84, valutazione))
                potenziale = max(valutazione + 1, min(99, potenziale))
            
            # 4. Create the player
            ruolo = random.choice(['PG', 'SG', 'SF', 'PF', 'C'])
            archetipo = random.choice(archetipi_per_ruolo[ruolo])
            abilita, tendenze = self._genera_attributi_per_archetipo(ruolo, archetipo, valutazione, pedigree)
            
            rookie = Giocatore(
                nome=nome, ruolo=ruolo, eta=random.randint(18, 23), 
                valutazione=valutazione, potenziale=potenziale, 
                abilita=abilita, tendenze=tendenze, squadra=None,
                provenance=provenance,
                pedigree=pedigree
            )
            rookies_generati.append(rookie)

        return rookies_generati

    def _genera_attributi_per_archetipo(self, ruolo: str, archetipo: str, valutazione: int, pedigree: str) -> Tuple['Abilita', 'Tendenze']:
        """
        REWORKED: Polarized archetypes, realistic ceilings, factory Flaws and Role-Player Clamps.
        """
        # 1. MAP OF EXTREME ARCHETYPES (Definitive, Supporting, Negative)
        archetype_skills = {
            # PM
            "Floor General": (['passing_vision', 'passing_accuracy', 'offensive_iq_rating'], ['mid_range_shot_rating', 'perimeter_defense_rating', 'ball_handling'], ['dunk_rating', 'block_rating', 'offensive_rebound_rating']),
            "Luka-Esque": (['ball_handling', 'close_shot_rating', 'defensive_rebound_rating'], ['passing_vision', 'strength', 'three_point_shot_rating'], ['speed', 'perimeter_defense_rating', 'block_rating']),
            "Tiratore dal Dribbling": (['three_point_shot_rating', 'ball_handling'], ['speed', 'free_throw_rating', 'mid_range_shot_rating'], ['interior_defense_rating', 'strength', 'offensive_rebound_rating']),
            # G
            "3&D Guard": (['three_point_shot_rating', 'perimeter_defense_rating', 'defensive_iq_rating'], ['steal_rating', 'stamina', 'speed'], ['passing_vision', 'ball_handling', 'close_shot_rating']),
            "Mid-Range Specialist": (['mid_range_shot_rating', 'ball_handling', 'close_shot_rating'], ['free_throw_rating', 'offensive_iq_rating', 'passing_accuracy'], ['three_point_shot_rating', 'block_rating', 'defensive_rebound_rating']),
            "Slasher Puro": (['dunk_rating', 'acceleration', 'close_shot_rating'], ['vertical', 'speed', 'strength'], ['three_point_shot_rating', 'passing_vision', 'defensive_iq_rating']),
            # AP
            "Ala Rimbalzista": (['defensive_rebound_rating', 'strength', 'interior_defense_rating'], ['offensive_rebound_rating', 'stamina', 'vertical'], ['three_point_shot_rating', 'passing_vision', 'ball_handling']),
            "Tiratrice Pura": (['three_point_shot_rating', 'shot_iq'], ['free_throw_rating', 'offensive_iq_rating', 'mid_range_shot_rating'], ['strength', 'block_rating', 'passing_vision']),
            "Two-Way Wing": (['perimeter_defense_rating', 'defensive_iq_rating', 'steal_rating'], ['speed', 'stamina', 'close_shot_rating'], ['passing_vision', 'post_control_rating']),
            # AG
            "Difensore/Rimbalzista": (['defensive_rebound_rating', 'interior_defense_rating', 'block_rating'], ['strength', 'offensive_rebound_rating', 'defensive_iq_rating'], ['three_point_shot_rating', 'ball_handling', 'passing_vision']),
            "Scoring Forward": (['close_shot_rating', 'dunk_rating', 'acceleration'], ['strength', 'mid_range_shot_rating', 'vertical'], ['passing_vision', 'steal_rating', 'three_point_shot_rating']),
            "Stretch Four": (['three_point_shot_rating', 'mid_range_shot_rating'], ['shot_iq', 'offensive_iq_rating', 'defensive_rebound_rating'], ['block_rating', 'interior_defense_rating', 'strength']),
            # C
            "Centro Puro": (['interior_defense_rating', 'block_rating', 'defensive_rebound_rating'], ['strength', 'offensive_rebound_rating', 'close_shot_rating'], ['three_point_shot_rating', 'passing_vision', 'ball_handling', 'speed']),
            "Unicorno": (['three_point_shot_rating', 'block_rating'], ['mid_range_shot_rating', 'free_throw_rating', 'vertical'], ['strength', 'defensive_rebound_rating', 'offensive_rebound_rating', 'post_control_rating']),
            "Point Center": (['passing_vision', 'offensive_iq_rating', 'post_control_rating'], ['close_shot_rating', 'defensive_rebound_rating', 'mid_range_shot_rating'], ['speed', 'block_rating', 'vertical', 'three_point_shot_rating'])
        }

        defining_skills, supporting_skills, negative_skills = archetype_skills.get(archetipo, ([], [], []))
        is_elite = pedigree in ["Generational Talent", "Elite Scorer", "NBA Ready Prospect"]
        max_stat_cap = 95 if is_elite else 85

        # 2. STRICT BASE PHYSIQUE (Nerf G speed, Fix C verticals)
        fisico_base = {
            'PG': {'speed': (72, 88), 'acceleration': (74, 89), 'strength': (35, 55), 'vertical': (60, 80), 'stamina': (75, 90)},
            'SG':  {'speed': (68, 86), 'acceleration': (70, 86), 'strength': (42, 62), 'vertical': (65, 85), 'stamina': (75, 90)},
            'SF': {'speed': (65, 80), 'acceleration': (65, 80), 'strength': (52, 75), 'vertical': (60, 85), 'stamina': (70, 88)},
            'PF': {'speed': (50, 70), 'acceleration': (50, 70), 'strength': (68, 88), 'vertical': (60, 82), 'stamina': (65, 80)},
            'C':  {'speed': (30, 50), 'acceleration': (30, 50), 'strength': (78, 97), 'vertical': (55, 78), 'stamina': (60, 75)}
        }

        base_abilita = {}
        for key in Abilita.__annotations__:
            if key in fisico_base[ruolo]:
                min_f, max_f = fisico_base[ruolo][key]
                base_abilita[key] = int(random.triangular(min_f, max_f, (min_f + max_f)/2))
                
                # Archetype-specific physical boosts
                if archetipo == "Slasher Puro" and key in ['speed', 'acceleration', 'vertical']:
                    base_abilita[key] = min(max_stat_cap, base_abilita[key] + 10)
                if archetipo == "Unicorno" and key == 'strength':
                    base_abilita[key] = max(40, base_abilita[key] - 15) # Unicorns are frail
            elif key in defining_skills:
                boost = 12 if is_elite else 8
                base_abilita[key] = min(max_stat_cap, int(random.triangular(valutazione + boost - 4, valutazione + boost + 6, valutazione + boost)))
            elif key in supporting_skills:
                base_abilita[key] = min(max_stat_cap - 5, int(random.triangular(valutazione, valutazione + 8, valutazione + 4)))
            elif key in negative_skills:
                base_abilita[key] = max(35, valutazione - int(random.triangular(15, 25, 20)))
            else:
                base_abilita[key] = max(45, valutazione - int(random.triangular(5, 15, 10)))

        # 3. SAFETY NETS (Guarantee functionality in the game engine)
        if ruolo in ['C', 'PF']:
            base_abilita['shot_iq'] = max(70, base_abilita.get('shot_iq', 50))
            base_abilita['defensive_rebound_rating'] = max(70, base_abilita.get('defensive_rebound_rating', 50))
        if ruolo in ['PG', 'SG']:
            base_abilita['ball_handling'] = max(65, base_abilita.get('ball_handling', 50))

        # 4. ROOKIE FLAWS (Youth defects, skipped if Generational)
        flaw = "None"
        if not is_elite and random.random() < 0.30: # 30% of normal rookies have an obvious flaw
            flaw = random.choice(["Foul Prone", "Turnover Machine", "Gassed", "Black Hole"])
            if flaw == "Gassed":
                base_abilita['stamina'] = max(45, base_abilita['stamina'] - 20)
            elif flaw == "Turnover Machine":
                base_abilita['offensive_iq_rating'] = max(40, base_abilita['offensive_iq_rating'] - 15)

        # 5. TENDENCY GENERATION (THE ENGINE OF THE SIMULATION)
        base_tendenze = {}
        
        # Touch Tendency (Usage base basato sul talento)
        base_touch = 85 if is_elite else (75 if valutazione >= 78 else 55)
        base_tendenze['touch_tendency'] = max(30, min(98, base_touch + random.randint(-5, 5)))

        # Shooting and Drives
        three_rtg = base_abilita.get('three_point_shot_rating', 50)
        base_tendenze['three_point_shot_tendency'] = max(5, min(95, three_rtg + random.randint(-5, 15)))
        base_tendenze['mid_range_shot_tendency'] = max(10, min(90, base_abilita.get('mid_range_shot_rating', 50)))
        
        drive_base = base_abilita.get('acceleration', 50)
        if base_tendenze['three_point_shot_tendency'] > 75:
            drive_base -= 20 # Those who shoot from outside drive less
        base_tendenze['drive_to_basket_tendency'] = max(10, min(95, drive_base))
        
        base_tendenze['post_up_tendency'] = max(5, min(95, base_abilita.get('post_control_rating', 40)))
        base_tendenze['spot_up_shot_tendency'] = base_tendenze['three_point_shot_tendency'] + 10

        # Passing and Defense (Boosted to guarantee stable assists in the league over 20+ years)
        pass_vis = base_abilita.get('passing_vision', 50)
        if ruolo in ['PG', 'SG']:
            pass_vis = max(68, pass_vis)
        elif ruolo == 'SF':
            pass_vis = max(58, pass_vis)
        base_tendenze['dish_to_open_man_tendency'] = max(45, min(95, pass_vis + 15))
        base_tendenze['pass_out_of_shot_tendency'] = max(35, min(85, base_tendenze['dish_to_open_man_tendency'] - 10))
        base_tendenze['hero_ball_tendency'] = max(5, min(80, base_tendenze['touch_tendency'] - 25))
        base_tendenze['foul_tendency'] = max(40, min(95, 85 - (base_abilita.get('defensive_iq_rating', 50) // 2)))
        base_tendenze['putback_tendency'] = max(5, min(95, base_abilita.get('offensive_rebound_rating', 40)))
        
        # New key tendencies (Rebound & Playmaking)
        off_reb = base_abilita.get('offensive_rebound_rating', 40)
        def_reb = base_abilita.get('defensive_rebound_rating', 40)
        avg_reb = (off_reb + def_reb) // 2
        if three_rtg >= 75 or base_tendenze.get('three_point_shot_tendency', 40) >= 65:
            avg_reb = int(avg_reb * 0.82)
        base_tendenze['rebound_tendency'] = max(20, min(99, avg_reb + random.randint(-4, 4)))
        
        playmaking_base = int(pass_vis * 0.6 + base_abilita.get('passing_accuracy', 50) * 0.4)
        if ruolo == 'PG':
            playmaking_base = max(70, playmaking_base + 10)
        elif ruolo == 'SG':
            playmaking_base = max(45, playmaking_base)
        base_tendenze['playmaking_tendency'] = max(15, min(99, playmaking_base + random.randint(-4, 4)))

        # P&R Logica
        if ruolo in ['PF', 'C']:
            base_tendenze['roll_vs_pop_tendency'] = max(5, min(95, (three_rtg - base_abilita.get('close_shot_rating', 50)) + 50))
        else:
            base_tendenze['roll_vs_pop_tendency'] = 50

        # 6. ROLE PLAYER CLAMPS & ARCHETYPE OVERRIDES (The gameplay fix)
        # Forces extreme behaviors ignoring the pure stats

        # --- Playmakers ---
        if archetipo == "Floor General": # CP3
            base_tendenze['dish_to_open_man_tendency'] = max(88, base_tendenze['dish_to_open_man_tendency'])
            base_tendenze['playmaking_tendency'] = max(90, base_tendenze.get('playmaking_tendency', 75))
            base_tendenze['touch_tendency'] = min(75, base_tendenze['touch_tendency']) # Doesn't monopolize the shots, only the ball
        elif archetipo == "Luka-Esque":
            base_tendenze['touch_tendency'] = max(90, base_tendenze['touch_tendency'])
            base_tendenze['playmaking_tendency'] = max(85, base_tendenze.get('playmaking_tendency', 75))
            base_tendenze['hero_ball_tendency'] = max(70, base_tendenze['hero_ball_tendency'])

        # --- Guards / Wings ---
        elif archetipo in ["3&D Guard", "Tiratrice Pura", "Ala Rimbalzista", "Two-Way Wing"]: 
            # Role players do NOT touch the ball.
            base_tendenze['touch_tendency'] = min(50, base_tendenze['touch_tendency'])
            base_tendenze['hero_ball_tendency'] = 5
            base_tendenze['drive_to_basket_tendency'] = min(30, base_tendenze['drive_to_basket_tendency'])
            if "Tirat" in archetipo or "3&D" in archetipo:
                base_tendenze['spot_up_shot_tendency'] = 95
            if "Rimbalzista" in archetipo:
                base_tendenze['rebound_tendency'] = max(85, base_tendenze.get('rebound_tendency', 60))
        
        elif archetipo == "Mid-Range Specialist": # DeRozan
            base_tendenze['mid_range_shot_tendency'] = max(85, base_tendenze['mid_range_shot_tendency'])
            base_tendenze['three_point_shot_tendency'] = min(35, base_tendenze['three_point_shot_tendency'])
            base_tendenze['touch_tendency'] = max(75, base_tendenze['touch_tendency'])

        # --- Bigs ---
        elif archetipo == "Unicorno": # Porzingis
            base_tendenze['post_up_tendency'] = min(30, base_tendenze['post_up_tendency'])
            base_tendenze['roll_vs_pop_tendency'] = max(85, base_tendenze['roll_vs_pop_tendency']) # Only pops
            base_tendenze['putback_tendency'] = min(20, base_tendenze['putback_tendency'])
            base_tendenze['rebound_tendency'] = min(55, base_tendenze.get('rebound_tendency', 50))
            
        elif archetipo == "Point Center": # Jokic
            base_tendenze['touch_tendency'] = max(85, base_tendenze['touch_tendency'])
            base_tendenze['dish_to_open_man_tendency'] = max(80, base_tendenze['dish_to_open_man_tendency'])
            base_tendenze['playmaking_tendency'] = max(88, base_tendenze.get('playmaking_tendency', 70))
            base_tendenze['post_up_tendency'] = max(70, base_tendenze['post_up_tendency'])
            
        elif archetipo in ["Centro Puro", "Difensore/Rimbalzista"]: # Gobert/Rodman
            # They must grab rebounds and block shots, but on offense they live off scraps
            base_tendenze['touch_tendency'] = min(45, base_tendenze['touch_tendency'])
            base_tendenze['spot_up_shot_tendency'] = 5
            base_tendenze['post_up_tendency'] = min(40, base_tendenze['post_up_tendency'])
            base_tendenze['putback_tendency'] = max(85, base_tendenze['putback_tendency'])
            base_tendenze['rebound_tendency'] = max(90, base_tendenze.get('rebound_tendency', 70))
            
            # BUT, if they are Elite (Shaq), they break the rule and monopolize the post
            if is_elite or valutazione >= 85:
                base_tendenze['touch_tendency'] = max(88, base_tendenze['touch_tendency'])
                base_tendenze['post_up_tendency'] = max(90, base_tendenze['post_up_tendency'])

        # Applying Flaws to the Tendencies
        if flaw == "Foul Prone":
            base_tendenze['foul_tendency'] = 95
        elif flaw == "Black Hole":
            base_tendenze['dish_to_open_man_tendency'] = min(20, base_tendenze['dish_to_open_man_tendency'])
            base_tendenze['pass_out_of_shot_tendency'] = 5

        return Abilita(**base_abilita), Tendenze(**base_tendenze)



    def get_draft_state(self) -> dict:
        """Returns the complete current state of the draft for the API."""
        ordine = []
        for p_idx in range(self.scelte_totali):
            r = (p_idx // len(self.ordine_originale)) + 1
            p_in_r = (p_idx % len(self.ordine_originale)) + 1
            orig_team = self.ordine_originale[p_in_r - 1]
            lookup_key = f"R{r}-{orig_team}"
            curr_team = self.torneo.pick_ownership[1].get(lookup_key, orig_team)
            ordine.append({
                "pick_index": p_idx,
                "round": r,
                "pick": p_in_r,
                "original_owner": orig_team,
                "current_owner": curr_team
            })
            
        on_the_clock = ordine[self.pick_corrente] if self.pick_corrente < self.scelte_totali else None
        
        is_user_turn = False
        if on_the_clock and self.squadra_giocatore:
            is_user_turn = (on_the_clock["current_owner"] == self.squadra_giocatore.nome)
            
        # The user sees the class through their scouts, as on the Scouting page (never the true ratings).
        prospects = scouted_prospects(self.draft_class, getattr(self.torneo, 'scouting_fog_of_war', True),
                                      getattr(self.torneo, 'scout_staff', []))
        
        return {
            "status": "DRAFT_IN_PROGRESS" if self.pick_corrente < self.scelte_totali else "COMPLETED",
            "pick_corrente": self.pick_corrente,
            "scelte_totali": self.scelte_totali,
            "on_the_clock": on_the_clock,
            "ordine": ordine,
            "is_user_turn": is_user_turn,
            "history": self.risultati_draft,
            "prospects": prospects,
            "ultimo_scambio": getattr(self, 'ultimo_scambio', None),
            "trades": self._scambi_draft()
        }

    def _scambi_draft(self) -> list:
        """CPU-to-CPU trades of this draft, kept in the offseason log so the draft wire survives a reload."""
        log = self.torneo.offseason_log_data
        if not isinstance(log, dict):
            log = self.torneo.offseason_log_data = {}
        return log.setdefault('draft_trades', [])

    def _ricorda_scambio(self, trade_result: dict) -> None:
        self._scambi_draft().append({**trade_result, "pick_index": self.pick_corrente})

    def simula_singolo_pick(self) -> dict:
        """Simulates a CPU pick. If it is the user's turn, returns the state."""
        if self.pick_corrente >= self.scelte_totali:
            return self.get_draft_state()
            
        # Reset the last trade on every pick
        self.ultimo_scambio = None
        
        round_num = (self.pick_corrente // len(self.ordine_originale)) + 1
        pick_num_in_round = (self.pick_corrente % len(self.ordine_originale)) + 1
        squadra_originale = self.ordine_originale[pick_num_in_round - 1]
        
        lookup_key = f"R{round_num}-{squadra_originale}"
        nome_squadra_che_sceglie = self.torneo.pick_ownership[1].get(lookup_key, squadra_originale)
        
        # If it is the user's turn, do not simulate and return the state
        if self.squadra_giocatore and nome_squadra_che_sceglie == self.squadra_giocatore.nome:
            return self.get_draft_state()
            
        # CPU-CPU trade attempt before the pick (evaluated contextually in the first round)
        if self.pick_corrente < len(self.ordine_originale):
            from trades.engines import draft_night
            from trades.trade_finder import TradeFinder
            finder = TradeFinder(self.torneo, self.squadre, self.squadra_giocatore)
            team_obj = next((s for s in self.squadre if s.nome == nome_squadra_che_sceglie), None)
            if team_obj:
                trade_result = draft_night.run_on_the_clock(finder, team_obj, self.pick_corrente + 1, lookup_key)
                if trade_result:
                    self.ultimo_scambio = trade_result
                    self._ricorda_scambio(trade_result)
                    # Recompute who picks now for this pick after the trade
                    nome_squadra_che_sceglie = self.torneo.pick_ownership[1].get(lookup_key, squadra_originale)
            
        self._esegui_scelta_IA(round_num, pick_num_in_round, nome_squadra_che_sceglie, squadra_originale)
        self.pick_corrente += 1
        self.torneo.draft_pick_corrente = self.pick_corrente
        
        # End-of-draft save
        if self.pick_corrente >= self.scelte_totali:
            self.torneo.offseason_log_data['draft'] = self.risultati_draft
            self.torneo.offseason_log_data['draft_in_progress'] = None
            
        return self.get_draft_state()

    def esegui_scelta_utente(self, nome_giocatore_scelto: str) -> dict:
        """Registers the user's pick and advances by one pick."""
        if self.pick_corrente >= self.scelte_totali:
            return self.get_draft_state()
            
        round_num = (self.pick_corrente // len(self.ordine_originale)) + 1
        pick_num_in_round = (self.pick_corrente % len(self.ordine_originale)) + 1
        squadra_originale = self.ordine_originale[pick_num_in_round - 1]
        
        giocatore_scelto = next((p for p in self.draft_class if p.nome == nome_giocatore_scelto), None)
        
        if giocatore_scelto:
            self._registra_scelta(giocatore_scelto, round_num, pick_num_in_round, self.squadra_giocatore.nome, squadra_originale)
            self.draft_class.remove(giocatore_scelto)
        else:
            main_log.warning(f"Player '{nome_giocatore_scelto}' not found on the draft board. The AI picks for the user.")
            self._esegui_scelta_IA(round_num, pick_num_in_round, self.squadra_giocatore.nome, squadra_originale)
            
        self.pick_corrente += 1
        self.torneo.draft_pick_corrente = self.pick_corrente
        
        # End-of-draft save
        if self.pick_corrente >= self.scelte_totali:
            self.torneo.offseason_log_data['draft'] = self.risultati_draft
            self.torneo.offseason_log_data['draft_in_progress'] = None
            
        return self.get_draft_state()

    def esegui_o_continua_draft(self):
        """Runs the draft (CPU picks) until the user is on the clock, and returns the draft results."""
        while self.pick_corrente < self.scelte_totali:
            round_num = (self.pick_corrente // len(self.ordine_originale)) + 1
            pick_num_in_round = (self.pick_corrente % len(self.ordine_originale)) + 1
            squadra_originale = self.ordine_originale[pick_num_in_round - 1]
            
            lookup_key = f"R{round_num}-{squadra_originale}"
            nome_squadra_che_sceglie = self.torneo.pick_ownership[1].get(lookup_key, squadra_originale)
            
            if self.squadra_giocatore and nome_squadra_che_sceglie == self.squadra_giocatore.nome:
                draft_board = [{"nome": p.nome, "ruolo": p.ruolo, "ovr": p.valutazione, "pot": p.potenziale, "provenance": p.provenance, "pedigree": p.pedigree} for p in self.draft_class[:20]]
                return {
                    "status": "USER_PICK",
                    "pick_info": {"round": round_num, "pick": pick_num_in_round, "team": nome_squadra_che_sceglie},
                    "draft_board": draft_board
                }
            
            self._esegui_scelta_IA(round_num, pick_num_in_round, nome_squadra_che_sceglie, squadra_originale)
            self.pick_corrente += 1
            self.torneo.draft_pick_corrente = self.pick_corrente
            
        return self.risultati_draft


    def _esegui_scelta_IA(self, round_num: int, pick_num_in_round: int, nome_squadra_che_sceglie: str, squadra_originale: str):
        """Draft logic that balances BPA and Need."""
        if not self.draft_class: return

        squadra = next((s for s in self.squadre if s.nome == nome_squadra_che_sceglie), None)
        if not squadra:
            giocatore_scelto = self.draft_class.pop(0)
            self._registra_scelta(giocatore_scelto, round_num, pick_num_in_round, nome_squadra_che_sceglie, squadra_originale)
            return

        fo = getattr(self.torneo, 'front_office', None)
        plan = getattr((getattr(fo, 'plans', None) or {}).get(squadra.nome), 'state', None) or "MIDDLE"
        user = getattr(self.squadra_giocatore, 'nome', None)
        gm = fo.seated_gm(squadra.nome) if fo is not None and squadra.nome != user and hasattr(fo, 'seated_gm') else None
        era = era_lines_for(self.torneo)
        giocatore_scelto = best_prospect(self.draft_class, squadra.roster, era, plan, pick_num_in_round,
                                         gm=gm, year=era.year)
        main_log.info(f"DRAFT AI ({squadra.nome}, {plan}): picks {giocatore_scelto.nome} ({giocatore_scelto.ruolo}).")

        if giocatore_scelto in self.draft_class:
            self.draft_class.remove(giocatore_scelto)
        self._registra_scelta(giocatore_scelto, round_num, pick_num_in_round, nome_squadra_che_sceglie, squadra_originale)

    def _registra_scelta(self, giocatore: Giocatore, round_num: int, pick_num_in_round: int, nome_squadra: str, squadra_originale: str):
        """Assigns a player to a team and records the log."""
        squadra_che_sceglie = next((s for s in self.squadre if s.nome == nome_squadra), None)

        if squadra_che_sceglie:
            cfg_eco = CONFIG.ECONOMY
            from core.models import ACTIVE_TOURNAMENT
            raw_cap = ACTIVE_TOURNAMENT.salary_cap if ACTIVE_TOURNAMENT else 155.0
            anno = getattr(ACTIVE_TOURNAMENT, 'anno_corrente', 2025) if ACTIVE_TOURNAMENT else 2025
            is_no_cap = (ACTIVE_TOURNAMENT and getattr(ACTIVE_TOURNAMENT, 'cba_mode', '') == 'no_cap') or (raw_cap >= 9000.0)
            cap = cfg_eco.get_cap_for_year(anno, raw_cap, is_no_cap)
            cap_ratio = cap / 155.0

            if round_num == 1:
                salario_base = next((sal for pos, sal in sorted(cfg_eco.ROOKIE_SALARY_SCALE.items()) if pick_num_in_round <= pos), 2.5)
                salario_rookie = max(0.5, round(salario_base * cap_ratio, 2))
                anni_contratto = 4
                team_opt = True
            else:
                salario_rookie = max(0.4, round(1.6 * cap_ratio, 2))
                anni_contratto = 2
                team_opt = True

            giocatore.contract = Contract(anni_rimanenti=anni_contratto, salario_annuale=salario_rookie, team_option=team_opt)
            
            giocatore.squadra = squadra_che_sceglie
            giocatore.is_rookie = True  # Tag rookies for the end-of-season awards
            if round_num == 1 or giocatore.potenziale >= 80:
                giocatore.is_untouchable = True  # Untouchable: core and future of the franchise
            squadra_che_sceglie.roster.append(giocatore)
            
            self.risultati_draft.append({
                "scelta": f"R{round_num} P{pick_num_in_round}",
                "squadra": nome_squadra,
                "original_owner": squadra_originale,  # To check pick trades
                "nome": giocatore.nome,
                "ruolo": giocatore.ruolo,
                "valutazione": giocatore.valutazione,
                "potenziale": giocatore.potenziale,
                "provenance": giocatore.provenance,
                "pedigree": giocatore.pedigree
            })
            main_log.info(f"DRAFT: With pick #{pick_num_in_round} (R{round_num}), the {nome_squadra} select {giocatore.nome}.")
            record_draft_pick(self.torneo, nome_squadra, giocatore, (round_num - 1) * len(self.squadre) + pick_num_in_round)

    def _analizza_bisogni_roster(self, squadra: 'Squadra') -> List[str]:
        """
        Analyzes a team's roster to determine the positional needs.
        """
        if not squadra or not squadra.roster:
            return ['PG', 'SG', 'SF', 'PF', 'C']

        position_scores = {'PG': 0, 'SG': 0, 'SF': 0, 'PF': 0, 'C': 0}
        
        for player in squadra.roster:
            score = player.ovr + player.potenziale
            if player.eta < 25:
                score *= 1.5
            elif player.eta > 30:
                score *= 0.5
            
            for pos, val_pos in player.valutazioni_posizionali.items():
                if pos in position_scores:
                    base_pos_score = (val_pos / 99.0) * score
                    multiplier = 2.0 if player.ruolo == pos else 1.0
                    position_scores[pos] += base_pos_score * multiplier
        
        bisogni_ordinati = sorted(position_scores, key=position_scores.get)
        return bisogni_ordinati