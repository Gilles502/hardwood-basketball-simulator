# File: core/franchise_legacy.py
"""
Franchise Legacy & Trophy Room Engine for Hardwood Basketball Simulator
100% Driven by the Simulation Universe:
- Championship Banners hanging in Arena Rafters: generated from league_history.json / sqlite league_history
- Trophy Cabinet (Larry O'Brien, Finals MVP, MVP, DPOY, ROY, 6MOTY): generated from simulation awards & league_history.json
- Retired Jersey Numbers: awarded to franchise legends when they retire or enter Hall of Fame in the simulation, with unique generated jersey numbers
- All-Time Franchise Leaders (PTS, REB, AST, GP, 3PM): computed dynamically from career_stats DB, player_careers.json, and active tournament roster stats
- Franchise Single-Game and Single-Season Records: tracked live from games played and seasons completed in the simulation
"""

import os
import json
import sqlite3
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from core import paths
from core.save_manager import get_historical_file_path
from core.league.registry import get_active_registry
import logging
logger = logging.getLogger('main_sim')

# The writable user root (holds the active data/nba_sim.db), see core.paths.
BASE_DIR = paths.user_root()

# =============================================================================
# 1. TEAM BRANDING (colors, arena, city label: from the active league's franchise registry)
# =============================================================================

def get_team_branding(team_name: str) -> Dict[str, Any]:
    """Returns the arena, colors and abbreviation for the graphical display (generic fallback for unknown teams)."""
    return get_active_registry().branding(team_name)


# =============================================================================
# 2. GESTIONE FILE FRANCHISE RECORDS (Record e Maglie Ritirate Simulate)
# =============================================================================

def load_franchise_records_file() -> Dict[str, Any]:
    """Loads or initializes franchise_records.json from the active save."""
    records_file = get_historical_file_path("franchise_records.json")
    if os.path.exists(records_file):
        try:
            with open(records_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "single_game_records" not in data:
                        data["single_game_records"] = {}
                    if "retired_jerseys" not in data:
                        data["retired_jerseys"] = {}
                    return data
        except Exception:
            logger.warning("Ignored error in load_franchise_records_file()", exc_info=True)
    return {"single_game_records": {}, "retired_jerseys": {}}

def career_name(slug: str, seasons: List[Dict[str, Any]]) -> str:
    """A player's name as saved in his career seasons ("Adam Smith"); the id title-cased for old saves."""
    for s in reversed(seasons or []):
        if isinstance(s, dict) and s.get("nome"):
            return s["nome"]
    return slug.replace("-", " ").title()

def save_franchise_records_file(data: Dict[str, Any]):
    """Writes franchise_records.json to disk in the active save."""
    records_file = get_historical_file_path("franchise_records.json")
    try:
        with open(records_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Could not save franchise_records.json: {e}")


# =============================================================================
# 3. TITOLI & STENDARDI DAI DATI SIMULATI (BANNERS NEI RAFTERS)
# =============================================================================

def get_franchise_banners(team_name: str) -> List[Dict[str, Any]]:
    """
    Extracts all NBA titles won by the franchise during the simulated seasons
    by reading league_history.json and/or the sqlite league_history table.
    """
    banners: List[Dict[str, Any]] = []
    
    # 1. Read league_history.json from the active slot
    history_file = get_historical_file_path("league_history.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_list = json.load(f)
                if isinstance(history_list, list):
                    for h in history_list:
                        if isinstance(h, dict) and h.get("campione") == team_name:
                            season_num = h.get("stagione", 1)
                            banners.append({
                                "year": f"Season {season_num}",
                                "title": "NBA Champions",
                                "type": "NBA Finals",
                                "finals_mvp": h.get("mvp_finali", "N/A"),
                                "opponent": h.get("finalista", "Playoff")
                            })
        except Exception:
            logger.warning("Ignored error in get_franchise_banners()", exc_info=True)

    # 2. Read from sqlite league_history if present
    db_path = os.path.join(BASE_DIR, "data", "nba_sim.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            rows = cur.execute("""
                SELECT lh.season, p.name as finals_mvp
                FROM league_history lh
                JOIN teams t ON lh.champion_team_id = t.id
                LEFT JOIN players p ON lh.finals_mvp_player_id = p.id
                WHERE t.name = ?
            """, (team_name,)).fetchall()
            
            existing_seasons = {b["year"] for b in banners}
            for r in rows:
                s_label = f"Season {r[0]}"
                if s_label not in existing_seasons:
                    banners.append({
                        "year": s_label,
                        "title": "NBA Champions",
                        "type": "NBA Finals",
                        "finals_mvp": r[1] if r[1] else "N/A",
                        "opponent": "NBA Finals"
                    })
            conn.close()
        except Exception:
            logger.warning("Ignored error in get_franchise_banners()", exc_info=True)

    return banners


# =============================================================================
# 4. FRANCHISE TROPHY CABINET
# =============================================================================

def get_franchise_trophy_cabinet(team_name: str, tournament: Optional[Any] = None) -> Dict[str, Any]:
    """
    Collects all the trophies won by players wearing this franchise's jersey
    during the simulated seasons.
    """
    cabinet = {
        "larry_obrien": 0,
        "finals_mvp": [],
        "mvp": [],
        "dpoy": [],
        "roy": [],
        "sixth_man": []
    }
    
    # Conteggio Larry O'Brien e Finals MVP dai banners
    banners = get_franchise_banners(team_name)
    cabinet["larry_obrien"] = len(banners)
    for b in banners:
        if b.get("finals_mvp") and b["finals_mvp"] != "N/A":
            cabinet["finals_mvp"].append({
                "player": b["finals_mvp"],
                "year": b["year"]
            })

    # Leggi premi individuali da league_history.json
    history_file = get_historical_file_path("league_history.json")
    careers_file = get_historical_file_path("player_careers.json")
    
    player_careers = {}
    if os.path.exists(careers_file):
        try:
            with open(careers_file, 'r', encoding='utf-8') as f:
                player_careers = json.load(f)
        except Exception:
            player_careers = {}

    def get_player_team_in_season(player_name_raw: str, season_num: int) -> Optional[str]:
        if not player_name_raw or player_name_raw in ["N/A", "None", ""]:
            return None
        slug = player_name_raw.strip().lower().replace(" ", "-")
        # Look in player_careers.json
        if slug in player_careers:
            for s_entry in player_careers[slug]:
                if s_entry.get("stagione") == season_num:
                    return s_entry.get("squadra")
        # Look in sqlite
        db_path = os.path.join(BASE_DIR, "data", "nba_sim.db")
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                row = cur.execute("""
                    SELECT t.name FROM career_stats cs
                    JOIN players p ON cs.player_id = p.id
                    JOIN teams t ON cs.team_id = t.id
                    WHERE p.name = ? AND cs.season = ?
                """, (player_name_raw, season_num)).fetchone()
                conn.close()
                if row:
                    return row[0]
            except Exception:
                logger.warning("Ignored error in get_player_team_in_season()", exc_info=True)
        # Look in the active tournament if it is the current season
        if tournament:
            for sq in getattr(tournament, 'squadre', []):
                for pl in getattr(sq, 'roster', []):
                    if pl.nome == player_name_raw:
                        return sq.nome
        return None

    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_list = json.load(f)
                for h in history_list:
                    season_num = h.get("stagione", 1)
                    premi = h.get("premi", {})
                    
                    # MVP
                    mvp = premi.get("mvp")
                    if mvp and get_player_team_in_season(mvp, season_num) == team_name:
                        cabinet["mvp"].append({"player": mvp, "year": f"Season {season_num}"})
                    
                    # DPOY
                    dpoy = premi.get("dpoy")
                    if dpoy and get_player_team_in_season(dpoy, season_num) == team_name:
                        cabinet["dpoy"].append({"player": dpoy, "year": f"Season {season_num}"})
                    
                    # 6MOTY
                    smoy = premi.get("sesto_uomo")
                    if smoy and get_player_team_in_season(smoy, season_num) == team_name:
                        cabinet["sixth_man"].append({"player": smoy, "year": f"Season {season_num}"})
                    
                    # ROY
                    roy = premi.get("roy")
                    if roy and get_player_team_in_season(roy, season_num) == team_name:
                        cabinet["roy"].append({"player": roy, "year": f"Season {season_num}"})
        except Exception:
            logger.warning("Ignored error in get_player_team_in_season()", exc_info=True)

    return cabinet


# =============================================================================
# 5. MAGLIE E NUMERI RITIRATI NEI RAFTERS (RETIRED JERSEYS)
# =============================================================================

def get_franchise_retired_jerseys(team_name: str, tournament: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Returns the franchise's retired jerseys from the simulator.
    If a franchise legend has retired (or is in the Hall of Fame)
    and does not yet have a retired jersey, assigns a number and retires it.
    """
    data = load_franchise_records_file()
    retired_dict = data.get("retired_jerseys", {})
    team_jerseys: List[Dict[str, Any]] = list(retired_dict.get(team_name, []))
    saved_count = len(team_jerseys)

    # Lower-cased: older saves stored names built from the id ("Lebron James").
    existing_retired_names = {j["player"].lower() for j in team_jerseys}
    used_numbers = {str(j["number"]) for j in team_jerseys}

    def generate_jersey_number(player_name: str) -> str:
        # Generate a 1-99 number based on a hash of the name, avoiding duplicates
        hash_val = int(hashlib.md5(player_name.encode()).hexdigest(), 16)
        num = (hash_val % 99) + 1
        for delta in range(100):
            cand = str((num + delta) % 100)
            if cand not in used_numbers:
                used_numbers.add(cand)
                return cand
        return "00"

    # Check Hall of Fame or retired players in the active slot
    hof_file = get_historical_file_path("hall_of_fame.json")
    careers_file = get_historical_file_path("player_careers.json")
    retired_ids_file = get_historical_file_path("retired_players_ids.json")
    
    hof_players = set()
    if os.path.exists(hof_file):
        try:
            with open(hof_file, 'r', encoding='utf-8') as f:
                hof_data = json.load(f)
                classes = hof_data.get("classes", []) if isinstance(hof_data, dict) else (hof_data if isinstance(hof_data, list) else [])
                for cl in classes:
                    for ind in cl.get("inductees", []):
                        hof_players.add(ind.get("nome", ""))
        except Exception:
            logger.warning("Ignored error in generate_jersey_number()", exc_info=True)

    if os.path.exists(retired_ids_file):
        try:
            with open(retired_ids_file, 'r', encoding='utf-8') as f:
                r_ids = json.load(f)
                if isinstance(r_ids, list):
                    set(r_ids)
        except Exception:
            logger.warning("Ignored error in generate_jersey_number()", exc_info=True)

    # If we have the active tournament, exclude players who are still active
    active_player_names = set()
    if tournament:
        for s in getattr(tournament, 'squadre', []):
            for p in getattr(s, 'roster', []):
                active_player_names.add(getattr(p, 'nome', ''))
        for p in getattr(tournament, 'free_agents_pool', []):
            active_player_names.add(getattr(p, 'nome', ''))

    if os.path.exists(careers_file):
        try:
            with open(careers_file, 'r', encoding='utf-8') as f:
                careers = json.load(f)
                for slug, seasons in careers.items():
                    if not seasons:
                        continue
                    p_name = career_name(slug, seasons)
                    if p_name.lower() in existing_retired_names:
                        continue
                    
                    # An active player cannot have his jersey retired while he is still playing
                    if p_name in active_player_names:
                        continue

                    # Count seasons and games played with this franchise
                    seasons_with_team = [s for s in seasons if s.get("squadra") == team_name]
                    if not seasons_with_team:
                        continue
                    
                    total_gp_with_team = sum(s.get("gp") or s.get("partite_giocate_rs", 0) for s in seasons_with_team)
                    total_pts_with_team = sum(s.get("pts") or s.get("punti", 0) for s in seasons_with_team)
                    championships_with_team = sum(1 for s in seasons_with_team if s.get("is_champion", False))
                    
                    # Awards won with this specific jersey
                    all_team_awards = []
                    for s in seasons_with_team:
                        all_team_awards.extend(s.get("premi", []))
                    
                    has_finals_mvp = any("Finals MVP" in str(aw) for aw in all_team_awards)
                    has_rs_mvp = any("MVP" in str(aw) and "Finals" not in str(aw) for aw in all_team_awards)
                    all_star_or_all_nba_seasons = sum(1 for s in seasons_with_team if any("All-Star" in str(aw) or "All-NBA" in str(aw) or "MVP" in str(aw) for aw in s.get("premi", [])))
                    
                    is_hof = p_name in hof_players
                    num_seasons = len(seasons_with_team)
                    
                    # =========================================================================
                    # STRICT NBA CRITERIA FOR RETIRING A JERSEY (HALL OF FAME / RAFTERS)
                    # =========================================================================
                    merita_ritiro = False
                    role_tag = "Legend"

                    # 1. Loyal Hall of Famer (at least 5 seasons and 300+ games with the franchise)
                    if is_hof and num_seasons >= 5 and total_gp_with_team >= 300:
                        merita_ritiro = True
                        role_tag = "Hall of Fame Icon"
                    
                    # 2. Title Hero (won the ring + Finals MVP/MVP, or 5+ seasons as a cornerstone + a ring)
                    elif championships_with_team >= 1 and total_gp_with_team >= 250:
                        if has_finals_mvp or has_rs_mvp or (num_seasons >= 5 and (all_star_or_all_nba_seasons >= 1 or total_pts_with_team >= 4000)):
                            merita_ritiro = True
                            role_tag = "Championship Hero"
                            
                    # 3. Franchise Icon (7+ seasons, 400+ games, multiple All-Star/All-NBA honors)
                    elif num_seasons >= 7 and total_gp_with_team >= 400 and all_star_or_all_nba_seasons >= 2:
                        merita_ritiro = True
                        role_tag = "Franchise Pillar"

                    # 4. Legendary Stat Leader (at least 7000 points scored for the franchise over 6+ seasons and 400+ games)
                    elif num_seasons >= 6 and total_gp_with_team >= 400 and total_pts_with_team >= 7000:
                        merita_ritiro = True
                        role_tag = "All-Time Scorer"

                    if merita_ritiro:
                        min_s = min(s.get("stagione", 1) for s in seasons_with_team)
                        max_s = max(s.get("stagione", 1) for s in seasons_with_team)
                        era_str = f"Seasons {min_s}-{max_s}" if min_s != max_s else f"Season {min_s}"
                        
                        num = generate_jersey_number(p_name)
                        team_jerseys.append({
                            "number": num,
                            "player": p_name,
                            "era": era_str,
                            "role": role_tag
                        })
                        existing_retired_names.add(p_name.lower())
        except Exception as e:
            print(f"Could not check jersey retirements for {team_name}: {e}")

    if len(team_jerseys) != saved_count:
        retired_dict[team_name] = team_jerseys
        data["retired_jerseys"] = retired_dict
        save_franchise_records_file(data)

    return team_jerseys


# =============================================================================
# 6. FRANCHISE ALL-TIME LEADERBOARDS (SIMULATED STAT LEADERS)
# =============================================================================

def get_franchise_all_time_leaders(team_name: str, tournament: Optional[Any] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Computes the franchise All-Time leaderboards (Points, Rebounds, Assists, Games, Threes)
    by dynamically aggregating the real game data:
    1. career_stats from sqlite
    2. player_careers.json
    3. current-season statistics in the active tournament
    """
    player_totals: Dict[str, Dict[str, Any]] = {}

    def add_stats(name: str, pts: int, reb: int, ast: int, gp: int, t3: int, era_label: str):
        if not name or name in ["N/A", "None"]:
            return
        if name not in player_totals:
            player_totals[name] = {
                "name": name,
                "points": 0,
                "rebounds": 0,
                "assists": 0,
                "games": 0,
                "three_pointers": 0,
                "eras": set()
            }
        player_totals[name]["points"] += pts
        player_totals[name]["rebounds"] += reb
        player_totals[name]["assists"] += ast
        player_totals[name]["games"] += gp
        player_totals[name]["three_pointers"] += t3
        if era_label:
            player_totals[name]["eras"].add(era_label)

    # 1. Dati da SQLite career_stats
    db_path = os.path.join(BASE_DIR, "data", "nba_sim.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            rows = cur.execute("""
                SELECT p.name,
                       SUM(cs.rs_points),
                       SUM(cs.rs_rebounds),
                       SUM(cs.rs_assists),
                       SUM(cs.rs_games_played),
                       SUM(cs.rs_three_pointers_made),
                       MIN(cs.season),
                       MAX(cs.season)
                FROM career_stats cs
                JOIN players p ON cs.player_id = p.id
                JOIN teams t ON cs.team_id = t.id
                WHERE t.name = ?
                GROUP BY p.id, p.name
            """, (team_name,)).fetchall()
            
            for r in rows:
                p_name, pts, reb, ast, gp, t3, min_s, max_s = r
                era_str = f"Seasons {min_s}-{max_s}" if min_s != max_s else f"Season {min_s}"
                add_stats(p_name, pts or 0, reb or 0, ast or 0, gp or 0, t3 or 0, era_str)
            conn.close()
        except Exception:
            logger.warning("Ignored error in add_stats()", exc_info=True)

    # 2. Data from player_careers.json (if not already aggregated, or for historical seasons)
    careers_file = get_historical_file_path("player_careers.json")
    if os.path.exists(careers_file):
        try:
            with open(careers_file, 'r', encoding='utf-8') as f:
                careers = json.load(f)
                for slug, seasons in careers.items():
                    p_name = career_name(slug, seasons)
                    # If already present from the SQLite DB, don't duplicate the same seasons
                    if p_name in player_totals and player_totals[p_name]["games"] > 0:
                        continue
                    
                    team_seasons = [s for s in seasons if s.get("squadra") == team_name]
                    if not team_seasons:
                        continue
                    
                    total_pts = 0
                    total_reb = 0
                    total_ast = 0
                    total_gp = 0
                    total_3pm = 0
                    seasons_nums = []

                    for s in team_seasons:
                        gp = s.get("gp") or s.get("partite_giocate_rs", 0)
                        total_gp += gp
                        seasons_nums.append(s.get("stagione", 1))
                        
                        if "pts" in s:
                            total_pts += s.get("pts", 0)
                            total_reb += s.get("reb", 0)
                            total_ast += s.get("ast", 0)
                            total_3pm += s.get("three_pointers", 0)
                        elif "stats_rs" in s:
                            stats = s.get("stats_rs", {})
                            total_pts += round(stats.get("ppg", 0) * gp)
                            total_reb += round(stats.get("rpg", 0) * gp)
                            total_ast += round(stats.get("apg", 0) * gp)
                            total_3pm += round(stats.get("t3pg", 0) * gp)

                    min_s = min(seasons_nums) if seasons_nums else 1
                    max_s = max(seasons_nums) if seasons_nums else 1
                    era_str = f"Seasons {min_s}-{max_s}" if min_s != max_s else f"Season {min_s}"
                    add_stats(p_name, total_pts, total_reb, total_ast, total_gp, total_3pm, era_str)
        except Exception:
            logger.warning("Ignored error in add_stats()", exc_info=True)

    # 3. Data from the current season in the active tournament (if not yet saved to the DB)
    if tournament:
        for sq in getattr(tournament, 'squadre', []):
            if sq.nome == team_name:
                for pl in getattr(sq, 'roster', []):
                    st = getattr(pl, 'season_stats', None)
                    if st and st.partite_giocate > 0:
                        add_stats(
                            pl.nome,
                            st.punti,
                            st.rimbalzi,
                            st.assist,
                            st.partite_giocate,
                            getattr(st, 'tiri_fatti_3', 0),
                            f"Season {getattr(tournament, 'season_number', 1)}"
                        )

    # 4. Fallback for season 1 before games start: show the active roster
    if not player_totals:
        # Retrieve the roster from sqlite or the tournament
        if tournament:
            for sq in getattr(tournament, 'squadre', []):
                if sq.nome == team_name:
                    for pl in getattr(sq, 'roster', []):
                        add_stats(pl.nome, 0, 0, 0, 0, 0, "Current Roster")
        elif os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                r_players = cur.execute("""
                    SELECT p.name, p.overall FROM players p
                    JOIN teams t ON p.team_id = t.id
                    WHERE t.name = ?
                    ORDER BY p.overall DESC
                """, (team_name,)).fetchall()
                for rp in r_players:
                    add_stats(rp[0], 0, 0, 0, 0, 0, "Current Roster")
                conn.close()
            except Exception:
                logger.warning("Ignored error in add_stats()", exc_info=True)

    # Format the Top 10 leaderboards for each category
    def get_top(stat_key: str) -> List[Dict[str, Any]]:
        entries = []
        for p in player_totals.values():
            val = p[stat_key]
            era_formatted = ", ".join(sorted(list(p["eras"]))) if p["eras"] else "Simulation"
            entries.append({
                "name": p["name"],
                "value": val,
                "era": era_formatted,
                "is_simulated": True
            })
        entries.sort(key=lambda x: x["value"], reverse=True)
        return entries[:10]

    return {
        "points": get_top("points"),
        "rebounds": get_top("rebounds"),
        "assists": get_top("assists"),
        "games": get_top("games"),
        "three_pointers": get_top("three_pointers")
    }


# =============================================================================
# 7. FRANCHISE HISTORICAL RECORDS (SINGLE GAME AND SINGLE SEASON)
# =============================================================================

def record_franchise_game_performance(team_name: str, player_name: str, stat_name: str,
                                      value: int, opponent: str, season_num: int = 1):
    """
    Called by the game engine (core/records.py) when a player has an exceptional performance.
    Updates franchise_records.json if it is a new franchise record.
    """
    if not team_name or not player_name or value <= 0:
        return
    
    data = load_franchise_records_file()
    single_game = data.get("single_game_records", {})
    if team_name not in single_game:
        single_game[team_name] = {}
    
    current = single_game[team_name].get(stat_name)
    if current is None or value > current.get("value", 0):
        single_game[team_name][stat_name] = {
            "value": value,
            "player": player_name,
            "opponent": opponent or "NBA",
            "year": f"Season {season_num}"
        }
        data["single_game_records"] = single_game
        save_franchise_records_file(data)

def get_franchise_records(team_name: str, tournament: Optional[Any] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns the single-game and single-season records registered in the simulator.
    """
    data = load_franchise_records_file()
    single_game = data.get("single_game_records", {}).get(team_name, {})

    # Clean default for single games if no performance has been recorded yet
    game_records_formatted = {}
    for k, _default_label in [
        ("points", "Points"),
        ("rebounds", "Rebounds"),
        ("assists", "Assists"),
        ("three_pointers", "Threes"),
        ("blocks", "Blocks"),
        ("steals", "Steals")
    ]:
        if k in single_game:
            game_records_formatted[k] = single_game[k]
        else:
            game_records_formatted[k] = {
                "value": 0,
                "player": "Waiting for games",
                "opponent": "-",
                "year": "-"
            }

    # Dynamically compute single-season records from the franchise's career data
    season_records: Dict[str, Any] = {
        "points": {"value": 0, "player": "In progress", "year": "-"},
        "ppg": {"value": 0.0, "player": "In progress", "year": "-"},
        "rebounds": {"value": 0, "player": "In progress", "year": "-"},
        "rpg": {"value": 0.0, "player": "In progress", "year": "-"},
        "assists": {"value": 0, "player": "In progress", "year": "-"},
        "three_pointers": {"value": 0, "player": "In progress", "year": "-"}
    }

    # Compute single-season records from player_careers.json
    careers_file = get_historical_file_path("player_careers.json")
    if os.path.exists(careers_file):
        try:
            with open(careers_file, 'r', encoding='utf-8') as f:
                careers = json.load(f)
                for slug, seasons in careers.items():
                    p_name = career_name(slug, seasons)
                    for s in seasons:
                        if s.get("squadra") != team_name:
                            continue
                        s_year = f"Season {s.get('stagione', 1)}"
                        gp = s.get("gp") or s.get("partite_giocate_rs", 0)
                        
                        pts = s.get("pts") or round(s.get("stats_rs", {}).get("ppg", 0) * gp)
                        reb = s.get("reb") or round(s.get("stats_rs", {}).get("rpg", 0) * gp)
                        ast = s.get("ast") or round(s.get("stats_rs", {}).get("apg", 0) * gp)
                        t3 = s.get("three_pointers") or round(s.get("stats_rs", {}).get("t3pg", 0) * gp)
                        
                        ppg = round(pts / gp, 1) if gp > 10 else 0.0
                        rpg = round(reb / gp, 1) if gp > 10 else 0.0

                        if pts > season_records["points"]["value"]:
                            season_records["points"] = {"value": pts, "player": p_name, "year": s_year}
                        if ppg > season_records["ppg"]["value"]:
                            season_records["ppg"] = {"value": ppg, "player": p_name, "year": s_year}
                        if reb > season_records["rebounds"]["value"]:
                            season_records["rebounds"] = {"value": reb, "player": p_name, "year": s_year}
                        if rpg > season_records["rpg"]["value"]:
                            season_records["rpg"] = {"value": rpg, "player": p_name, "year": s_year}
                        if ast > season_records["assists"]["value"]:
                            season_records["assists"] = {"value": ast, "player": p_name, "year": s_year}
                        if t3 > season_records["three_pointers"]["value"]:
                            season_records["three_pointers"] = {"value": t3, "player": p_name, "year": s_year}
        except Exception:
            logger.warning("Ignored error in get_franchise_records()", exc_info=True)

    # Also update from the current season in the tournament if there are higher performances
    if tournament:
        for sq in getattr(tournament, 'squadre', []):
            if sq.nome == team_name:
                s_year = f"Season {getattr(tournament, 'season_number', 1)}"
                for pl in getattr(sq, 'roster', []):
                    st = getattr(pl, 'season_stats', None)
                    if not st or st.partite_giocate == 0:
                        continue
                    gp = st.partite_giocate
                    pts = st.punti
                    reb = st.rimbalzi
                    ast = st.assist
                    t3 = getattr(st, 'tiri_fatti_3', 0)
                    ppg = round(pts / gp, 1) if gp >= 5 else 0.0
                    rpg = round(reb / gp, 1) if gp >= 5 else 0.0

                    if pts > season_records["points"]["value"]:
                        season_records["points"] = {"value": pts, "player": pl.nome, "year": s_year}
                    if ppg > season_records["ppg"]["value"]:
                        season_records["ppg"] = {"value": ppg, "player": pl.nome, "year": s_year}
                    if reb > season_records["rebounds"]["value"]:
                        season_records["rebounds"] = {"value": reb, "player": pl.nome, "year": s_year}
                    if rpg > season_records["rpg"]["value"]:
                        season_records["rpg"] = {"value": rpg, "player": pl.nome, "year": s_year}
                    if ast > season_records["assists"]["value"]:
                        season_records["assists"] = {"value": ast, "player": pl.nome, "year": s_year}
                    if t3 > season_records["three_pointers"]["value"]:
                        season_records["three_pointers"] = {"value": t3, "player": pl.nome, "year": s_year}

    return game_records_formatted, season_records


def get_franchise_standings_history(team_name: str, tournament: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Extracts the complete history of Regular Season standings for a franchise.
    Combines league_history.json with the active season in memory and the team models.
    """
    clean_name = team_name.strip()
    history_map: Dict[int, Dict[str, Any]] = {}
    
    # 1. Da league_history.json
    history_file = get_historical_file_path("league_history.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_list = json.load(f)
                
            for h in history_list:
                s_num = h.get("stagione", 1)
                s_year = h.get("anno", 2024 + s_num)
                is_champ = (h.get("campione") == clean_name)
                
                # Check standings array
                standings = h.get("standings", [])
                matching_entry = next((item for item in standings if item.get("team") == clean_name), None)
                
                if matching_entry:
                    conf = matching_entry.get("conference", "East")
                    
                    # If conf_seed is explicitly present, use it; otherwise compute
                    conf_seed = matching_entry.get("conf_seed")
                    if conf_seed is None:
                        conf_teams = [t for t in standings if t.get("conference") == conf]
                        sorted_conf = sorted(conf_teams, key=lambda x: (x.get("wins", 0), -x.get("losses", 0)), reverse=True)
                        conf_seed = next((idx + 1 for idx, t in enumerate(sorted_conf) if t.get("team") == clean_name), 8)
                    
                    # Overall rank
                    league_rank = matching_entry.get("league_rank")
                    if league_rank is None:
                        sorted_all = sorted(standings, key=lambda x: (x.get("wins", 0), -x.get("losses", 0)), reverse=True)
                        league_rank = next((idx + 1 for idx, t in enumerate(sorted_all) if t.get("team") == clean_name), 15)
                        
                    wins = matching_entry.get("wins", 0)
                    losses = matching_entry.get("losses", 0)
                    ppg = matching_entry.get("ppg", 0.0)
                    oppg = matching_entry.get("oppg", 0.0)
                    diff = matching_entry.get("diff", round(ppg - oppg, 1))
                    
                    playoff_round = matching_entry.get("playoff_round")
                    if not playoff_round:
                        if is_champ: playoff_round = "Campione NBA 🏆"
                        elif conf_seed <= 8: playoff_round = "Playoffs"
                        elif conf_seed <= 10: playoff_round = "Play-In"
                        else: playoff_round = "Lottery"

                    history_map[s_num] = {
                        "season": s_num,
                        "year": s_year,
                        "conference": conf,
                        "conf_seed": conf_seed,
                        "league_rank": league_rank,
                        "wins": wins,
                        "losses": losses,
                        "win_pct": round(wins / max(1, wins + losses), 3),
                        "ppg": ppg,
                        "oppg": oppg,
                        "diff": diff,
                        "is_champion": is_champ,
                        "playoff_round": playoff_round
                    }
        except Exception:
            logger.warning("Ignored error in get_franchise_standings_history()", exc_info=True)

    # 2. From the in-memory team if active
    if tournament and getattr(tournament, 'squadre', None):
        sq = next((s for s in tournament.squadre if s.nome == clean_name), None)
        if sq:
            # Integra eventuali record in sq.standings_history
            for entry in getattr(sq, 'standings_history', []):
                s_idx = entry.get("season", 1)
                if s_idx not in history_map:
                    history_map[s_idx] = entry
                else:
                    history_map[s_idx].update(entry)
            
            # If the current season is not yet archived in league_history.json
            cur_season = getattr(tournament, 'season_number', 1)
            gp = sq.vittorie + sq.sconfitte
            if cur_season not in history_map and gp > 0:
                # Compute live seed
                east_sqs = sorted([s for s in tournament.squadre if getattr(s, 'conference', '').lower() in ['east', 'est']], key=lambda s: (-s.vittorie, s.sconfitte))
                west_sqs = sorted([s for s in tournament.squadre if getattr(s, 'conference', '').lower() in ['west', 'ovest']], key=lambda s: (-s.vittorie, s.sconfitte))
                all_sqs = sorted(tournament.squadre, key=lambda s: (-s.vittorie, s.sconfitte))
                
                conf_name = getattr(sq, 'conference', 'East')
                if conf_name.lower() in ['east', 'est']:
                    conf_seed = next((i + 1 for i, s in enumerate(east_sqs) if s.nome == clean_name), 1)
                else:
                    conf_seed = next((i + 1 for i, s in enumerate(west_sqs) if s.nome == clean_name), 1)
                league_rank = next((i + 1 for i, s in enumerate(all_sqs) if s.nome == clean_name), 1)
                
                pts_for = getattr(sq, 'punti_fatti_stagione', getattr(sq, 'punti_fatti', 0))
                pts_against = getattr(sq, 'punti_subiti_stagione', getattr(sq, 'punti_subiti', 0))
                ppg = round(pts_for / max(1, gp), 1)
                oppg = round(pts_against / max(1, gp), 1)
                
                history_map[cur_season] = {
                    "season": cur_season,
                    "year": getattr(tournament, 'anno_corrente', 2025),
                    "conference": conf_name,
                    "conf_seed": conf_seed,
                    "league_rank": league_rank,
                    "wins": sq.vittorie,
                    "losses": sq.sconfitte,
                    "win_pct": round(sq.vittorie / max(1, gp), 3),
                    "ppg": ppg,
                    "oppg": oppg,
                    "diff": round(ppg - oppg, 1),
                    "is_champion": bool(tournament.campione and tournament.campione.nome == clean_name),
                    "playoff_round": "In Progress" if tournament.playoff_state != "COMPLETE" else ("Campione NBA 🏆" if tournament.campione and tournament.campione.nome == clean_name else "Playoff")
                }

    # Sort chronologically
    results = sorted(list(history_map.values()), key=lambda x: x.get("season", 1))
    return results


# =============================================================================
# 8. MASTER LEGACY COMPOSER: get_franchise_legacy & get_all_franchises_summary
# =============================================================================

def get_franchise_legacy(team_name: str, tournament: Optional[Any] = None) -> Dict[str, Any]:
    """
    Builds the franchise's whole historical hub, 100% based on the active simulation.
    """
    clean_name = team_name.strip()
    branding = get_team_branding(clean_name)
    
    # 1. Banners nei rafters
    banners = get_franchise_banners(clean_name)
    
    # 2. Trophy cabinet
    cabinet = get_franchise_trophy_cabinet(clean_name, tournament)
    
    # 3. Retired jerseys
    retired = get_franchise_retired_jerseys(clean_name, tournament)
    
    # 4. Franchise All-Time leaderboards
    leaders = get_franchise_all_time_leaders(clean_name, tournament)
    
    # 5. Single-game and single-season records
    game_records, season_records = get_franchise_records(clean_name, tournament)
    
    # 6. Regular Season standings history
    standings_history = get_franchise_standings_history(clean_name, tournament)
    
    total_trophies = len(banners) + len(cabinet["finals_mvp"]) + len(cabinet["mvp"]) + \
                     len(cabinet["dpoy"]) + len(cabinet["roy"]) + len(cabinet["sixth_man"])

    return {
        "team_name": clean_name,
        "abbreviation": branding["abbreviation"],
        "arena": branding["arena"],
        "city": branding["city"],
        "established": branding.get("established", 1970),
        "colors": {
            "primary": branding["primary"],
            "secondary": branding["secondary"]
        },
        "total_trophies_count": total_trophies,
        "banners": banners,
        "trophy_cabinet": cabinet,
        "retired_jerseys": retired,
        "all_time_leaders": leaders,
        "single_game_records": game_records,
        "single_season_records": season_records,
        "standings_history": standings_history
    }

def get_all_franchises_summary(tournament: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Returns the list of all franchises in the simulator universe
    with their trophy and retired-jersey counts.
    """
    team_names = []

    # 1. From the active tournament if running
    if tournament and getattr(tournament, 'squadre', None):
        team_names = [sq.nome for sq in tournament.squadre]

    # 2. Dal database SQLite
    if not team_names:
        db_path = os.path.join(BASE_DIR, "data", "nba_sim.db")
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                team_names = [r[0] for r in cur.execute("SELECT name FROM teams ORDER BY name ASC").fetchall()]
                conn.close()
            except Exception:
                logger.warning("Ignored error in get_all_franchises_summary()", exc_info=True)

    # 3. Fallback to the active league's teams if no data is available
    if not team_names:
        team_names = sorted(get_active_registry().names())

    # Quick state of titles and jerseys
    data = load_franchise_records_file()
    retired_dict = data.get("retired_jerseys", {})
    
    history_file = get_historical_file_path("league_history.json")
    champs_count: Dict[str, int] = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_list = json.load(f)
                for h in history_list:
                    c = h.get("campione")
                    if c:
                        champs_count[c] = champs_count.get(c, 0) + 1
        except Exception:
            logger.warning("Ignored error in get_all_franchises_summary()", exc_info=True)

    summary_list = []
    for t_name in team_names:
        branding = get_team_branding(t_name)
        c_count = champs_count.get(t_name, 0)
        ret_count = len(retired_dict.get(t_name, []))
        
        summary_list.append({
            "team_name": t_name,
            "abbreviation": branding["abbreviation"],
            "arena": branding["arena"],
            "city": branding["city"],
            "established": branding.get("established", 1970),
            "championships_count": c_count,
            "retired_jerseys_count": ret_count,
            "colors": {
                "primary": branding["primary"],
                "secondary": branding["secondary"]
            }
        })

    return summary_list
