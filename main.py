# main.py (REFACTORED VERSION FOR THE API)
import sys
from core import db_manager
import os
import json
import random
import traceback
import logging
from typing import List, Tuple, Optional, Dict, Set, Any
from dataclasses import dataclass
from core.config import CONFIG, normalize_owner_personality
from core.league.draft_source import draft_class_file
from core.league.registry import current_league_era, get_active_registry
from core.roles import normalize_role, normalize_role_keys
from core.models import Squadra, Giocatore, Abilita, Tendenze, Contract, CumulativeStats, POSITION_COMPATIBILITY_PENALTY, applica_regole_anni_opzioni_contratto, add_retired_player, league_season_scales
from core.game_engine import Partita # We assume it exists
from core.models import Coach

# Import extracted modules
from trades.calendar import deadline_passed
from trades.trade_finder import TradeFinder
from trades.windows import refresh_untouchables, run_trade_window
from offseason.draft import Draft
from offseason.free_agency import FreeAgency
from core.podcast_logger import PodcastLogger
from core.save_manager import get_historical_file_path
from core.lottery_view import annotate_owners, hunt_steps, lottery_teams, lottery_weights, pick_owner
from core.lottery_view import odds_table as lottery_odds_table
from core.all_star_weekend import pick_host, pick_sophomores, play_weekend, player_line
from core.front_office.awards import coach_of_the_year, gm_of_the_year, record_gm_award
from core.front_office.offseason import front_office_offseason
from core.front_office.plans import checkpoint_deadline, checkpoint_new_season, rebuild_on_schedule, team_plan_state
from core.front_office.seasons import (close_season, ensure_season_marks, expected_wins, league_avg_ovr,
                                       mark_coach_change, mark_season_end)
from core.front_office.state import build_front_office, current_year, ensure_front_office
from core.front_office import trade_requests

# Import news generation functions for in-game events
from core.news_generator import (generate_game_performance_news, generate_injury_news,
                                 generate_rivalry_postgame_news, generate_rumor_news)
try:
    from core.records import check_and_update_records
except ImportError:
    check_and_update_records = None
NEWS_ENABLED = True

# Import rivalry and storyline systems
from core.rivalry_tracker import RivalryTracker
from core.storyline_engine import StorylineEngine


 # Make sure Coach is defined in models.py

# --- SETUP LOGGER ---
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def _log_dir() -> str:
    from core import paths
    return paths.user_path("scratch")

def setup_main_logger():
    main_logger = logging.getLogger('main_sim'); main_logger.setLevel(logging.DEBUG); main_logger.propagate = False
    if main_logger.hasHandlers(): main_logger.handlers.clear()
    log_dir = _log_dir()
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "simulation_log.txt")
    file_formatter = logging.Formatter('%(message)s'); file_handler = logging.FileHandler(filename=log_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG); file_handler.setFormatter(file_formatter); main_logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout); console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s'); console_handler.setFormatter(console_formatter); main_logger.addHandler(console_handler)
    return main_logger
main_log = setup_main_logger()
def stampa_report_fine_stagione(torneo: 'Tournament'):
    """
    Simple version of the end-of-season report, with no external dependencies.
    """
    print(f"\n{'='*25} REPORT FINE REGULAR SEASON {torneo.season_number} {'='*25}")

    squadre_ordinate = sorted(torneo.squadre, key=lambda s: (s.conference, -s.vittorie))

    for squadra in squadre_ordinate:
        print(f"\n--- {squadra.nome.upper()} ({squadra.vittorie}-{squadra.sconfitte}) ---")
        header = f"{'Giocatore':<20} | {'PG':>3} | {'MIN':>5} | {'PTS':>5} | {'REB':>5} | {'AST':>5} | {'STL':>5} | {'BLK':>5} | {'FG%':>6} | {'3PM/A':>7} | {'3P%':>6}"
        print(header)
        print("-" * len(header))
        
        giocatori_ordinati = sorted(
            [p for p in squadra.roster if p.season_stats.partite_giocate > 0],
            key=lambda p: p.season_stats.punti / p.season_stats.partite_giocate,
            reverse=True
        )

        for p in giocatori_ordinati:
            stats = p.season_stats; pg = stats.partite_giocate
            min_pg = stats.minuti_giocati / pg if pg > 0 else 0
            pts_pg = stats.punti / pg if pg > 0 else 0
            reb_pg = stats.rimbalzi / pg if pg > 0 else 0
            ast_pg = stats.assist / pg if pg > 0 else 0
            stl_pg = stats.steals / pg if pg > 0 else 0
            blk_pg = stats.blocks / pg if pg > 0 else 0
            fg_tentati = stats.tiri_tentati_2 + stats.tiri_tentati_3
            fg_fatti = stats.tiri_fatti_2 + stats.tiri_fatti_3
            fg_perc = (fg_fatti / fg_tentati * 100) if fg_tentati > 0 else 0
            p3m_pg = stats.tiri_fatti_3 / pg if pg > 0 else 0
            p3a_pg = stats.tiri_tentati_3 / pg if pg > 0 else 0
            p3_str = f"{p3m_pg:.1f}/{p3a_pg:.1f}"
            p3_perc = (stats.tiri_fatti_3 / stats.tiri_tentati_3 * 100) if stats.tiri_tentati_3 > 0 else 0

            try:
                print(f"{p.nome:<20} | {pg:>3} | {min_pg:>5.1f} | {pts_pg:>5.1f} | {reb_pg:>5.1f} | {ast_pg:>5.1f} | {stl_pg:>5.1f} | {blk_pg:>5.1f} | {fg_perc:>5.1f}% | {p3_str:>7} | {p3_perc:>5.1f}%")
            except UnicodeEncodeError:
                safe_nome = p.nome.encode('ascii', errors='replace').decode('ascii')
                print(f"{safe_nome:<20} | {pg:>3} | {min_pg:>5.1f} | {pts_pg:>5.1f} | {reb_pg:>5.1f} | {ast_pg:>5.1f} | {stl_pg:>5.1f} | {blk_pg:>5.1f} | {fg_perc:>5.1f}% | {p3_str:>7} | {p3_perc:>5.1f}%")

def stampa_report_squadre_fine_stagione(torneo: 'Tournament'):
    print("\n========================= TEAM STATISTICS - SEASON {} =========================".format(torneo.season_number))
    header = f"{'Squadra':<25} | {'W-L':<7} | {'PPG':<6} | {'Opp PPG':<8} | {'Diff.':<6} | {'Off Rtg':<8} | {'Def Rtg':<8} | {'FGA':<6} | {'3PA':<6} | {'APG':<6} | {'RPG':<6}"
    print(header)
    print("-" * len(header))

    squadre_ordinate = sorted(torneo.squadre, key=lambda s: s.vittorie, reverse=True)

    pace_est_base = round(100.0 * (torneo.get_era_pace_factor() if hasattr(torneo, 'get_era_pace_factor') else 0.95), 1)

    for squadra in squadre_ordinate:
        partite_giocate = squadra.vittorie + squadra.sconfitte
        if partite_giocate == 0: continue

        # Points average calculation
        ppg_fatti = round(squadra.punti_fatti_stagione / partite_giocate, 1)
        ppg_subiti = round(squadra.punti_subiti_stagione / partite_giocate, 1)
        differenziale = round(ppg_fatti - ppg_subiti, 1)

        # Basic rating calculation (Points per 100 possessions based on the era's pace)
        possessi_stimati = partite_giocate * pace_est_base 
        off_rating = round((squadra.punti_fatti_stagione / possessi_stimati) * 100, 1) if possessi_stimati > 0 else 0
        def_rating = round((squadra.punti_subiti_stagione / possessi_stimati) * 100, 1) if possessi_stimati > 0 else 0

        # Formatting for printing
        record = f"{squadra.vittorie}-{squadra.sconfitte}"
        diff_str = f"+{differenziale}" if differenziale > 0 else str(differenziale)

        fg_tentati_tot = sum(p.season_stats.tiri_tentati_2 + p.season_stats.tiri_tentati_3 for p in squadra.roster)
        fg_tentati = round(fg_tentati_tot / partite_giocate, 1)
        
        p3a_tot = sum(p.season_stats.tiri_tentati_3 for p in squadra.roster)
        p3a = round(p3a_tot / partite_giocate, 1)

        ast_tot = sum(p.season_stats.assist for p in squadra.roster)
        apg = round(ast_tot / partite_giocate, 1)
        
        reb_tot = sum(p.season_stats.rimbalzi for p in squadra.roster)
        rpg = round(reb_tot / partite_giocate, 1)

        print(f"{squadra.nome:<25} | {record:<7} | {ppg_fatti:<6.1f} | {ppg_subiti:<8.1f} | {diff_str:<6} | {off_rating:<8.1f} | {def_rating:<8.1f} | {fg_tentati:<6.1f} | {p3a:<6.1f} | {apg:<6.1f} | {rpg:<6.1f}")

    print("-" * len(header))

def coach_retires_now(age: int, roll: float) -> bool:
    """A head coach this old retires this offseason (roll in [0, 1)): never before CONFIG.COACHING.RETIRE_MIN_AGE,
    then RETIRE_BASE_CHANCE plus RETIRE_CHANCE_PER_YEAR a year, always at RETIRE_MAX_AGE."""
    cc = CONFIG.COACHING
    if age < cc.RETIRE_MIN_AGE:
        return False
    if age >= cc.RETIRE_MAX_AGE:
        return True
    return roll < cc.RETIRE_BASE_CHANCE + (age - cc.RETIRE_MIN_AGE) * cc.RETIRE_CHANCE_PER_YEAR


def tag_season1_rookies(torneo) -> Tuple[int, str]:
    """Tags the rookies already on the starting rosters (is_rookie), so season 1 has a Rookie of the Year.

    The starting year's draft file (DRAFT_<start year>.json, names under "name" or "nome") when the league has one;
    otherwise the young players in their first year on the team (CONFIG.LEAGUE.SEASON1_ROOKIE_*), because league
    files carry no draft year. Returns (players tagged, source)."""
    players = [p for s in torneo.squadre for p in s.roster]
    year = int(getattr(torneo, 'starting_year', 2002))
    path = draft_class_file(torneo, year)
    if path:
        with open(path, 'r', encoding='utf-8') as f:
            names = {e.get("name") or e.get("nome") for e in json.load(f) if isinstance(e, dict)}
        rookies = [p for p in players if p.nome in names]
        source = f"DRAFT_{year}.json"
    else:
        cfg = CONFIG.LEAGUE
        rookies = [p for p in players if p.eta <= cfg.SEASON1_ROOKIE_MAX_AGE
                   and getattr(p, '_start_years_on_team', 99) <= cfg.SEASON1_ROOKIE_MAX_YEARS_ON_TEAM]
        source = "first-year young players"
    for p in rookies:
        p.is_rookie = True
    for p in players:
        p.__dict__.pop('_start_years_on_team', None)
    return len(rookies), source


def calcola_hof_score(player_career_data: List[Dict]) -> Tuple[int, Dict]:
    """
    Computes a player's Hall of Fame score by analyzing his whole career.
    Returns a numeric score and a dictionary with the career highlights.
    """
    if not player_career_data:
        return 0, {}

    # ### SCORE AND HIGHLIGHTS INITIALIZATION ###
    score = 0
    
    # Data structure for the highlights. All the statistics are grouped together.
    highlights = {
        "accolades": {
            "titoli": 0, "mvp": 0, "finals_mvp": 0, "dpoy": 0,
            "all_nba_1st": 0, "all_nba_total": 0, "all_star": 0
        },
        "stats": {
            "career_ppg": 0.0, "career_rpg": 0.0, "career_apg": 0.0, # Career averages
            "peak_ppg": 0.0  # Best scoring season
        }
    }
    
    # Weights for each individual award
    punti_premi = {
        "MVP": 60, "Finals MVP": 50, "DPOY": 30,
        "All-NBA 1st": 25, "All-NBA 2nd": 15, "All-NBA 3rd": 8,
        "All-Defensive": 12, "6th Man": 5, "All-Rookie": 2, "ROY": 10,
        "All-Star Starter": 10, "All-Star": 8
    }
    
    # Variables for aggregate calculations
    tot_punti_carriera = 0
    stagioni_da_30_ppg = 0
    tot_ppg, tot_rpg, tot_apg = 0.0, 0.0, 0.0
    num_stagioni = len(player_career_data)
    titoli_contribuiti = 0

    # ### SEASON-BY-SEASON ANALYSIS LOOP ###
    for season in player_career_data:
        premi_lista = season.get("premi") or season.get("awards") or []
        
        # 1. Score calculation based on the awards
        for premio in premi_lista:
            score += punti_premi.get(premio, 0)
        
        # 2. Update of the highlights (accolades)
        if "MVP" in premi_lista: highlights["accolades"]["mvp"] += 1
        if "Finals MVP" in premi_lista: highlights["accolades"]["finals_mvp"] += 1
        if "DPOY" in premi_lista: highlights["accolades"]["dpoy"] += 1
        if "All-NBA 1st" in premi_lista: highlights["accolades"]["all_nba_1st"] += 1
        if any("All-NBA" in s for s in premi_lista): highlights["accolades"]["all_nba_total"] += 1
        if any(x in premi_lista for x in ["All-Star Starter", "All-Star"]):
            highlights["accolades"]["all_star"] += 1
        
        # 3. Update of the aggregate and peak statistics
        stats_rs = season.get("stats_rs")
        if not stats_rs and "pts" in season and "gp" in season:
            gp = season.get("gp") or 1
            stats_rs = {
                "ppg": round(season.get("pts", 0) / gp, 1),
                "rpg": round(season.get("reb", 0) / gp, 1),
                "apg": round(season.get("ast", 0) / gp, 1)
            }

        if stats_rs:
            ppg_season = stats_rs.get("ppg", 0.0)
            rpg_season = stats_rs.get("rpg", 0.0)
            apg_season = stats_rs.get("apg", 0.0)
            
            # Update total statistics for career averages
            tot_ppg += ppg_season
            tot_rpg += rpg_season
            tot_apg += apg_season
            
            # Compute total career points
            partite_giocate = season.get("partite_giocate_rs", 82)
            tot_punti_carriera += ppg_season * partite_giocate
            
            # Track elite scoring seasons
            if ppg_season >= 30:
                stagioni_da_30_ppg += 1
            
            # Compare and update the PPG peak
            if ppg_season > highlights["stats"]["peak_ppg"]:
                highlights["stats"]["peak_ppg"] = ppg_season
                
            # 4. Scaled assignment of title points based on the actual contribution
            if season.get("is_champion", False):
                highlights["accolades"]["titoli"] += 1
                
                # Compute the contribution to tell whether he is a star or a bench player
                has_finals_mvp = "Finals MVP" in season.get("premi", [])
                has_mvp = "MVP" in season.get("premi", [])
                has_all_nba = any("All-NBA" in p for p in season.get("premi", []))
                
                # Weighted contribution index (points + rebounds + assists)
                contrib = ppg_season + rpg_season * 1.2 + apg_season * 1.5
                
                title_points = CONFIG.HISTORY.HOF_TITLE_POINTS
                if has_mvp or has_finals_mvp or has_all_nba or contrib >= title_points[0][0]:
                    # Team leader: the only titles that count for the multi-title bonus
                    score += title_points[0][1]
                    titoli_contribuiti += 1
                else:
                    # Starter / rotation player / bench: less, and nothing for a garbage-time ring
                    score += next((pts for bar, pts in title_points[1:] if contrib >= bar), 0)

    # Compute the final career averages
    if num_stagioni > 0:
        highlights["stats"]["career_ppg"] = round(tot_ppg / num_stagioni, 1)
        highlights["stats"]["career_rpg"] = round(tot_rpg / num_stagioni, 1)
        highlights["stats"]["career_apg"] = round(tot_apg / num_stagioni, 1)

    # ### APPLYING BONUSES TO THE FINAL SCORE ###
    # Additional milestone bonus for significant titles as a protagonist
    for titles_needed, bonus in CONFIG.HISTORY.HOF_TITLES_BONUS:
        if titoli_contribuiti >= titles_needed:
            score += bonus
    
    # Longevity bonus
    score += num_stagioni * 5
    
    # Bonus for total points milestones
    if tot_punti_carriera > 20000: score += 25
    if tot_punti_carriera > 25000: score += 35
    if tot_punti_carriera > 30000: score += 50
    
    # Bonus for scoring peaks
    if highlights["stats"]["peak_ppg"] >= 32: score += 20
    if stagioni_da_30_ppg >= 3: score += 30

    return int(score), highlights

def genera_e_assegna_coach_iniziali(squadre: List[Squadra]):
    """
    ### SMART COACH ASSIGNMENT v1.0 ###
    Analyzes each team's star player and assigns a coaching style that fits their archetype.
    """
    from core.league.registry import staff_names
    nomi_coach = staff_names("coach_names", CONFIG.COACHINGSTYLES.COACH_NAMES)
    stili_disponibili = list(CONFIG.COACHINGSTYLES.STYLES.keys())
    
    def _detect_player_archetype(player) -> str:
        """Detect the archetype of a player based on their stats."""
        if not player:
            return "BALANCED"
        
        abilities = player.abilita
        role = player.ruolo
        
        # POINT GUARD ARCHETYPE: Elite playmaker who orchestrates the offense
        if role in ['PG'] and abilities.passing_vision >= 85:
            return "POINT_GUARD"
        
        # POINT-CENTER/FORWARD ARCHETYPE: Big with elite vision (Jokic, Sabonis)
        if role in ['C', 'PF'] and abilities.passing_vision >= 88:
            return "POINT_BIG"
        
        # SCORING GUARD ARCHETYPE: Perimeter scorer (SGA, Booker, Curry)
        if role in ['PG', 'SG'] and (abilities.three_point_shot_rating >= 85 or abilities.mid_range_shot_rating >= 85):
            return "SCORING_GUARD"
        
        # POST DOMINATOR ARCHETYPE: Traditional center (Embiid, AD)
        if role in ['C', 'PF'] and (abilities.close_shot_rating >= 80 or player.ovr >= 88) and abilities.strength >= 78:
            return "POST_DOMINATOR"
        
        # TWO-WAY BIG ARCHETYPE: Defensive anchor (Gobert, Mobley)
        if role in ['C', 'PF'] and (abilities.interior_defense_rating >= 85 or abilities.block_rating >= 80):
            return "DEFENSIVE_BIG"
        
        # WING SCORER ARCHETYPE: Versatile wing (Tatum, LeBron, Kawhi)
        if role in ['SF'] and player.ovr >= 85:
            return "WING_SCORER"
        
        # SLASHER ARCHETYPE: Explosive driver (Giannis, Zion)
        if (abilities.speed >= 80 or player.ovr >= 88) and abilities.close_shot_rating >= 80:
            return "SLASHER"
        
        return "BALANCED"
    
    # Map archetypes to preferred coaching styles
    ARCHETYPE_TO_STYLES = {
        "POINT_GUARD": ["Point Guard Maestro", "System Basketball", "Pace & Space"],
        "POINT_BIG": ["System Basketball", "Point Guard Maestro", "Triangle Offense"],
        "SCORING_GUARD": ["Pace & Space", "Perimeter-centric", "Run and Gun"],
        "POST_DOMINATOR": ["Post Play Dominance", "Twin Towers", "Grit & Grind"],
        "DEFENSIVE_BIG": ["Defensive Minded", "Grit & Grind", "Twin Towers"],
        "WING_SCORER": ["Balanced Offense", "Run and Gun", "Pace & Space"],
        "SLASHER": ["Fast Break Offense", "Run and Gun", "Pace & Space"],
        "BALANCED": stili_disponibili  # Random from all styles
    }
    
    for squadra in squadre:
        # Find the team's best player
        if squadra.roster:
            star_player = max(squadra.roster, key=lambda p: p.ovr)
            archetype = _detect_player_archetype(star_player)
        else:
            archetype = "BALANCED"
            star_player = None
        
        # Get coaching style based on archetype
        preferred_styles = ARCHETYPE_TO_STYLES.get(archetype, stili_disponibili)
        coach_style = random.choice(preferred_styles)
        
        # Get coach name
        if not nomi_coach:
            nome_coach = f"Coach {random.choice(['Smith', 'Johnson', 'Williams', 'Brown', 'Davis'])}"
        else:
            nome_coach = random.choice(nomi_coach)
            nomi_coach.remove(nome_coach)
            
        coach = Coach(
            nome=nome_coach,
            stile_gioco=coach_style,
            ovr_offensivo=random.randint(70, 95),
            ovr_difensivo=random.randint(70, 95),
            eta=random.randint(35,55),
            potenziale=random.randint(85, 98)
        )
        squadra.coach = coach
        
        # Optional logging for debugging
        # if star_player:
        #     print(f"{squadra.nome}: Star={star_player.nome} ({archetype}) -> Coach Style: {coach_style}")
def _all_star_premi(torneo) -> dict:
    """The All-Star keys of a season's history entry, including the whole weekend snapshot (None if not played)."""
    def winner(contest):
        return contest.get('winner', 'N/A') if isinstance(contest, dict) else "N/A"
    starters = getattr(torneo, 'all_star_starters', {})
    reserves = getattr(torneo, 'all_star_reserves', {})
    return {
        "all_star_starters": {conf: [p.nome for p in starters.get(conf, [])] for conf in ('east', 'west')},
        "all_star_reserves": {conf: [p.nome for p in reserves.get(conf, [])] for conf in ('east', 'west')},
        "all_star_mvp": getattr(torneo, 'all_star_mvp', None) or "N/A",
        "three_point_contest": winner(getattr(torneo, 'three_point_contest', None)),
        "dunk_contest": winner(getattr(torneo, 'dunk_contest', None)),
        "all_star_weekend": getattr(torneo, 'all_star_weekend', None),
    }


def build_season_entry(torneo: 'Tournament', record_standings: bool = False) -> dict:
    """The season summary saved in league_history.json (champion, awards, standings, team stats).
    record_standings also records each team's standing on its own history (done once, when archiving)."""
    
    # Standings & Team Stats snapshot
    standings_snapshot = []
    team_stats_snapshot = []
    pace_est_base = round(100.0 * (torneo.get_era_pace_factor() if hasattr(torneo, 'get_era_pace_factor') else 0.95), 1)

    # Rank East & West separately for conference seeds 1-15, and rank all 30 teams for overall league rank 1-30
    east_teams = sorted([s for s in torneo.squadre if getattr(s, 'conference', '').lower() in ['east', 'est']], key=lambda s: (-s.vittorie, s.sconfitte))
    west_teams = sorted([s for s in torneo.squadre if getattr(s, 'conference', '').lower() in ['west', 'ovest']], key=lambda s: (-s.vittorie, s.sconfitte))
    overall_teams = sorted(torneo.squadre, key=lambda s: (-s.vittorie, s.sconfitte))
    
    east_seed_map = {s.nome: i + 1 for i, s in enumerate(east_teams)}
    west_seed_map = {s.nome: i + 1 for i, s in enumerate(west_teams)}
    league_rank_map = {s.nome: i + 1 for i, s in enumerate(overall_teams)}

    for squadra in overall_teams:
        gp = squadra.vittorie + squadra.sconfitte
        pts_for = getattr(squadra, 'punti_fatti_stagione', getattr(squadra, 'punti_fatti', 0))
        pts_against = getattr(squadra, 'punti_subiti_stagione', getattr(squadra, 'punti_subiti', 0))
        w_pct = round(squadra.vittorie / max(1, gp), 3) if gp > 0 else 0.0
        ppg = round(pts_for / max(1, gp), 1) if gp > 0 else 0.0
        oppg = round(pts_against / max(1, gp), 1) if gp > 0 else 0.0
        diff = round(ppg - oppg, 1)

        conf_name = getattr(squadra, 'conference', 'East')
        conf_seed = east_seed_map.get(squadra.nome, west_seed_map.get(squadra.nome, 1))
        league_rank = league_rank_map.get(squadra.nome, 1)
        is_champ = bool(torneo.campione and torneo.campione.nome == squadra.nome)
        
        # Determine playoff round reached
        playoff_round = "Regular Season"
        if is_champ:
            playoff_round = "Campione NBA 🏆"
        elif getattr(torneo, 'playoff_bracket_data', None):
            finals = torneo.playoff_bracket_data.get('finals', [])
            f_east = torneo.playoff_bracket_data.get('east', {}).get('finals', [])
            f_west = torneo.playoff_bracket_data.get('west', {}).get('finals', [])
            if finals and any(isinstance(s, dict) and (s.get('s1_nome') == squadra.nome or s.get('s2_nome') == squadra.nome) for s in finals):
                playoff_round = "Finali NBA"
            elif any(isinstance(s, dict) and (s.get('s1_nome') == squadra.nome or s.get('s2_nome') == squadra.nome) for s in f_east + f_west):
                playoff_round = "Finali Conference"
            else:
                # The real bracket, not the seed: a 7-8 seed out in the play-in is a play-in team, and seeds
                # 9-10 are lottery teams in a season without the play-in.
                in_playoffs = any(s is squadra or getattr(s, 'nome', None) == squadra.nome
                                  for side in (getattr(torneo, 'playoff_teams', None) or {}).values() for s in side)
                if in_playoffs:
                    playoff_round = "Playoffs"
                elif getattr(torneo, 'enable_play_in', False) and conf_seed <= CONFIG.DASHBOARD.PLAY_IN_LAST_SEED:
                    playoff_round = "Play-In"
                else:
                    playoff_round = "Lottery"

        # Record onto the team model history (only when the season is archived)
        if record_standings:
            squadra.record_season_standing(
                season=torneo.season_number,
                year=getattr(torneo, 'anno_corrente', 2025),
                conf_seed=conf_seed,
                league_rank=league_rank,
                wins=squadra.vittorie,
                losses=squadra.sconfitte,
                ppg=ppg,
                oppg=oppg,
                is_champion=is_champ,
                playoff_round=playoff_round
            )

        standings_snapshot.append({
            "team": squadra.nome,
            "conference": conf_name,
            "conf_seed": conf_seed,
            "league_rank": league_rank,
            "wins": squadra.vittorie,
            "losses": squadra.sconfitte,
            "win_pct": w_pct,
            "gp": gp,
            "ppg": ppg,
            "oppg": oppg,
            "diff": diff,
            "is_champion": is_champ,
            "playoff_round": playoff_round
        })

        if gp > 0:
            possessi_stimati = gp * pace_est_base
            off_rating = round((pts_for / possessi_stimati) * 100, 1) if possessi_stimati > 0 else 0.0
            def_rating = round((pts_against / possessi_stimati) * 100, 1) if possessi_stimati > 0 else 0.0
            fg_tentati = round(sum(p.season_stats.tiri_tentati_2 + p.season_stats.tiri_tentati_3 for p in squadra.roster) / gp, 1)
            p3a = round(sum(p.season_stats.tiri_tentati_3 for p in squadra.roster) / gp, 1)
            apg = round(sum(p.season_stats.assist for p in squadra.roster) / gp, 1)
            rpg = round(sum(p.season_stats.rimbalzi for p in squadra.roster) / gp, 1)

            team_stats_snapshot.append({
                "team": squadra.nome,
                "conference": conf_name,
                "conf_seed": conf_seed,
                "league_rank": league_rank,
                "record": f"{squadra.vittorie}-{squadra.sconfitte}",
                "wins": squadra.vittorie,
                "losses": squadra.sconfitte,
                "win_pct": w_pct,
                "gp": gp,
                "ppg": ppg,
                "oppg": oppg,
                "diff": diff,
                "off_rating": off_rating,
                "def_rating": def_rating,
                "fga": fg_tentati,
                "3pa": p3a,
                "apg": apg,
                "rpg": rpg
            })

    stagione_corrente_data = {
        "stagione": torneo.season_number,
        "anno": getattr(torneo, 'anno_corrente', 2025),
        "campione": torneo.campione.nome if torneo.campione else "Playoff non disputati",
        "mvp_finali": torneo.finals_mvp.nome if torneo.finals_mvp else "N/A",
        "premi": {
            "mvp": torneo.regular_season_mvp.nome if torneo.regular_season_mvp else "N/A",
            "dpoy": torneo.defensive_player_of_the_year.nome if torneo.defensive_player_of_the_year else "N/A",
            "sesto_uomo": torneo.sesto_uomo.nome if torneo.sesto_uomo else "N/A",
            "roy": torneo.rookie_of_the_year.nome if getattr(torneo, 'rookie_of_the_year', None) else "N/A",
            "mip": torneo.most_improved_player.nome if getattr(torneo, 'most_improved_player', None) else "N/A",
            "coy": (getattr(torneo, 'coach_of_the_year', None) or {}).get("nome", "N/A"),
            "gm_of_the_year": (getattr(torneo, 'gm_of_the_year', None) or {}).get("nome", "N/A"),
            "all_nba_1st": [p.nome for p in torneo.all_nba_teams[0]] if getattr(torneo, 'all_nba_teams', None) and len(torneo.all_nba_teams) > 0 else [],
            "all_nba_2nd": [p.nome for p in torneo.all_nba_teams[1]] if getattr(torneo, 'all_nba_teams', None) and len(torneo.all_nba_teams) > 1 else [],
            "all_nba_3rd": [p.nome for p in torneo.all_nba_teams[2]] if getattr(torneo, 'all_nba_teams', None) and len(torneo.all_nba_teams) > 2 else [],
            "all_defensive": [p.nome for p in getattr(torneo, 'all_defensive_team', [])],
            "all_rookie": [p.nome for p in getattr(torneo, 'all_rookie_team', [])],
            **_all_star_premi(torneo)
        },
        "standings": standings_snapshot,
        "team_stats": team_stats_snapshot
    }
    return stagione_corrente_data


def update_league_history(torneo: 'Tournament'):
    """
    Saves a complete summary of the completed season to league_history.json.
    Includes the champion, Finals MVP, complete individual awards, All-Stars,
    complete standings and team statistical averages.
    """
    history_file = get_historical_file_path("league_history.json")
    stagione_corrente_data = build_season_entry(torneo, record_standings=True)

    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                storia_lega = json.load(f)
        except json.JSONDecodeError:
            storia_lega = []
    else:
        storia_lega = []
        
    storia_lega = [x for x in storia_lega if x.get("stagione") != torneo.season_number]
    storia_lega.append(stagione_corrente_data)
    storia_lega.sort(key=lambda x: x.get("stagione", 0))
    
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(storia_lega, f, indent=4)

# --- CLASSES (TradeFinder, Draft, FreeAgency - With minor changes) ---
# Your classes are already well structured. The main changes are:
# 1. Remove `print()` and `input()`.
# 2. Make the methods return logs or data instead of printing them.
def update_player_careers(torneo: 'Tournament'):
    print("=== DEBUG: update_player_careers CHIAMATA! ===", flush=True)
    career_file = get_historical_file_path("player_careers.json")
    
    try:
        if os.path.exists(career_file):
            with open(career_file, 'r', encoding='utf-8') as f:
                all_careers = json.load(f)
        else:
            all_careers = {}
        
        # ### DEBUG LOGIC: Extract the winners' names only once ###
        mvp_name = torneo.regular_season_mvp.nome if torneo.regular_season_mvp else None
        finals_mvp_name = torneo.finals_mvp.nome if torneo.finals_mvp else None
        dpoy_name = torneo.defensive_player_of_the_year.nome if torneo.defensive_player_of_the_year else None
        smoy_name = torneo.sesto_uomo.nome if torneo.sesto_uomo else None
        roy_name = torneo.rookie_of_the_year.nome if getattr(torneo, 'rookie_of_the_year', None) else None
        mip_name = torneo.most_improved_player.nome if getattr(torneo, 'most_improved_player', None) else None
        
        # Create sets of names for an O(1) lookup, much faster and more efficient
        all_nba_1st_names = {p.nome for p in torneo.all_nba_teams[0]} if len(torneo.all_nba_teams) > 0 else set()
        all_nba_2nd_names = {p.nome for p in torneo.all_nba_teams[1]} if len(torneo.all_nba_teams) > 1 else set()
        all_nba_3rd_names = {p.nome for p in torneo.all_nba_teams[2]} if len(torneo.all_nba_teams) > 2 else set()
        all_defensive_names = {p.nome for p in torneo.all_defensive_team}
        all_rookie_names = {p.nome for p in torneo.all_rookie_team}
        
        # All-Star tracking sets
        all_star_starters_names = set()
        all_star_reserves_names = set()
        for conf in ['east', 'west']:
            if torneo.all_star_starters.get(conf):
                all_star_starters_names.update(p.nome for p in torneo.all_star_starters[conf])
            if torneo.all_star_reserves.get(conf):
                all_star_reserves_names.update(p.nome for p in torneo.all_star_reserves[conf])
        
        # Contest winners
        three_pt_winner = torneo.three_point_contest.get('winner', '')
        dunk_winner = torneo.dunk_contest.get('winner', '')
        all_star_mvp = torneo.all_star_mvp or ''

        # Full regular-season and playoff lines from the box scores (still there: they are wiped at the new season;
        # playoff box scores live in the bracket)
        from core.analytics_view import archive_season_lines
        season_lines = archive_season_lines(getattr(torneo, 'box_scores', {}) or {},
                                            getattr(torneo, 'playoff_bracket_data', None),
                                            [p.nome for s in torneo.squadre for p in s.roster])
        full_lines, full_po_lines = season_lines['rs'], season_lines['po']

        player_count = 0
        for squadra in torneo.squadre:
            is_champion_team = (torneo.campione and torneo.campione.nome == squadra.nome)

            for player in squadra.roster:
                player_id = player.nome.replace(" ", "-").lower()
                pg_rs = player.season_stats.partite_giocate or 1
                pg_po = player.playoff_stats.partite_giocate or 1
                
                season_record = {
                    "stagione": torneo.season_number,
                    "squadra": squadra.nome,
                    "nome": player.nome,
                    "ruolo": player.ruolo,
                    "eta": player.eta,
                    "ovr": player.ovr,
                    "potenziale": player.potenziale,
                    "is_champion": is_champion_team,
                    "partite_giocate_rs": player.season_stats.partite_giocate,
                    "partite_giocate_po": player.playoff_stats.partite_giocate,
                    "gp": player.season_stats.partite_giocate,
                    "gp_po": player.playoff_stats.partite_giocate,
                    "stats_rs": {
                        "ppg": round(player.season_stats.punti / pg_rs, 1),
                        "rpg": round(player.season_stats.rimbalzi / pg_rs, 1),
                        "apg": round(player.season_stats.assist / pg_rs, 1),
                        "spg": round(player.season_stats.steals / pg_rs, 1),
                        "bpg": round(player.season_stats.blocks / pg_rs, 1),
                        "fg_pct": player.season_stats.fg_pct,
                        "three_pct": player.season_stats.three_pct,
                        "ft_pct": player.season_stats.ft_pct
                    },
                    "stats_po": {
                        "ppg": round(player.playoff_stats.punti / pg_po, 1),
                        "rpg": round(player.playoff_stats.rimbalzi / pg_po, 1),
                        "apg": round(player.playoff_stats.assist / pg_po, 1),
                        "spg": round(player.playoff_stats.steals / pg_po, 1),
                        "bpg": round(player.playoff_stats.blocks / pg_po, 1),
                        "fg_pct": player.playoff_stats.fg_pct,
                        "three_pct": player.playoff_stats.three_pct,
                        "ft_pct": player.playoff_stats.ft_pct
                    } if player.playoff_stats.partite_giocate > 0 else None,
                    "premi": []
                }
                if player.nome in full_lines:
                    season_record["full_rs"] = full_lines[player.nome]
                if player.nome in full_po_lines:
                    season_record["full_po"] = full_po_lines[player.nome]

                # ### ROBUST AWARD ASSIGNMENT LOGIC ###
                p_name = player.nome.strip()
                if mvp_name and p_name == mvp_name.strip(): season_record["premi"].append("MVP")
                if finals_mvp_name and p_name == finals_mvp_name.strip(): season_record["premi"].append("Finals MVP")
                if dpoy_name and p_name == dpoy_name.strip(): season_record["premi"].append("DPOY")
                if smoy_name and p_name == smoy_name.strip(): season_record["premi"].append("6th Man")

                if p_name in all_nba_1st_names: season_record["premi"].append("All-NBA 1st")
                elif p_name in all_nba_2nd_names: season_record["premi"].append("All-NBA 2nd")
                elif p_name in all_nba_3rd_names: season_record["premi"].append("All-NBA 3rd")
                    
                if p_name in all_defensive_names: season_record["premi"].append("All-Defensive")
                if p_name in all_rookie_names: season_record["premi"].append("All-Rookie")
                if roy_name and p_name == roy_name.strip(): season_record["premi"].append("ROY")
                if mip_name and p_name == mip_name.strip(): season_record["premi"].append("MIP")
                
                # All-Star Weekend awards
                if p_name in all_star_starters_names: season_record["premi"].append("All-Star Starter")
                elif p_name in all_star_reserves_names: season_record["premi"].append("All-Star")
                if p_name == three_pt_winner: season_record["premi"].append("3PT Contest Winner")
                if p_name == dunk_winner: season_record["premi"].append("Dunk Contest Winner")
                if p_name == all_star_mvp: season_record["premi"].append("All-Star MVP")

                if player_id not in all_careers:
                    all_careers[player_id] = []
                
                # Deduplicate existing entry for the current season if re-running
                all_careers[player_id] = [s for s in all_careers[player_id] if s.get("stagione") != torneo.season_number]
                all_careers[player_id].append(season_record)
                player_count += 1

                # Also update the in-memory Player object for the UI and the cards
                all_awards = []
                career_rings = 0
                for s in all_careers[player_id]:
                    if s.get("is_champion"):
                        career_rings += 1
                    for aw in s.get("premi", []):
                        all_awards.append(aw)
                player.premi = all_awards
                player.anelli_vinti = max(getattr(player, 'anelli_vinti', 0), career_rings)

        with open(career_file, 'w', encoding='utf-8') as f:
            json.dump(all_careers, f, indent=2)
        print(f"=== DEBUG: update_player_careers COMPLETED! {player_count} players saved in {career_file} ===", flush=True)
    except Exception as e:
        print(f"!!! ERROR in update_player_careers: {e} !!!", flush=True)
        import traceback
        traceback.print_exc()

# TradeFinder, Draft, and FreeAgency classes have been extracted to:
# - trades/trade_finder.py
# - offseason/draft.py
# - offseason/free_agency.py

        
class Tournament:
    def __init__(self, squadre: List[Squadra], league_settings: Optional[Dict[str, Any]] = None):
        self.squadre = squadre
        self.season_number = 1
        self.squadre_est = [s for s in squadre if s.conference == 'East']
        self.squadre_ovest = [s for s in squadre if s.conference == 'West']
        self.squadra_giocatore: Optional[Squadra] = None 
        self.giocatori_ritirati: List[Giocatore] = []
        self.free_agents_pool: List[Giocatore] = []

        # League Settings & Sandbox Options
        self.league_settings = league_settings or {}
        self.league_meta: Dict[str, Any] = {}  # name/era/start_year of the league this save was built from
        self.franchise_registry = None  # FranchiseRegistry, set by the league loader or restored from the save
        self.enable_play_in: bool = self.league_settings.get('enable_play_in', True)
        self.cba_mode: str = self.league_settings.get('cba_mode', 'realistic')  # 'realistic', 'soft_cap', 'no_cap'
        self.injury_frequency: str = self.league_settings.get('injury_frequency', 'realistic')  # 'realistic', 'low', 'off'
        self.trade_difficulty: str = self.league_settings.get('trade_difficulty', 'realistic')  # 'easy', 'realistic', 'hardcore'
        self.scouting_fog_of_war: bool = self.league_settings.get('scouting_fog_of_war', True)
        self.gm_firing_enabled: bool = self.league_settings.get('gm_firing_enabled', True)
        self.user_role: str = self.league_settings.get('user_role', 'gm_coach')  # 'gm_coach', 'only_gm', 'only_coach', 'spectator'
        
        self.regular_season_mvp: Optional[Giocatore] = None
        self.defensive_player_of_the_year: Optional[Giocatore] = None
        self.sesto_uomo: Optional[Giocatore] = None
        self.all_nba_teams: List[List[Giocatore]] = []
        self.all_defensive_team: List[Giocatore] = []
        self.all_rookie_team: List[Giocatore] = []
        self.rookie_of_the_year: Optional[Giocatore] = None
        self.most_improved_player: Optional[Giocatore] = None
        self.finals_mvp: Optional[Giocatore] = None
        self.campione: Optional[Squadra] = None
        
        self.podcast_logger = PodcastLogger(self.season_number)
        
        self.playoff_bracket_data: Optional[Dict] = None
        self.offseason_log_data: Optional[Dict] = None
        self.playoff_state = "NOT_STARTED"
        self.playoff_teams = {'east': [], 'west': []}
        self.next_round_teams = {'east': [], 'west': []}
        self.active_playoff_series: List[Dict] = []
        
        # Play-In Tournament support
        self.play_in_teams = {'east': [], 'west': []}  # Seeds 7-10
        self.direct_qualifiers = {'east': [], 'west': []}  # Seeds 1-6
        self.play_in_results = {'east': {}, 'west': {}}
        self.play_in_game_index = 0  # 0-5: tracks which game to simulate next

        # State variables for the phased offseason
        self.nuovi_free_agents: List[Giocatore] = []
        self.squadre_precedenti_fa: Dict[str, Squadra] = {}
        self.unemployed_coaches: List[Coach] = []
        self.offseason_log_data: Dict[str, List] = {}
        self.pending_trade_block_offers: List[Dict] = []
        self.pick_ownership: Dict[int, Dict[str, str]] = {1:{}, 2:{}, 3:{}, 4:{}, 5:{}}
        self.pick_protections: Dict[int, Dict[str, str]] = {1:{}, 2:{}, 3:{}, 4:{}, 5:{}}
        self._initialize_pick_ownership()
        
        # Scouting and draft class state
        self.draft_class: List['Giocatore'] = []
        self.scout_staff: List[dict] = []
        self.scouting_workouts_left: int = 5

        # ### NEW DYNAMIC ECONOMIC ATTRIBUTES ###
        is_2002 = current_league_era() == "2002"

        if 'starting_year' in self.league_settings:
            self.starting_year = int(self.league_settings['starting_year'])
        else:
            self.starting_year = 2002 if is_2002 else 2025
        self.anno_corrente = self.starting_year
        self._era_pace_drift = 0.0
        self._era_3pt_drift = 0.0
        self.update_dynamic_economy()

        from core import models
        models.ACTIVE_TOURNAMENT = self

        # ### KEY CHANGE: Assign the tournament reference to every team ###
        for s in self.squadre:
            s.torneo = self

        # ### RIVALRY & STORYLINE SYSTEM ###
        self.rivalry_tracker = RivalryTracker()
        self.storyline_engine = StorylineEngine()
        self._initialize_division_rivalries()
        
        # ### ALL-STAR WEEKEND ###
        self.all_star_hosts = []         # host cities, newest last
        self.last_season_rookies = []    # names of last season's rookies (sophomores this season)
        self.reset_all_star_weekend()

        self.calendario = []
        self.genera_calendario()

    def update_dynamic_economy(self):
        self.anno_corrente = self.starting_year + (self.season_number - 1)
        
        # Historical NBA salary caps
        YEARLY_SALARY_CAPS = {
            2002: 40.27, 2003: 43.84, 2004: 43.87, 2005: 49.50,
            2006: 53.13, 2007: 55.63, 2008: 58.68, 2009: 57.70,
            2010: 58.04, 2011: 58.04, 2012: 58.04, 2013: 58.68,
            2014: 63.06, 2015: 70.00, 2016: 94.14, 2017: 99.09,
            2018: 101.87, 2019: 109.14, 2020: 109.14, 2021: 112.41,
            2022: 123.65, 2023: 136.02, 2024: 140.58, 2025: 155.00
        }
        
        cap = YEARLY_SALARY_CAPS.get(self.anno_corrente, 155.0)
        self.salary_cap = cap
        
        # Scale tax and MLE proportionally
        scale_factor = cap / 155.0
        self.salary_floor = round(cap * CONFIG.ECONOMY.SALARY_FLOOR_RATIO, 1)
        self.luxury_tax_threshold = round(185.0 * scale_factor, 1)
        
        # Dynamic Era Rules:
        # 1. First & Second Aprons were only introduced in the modern CBA (2023+)
        if self.anno_corrente >= 2023:
            self.first_apron = round(CONFIG.ECONOMY.FIRST_APRON * scale_factor, 1)
            self.second_apron = round(CONFIG.ECONOMY.SECOND_APRON * scale_factor, 1)
        else:
            # Historical / Pre-2023 eras: No First or Second Apron restrictions!
            self.first_apron = 9999.0
            self.second_apron = 9999.0
            
        self.first_apron_threshold = self.first_apron
        self.second_apron_threshold = self.second_apron
        self.mle_value = round(12.5 * scale_factor, 1)
        self.mle_amount = self.mle_value
        self.min_salary = round(3.5 * scale_factor, 1)
        self.minimum_salary = self.min_salary
        self.max_salary_theoretical = round(CONFIG.ECONOMY.MAX_SALARY_THEORETICAL * scale_factor, 1)

        # 2. Play-In: on or off for this season, from the league setting
        self.resolve_play_in()

        # Sandbox CBA adjustments
        cba = getattr(self, 'cba_mode', 'realistic')
        if cba == 'no_cap':
            self.salary_cap = 9999.0
            self.salary_floor = 0.0
            self.luxury_tax_threshold = 9999.0
            self.first_apron = 9999.0
            self.first_apron_threshold = 9999.0
            self.second_apron = 9999.0
            self.second_apron_threshold = 9999.0
            self.mle_value = 999.0
            self.mle_amount = 999.0
            self.min_salary = 1.0
            self.minimum_salary = 1.0
        elif cba == 'soft_cap':
            # Soft cap: keep Salary Cap and Luxury Tax, but eliminate First/Second Aprons restrictions
            self.first_apron = 9999.0
            self.first_apron_threshold = 9999.0
            self.second_apron = 9999.0
            self.second_apron_threshold = 9999.0

        if 'salary_cap' in self.league_settings and self.league_settings['salary_cap'] and cba != 'no_cap':
            try:
                custom_cap = float(self.league_settings['salary_cap'])
                if custom_cap > 0:
                    self.salary_cap = custom_cap
            except (ValueError, TypeError):
                pass

    def resolve_play_in(self) -> None:
        """Sets enable_play_in for the current season from the league settings.

        'play_in_start_year' (int, or None = never) wins; otherwise a legacy 'enable_play_in' bool forces it on or off
        (saves made before the start-year setting); with neither, the historical default year applies.
        """
        settings = self.league_settings or {}
        year = getattr(self, 'anno_corrente', CONFIG.ERA.START_YEAR)
        if 'play_in_start_year' in settings:
            start = settings['play_in_start_year']
            self.enable_play_in = start is not None and year >= int(start)
        elif 'enable_play_in' in settings:
            self.enable_play_in = bool(settings['enable_play_in'])
        else:
            self.enable_play_in = year >= CONFIG.ERA.PLAY_IN_DEFAULT_START_YEAR

    @staticmethod
    def _era_logistic(year: float, floor: float, span: float, inflection: float, rate: float) -> float:
        import math
        return floor + span / (1.0 + math.exp(-rate * (year - inflection)))

    def is_modern_start(self) -> bool:
        """True for a league that started at CONFIG.ERA.END_YEAR or later (modern database): its rosters already
        shoot like today's league, so the era curves use the CONFIG.ERA.MODERN_START_* values."""
        return getattr(self, 'starting_year', CONFIG.ERA.START_YEAR) >= CONFIG.ERA.END_YEAR

    def get_era_3pt_multiplier(self) -> float:
        """Three-point volume multiplier for the current year: logistic curve (CONFIG.ERA.THREE_*) plus the
        post-2025 random drift. A 2002 league: ~0.85 in 2002, ~1.06 in 2010, ~1.73 in 2020, ~1.93 in 2025.
        A modern-start league keeps the gentler curve (~1.38 in 2025)."""
        era = CONFIG.ERA
        span, inflection = era.THREE_SPAN, era.THREE_INFLECTION
        if self.is_modern_start():
            span, inflection = era.MODERN_START_THREE_SPAN, era.MODERN_START_THREE_INFLECTION
        base = self._era_logistic(getattr(self, 'anno_corrente', era.END_YEAR), era.THREE_FLOOR, span,
                                  inflection, era.THREE_RATE)
        lo, hi = era.THREE_CLAMP
        return min(hi, max(lo, round(base + getattr(self, '_era_3pt_drift', 0.0), 3)))

    def get_era_pace_factor(self) -> float:
        """Pace (possessions) factor for the current year: logistic curve (CONFIG.ERA.PACE_*) plus the post-2025
        random drift. ~0.91 in 2002 (~91 possessions), ~1.00 in 2020, ~1.02 in 2025, ceiling ~1.035."""
        era = CONFIG.ERA
        base = self._era_logistic(getattr(self, 'anno_corrente', era.END_YEAR), era.PACE_FLOOR, era.PACE_SPAN,
                                  era.PACE_INFLECTION, era.PACE_RATE)
        lo, hi = era.PACE_CLAMP
        return min(hi, max(lo, round(base + getattr(self, '_era_pace_drift', 0.0), 3)))

    def genera_calendario(self):
        """
        Generates the procedural and authentic NBA calendar over 176 days (exactly 1230 games, 82 per franchise)
        using the geographic solver with distance clustering, strict respect of the B2B <= 16 constraint,
        total absence of 3-in-3s, holiday showcases and a Grand Finale with 15 simultaneous games (Day 176).
        """
        # A new calendar means a new season: trades/logs are now "in-season" (see TradeFinder._log_trade_to_file)
        self.fase_torneo = "SEASON"
        from core.calendar_generator import NBACalendarGenerator
        generator = NBACalendarGenerator(
            teams=self.squadre,
            starting_year=getattr(self, 'anno_corrente', 2025)
        )
        self.calendario = generator.generate_calendar()
        self._current_gameday = 0
        self.current_day = 0
        self._last_played_day = {}
        self._first_half_complete = False
        self._trade_deadline_completed = False
        self.reset_all_star_weekend()
        self.team_map = {s.nome: s for s in self.squadre}
        
        # Link the Team object references to every scheduled game
        for day in self.calendario:
            for g in day.games:
                g.home_team_obj = self.team_map.get(g.home_team)
                g.away_team_obj = self.team_map.get(g.away_team)

    def _initialize_division_rivalries(self):
        """
        Set up base division rivalries at simulation start.
        Teams in the same division get a base rivalry intensity.
        """
        # Divisions of the active league (core/league/registry.py), limited to the teams in this simulation
        team_names = {s.nome for s in self.squadre}
        filtered_divisions = {}
        for div_name, teams in get_active_registry().divisions().items():
            existing_teams = [t for t in teams if t in team_names]
            if len(existing_teams) >= 2:
                filtered_divisions[div_name] = existing_teams

        # Initialize rivalries through the tracker
        self.rivalry_tracker.initialize_division_rivalries(filtered_divisions)
        
        # Also set up the league's historic rivalries with higher base intensity
        historic_rivalries = get_active_registry().rivalries()

        for team1, team2, intensity in historic_rivalries:
            if team1 in team_names and team2 in team_names:
                rivalry = self.rivalry_tracker.get_or_create_rivalry(team1, team2, rivalry_type="historic")
                rivalry.intensity = max(rivalry.intensity, intensity)
        
        main_log.info(f"Initialized {len(self.rivalry_tracker.rivalries)} rivalries")

    def _gestisci_crescita_economica(self):
        """
        ### REWORKED (v22.0 - Stabilized NBA Revenue & Cap Smoothing Engine) ###
        Adjusts the Salary Cap at the end of the season based on organic economic growth (BRI / TV Contracts)
        and the official NBA Cap Smoothing rules (max +4.0% / -2.5% per year), decoupling growth
        from the median payroll to permanently eliminate the infinite loop of exorbitant contracts ($80M+).
        Includes stabilization toward a realistic plateau ($165M-$180M) and self-healing
        for historical saves that had reached the anomalous ceiling of $220M-$250M.
        """
        main_log.info("\n--- LEAGUE ECONOMIC UPDATE ---")
        self.anno_corrente = self.starting_year + (self.season_number - 1)
        
        # In historical eras, force the salary cap to evolve along the real historic path
        if self.starting_year + (self.season_number - 1) < 2025:
            old_cap = self.salary_cap
            self.update_dynamic_economy()
            main_log.info(f"Historical Salary Cap Evolution: ${old_cap}M -> ${self.salary_cap}M (Year {self.anno_corrente})")
            return
            
        cfg_base = CONFIG.ECONOMY
        CAP_INIZIALE = cfg_base.SALARY_CAP  # 155.0
        CAP_MINIMO = 145.0                  # Minimum economic safety floor
        CAP_MASSIMO = 185.0                 # Realistic ceiling to keep supermax contracts within $60M-$65M/year
        
        current_cap = getattr(self, 'salary_cap', CAP_INIZIALE)
        
        # 1. Detect and handle saves with a cap inflated by old versions (>185M)
        if current_cap > CAP_MASSIMO:
            # Gradual multi-season cooling (-3.5M to -6.5M per year until back to target)
            delta = -random.uniform(3.5, 6.5)
            main_log.info(f"Legacy Cap Normalization: ${current_cap:.1f}M > ${CAP_MASSIMO:.1f}M -> Cooling (Delta: {delta:.1f}M)")
            nuovo_salary_cap = round(current_cap + delta, 1)
        else:
            # 2. Organic economic growth model of the league (NBA BRI / TV Contracts / Inflation)
            # Natural economic growth fluctuates between +1.0% and +3.2% per year
            # With a rare chance (8%) of a slight economic recession (-1.2% to 0.0%)
            roll_recessione = random.random()
            if roll_recessione < 0.08:
                growth_rate = random.uniform(-0.012, 0.0)
            else:
                growth_rate = random.uniform(0.012, 0.030)
                
            # If we are approaching the equilibrium target ($170M - $185M), growth naturally slows
            if current_cap >= 170.0:
                distanza_max = max(0.0, (CAP_MASSIMO - current_cap) / (CAP_MASSIMO - 170.0))
                growth_rate *= (0.20 + 0.80 * distanza_max)
                
            delta = current_cap * growth_rate
            
            # NBA Cap Smoothing: strict limit on annual change (+5.5M max, -3.5M min)
            delta = max(-3.5, min(5.5, delta))
            
            # Market noise (-0.3M to +0.3M)
            rumore = random.uniform(-0.3, 0.3)
            nuovo_salary_cap = current_cap + delta + rumore
            nuovo_salary_cap = max(CAP_MINIMO, min(CAP_MASSIMO, nuovo_salary_cap))
            nuovo_salary_cap = round(nuovo_salary_cap, 1)
            
            main_log.info(f"Organic Economic Growth: ${current_cap:.1f}M -> ${nuovo_salary_cap:.1f}M (Growth: {growth_rate*100:+.2f}%, Delta: {delta:+.1f}M)")

        # 3. Recompute all the thresholds (Tax, Aprons, MLE, Min) in exact proportion to the new Cap
        nuova_luxury_tax = round(nuovo_salary_cap * (cfg_base.LUXURY_TAX_THRESHOLD / CAP_INIZIALE), 1)
        nuovo_first_apron = round(nuova_luxury_tax * 1.054, 1) # Always above the Luxury Tax
        nuovo_second_apron = round(nuova_luxury_tax * 1.108, 1) # Always above the First Apron
        nuova_mle = round(nuovo_salary_cap * (cfg_base.MLE_VALUE / CAP_INIZIALE), 1)
        nuovo_min = round(nuovo_salary_cap * (3.5 / CAP_INIZIALE), 1)
        nuovo_floor = round(nuovo_salary_cap * cfg_base.SALARY_FLOOR_RATIO, 1)

        main_log.info(f"Salary Cap Update: ${self.salary_cap}M -> ${nuovo_salary_cap}M | Floor: ${nuovo_floor}M | Tax: ${nuova_luxury_tax}M | Apron1: ${nuovo_first_apron}M | Apron2: ${nuovo_second_apron}M")

        # 4. Apply the new values
        self.salary_cap = nuovo_salary_cap
        self.salary_floor = nuovo_floor
        self.luxury_tax_threshold = nuova_luxury_tax
        self.first_apron = nuovo_first_apron
        self.first_apron_threshold = nuovo_first_apron
        self.second_apron = nuovo_second_apron
        self.second_apron_threshold = nuovo_second_apron
        self.mle_value = nuova_mle
        self.mle_amount = nuova_mle
        self.min_salary = nuovo_min
        self.minimum_salary = nuovo_min

        # Organic evolution of the game trends (pace and 3pt volume) for the modern/future years with mean-reversion
        era = CONFIG.ERA
        if self.anno_corrente >= era.DRIFT_FROM_YEAR:
            cur_p_drift = getattr(self, '_era_pace_drift', 0.0)
            cur_3_drift = getattr(self, '_era_3pt_drift', 0.0)
            drift_p = random.uniform(-era.PACE_DRIFT_STEP, era.PACE_DRIFT_STEP) - (cur_p_drift * era.DRIFT_REVERSION)
            drift_3 = random.uniform(-era.THREE_DRIFT_STEP, era.THREE_DRIFT_STEP) - (cur_3_drift * era.DRIFT_REVERSION)
            self._era_pace_drift = max(era.PACE_DRIFT_CLAMP[0], min(era.PACE_DRIFT_CLAMP[1], cur_p_drift + drift_p))
            self._era_3pt_drift = max(era.THREE_DRIFT_CLAMP[0], min(era.THREE_DRIFT_CLAMP[1], cur_3_drift + drift_3))
            main_log.info(f"Era Tactical Evolution: Pace Factor {self.get_era_pace_factor():.3f} (drift {self._era_pace_drift:+.3f}), 3PT Mult {self.get_era_3pt_multiplier():.3f} (drift {self._era_3pt_drift:+.3f})")

    def _determina_stato_squadra(self, squadra: Squadra) -> str:
        """
        ### REWORKED (v20.6) - Dynamic Thresholds ###
        Determines a team's strategic objective with clearer and more robust rules,
        essential for the new trade and free agency logic. Thresholds relative to the league average.
        """
        if not squadra.roster: return "Rebuilding"
        
        # 1. Protection of Reigning Champions
        if getattr(self, 'campione', None) and self.campione.nome == squadra.nome:
            return "Defending Champion"

        # Compute the talent (top 8 players) and the average age of the core (top 5)
        top_8 = sorted(squadra.roster, key=lambda p: p.ovr, reverse=True)[:8]
        core_5 = top_8[:5]
        
        media_ovr_top_8 = sum(p.ovr for p in top_8) / len(top_8) if top_8 else 0
        media_eta_core_5 = sum(p.eta for p in core_5) / len(core_5) if core_5 else 30

        # Compute the league's top-8 average to make the thresholds dynamic
        total_top8_sum = 0
        teams_count = 0
        for s in self.squadre:
            if s.roster:
                s_top8 = sorted(s.roster, key=lambda p: p.ovr, reverse=True)[:8]
                total_top8_sum += sum(p.ovr for p in s_top8) / len(s_top8)
                teams_count += 1
        avg_top8 = (total_top8_sum / teams_count) if teams_count > 0 else 80.0

        # 2. Contenders: Elite roster (At least 2.5 OVR above league average)
        if media_ovr_top_8 >= avg_top8 + 2.5:
            return "Contender"
        
        # 3. Young rising teams (Age core <= 25.5 and OVR not too far from average)
        if media_eta_core_5 <= 25.5 and media_ovr_top_8 >= avg_top8 - 3.0:
            return "Rising Star"

        # 4. Solide squadre da Playoff (At least within 0.5 of league average)
        if media_ovr_top_8 >= avg_top8 - 0.5:
            if media_eta_core_5 >= 30.5:
                return "Aging Core"
            return "Playoff Team"

        # 5. Teams clearly rebuilding (Low talent - more than 2.0 below league average)
        if media_ovr_top_8 < avg_top8 - 2.0:
            return "Rebuilding"

        # 6. All the others ("Stuck in the middle")
        return "Mediocre"
    def _calcola_vittorie_attese(self):
        """Computes the expected wins for each team based on talent."""
        league_avg = league_avg_ovr(self)
        for squadra in self.squadre:
            squadra.vittorie_attese = expected_wins(squadra, league_avg)

    def _coach_candidate_name(self) -> str:
        """A coach name from the active league's staff.coach_names (else CONFIG): a full name nobody coaching
        or on the market holds; once all are taken, a first name and a last name of the list mixed."""
        from core.league.registry import staff_names
        pool = staff_names("coach_names", CONFIG.COACHINGSTYLES.COACH_NAMES)
        coaches = [getattr(s, "coach", None) for s in getattr(self, "squadre", [])]
        coaches += list(getattr(self, "unemployed_coaches", None) or [])
        in_use = {str(getattr(c, "nome", "")).replace("Interim ", "", 1) for c in coaches if c is not None}
        free = [n for n in pool if n not in in_use]
        if free:
            return random.choice(free)
        firsts = [n.split(" ", 1)[0] for n in pool]
        lasts = [n.split(" ", 1)[-1] for n in pool]
        name = f"{random.choice(firsts)} {random.choice(lasts)}"
        for _ in range(50):
            if name not in in_use:
                break
            name = f"{random.choice(firsts)} {random.choice(lasts)}"
        return name

    def _generate_coach_candidate(self, archetype=None):
        """Generates a realistic coach candidate with credible attributes, specialization and résumé."""
        name = self._coach_candidate_name()
        
        archetypes = [
            {"spec": "Offensive Mastermind", "off_boost": 6, "def_boost": -2, "dev_boost": 2, "tac_boost": 4, "styles": ["Pace & Space", "Run and Gun", "System Basketball"]},
            {"spec": "Defensive Architect", "off_boost": -2, "def_boost": 7, "dev_boost": 2, "tac_boost": 3, "styles": ["Grit & Grind", "Defensive Minded", "Man-to-Man Lockdown"]},
            {"spec": "Player Developer", "off_boost": 1, "def_boost": 1, "dev_boost": 8, "tac_boost": 0, "styles": ["Balanced Offense", "Pace & Space", "Small Ball Strategy"]},
            {"spec": "Tactical Innovator", "off_boost": 3, "def_boost": 3, "dev_boost": 2, "tac_boost": 7, "styles": ["Point Guard Maestro", "System Basketball", "Triangle Offense"]},
            {"spec": "Veteran Leader", "off_boost": 4, "def_boost": 4, "dev_boost": 3, "tac_boost": 5, "styles": ["Balanced Offense", "Triangle Offense", "Twin Towers"]}
        ]
        
        arch = archetype if archetype else random.choice(archetypes)
        selected_style = random.choice(arch.get("styles", list(CONFIG.COACHINGSTYLES.STYLES.keys())))
            
        base_ovr = random.randint(70, 84)
        off_r = max(55, min(95, base_ovr + arch.get("off_boost", 0) + random.randint(-2, 3)))
        def_r = max(55, min(95, base_ovr + arch.get("def_boost", 0) + random.randint(-2, 3)))
        dev_r = max(55, min(95, base_ovr + arch.get("dev_boost", 0) + random.randint(-2, 3)))
        tac_r = max(55, min(95, base_ovr + arch.get("tac_boost", 0) + random.randint(-2, 3)))
        disc_r = random.randint(70, 90)
        
        eta = random.randint(38, 62)
        contract_years = random.choice([3, 4, 4, 5])
        salary = round(max(2.5, min(10.5, (base_ovr - 65) * 0.45 + random.uniform(1.0, 2.5))), 1)
        
        badges = {
            "Rookie Developer": 2 if arch["spec"] == "Player Developer" else (1 if random.random() < 0.3 else 0),
            "Defense Guru": 2 if arch["spec"] == "Defensive Architect" else (1 if random.random() < 0.3 else 0),
            "Tactician": 2 if arch["spec"] == "Tactical Innovator" else (1 if random.random() < 0.3 else 0),
            "Fitness Specialist": 1 if random.random() < 0.25 else 0,
            "Motivator": 2 if arch["spec"] == "Veteran Leader" else (1 if random.random() < 0.3 else 0),
            "Clutch Master": 1 if random.random() < 0.25 else 0
        }
        
        return Coach(
            nome=name,
            stile_gioco=selected_style,
            ovr_offensivo=off_r,
            ovr_difensivo=def_r,
            player_development=dev_r,
            tactical_acumen=tac_r,
            discipline_culture=disc_r,
            eta=eta,
            potenziale=min(99, max(off_r, def_r) + random.randint(5, 12)),
            contratto_anni_rimanenti=contract_years,
            contratto_totale_anni=contract_years,
            salario=salary,
            job_security=75.0,
            years_with_current_team=0,
            badges=badges,
            specialization=arch["spec"],
            historical_wins=random.randint(50, 450) if eta > 48 else random.randint(0, 100),
            historical_losses=random.randint(40, 380) if eta > 48 else random.randint(0, 80),
            playoff_appearances=random.randint(1, 8) if eta > 48 else random.randint(0, 2),
            championships=1 if (eta > 52 and random.random() < 0.2) else 0
        )

    def _gestisci_fase_licenziamenti(self):
        """Cycles through all the teams and decides whom to fire with realistic criteria and a grace period."""
        main_log.info("\n--- COACH FIRING PHASE ('Black Monday') ---")
        fo = ensure_front_office(self)
        close_season(self, fo)
        self._calcola_vittorie_attese()
        cfg = CONFIG.FRONT_OFFICE
        patience_table = CONFIG.ECONOMY.OWNER_BOARD_PATIENCE
        squadre_che_hanno_licenziato = []

        is_user_spectator = getattr(self, 'is_spectator', False)
        user_team_name = self.squadra_giocatore.nome if (self.squadra_giocatore and not is_user_spectator) else None

        for squadra in self.squadre:
            if not squadra.coach: continue
            coach = squadra.coach
            
            # 1. Reigning champions are totally immune
            if self.campione and squadra.nome == self.campione.nome:
                coach.job_security = 99.0
                coach.championships += 1
                continue

            # Do not automatically fire the coach of the user's team (it is the GM's/user's decision)
            if user_team_name and squadra.nome == user_team_name:
                continue

            jss = cfg.COACH_JSS_BASE

            # The season's expectation was fixed at its start and sits in the season record
            record = fo.records.get(squadra.nome, [])
            season_row = record[-1] if record else None
            expected = season_row["expected"] if season_row else squadra.vittorie_attese

            # Factor 1: Performance vs Expectations
            performance_delta = squadra.vittorie - expected
            jss += performance_delta * cfg.COACH_JSS_PER_WIN

            # Factor 2: Grace Period for a new contract (first 1-2 years of a multi-year deal)
            if coach.years_with_current_team <= 1 and coach.contratto_totale_anni >= 3:
                jss += cfg.COACH_GRACE_NEW_DEAL # New coaches have time to install their system!
            elif coach.years_with_current_team == 2 and coach.contratto_totale_anni >= 4:
                jss += cfg.COACH_GRACE_SECOND_YEAR

            # Factor 3: Playoff Success
            in_playoffs = (squadra in self.playoff_teams.get('east', []) or squadra in self.playoff_teams.get('west', []))
            if in_playoffs:
                jss += cfg.COACH_PLAYOFF_BONUS
                coach.playoff_appearances += 1
            else:
                jss -= cfg.COACH_NO_PLAYOFF_PENALTY

            # Factor 4: Patience for a rebuild that is on schedule (from the saved plan). Only for a season that
            # started as a rebuild: a contender that collapsed into one at the deadline is judged as a contender.
            plan_start = (season_row.get("plan_start") if season_row else None) or team_plan_state(self, squadra)
            if plan_start == "REBUILDER" and rebuild_on_schedule(fo.plans.get(squadra.nome)):
                jss += cfg.COACH_REBUILD_PATIENCE

            # Factor 5: Owner's Patience (a demanding owner gives less rope, a rebuilding one more)
            if performance_delta < cfg.COACH_OWNER_DELTA:
                owner = normalize_owner_personality(squadra.personalita_proprietario)
                neutral = cfg.COACH_OWNER_NEUTRAL_PATIENCE
                jss += (patience_table.get(owner, neutral) - neutral) * cfg.COACH_OWNER_PATIENCE_STEP

            coach.job_security = round(max(5.0, min(99.0, jss)), 1)

            # Firing criterion: low JSS AND enough seasons with the team (barring an epochal disaster for a Contender)
            is_catastrophic = (squadra.vittorie < cfg.COACH_CATASTROPHE_WINS and expected >= cfg.COACH_CATASTROPHE_EXPECTED)
            should_fire = (coach.job_security < cfg.COACH_FIRE_JSS
                           and coach.years_with_current_team >= cfg.COACH_FIRE_MIN_SEASONS) or is_catastrophic

            if should_fire:
                if season_row:
                    season_row["coach_fired"] = True
                squadre_che_hanno_licenziato.append(squadra)
                log_msg = f"FIRING: The {squadra.nome} fired coach {coach.nome} (Record: {squadra.vittorie}-{squadra.sconfitte}, JSS: {coach.job_security:.1f})"
                if 'ritiri_sviluppo' in self.offseason_log_data:
                    self.offseason_log_data['ritiri_sviluppo'].append(log_msg)
                main_log.info(log_msg)
                
                try:   # news never break the offseason
                    from core.news_generator import generate_front_office_news
                    generate_front_office_news("fired", squadra.nome, "coach", coach.nome,
                                               f"The {squadra.nome} part ways with {coach.nome} after a "
                                               f"{squadra.vittorie}-{squadra.sconfitte} season.", season=self.season_number)
                except Exception as exc:
                    main_log.warning("coach firing news failed: %s", exc)

                if not hasattr(self, 'unemployed_coaches'):
                    self.unemployed_coaches = []
                self.unemployed_coaches.append(coach)
                squadra.coach = None

        # The owners' verdict on their GMs, retirements and the GM hiring round (core/front_office/offseason.py)
        front_office_offseason(self)

    def _gestisci_fase_assunzioni(self):
        """Teams without a coach hire a new one by weighing roster fit and résumé."""
        squadre_senza_coach = [s for s in self.squadre if not s.coach]
        if not squadre_senza_coach: return
        
        main_log.info("\n--- COACH HIRING PHASE ---")

        if not hasattr(self, 'unemployed_coaches'):
            self.unemployed_coaches = []

        # Ensure a rich pool of at least 8 credible candidates
        candidate_pool = self.unemployed_coaches.copy()
        needed_new = max(5, 8 - len(candidate_pool))
        for _ in range(needed_new):
            new_c = self._generate_coach_candidate()
            candidate_pool.append(new_c)
            self.unemployed_coaches.append(new_c)

        is_user_spectator = getattr(self, 'is_spectator', False)
        user_team_name = self.squadra_giocatore.nome if (self.squadra_giocatore and not is_user_spectator) else None

        for squadra in squadre_senza_coach:
            if user_team_name and squadra.nome == user_team_name:
                continue # The user will pick his own coach in the GM office

            miglior_candidato = None
            max_hiring_score = -1

            for coach in candidate_pool:
                fit_info = coach.calcola_roster_fit(squadra)
                fit_mult = fit_info.get("fit_score", 70) / 70.0
                score = (coach.ovr_totale * 0.55 + coach.tactical_acumen * 0.25 + coach.player_development * 0.20) * fit_mult

                owner_type = squadra.personalita_proprietario
                if owner_type == "Spendaccione" and coach.championships > 0:
                    score *= 1.3
                if owner_type == "Risparmiatore" and coach.salario <= 4.0:
                    score *= 1.25

                if score > max_hiring_score:
                    max_hiring_score = score
                    miglior_candidato = coach

            if miglior_candidato:
                miglior_candidato.contratto_totale_anni = random.choice([3, 4, 4, 5])
                miglior_candidato.contratto_anni_rimanenti = miglior_candidato.contratto_totale_anni
                miglior_candidato.years_with_current_team = 1
                miglior_candidato.job_security = 75.0
                
                squadra.coach = miglior_candidato
                candidate_pool.remove(miglior_candidato)
                if miglior_candidato in self.unemployed_coaches:
                    self.unemployed_coaches.remove(miglior_candidato)

                log_msg = f"HIRING: The {squadra.nome} hired coach {miglior_candidato.nome} (Style: {miglior_candidato.stile_gioco}, Deal {miglior_candidato.contratto_totale_anni} years at ${miglior_candidato.salario:.1f}M/year)."
                try:   # news never break the offseason
                    from core.news_generator import generate_front_office_news
                    generate_front_office_news("hired", squadra.nome, "coach", miglior_candidato.nome,
                                               f"{miglior_candidato.nome} signs for {miglior_candidato.contratto_totale_anni} "
                                               f"years and brings a {miglior_candidato.stile_gioco} system.",
                                               season=self.season_number)
                except Exception as exc:
                    main_log.warning("coach hiring news failed: %s", exc)
                if 'ritiri_sviluppo' in self.offseason_log_data:
                    self.offseason_log_data['ritiri_sviluppo'].append(log_msg)
                main_log.info(log_msg)

    def _gestisci_licenziamenti_midseason(self):
        """
        🚨 Mid-Season Coaching Changes (Only in case of an exceptional collapse for contenders) 🚨
        """
        main_log.info("\n--- MID-SEASON COACH EVALUATION ---")
        cfg = CONFIG.FRONT_OFFICE
        fo = ensure_front_office(self)
        year = current_year(self)
        fired_count = 0
        
        is_user_spectator = getattr(self, 'is_spectator', False)
        user_team_name = self.squadra_giocatore.nome if (self.squadra_giocatore and not is_user_spectator) else None

        for squadra in self.squadre:
            if not squadra.coach: continue
            if user_team_name and squadra.nome == user_team_name:
                continue
            
            # Only Contenders with a disastrous record and enough seasons in charge (judged by the season-start plan,
            # since checkpoint_deadline has just flipped a collapsing contender to REBUILDER).
            mark = fo.season_marks.get(squadra.nome)
            plan_start = mark.get("plan") if (mark and mark.get("year") == year) else None
            if (plan_start or team_plan_state(self, squadra)) != "CONTENDER":
                continue
                
            total_games = squadra.vittorie + squadra.sconfitte
            if total_games < cfg.COACH_MIDSEASON_MIN_GAMES: continue
            
            win_rate = squadra.vittorie / total_games
            if (win_rate < cfg.COACH_MIDSEASON_WIN_PCT
                    and getattr(squadra.coach, 'years_with_current_team', 1) >= cfg.COACH_MIDSEASON_MIN_SEASONS):
                log_msg = f"🚨 COACH FIRED MID-SEASON: The {squadra.nome} fired coach {squadra.coach.nome} (Record: {squadra.vittorie}-{squadra.sconfitte})."
                main_log.info(log_msg)
                from core.news_generator import add_news, firing_tier
                add_news(
                    category="general",
                    title=f"{squadra.nome} fire coach {squadra.coach.nome}",
                    excerpt=f"The ownership dismisses the coach with the team at {squadra.vittorie}-{squadra.sconfitte}.",
                    teams=[squadra.nome],
                    season=self.season_number,
                    kind="firing",
                    tier=firing_tier(squadra.coach.nome)
                )

                if not hasattr(self, 'unemployed_coaches'):
                    self.unemployed_coaches = []
                self.unemployed_coaches.append(squadra.coach)
                
                # Replacement with an interim from the pool or a promoted new assistant
                interim = self._generate_coach_candidate()
                interim.contratto_anni_rimanenti = 1
                interim.contratto_totale_anni = 1
                interim.nome = f"Interim {interim.nome}"
                squadra.coach = interim
                mark_coach_change(self, fo, squadra.nome)
                main_log.info(f"   The {squadra.nome} named {interim.nome} as interim coach.")
                fired_count += 1
                
        if fired_count == 0:
            main_log.info("   Technical stability confirmed across the league.")

    def _gestisci_progressione_coach(self):
        """At the end of the offseason, all the coaches age, receive seasonal XP, develop and handle their contracts."""
        main_log.info("\n--- COACH DEVELOPMENT AND CONTRACTS PHASE ---")
        for squadra in self.squadre:
            coach = squadra.coach
            if not coach:
                continue

            coach.eta += 1
            coach.years_with_current_team += 1
            coach.contratto_anni_rimanenti = max(0, coach.contratto_anni_rimanenti - 1)

            # Retirement by age (CONFIG.COACHING RETIRE_*): a CPU head coach under contract retired only if his
            # contract ran out unrenewed, so one coached at 84. The user's coach is the user's call.
            is_user_bench = (self.squadra_giocatore and squadra.nome == self.squadra_giocatore.nome
                             and not getattr(self, 'is_spectator', False))
            if not is_user_bench and coach_retires_now(coach.eta, random.random()):
                main_log.info(f"   🎓 COACH RETIREMENT: {coach.nome} ({coach.eta}) retires from the {squadra.nome} bench.")
                try:   # news never break the offseason
                    from core.news_generator import generate_front_office_news
                    generate_front_office_news("retired", squadra.nome, "coach", coach.nome,
                                               f"{coach.nome} retires at {coach.eta} after "
                                               f"{coach.years_with_current_team} seasons with the {squadra.nome}.",
                                               season=self.season_number)
                except Exception as exc:
                    main_log.warning("coach retirement news failed: %s", exc)
                squadra.coach = None
                continue

            # End-of-season XP bonus
            season_xp = 200 + (squadra.vittorie * 15)
            if squadra in self.playoff_teams.get('east', []) or squadra in self.playoff_teams.get('west', []):
                season_xp += 150
            if self.campione and squadra.nome == self.campione.nome:
                season_xp += 750
            
            coach.add_xp(season_xp)

            # OVR development (CONFIG.COACHING): only a season over expectations, before the growth age limit
            cc = CONFIG.COACHING
            if coach.ovr_totale < coach.potenziale and coach.eta < cc.GROWTH_MAX_AGE:
                performance_delta = squadra.vittorie - squadra.vittorie_attese
                guadagno = max(0, min(cc.GROWTH_MAX_PER_SEASON, int(performance_delta / cc.GROWTH_WINS_PER_POINT)))
                if guadagno > 0:
                    coach.ovr_offensivo = min(99, coach.ovr_offensivo + guadagno)
                    coach.ovr_difensivo = min(99, coach.ovr_difensivo + guadagno)
                    coach.player_development = min(99, coach.player_development + guadagno)
                    coach.tactical_acumen = min(99, coach.tactical_acumen + guadagno)
            elif coach.eta >= cc.DECLINE_AGE:
                coach.ovr_offensivo = max(cc.DECLINE_FLOOR, coach.ovr_offensivo - 1)
                coach.ovr_difensivo = max(cc.DECLINE_FLOOR, coach.ovr_difensivo - 1)

            # Handling of Expiring Contracts (0 years remaining)
            if coach.contratto_anni_rimanenti <= 0:
                is_user_team = (self.squadra_giocatore and squadra.nome == self.squadra_giocatore.nome and not getattr(self, 'is_spectator', False))
                if is_user_team:
                    log_msg = f"CONTRACT EXPIRED: Coach {coach.nome}'s contract with the {squadra.nome} has expired! Renew it in the GM Office or hire a replacement."
                    if 'ritiri_sviluppo' in self.offseason_log_data:
                        self.offseason_log_data['ritiri_sviluppo'].append(log_msg)
                    main_log.info(f"   🚨 {log_msg}")
                else:
                    # Renewal / Expiration logic for AI Teams
                    performance = squadra.vittorie - squadra.vittorie_attese
                    if coach.ovr_totale >= 72 and performance >= CONFIG.FRONT_OFFICE.COACH_OWNER_DELTA:
                        anni_rinnovo = random.choice([2, 3, 4])
                        coach.contratto_totale_anni = anni_rinnovo
                        coach.contratto_anni_rimanenti = anni_rinnovo
                        coach.job_security = 75.0
                        log_msg = f"AI RENEWAL: The {squadra.nome} renewed coach {coach.nome}'s contract for {anni_rinnovo} years at ${coach.salario:.1f}M/year."
                        main_log.info(f"   👔 {log_msg}")
                    else:
                        log_msg = f"CONTRACT EXPIRATION: Coach {coach.nome}'s contract with the {squadra.nome} has ended."
                        main_log.info(f"   ⌛ {log_msg}")
                        if performance < CONFIG.FRONT_OFFICE.COACH_OWNER_DELTA:
                            # Let go for results: a coaching change on the season just closed (owners.py reads it)
                            rows = ensure_front_office(self).records.get(squadra.nome)
                            if rows:
                                rows[-1]["coach_fired"] = True
                            try:   # news never break the offseason
                                from core.news_generator import generate_front_office_news
                                generate_front_office_news("fired", squadra.nome, "coach", coach.nome,
                                                           f"The {squadra.nome} let {coach.nome} go at the end of "
                                                           f"his contract after {squadra.vittorie}-{squadra.sconfitte}.",
                                                           season=self.season_number)
                            except Exception as exc:
                                main_log.warning("coach firing news failed: %s", exc)
                        if coach.eta < 68:
                            if not hasattr(self, 'unemployed_coaches'):
                                self.unemployed_coaches = []
                            self.unemployed_coaches.append(coach)
                        squadra.coach = None

        # This phase runs AFTER the hiring phase: CPU teams whose coach just left would
        # otherwise play a full season without a head coach. Fill those vacancies now
        # (the user's team is skipped inside _gestisci_fase_assunzioni).
        self._gestisci_fase_assunzioni()

    def esegui_draft_lottery(self):
        """
        Simulates the NBA lottery system.
        """
        main_log.info("\n--- DRAFT LOTTERY (Pre-Trade) ---")
        
        playoff_teams_obj = self.get_playoff_teams(self.squadre)
        squadre_lotteria_obj = lottery_teams(self)
        # We save the pre-lottery projection for the logs
        ordine_pre_lottery = [s.nome for s in squadre_lotteria_obj]
        
        num_lottery_teams = len(squadre_lotteria_obj)
        squadre_lotteria = [s.nome for s in squadre_lotteria_obj]
        
        main_log.info(f"Teams in the lottery: {num_lottery_teams}")
        
        nba_odds_per_seed = lottery_weights(num_lottery_teams)
        
        lottery_pool = squadre_lotteria.copy()
        lottery_odds = nba_odds_per_seed[:num_lottery_teams]

        top_4_picks = []
        for i in range(1, CONFIG.OFFSEASON.LOTTERY_DRAWN_PICKS + 1):
            if not lottery_pool: break

            total_odds = sum(lottery_odds)
            normalized_odds = [odd / total_odds for odd in lottery_odds]
            
            winner = random.choices(lottery_pool, weights=normalized_odds, k=1)[0]
            top_4_picks.append(winner)
            
            winner_index = lottery_pool.index(winner)
            lottery_pool.pop(winner_index)
            lottery_odds.pop(winner_index)
            
        ordine_finale_lotteria = top_4_picks
        squadre_rimanenti = [team for team in squadre_lotteria if team not in top_4_picks]
        ordine_finale_lotteria.extend(squadre_rimanenti)
        
        # LOGS
        main_log.info("\n--- LOTTERY RESULTS ---")
        team_obj_map = {s.nome: s for s in self.squadre}
        
        # Exact odds of the #1 pick and of a drawn pick for every seed, from the weights used above
        seed_odds = lottery_odds_table(nba_odds_per_seed)

        # Pre-Lottery Odds Table (Ordinata per seed 1..14)
        odds_table = []
        for idx, sq_obj in enumerate(squadre_lotteria_obj):
            t_name = sq_obj.nome
            w = getattr(sq_obj, 'vittorie', 0)
            l = getattr(sq_obj, 'sconfitte', 0)
            final_p = ordine_finale_lotteria.index(t_name) + 1 if t_name in ordine_finale_lotteria else idx + 1
            odds_table.append({
                "seed": idx + 1,
                "team": t_name,
                "record": f"{w}-{l}",
                "win_pct": round(w / max(1, w + l), 3),
                "odds_first": seed_odds[idx]["odds_first"],
                "odds_top4": seed_odds[idx]["odds_top"],
                "final_pick": final_p,
                "delta": (idx + 1) - final_p
            })

        # Top Prospects Preview (5 migliori rookie)
        top_prospects = []
        anno_corrente = getattr(self, 'anno_corrente', 2024)
        draft_file_candidates = [p for p in (draft_class_file(self, anno_corrente),
                                             draft_class_file(self, anno_corrente + 1)) if p]
        loaded_rookies = []
        if hasattr(self, 'draft_class') and self.draft_class:
            loaded_rookies = self.draft_class
        else:
            for d_path in draft_file_candidates:
                if os.path.exists(d_path):
                    try:
                        with open(d_path, 'r', encoding='utf-8') as f:
                            r_list = json.load(f)
                            if isinstance(r_list, list):
                                loaded_rookies = sorted(r_list, key=lambda x: x.get('potenziale', 70), reverse=True)
                                break
                    except Exception:
                        pass

        if loaded_rookies:
            for r in loaded_rookies[:5]:
                if isinstance(r, dict):
                    top_prospects.append({
                        "nome": r.get("nome", "Top Prospect"),
                        "ruolo": normalize_role(r.get("ruolo")) or "SG",
                        "valutazione": r.get("valutazione", 76),
                        "potenziale": r.get("potenziale", 88),
                        "provenance": r.get("provenance", "NCAA / International"),
                        "pedigree": r.get("pedigree", "Lottery Prospect")
                    })
                elif hasattr(r, 'nome'):
                    top_prospects.append({
                        "nome": r.nome,
                        "ruolo": r.ruolo,
                        "valutazione": getattr(r, 'valutazione', 76),
                        "potenziale": getattr(r, 'potenziale', 88),
                        "provenance": getattr(r, 'provenance', "NCAA / International"),
                        "pedigree": getattr(r, 'pedigree', "Lottery Prospect")
                    })

        # Build the list of the 14 lottery picks
        lottery_picks_details = []
        for i, team in enumerate(ordine_finale_lotteria):
            pick_num = i + 1
            pos_originale = ordine_pre_lottery.index(team) + 1
            delta = pos_originale - pick_num
            sq_obj = team_obj_map.get(team)
            w = getattr(sq_obj, 'vittorie', 0) if sq_obj else 0
            l = getattr(sq_obj, 'sconfitte', 0) if sq_obj else 0
            orig_seed_idx = pos_originale - 1
            if delta > 0:
                delta_str = f"(↑ {delta} posizioni)"
            elif delta < 0:
                delta_str = f"(↓ {-delta} posizioni)"
            else:
                delta_str = "(-)"
            main_log.info(f"Pick #{pick_num}: {team} [Projection: #{pos_originale}] {delta_str}")
            
            if 'lottery_results' not in self.offseason_log_data:
                self.offseason_log_data['lottery_results'] = []
            self.offseason_log_data['lottery_results'].append(f"Pick #{pick_num}: {team} [Proj: #{pos_originale}] {delta_str}")
            
            lottery_picks_details.append({
                "pick": pick_num,
                "team": team,
                "projected": pos_originale,
                "delta": delta,
                "record": f"{w}-{l}",
                "win_pct": round(w / max(1, w + l), 3),
                "odds_first": seed_odds[orig_seed_idx]["odds_first"],
                "odds_top4": seed_odds[orig_seed_idx]["odds_top"]
            })

        # Complete Round 1 Board (Picks 1-30)
        scelte_playoff = [s.nome for s in sorted(playoff_teams_obj, key=lambda s: s.vittorie)]
        self.draft_lottery_order = ordine_finale_lotteria + scelte_playoff
        self.ordine_draft = self.draft_lottery_order

        full_round_1 = []
        for i, team in enumerate(self.draft_lottery_order):
            pick_num = i + 1
            is_lottery = i < len(ordine_finale_lotteria)
            sq_obj = team_obj_map.get(team)
            w = getattr(sq_obj, 'vittorie', 0) if sq_obj else 0
            l = getattr(sq_obj, 'sconfitte', 0) if sq_obj else 0
            if is_lottery:
                pos_orig = ordine_pre_lottery.index(team) + 1
                delta = pos_orig - pick_num
            else:
                pos_orig = pick_num
                delta = 0
            full_round_1.append({
                "pick": pick_num,
                "team": team,
                "record": f"{w}-{l}",
                "is_lottery": is_lottery,
                "projected": pos_orig,
                "delta": delta
            })

        # Winners and Losers
        max_jump = max(lottery_picks_details, key=lambda p: p["delta"]) if lottery_picks_details else None
        max_drop = min(lottery_picks_details, key=lambda p: p["delta"]) if lottery_picks_details else None

        # Package rich lottery object
        rich_lottery_data = {
            "picks": lottery_picks_details,
            "odds_table": odds_table,
            "hunt_steps": hunt_steps(nba_odds_per_seed, [ordine_pre_lottery.index(t) for t in ordine_finale_lotteria]),
            "full_round_1": full_round_1,
            "top_prospects": top_prospects,
            "winner_team": ordine_finale_lotteria[0] if ordine_finale_lotteria else "N/A",
            "biggest_winner": max_jump if max_jump and max_jump["delta"] > 0 else None,
            "biggest_loser": max_drop if max_drop and max_drop["delta"] < 0 else None,
            "season_year": anno_corrente
        }

        # Who owns each lottery pick before and after the protections are resolved (a protected pick can go back)
        owners_before = {team: pick_owner(self, 1, team) for team in ordine_finale_lotteria}
        self.offseason_log_data['lottery_details'] = rich_lottery_data
        self._resolve_pick_protections_year_1()
        annotate_owners(lottery_picks_details, owners_before, self)

    def _resolve_pick_protections_year_1(self):
        """
        Resolves the protections on Year 1 picks after the lottery.
        If a protected pick lands in the protected range, it is returned
        to the original owner. No compensation is provided (penalty).
        """
        if 1 not in self.pick_ownership:
            return
            
        main_log.info("\n--- DRAFT PICK PROTECTION RESOLUTION ---")
        picks_year_1 = list(self.pick_ownership[1].items())
        
        for pick_key, current_owner in picks_year_1:
            if not pick_key.startswith("R1"):
                continue # Protections only apply to the first round
                
            parts = pick_key.split("-")
            if len(parts) < 2:
                continue
            original_team_name = parts[1]
            
            # If the pick still belongs to the original owner, there is nothing to resolve
            if current_owner == original_team_name:
                continue
                
            # Check whether there is a protection for this pick
            protection = self.pick_protections.get(1, {}).get(pick_key, "Unprotected")
            if protection == "Unprotected":
                continue
                
            # Find the draft position of this original pick
            if original_team_name in self.draft_lottery_order:
                pick_pos = self.draft_lottery_order.index(original_team_name) + 1
            else:
                continue
                
            # Check whether the protection is triggered
            triggered = False
            if protection == "Top 3" and pick_pos <= 3:
                triggered = True
            elif protection == "Top 5" and pick_pos <= 5:
                triggered = True
            elif protection == "Lottery" and pick_pos <= CONFIG.OFFSEASON.LOTTERY_TEAMS_COUNT:
                triggered = True
                
            if triggered:
                # Return the pick to the original owner
                self.pick_ownership[1][pick_key] = original_team_name
                
                log_msg = f"PROTECTION TRIGGERED: The R1-{original_team_name} pick (landing at position #{pick_pos}) was protected ({protection}). It goes back to {original_team_name}. {current_owner} loses the pick without compensation."
                main_log.info(log_msg)
                
                if 'lottery_results' not in self.offseason_log_data:
                    self.offseason_log_data['lottery_results'] = []
                self.offseason_log_data['lottery_results'].append(log_msg)

    def trade_period_midseason(self):
        """
        MID-SEASON TRADE DEADLINE
        Every CPU trade is born from a GM wish (trades/windows.py); `trade_difficulty` acts inside acceptance.
        """
        main_log.info("=" * 60)
        main_log.info("MID-SEASON TRADE DEADLINE")
        main_log.info("=" * 60)

        trades_completed, trade_finder = run_trade_window(self, "deadline")

        main_log.info(f"\n{'=' * 60}")
        main_log.info(f"DEADLINE ENDED: {trades_completed} trade(s) completed")
        main_log.info(f"{'=' * 60}\n")

        # Log trades for UI
        if 'scambi_midseason' not in self.offseason_log_data:
            self.offseason_log_data['scambi_midseason'] = []
        self.offseason_log_data['scambi_midseason'] = trade_finder.logscambi.copy()
        for trade in trade_finder.logscambi:
            self.podcast_logger.log_trade(trade, period="mid_season")

    def check_and_generate_trade_block_offer(self, force=False):
        """
        Check for a random chance to generate a trade block offer from a CPU team
        targeting a player on the user's trade block. Keep the list size capped at 5.
        """
        if not self.squadra_giocatore or deadline_passed(self):
            return
            
        import random
        diff = getattr(self, 'trade_difficulty', 'realistic')
        offer_chance = 0.25 if diff == 'easy' else (0.12 if diff == 'realistic' else 0.05)
        
        if force or random.random() < offer_chance:
            from trades.trade_block_manager import TradeBlockManager
            offer = TradeBlockManager.generate_offer_for_simulation(self, self.squadra_giocatore)
            if offer:
                # If we exceed the cap of 5 pending offers, remove the oldest one
                if len(self.pending_trade_block_offers) >= 5:
                    self.pending_trade_block_offers.pop(0)
                self.pending_trade_block_offers.append(offer)
                main_log.info(f"TRADE BLOCK OFFER: {offer['offering_team']} offered a trade block deal targeting a player.")

    def trade_period_predraft(self):
        """
        PRE-DRAFT TRADE PERIOD
        Every CPU trade is born from a GM wish (trades/windows.py); draft-night trades happen live in the draft.
        """
        main_log.info("=" * 60)
        main_log.info("PRE-DRAFT TRADE PERIOD")
        main_log.info("=" * 60)

        trades_completed, trade_finder = run_trade_window(self, "predraft")

        main_log.info(f"\n{'=' * 60}")
        main_log.info(f"PRE-DRAFT PERIOD ENDED: {trades_completed} trade(s) completed")
        main_log.info(f"{'=' * 60}\n")
        print(f"PRE-DRAFT PERIOD ENDED: {trades_completed} trade(s) completed", flush=True)

        # Log trades for UI
        if 'scambi' not in self.offseason_log_data:
            self.offseason_log_data['scambi'] = []
        self.offseason_log_data['scambi'] = trade_finder.logscambi.copy()
        for trade in trade_finder.logscambi:
            self.podcast_logger.log_trade(trade, period="offseason")

    def _setup_playoffs(self):
        """
        Setup playoffs with Play-In Tournament.
        Seeds 1-6 go directly to playoffs.
        Seeds 7-10 compete in Play-In Tournament.
        """
        self.imposta_rotazioni_stagione(force_user=False)
        for team in self.squadre:
            for player in team.roster:
                player.reset_for_playoffs()
        
        classifica_est = sorted(self.squadre_est, key=lambda s: s.vittorie, reverse=True)
        classifica_ovest = sorted(self.squadre_ovest, key=lambda s: s.vittorie, reverse=True)

        if not getattr(self, 'enable_play_in', True):
            # Play-In Disabled: Classic Top 8 qualify directly
            self.direct_qualifiers['east'] = classifica_est[:8]
            self.direct_qualifiers['west'] = classifica_ovest[:8]
            self.playoff_teams['east'] = classifica_est[:8]
            self.playoff_teams['west'] = classifica_ovest[:8]
            self.play_in_teams = {'east': [], 'west': []}
            self.play_in_results = {'east': {}, 'west': {}}
            self.play_in_game_index = 6
            self.playoff_bracket_data = {
                'east': {'play_in': [], 'qf': [], 'sf': [], 'cf': []},
                'west': {'play_in': [], 'qf': [], 'sf': [], 'cf': []},
                'finals': []
            }
            self.playoff_state = "QF"
            self.setup_current_playoff_round()
            main_log.info("\n" + "=" * 60)
            main_log.info("CLASSIC TOP 8 PLAYOFFS SETUP (PLAY-IN DISABLED)")
            main_log.info(f"East Seeds 1-8: {[t.nome for t in self.playoff_teams['east']]}")
            main_log.info(f"West Seeds 1-8: {[t.nome for t in self.playoff_teams['west']]}")
            main_log.info("=" * 60)
            return

        # Seeds 1-6 are direct qualifiers
        self.direct_qualifiers['east'] = classifica_est[:6]
        self.direct_qualifiers['west'] = classifica_ovest[:6]
        
        # Seeds 7-10 go to Play-In Tournament
        self.play_in_teams['east'] = classifica_est[6:10]
        self.play_in_teams['west'] = classifica_ovest[6:10]
        
        self.playoff_bracket_data = {
            'east': {'play_in': [], 'qf': [], 'sf': [], 'cf': []},
            'west': {'play_in': [], 'qf': [], 'sf': [], 'cf': []},
            'finals': []
        }
        
        # Start with Play-In state
        self.playoff_state = "PLAY_IN"
        main_log.info("\n" + "=" * 60)
        main_log.info("PLAY-IN TOURNAMENT SETUP")
        main_log.info("=" * 60)
        main_log.info(f"East Direct Qualifiers (1-6): {[t.nome for t in self.direct_qualifiers['east']]}")
        main_log.info(f"East Play-In (7-10): {[t.nome for t in self.play_in_teams['east']]}")
        main_log.info(f"West Direct Qualifiers (1-6): {[t.nome for t in self.direct_qualifiers['west']]}")
        main_log.info(f"West Play-In (7-10): {[t.nome for t in self.play_in_teams['west']]}")

    def _simula_play_in(self, watch_series_id: str = None):
        """
        Simulate ONE Play-In game based on play_in_game_index.
        Games 0-2: East (G1, G2, G3)
        Games 3-5: West (G1, G2, G3)
        Returns the game result for UI display.
        """
        idx = self.play_in_game_index
        
        # Determine conference and game number
        if idx < 3:
            conf = 'east'
            game_num = idx  # 0, 1, 2
        else:
            conf = 'west'
            game_num = idx - 3  # 0, 1, 2
        
        conf_name = "Eastern" if conf == 'east' else "Western"
        teams = self.play_in_teams[conf]
        
        if len(teams) < 4:
            main_log.warning(f"Not enough teams for {conf_name} Play-In")
            self.play_in_game_index += 1
            return None
        
        # Initialize conference results if needed
        if 'game1' not in self.play_in_results[conf]:
            self.play_in_results[conf] = {
                'game1': None, 'game2': None, 'game3': None,
                'seventh_seed': None, 'eighth_seed': None, 'eliminated': []
            }
            self.playoff_bracket_data[conf]['play_in'] = [None, None, None]
        
        result = None
        
        # Determine teams playing to check if this is the watched game
        if game_num == 0:
            teamA, teamB = teams[0], teams[1]
            desc = f"{conf_name} Play-In 7v8"
        elif game_num == 1:
            teamA, teamB = teams[2], teams[3]
            desc = f"{conf_name} Play-In 9v10"
        else:
            teamA = self.play_in_results[conf]['game1']['loser_obj']
            teamB = self.play_in_results[conf]['game2']['winner_obj']
            desc = f"{conf_name} Play-In Final"

        is_watch = False
        if watch_series_id is not None:
            if watch_series_id in [teamA.nome, teamB.nome] or watch_series_id == f"{teamA.nome}_{teamB.nome}" or watch_series_id == f"{teamB.nome}_{teamA.nome}" or watch_series_id == "PLAY_IN":
                is_watch = True

        if game_num == 0:
            main_log.info(f"\n{conf_name} Play-In Game 1: {teamA.nome} vs {teamB.nome}")
            winner, loser, log = self._simula_serie(teamA, teamB, desc, best_of=1, enable_play_log=is_watch)
            main_log.info(f"  Winner (7th seed): {winner.nome}")
            
            self.play_in_results[conf]['game1'] = {
                'winner': winner.nome, 'loser': loser.nome, 'log': log,
                'winner_obj': winner, 'loser_obj': loser
            }
            self.play_in_results[conf]['seventh_seed'] = winner.nome
            self.playoff_bracket_data[conf]['play_in'][0] = log
            result = {'game': 'G1', 'conf': conf, 'winner': winner.nome, 'loser': loser.nome}
            
        elif game_num == 1:
            main_log.info(f"\n{conf_name} Play-In Game 2: {teamA.nome} vs {teamB.nome}")
            winner, loser, log = self._simula_serie(teamA, teamB, desc, best_of=1, enable_play_log=is_watch)
            main_log.info(f"  Winner advances: {winner.nome}")
            main_log.info(f"  ELIMINATED: {loser.nome}")
            
            self.play_in_results[conf]['game2'] = {
                'winner': winner.nome, 'loser': loser.nome, 'log': log,
                'winner_obj': winner, 'loser_obj': loser
            }
            self.play_in_results[conf]['eliminated'].append(loser.nome)
            self.playoff_bracket_data[conf]['play_in'][1] = log
            result = {'game': 'G2', 'conf': conf, 'winner': winner.nome, 'loser': loser.nome, 'eliminated': loser.nome}
            
        elif game_num == 2:
            main_log.info(f"\n{conf_name} Play-In Final: {teamA.nome} vs {teamB.nome}")
            winner, loser, log = self._simula_serie(teamA, teamB, desc, best_of=1, enable_play_log=is_watch)
            main_log.info(f"  Winner (8th seed): {winner.nome}")
            main_log.info(f"  ELIMINATED: {loser.nome}")
            
            self.play_in_results[conf]['game3'] = {
                'winner': winner.nome, 'loser': loser.nome, 'log': log,
                'winner_obj': winner, 'loser_obj': loser
            }
            self.play_in_results[conf]['eighth_seed'] = winner.nome
            self.play_in_results[conf]['eliminated'].append(loser.nome)
            self.playoff_bracket_data[conf]['play_in'][2] = log
            
            # Set playoff teams for this conference
            seventh_seed = self.play_in_results[conf]['game1']['winner_obj']
            self.playoff_teams[conf] = self.direct_qualifiers[conf] + [seventh_seed, winner]
            
            main_log.info(f"\n{conf_name} Conference Playoff Field:")
            for i, team in enumerate(self.playoff_teams[conf], 1):
                seed_label = f"({i})" if i <= 6 else f"({i} via Play-In)"
                main_log.info(f"  {seed_label} {team.nome}")
            
            result = {'game': 'G3', 'conf': conf, 'winner': winner.nome, 'loser': loser.nome, 'eliminated': loser.nome}
        
        # If this is the watched game, package the live simulation logs
        if is_watch and teamA.partita:
            result['watch_game'] = {
                'game_num': 1,
                'team1': teamA.nome,
                'team2': teamB.nome,
                'home_team': teamA.partita.squadra_casa.nome,
                'away_team': teamA.partita.squadra_ospite.nome,
                'home_score': teamA.partita.punteggio[teamA.partita.squadra_casa.nome],
                'away_score': teamA.partita.punteggio[teamA.partita.squadra_ospite.nome],
                'winner': winner.nome,
                'play_log': teamA.partita.play_log,
                'series_score': "1-0"
            }

        # Advance index
        self.play_in_game_index += 1
        
        # Check if all 6 games complete (indices 0-5)
        if self.play_in_game_index >= 6:
            self.playoff_state = "QF"
            main_log.info("\n" + "=" * 60)
            main_log.info("Play-In Complete! Moving to Quarterfinals...")
            main_log.info("=" * 60)
        
        return result

    def setup_current_playoff_round(self):
        """Initializes the active series for the current playoff round."""
        self.active_playoff_series = []
        
        if self.playoff_state == "QF":
            east_qf = self.playoff_teams['east']
            west_qf = self.playoff_teams['west']
            
            # Matchups for the Quarterfinals (QF)
            self.active_playoff_series.append({"s1": east_qf[0], "s2": east_qf[7], "s1_seed": 1, "s2_seed": 8, "conf": "east", "round": "QF"})
            self.active_playoff_series.append({"s1": east_qf[3], "s2": east_qf[4], "s1_seed": 4, "s2_seed": 5, "conf": "east", "round": "QF"})
            self.active_playoff_series.append({"s1": east_qf[2], "s2": east_qf[5], "s1_seed": 3, "s2_seed": 6, "conf": "east", "round": "QF"})
            self.active_playoff_series.append({"s1": east_qf[1], "s2": east_qf[6], "s1_seed": 2, "s2_seed": 7, "conf": "east", "round": "QF"})
            
            self.active_playoff_series.append({"s1": west_qf[0], "s2": west_qf[7], "s1_seed": 1, "s2_seed": 8, "conf": "west", "round": "QF"})
            self.active_playoff_series.append({"s1": west_qf[3], "s2": west_qf[4], "s1_seed": 4, "s2_seed": 5, "conf": "west", "round": "QF"})
            self.active_playoff_series.append({"s1": west_qf[2], "s2": west_qf[5], "s1_seed": 3, "s2_seed": 6, "conf": "west", "round": "QF"})
            self.active_playoff_series.append({"s1": west_qf[1], "s2": west_qf[6], "s1_seed": 2, "s2_seed": 7, "conf": "west", "round": "QF"})
            
        elif self.playoff_state == "SF":
            east_sf = self.next_round_teams['east']
            west_sf = self.next_round_teams['west']
            
            self.active_playoff_series.append({"s1": east_sf[0], "s2": east_sf[1], "s1_seed": getattr(east_sf[0], 'playoff_seed', ''), "s2_seed": getattr(east_sf[1], 'playoff_seed', ''), "conf": "east", "round": "SF"})
            self.active_playoff_series.append({"s1": east_sf[2], "s2": east_sf[3], "s1_seed": getattr(east_sf[2], 'playoff_seed', ''), "s2_seed": getattr(east_sf[3], 'playoff_seed', ''), "conf": "east", "round": "SF"})
            
            self.active_playoff_series.append({"s1": west_sf[0], "s2": west_sf[1], "s1_seed": getattr(west_sf[0], 'playoff_seed', ''), "s2_seed": getattr(west_sf[1], 'playoff_seed', ''), "conf": "west", "round": "SF"})
            self.active_playoff_series.append({"s1": west_sf[2], "s2": west_sf[3], "s1_seed": getattr(west_sf[2], 'playoff_seed', ''), "s2_seed": getattr(west_sf[3], 'playoff_seed', ''), "conf": "west", "round": "SF"})
            
        elif self.playoff_state == "CF":
            east_cf = self.next_round_teams['east']
            west_cf = self.next_round_teams['west']
            
            self.active_playoff_series.append({"s1": east_cf[0], "s2": east_cf[1], "s1_seed": getattr(east_cf[0], 'playoff_seed', ''), "s2_seed": getattr(east_cf[1], 'playoff_seed', ''), "conf": "east", "round": "CF"})
            self.active_playoff_series.append({"s1": west_cf[0], "s2": west_cf[1], "s1_seed": getattr(west_cf[0], 'playoff_seed', ''), "s2_seed": getattr(west_cf[1], 'playoff_seed', ''), "conf": "west", "round": "CF"})
            
        elif self.playoff_state == "FINALS":
            east_final = self.next_round_teams['east'][0]
            west_final = self.next_round_teams['west'][0]
            
            self.active_playoff_series.append({"s1": east_final, "s2": west_final, "s1_seed": getattr(east_final, 'playoff_seed', ''), "s2_seed": getattr(west_final, 'playoff_seed', ''), "conf": "finals", "round": "FINALS"})

        for series in self.active_playoff_series:
            series["vittorie_s1"] = 0
            series["vittorie_s2"] = 0
            series["winner_nome"] = None
            series["games"] = []

    def _aggiorna_playoff_bracket_data(self):
        """Updates the playoff bracket information in real time."""
        if not self.playoff_bracket_data:
            self.playoff_bracket_data = {
                'east': {'play_in': [None, None, None], 'qf': [], 'sf': [], 'cf': []},
                'west': {'play_in': [None, None, None], 'qf': [], 'sf': [], 'cf': []},
                'finals': []
            }
            
        for series in self.active_playoff_series:
            r = series["round"].lower()
            conf = series["conf"]
            
            # Keep full game reports (including box scores) for all rounds of playoffs (QF, SF, CF, Finals)
            lean_games = series["games"]
            
            series_log = {
                "s1_nome": series["s1"].nome,
                "s1_vittorie": series["vittorie_s1"],
                "s2_nome": series["s2"].nome,
                "s2_vittorie": series["vittorie_s2"],
                "winner_nome": series["winner_nome"],
                "s1_seed": series["s1_seed"],
                "s2_seed": series["s2_seed"],
                "games": lean_games
            }
            
            if conf == "finals":
                self.playoff_bracket_data["finals"] = [series_log]
            else:
                existing = self.playoff_bracket_data[conf][r]
                match_idx = -1
                for idx, val in enumerate(existing):
                    if val and val.get("s1_nome") == series["s1"].nome and val.get("s2_nome") == series["s2"].nome:
                        match_idx = idx
                        break
                
                if match_idx >= 0:
                    self.playoff_bracket_data[conf][r][match_idx] = series_log
                else:
                    self.playoff_bracket_data[conf][r].append(series_log)

    def _registra_gara_playoff(self, game_num: int, squadra_casa: 'Squadra', squadra_ospite: 'Squadra', round_name: str) -> Dict[str, Any]:
        """Log of one finished playoff / play-in game, with the same result sheet the calendar games get."""
        partita = squadra_casa.partita

        def team_log(squadra):
            return {
                "nome": squadra.nome,
                "punteggio": partita.punteggio[squadra.nome],
                "punteggi_quarti": partita.punteggi_quarti[squadra.nome],
                "coach": squadra.coach.nome if squadra.coach else "N/A",
                "stile": squadra.coach.stile_gioco if squadra.coach else "N/A",
            }

        game_id = f"PO-{round_name}-{squadra_ospite.nome}@{squadra_casa.nome}-G{game_num}"
        return {
            "game_num": game_num,
            "squadra_casa": team_log(squadra_casa),
            "squadra_ospite": team_log(squadra_ospite),
            "game_winner_info": partita.ultimo_evento if "GAME WINNER" in partita.ultimo_evento else None,
            "result_sheet": self._genera_box_score_partita(partita, squadra_casa, squadra_ospite, game_id),
        }

    def simula_gara_playoff(self) -> Dict:
        """
        Simulates exactly ONE game for each ongoing series in the current playoff round.
        Returns a summary of the simulated game results.
        """
        if not getattr(self, 'active_playoff_series', None):
            self.setup_current_playoff_round()
            
        summary = {"round": self.playoff_state, "games": [], "finished_series": []}
        any_series_active = False
        
        for series in self.active_playoff_series:
            if series["winner_nome"] is not None:
                continue
                
            any_series_active = True
            s1 = series["s1"]
            s2 = series["s2"]
            best_of = 7
            vittorie_necessarie = (best_of // 2) + 1
            
            i = len(series["games"]) + 1
            squadra_casa, squadra_ospite = (s1, s2) if i in [1, 2, 5, 7] else (s2, s1)
            
            current_score = (series["vittorie_s1"], series["vittorie_s2"]) if squadra_casa == s1 else (series["vittorie_s2"], series["vittorie_s1"])
            
            vincitore_partita = self._simula_e_registra_partita(squadra_casa, squadra_ospite, True, round_name=series["round"], series_score=current_score)
            
            punteggio_casa = squadra_casa.partita.punteggio[squadra_casa.nome]
            punteggio_ospite = squadra_ospite.partita.punteggio[squadra_ospite.nome]
            
            if vincitore_partita.nome == s1.nome:
                series["vittorie_s1"] += 1
            else:
                series["vittorie_s2"] += 1

            series["games"].append(self._registra_gara_playoff(i, squadra_casa, squadra_ospite, series["round"]))

            summary["games"].append({
                "series_desc": f"{s1.nome} ({series['vittorie_s1']}) vs {s2.nome} ({series['vittorie_s2']})",
                "game_num": i,
                "winner": vincitore_partita.nome,
                "score": f"{squadra_casa.nome} {punteggio_casa} - {punteggio_ospite} {squadra_ospite.nome}"
            })

            if series["vittorie_s1"] == vittorie_necessarie or series["vittorie_s2"] == vittorie_necessarie:
                winner_nome = s1.nome if series["vittorie_s1"] > series["vittorie_s2"] else s2.nome
                loser_nome = s2.nome if winner_nome == s1.nome else s1.nome
                series["winner_nome"] = winner_nome
                summary["finished_series"].append({
                    "winner": winner_nome,
                    "loser": loser_nome,
                    "score": f"{series['vittorie_s1']}-{series['vittorie_s2']}"
                })

                # Dynamic Playoff News generation
                try:
                    from core.news_generator import add_news
                    w_seed = series["s1_seed"] if winner_nome == s1.nome else series["s2_seed"]
                    l_seed = series["s2_seed"] if winner_nome == s1.nome else series["s1_seed"]
                    w_wins = series["vittorie_s1"] if winner_nome == s1.nome else series["vittorie_s2"]
                    l_wins = series["vittorie_s2"] if winner_nome == s1.nome else series["vittorie_s1"]
                    
                    # Count running scores for comebacks
                    w_run, l_run = 0, 0
                    was_down_3_0, was_down_3_1, was_down_2_0 = False, False, False
                    for g in series["games"]:
                        g_casa = g["squadra_casa"]
                        g_ospite = g["squadra_ospite"]
                        g_win = g_casa["nome"] if g_casa["punteggio"] > g_ospite["punteggio"] else g_ospite["nome"]
                        if g_win == winner_nome:
                            w_run += 1
                        else:
                            l_run += 1
                        
                        if l_run == 3 and w_run == 0:
                            was_down_3_0 = True
                        if l_run == 3 and w_run == 1:
                            was_down_3_1 = True
                        if l_run == 2 and w_run == 0:
                            was_down_2_0 = True
                            
                    is_sweep = (w_wins == 4 and l_wins == 0)
                    is_game_7 = (w_wins == 4 and l_wins == 3)
                    # Later rounds may carry '' as seed (playoff_seed missing): no upset detection then
                    is_upset = isinstance(w_seed, int) and isinstance(l_seed, int) and w_seed > l_seed + 1
                    
                    score = f"{w_wins}-{l_wins}"
                    finals = series["round"] == "FINALS"
                    if finals:
                        title = f"{winner_nome} are champions"
                        excerpt = f"They beat the {loser_nome} {score} in the Finals."
                    elif was_down_3_0:
                        title = f"{winner_nome} come back from 3-0 down to eliminate {loser_nome}"
                        excerpt = "Four straight wins after losing the first three games of the series."
                    elif was_down_3_1:
                        title = f"{winner_nome} come back from 3-1 down to eliminate {loser_nome}"
                        excerpt = "Three straight wins to take the series 4-3."
                    elif is_sweep:
                        title = f"{winner_nome} sweep {loser_nome}"
                        excerpt = "The series is over in four games."
                    elif is_upset:
                        title = f"Upset: No. {w_seed} {winner_nome} eliminate No. {l_seed} {loser_nome}"
                        excerpt = f"The lower seed takes the series {score}."
                    elif is_game_7:
                        title = f"{winner_nome} win Game 7 against {loser_nome}"
                        excerpt = f"The series ends {score}."
                    else:
                        title = f"{winner_nome} eliminate {loser_nome} {score}"
                        excerpt = "They move on to the next round."
                    big = finals or series["round"] == "CF" or is_upset or is_game_7 or was_down_3_1 or was_down_3_0
                    recap = []
                    for n, g in enumerate(series["games"], start=1):
                        home, away = g["squadra_casa"], g["squadra_ospite"]
                        recap.append({"game": n, "home": home["nome"], "home_score": home["punteggio"],
                                      "away": away["nome"], "away_score": away["punteggio"]})

                    add_news(
                        category="playoffs",
                        title=title,
                        excerpt=excerpt,
                        teams=[winner_nome, loser_nome],
                        season=self.season_number,
                        kind="champion" if finals else "playoffs",
                        tier=3 if big else 2,
                        details={"round": series["round"], "score": score, "games": recap}
                    )
                except Exception as ex:
                    main_log.error(f"Error logging playoff series news: {ex}")
                
        self._aggiorna_playoff_bracket_data()
        
        if any_series_active:
            all_complete = all(series["winner_nome"] is not None for series in self.active_playoff_series)
            if all_complete:
                self.finalizza_round_playoff()
                summary["round_completed"] = True
                summary["next_round"] = self.playoff_state
            else:
                summary["round_completed"] = False
        else:
            self.finalizza_round_playoff()
            summary["round_completed"] = True
            summary["next_round"] = self.playoff_state
            
        return summary

    def simula_gara_playoff_con_diretta(self, watch_series_id: str = None) -> Dict:
        """
        Simulates exactly ONE game for each active series.
        If watch_series_id is provided, that specific game is simulated with
        the play-by-play log enabled and the log is returned in the summary.
        All the other games are simulated in the background without a game log.
        """
        if not getattr(self, 'active_playoff_series', None):
            self.setup_current_playoff_round()
            
        summary = {"round": self.playoff_state, "watch_game": None, "games": [], "finished_series": []}
        any_series_active = False
        
        for series in self.active_playoff_series:
            if series["winner_nome"] is not None:
                continue
                
            any_series_active = True
            s1 = series["s1"]
            s2 = series["s2"]
            best_of = 7
            vittorie_necessarie = (best_of // 2) + 1
            
            i = len(series["games"]) + 1
            squadra_casa, squadra_ospite = (s1, s2) if i in [1, 2, 5, 7] else (s2, s1)
            current_score = (series["vittorie_s1"], series["vittorie_s2"]) if squadra_casa == s1 else (series["vittorie_s2"], series["vittorie_s1"])
            
            # Check whether this is the series selected to be watched
            is_watch_series = False
            if watch_series_id is not None:
                if watch_series_id in [s1.nome, s2.nome] or watch_series_id == f"{s1.nome}_{s2.nome}" or watch_series_id == f"{s2.nome}_{s1.nome}" or watch_series_id == series.get("id"):
                    is_watch_series = True
            
            vincitore_partita = self._simula_e_registra_partita(squadra_casa, squadra_ospite, True, round_name=series["round"], series_score=current_score, enable_play_log=is_watch_series)
            
            punteggio_casa = squadra_casa.partita.punteggio[squadra_casa.nome]
            punteggio_ospite = squadra_ospite.partita.punteggio[squadra_ospite.nome]
            
            if vincitore_partita.nome == s1.nome:
                series["vittorie_s1"] += 1
            else:
                series["vittorie_s2"] += 1

            series["games"].append(self._registra_gara_playoff(i, squadra_casa, squadra_ospite, series["round"]))

            summary["games"].append({
                "series_desc": f"{s1.nome} ({series['vittorie_s1']}) vs {s2.nome} ({series['vittorie_s2']})",
                "game_num": i,
                "winner": vincitore_partita.nome,
                "score": f"{squadra_casa.nome} {punteggio_casa} - {punteggio_ospite} {squadra_ospite.nome}"
            })

            # If this is the game to watch, we save the game log
            if is_watch_series and squadra_casa.partita:
                summary["watch_game"] = {
                    "game_num": i,
                    "team1": s1.nome,
                    "team2": s2.nome,
                    "home_team": squadra_casa.nome,
                    "away_team": squadra_ospite.nome,
                    "home_score": punteggio_casa,
                    "away_score": punteggio_ospite,
                    "winner": vincitore_partita.nome,
                    "play_log": squadra_casa.partita.play_log,
                    "series_score": f"{series['vittorie_s1']}-{series['vittorie_s2']}"
                }
                
            if series["vittorie_s1"] == vittorie_necessarie or series["vittorie_s2"] == vittorie_necessarie:
                winner_nome = s1.nome if series["vittorie_s1"] > series["vittorie_s2"] else s2.nome
                loser_nome = s2.nome if winner_nome == s1.nome else s1.nome
                series["winner_nome"] = winner_nome
                summary["finished_series"].append({
                    "winner": winner_nome,
                    "loser": loser_nome,
                    "score": f"{series['vittorie_s1']}-{series['vittorie_s2']}"
                })
                
                # Dynamic Playoff News generation
                try:
                    from core.news_generator import add_news
                    w_seed = series["s1_seed"] if winner_nome == s1.nome else series["s2_seed"]
                    l_seed = series["s2_seed"] if winner_nome == s1.nome else series["s1_seed"]
                    w_wins = series["vittorie_s1"] if winner_nome == s1.nome else series["vittorie_s2"]
                    l_wins = series["vittorie_s2"] if winner_nome == s1.nome else series["vittorie_s1"]
                    
                    # Count running scores for comebacks
                    w_run, l_run = 0, 0
                    for g in series["games"]:
                        g_casa = g["squadra_casa"]
                        g_ospite = g["squadra_ospite"]
                        g_win = g_casa["nome"] if g_casa["punteggio"] > g_ospite["punteggio"] else g_ospite["nome"]
                        if g_win == winner_nome:
                            w_run += 1
                        else:
                            l_run += 1
                    from core.news_generator import generate_playoff_elimination_news
                    generate_playoff_elimination_news(winner_nome, loser_nome, (w_wins, l_wins), series["round"], season=self.season_number)
                except Exception as e:
                    main_log.warning(f"Error creating playoff news: {str(e)}")
                    
        self._aggiorna_playoff_bracket_data()
        
        if any_series_active:
            all_complete = all(series["winner_nome"] is not None for series in self.active_playoff_series)
            if all_complete:
                self.finalizza_round_playoff()
                summary["round_completed"] = True
                summary["next_round"] = self.playoff_state
            else:
                summary["round_completed"] = False
        else:
            self.finalizza_round_playoff()
            summary["round_completed"] = True
            summary["next_round"] = self.playoff_state
            
        return summary

    def finalizza_round_playoff(self):
        """Finalizes the current playoff round, populating self.next_round_teams and advancing the state."""
        if self.playoff_state == "QF":
            east_winners = [
                self.active_playoff_series[0]["winner_nome"],
                self.active_playoff_series[1]["winner_nome"],
                self.active_playoff_series[2]["winner_nome"],
                self.active_playoff_series[3]["winner_nome"]
            ]
            self.next_round_teams['east'] = [next(s for s in self.squadre if s.nome == name) for name in east_winners]
            
            west_winners = [
                self.active_playoff_series[4]["winner_nome"],
                self.active_playoff_series[5]["winner_nome"],
                self.active_playoff_series[6]["winner_nome"],
                self.active_playoff_series[7]["winner_nome"]
            ]
            self.next_round_teams['west'] = [next(s for s in self.squadre if s.nome == name) for name in west_winners]
            
            self.playoff_state = "SF"
            self.active_playoff_series = []
            
        elif self.playoff_state == "SF":
            east_winners = [
                self.active_playoff_series[0]["winner_nome"],
                self.active_playoff_series[1]["winner_nome"]
            ]
            self.next_round_teams['east'] = [next(s for s in self.squadre if s.nome == name) for name in east_winners]
            
            west_winners = [
                self.active_playoff_series[2]["winner_nome"],
                self.active_playoff_series[3]["winner_nome"]
            ]
            self.next_round_teams['west'] = [next(s for s in self.squadre if s.nome == name) for name in west_winners]
            
            self.playoff_state = "CF"
            self.active_playoff_series = []
            
        elif self.playoff_state == "CF":
            east_winner = self.active_playoff_series[0]["winner_nome"]
            west_winner = self.active_playoff_series[1]["winner_nome"]
            
            self.next_round_teams['east'] = [next(s for s in self.squadre if s.nome == name) for name in [east_winner]]
            self.next_round_teams['west'] = [next(s for s in self.squadre if s.nome == name) for name in [west_winner]]
            
            self.playoff_state = "FINALS"
            self.active_playoff_series = []
            
        elif self.playoff_state == "FINALS":
            winner_name = self.active_playoff_series[0]["winner_nome"]
            s1_name = self.active_playoff_series[0]["s1"].nome
            self.campione = next(s for s in self.squadre if s.nome == winner_name)
            finalista = self.active_playoff_series[0]["s2"] if winner_name == s1_name else self.active_playoff_series[0]["s1"]
            
            self._calcola_mvp_finali(self.campione, finalista)
            self.playoff_state = "COMPLETE"
            self.active_playoff_series = []
            self.podcast_logger.log_playoff_bracket(self.playoff_bracket_data)

    def simula_turno_playoff(self) -> str:
        """Simulates a whole playoff round, game by game until completion."""
        if self.playoff_state == "NOT_STARTED":
            self._setup_playoffs()
        
        if self.playoff_state == "PLAY_IN":
            self._simula_play_in()
            return self.playoff_state
        
        if self.playoff_state in ["QF", "SF", "CF", "FINALS"]:
            self.setup_current_playoff_round()
            while self.active_playoff_series and any(s["winner_nome"] is None for s in self.active_playoff_series):
                self.simula_gara_playoff()
                
        return self.playoff_state

    def start_offseason_progression(self, user_decisions=None) -> Tuple[List[Giocatore], Dict[str, Squadra]]:
        """
        ### REWORKED (Bugfix: FA Pool Duplication) ###
        Step 1 of the Offseason. Handles the update of the careers, the progression,
        and the retirements.
        CRUCIAL: It no longer modifies the global FA state, but RETURNS the list
        of the new free agents and the map of the previous teams for the next phase.
        """
        print("=== DEBUG: start_offseason_progression CHIAMATA! ===", flush=True)
        self.fase_torneo = "OFFSEASON"
        main_log.info(f"\n\n{'='*25} OFF-SEASON START (pre-Season {self.season_number + 1}) {'='*25}")
        mark_season_end(self, ensure_front_office(self))
        # Trade requests: the summer check, while playoff_teams still holds the season just played (once a season)
        if trade_requests.summer_due(self):
            trade_requests.end_of_season(self)

        # Reset trade cooldowns for all players at the start of the offseason
        for squadra in self.squadre:
            for p in squadra.roster:
                p.giorni_cooldown_scambio = 0

        # --- PREPARATION (Unchanged) ---
        print("=== DEBUG: Calling db_manager.save_season_data... ===", flush=True)
        db_manager.save_season_data(self)
        print("=== DEBUG: Chiamando update_league_history... ===", flush=True)
        update_league_history(self)
        print("=== DEBUG: Chiamando update_player_careers... ===", flush=True)
        update_player_careers(self)
        print("=== DEBUG: update_player_careers completata! ===", flush=True)
        kept = {key: (self.offseason_log_data or {}).get(key) for key in ('roster_before', 'league_before')}
        self.offseason_log_data = {'ritiri_sviluppo': [], 'scambi': [], 'draft': [], 'free_agency': [], 'development': [], 'retirements': []}
        # Snapshots taken by start_offseason for the hub's New season summary
        self.offseason_log_data.update({key: value for key, value in kept.items() if value})
        self._aggiorna_fvs_fine_stagione()

        # --- PLAYER PROGRESSION AND RETIREMENT LOGIC (Refactored) ---
        main_log.info("\n--- Player Development and Retirements Phase ---")
        
        # Temporary lists for this process
        all_logs = []
        new_free_agents = []
        previous_teams_map = {}
        
        # Load the persistent set of retired IDs
        retired_ids_file = get_historical_file_path("retired_players_ids.json")
        retired_player_ids = set()
        if os.path.exists(retired_ids_file):
            try:
                with open(retired_ids_file, 'r', encoding='utf-8') as f:
                    retired_player_ids = set(json.load(f))
            except Exception:
                retired_player_ids = set()
        
        # 0. RESOLVE CONTRACT OPTIONS (PO/TO) - BEFORE decrementing contracts
        self._resolve_contract_options(user_decisions=user_decisions)
        
        # 1. Process all the players on the rosters
        for squadra in self.squadre:
            roster_sopravvissuti = []
            for player in squadra.roster:
                # Increment the years with the team (crucial for RFA vs UFA logic)
                player.anni_nella_squadra = getattr(player, 'anni_nella_squadra', 0) + 1
                if player.decide_ritiro():
                    log_msg = f"RETIREMENT: {player.nome} ({player.eta} years old, {player.ovr} OVR) retires from {squadra.nome}."
                    all_logs.append(log_msg); main_log.info(log_msg)
                    self.offseason_log_data['retirements'].append({"name": player.nome, "team": squadra.nome, "age": player.eta, "ovr": player.ovr})
                    add_retired_player(self, player)
                    retired_player_ids.add(player.nome.replace(" ", "-").lower())
                    self.podcast_logger.log_retirement({
                        "name": player.nome, "team": squadra.nome, "age": player.eta, "ovr": player.ovr
                    })
                    continue # Move on to the next player, he is not added to the survivors

                # Progressione
                cambiamenti = player.gestisci_progressione_offseason()
                if cambiamenti.get('valutazione', 0) != 0:
                    valutazione_cambio = cambiamenti.get('valutazione', 0)
                    val_prec = player.ovr - valutazione_cambio
                    segno = '+' if valutazione_cambio > 0 else ''
                    gp_count = getattr(player.season_stats, 'partite_giocate', 0)
                    pvs_val = getattr(player.performance_scores, 'total', player.ovr)
                    log_msg = f"PROG: {player.nome} ({player.eta} years old, {gp_count} GP) OVR: {val_prec} -> {player.ovr} ({segno}{valutazione_cambio}) [Pot: {player.potenziale}, PVS: {pvs_val:.1f}]."
                    all_logs.append(log_msg)
                    self.offseason_log_data['development'].append({"name": player.nome, "team": squadra.nome, "age": player.eta, "position": player.ruolo, "ovr_before": val_prec, "ovr_after": player.ovr})
                
                # Check whether the contract expired AFTER the progression
                if player.contract and player.contract.anni_rimanenti <= 0:
                    main_log.info(f"Contract expired: {player.nome} leaves the {squadra.nome} for Free Agency.")
                    previous_teams_map[player.nome] = squadra
                    player.squadra = None
                    new_free_agents.append(player)
                else:
                    roster_sopravvissuti.append(player)
            
            # Update the team roster with only the survivors who are still under contract
            squadra.roster = roster_sopravvissuti

        # 2. Process the free agents from the previous season
        for player in self.free_agents_pool:
            if player.decide_ritiro():
                log_msg = f"RETIREMENT (FA): {player.nome} ({player.eta} years old, {player.ovr} OVR) retires from Free Agency."
                all_logs.append(log_msg); main_log.info(log_msg)
                self.offseason_log_data['retirements'].append({"name": player.nome, "team": "Free Agency", "age": player.eta, "ovr": player.ovr})
                add_retired_player(self, player)
                retired_player_ids.add(player.nome.replace(" ", "-").lower())
                self.podcast_logger.log_retirement({
                    "name": player.nome, "team": "Free Agency", "age": player.eta, "ovr": player.ovr
                })
                continue
            
            player.gestisci_progressione_offseason() # FAs also age and develop
            new_free_agents.append(player) # Add them to the FA pool for the new season

        # Save the updated persistent list of retired IDs
        try:
            with open(retired_ids_file, 'w', encoding='utf-8') as f:
                json.dump(list(retired_player_ids), f, indent=2)
        except Exception as e:
            main_log.error(f"Error saving {retired_ids_file}: {e}")

        # 3. Clean the old FA pool and prepare the return data
        self.free_agents_pool = [] # We empty the pool. It will be repopulated at the end of FA.
        self.offseason_log_data['ritiri_sviluppo'] = sorted(list(set(all_logs)))
        
        # 4. Return the results for the Free Agency phase
        return new_free_agents, previous_teams_map
    

    def _gestisci_progressione_e_ritiri(self):
        """
        ### REWORKED (v7.2 - FIXED) ###
        Handles the development, the retirements and the RFA renewal window.
        Now uses the unique decision brain correctly, computing
        the team's status at the moment of the decision.
        """
        main_log.info("\n--- Player Development and Retirements Phase ---")
        
        all_logs = self.offseason_log_data.get('ritiri_sviluppo', [])
        retired_ids_file = get_historical_file_path("retired_players_ids.json")
        
        try:
            with open(retired_ids_file, 'r', encoding='utf-8') as f:
                retired_player_ids = set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            retired_player_ids = set()

        tutti_giocatori_attivi = [p for s in self.squadre for p in s.roster] + self.free_agents_pool
        giocatori_sopravvissuti = []


        for player in tutti_giocatori_attivi:
            # season as a free agent. Let's give him a morale boost.
            if player.squadra is None:
                morale_precedente = player.morale
                player.morale = min(100, player.morale + 50) # Increases by 50, capped at 100
                if player.morale > morale_precedente:
                    log_msg = f"MORALE BOOST (FA): {player.nome} (Morale: {morale_precedente} -> {player.morale}) is more motivated to return to the team."
                    all_logs.append(log_msg)
            # ### END OF NEW LOGIC ###
            if player.decide_ritiro():
                squadra_nome = player.squadra.nome if player.squadra else "Free Agency"
                log_msg = f"RETIREMENT: {player.nome} ({player.eta} years old, {player.ovr} OVR) retires from {squadra_nome}."
                all_logs.append(log_msg)
                main_log.info(log_msg)
                add_retired_player(self, player)
                player_id = player.nome.replace(" ", "-").lower()
                retired_player_ids.add(player_id)
                continue
            
            cambiamenti = player.gestisci_progressione_offseason()
            if cambiamenti.get('valutazione', 0) != 0:
                valutazione_precedente = player.ovr - cambiamenti.get('valutazione', 0)
                segno = '+' if cambiamenti.get('valutazione', 0) > 0 else ''
                gp_count = getattr(player.season_stats, 'partite_giocate', 0)
                pvs_val = getattr(player.performance_scores, 'total', player.ovr)
                log_msg = f"PROG: {player.nome} ({player.eta} years old, {gp_count} GP) OVR: {valutazione_precedente} -> {player.ovr} ({segno}{cambiamenti.get('valutazione', 0)}) [Pot: {player.potenziale}, PVS: {pvs_val:.1f}]."
                all_logs.append(log_msg)
            
            giocatori_sopravvissuti.append(player)

        with open(retired_ids_file, 'w', encoding='utf-8') as f:
            json.dump(list(retired_player_ids), f, indent=2)

        self.free_agents_pool = [p for p in giocatori_sopravvissuti if not p.squadra]
        for squadra in self.squadre:
            squadra.roster = [p for p in squadra.roster if p in giocatori_sopravvissuti]

        nuovi_fa_pool = []
        squadre_precedenti_map = {}
        
        for squadra in self.squadre:
            # Find all the players with an expired contract
            giocatori_in_scadenza = [p for p in squadra.roster if p.contract and p.contract.anni_rimanenti <= 0]
            if not giocatori_in_scadenza: continue

            for fa in giocatori_in_scadenza:
                # We map the player to his previous team.
                # This map is crucial for the RFA logic.
                squadre_precedenti_map[fa.nome] = squadra
                
                # We release the player from the current roster.
                nuovi_fa_pool.append(fa)
                squadra.roster.remove(fa)
                fa.squadra = None
                main_log.info(f"Contract expired: {fa.nome} leaves the {squadra.nome} and enters the market.")

        # --- FIX v20.7: Unification of the Free Agent Pools ---
        # The duplication bug happened because a player could end up in both
        # 'nuovi_fa_pool' and 'self.free_agents_pool'. Now we unify everything
        # into a single list, using a set to guarantee the uniqueness of each player object.
        tutti_i_nuovi_fa = self.free_agents_pool + nuovi_fa_pool
        giocatori_unici = list({id(p): p for p in tutti_i_nuovi_fa}.values())

        self.nuovi_free_agents = giocatori_unici # This will be the only source for FA
        self.free_agents_pool = [] # We empty the old pool to avoid duplications
        self.squadre_precedenti_fa = squadre_precedenti_map
        self.offseason_log_data['ritiri_sviluppo'] = sorted(list(set(all_logs)))

    def _aggiorna_carriera_giocatori(self):
        """
        Saves the current season's statistics for all active players to the player_careers.json file.
        """
        update_player_careers(self)

    def eleggi_classe_hof(self):
        msg_header = f"\n🏆 --- HALL OF FAME ELECTIONS - SEASON {self.season_number} ---"
        main_log.info(msg_header)
        print(msg_header, flush=True)

        try:
            career_file = get_historical_file_path("player_careers.json")
            with open(career_file, 'r', encoding='utf-8') as f:
                all_careers = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            msg_err = "⚠️ HOF: player_careers.json file not found or empty. Unable to elect the HOF."
            main_log.warning(msg_err)
            print(msg_err, flush=True)
            return

        retired_player_ids = set()
        retired_ids_file = get_historical_file_path("retired_players_ids.json")
        if os.path.exists(retired_ids_file):
            try:
                with open(retired_ids_file, 'r', encoding='utf-8') as f:
                    retired_player_ids = set(json.load(f))
            except (FileNotFoundError, json.JSONDecodeError):
                retired_player_ids = set()

        # Merge with the retired players present in memory in the tournament
        for p in getattr(self, 'giocatori_ritirati', []):
            retired_player_ids.add(p.nome.replace(" ", "-").lower())

        # Always save the updated list to disk
        if retired_player_ids:
            try:
                with open(retired_ids_file, 'w', encoding='utf-8') as f:
                    json.dump(list(retired_player_ids), f, indent=2)
            except Exception:
                pass
        else:
            msg_no_ret = "ℹ️ HOF: No retired players found in the retired IDs database."
            main_log.info(msg_no_ret)
            print(msg_no_ret, flush=True)
            return

        hof_file = get_historical_file_path("hall_of_fame.json")
        try:
            with open(hof_file, 'r', encoding='utf-8') as f:
                raw_hof_data = json.load(f)
                if isinstance(raw_hof_data, list):
                    hall_of_fame_data = {"classes": raw_hof_data}
                elif isinstance(raw_hof_data, dict):
                    hall_of_fame_data = raw_hof_data
                    if "classes" not in hall_of_fame_data:
                        hall_of_fame_data["classes"] = []
                else:
                    hall_of_fame_data = {"classes": []}
        except (FileNotFoundError, json.JSONDecodeError):
            hall_of_fame_data = {"classes": []}

        gia_eletti_ids = set()
        for hof_class in hall_of_fame_data.get("classes", []):
            if isinstance(hof_class, dict):
                for player in hof_class.get("inductees", []):
                    if isinstance(player, dict) and 'id' in player:
                        gia_eletti_ids.add(player['id'])

        candidati = []
        for player_id in retired_player_ids:
            if player_id in gia_eletti_ids or player_id not in all_careers:
                continue

            player_career = all_careers[player_id]
            if not player_career: continue

            score, highlights = calcola_hof_score(player_career)
            nome_giocatore = player_career[-1].get("nome", player_id.replace("-", " ").title())
            candidati.append({"nome": nome_giocatore, "score": score, "id": player_id, "highlights": highlights})

        if not candidati:
            msg_none = "ℹ️ HOF: No eligible candidates left for the Hall of Fame in this cycle."
            main_log.info(msg_none)
            print(msg_none, flush=True)
            return

        print(f"📊 HOF: Evaluating {len(candidati)} available retired candidates...", flush=True)
            
        # The bar the History page shows (CONFIG.HISTORY.HOF_MIN_SCORE): a weak year elects nobody. The old bar (110,
        # or the best three at 45+) put 74 of 97 inductees under it in a 25-season save.
        hof_cfg = CONFIG.HISTORY
        candidati_idonei = sorted((c for c in candidati if c["score"] >= hof_cfg.HOF_MIN_SCORE),
                                  key=lambda x: x["score"], reverse=True)[:hof_cfg.HOF_MAX_CLASS]

        classe_di_quest_anno = candidati_idonei

        if classe_di_quest_anno:
            print(f"🎉 --- NEW HALL OF FAME CLASS ELECTED (Season {self.season_number}) ---", flush=True)
            main_log.info(f"Hall of Fame Class of Season {self.season_number}:")
            for eletto in classe_di_quest_anno:
                line_msg = f"   🌟 {eletto['nome']} (Score: {eletto['score']})"
                main_log.info(line_msg)
                print(line_msg, flush=True)
            
            hall_of_fame_data["classes"].append({
                "stagione_elezione": self.season_number,
                "inductees": classe_di_quest_anno
            })
            if hasattr(self, 'podcast_logger'):
                self.podcast_logger.log_hof(classe_di_quest_anno)
            with open(hof_file, 'w', encoding='utf-8') as f:
                json.dump(hall_of_fame_data, f, indent=2)
            print(f"✅ HOF: Class successfully elected and saved to hall_of_fame.json!\n", flush=True)
        else:
            msg_empty = "ℹ️ HOF: No player reached the minimum threshold for election in this cycle."
            main_log.info(msg_empty)
            print(msg_empty, flush=True)

    def _taglia_giocatore(self, squadra, giocatore, log_tagli):
        """Cuts one player: off the roster and contract, news for notable names, then retirement for veterans at the
        end of the line (past 34, under 76 OVR) or the free-agent pool."""
        squadra.roster.remove(giocatore)
        log_msg = f"CUT: {squadra.nome} cut {giocatore.nome} ({giocatore.ovr} OVR)."
        log_tagli.append(log_msg)
        main_log.info(log_msg)
        try:
            from core.news_generator import add_news
            if giocatore.ovr >= 74:
                add_news(
                    category="signings",
                    title=f"CUT: {squadra.nome} cut {giocatore.nome}",
                    excerpt=f"The {squadra.nome} decide to cut {giocatore.nome} ({giocatore.ovr} OVR) to get within the roster limits for the new season.",
                    teams=[squadra.nome],
                    season=self.season_number
                )
        except Exception:
            pass
        giocatore.squadra = None
        giocatore.contract = None
        if giocatore.eta > 34 and giocatore.ovr < 76:
            add_retired_player(self, giocatore)
            main_log.info(f"  -> {giocatore.nome} announces his retirement.")
        else:
            self.free_agents_pool.append(giocatore)
            main_log.info(f"  -> {giocatore.nome} enters the free agent market.")

    def release_players(self, squadra, names):
        """The user's own cuts on cut-down day (End of Season Hub), applied before the engine cuts every team.
        Names not on the roster are skipped; returns the players released."""
        log_tagli = []
        released = []
        for name in names:
            giocatore = next((p for p in squadra.roster if p.nome == name), None)
            if giocatore is None:
                continue
            self._taglia_giocatore(squadra, giocatore, log_tagli)
            released.append(giocatore)
        if not isinstance(getattr(self, 'offseason_log_data', None), dict):
            self.offseason_log_data = {}
        self.offseason_log_data.setdefault('tagli_roster', []).extend(log_tagli)
        self.offseason_log_data.setdefault('user_releases', []).extend(p.nome for p in released)
        return released

    def _gestisci_fase_tagli_roster(self):
        """
        ### REWORKED (v19.1 - No More Ghosts) ###
        Players who are cut now correctly enter the free agent pool
        or retire if they are veterans at the end of their careers.
        """
        main_log.info("\n--- FASE DI TAGLI ROSTER (Cut-Down Day) ---")
        from core.roster_cuts import cut_target, pick_cuts
        cfg = CONFIG.OFFSEASON
        roster_limit = cut_target(cfg)
        log_tagli = []

        for squadra in self.squadre:
            for giocatore_da_tagliare in pick_cuts(squadra.roster, roster_limit, cfg):
                self._taglia_giocatore(squadra, giocatore_da_tagliare, log_tagli)

        if 'tagli_roster' not in self.offseason_log_data:
            self.offseason_log_data['tagli_roster'] = []
        self.offseason_log_data['tagli_roster'].extend(log_tagli)

        self._riempi_roster_cpu_post_tagli()

    def _riempi_roster_cpu_post_tagli(self):
        """
        Cut-down day runs AFTER free agency: when the FA pool was already empty (common in the
        first 2002 seasons) CPU teams stayed below the minimum for a whole season while full teams
        had just released players. CPU teams below ROSTER_SIZE_MIN now sign the best available
        free agents (often those just-released players) on 1-year minimum deals.
        """
        min_size = CONFIG.OFFSEASON.ROSTER_SIZE_MIN
        user_team = self.squadra_giocatore if not getattr(self, 'is_spectator', False) else None
        for squadra in sorted(self.squadre, key=lambda s: len(s.roster)):
            if user_team and squadra.nome == user_team.nome:
                continue  # the user manages their own roster
            while len(squadra.roster) < min_size and self.free_agents_pool:
                candidato = max(self.free_agents_pool, key=lambda p: p.ovr)
                self.free_agents_pool.remove(candidato)
                candidato.contract = Contract(anni_rimanenti=1, salario_annuale=self.min_salary)
                candidato.squadra = squadra
                candidato.anni_nella_squadra = 0
                squadra.roster.append(candidato)
                main_log.info(f"POST-CUT SIGNING: {squadra.nome} sign {candidato.nome} ({candidato.ovr} OVR) at the minimum to complete the roster.")

    def _pulizia_post_free_agency(self, unrestricted_free_agents: List[Giocatore]):
        """
        Cleans up the Free Agent pool after the signing phase.
        Old players or 'busts' who found no team retire.
        """
        main_log.info("\n--- Post-Free Agency Cleanup ---")
        new_fa_pool = []
        
        # Filter for forced retirement (Fast)
        for fa in unrestricted_free_agents:
            # Forced retirement conditions (old poor players or young busts)
            # We raised the bar a little to keep too many "useful" veterans from disappearing
            if (fa.eta > 34 and fa.ovr < 78) or fa.is_young_bust():
                log_msg = f"FA RETIREMENT: {fa.nome} ({fa.eta} years old, {fa.ovr} OVR) leaves the league after failing to find a contract."
                if 'ritiri_sviluppo' not in self.offseason_log_data:
                    self.offseason_log_data['ritiri_sviluppo'] = []
                self.offseason_log_data['ritiri_sviluppo'].append(log_msg)
                main_log.info(log_msg)
                
                add_retired_player(self, fa)
                if hasattr(self, 'podcast_logger'):
                    self.podcast_logger.log_retirement({
                        "name": fa.nome, "team": "Free Agency", "age": fa.eta, "ovr": fa.ovr
                    })
                
                # ID PERSISTENCE FOR THE HOF (Crucial for them to appear in the voting)
                try:
                    import json, os
                    filename = get_historical_file_path("retired_players_ids.json")
                    ids = set()
                    if os.path.exists(filename):
                        with open(filename, 'r', encoding='utf-8') as f:
                            ids = set(json.load(f))
                    
                    ids.add(fa.nome.replace(" ", "-").lower())
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(list(ids), f, indent=2)
                except Exception as e:
                    main_log.error(f"Error saving retired ID for HOF: {e}")
            else:
                new_fa_pool.append(fa)
        
        self.free_agents_pool = new_fa_pool
        main_log.info(f"FA pool cleaned: {len(new_fa_pool)} players left available.")


    def _simula_serie(self, s1: 'Squadra', s2: 'Squadra', nome_serie: str, best_of=7, enable_play_log=False):
        main_log.info(f"\n--- Series Start: {nome_serie} ({s1.nome} vs {s2.nome}) ---")
        vittorie_s1, vittorie_s2 = 0, 0
        vittorie_necessarie = (best_of // 2) + 1
        serie_log = {
            "s1_nome": s1.nome, "s1_vittorie": 0,
            "s2_nome": s2.nome, "s2_vittorie": 0,
            "winner_nome": None,
            "games": []
        }
        
        for i in range(1, best_of + 1):
            squadra_casa, squadra_ospite = (s1, s2) if i in [1, 2, 5, 7] else (s2, s1)
            
            # Pass series info to rivalry system
            current_score = (vittorie_s1, vittorie_s2) if squadra_casa == s1 else (vittorie_s2, vittorie_s1)
            vincitore_partita = self._simula_e_registra_partita(squadra_casa, squadra_ospite, True, round_name=nome_serie, series_score=current_score, enable_play_log=enable_play_log)

            if vincitore_partita.nome == s1.nome: vittorie_s1 += 1
            else: vittorie_s2 += 1
            
            serie_log["games"].append(self._registra_gara_playoff(i, squadra_casa, squadra_ospite, nome_serie))
            
            main_log.info(f"Game {i}: {vincitore_partita.nome} wins. Series: {s1.nome} {vittorie_s1} - {vittorie_s2} {s2.nome}")

            if vittorie_s1 == vittorie_necessarie or vittorie_s2 == vittorie_necessarie:
                break
        
        serie_log["s1_vittorie"] = vittorie_s1
        serie_log["s2_vittorie"] = vittorie_s2
        serie_log["winner_nome"] = s1.nome if vittorie_s1 > vittorie_s2 else s2.nome
        
        # Ultra-light version for the early rounds, but detailed for the finals
        if nome_serie in ["CF", "FINALI", "FINALE"]:
            lean_games = serie_log["games"]
        else:
            lean_games = []
            for g in serie_log["games"]:
                lean_games.append({
                    "game_num": g["game_num"],
                    "away": g["squadra_ospite"]["nome"],
                    "home": g["squadra_casa"]["nome"],
                    "away_score": g["squadra_ospite"]["punteggio"],
                    "home_score": g["squadra_casa"]["punteggio"],
                    "buzzer_beater": g["game_winner_info"]
                })
            
        podcast_log = {
            "matchup": f"{s1.nome} vs {s2.nome}",
            "result": f"{vittorie_s1} - {vittorie_s2}",
            "winner": serie_log["winner_nome"],
            "games": lean_games
        }
        self.podcast_logger.log_playoff_series(podcast_log)

        if vittorie_s1 > vittorie_s2:
            return s1, s2, serie_log
        else:
            return s2, s1, serie_log

    def _simula_torneo_conference(self, squadre_conference, nome_conference):
        classifica = sorted(squadre_conference, key=lambda s: s.vittorie, reverse=True)
        if len(classifica) < 8: return None, {}
        playoff_teams = classifica[:8]
        bracket = {'qf': [], 'sf': [], 'cf': []}

        qf1, _, log_qf1 = self._simula_serie(playoff_teams[0], playoff_teams[7], "QF")
        qf2, _, log_qf2 = self._simula_serie(playoff_teams[3], playoff_teams[4], "QF")
        qf3, _, log_qf3 = self._simula_serie(playoff_teams[2], playoff_teams[5], "QF")
        qf4, _, log_qf4 = self._simula_serie(playoff_teams[1], playoff_teams[6], "QF")
        bracket['qf'] = [
            {**log_qf1, "s1_seed": 1, "s2_seed": 8},
            {**log_qf2, "s1_seed": 4, "s2_seed": 5},
            {**log_qf3, "s1_seed": 3, "s2_seed": 6},
            {**log_qf4, "s1_seed": 2, "s2_seed": 7}
        ]
        
        sf1, _, log_sf1 = self._simula_serie(qf1, qf2, "SF")
        sf2, _, log_sf2 = self._simula_serie(qf3, qf4, "SF")
        bracket['sf'] = [log_sf1, log_sf2]

        campione, _, log_cf = self._simula_serie(sf1, sf2, "CF")
        bracket['cf'] = [log_cf]
        
        return campione, bracket

    # Leave here all the rest of your Tournament class (awards calculation, standings, etc.)
    # The awards calculation methods are perfect, we will use them to populate the API data.
    # ... (methods _calcola_e_stampa_premi_stagionali, _calcola_all_nba_teams, etc.)
    # Include all the methods of your Tournament class here.
    @staticmethod
    def _clear_stale_offensive_options(squadra: 'Squadra') -> None:
        """Clears a designated offensive option whose player is no longer on the roster (traded, released, retired)."""
        tp = getattr(squadra, 'tactical_plan', None)
        if not tp:
            return
        on_roster = {p.nome for p in squadra.roster} | {str(getattr(p, 'id', '')) for p in squadra.roster}
        for field in ('offensive_first_option', 'offensive_second_option', 'offensive_third_option'):
            name = getattr(tp, field, None)
            if name and name not in on_roster:
                setattr(tp, field, None)

    def check_and_adjust_user_rotations(self, squadra: 'Squadra') -> bool:
        """
        Handles the rotations and minutes for the team controlled by the user.
        Strictly preserves the user's manual choices:
        - NEVER forces the AI auto-rotation during game simulation.
        - If there are no injuries or absences, applies exactly the minutes configured by the user.
        - If there are injuries, temporarily zeroes only the injured player's minutes and distributes the share among the healthy ones.
        - As soon as the player recovers, his original minutes are restored 100%.
        """
        roster_sano = [p for p in squadra.roster if not p.infortunato and not p.is_resting_today]
        if not roster_sano:
            return False

        # Initialize or validate the backup of the user's custom rotations
        if not getattr(squadra, 'rotazioni_personalizzate_utente', None):
            current_mins = {p.nome: p.minuti_target for p in squadra.roster if p.minuti_target > 0}
            if sum(current_mins.values()) == 240:
                squadra.rotazioni_personalizzate_utente = current_mins
            else:
                self.imposta_rotazioni_stagione_per_squadra(squadra, force_user=True)
                squadra.rotazioni_personalizzate_utente = {p.nome: p.minuti_target for p in squadra.roster}
                return True

        infortunati = [p for p in squadra.roster if p.infortunato or p.is_resting_today]
        infortunati_con_minuti = [p for p in infortunati if squadra.rotazioni_personalizzate_utente.get(p.nome, 0) > 0]

        # Scenario A: No injured players among those the user assigned minutes to -> Exact restoration of the user's plan
        if not infortunati_con_minuti:
            changed = False
            for p in squadra.roster:
                target_backup = squadra.rotazioni_personalizzate_utente.get(p.nome, 0)
                if p.minuti_target != target_backup:
                    p.minuti_target = target_backup
                    changed = True
            return changed

        # Scenario B: There are injuries in the rotation -> Temporary adaptation without overwriting the base plan
        minuti_da_ridistribuire = sum(squadra.rotazioni_personalizzate_utente.get(p.nome, 0) for p in infortunati_con_minuti)
        sani_con_minuti = [p for p in roster_sano if squadra.rotazioni_personalizzate_utente.get(p.nome, 0) > 0]

        if not sani_con_minuti:
            # All the rotation starters are injured, temporarily assign to the healthy ones
            minuti_per_giocatore = 240 // len(roster_sano) if roster_sano else 0
            for p in squadra.roster:
                p.minuti_target = minuti_per_giocatore if p in roster_sano else 0
            return True

        somma_minuti_sani_backup = sum(squadra.rotazioni_personalizzate_utente.get(p.nome, 0) for p in sani_con_minuti)
        minuti_aggiornati = {}
        minuti_assegnati_totali = 0

        for p in squadra.roster:
            if p.infortunato or p.is_resting_today or p not in sani_con_minuti:
                minuti_aggiornati[p.nome] = 0
            else:
                base_min = squadra.rotazioni_personalizzate_utente.get(p.nome, 0)
                quota = base_min / somma_minuti_sani_backup if somma_minuti_sani_backup > 0 else 0
                extra = round(quota * minuti_da_ridistribuire)
                minuti_p = min(44, base_min + extra)
                minuti_aggiornati[p.nome] = minuti_p
                minuti_assegnati_totali += minuti_p

        # Rounding to get exactly 240 minutes
        differenza = 240 - minuti_assegnati_totali
        if differenza != 0 and sani_con_minuti:
            migliore = max(sani_con_minuti, key=lambda p: minuti_aggiornati[p.nome])
            minuti_aggiornati[migliore.nome] = max(10, minuti_aggiornati[migliore.nome] + differenza)

        changed = False
        for p in squadra.roster:
            val_nuovo = minuti_aggiornati.get(p.nome, 0)
            if p.minuti_target != val_nuovo:
                p.minuti_target = val_nuovo
                changed = True

        return changed

    def imposta_rotazioni_stagione(self, force_user=False, squadre=None):
        """### REWORK v17.0: Hierarchical rotation logic. ###
        `squadre`: only these teams (default: the whole league). The team state still compares with the league."""
        gcounter = 0
        #main_log.info("\n--- Setting Team Rotations for the Season ---")
        for squadra in (self.squadre if squadre is None else squadre):
            if squadra == self.squadra_giocatore and not force_user:
                # Check and fix if necessary (e.g. injuries/returns), otherwise skip to preserve the user's choices
                self._clear_stale_offensive_options(squadra)
                self.check_and_adjust_user_rotations(squadra)
                continue

            gcounter = 0
            for g in squadra.roster:
                gcounter +=1
                g.minuti_target = 0 # Reset for everyone

            roster_sano = [p for p in squadra.roster if not p.infortunato and not p.is_resting_today]
            if not roster_sano: continue

            # --- DETECT PLAYOFF CONTEXT FIRST (needed for rotation logic below) ---
            is_playoff_context = self.playoff_state in ["QF", "SF", "CF", "FINALS"]

            # 1. Compute an "Importance Score" for every player.
            # In the PLAYOFFS: ZERO development bonus. The rotation is purely merit-based.
            # In the REGULAR SEASON: We give a BOOST to talented young players if the team is not contending for the title.
            stato_squadra = self._determina_stato_squadra(squadra)
            is_developing = stato_squadra in ["Rebuilding", "Mediocre", "Rising Star"]
            
            valutazioni_rotazione = {}
            for p in roster_sano:
                bonus_sviluppo = 0
                # FIX: In playoff, NO development bonus — only the best players play
                if not is_playoff_context and p.eta <= 23 and p.potenziale > p.ovr:
                    if is_developing:
                        # Rebuilding: plays the youngsters regardless
                        bonus_sviluppo = min(8, (p.potenziale - p.ovr) * 0.4)
                    else:
                        # Contender: little room
                        bonus_sviluppo = min(3, (p.potenziale - p.ovr) * 0.15)
                valutazioni_rotazione[p.nome] = p.ovr + bonus_sviluppo

            # We use a power to create a clear separation. Perceived OVR is used here.
            punteggi_importanza = {p.nome: valutazioni_rotazione[p.nome] ** 3.5 for p in roster_sano}
            
            # 2. Determine the actual rotation (Starters by position + Best bench players)
            posizioni = ['PG', 'SG', 'SF', 'PF', 'C']
            custom_lineup = getattr(squadra, 'user_custom_lineup', None)
            if custom_lineup:
                custom_lineup = normalize_role_keys(custom_lineup)
            titolari = []
            used_ids = set()
            
            # If the user has set a specific lineup, use it
            if custom_lineup:
                for pos in posizioni:
                    pname = custom_lineup.get(pos)
                    cand = next((p for p in roster_sano if p.nome == pname and id(p) not in used_ids), None)
                    if cand:
                        titolari.append(cand)
                        used_ids.add(id(cand))
            
            # For the remaining positions, find the best candidate by role
            for pos in posizioni:
                if len(titolari) < 5 and pos not in [normalize_role(getattr(t, 'ruolo', '')) for t in titolari]:
                    cands = [p for p in roster_sano if id(p) not in used_ids and normalize_role(p.ruolo) == pos]
                    cand = max(cands, key=lambda p: valutazioni_rotazione[p.nome], default=None)
                    if not cand:
                        avail = [p for p in roster_sano if id(p) not in used_ids]
                        if avail:
                            cand = max(avail, key=lambda p: (valutazioni_rotazione[p.nome] - POSITION_COMPATIBILITY_PENALTY.get(p.ruolo, {}).get(pos, 0)))
                    if cand:
                        titolari.append(cand)
                        used_ids.add(id(cand))
            
            # Failsafe in case there are fewer than 5 healthy players
            while len(titolari) < min(5, len(roster_sano)):
                cand = max([p for p in roster_sano if id(p) not in used_ids], key=lambda p: valutazioni_rotazione[p.nome])
                titolari.append(cand)
                used_ids.add(id(cand))
            
            # Determine the rotation size (8 in the playoffs, 9 in the regular season)
            rot_target_size = 9
            if is_playoff_context and squadra.coach:
                stile = squadra.coach.stile_gioco
                rot_target_size = CONFIG.COACHINGSTYLES.PLAYOFF_ROTATION_SIZES.get(stile, 8)
                
            panchina_size = max(0, rot_target_size - len(titolari))
            panchina = sorted([p for p in roster_sano if id(p) not in used_ids], key=lambda p: valutazioni_rotazione[p.nome], reverse=True)[:panchina_size]
            
            rotazione_effettiva = titolari + panchina

            if not rotazione_effettiva: continue

            # 3. Distribute the total 240 minutes based on the importance "shares"
            year = getattr(self, 'anno_corrente', 2002)
            minutes_cap = next(cap for last, cap in CONFIG.COACHING.MINUTES_CAP_BY_YEAR if year <= last)
            if is_playoff_context:
                minutes_cap += CONFIG.COACHING.PLAYOFF_MINUTES_EXTRA
            somma_punteggi = sum(punteggi_importanza[p.nome] for p in rotazione_effettiva)
            
            if somma_punteggi == 0: continue

            minuti_distribuiti = 0
            for giocatore in rotazione_effettiva:
                quota = punteggi_importanza[giocatore.nome] / somma_punteggi
                minuti_assegnati = round(quota * 240)
                
                # Distinction between Starters (top 5 of the rotation) and Bench
                idx_rot = rotazione_effettiva.index(giocatore)
                is_starter = (idx_rot < 5)
                
                if giocatore.is_star() or is_starter:
                    # The superstars of the 2002-03 era (Iverson, Kobe, Shaq, Duncan, Garnett, Kidd) play 36-39 min
                    if giocatore.ovr >= 90:
                        min_minuti = 36 if not is_playoff_context else 38
                        max_minuti = 39 if not is_playoff_context else 43
                    elif giocatore.ovr >= 84:
                        min_minuti = 33 if not is_playoff_context else 35
                        max_minuti = 36 if not is_playoff_context else 39
                    else:
                        min_minuti = 28 if not is_playoff_context else 30
                        max_minuti = 33 if not is_playoff_context else 36
                else:
                    # Bench: 6th man up to 26 min, others scaled proportionally
                    if idx_rot == 5:
                        min_minuti = 18 if not is_playoff_context else 12
                        max_minuti = 26 if not is_playoff_context else 22
                    elif idx_rot == 6:
                        min_minuti = 12 if not is_playoff_context else 8
                        max_minuti = 18 if not is_playoff_context else 14
                    elif idx_rot == 7:
                        min_minuti = 8 if not is_playoff_context else 4
                        max_minuti = 14 if not is_playoff_context else 10
                    else: # idx_rot == 8
                        min_minuti = 4 if not is_playoff_context else 0
                        max_minuti = 10 if not is_playoff_context else 6
                
                max_minuti = min(max_minuti, minutes_cap)
                min_minuti = min(min_minuti, max_minuti)
                giocatore.minuti_target = max(min_minuti, min(max_minuti, minuti_assegnati))
                minuti_distribuiti += giocatore.minuti_target

            # Exact normalization to 240 minutes per team (avoids over-allocations that choke the stars)
            diff = 240 - sum(g.minuti_target for g in rotazione_effettiva)
            if diff != 0:
                for g in reversed(rotazione_effettiva):
                    if diff == 0: break
                    step = 1 if diff > 0 else -1
                    if (step > 0 and g.minuti_target < minutes_cap) or (step < 0 and g.minuti_target > 4):
                        g.minuti_target += step
                        diff -= step

            # Offensive options. A CPU team picks them again every time (they used to be set once in season 1 and
            # kept the 2002 names for good: retired or traded players, and no later star ever became an option).
            # The user's team keeps its manual choices: only names no longer on the roster are cleared.
            tp = getattr(squadra, 'tactical_plan', None)
            is_user_team = squadra == self.squadra_giocatore
            if tp and not is_user_team:
                tp.offensive_first_option = tp.offensive_second_option = tp.offensive_third_option = None
            elif tp:
                self._clear_stale_offensive_options(squadra)
            if tp and not tp.offensive_first_option:
                titolari = rotazione_effettiva[:5]
                if titolari:
                    def score_opzione(p):
                        touch = getattr(p.temp_tendenze, 'touch_tendency', 50)
                        # Boost for high-potential young players on developing/rebuilding teams
                        pot_boost = max(0, p.potenziale - p.ovr) * 0.45 if (is_developing and p.eta <= 24) else 0
                        return (p.ovr * 0.8) + (touch * 0.3) + pot_boost

                    ordinati_opz = sorted(titolari, key=score_opzione, reverse=True)
                    squadra.tactical_plan.offensive_first_option = ordinati_opz[0].nome
                    if len(ordinati_opz) > 1:
                        squadra.tactical_plan.offensive_second_option = ordinati_opz[1].nome
                    if len(ordinati_opz) > 2:
                        squadra.tactical_plan.offensive_third_option = ordinati_opz[2].nome
            
    def _calcola_e_stampa_premi_stagionali(self):
        self._calcola_mvp_regular_season()
        self._calcola_defensive_player_of_the_year()
        self.sesto_uomo = self._calcola_sesto_uomo()
        self.all_nba_teams = self._calcola_all_nba_teams()
        self.all_defensive_team = self._calcola_all_defensive_team()
        self.all_rookie_team = self._calcola_all_rookie_team()
        self.rookie_of_the_year = self._calcola_rookie_of_the_year()
        self.most_improved_player = self._calcola_most_improved_player()
        fo = ensure_front_office(self)
        self.coach_of_the_year = coach_of_the_year(self, fo)
        self.gm_of_the_year = gm_of_the_year(self, fo)
        record_gm_award(self, fo, self.gm_of_the_year)
        
        self.podcast_logger.log_awards({
            "mvp": self.regular_season_mvp.nome if getattr(self, 'regular_season_mvp', None) else None,
            "dpoy": self.defensive_player_of_the_year.nome if getattr(self, 'defensive_player_of_the_year', None) else None,
            "sixth_man": self.sesto_uomo.nome if getattr(self, 'sesto_uomo', None) else None,
            "all_nba_1st": [p.nome for p in self.all_nba_teams[0]] if len(getattr(self, 'all_nba_teams', [])) > 0 else [],
            "all_nba_2nd": [p.nome for p in self.all_nba_teams[1]] if len(getattr(self, 'all_nba_teams', [])) > 1 else [],
            "all_nba_3rd": [p.nome for p in self.all_nba_teams[2]] if len(getattr(self, 'all_nba_teams', [])) > 2 else [],
            "all_defensive": [p.nome for p in getattr(self, 'all_defensive_team', [])],
            "all_rookie": [p.nome for p in getattr(self, 'all_rookie_team', [])],
            "roy": self.rookie_of_the_year.nome if self.rookie_of_the_year else None,
            "mip": self.most_improved_player.nome if self.most_improved_player else None
        })
    def _calcola_sesto_uomo(self) -> Optional[Giocatore]:
        """
        Calculates the Sixth Man of the Year.
        Eligibility: >50 games played, <25.0 minutes per game.
        Evaluates scoring, playmaking, and efficiency off the bench.
        """
        candidati = []
        for squadra in self.squadre:
            for giocatore in squadra.roster:
                stats = giocatore.season_stats
                if stats.partite_giocate >= 50:
                    minuti_medi = stats.minuti_giocati / stats.partite_giocate
                    if minuti_medi < 25.0:
                        candidati.append(giocatore)
        
        if not candidati:
            return None

        def sesto_uomo_score(g: Giocatore) -> float:
            st = g.season_stats
            pg = st.partite_giocate or 1
            return (st.punti / pg) + ((st.assist / pg) * 1.2) + ((st.rimbalzi / pg) * 0.8) + ((st.steals / pg) * 1.2)

        return max(candidati, key=sesto_uomo_score, default=None)

    def _calcola_all_nba_teams(self) -> List[List[Giocatore]]:
        """
        Positionless All-NBA Teams (1st, 2nd, 3rd) based on MVP composite score.
        """
        tutti_giocatori = [p for s in self.squadre for p in s.roster if p.season_stats.partite_giocate >= 60]
        if not tutti_giocatori:
            return []

        def mvp_score(g: Giocatore) -> float:
            st = g.season_stats
            pg = st.partite_giocate or 1
            ppg = st.punti / pg
            rpg = st.rimbalzi / pg
            apg = st.assist / pg
            spg = st.steals / pg
            bpg = st.blocks / pg
            topg = st.turnover / pg
            tot_g = (g.squadra.vittorie + g.squadra.sconfitte) or 1
            win_pct = g.squadra.vittorie / tot_g
            raw_stat = ppg + (rpg * 1.15) + (apg * 1.35) + (spg * 1.5) + (bpg * 1.5) - (topg * 1.1)
            return raw_stat * (0.8 + win_pct * 0.6)

        classifica_generale = sorted(tutti_giocatori, key=mvp_score, reverse=True)
        
        if len(classifica_generale) < 15:
            main_log.warning("There are not enough eligible players to form 3 All-NBA teams.")
        
        primo_quintetto = classifica_generale[0:5]
        secondo_quintetto = classifica_generale[5:10]
        terzo_quintetto = classifica_generale[10:15]
        
        teams = []
        if primo_quintetto: teams.append(primo_quintetto)
        if secondo_quintetto: teams.append(secondo_quintetto)
        if terzo_quintetto: teams.append(terzo_quintetto)
        
        return teams

    def _calcola_all_defensive_team(self) -> List[Giocatore]:
        tutti_giocatori = [p for s in self.squadre for p in s.roster if p.season_stats.partite_giocate >= 60]
        if not tutti_giocatori:
            return []

        def def_metric(g: Giocatore) -> float:
            st = g.season_stats
            pg = st.partite_giocate or 1
            spg = st.steals / pg
            bpg = st.blocks / pg
            drpg = (st.rimbalzi * 0.7) / pg
            def_iq = getattr(g.abilita, 'defensive_iq_rating', 70)
            int_def = getattr(g.abilita, 'interior_defense_rating', 70)
            per_def = getattr(g.abilita, 'perimeter_defense_rating', 70)
            rating_bonus = (def_iq * 0.05) + (max(int_def, per_def) * 0.05)
            tot_g = (g.squadra.vittorie + g.squadra.sconfitte) or 1
            win_pct = g.squadra.vittorie / tot_g
            return ((spg * 2.2) + (bpg * 2.5) + (drpg * 0.5) + rating_bonus) * (0.85 + win_pct * 0.3)

        guards = sorted([p for p in tutti_giocatori if p.ruolo in ['PG', 'SG']], key=def_metric, reverse=True)
        forwards = sorted([p for p in tutti_giocatori if p.ruolo in ['SF', 'PF']], key=def_metric, reverse=True)
        centers = sorted([p for p in tutti_giocatori if p.ruolo == 'C'], key=def_metric, reverse=True)
        
        team = []
        if len(guards) >= 2: team.extend(guards[:2])
        if len(forwards) >= 2: team.extend(forwards[:2])
        if len(centers) >= 1: team.extend(centers[:1])
        if len(team) < 5:
            remaining = [p for p in tutti_giocatori if p not in team]
            team.extend(sorted(remaining, key=def_metric, reverse=True)[:5 - len(team)])
        return team

    def _calcola_stat_score_rookie(self, p: Giocatore) -> float:
        """
        Pure Box-Score Efficiency metric for Rookies (zero win percentage bias).
        Evaluates PTS, REB, AST, STL, BLK, TO, and FG/FT misses.
        """
        st = p.season_stats
        pg = st.partite_giocate or 1
        ppg = st.punti / pg
        rpg = st.rimbalzi / pg
        apg = st.assist / pg
        spg = st.steals / pg
        bpg = st.blocks / pg
        topg = st.turnover / pg
        
        fg_att = st.tiri_tentati_2 + st.tiri_tentati_3
        fg_made = st.tiri_fatti_2 + st.tiri_fatti_3
        fg_missed = (fg_att - fg_made) / pg
        ft_missed = (st.tiri_liberi_tentati - st.punti_liberi) / pg
        
        return ppg + (rpg * 1.2) + (apg * 1.4) + (spg * 1.6) + (bpg * 1.6) - (topg * 1.2) - (fg_missed * 0.4) - (ft_missed * 0.4)

    def _calcola_all_rookie_team(self) -> List[Giocatore]:
        """Selects the 5 best rookies based solely on pure individual statistics."""
        rookies = [p for s in self.squadre for p in s.roster if getattr(p, 'is_rookie', False) and p.season_stats.partite_giocate >= 40]
        return sorted(rookies, key=self._calcola_stat_score_rookie, reverse=True)[:5]

    def _calcola_rookie_of_the_year(self) -> Optional[Giocatore]:
        """Selects the Rookie of the Year based solely on pure individual statistics (zero team-win weight)."""
        rookies = [p for s in self.squadre for p in s.roster if getattr(p, 'is_rookie', False) and p.season_stats.partite_giocate >= 40]
        if not rookies:
            return None
        return max(rookies, key=self._calcola_stat_score_rookie, default=None)
    
    # ==========================================
    # ### ALL-STAR WEEKEND METHODS ###
    # ==========================================
    
    @staticmethod
    def _all_star_score(p):
        """All-Star ranking: PPG + RPG + APG weighted."""
        pg = p.season_stats.partite_giocate or 1
        ppg = p.season_stats.punti / pg
        rpg = p.season_stats.rimbalzi / pg
        apg = p.season_stats.assist / pg
        return ppg * 1.0 + rpg * 0.5 + apg * 0.7

    def _all_star_eligible(self, conf):
        """Conference players with at least 20 games (everyone when fewer than 12 qualify)."""
        conf_teams = self.squadre_est if conf == 'east' else self.squadre_ovest
        players = [p for s in conf_teams for p in s.roster
                   if p.season_stats.partite_giocate >= 20]
        if len(players) < 12:
            players = [p for s in conf_teams for p in s.roster]
        return players

    def reset_all_star_weekend(self):
        """Clears this season's All-Star Weekend; keeps the host history and last season's rookies."""
        self.all_star_rosters = {'east': [], 'west': []}  # 12 players per conf
        self.all_star_starters = {'east': [], 'west': []}  # 5 starters per conf
        self.all_star_reserves = {'east': [], 'west': []}  # 7 reserves per conf
        self.all_star_game_log = None
        self.all_star_mvp = None
        self.three_point_contest = {'participants': [], 'results': [], 'winner': None}
        self.dunk_contest = {'participants': [], 'results': [], 'winner': None}
        self.all_star_weekend = None
        self.all_star_weekend_complete = False

    def _remember_rookies(self):
        """Keeps this season's rookies' names (next season's sophomores) before is_rookie is reset."""
        players = [p for s in self.squadre for p in s.roster] + list(getattr(self, 'free_agents_pool', []) or [])
        self.last_season_rookies = [p.nome for p in players if getattr(p, 'is_rookie', False)]

    def _all_star_host_cities(self):
        """Cities of the league's current teams, deduplicated; teams with no known city are skipped."""
        cities = []
        for s in self.squadre:
            city = getattr(s, 'city', None)
            if city not in CONFIG.GEO.CITIES:
                city = get_active_registry().geo_city(s.nome, None)
            if city and city not in cities:
                cities.append(city)
        return cities

    def _all_star_selections(self):
        """Starters, reserves and the best left out of each conference, as player lines."""
        selections = {}
        for conf in ('east', 'west'):
            picked = {id(p) for p in self.all_star_rosters.get(conf, [])}
            left_out = sorted((p for p in self._all_star_eligible(conf) if id(p) not in picked),
                              key=self._all_star_score, reverse=True)[:CONFIG.ALL_STAR.LEFT_OUT_SHOWN]
            selections[conf] = {
                'starters': [player_line(p) for p in self.all_star_starters.get(conf, [])],
                'reserves': [player_line(p) for p in self.all_star_reserves.get(conf, [])],
                'left_out': [player_line(p) for p in left_out],
            }
        return selections

    def _all_star_rising_stars(self):
        """Rookies (best by PPG) and sophomores for the Rising Stars game, as player lines."""
        cfg = CONFIG.ALL_STAR
        lines = [(p.is_rookie, player_line(p)) for s in self.squadre for p in s.roster]
        rookies = sorted((x for is_rookie, x in lines if is_rookie), key=lambda x: -x['ppg'])
        others = [x for is_rookie, x in lines if not is_rookie]
        sophomores = pick_sophomores(others, getattr(self, 'last_season_rookies', None) or [],
                                     cfg.ROOKIE_CHALLENGE_SIZE, cfg.SOPHOMORE_FALLBACK_AGE)
        return rookies[:cfg.ROOKIE_CHALLENGE_SIZE], sophomores

    def run_all_star_weekend(self, rng=random):
        """Plays the whole All-Star Weekend once and returns its snapshot (the stored one when already played)."""
        if getattr(self, 'all_star_weekend_complete', False):
            return getattr(self, 'all_star_weekend', None)

        # Fresh selection from the stats at the break.
        self.reset_all_star_weekend()
        self._select_all_stars()
        self._select_3pt_contest_participants()
        self._select_dunk_contest_participants()

        rookies, sophomores = self._all_star_rising_stars()
        hosts = getattr(self, 'all_star_hosts', None)
        if hosts is None:
            hosts = self.all_star_hosts = []
        cities = self._all_star_host_cities()
        no_repeat = CONFIG.ALL_STAR.HOST_NO_REPEAT
        host = pick_host(cities, hosts[-no_repeat:] if no_repeat else [], rng) if cities else None

        snap = play_weekend(
            season=getattr(self, 'season_number', 1), host=host,
            selections=self._all_star_selections(),
            shooters=[player_line(p) for p in self.three_point_contest['participants']],
            dunkers=[player_line(p) for p in self.dunk_contest['participants']],
            rookies=rookies, sophomores=sophomores, rng=rng)

        self.all_star_weekend = snap
        if host:
            hosts.append(host)
        game = snap['game']
        self.all_star_game_log = game
        self.all_star_mvp = game['mvp']['name'] if game else None
        self.three_point_contest['winner'] = snap['three_point']['winner']
        self.dunk_contest['winner'] = snap['dunk']['winner']
        self.all_star_weekend_complete = True

        if game:
            main_log.info(f"⭐ ALL-STAR GAME ({host}): {game['sides'][0]['label']} {game['sides'][0]['score']} - "
                          f"{game['sides'][1]['score']} {game['sides'][1]['label']}, MVP {self.all_star_mvp}")
        self.podcast_logger.log_all_star({
            "east_roster": [p.nome for p in self.all_star_rosters.get('east', [])],
            "west_roster": [p.nome for p in self.all_star_rosters.get('west', [])],
            "mvp": self.all_star_mvp,
            "three_pt_winner": self.three_point_contest.get('winner'),
            "dunk_winner": self.dunk_contest.get('winner'),
            "game_score": {s['label'].lower(): s['score'] for s in game['sides']} if game else None
        })
        return snap

    def _select_all_stars(self):
        """
        Select All-Star players for both conferences.
        Starters: 2 guards + 3 frontcourt (by fan voting = stats)
        Reserves: 7 best remaining players (coach selection = stats)
        """
        # Guard: Prevent duplicate selection only if complete
        if (self.all_star_starters.get('east') and len(self.all_star_starters['east']) >= 5 and
            self.all_star_starters.get('west') and len(self.all_star_starters['west']) >= 5):
            main_log.info("All-Stars already selected, skipping...")
            return
        
        main_log.info("\n" + "=" * 60)
        main_log.info("ALL-STAR SELECTION")
        main_log.info("=" * 60)
        
        for conf in ['east', 'west']:
            conf_name = "Eastern" if conf == 'east' else "Western"
            players = self._all_star_eligible(conf)
            all_star_score = self._all_star_score

            guards = sorted([p for p in players if p.ruolo in ['PG', 'SG']], 
                          key=all_star_score, reverse=True)
            frontcourt = sorted([p for p in players if p.ruolo in ['SF', 'PF', 'C']], 
                              key=all_star_score, reverse=True)
            
            # Starters: 2 guards + 3 frontcourt
            starters = guards[:2] + frontcourt[:3]
            if len(starters) < 5:
                starter_ids = {id(p) for p in starters}
                rem = [p for p in sorted(players, key=all_star_score, reverse=True) if id(p) not in starter_ids]
                starters.extend(rem[:5 - len(starters)])

            self.all_star_starters[conf] = starters
            
            # Reserves: Next 7 best overall (excluding starters)
            starter_ids = {id(p) for p in starters}
            remaining = [p for p in players if id(p) not in starter_ids]
            reserves = sorted(remaining, key=all_star_score, reverse=True)[:7]
            self.all_star_reserves[conf] = reserves
            
            # Full roster
            self.all_star_rosters[conf] = starters + reserves
            
            main_log.info(f"\n{conf_name} Conference All-Stars:")
            main_log.info("  STARTERS:")
            for p in starters:
                pg = p.season_stats.partite_giocate or 1
                ppg = p.season_stats.punti / pg
                team_nome = p.squadra.nome if p.squadra else "FA"
                main_log.info(f"    ⭐ {p.nome} ({team_nome}) - {ppg:.1f} PPG")
            main_log.info("  RESERVES:")
            for p in reserves:
                pg = p.season_stats.partite_giocate or 1
                ppg = p.season_stats.punti / pg
                team_nome = p.squadra.nome if p.squadra else "FA"
                main_log.info(f"    {p.nome} ({team_nome}) - {ppg:.1f} PPG")
    
    def _select_3pt_contest_participants(self):
        """Select 8 best 3-point shooters for the contest."""
        # Guard: Prevent duplicate selection
        if self.three_point_contest.get('participants') and len(self.three_point_contest['participants']) >= 8:
            main_log.info("3-Point Contest participants already selected, skipping...")
            return
        
        all_players = [p for s in self.squadre for p in s.roster 
                      if p.season_stats.tiri_tentati_3 >= 100]
        if len(all_players) < 8:
            all_players = [p for s in self.squadre for p in s.roster 
                          if p.season_stats.tiri_tentati_3 >= 20]
        if len(all_players) < 8:
            all_players = [p for s in self.squadre for p in s.roster]
        
        # Sort by 3P% with volume consideration
        def three_pt_score(p):
            pct = (p.season_stats.tiri_fatti_3 / p.season_stats.tiri_tentati_3 * 100) if p.season_stats.tiri_tentati_3 > 0 else 0
            volume_bonus = min(p.season_stats.tiri_fatti_3 / 50, 1.0)  # Bonus for volume
            base_skill = getattr(p.abilita, 'three_point_shot_rating', 50) * 0.3
            return pct * (1 + volume_bonus * 0.2) + base_skill
        
        sorted_shooters = sorted(all_players, key=three_pt_score, reverse=True)
        self.three_point_contest['participants'] = sorted_shooters[:8]
        
        main_log.info("\n3-POINT CONTEST PARTICIPANTS:")
        for p in self.three_point_contest['participants']:
            pct = (p.season_stats.tiri_fatti_3 / p.season_stats.tiri_tentati_3 * 100) if p.season_stats.tiri_tentati_3 > 0 else 0
            team_nome = p.squadra.nome if p.squadra else "FA"
            main_log.info(f"  🎯 {p.nome} ({team_nome}) - {pct:.1f}% 3P")
    
    def _select_dunk_contest_participants(self):
        """Select 4 players for Slam Dunk Contest (athletic wings/guards)."""
        # Guard: Prevent duplicate selection
        if self.dunk_contest.get('participants') and len(self.dunk_contest['participants']) >= 4:
            main_log.info("Dunk Contest participants already selected, skipping...")
            return
        
        all_players = [p for s in self.squadre for p in s.roster 
                      if p.eta <= 27 and p.ruolo in ['PG', 'SG', 'SF', 'PF']]
        
        if len(all_players) < 4:
            all_players = [p for s in self.squadre for p in s.roster 
                          if p.ruolo in ['PG', 'SG', 'SF', 'PF']]
        if len(all_players) < 4:
            all_players = [p for s in self.squadre for p in s.roster]
        
        # Sort by athleticism (speed + vertical + dunk_rating)
        def dunk_score(p):
            dunk_rtg = getattr(p.abilita, 'dunk_rating', 50)
            athleticism = (p.abilita.speed + p.abilita.vertical + p.abilita.acceleration) / 3
            return (athleticism * 0.6) + (dunk_rtg * 0.4) + random.randint(0, 15)
        
        sorted_dunkers = sorted(all_players, key=dunk_score, reverse=True)
        self.dunk_contest['participants'] = sorted_dunkers[:4]
        
        main_log.info("\nSLAM DUNK CONTEST PARTICIPANTS:")
        for p in self.dunk_contest['participants']:
            team_nome = p.squadra.nome if p.squadra else "FA"
            main_log.info(f"  🔥 {p.nome} ({team_nome})")
    

    @staticmethod
    def get_playoff_teams(squadre: List[Squadra]) -> List[Squadra]:
        squadre_est = [s for s in squadre if s.conference == 'East']; squadre_ovest = [s for s in squadre if s.conference == 'West']
        classifica_est = sorted(squadre_est, key=lambda s: s.vittorie, reverse=True); classifica_ovest = sorted(squadre_ovest, key=lambda s: s.vittorie, reverse=True)
        return classifica_est[:8] + classifica_ovest[:8]
    def imposta_rotazioni_stagione_per_squadra(self, squadra_singola: 'Squadra', force_user=False):
        """
        ### REWORKED (v20.6) ###
        Sets the base target minutes for a SINGLE team.
        It used to swap self.squadre for [squadra_singola]: the team state then compared the team with itself, so
        Contender, Rebuilding and Mediocre never came up in season (and young players lost their minutes boost).
        """
        self.imposta_rotazioni_stagione(force_user=force_user, squadre=[squadra_singola])
    def _simula_e_registra_partita(self, s1: Squadra, s2: Squadra, is_playoff: bool = False, giorni_di_riposo: int = 1, round_name: str = "Regular Season", series_score: Optional[Tuple[int, int]] = None, enable_play_log: bool = False, giorni_di_riposo_s1: Optional[int] = None, giorni_di_riposo_s2: Optional[int] = None) -> Squadra:
        """
        UPDATED VERSION: Integrates the Seasonal Stamina logic before and after the game.
        """
        
        # ==============================================================================
        # ### PRE-GAME BLOCK: LOAD MANAGEMENT AND MINUTES REDUCTION ###
        # This logic runs BEFORE the Game object is created.
        # ==============================================================================

        # Determine injury and resting status FIRST so that prepara_partita knows who is active
        for squadra in [s1, s2]:
            for giocatore in squadra.roster:
                giocatore.is_resting_today = False # Reset the rest flag
                if getattr(giocatore, 'giorni_infortunio_rimanenti', 0) > 0:
                    if is_playoff:   # no calendar days in the playoffs: a game is DAYS_PER_GAME days (simula_giornata
                        # takes one day a day in the regular season)
                        giocatore.giorni_infortunio_rimanenti = max(
                            0, giocatore.giorni_infortunio_rimanenti - round(CONFIG.INJURIES.DAYS_PER_GAME))
                    if giocatore.giorni_infortunio_rimanenti <= 0:
                        giocatore.giorni_infortunio_rimanenti = 0
                        giocatore.infortunato = False
                        giocatore.infortunio_nome = None
                        giocatore.is_day_to_day = False
                        giocatore.infortunio_impatto = 0.0
                    else:
                        # If it is a Day-to-Day ache, we evaluate whether he takes the court with a penalty or rests
                        if getattr(giocatore, 'is_day_to_day', False):
                            play_chance = 75.0 if is_playoff else 35.0
                            if random.uniform(0, 100) < play_chance:
                                giocatore.infortunato = False # Plays through the ache
                                giocatore.infortunio_impatto = 0.07 # 7% malus
                            else:
                                giocatore.infortunato = True # Rests as a precaution
                                giocatore.infortunio_impatto = 0.0
                        else:
                            giocatore.infortunato = True
                            giocatore.infortunio_impatto = 0.0
                else:
                    giocatore.infortunato = False
                    giocatore.infortunio_nome = None
                    giocatore.is_day_to_day = False
                    giocatore.infortunio_impatto = 0.0

                if not giocatore.infortunato and not is_playoff:
                    # Raised the fatigue threshold from 45.0 to 70.0/75.0 to make fatigue influential
                    soglia_LM = 75.0 if giocatore.ovr > 85 else (70.0 if giocatore.ovr > 78 else 45.0)
                    if giocatore.stamina_stagionale < soglia_LM:
                        # Rebalanced the rest probability to avoid them missing too many or too few games.
                        # With a moderate probability (20% for superstars, 15% for minor stars, 5% for others),
                        # players will rest only sporadically when fatigued.
                        prob_riposo = 20.0 if giocatore.ovr > 85 else (15.0 if giocatore.ovr > 78 else 5.0)
                        if random.uniform(0, 100) < prob_riposo * self._load_management_factor():
                            giocatore.is_resting_today = True
                            # main_log.info(f"LOAD MANAGEMENT: {giocatore.nome} ({squadra.nome}) rests to recover energy.")
                    
                    # Strategic rest against weak opponents (Opponent-based Load Management)
                    elif giocatore.ovr > 85 and giocatore.stamina_stagionale < 85.0:
                        total_games = squadra.vittorie + squadra.sconfitte
                        if total_games >= 15:
                            squadra_avversaria = s2 if squadra == s1 else s1
                            win_pct_att = squadra.vittorie / total_games
                            win_pct_opp = (squadra_avversaria.vittorie / (squadra_avversaria.vittorie + squadra_avversaria.sconfitte)) if (squadra_avversaria.vittorie + squadra_avversaria.sconfitte) > 0 else 0.5
                            
                            # If we are a strong team (>60% W) and play against a weak one (<35% W)
                            if win_pct_att > 0.60 and win_pct_opp < 0.35:
                                # 25% chance of resting the star against a poor team (in today's league)
                                if random.uniform(0, 100) < 25.0 * self._load_management_factor():
                                    giocatore.is_resting_today = True

        # --- FIX v20.5: Centralized and corrected pre-game reset logic ---
        s1.prepara_partita()
        s2.prepara_partita()
        # --- FINE FIX ---

        # 3. Seasonal wear fatigue logic (affects starting energy without corrupting the minuti_target)
        for squadra in [s1, s2]:
            for giocatore in squadra.roster:
                if not giocatore.infortunato and not giocatore.is_resting_today:
                    if giocatore.stamina_stagionale < 70.0:
                        giocatore.energia = max(50, int(giocatore.stamina_stagionale))

        # RIVALRY CHECK & INTENSITY BOOST
        rivalry = self.rivalry_tracker.get_rivalry(s1.nome, s2.nome)
        intensity = rivalry.intensity if rivalry else 10.0 # Base for all games
        
        if intensity >= 50:
            main_log.info(f"🔥 RIVALRY MATCH: Intensity is high ({intensity:.1f}%) between {s1.nome} and {s2.nome}!")

        # Ensure strict synchronization of roster player team pointers
        for p in s1.roster:
            p.squadra = s1
        for p in s2.roster:
            p.squadra = s2

        # Now that the minutes and the rest status are set, we can create and play the game.
        partita = Partita(s1, s2, is_playoff, rivalry_intensity=intensity, enable_play_log=enable_play_log)
        s1.partita = partita
        s2.partita = partita
        
        punteggio1, punteggio2 = partita.gioca()
        
        if not is_playoff:   # season points are read per regular-season game (W + L); playoff points inflated PPG
            s1.punti_fatti_stagione += punteggio1
            s1.punti_subiti_stagione += punteggio2
            s2.punti_fatti_stagione += punteggio2
            s2.punti_subiti_stagione += punteggio1
        
        vincitore = s1 if punteggio1 > punteggio2 else s2
        perdente = s2 if punteggio1 > punteggio2 else s1
        
        if not is_playoff:
            vincitore.vittorie += 1
            perdente.sconfitte += 1
            
        # --- COACH XP PROGRESSION ---
        xp_gain = 25 if is_playoff else 10
        
        if vincitore.coach:
            vc = vincitore.coach
            vc.xp = getattr(vc, 'xp', 0) + xp_gain
            # historical_wins / historical_losses are counted once, in Partita.gioca (they were counted twice)
            
            # Check Level Up
            current_level = getattr(vc, 'level', 1)
            xp_needed = current_level * 100
            if vc.xp >= xp_needed:
                vc.xp -= xp_needed
                vc.level = current_level + 1
                vc.badge_points = getattr(vc, 'badge_points', 0) + 1
                # A level brings badge points only: ratings grow once a season (_gestisci_progressione_coach)

                # Auto-upgrade badges for the CPU (for the user the user does it himself)
                is_user_team = getattr(self, 'squadra_giocatore', None) and vincitore.nome == self.squadra_giocatore.nome
                if not is_user_team:
                    badges_list = ["Rookie Developer", "Defense Guru", "Tactician", "Fitness Specialist", "Motivator"]
                    style = getattr(vc, 'stile_gioco', 'Balanced')
                    weights = [20, 20, 20, 20, 20]
                    if "Defense" in style or "Grit" in style:
                        weights = [10, 40, 10, 30, 10]
                    elif "Pace" in style or "Run" in style or "Perimeter" in style:
                        weights = [20, 10, 45, 15, 10]
                    elif "Maestro" in style or "System" in style:
                        weights = [35, 10, 20, 10, 25]
                        
                    chosen_badge = random.choices(badges_list, weights=weights, k=1)[0]
                    if not isinstance(vc.badges, dict):
                        vc.badges = {"Rookie Developer": 0, "Defense Guru": 0, "Tactician": 0, "Fitness Specialist": 0, "Motivator": 0}
                    current_badge_level = vc.badges.get(chosen_badge, 0)
                    if current_badge_level < 3:
                        vc.badges[chosen_badge] = current_badge_level + 1
                        vc.badge_points = max(0, vc.badge_points - 1)
                        

        self._aggiorna_morale_e_intesa_post_partita(vincitore, perdente)
        
        # ==============================================================================
        # ### POST-GAME BLOCK: SEASONAL WEAR UPDATE ###
        # This logic runs AFTER the game and before moving on to the next one.
        # ==============================================================================
        
        if not is_playoff:
            rest_1 = giorni_di_riposo_s1 if giorni_di_riposo_s1 is not None else giorni_di_riposo
            rest_2 = giorni_di_riposo_s2 if giorni_di_riposo_s2 is not None else giorni_di_riposo
            for giocatore in s1.roster:
                giocatore.aggiorna_stamina_stagionale(giorni_di_riposo=rest_1)
            for giocatore in s2.roster:
                giocatore.aggiorna_stamina_stagionale(giorni_di_riposo=rest_2)
        
        # ==============================================================================
        # ### POST-GAME BLOCK: RIVALRY UPDATE ###
        # Tracks the game result to update the rivalries between the teams.
        # ==============================================================================
        
        winner_score = max(punteggio1, punteggio2)
        loser_score = min(punteggio1, punteggio2)
        
        if is_playoff:
            # Adjust series_score to be AFTER this game
            final_series_score = series_score
            if series_score:
                s1_wins, s2_wins = series_score
                if vincitore == s1: s1_wins += 1
                else: s2_wins += 1
                final_series_score = (s1_wins, s2_wins)
            
            # Playoff games update both regular (all-time) and specific playoff records
            self.rivalry_tracker.record_playoff_game(
                vincitore.nome, perdente.nome, winner_score, loser_score,
                final_series_score if final_series_score else (1,0), round_name
            )
        else:
            self.rivalry_tracker.record_regular_season_game(
                vincitore.nome, perdente.nome, winner_score, loser_score
            )
        
        # Generate rivalry news for notable matchups
        if NEWS_ENABLED:
            try:
                rivalry_context = self.rivalry_tracker.get_matchup_context(vincitore.nome, perdente.nome)
                if (not is_playoff and rivalry_context.get('has_rivalry')   # the playoffs have their series stories
                        and rivalry_context.get('intensity', 0) >= CONFIG.NEWS.RIVALRY_NEWS_MIN_INTENSITY):
                    generate_rivalry_postgame_news(
                        vincitore.nome, perdente.nome, 
                        winner_score, loser_score,
                        rivalry_context, 
                        season=self.season_number
                    )
            except Exception:
                pass  # Don't let news generation errors break the simulation
        
        # ==============================================================================
        # ### POST-GAME BLOCK: NEWS GENERATION FOR NOTABLE PERFORMANCES ###
        # ==============================================================================
        
        if NEWS_ENABLED:
            opponent_map = {s1.nome: s2.nome, s2.nome: s1.nome}
            for squadra in [s1, s2]:
                for giocatore in squadra.roster:
                    if giocatore.game_stats.punti > 0:
                        generate_game_performance_news(
                            giocatore.game_stats,
                            giocatore.nome,
                            squadra.nome,
                            opponent_map[squadra.nome],
                            season=self.season_number
                        )
                        # Record notable milestones/performances in the career_log
                        pts = getattr(giocatore.game_stats, 'punti', 0)
                        reb = getattr(giocatore.game_stats, 'rimbalzi', 0)
                        ast = getattr(giocatore.game_stats, 'assist', 0)
                        opp = opponent_map.get(squadra.nome, "Opponent")
                        c_day = getattr(self, '_current_gameday', getattr(self, 'current_day', 1))
                        c_season = getattr(self, 'season_number', 1)
                        
                        if pts >= 40 and hasattr(giocatore, 'add_career_log'):
                            icon_p = '🔥' if pts < 50 else '💥'
                            giocatore.add_career_log(
                                event_type='performance',
                                title=f"Explosion: {pts} POINTS scored!",
                                description=f"Outstanding performance against the {opp}: {pts} PTS, {reb} REB, {ast} AST.",
                                season=c_season,
                                day=c_day,
                                icon=icon_p,
                                team=squadra.nome
                            )
                        elif pts >= 10 and reb >= 10 and ast >= 10 and hasattr(giocatore, 'add_career_log'):
                            giocatore.add_career_log(
                                event_type='triple_double',
                                title=f"Triple-Double ({pts}p/{reb}r/{ast}a)",
                                description=f"All-around performance against the {opp}: {pts} PTS, {reb} REB, {ast} AST.",
                                season=c_season,
                                day=c_day,
                                icon='👑',
                                team=squadra.nome
                            )

                        # Check and update league records
                        if check_and_update_records:
                            try:
                                check_and_update_records(
                                    giocatore.game_stats,
                                    giocatore.nome,
                                    giocatore.nome,  # Use nome as player_id since Giocatore has no id attr
                                    squadra.nome,
                                    opponent_map[squadra.nome],
                                    self.season_number
                                )
                            except Exception:
                                pass
                    # A new injury shows as more days out than at the last check (the count only falls while healing).
                    injury_days = giocatore.giorni_infortunio_rimanenti
                    new_injury = injury_days > getattr(giocatore, '_injury_news_days', 0)
                    giocatore._injury_news_days = injury_days
                    if new_injury and injury_days >= CONFIG.NEWS.INJURY_MIN_DAYS:
                        generate_injury_news(
                            giocatore.nome,
                            squadra.nome,
                            giocatore.giorni_infortunio_rimanenti,
                            season=self.season_number,
                            ovr=giocatore.ovr
                        )
        
        return vincitore

    def _genera_box_score_partita(self, partita_obj, home_team, away_team, game_id: str, date: str = "", day_index: int = 0) -> Dict[str, Any]:
        """
        Extracts and serializes the complete box score of the simulated game,
        including quarters, individual statistics of starters and bench, shooting percentages,
        plus/minus and team totals.
        """
        home_pts = partita_obj.punteggio.get(home_team.nome, 0)
        away_pts = partita_obj.punteggio.get(away_team.nome, 0)
        home_q = partita_obj.punteggi_quarti.get(home_team.nome, [])
        away_q = partita_obj.punteggi_quarti.get(away_team.nome, [])

        def process_team(team_name, team_obj):
            snapshots = getattr(partita_obj, 'final_box_scores', {}).get(team_name, [])
            starters_set = getattr(partita_obj, 'starters', {}).get(team_name, set())
            roster_map = {p.nome: p for p in getattr(team_obj, 'roster', [])}

            players = []
            for s in snapshots:
                p_name = s.get('nome', '')
                gs = s.get('game_stats')
                pm = s.get('plus_minus', 0)
                p_obj = roster_map.get(p_name)
                pos = getattr(p_obj, 'ruolo', normalize_role(s.get('ruolo')) or 'SG')
                is_starter = s.get('is_starter', False) or (p_name in starters_set)

                if not gs:
                    continue

                sec = getattr(gs, 'secondi_giocati', 0)
                mins = round(sec / 60.0, 1) if sec > 0 else round(getattr(gs, 'minuti_giocati', 0.0), 1)
                pts = getattr(gs, 'punti', 0)
                reb = getattr(gs, 'rimbalzi', 0)
                ast = getattr(gs, 'assist', 0)
                stl = getattr(gs, 'steals', 0)
                blk = getattr(gs, 'blocks', 0)
                to = getattr(gs, 'turnover', 0)
                pf = getattr(gs, 'falli_commessi', 0)

                t2_m = getattr(gs, 'tiri_fatti_2', 0)
                t2_a = getattr(gs, 'tiri_tentati_2', 0)
                t3_m = getattr(gs, 'tiri_fatti_3', 0)
                t3_a = getattr(gs, 'tiri_tentati_3', 0)
                fgm = t2_m + t3_m
                fga = t2_a + t3_a
                fg_pct = round((fgm / fga * 100), 1) if fga > 0 else 0.0

                tpm = t3_m
                tpa = t3_a
                three_pct = round((tpm / tpa * 100), 1) if tpa > 0 else 0.0

                ftm = getattr(gs, 'punti_liberi', 0)
                fta = getattr(gs, 'tiri_liberi_tentati', 0)
                ft_pct = round((ftm / fta * 100), 1) if fta > 0 else 0.0

                players.append({
                    "name": p_name,
                    "pos": pos,
                    "is_starter": bool(is_starter),
                    "min": mins,
                    "pts": pts,
                    "reb": reb,
                    "ast": ast,
                    "stl": stl,
                    "blk": blk,
                    "to": to,
                    "pf": pf,
                    "fgm": fgm,
                    "fga": fga,
                    "fg_pct": fg_pct,
                    "tpm": tpm,
                    "tpa": tpa,
                    "three_pct": three_pct,
                    "ftm": ftm,
                    "fta": fta,
                    "ft_pct": ft_pct,
                    "plus_minus": pm,
                    # Counted since 2026-11-15 (see GameStats); older box scores lack these keys
                    "oreb": getattr(gs, 'oreb', 0),
                    "dreb": reb - getattr(gs, 'oreb', 0),
                    "ast_fgm": getattr(gs, 'ast_fgm', 0),
                    "rim_fga": getattr(gs, 'rim_fga', 0),
                    "rim_fgm": getattr(gs, 'rim_fgm', 0),
                    "mid_fga": getattr(gs, 'mid_fga', 0),
                    "mid_fgm": getattr(gs, 'mid_fgm', 0),
                    "clutch_pts": getattr(gs, 'clutch_pts', 0),
                    "clutch_fga": getattr(gs, 'clutch_fga', 0),
                    "clutch_fgm": getattr(gs, 'clutch_fgm', 0),
                    "clutch_min": round(getattr(gs, 'clutch_sec', 0) / 60.0, 1),
                })

            starters = [p for p in players if p["is_starter"]]
            bench = [p for p in players if not p["is_starter"]]
            starters.sort(key=lambda x: x["min"], reverse=True)
            bench.sort(key=lambda x: x["min"], reverse=True)
            sorted_players = starters + bench

            tot_fga = sum(p["fga"] for p in sorted_players)
            tot_fgm = sum(p["fgm"] for p in sorted_players)
            tot_tpa = sum(p["tpa"] for p in sorted_players)
            tot_tpm = sum(p["tpm"] for p in sorted_players)
            tot_fta = sum(p["fta"] for p in sorted_players)
            tot_ftm = sum(p["ftm"] for p in sorted_players)

            totals = {
                "min": round(sum(p["min"] for p in sorted_players), 1),
                "pts": sum(p["pts"] for p in sorted_players),
                "reb": sum(p["reb"] for p in sorted_players),
                "ast": sum(p["ast"] for p in sorted_players),
                "stl": sum(p["stl"] for p in sorted_players),
                "blk": sum(p["blk"] for p in sorted_players),
                "to": sum(p["to"] for p in sorted_players),
                "pf": sum(p["pf"] for p in sorted_players),
                "fgm": tot_fgm,
                "fga": tot_fga,
                "fg_pct": round(tot_fgm / tot_fga * 100, 1) if tot_fga > 0 else 0.0,
                "tpm": tot_tpm,
                "tpa": tot_tpa,
                "three_pct": round(tot_tpm / tot_tpa * 100, 1) if tot_tpa > 0 else 0.0,
                "ftm": tot_ftm,
                "fta": tot_fta,
                "ft_pct": round(tot_ftm / tot_fta * 100, 1) if tot_fta > 0 else 0.0,
            }

            return sorted_players, totals

        away_players, away_totals = process_team(away_team.nome, away_team)
        home_players, home_totals = process_team(home_team.nome, home_team)

        all_p = away_players + home_players
        top_performer = None
        if all_p:
            best = max(all_p, key=lambda p: (p["pts"], p["pts"] + p["reb"] + p["ast"]))
            p_team = away_team.nome if any(p["name"] == best["name"] for p in away_players) else home_team.nome
            top_performer = {
                "name": best["name"],
                "team": p_team,
                "pts": best["pts"],
                "reb": best["reb"],
                "ast": best["ast"],
                "min": best["min"]
            }

        return {
            "game_id": game_id,
            "date": date,
            "day_index": day_index,
            "home_team": {
                "name": home_team.nome,
                "score": home_pts,
                "quarters": list(home_q),
                "players": home_players,
                "totals": home_totals
            },
            "away_team": {
                "name": away_team.nome,
                "score": away_pts,
                "quarters": list(away_q),
                "players": away_players,
                "totals": away_totals
            },
            "top_performer": top_performer
        }

    def _inizializza_inizio_giornata(self, day_index: int):
        """Runs the global injury ticking and the rest recovery for the teams that do not play today."""
        if day_index >= len(self.calendario):
            return
        day = self.calendario[day_index]

        # 0. Rumors about unhappy players, once every CONFIG.NEWS.RUMOR_INTERVAL_DAYS (only once per day)
        if (NEWS_ENABLED and day_index > 0 and day_index % CONFIG.NEWS.RUMOR_INTERVAL_DAYS == 0
                and not getattr(day, '_rumors_checked', False)):
            day._rumors_checked = True
            try:
                generate_rumor_news(self)
            except Exception:
                pass  # news never break the simulation

        # 0b. Trade requests: the weekly frustration check (core/front_office/trade_requests.py), regular season only
        if (day_index > 0 and day_index % CONFIG.TRADE_REQUESTS.TICK_DAYS == 0 and self.fase_torneo == "SEASON"
                and trade_requests.tick_due(self, day_index)):
            trade_requests.weekly_tick(self)

        # 1. Injuries are calendar days: every roster heals one day a day (playoff games take theirs in
        # _simula_e_registra_partita). Before, a day also came off before each game: injuries lasted a third.
        if not getattr(day, '_injuries_ticked', False):
            for s in self.squadre:
                for g in s.roster:
                    if getattr(g, 'giorni_infortunio_rimanenti', 0) > 0:
                        g.giorni_infortunio_rimanenti -= 1
                        if g.giorni_infortunio_rimanenti <= 0:
                            g.giorni_infortunio_rimanenti = 0
                            g.infortunato = False
                            g.infortunio_nome = None
                            g.is_day_to_day = False
                            g.infortunio_impatto = 0.0
            day._injuries_ticked = True

        # 2. Identify the teams playing today and the teams resting (stamina/wear recovery)
        if not getattr(day, '_rest_processed', False):
            teams_playing_today = set()
            for game in day.games:
                teams_playing_today.add(game.home_team)
                teams_playing_today.add(game.away_team)

            if not hasattr(self, '_last_played_day'):
                self._last_played_day = {}
            if not hasattr(self, 'team_map'):
                self.team_map = {s.nome: s for s in self.squadre}

            for s in self.squadre:
                if s.nome not in teams_playing_today:
                    for p in s.roster:
                        p.aggiorna_stamina_stagionale(giorni_di_riposo=1)
            day._rest_processed = True

    def _finalizza_fine_giornata(self, day_index: int) -> Any:
        """Runs the end-of-day routines (scouting, job security, special events) and advances the calendar."""
        day = self.calendario[day_index]
        if getattr(day, '_finalized', False):
            return day

        # Daily routines
        self.check_and_generate_trade_block_offer()
        self.avanza_scouting_giornata()
        self.aggiorna_draft_stock_giornata()
        self.aggiorna_job_security_giornata()
        self.avanza_cooldown_scambi_giornata()

        # Handling of Special Calendar Events
        events = getattr(day, 'events', [])
        if "TRADE_DEADLINE" in events and not getattr(self, '_trade_deadline_completed', False):
            self._gestisci_finestra_estensioni()
            checkpoint_deadline(self)
            self._deadline_window = True  # CPU moves logged now are deadline moves (front office log)
            try:
                self.trade_period_midseason()
            finally:
                self._deadline_window = False
            self._trade_deadline_completed = True
            self.pending_trade_block_offers.clear()  # offers cannot outlive the deadline

        if "ALL_STAR_GAME" in events:
            self.run_all_star_weekend()

        # End of the Regular Season (Day 176 - Last Day)
        if day_index == len(self.calendario) - 1:
            self._concludi_regular_season()

        day._finalized = True
        self._current_gameday = day_index + 1
        return day

    def simula_singola_partita_calendario(self, game_id: str, enable_play_log: bool = False) -> Optional[Dict[str, Any]]:
        """
        Simulates a single game scheduled in the authentic calendar.
        If enable_play_log=True, generates and returns the complete chronological log action by action (play-by-play).
        If all the games of the day are played, finalizes the day and advances to the next day.
        """
        if not getattr(self, "calendario", None):
            self.genera_calendario()

        day_index = getattr(self, '_current_gameday', 0)
        if day_index >= len(self.calendario):
            return None

        # Look for the game first in the current day, then globally if necessary
        day = self.calendario[day_index]
        target_game = None
        for g in day.games:
            if g.game_id == game_id:
                target_game = g
                break

        if not target_game:
            for d_idx, d in enumerate(self.calendario):
                for g in d.games:
                    if g.game_id == game_id:
                        target_game = g
                        day = d
                        day_index = d_idx
                        break
                if target_game:
                    break

        if not target_game:
            return None

        # If already played, return the result right away
        if target_game.played:
            day_completed = all(g.played for g in day.games)
            return {
                "game": target_game.to_dict() if hasattr(target_game, 'to_dict') else target_game,
                "day_completed": day_completed,
                "current_day": getattr(self, '_current_gameday', 0),
                "play_log": [],
                "home_team": target_game.home_team,
                "away_team": target_game.away_team
            }

        # Initialize the start of the day if not done yet
        self._inizializza_inizio_giornata(day_index)

        if not hasattr(self, '_last_played_day'):
            self._last_played_day = {}
        self.team_map = {s.nome: s for s in self.squadre}   # live teams by name (see simula_giornata)

        home_team = self.team_map.get(target_game.home_team)
        away_team = self.team_map.get(target_game.away_team)
        if not (home_team and away_team):
            main_log.error(f"Calendar game {game_id} has a team that is not in the league: not played")

        vincitore = None
        partita_obj = None

        if home_team and away_team:
            last_h = self._last_played_day.get(home_team.nome, -2)
            last_a = self._last_played_day.get(away_team.nome, -2)
            rest_h = max(0, day_index - last_h - 1)
            rest_a = max(0, day_index - last_a - 1)

            vincitore = self._simula_e_registra_partita(
                home_team, away_team, 
                is_playoff=False, 
                giorni_di_riposo=min(rest_h, rest_a),
                giorni_di_riposo_s1=rest_h,
                giorni_di_riposo_s2=rest_a,
                enable_play_log=enable_play_log
            )

            self._last_played_day[home_team.nome] = day_index
            self._last_played_day[away_team.nome] = day_index

            partita_obj = getattr(home_team, 'partita', None)
            if partita_obj and hasattr(partita_obj, 'punteggio'):
                home_pts = partita_obj.punteggio.get(home_team.nome, 0)
                away_pts = partita_obj.punteggio.get(away_team.nome, 0)
                target_game.home_score = home_pts
                target_game.away_score = away_pts
                target_game.played = True

                bs_data = self._genera_box_score_partita(
                    partita_obj, home_team, away_team, 
                    target_game.game_id, target_game.date, target_game.day_index
                )
                if not hasattr(self, 'box_scores'):
                    self.box_scores = {}
                self.box_scores[target_game.game_id] = bs_data
                target_game.box_score_id = target_game.game_id
                target_game.box_score = bs_data
                target_game.quarter_scores = {
                    "home": list(partita_obj.punteggi_quarti.get(home_team.nome, [])),
                    "away": list(partita_obj.punteggi_quarti.get(away_team.nome, []))
                }
                if bs_data.get("top_performer"):
                    target_game.top_performer = bs_data["top_performer"]

        day_completed = all(g.played for g in day.games)
        if day_completed and day_index == getattr(self, '_current_gameday', 0):
            self._finalizza_fine_giornata(day_index)

        play_log = []
        if partita_obj and enable_play_log:
            play_log = list(getattr(partita_obj, 'play_log', []) or [])

        return {
            "game": target_game.to_dict() if hasattr(target_game, 'to_dict') else target_game,
            "day_completed": day_completed,
            "current_day": getattr(self, '_current_gameday', 0),
            "play_log": play_log,
            "home_team": home_team.nome if home_team else target_game.home_team,
            "away_team": away_team.nome if away_team else target_game.away_team,
            "winner": vincitore.nome if vincitore else None
        }


    def simula_giornata(self, day_index: Optional[int] = None) -> Optional[Any]:
        """
        Simulates a single day of the authentic calendar (day_index).
        Simulates all the games not yet played and finalizes the day.
        """
        if not getattr(self, "calendario", None):
            self.genera_calendario()

        if day_index is None:
            day_index = getattr(self, '_current_gameday', 0)

        if day_index >= len(self.calendario):
            return None

        day = self.calendario[day_index]
        self._current_gameday = day_index

        self._inizializza_inizio_giornata(day_index)

        if not hasattr(self, '_last_played_day'):
            self._last_played_day = {}
        # Resolve the teams of today's games by name from the live league: a cached object (team_map,
        # home_team_obj) left over from an older copy recorded the game on a team outside the league
        # (a 25-season save had two teams at 81 games).
        self.team_map = {s.nome: s for s in self.squadre}

        for game in day.games:
            if game.played:
                continue

            home_team = self.team_map.get(game.home_team)
            away_team = self.team_map.get(game.away_team)
            if not (home_team and away_team):
                main_log.error(f"Calendar game {game.game_id} ({game.away_team} @ {game.home_team}) has a team "
                               f"that is not in the league: not played")

            if home_team and away_team:
                last_h = self._last_played_day.get(home_team.nome, -2)
                last_a = self._last_played_day.get(away_team.nome, -2)
                rest_h = max(0, day_index - last_h - 1)
                rest_a = max(0, day_index - last_a - 1)

                vincitore = self._simula_e_registra_partita(
                    home_team, away_team, 
                    is_playoff=False, 
                    giorni_di_riposo=min(rest_h, rest_a),
                    giorni_di_riposo_s1=rest_h,
                    giorni_di_riposo_s2=rest_a
                )

                self._last_played_day[home_team.nome] = day_index
                self._last_played_day[away_team.nome] = day_index

                partita_obj = getattr(home_team, 'partita', None)
                if partita_obj and hasattr(partita_obj, 'punteggio'):
                    home_pts = partita_obj.punteggio.get(home_team.nome, 0)
                    away_pts = partita_obj.punteggio.get(away_team.nome, 0)
                    game.home_score = home_pts
                    game.away_score = away_pts
                    game.played = True

                    bs_data = self._genera_box_score_partita(
                        partita_obj, home_team, away_team, 
                        game.game_id, game.date, game.day_index
                    )
                    if not hasattr(self, 'box_scores'):
                        self.box_scores = {}
                    self.box_scores[game.game_id] = bs_data
                    game.box_score_id = game.game_id
                    game.box_score = bs_data
                    game.quarter_scores = {
                        "home": list(partita_obj.punteggi_quarti.get(home_team.nome, [])),
                        "away": list(partita_obj.punteggi_quarti.get(away_team.nome, []))
                    }
                    if bs_data.get("top_performer"):
                        game.top_performer = bs_data["top_performer"]

        self._finalizza_fine_giornata(day_index)
        return day

    def simula_fino_a_giornata(self, target_day_index: int) -> List[Any]:
        """
        Progressively simulates all the days up to the specified target day.
        If for example target_day_index = 24, simulates all the previous days until
        the active day is 24 (or stops at the All-Star Break / end of the season).
        """
        simulated_days = []
        target_day_index = min(target_day_index, len(self.calendario))
        while getattr(self, '_current_gameday', 0) < target_day_index:
            day = self.simula_giornata()
            if day is None:  # a CalendarDay with no games (break, off day) is falsy
                break
            simulated_days.append(day)
            # Pause once, right after the All-Star Game day (the weekend may already be played at the break).
            if getattr(self, 'all_star_weekend_complete', False) and "ALL_STAR_GAME" in getattr(day, 'events', []):
                break
        return simulated_days

    def simula_settimana(self) -> List[Any]:
        """Simulates the next 7 calendar days."""
        days = []
        for _ in range(7):
            if getattr(self, '_current_gameday', 0) >= len(self.calendario):
                break
            day = self.simula_giornata(self._current_gameday)
            if day is not None:
                days.append(day)
        return days

    def _concludi_regular_season(self):
        """Runs the closing operations at the end of day 176."""
        self._calcola_e_stampa_premi_stagionali()

        # Reset is_rookie RIGHT AFTER the awards: the tag has done its job
        # (their names are kept first: next season's All-Star sophomores).
        self._remember_rookies()
        for squadra in self.squadre:
            for player in squadra.roster:
                player.is_rookie = False
        for fa in self.free_agents_pool:
            fa.is_rookie = False
        
        scales = league_season_scales(self)   # PVS on the reference era's level
        for squadra in self.squadre:
            for player in squadra.roster:
                player.calcola_pvs(scales)
        
        self.podcast_logger.log_standings(
            sorted([s for s in self.squadre if s.conference == 'East'], key=lambda x: x.vittorie, reverse=True),
            sorted([s for s in self.squadre if s.conference == 'West'], key=lambda x: x.vittorie, reverse=True)
        )
        
        stampa_report_squadre_fine_stagione(self)
        stampa_report_fine_stagione(self)
        self._first_half_complete = True
        self._regular_season_complete = True

    def simula_regular_season(self):
        """Simulates the whole Regular Season (176 days, 1230 games) in one go."""
        self.simula_first_half()
        
        # All-Star events if not yet completed (no-op once played)
        self.run_all_star_weekend()

        self.simula_second_half()
    
    def simula_first_half(self):
        """Simulates the first half of the season up to the All-Star Break (~Day 114)."""
        if not getattr(self, "calendario", None):
            self.genera_calendario()

        all_star_day = 114
        for idx, day in enumerate(self.calendario):
            if getattr(day, 'phase', '') == "ALL_STAR_BREAK" or "ALL_STAR_BREAK" in getattr(day, 'events', []):
                all_star_day = idx
                break

        main_log.info("\n" + "=" * 60)
        main_log.info(f"SIMULATING FIRST HALF OF THE REGULAR SEASON (Days 1 -> {all_star_day})")
        main_log.info("=" * 60)

        while getattr(self, '_current_gameday', 0) < all_star_day and self._current_gameday < len(self.calendario):
            self.simula_giornata(self._current_gameday)

        # If the trade deadline has not passed yet, run it at the end of the first half
        if not getattr(self, '_trade_deadline_completed', False):
            self._gestisci_finestra_estensioni()
            checkpoint_deadline(self)
            self._deadline_window = True  # CPU moves logged now are deadline moves (front office log)
            try:
                self.trade_period_midseason()
            finally:
                self._deadline_window = False
            self._trade_deadline_completed = True
            self.pending_trade_block_offers.clear()

        self._first_half_complete = True
        self._gestisci_licenziamenti_midseason()

        main_log.info("\n" + "=" * 60)
        main_log.info("FIRST HALF COMPLETED - ALL-STAR BREAK!")
        main_log.info("=" * 60)
    
    def simula_second_half(self):
        """Simulates the second half of the season from the All-Star Break to the Grand Finale (Day 176)."""
        if not getattr(self, "calendario", None):
            self.genera_calendario()

        total_days = len(self.calendario)
        start_day = getattr(self, '_current_gameday', 0)

        main_log.info("\n" + "=" * 60)
        main_log.info(f"SIMULATING SECOND HALF OF THE REGULAR SEASON (Days {start_day + 1} -> {total_days})")
        main_log.info("=" * 60)

        while getattr(self, '_current_gameday', 0) < total_days:
            self.simula_giornata(self._current_gameday)

        main_log.info("\n" + "=" * 60)
        main_log.info("REGULAR SEASON COMPLETED - START OF THE POSTSEASON!")
        main_log.info("=" * 60)

    def avanza_cooldown_scambi_giornata(self):
        """Decrements the trade cooldown for all the players in the league by 1 day/game."""
        for squadra in self.squadre:
            for p in squadra.roster:
                if getattr(p, 'giorni_cooldown_scambio', 0) > 0:
                    p.giorni_cooldown_scambio -= 1

    def avanza_scouting_giornata(self):
        """
        Increments the scouting progress for the prospects assigned to active scouts.
        It is called at the end of every simulated regular-season day.
        """
        if not getattr(self, 'scout_staff', None) or not getattr(self, 'draft_class', None):
            return
            
        # Scouting speed based on the scout's level rating
        SPEED_MAP = {
            'A': 3.5,
            'B': 2.5,
            'C': 1.5
        }
        
        # Map of the prospects by name
        prospects_by_name = {}
        for p in self.draft_class:
            name = p.get("nome") if isinstance(p, dict) else getattr(p, "nome", None)
            if name:
                prospects_by_name[name] = p
        
        for scout in self.scout_staff:
            assigned_player_name = scout.get("assigned_to")
            if assigned_player_name and assigned_player_name in prospects_by_name:
                prospect = prospects_by_name[assigned_player_name]
                speed = SPEED_MAP.get(scout.get("speed", "C"), 1.5)
                # Increase progress with a slight random variation
                incremento = speed * random.uniform(0.8, 1.2)
                
                if isinstance(prospect, dict):
                    curr = prospect.get("scouting_progress", 10.0) or 10.0
                    new_prog = min(100.0, curr + incremento)
                    prospect["scouting_progress"] = new_prog
                    if new_prog >= 100.0:
                        scout["assigned_to"] = None
                else:
                    curr = getattr(prospect, 'scouting_progress', 10.0) or 10.0
                    new_prog = min(100.0, curr + incremento)
                    prospect.scouting_progress = new_prog
                    if new_prog >= 100.0:
                        scout["assigned_to"] = None

    def aggiorna_draft_stock_giornata(self):
        """
        Randomly updates the draft stock of some prospects, simulating college news.
        """
        if not getattr(self, 'draft_class', None):
            return
            
        # 10% chance per day of having news about a prospect
        if random.random() < 0.10:
            prospect = random.choice(self.draft_class)
            # Determine whether it goes up or down
            change = random.choice([-5, -3, 3, 5])
            
            if isinstance(prospect, dict):
                p_nome = prospect.get('nome', 'Prospect')
                p_provenance = prospect.get('provenance', 'NCAA')
                curr_mod = prospect.get('draft_stock_mod', 0.0) or 0.0
                prospect['draft_stock_mod'] = max(-10.0, min(10.0, curr_mod + change))
            else:
                p_nome = getattr(prospect, 'nome', 'Prospect')
                p_provenance = getattr(prospect, 'provenance', 'NCAA')
                curr_mod = getattr(prospect, 'draft_stock_mod', 0.0) or 0.0
                prospect.draft_stock_mod = max(-10.0, min(10.0, curr_mod + change))
            
            # Create a news item in the feed
            from core.news_generator import add_news
            if change > 0:
                title = f"Draft prospect {p_nome} is rising"
                excerpt = f"Strong recent games for {p_nome} ({p_provenance}). Scouts are moving him up their boards."
            else:
                title = f"Draft prospect {p_nome} is sliding"
                excerpt = f"A poor stretch for {p_nome} ({p_provenance}). Scouts are moving him down their boards."
                
            add_news(
                category="draft",
                title=title,
                excerpt=excerpt,
                teams=[],
                season=self.season_number,
                kind="draft",
                tier=1
            )

    def aggiorna_job_security_giornata(self):
        """Updates the front office's confidence in each coach on a daily basis, against the season-start
        expectation (core/front_office/seasons.py)."""
        cfg = CONFIG.FRONT_OFFICE
        fo = ensure_front_office(self)
        year = current_year(self)
        league_avg = None
        for squadra in self.squadre:
            if not squadra.coach: continue
            
            total_games = squadra.vittorie + squadra.sconfitte
            if total_games < cfg.COACH_DRIFT_MIN_GAMES:
                squadra.coach.job_security = 75.0
                continue
                
            mark = fo.season_marks.get(squadra.nome)
            if mark and mark.get("year") == year:
                vittorie_attese = mark["expected"]
            else:
                if league_avg is None:
                    league_avg = league_avg_ovr(self)
                vittorie_attese = expected_wins(squadra, league_avg)
            target_win_pct = vittorie_attese / 82.0
            
            actual_win_pct = squadra.vittorie / total_games
            delta = actual_win_pct - target_win_pct
            
            owner_type = normalize_owner_personality(getattr(squadra, 'personalita_proprietario', None))
            patience_factor = 1.0
            if delta < 0:
                patience_factor = cfg.COACH_DRIFT_PATIENCE.get(owner_type, 1.0)
                
            change = delta * cfg.COACH_DRIFT_PER_WIN_PCT * patience_factor
            
            if team_plan_state(self, squadra) == "REBUILDER":
                if change < 0:
                    change *= cfg.COACH_DRIFT_REBUILD_FALL
                else:
                    change *= cfg.COACH_DRIFT_REBUILD_RISE
                    
            # The meter only: CPU coaches are fired by the judged checks (_gestisci_licenziamenti_midseason at the
            # All-Star break, _gestisci_fase_licenziamenti at season end), never by this daily drift.
            squadra.coach.job_security = max(0.0, min(100.0, squadra.coach.job_security + change))

    def _calcola_mvp_regular_season(self):
        tutti_giocatori = [p for s in self.squadre for p in s.roster if p.season_stats.partite_giocate >= 60]
        if not tutti_giocatori: self.regular_season_mvp = None; return

        # --- VOTER FATIGUE RECOVERY & HISTORY CHECK ---
        last_season_mvp, two_seasons_ago_mvp, career_mvp_counts = self._award_winner_history(
            "mvp", "MVP", tutti_giocatori)

        def mvp_metric(p: Giocatore) -> float:
            st = p.season_stats
            pg = st.partite_giocate or 1
            ppg = st.punti / pg
            rpg = st.rimbalzi / pg
            apg = st.assist / pg
            spg = st.steals / pg
            bpg = st.blocks / pg
            topg = st.turnover / pg
            tot_g = (p.squadra.vittorie + p.squadra.sconfitte) or 1
            win_pct = p.squadra.vittorie / tot_g
            raw_stat = ppg + (rpg * 1.15) + (apg * 1.35) + (spg * 1.5) + (bpg * 1.5) - (topg * 1.1)
            
            # --- APPLYING VOTER FATIGUE ---
            fatigue_mult = 1.0
            # Back-to-back: whoever won last year has to clear a higher bar
            if p.nome == last_season_mvp:
                fatigue_mult -= 0.09 # -9%
                # Three-peat attempt: storicamente rarissimo (solo Russell, Wilt, Bird)
                if p.nome == two_seasons_ago_mvp:
                    fatigue_mult -= 0.11 # Additional -11% (total -20%)
            
            # Soft fatigue for too many MVPs won in a career (favors new faces with equal performance)
            prior_mvps = career_mvp_counts.get(p.nome, 0)
            if prior_mvps > 0:
                discount = min(0.06, prior_mvps * 0.015)
                fatigue_mult -= discount

            fatigue_mult = max(0.75, fatigue_mult)
            return raw_stat * (0.8 + win_pct * 0.6) * fatigue_mult

        self.regular_season_mvp = max(tutti_giocatori, key=mvp_metric)
    
    def _calcola_most_improved_player(self) -> Optional[Giocatore]:
        """
        ### NEW: Most Improved Player ###
        Calculates the MIP based on statistical growth or overperformance.
        Year 1: Differential between OVR-based expected performance and actual production.
        Year 2+: Growth in (PPG + RPG + APG) from previous season.
        """
        cfg = CONFIG.AWARDS
        mvp = getattr(self, 'regular_season_mvp', None)
        tutti_giocatori = [p for s in self.squadre for p in s.roster if p.season_stats.partite_giocate >= 60
                           and p is not mvp and not getattr(p, 'is_rookie', False)
                           and p.season_stats.minuti_giocati / p.season_stats.partite_giocate >= cfg.MIP_MIN_MPG]
        if not tutti_giocatori: return None
        
        # Load career data for Year 2+ growth calculation
        career_file = get_historical_file_path("player_careers.json")
        all_careers = {}
        if self.season_number > 1 and os.path.exists(career_file):
            try:
                with open(career_file, 'r', encoding='utf-8') as f:
                    all_careers = json.load(f)
            except: pass

        def get_mip_score(p):
            stats = p.season_stats
            pg = stats.partite_giocate or 1
            current_total = (stats.punti + stats.rimbalzi + stats.assist) / pg
            
            if self.season_number == 1:
                # YEAR 1 Logic: Performance vs OVR Expected
                expected_total = (p.ovr - 50) * 0.65 # Heuristic for mid-range stats
                return current_total - expected_total
            else:
                # YEAR 2+ Logic: Compare with previous season
                p_id = p.nome.replace(" ", "-").lower()
                hist = all_careers.get(p_id, [])
                # Find the most recent non-current season
                prev_season = None
                for s in reversed(hist):
                    if s.get('stagione', 0) < self.season_number:
                        prev_season = s
                        break
                
                if prev_season and (prev_season.get('partite_giocate_rs') or prev_season.get('gp') or 0) >= cfg.MIP_PREV_MIN_GP:
                    s_rs = prev_season.get('stats_rs', {})
                    prev_total = s_rs.get('ppg', 0) + s_rs.get('rpg', 0) + s_rs.get('apg', 0)
                    # Significant growth score
                    return current_total - prev_total
                else:
                    return float('-inf')   # no real season to improve on (short or missing year)

        best = max(tutti_giocatori, key=get_mip_score, default=None)
        return best if best is not None and get_mip_score(best) > float('-inf') else None
    
    def _award_winner_history(self, history_key: str, award_label: str, players) -> tuple:
        """Last season's and two seasons ago's winner of an award, and career counts by name, from league_history.json
        (`premi[history_key]`) and the players' own awards list (`award_label`). For voter fatigue."""
        last_winner = two_ago_winner = None
        career_counts = {}
        try:
            history_file = get_historical_file_path("league_history.json")
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    storia = json.load(f)
                for s in storia:
                    st_num = s.get("stagione")
                    winner = (s.get("premi") or {}).get(history_key)
                    if winner and winner != "N/A":
                        career_counts[winner] = career_counts.get(winner, 0) + 1
                        if st_num == self.season_number - 1:
                            last_winner = winner
                        elif st_num == self.season_number - 2:
                            two_ago_winner = winner
        except Exception as e:
            main_log.warning(f"Error reading league_history for {award_label} voter fatigue: {e}")
        for p in players:
            premi = getattr(p, 'premi', []) or []
            if isinstance(premi, list):
                career_counts[p.nome] = max(career_counts.get(p.nome, 0), premi.count(award_label))
        return last_winner, two_ago_winner, career_counts

    def _calcola_defensive_player_of_the_year(self):
        """DPOY: stocks, defensive rebounds and defensive ratings, times the team's record and its defense (points
        allowed against the league), with voter fatigue like the MVP and a small discount for the season's MVP. It
        had no fatigue, a record worth +-4% and rebounds worth so much that one center won 14 in a row on a .500
        team (CONFIG.AWARDS.DPOY_*)."""
        cfg = CONFIG.AWARDS
        tutti_giocatori = [p for s in self.squadre for p in s.roster if p.season_stats.partite_giocate >= 60]
        if not tutti_giocatori: self.defensive_player_of_the_year = None; return

        last_dpoy, two_ago_dpoy, career_dpoy = self._award_winner_history("dpoy", "DPOY", tutti_giocatori)
        season_mvp = getattr(self, 'regular_season_mvp', None)   # set just before (_calcola_mvp_regular_season)

        def allowed_per_game(s):
            gp = (s.vittorie + s.sconfitte) or 0
            return s.punti_subiti_stagione / gp if gp and s.punti_subiti_stagione else None
        allowed = [a for a in (allowed_per_game(s) for s in self.squadre) if a]
        league_allowed = sum(allowed) / len(allowed) if allowed else None

        def dpoy_metric(p: Giocatore) -> float:
            st = p.season_stats
            pg = st.partite_giocate or 1
            spg = st.steals / pg
            bpg = st.blocks / pg
            drpg = max(0, st.rimbalzi - (getattr(st, 'oreb', 0) or 0)) / pg
            def_iq = getattr(p.abilita, 'defensive_iq_rating', 70)
            int_def = getattr(p.abilita, 'interior_defense_rating', 70)
            per_def = getattr(p.abilita, 'perimeter_defense_rating', 70)
            rating_bonus = (def_iq * 0.05) + (max(int_def, per_def) * 0.05)
            raw = (spg * cfg.DPOY_STEAL_WEIGHT) + (bpg * cfg.DPOY_BLOCK_WEIGHT) + (drpg * cfg.DPOY_DREB_WEIGHT) + rating_bonus

            tot_g = (p.squadra.vittorie + p.squadra.sconfitte) or 1
            win_pct = p.squadra.vittorie / tot_g
            team_mult = cfg.DPOY_WIN_BASE + win_pct * cfg.DPOY_WIN_WEIGHT
            team_allowed = allowed_per_game(p.squadra)
            if league_allowed and team_allowed:
                team_mult *= 1.0 + (league_allowed / team_allowed - 1.0) * cfg.DPOY_TEAM_DEFENSE_WEIGHT

            fatigue = 1.0
            if p.nome == last_dpoy:
                fatigue -= cfg.DPOY_FATIGUE_REPEAT
                if p.nome == two_ago_dpoy:
                    fatigue -= cfg.DPOY_FATIGUE_THREE_PEAT
            fatigue -= min(cfg.DPOY_FATIGUE_CAREER_MAX, career_dpoy.get(p.nome, 0) * cfg.DPOY_FATIGUE_CAREER_EACH)
            mvp_share = cfg.DPOY_MVP_SHARE if p is season_mvp else 1.0
            return raw * team_mult * max(cfg.DPOY_FATIGUE_FLOOR, fatigue) * mvp_share

        self.defensive_player_of_the_year = max(tutti_giocatori, key=dpoy_metric)
    def _calcola_mvp_finali(self, campione, finalista):
        candidati = [p for p in campione.roster if p.playoff_stats.partite_giocate > 0]
        if not candidati: self.finals_mvp = None; return
        self.finals_mvp = max(candidati, key=lambda p: p.playoff_stats.mvp_points / (p.playoff_stats.partite_giocate or 1))
        self.podcast_logger.log_finals_mvp(self.finals_mvp.nome)
    def _gestisci_finestra_estensioni(self):
        main_log.info("\n--- START OF THE MID-SEASON CONTRACT EXTENSION WINDOW ---")
        
        # Use the new centralized ContractExtensions module
        try:
            from offseason.contract_extensions import ContractExtensions
            extensions_manager = ContractExtensions(self, self.squadre)
            log_estensioni = extensions_manager.process_extensions()
            
            if 'estensioni' not in self.offseason_log_data: self.offseason_log_data['estensioni'] = {}
            self.offseason_log_data['estensioni'] = log_estensioni
            
        except ImportError:
            main_log.error("Could not import ContractExtensions. Using legacy fallback (which is empty now).")
        except Exception as e:
            main_log.error(f"Error during contract extensions: {e}")
            import traceback
            traceback.print_exc()

    def _calcola_richiesta_salariale_base(self, giocatore: Giocatore, premi: bool = True) -> float:
        """
        ### REWORKED (v8.0 - Centralized Logic) ###
        This method now primarily relies on the player's own market value calculation
        and applies award bonuses on top.
        """
        # Get the tiered, capped market value directly from the player object
        salario_base = giocatore._calcola_valore_di_mercato()
        
        cfg_eco = CONFIG.ECONOMY
        
        if premi:
            player_awards = self.get_player_awards_last_season(giocatore.nome)
            bonus_totale = sum(cfg_eco.AWARD_SALARY_BONUSES.get(award, 0.0) for award in player_awards)
            bonus_applicato = min(3.5, bonus_totale * 0.35)
            salario_base += bonus_applicato

        return round(salario_base, 1)

    def _initialize_pick_ownership(self):
        """Initializes the map of the pick owners."""
        for squadra in self.squadre:
            for year in range(1, 6):
                # Key: "R{round}-{original_team}", Value: current_owner
                self.pick_ownership[year][f"R1-{squadra.nome}"] = squadra.nome
                self.pick_ownership[year][f"R2-{squadra.nome}"] = squadra.nome

    def _load_management_factor(self) -> float:
        """Share of today's rest days a star takes in this league year (CONFIG.SIM.LOAD_MANAGEMENT_*): stars of the
        early 2000s rarely sat healthy, load management grew in the 2010s. It was the same in every era."""
        cfg = CONFIG.SIM
        start, full = cfg.LOAD_MANAGEMENT_RAMP_YEARS
        ratio = min(1.0, max(0.0, (getattr(self, 'anno_corrente', full) - start) / max(1, full - start)))
        return cfg.LOAD_MANAGEMENT_EARLY_FACTOR + (1.0 - cfg.LOAD_MANAGEMENT_EARLY_FACTOR) * ratio

    def _fade_rivalries(self):
        """Season rollover of the rivalries: intensity decays (RivalryTracker.apply_season_decay). It was never
        called, so every pair that met in the playoffs climbed for good: ~115 'heated' rivalries and as many
        rivalry stories a season after 20 years."""
        tracker = getattr(self, 'rivalry_tracker', None)
        if tracker is None:
            return
        tracker.current_season = self.season_number   # the tracker is rebuilt on load: keep it on the league's count
        tracker.advance_season()

    def _age_draft_picks(self):
        """Moves the draft pick ownership forward by one year."""
        # Normalize existing keys to ints
        current_ownership = {}
        if hasattr(self, 'pick_ownership') and self.pick_ownership:
            for k, v in self.pick_ownership.items():
                try:
                    current_ownership[int(k)] = v
                except (ValueError, TypeError):
                    pass
                    
        current_protections = {}
        if hasattr(self, 'pick_protections') and self.pick_protections:
            for k, v in self.pick_protections.items():
                try:
                    current_protections[int(k)] = v
                except (ValueError, TypeError):
                    pass

        new_ownership = {year: {} for year in range(1, 6)} # Initialize all 5 years as empty dicts
        new_protections = {year: {} for year in range(1, 6)}
        
        for year in range(1, 5): # From year 1 to 4 (which will become year 2 to 5)
            # Picks from year+1 become picks for 'year'
            if (year + 1) in current_ownership:
                for pick_key, owner in current_ownership[year + 1].items():
                    new_ownership[year][pick_key] = owner
            if (year + 1) in current_protections:
                for pick_key, prot in current_protections[year + 1].items():
                    new_protections[year][pick_key] = prot
        
        # Add the new picks for the "new" year 5
        for squadra in self.squadre:
            new_ownership[5][f"R1-{squadra.nome}"] = squadra.nome
            new_ownership[5][f"R2-{squadra.nome}"] = squadra.nome
            # new_protections[5] stays empty/Unprotected
        
        self.pick_ownership = new_ownership
        self.pick_protections = new_protections
    def _aggiorna_fvs_fine_stagione(self):
        """
        ### REWORKED (v3.0 - PVS Integration) ###
        At the end of the season, updates each player's Franchise Value Score using
        the new detailed performance scores.
        """
        main_log.info("\n--- Franchise Value Score (FVS) Update ---")
        for squadra in self.squadre:
            for giocatore in squadra.roster:
                fvs_change = 0
                
                # --- KEY CHANGE: We use the new performance_scores ---
                # 1. Performance vs Contract
                # A "good contract" is when a player produces at a level (total PVS)
                # above his reputation (OVR), especially if his salary is low.
                salario_mercato = giocatore._calcola_valore_di_mercato()
                pvs_totale = giocatore.performance_scores.total
                
                if giocatore.contract:
                    # Case 1: Overperforming player (e.g. PVS 90, OVR 84) on a favorable contract
                    if pvs_totale > giocatore.ovr + 4 and giocatore.contract.salario_annuale < salario_mercato * 1.1:
                        fvs_change += 10 # He is overperforming a favorable contract -> great asset
                    
                    # Case 2: Underperforming player (e.g. PVS 80, OVR 86) on a heavy contract
                    elif pvs_totale < giocatore.ovr - 4 and giocatore.contract.salario_annuale > salario_mercato * 0.9:
                        fvs_change -= 10 # Heavy contract for a declining player -> bad asset

                # 2. Team success/failure
                if squadra.vittorie > squadra.vittorie_attese + 5:
                    fvs_change += 5 # Being part of a winning team increases the value
                elif squadra.vittorie < squadra.vittorie_attese - 10:
                    fvs_change -= 7 # Being part of a disappointing team decreases it

                # 3. Infortuni (Liability)
                if giocatore.giorni_infortunio_rimanenti > 30: # He suffered a serious injury
                    fvs_change -= 15 # A serious injury reduces his value for the franchise
                
                # Apply the change and limit the value between 0 and 100
                giocatore.fvs = max(0, min(100, giocatore.fvs + fvs_change))

    def get_player_awards_last_season(self, player_name: str) -> List[str]:
        """
        ### NEW HELPER METHOD (v6.2.2 - FIX) ###
        Retrieves the awards won by a player in the most recent season
        by searching the careers database.
        """
        player_id = player_name.replace(" ", "-").lower()
        
        try:
            career_file = get_historical_file_path("player_careers.json")
            with open(career_file, 'r', encoding='utf-8') as f:
                all_careers = json.load(f)
            
            player_career = all_careers.get(player_id)
            if not player_career:
                return []
            
            # Find the most recent season for that player
            last_season_data = max(player_career, key=lambda s: s['stagione'])
            
            # Check whether the season found is actually the one that just ended
            if last_season_data['stagione'] == self.season_number:
                return last_season_data.get("premi", [])

        except (FileNotFoundError, json.JSONDecodeError):
            # If the file does not exist or is corrupted, there are no awards to find
            return []
            
        return []
    def _calcola_punteggio_accettazione(self, giocatore: 'Giocatore', squadra: 'Squadra', offerta_salariale: float, goal_squadra: str, option_type: str = "None") -> float:
        """
        ### REWORKED (v7.2) ###
        The unique "brain" now receives the team's goal as a parameter,
        making it independent of context and usable in every phase of the game.
        """
        punteggio = 50.0
        valore_mercato_base = self._calcola_richiesta_salariale_base(giocatore)
        if valore_mercato_base <= 0: valore_mercato_base = self.min_salary

        # Apply financial trade-off for contract option types
        if option_type == "PO":
            valore_mercato_base *= 0.90
        elif option_type == "TO":
            valore_mercato_base *= 1.10

        # 1. Economic Factor
        ratio_offerta = offerta_salariale / valore_mercato_base
        
        # Hard block: If the offer is way too low compared to the player's market value,
        # stars and starters in their prime (under 33) will reject it outright.
        if giocatore.eta < 33:
            if giocatore.ovr >= 85 and ratio_offerta < 0.8:
                main_log.info(f"SIGNING DEBUG - Player {giocatore.nome} instantly rejects low-ball offer of ${offerta_salariale}M (Asking: ${valore_mercato_base}M)")
                return 0.0
            elif giocatore.ovr >= 78 and ratio_offerta < 0.7:
                main_log.info(f"SIGNING DEBUG - Player {giocatore.nome} instantly rejects low-ball offer of ${offerta_salariale}M (Asking: ${valore_mercato_base}M)")
                return 0.0
            elif giocatore.ovr >= 72 and ratio_offerta < 0.5:
                main_log.info(f"SIGNING DEBUG - Player {giocatore.nome} instantly rejects low-ball offer of ${offerta_salariale}M (Asking: ${valore_mercato_base}M)")
                return 0.0

        punteggio += (ratio_offerta - 1.0) * 60

        # 2. Morale Factor
        punteggio += (giocatore.morale - 70) * 0.4

        # 3. Team Success Factor (now uses the parameter)
        if goal_squadra == "Defending Champion": punteggio += 25
        elif goal_squadra == "Contender": punteggio += 15
        elif goal_squadra == "Playoff Team": punteggio += 8
        elif goal_squadra == "Rising Star": punteggio += 5
        elif goal_squadra == "Rebuilding": punteggio -= 15
        elif goal_squadra == "Mediocre": punteggio -= 10

        # 4. Ambition Factor
        if giocatore.eta < 28 and giocatore.ovr >= 85: punteggio -= 10
        elif giocatore.eta > 32: punteggio += 10

        main_log.info(f"SIGNING DEBUG - Player: {giocatore.nome} ({giocatore.ovr} OVR, Morale: {giocatore.morale}) | Team: {squadra.nome} (Goal: {goal_squadra}) | Offer: ${offerta_salariale}M (Base Req.: ${valore_mercato_base}M) -> Score: {punteggio:.1f}")

        return max(0, min(100, punteggio))
    def _aggiorna_morale_e_intesa_post_partita(self, vincitore: 'Squadra', perdente: 'Squadra'):
        """
        Updates the players' morale and the team chemistry AFTER a game.
        This logic now lives in the Tournament to guarantee data persistence.
        """
        # 1. Team Chemistry update with amplified effects
        vincitore.intesa = min(100, vincitore.intesa + 3)
        perdente.intesa = max(0, perdente.intesa - 4)

        # 2. Individual Morale update with amplified effects
        for squadra in [vincitore, perdente]:
            is_winner = (squadra == vincitore)
            for giocatore in squadra.roster:
                # Morale only changes if the player actually played
                if giocatore.game_stats.minuti_giocati > 5: # Minimum 5 minutes to have an impact
                    cambio_morale = 0
                    # Win/loss effect (stronger)
                    cambio_morale += 4 if is_winner else -5
                    
                    # Individual performance effect (stronger)
                    mvp_pts = giocatore.game_stats.mvp_points
                    if mvp_pts > 25: cambio_morale += 5 # Star game
                    elif mvp_pts < 8: cambio_morale -= 4 # Negative game

                    # Minutes vs expectations effect (unchanged)
                    if giocatore.minuti_target > 0 and giocatore.game_stats.minuti_giocati < giocatore.minuti_target * 0.6:
                        cambio_morale -= 3
                    
                    giocatore.morale = max(0, min(100, giocatore.morale + cambio_morale))

    # NOTE: start_offseason_progression is defined above with the full logic
    # DO NOT ADD duplicate functions here!

    def _resolve_contract_options(self, user_decisions=None):
        """
        Checks the expiring contracts (anni_rimanenti == 1) with PO/TO options.
        Decides whether to exercise or decline based on the market value.
        """
        if user_decisions is None:
            user_decisions = {}
        main_log.info("Evaluating Contract Options (Player & Team Options)...")
        options_exercised = 0
        options_declined = 0
        if not isinstance(getattr(self, 'offseason_log_data', None), dict):
            self.offseason_log_data = {}
        options_log = self.offseason_log_data.setdefault('options', [])
        
        for squadra in self.squadre:
            is_user_team = (squadra == self.squadra_giocatore)
            for p in squadra.roster:
                if not p.contract or p.contract.anni_rimanenti != 1:
                    continue 

                # Compute the current market value
                try:
                    market_value = p._calcola_valore_di_mercato()
                except:
                    market_value = p.valutazione * 0.5 # Fallback
                
                current_salary = p.contract.salario_annuale
                
                # --- PLAYER OPTION ---
                if getattr(p.contract, 'player_option', False):
                    decision, reason = p.valuta_player_option(squadra=squadra, torneo=self)
                    if decision == "DECLINE":
                        main_log.info(f"[PO DECLINE] {p.nome} ({p.ovr} OVR, {p.eta}y) declines PO (${current_salary:.1f}M). Reason: {reason}")
                        # Decline -> Years stay at 1, will be decremented to 0 shortly -> FA
                        options_declined += 1
                        p.contract.player_option = False # Consumata
                        options_log.append({"name": p.nome, "team": squadra.nome, "kind": "player", "decision": "out"})
                    else:
                        main_log.info(f"[PO ACCEPT] {p.nome} ({p.ovr} OVR, {p.eta}y) exercises PO (${current_salary:.1f}M). Reason: {reason}")
                        # Accept -> We add 1 year, so after the decrement 1 remains.
                        p.contract.anni_rimanenti += 1
                        p.contract.player_option = False # Consumata
                        options_exercised += 1
                        options_log.append({"name": p.nome, "team": squadra.nome, "kind": "player", "decision": "in"})

                # --- TEAM OPTION ---
                elif getattr(p.contract, 'team_option', False):
                    if is_user_team:
                        # Check if user made a decision
                        # The hub sends "PICKUP" / "DECLINE"; older callers sent booleans.
                        pickup = user_decisions.get(p.nome)
                        if isinstance(pickup, str):
                            pickup = pickup.upper() == "PICKUP"
                        if pickup is None:
                            decision, reason = p.valuta_team_option(squadra=squadra, torneo=self)
                            pickup = (decision == "PICKUP")
                        
                        if pickup:
                            main_log.info(f"[USER TO PICKUP] {squadra.nome} exercise the TO on {p.nome} (${current_salary:.1f}M).")
                            p.contract.anni_rimanenti += 1
                            p.contract.team_option = False
                            options_exercised += 1
                            options_log.append({"name": p.nome, "team": squadra.nome, "kind": "team", "decision": "in"})
                        else:
                            main_log.info(f"[USER TO DECLINE] {squadra.nome} decline the TO on {p.nome} (${current_salary:.1f}M).")
                            options_declined += 1
                            p.contract.team_option = False
                            options_log.append({"name": p.nome, "team": squadra.nome, "kind": "team", "decision": "out"})
                    else:
                        # AI decision
                        decision, reason = p.valuta_team_option(squadra=squadra, torneo=self)
                        if decision == "PICKUP":
                             main_log.info(f"[TO PICKUP] {squadra.nome} exercise the TO on {p.nome} (${current_salary:.1f}M). Reason: {reason}")
                             p.contract.anni_rimanenti += 1
                             p.contract.team_option = False
                             options_exercised += 1
                             options_log.append({"name": p.nome, "team": squadra.nome, "kind": "team", "decision": "in"})
                        else:
                             main_log.info(f"[TO DECLINE] {squadra.nome} decline the TO on {p.nome} (${current_salary:.1f}M). Reason: {reason}")
                             # Decline -> Expires -> FA
                             options_declined += 1
                             p.contract.team_option = False
                             options_log.append({"name": p.nome, "team": squadra.nome, "kind": "team", "decision": "out"})

        main_log.info(f"Options Report: {options_exercised} Exercised, {options_declined} Declined.")

# --- NEW SETUP AND DATA EXPORT FUNCTIONS ---

def caricamento_squadre() -> Tuple[List[Squadra], List[Giocatore]]:
    """
    ### REWORKED (v22.0 - English DB Migration) ###
    Loads the data from the DB with English columns and maps the roles to the engine's format.
    """
    main_log.info("Loading data from the nba_sim.db database...")
    lista_squadre = []
    lista_free_agents = []
    
    # DB roles may be English or legacy Italian: normalize to the English standard (core/roles.py)
    
    registry = get_active_registry()

    try:
        db_teams = db_manager.load_teams()
        for team_data in db_teams:
            team_name = team_data['name']

            # Conference and franchise id from the active league; an old DB has no franchise_id column
            team_id = team_data.get('franchise_id') or ''
            franchise = registry.by_id(team_id) if team_id else None
            if franchise is None:
                franchise = registry.by_name(team_name)
            squadra_conference = franchise.conference if franchise else None
            if squadra_conference is None:
                main_log.warning(f"Conference not found for '{team_name}'. The team will not take part in a conference.")

            squadra = Squadra(
                nome=team_name,
                conference=squadra_conference,
                team_id=team_id
            )
            # Curated owner personality from the era DB (if any); used by assegna_personalita_proprietari
            squadra._db_owner_personality = normalize_owner_personality(team_data.get('owner_personality'))
            
            db_players = db_manager.load_players_for_team(team_data['id'])
            for player_data in db_players:
                player_id = player_data['id']
                
                abilities_data = db_manager.load_abilities(player_id)
                tendencies_data = db_manager.load_tendencies(player_id)

                if not abilities_data or not tendencies_data:
                    main_log.warning(f"Missing ability or tendency data for player ID {player_id} ({player_data['name']}). Skipping.")
                    continue
                
                abilities_data.pop('player_id', None)
                tendencies_data.pop('player_id', None)
                
                abilita = Abilita(**abilities_data)
                tendenze = Tendenze(**tendencies_data)
                
                # Map role from DB format to engine format
                db_role = player_data['role']
                engine_role = normalize_role(db_role)
                
                giocatore = Giocatore(
                    db_id=player_data['id'],
                    squadra=squadra,
                    nome=player_data['name'],
                    ruolo=engine_role,
                    eta=player_data['age'],
                    valutazione=player_data['overall'],
                    potenziale=player_data['potential'],
                    provenance=player_data.get('provenance', 'Unknown'),
                    pedigree=player_data.get('pedigree', 'Unknown'),
                    abilita=abilita,
                    tendenze=tendenze
                )
                # Read once by tag_season1_rookies (then removed): contracts set anni_nella_squadra again
                giocatore._start_years_on_team = player_data.get('years_on_team') or 0
                squadra.roster.append(giocatore)
            
            lista_squadre.append(squadra)

        # Loading the free agents
        db_free_agents = db_manager.load_free_agents()
        for player_data in db_free_agents:
            player_id = player_data['id']
            abilities_data = db_manager.load_abilities(player_id)
            tendencies_data = db_manager.load_tendencies(player_id)
            if not abilities_data or not tendencies_data: continue

            abilities_data.pop('player_id', None)
            tendencies_data.pop('player_id', None)
            abilita = Abilita(**abilities_data)
            tendenze = Tendenze(**tendencies_data)

            db_role = player_data['role']
            engine_role = normalize_role(db_role)

            free_agent = Giocatore(
                squadra=None, nome=player_data['name'], ruolo=engine_role,
                eta=player_data['age'], valutazione=player_data['overall'],
                potenziale=player_data['potential'], provenance=player_data.get('provenance', 'Unknown'),
                pedigree=player_data.get('pedigree', 'Unknown'), abilita=abilita, tendenze=tendenze
            )
            lista_free_agents.append(free_agent)


        main_log.info("Database loading completed successfully.")
        return lista_squadre, lista_free_agents

    except Exception as e:
        main_log.critical(f"CRITICAL ERROR while loading from the database: {e}", exc_info=True)
        sys.exit(1)

def assegna_contratti_iniziali(squadre: List[Squadra], torneo: Optional['Tournament'] = None):
    """
    REWORKED (v2.7 - Day 1 Era-Aware Economy Balance & Cap Scaling):
    Assigns the contracts simulating a real NBA league, distinguishing between the Historical Era (e.g. 2002) and the Modern Era (2025):
    - Uses the tournament's active cap, year and CBA rules (or DB fallback).
    - Avoids rookie discounts for young superstars (ovr >= 84).
    - Scales the contracts identically to _calcola_valore_di_mercato, free agency and extensions.
    """
    main_log.info("Assigning initial contracts (Day 1 Balancing)...")
    cfg_eco = CONFIG.ECONOMY
    
    # 1. Retrieve the tournament parameters or fallback
    if torneo is None and len(squadre) > 0 and getattr(squadre[0], 'torneo', None):
        torneo = squadre[0].torneo
        
    YEARLY_SALARY_CAPS = {
        2002: 40.27, 2003: 43.84, 2004: 43.87, 2005: 49.50,
        2006: 53.13, 2007: 55.63, 2008: 58.68, 2009: 57.70,
        2010: 58.04, 2011: 58.04, 2012: 58.04, 2013: 58.68,
        2014: 63.06, 2015: 70.00, 2016: 94.14, 2017: 99.09,
        2018: 101.87, 2019: 109.14, 2020: 109.14, 2021: 112.41,
        2022: 123.65, 2023: 136.02, 2024: 140.58, 2025: 155.00
    }
    
    raw_cap = getattr(torneo, 'salary_cap', None) if torneo else None
    anno = getattr(torneo, 'anno_corrente', None) or getattr(torneo, 'starting_year', None) if torneo else None
    cba_mode = getattr(torneo, 'cba_mode', 'realistic') if torneo else 'realistic'
    
    if anno is None or raw_cap is None:
        # Fallback via DB inspection
        is_2002 = current_league_era() == "2002"
        anno = 2002 if is_2002 else 2025
        raw_cap = YEARLY_SALARY_CAPS.get(anno, 155.0)

    is_no_cap = (cba_mode == 'no_cap') or (raw_cap >= 9000.0)
    cap = YEARLY_SALARY_CAPS.get(anno, 155.0) if is_no_cap else raw_cap
    is_historical = (anno < 2023) or (cap < 80.0)
    scale_factor = cap / 155.0

    for squadra in squadre:
        for giocatore in squadra.roster:
            negotiation_ovr = giocatore.effective_ovr
            
            # Realistic NBA salary tiers by Era (aligned with core/models.py _calcola_valore_di_mercato)
            if is_historical:
                # Classic Era / Pre-Apron (2002-2022):
                if negotiation_ovr >= 93:
                    tier_pct = (0.32, 0.38)   # Classic Supermax (32% - 38%)
                elif negotiation_ovr >= 88:
                    tier_pct = (0.26, 0.32)   # All-Star Max (26% - 32%)
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
                # Modern Era (2023+ CBA with 1st and 2nd Apron)
                if negotiation_ovr >= 93:
                    tier_pct = (0.30, 0.35)   # Supermax (~$46.5M - $54.2M)
                elif negotiation_ovr >= 88:
                    tier_pct = (0.25, 0.30)   # Max Player (~$38.7M - $46.5M)
                elif negotiation_ovr >= 84:
                    tier_pct = (0.20, 0.25)   # Star / All-Star (~$31.0M - $38.7M)
                elif negotiation_ovr >= 80:
                    tier_pct = (0.15, 0.20)   # Solid Starter (~$23.2M - $31.0M)
                elif negotiation_ovr >= 76:
                    tier_pct = (0.09, 0.14)   # Rotation / 6th Man (~$14.0M - $21.7M)
                elif negotiation_ovr >= 72:
                    tier_pct = (0.05, 0.085)  # Bench (~$7.8M - $13.2M)
                elif negotiation_ovr >= 68:
                    tier_pct = (0.028, 0.048) # Deep Bench (~$4.3M - $7.4M)
                else:
                    tier_pct = (0.015, 0.024) # Deep Bench / Minimo (~$2.3M - $3.7M)

            min_pct, max_pct = tier_pct

            # Continuous grading within the OVR tier
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

            # Day 1 Modifiers:
            # A. Rookie scale (only for young players who are not yet superstars: ovr < 84 and (eta <= 22 or is_rookie))
            # Scales in dynamic proportion to the active Cap instead of fixed values
            is_rookie_scale = (giocatore.ovr < 84) and (giocatore.eta <= 22 or getattr(giocatore, 'is_rookie', False))
            if is_rookie_scale:
                scale_to_modern = cap / 155.0
                if giocatore.ovr >= 78:
                    salario_base = random.uniform(6.5, 10.0) * scale_to_modern
                elif giocatore.ovr >= 74:
                    salario_base = random.uniform(3.5, 6.5) * scale_to_modern
                else:
                    salario_base = random.uniform(1.8, 3.5) * scale_to_modern
            # B. Veteran Discount (Ring Chasers at the end of their careers)
            elif giocatore.eta >= 34 and giocatore.ovr < 85:
                salario_base *= 0.80

            # Absolute NBA limits
            min_sal = max(0.9, round(3.5 * scale_factor, 1)) if is_historical else cfg_eco.MIN_SALARY
            max_pct_cap = 0.40 if is_historical else 0.35
            salario_assegnato = min(cap * max_pct_cap, max(min_sal, salario_base))
            salario_assegnato = round(salario_assegnato, 1)

            # 1. Initial contract length (staggered Day 1)
            if giocatore.eta >= 38:
                anni = 1
            elif 35 <= giocatore.eta <= 37:
                anni = random.choice([1, 2])
            elif giocatore.eta <= 23:
                anni = random.choice([2, 3, 4])
            elif giocatore.ovr >= 84 and (26 <= giocatore.eta <= 32):
                anni = random.choice([2, 3, 4])
            else:
                anni = random.choice([1, 2, 3, 4])

            giocatore.contract = Contract(
                anni_rimanenti=anni,
                salario_annuale=salario_assegnato,
                player_option=False,
                team_option=False
            )
            
            # 2. Apply the automated logic (Years + PO / TO / Guaranteed Options)
            applica_regole_anni_opzioni_contratto(giocatore)
            giocatore.anni_nella_squadra = random.randint(1, 3)

        # Control log
        main_log.info(f"Team: {squadra.nome}, Initial Payroll: ${squadra.payroll:.1f}M")
        for giocatore in squadra.roster:
            main_log.info(f"Player: {giocatore.nome}, contract: {giocatore.contract}")

def _inject_draft_class_to_teams(torneo: 'Tournament', season_year: int):
    """
    Looks for a JSON file for the draft class of the specified year and injects the players
    into their respective destination teams.
    """
    filepath = draft_class_file(torneo, season_year)
    
    if not filepath:
        main_log.info(f"No custom draft class found for year {season_year}. Skipping injection.")
        return

    main_log.info(f"Draft class {season_year} found. Injecting the rookies into the rosters...")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            rookie_data_list = json.load(f)
            
        rookie_contracts_created = 0
        for rookie_info in rookie_data_list:
            team_name = rookie_info.get("squadra_destinazione")
            if not team_name:
                main_log.warning(f"Rookie '{rookie_info.get('nome')}' in the JSON file has no 'squadra_destinazione'. Skipping.")
                continue

            target_team = next((s for s in torneo.squadre if s.nome == team_name), None)
            
            if not target_team:
                main_log.warning(f"Team '{team_name}' not found for rookie '{rookie_info.get('nome')}'. Skipping.")
                continue

            # Create the complete Giocatore object
            abilita = Abilita(**rookie_info.get("abilita", {}))
            tendenze = Tendenze(**rookie_info.get("tendenze", {}))
            
            rookie = Giocatore(
                nome=rookie_info.get("nome", "Unknown Rookie"),
                ruolo=normalize_role(rookie_info.get("ruolo")) or "SG",
                eta=19,
                valutazione=rookie_info.get("valutazione", 60),
                potenziale=rookie_info.get("potenziale", 70),
                abilita=abilita,
                tendenze=tendenze,
                squadra=target_team,
                provenance=rookie_info.get("provenance", f"{season_year} Draft Class"),
                pedigree=rookie_info.get("pedigree", "Real Prospect")
            )
            rookie.is_rookie = True  # Tag rookies for the end-of-season awards
            # Assign a rookie contract (simplified logic)
            salario_rookie = CONFIG.ECONOMY.ROOKIE_SALARY_SCALE.get(15, 2.5) # Default for a mid-first-round pick
            from core.models import ACTIVE_TOURNAMENT
            if ACTIVE_TOURNAMENT:
                cap_ratio = ACTIVE_TOURNAMENT.salary_cap / 155.0
                salario_rookie = max(0.9, round(salario_rookie * cap_ratio, 2))
            rookie.contract = Contract(anni_rimanenti=4, salario_annuale=salario_rookie)
            applica_regole_anni_opzioni_contratto(rookie)
            rookie.anni_nella_squadra = 0 # He has just arrived
            
            # Add to the roster
            target_team.roster.append(rookie)
            rookie_contracts_created +=1
            
        main_log.info(f"Injection completed: {rookie_contracts_created} rookies from {season_year} added to the rosters.")

    except (json.JSONDecodeError, KeyError) as e:
        main_log.error(f"Error while reading or processing {filepath}: {e}")


def _populate_roster_depth(torneo: 'Tournament', filepath: str, target_size: int):
    """
    Fills the team rosters up to a target size using a pool of "filler" players.
    """
    if not os.path.exists(filepath):
        main_log.warning(f"Filler players file '{filepath}' not found. Skipping the roster filling.")
        return

    main_log.info(f"Filling the rosters up to {target_size} players using '{filepath}'...")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            filler_data_list = json.load(f)

        # Create all the Giocatore objects and put them in a pool
        filler_pool = []
        for filler_info in filler_data_list:
            abilita = Abilita(**filler_info.get("abilita", {}))
            tendenze = Tendenze(**filler_info.get("tendenze", {}))
            filler_player = Giocatore(
                nome=filler_info.get("nome", "Generic Player"),
                ruolo=normalize_role(filler_info.get("ruolo")) or "SG",
                eta=filler_info.get("eta", 25),
                valutazione=filler_info.get("valutazione", 70),
                potenziale=filler_info.get("potenziale", 72),
                abilita=abilita,
                tendenze=tendenze,
                squadra=None, # No team at the start
                provenance="Filler Pool",
                pedigree="Journeyman"
            )
            filler_pool.append(filler_player)
        
        random.shuffle(filler_pool)
        
        players_added = 0
        for squadra in torneo.squadre:
            while len(squadra.roster) < target_size:
                if not filler_pool:
                    main_log.warning("Filler player pool exhausted. Some teams may be left with short rosters.")
                    break
                
                player_to_add = filler_pool.pop()
                player_to_add.squadra = squadra
                
                # Assign a minimum contract
                player_to_add.contract = Contract(
                    anni_rimanenti=1, 
                    salario_annuale=torneo.min_salary
                )
                player_to_add.anni_nella_squadra = 0
                
                squadra.roster.append(player_to_add)
                players_added += 1
            
            if not filler_pool:
                break # Also exit the team loop if the players have run out

        main_log.info(f"Filling completed: {players_added} players added to reach the roster depth.")

    except (json.JSONDecodeError, KeyError) as e:
        main_log.error(f"Error while reading or processing {filepath}: {e}")

def assegna_personalita_proprietari(squadre: List[Squadra]):
    # Teams with a curated owner in the era DB keep it; the others draw from OWNER_DISTRIBUTION.
    tipi = list(CONFIG.ECONOMY.OWNER_DISTRIBUTION)
    random.shuffle(tipi)
    for squadra in squadre:
        db_tipo = getattr(squadra, '_db_owner_personality', None)
        if db_tipo:
            squadra.personalita_proprietario = db_tipo
        else:
            squadra.personalita_proprietario = tipi.pop() if tipi else "Bilanciato"
        #main_log.info(f"Owner of {squadra.nome} is of type: {tipo}")
def run_full_season_cycle(torneo: 'Tournament'):
    """
    Runs a complete cycle of a season, from the regular season to the preparation of the next one.
    UPDATED for the new Trade v2.0 system
    """
    print(f"\n==================== AUTO-SIM: START OF SEASON CYCLE {torneo.season_number} ====================", flush=True)
    main_log.info(f"\n{'='*20} AUTO-SIM: START OF SEASON CYCLE {torneo.season_number} {'='*20}")

    # 1. Regular Season (Already includes the Mid-Season Trade Deadline at 50% of the games)
    print(f"🏀 AUTO-SIM (Season {torneo.season_number}): Regular Season simulation in progress...", flush=True)
    main_log.info(f"--- AUTO-SIM: Regular Season simulation... ---")
    torneo.simula_regular_season()
    
    # Snapshot payroll inizio offseason
    start_payroll_map = {team.nome: round(team.payroll, 1) for team in torneo.squadre}

    # 2. Playoffs (simulates all rounds in one go)
    print(f"🏆 AUTO-SIM (Season {torneo.season_number}): Playoffs simulation...", flush=True)
    main_log.info(f"--- AUTO-SIM: Playoffs simulation... ---")
    torneo._setup_playoffs()
    while torneo.playoff_state != "COMPLETE":
        torneo.simula_turno_playoff()

    if torneo.campione:
        print(f"🥇 SEASON {torneo.season_number} CHAMPIONS: {torneo.campione.nome} | FINALS MVP: {torneo.finals_mvp.nome if torneo.finals_mvp else 'N/A'}", flush=True)

    # 3. Offseason Completa
    print(f"📅 AUTO-SIM (Season {torneo.season_number}): Offseason start (Retirements, Draft, Free Agency)...", flush=True)
    for team in torneo.squadre:
        team.financial_summary = {
            "start_offseason_payroll": start_payroll_map.get(team.nome, 0),
            "end_offseason_payroll": 0,
            "events": []
        }

    # A. Progression, Retirements & Firings
    nuovi_fa, squadre_precedenti_fa_map = torneo.start_offseason_progression()
    torneo._gestisci_fase_licenziamenti()

    # B. Coach Hiring
    torneo._gestisci_fase_assunzioni()
    
    # C. Expiring Contracts Log
    for squadra in torneo.squadre:
        giocatori_in_scadenza = [p for p in squadra.roster if p.contract and p.contract.anni_rimanenti <= 0]
        if giocatori_in_scadenza:
            payroll_freed = sum(p.contract.salario_annuale for p in giocatori_in_scadenza)
            squadra.log_financial_event("Expired Contracts", -payroll_freed, f"{len(giocatori_in_scadenza)} players became free agents.")

    # D. PRE-DRAFT TRADES
    main_log.info("--- AUTO-SIM: Start of the Pre-Draft Trades Phase ---")
    torneo.esegui_draft_lottery()
    torneo.trade_period_predraft()

    # E. Draft
    draft_instance = Draft(torneo, torneo.squadre, None)
    draft_logs = draft_instance.esegui_o_continua_draft()
    torneo.offseason_log_data['draft'] = draft_logs
    for pick in draft_logs:
        torneo.podcast_logger.log_draft_pick(pick)

    # Log Draft Signings
    for team in torneo.squadre:
        new_rookies = [p for p in team.roster if p.eta == 19 and p.anni_nella_squadra == 0]
        if new_rookies:
            rookie_payroll = sum(r.contract.salario_annuale for r in new_rookies)
            team.log_financial_event("Draft Signings", rookie_payroll, f"Signed {len(new_rookies)} rookies.")

    # F. Free Agency
    tutti_i_free_agent = nuovi_fa + torneo.free_agents_pool
    nomi_visti = set()
    free_agents_unici = [fa for fa in tutti_i_free_agent if fa.nome not in nomi_visti and not nomi_visti.add(fa.nome)] # type: ignore

    free_agency_instance = FreeAgency(torneo, torneo.squadre, free_agents_unici, squadre_precedenti_fa_map, None)
    fa_logs = free_agency_instance.esegui_free_agency()
    torneo.offseason_log_data['free_agency'] = fa_logs
    for signing in fa_logs:
        torneo.podcast_logger.log_free_agency_signing(signing)

    # Post-FA cleanup (Retire the poor veterans and the busts left unsigned)
    torneo._pulizia_post_free_agency(free_agency_instance.unrestricted_free_agents)

    # Update and retire the coaches before the HOF
    torneo._gestisci_progressione_coach()

    # G. HOF Elections (Every year at the end of the offseason)
    if torneo.season_number > 0:
        torneo.eleggi_classe_hof()

    # H. Roster Cuts
    torneo._gestisci_fase_tagli_roster()

    # Finalize Financials
    for team in torneo.squadre:
        team.financial_summary['end_offseason_payroll'] = round(team.payroll, 1)

    # Export the completed JSON data for the Podcast
    torneo.podcast_logger.export_to_json()

    # 4. New Season Preparation
    main_log.info(f"--- AUTO-SIM: Preparing Season {torneo.season_number + 1}... ---")
    torneo._age_draft_picks()
    torneo._fade_rivalries()
    torneo.season_number += 1
    torneo.box_scores = {}  # as the server's new-season step does: last season's games must not count in the next one
    torneo._gestisci_crescita_economica() # type: ignore
    checkpoint_new_season(torneo)  # GMs age; team plans reviewed (the champion is still known here)
    
    # Reset draft variables for the new season
    if hasattr(torneo, 'draft_pick_corrente'):
        delattr(torneo, 'draft_pick_corrente')
    if hasattr(torneo, 'draft_risultati'):
        delattr(torneo, 'draft_risultati')
    if hasattr(torneo, 'draft_class'):
        delattr(torneo, 'draft_class')
    if hasattr(torneo, 'draft_lottery_order'):
        delattr(torneo, 'draft_lottery_order')
        
    inizializza_scouting_e_classe_draft(torneo)
    
    # Auto-generate trade block offers for the new season if player team exists
    if torneo.squadra_giocatore:
        from trades.trade_block_manager import TradeBlockManager
        torneo.pending_trade_block_offers = TradeBlockManager.generate_offers(
            torneo, torneo.squadra_giocatore
        )
    
    # Reset tournament variables
    torneo.regular_season_mvp = None
    torneo.finals_mvp = None
    torneo.campione = None
    torneo.playoff_bracket_data = None
    torneo.offseason_log_data = {}
    torneo.playoff_state = "NOT_STARTED"
    
    # Reset Awards
    torneo.defensive_player_of_the_year = None
    torneo.sesto_uomo = None
    torneo.rookie_of_the_year = None
    torneo.coach_of_the_year = None
    torneo.gm_of_the_year = None
    torneo.all_nba_teams = []
    torneo.all_defensive_team = []
    torneo.all_rookie_team = []
    
    # Reset All-Star Weekend data
    torneo.reset_all_star_weekend()
    
    # Reset Play-In Tournament data
    torneo.play_in_teams = {'east': [], 'west': []}
    torneo.direct_qualifiers = {'east': [], 'west': []}
    torneo.play_in_results = {'east': {}, 'west': {}}
    torneo.play_in_game_index = 0
    torneo.playoff_teams = {'east': [], 'west': []}
    torneo.next_round_teams = {'east': [], 'west': []}
    
    # Reset internal simulation flags
    torneo._first_half_complete = False
    torneo._current_gameday = 0
    torneo._trade_deadline_completed = False
    
    # Reset caches (free agency optimization cache)
    if hasattr(torneo, '_careers_cache'):
        del torneo._careers_cache
    
    # Create new PodcastLogger for the new season
    torneo.podcast_logger = PodcastLogger(torneo.season_number)
    
    for squadra in torneo.squadre:
        squadra.reset_record_stagionale()
    refresh_untouchables(torneo)   # draft-night flags and last season's cores must not pile up

    torneo.genera_calendario()
    torneo.imposta_rotazioni_stagione()

    main_log.info(f"{'='*20} AUTO-SIM: SEASON CYCLE COMPLETED. NEW SEASON: {torneo.season_number} {'='*20}\n")

def _run_expansion_draft(torneo: 'Tournament'):
    """
    Fills the empty teams (Expansion) by drawing from the Free Agents pool
    or generating filler players if necessary.
    """
    squadre_vuote = [s for s in torneo.squadre if len(s.roster) == 0]
    
    if not squadre_vuote:
        return

    main_log.info(f"--- EXPANSION DRAFT: Found {len(squadre_vuote)} new teams to populate ---")
    
    # We load a pool of generic players for safety (as a fallback)
    # You can use the existing _populate_roster_depth function or create a variant here
    
    # 1. First we try to take the best available Free Agents (the "leftovers" of the other teams)
    # We sort the FAs by OVR to give immediate competitiveness
    fa_disponibili = sorted(torneo.free_agents_pool, key=lambda p: p.ovr, reverse=True)
    
    for squadra in squadre_vuote:
        main_log.info(f"Populating the roster for {squadra.nome}...")
        
        # Target: 14 players
        players_needed = 12
        
        # We take the first N from the FA pool
        if len(fa_disponibili) >= players_needed:
            picks = fa_disponibili[:players_needed]
            # We remove them from the global pool
            fa_disponibili = fa_disponibili[players_needed:]
            
            # We assign them to the team
            for p in picks:
                p.squadra = squadra
                # We assign "Expansion" contracts (2-3 years at reasonable prices)
                salario = p._calcola_valore_di_mercato() * 0.9 # Expansion discount
                p.contract = Contract(anni_rimanenti=random.randint(2,3), salario_annuale=salario)
                p.anni_nella_squadra = 0
                squadra.roster.append(p)
                if p in torneo.free_agents_pool:
                    torneo.free_agents_pool.remove(p)
        else:
            # If there are not enough FAs, we use the fillers (the existing function)
            main_log.warning(f"Not enough FAs for {squadra.nome}. Generating fillers...")
            _populate_roster_depth(torneo, "filler_players.json", 14)

    main_log.info("--- EXPANSION DRAFT COMPLETED ---")

def role_can_shoot_3s(ruolo: str) -> bool:
    return ruolo in ['PG', 'SG', 'SF']

def genera_statistiche_college(giocatore: 'Giocatore') -> dict:
    import random
    ruolo = giocatore.ruolo
    abilita = giocatore.abilita
    
    # Base values computed from the player's hidden attributes
    base_pts = 10.0 + (abilita.three_point_shot_rating - 50) * 0.18 + (abilita.close_shot_rating - 50) * 0.15 + (abilita.mid_range_shot_rating - 50) * 0.12
    base_reb = 2.0 + (abilita.defensive_rebound_rating - 50) * 0.15 + (abilita.offensive_rebound_rating - 50) * 0.05
    base_ast = 1.0 + (abilita.passing_vision - 50) * 0.15 + (abilita.passing_accuracy - 50) * 0.05
    base_stl = 0.5 + (abilita.steal_rating - 50) * 0.05
    base_blk = 0.2 + (abilita.block_rating - 50) * 0.08
    
    # Modifiers based on the role
    if ruolo in ['PG']:
        base_pts += 1.5
        base_ast += 3.5
        base_reb -= 0.5
    elif ruolo in ['SG']:
        base_pts += 3.5
        base_ast += 1.0
        base_reb += 0.5
    elif ruolo in ['SF']:
        base_pts += 2.5
        base_reb += 1.5
        base_ast += 0.5
    elif ruolo in ['PF']:
        base_pts += 0.5
        base_reb += 4.0
        base_blk += 0.8
    elif ruolo == 'C':
        base_pts -= 1.0
        base_reb += 5.5
        base_blk += 1.4
        
    # Percentuali
    fg_pct = 40.0 + (abilita.close_shot_rating - 50) * 0.2 + random.uniform(-3, 3)
    fg_pct = max(35.0, min(65.0, fg_pct))
    
    tp_pct = 0.0
    if role_can_shoot_3s(ruolo) or abilita.three_point_shot_rating > 60:
        tp_pct = 28.0 + (abilita.three_point_shot_rating - 50) * 0.25 + random.uniform(-4, 4)
        tp_pct = max(20.0, min(48.0, tp_pct))
        
    pts = max(5.0, base_pts + random.uniform(-2.5, 2.5))
    reb = max(1.0, base_reb + random.uniform(-1.2, 1.2))
    ast = max(0.5, base_ast + random.uniform(-0.8, 0.8))
    stl = max(0.1, base_stl + random.uniform(-0.25, 0.25))
    blk = max(0.0, base_blk + random.uniform(-0.15, 0.15))
    
    return {
        'pts': round(pts, 1),
        'reb': round(reb, 1),
        'ast': round(ast, 1),
        'stl': round(stl, 1),
        'blk': round(blk, 1),
        'fg_pct': f"{fg_pct:.1f}%",
        'tp_pct': f"{tp_pct:.1f}%" if tp_pct > 0 else "0.0%"
    }

def inizializza_scouting_e_classe_draft(torneo: 'Tournament'):
    """
    Initializes the draft class (college stats included) and the scouting staff
    at the start of every regular season.
    """
    from offseason.draft import Draft
    import random
    main_log.info(f"--- SCOUTING & DRAFT CLASS INITIALIZATION FOR SEASON {torneo.season_number} ---")
    
    # Generate the draft class using the standard procedural generator
    draft_instance = Draft(torneo, torneo.squadre, torneo.squadra_giocatore)
    classe_draft = draft_instance._carica_o_genera_classe_draft()
    
    # Genera statistiche college, resetta progresso di scouting e stock
    for prospect in classe_draft:
        prospect.college_stats = genera_statistiche_college(prospect)
        prospect.scouting_progress = 10.0  # Base knowledge at 10%
        prospect.draft_stock_mod = 0.0
        
    torneo.draft_class = classe_draft
    
    # Initialize the scouting staff (Senior, Junior, International)
    torneo.scout_staff = [
        {"name": "Jack Vance", "accuracy": "A", "speed": "B", "assigned_to": None},
        {"name": "Sarah Jenkins", "accuracy": "B", "speed": "A", "assigned_to": None},
        {"name": "Elena Rostova", "accuracy": "C", "speed": "C", "assigned_to": None}
    ]
    torneo.scouting_workouts_left = 5
    main_log.info(f"Draft class generated ({len(classe_draft)} prospects) and scouting staff initialized.")

def setup_simulation(league_settings: Optional[Dict[str, Any]] = None,
                     league_meta: Optional[Dict[str, Any]] = None,
                     franchise_registry: Any = None) -> Tournament:
    """
    v22.0 - Season 25/26 start. No expansion draft, no 2024 draft injection.

    `league_meta` / `franchise_registry`: the league this save plays (a new career's league, or a loaded save's
    stored one). They go on the Tournament before any draft-class read, so a league save never takes the
    old-save branch of core/league/draft_source.py (which reads the Real Names 2002 mod's classes).
    """
    squadre, free_agents_iniziali = caricamento_squadre()
    
    assegna_personalita_proprietari(squadre)
    genera_e_assegna_coach_iniziali(squadre)
    
    torneo = Tournament(squadre, league_settings=league_settings)
    torneo.league_meta = dict(league_meta or {})
    if franchise_registry is not None:
        torneo.franchise_registry = franchise_registry
    torneo.free_agents_pool = free_agents_iniziali

    # Assign contracts using the tournament (with the historical cap, starting_year and cba_mode precisely)
    squadre_con_roster = [s for s in squadre if len(s.roster) > 0]
    assegna_contratti_iniziali(squadre_con_roster, torneo=torneo)
    
    # Season 1 = 2025-26, first draft at end of season = DRAFT_2026
    # No expansion draft needed - all 30 NBA teams are pre-populated
    
    # === SEASON 1 ROOKIE TAGGING ===
    try:
        tagged_count, source = tag_season1_rookies(torneo)
        main_log.info(f"Season 1 Rookies: {tagged_count} players tagged as rookies ({source}).")
    except Exception as e:
        main_log.error(f"Error tagging the Season 1 rookies: {e}")
    
    torneo.imposta_rotazioni_stagione()

    for squadra in torneo.squadre:
        squadra.team_goal = torneo._determina_stato_squadra(squadra)
        squadra.designa_intoccabili(torneo)
        for player in squadra.roster:
            player.calcola_pvs()
            
    inizializza_scouting_e_classe_draft(torneo)

    # CPU GMs for every team. No user team exists yet: the new-league route rebuilds this once it is chosen,
    # and loading a save replaces it with the saved one.
    torneo.front_office = build_front_office(torneo)
    ensure_season_marks(torneo, torneo.front_office)
    return torneo

def _get_player_details(player: Giocatore) -> dict:
    from dataclasses import asdict
    pg_rs = player.season_stats.partite_giocate or 1
    pg_po = player.playoff_stats.partite_giocate or 1
    
    contract_str = "N/A"
    contract_data = None
    
    if player.contract:
        c_val = f"${player.contract.salario_annuale}M / {player.contract.anni_rimanenti}y"
        if getattr(player.contract, 'player_option', False):
            c_val += " (PO)"
        elif getattr(player.contract, 'team_option', False):
            c_val += " (TO)"
        contract_str = c_val
        
        contract_data = {
            "salary": player.contract.salario_annuale,
            "years": player.contract.anni_rimanenti,
            "player_option": getattr(player.contract, 'player_option', False),
            "team_option": getattr(player.contract, 'team_option', False)
        }

    abilita_dict = asdict(player.abilita) if hasattr(player, 'abilita') and player.abilita and hasattr(player.abilita, '__dataclass_fields__') else (player.abilita if isinstance(getattr(player, 'abilita', None), dict) else {})
    tendenze_dict = asdict(player.tendenze) if hasattr(player, 'tendenze') and player.tendenze and hasattr(player.tendenze, '__dataclass_fields__') else (player.tendenze if isinstance(getattr(player, 'tendenze', None), dict) else {})

    try:
        from core.player_lore import generate_player_lore
        lore_dict = generate_player_lore(player, getattr(player, 'squadra', None))
    except Exception:
        lore_dict = {"role_badge": "Giocatore", "career_phase": "", "status_narrative": ""}

    return {
        "id": player.nome.replace(" ", "-").lower(),
        "nome": player.nome,
        "squadra": player.squadra.nome if player.squadra else "Free Agent",
        "ruolo": player.ruolo,
        "ruolo_secondario": getattr(player, 'ruolo_secondario', None),
        "eta": player.eta,
        "ovr": player.ovr,
        "pot": player.potenziale,
        "potenziale": player.potenziale,
        "contratto": contract_str,
        "contract_data": contract_data,
        "anni_nella_squadra": getattr(player, 'anni_nella_squadra', 1),
        "stamina_stagionale": getattr(player, 'stamina_stagionale', 100.0),
        "morale": getattr(player, 'morale', 85),
        "trade_request": bool(getattr(player, 'trade_request', False)),   # asked to be traded
        "abilita": abilita_dict,
        "tendenze": tendenze_dict,
        "valutazioni_posizionali": getattr(player, 'valutazioni_posizionali', {}),
        "infortunato": getattr(player, 'infortunato', False),
        "tipo_infortunio": getattr(player, 'infortunio_nome', getattr(player, 'tipo_infortunio', None)),
        "infortunio_nome": getattr(player, 'infortunio_nome', getattr(player, 'tipo_infortunio', None)),
        "is_day_to_day": getattr(player, 'is_day_to_day', False),
        "infortunio_impatto": getattr(player, 'infortunio_impatto', 0.0),
        "giorni_infortunio_rimanenti": getattr(player, 'giorni_infortunio_rimanenti', 0),
        "lore": lore_dict,
        "on_trade_block": getattr(player, 'on_trade_block', False),
        "is_untouchable": getattr(player, 'is_untouchable', False),
        "gp_rs": player.season_stats.partite_giocate,
        "gp_po": player.playoff_stats.partite_giocate,
        "stats_rs": {
            "ppg": round(player.season_stats.punti / pg_rs, 1),
            "rpg": round(player.season_stats.rimbalzi / pg_rs, 1),
            "apg": round(player.season_stats.assist / pg_rs, 1),
            "spg": round(player.season_stats.steals / pg_rs, 1),
            "bpg": round(player.season_stats.blocks / pg_rs, 1),
            "fg_pct": player.season_stats.fg_pct,
            "three_pct": player.season_stats.three_pct,
            "ft_pct": player.season_stats.ft_pct,
        },
        "last_progression": getattr(player, 'last_progression', None),
        "premi": getattr(player, 'premi', []),
        "anelli_vinti": getattr(player, 'anelli_vinti', 0),
        "ovr_history": getattr(player, 'ovr_history', []),
        "stats_po": {
            "ppg": round(player.playoff_stats.punti / pg_po, 1),
            "rpg": round(player.playoff_stats.rimbalzi / pg_po, 1),
            "apg": round(player.playoff_stats.assist / pg_po, 1),
            "spg": round(player.playoff_stats.steals / pg_po, 1),
            "bpg": round(player.playoff_stats.blocks / pg_po, 1),
            "fg_pct": player.playoff_stats.fg_pct,
            "three_pct": player.playoff_stats.three_pct,
            "ft_pct": player.playoff_stats.ft_pct,
        } if player.playoff_stats.partite_giocate > 0 else None
    }

def team_future_picks(torneo: 'Tournament', squadra) -> list:
    """The next five drafts for one team: picks it holds (own or via others) and its own picks held by others."""
    future_picks = []
    for pick_year in range(1, 6):
        starting_year = getattr(torneo, 'starting_year', 2025)
        draft_year = starting_year + torneo.season_number + pick_year - 1
        
        owned_picks = []
        for pick_key, owner in torneo.pick_ownership.get(pick_year, {}).items():
            if owner == squadra.nome:
                parts = pick_key.split("-", 1)
                rnd = parts[0]
                orig_owner = parts[1] if len(parts) > 1 else "Unknown"
                prot = torneo.pick_protections.get(pick_year, {}).get(pick_key, "Unprotected")
                owned_picks.append({
                    "round": 1 if rnd == "R1" else 2,
                    "original_owner": orig_owner,
                    "is_own": orig_owner == squadra.nome,
                    "protection": prot
                })
        owned_picks.sort(key=lambda x: x["round"])
        
        traded_picks = []
        for rnd in ["R1", "R2"]:
            pick_key = f"{rnd}-{squadra.nome}"
            current_owner = torneo.pick_ownership.get(pick_year, {}).get(pick_key)
            if current_owner and current_owner != squadra.nome:
                prot = torneo.pick_protections.get(pick_year, {}).get(pick_key, "Unprotected")
                traded_picks.append({
                    "round": 1 if rnd == "R1" else 2,
                    "current_owner": current_owner,
                    "protection": prot
                })
        
        future_picks.append({
            "year": draft_year,
            "year_offset": pick_year,
            "owned": owned_picks,
            "traded": traded_picks
        })
    return future_picks


def get_league_database(torneo: 'Tournament') -> dict:
    """
    Creates a complete "database" of the league with teams and players.
    ### FIX v10.3: Ensures the global list of players is sorted by OVR. ###
    """
    squadre_data = []
    # Sort the teams alphabetically for a consistent display
    for squadra in sorted(torneo.squadre, key=lambda s: s.nome):
        future_picks = team_future_picks(torneo, squadra)

        squadre_data.append({
            "id": squadra.nome.replace(" ", "-").lower(),
            "nome": squadra.nome,
            "record": f"{squadra.vittorie}-{squadra.sconfitte}",
            "payroll": round(squadra.payroll, 1),
            "roster": [_get_player_details(p) for p in sorted(squadra.roster, key=lambda p: p.valutazione, reverse=True)],
            "future_picks": future_picks,
            "standings_history": getattr(squadra, 'standings_history', [])
        })
        
    # --- THE FIX IS HERE ---
    # 1. Collect ALL the active players in a single list.
    tutti_giocatori_attivi = [p for s in torneo.squadre for p in s.roster]
    
    # 2. Sort THAT list by OVR (valutazione).
    giocatori_attivi_ordinati = sorted(tutti_giocatori_attivi, key=lambda p: p.valutazione, reverse=True)

    # 3. Create the detailed data from the already sorted list.
    giocatori_attivi_data = [_get_player_details(p) for p in giocatori_attivi_ordinati]
    
    # We apply the same sorting for consistency to FA and retired players too
    giocatori_fa_data = [_get_player_details(p) for p in sorted(torneo.free_agents_pool, key=lambda p: p.valutazione, reverse=True)]
    giocatori_ritirati_data = [_get_player_details(p) for p in sorted(torneo.giocatori_ritirati, key=lambda p: p.valutazione, reverse=True)]
    
    return {
        "teams": squadre_data,
        "players_active": giocatori_attivi_data,
        "players_retired": giocatori_ritirati_data,
        "players_fa": giocatori_fa_data
    }
### MODIFICATO ###
# Crucial function for communication with the frontend
def stat_leader_pool(players):
    """Players who can lead a stat on the Dashboard: at least LEADERS_MIN_GP_SHARE of the most games anyone has
    played, so leaders show from the first games of the season."""
    most = max((p.season_stats.partite_giocate for p in players), default=0)
    if most <= 0:
        return []
    need = CONFIG.DASHBOARD.LEADERS_MIN_GP_SHARE * most
    return [p for p in players if p.season_stats.partite_giocate > 0 and p.season_stats.partite_giocate >= need]


def _get_api_data_from_tournament(torneo: Tournament, lean: bool = False) -> dict:
    """
    ### DEBUG VERSION (v10.2) ###
    Adds aggressive logging during the creation of the payload to
    identify the exact object that causes the serialization crash.
    """
    try:
        # 1. Standings and Stat Leaders
        classifica_est = sorted(torneo.squadre_est, key=lambda s: s.vittorie, reverse=True)
        classifica_ovest = sorted(torneo.squadre_ovest, key=lambda s: s.vittorie, reverse=True)
        classifica_data = {
            "east": [{"pos": i+1, "nome": t.nome, "v": t.vittorie, "s": t.sconfitte} for i, t in enumerate(classifica_est)],
            "west": [{"pos": i+1, "nome": t.nome, "v": t.vittorie, "s": t.sconfitte} for i, t in enumerate(classifica_ovest)],
        }
        # ... (the stat leaders logic stays the same, I omit it for brevity)
        tutti_giocatori = stat_leader_pool([p for s in torneo.squadre for p in s.roster])
        if tutti_giocatori:
            def get_stats(p, stat_name):
                pg = p.season_stats.partite_giocate or 1
                return round(getattr(p.season_stats, stat_name) / pg, 1)

            leaders = {
                "punti": max(tutti_giocatori, key=lambda p: get_stats(p, 'punti'), default=None),
                "rimbalzi": max(tutti_giocatori, key=lambda p: get_stats(p, 'rimbalzi'), default=None),
                "assist": max(tutti_giocatori, key=lambda p: get_stats(p, 'assist'), default=None),
                "stoppate": max(tutti_giocatori, key=lambda p: get_stats(p, 'blocks'), default=None),
                "recuperi": max(tutti_giocatori, key=lambda p: get_stats(p, 'steals'), default=None),
            }
            classifica_data['stat_leaders'] = {
                k: {"nome": p.nome, "stats": {
                    "ppg": get_stats(p, 'punti'), "rpg": get_stats(p, 'rimbalzi'), 
                    "apg": get_stats(p, 'assist'), "bpg": get_stats(p, 'blocks'), "spg": get_stats(p, 'steals')
                    }}
                for k, p in leaders.items() if p is not None
            }
        
        # 2. Seasonal Awards
        # 2. Premi
        premi_data = None
        if torneo.regular_season_mvp:
            def get_player_award_stats(p: Giocatore):
                pg = p.season_stats.partite_giocate or 1
                return {
                    "ppg": round(p.season_stats.punti / pg, 1), "rpg": round(p.season_stats.rimbalzi / pg, 1),
                    "apg": round(p.season_stats.assist / pg, 1), "spg": round(p.season_stats.steals / pg, 1),
                    "bpg": round(p.season_stats.blocks / pg, 1)
                }
            
            def get_team_name(player): return player.squadra.nome if player.squadra else "N/A"

            premi_data = {
                "mvp": {"nome": torneo.regular_season_mvp.nome, "squadra": get_team_name(torneo.regular_season_mvp), "stats": get_player_award_stats(torneo.regular_season_mvp)},
                "dpoy": {"nome": torneo.defensive_player_of_the_year.nome, "squadra": get_team_name(torneo.defensive_player_of_the_year), "stats": get_player_award_stats(torneo.defensive_player_of_the_year)},
                "mip": {"nome": torneo.most_improved_player.nome, "squadra": get_team_name(torneo.most_improved_player), "stats": get_player_award_stats(torneo.most_improved_player)} if torneo.most_improved_player else None,
                "sesto_uomo": {"nome": torneo.sesto_uomo.nome, "squadra": get_team_name(torneo.sesto_uomo), "stats": get_player_award_stats(torneo.sesto_uomo)},
                "roy": {"nome": torneo.rookie_of_the_year.nome, "squadra": get_team_name(torneo.rookie_of_the_year), "stats": get_player_award_stats(torneo.rookie_of_the_year)} if torneo.rookie_of_the_year else None,
                "coy": getattr(torneo, 'coach_of_the_year', None),
                "gm_of_the_year": getattr(torneo, 'gm_of_the_year', None),
                "all_nba": [[{"ruolo": p.ruolo, "nome": p.nome, "squadra": get_team_name(p)} for p in team] for team in torneo.all_nba_teams],
                "all_defensive": [{"ruolo": p.ruolo, "nome": p.nome, "squadra": get_team_name(p)} for p in torneo.all_defensive_team],
                "all_rookie": [{"ruolo": p.ruolo, "nome": p.nome, "squadra": get_team_name(p)} for p in torneo.all_rookie_team],
            }

        # 3. Playoff Data
        playoffs_data = None
        # ### THE CRUCIAL FIX IS HERE ###
        # Instead of `if torneo.playoff_state == "COMPLETE"`, we check whether the playoffs have *started*.
        # This allows showing the bracket while the playoffs are in progress.
        if torneo.playoff_state != "NOT_STARTED" and torneo.playoff_bracket_data:
            def format_series_for_api(series_log):
                if not series_log: return None
                return {
                    "s1_nome": series_log.get("s1_nome"),
                    "s1_seed": series_log.get("s1_seed", ""), 
                    "s1_vittorie": series_log.get("s1_vittorie", 0),
                    "s2_nome": series_log.get("s2_nome"),
                    "s2_seed": series_log.get("s2_seed", ""),
                    "s2_vittorie": series_log.get("s2_vittorie", 0),
                    "winner_nome": series_log.get("winner_nome"),
                    "games": series_log.get("games", [])
                }
            
            pg_po_mvp = (torneo.finals_mvp.playoff_stats.partite_giocate or 1) if torneo.finals_mvp else 1

            playoffs_data = {
                "campione": torneo.campione.nome if torneo.campione else None,
                "mvp_finali": {
                    "nome": torneo.finals_mvp.nome,
                    "stats": {
                        "ppg": round(torneo.finals_mvp.playoff_stats.punti / pg_po_mvp, 1),
                        "rpg": round(torneo.finals_mvp.playoff_stats.rimbalzi / pg_po_mvp, 1),
                        "apg": round(torneo.finals_mvp.playoff_stats.assist / pg_po_mvp, 1),
                        "spg": round(torneo.finals_mvp.playoff_stats.steals / pg_po_mvp, 1),
                        "bpg": round(torneo.finals_mvp.playoff_stats.blocks / pg_po_mvp, 1)
                    }
                } if torneo.finals_mvp else None,
                "bracket": {
                    "east": {
                        "qf": [format_series_for_api(s) for s in torneo.playoff_bracket_data['east']['qf']],
                        "sf": [format_series_for_api(s) for s in torneo.playoff_bracket_data['east']['sf']],
                        "cf": [format_series_for_api(s) for s in torneo.playoff_bracket_data['east']['cf']],
                    },
                    "west": {
                        "qf": [format_series_for_api(s) for s in torneo.playoff_bracket_data['west']['qf']],
                        "sf": [format_series_for_api(s) for s in torneo.playoff_bracket_data['west']['sf']],
                        "cf": [format_series_for_api(s) for s in torneo.playoff_bracket_data['west']['cf']],
                    },
                    "finals": [format_series_for_api(s) for s in torneo.playoff_bracket_data.get('finals', [])],
                    # ### IMPROVEMENT: We add the next round's state for the UX ###
                    "next_turn": torneo.playoff_state if torneo.playoff_state not in ["COMPLETE", "FINALS"] else ("FINALS" if torneo.playoff_state == "FINALS" else "OFFSEASON")
                }
            }
        # 4. Offseason Data
        offseason_data = torneo.offseason_log_data

        cal_len = len(torneo.calendario) if getattr(torneo, 'calendario', None) else 176
        cur_day = getattr(torneo, '_current_gameday', 0)

        payload = {
            "stagione": torneo.season_number,
            "season_number": torneo.season_number,
            "anno_corrente": getattr(torneo, 'anno_corrente', 2025),
            "current_day": cur_day,
            "total_calendar_days": cal_len,
            "calendar_progress_pct": round((cur_day / cal_len) * 100.0, 1) if cal_len > 0 else 0.0,
            "classifica": classifica_data,
            "premi": premi_data,
            "playoffs": playoffs_data,
            "offseason": offseason_data
        }

        if not lean:
            payload['league_database'] = get_league_database(torneo)

        return payload
    
    except Exception as e:
        print("\n\n!!!!!!!!! CRASH WHILE CREATING THE API PAYLOAD !!!!!!!!!")
        print(f"Errore: {e}")
        import traceback
        traceback.print_exc()
        print("="*60 + "\n")
        # Return an explicit error instead of failing silently
        return {"error": "Critical error while serializing the data", "details": str(e)}

def run_trade_finder_tool(torneo: Tournament):
    """
    ### TRADE FINDER TOOL v14.0 - UPDATED FOR NEW TRADE SYSTEM ###
    Updated version compatible with the new dynamic evaluation system.
    """
    print("=" * 20 + " TRADE FINDER TOOL v14.0 " + "=" * 20)
    print("Enter a player's name to see the offers, or 'exit' to quit.")
    
    trade_finder = TradeFinder(torneo, torneo.squadre, None)
    
    while True:
        player_name = input("\nPlayer to trade: ").strip()
        
        if player_name.lower() == 'exit':
            print("Exiting the Trade Finder Tool.")
            break
        
        # Find the player
        target_player, requesting_team = None, None
        for team in torneo.squadre:
            player = next((p for p in team.roster if p.nome.lower() == player_name.lower()), None)
            if player:
                target_player = player
                requesting_team = team
                break
        
        if not target_player:
            print(f"ERROR: Player '{player_name}' not found on any team.")
            continue
        
        print(f"\n--- Market Analysis for {target_player.nome} ({target_player.ovr} OVR) of the {requesting_team.nome} ---")
        
        player_value = trade_finder.get_strategic_value(target_player, requesting_team)
        print(f"Computed Trade Value for {requesting_team.nome}: {player_value:.1f}")
        
        all_offers = []
        potential_partners = [t for t in torneo.squadre if t.nome != requesting_team.nome]
        
        for partner_team in potential_partners:
            # For simplicity, we use the _build_bid_for_veteran helper which perfectly simulates a Contender's offer for a vet
            bid = trade_finder._build_bid_for_veteran(partner_team, requesting_team, target_player)
            if bid:
                all_offers.append(bid)
        
        if not all_offers:
            print("❌ No valid offers found on the market.")
            continue
        
        # Show the offers
        print(f"\n--- Found {len(all_offers)} Valid Offers ---")
        sorted_offers = sorted(all_offers, key=lambda x: x['value_to_seller'], reverse=True)
        
        for i, offer in enumerate(sorted_offers[:min(len(all_offers), 5)]):  # Show the top 5
            package_names = [trade_finder._format_asset(a) for a in offer['assets']]
            is_accepted = trade_finder.would_accept_trade(requesting_team, offer['assets'], [target_player])
            status = "✅ ACCETTATA" if is_accepted else "❌ RIFIUTATA"
            print(f"#{i+1} from {offer['partner'].nome} | Value for us: {offer['value_to_seller']:.1f} | {status}")
            print(f"  - Offre: {', '.join(package_names)}")
