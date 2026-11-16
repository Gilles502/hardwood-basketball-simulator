# File: db_manager.py
import logging
import sqlite3
from typing import List, Dict, Any, Optional
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import Tournament 
# We assume the classes live in models.py (same package)
from .models import Giocatore

main_log = logging.getLogger('main_sim')

DB_NAME = "data/nba_sim.db"

def get_db_connection():
    """Creates and returns a database connection."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Allows access to columns by name
    return conn

# --- SAVE FUNCTIONS ---

def save_season_data(torneo: 'Tournament'):
    """
    Orchestrator function that saves all the relevant data at the end of a season.
    """
    main_log.debug(f"--- DB MANAGER (DEBUG MODE): Starting save of Season {torneo.season_number} ---")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if torneo.campione:
             main_log.debug(f"  - Saving champion: {torneo.campione.nome}")
        
        all_players = [p for s in torneo.squadre for p in s.roster]
        main_log.debug(f"  - Found {len(all_players)} players in total to process.")

        for i, player in enumerate(all_players):
            # LOG BEFORE EVERY PLAYER OPERATION
            main_log.debug(f"\n  -> Processing player {i+1}/{len(all_players)}: {player.nome} (Team: {player.squadra.nome if player.squadra else 'N/A'})")

            if player.season_stats.partite_giocate == 0:
                main_log.debug("     - SKIP: 0 games played.")
                continue

            player_id = _get_or_create_player_id(cursor, player)
            main_log.debug(f"     - ID DB: {player_id}")
            
            team_id = _get_team_id(cursor, player.squadra.nome) if player.squadra else None
            main_log.debug(f"     - Team ID DB: {team_id}")
            
            main_log.debug("     - Trying to save career stats...")
            _save_player_career_stats(cursor, player, player_id, team_id, torneo.season_number)
            main_log.debug("     - Career stats saved successfully.")
            
            main_log.debug("     - Trying to save awards...")
            _save_player_awards(cursor, player, player_id, torneo)
            main_log.debug("     - Awards saved successfully.")

        main_log.debug("\n--- DB MANAGER (DEBUG MODE): All players processed. Attempting final COMMIT...")
        conn.commit()
        main_log.debug("--- DB MANAGER: COMMIT EXECUTED. Save completed successfully. ---")
    except Exception as e: # Catch ANY exception
        main_log.error("\n\n!!!!!!!!! CRITICAL ERROR WHILE SAVING THE DB !!!!!!!!!")
        main_log.error(f"THE ERROR OCCURRED ON PLAYER: {player.nome if 'player' in locals() else 'UNKNOWN'}")
        main_log.error(f"ERROR DETAILS: {e}")
        import traceback
        traceback.print_exc()
        main_log.error("Executing ROLLBACK. No data was saved.")
        conn.rollback()
    finally:
        conn.close()


def _save_player_career_stats(cursor, player: Giocatore, player_id: int, team_id: Optional[int], season: int):
    """Saves a player's complete statistics for a given season. (FIXED VERSION)"""
    rs = player.season_stats
    po = player.playoff_stats

    # List of the column names (31 in total) - English column names
    columns = [
        'player_id', 'team_id', 'season', 'age', 'is_champion',
        'rs_games_played', 'rs_points', 'rs_rebounds', 'rs_assists', 'rs_blocks', 'rs_steals',
        'rs_free_throws_made', 'rs_free_throws_attempted', 'rs_two_pointers_made', 'rs_two_pointers_attempted',
        'rs_three_pointers_made', 'rs_three_pointers_attempted', 'rs_turnovers',
        'po_games_played', 'po_points', 'po_rebounds', 'po_assists', 'po_blocks', 'po_steals',
        'po_free_throws_made', 'po_free_throws_attempted', 'po_two_pointers_made', 'po_two_pointers_attempted',
        'po_three_pointers_made', 'po_three_pointers_attempted', 'po_turnovers'
    ]
    
    # Dynamically build the '?' placeholder string
    # This approach is error-proof: the number of '?' always matches
    # the number of columns.
    placeholders = ', '.join(['?'] * len(columns))
    
    # Tuple of values to insert (31 in total)
    values = (
        player_id, team_id, season, player.eta,
        (player.squadra.nome == player.squadra.torneo.campione.nome) if player.squadra and player.squadra.torneo and player.squadra.torneo.campione else False,
        # Regular Season Stats
        rs.partite_giocate, rs.punti, rs.rimbalzi, rs.assist, rs.blocks, rs.steals,
        rs.punti_liberi, rs.tiri_liberi_tentati, rs.tiri_fatti_2, rs.tiri_tentati_2,
        rs.tiri_fatti_3, rs.tiri_tentati_3, rs.turnover,
        # Playoff Stats
        po.partite_giocate, po.punti, po.rimbalzi, po.assist, po.blocks, po.steals,
        po.punti_liberi, po.tiri_liberi_tentati, po.tiri_fatti_2, po.tiri_tentati_2,
        po.tiri_fatti_3, po.tiri_tentati_3, po.turnover
    )

    # Build the final query
    query = f"INSERT INTO career_stats ({', '.join(columns)}) VALUES ({placeholders})"
    
    # Run the query
    try:
        cursor.execute(query, values)
    except Exception as e:
        main_log.error(f"!!! DEBUG: Error while running the query for {player.nome}")
        main_log.error(f"Number of columns: {len(columns)}")
        main_log.error(f"Number of values: {len(values)}")
        raise e

def _save_player_awards(cursor, player: Giocatore, player_id: int, torneo: 'Tournament'):
    """Saves the awards won by a player in a season."""
    awards = []
    if torneo.regular_season_mvp and torneo.regular_season_mvp.nome == player.nome:
        awards.append("MVP")
    if torneo.defensive_player_of_the_year and torneo.defensive_player_of_the_year.nome == player.nome:
        awards.append("DPOY")
    if torneo.sesto_uomo and torneo.sesto_uomo.nome == player.nome:
        awards.append("6th Man")
    if getattr(torneo, 'rookie_of_the_year', None) and torneo.rookie_of_the_year.nome == player.nome:
        awards.append("ROY")
    
    for i, team in enumerate(torneo.all_nba_teams):
        if player in team:
            awards.append(f"All-NBA {i+1}st")
    
    if player in getattr(torneo, 'all_defensive_team', []):
        awards.append("All-Defensive")
    if player in getattr(torneo, 'all_rookie_team', []):
        awards.append("All-Rookie")
            
    # And so on for the other awards...

    for award in awards:
        cursor.execute(
            "INSERT INTO awards (player_id, season, award) VALUES (?, ?, ?)",
            (player_id, torneo.season_number, award)
        )

# Make _get_player_id "smarter"
def _get_player_id(cursor, player_name: str) -> Optional[int]:
    """Helper to find a player's ID. If it does not exist, it does NOT create it."""
    cursor.execute("SELECT id FROM players WHERE name = ?", (player_name,))
    result = cursor.fetchone()
    return result['id'] if result else None

def _get_or_create_player_id(cursor, player: 'Giocatore') -> int:
    """
    Retrieves a player's ID. If the player is new (e.g. a rookie) and has no ID,
    inserts them into the 'players' table and returns the new ID.
    """
    if player.db_id is not None:
        return player.db_id

    # Try to look them up by name (fallback)
    existing_id = _get_player_id(cursor, player.nome)
    if existing_id:
        player.db_id = existing_id
        return existing_id

    # If they don't exist, it's a new player (rookie). Insert them.
    main_log.debug(f"DB INFO: New player '{player.nome}' not found in the DB. Inserting...")
    cursor.execute(
        "INSERT INTO players (name, role, age, overall, potential, provenance, pedigree) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (player.nome, player.ruolo, player.eta, player.valutazione, player.potenziale, player.provenance, player.pedigree)
    )
    new_id = cursor.lastrowid
    player.db_id = new_id
    
    # Also insert their abilities and tendencies dynamically and safely
    # (This part is crucial for rookies or new free agents)
    cursor.execute("PRAGMA table_info(abilities)")
    ab_cols = [r[1] for r in cursor.fetchall() if r[1] != 'player_id']
    if ab_cols:
        ab_cols_str = ", ".join(ab_cols)
        ab_placeholders = ", ".join(["?"] * (len(ab_cols) + 1))
        ab_vals = [new_id] + [getattr(player.abilita, c, 70) for c in ab_cols]
        cursor.execute(f"INSERT INTO abilities (player_id, {ab_cols_str}) VALUES ({ab_placeholders})", ab_vals)

    cursor.execute("PRAGMA table_info(tendencies)")
    tend_cols = [r[1] for r in cursor.fetchall() if r[1] != 'player_id']
    if tend_cols:
        tend_cols_str = ", ".join(tend_cols)
        tend_placeholders = ", ".join(["?"] * (len(tend_cols) + 1))
        tend_vals = [new_id] + [getattr(player.tendenze, c, 50) for c in tend_cols]
        cursor.execute(f"INSERT INTO tendencies (player_id, {tend_cols_str}) VALUES ({tend_placeholders})", tend_vals)

    main_log.debug(f"DB INFO: Player '{player.nome}' inserted with ID {new_id}.")
    return new_id

def _get_team_id(cursor, team_name: str) -> Optional[int]:
    """Helper to find a team's ID from its name."""
    cursor.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
    result = cursor.fetchone()
    return result['id'] if result else None


# --- LOAD FUNCTIONS (moved and centralized here) ---

def load_teams() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    teams = conn.execute("SELECT * FROM teams").fetchall()
    conn.close()
    return [dict(row) for row in teams]

def load_players_for_team(team_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    players = conn.execute("SELECT * FROM players WHERE team_id = ?", (team_id,)).fetchall()
    conn.close()
    return [dict(row) for row in players]

def load_free_agents() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    players = conn.execute("SELECT * FROM players WHERE team_id IS NULL").fetchall()
    conn.close()
    return [dict(row) for row in players]

def load_abilities(player_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    abilities = conn.execute("SELECT * FROM abilities WHERE player_id = ?", (player_id,)).fetchone()
    conn.close()
    return dict(abilities) if abilities else None

def load_tendencies(player_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    tendencies = conn.execute("SELECT * FROM tendencies WHERE player_id = ?", (player_id,)).fetchone()
    conn.close()
    return dict(tendencies) if tendencies else None

def load_player_stats_for_season(season_number: int) -> List[Dict[str, Any]]:
    """
    Loads the complete statistics of all players for a specific season.
    Computes averages and percentages on the fly.
    """
    conn = get_db_connection()
    
    # ### CHANGE #1: EXPAND THE QUERY ###
    # Add all the shooting fields we need for the calculations
    query = """
    SELECT
        p.id as player_id,
        p.name as player_name,
        t.name as team_name,
        cs.age,
        cs.rs_games_played as gp,
        cs.rs_points as pts,
        cs.rs_rebounds as reb,
        cs.rs_assists as ast,
        cs.rs_steals as stl,
        cs.rs_blocks as blk,
        
        -- Fields for percentages
        cs.rs_two_pointers_made as fg2m,
        cs.rs_two_pointers_attempted as fg2a,
        cs.rs_three_pointers_made as fg3m,
        cs.rs_three_pointers_attempted as fg3a,
        cs.rs_free_throws_made as ftm,
        cs.rs_free_throws_attempted as fta,
        cs.rs_turnovers as tov
        
    FROM career_stats cs
    JOIN players p ON cs.player_id = p.id
    LEFT JOIN teams t ON cs.team_id = t.id
    WHERE cs.season = ? AND cs.rs_games_played > 0
    """
    raw_stats = conn.execute(query, (season_number,)).fetchall()
    conn.close()

    processed_stats = []
    for row in raw_stats:
        player_data = dict(row)
        gp = player_data['gp']
        if gp <= 0: continue # Skip players who did not play

        # Shooting percentages
        
        # Total shot calculations
        fgm = player_data['fg2m'] + player_data['fg3m']
        fga = player_data['fg2a'] + player_data['fg3a']
        
        # Per-game averages (existing)
        player_data['ppg'] = round(player_data['pts'] / gp, 1)
        player_data['rpg'] = round(player_data['reb'] / gp, 1)
        player_data['apg'] = round(player_data['ast'] / gp, 1)
        player_data['spg'] = round(player_data['stl'] / gp, 1)
        player_data['bpg'] = round(player_data['blk'] / gp, 1)
        player_data['tovg'] = round(player_data['tov'] / gp, 1) # Turnovers per game

        # New percentages
        player_data['fg_pct'] = round(fgm / fga * 100, 1) if fga > 0 else 0.0
        player_data['fg3_pct'] = round(player_data['fg3m'] / player_data['fg3a'] * 100, 1) if player_data['fg3a'] > 0 else 0.0
        player_data['ft_pct'] = round(player_data['ftm'] / player_data['fta'] * 100, 1) if player_data['fta'] > 0 else 0.0
        
        # True Shooting Percentage (TS%) - a key advanced metric
        ts_denominator = 2 * (fga + 0.44 * player_data['fta'])
        player_data['ts_pct'] = round(player_data['pts'] / ts_denominator * 100, 1) if ts_denominator > 0 else 0.0

        processed_stats.append(player_data)
        
    return processed_stats

def get_available_seasons() -> List[int]:
    """Returns a list of the seasons for which statistics exist."""
    conn = get_db_connection()
    seasons = conn.execute("SELECT DISTINCT season FROM career_stats ORDER BY season DESC").fetchall()
    conn.close()
    return [row['season'] for row in seasons]

def load_all_career_stats() -> List[Dict[str, Any]]:
    """
    Loads the complete statistics history of all players,
    joining the tables to get complete data.
    """
    conn = get_db_connection()
    query = """
    SELECT
        p.name as player_name,
        t.name as team_name,
        cs.season,
        cs.age,
        cs.rs_games_played,
        cs.rs_points,
        cs.rs_rebounds,
        cs.rs_assists,
        cs.po_games_played,
        cs.po_points,
        cs.po_rebounds,
        cs.po_assists
    FROM career_stats cs
    JOIN players p ON cs.player_id = p.id
    LEFT JOIN teams t ON cs.team_id = t.id
    ORDER BY p.name, cs.season
    """
    stats = conn.execute(query).fetchall()
    conn.close()
    return [dict(row) for row in stats]