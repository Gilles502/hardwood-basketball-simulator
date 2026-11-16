# records.py
# Module for tracking and managing league records (single-game highs, etc.)

from datetime import datetime
from typing import Optional, Dict, Any
import logging
logger = logging.getLogger('main_sim')

# Global records storage
LEAGUE_RECORDS = {
    "points_single_game": None,
    "rebounds_single_game": None,
    "assists_single_game": None,
    "steals_single_game": None,
    "blocks_single_game": None,
    "three_pointers_single_game": None,
    "triple_doubles_count": {}  # player_id -> count
}

def _create_record(value: int, player_name: str, player_id: str, team_name: str, 
                   opponent_name: str, season: int) -> Dict[str, Any]:
    """Create a record entry."""
    return {
        "value": value,
        "player_name": player_name,
        "player_id": player_id,
        "team_name": team_name,
        "opponent_name": opponent_name,
        "season": season,
        "date": datetime.now().strftime("%Y-%m-%d")
    }


def check_and_update_records(player_stats: Any, player_name: str, player_id: str,
                              team_name: str, opponent_name: str, season: int = 1) -> list:
    """
    Check if any new records were set and update accordingly.
    Returns a list of record categories that were broken.
    """
    global LEAGUE_RECORDS
    records_broken = []
    
    # Map stat names to record categories
    stat_checks = [
        ("punti", "points_single_game", "points"),
        ("rimbalzi", "rebounds_single_game", "rebounds"),
        ("assist", "assists_single_game", "assists"),
        ("steals", "steals_single_game", "steals"),
        ("blocks", "blocks_single_game", "blocks"),
        ("tiri_fatti_3", "three_pointers_single_game", "three_pointers"),
    ]
    
    for item in stat_checks:
        stat_attr, record_key, franchise_stat = item
        stat_value = getattr(player_stats, stat_attr, 0)
        if stat_value <= 0:
            continue
            
        current_record = LEAGUE_RECORDS.get(record_key)
        
        # Check if this is a new league record
        if current_record is None or stat_value > current_record["value"]:
            LEAGUE_RECORDS[record_key] = _create_record(
                value=stat_value,
                player_name=player_name,
                player_id=player_id,
                team_name=team_name,
                opponent_name=opponent_name,
                season=season
            )
            records_broken.append({
                "category": record_key,
                "value": stat_value,
                "player_name": player_name,
                "previous_value": current_record["value"] if current_record else None,
                "previous_holder": current_record["player_name"] if current_record else None
            })

        # Check and update franchise-level record
        try:
            from core.franchise_legacy import record_franchise_game_performance
            record_franchise_game_performance(
                team_name=team_name,
                player_name=player_name,
                stat_name=franchise_stat,
                value=stat_value,
                opponent=opponent_name,
                season_num=season
            )
        except Exception:
            logger.warning("Ignored error in check_and_update_records()", exc_info=True)
    
    # Check for triple-double
    punti = getattr(player_stats, 'punti', 0)
    rimbalzi = getattr(player_stats, 'rimbalzi', 0)
    assist = getattr(player_stats, 'assist', 0)
    
    if punti >= 10 and rimbalzi >= 10 and assist >= 10:
        if player_id not in LEAGUE_RECORDS["triple_doubles_count"]:
            LEAGUE_RECORDS["triple_doubles_count"][player_id] = {
                "count": 0,
                "player_name": player_name
            }
        LEAGUE_RECORDS["triple_doubles_count"][player_id]["count"] += 1
    
    return records_broken


def get_all_records() -> Dict[str, Any]:
    """Get all current records."""
    records = {}
    
    for key, value in LEAGUE_RECORDS.items():
        if key == "triple_doubles_count":
            # Sort by count and get top 10
            sorted_td = sorted(
                LEAGUE_RECORDS["triple_doubles_count"].items(),
                key=lambda x: x[1]["count"],
                reverse=True
            )[:10]
            records["triple_doubles_leaders"] = [
                {"player_id": pid, **data} for pid, data in sorted_td
            ]
        elif value is not None:
            records[key] = value
    
    return records



def clear_records():
    """Clear all records (for testing or new league)."""
    global LEAGUE_RECORDS
    LEAGUE_RECORDS = {
        "points_single_game": None,
        "rebounds_single_game": None,
        "assists_single_game": None,
        "steals_single_game": None,
        "blocks_single_game": None,
        "three_pointers_single_game": None,
        "triple_doubles_count": {}
    }

def export_raw_records() -> Dict[str, Any]:
    """Export the raw LEAGUE_RECORDS dictionary for serialization."""
    global LEAGUE_RECORDS
    return dict(LEAGUE_RECORDS)

def import_raw_records(records_data: Optional[Dict[str, Any]]):
    """Restore the LEAGUE_RECORDS dictionary from saved state."""
    global LEAGUE_RECORDS
    if isinstance(records_data, dict):
        LEAGUE_RECORDS = dict(records_data)
        if "triple_doubles_count" not in LEAGUE_RECORDS:
            LEAGUE_RECORDS["triple_doubles_count"] = {}
    else:
        clear_records()


# Record display names for the UI
RECORD_DISPLAY_NAMES = {
    "points_single_game": "🏀 Points in a Single Game",
    "rebounds_single_game": "💪 Rebounds in a Single Game", 
    "assists_single_game": "🎯 Assists in a Single Game",
    "steals_single_game": "🖐️ Steals in a Single Game",
    "blocks_single_game": "🛡️ Blocks in a Single Game",
    "three_pointers_single_game": "☄️ Threes in a Single Game"
}
