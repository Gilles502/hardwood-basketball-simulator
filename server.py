# server.py (FINAL AND CORRECTED VERSION - v4 "Just-In-Time")

from flask import Flask, jsonify, request, send_file, send_from_directory, Response
from datetime import datetime
import main as simulation_logic
from core import paths
from core.config import CONFIG
from core.league import catalog as league_catalog
from core.league.registry import FranchiseRegistry, get_active_registry, reset_active_registry, set_active_registry
from core.league.schema import LeagueError
from core.roles import ROLES, normalize_role, normalize_role_keys
from core.co_gm_tool import export_co_gm_data
from core.dashboard_summary import build_summary as build_dashboard_summary
from core.league_finances import build_economy as build_league_finances, team_outlook as build_team_outlook
from core.end_season import clamp_hub_step, end_season_status, league_snapshot, remember_market, restore_previous_teams, roster_snapshot
from core.scouting_view import scouted_prospects
from core.lottery_view import complete_details, lottery_preview
from offseason.draft import completed_draft_payload
import shutil
import logging
import os
import sys
import json
import re

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Disable caching of static files so the browser does not keep old JS/CSS versions
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- Saves: one at a time, after the key game moments, and a close that waits for running work ---
import threading
import time

SAVE_LOCK = threading.RLock()
_INFLIGHT_LOCK = threading.Condition()
_INFLIGHT = 0

# Game moments that change the career and had no save of their own (the calendar and season sims autosave
# inside their routes; the trade deadline and the season start run inside those). The draft saves once, at its
# end (concludi_draft_logica): it runs pick by pick in memory.
AUTOSAVE_AFTER_ROUTES = frozenset({
    "/api/start_offseason",
    "/api/offseason/hub_step",
    "/api/offseason/run_options_decision",
    "/api/offseason/free_agency/simulate_day",
    "/api/offseason/free_agency/match_rfa",
    "/api/simula_playoff_turno",
    "/api/simula_playin_game",
    "/api/nbatv/simulate-next-game",
    "/api/execute-user-trade",
    "/api/execute-3-team-trade",
    "/api/trades/execute-4-team",
    "/api/trade-block/respond",
})


def _request_started():
    global _INFLIGHT
    with _INFLIGHT_LOCK:
        _INFLIGHT += 1


def _request_finished():
    global _INFLIGHT
    with _INFLIGHT_LOCK:
        _INFLIGHT = max(0, _INFLIGHT - 1)
        _INFLIGHT_LOCK.notify_all()


def wait_for_idle(timeout_s: float) -> bool:
    """True once no game request (non-GET /api/) is running, False if the timeout passes first."""
    with _INFLIGHT_LOCK:
        return _INFLIGHT_LOCK.wait_for(lambda: _INFLIGHT == 0, timeout=timeout_s)


def _is_game_request() -> bool:
    return request.method != "GET" and request.path.startswith("/api/")


@app.before_request
def _count_request_start():
    if _is_game_request():
        _request_started()  # teardown always runs, so count first even when the run lock answers below
        if sim_run_active() and request.path not in SIM_RUN_ROUTES:
            return jsonify({"error": "Stop the simulation first", "sim_running": True}), 409


# Live simulation run: the frontend sims one quiet day per request. While a run is going, every other game
# route is refused, so nothing changes the league between two days. The flag expires if the run goes quiet.
SIM_RUN_ROUTES = frozenset({"/api/calendar/simulate_day", "/api/calendar/sim_run_end",
                            # POSTs that change no league data (a search, the news 'seen' marker), like any GET page
                            "/api/news/seen", "/api/database/finder"})
_SIM_RUN_LAST_DAY = None


def sim_run_active() -> bool:
    return _SIM_RUN_LAST_DAY is not None and time.monotonic() - _SIM_RUN_LAST_DAY < CONFIG.LIVE_SIM.RUN_STALE_S


def _sim_milestones(torneo) -> dict:
    """Calendar days the Dashboard's 'Sim until' offers: trade deadline and the first All-Star break day."""
    days = list(getattr(torneo, 'calendario', None) or [])
    deadline = next((i for i, d in enumerate(days) if "TRADE_DEADLINE" in (getattr(d, 'events', None) or [])), None)
    all_star = next((i for i, d in enumerate(days) if getattr(d, 'phase', '') == "ALL_STAR_BREAK"), None)
    return {"trade_deadline_day": deadline,
            "trade_deadline_done": bool(getattr(torneo, '_trade_deadline_completed', False)),
            "all_star_day": all_star}


@app.teardown_request
def _count_request_end(_exc=None):
    if _is_game_request():
        _request_finished()


@app.after_request
def _autosave_after_key_route(response):
    if request.method == "POST" and request.path in AUTOSAVE_AFTER_ROUTES and response.status_code < 400:
        body = response.get_json(silent=True) if response.is_json else None
        if not (isinstance(body, dict) and (body.get("success") is False or "error" in body)):
            auto_save_active_game()
    return response

# --- Global State Management ---
SIMULATION_TOURNAMENT = None
LEAGUE_STATE = "PRE_SEASON"
ACTIVE_DRAFT_INSTANCE = None
ACTIVE_FREE_AGENCY_INSTANCE = None
ACTIVE_SAVE_NAME = None

# Let the trade code read the live phase / running draft without importing this module.
from core import runtime_state
runtime_state.register(league_state=lambda: LEAGUE_STATE, active_draft=lambda: ACTIVE_DRAFT_INSTANCE)

# NEW global variables to pass the FA data between routes
OFFSEASON_FA_POOL = []
OFFSEASON_PREVIOUS_TEAMS = {}
NEGOTIATION_ATTEMPTS = {}

# --- NBA TV Game-by-Game Playoff State ---
# Tracks each playoff series: {series_id: {team1, team2, wins1, wins2, round, games_log}}
PLAYOFF_SERIES = {}
# Current game number being played (1-7)
PLAYOFF_CURRENT_GAME = 0
# Set to True when playoffs are set up for game-by-game simulation
PLAYOFF_GAMEBYGAME_MODE = False

# --- NEWS FEED SYSTEM (imported from core.news_generator) ---
from core import news_generator
from core.news_generator import (
    get_news_feed, add_news,
    generate_regular_season_news as _gen_rs_news,
    generate_draft_news, generate_signing_news, generate_trade_news,
    generate_power_rankings_news, generate_trade_deadline_news
)
from dataclasses import asdict
from core.models import (
    UserProfileGM, GMContract, GMBadge, GMAchievement, BoardProfile, BoardObjective,
    applica_regole_anni_opzioni_contratto
)
from core.records import clear_records
from core.board_engine import (
    init_board_profile_for_team, init_user_gm_profile,
    update_approval_rating, evaluate_gm_contract_and_renewal,
    generate_seasonal_objectives, check_gm_achievements,
    generate_gm_job_offers, board_profile_to_dict, user_gm_profile_to_dict,
    sync_board_objectives, generate_annual_season_report,
    get_or_create_summit_data, submit_summit_decision,
    check_board_concern_trigger, resolve_board_concern,
    generate_job_carousel_offers, switch_user_franchise
)
from core.front_office.seasons import ensure_season_marks
from core.front_office.state import build_front_office, sync_user_seat, user_moves_team
from core.front_office.plans import checkpoint_new_season
from core.front_office import trade_requests
from core.front_office.wishes import asked_out
from core.front_office.view import gm_card, gm_market, league_table

main_log = logging.getLogger('main_sim')



# Wrappers that pass tournament data to the news generation
def generate_regular_season_news():
    """Conference leaders (and the MVP when known): All-Star break and end of the regular season."""
    torneo = SIMULATION_TOURNAMENT
    if not torneo:
        return
    east_teams = sorted([s for s in torneo.squadre if s.conference == "East"],
                        key=lambda x: x.vittorie, reverse=True)
    west_teams = sorted([s for s in torneo.squadre if s.conference == "West"],
                        key=lambda x: x.vittorie, reverse=True)
    _gen_rs_news(east_teams, west_teams, torneo.regular_season_mvp, torneo.season_number)


def generate_champion_news(champion_name, finals_mvp=None):
    """The title story, with the Finals MVP when known."""
    body = f"The {champion_name} win the championship."
    if finals_mvp:
        body += f" {finals_mvp} is the Finals MVP."
    add_news("highlights", f"{champion_name} are champions", body, teams=[champion_name], kind="champion", tier=3,
             players=[finals_mvp] if finals_mvp else None)


# --- Helper Functions for the API Payloads ---

def get_full_league_data_payload():
    """Sends the complete payload, to be used only for the initial load and for resets."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if SIMULATION_TOURNAMENT is None: return {"error": "Simulation not initialized"}
        
    data = simulation_logic._get_api_data_from_tournament(SIMULATION_TOURNAMENT, lean=False)
    data['league_state'] = LEAGUE_STATE
    data['end_season'] = end_season_status(LEAGUE_STATE, getattr(SIMULATION_TOURNAMENT, 'offseason_log_data', None))
    data['season_number'] = SIMULATION_TOURNAMENT.season_number
    data['anno_corrente'] = getattr(SIMULATION_TOURNAMENT, 'anno_corrente', 2025)
    data['player_team_name'] = SIMULATION_TOURNAMENT.squadra_giocatore.nome if SIMULATION_TOURNAMENT.squadra_giocatore else None
    data['is_spectator'] = getattr(SIMULATION_TOURNAMENT, 'is_spectator', False)
    data['is_fired'] = getattr(SIMULATION_TOURNAMENT, 'is_fired', False)
    data['firing_info'] = getattr(SIMULATION_TOURNAMENT, 'firing_info', None)
    data['user_role'] = getattr(SIMULATION_TOURNAMENT, 'user_role', 'gm_coach')
    data['enable_play_in'] = getattr(SIMULATION_TOURNAMENT, 'enable_play_in', True)
    data['sim_milestones'] = _sim_milestones(SIMULATION_TOURNAMENT)
    return data

def get_lean_league_data_payload():
    """Sends a lightweight payload for all the intermediate actions, for speed and safety."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if SIMULATION_TOURNAMENT is None: return {"error": "Simulation not initialized"}
        
    data = simulation_logic._get_api_data_from_tournament(SIMULATION_TOURNAMENT, lean=True)
    data['league_state'] = LEAGUE_STATE
    data['end_season'] = end_season_status(LEAGUE_STATE, getattr(SIMULATION_TOURNAMENT, 'offseason_log_data', None))
    data['season_number'] = SIMULATION_TOURNAMENT.season_number
    data['anno_corrente'] = getattr(SIMULATION_TOURNAMENT, 'anno_corrente', 2025)
    data['player_team_name'] = SIMULATION_TOURNAMENT.squadra_giocatore.nome if SIMULATION_TOURNAMENT.squadra_giocatore else None
    data['is_spectator'] = getattr(SIMULATION_TOURNAMENT, 'is_spectator', False)
    data['is_fired'] = getattr(SIMULATION_TOURNAMENT, 'is_fired', False)
    data['firing_info'] = getattr(SIMULATION_TOURNAMENT, 'firing_info', None)
    data['user_role'] = getattr(SIMULATION_TOURNAMENT, 'user_role', 'gm_coach')
    data['enable_play_in'] = getattr(SIMULATION_TOURNAMENT, 'enable_play_in', True)
    data['sim_milestones'] = _sim_milestones(SIMULATION_TOURNAMENT)
    return data

def ensure_calendar_integrity(torneo):
    """
    Makes sure the procedural NBA calendar is present, consistent and usable
    for the season currently in progress.
    If the calendar is missing, empty, or if we are in PRE_SEASON and all the games
    are already played / _current_gameday >= len(calendar) (stale state from a previous season),
    automatically regenerates the calendar for the active season (176 days, 1230 games).
    """
    global LEAGUE_STATE
    if not torneo:
        return
    cal = getattr(torneo, 'calendario', None)
    cur_day = getattr(torneo, '_current_gameday', 0)
    cur_year = getattr(torneo, 'anno_corrente', 2025)
    
    needs_gen = False
    if not cal or len(cal) == 0:
        needs_gen = True
    elif LEAGUE_STATE == "PRE_SEASON":
        if cur_day >= len(cal):
            needs_gen = True
        elif all(getattr(g, 'played', False) for d in cal for g in getattr(d, 'games', [])):
            # Only a calendar whose every game is played is stale; day 0 alone being played is normal mid-season.
            needs_gen = True
    elif cur_day >= len(cal) and getattr(torneo, 'season_number', 1) > 1 and getattr(torneo, 'campione', None) is None and LEAGUE_STATE in ("PRE_SEASON", "ALL_STAR_BREAK"):
        needs_gen = True
        
    if needs_gen:
        print(f"--- AUTO-RECOVERY: Regenerating the NBA calendar for Season {getattr(torneo, 'season_number', 1)} (Year {cur_year}) ---", flush=True)
        torneo.genera_calendario()
        torneo.imposta_rotazioni_stagione()
        try:
            auto_save_active_game()
        except Exception:
            pass

# --- API Endpoints ---

from trades.calendar import user_trade_window
from core.save_manager import (
    get_all_saves_metadata, save_game, load_game, 
    duplicate_save, rename_save, delete_save, migrate_legacy_files,
    restore_tournament_state, get_historical_file_path, set_active_save_name, get_save_path,
    saved_league_registry
)


from core.league.draft_source import copy_league_draft_classes

def save_current_game(save_name):
    """Every save goes through here. The saved state reads the phase from the tournament object, which the
    server never updated during the season: a playoff save came back as PRE_SEASON and the calendar check
    then wiped the calendar. Copy the live LEAGUE_STATE onto it first."""
    with SAVE_LOCK:
        SIMULATION_TOURNAMENT.league_state = LEAGUE_STATE
        return save_game(save_name, SIMULATION_TOURNAMENT, extra_metadata={"phase": LEAGUE_STATE})

def loaded_phase(meta, tournament):
    """Phase of a loaded save. The metadata phase is the live LEAGUE_STATE at save time; the state file's
    league_state was stale (always PRE_SEASON) in saves made before save_current_game existed."""
    return meta.get("phase") or getattr(tournament, 'league_state', "PRE_SEASON")

def auto_save_active_game():
    """Automatically saves the league state to the active save folder on every advance."""
    global ACTIVE_SAVE_NAME, SIMULATION_TOURNAMENT, LEAGUE_STATE
    if SIMULATION_TOURNAMENT and ACTIVE_SAVE_NAME:
        try:
            save_current_game(ACTIVE_SAVE_NAME)
        except Exception as e:
            print(f"Error during auto-save: {e}")

def _open_folder(path):
    """Opens a folder in the system file manager (Explorer on Windows)."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 - a local folder the game owns
    else:
        import subprocess
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


@app.route('/api/app_info', methods=['GET'])
def api_app_info():
    """Settings window: the game version and the real saves folder (Documents/Hardwood/saves in the exe)."""
    from core import version as game_version
    from core.save_manager import get_saves_dir
    return jsonify({"version": game_version.label(), "saves_dir": os.path.abspath(get_saves_dir())})


@app.route('/api/open_saves_folder', methods=['POST'])
def api_open_saves_folder():
    from core.save_manager import get_saves_dir
    try:
        _open_folder(os.path.abspath(get_saves_dir()))
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not open the folder: {e}"}), 500
    return jsonify({"ok": True})


@app.route('/api/saves', methods=['GET'])
def api_get_saves():
    """Returns the list of all the available saves with their metadata."""
    saves = get_all_saves_metadata()
    return jsonify({
        "success": True,
        "saves": saves,
        "active_save_name": ACTIVE_SAVE_NAME
    })

@app.route('/api/saves/save', methods=['POST'])
def api_save_game():
    """Saves the current league to the saves/<save_name>/ folder."""
    global SIMULATION_TOURNAMENT, ACTIVE_SAVE_NAME, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "No active simulation to save"}), 400
        
    data = request.get_json(silent=True) or {}
    save_name = data.get("save_name") or ACTIVE_SAVE_NAME or "My_NBA_League"
    
    try:
        metadata = save_current_game(save_name)
        ACTIVE_SAVE_NAME = metadata['save_name']
        return jsonify({
            "success": True,
            "message": f"Save '{metadata['display_name']}' completed successfully!",
            "metadata": metadata
        })
    except Exception as e:
        return jsonify({"error": f"Error while saving: {str(e)}"}), 500

def apply_loaded_save_state(save_name: str, loaded: dict):
    """Restores both the league state from the DB and the in-memory state (standings, playoffs, user team, FA pool, news, records)."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE, ACTIVE_SAVE_NAME, OFFSEASON_FA_POOL, OFFSEASON_PREVIOUS_TEAMS
    global NEGOTIATION_ATTEMPTS, PLAYOFF_SERIES, PLAYOFF_CURRENT_GAME, PLAYOFF_GAMEBYGAME_MODE
    global ACTIVE_FREE_AGENCY_INSTANCE, DRAFT_INSTANCE
    
    meta = loaded.get("metadata", {})
    state_data = loaded.get("state_data", {})
    
    ACTIVE_SAVE_NAME = meta.get("save_name", save_name)
    set_active_save_name(ACTIVE_SAVE_NAME)
    
    # The save's franchise registry goes in before setup: the Tournament reads conferences, divisions and
    # rivalries from it (an old save gets its legacy registry, never the league of the career played before).
    saved_registry = saved_league_registry(state_data)
    set_active_registry(saved_registry)
    # Reload the base tournament instance from the restored DB. The save's own league_meta goes in too, so
    # setup's draft-class read follows the save (a league save never reads the Real Names 2002 mod's classes).
    saved_meta = ((state_data or {}).get("league") or {}).get("meta") or {}
    SIMULATION_TOURNAMENT = simulation_logic.setup_simulation(league_meta=saved_meta,
                                                              franchise_registry=saved_registry)
    if hasattr(SIMULATION_TOURNAMENT, 'era_name') and meta.get('era'):
        SIMULATION_TOURNAMENT.era_name = meta.get('era')
        
    # Restore the full in-memory state of the tournament (including records and news)
    restore_tournament_state(SIMULATION_TOURNAMENT, state_data)
    import core.models
    core.models.ACTIVE_TOURNAMENT = SIMULATION_TOURNAMENT
    simulation_logic.ACTIVE_TOURNAMENT = SIMULATION_TOURNAMENT
    
    # Apply the automatic NBA rules on contract years and options and designate the untouchables
    for s in getattr(SIMULATION_TOURNAMENT, 'squadre', []):
        s.designa_intoccabili(SIMULATION_TOURNAMENT)
        for p in getattr(s, 'roster', []):
            if getattr(p, 'contract', None):
                applica_regole_anni_opzioni_contratto(p)
    
    LEAGUE_STATE = loaded_phase(meta, SIMULATION_TOURNAMENT)
    SIMULATION_TOURNAMENT.league_state = LEAGUE_STATE

    # An old save made at the break before the weekend was played: play it now, as entering the break does
    # (otherwise the page shows it upcoming during the break and it plays unseen in Sim 2nd Half).
    if LEAGUE_STATE == 'ALL_STAR_BREAK' and not getattr(SIMULATION_TOURNAMENT, 'all_star_weekend_complete', False):
        SIMULATION_TOURNAMENT.run_all_star_weekend()

    # Reset/alignment of transition states
    NEGOTIATION_ATTEMPTS = {}
    ACTIVE_FREE_AGENCY_INSTANCE = None
    DRAFT_INSTANCE = None
    
    extra_playoff = state_data.get("extra_playoff_data", {})
    PLAYOFF_CURRENT_GAME = extra_playoff.get("playoff_current_game", 0)
    PLAYOFF_GAMEBYGAME_MODE = extra_playoff.get("playoff_gamebygame_mode", False)
    PLAYOFF_SERIES = {}

    # Restore the FA pool if we are in the offseason
    if getattr(SIMULATION_TOURNAMENT, 'nuovi_free_agents', None):
        OFFSEASON_FA_POOL = SIMULATION_TOURNAMENT.nuovi_free_agents
        OFFSEASON_PREVIOUS_TEAMS = restore_previous_teams(SIMULATION_TOURNAMENT)
    elif getattr(SIMULATION_TOURNAMENT, 'free_agents_pool', None):
        OFFSEASON_FA_POOL = SIMULATION_TOURNAMENT.free_agents_pool

    # Check and ensure the calendar integrity for the active season
    ensure_calendar_integrity(SIMULATION_TOURNAMENT)

@app.route('/api/saves/load', methods=['POST'])
def api_load_game():
    """Loads a save specified by name."""
    data = request.get_json(silent=True) or {}
    save_name = data.get("save_name")
    
    if not save_name:
        return jsonify({"error": "Save name required"}), 400
        
    try:
        loaded = load_game(save_name)
        meta = loaded.get("metadata", {})
        
        apply_loaded_save_state(save_name, loaded)
            
        result = {
            "success": True,
            "message": f"Save '{meta.get('display_name', save_name)}' loaded!",
            "payload": get_full_league_data_payload()
        }
        if loaded.get("recovered_from_backup"):
            result["warning"] = "The last save was damaged: the previous save was loaded."
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Unable to load the save: {str(e)}"}), 500

@app.route('/api/saves/duplicate', methods=['POST'])
def api_duplicate_save():
    """Duplicates a save folder to create a test/cloned point."""
    data = request.get_json(silent=True) or {}
    source_name = data.get("source_save_name")
    target_name = data.get("target_save_name")
    
    if not source_name or not target_name:
        return jsonify({"error": "source_save_name and target_save_name are required"}), 400
        
    try:
        meta = duplicate_save(source_name, target_name)
        return jsonify({
            "success": True,
            "message": f"Save duplicated as '{meta['display_name']}'!",
            "metadata": meta
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/saves/rename', methods=['POST'])
def api_rename_save():
    """Renames a save."""
    data = request.get_json(silent=True) or {}
    old_name = data.get("old_save_name")
    new_name = data.get("new_display_name")
    
    if not old_name or not new_name:
        return jsonify({"error": "old_save_name and new_display_name are required"}), 400
        
    try:
        meta = rename_save(old_name, new_name)
        global ACTIVE_SAVE_NAME
        if ACTIVE_SAVE_NAME == old_name:
            ACTIVE_SAVE_NAME = meta['save_name']
        return jsonify({
            "success": True,
            "message": "Save renamed!",
            "metadata": meta
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/saves/delete', methods=['POST'])
def api_delete_save():
    """Deletes a save folder."""
    global ACTIVE_SAVE_NAME
    data = request.get_json(silent=True) or {}
    save_name = data.get("save_name")
    
    if not save_name:
        return jsonify({"error": "Save name required"}), 400
        
    try:
        success = delete_save(save_name)
        if ACTIVE_SAVE_NAME == save_name:
            ACTIVE_SAVE_NAME = None
        return jsonify({
            "success": success,
            "message": f"Save '{save_name}' deleted."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/career-leaders', methods=['GET'])
def get_career_leaders():
    """All-Time Leaders boards (core/records_view.py) from player_careers.json."""
    from core.history_view import season_years
    from core.records_view import career_leaders_view
    careers = _read_historical_json("player_careers.json", {})
    history = _read_historical_json("league_history.json", [])
    return jsonify(career_leaders_view(careers if isinstance(careers, dict) else {}, _user_team_name(),
                                       season_years(history if isinstance(history, list) else []),
                                       getattr(SIMULATION_TOURNAMENT, 'starting_year', None)))

_NEWS_PHASES = {"PRE_SEASON": "Regular season", "ALL_STAR_BREAK": "Regular season",
                "REGULAR_SEASON_END": "Regular season", "PLAYOFFS_IN_PROGRESS": "Playoffs",
                "PLAYOFFS_END": "Playoffs"}


def _news_clock():
    """The game moment stamped on news items (core.news_generator.set_clock_provider)."""
    torneo = SIMULATION_TOURNAMENT
    if not torneo:
        return None
    now = {"season": torneo.season_number, "day": None, "date": "",
           "phase": _NEWS_PHASES.get(LEAGUE_STATE, "Offseason")}
    calendar = getattr(torneo, 'calendario', None) or []
    if LEAGUE_STATE in ("PRE_SEASON", "ALL_STAR_BREAK") and calendar:
        day = min(getattr(torneo, '_current_gameday', 0), len(calendar) - 1)
        now["day"] = day
        now["date"] = getattr(calendar[day], 'date', "") or ""
    return now


news_generator.set_clock_provider(_news_clock)


@app.route('/api/news', methods=['GET'])
def get_news():
    """The league news. Filters: after_id (newer than), kind (comma list), mine=1 (user's team), min_tier
    (after the user-team raise), season, limit. Items come newest first."""
    torneo = SIMULATION_TOURNAMENT
    user_team = torneo.squadra_giocatore.nome if torneo and torneo.squadra_giocatore else None
    items = [news_generator.view_item(item, user_team) for item in get_news_feed()]

    unread_big = news_generator.unread_big_count(user_team)
    try:
        after_id = int(request.args.get('after_id', 0))
        min_tier = int(request.args.get('min_tier', 1))
        limit = max(1, min(int(request.args.get('limit', 400)), CONFIG.NEWS.MAX_ITEMS))
        season = request.args.get('season')
        season = int(season) if season else None
    except ValueError:
        return jsonify({"error": "Invalid news filter"}), 400
    kinds = {k for k in request.args.get('kind', '').split(',') if k}
    mine_only = request.args.get('mine') == '1'

    def keep(item):
        return (item["id"] > after_id and item["tier"] >= min_tier
                and (not kinds or item["kind"] in kinds)
                and (not mine_only or item["mine"])
                and (season is None or item["season"] == season))

    shown = [item for item in items if keep(item)]
    return jsonify({
        "news": shown[:limit],
        "total": len(shown),
        "last_seen_id": news_generator.get_last_seen_id(),
        "unread_big": unread_big,
        "clock": news_generator.get_clock(),
    })


@app.route('/api/news/seen', methods=['POST'])
def mark_news_seen():
    """The user opened the news page: every current item counts as read."""
    return jsonify({"last_seen_id": news_generator.mark_all_seen()})


@app.route('/api/dati_stagione', methods=['GET'])
def get_dati_stagione():
    return jsonify(get_full_league_data_payload())

@app.route('/api/co_gm/export', methods=['GET', 'POST'])
def co_gm_export():
    global SIMULATION_TOURNAMENT, LEAGUE_STATE, ACTIVE_FREE_AGENCY_INSTANCE, OFFSEASON_FA_POOL
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    try:
        fa_objs = None
        if ACTIVE_FREE_AGENCY_INSTANCE and hasattr(ACTIVE_FREE_AGENCY_INSTANCE, 'unrestricted_free_agents'):
            fa_objs = ACTIVE_FREE_AGENCY_INSTANCE.unrestricted_free_agents
        elif OFFSEASON_FA_POOL:
            fa_objs = OFFSEASON_FA_POOL
        res = export_co_gm_data(SIMULATION_TOURNAMENT, LEAGUE_STATE, fa_objects=fa_objs)
        return jsonify(res)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/set_player_team', methods=['POST'])
def set_player_team():
    global SIMULATION_TOURNAMENT, ACTIVE_SAVE_NAME
    data = request.get_json() or {}
    team_name = data.get('team_name')
    if not team_name:
        SIMULATION_TOURNAMENT.squadra_giocatore = None
        SIMULATION_TOURNAMENT.is_spectator = True
        SIMULATION_TOURNAMENT.is_fired = False
        SIMULATION_TOURNAMENT.firing_info = None
    else:
        squadra_scelta = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == team_name), None)
        SIMULATION_TOURNAMENT.squadra_giocatore = squadra_scelta
        SIMULATION_TOURNAMENT.is_spectator = False
        SIMULATION_TOURNAMENT.is_fired = False
        SIMULATION_TOURNAMENT.firing_info = None
        
        # Initialize the board profile and GM profile for the chosen franchise
        if squadra_scelta:
            board_prof = init_board_profile_for_team(squadra_scelta, force_reset=True)
            board_prof.approval_rating = 75.0
            board_prof.status_label = "Stable"
            generate_seasonal_objectives(squadra_scelta, board_prof)
            gm = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
            if not gm:
                gm = init_user_gm_profile(squadra_scelta.nome)
                SIMULATION_TOURNAMENT.user_gm_profile = gm
            gm.current_team_name = squadra_scelta.nome
            if not gm.contract or gm.contract.years_remaining <= 0:
                gm.contract = GMContract(salary_per_year=4.5, years_remaining=4, total_years=4)
    sync_user_seat(SIMULATION_TOURNAMENT)  # no CPU GM at the user's team, one everywhere else

    if ACTIVE_SAVE_NAME:
        try:
            save_current_game(ACTIVE_SAVE_NAME)
        except Exception as e:
            print(f"Auto-save error after team selection: {e}")
            
    return jsonify(get_full_league_data_payload())

@app.route('/api/board', methods=['GET'])
def get_board_info():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    user_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
    if not gm_prof:
        user_team_name = user_team.nome if user_team else "Free Agent GM"
        gm_prof = init_user_gm_profile(user_team_name)
        SIMULATION_TOURNAMENT.user_gm_profile = gm_prof

    is_fired_flag = getattr(SIMULATION_TOURNAMENT, 'is_fired', False)
    firing_info = getattr(SIMULATION_TOURNAMENT, 'firing_info', None)

    if not user_team:
        job_offers = generate_gm_job_offers(SIMULATION_TOURNAMENT, gm_prof) if is_fired_flag else []
        return jsonify({
            "board_profile": None,
            "user_gm_profile": user_gm_profile_to_dict(gm_prof) if gm_prof else None,
            "is_fired": is_fired_flag,
            "firing_info": firing_info,
            "job_offers": job_offers,
            "annual_reports": getattr(gm_prof, 'season_reports', []) if gm_prof else [],
            "live_report": None
        })

    board_prof = init_board_profile_for_team(user_team)
    gm_prof.current_team_name = user_team.nome

    # Sync live objectives
    sync_board_objectives(user_team, SIMULATION_TOURNAMENT, board_prof)

    # Check live achievements
    check_gm_achievements(gm_prof, SIMULATION_TOURNAMENT)

    # Generate the seasonal report in real time
    live_report = generate_annual_season_report(user_team, SIMULATION_TOURNAMENT, gm_prof, is_live=True)

    is_fired = is_fired_flag or board_prof.approval_rating < 25.0
    job_offers = []
    if is_fired or (gm_prof.contract and gm_prof.contract.years_remaining <= 0):
        job_offers = generate_gm_job_offers(SIMULATION_TOURNAMENT, gm_prof)

    return jsonify({
        "board_profile": board_profile_to_dict(board_prof),
        "user_gm_profile": user_gm_profile_to_dict(gm_prof),
        "is_fired": is_fired,
        "firing_info": firing_info,
        "job_offers": job_offers,
        "annual_reports": getattr(gm_prof, 'season_reports', []),
        "live_report": live_report
    })

@app.route('/api/board/annual_reports', methods=['GET'])
def get_annual_reports():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    user_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
    if not gm_prof:
        user_team_name = user_team.nome if user_team else "Free Agent GM"
        gm_prof = init_user_gm_profile(user_team_name)
        SIMULATION_TOURNAMENT.user_gm_profile = gm_prof

    live_report = None
    if user_team:
        live_report = generate_annual_season_report(user_team, SIMULATION_TOURNAMENT, gm_prof, is_live=True)

    return jsonify({
        "archived_reports": getattr(gm_prof, 'season_reports', []),
        "live_report": live_report
    })

@app.route('/api/board/extend_contract', methods=['POST'])
def extend_gm_contract():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT or not getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None):
        return jsonify({"error": "GM profile not found"}), 400

    gm_prof = SIMULATION_TOURNAMENT.user_gm_profile
    contract = gm_prof.contract
    if contract.can_extend and contract.extension_offered:
        ext = contract.extension_offered
        contract.years_remaining += ext.get("years", 3)
        contract.salary_per_year = ext.get("salary", contract.salary_per_year)
        contract.can_extend = False
        contract.extension_offered = None
        return jsonify({"success": True, "message": "Contract renewed successfully!", "contract": asdict(contract)})
    
    return jsonify({"error": "No renewal available at the moment"}), 400

@app.route('/api/board/gm_job_offers', methods=['GET'])
def get_job_offers_endpoint():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    user_gm = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
    if not user_gm:
        user_team_name = SIMULATION_TOURNAMENT.squadra_giocatore.nome if SIMULATION_TOURNAMENT.squadra_giocatore else "Unknown"
        user_gm = init_user_gm_profile(user_team_name)
        SIMULATION_TOURNAMENT.user_gm_profile = user_gm

    offers = generate_gm_job_offers(SIMULATION_TOURNAMENT, user_gm)
    return jsonify({"job_offers": offers})

@app.route('/api/board/accept_job_offer', methods=['POST'])
def accept_job_offer_endpoint():
    global SIMULATION_TOURNAMENT, ACTIVE_SAVE_NAME
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    data = request.get_json() or {}
    new_team_name = data.get("team_name")
    salary = data.get("salary", 4.5)
    years = data.get("years", 4)

    new_team = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == new_team_name), None)
    if not new_team:
        return jsonify({"error": f"Team '{new_team_name}' not found"}), 404

    # Update the player's team
    old_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    SIMULATION_TOURNAMENT.squadra_giocatore = new_team
    SIMULATION_TOURNAMENT.is_spectator = False
    SIMULATION_TOURNAMENT.is_fired = False
    SIMULATION_TOURNAMENT.firing_info = None
    # The new team's CPU GM goes to the market, the old team gets a GM
    user_moves_team(SIMULATION_TOURNAMENT, old_team.nome if old_team else None, new_team.nome)
    sync_user_seat(SIMULATION_TOURNAMENT)

    # Initialize a new board profile for the new team
    board_prof = init_board_profile_for_team(new_team, force_reset=True)
    board_prof.approval_rating = 75.0
    board_prof.status_label = "Stable"
    generate_seasonal_objectives(new_team, board_prof)

    # Update the GM profile
    gm = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
    if not gm:
        gm = init_user_gm_profile(new_team.nome)
        SIMULATION_TOURNAMENT.user_gm_profile = gm

    gm.current_team_name = new_team.nome
    gm.contract = GMContract(salary_per_year=salary, years_remaining=years, total_years=years)
    gm.teams_managed_history.append({
        "team": new_team.nome,
        "start_season": getattr(SIMULATION_TOURNAMENT, 'season_number', 1),
        "titles": 0
    })

    if ACTIVE_SAVE_NAME:
        try:
            save_current_game(ACTIVE_SAVE_NAME)
        except Exception as e:
            print(f"Auto-save error after GM franchise change: {e}")

    return jsonify({
        "success": True,
        "message": f"Job accepted! You are now the new GM of the {new_team.nome}.",
        "new_team_name": new_team.nome,
        "payload": get_full_league_data_payload()
    })

# --- FRONT OFFICE (AI GM): the league's GMs, a GM card, the GM market ---
@app.route('/api/front_office/gms', methods=['GET'])
def front_office_gms():
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    return jsonify(league_table(SIMULATION_TOURNAMENT))

@app.route('/api/front_office/gm', methods=['GET'])
def front_office_gm_card():
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    team_name = request.args.get('team', '')
    card = gm_card(SIMULATION_TOURNAMENT, team_name)
    if card is None:
        return jsonify({"error": f"Team '{team_name}' not found"}), 404
    return jsonify(card)

@app.route('/api/front_office/market', methods=['GET'])
def front_office_market():
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    return jsonify(gm_market(SIMULATION_TOURNAMENT))

# --- BOARD CONCERN & FRANCHISE CAROUSEL ENDPOINTS ---
@app.route('/api/board/concern', methods=['GET'])
def get_board_concern_dialogue():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 400

    user_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    if not user_team:
        return jsonify({"concern": None})

    concern = getattr(user_team, 'pending_board_concern', None)
    return jsonify({"concern": concern})

@app.route('/api/board/concern/resolve', methods=['POST'])
def resolve_board_concern_endpoint():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 400

    user_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    if not user_team:
        return jsonify({"error": "No user team found"}), 400

    gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
    data = request.get_json() or {}
    action = data.get("action")
    if not action:
        return jsonify({"error": "action is required"}), 400

    res = resolve_board_concern(user_team, gm_prof, action, SIMULATION_TOURNAMENT)
    return jsonify(res)

@app.route('/api/board/job_carousel', methods=['GET'])
def get_job_carousel_offers_endpoint():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 400

    gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
    if not gm_prof:
        user_team_name = SIMULATION_TOURNAMENT.squadra_giocatore.nome if SIMULATION_TOURNAMENT.squadra_giocatore else "Unknown"
        gm_prof = init_user_gm_profile(user_team_name)
        SIMULATION_TOURNAMENT.user_gm_profile = gm_prof

    offers = generate_job_carousel_offers(SIMULATION_TOURNAMENT, gm_prof)
    return jsonify({
        "offers": offers,
        "prestige_score": getattr(gm_prof, 'prestige_score', 65.0)
    })

@app.route('/api/board/switch_team', methods=['POST'])
def switch_team_carousel_endpoint():
    global SIMULATION_TOURNAMENT, ACTIVE_SAVE_NAME
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 400

    gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
    if not gm_prof:
        return jsonify({"error": "No user GM profile"}), 400

    data = request.get_json() or {}
    target_team_name = data.get("target_team_name")
    offer = data.get("offer")
    if not target_team_name:
        return jsonify({"error": "target_team_name is required"}), 400

    old_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    res = switch_user_franchise(SIMULATION_TOURNAMENT, gm_prof, target_team_name, offer)
    if not res.get("success"):
        return jsonify(res), 400
    # The new team's CPU GM goes to the market, the old team gets a GM
    user_moves_team(SIMULATION_TOURNAMENT, old_team.nome if old_team else None, target_team_name)
    sync_user_seat(SIMULATION_TOURNAMENT)

    if ACTIVE_SAVE_NAME:
        try:
            save_current_game(ACTIVE_SAVE_NAME)
        except Exception as e:
            print(f"Error auto-saving after franchise switch: {e}")

    res["payload"] = get_full_league_data_payload()
    return jsonify(res)

@app.route('/api/board/resign', methods=['POST'])
def resign_gm_endpoint():
    global SIMULATION_TOURNAMENT, ACTIVE_SAVE_NAME
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 400

    gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
    if not gm_prof:
        return jsonify({"error": "No user GM profile"}), 400

    curr_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    curr_team_name = curr_team.nome if curr_team else "Unknown"
    
    gm_prof.teams_managed_history.append({
        "team": curr_team_name,
        "start_season": getattr(SIMULATION_TOURNAMENT, 'season_number', 1),
        "end_season": getattr(SIMULATION_TOURNAMENT, 'season_number', 1),
        "resigned": True
    })
    gm_prof.current_team_name = "Free Agent GM"
    SIMULATION_TOURNAMENT.is_spectator = True
    SIMULATION_TOURNAMENT.squadra_giocatore = None
    sync_user_seat(SIMULATION_TOURNAMENT)  # the team left behind gets a GM

    offers = generate_job_carousel_offers(SIMULATION_TOURNAMENT, gm_prof)

    if ACTIVE_SAVE_NAME:
        try:
            save_current_game(ACTIVE_SAVE_NAME)
        except Exception as e:
            print(f"Error auto-saving after GM resignation: {e}")

    return jsonify({
        "success": True,
        "message": f"You have resigned from the {curr_team_name}. You are now on the open GM market.",
        "offers": offers,
        "payload": get_full_league_data_payload()
    })

# --- PRE-SEASON GM & HEAD COACH SUMMIT ENDPOINTS ---

@app.route('/api/front_office/summit', methods=['GET'])
def get_front_office_summit():
    """Returns the current state or the proposal of the Summit between the GM and the Head Coach."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT or not SIMULATION_TOURNAMENT.squadra_giocatore:
        return jsonify({"available": False, "reason": "No active player team"})
    
    data = get_or_create_summit_data(SIMULATION_TOURNAMENT.squadra_giocatore, SIMULATION_TOURNAMENT)
    return jsonify(data)

@app.route('/api/front_office/summit/respond', methods=['POST'])
def respond_front_office_summit():
    """Receives the Head Coach's response or counter-proposal and aligns the franchise."""
    global SIMULATION_TOURNAMENT, ACTIVE_SAVE_NAME
    if not SIMULATION_TOURNAMENT or not SIMULATION_TOURNAMENT.squadra_giocatore:
        return jsonify({"error": "No active player team"}), 400
    
    req = request.get_json(silent=True) or {}
    choice = req.get("choice", "consensus")
    
    res = submit_summit_decision(SIMULATION_TOURNAMENT.squadra_giocatore, SIMULATION_TOURNAMENT, choice)
    auto_save_active_game()
    return jsonify({
        "success": True,
        "summit": res.get("summit"),
        "payload": get_lean_league_data_payload()
    })


@app.route('/api/era_teams', methods=['GET'])
def get_era_teams():
    """Returns the 30 teams of the requested era with top-8 OVR and main star for the Setup Wizard."""
    era = request.args.get('era', 'modern')
    league_info = None
    if era == "2002":
        # The 2002 era plays the active league (Mods screen); its DB is built on demand.
        try:
            db_file = league_catalog.ensure_active_league_db()
            active = league_catalog.active_league() or {}
        except LeagueError as e:
            return jsonify({"error": "No playable league", "errors": e.errors}), 400
        except Exception as e:  # disk or sqlite failure while building: still a JSON answer
            return jsonify({"error": f"Cannot prepare the league database: {e}"}), 500
        league_info = {"id": active.get("id"), "name": active.get("name")}
    else:
        db_file = paths.game_path("data", "nba_sim_modern.db")
        if not os.path.exists(db_file):
            db_file = os.path.join("data", "nba_sim.db")

    import sqlite3
    try:
        conn = sqlite3.connect(db_file)
        teams_rows = conn.execute("SELECT id, name, conference, owner_personality FROM teams ORDER BY name").fetchall()
        east_teams = []
        west_teams = []
        
        for t_id, t_name, t_conf, owner_p in teams_rows:
            top8_rows = conn.execute(
                "SELECT name, overall, role FROM players WHERE team_id = ? ORDER BY overall DESC LIMIT 8",
                (t_id,)
            ).fetchall()
            
            if top8_rows:
                avg_ovr = round(sum(r[1] for r in top8_rows) / len(top8_rows), 1)
                star_name = top8_rows[0][0]
                star_ovr = top8_rows[0][1]
                star_role = top8_rows[0][2]
            else:
                avg_ovr = 75.0
                star_name = "N/A"
                star_ovr = 75
                star_role = "SG"
                
            # The DB's conference column; a DB without one (modern) asks the active league by name
            if t_conf not in ('East', 'West'):
                t_conf = get_active_registry().conference_of(t_name)
            conf = 'East' if t_conf == 'East' else 'West'
            team_info = {
                "id": t_id,
                "name": t_name,
                "conference": conf,
                "ovr": avg_ovr,
                "star_player": star_name,
                "star_ovr": star_ovr,
                "star_role": star_role,
                "owner_personality": owner_p or "Bilanciato"
            }
            if conf == 'East':
                east_teams.append(team_info)
            else:
                west_teams.append(team_info)
                
        conn.close()
        return jsonify({
            "success": True, 
            "east": east_teams, 
            "west": west_teams, 
            "teams": east_teams + west_teams,
            "era": era,
            "league": league_info
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/leagues', methods=['GET'])
def get_leagues():
    """The league catalogue for the Mods screen: the built-in league and every mod, with the active id."""
    active = league_catalog.active_league()
    return jsonify({"leagues": league_catalog.list_leagues(), "active": active["id"] if active else None})


@app.route('/api/leagues/build', methods=['POST'])
def build_league():
    """Validates the chosen league, builds its starting DB and makes it active. 400 with the errors on failure."""
    data = request.get_json(silent=True) or {}
    league_id = data.get("league_id")
    if not isinstance(league_id, str) or not league_id:
        return jsonify({"ok": False, "errors": ["league_id is required"]}), 400
    result = league_catalog.build_and_activate(league_id)
    return jsonify(result), (200 if result["ok"] else 400)


@app.route('/api/init_simulation', methods=['POST'])
def init_simulation():
    global SIMULATION_TOURNAMENT, LEAGUE_STATE, ACTIVE_FREE_AGENCY_INSTANCE, OFFSEASON_FA_POOL, DRAFT_INSTANCE, ACTIVE_SAVE_NAME
    global NEGOTIATION_ATTEMPTS, PLAYOFF_SERIES, PLAYOFF_CURRENT_GAME, PLAYOFF_GAMEBYGAME_MODE
    
    try:
        data = request.get_json(silent=True) or {}
        start_era = data.get("start_era", "modern")
        custom_save_name = data.get("save_name")
        league_settings = data.get("league_settings", {})
        selected_team = data.get("selected_team")
        user_role = data.get("user_role", "gm_coach")
        league_settings["user_role"] = user_role
        
        import datetime
        era_title = "2002 Era" if start_era == "2002" else "Modern Era"
        from core.save_manager import default_save_name, unique_save_name
        default_name = default_save_name(None if user_role == "spectator" else selected_team, start_era)
        save_name = unique_save_name(custom_save_name.strip() if custom_save_name and custom_save_name.strip() else default_name)
        
        print(f"--- SERVER: Initializing new simulation '{save_name}' (Era: {start_era}, Team: {selected_team}, Role: {user_role}) ---", flush=True)

        # 0. The 2002 era starts from the active league (Mods screen): resolve it before any state changes.
        league_entry = league_data = league_db = league_draft_dir = None
        if start_era == "2002":
            try:
                league_db = league_catalog.ensure_active_league_db()
                league_data = league_catalog.active_league_data()
            except LeagueError as e:
                return jsonify({"error": "No playable league: " + "; ".join(e.errors[:5]), "errors": e.errors}), 400
            league_entry = league_catalog.active_league()
            league_draft_dir = league_catalog.active_draft_dir()

        # 1. Reset state variables
        LEAGUE_STATE = "PRE_SEASON"
        ACTIVE_FREE_AGENCY_INSTANCE = None
        OFFSEASON_FA_POOL = None
        DRAFT_INSTANCE = None
        ACTIVE_SAVE_NAME = save_name
        set_active_save_name(save_name)
        NEGOTIATION_ATTEMPTS = {}
        PLAYOFF_SERIES = {}
        PLAYOFF_CURRENT_GAME = 0
        PLAYOFF_GAMEBYGAME_MODE = False
        
        # Clear news feed
        try:
            news_generator.reset_news()
        except Exception:
            pass
        
        # 2. Clean save history JSON and text files for clean fresh state
        for f in ["league_history.json", "hall_of_fame.json", "retired_players_ids.json", "player_careers.json", "franchise_records.json", "trades_history.txt"]:
            h_path = get_historical_file_path(f)
            if os.path.exists(h_path):
                try:
                    os.remove(h_path)
                except OSError:
                    pass
        th_file = get_historical_file_path("trades_history.txt")
        with open(th_file, "w", encoding="utf-8") as f:
            f.write("")
                    
        # Reset records
        clear_records()
        
        # 3. Copy target database template to active database
        db_active = os.path.join("data", "nba_sim.db")
        if start_era == "2002":
            db_template = league_db
        else:
            db_template = paths.game_path("data", "nba_sim_modern.db")
            
        if not os.path.exists(db_template):
            db_backup = os.path.join("data", "nba_sim_modern.db")
            if os.path.exists(db_active) and not os.path.exists(db_backup):
                try:
                    shutil.copyfile(db_active, db_backup)
                except Exception:
                    pass
                
        try:
            if os.path.exists(db_template):
                import sqlite3
                src_conn = sqlite3.connect(db_template)
                dst_conn = sqlite3.connect(db_active)
                src_conn.backup(dst_conn)
                dst_conn.close()
                src_conn.close()
                print(f"Applied database template '{db_template}' to active db via SQLite backup.", flush=True)
            else:
                shutil.copyfile(db_template, db_active)
                print(f"Copied database template '{db_template}' to active db.", flush=True)
        except Exception as e:
            print(f"WARNING: SQLite backup failed, attempting fallback copy: {e}", flush=True)
            try:
                shutil.copyfile(db_template, db_active)
            except Exception as e2:
                print(f"ERROR: Failed to copy database template: {e2}", flush=True)
                return jsonify({"error": f"Failed to initialize database: {str(e2)}"}), 500
            
        # 4. Reload simulation with League Settings
        try:
            league_registry = None
            league_meta = None
            if league_data is not None:
                # Installed before setup: the Tournament reads divisions and rivalries from the active registry.
                league_registry = FranchiseRegistry.from_league(league_data)
                set_active_registry(league_registry)
                league_meta = {"id": league_entry["id"], "name": league_entry["name"], "era": league_entry["era"]}
                # The new save's own copy of the league's draft classes (none = generated rookies), in place
                # before setup reads the first class; it replaces any folder an older career left there.
                copy_league_draft_classes(league_draft_dir, get_save_path(ACTIVE_SAVE_NAME))
            else:
                # Modern era: the default registry, never the league of a 2002 career played before.
                reset_active_registry()
            # league_meta is on the Tournament before setup's draft-class read (else it reads the mod's class).
            SIMULATION_TOURNAMENT = simulation_logic.setup_simulation(
                league_settings=league_settings, league_meta=league_meta, franchise_registry=league_registry)
            SIMULATION_TOURNAMENT.era_name = era_title

            # Setup User Team & Role
            SIMULATION_TOURNAMENT.user_role = user_role
            SIMULATION_TOURNAMENT.resolve_play_in()
            if selected_team and user_role != 'spectator':
                squadra_scelta = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == selected_team), None)
                if squadra_scelta:
                    SIMULATION_TOURNAMENT.squadra_giocatore = squadra_scelta
                    SIMULATION_TOURNAMENT.is_spectator = False
                    SIMULATION_TOURNAMENT.is_fired = False
                    SIMULATION_TOURNAMENT.firing_info = None
                    
                    board_prof = init_board_profile_for_team(squadra_scelta, force_reset=True)
                    board_prof.approval_rating = 75.0
                    board_prof.status_label = "Stable"
                    generate_seasonal_objectives(squadra_scelta, board_prof)
                    gm = init_user_gm_profile(squadra_scelta.nome)
                    SIMULATION_TOURNAMENT.user_gm_profile = gm
                    gm.current_team_name = squadra_scelta.nome
                    gm.contract = GMContract(salary_per_year=4.5, years_remaining=4, total_years=4)
                    
                    # Initialize the Pre-Season Summit proposal
                    try:
                        get_or_create_summit_data(squadra_scelta, SIMULATION_TOURNAMENT)
                    except Exception as e_summit:
                        print(f"Warning: error pre-generating summit data: {e_summit}")
                else:
                    SIMULATION_TOURNAMENT.squadra_giocatore = None
                    SIMULATION_TOURNAMENT.is_spectator = True
            else:
                SIMULATION_TOURNAMENT.squadra_giocatore = None
                SIMULATION_TOURNAMENT.is_spectator = True
                SIMULATION_TOURNAMENT.is_fired = False
                SIMULATION_TOURNAMENT.firing_info = None
                SIMULATION_TOURNAMENT.user_gm_profile = None

            # CPU GMs again, now that the user's team (no CPU GM there) or spectator mode is known.
            SIMULATION_TOURNAMENT.front_office = build_front_office(SIMULATION_TOURNAMENT)
            ensure_season_marks(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.front_office)

            print(f"League re-initialized for Season {SIMULATION_TOURNAMENT.season_number}. Teams: {len(SIMULATION_TOURNAMENT.squadre)}", flush=True)
            
            # 5. Immediately save the new save's folder
            save_current_game(ACTIVE_SAVE_NAME)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to reload simulation: {str(e)}"}), 500
            
        return jsonify(get_full_league_data_payload())
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Init simulation uncaught error: {str(e)}"}), 500

# --- MAIN GAME FLOW (Regular Season and Playoffs) ---

def _generate_power_rankings():
    """Generate power rankings news based on current standings."""
    global SIMULATION_TOURNAMENT
    torneo = SIMULATION_TOURNAMENT
    if not torneo:
        return
    
    # Get all teams sorted by wins
    all_teams = sorted(torneo.squadre, key=lambda x: (x.vittorie, -x.sconfitte), reverse=True)
    
    # Build ranked data for news
    teams_ranked = []
    for team in all_teams[:10]:  # Top 10
        teams_ranked.append({
            'name': team.nome,
            'record': f"{team.vittorie}-{team.sconfitte}",
            'movement': 0  # Could track week-to-week changes in future
        })
    
    # Determine week number based on games played
    if all_teams:
        total_games = all_teams[0].vittorie + all_teams[0].sconfitte
        week_number = (total_games // 3) + 1  # Roughly 3 games per week
    else:
        week_number = 1
    
    generate_power_rankings_news(teams_ranked, week_number, season=torneo.season_number)

def _on_all_star_break_reached():
    """Hook run only once when the league enters the All-Star Break
    (both through 'Sim 1st Half' and through day-by-day simulation)."""
    # Play the All-Star Weekend from the first half stats (no-op once played)
    SIMULATION_TOURNAMENT.run_all_star_weekend()

    # CPU mid-season coach firings: simula_first_half runs them itself; a day-by-day run reaches the break
    # without it, so run them here, once per season (the flag is reset at each new season).
    if not getattr(SIMULATION_TOURNAMENT, '_first_half_complete', False):
        SIMULATION_TOURNAMENT._first_half_complete = True
        SIMULATION_TOURNAMENT._gestisci_licenziamenti_midseason()

    # Generate mid-season news
    generate_regular_season_news()
    
    # Generate power rankings at All-Star break
    _generate_power_rankings()
    
    # Trade deadline approaching news
    generate_trade_deadline_news(7, season=SIMULATION_TOURNAMENT.season_number)
    
    # Update Board Approval Rating & Objectives
    if SIMULATION_TOURNAMENT.squadra_giocatore:
        user_team = SIMULATION_TOURNAMENT.squadra_giocatore
        gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
        if not gm_prof:
            gm_prof = init_user_gm_profile(user_team.nome)
            SIMULATION_TOURNAMENT.user_gm_profile = gm_prof
        update_approval_rating(user_team, gm_prof, "weekly_check")


def _on_regular_season_end():
    """Hook run only once at the end of the Regular Season
    (both through 'Sim 2nd Half' and through day-by-day simulation)."""
    # Update Board Approval Rating, Objectives & GM Career Stats
    if SIMULATION_TOURNAMENT.squadra_giocatore:
        user_team = SIMULATION_TOURNAMENT.squadra_giocatore
        gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
        if not gm_prof:
            gm_prof = init_user_gm_profile(user_team.nome)
            SIMULATION_TOURNAMENT.user_gm_profile = gm_prof

        # Add regular season wins/losses to GM career
        gm_prof.career_wins += user_team.vittorie
        gm_prof.career_losses += user_team.sconfitte

        update_approval_rating(user_team, gm_prof, "season_end")

        # Check regular season achievements
        cap = getattr(SIMULATION_TOURNAMENT, 'salary_cap', 136.0)
        under_cap = user_team.payroll <= cap
        winning = user_team.vittorie > 41
        check_gm_achievements(gm_prof, SIMULATION_TOURNAMENT, {
            "season_wins": user_team.vittorie,
            "under_cap_and_winning": under_cap and winning
        })

    # Generate end of season news
    generate_regular_season_news()
    
    # Final power rankings before playoffs
    _generate_power_rankings()


def _apply_calendar_state_transitions(simulated_days):
    """Updates LEAGUE_STATE after a day-based simulation and runs the phase hooks.
    Unifies the 'day by day' path with the 'half season' one."""
    global LEAGUE_STATE
    if LEAGUE_STATE == "PRE_SEASON":
        for d in simulated_days:
            # 'is not None': a CalendarDay with no games (every break day) is falsy
            if d is not None and (getattr(d, 'phase', '') == "ALL_STAR_BREAK" or "ALL_STAR_GAME" in getattr(d, 'events', [])):
                LEAGUE_STATE = "ALL_STAR_BREAK"
                _on_all_star_break_reached()
                break

    cur_day = getattr(SIMULATION_TOURNAMENT, '_current_gameday', 0)
    if cur_day >= len(SIMULATION_TOURNAMENT.calendario) and LEAGUE_STATE in ("PRE_SEASON", "ALL_STAR_BREAK"):
        if LEAGUE_STATE == "PRE_SEASON":
            _on_all_star_break_reached()
        LEAGUE_STATE = "REGULAR_SEASON_END"
        _on_regular_season_end()


@app.route('/api/simula_regular_season', methods=['POST'])
def simula_regular_season():
    """Simulate first half of regular season then pause for All-Star."""
    global LEAGUE_STATE
    ensure_calendar_integrity(SIMULATION_TOURNAMENT)
    if LEAGUE_STATE == "PRE_SEASON":
        SIMULATION_TOURNAMENT.simula_first_half()
        LEAGUE_STATE = "ALL_STAR_BREAK"
        _on_all_star_break_reached()
        auto_save_active_game()
    return jsonify(get_full_league_data_payload())


@app.route('/api/simula_second_half', methods=['POST'])
def simula_second_half():
    """Resume and complete regular season after All-Star break."""
    global LEAGUE_STATE
    ensure_calendar_integrity(SIMULATION_TOURNAMENT)
    if LEAGUE_STATE == "ALL_STAR_BREAK":
        SIMULATION_TOURNAMENT.simula_second_half()
        LEAGUE_STATE = "REGULAR_SEASON_END"
        _on_regular_season_end()
        auto_save_active_game()
    return jsonify(get_full_league_data_payload())


@app.route('/api/calendar', methods=['GET'])
def get_calendar_api():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    ensure_calendar_integrity(SIMULATION_TOURNAMENT)

    start = request.args.get('start', default=None, type=int)
    count = request.args.get('count', default=None, type=int)
    team = request.args.get('team', default=None, type=str)

    days = SIMULATION_TOURNAMENT.calendario
    current_gameday = getattr(SIMULATION_TOURNAMENT, '_current_gameday', 0)

    # Filter by team if requested
    if team:
        filtered_days = []
        for d in days:
            matching_games = [g for g in d.games if g.home_team == team or g.away_team == team]
            if matching_games or d.events:
                d_dict = d.to_dict() if hasattr(d, 'to_dict') else d
                if isinstance(d_dict, dict):
                    d_dict = dict(d_dict)
                    d_dict['games'] = [g.to_dict() if hasattr(g, 'to_dict') else g for g in matching_games]
                filtered_days.append(d_dict)
        return jsonify({
            "current_day": current_gameday,
            "total_days": len(days),
            "days": filtered_days
        })

    # Slice if start and count provided
    if start is not None and count is not None:
        selected_days = days[start:start+count]
    else:
        selected_days = days

    serialized = [d.to_dict() if hasattr(d, 'to_dict') else d for d in selected_days]
    return jsonify({
        "current_day": current_gameday,
        "total_days": len(days),
        "days": serialized
    })


@app.route('/api/calendar/today', methods=['GET'])
def get_calendar_today_api():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    ensure_calendar_integrity(SIMULATION_TOURNAMENT)

    cur_idx = getattr(SIMULATION_TOURNAMENT, '_current_gameday', 0)
    if cur_idx < len(SIMULATION_TOURNAMENT.calendario):
        day = SIMULATION_TOURNAMENT.calendario[cur_idx]
        return jsonify({
            "current_day": cur_idx,
            "total_days": len(SIMULATION_TOURNAMENT.calendario),
            "day": day.to_dict() if hasattr(day, 'to_dict') else day
        })
    else:
        return jsonify({
            "current_day": cur_idx,
            "total_days": len(SIMULATION_TOURNAMENT.calendario),
            "completed": True,
            "day": None
        })


@app.route('/api/dashboard/summary', methods=['GET'])
def get_dashboard_summary_api():
    """Light read-only payload for the sidebar and Dashboard. Never mutates state (it is polled)."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 503
    try:
        user_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
        offers = getattr(SIMULATION_TOURNAMENT, 'pending_trade_block_offers', None) or []
        concern = bool(getattr(user_team, 'pending_board_concern', None)) if user_team else False
        summary = build_dashboard_summary(SIMULATION_TOURNAMENT, LEAGUE_STATE, CONFIG.DASHBOARD, len(offers), concern)
        summary["attention"]["news_unread"] = news_generator.unread_big_count(user_team.nome if user_team else None)
        return jsonify(summary)
    except Exception as e:
        logging.exception("dashboard summary failed")
        return jsonify({"error": str(e)}), 500


@app.route('/api/calendar/simulate_day', methods=['POST'])
def api_calendar_simulate_day():
    """One calendar day. Body {"autosave": false, "lean": true} is a live-run day: no save (the run saves once
    at /api/calendar/sim_run_end), the light payload, and the run lock refreshed."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE, _SIM_RUN_LAST_DAY
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    body = request.get_json(silent=True) or {}
    autosave = body.get("autosave", True) is not False
    payload = get_lean_league_data_payload if body.get("lean") else get_full_league_data_payload
    if not autosave:
        _SIM_RUN_LAST_DAY = time.monotonic()

    ensure_calendar_integrity(SIMULATION_TOURNAMENT)

    if LEAGUE_STATE not in ("PRE_SEASON", "ALL_STAR_BREAK"):
        return jsonify({"completed": True, "league_state": LEAGUE_STATE, "league_data": payload()})

    if getattr(SIMULATION_TOURNAMENT, '_current_gameday', 0) >= len(SIMULATION_TOURNAMENT.calendario):
        _apply_calendar_state_transitions([])
        if autosave:
            auto_save_active_game()
        return jsonify({"completed": True, "league_state": LEAGUE_STATE, "league_data": payload()})

    simulated_day = SIMULATION_TOURNAMENT.simula_giornata()
    cur_day = getattr(SIMULATION_TOURNAMENT, '_current_gameday', 0)

    # Shared phase transitions (All-Star Break / End of Regular Season)
    _apply_calendar_state_transitions([simulated_day])

    if autosave:
        auto_save_active_game()
    else:
        _SIM_RUN_LAST_DAY = time.monotonic()  # a long day must not let the lock expire mid-run
    return jsonify({
        "simulated_day": simulated_day.to_dict() if hasattr(simulated_day, 'to_dict') else None,
        "current_day": cur_day,
        "total_days": len(SIMULATION_TOURNAMENT.calendario),
        "league_state": LEAGUE_STATE,
        "league_data": payload()
    })


@app.route('/api/calendar/sim_run_end', methods=['POST'])
def api_calendar_sim_run_end():
    """End of a live run (target reached, Stop, or error): unlock the game routes, save once, full payload."""
    global _SIM_RUN_LAST_DAY
    _SIM_RUN_LAST_DAY = None
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    auto_save_active_game()
    return jsonify({"league_data": get_full_league_data_payload()})


@app.route('/api/calendar/simulate_week', methods=['POST'])
def api_calendar_simulate_week():
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    ensure_calendar_integrity(SIMULATION_TOURNAMENT)

    if LEAGUE_STATE not in ("PRE_SEASON", "ALL_STAR_BREAK"):
        return jsonify({"completed": True, "simulated_days": [], "league_state": LEAGUE_STATE, "league_data": get_full_league_data_payload()})

    days_simulated = SIMULATION_TOURNAMENT.simula_settimana()
    cur_day = getattr(SIMULATION_TOURNAMENT, '_current_gameday', 0)

    # Shared phase transitions (All-Star Break / End of Regular Season)
    _apply_calendar_state_transitions(days_simulated)

    auto_save_active_game()
    return jsonify({
        "simulated_days": [d.to_dict() if hasattr(d, 'to_dict') else d for d in days_simulated],
        "current_day": cur_day,
        "total_days": len(SIMULATION_TOURNAMENT.calendario),
        "league_state": LEAGUE_STATE,
        "league_data": get_full_league_data_payload()
    })


@app.route('/api/calendar/simulate_until', methods=['POST'])
def api_calendar_simulate_until():
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    ensure_calendar_integrity(SIMULATION_TOURNAMENT)

    if LEAGUE_STATE not in ("PRE_SEASON", "ALL_STAR_BREAK"):
        return jsonify({"completed": True, "simulated_days": [], "league_state": LEAGUE_STATE, "league_data": get_full_league_data_payload()})

    data = request.get_json(silent=True) or {}
    target_day = data.get('target_day')
    target_day_index = data.get('target_day_index')

    if target_day_index is None:
        if target_day is not None:
            include_target = data.get('include_target', False)
            if include_target:
                target_day_index = int(target_day)
            else:
                target_day_index = int(target_day) - 1 if int(target_day) > 0 else 0
        else:
            return jsonify({"error": "Parameter target_day or target_day_index required"}), 400

    target_day_index = max(0, min(int(target_day_index), len(SIMULATION_TOURNAMENT.calendario)))

    days_simulated = SIMULATION_TOURNAMENT.simula_fino_a_giornata(target_day_index)
    cur_day = getattr(SIMULATION_TOURNAMENT, '_current_gameday', 0)

    _apply_calendar_state_transitions(days_simulated)
    auto_save_active_game()

    return jsonify({
        "simulated_days_count": len(days_simulated),
        "current_day": cur_day,
        "total_days": len(SIMULATION_TOURNAMENT.calendario),
        "league_state": LEAGUE_STATE,
        "league_data": get_full_league_data_payload()
    })


@app.route('/api/calendar/simulate_game', methods=['POST'])
def api_calendar_simulate_game():
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    ensure_calendar_integrity(SIMULATION_TOURNAMENT)

    if LEAGUE_STATE not in ("PRE_SEASON", "ALL_STAR_BREAK"):
        return jsonify({"completed": True, "league_state": LEAGUE_STATE, "league_data": get_full_league_data_payload()})

    data = request.get_json(silent=True) or {}
    game_id = data.get('game_id')
    enable_play_log = bool(data.get('enable_play_log', False))
    if not game_id:
        return jsonify({"error": "Missing game_id parameter"}), 400

    res = SIMULATION_TOURNAMENT.simula_singola_partita_calendario(game_id, enable_play_log=enable_play_log)
    if not res:
        return jsonify({"error": f"Game {game_id} not found or not simulatable"}), 404

    cur_day = getattr(SIMULATION_TOURNAMENT, '_current_gameday', 0)
    day_completed = res.get('day_completed', False)

    if day_completed:
        prev_day_idx = max(0, cur_day - 1)
        if prev_day_idx < len(SIMULATION_TOURNAMENT.calendario):
            completed_day = SIMULATION_TOURNAMENT.calendario[prev_day_idx]
            _apply_calendar_state_transitions([completed_day])

    auto_save_active_game()

    return jsonify({
        "success": True,
        "game": res.get("game"),
        "day_completed": day_completed,
        "current_day": cur_day,
        "total_days": len(SIMULATION_TOURNAMENT.calendario),
        "league_state": LEAGUE_STATE,
        "league_data": get_full_league_data_payload(),
        "play_log": res.get("play_log", []),
        "home_team": res.get("home_team"),
        "away_team": res.get("away_team"),
        "winner": res.get("winner")
    })



@app.route('/api/calendar/box_score/<game_id>', methods=['GET'])
def get_calendar_box_score_api(game_id):
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    # 1. Look in the tournament's box_scores dictionary
    box_scores = getattr(SIMULATION_TOURNAMENT, 'box_scores', {})
    if game_id in box_scores:
        return jsonify({"success": True, "box_score": box_scores[game_id]})

    # 2. Look among the calendar games
    for d in getattr(SIMULATION_TOURNAMENT, 'calendario', []):
        for g in getattr(d, 'games', []):
            if g.game_id == game_id:
                if hasattr(g, 'box_score') and g.box_score:
                    return jsonify({"success": True, "box_score": g.box_score})
                
                # If the game was played but the detailed box score is not present, build a fallback
                if g.played:
                    q_scores = getattr(g, 'quarter_scores', {}) or {}
                    fallback_bs = {
                        "game_id": g.game_id,
                        "date": g.date,
                        "day_index": g.day_index,
                        "home_team": {
                            "name": g.home_team,
                            "score": g.home_score,
                            "quarters": q_scores.get('home', []),
                            "players": [],
                            "totals": {"pts": g.home_score}
                        },
                        "away_team": {
                            "name": g.away_team,
                            "score": g.away_score,
                            "quarters": q_scores.get('away', []),
                            "players": [],
                            "totals": {"pts": g.away_score}
                        },
                        "top_performer": getattr(g, 'top_performer', None),
                        "is_legacy": True
                    }
                    return jsonify({"success": True, "box_score": fallback_bs})
                return jsonify({"error": "Game not yet played"}), 400

    return jsonify({"error": "Game not found"}), 404


@app.route('/api/simula_playoff_turno', methods=['POST'])
def simula_playoff_turno():
    global LEAGUE_STATE
    
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    data = request.get_json(silent=True) or {}
    bulk = data.get("bulk", False)
    watch_series_id = data.get("watch_series_id", None)
    
    # 1. If the state is REGULAR_SEASON_END, we set up the playoffs and enter PLAYOFFS_IN_PROGRESS
    if LEAGUE_STATE == "REGULAR_SEASON_END":
        SIMULATION_TOURNAMENT._setup_playoffs()
        SIMULATION_TOURNAMENT.simula_turno_playoff()
        LEAGUE_STATE = "PLAYOFFS_IN_PROGRESS"
        
    elif LEAGUE_STATE == "PLAYOFFS_IN_PROGRESS":
        # If we are in PLAY_IN, we keep simulating one play-in game at a time (or do bulk if requested)
        watch_result = None
        if SIMULATION_TOURNAMENT.playoff_state == "PLAY_IN":
            if bulk:
                while SIMULATION_TOURNAMENT.playoff_state == "PLAY_IN":
                    SIMULATION_TOURNAMENT._simula_play_in()
            else:
                playin_res = SIMULATION_TOURNAMENT._simula_play_in(watch_series_id)
                if playin_res and "watch_game" in playin_res:
                    watch_result = playin_res["watch_game"]
        else:
            # We are in QF, SF, CF, FINALS
            if not getattr(SIMULATION_TOURNAMENT, 'active_playoff_series', None):
                SIMULATION_TOURNAMENT.setup_current_playoff_round()
                
            user_team = SIMULATION_TOURNAMENT.squadra_giocatore
            user_active = False
            if user_team:
                # Check whether the user's team is still alive in this round
                for series in SIMULATION_TOURNAMENT.active_playoff_series:
                    if (series["s1"].nome == user_team.nome or series["s2"].nome == user_team.nome) and series["winner_nome"] is None:
                        user_active = True
                        break
            
            if not bulk:
                # We simulate only one game for the active series, with live-watch support
                res = SIMULATION_TOURNAMENT.simula_gara_playoff_con_diretta(watch_series_id)
                if res and "watch_game" in res:
                    watch_result = res["watch_game"]
            else:
                # We simulate the whole round in bulk
                while SIMULATION_TOURNAMENT.active_playoff_series and any(s["winner_nome"] is None for s in SIMULATION_TOURNAMENT.active_playoff_series):
                    SIMULATION_TOURNAMENT.simula_gara_playoff()
                    
        # Check if playoffs are complete
        if SIMULATION_TOURNAMENT.campione:
            LEAGUE_STATE = "PLAYOFFS_END"
            generate_champion_news(SIMULATION_TOURNAMENT.campione.nome)

            if SIMULATION_TOURNAMENT.squadra_giocatore:
                user_team = SIMULATION_TOURNAMENT.squadra_giocatore
                gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
                if not gm_prof:
                    gm_prof = init_user_gm_profile(user_team.nome)
                    SIMULATION_TOURNAMENT.user_gm_profile = gm_prof
                
                if SIMULATION_TOURNAMENT.campione.nome == user_team.nome:
                    gm_prof.titles_won += 1
                    for th in gm_prof.teams_managed_history:
                        if th.get("team") == user_team.nome:
                            th["titles"] = th.get("titles", 0) + 1
                    check_gm_achievements(gm_prof, SIMULATION_TOURNAMENT)
                    update_approval_rating(user_team, gm_prof, "playoffs_end")
            
        payload = get_lean_league_data_payload()
        if watch_result:
            payload["watch_game"] = watch_result
        return jsonify(payload)
        
    return jsonify(get_lean_league_data_payload())

@app.route('/api/playin', methods=['GET'])
def get_playin_data():
    """Return Play-In tournament data for UI display."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    torneo = SIMULATION_TOURNAMENT
    
    # Helper to serialize game result (remove non-serializable objects)
    def serialize_result(result):
        if not result:
            return None
        return {k: v for k, v in result.items() if k not in ['winner_obj', 'loser_obj']}
    
    east_results = torneo.play_in_results.get('east', {})
    west_results = torneo.play_in_results.get('west', {})
    
    # Get Play-In teams and results
    playin_data = {
        "state": torneo.playoff_state,
        "game_index": torneo.play_in_game_index,  # 0-5: which game is next
        "east": {
            "direct_qualifiers": [t.nome for t in torneo.direct_qualifiers.get('east', [])],
            "play_in_teams": [t.nome for t in torneo.play_in_teams.get('east', [])],
            "results": {
                'game1': serialize_result(east_results.get('game1')),
                'game2': serialize_result(east_results.get('game2')),
                'game3': serialize_result(east_results.get('game3')),
                'seventh_seed': east_results.get('seventh_seed'),
                'eighth_seed': east_results.get('eighth_seed'),
                'eliminated': east_results.get('eliminated', [])
            },
            "games": torneo.playoff_bracket_data.get('east', {}).get('play_in', []) if torneo.playoff_bracket_data else []
        },
        "west": {
            "direct_qualifiers": [t.nome for t in torneo.direct_qualifiers.get('west', [])],
            "play_in_teams": [t.nome for t in torneo.play_in_teams.get('west', [])],
            "results": {
                'game1': serialize_result(west_results.get('game1')),
                'game2': serialize_result(west_results.get('game2')),
                'game3': serialize_result(west_results.get('game3')),
                'seventh_seed': west_results.get('seventh_seed'),
                'eighth_seed': west_results.get('eighth_seed'),
                'eliminated': west_results.get('eliminated', [])
            },
            "games": torneo.playoff_bracket_data.get('west', {}).get('play_in', []) if torneo.playoff_bracket_data else []
        },
        "playoff_teams": {
            "east": [t.nome for t in torneo.playoff_teams.get('east', [])],
            "west": [t.nome for t in torneo.playoff_teams.get('west', [])]
        }
    }
    
    return jsonify(playin_data)

@app.route('/api/simula_playin_game', methods=['POST'])
def simula_playin_game():
    """Simulate a single Play-In game and return the result."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    if SIMULATION_TOURNAMENT.playoff_state != "PLAY_IN":
        return jsonify({"error": "Not in Play-In state", "state": SIMULATION_TOURNAMENT.playoff_state}), 400
    
    data = request.get_json(silent=True) or {}
    watch_series_id = data.get("watch_series_id", None)

    # Simulate one game
    result = SIMULATION_TOURNAMENT._simula_play_in(watch_series_id)
    
    payload = {
        "success": True,
        "result": result,
        "game_index": SIMULATION_TOURNAMENT.play_in_game_index,
        "state": SIMULATION_TOURNAMENT.playoff_state,
        "complete": SIMULATION_TOURNAMENT.playoff_state == "QF"
    }
    
    if result and "watch_game" in result:
        payload["watch_game"] = result["watch_game"]
        
    return jsonify(payload)

# --- ALL-STAR WEEKEND API ---

def _all_star_break_passed(t):
    """True once this season's All-Star Game day is behind: the weekend is complete, the regular season is
    over, or the current day is past the game day (old saves may store the complete flag as False)."""
    if getattr(t, 'all_star_weekend_complete', False):
        return True
    if LEAGUE_STATE not in ("PRE_SEASON", "ALL_STAR_BREAK"):
        return True
    calendar = getattr(t, 'calendario', None) or []
    game_days = [i for i, d in enumerate(calendar) if "ALL_STAR_GAME" in (getattr(d, 'events', None) or [])]
    if not game_days:
        game_days = [i for i, d in enumerate(calendar) if getattr(d, 'phase', None) == 'ALL_STAR_BREAK']
    return bool(game_days) and getattr(t, '_current_gameday', 0) > game_days[-1]

@app.route('/api/allstar', methods=['GET'])
def get_allstar_data():
    """All-Star page (core/all_star_view.py): the current season's weekend, or a past one with ?season=N."""
    from core.all_star_view import all_star_view, legacy_weekend, season_label
    from core.history_view import parse_season, season_years, year_for

    t = SIMULATION_TOURNAMENT
    if not t:
        return jsonify({"error": "Simulation not initialized"}), 500
    current = getattr(t, 'season_number', 1) or 1
    raw = request.args.get('season')
    try:
        season = int(raw) if raw not in (None, '') else current
    except ValueError:
        return jsonify({"error": f"Invalid season: {raw}"}), 400

    history = _read_historical_json("league_history.json", [])
    history = [h for h in history if isinstance(h, dict) and h.get('stagione')] if isinstance(history, list) else []
    by_season = {h['stagione']: h for h in history}
    years = season_years(history)
    starting_year = getattr(t, 'starting_year', None)

    def label(n):
        return season_label(year_for(n, years, starting_year))

    def stored_weekend(entry):
        premi = entry.get('premi') or {}
        return premi.get('all_star_weekend') or legacy_weekend(premi, entry['stagione'])

    live = getattr(t, 'all_star_weekend', None)
    if season == current and live and live.get('season', current) == current:
        weekend, status = live, 'played'
    elif season in by_season:
        weekend = stored_weekend(by_season[season])
        status = 'played' if weekend else 'not_recorded'
    elif season == current:
        # Old saves may have passed the break without a stored weekend (and with the complete flag lost).
        weekend, status = None, 'not_recorded' if _all_star_break_passed(t) else 'upcoming'
    else:
        return jsonify({"error": f"No season {season}"}), 404

    # Earlier All-Star MVPs with their team: from the stored weekend, else from the careers file (old careers
    # store "Season 5"); an MVP whose team is unknown still counts, with team None.
    careers = _read_historical_json("player_careers.json", {})
    career_teams = {}
    for records in (careers.values() if isinstance(careers, dict) else []):
        for r in records if isinstance(records, list) else []:
            if isinstance(r, dict) and r.get('nome') and r.get('stagione'):
                career_teams[(r['nome'], parse_season(r['stagione']))] = r.get('squadra')
    past_mvps = []
    for n, entry in sorted(by_season.items()):
        if n >= season:
            continue
        premi = entry.get('premi') or {}
        mvp = ((premi.get('all_star_weekend') or {}).get('game') or {}).get('mvp') or {}
        name = mvp.get('name') or premi.get('all_star_mvp')
        team = mvp.get('team') or career_teams.get((name, n))
        if name and name != 'N/A':
            past_mvps.append({'season': n, 'name': name, 'team': team})

    break_info = None
    if status == 'upcoming':
        for i, d in enumerate(getattr(t, 'calendario', None) or []):
            if getattr(d, 'phase', None) == 'ALL_STAR_BREAK':
                break_info = {'day': i, 'date': getattr(d, 'date', None)}
                break

    user = None if getattr(t, 'is_spectator', False) else getattr(t, 'squadra_giocatore', None)
    seasons = [{'season': n, 'label': label(n)} for n in sorted(set(by_season) | {current})]
    return jsonify(all_star_view(weekend=weekend, season=season, label=label(season), status=status,
                                 user_team=user.nome if user else None, seasons=seasons,
                                 past_mvps=past_mvps, break_info=break_info))

@app.route('/api/simulate_entire_season', methods=['POST'])
def api_simulate_entire_season():
    global LEAGUE_STATE, SIMULATION_TOURNAMENT, ACTIVE_DRAFT_INSTANCE, ACTIVE_FREE_AGENCY_INSTANCE, OFFSEASON_FA_POOL, OFFSEASON_PREVIOUS_TEAMS, NEGOTIATION_ATTEMPTS
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    try:
        # Reset intermediate states
        ACTIVE_DRAFT_INSTANCE = None
        ACTIVE_FREE_AGENCY_INSTANCE = None
        OFFSEASON_FA_POOL = None
        OFFSEASON_PREVIOUS_TEAMS = None
        NEGOTIATION_ATTEMPTS.clear()
        
        # Read num_seasons parameter
        data = request.get_json(silent=True) or {}
        num_seasons = int(data.get("num_seasons", 1))
        num_seasons = max(1, min(num_seasons, 50))

        print(f"--- SERVER (AUTO-SIM): Simulating {num_seasons} seasons... ---", flush=True)

        # Execute the native simulation cycle multiple times
        for i in range(num_seasons):
            print(f"--- SERVER (AUTO-SIM): Simulating season cycle {i+1}/{num_seasons} (Year {SIMULATION_TOURNAMENT.season_number}) ---", flush=True)
            user_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
            if user_team:
                gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
                if not gm_prof:
                    gm_prof = init_user_gm_profile(user_team.nome)
                    SIMULATION_TOURNAMENT.user_gm_profile = gm_prof

            prev_vittorie = user_team.vittorie if user_team else 0
            prev_sconfitte = user_team.sconfitte if user_team else 0

            simulation_logic.run_full_season_cycle(SIMULATION_TOURNAMENT)

            if user_team:
                gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
                if gm_prof:
                    gm_prof.career_wins += prev_vittorie
                    gm_prof.career_losses += prev_sconfitte
                    if getattr(SIMULATION_TOURNAMENT, 'campione', None) and SIMULATION_TOURNAMENT.campione.nome == user_team.nome:
                        gm_prof.titles_won += 1
                        for th in gm_prof.teams_managed_history:
                            if th.get("team") == user_team.nome:
                                th["titles"] = th.get("titles", 0) + 1
                    
                    check_gm_achievements(gm_prof, SIMULATION_TOURNAMENT)
                    
                    # Generate and archive the report
                    season_rep = generate_annual_season_report(user_team, SIMULATION_TOURNAMENT, gm_prof, is_live=False)
                    if not hasattr(gm_prof, 'season_reports') or gm_prof.season_reports is None:
                        gm_prof.season_reports = []
                    if not any(r.get("season_number") == season_rep.get("season_number") for r in gm_prof.season_reports):
                        gm_prof.season_reports.append(season_rep)
        
        # Reset the league state for the new season
        LEAGUE_STATE = "PRE_SEASON"
        
        return jsonify(get_full_league_data_payload())
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error during the year simulation: {str(e)}"}), 500

# --- FLUSSO OFFSEASON - ORCHESTRATO DAL SERVER ---


@app.route('/api/offseason/hub_step', methods=['POST'])
def set_offseason_hub_step():
    """Moves the End of Season Hub marker inside the phases the current state allows."""
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    try:
        step = int((request.get_json(silent=True) or {}).get("step"))
    except (TypeError, ValueError):
        return jsonify({"error": "step must be a number"}), 400
    clamped = clamp_hub_step(LEAGUE_STATE, step)
    if clamped is None:
        return jsonify({"error": "The End of Season Hub is closed"}), 400
    if not isinstance(getattr(SIMULATION_TOURNAMENT, 'offseason_log_data', None), dict):
        SIMULATION_TOURNAMENT.offseason_log_data = {}
    SIMULATION_TOURNAMENT.offseason_log_data["hub_step"] = clamped
    return jsonify(get_lean_league_data_payload())

@app.route('/api/start_offseason', methods=['POST'])
def start_offseason():
    """
    Step 1: Transition to the contract options decision phase.
    """
    global LEAGUE_STATE, SIMULATION_TOURNAMENT
    if LEAGUE_STATE == "PLAYOFFS_END":
        print("--- SERVER: Transitioning to contract options decision phase ---", flush=True)
        LEAGUE_STATE = "OFFSEASON_OPTIONS_DECISION"
        if SIMULATION_TOURNAMENT.squadra_giocatore:
            if not isinstance(getattr(SIMULATION_TOURNAMENT, 'offseason_log_data', None), dict):
                SIMULATION_TOURNAMENT.offseason_log_data = {}
            SIMULATION_TOURNAMENT.offseason_log_data['roster_before'] = roster_snapshot(SIMULATION_TOURNAMENT.squadra_giocatore)
        SIMULATION_TOURNAMENT.offseason_log_data['league_before'] = league_snapshot(SIMULATION_TOURNAMENT.squadre)
        
        # Archive the Annual Report of the season that just ended
        if SIMULATION_TOURNAMENT.squadra_giocatore:
            user_team = SIMULATION_TOURNAMENT.squadra_giocatore
            gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
            if not gm_prof:
                gm_prof = init_user_gm_profile(user_team.nome)
                SIMULATION_TOURNAMENT.user_gm_profile = gm_prof

            curr_season_num = SIMULATION_TOURNAMENT.season_number
            already_reported = any(r.get("season_number") == curr_season_num for r in getattr(gm_prof, 'season_reports', []))
            if not already_reported:
                season_rep = generate_annual_season_report(user_team, SIMULATION_TOURNAMENT, gm_prof, is_live=False)
                if not hasattr(gm_prof, 'season_reports') or gm_prof.season_reports is None:
                    gm_prof.season_reports = []
                gm_prof.season_reports.append(season_rep)

        # Auto-generate trade block offers
        if SIMULATION_TOURNAMENT.squadra_giocatore:
            from trades.trade_block_manager import TradeBlockManager
            SIMULATION_TOURNAMENT.pending_trade_block_offers = TradeBlockManager.generate_offers(
                SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadra_giocatore
            )
            print(f"--- SERVER: Generated {len(SIMULATION_TOURNAMENT.pending_trade_block_offers)} trade block offers for offseason ---", flush=True)
            
    return jsonify(get_lean_league_data_payload())

@app.route('/api/offseason/options', methods=['GET'])
def get_offseason_options():
    """Contract options (End of Season Hub phase 2): the user's team and player options with season lines and a take,
    the money behind next season's payroll, and other teams' player options."""
    from core.end_season_views import option_take, options_money
    from core.league_finances import season_lines
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400

    def market(p):
        try:
            return p._calcola_valore_di_mercato()
        except Exception:
            return p.valutazione * 0.5

    def has_option(p):
        return p.contract and p.contract.anni_rimanenti == 1 and (p.contract.player_option or p.contract.team_option)

    lines = {l["name"]: l for l in _season_lines(user_team)}
    options_data = []
    for p in user_team.roster:
        if not has_option(p):
            continue
        market_val = round(market(p), 1)
        line = lines.get(p.nome) or {}
        player_decision = decision_reason = None
        if p.contract.player_option:
            player_decision, decision_reason = p.valuta_player_option(squadra=user_team, torneo=SIMULATION_TOURNAMENT)
        options_data.append({
            "nome": p.nome, "ruolo": p.ruolo, "ovr": p.ovr, "eta": p.eta, "salario": p.contract.salario_annuale,
            "player_option": p.contract.player_option, "team_option": p.contract.team_option,
            "market_value": market_val, "player_decision": player_decision, "decision_reason": decision_reason,
            "season": {k: line.get(k) for k in ("ppg", "rpg", "apg", "mpg")},
            "take": option_take(p.contract.salario_annuale, market_val, line.get("mpg") or 0)
            if p.contract.team_option else None,
        })

    guaranteed = sum(p.contract.salario_annuale for p in user_team.roster if p.contract and p.contract.anni_rimanenti >= 2)
    around = []
    for squadra in SIMULATION_TOURNAMENT.squadre:
        if squadra is user_team:
            continue
        for p in squadra.roster:
            if has_option(p) and p.contract.player_option:
                decision, _reason = p.valuta_player_option(squadra=squadra, torneo=SIMULATION_TOURNAMENT)
                around.append({"name": p.nome, "team": squadra.nome, "ovr": p.ovr, "salary": p.contract.salario_annuale,
                               "decision": "out" if decision == "DECLINE" else "in"})
    around.sort(key=lambda o: (o["decision"] != "out", -o["salary"]))
    return jsonify({
        "success": True,
        "team_name": user_team.nome,
        "options": options_data,
        "money": options_money(guaranteed, season_lines(SIMULATION_TOURNAMENT, CONFIG.ECONOMY)),
        "around_league": around[:CONFIG.END_SEASON.OPTIONS_AROUND_LEAGUE],
        "around_league_total": len(around),
    })

@app.route('/api/offseason/run_options_decision', methods=['POST'])
def run_options_decision():
    global LEAGUE_STATE, SIMULATION_TOURNAMENT, OFFSEASON_FA_POOL, OFFSEASON_PREVIOUS_TEAMS
    if LEAGUE_STATE == "OFFSEASON_OPTIONS_DECISION":
        print("--- SERVER: Resolving contract options & running offseason progression ---", flush=True)
        data = request.get_json() or {}
        user_decisions = data.get("decisions", {})
        
        nuovi_fa, squadre_precedenti = SIMULATION_TOURNAMENT.start_offseason_progression(user_decisions=user_decisions)
        
        SIMULATION_TOURNAMENT.eleggi_classe_hof()
        print("--- SERVER: Hall of Fame election completed ---", flush=True)
        
        OFFSEASON_FA_POOL = nuovi_fa
        OFFSEASON_PREVIOUS_TEAMS = squadre_precedenti
        remember_market(SIMULATION_TOURNAMENT, nuovi_fa, squadre_precedenti)
        
        SIMULATION_TOURNAMENT._gestisci_fase_licenziamenti()
        LEAGUE_STATE = "OFFSEASON_COACH_HIRING_START"
        
    return jsonify(get_lean_league_data_payload())

@app.route('/api/run_coach_hiring', methods=['POST'])
def run_coach_hiring():
    """Step 2 / 3: Hire new coaches and run the Draft Lottery."""
    global LEAGUE_STATE, SIMULATION_TOURNAMENT
    if LEAGUE_STATE == "OFFSEASON_COACH_HIRING_START":
        print("--- SERVER: Step 2: Hiring Coaches ---", flush=True)
        SIMULATION_TOURNAMENT._gestisci_fase_assunzioni()
        
        print("--- SERVER: Step 2.5: Running Draft Lottery ---", flush=True)
        SIMULATION_TOURNAMENT.esegui_draft_lottery()

        # Check lottery achievement
        if SIMULATION_TOURNAMENT.squadra_giocatore:
            user_team = SIMULATION_TOURNAMENT.squadra_giocatore
            gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
            if not gm_prof:
                gm_prof = init_user_gm_profile(user_team.nome)
            lottery_order = getattr(SIMULATION_TOURNAMENT, 'draft_lottery_order', getattr(SIMULATION_TOURNAMENT, 'ordine_draft', []))
            won_lottery = bool(lottery_order and lottery_order[0] == user_team.nome)
            if won_lottery:
                check_gm_achievements(gm_prof, SIMULATION_TOURNAMENT, {"won_lottery": True})
        
        LEAGUE_STATE = "OFFSEASON_TRADES_START"
        
        # Auto-generate trade block offers for offseason trade window
        if SIMULATION_TOURNAMENT.squadra_giocatore:
            from trades.trade_block_manager import TradeBlockManager
            SIMULATION_TOURNAMENT.pending_trade_block_offers = TradeBlockManager.generate_offers(
                SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadra_giocatore
            )
            print(f"--- SERVER: Generated {len(SIMULATION_TOURNAMENT.pending_trade_block_offers)} trade block offers for pre-draft trade period ---", flush=True)
            
    return jsonify(get_lean_league_data_payload())

@app.route('/api/lottery/details', methods=['GET'])
def api_get_lottery_details():
    """Returns the complete object with details, odds, top prospects and picks 1-30 of the lottery."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not active"}), 400
        
    lottery_data = SIMULATION_TOURNAMENT.offseason_log_data.get('lottery_details', None)
    if not lottery_data:
        # Not drawn yet: the lottery teams, their pick's owner and odds, for the page before the draw
        return jsonify({"available": False, "message": "Lottery not yet drawn for this season",
                        "preview": lottery_preview(SIMULATION_TOURNAMENT)})

    # Owners are read now, so picks traded after the draw show their new team
    return jsonify({
        "available": True,
        "data": complete_details(lottery_data, SIMULATION_TOURNAMENT)
    })

IS_SIMULATING_TRADES = False

@app.route('/api/run_trades', methods=['POST'])
def run_trades():
    """
    Step 3: Runs the PRE-DRAFT trades with protection against multiple clicks.
    """
    global LEAGUE_STATE, SIMULATION_TOURNAMENT, IS_SIMULATING_TRADES
    
    if IS_SIMULATING_TRADES:
        return jsonify(get_lean_league_data_payload())
        
    if LEAGUE_STATE == "OFFSEASON_TRADES_START" and SIMULATION_TOURNAMENT:
        IS_SIMULATING_TRADES = True
        try:
            print("--- SERVER: Step 3: Running Pre-Draft Trades ---", flush=True)
            SIMULATION_TOURNAMENT.trade_period_predraft()
            print("--- SERVER: Pre-Draft trade phase completed. ---", flush=True)
            LEAGUE_STATE = "OFFSEASON_DRAFT_START"
        finally:
            IS_SIMULATING_TRADES = False
            
    return jsonify(get_lean_league_data_payload())

@app.route('/api/run_draft', methods=['POST'])
def run_draft():
    """Step 5: Run the Draft."""
    global LEAGUE_STATE, SIMULATION_TOURNAMENT, ACTIVE_DRAFT_INSTANCE
    if ACTIVE_DRAFT_INSTANCE:
        return jsonify(get_lean_league_data_payload())
        
    if LEAGUE_STATE in ["OFFSEASON_DRAFT_START", "DRAFT_USER_PICK"]:
        print("--- SERVER: Step 5: Initializing Draft Rework ---", flush=True)
        draft_instance = simulation_logic.Draft(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore)
        ACTIVE_DRAFT_INSTANCE = draft_instance
        LEAGUE_STATE = "DRAFT_USER_PICK"
        SIMULATION_TOURNAMENT.offseason_log_data['draft_in_progress'] = draft_instance.get_draft_state()
        print("--- SERVER: Finished run_draft setup ---", flush=True)
    return jsonify(get_lean_league_data_payload())

# --- NEW ENDPOINTS FOR THE STEP-BY-STEP DRAFT REWORK ---

@app.route('/api/draft/state', methods=['GET'])
def api_draft_state():
    global ACTIVE_DRAFT_INSTANCE, LEAGUE_STATE, SIMULATION_TOURNAMENT
    
    # Auto-restore if the server restarted during the draft
    if not ACTIVE_DRAFT_INSTANCE and LEAGUE_STATE == "DRAFT_USER_PICK":
        print("--- SERVER: Auto-resuming Draft Instance after server restart ---", flush=True)
        ACTIVE_DRAFT_INSTANCE = simulation_logic.Draft(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore)
        
    if not ACTIVE_DRAFT_INSTANCE:
        user_team = SIMULATION_TOURNAMENT.squadra_giocatore.nome if SIMULATION_TOURNAMENT and SIMULATION_TOURNAMENT.squadra_giocatore else None
        finished = None
        if LEAGUE_STATE not in ("OFFSEASON_DRAFT_START", "DRAFT_USER_PICK"):
            finished = completed_draft_payload(getattr(SIMULATION_TOURNAMENT, 'offseason_log_data', None), user_team)
        if finished:
            finished["league_state"] = LEAGUE_STATE
            return jsonify(finished)
        return jsonify({"status": "NOT_STARTED", "league_state": LEAGUE_STATE})
    
    state = ACTIVE_DRAFT_INSTANCE.get_draft_state()
    state["league_state"] = LEAGUE_STATE
    return jsonify(state)

@app.route('/api/draft/step', methods=['POST'])
def api_draft_step():
    global ACTIVE_DRAFT_INSTANCE, LEAGUE_STATE
    if not ACTIVE_DRAFT_INSTANCE:
        return jsonify({"error": "Draft not started"}), 400
        
    state = ACTIVE_DRAFT_INSTANCE.get_draft_state()
    # If it is the user's turn, do not simulate the automatic step
    if state.get("is_user_turn"):
        return jsonify(state)
        
    new_state = ACTIVE_DRAFT_INSTANCE.simula_singolo_pick()
    
    # If the draft ends
    if new_state.get("status") == "COMPLETED":
        concludi_draft_logica()
        
    return jsonify(new_state)

@app.route('/api/draft/sim_to_user', methods=['POST'])
def api_draft_sim_to_user():
    global ACTIVE_DRAFT_INSTANCE
    if not ACTIVE_DRAFT_INSTANCE:
        return jsonify({"error": "Draft not started"}), 400
        
    state = ACTIVE_DRAFT_INSTANCE.simula_fino_utente()
    if state.get("status") == "COMPLETED":
        concludi_draft_logica()
        
    return jsonify(state)

def concludi_draft_logica():
    global LEAGUE_STATE, SIMULATION_TOURNAMENT, ACTIVE_DRAFT_INSTANCE, ACTIVE_FREE_AGENCY_INSTANCE, OFFSEASON_FA_POOL, OFFSEASON_PREVIOUS_TEAMS
    risultato = ACTIVE_DRAFT_INSTANCE.risultati_draft
    SIMULATION_TOURNAMENT.offseason_log_data['draft'] = risultato
    if hasattr(SIMULATION_TOURNAMENT, 'podcast_logger'):
        for pick in risultato:
            SIMULATION_TOURNAMENT.podcast_logger.log_draft_pick(pick)
            
    LEAGUE_STATE = "OFFSEASON_UFA_START"
    generate_draft_news(risultato)
    
    # Filter out any player who is currently on an active team roster or was drafted to prevent duplicate free agency entries
    rostered_names = {p.nome for s in SIMULATION_TOURNAMENT.squadre for p in s.roster}
    clean_fa_pool = [p for p in (OFFSEASON_FA_POOL or []) if p.nome not in rostered_names]
    OFFSEASON_FA_POOL = clean_fa_pool

    # Initialize Free Agency
    ACTIVE_FREE_AGENCY_INSTANCE = simulation_logic.FreeAgency(
        SIMULATION_TOURNAMENT,
        SIMULATION_TOURNAMENT.squadre,
        OFFSEASON_FA_POOL,
        OFFSEASON_PREVIOUS_TEAMS,
        SIMULATION_TOURNAMENT.squadra_giocatore
    )
    ACTIVE_FREE_AGENCY_INSTANCE._build_caches()
    ACTIVE_DRAFT_INSTANCE = None
    auto_save_active_game()  # the draft is played pick by pick in memory: its end is the save point

@app.route('/api/draft/cpu_offers', methods=['GET'])
def api_draft_cpu_offers():
    global ACTIVE_DRAFT_INSTANCE, SIMULATION_TOURNAMENT
    if not ACTIVE_DRAFT_INSTANCE:
        return jsonify([])
        
    state = ACTIVE_DRAFT_INSTANCE.get_draft_state()
    on_the_clock = state.get("on_the_clock")
    
    if not on_the_clock or not state.get("is_user_turn"):
        return jsonify([])
        
    # Compute the pick_key and pick_pos
    round_num = on_the_clock["round"]
    pick_num = on_the_clock["pick"]
    orig_team = on_the_clock["original_owner"]
    pick_key = f"R{round_num}-{orig_team}"
    pick_pos = on_the_clock["pick_index"] + 1
    
    # Import and instance of TradeFinder
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore)
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    
    cpu_offers = finder.generate_live_draft_offers(user_team, pick_pos, pick_key)
    
    serializable_offers = []
    for offer in cpu_offers:
        gives_players_info = []
        for asset in offer["cpu_gives_assets"]:
            if not isinstance(asset, str):  # It is a Giocatore
                gives_players_info.append({
                    "nome": asset.nome,
                    "ruolo": asset.ruolo,
                    "ovr": asset.ovr,
                    "pot": asset.potenziale,
                    "eta": asset.eta,
                    "salario": asset.contract.salario_annuale if asset.contract else 1.0,
                    "anni_contratto": asset.contract.anni_rimanenti if asset.contract else 1
                })
        
        serializable_offers.append({
            "id": offer["id"],
            "partner": offer["partner"],
            "type": offer["type"],
            "cpu_gives_players": offer["cpu_gives_players"],
            "cpu_gives_players_ovr": offer["cpu_gives_players_ovr"],
            "cpu_gives_picks": offer["cpu_gives_picks"],
            "user_gives_picks": offer["user_gives_picks"],
            "description": offer["description"],
            "why": offer.get("why", ""),
            "gives_players_info": gives_players_info
        })
        
    app.config["ACTIVE_DRAFT_OFFERS"] = cpu_offers
    return jsonify(serializable_offers)

@app.route('/api/draft/accept_cpu_offer', methods=['POST'])
def api_draft_accept_cpu_offer():
    global ACTIVE_DRAFT_INSTANCE, SIMULATION_TOURNAMENT
    if not ACTIVE_DRAFT_INSTANCE:
        return jsonify({"error": "Draft not active"}), 400
        
    data = request.get_json()
    offer_id = data.get("offer_id")
    
    active_offers = app.config.get("ACTIVE_DRAFT_OFFERS", [])
    selected_offer = next((o for o in active_offers if o["id"] == offer_id), None)
    
    if not selected_offer:
        return jsonify({"error": "Offer not found or expired"}), 400
        
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore)
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    partner_team = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == selected_offer["partner"]), None)
    
    if not partner_team:
        return jsonify({"error": "Partner team not found"}), 400
        
    success = finder.execute_trade(
        user_team, 
        partner_team, 
        selected_offer["user_gives_assets"], 
        selected_offer["cpu_gives_assets"],
        reason=f"Draft Trade ({selected_offer['type']})",
        motive=selected_offer.get("motive")
    )
    
    if not success:
        return jsonify({"error": "The trade failed the financial rules or the roster limit (15 max)."}), 400
        
    app.config["ACTIVE_DRAFT_OFFERS"] = []
    
    # Update log_data for the frontend
    new_state = ACTIVE_DRAFT_INSTANCE.get_draft_state()
    SIMULATION_TOURNAMENT.offseason_log_data['draft_in_progress'] = new_state
    return jsonify(new_state)

@app.route('/api/draft/propose_custom_trade', methods=['POST'])
def api_draft_propose_custom_trade():
    global ACTIVE_DRAFT_INSTANCE, SIMULATION_TOURNAMENT
    if not ACTIVE_DRAFT_INSTANCE:
        return jsonify({"error": "Draft not active"}), 400
        
    data = request.get_json()
    partner_name = data.get("partner")
    user_gives_players_names = data.get("user_gives_players", [])
    user_gives_picks_keys = data.get("user_gives_picks", [])
    cpu_gives_players_names = data.get("cpu_gives_players", [])
    cpu_gives_picks_keys = data.get("cpu_gives_picks", [])
    
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    partner_team = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == partner_name), None)
    
    if not partner_team:
        return jsonify({"error": "Partner team not found"}), 400
        
    user_gives_assets = []
    for name in user_gives_players_names:
        p = next((x for x in user_team.roster if x.nome == name), None)
        if p: user_gives_assets.append(p)
    for pk in user_gives_picks_keys:
        user_gives_assets.append(pk)
        
    cpu_gives_assets = []
    for name in cpu_gives_players_names:
        p = next((x for x in partner_team.roster if x.nome == name), None)
        if p: cpu_gives_assets.append(p)
    for pk in cpu_gives_picks_keys:
        cpu_gives_assets.append(pk)
        
    user_pick_protections = data.get("user_pick_protections", {})
    cpu_pick_protections = data.get("cpu_pick_protections", {})
    all_pick_protections = {}
    for prot_dict in [user_pick_protections, cpu_pick_protections]:
        if isinstance(prot_dict, dict):
            for k, v in prot_dict.items():
                all_pick_protections[k] = v
                if ":" in k:
                    p_short = k.split(":", 1)[1]
                    all_pick_protections[p_short] = v
                else:
                    for y in range(1, 6):
                        all_pick_protections[f"{y}:{k}"] = v
    for pk in user_gives_picks_keys + cpu_gives_picks_keys:
        if pk not in all_pick_protections:
            all_pick_protections[pk] = "Unprotected"
            if ":" in pk:
                all_pick_protections[pk.split(":", 1)[1]] = "Unprotected"
            else:
                for y in range(1, 6):
                    all_pick_protections[f"{y}:{pk}"] = "Unprotected"
        
    from trades.trade_validator import TradeValidator
    is_valid, validation_msg = TradeValidator.validate_trade(
        user_team, partner_team, user_gives_assets, cpu_gives_assets, torneo=SIMULATION_TOURNAMENT
    )
    if not is_valid:
        return jsonify({"error": f"Trade rules not met: {validation_msg}"}), 400
        
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore, manual=True)
    finder.begin_window("draft")   # the CPU's draft wishes count on draft night
    ai_accepted, ai_reason = finder.would_accept_trade_with_reason(
        partner_team, user_gives_assets, cpu_gives_assets, pick_protections=all_pick_protections
    )
    if not ai_accepted:
        return jsonify({"error": f"The partner team rejects the trade: {ai_reason}"}), 400

    success = finder.execute_trade(
        user_team,
        partner_team,
        user_gives_assets,
        cpu_gives_assets,
        reason="Custom Draft-Night Trade",
        pick_protections=all_pick_protections,
        motive=finder.user_motive(finder.pair_deal(user_team, partner_team, user_gives_assets, cpu_gives_assets))
    )
    
    if not success:
        return jsonify({"error": "Error while executing the trade"}), 500
        
    new_state = ACTIVE_DRAFT_INSTANCE.get_draft_state()
    SIMULATION_TOURNAMENT.offseason_log_data['draft_in_progress'] = new_state
    return jsonify(new_state)


@app.route('/api/run_free_agency', methods=['POST'])
def run_free_agency():
    """Step 6: Esegui la Unrestricted Free Agency e concludi l'offseason (Auto-Simulate to completion)."""
    global LEAGUE_STATE, SIMULATION_TOURNAMENT, ACTIVE_FREE_AGENCY_INSTANCE, OFFSEASON_FA_POOL, OFFSEASON_PREVIOUS_TEAMS
    
    if LEAGUE_STATE == "OFFSEASON_UFA_START":
        print("--- SERVER: Step 6: Running UFA (Auto-Sim) ---", flush=True)
        
        if ACTIVE_FREE_AGENCY_INSTANCE is None:
            ACTIVE_FREE_AGENCY_INSTANCE = simulation_logic.FreeAgency(
                SIMULATION_TOURNAMENT,
                SIMULATION_TOURNAMENT.squadre,
                OFFSEASON_FA_POOL,
                OFFSEASON_PREVIOUS_TEAMS,
                SIMULATION_TOURNAMENT.squadra_giocatore
            )
            
        # Run free agency to completion
        fa_logs = ACTIVE_FREE_AGENCY_INSTANCE.esegui_free_agency()
        SIMULATION_TOURNAMENT.offseason_log_data['free_agency'] = fa_logs
        
        if hasattr(SIMULATION_TOURNAMENT, 'podcast_logger'):
            for signing in fa_logs:
                SIMULATION_TOURNAMENT.podcast_logger.log_free_agency_signing(signing)
                
        # Generate news for significant signings
        season = SIMULATION_TOURNAMENT.season_number
        for log_entry in fa_logs[:15]:
            if isinstance(log_entry, dict):
                player_name = log_entry.get("giocatore", "")
                team_name = log_entry.get("nuova_squadra", "")
                contract_info = log_entry.get("contratto", "")
                
                is_star = False
                if contract_info:
                    try:
                        salary_str = contract_info.split("$")[1].split("M")[0]
                        salary = float(salary_str)
                        is_star = salary >= 25.0
                    except:
                        pass
                
                if player_name and team_name:
                    generate_signing_news(player_name, team_name, contract_info=contract_info, is_star=is_star, season=season)

        SIMULATION_TOURNAMENT._pulizia_post_free_agency(ACTIVE_FREE_AGENCY_INSTANCE.unrestricted_free_agents)
        
        _remember_final_market()
        OFFSEASON_FA_POOL = []
        OFFSEASON_PREVIOUS_TEAMS = {}
        ACTIVE_FREE_AGENCY_INSTANCE = None
        
        SIMULATION_TOURNAMENT._gestisci_progressione_coach()
            
        LEAGUE_STATE = "OFFSEASON_CUTDOWN_START"
        print(f"--- SERVER: New state -> {LEAGUE_STATE} ---", flush=True)

    return jsonify(get_lean_league_data_payload())

def _cba_line(value):
    """A CBA line for the UI, or None when the engine uses its 9999 'no limit' placeholder."""
    return None if value is None or value >= CONFIG.ECONOMY.UNLIMITED_LINE else round(value, 1)


@app.route('/api/offseason/free_agency/state', methods=['GET'])
def get_free_agency_state():
    global ACTIVE_FREE_AGENCY_INSTANCE, LEAGUE_STATE, SIMULATION_TOURNAMENT, OFFSEASON_FA_POOL, OFFSEASON_PREVIOUS_TEAMS
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    if ACTIVE_FREE_AGENCY_INSTANCE is None and LEAGUE_STATE == "OFFSEASON_UFA_START":
        ACTIVE_FREE_AGENCY_INSTANCE = simulation_logic.FreeAgency(
            SIMULATION_TOURNAMENT,
            SIMULATION_TOURNAMENT.squadre,
            OFFSEASON_FA_POOL,
            OFFSEASON_PREVIOUS_TEAMS,
            SIMULATION_TOURNAMENT.squadra_giocatore
        )
        ACTIVE_FREE_AGENCY_INSTANCE._build_caches()
        
    if ACTIVE_FREE_AGENCY_INSTANCE is None:
        # The market is over: the page still shows its last state (last night's recap, the Signed list)
        final = (getattr(SIMULATION_TOURNAMENT, 'offseason_log_data', None) or {}).get('fa_final')
        if final:
            return jsonify(final)
        return jsonify({"error": "Free agency is not active"}), 400
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No user team"}), 400
        
    # Compile CBA metrics for user team
    full_mle_val = round(SIMULATION_TOURNAMENT.mle_value, 1)
    taxpayer_mle_val = round(SIMULATION_TOURNAMENT.mle_value * 0.41, 1)
    bae_val = round(CONFIG.ECONOMY.BAE_VALUE, 1)

    mle_type = "NONE"
    mle_available = False
    if not user_team.ha_usato_mle:
        if user_team.payroll < SIMULATION_TOURNAMENT.first_apron:
            mle_type = "FULL_MLE"
            mle_available = True
        elif user_team.payroll < SIMULATION_TOURNAMENT.second_apron:
            mle_type = "TAXPAYER_MLE"
            mle_available = True

    bae_available = (not user_team.ha_usato_bae) and (user_team.payroll < SIMULATION_TOURNAMENT.first_apron)
    all_roles = ['PG', 'SG', 'SF', 'PF', 'C']
    positional_needs = [r for r in all_roles if user_team.ha_bisogno_di_ruolo(r)]
    team_goal = SIMULATION_TOURNAMENT._determina_stato_squadra(user_team)

    # Compile available free agents
    players_data = []
    for player in ACTIVE_FREE_AGENCY_INSTANCE.unrestricted_free_agents:
        prev_squadra = ACTIVE_FREE_AGENCY_INSTANCE.squadre_precedenti.get(player.nome)
        req = ACTIVE_FREE_AGENCY_INSTANCE._calcola_richiesta_salariale(player)
        is_own = (prev_squadra == user_team)
        
        # Get active user offer
        user_off = ACTIVE_FREE_AGENCY_INSTANCE.user_offers.get(player.nome)
        
        # Calculate willingness deterministically for display
        if user_off:
            willingness = ACTIVE_FREE_AGENCY_INSTANCE._calcola_punteggio_accettazione_cached(
                player, user_team, user_off["salary"], option_type=user_off.get("option_type", "None")
            )
        else:
            willingness = ACTIVE_FREE_AGENCY_INSTANCE._calcola_punteggio_accettazione_cached(
                player, user_team, req
            )
        
        # Get competing AI offers
        comp_offs = ACTIVE_FREE_AGENCY_INSTANCE.ai_offers.get(player.nome, [])
        
        players_data.append({
            "nome": player.nome,
            "ruolo": player.ruolo,
            "ovr": player.ovr,
            "potenziale": player.potenziale,
            "eta": player.eta,
            "prev_team": prev_squadra.nome if prev_squadra else "N/A",
            "is_own_fa": is_own,
            "has_bird_rights": is_own,
            "is_rfa": ACTIVE_FREE_AGENCY_INSTANCE.is_rfa(player),
            "expected_salary": req,
            "willingness": round(willingness, 1),
            "active_user_offer": user_off,
            "competing_offers": comp_offs,
            # What the page shows: market value, today's ask, the offers on the table and why the player likes yours
            "ask": req,
            "race": _fa_race_json(ACTIVE_FREE_AGENCY_INSTANCE.classifica_offerte(player)),
            "score": ACTIVE_FREE_AGENCY_INSTANCE.dettaglio_punteggio(
                player, user_team, user_off["salary"] if user_off else req,
                option_type=user_off.get("option_type", "None") if user_off else "None"),
        })
        
    # Sort players by OVR descending
    players_data.sort(key=lambda x: x["ovr"], reverse=True)
    signings = getattr(ACTIVE_FREE_AGENCY_INSTANCE, 'signings', [])
    signed_by_user = {s["player"] for s in signings if s["team"] == user_team.nome}
    
    return jsonify({
        "success": True,
        "current_day": ACTIVE_FREE_AGENCY_INSTANCE.current_day,
        "days_total": CONFIG.OFFSEASON.FREE_AGENCY_DAYS,
        "completed": ACTIVE_FREE_AGENCY_INSTANCE.completed,
        "signings": signings,
        "night_moves": list(getattr(ACTIVE_FREE_AGENCY_INSTANCE, 'night_moves', [])),   # tonight's raises, pull-outs, signings
        "user_team": {
            "nome": user_team.nome,
            "roster": [{"name": p.nome, "role": p.ruolo, "ovr": p.ovr, "new": p.nome in signed_by_user} for p in user_team.roster],
            "payroll": round(user_team.payroll, 1),
            "cap_space": round(user_team.salary_cap_space, 1),
            "salary_cap": _cba_line(SIMULATION_TOURNAMENT.salary_cap),
            "luxury_tax_threshold": _cba_line(SIMULATION_TOURNAMENT.luxury_tax_threshold),
            "first_apron": _cba_line(SIMULATION_TOURNAMENT.first_apron),
            "second_apron": _cba_line(SIMULATION_TOURNAMENT.second_apron),
            "ha_usato_mle": user_team.ha_usato_mle,
            "ha_usato_bae": user_team.ha_usato_bae,
            "mle_type": mle_type,
            "mle_available": mle_available,
            "mle_amount": full_mle_val if mle_type == "FULL_MLE" else (taxpayer_mle_val if mle_type == "TAXPAYER_MLE" else 0.0),
            "bae_amount": bae_val,
            "bae_available": bae_available,
            "min_salary": round(ACTIVE_FREE_AGENCY_INSTANCE._min_salary, 1),
            "roster_count": len(user_team.roster),
            "roster_limit": CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT,
            "roster_min": CONFIG.OFFSEASON.ROSTER_SIZE_MIN,
            "team_goal": team_goal,
            "positional_needs": positional_needs,
            "is_hard_capped": getattr(user_team, 'is_hard_capped', False),
            "hard_cap_limit": round(getattr(user_team, 'hard_cap_limit', 0.0), 1) if getattr(user_team, 'is_hard_capped', False) else None
        },
        "user_offers": ACTIVE_FREE_AGENCY_INSTANCE.user_offers,
        "signings_log": ACTIVE_FREE_AGENCY_INSTANCE.signings_log,
        "pending_rfa_match": ACTIVE_FREE_AGENCY_INSTANCE.pending_rfa_match,
        "players": players_data
    })

@app.route('/api/offseason/free_agency/offer', methods=['POST'])
def make_free_agency_offer():
    global ACTIVE_FREE_AGENCY_INSTANCE
    if ACTIVE_FREE_AGENCY_INSTANCE is None:
        return jsonify({"success": False, "error": "Free agency is not active"}), 400
        
    data = request.get_json() or {}
    player_name = data.get("player_name")
    salary = data.get("salary")
    years = data.get("years")
    option_type = data.get("option_type", "None")
    raise_pct = float(data.get("raise_pct", 0.05))
    
    if not player_name or salary is None or years is None:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    try:
        salary = float(salary)
        years = int(years)
    except:
        return jsonify({"success": False, "error": "Invalid parameters"}), 400
        
    valid, tool_or_err = ACTIVE_FREE_AGENCY_INSTANCE.check_user_offer_validity(player_name, salary, years)
    if not valid:
        return jsonify({"success": False, "error": tool_or_err}), 200
        
    ACTIVE_FREE_AGENCY_INSTANCE.user_offers[player_name] = {
        "team": ACTIVE_FREE_AGENCY_INSTANCE.squadra_giocatore.nome,
        "salary": salary,
        "years": years,
        "tool": tool_or_err,
        "option_type": option_type,
        "raise_pct": raise_pct
    }
    
    return jsonify({"success": True})

def _remember_final_market() -> None:
    """Keeps the closing market's last state in the offseason log before the server drops the market."""
    try:
        response = get_free_agency_state()
        data = response.get_json() if hasattr(response, 'get_json') else None
    except Exception:
        data = None
    if data and data.get("success"):
        SIMULATION_TOURNAMENT.offseason_log_data['fa_final'] = {**data, "completed": True, "players": [],
                                                               "pending_rfa_match": None, "user_offers": {}}


def _fa_race_json(race: dict) -> dict:
    """The offer ranking without the raw offer dicts (they carry engine-only fields such as the signing tool)."""
    return {**race, "offers": [{k: v for k, v in o.items() if k != "offer"} for o in race["offers"]]}


@app.route('/api/offseason/free_agency/preview_offer', methods=['POST'])
def preview_free_agency_offer():
    """What an offer would do (allowed or why not, his score, the race tonight) without making it."""
    if ACTIVE_FREE_AGENCY_INSTANCE is None:
        return jsonify({"success": False, "error": "Free agency is not active"}), 400
    data = request.get_json() or {}
    try:
        salary = float(data.get("salary"))
        years = int(data.get("years"))
        raise_pct = float(data.get("raise_pct", 0.05))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid parameters"}), 400
    preview = ACTIVE_FREE_AGENCY_INSTANCE.anteprima_offerta(data.get("player_name", ""), salary, years,
                                                            data.get("option_type", "None"), raise_pct)
    if preview["race"] is not None:
        preview["race"] = _fa_race_json(preview["race"])
    return jsonify({"success": True, **preview})


@app.route('/api/offseason/free_agency/cancel_offer', methods=['POST'])
def cancel_free_agency_offer():
    global ACTIVE_FREE_AGENCY_INSTANCE
    if ACTIVE_FREE_AGENCY_INSTANCE is None:
        return jsonify({"success": False, "error": "Free agency is not active"}), 400
        
    data = request.get_json() or {}
    player_name = data.get("player_name")
    
    if not player_name:
        return jsonify({"success": False, "error": "Missing player_name parameter"}), 400
        
    ACTIVE_FREE_AGENCY_INSTANCE.user_offers.pop(player_name, None)
    return jsonify({"success": True})

@app.route('/api/offseason/free_agency/simulate_day', methods=['POST'])
def simulate_free_agency_day():
    global ACTIVE_FREE_AGENCY_INSTANCE, LEAGUE_STATE, SIMULATION_TOURNAMENT, OFFSEASON_FA_POOL, OFFSEASON_PREVIOUS_TEAMS
    if ACTIVE_FREE_AGENCY_INSTANCE is None:
        return jsonify({"success": False, "error": "Free agency is not active"}), 400
        
    res = ACTIVE_FREE_AGENCY_INSTANCE.simulate_day()
    
    # If the simulation day completes the free agency, run post-FA cleanup and transitions
    if ACTIVE_FREE_AGENCY_INSTANCE and ACTIVE_FREE_AGENCY_INSTANCE.completed:
        fa_logs = ACTIVE_FREE_AGENCY_INSTANCE.log_fa
        SIMULATION_TOURNAMENT.offseason_log_data['free_agency'] = fa_logs
        
        if hasattr(SIMULATION_TOURNAMENT, 'podcast_logger'):
            for signing in fa_logs:
                SIMULATION_TOURNAMENT.podcast_logger.log_free_agency_signing(signing)
                
        # Generate news for top signings
        season = SIMULATION_TOURNAMENT.season_number
        for log_entry in fa_logs[:15]:
            if isinstance(log_entry, dict):
                player_name = log_entry.get("giocatore", "")
                team_name = log_entry.get("nuova_squadra", "")
                contract_info = log_entry.get("contratto", "")
                
                is_star = False
                if contract_info:
                    try:
                        salary_str = contract_info.split("$")[1].split("M")[0]
                        salary = float(salary_str)
                        is_star = salary >= 25.0
                    except:
                        pass
                
                if player_name and team_name:
                    generate_signing_news(player_name, team_name, contract_info=contract_info, is_star=is_star, season=season)
                    
        # Reset FA globals
        _remember_final_market()
        OFFSEASON_FA_POOL = []
        OFFSEASON_PREVIOUS_TEAMS = {}
        ACTIVE_FREE_AGENCY_INSTANCE = None
        
        SIMULATION_TOURNAMENT._gestisci_progressione_coach()
            
        LEAGUE_STATE = "OFFSEASON_CUTDOWN_START"
        print(f"--- SERVER: UFA completed. Next state -> {LEAGUE_STATE} ---", flush=True)
        
    return jsonify(res)

@app.route('/api/offseason/free_agency/match_rfa', methods=['POST'])
def match_rfa_offer():
    global ACTIVE_FREE_AGENCY_INSTANCE
    if ACTIVE_FREE_AGENCY_INSTANCE is None:
        return jsonify({"success": False, "error": "Free agency is not active"}), 400
        
    data = request.get_json() or {}
    player_name = data.get("player_name")
    match = data.get("match")
    
    if not player_name or match is None:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    ACTIVE_FREE_AGENCY_INSTANCE.resolve_rfa_match(match)
    
    # After match resolution, continue simulating the day
    res = ACTIVE_FREE_AGENCY_INSTANCE.simulate_day()
    return jsonify(res)

def _season_lines(team):
    """Per-game lines of a roster this season, for the hub pages."""
    lines = []
    for p in team.roster if team else []:
        st = getattr(p, 'season_stats', None)
        gp = getattr(st, 'partite_giocate', 0) if st else 0
        if not gp:
            continue
        lines.append({"name": p.nome, "gp": gp, "ppg": round(st.punti / gp, 1), "rpg": round(st.rimbalzi / gp, 1),
                      "apg": round(st.assist / gp, 1),
                      "mpg": round(getattr(st, 'minuti_giocati', 0) / gp, 1)})
    return lines


def _player_teams():
    """Player name -> current team (live rosters), falling back to the last team in player_careers.json."""
    careers = _read_historical_json("player_careers.json", {})
    teams = {}
    if isinstance(careers, dict):
        for seasons in careers.values():
            if seasons and isinstance(seasons[-1], dict) and seasons[-1].get("nome"):
                teams[seasons[-1]["nome"]] = seasons[-1].get("squadra")
    for squadra in SIMULATION_TOURNAMENT.squadre:
        for p in squadra.roster:
            teams[p.nome] = squadra.nome
    return teams


@app.route('/api/offseason/recap', methods=['GET'])
def offseason_recap():
    """Season recap (End of Season Hub phase 1): your season and the league's, from the live state at the end of the
    playoffs or, once archived, from league_history.json."""
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    from core.end_season_views import season_recap_view
    torneo = SIMULATION_TOURNAMENT
    if LEAGUE_STATE == "PLAYOFFS_END":
        entry = simulation_logic.build_season_entry(torneo)
    else:
        history = _read_historical_json("league_history.json", [])
        entry = next((h for h in history if isinstance(h, dict) and h.get("stagione") == torneo.season_number), None) \
            if isinstance(history, list) else None
    if not entry:
        return jsonify({"error": "No season to recap"}), 404
    user = torneo.squadra_giocatore
    return jsonify(season_recap_view(entry, getattr(torneo, 'playoff_bracket_data', None), user.nome if user else None,
                                     _season_lines(user), _player_teams()))


@app.route('/api/offseason/development', methods=['GET'])
def offseason_development():
    """Development & retirements (End of Season Hub phase 3): your roster before -> after, league movers, retirees."""
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    from core.end_season_views import development_view
    log = SIMULATION_TOURNAMENT.offseason_log_data if isinstance(getattr(SIMULATION_TOURNAMENT, 'offseason_log_data', None), dict) else {}
    user = SIMULATION_TOURNAMENT.squadra_giocatore
    roster = [{"name": p.nome, "age": p.eta, "position": p.ruolo, "ovr": p.ovr} for p in user.roster] if user else []
    careers = _read_historical_json("player_careers.json", {})
    return jsonify(development_view(log.get("development") or [], log.get("retirements") or [],
                                    careers if isinstance(careers, dict) else {}, user.nome if user else None, roster))


@app.route('/api/offseason/trade_desk', methods=['GET'])
def offseason_trade_desk():
    """Pre-draft trades (End of Season Hub phase 5): offer cards, your picks and trade block, the league's wire."""
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    from core.end_season_views import trade_desk_view
    from trades.trade_finder import TradeFinder
    torneo = SIMULATION_TOURNAMENT
    user = torneo.squadra_giocatore
    if not user:
        return jsonify({"error": "No team selected"}), 400
    log = torneo.offseason_log_data if isinstance(getattr(torneo, 'offseason_log_data', None), dict) else {}
    owned = [f"{year}:{key}" for year, key in TradeFinder(torneo, torneo.squadre, user)._collect_team_picks(user)]
    owned.sort(key=lambda a: (int(a.split(":", 1)[0]), a))
    block = [{"name": p.nome, "position": p.ruolo, "ovr": p.ovr} for p in user.roster if getattr(p, 'on_trade_block', False)]
    payroll = round(sum(p.contract.salario_annuale for p in user.roster if p.contract), 1)
    return jsonify(trade_desk_view(getattr(torneo, 'pending_trade_block_offers', []) or [], user.nome,
                                   getattr(torneo, 'anno_corrente', None),
                                   getattr(torneo, 'draft_lottery_order', None) or getattr(torneo, 'ordine_draft', None) or [],
                                   payroll, owned, block, log.get("scambi") or [],
                                   [s.nome for s in torneo.squadre]))


@app.route('/api/offseason/new_season', methods=['GET'])
def offseason_new_season():
    """New season (End of Season Hub phase 9): your offseason report card and the league's preseason power rankings."""
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    from core.end_season_views import new_season_view
    torneo = SIMULATION_TOURNAMENT
    log = torneo.offseason_log_data if isinstance(getattr(torneo, 'offseason_log_data', None), dict) else {}
    user = torneo.squadra_giocatore
    roster_now = [{"name": p.nome, "position": p.ruolo, "ovr": p.ovr, "age": p.eta,
                   "salary": round(p.contract.salario_annuale, 2) if p.contract else 0.0} for p in user.roster] if user else []
    order = getattr(torneo, 'draft_lottery_order', None) or getattr(torneo, 'ordine_draft', None) or []
    logs = {key: log.get(key) or [] for key in ("draft", "fa_signings", "retirements", "user_releases", "options", "scambi")}
    logs["draft_size"] = len(order) or len(torneo.squadre)
    return jsonify(new_season_view(log.get("roster_before"), log.get("league_before"), roster_now,
                                   {s.nome: [p.ovr for p in s.roster] for s in torneo.squadre},
                                   {s.nome: [p.nome for p in s.roster] for s in torneo.squadre},
                                   logs, user.nome if user else None, CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT))


@app.route('/api/offseason/cut_preview', methods=['GET'])
def offseason_cut_preview():
    """Roster cuts (End of Season Hub phase 8): the user's roster in cut order with the engine's picks marked, and the
    players the other teams will release (same choice as the engine)."""
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    from core.end_season_views import cut_sheet_view
    from core.roster_cuts import cut_order, cut_target, is_protected, pick_cuts
    cfg = CONFIG.OFFSEASON
    target = cut_target(cfg)
    user = SIMULATION_TOURNAMENT.squadra_giocatore
    log = SIMULATION_TOURNAMENT.offseason_log_data if isinstance(getattr(SIMULATION_TOURNAMENT, 'offseason_log_data', None), dict) else {}
    before = {p.get("name") for p in ((log.get("roster_before") or {}).get("players") or [])}
    rows, engine_picks = [], []
    if user:
        engine_picks = [p.nome for p in pick_cuts(user.roster, target, cfg)]
        rows = [{"name": p.nome, "position": p.ruolo, "age": p.eta, "ovr": p.ovr, "potential": p.potenziale,
                 "salary": round(p.contract.salario_annuale, 2) if p.contract else 0.0,
                 "protected": is_protected(p, cfg), "new": bool(before) and p.nome not in before}
                for p in cut_order(user.roster, cfg)]
    league = [{"team": s.nome, "name": p.nome, "ovr": p.ovr, "age": p.eta}
              for s in SIMULATION_TOURNAMENT.squadre if s is not user for p in pick_cuts(s.roster, target, cfg)]
    return jsonify(cut_sheet_view(rows, engine_picks, target, league))

@app.route('/api/run_roster_cuts', methods=['POST'])
def run_roster_cuts():
    """NEW Step 7: Runs the final roster cuts."""
    global LEAGUE_STATE, SIMULATION_TOURNAMENT
    
    if LEAGUE_STATE == "OFFSEASON_CUTDOWN_START":
        from core.roster_cuts import cut_target, validate_releases
        user = SIMULATION_TOURNAMENT.squadra_giocatore
        if user:
            releases = (request.get_json(silent=True) or {}).get("releases")
            target = cut_target(CONFIG.OFFSEASON)
            if releases is None:
                if len(user.roster) > target:
                    return jsonify({"error": "Pick who to release"}), 400
                releases = []
            error = validate_releases([p.nome for p in user.roster], list(releases), target)
            if error:
                return jsonify({"error": error}), 400
            SIMULATION_TOURNAMENT.release_players(user, list(releases))
        print("--- SERVER: Step 7: Final Roster Cut-Down Day ---", flush=True)
        SIMULATION_TOURNAMENT._gestisci_fase_tagli_roster()
        # Coach progression already ran when free agency closed (as in main.py): running it again here aged
        # every coach two years and ticked two contract years per offseason.
        LEAGUE_STATE = "OFFSEASON_COMPLETE"
        print(f"--- SERVER: New state -> {LEAGUE_STATE} ---", flush=True)

    return jsonify(get_lean_league_data_payload())
@app.route('/api/nuova_stagione', methods=['POST'])
def nuova_stagione():
    """Starts the next season."""
    global LEAGUE_STATE, SIMULATION_TOURNAMENT, ACTIVE_DRAFT_INSTANCE, OFFSEASON_FA_POOL, OFFSEASON_PREVIOUS_TEAMS
    if LEAGUE_STATE == "OFFSEASON_COMPLETE":
        # Export the completed JSON data for the Podcast for the manual sims
        if hasattr(SIMULATION_TOURNAMENT, 'podcast_logger'):
            SIMULATION_TOURNAMENT.podcast_logger.export_to_json()
        
        # Freeze and archive the post-trade records of the season that just ended
        if hasattr(SIMULATION_TOURNAMENT, 'trade_analytics_history') and SIMULATION_TOURNAMENT.trade_analytics_history:
            curr_s = SIMULATION_TOURNAMENT.season_number
            for tr in SIMULATION_TOURNAMENT.trade_analytics_history:
                if tr.get('season') == curr_s:
                    for t_entry in tr.get('teams', []):
                        sq = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome.lower() == t_entry.get('team_name', '').lower()), None)
                        if sq:
                            w_pre = t_entry.get('wins_pre', 0)
                            l_pre = t_entry.get('losses_pre', 0)
                            wp_pre = t_entry.get('win_pct_pre', 0.5)
                            g_pre = w_pre + l_pre
                            tot_g = sq.vittorie + sq.sconfitte
                            g_post = max(0, tot_g - g_pre)
                            w_post = max(0, sq.vittorie - w_pre)
                            l_post = max(0, sq.sconfitte - l_pre)
                            wp_post = round(w_post / g_post, 3) if g_post > 0 else wp_pre
                            d_wp = round((wp_post - wp_pre) * 100, 1)

                            t_entry['wins_final'] = sq.vittorie
                            t_entry['losses_final'] = sq.sconfitte
                            t_entry['games_post'] = g_post
                            t_entry['wins_post'] = w_post
                            t_entry['losses_post'] = l_post
                            t_entry['win_pct_post'] = wp_post
                            t_entry['delta_win_pct'] = d_wp
                            t_entry['is_finalized'] = True

        SIMULATION_TOURNAMENT._age_draft_picks()
        SIMULATION_TOURNAMENT._fade_rivalries()
        SIMULATION_TOURNAMENT.season_number += 1
        SIMULATION_TOURNAMENT._gestisci_crescita_economica()
        checkpoint_new_season(SIMULATION_TOURNAMENT)  # GMs age; team plans reviewed (champion still known)
        SIMULATION_TOURNAMENT.regular_season_mvp = None; SIMULATION_TOURNAMENT.finals_mvp = None; SIMULATION_TOURNAMENT.coach_of_the_year = None; SIMULATION_TOURNAMENT.gm_of_the_year = None; SIMULATION_TOURNAMENT.campione = None
        SIMULATION_TOURNAMENT.playoff_bracket_data = None; SIMULATION_TOURNAMENT.offseason_log_data = {}; SIMULATION_TOURNAMENT.playoff_state = "NOT_STARTED"; SIMULATION_TOURNAMENT.nuovi_free_agents = []
        
        # Reset All-Star Weekend data
        SIMULATION_TOURNAMENT.reset_all_star_weekend()
        
        # Reset Play-In Tournament data
        SIMULATION_TOURNAMENT.play_in_teams = {'east': [], 'west': []}
        SIMULATION_TOURNAMENT.direct_qualifiers = {'east': [], 'west': []}
        SIMULATION_TOURNAMENT.play_in_results = {'east': {}, 'west': {}}
        SIMULATION_TOURNAMENT.play_in_game_index = 0
        SIMULATION_TOURNAMENT.playoff_teams = {'east': [], 'west': []}
        SIMULATION_TOURNAMENT.next_round_teams = {'east': [], 'west': []}
        
        ACTIVE_DRAFT_INSTANCE = None # Final cleanup
        if hasattr(SIMULATION_TOURNAMENT, 'draft_pick_corrente'):
            delattr(SIMULATION_TOURNAMENT, 'draft_pick_corrente')
        if hasattr(SIMULATION_TOURNAMENT, 'draft_risultati'):
            delattr(SIMULATION_TOURNAMENT, 'draft_risultati')
        if hasattr(SIMULATION_TOURNAMENT, 'draft_class'):
            delattr(SIMULATION_TOURNAMENT, 'draft_class')
        if hasattr(SIMULATION_TOURNAMENT, 'draft_lottery_order'):
            delattr(SIMULATION_TOURNAMENT, 'draft_lottery_order')
        OFFSEASON_FA_POOL = []
        OFFSEASON_PREVIOUS_TEAMS = {}
        global NEGOTIATION_ATTEMPTS
        NEGOTIATION_ATTEMPTS = {}

        # Update GM profile & Board objectives for the new season
        if SIMULATION_TOURNAMENT.squadra_giocatore:
            user_team = SIMULATION_TOURNAMENT.squadra_giocatore
            gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
            if not gm_prof:
                gm_prof = init_user_gm_profile(user_team.nome)
                SIMULATION_TOURNAMENT.user_gm_profile = gm_prof
            
            eval_res = evaluate_gm_contract_and_renewal(user_team, gm_prof)
            gm_firing_allowed = getattr(SIMULATION_TOURNAMENT, 'gm_firing_enabled', True)
            if eval_res and eval_res.get("status") in ["fired", "contract_expired"] and gm_firing_allowed:
                main_log.info(f"GM STATUS: {eval_res.get('message')}")
                SIMULATION_TOURNAMENT.squadra_giocatore = None
                SIMULATION_TOURNAMENT.is_spectator = False
                SIMULATION_TOURNAMENT.is_fired = True
                SIMULATION_TOURNAMENT.firing_info = eval_res
                sync_user_seat(SIMULATION_TOURNAMENT)  # the team that fired the user gets a GM
            else:
                SIMULATION_TOURNAMENT.is_fired = False
                SIMULATION_TOURNAMENT.firing_info = None
                if not gm_firing_allowed and gm_prof.contract and gm_prof.contract.years_remaining <= 0:
                    gm_prof.contract.years_remaining = 3
                generate_seasonal_objectives(user_team)

        # Reset Awards
        SIMULATION_TOURNAMENT.defensive_player_of_the_year = None
        SIMULATION_TOURNAMENT.sesto_uomo = None
        SIMULATION_TOURNAMENT.rookie_of_the_year = None
        SIMULATION_TOURNAMENT.most_improved_player = None
        SIMULATION_TOURNAMENT.all_nba_teams = []
        SIMULATION_TOURNAMENT.all_defensive_team = []
        SIMULATION_TOURNAMENT.all_rookie_team = []

        # Reset simulation flags & logs
        SIMULATION_TOURNAMENT._first_half_complete = False
        SIMULATION_TOURNAMENT._trade_deadline_completed = False
        SIMULATION_TOURNAMENT._current_gameday = 0
        SIMULATION_TOURNAMENT.current_day = 0
        SIMULATION_TOURNAMENT.box_scores = {}

        # Reset team records
        for squadra in SIMULATION_TOURNAMENT.squadre:
            squadra.reset_record_stagionale()
        from trades.windows import refresh_untouchables
        refresh_untouchables(SIMULATION_TOURNAMENT)   # draft-night flags and last season's cores must not pile up
        
        # Generate the new authentic calendar for the new season!
        SIMULATION_TOURNAMENT.genera_calendario()
        print(f"--- SERVER: Generated new calendar for Season {SIMULATION_TOURNAMENT.season_number} (Year {getattr(SIMULATION_TOURNAMENT, 'anno_corrente', 2025)}): {len(SIMULATION_TOURNAMENT.calendario)} days ---", flush=True)

        SIMULATION_TOURNAMENT.imposta_rotazioni_stagione()
        LEAGUE_STATE = "PRE_SEASON"
        SIMULATION_TOURNAMENT.league_state = "PRE_SEASON"
        
        # Initialize scouting and draft class for the new season
        simulation_logic.inizializza_scouting_e_classe_draft(SIMULATION_TOURNAMENT)
        
        # Auto-generate trade block offers
        if SIMULATION_TOURNAMENT.squadra_giocatore:
            from trades.trade_block_manager import TradeBlockManager
            SIMULATION_TOURNAMENT.pending_trade_block_offers = TradeBlockManager.generate_offers(
                SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadra_giocatore
            )
            print(f"--- SERVER: Generated {len(SIMULATION_TOURNAMENT.pending_trade_block_offers)} trade block offers ---", flush=True)

        # Auto-save the new league state
        auto_save_active_game()
            
    return jsonify(get_full_league_data_payload())

# --- Utility Endpoints ---
@app.route('/api/make_draft_pick', methods=['POST'])
def make_draft_pick():
    global LEAGUE_STATE, SIMULATION_TOURNAMENT, ACTIVE_DRAFT_INSTANCE
    data = request.get_json()
    player_name = data.get('player_name')
    if LEAGUE_STATE == "DRAFT_USER_PICK" and player_name and ACTIVE_DRAFT_INSTANCE:
        new_state = ACTIVE_DRAFT_INSTANCE.esegui_scelta_utente(player_name)
        SIMULATION_TOURNAMENT.offseason_log_data['draft_in_progress'] = new_state
        if new_state.get("status") == "COMPLETED":
            concludi_draft_logica()
    return jsonify(get_lean_league_data_payload())

@app.route('/api/league-database', methods=['GET'])
def get_league_db():
    return jsonify(simulation_logic.get_league_database(SIMULATION_TOURNAMENT)) if SIMULATION_TOURNAMENT else ({"error": "Simulation not initialized"}, 500)

@app.route('/api/player/<path:player_name>/career', methods=['GET'])
def api_get_player_career_full(player_name):
    global SIMULATION_TOURNAMENT
    import urllib.parse
    decoded_query = urllib.parse.unquote(player_name).strip()
    
    # 1. Match player object from live tournament
    target_player = None
    target_team_name = "Free Agent"
    if SIMULATION_TOURNAMENT:
        def matches_player(p, query):
            if not p or not hasattr(p, 'nome'): return False
            p_name = p.nome.lower()
            q_name = query.lower()
            if p_name == q_name: return True
            clean_p = ''.join(c for c in p_name if c.isalnum())
            clean_q = ''.join(c for c in q_name if c.isalnum())
            return clean_p == clean_q
            
        for s in getattr(SIMULATION_TOURNAMENT, 'squadre', []):
            for p in getattr(s, 'roster', []):
                if matches_player(p, decoded_query):
                    target_player = p
                    target_team_name = s.nome
                    break
            if target_player: break
            
        if not target_player:
            for p in getattr(SIMULATION_TOURNAMENT, 'free_agents_pool', []):
                if matches_player(p, decoded_query):
                    target_player = p
                    target_team_name = "Free Agent"
                    break
                    
        if not target_player:
            for p in getattr(SIMULATION_TOURNAMENT, 'giocatori_ritirati', []):
                if matches_player(p, decoded_query):
                    target_player = p
                    target_team_name = "Retired"
                    break
                    
    # 2. Extract player live details
    player_details = None
    if target_player:
        player_details = simulation_logic._get_player_details(target_player)
        player_details["squadra"] = target_team_name

    # 3. Load career data from player_careers.json
    career_file = get_historical_file_path("player_careers.json")
    raw_career_list = []
    if os.path.exists(career_file):
        try:
            with open(career_file, 'r', encoding='utf-8') as f:
                all_careers = json.load(f)
            
            norm_key1 = decoded_query.lower().replace(" ", "-")
            clean_key1 = ''.join(c for c in decoded_query.lower() if c.isalnum())
            
            # Try direct lookup
            if norm_key1 in all_careers:
                raw_career_list = all_careers[norm_key1]
            else:
                # Try finding key with clean alnum match
                for k, entries in all_careers.items():
                    clean_k = ''.join(c for c in k.lower() if c.isalnum())
                    if clean_k == clean_key1:
                        raw_career_list = entries
                        break
        except Exception as e:
            raw_career_list = []

    # Deduplicate entries for the same season number
    cleaned_list = []
    seasons_seen = set()
    for entry in sorted(raw_career_list, key=lambda x: (x.get('stagione', 0), x.get('gp', 0) or x.get('partite_giocate_rs', 0)), reverse=True):
        st = entry.get('stagione')
        if st not in seasons_seen:
            seasons_seen.add(st)
            cleaned_list.append(entry)
    cleaned_list.sort(key=lambda x: x.get('stagione', 0))

    # 4. Build the Unified Timeline and Player Storyline
    timeline = []
    
    # A. Add past historical events from cleaned_list (player_careers.json)
    for s_entry in cleaned_list:
        s_num = s_entry.get("stagione", 1)
        s_team = s_entry.get("squadra", "N/A")
        s_gp = s_entry.get("gp") or s_entry.get("partite_giocate_rs", 0)
        s_pts = s_entry.get("stats_rs", {}).get("ppg", 0) or s_entry.get("pts", 0)
        
        # NBA Title
        if s_entry.get("is_champion"):
            timeline.append({
                "season": s_num,
                "day": 100,
                "type": "championship",
                "title": f"NBA Champion 🏆",
                "description": f"Wins the NBA ring with the {s_team} in Season {s_num}.",
                "icon": "🏆",
                "team": s_team,
                "age": s_entry.get("eta", 25)
            })
            
        # Awards won
        for aw in s_entry.get("premi", []):
            timeline.append({
                "season": s_num,
                "day": 85,
                "type": "award",
                "title": f"Individual Award: {aw}",
                "description": f"Official recognition awarded in Season {s_num} with the {s_team}.",
                "icon": "⭐",
                "team": s_team,
                "age": s_entry.get("eta", 25)
            })
            
        # Notable seasonal milestone (>25 PPG or 80+ GP)
        if s_pts >= 25.0 and s_gp >= 50:
            timeline.append({
                "season": s_num,
                "day": 83,
                "type": "milestone",
                "title": f"Superstar Season: {s_pts:.1f} PPG",
                "description": f"Absolute offensive pillar for the {s_team} ({s_gp} games played).",
                "icon": "🌟",
                "team": s_team,
                "age": s_entry.get("eta", 25)
            })

    # B. Add live events recorded in memory (injuries, 50-point games, triple-doubles)
    if target_player and hasattr(target_player, 'career_log') and target_player.career_log:
        for evt in target_player.career_log:
            timeline.append(evt)

    # Sort chronologically from newest to oldest
    timeline.sort(key=lambda x: (x.get("season", 1), x.get("day", 0)), reverse=True)

    if player_details:
        career_premi = []
        career_rings = 0
        for season_entry in cleaned_list:
            for award in season_entry.get("premi", []):
                career_premi.append(award)
            if season_entry.get("is_champion"):
                career_rings += 1
        if career_premi or cleaned_list:
            player_details["premi"] = career_premi
        player_details["anelli_vinti"] = max(int(player_details.get("anelli_vinti", 0) or 0), career_rings)

        # Make sure ovr_history is always populated with consistent historical data
        ovr_hist = list(player_details.get("ovr_history") or [])
        if not ovr_hist:
            start_yr = getattr(SIMULATION_TOURNAMENT, 'starting_year', 2025) if SIMULATION_TOURNAMENT else 2025
            for c_entry in cleaned_list:
                s_num = c_entry.get("stagione", 1)
                s_ovr = c_entry.get("ovr", player_details.get("ovr", 75))
                ovr_hist.append({
                    "season": s_num,
                    "year": start_yr + s_num - 1,
                    "age": c_entry.get("eta", player_details.get("eta", 20)),
                    "ovr": s_ovr,
                    "potenziale": c_entry.get("potenziale", player_details.get("potenziale", 80)),
                    "team": c_entry.get("squadra", "Free Agent"),
                    "delta": 0,
                    "stats": c_entry.get("stats_rs", {})
                })
            if not ovr_hist:
                cur_s = getattr(SIMULATION_TOURNAMENT, 'season_number', 1) if SIMULATION_TOURNAMENT else 1
                cur_y = getattr(SIMULATION_TOURNAMENT, 'anno_corrente', 2025) if SIMULATION_TOURNAMENT else 2025
                ovr_hist.append({
                    "season": cur_s,
                    "year": cur_y,
                    "age": player_details.get("eta", 20),
                    "ovr": player_details.get("ovr", 75),
                    "potenziale": player_details.get("potenziale", 80),
                    "team": player_details.get("squadra", "Free Agent"),
                    "delta": 0
                })
        player_details["ovr_history"] = ovr_hist

    return jsonify({
        "giocatore": player_details,
        "carriera": cleaned_list,
        "timeline": timeline
    })

@app.route('/api/player-career/<player_id>', methods=['GET'])
def get_player_career(player_id):
    career_file = get_historical_file_path("player_careers.json")
    normalized_id = player_id.lower().replace(" ", "-")
    if os.path.exists(career_file):
        with open(career_file, 'r', encoding='utf-8') as f:
            try: all_careers = json.load(f)
            except json.JSONDecodeError: all_careers = {}
        raw_list = all_careers.get(normalized_id, [])
        
        # Deduplicate entries for the same season number
        cleaned_list = []
        seasons_seen = set()
        for entry in sorted(raw_list, key=lambda x: (x.get('stagione', 0), x.get('gp', 0)), reverse=True):
            st = entry.get('stagione')
            if st not in seasons_seen:
                seasons_seen.add(st)
                cleaned_list.append(entry)
        cleaned_list.sort(key=lambda x: x.get('stagione', 0))
        return jsonify(cleaned_list)

@app.route('/api/player-profile/<path:player_name>', methods=['GET'])
def api_get_player_profile(player_name):
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Tournament not initialized"}), 500
        
    import urllib.parse
    decoded_query = urllib.parse.unquote(player_name).strip()
    
    def matches_player(p, query):
        if not p or not hasattr(p, 'nome'):
            return False
        p_name = p.nome.lower()
        q_name = query.lower()
        if p_name == q_name:
            return True
        clean_p = ''.join(c for c in p_name if c.isalnum())
        clean_q = ''.join(c for c in q_name if c.isalnum())
        return clean_p == clean_q
    
    # Search active rosters
    target_player = None
    target_team_name = "Free Agent"
    for s in getattr(SIMULATION_TOURNAMENT, 'squadre', []):
        for p in getattr(s, 'roster', []):
            if matches_player(p, decoded_query):
                target_player = p
                target_team_name = s.nome
                break
        if target_player:
            break
            
    # Search free agents
    if not target_player:
        for p in getattr(SIMULATION_TOURNAMENT, 'free_agents_pool', []):
            if matches_player(p, decoded_query):
                target_player = p
                target_team_name = "Free Agent"
                break
                
    # Search retired
    if not target_player:
        for p in getattr(SIMULATION_TOURNAMENT, 'giocatori_ritirati', []):
            if matches_player(p, decoded_query):
                target_player = p
                target_team_name = "Retired"
                break
                
    if not target_player:
        return jsonify({"error": f"Player '{player_name}' not found"}), 404
        
    details = simulation_logic._get_player_details(target_player)
    details["squadra"] = target_team_name
    return jsonify(details)

@app.route('/api/history', methods=['GET'])
def get_history():
    """Championship history for the History page (core/history_view.py), newest season first."""
    from core.history_view import championship_history
    data = _read_historical_json("league_history.json", [])
    return jsonify(championship_history(data if isinstance(data, list) else [], _user_team_name()))

@app.route('/api/hall-of-fame', methods=['GET'])
def get_hall_of_fame():
    """Ranked Hall of Fame (podium + tiers) for the History page."""
    from core.history_view import hall_of_fame_view
    data = _read_historical_json("hall_of_fame.json", {})
    careers = _read_historical_json("player_careers.json", {})
    classes = data.get("classes", []) if isinstance(data, dict) else []
    return jsonify(hall_of_fame_view(classes, careers if isinstance(careers, dict) else {}, _user_team_name()))

def _read_historical_json(filename, default):
    """A save's history file, or `default` when it is missing or unreadable."""
    path = get_historical_file_path(filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default

def _user_team_name():
    team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None) if SIMULATION_TOURNAMENT else None
    return team.nome if team else None

import main as simulation_logic # Make sure the import is like this
from core.records import get_all_records

@app.route('/api/records', methods=['GET'])
def get_records():
    """League Records (core/records_view.py): single-game highs, single-season bests, triple-doubles."""
    from core.history_view import season_years
    from core.records_view import league_records_view
    careers = _read_historical_json("player_careers.json", {})
    history = _read_historical_json("league_history.json", [])
    return jsonify(league_records_view(get_all_records(), careers if isinstance(careers, dict) else {},
                                       _user_team_name(), season_years(history if isinstance(history, list) else []),
                                       getattr(SIMULATION_TOURNAMENT, 'starting_year', None)))


# =============================================================================
# ### FRANCHISE LEGACY & TROPHY ROOM ENDPOINTS ###
# =============================================================================

@app.route('/api/franchise-legacy/teams', methods=['GET'])
def api_franchise_legacy_teams():
    """The Trophy Room's team picker: the user's team first, then by titles."""
    from core.franchise_legacy import get_all_franchises_summary
    from core.trophy_room_view import franchise_list
    return jsonify(franchise_list(get_all_franchises_summary(SIMULATION_TOURNAMENT), _user_team_name()))

@app.route('/api/franchise-legacy/<path:team_name>', methods=['GET'])
def api_franchise_legacy_detail(team_name):
    """One franchise's Trophy Room (core/trophy_room_view.py)."""
    from urllib.parse import unquote
    from core.franchise_legacy import get_franchise_legacy
    from core.trophy_room_view import trophy_room_view

    clean_name = unquote(team_name).strip()
    history = _read_historical_json("league_history.json", [])
    return jsonify(trophy_room_view(get_franchise_legacy(clean_name, SIMULATION_TOURNAMENT),
                                    history if isinstance(history, list) else [], get_all_records(),
                                    _user_team_name(), getattr(SIMULATION_TOURNAMENT, 'starting_year', None)))


# =============================================================================
# ### RIVALRY & STORYLINE API ENDPOINTS ###
# =============================================================================

@app.route('/api/rivalries', methods=['GET'])
def get_rivalries():
    """Return all rivalry data for the frontend."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    rivalry_data = SIMULATION_TOURNAMENT.rivalry_tracker.to_dict()
    return jsonify(rivalry_data)


@app.route('/api/rivalry/<team1>/<team2>', methods=['GET'])
def get_rivalry_detail(team1, team2):
    """Get detailed rivalry history between two teams."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    # Decode URL-encoded team names (spaces become %20)
    from urllib.parse import unquote
    team1 = unquote(team1)
    team2 = unquote(team2)
    
    context = SIMULATION_TOURNAMENT.rivalry_tracker.get_matchup_context(team1, team2)
    
    # Add team records for context
    team1_obj = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == team1), None)
    team2_obj = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == team2), None)
    
    if team1_obj:
        context['team1_record'] = f"{team1_obj.vittorie}-{team1_obj.sconfitte}"
    if team2_obj:
        context['team2_record'] = f"{team2_obj.vittorie}-{team2_obj.sconfitte}"
    
    return jsonify(context)


@app.route('/api/storylines', methods=['GET'])
def get_storylines():
    """Return current active storylines (MVP race, streaks, etc.)."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    # Update MVP race before returning
    all_players = [p for s in SIMULATION_TOURNAMENT.squadre for p in s.roster]
    SIMULATION_TOURNAMENT.storyline_engine.update_mvp_race(all_players)
    
    storyline_data = SIMULATION_TOURNAMENT.storyline_engine.to_dict()
    
    # Add top rivalries to storylines
    storyline_data['top_rivalries'] = SIMULATION_TOURNAMENT.rivalry_tracker.to_dict().get('top_rivalries', [])[:5]
    
    return jsonify(storyline_data)


@app.route('/api/matchup-preview/<team1>/<team2>', methods=['GET'])
def get_matchup_preview(team1, team2):
    """Get pre-game storylines, starting lineups, and tactical context for a matchup."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    from urllib.parse import unquote
    team1 = unquote(team1)
    team2 = unquote(team2)
    
    # Get team objects
    team1_obj = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == team1), None)
    team2_obj = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome == team2), None)
    
    if not team1_obj or not team2_obj:
        return jsonify({"error": "Team not found"}), 404
    
    # Get rivalry context
    rivalry_context = SIMULATION_TOURNAMENT.rivalry_tracker.get_matchup_context(team1, team2)
    
    # Get pregame storylines
    storylines = SIMULATION_TOURNAMENT.storyline_engine.get_pregame_storylines(
        team1_obj, team2_obj, SIMULATION_TOURNAMENT.rivalry_tracker
    )
    
    # Ensure starting lineups are initialized and not stale from previous game's substitutions
    for team_obj in [team1_obj, team2_obj]:
        team_obj.scegli_quintetto_iniziale()
            
    def get_lineup_data(team_obj):
        lineup_list = []
        posizioni = ['PG', 'SG', 'SF', 'PF', 'C']
        for pos in posizioni:
            p = team_obj.posizione_in_campo.get(pos)
            if p:
                estimated_off = int(round((p.abilita.close_shot_rating + p.abilita.mid_range_shot_rating + p.abilita.three_point_shot_rating + p.abilita.shot_iq + p.abilita.passing_accuracy + p.abilita.ball_handling) / 6))
                estimated_def = int(round((p.abilita.interior_defense_rating + p.abilita.perimeter_defense_rating + p.abilita.steal_rating + p.abilita.block_rating + p.abilita.defensive_rebound_rating + p.abilita.defensive_iq_rating) / 6))
                lineup_list.append({
                    "posizione": pos,
                    "nome": p.nome,
                    "ruolo_naturale": p.ruolo,
                    "valutazione_posizionale": p.valutazioni_posizionali.get(pos, p.valutazione),
                    "ovr": p.valutazione,
                    "eta": p.eta,
                    "off_score": estimated_off,
                    "def_score": estimated_def,
                    "infortunato": p.infortunato
                })
            else:
                lineup_list.append({
                    "posizione": pos,
                    "nome": "Unavailable",
                    "ruolo_naturale": "-",
                    "valutazione_posizionale": 0,
                    "ovr": 0,
                    "eta": 0,
                    "off_score": 0,
                    "def_score": 0,
                    "infortunato": False
                })
        return lineup_list

    lineup1 = get_lineup_data(team1_obj)
    lineup2 = get_lineup_data(team2_obj)
    
    # Generate tactical warnings and recommendations
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    tactical_warnings = []
    
    our_team_obj = None
    opp_team_obj = None
    if user_team:
        if team1_obj.nome == user_team.nome:
            our_team_obj = team1_obj
            opp_team_obj = team2_obj
        elif team2_obj.nome == user_team.nome:
            our_team_obj = team2_obj
            opp_team_obj = team1_obj
            
    if our_team_obj and opp_team_obj:
        # 1. Opponent center check
        opp_c = opp_team_obj.posizione_in_campo.get('C')
        if opp_c and (opp_c.valutazione >= 85 or opp_c.abilita.interior_defense_rating >= 85):
            tactical_warnings.append({
                "type": "warning",
                "message": f"Opposing center {opp_c.nome} (OVR {opp_c.valutazione}) commands the paint.",
                "recommendation": "Protect the Paint"
            })
        # 2. Opponent power forward check
        opp_pf = opp_team_obj.posizione_in_campo.get('PF')
        if opp_pf and (opp_pf.valutazione >= 85 or opp_pf.abilita.interior_defense_rating >= 85):
            tactical_warnings.append({
                "type": "warning",
                "message": f"Opposing power forward {opp_pf.nome} (OVR {opp_pf.valutazione}) is dominant on the low block.",
                "recommendation": "Protect the Paint"
            })
        # 3. Opponent perimeter threats
        perimeter_threats = []
        for pos in ['PG', 'SG', 'SF']:
            p = opp_team_obj.posizione_in_campo.get(pos)
            if p and p.abilita.three_point_shot_rating >= 85:
                perimeter_threats.append(f"{p.nome} (3PT {p.abilita.three_point_shot_rating})")
        if perimeter_threats:
            threat_names = ", ".join(perimeter_threats)
            tactical_warnings.append({
                "type": "warning",
                "message": f"Watch out for lethal opposing perimeter shooters: {threat_names}.",
                "recommendation": "Run Shooters Off the Line"
            })
        # 4. Opponent weak ball handler
        opp_pm = opp_team_obj.posizione_in_campo.get('PG')
        if opp_pm and opp_pm.abilita.ball_handling <= 78:
            tactical_warnings.append({
                "type": "tip",
                "message": f"Opposing point guard {opp_pm.nome} has shaky ball-handling ({opp_pm.abilita.ball_handling}). Apply full-court ball pressure.",
                "recommendation": "Full-Court Press"
            })
        # 5. Our team spacing check
        our_shooters = sum(1 for pos in ['PG', 'SG', 'SF'] if (
            our_team_obj.posizione_in_campo.get(pos) and 
            our_team_obj.posizione_in_campo.get(pos).abilita.three_point_shot_rating >= 80
        ))
        if our_shooters >= 2:
            tactical_warnings.append({
                "type": "tip",
                "message": f"You have {our_shooters} elite 3-point marksmen in your starting unit. Spread the floor.",
                "recommendation": "Hunt for Threes"
            })
        # 6. Star player check
        our_star = next((p for p in our_team_obj.quintetto if p.valutazione >= 88), None)
        if our_star:
            tactical_warnings.append({
                "type": "info",
                "message": f"Your star {our_star.nome} (OVR {our_star.valutazione}) is your main weapon.",
                "recommendation": "Feed the Hot Hand"
            })
    else:
        tactical_warnings.append({
            "type": "info",
            "message": "No tactical recommendation (neutral matchup).",
            "recommendation": "Balanced Approach"
        })
        
    return jsonify({
        "rivalry": rivalry_context,
        "storylines": [
            {
                "type": s.type,
                "headline": s.headline,
                "description": s.description,
                "intensity": s.intensity,
                "icon": s.icon
            }
            for s in storylines
        ],
        "team1": {
            "name": team1,
            "record": f"{team1_obj.vittorie}-{team1_obj.sconfitte}",
            "conference": team1_obj.conference,
            "lineup": lineup1
        },
        "team2": {
            "name": team2,
            "record": f"{team2_obj.vittorie}-{team2_obj.sconfitte}",
            "conference": team2_obj.conference,
            "lineup": lineup2
        },
        "tactical_warnings": tactical_warnings
    })


# =============================================================================
# ### LEAGUE ANALYTICS API ENDPOINTS (core/analytics_view.py, built from the season's box scores) ###
# =============================================================================

def _analytics_inputs(kind='rs'):
    """Box scores, team -> conference, the user's team and every rostered player name, for core/analytics_view.
    kind 'po': the season's playoff games, which keep their box scores in the bracket."""
    from core.analytics_view import playoff_box_scores
    torneo = SIMULATION_TOURNAMENT
    teams = getattr(torneo, 'squadre', []) or []
    conferences = {s.nome: getattr(s, 'conference', None) for s in teams}
    rostered = {p.nome for s in teams for p in (getattr(s, 'roster', []) or [])}
    if kind == 'po':
        box_scores = playoff_box_scores(getattr(torneo, 'playoff_bracket_data', None))
    else:
        box_scores = getattr(torneo, 'box_scores', {}) or {}
    return box_scores, conferences, _user_team_name(), rostered


def _analytics_kind():
    return 'po' if request.args.get('kind') == 'po' else 'rs'


def _with_kind(view, kind):
    view.setdefault('meta', {})['kind'] = kind
    return view


@app.route('/api/analytics/players', methods=['GET'])
def get_analytics_players():
    from core.analytics_view import players_view
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    kind = _analytics_kind()
    box_scores, _conferences, user_team, rostered = _analytics_inputs(kind)
    return jsonify(_with_kind(players_view(box_scores, rostered, user_team), kind))


@app.route('/api/analytics/teams', methods=['GET'])
def get_analytics_teams():
    from core.analytics_view import teams_view
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    kind = _analytics_kind()
    box_scores, conferences, user_team, _rostered = _analytics_inputs(kind)
    return jsonify(_with_kind(teams_view(box_scores, conferences, user_team), kind))


@app.route('/api/analytics/league', methods=['GET'])
def get_analytics_league():
    from core.analytics_view import league_view
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    box_scores, _conferences, user_team, _rostered = _analytics_inputs()
    return jsonify(league_view(box_scores, user_team))


@app.route('/api/analytics/splits', methods=['GET'])
def get_analytics_splits():
    from core.analytics_view import splits_view
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    player, team = request.args.get('player'), request.args.get('team')
    if not player and not team:
        return jsonify({"error": "Pick a player or a team"}), 400
    box_scores, conferences, user_team, _rostered = _analytics_inputs()
    view = splits_view(box_scores, conferences, user_team, player=player or None, team=None if player else team)
    if view is None:
        return jsonify({"error": f"No games found for {player or team} this season"}), 404
    return jsonify(view)


def _database_inputs():
    """Careers (with the season being played merged in), live players, retired slugs, years, starting year, user team
    for core/database_view."""
    from core.analytics_view import archive_season_lines
    from core.database_view import current_records, merged_careers, slug
    from core.history_view import season_years
    torneo = SIMULATION_TOURNAMENT
    careers = _read_historical_json("player_careers.json", {})
    history = _read_historical_json("league_history.json", [])
    retired_ids = _read_historical_json("retired_players_ids.json", [])
    live, players = {}, []
    rostered = [(p, s.nome, 'Active') for s in getattr(torneo, 'squadre', []) or [] for p in getattr(s, 'roster', []) or []]
    # Free agents: the in-season pool, plus the offseason market (kept in OFFSEASON_FA_POOL until free agency ends)
    pool = [(p, None, 'Free agent') for p in (getattr(torneo, 'free_agents_pool', []) or []) + (OFFSEASON_FA_POOL or [])]
    for p, team, status in rostered + pool:
        contract = getattr(p, 'contract', None)
        info = {'name': p.nome, 'status': status, 'team': team, 'pos': getattr(p, 'ruolo', None),
                'age': getattr(p, 'eta', None), 'ovr': getattr(p, 'ovr', None), 'pot': getattr(p, 'potenziale', None),
                'salary': getattr(contract, 'salario_annuale', None), 'years': getattr(contract, 'anni_rimanenti', None)}
        live.setdefault(slug(p.nome), info)
        players.append(info)
    season = getattr(torneo, 'season_number', None)
    season_lines = archive_season_lines(getattr(torneo, 'box_scores', {}) or {},
                                        getattr(torneo, 'playoff_bracket_data', None), [p['name'] for p in players])
    current = current_records(players, season_lines['rs'], season, po_lines=season_lines['po'])
    careers = merged_careers(careers if isinstance(careers, dict) else {}, current, season)
    retired = set(retired_ids if isinstance(retired_ids, list) else [])
    retired |= {slug(p.nome) for p in getattr(torneo, 'giocatori_ritirati', []) or []}
    return (careers, live, retired, season_years(history if isinstance(history, list) else []),
            getattr(torneo, 'starting_year', None), _user_team_name())


def _not_initialized():
    return jsonify({"error": "Simulation not initialized"}), 500


@app.route('/api/database/players', methods=['GET'])
def get_database_players():
    from core.database_view import directory_view
    if not SIMULATION_TOURNAMENT:
        return _not_initialized()
    careers, live, retired, years, starting_year, _user_team = _database_inputs()
    return jsonify(directory_view(careers, live, retired, years, starting_year, request.args.to_dict()))


@app.route('/api/database/player/<player_slug>', methods=['GET'])
def get_database_player(player_slug):
    from core.database_view import player_view
    if not SIMULATION_TOURNAMENT:
        return _not_initialized()
    careers, live, retired, years, starting_year, _user_team = _database_inputs()
    view = player_view(player_slug, careers, live, retired, years, starting_year)
    if view is None:
        return jsonify({"error": "Player not found"}), 404
    return jsonify(view)


@app.route('/api/database/season', methods=['GET'])
def get_database_season():
    from core.database_view import season_view
    if not SIMULATION_TOURNAMENT:
        return _not_initialized()
    careers, _live, _retired, years, starting_year, user_team = _database_inputs()
    return jsonify(season_view(careers, request.args.get('season', type=int), request.args.get('kind', 'rs'),
                               years, starting_year, user_team))


@app.route('/api/database/finder', methods=['POST'])
def post_database_finder():
    from core.database_view import finder_view
    if not SIMULATION_TOURNAMENT:
        return _not_initialized()
    careers, live, retired, years, starting_year, user_team = _database_inputs()
    return jsonify(finder_view(careers, request.get_json(silent=True) or {}, live, retired, years, starting_year,
                               user_team))


@app.route('/api/database/presets', methods=['GET'])
def get_database_presets():
    return jsonify(list(CONFIG.DATABASE.PRESETS))


@app.route('/api/team-card/<path:team_name>', methods=['GET'])
def get_team_card(team_name):
    """The team card popup (core/team_card_view.py)."""
    from urllib.parse import unquote
    from core.league_finances import season_lines
    from core.team_card_view import team_card_view
    if not SIMULATION_TOURNAMENT:
        return _not_initialized()
    torneo = SIMULATION_TOURNAMENT
    name = unquote(team_name).strip()
    squadra = next((s for s in torneo.squadre if s.nome == name), None)
    if squadra is None:
        return jsonify({"error": "Team not found"}), 404

    def player_row(p):
        stats, contract = getattr(p, 'season_stats', None), getattr(p, 'contract', None)
        gp = getattr(stats, 'partite_giocate', 0) or 0
        return {'name': p.nome, 'pos': p.ruolo, 'age': p.eta, 'ovr': p.ovr, 'pot': getattr(p, 'potenziale', None),
                'ppg': round(stats.punti / gp, 1) if gp else None,
                'salary': getattr(contract, 'salario_annuale', None), 'years': getattr(contract, 'anni_rimanenti', None),
                'injured': bool(getattr(p, 'infortunato', False))}

    league = [{'name': s.nome, 'conference': getattr(s, 'conference', None), 'wins': s.vittorie, 'losses': s.sconfitte}
              for s in torneo.squadre]
    team = {'name': squadra.nome, 'conference': getattr(squadra, 'conference', None), 'wins': squadra.vittorie,
            'losses': squadra.sconfitte, 'payroll': squadra.payroll, 'roster': [player_row(p) for p in squadra.roster],
            'future_picks': simulation_logic.team_future_picks(torneo, squadra),
            'standings_history': list(getattr(squadra, 'standings_history', []) or [])}
    return jsonify(team_card_view(team, league, season_lines(torneo, CONFIG.ECONOMY), CONFIG.OFFSEASON.ROSTER_SIZE_LIMIT,
                                  CONFIG.TEAM_CARD.ROTATION_SIZE, CONFIG.TEAM_CARD.SEASONS_SHOWN, _user_team_name()))


# =============================================================================
# ### TRADE FINDER API ENDPOINTS ###
# =============================================================================

def trade_window_closed_response():
    """A 400 response when user trades are not allowed right now, else None."""
    open_, message = user_trade_window(SIMULATION_TOURNAMENT, LEAGUE_STATE)
    if open_:
        return None
    return jsonify({"error": message}), 400


@app.route('/api/trade-finder', methods=['POST'])
def trade_finder():
    """
    Find possible trades for a specific player, pick, or customized multi-asset package.
    Input: { giving_players?: string[], giving_picks?: string[], player_name?: string }
    Output: { trades: [...], player: {...} }
    """
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
    
    data = request.get_json() or {}
    giving_player_names = data.get('giving_players', [])
    giving_pick_keys = data.get('giving_picks', [])
    asset_key = data.get('player_name', '')
    
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore, manual=True)
    
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400

    # Multi-Asset Package Search
    if giving_player_names or giving_pick_keys:
        resolved_players = []
        for name in giving_player_names:
            for p in user_team.roster:
                if p.nome.lower() == name.lower():
                    resolved_players.append(p)
                    break
        
        include_3_team = data.get('include_3_team', True)
        include_chains = data.get('include_chains', True)
        target_position = data.get('target_position', None)
        trade_mode_filter = data.get('trade_mode_filter', 'all') # 'all' | '2-team' | '3-team' | 'multi-team'
        
        trades_2 = []
        if trade_mode_filter in ['all', '2-team']:
            trades_2 = finder.find_trades_for_package(resolved_players, giving_pick_keys)
            for t in trades_2:
                t["trade_type"] = "2-team"

        trades_3 = []
        if include_3_team and resolved_players and trade_mode_filter in ['all', '3-team']:
            trades_3 = finder.find_3_team_trades_for_package(resolved_players, giving_pick_keys, target_position=target_position)

        trades_chain = []
        if (include_chains or trade_mode_filter == 'multi-team') and trade_mode_filter in ['all', 'multi-team']:
            trades_chain = finder.find_multi_team_chain_trades(giving_players=resolved_players, giving_picks=giving_pick_keys)

        if trade_mode_filter == '3-team':
            trades = trades_3
        elif trade_mode_filter == '2-team':
            trades = trades_2
        elif trade_mode_filter == 'multi-team':
            trades = trades_chain
        else:
            trades = trades_3 + trades_2 + trades_chain

        summary_names = [p.nome for p in resolved_players] + giving_pick_keys
        player_info = {
            "name": "Custom Package (" + ", ".join(summary_names) + ")",
            "team": user_team.nome,
            "ovr": max([p.ovr for p in resolved_players], default=75),
            "potential": max([p.potenziale for p in resolved_players], default=75),
            "position": "Multi-Asset",
            "age": round(sum(p.eta for p in resolved_players)/len(resolved_players), 1) if resolved_players else 25,
            "salary": sum(p.contract.salario_annuale for p in resolved_players if p.contract),
            "contract_years": 2,
            "trade_value": sum(finder.get_strategic_value(p, user_team) for p in resolved_players) + sum(finder.get_strategic_value(pk, user_team) for pk in giving_pick_keys)
        }
        return jsonify({"trades": trades, "player": player_info})
        
    if not asset_key:
        return jsonify({"error": "Asset key or package required"}), 400
        
    # Check prefixes
    if asset_key.startswith('player:'):
        # Specific user player search
        player_name = asset_key[len('player:'):]
        player = None
        for p in user_team.roster:
            if p.nome.lower() == player_name.lower():
                player = p
                break
        if not player:
            for squadra in SIMULATION_TOURNAMENT.squadre:
                for p in squadra.roster:
                    if p.nome.lower() == player_name.lower():
                        player = p
                        break
                if player:
                    break
                
        if not player:
            return jsonify({"error": f"Player '{player_name}' not found"}), 404
            
        trades = finder.find_trades_for_player(player)
        player_info = {
            "name": player.nome,
            "team": player.squadra.nome if player.squadra else "FA",
            "ovr": player.ovr,
            "potential": player.potenziale,
            "position": player.ruolo,
            "age": player.eta,
            "salary": player.contract.salario_annuale if player.contract else 0,
            "contract_years": player.contract.anni_rimanenti if player.contract else 0,
            "trade_value": round(player.trade_value, 1) if hasattr(player, 'trade_value') else player.ovr
        }
    elif asset_key.startswith('pick:'):
        # Draft pick search
        pick_key = asset_key[len('pick:'):]
        trades = finder.find_trades_for_pick(pick_key)
        
        try:
            y_str, pk = pick_key.split(":", 1)
            pick_year = int(y_str)
        except ValueError:
            pick_year = 1
            pk = pick_key
            
        season_num = SIMULATION_TOURNAMENT.season_number
        starting_year = getattr(SIMULATION_TOURNAMENT, 'starting_year', 2025)
        draft_year = starting_year + season_num + pick_year - 1
        pick_val = finder.get_strategic_value(pick_key, SIMULATION_TOURNAMENT.squadra_giocatore)
        
        player_info = {
            "name": f"{draft_year} Draft Pick ({pk})",
            "team": SIMULATION_TOURNAMENT.squadra_giocatore.nome,
            "ovr": "PICK",
            "potential": "-",
            "position": "Pick",
            "age": "-",
            "salary": 0.0,
            "contract_years": "-",
            "trade_value": round(pick_val, 1)
        }
    elif asset_key.startswith('target:'):
        target_name = asset_key[len('target:'):]
        target = None
        for squadra in SIMULATION_TOURNAMENT.squadre:
            for p in squadra.roster:
                if p.nome.lower() == target_name.lower():
                    target = p
                    break
            if target:
                break
                
        if not target:
            return jsonify({"error": f"Target player '{target_name}' not found"}), 404
            
        trades = finder.find_trades_for_target_player(target)
        player_info = {
            "name": f"🎯 target: {target.nome}",
            "team": target.squadra.nome if target.squadra else "FA",
            "ovr": target.ovr,
            "potential": target.potenziale,
            "position": target.ruolo,
            "age": target.eta,
            "salary": target.contract.salario_annuale if target.contract else 0,
            "contract_years": target.contract.anni_rimanenti if target.contract else 0,
            "trade_value": round(target.trade_value, 1) if hasattr(target, 'trade_value') else target.ovr
        }
    else:
        player_name = asset_key
        player = None
        for squadra in SIMULATION_TOURNAMENT.squadre:
            for p in squadra.roster:
                if p.nome.lower() == player_name.lower():
                    player = p
                    break
            if player:
                break
                
        if not player:
            return jsonify({"error": f"Player '{player_name}' not found"}), 404
            
        trades = finder.find_trades_for_player(player)
        player_info = {
            "name": player.nome,
            "team": player.squadra.nome if player.squadra else "FA",
            "ovr": player.ovr,
            "potential": player.potenziale,
            "position": player.ruolo,
            "age": player.eta,
            "salary": player.contract.salario_annuale if player.contract else 0,
            "contract_years": player.contract.anni_rimanenti if player.contract else 0,
            "trade_value": round(player.trade_value, 1) if hasattr(player, 'trade_value') else player.ovr
        }
        
    return jsonify({"trades": trades, "player": player_info})


# =============================================================================
# ### 3-TEAM TRADE ENDPOINTS ###
# =============================================================================

@app.route('/api/validate-3-team-trade', methods=['POST'])
def validate_3_team_trade_endpoint():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No user team selected"}), 400
        
    data = request.get_json() or {}
    team_b_name = data.get('team_b', '')
    team_c_name = data.get('team_c', '')
    
    team_b = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome.lower() == team_b_name.lower()), None)
    team_c = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome.lower() == team_c_name.lower()), None)
    
    if not team_b or not team_c:
        return jsonify({"error": "Select both partner teams (B and C)"}), 400
    if len({user_team.nome, team_b.nome, team_c.nome}) < 3:
        return jsonify({"error": "The three teams must be distinct"}), 400
        
    raw_trade_data = data.get('trade_data', {})
    pick_protections = data.get('pick_protections', {})
    
    # Helper to resolve player objects
    def resolve_assets(team_obj, p_names, pick_keys):
        resolved = []
        for name in p_names:
            for p in team_obj.roster:
                if p.nome.lower() == name.lower():
                    resolved.append(p)
                    break
        for pk in pick_keys:
            resolved.append(pk)
        return resolved
        
    trade_data = {
        "team_a": {
            "gives_to_b": resolve_assets(user_team, raw_trade_data.get('a_to_b_players', []), raw_trade_data.get('a_to_b_picks', [])),
            "gives_to_c": resolve_assets(user_team, raw_trade_data.get('a_to_c_players', []), raw_trade_data.get('a_to_c_picks', []))
        },
        "team_b": {
            "gives_to_a": resolve_assets(team_b, raw_trade_data.get('b_to_a_players', []), raw_trade_data.get('b_to_a_picks', [])),
            "gives_to_c": resolve_assets(team_b, raw_trade_data.get('b_to_c_players', []), raw_trade_data.get('b_to_c_picks', []))
        },
        "team_c": {
            "gives_to_a": resolve_assets(team_c, raw_trade_data.get('c_to_a_players', []), raw_trade_data.get('c_to_a_picks', [])),
            "gives_to_b": resolve_assets(team_c, raw_trade_data.get('c_to_b_players', []), raw_trade_data.get('c_to_b_picks', []))
        }
    }
    
    from trades.trade_validator import TradeValidator
    is_valid, validation_msg, status_dict = TradeValidator.validate_3_team_trade(
        user_team, team_b, team_c, trade_data, torneo=SIMULATION_TOURNAMENT
    )
    
    ai_accepted_b = False
    ai_reason_b = "CBA rules not met"
    ai_accepted_c = False
    ai_reason_c = "CBA rules not met"
    why = ""

    if is_valid:
        from trades.trade_finder import TradeFinder
        finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore, manual=True)
        
        gives_b = trade_data["team_b"]["gives_to_a"] + trade_data["team_b"]["gives_to_c"]
        receives_b = trade_data["team_a"]["gives_to_b"] + trade_data["team_c"]["gives_to_b"]
        ai_accepted_b, ai_reason_b = finder.would_accept_trade_with_reason(team_b, receives_b, gives_b, pick_protections=pick_protections)
        
        gives_c = trade_data["team_c"]["gives_to_a"] + trade_data["team_c"]["gives_to_b"]
        receives_c = trade_data["team_a"]["gives_to_c"] + trade_data["team_b"]["gives_to_c"]
        ai_accepted_c, ai_reason_c = finder.would_accept_trade_with_reason(team_c, receives_c, gives_c, pick_protections=pick_protections)
        if ai_accepted_b and ai_accepted_c:
            why = finder.user_motive(finder.three_team_deal(user_team, team_b, team_c, trade_data)).why

    return jsonify({
        "is_valid": is_valid,
        "validation_message": validation_msg,
        "status_by_team": status_dict,
        "team_b": {
            "name": team_b.nome,
            "accepted": ai_accepted_b,
            "reason": ai_reason_b
        },
        "team_c": {
            "name": team_c.nome,
            "accepted": ai_accepted_c,
            "reason": ai_reason_c
        },
        "all_accepted": is_valid and ai_accepted_b and ai_accepted_c,
        "why": why
    })


@app.route('/api/execute-3-team-trade', methods=['POST'])
def execute_3_team_trade_endpoint():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No user team selected"}), 400
        
    data = request.get_json() or {}
    team_b_name = data.get('team_b', '')
    team_c_name = data.get('team_c', '')
    
    team_b = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome.lower() == team_b_name.lower()), None)
    team_c = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome.lower() == team_c_name.lower()), None)
    
    if not team_b or not team_c:
        return jsonify({"error": "Partner teams not found"}), 400
        
    raw_trade_data = data.get('trade_data', {})
    pick_protections = data.get('pick_protections', {})
    
    def resolve_assets(team_obj, p_names, pick_keys):
        resolved = []
        for name in p_names:
            for p in team_obj.roster:
                if p.nome.lower() == name.lower():
                    resolved.append(p)
                    break
        for pk in pick_keys:
            resolved.append(pk)
        return resolved
        
    if 'team_a' in raw_trade_data:
        # Structured format generated by the 3-team Trade Finder
        def parse_asset_list(team_obj, asset_list):
            players = []
            picks = []
            for a in asset_list:
                if isinstance(a, str) and ":" in a:
                    picks.append(a)
                elif isinstance(a, str):
                    players.append(a)
                elif hasattr(a, 'nome'):
                    players.append(a.nome)
            return resolve_assets(team_obj, players, picks)

        trade_data = {
            "team_a": {
                "gives_to_b": parse_asset_list(user_team, raw_trade_data.get('team_a', {}).get('gives_to_b', [])),
                "gives_to_c": parse_asset_list(user_team, raw_trade_data.get('team_a', {}).get('gives_to_c', []))
            },
            "team_b": {
                "gives_to_a": parse_asset_list(team_b, raw_trade_data.get('team_b', {}).get('gives_to_a', [])),
                "gives_to_c": parse_asset_list(team_b, raw_trade_data.get('team_b', {}).get('gives_to_c', []))
            },
            "team_c": {
                "gives_to_a": parse_asset_list(team_c, raw_trade_data.get('team_c', {}).get('gives_to_a', [])),
                "gives_to_b": parse_asset_list(team_c, raw_trade_data.get('team_c', {}).get('gives_to_b', []))
            }
        }
    else:
        trade_data = {
            "team_a": {
                "gives_to_b": resolve_assets(user_team, raw_trade_data.get('a_to_b_players', []), raw_trade_data.get('a_to_b_picks', [])),
                "gives_to_c": resolve_assets(user_team, raw_trade_data.get('a_to_c_players', []), raw_trade_data.get('a_to_c_picks', []))
            },
            "team_b": {
                "gives_to_a": resolve_assets(team_b, raw_trade_data.get('b_to_a_players', []), raw_trade_data.get('b_to_a_picks', [])),
                "gives_to_c": resolve_assets(team_b, raw_trade_data.get('b_to_c_players', []), raw_trade_data.get('b_to_c_picks', []))
            },
            "team_c": {
                "gives_to_a": resolve_assets(team_c, raw_trade_data.get('c_to_a_players', []), raw_trade_data.get('c_to_a_picks', [])),
                "gives_to_b": resolve_assets(team_c, raw_trade_data.get('c_to_b_players', []), raw_trade_data.get('c_to_b_picks', []))
            }
        }
    
    from trades.trade_validator import TradeValidator
    is_valid, validation_msg, _ = TradeValidator.validate_3_team_trade(
        user_team, team_b, team_c, trade_data, torneo=SIMULATION_TOURNAMENT
    )
    if not is_valid:
        return jsonify({"error": f"Trade not CBA compliant: {validation_msg}"}), 400
        
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore, manual=True)
    
    # Check acceptance
    gives_b = trade_data["team_b"]["gives_to_a"] + trade_data["team_b"]["gives_to_c"]
    receives_b = trade_data["team_a"]["gives_to_b"] + trade_data["team_c"]["gives_to_b"]
    ai_acc_b, reason_b = finder.would_accept_trade_with_reason(team_b, receives_b, gives_b, pick_protections=pick_protections)
    if not ai_acc_b:
        return jsonify({"error": f"{team_b.nome} rejects the trade: {reason_b}"}), 400
        
    gives_c = trade_data["team_c"]["gives_to_a"] + trade_data["team_c"]["gives_to_b"]
    receives_c = trade_data["team_a"]["gives_to_c"] + trade_data["team_b"]["gives_to_c"]
    ai_acc_c, reason_c = finder.would_accept_trade_with_reason(team_c, receives_c, gives_c, pick_protections=pick_protections)
    if not ai_acc_c:
        return jsonify({"error": f"{team_c.nome} rejects the trade: {reason_c}"}), 400
        
    motive = finder.user_motive(finder.three_team_deal(user_team, team_b, team_c, trade_data))
    success = finder.execute_3_team_trade(user_team, team_b, team_c, trade_data, pick_protections=pick_protections, motive=motive)
    if not success:
        return jsonify({"error": "Error while executing the 3-team trade"}), 500
        
    return jsonify({
        "success": True,
        "message": f"3-team Blockbuster completed between {user_team.nome}, {team_b.nome} and {team_c.nome}!"
    })

@app.route('/api/trades/execute-4-team', methods=['POST'])
def execute_4_team_trade_endpoint():
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
        
    data = request.get_json() or {}
    raw_data = data.get('raw_trade_data', {})
    flow = raw_data.get('flow', data.get('flow', []))
    
    if not flow or len(flow) < 4:
        return jsonify({"error": "Incomplete 4-team trade data"}), 400
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    teams_dict = {s.nome.lower(): s for s in SIMULATION_TOURNAMENT.squadre}
    team_a_name = raw_data.get('team_a', flow[0]['from'])
    team_b_name = raw_data.get('team_b', flow[1]['from'])
    team_c_name = raw_data.get('team_c', flow[2]['from'])
    team_d_name = raw_data.get('team_d', flow[3]['from'])
    
    team_a = teams_dict.get(team_a_name.lower())
    team_b = teams_dict.get(team_b_name.lower())
    team_c = teams_dict.get(team_c_name.lower())
    team_d = teams_dict.get(team_d_name.lower())
    
    if not (team_a and team_b and team_c and team_d):
        return jsonify({"error": "One or more of the franchises involved were not found"}), 404
        
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, user_team, manual=True)
    
    deal = finder.four_team_deal([team_a, team_b, team_c, team_d], flow)
    if deal is None:
        return jsonify({"error": "Incomplete 4-team trade data"}), 400
    for team in deal.teams:
        if finder._is_user_team(team):
            continue
        accepted, reason = finder.would_accept_trade_with_reason(team, deal.receives(team.nome), deal.gives(team.nome))
        if not accepted:
            return jsonify({"error": f"{team.nome} rejects the trade: {reason}"}), 400

    success = finder.execute_4_team_trade(team_a, team_b, team_c, team_d, flow, reason="4-Team Mega-Blockbuster (User Trade Finder)",
                                          motive=finder.user_motive(deal))
    if not success:
        return jsonify({"error": "Error while executing the 4-team Mega-Blockbuster"}), 500
        
    return jsonify({
        "success": True,
        "message": f"4-team Mega-Blockbuster successfully completed between {team_a.nome}, {team_b.nome}, {team_c.nome} and {team_d.nome}!"
    })

@app.route('/api/trades/search-by-need', methods=['POST'])
def search_trades_by_need():
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400

    data = request.get_json() or {}
    position = data.get('position', 'SF')
    min_ovr = int(data.get('min_ovr', 76))
    archetype = data.get('archetype', None)

    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, user_team, manual=True)
    res = finder.find_trades_by_need(target_position=position, min_ovr=min_ovr, archetype=archetype)
    return jsonify(res)

@app.route('/api/trades/what-would-it-take', methods=['POST'])
def what_would_it_take():
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400

    data = request.get_json() or {}
    player_name = data.get('player_name', '')
    if not player_name:
        return jsonify({"error": "player_name required"}), 400

    target_player = None
    for sq in SIMULATION_TOURNAMENT.squadre:
        for p in sq.roster:
            if p.nome.lower() == player_name.lower():
                target_player = p
                break
        if target_player:
            break

    if not target_player:
        return jsonify({"error": f"Player '{player_name}' not found"}), 404

    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, user_team, manual=True)
    result = finder.calculate_what_would_it_take(target_player)
    return jsonify(result)

@app.route('/api/trades/multi-team-chains', methods=['GET'])
def get_multi_team_chains():
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400

    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, user_team, manual=True)
    chains = finder.find_multi_team_chain_trades()
    return jsonify({"chains": chains})

@app.route('/api/economy/team-multi-year/<team_name>', methods=['GET'])
def get_team_multi_year_economy(team_name: str):
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    sq = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome.lower() == team_name.lower()), None)
    if not sq:
        return jsonify({"error": f"Team '{team_name}' not found"}), 404
        
    return jsonify(build_team_outlook(sq, SIMULATION_TOURNAMENT, CONFIG.ECONOMY))


@app.route('/api/trade-block/toggle', methods=['POST'])
def toggle_trade_block():
    """Toggles on_trade_block status for a player."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    data = request.get_json() or {}
    player_name = data.get("player_name")
    if not player_name:
        return jsonify({"error": "Player name missing"}), 400
        
    player = None
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "User team not set"}), 400
        
    for p in user_team.roster:
        if p.nome.lower() == player_name.lower():
            player = p
            break
            
    if not player:
        return jsonify({"error": f"Player {player_name} not found on the user's team"}), 404
        
    player.on_trade_block = not getattr(player, 'on_trade_block', False)
    return jsonify({
        "success": True,
        "player_name": player.nome,
        "on_trade_block": player.on_trade_block
    })


@app.route('/api/trade-block/offers', methods=['GET'])
def get_trade_block_offers():
    """Returns currently pending trade block offers."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    offers = getattr(SIMULATION_TOURNAMENT, 'pending_trade_block_offers', [])
    return jsonify({
        "offers": offers,
        "count": len(offers)
    })


@app.route('/api/trade-block/generate', methods=['POST'])
def generate_trade_block_offers_endpoint():
    """Manually triggers generation of trade block offers."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    if LEAGUE_STATE != "OFFSEASON_OPTIONS_DECISION":
        closed = trade_window_closed_response()
        if closed:
            return closed
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "User team not set"}), 400
        
    # Check if the state is appropriate
    if LEAGUE_STATE not in ["PRE_SEASON", "OFFSEASON_OPTIONS_DECISION"]:
        return jsonify({"error": "Trade block offers can only be generated in the Pre-Season or during the Options Decision"}), 400
        
    from trades.trade_block_manager import TradeBlockManager
    offers = TradeBlockManager.generate_offers(SIMULATION_TOURNAMENT, user_team)
    SIMULATION_TOURNAMENT.pending_trade_block_offers = offers
    
    return jsonify({
        "success": True,
        "offers": offers,
        "count": len(offers)
    })


@app.route('/api/trade-block/respond', methods=['POST'])
def respond_trade_block_offer():
    """Accepts or declines a pending trade block offer."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    if LEAGUE_STATE != "OFFSEASON_OPTIONS_DECISION":
        closed = trade_window_closed_response()
        if closed:
            return closed
        
    data = request.get_json() or {}
    offer_id = data.get("offer_id")
    action = data.get("action")  # "ACCEPT" or "DECLINE"
    
    if not offer_id or not action:
        return jsonify({"error": "Missing offer_id or action parameters"}), 400
        
    offers = getattr(SIMULATION_TOURNAMENT, 'pending_trade_block_offers', [])
    offer = next((o for o in offers if o["id"] == offer_id), None)
    
    if not offer:
        return jsonify({"error": "Offer not found"}), 404
        
    if action == "DECLINE":
        SIMULATION_TOURNAMENT.pending_trade_block_offers = [o for o in offers if o["id"] != offer_id]
        return jsonify({"success": True, "message": "Offer rejected and removed."})
        
    elif action == "ACCEPT":
        # Let's execute the trade. Resolve player objects and execute swap.
        user_team = SIMULATION_TOURNAMENT.squadra_giocatore
        partner_team_name = offer["offering_team"]
        partner_team = next((t for t in SIMULATION_TOURNAMENT.squadre if t.nome == partner_team_name), None)
        
        if not user_team or not partner_team:
            return jsonify({"error": "Teams involved not found"}), 400
            
        # Find player objects by name
        giving_players = []
        for gp_info in offer["receiving_players"]:
            p = next((x for x in user_team.roster if x.nome == gp_info["name"]), None)
            if not p:
                return jsonify({"error": f"User player {gp_info['name']} not found on the roster"}), 400
            giving_players.append(p)
            
        receiving_players = []
        for rp_info in offer["giving_players"]:
            p = next((x for x in partner_team.roster if x.nome == rp_info["name"]), None)
            if not p:
                return jsonify({"error": f"CPU player {rp_info['name']} not found on the roster"}), 400
            receiving_players.append(p)
            
        giving_picks = offer["receiving_picks"]
        receiving_picks = offer["giving_picks"]
        
        from trades.trade_validator import TradeValidator
        # Double check validity just before execution
        is_valid, err = TradeValidator.validate_trade(
            user_team, partner_team,
            giving_players + giving_picks,
            receiving_players + receiving_picks,
            torneo=SIMULATION_TOURNAMENT
        )
        if not is_valid:
            return jsonify({"error": f"Trade no longer valid: {err}"}), 400
            
        # The CPU answers the same two questions as for any trade (the offer may have gone stale), then the one executor
        from trades.trade_finder import TradeFinder
        finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, user_team)
        accepted, reason = finder.would_accept_trade_with_reason(partner_team, giving_players + giving_picks,
                                                                 receiving_players + receiving_picks)
        if not accepted:
            return jsonify({"error": f"The partner team rejects the trade: {reason}"}), 400
        deal = finder.pair_deal(user_team, partner_team, giving_players + giving_picks,
                                receiving_players + receiving_picks, reason="Trade Block")
        if not finder.execute_deal(deal, motive=finder.user_motive(deal)):
            return jsonify({"error": "Error while executing the trade"}), 500

        # Clean pending offers list
        SIMULATION_TOURNAMENT.pending_trade_block_offers = []
        
        return jsonify({
            "success": True,
            "message": "Trade executed successfully!",
            "payload": get_full_league_data_payload()
        })
        
    return jsonify({"error": "Invalid action"}), 400


@app.route('/api/tradeable-players', methods=['GET'])
def get_tradeable_players_list():
    """
    Returns players on the user's controlled team that can be traded.
    """
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"players": [], "count": 0})
        
    players = []
    for p in user_team.roster:
        if p.contract:
            players.append({
                "name": p.nome,
                "ovr": p.ovr,
                "team": user_team.nome,
                "position": p.ruolo,
                "salary": p.contract.salario_annuale
            })
            
    # Sort by ovr desc
    players.sort(key=lambda x: x['ovr'], reverse=True)
    
    # Picks owned by this team
    picks = []
    season_num = getattr(SIMULATION_TOURNAMENT, 'season_number', 1)
    starting_year = getattr(SIMULATION_TOURNAMENT, 'starting_year', 2025)
    for year in range(1, 6):
        draft_cal_year = starting_year + season_num + year - 1
        for pick_key, owner in SIMULATION_TOURNAMENT.pick_ownership.get(year, {}).items():
            if owner == user_team.nome:
                prot = SIMULATION_TOURNAMENT.pick_protections.get(year, {}).get(pick_key, "Unprotected")
                display_str = f"Draft {draft_cal_year} - {pick_key}"
                if prot != "Unprotected":
                    display_str += f" ({prot})"
                picks.append({
                    "year": year,
                    "key": f"{year}:{pick_key}",
                    "display_name": display_str,
                    "protection": prot
                })
                
    return jsonify({
        "players": players,
        "picks": picks,
        "count": len(players) + len(picks)
    })



@app.route('/api/user-trade-info', methods=['GET'])
def get_user_trade_info():
    """
    Returns assets (players & draft picks) for the player's team and the selected partner team.
    Also returns whether the trade window is open.
    Query param: partner_team (string)
    """
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    player_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not player_team:
        return jsonify({"error": "No team selected by the player"}), 400
    
    partner_team_name = request.args.get('partner_team', '')
    partner_team = None
    if partner_team_name:
        for s in SIMULATION_TOURNAMENT.squadre:
            if s.nome.lower() == partner_team_name.lower():
                partner_team = s
                break
            
    # Check if trade window is open
    trade_window_open, trade_window_message = user_trade_window(SIMULATION_TOURNAMENT, LEAGUE_STATE)
    
    from trades.execution import can_set_pick_protection

    def serialize_team_assets(team):
        if not team:
            return {"players": [], "picks": []}
            
        # Players
        players_data = []
        for p in team.roster:
            if p.contract:
                players_data.append({
                    "name": p.nome,
                    "nome": p.nome,
                    "position": p.ruolo,
                    "ruolo": p.ruolo,
                    "age": p.eta,
                    "eta": p.eta,
                    "ovr": p.ovr,
                    "potential": p.potenziale,
                    "potenziale": p.potenziale,
                    "salary": p.contract.salario_annuale,
                    "salario": p.contract.salario_annuale,
                    "contract_years": p.contract.anni_rimanenti,
                    "anni_rimanenti": p.contract.anni_rimanenti,
                    "trade_value": round(p.trade_value, 1) if hasattr(p, 'trade_value') else p.ovr,
                    "on_trade_block": getattr(p, 'on_trade_block', False)
                })
        # Sort players by OVR desc
        players_data.sort(key=lambda x: x['ovr'], reverse=True)
        
        # Picks owned by this team
        picks_data = []
        active_draft = ACTIVE_DRAFT_INSTANCE
        season_num = getattr(SIMULATION_TOURNAMENT, 'season_number', 1)
        starting_year = getattr(SIMULATION_TOURNAMENT, 'starting_year', 2025)
        
        for year in range(1, 6):
            draft_cal_year = starting_year + season_num + year - 1
            for pick_key, owner in SIMULATION_TOURNAMENT.pick_ownership.get(year, {}).items():
                if owner == team.nome:
                    if active_draft and getattr(active_draft, 'pick_corrente', 0) > 0 and year == 1:
                        already_picked = False
                        for item in active_draft.get_draft_state().get("ordine", []):
                            item_key = f"R{item['round']}-{item['original_owner']}"
                            if item_key == pick_key and item['pick_index'] < active_draft.pick_corrente:
                                already_picked = True
                                break
                        if already_picked:
                            continue
                            
                    prot = SIMULATION_TOURNAMENT.pick_protections.get(year, {}).get(pick_key, "Unprotected")
                    orig_team = pick_key.split("-", 1)[1] if "-" in pick_key else pick_key
                    
                    if year == 1:
                        if hasattr(SIMULATION_TOURNAMENT, 'draft_lottery_order') and SIMULATION_TOURNAMENT.draft_lottery_order and orig_team in SIMULATION_TOURNAMENT.draft_lottery_order and pick_key.startswith("R1"):
                            pick_pos = SIMULATION_TOURNAMENT.draft_lottery_order.index(orig_team) + 1
                            display_str = f"Draft {draft_cal_year} (#{pick_pos}) - {pick_key}"
                        else:
                            display_str = f"Draft {draft_cal_year} - {pick_key}"
                    else:
                        display_str = f"Draft {draft_cal_year} - {pick_key}"
                        
                    if prot != "Unprotected":
                        display_str += f" ({prot})"
                        
                    picks_data.append({
                        "year": year,
                        "key": f"{year}:{pick_key}",
                        "display_name": display_str,
                        "protection": prot,
                        "can_protect": can_set_pick_protection(SIMULATION_TOURNAMENT, f"{year}:{pick_key}", team.nome)
                    })
        return {"players": players_data, "picks": picks_data}
        
    res = {
        "player_team_name": player_team.nome,
        "partner_team_name": partner_team.nome if partner_team else "",
        "trade_window_open": trade_window_open,
        "trade_window_message": trade_window_message,
        "league_state": LEAGUE_STATE,
        "pick_protection_options": list(CONFIG.TRADES.PICK_PROTECTIONS),
        "player_team_assets": serialize_team_assets(player_team),
        "partner_team_assets": serialize_team_assets(partner_team) if partner_team else {"players": [], "picks": []}
    }
    return jsonify(res)


@app.route('/api/team-strategy-intel', methods=['GET'])
def get_team_strategy_intel():
    """
    Returns GM Strategy, Market Intel, Positional Needs, Untouchables & Trade Block
    for any team in the league.
    """
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    team_name = request.args.get('team_name', '')
    team = None
    if team_name:
        team = next((t for t in SIMULATION_TOURNAMENT.squadre if t.nome.lower() == team_name.lower()), None)
    if not team:
        team = SIMULATION_TOURNAMENT.squadra_giocatore or SIMULATION_TOURNAMENT.squadre[0]

    from trades.trade_finder import TradeFinder
    tf = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore)
    
    stato_squadra = SIMULATION_TOURNAMENT._determina_stato_squadra(team)
    strategy_type = tf.get_team_strategy(team)
    owner_personality = getattr(team, 'personalita_proprietario', 'Bilanciato')
    
    # Narrative direction & description
    if stato_squadra == "Defending Champion":
        direction_title = "Title Defense & All-In"
        direction_desc = "Defending champions: the front office is ready to sacrifice future picks for veterans with immediate impact and keep the title window open."
    elif stato_squadra == "Contender":
        direction_title = "Title Hunt (Win-Now)"
        direction_desc = "Title window open: the franchise is looking for the missing piece (high-level starters) and is willing to give up picks or young prospects."
    elif stato_squadra == "Playoff Team":
        direction_title = "Playoff Competitiveness & Targeted Upgrades"
        direction_desc = "Solid playoff team: looks for even trades to fill positional gaps and avoid toxic contracts."
    elif stato_squadra == "Rising Star":
        direction_title = "Young Core Development & Future"
        direction_desc = "Young, promising core: the front office protects the young talents, looks for complementary players and accumulates draft capital."
    elif stato_squadra == "Aging Core":
        direction_title = "Last Run / Imminent Restructuring"
        direction_desc = "Declining veteran core: weighs whether to attempt one last run or move the heavy contracts before they lose value."
    elif stato_squadra == "Rebuilding":
        direction_title = "Full Rebuild & Draft Asset Accumulation"
        direction_desc = "Open rebuild: the franchise evaluates offers for veterans, absorbs salary for draft picks, and builds through the draft."
    else:
        direction_title = "Transition / Evaluation Phase"
        direction_desc = "Middle-tier franchise: front office evaluates standings to decide whether to sell veterans or push for a playoff berth."

    # Positional Needs
    needs_list = tf._get_team_positional_needs(team)
    primary_need = needs_list[0] if needs_list else "PG"
    secondary_need = needs_list[1] if len(needs_list) > 1 else "C"
    surplus_role = needs_list[-1] if needs_list else "SG"

    # Role details breakdown
    role_breakdown = {}
    for r in ["PG", "SG", "SF", "PF", "C"]:
        players_at_r = [p for p in team.roster if p.ruolo == r]
        avg_ovr = round(sum(p.ovr for p in players_at_r) / len(players_at_r), 1) if players_at_r else 0
        best_p = max(players_at_r, key=lambda p: p.ovr) if players_at_r else None
        role_breakdown[r] = {
            "count": len(players_at_r),
            "avg_ovr": avg_ovr,
            "best_player": f"{best_p.nome} ({best_p.ovr})" if best_p else "None",
            "is_urgent_need": (r == primary_need),
            "is_need": (r in [primary_need, secondary_need]),
            "is_surplus": (r == surplus_role and len(players_at_r) >= 3)
        }

    # 3-Tier Classification System:
    # Tier 1: untouchables (Franchise Cornerstones & Core)
    # Tier 2: key_starters (Key Starters / Super-Offers Only)
    # Tier 3: trade_block (Active Trade Block & Surplus)
    untouchables = []
    key_starters = []
    trade_block = []

    sorted_roster = sorted(team.roster, key=lambda x: x.ovr, reverse=True)
    is_rebuilder_state = stato_squadra in ["Rebuilding", "Rising Star"] or strategy_type == "REBUILDER"
    
    # Top player by role
    top_player_by_role = {}
    for r in ["PG", "SG", "SF", "PF", "C"]:
        players_at_r = [p for p in team.roster if p.ruolo == r]
        if players_at_r:
            top_player_by_role[r] = max(players_at_r, key=lambda p: p.ovr)

    # Top 2 overall players on the team
    top_2_names = {p.nome for p in sorted_roster[:2]}

    for p in sorted_roster:
        p_info = {
            "nome": p.nome,
            "ruolo": p.ruolo,
            "ovr": p.ovr,
            "potenziale": p.potenziale,
            "eta": p.eta,
            "salario": p.contract.salario_annuale if p.contract else getattr(p, 'salario', 0),
            "anni": p.contract.anni_rimanenti if p.contract else getattr(p, 'contract_years', 1),
            "trade_value": round(float(p.trade_value), 1),
            "on_trade_block": getattr(p, 'on_trade_block', False),
            "tag": ""
        }

        # 1. EXPLICIT TRADE BLOCK or DEMANDING TRADE -> Tier 3
        if getattr(p, 'on_trade_block', False):
            p_info["tag"] = "On the Trade Block"
            trade_block.append(p_info)
            continue
        if getattr(p, 'trade_request', False):
            p_info["tag"] = "Asked for a trade"
            trade_block.append(p_info)
            continue
        if asked_out(p) or getattr(p, 'morale', 75) < 35:
            p_info["tag"] = "Unhappy / Sell"
            trade_block.append(p_info)
            continue

        # 2. TIER 1: UNBREAKABLE PILLARS & CORE OF THE FUTURE
        is_tier_1 = getattr(p, 'is_untouchable', False)
        tag_1 = "Untouchable"

        if not is_tier_1:
            if p.ovr >= 85:
                is_tier_1 = True
                tag_1 = "Franchise Superstar"
            elif p.nome in top_2_names and p.ovr >= 80:
                is_tier_1 = True
                tag_1 = "Roster Cornerstone"
            elif p.ovr >= 82 and p == top_player_by_role.get(p.ruolo):
                is_tier_1 = True
                tag_1 = "Untouchable Starter"

        # Young High-Upside Talents & Core of the Future
        if not is_tier_1:
            if is_rebuilder_state:
                if (p.eta <= 23 and (p.potenziale >= 78 or p.ovr >= 73)) or (p.eta <= 21):
                    is_tier_1 = True
                    tag_1 = "Rebuild Future"
                elif p.eta <= 24 and p.potenziale >= 82:
                    is_tier_1 = True
                    tag_1 = "Young Prospect"
            else:
                if p.eta <= 22 and p.potenziale >= 83:
                    is_tier_1 = True
                    tag_1 = "Rising Star"
                elif p.eta <= 24 and p.potenziale >= 86:
                    is_tier_1 = True
                    tag_1 = "Talent to Develop"

        if is_tier_1:
            p_info["tag"] = tag_1
            untouchables.append(p_info)
            continue

        # 3. TIER 3: EXPLICIT SURPLUS / REBUILDING VETERAN MISMATCH / DEEP BENCH
        # Rebuilding team veteran
        if is_rebuilder_state and p.eta >= 28 and p.ovr <= 82:
            p_info["tag"] = "Veteran for Picks"
            trade_block.append(p_info)
            continue

        # Role Surplus
        players_at_r = [x for x in sorted_roster if x.ruolo == p.ruolo]
        rank_at_r = players_at_r.index(p) + 1 if p in players_at_r else 1
        if rank_at_r >= 3 and p.ruolo == surplus_role and p.ovr <= 77:
            p_info["tag"] = f"Surplus {p.ruolo} (#{rank_at_r})"
            trade_block.append(p_info)
            continue

        # Deep bench scrub
        if p.ovr <= 71 and p.eta >= 25:
            p_info["tag"] = "End of the Bench"
            trade_block.append(p_info)
            continue

        # 4. TIER 2: KEY STARTERS / TRADEABLE ONLY FOR SUPER-OFFERS ("The middle ground")
        if p == top_player_by_role.get(p.ruolo):
            p_info["tag"] = f"{p.ruolo} Starter"
        elif rank_at_r == 2 and p.ovr >= 74:
            p_info["tag"] = f"Sixth Man / {p.ruolo} Rotation"
        elif p.ovr >= 75:
            p_info["tag"] = "Primary Rotation"
        elif p.eta <= 24:
            p_info["tag"] = "Rotation Youngster"
        else:
            p_info["tag"] = "Specialist"

        key_starters.append(p_info)

    # Draft Picks Owned
    picks_owned = []
    for y in range(1, 6):
        for pk, owner in SIMULATION_TOURNAMENT.pick_ownership.get(y, {}).items():
            if owner == team.nome:
                prot = SIMULATION_TOURNAMENT.pick_protections.get(y, {}).get(pk, "Unprotected")
                picks_owned.append({
                    "year": y,
                    "pick": pk,
                    "protection": prot
                })
                
    firsts_count = sum(1 for p in picks_owned if "R1" in p['pick'])
    seconds_count = sum(1 for p in picks_owned if "R2" in p['pick'])
    
    cap = getattr(SIMULATION_TOURNAMENT, 'salary_cap', 155.0)
    tax = getattr(SIMULATION_TOURNAMENT, 'luxury_tax_threshold', 185.0)
    floor = getattr(SIMULATION_TOURNAMENT, 'salary_floor', cap * 0.90)

    return jsonify({
        "team_name": team.nome,
        "team_state": stato_squadra,
        "strategy_type": strategy_type,
        "owner_personality": owner_personality,
        "direction_title": direction_title,
        "direction_description": direction_desc,
        "primary_need": primary_need,
        "secondary_need": secondary_need,
        "surplus_role": surplus_role,
        "needs_ranked": needs_list,
        "role_breakdown": role_breakdown,
        "untouchables": untouchables,
        "key_starters": key_starters,
        "trade_block": trade_block,
        "tradeables": trade_block,
        "financials": {
            "payroll": round(team.payroll, 1),
            "salary_cap": round(cap, 1),
            "salary_cap_space": round(team.salary_cap_space, 1),
            "luxury_tax_threshold": round(tax, 1),
            "is_taxpayer": team.payroll > tax,
            "salary_floor": round(floor, 1),
            "is_below_floor": team.payroll < floor,
            "floor_deficit": round(max(0.0, floor - team.payroll), 1)
        },
        "draft_capital": {
            "firsts_count": firsts_count,
            "seconds_count": seconds_count,
            "total_picks": len(picks_owned),
            "picks": picks_owned
        }
    })


def user_deal_pick_terms(user_team, partner_team, data: dict) -> dict:
    """The protection each pick of a 2-team user deal carries, from what the request asks for."""
    from trades.execution import settle_pick_terms
    return settle_pick_terms(SIMULATION_TOURNAMENT, [
        (user_team.nome, data.get('giving_picks', []), data.get('giving_pick_protections') or {}),
        (partner_team.nome, data.get('receiving_picks', []), data.get('receiving_pick_protections') or {})])


@app.route('/api/validate-user-trade', methods=['POST'])
def validate_user_trade():
    """
    Validates a proposed user trade and evaluates AI acceptance in real-time.
    """
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
    
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected by the player"}), 400
        
    data = request.get_json()
    partner_team_name = data.get('partner_team', '')
    giving_player_names = data.get('giving_players', [])
    giving_pick_keys = data.get('giving_picks', [])
    receiving_player_names = data.get('receiving_players', [])
    receiving_pick_keys = data.get('receiving_picks', [])
    
    partner_team = None
    for s in SIMULATION_TOURNAMENT.squadre:
        if s.nome.lower() == partner_team_name.lower():
            partner_team = s
            break
            
    if not partner_team:
        return jsonify({"error": f"Partner team '{partner_team_name}' not found"}), 400
    all_pick_protections = user_deal_pick_terms(user_team, partner_team, data)
        
    # Resolve player objects
    user_players = []
    for name in giving_player_names:
        found = False
        for p in user_team.roster:
            if p.nome.lower() == name.lower():
                user_players.append(p)
                found = True
                break
        if not found:
            return jsonify({"error": f"Player '{name}' not found on your team"}), 400
            
    partner_players = []
    for name in receiving_player_names:
        found = False
        for p in partner_team.roster:
            if p.nome.lower() == name.lower():
                partner_players.append(p)
                found = True
                break
        if not found:
            return jsonify({"error": f"Player '{name}' not found on the partner team"}), 400
            
    assets_a_gives = user_players + giving_pick_keys
    assets_b_gives = partner_players + receiving_pick_keys
    
    from trades.trade_validator import TradeValidator
    is_valid, validation_msg = TradeValidator.validate_trade(
        user_team, partner_team, assets_a_gives, assets_b_gives, torneo=SIMULATION_TOURNAMENT
    )
    
    ai_accepted = False
    ai_reason = "Trade rules invalid"
    why = ""

    if is_valid:
        from trades.trade_finder import TradeFinder
        finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore, manual=True)
        # Partner team (B) receives user gives (A) and gives partner gives (B)
        ai_accepted, ai_reason = finder.would_accept_trade_with_reason(partner_team, assets_a_gives, assets_b_gives, pick_protections=all_pick_protections)
        if ai_accepted:
            why = finder.user_motive(finder.pair_deal(user_team, partner_team, assets_a_gives, assets_b_gives)).why

    return jsonify({
        "is_valid": is_valid,
        "validation_message": validation_msg,
        "ai_accepted": ai_accepted,
        "ai_reason": ai_reason,
        "why": why
    })


@app.route('/api/counter-offer-trade', methods=['POST'])
def counter_offer_trade():
    """
    Generates a CPU GM counter-offer for a proposed user trade.
    """
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected by the player"}), 400
        
    data = request.get_json() or {}
    partner_team_name = data.get('partner_team', '')
    giving_player_names = data.get('giving_players', [])
    giving_pick_keys = data.get('giving_picks', [])
    receiving_player_names = data.get('receiving_players', [])
    receiving_pick_keys = data.get('receiving_picks', [])
    
    partner_team = None
    for s in SIMULATION_TOURNAMENT.squadre:
        if s.nome.lower() == partner_team_name.lower():
            partner_team = s
            break
            
    if not partner_team:
        return jsonify({"error": f"Partner team '{partner_team_name}' not found"}), 400
    all_pick_protections = user_deal_pick_terms(user_team, partner_team, data)
        
    user_players = [p for name in giving_player_names for p in user_team.roster if p.nome.lower() == name.lower()]
    partner_players = [p for name in receiving_player_names for p in partner_team.roster if p.nome.lower() == name.lower()]
    
    assets_a_gives = user_players + giving_pick_keys
    assets_b_gives = partner_players + receiving_pick_keys
    
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore, manual=True)
    counter_res = finder.generate_counter_offer(partner_team, user_team, assets_a_gives, assets_b_gives, pick_protections=all_pick_protections)
    
    return jsonify(counter_res)


@app.route('/api/execute-user-trade', methods=['POST'])
def execute_user_trade():
    """
    Executes a proposed user trade after performing final validation checks.
    """
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    closed = trade_window_closed_response()
    if closed:
        return closed
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    data = request.get_json()
    partner_team_name = data.get('partner_team', '')
    giving_player_names = data.get('giving_players', [])
    giving_pick_keys = data.get('giving_picks', [])
    receiving_player_names = data.get('receiving_players', [])
    receiving_pick_keys = data.get('receiving_picks', [])
    
    partner_team = None
    for s in SIMULATION_TOURNAMENT.squadre:
        if s.nome.lower() == partner_team_name.lower():
            partner_team = s
            break
            
    if not partner_team:
        return jsonify({"error": f"Partner team '{partner_team_name}' not found"}), 400
    all_pick_protections = user_deal_pick_terms(user_team, partner_team, data)
        
    # Resolve player objects
    user_players = []
    for name in giving_player_names:
        found = False
        for p in user_team.roster:
            if p.nome.lower() == name.lower():
                user_players.append(p)
                found = True
                break
        if not found:
            return jsonify({"error": f"Player '{name}' not found on your team"}), 400
            
    partner_players = []
    for name in receiving_player_names:
        found = False
        for p in partner_team.roster:
            if p.nome.lower() == name.lower():
                partner_players.append(p)
                found = True
                break
        if not found:
            return jsonify({"error": f"Player '{name}' not found on the partner team"}), 400
            
    assets_a_gives = user_players + giving_pick_keys
    assets_b_gives = partner_players + receiving_pick_keys
    
    from trades.trade_validator import TradeValidator
    is_valid, validation_msg = TradeValidator.validate_trade(
        user_team, partner_team, assets_a_gives, assets_b_gives, torneo=SIMULATION_TOURNAMENT
    )
    if not is_valid:
        return jsonify({"error": f"Trade rules not met: {validation_msg}"}), 400
        
    from trades.trade_finder import TradeFinder
    finder = TradeFinder(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre, SIMULATION_TOURNAMENT.squadra_giocatore, manual=True)
    
    ai_accepted, ai_reason = finder.would_accept_trade_with_reason(partner_team, assets_a_gives, assets_b_gives, pick_protections=all_pick_protections)
    if not ai_accepted:
        return jsonify({"error": f"The partner team rejects the trade: {ai_reason}"}), 400
        
    motive = finder.user_motive(finder.pair_deal(user_team, partner_team, assets_a_gives, assets_b_gives))
    success = finder.execute_trade(user_team, partner_team, assets_a_gives, assets_b_gives, reason="User Trade",
                                   pick_protections=all_pick_protections, motive=motive)
    if not success:
        return jsonify({"error": "Error while executing the trade in the database"}), 500
        
    # Generate news article so it shows up in the news feed
    trade_desc = f"{user_team.nome} and {partner_team.nome} have completed a trade. "
    
    user_gives_picks_desc = []
    for k in giving_pick_keys:
        prot = all_pick_protections.get(k, "Unprotected")
        user_gives_picks_desc.append(f"{k} ({prot})" if prot != "Unprotected" else k)
        
    partner_gives_picks_desc = []
    for k in receiving_pick_keys:
        prot = all_pick_protections.get(k, "Unprotected")
        partner_gives_picks_desc.append(f"{k} ({prot})" if prot != "Unprotected" else k)
        
    user_gives_str = ", ".join([p.nome for p in user_players] + user_gives_picks_desc)
    partner_gives_str = ", ".join([p.nome for p in partner_players] + partner_gives_picks_desc)
    trade_desc += f"{user_team.nome} send: [{user_gives_str}] | {partner_team.nome} send: [{partner_gives_str}]."
    generate_trade_news(trade_desc, [user_team.nome, partner_team.nome])
    
    # Save mid-season log or offseason log depending on state
    if LEAGUE_STATE == "OFFSEASON_TRADES_START":
        if 'scambi' not in SIMULATION_TOURNAMENT.offseason_log_data:
            SIMULATION_TOURNAMENT.offseason_log_data['scambi'] = []
        SIMULATION_TOURNAMENT.offseason_log_data['scambi'].append(finder.logscambi[-1] if finder.logscambi else trade_desc)
    else:
        if 'scambi_midseason' not in SIMULATION_TOURNAMENT.offseason_log_data:
            SIMULATION_TOURNAMENT.offseason_log_data['scambi_midseason'] = []
        SIMULATION_TOURNAMENT.offseason_log_data['scambi_midseason'].append(finder.logscambi[-1] if finder.logscambi else trade_desc)

    # Board Approval & Achievement Triggers for Trades
    try:
        gm_prof = getattr(SIMULATION_TOURNAMENT, 'user_gm_profile', None)
        if not gm_prof:
            gm_prof = init_user_gm_profile(user_team.nome)
            SIMULATION_TOURNAMENT.user_gm_profile = gm_prof

        max_acquired_ovr = max([p.ovr for p in partner_players], default=0)
        sal_in = sum(p.contract.salario_annuale for p in partner_players if p.contract)
        sal_out = sum(p.contract.salario_annuale for p in user_players if p.contract)
        added_salary = sal_in - sal_out

        update_approval_rating(user_team, gm_prof, "trade_executed", {
            "added_salary": added_salary,
            "star_acquired": max_acquired_ovr >= 88
        })

        if max_acquired_ovr >= 90:
            check_gm_achievements(gm_prof, SIMULATION_TOURNAMENT, {"acquired_ovr": max_acquired_ovr})
    except Exception as e:
        print(f"Error updating board/achievements on trade: {e}")

    return jsonify({
        "success": True,
        "message": "Trade completed successfully!"
    })


# =============================================================================
# ### TEAM MANAGER ENDPOINTS ###
# =============================================================================

@app.route('/api/team-manager/info', methods=['GET'])
def get_team_manager_info():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    roster_data = []
    for p in user_team.roster:
        roster_data.append({
            "nome": p.nome,
            "ruolo": p.ruolo,
            "ovr": p.ovr,
            "potenziale": p.potenziale,
            "eta": p.eta,
            "minuti_target": p.minuti_target,
            "infortunato": p.infortunato,
            "giorni_infortunio_rimanenti": getattr(p, 'giorni_infortunio_rimanenti', 0),
            "is_star": p.is_star(),
            "valutazioni_posizionali": getattr(p, 'valutazioni_posizionali', {}),
            "ruolo_originale": getattr(p, 'ruolo_originale', None),
            "ovr_if_role": {r: p.ovr_at_role(r) for r in ROLES},   # OVR after a role change (capped)
        })
        
    coach_data = None
    if user_team.coach:
        c = user_team.coach
        coach_data = {
            "nome": c.nome,
            "stile_gioco": c.stile_gioco,
            "ovr_offensivo": c.ovr_offensivo,
            "ovr_difensivo": c.ovr_difensivo,
            "ovr_totale": c.ovr_totale,
            "eta": c.eta,
            "contratto_anni_rimanenti": c.contratto_anni_rimanenti
        }
        
    # Get all coaching styles
    from core.config import CONFIG
    styles_data = []
    for style_name, style_info in CONFIG.COACHINGSTYLES.STYLES.items():
        styles_data.append({
            "name": style_name,
            "descrizione": style_info.get("descrizione", "")
        })
        
    tp = getattr(user_team, 'tactical_plan', None)
    tactical_plan_data = {
        "pnr_coverage": tp.pnr_coverage if tp else "DROP",
        "defensive_scheme": tp.defensive_scheme if tp else "MAN_TO_MAN",
        "offensive_focus": tp.offensive_focus if tp else "BALANCED",
        "pace_preference": tp.pace_preference if tp else "BALANCED",
        "stagger_stars": tp.stagger_stars if tp else False,
        "offensive_first_option": getattr(tp, 'offensive_first_option', None) if tp else None,
        "offensive_second_option": getattr(tp, 'offensive_second_option', None) if tp else None,
        "offensive_third_option": getattr(tp, 'offensive_third_option', None) if tp else None,
        "player_touch_modifiers": getattr(tp, 'player_touch_modifiers', {}) if tp else {}
    }

    return jsonify({
        "success": True,
        "team_name": user_team.nome,
        "intesa": getattr(user_team, 'intesa', 70),
        "roster": roster_data,
        "coach": coach_data,
        "coach_styles": styles_data,
        "user_custom_lineup": getattr(user_team, 'user_custom_lineup', {}),
        "active_poe": getattr(user_team, 'active_poe', 'Balanced Approach'),
        "tactical_plan": tactical_plan_data
    })


def _court_positions(team) -> dict:
    """Healthy starter at each position, as the engine picks it at tip-off (leftover court positions from the
    last game can be anything), else the best healthy player by role."""
    try:
        team.scegli_quintetto_iniziale()
    except Exception as e:
        print(f"WARNING: could not pick the starting five of {team.nome}: {e}")
    current = getattr(team, 'posizione_in_campo', {}) or {}
    positions, used = {}, set()
    for pos in ['PG', 'SG', 'SF', 'PF', 'C']:
        p = current.get(pos)
        if p is not None and p in team.roster and not p.infortunato and p.nome not in used:
            positions[pos] = p
            used.add(p.nome)
    for pos in ['PG', 'SG', 'SF', 'PF', 'C']:
        if pos in positions:
            continue
        candidates = [p for p in team.roster if not p.infortunato and p.nome not in used]
        same_role = [p for p in candidates if normalize_role(p.ruolo) == pos]
        pool = same_role or candidates
        if pool:
            best = max(pool, key=lambda p: (p.minuti_target, p.ovr))
            positions[pos] = best
            used.add(best.nome)
    return positions


def _user_series_opponent(torneo, user_team):
    """(opponent team, series context) of the user's unfinished playoff series, or (None, None)."""
    from core.scouting_matchups import series_opponent
    found = series_opponent(user_team.nome, PLAYOFF_SERIES, getattr(torneo, 'active_playoff_series', None),
                            getattr(torneo, 'playoff_bracket_data', None))
    opp = next((t for t in torneo.squadre if found and t.nome == found["opponent"]), None)
    if not opp:
        return None, None
    return opp, {"kind": "series", "round": found["round"], "user_wins": found["user_wins"],
                 "opp_wins": found["opp_wins"], "game_number": found["user_wins"] + found["opp_wins"] + 1}


@app.route('/api/team-manager/opponent', methods=['GET'])
def get_opponent_scouting():
    """Opponent tab: the next (or chosen) opponent, their threats against our defense and our plan for them."""
    from core.dashboard_summary import build_standings, next_game
    from core.scouting_matchups import TENDENCY_OF, build_report, skills_of
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    torneo = SIMULATION_TOURNAMENT
    user_team = torneo.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400

    cfg = CONFIG.SCOUTING_MATCHUPS
    teams_by_name = {t.nome: t for t in torneo.squadre if t is not user_team}
    payload = {
        "team": None, "context": None, "teams": sorted(teams_by_name),
        "report": [], "their_players": [], "my_players": [], "plan": {"matchups": {}, "double_teams": []},
        "config": {k: getattr(cfg, k) for k in ("BAD_GAP", "WATCH_GAP", "GAP_WEIGHT", "TENDENCY_BASE", "TENDENCY_SPAN")},
    }

    requested = request.args.get('team')
    opp, context = _user_series_opponent(torneo, user_team)
    if requested:
        if requested not in teams_by_name:
            return jsonify({"error": f"Unknown team '{requested}'"}), 400
        if not opp or opp.nome != requested:
            opp, context = teams_by_name[requested], None
    if not opp:
        nxt = next_game(getattr(torneo, 'calendario', None), getattr(torneo, '_current_gameday', 0), user_team.nome)
        if nxt and nxt["opponent"] in teams_by_name:
            opp = teams_by_name[nxt["opponent"]]
            context = {"kind": "game", "date": nxt["date"], "is_home": nxt["is_home"]}
    if not opp:
        return jsonify(payload)
    if context is None:
        # A team picked by hand: show the next game against them if there is one
        for day in getattr(torneo, 'calendario', None) or []:
            if day.day_index < getattr(torneo, '_current_gameday', 0):
                continue
            g = next((g for g in day.games if not g.played and {g.home_team, g.away_team} == {user_team.nome, opp.nome}), None)
            if g:
                context = {"kind": "game", "date": g.date, "is_home": g.home_team == user_team.nome}
                break

    standings = build_standings(torneo, CONFIG.DASHBOARD)
    record = next(((conf, row) for conf in ("east", "west") for row in standings[conf] if row["nome"] == opp.nome), (None, None))
    payload["team"] = {
        "name": opp.nome,
        "record": f"{opp.vittorie}-{opp.sconfitte}",
        "conference": {"east": "East", "west": "West"}.get(record[0]),
        "rank": record[1]["pos"] if record[1] else None,
    }

    their_positions = _court_positions(opp)
    pos_of = {p.nome: pos for pos, p in their_positions.items()}
    rotation = sorted([p for p in opp.roster if not p.infortunato and p.minuti_target > 0], key=lambda p: -p.minuti_target)
    for p in their_positions.values():
        if p not in rotation:
            rotation.append(p)
    their_rotation = [(p, pos_of.get(p.nome)) for p in rotation]

    my_positions = _court_positions(user_team)
    plan = user_team.tactical_plan.plan_vs(opp.nome) if getattr(user_team, 'tactical_plan', None) else {"matchups": {}, "double_teams": []}
    payload["plan"] = plan
    payload["report"] = build_report(their_rotation, user_team.roster, my_positions, plan, cfg)
    payload["their_players"] = [{
        "name": p.nome, "pos": pos, "ruolo": normalize_role(p.ruolo), "minutes": p.minuti_target,
        "skills": skills_of(p),
        "tendencies": {k: getattr(p.tendenze, attr, 50) for k, attr in TENDENCY_OF.items()},
        "auto_defender": my_positions[pos or normalize_role(p.ruolo)].nome if my_positions.get(pos or normalize_role(p.ruolo)) else None,
    } for p, pos in their_rotation]
    payload["my_players"] = [{
        "name": p.nome, "ruolo": normalize_role(p.ruolo), "minutes": p.minuti_target, "injured": p.infortunato,
        "per_d": p.abilita.perimeter_defense_rating, "int_d": p.abilita.interior_defense_rating,
    } for p in user_team.roster]  # roster order, so ties in the fix pick the same player as build_report
    payload["context"] = context
    return jsonify(payload)


@app.route('/api/team-manager/opponent-plan', methods=['POST'])
def save_opponent_plan():
    """Stores the matchups and double-teams for one opponent. Names not on the two rosters are dropped."""
    from core.models import TacticalPlan
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
    data = request.get_json() or {}
    opp = next((t for t in SIMULATION_TOURNAMENT.squadre if t.nome == data.get("team") and t is not user_team), None)
    if not opp:
        return jsonify({"error": f"Unknown team '{data.get('team')}'"}), 400

    theirs = {p.nome for p in opp.roster}
    mine = {p.nome for p in user_team.roster}
    plan = {
        "matchups": {t: d for t, d in (data.get("matchups") or {}).items() if t in theirs and d in mine},
        "double_teams": [n for n in dict.fromkeys(data.get("double_teams") or []) if n in theirs],
    }
    if not getattr(user_team, 'tactical_plan', None):
        user_team.tactical_plan = TacticalPlan()
    user_team.tactical_plan.opponent_plans[opp.nome] = plan
    auto_save_active_game()
    return jsonify({"success": True, "plan": plan})


@app.route('/api/team-manager/extensions', methods=['GET'])
def get_team_extensions():
    global SIMULATION_TOURNAMENT, NEGOTIATION_ATTEMPTS
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    from offseason.contract_extensions import ContractExtensions
    ext_engine = ContractExtensions(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre)

    expiring_players = []
    for p in user_team.roster:
        if p.contract and p.contract.anni_rimanenti == 1:
            option_type = "None"
            if p.contract.player_option:
                option_type = "Player"
            elif p.contract.team_option:
                option_type = "Team"
                
            market_val = ext_engine.compute_player_market_request(p, option_type="None")
            attempts = NEGOTIATION_ATTEMPTS.get(p.nome, 0)
            
            expiring_players.append({
                "nome": p.nome,
                "ruolo": p.ruolo,
                "ovr": p.ovr,
                "potenziale": p.potenziale,
                "eta": p.eta,
                "salario_attuale": p.contract.salario_annuale,
                "option_type": option_type,
                "valore_mercato": round(market_val, 1),
                "willingness": p.get_willingness_tier(),
                "willingness_score": round(p.get_extension_willingness(), 1),
                "willingness_breakdown": p.get_extension_willingness_breakdown(),
                "attempts": attempts,
                "is_closed": attempts >= 3
            })
            
    return jsonify({
        "success": True,
        "salary_cap": SIMULATION_TOURNAMENT.salary_cap,
        "min_salary": getattr(SIMULATION_TOURNAMENT, 'min_salary', 3.5),
        "max_allowed_salary": round(SIMULATION_TOURNAMENT.salary_cap * 0.35, 1),
        "players": expiring_players
    })

@app.route('/api/team-manager/extensions/offer', methods=['POST'])
def offer_extension():
    global SIMULATION_TOURNAMENT, NEGOTIATION_ATTEMPTS
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    data = request.get_json() or {}
    player_name = data.get('player_name')
    years = int(data.get('years', 1))
    salary = float(data.get('salary', 2.0))
    option_type = data.get('option_type', 'None')
    raise_pct = float(data.get('raise_pct', 0.05))
    force_sign = bool(data.get('force_sign', False))
    
    player = next((p for p in user_team.roster if p.nome == player_name), None)
    if not player or not player.contract or player.contract.anni_rimanenti != 1:
        return jsonify({"success": False, "message": "Invalid player or not expiring."}), 400
        
    attempts = NEGOTIATION_ATTEMPTS.get(player_name, 0)
    if attempts >= 3 and not force_sign:
        return jsonify({
            "success": False, 
            "message": f"Negotiations with {player_name} are closed. The player will test Free Agency.",
            "attempts": attempts,
            "is_closed": True
        })
        
    # Increment attempts
    attempts += 1
    NEGOTIATION_ATTEMPTS[player_name] = attempts
    
    player_opt = (option_type == "PO")
    team_opt = (option_type == "TO")
    raise_str = f"+{raise_pct*100:.0f}%" if raise_pct > 0 else f"{raise_pct*100:.0f}%"
    
    if force_sign:
        new_salari = [player.contract.salario_annuale]
        cur_sal = salary
        for _ in range(years):
            new_salari.append(round(cur_sal, 2))
            cur_sal *= (1.0 + raise_pct)
        player.contract.salari_per_anno = new_salari
        player.contract.anni_rimanenti = len(new_salari)
        player.contract.salario_annuale = round(salary, 1)
        player.contract.player_option = player_opt
        player.contract.team_option = team_opt
        player.is_flight_risk = False
        player.walks_away = ""
        trade_requests.clear_request(player)   # he signed on: the request is over
        player.morale = min(100, player.morale + 5)
        
        opt_str = ""
        if player_opt: opt_str = " [Player Option]"
        elif team_opt: opt_str = " [Team Option]"
        
        from core.news_generator import add_news
        add_news(
            category="signings",
            title=f"✍️ EXTENSION: {player.nome} signs with the {user_team.nome}!",
            excerpt=f"Agreement reached between the {user_team.nome} and {player.nome}: contract extension of {years} years starting at ${salary:.1f}M/year ({raise_str} annual raises){opt_str}.",
            teams=[user_team.nome],
            season=SIMULATION_TOURNAMENT.season_number
        )
        
        return jsonify({
            "success": True,
            "message": f"Forced renewal! {player_name} signed an extension of {years} years starting at ${salary:.1f}M/year ({raise_str} annual){opt_str}.",
            "attempts": attempts,
            "is_closed": False
        })
        
    # Full FA-aligned evaluation
    from offseason.contract_extensions import ContractExtensions
    ext_engine = ContractExtensions(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre)
    
    final_score, feedback_reason = ext_engine.calculate_extension_score(player, user_team, salary, option_type, raise_pct=raise_pct)
    
    # Acceptance Threshold
    acceptance_threshold = 52.0
    if player.ovr >= 88:
        acceptance_threshold += 4.0

    if final_score >= acceptance_threshold:
        new_salari = [player.contract.salario_annuale]
        cur_sal = salary
        for _ in range(years):
            new_salari.append(round(cur_sal, 2))
            cur_sal *= (1.0 + raise_pct)
        player.contract.salari_per_anno = new_salari
        player.contract.anni_rimanenti = len(new_salari)
        player.contract.salario_annuale = round(salary, 1)
        player.contract.player_option = player_opt
        player.contract.team_option = team_opt
        player.is_flight_risk = False
        player.walks_away = ""
        trade_requests.clear_request(player)   # he signed on: the request is over
        player.morale = min(100, player.morale + 5)
        
        opt_str = ""
        if player_opt: opt_str = " with a Player Option"
        elif team_opt: opt_str = " with a Team Option"
        
        from core.news_generator import add_news
        is_star = player.ovr >= 83
        add_news(
            category="signings",
            title=f"✍️ EXTENSION: {player.nome} renews with the {user_team.nome}!" if is_star else f"{player.nome} extends with the {user_team.nome}",
            excerpt=f"The {user_team.nome} lock up {player.nome}: extension of {years} years signed starting at ${salary:.1f}M ({raise_str} annual raises){opt_str}.",
            teams=[user_team.nome],
            is_breaking=is_star,
            season=SIMULATION_TOURNAMENT.season_number
        )
        
        return jsonify({
            "success": True,
            "message": f"Agreement reached! {player_name} signed for {years} years starting at ${salary:.1f}M ({raise_str} annual){opt_str}.",
            "attempts": attempts,
            "is_closed": False
        })
    elif attempts >= 3:
        player.is_flight_risk = True
        from core.news_generator import add_news
        is_star = player.ovr >= 83
        add_news(
            category="signings",
            title=f"🚨 MARKET: {player.nome} refuses the renewal!",
            excerpt=f"Definitive break in the negotiations between the {user_team.nome} and {player.nome} (OVR {player.ovr}). The player will test Free Agency at the end of the season.",
            teams=[user_team.nome],
            is_breaking=is_star,
            season=SIMULATION_TOURNAMENT.season_number
        )
        return jsonify({
            "success": False,
            "message": f"Offer rejected ({final_score:.0f}/100): {feedback_reason}. Negotiations for this season are broken off.",
            "attempts": attempts,
            "is_closed": True
        })
    else:
        return jsonify({
            "success": False,
            "message": f"Offer rejected ({final_score:.0f}/100): {feedback_reason} (Attempts left: {3 - attempts})",
            "attempts": attempts,
            "is_closed": False
        })


@app.route('/api/contracts/evaluate-offer', methods=['POST'])
def evaluate_contract_offer():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    data = request.get_json() or {}
    player_name = data.get('player_name')
    offer_salary = float(data.get('offer_salary', 2.0))
    years = int(data.get('years', 2))
    option_type = data.get('option_type', 'None')
    mode = data.get('mode', 'extension')  # 'extension' or 'free_agency'
    raise_pct = float(data.get('raise_pct', 0.05))
    team_name = data.get('team_name')

    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    team = None
    if team_name:
        team = next((s for s in SIMULATION_TOURNAMENT.squadre if s.nome.lower() == team_name.lower()), None)
    if not team:
        team = user_team or (SIMULATION_TOURNAMENT.squadre[0] if SIMULATION_TOURNAMENT.squadre else None)

    if not team:
        return jsonify({"error": "No team available"}), 400

    # Find player in all teams or free agents pool
    target_player = None
    for s in SIMULATION_TOURNAMENT.squadre:
        for p in s.roster:
            if p.nome.lower() == player_name.lower():
                target_player = p
                break
        if target_player:
            break

    if not target_player:
        target_player = next((p for p in getattr(SIMULATION_TOURNAMENT, 'free_agents_pool', []) if p.nome.lower() == player_name.lower()), None)

    if not target_player:
        # During the offseason market the free agents live in OFFSEASON_FA_POOL / the active FreeAgency, not in free_agents_pool
        market = list(OFFSEASON_FA_POOL or [])
        if ACTIVE_FREE_AGENCY_INSTANCE is not None:
            market += list(getattr(ACTIVE_FREE_AGENCY_INSTANCE, 'unrestricted_free_agents', []) or [])
        target_player = next((p for p in market if p.nome.lower() == player_name.lower()), None)

    if not target_player:
        return jsonify({"error": f"Player {player_name} not found"}), 404

    from offseason.contract_extensions import ContractExtensions
    engine = ContractExtensions(SIMULATION_TOURNAMENT, SIMULATION_TOURNAMENT.squadre)
    evaluation = engine.evaluate_realtime_offer(target_player, team, offer_salary, years, option_type, mode=mode, raise_pct=raise_pct)

    # Attach team financial context
    cap = getattr(SIMULATION_TOURNAMENT, 'salary_cap', 155.0)
    tax = getattr(SIMULATION_TOURNAMENT, 'luxury_tax_threshold', 185.0)
    first_apron = getattr(SIMULATION_TOURNAMENT, 'first_apron', 195.0)
    second_apron = getattr(SIMULATION_TOURNAMENT, 'second_apron', 205.0)
    
    cur_payroll = getattr(team, 'payroll', 0.0)
    new_payroll = cur_payroll + offer_salary if mode == "free_agency" else cur_payroll
    cap_space_after = max(0.0, cap - new_payroll)

    evaluation["team_payroll"] = round(cur_payroll, 1)
    evaluation["team_cap"] = round(cap, 1)
    evaluation["team_tax"] = round(tax, 1)
    evaluation["team_first_apron"] = round(first_apron, 1)
    evaluation["team_second_apron"] = round(second_apron, 1)
    evaluation["cap_space_after"] = round(cap_space_after, 1)
    evaluation["is_over_cap"] = new_payroll > cap

    return jsonify({"success": True, "evaluation": evaluation})


@app.route('/api/team-manager/save-rotations', methods=['POST'])
def save_rotations():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    data = request.get_json() or {}
    rotations = data.get('rotations', {})
    
    # 1. First, check injuries and calculate total minutes
    totale_minuti = 0
    for p in user_team.roster:
        mins = int(rotations.get(p.nome, 0))
        if mins < 0:
            return jsonify({"error": f"The minutes for {p.nome} cannot be negative."}), 400
            
        if p.infortunato and mins > 0:
            return jsonify({"error": f"The injured player {p.nome} cannot have target minutes greater than 0."}), 400
            
        if not p.infortunato:
            totale_minuti += mins
            
    if totale_minuti != 240:
        return jsonify({"error": f"The sum of the healthy players' minutes must be exactly 240 (currently {totale_minuti})."}), 400
        
    # 2. Save target minutes and backup
    user_team.rotazioni_personalizzate_utente = {}
    for p in user_team.roster:
        p.minuti_target = int(rotations.get(p.nome, 0))
        user_team.rotazioni_personalizzate_utente[p.nome] = p.minuti_target
        
    return jsonify({
        "success": True,
        "message": "Rotations saved correctly!"
    })


@app.route('/api/team-manager/change-roles', methods=['POST'])
def change_roles():
    """Rotations > Roles: {"roles": {player name: "PG"|"SG"|"SF"|"PF"|"C"}} for players of the user's team. Each one
    plays the new role in games and his OVR becomes his rating there (Giocatore.change_role)."""
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
    roles = (request.get_json() or {}).get('roles', {})
    if not isinstance(roles, dict):
        return jsonify({"error": "roles must be an object"}), 400
    by_name = {p.nome: p for p in user_team.roster}
    unknown = [name for name in roles if name not in by_name]
    if unknown:
        return jsonify({"error": f"Not on your roster: {', '.join(unknown)}"}), 400
    bad = [r for r in roles.values() if normalize_role(r) not in ROLES]
    if bad:
        return jsonify({"error": f"Unknown role: {bad[0]}"}), 400
    changed = []
    for name, role in roles.items():
        p = by_name[name]
        before = (p.ruolo, p.ovr)
        p.change_role(role)
        if (p.ruolo, p.ovr) != before:
            changed.append({"nome": p.nome, "ruolo": p.ruolo, "ovr": p.ovr, "potenziale": p.potenziale,
                            "ruolo_originale": getattr(p, 'ruolo_originale', None),
                            "valutazioni_posizionali": dict(p.valutazioni_posizionali),
                            "ovr_if_role": {r: p.ovr_at_role(r) for r in ROLES}})
    if changed:
        user_team.scegli_quintetto_iniziale()
    return jsonify({"success": True, "changed": changed})


@app.route('/api/team-manager/save-lineup', methods=['POST'])
def save_lineup():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    data = request.get_json() or {}
    lineup = data.get('lineup', {})
    
    valid_positions = {'PG', 'SG', 'SF', 'PF', 'C'}
    if not getattr(user_team, 'user_custom_lineup', None):
        user_team.user_custom_lineup = {}
        
    for pos, player_name in lineup.items():
        pos = normalize_role(pos)  # accepts legacy Italian keys too
        if pos in valid_positions:
            if player_name in [None, "", "Auto", "Auto-Coach"]:
                if pos in user_team.user_custom_lineup:
                    del user_team.user_custom_lineup[pos]
            else:
                user_team.user_custom_lineup[pos] = player_name
                
    user_team.scegli_quintetto_iniziale()
    return jsonify({
        "success": True,
        "message": "Starting lineup saved correctly!",
        "user_custom_lineup": user_team.user_custom_lineup
    })


@app.route('/api/team-manager/save-poe', methods=['POST'])
def save_poe():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    data = request.get_json() or {}
    poe = data.get('poe')
    
    from core.config import CONFIG
    if poe in CONFIG.COACHINGTACTICS.POINTS_OF_EMPHASIS:
        user_team.active_poe = poe
        return jsonify({
            "success": True,
            "message": f"Point of Emphasis impostato su '{poe}' con successo!",
            "active_poe": user_team.active_poe
        })
        
    return jsonify({"error": "Point of Emphasis non valido."}), 400


@app.route('/api/team-manager/auto-rotate', methods=['POST'])
def auto_rotate():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    # Call core auto-rotate logic
    SIMULATION_TOURNAMENT.imposta_rotazioni_stagione_per_squadra(user_team, force_user=True)
    
    # Save the auto-rotate results to backup as well
    user_team.rotazioni_personalizzate_utente = {p.nome: p.minuti_target for p in user_team.roster}
    
    # Return updated target minutes
    updated_rotations = {}
    for p in user_team.roster:
        updated_rotations[p.nome] = p.minuti_target
        
    return jsonify({
        "success": True,
        "message": "Auto-rotation completed successfully!",
        "rotations": updated_rotations
    })


@app.route('/api/team-manager/change-coach-style', methods=['POST'])
def change_coach_style():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "No team selected"}), 400
        
    if not user_team.coach:
        return jsonify({"error": "Your team does not have an active coach"}), 400
        
    data = request.get_json() or {}
    new_style = data.get('stile_gioco')
    
    from core.config import CONFIG
    if new_style not in CONFIG.COACHINGSTYLES.STYLES:
        return jsonify({"error": f"Play style '{new_style}' is not valid."}), 400
        
    user_team.coach.stile_gioco = new_style
    return jsonify({
        "success": True,
        "message": f"The coach's play style updated to {new_style}!"
    })


# =============================================================================
# ### NBA TV PLAY-BY-PLAY API ENDPOINTS ###
# =============================================================================

# Storage for playoff game logs (in-memory)
NBATV_GAME_LOGS = {}

def _format_games_log_for_nbatv(games_list):
    log = []
    if not games_list:
        return log
    for idx, g in enumerate(games_list):
        if not g:
            continue
        game_num = g.get('game_num', idx + 1)
        if 'squadra_casa' in g and 'squadra_ospite' in g:
            h_name = g['squadra_casa'].get('nome', '')
            a_name = g['squadra_ospite'].get('nome', '')
            h_score = g['squadra_casa'].get('punteggio', 0)
            a_score = g['squadra_ospite'].get('punteggio', 0)
        else:
            h_name = g.get('home', g.get('home_team', ''))
            a_name = g.get('away', g.get('away_team', ''))
            h_score = g.get('home_score', 0)
            a_score = g.get('away_score', 0)
        winner = h_name if h_score > a_score else (a_name if a_score > h_score else '')
        log.append({
            'game_num': game_num,
            'home_team': h_name,
            'away_team': a_name,
            'home_score': h_score,
            'away_score': a_score,
            'winner': winner
        })
    return log

@app.route('/api/playoff_series_list', methods=['GET'])
@app.route('/api/nbatv/series', methods=['GET'])
def get_nbatv_series():
    """Get list of active playoff series for NBA TV viewing."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized", "available": False, "series": []}), 200
    
    # Check if we're in playoffs
    if LEAGUE_STATE not in ["PLAYOFFS_IN_PROGRESS", "PLAYOFFS_END"]:
        return jsonify({"available": False, "series": [], "message": "NBA TV is only available during the playoffs"}), 200
    
    torneo = SIMULATION_TOURNAMENT
    series_list = []
    
    # 1. Handle Play-In series
    if torneo.playoff_state == "PLAY_IN":
        for conf in ['east', 'west']:
            conf_name = "East" if conf == 'east' else "West"
            teams = torneo.play_in_teams.get(conf, [])
            results = torneo.play_in_results.get(conf, {})
            
            if len(teams) >= 4:
                # G1: 7 vs 8
                g1 = results.get('game1')
                g1_played = g1 is not None
                g1_winner = g1.get('winner') if g1_played else None
                g1_games = g1.get('log', {}).get('games', []) if (g1 and isinstance(g1.get('log'), dict)) else []
                g1_log = _format_games_log_for_nbatv(g1_games)
                if not g1_log and g1_played:
                    g1_log = [{
                        'game_num': 1,
                        'home_team': teams[0].nome,
                        'away_team': teams[1].nome,
                        'home_score': 0,
                        'away_score': 0,
                        'winner': g1_winner or ''
                    }]
                series_list.append({
                    'id': f"{conf}_playin_0",
                    'conference': conf_name,
                    'round': 'Play-In (7v8)',
                    'team1': teams[0].nome,
                    'team2': teams[1].nome,
                    'wins1': 1 if g1_winner == teams[0].nome else 0,
                    'wins2': 1 if g1_winner == teams[1].nome else 0,
                    'games_played': 1 if g1_played else 0,
                    'is_complete': g1_played,
                    'games_log': g1_log
                })
                
                # G2: 9 vs 10
                g2 = results.get('game2')
                g2_played = g2 is not None
                g2_winner = g2.get('winner') if g2_played else None
                g2_games = g2.get('log', {}).get('games', []) if (g2 and isinstance(g2.get('log'), dict)) else []
                g2_log = _format_games_log_for_nbatv(g2_games)
                if not g2_log and g2_played:
                    g2_log = [{
                        'game_num': 1,
                        'home_team': teams[2].nome,
                        'away_team': teams[3].nome,
                        'home_score': 0,
                        'away_score': 0,
                        'winner': g2_winner or ''
                    }]
                series_list.append({
                    'id': f"{conf}_playin_1",
                    'conference': conf_name,
                    'round': 'Play-In (9v10)',
                    'team1': teams[2].nome,
                    'team2': teams[3].nome,
                    'wins1': 1 if g2_winner == teams[2].nome else 0,
                    'wins2': 1 if g2_winner == teams[3].nome else 0,
                    'games_played': 1 if g2_played else 0,
                    'is_complete': g2_played,
                    'games_log': g2_log
                })
                
                # G3: Final
                g3 = results.get('game3')
                g3_played = g3 is not None
                g3_winner = g3.get('winner') if g3_played else None
                g3_team1 = results.get('game1', {}).get('loser') or 'Perdente G1'
                g3_team2 = results.get('game2', {}).get('winner') or 'Vincente G2'
                g3_games = g3.get('log', {}).get('games', []) if (g3 and isinstance(g3.get('log'), dict)) else []
                g3_log = _format_games_log_for_nbatv(g3_games)
                if not g3_log and g3_played:
                    g3_log = [{
                        'game_num': 1,
                        'home_team': g3_team1,
                        'away_team': g3_team2,
                        'home_score': 0,
                        'away_score': 0,
                        'winner': g3_winner or ''
                    }]
                series_list.append({
                    'id': f"{conf}_playin_2",
                    'conference': conf_name,
                    'round': 'Play-In Final',
                    'team1': g3_team1,
                    'team2': g3_team2,
                    'wins1': 1 if g3_winner == g3_team1 else 0,
                    'wins2': 1 if g3_winner == g3_team2 else 0,
                    'games_played': 1 if g3_played else 0,
                    'is_complete': g3_played,
                    'games_log': g3_log
                })
                
    # 2. Handle standard playoff rounds
    elif hasattr(torneo, 'active_playoff_series') and torneo.active_playoff_series:
        for idx, series in enumerate(torneo.active_playoff_series):
            team1 = series['s1']
            team2 = series['s2']
            wins1 = series.get('vittorie_s1', 0)
            wins2 = series.get('vittorie_s2', 0)
            is_complete = series.get('winner_nome') is not None
            
            series_list.append({
                'id': f"{series['conf']}_{series['round']}_{idx}",
                'conference': series['conf'].capitalize(),
                'round': series['round'],
                'team1': team1.nome,
                'team2': team2.nome,
                'wins1': wins1,
                'wins2': wins2,
                'games_played': wins1 + wins2,
                'is_complete': is_complete,
                'games_log': _format_games_log_for_nbatv(series.get('games', []))
            })
            
    # Fallback to general playoff bracket structure if active list empty
    if not series_list and torneo.playoff_bracket_data:
        for conf in ['east', 'west']:
            conf_name = "East" if conf == 'east' else "West"
            for round_name in ['qf', 'sf', 'cf']:
                matchups = torneo.playoff_bracket_data.get(conf, {}).get(round_name, [])
                for idx, m in enumerate(matchups):
                    if m:
                        series_list.append({
                            'id': f"{conf}_{round_name}_{idx}",
                            'conference': conf_name,
                            'round': round_name.upper(),
                            'team1': m.get('s1_nome'),
                            'team2': m.get('s2_nome'),
                            'wins1': m.get('s1_vittorie', 0),
                            'wins2': m.get('s2_vittorie', 0),
                            'games_played': m.get('s1_vittorie', 0) + m.get('s2_vittorie', 0),
                            'is_complete': m.get('winner_nome') is not None,
                            'games_log': _format_games_log_for_nbatv(m.get('games', []))
                        })
        # Add finals
        finals_matchups = torneo.playoff_bracket_data.get('finals', [])
        for idx, m in enumerate(finals_matchups):
            if m:
                series_list.append({
                    'id': f"finals_finals_{idx}",
                    'conference': 'Finals',
                    'round': 'Finals',
                    'team1': m.get('s1_nome'),
                    'team2': m.get('s2_nome'),
                    'wins1': m.get('s1_vittorie', 0),
                    'wins2': m.get('s2_vittorie', 0),
                    'games_played': m.get('s1_vittorie', 0) + m.get('s2_vittorie', 0),
                    'is_complete': m.get('winner_nome') is not None,
                    'games_log': _format_games_log_for_nbatv(m.get('games', []))
                })
                
    return jsonify({
        "available": True,
        "series": series_list,
        "season": torneo.season_number
    })


@app.route('/api/nbatv/watch/<series_id>/<int:game_num>', methods=['POST'])
def watch_nbatv_game(series_id, game_num):
    """Simulate and return play-by-play for a specific playoff game."""
    global SIMULATION_TOURNAMENT, NBATV_GAME_LOGS
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    torneo = SIMULATION_TOURNAMENT
    
    # Check if game already simulated and cached
    cache_key = f"{series_id}_G{game_num}"
    if cache_key in NBATV_GAME_LOGS:
        return jsonify(NBATV_GAME_LOGS[cache_key])
    
    # Parse series_id to get teams
    # Expected format: "East_R1_0" or similar
    parts = series_id.split('_')
    if len(parts) < 3:
        return jsonify({"error": "Invalid series ID"}), 400
    
    conf = parts[0]
    
    # Find the two teams from the request body or series info
    data = request.get_json() or {}
    team1_name = data.get('team1')
    team2_name = data.get('team2')
    
    if not team1_name or not team2_name:
        return jsonify({"error": "Team names required in request body"}), 400
    
    # Find team objects
    team1 = next((s for s in torneo.squadre if s.nome == team1_name), None)
    team2 = next((s for s in torneo.squadre if s.nome == team2_name), None)
    
    if not team1 or not team2:
        return jsonify({"error": "Teams not found"}), 404
    
    try:
        # Import game engine and simulate with play logging
        from core.game_engine import Partita
        
        # Determine home team based on game number (odd = team1 home, even = team2 home for games 1-4)
        home_team = team1 if game_num % 2 == 1 or game_num == 7 else team2
        away_team = team2 if home_team == team1 else team1
        
        # Simulate game with play-by-play logging enabled
        partita = Partita(home_team, away_team, is_playoff=True, enable_play_log=True)
        score1, score2 = partita.gioca()
        
        # Prepare result
        result = {
            'game_num': game_num,
            'home_team': home_team.nome,
            'away_team': away_team.nome,
            'home_score': score1,
            'away_score': score2,
            'winner': home_team.nome if score1 > score2 else away_team.nome,
            'play_log': partita.play_log,
            'play_count': len(partita.play_log)
        }
        
        # Cache the result
        NBATV_GAME_LOGS[cache_key] = result
        
        return jsonify(result)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"NBA TV WATCH ERROR: {error_details}")
        return jsonify({"error": str(e), "details": error_details}), 500


@app.route('/api/nbatv/clear_cache', methods=['POST'])
def clear_nbatv_cache():
    """Clear the NBA TV game logs cache."""
    global NBATV_GAME_LOGS
    NBATV_GAME_LOGS = {}
    return jsonify({"success": True, "message": "Cache cleared"})


@app.route('/api/nbatv/setup-playoffs', methods=['POST'])
def setup_playoffs_gamebygame():
    """Setup playoffs for game-by-game simulation mode."""
    global SIMULATION_TOURNAMENT, PLAYOFF_SERIES, PLAYOFF_CURRENT_GAME, PLAYOFF_GAMEBYGAME_MODE, LEAGUE_STATE
    
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    torneo = SIMULATION_TOURNAMENT
    
    # Setup playoffs if not already done
    if torneo.playoff_state == "NOT_STARTED":
        torneo._setup_playoffs()
    
    # Initialize game-by-game tracking
    PLAYOFF_SERIES = {}
    PLAYOFF_CURRENT_GAME = 1
    PLAYOFF_GAMEBYGAME_MODE = True
    
    # Create series entries for first round (QF)
    east_teams = torneo.playoff_teams.get('east', [])
    west_teams = torneo.playoff_teams.get('west', [])
    
    # QF Matchups: 1v8, 4v5, 3v6, 2v7
    matchups = [(0, 7), (3, 4), (2, 5), (1, 6)]
    
    for conf, teams in [('East', east_teams), ('West', west_teams)]:
        for idx, (i, j) in enumerate(matchups):
            if i < len(teams) and j < len(teams):
                series_id = f"{conf}_QF_{idx}"
                PLAYOFF_SERIES[series_id] = {
                    'id': series_id,
                    'team1': teams[i],
                    'team2': teams[j],
                    'team1_name': teams[i].nome,
                    'team2_name': teams[j].nome,
                    'wins1': 0,
                    'wins2': 0,
                    'games_played': 0,  # Track how many games have been played
                    'round': 'QF',
                    'conference': conf,
                    'games_log': [],
                    'complete': False,
                    'winner': None
                }
    
    LEAGUE_STATE = "PLAYOFFS_IN_PROGRESS"
    
    return jsonify({
        "success": True,
        "series_count": len(PLAYOFF_SERIES),
        "current_game": PLAYOFF_CURRENT_GAME,
        "series": [{
            'id': s['id'],
            'team1': s['team1_name'],
            'team2': s['team2_name'],
            'wins1': s['wins1'],
            'wins2': s['wins2'],
            'round': s['round'],
            'conference': s['conference']
        } for s in PLAYOFF_SERIES.values()]
    })


@app.route('/api/nbatv/simulate-next-game', methods=['POST'])
def simulate_next_playoff_game():
    """Simulate the next game for all active (incomplete) series."""
    global SIMULATION_TOURNAMENT, PLAYOFF_SERIES, PLAYOFF_CURRENT_GAME, NBATV_GAME_LOGS, LEAGUE_STATE
    
    if not SIMULATION_TOURNAMENT or not PLAYOFF_GAMEBYGAME_MODE:
        return jsonify({"error": "Playoff game-by-game mode not active"}), 400
    
    from core.game_engine import Partita
    
    results = []
    
    # Simulate one game for each incomplete series
    for series_id, series in PLAYOFF_SERIES.items():
        if series['complete']:
            continue
        
        # Use THIS series' game count, not global
        game_num = series['games_played'] + 1
        
        team1 = series['team1']
        team2 = series['team2']
        
        # Determine home court (2-2-1-1-1 format)
        is_team1_home = game_num in [1, 2, 5, 7]
        home_team = team1 if is_team1_home else team2
        away_team = team2 if is_team1_home else team1
        
        try:
            # Simulate with play-by-play logging
            partita = Partita(home_team, away_team, is_playoff=True, enable_play_log=True)
            score1, score2 = partita.gioca()
            
            # Determine winner and update series
            if score1 > score2:
                winner = home_team
                if home_team == team1:
                    series['wins1'] += 1
                else:
                    series['wins2'] += 1
            else:
                winner = away_team
                if away_team == team1:
                    series['wins1'] += 1
                else:
                    series['wins2'] += 1
            
            # Check if series is complete
            if series['wins1'] >= 4:
                series['complete'] = True
                series['winner'] = series['team1_name']
            elif series['wins2'] >= 4:
                series['complete'] = True
                series['winner'] = series['team2_name']
            
            # Increment games played for this series
            series['games_played'] += 1
            
            # Store game log
            game_result = {
                'game_num': game_num,
                'home_team': home_team.nome,
                'away_team': away_team.nome,
                'home_score': score1,
                'away_score': score2,
                'winner': winner.nome,
                'play_log': partita.play_log,
                'play_count': len(partita.play_log)
            }
            
            series['games_log'].append(game_result)
            NBATV_GAME_LOGS[f"{series_id}_G{game_num}"] = game_result
            
            results.append({
                'series_id': series_id,
                'team1': series['team1_name'],
                'team2': series['team2_name'],
                'game_num': game_num,
                'home_team': home_team.nome,
                'away_team': away_team.nome,
                'home_score': score1,
                'away_score': score2,
                'winner': winner.nome,
                'series_score': f"{series['wins1']}-{series['wins2']}",
                'series_complete': series['complete']
            })
        except Exception as e:
            import traceback
            results.append({
                'series_id': series_id,
                'error': str(e),
                'details': traceback.format_exc()
            })
    
    PLAYOFF_CURRENT_GAME += 1
    
    # Check if all series are complete (round is over)
    all_complete = all(s['complete'] for s in PLAYOFF_SERIES.values())
    
    # If round is complete, setup next round
    current_round = list(PLAYOFF_SERIES.values())[0]['round'] if PLAYOFF_SERIES else 'QF'
    
    if all_complete:
        # Get winners by conference
        east_winners = [s for s in PLAYOFF_SERIES.values() if s['conference'] == 'East' and s['complete']]
        west_winners = [s for s in PLAYOFF_SERIES.values() if s['conference'] == 'West' and s['complete']]
        
        # Update playoff_bracket_data for Playoff tab
        if SIMULATION_TOURNAMENT and hasattr(SIMULATION_TOURNAMENT, 'playoff_bracket_data'):
            bracket = SIMULATION_TOURNAMENT.playoff_bracket_data
            round_key = current_round.lower()
            
            for conf, winners in [('east', east_winners), ('west', west_winners)]:
                if round_key not in bracket[conf]:
                    bracket[conf][round_key] = []
                bracket[conf][round_key] = [{
                    's1_nome': w['team1_name'],
                    's1_vittorie': w['wins1'],
                    's2_nome': w['team2_name'],
                    's2_vittorie': w['wins2'],
                    'winner_nome': w['winner']
                } for w in winners]
        
        # Setup next round
        next_round_map = {'QF': 'SF', 'SF': 'CF', 'CF': 'FINALS'}
        next_round = next_round_map.get(current_round)
        
        if next_round and next_round != 'FINALS':
            # Get the winners' team objects
            new_series = {}
            
            for conf in ['East', 'West']:
                conf_winners = sorted([s for s in PLAYOFF_SERIES.values() if s['conference'] == conf], key=lambda x: x['id'])
                
                # Create matchups: winner of series 0 vs winner of series 1, etc.
                for i in range(0, len(conf_winners), 2):
                    if i+1 < len(conf_winners):
                        w1 = conf_winners[i]
                        w2 = conf_winners[i+1]
                        series_id = f"{conf}_{next_round}_{i//2}"
                        team1 = w1['team1'] if w1['winner'] == w1['team1_name'] else w1['team2']
                        team2 = w2['team1'] if w2['winner'] == w2['team1_name'] else w2['team2']
                        
                        new_series[series_id] = {
                            'id': series_id,
                            'team1': team1,
                            'team2': team2,
                            'team1_name': team1.nome,
                            'team2_name': team2.nome,
                            'wins1': 0,
                            'wins2': 0,
                            'games_played': 0,
                            'round': next_round,
                            'conference': conf,
                            'games_log': [],
                            'complete': False,
                            'winner': None
                        }
            
            PLAYOFF_SERIES = new_series
            PLAYOFF_CURRENT_GAME = 1
            print(f"--- ADVANCED TO {next_round}: {len(PLAYOFF_SERIES)} series ---")
        
        elif next_round == 'FINALS':
            # Setup Finals
            east_champ = [s for s in PLAYOFF_SERIES.values() if s['conference'] == 'East' and s['complete']][0]
            west_champ = [s for s in PLAYOFF_SERIES.values() if s['conference'] == 'West' and s['complete']][0]
            
            team1 = east_champ['team1'] if east_champ['winner'] == east_champ['team1_name'] else east_champ['team2']
            team2 = west_champ['team1'] if west_champ['winner'] == west_champ['team1_name'] else west_champ['team2']
            
            PLAYOFF_SERIES = {
                'FINALS_0': {
                    'id': 'FINALS_0',
                    'team1': team1,
                    'team2': team2,
                    'team1_name': team1.nome,
                    'team2_name': team2.nome,
                    'wins1': 0,
                    'wins2': 0,
                    'games_played': 0,
                    'round': 'FINALS',
                    'conference': 'NBA',
                    'games_log': [],
                    'complete': False,
                    'winner': None
                }
            }
            PLAYOFF_CURRENT_GAME = 1
            print(f"--- NBA FINALS: {team1.nome} vs {team2.nome} ---")
        
        else:
            # Finals complete - playoffs over
            LEAGUE_STATE = "PLAYOFFS_END"
            if SIMULATION_TOURNAMENT:
                finals_series = list(PLAYOFF_SERIES.values())[0]
                champ_team = finals_series['team1'] if finals_series['winner'] == finals_series['team1_name'] else finals_series['team2']
                SIMULATION_TOURNAMENT.campione = champ_team
            print(f"--- PLAYOFFS COMPLETE! ---")
    
    # Determine advanced_to value for response
    advanced_to = None
    if all_complete:
        next_round_map = {'QF': 'SF', 'SF': 'CF', 'CF': 'FINALS'}
        advanced_to = next_round_map.get(current_round)
    
    return jsonify({
        "success": True,
        "game_number": game_num if 'game_num' in dir() else 0,
        "results": results,
        "round_complete": all_complete,
        "next_game": PLAYOFF_CURRENT_GAME if not all_complete or advanced_to else None,
        "advanced_to": advanced_to
    })


@app.route('/api/nbatv/current-state', methods=['GET'])
def get_nbatv_state():
    """Get current playoff game-by-game state."""
    global PLAYOFF_SERIES, PLAYOFF_CURRENT_GAME, PLAYOFF_GAMEBYGAME_MODE
    
    if not PLAYOFF_GAMEBYGAME_MODE:
        return jsonify({"active": False})
    
    return jsonify({
        "active": True,
        "current_game": PLAYOFF_CURRENT_GAME,
        "series": [{
            'id': s['id'],
            'team1': s['team1_name'],
            'team2': s['team2_name'],
            'wins1': s['wins1'],
            'wins2': s['wins2'],
            'games_played': s['games_played'],
            'round': s['round'],
            'conference': s['conference'],
            'complete': s['complete'],
            'winner': s['winner']
        } for s in PLAYOFF_SERIES.values()]
    })

@app.route('/api/economy', methods=['GET'])
def get_economy_data():
    """League business for the Finances & CBA page: CBA lines, every team's payroll situation, contracts."""
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    return jsonify(build_league_finances(SIMULATION_TOURNAMENT, CONFIG.ECONOMY))

@app.route('/api/auto_sim_seasons', methods=['POST'])
def auto_sim_seasons():
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    
    data = request.get_json() or {}
    try:
        num_seasons_to_sim = max(1, min(int(data.get('years', 1)), 50))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid number of years"}), 400
        
    print(f"--- SERVER: Received Auto-Sim request for {num_seasons_to_sim} seasons. ---", flush=True)

    try:
        for i in range(num_seasons_to_sim):
            # We call our new orchestrator function
            simulation_logic.run_full_season_cycle(SIMULATION_TOURNAMENT)
            print(f"--- SERVER: Auto-Sim: Season {i+1}/{num_seasons_to_sim} completed. ---", flush=True)
        
        # After the cycle is finished, we reset the league state to PRE_SEASON
        LEAGUE_STATE = "PRE_SEASON"
        
        print("--- SERVER: Auto-Sim completed. Sending updated data. ---", flush=True)
        # We return the complete payload to update the whole UI
        return jsonify(get_full_league_data_payload())

    except Exception as e:
        print(f"!!! CRITICAL ERROR during the Auto-Sim: {e} !!!", flush=True)
        import traceback
        traceback.print_exc()
        # In case of error, we still return the current state to allow debugging
        return jsonify(get_full_league_data_payload()), 500
    
@app.route('/api/player-stats/career', methods=['GET'])
def get_career_stats():
    stats = simulation_logic.db_manager.load_all_career_stats()
    return jsonify(stats)
@app.route('/api/stats/seasons', methods=['GET'])
def get_available_seasons_api():
    """Returns the available seasons for the dropdown menu."""
    seasons = simulation_logic.db_manager.get_available_seasons()
    return jsonify(seasons)

@app.route('/api/stats/player-season-stats/<int:season_number>', methods=['GET'])
def get_player_season_stats(season_number):
    """Returns the players' statistics for a given season."""
    stats = simulation_logic.db_manager.load_player_stats_for_season(season_number)
    return jsonify(stats)
# =============================================================================
# ### OFFSEASON UI API ENDPOINTS ###
# =============================================================================

@app.route('/api/offseason/salary-cap-table', methods=['GET'])
def get_salary_cap_table():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    torneo = SIMULATION_TOURNAMENT
    teams_data = []
    
    for squadra in sorted(torneo.squadre, key=lambda s: s.nome):
        payroll = round(squadra.payroll, 1)
        cap_space = round(squadra.salary_cap_space, 1)
        
        roster_data = []
        for p in squadra.roster:
            try:
                contract_str = ""
                salario_val = 0
                anni_rimanenti = 0
                team_option = False
                player_option = False
                
                if hasattr(p, 'contract') and p.contract:
                    contract_str = f"${round(p.contract.salario_annuale, 1)}M / {p.contract.anni_rimanenti}y"
                    if getattr(p.contract, 'team_option', False) and p.contract.anni_rimanenti == 1:
                        contract_str += " (TO)"
                    elif getattr(p.contract, 'player_option', False) and p.contract.anni_rimanenti == 1:
                        contract_str += " (PO)"
                    salario_val = p.contract.salario_annuale
                    anni_rimanenti = p.contract.anni_rimanenti
                    team_option = getattr(p.contract, 'team_option', False)
                    player_option = getattr(p.contract, 'player_option', False)
                
                roster_data.append({
                    "nome": p.nome,
                    "ruolo": p.ruolo,
                    "eta": p.eta,
                    "ovr": p.ovr,
                    "pot": p.potenziale,
                    "contratto": contract_str,
                    "salario": salario_val,
                    "anni_rimanenti": anni_rimanenti,
                    "team_option": team_option,
                    "player_option": player_option
                })
            except Exception as e:
                print(f"Error processing player {p.nome} in salary cap table: {e}")
                
        # Sort roster by salary descending
        roster_data.sort(key=lambda x: x["salario"], reverse=True)
            
        teams_data.append({
            "nome": squadra.nome,
            "payroll": payroll,
            "cap_space": cap_space,
            "roster": roster_data
        })
        
    return jsonify({
        "salary_cap": torneo.salary_cap,
        "luxury_tax": torneo.luxury_tax_threshold,
        "first_apron": torneo.first_apron,
        "second_apron": torneo.second_apron,
        "teams": teams_data
    })

@app.route('/api/offseason/team-needs', methods=['GET'])
def get_team_needs():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
        
    torneo = SIMULATION_TOURNAMENT
    teams_data = []
    
    for squadra in sorted(torneo.squadre, key=lambda s: s.nome):
        try:
            stato = torneo._determina_stato_squadra(squadra)
            needs = []
            for role in ["PG", "SG", "SF", "PF", "C"]:
                if squadra.ha_bisogno_di_ruolo(role):
                    needs.append(role)
                    
            strategy = "Find a direction"
            if stato == "Rebuilding":
                strategy = "Build through the Draft"
            elif stato in ["Defending Champion", "Contender"]:
                if squadra.salary_cap_space > 20:
                    strategy = "Aggressive FA / All-In"
                else:
                    strategy = "Run It Back / Sign Veterans"
            elif stato == "Playoff Team":
                strategy = "Look for the last piece"
            elif stato == "Rising Star":
                strategy = "Develop the Youngsters"
            elif stato == "Aging Core":
                strategy = "Renew the Core"
            teams_data.append({
                "nome": squadra.nome,
                "stato": stato,
                "strategy": strategy,
                "cap_space": round(squadra.salary_cap_space, 1),
                "needs": needs
            })
        except Exception as e:
            print(f"Error processing team {squadra.nome} in team needs: {e}")
        
    return jsonify({"teams": teams_data})

# --- ROUTE TESTING PLAY-BY-PLAY ---

@app.route('/api/testing/teams', methods=['GET'])
def testing_get_teams():
    """Returns the list of the teams available for testing."""
    import main
    try:
        squadre, _ = main.caricamento_squadre()
        teams_data = [{"id": s.nome, "nome": s.nome} for s in squadre]
        return jsonify({"teams": teams_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/testing/simula_partita', methods=['POST'])
def testing_simula_partita():
    """Simulates a single game between two teams and returns the play-by-play log."""
    data = request.get_json(silent=True) or {}
    home_team_name = data.get('home_team')
    away_team_name = data.get('away_team')
    
    if not home_team_name or not away_team_name:
        return jsonify({"error": "Home and away teams are required."}), 400
        
    import main
    from core.game_engine import Partita
    
    try:
        squadre, _ = main.caricamento_squadre()
        home_team = next((s for s in squadre if s.nome == home_team_name), None)
        away_team = next((s for s in squadre if s.nome == away_team_name), None)
        
        if not home_team or not away_team:
            return jsonify({"error": "Teams not found."}), 404
            
        # Initialize and play the game with the play_log enabled
        partita = Partita(home_team, away_team, enable_play_log=True)
        partita.gioca()
        
        # --- AGGREGATE STATS ---
        def extract_team_stats(team):
            players_stats = []
            team_totals = {
                "punti": 0, "rimbalzi": 0, "assist": 0, "steals": 0, "blocks": 0, "turnover": 0, "falli_commessi": 0,
                "tiri_fatti": 0, "tiri_tentati": 0, "tiri_fatti_3": 0, "tiri_tentati_3": 0, "liberi_fatti": 0, "liberi_tentati": 0
            }
            
            for p in team.roster:
                gs = p.game_stats
                if gs.secondi_giocati > 0:
                    fgm = gs.tiri_fatti_2 + gs.tiri_fatti_3
                    fga = gs.tiri_tentati_2 + gs.tiri_tentati_3
                    players_stats.append({
                        "name": p.nome,
                        "minuti": round(gs.secondi_giocati / 60, 1),
                        "punti": gs.punti,
                        "rimbalzi": gs.rimbalzi,
                        "assist": gs.assist,
                        "steals": gs.steals,
                        "blocks": gs.blocks,
                        "turnover": gs.turnover,
                        "falli": gs.falli_commessi,
                        "fgm": fgm,
                        "fga": fga,
                        "fg_pct": round(fgm / fga * 100, 1) if fga > 0 else 0,
                        "fg3m": gs.tiri_fatti_3,
                        "fg3a": gs.tiri_tentati_3,
                        "fg3_pct": round(gs.tiri_fatti_3 / gs.tiri_tentati_3 * 100, 1) if gs.tiri_tentati_3 > 0 else 0,
                        "ftm": gs.punti_liberi,
                        "fta": gs.tiri_liberi_tentati,
                        "ft_pct": round(gs.punti_liberi / gs.tiri_liberi_tentati * 100, 1) if gs.tiri_liberi_tentati > 0 else 0
                    })
                    
                    team_totals["punti"] += gs.punti
                    team_totals["rimbalzi"] += gs.rimbalzi
                    team_totals["assist"] += gs.assist
                    team_totals["steals"] += gs.steals
                    team_totals["blocks"] += gs.blocks
                    team_totals["turnover"] += gs.turnover
                    team_totals["falli_commessi"] += gs.falli_commessi
                    team_totals["tiri_fatti"] += fgm
                    team_totals["tiri_tentati"] += fga
                    team_totals["tiri_fatti_3"] += gs.tiri_fatti_3
                    team_totals["tiri_tentati_3"] += gs.tiri_tentati_3
                    team_totals["liberi_fatti"] += gs.punti_liberi
                    team_totals["liberi_tentati"] += gs.tiri_liberi_tentati
            
            team_totals["fg_pct"] = round(team_totals["tiri_fatti"] / team_totals["tiri_tentati"] * 100, 1) if team_totals["tiri_tentati"] > 0 else 0
            team_totals["fg3_pct"] = round(team_totals["tiri_fatti_3"] / team_totals["tiri_tentati_3"] * 100, 1) if team_totals["tiri_tentati_3"] > 0 else 0
            team_totals["ft_pct"] = round(team_totals["liberi_fatti"] / team_totals["liberi_tentati"] * 100, 1) if team_totals["liberi_tentati"] > 0 else 0
            
            return {
                "totals": team_totals,
                "players": sorted(players_stats, key=lambda x: x["punti"], reverse=True)
            }
            
        home_stats = extract_team_stats(home_team)
        away_stats = extract_team_stats(away_team)
        
        import os, datetime, json
        os.makedirs('logs', exist_ok=True)
        filename = f"logs/match_{home_team.nome.replace(' ', '_')}_vs_{away_team.nome.replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        response_data = {
            "home": home_team.nome,
            "away": away_team.nome,
            "score": partita.punteggio,
            "home_stats": home_stats,
            "away_stats": away_stats,
            "play_log": partita.play_log
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, indent=4)
        
        return jsonify({
            **response_data,
            "saved_file": filename
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- ENDPOINTS SCOUTING CENTER ---

@app.route('/api/scouting/state', methods=['GET'])
def get_scouting_state():
    global SIMULATION_TOURNAMENT, LEAGUE_STATE
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "League not initialized"}), 400
        
    draft_class = getattr(SIMULATION_TOURNAMENT, 'draft_class', None)
    if not draft_class:
        return jsonify({"error": "Classe draft non generata"}), 400
        
    scout_staff = getattr(SIMULATION_TOURNAMENT, 'scout_staff', [])
    workouts_left = getattr(SIMULATION_TOURNAMENT, 'scouting_workouts_left', 0)
    
    prospects_list = scouted_prospects(draft_class, getattr(SIMULATION_TOURNAMENT, 'scouting_fog_of_war', True), scout_staff)

    return jsonify({
        "scout_staff": scout_staff,
        "workouts_left": workouts_left,
        "league_state": LEAGUE_STATE,
        "prospects": prospects_list
    })

@app.route('/api/scouting/assign', methods=['POST'])
def assign_scout():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "League not initialized"}), 400
        
    data = request.json or {}
    scout_index = data.get("scout_index")
    prospect_name = data.get("prospect_name")  # Can be None to free the scout
    
    scout_staff = getattr(SIMULATION_TOURNAMENT, 'scout_staff', [])
    if scout_index is None or scout_index < 0 or scout_index >= len(scout_staff):
        return jsonify({"error": "Invalid scout"}), 400
        
    # If we are assigning to a prospect, we free other scouts already assigned to that prospect
    if prospect_name:
        for s in scout_staff:
            if s.get("assigned_to") == prospect_name:
                s["assigned_to"] = None
                
    # Assign the current scout
    scout_staff[scout_index]["assigned_to"] = prospect_name
    return jsonify({"success": True, "scout_staff": scout_staff})

@app.route('/api/scouting/workout', methods=['POST'])
def run_private_workout():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "League not initialized"}), 400
        
    data = request.json or {}
    prospect_name = data.get("prospect_name")
    
    draft_class = getattr(SIMULATION_TOURNAMENT, 'draft_class', None)
    if not draft_class:
        return jsonify({"error": "Classe draft non generata"}), 400
        
    workouts_left = getattr(SIMULATION_TOURNAMENT, 'scouting_workouts_left', 0)
    if workouts_left <= 0:
        return jsonify({"error": "No private workout left for this season"}), 400
        
    target_prospect = None
    for p in draft_class:
        if p.nome == prospect_name:
            target_prospect = p
            break
            
    if not target_prospect:
        return jsonify({"error": "Prospect not found"}), 404
        
    # Run the workout
    target_prospect.scouting_progress = 100.0
    SIMULATION_TOURNAMENT.scouting_workouts_left -= 1
    
    # Remove the scout possibly assigned to him
    for s in SIMULATION_TOURNAMENT.scout_staff:
        if s.get("assigned_to") == prospect_name:
            s["assigned_to"] = None
            
    return jsonify({
        "success": True,
        "workouts_left": SIMULATION_TOURNAMENT.scouting_workouts_left,
        "prospect_name": prospect_name
    })

# --- ENDPOINTS GM COACHING OFFICE ---

def serialize_coach(coach):
    if not coach:
        return None
    return {
        "nome": coach.nome,
        "stile_gioco": coach.stile_gioco,
        "ovr_offensivo": coach.ovr_offensivo,
        "ovr_difensivo": coach.ovr_difensivo,
        "ovr_totale": coach.ovr_totale,
        "eta": coach.eta,
        "potenziale": coach.potenziale,
        "contratto_anni_rimanenti": coach.contratto_anni_rimanenti,
        "job_security": getattr(coach, 'job_security', 75.0),
        "xp": getattr(coach, 'xp', 0),
        "level": getattr(coach, 'level', 1),
        "badges": getattr(coach, 'badges', {
            "Rookie Developer": 0,
            "Defense Guru": 0,
            "Tactician": 0,
            "Fitness Specialist": 0,
            "Motivator": 0
        }),
        "salario": getattr(coach, 'salario', 2.5),
        "historical_wins": getattr(coach, 'historical_wins', 0),
        "historical_losses": getattr(coach, 'historical_losses', 0),
        "championships": getattr(coach, 'championships', 0),
        "badge_points": getattr(coach, 'badge_points', 0),
        "rpg_xp": getattr(coach, 'rpg_xp', getattr(coach, 'xp', 0)),
        "rpg_level": getattr(coach, 'rpg_level', getattr(coach, 'level', 1)),
        "skill_points": getattr(coach, 'skill_points', getattr(coach, 'badge_points', 0)),
        "unlocked_nodes": getattr(coach, 'unlocked_nodes', []),
        "player_development": getattr(coach, 'player_development', 75),
        "tactical_acumen": getattr(coach, 'tactical_acumen', 75),
        "discipline_culture": getattr(coach, 'discipline_culture', 75),
        "specialization": getattr(coach, 'specialization', 'Tactical Strategist'),
        "offensive_system": getattr(coach, 'offensive_system_label', getattr(coach, 'offensive_system', '')),
        "defensive_scheme": getattr(coach, 'defensive_scheme_label', getattr(coach, 'defensive_scheme', '')),
        "preferred_pace": getattr(coach, 'preferred_pace_label', getattr(coach, 'preferred_pace', '')),
        "contratto_totale_anni": getattr(coach, 'contratto_totale_anni', getattr(coach, 'contratto_anni_rimanenti', 1)),
        "years_with_current_team": getattr(coach, 'years_with_current_team', 1),
        "playoff_appearances": getattr(coach, 'playoff_appearances', 0),
        "coty_awards": getattr(coach, 'coty_awards', 0),
        "career_win_pct": getattr(coach, 'career_win_pct', 0.5),
        "job_security_label": getattr(coach, 'job_security_label', 'Secure'),
    }


def _coach_salary_ask(coach):
    """Yearly salary ($M) a coach asks to sign or extend; offers below 75% of it are refused."""
    return round(max(3.0, (coach.ovr_totale - 65) * 0.45), 1)


def _fire_user_coach(torneo, user_team):
    """Fire the user's coach: he joins the free-agent pool, the roster loses morale and chemistry.

    Returns (fired_coach, estimated_buyout_in_millions)."""
    fired_coach = user_team.coach
    buyout_amount = round(fired_coach.salario * max(1, fired_coach.contratto_anni_rimanenti) * 0.75, 1)

    fired_coach.contratto_anni_rimanenti = 1
    fired_coach.job_security = 50.0
    fired_coach.years_with_current_team = 0
    if user_team.nome not in getattr(fired_coach, 'past_teams', []):
        fired_coach.past_teams.append(user_team.nome)

    if not hasattr(torneo, 'unemployed_coaches'):
        torneo.unemployed_coaches = []
    torneo.unemployed_coaches.append(fired_coach)
    user_team.coach = None

    # Negative impact on morale and chemistry
    for p in user_team.roster:
        p.morale = max(40, p.morale - 3)
    user_team.intesa = max(30, getattr(user_team, 'intesa', 70) - 8)

    from core.news_generator import add_news
    add_news(
        category="general",
        title=f"🚨 GM DECISION: The {user_team.nome} fire coach {fired_coach.nome}",
        excerpt=f"The {user_team.nome} front office has announced the firing of head coach {fired_coach.nome} (Estimated buyout: ${buyout_amount:.1f}M). The franchise starts the search for the new head coach.",
        teams=[user_team.nome],
        is_breaking=True,
        season=torneo.season_number
    )
    return fired_coach, buyout_amount

@app.route('/api/coaching/state', methods=['GET'])
def get_coaching_state():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "League not initialized"}), 400
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        # If spectator mode, select first team for viewing
        user_team = SIMULATION_TOURNAMENT.squadre[0] if SIMULATION_TOURNAMENT.squadre else None
        if not user_team:
            return jsonify({"error": "No team defined"}), 400
        
    if not hasattr(SIMULATION_TOURNAMENT, 'unemployed_coaches'):
        SIMULATION_TOURNAMENT.unemployed_coaches = []

    unemployed = SIMULATION_TOURNAMENT.unemployed_coaches
    
    # Make sure there are at least 6-8 credible candidates on the market
    if len(unemployed) < 6 and hasattr(SIMULATION_TOURNAMENT, '_generate_coach_candidate'):
        while len(unemployed) < 8:
            new_c = SIMULATION_TOURNAMENT._generate_coach_candidate()
            unemployed.append(new_c)
        SIMULATION_TOURNAMENT.unemployed_coaches = unemployed

    # Serialize the user's coach with roster fit computation
    curr_coach_data = None
    if user_team.coach:
        curr_coach_data = serialize_coach(user_team.coach)
        curr_coach_data["roster_fit"] = user_team.coach.calcola_roster_fit(user_team) if hasattr(user_team.coach, 'calcola_roster_fit') else {"fit_score": 75, "rating": "Good"}
        curr_coach_data["job_security_label"] = getattr(user_team.coach, 'job_security_label', 'Secure')
        curr_coach_data["career_win_pct"] = getattr(user_team.coach, 'career_win_pct', 0.500)
        curr_coach_data["extension_ask"] = _coach_salary_ask(user_team.coach)

    # Serialize free-agent candidates with a preview of the fit relative to the user's roster
    serialized_unemployed = []
    for c in unemployed:
        c_dict = serialize_coach(c)
        if hasattr(c, 'calcola_roster_fit'):
            c_dict["roster_fit"] = c.calcola_roster_fit(user_team)
        else:
            c_dict["roster_fit"] = {"fit_score": 75, "rating": "Standard"}
        c_dict["career_win_pct"] = getattr(c, 'career_win_pct', 0.500)
        c_dict["min_salary"] = round(_coach_salary_ask(c) * 0.75, 1)
        serialized_unemployed.append(c_dict)

    # Directory of the coaches of the whole league
    league_coaches = []
    for sq in SIMULATION_TOURNAMENT.squadre:
        if sq.coach:
            sc = serialize_coach(sq.coach)
            sc["team_name"] = sq.nome
            sc["team_record"] = f"{sq.vittorie}-{sq.sconfitte}"
            sc["team_ovr"] = getattr(sq, 'valutazione', 75)
            sc["job_security_label"] = getattr(sq.coach, 'job_security_label', 'Secure')
            league_coaches.append(sc)

    return jsonify({
        "current_coach": curr_coach_data,
        "unemployed_coaches": serialized_unemployed,
        "league_coaches": league_coaches,
        "team_name": user_team.nome,
        "tactical_styles": CONFIG.COACHINGSTYLES.STYLES
    })

@app.route('/api/coaching/upgrade_badge', methods=['POST'])
def upgrade_coach_badge():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "League not initialized"}), 400
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team or not user_team.coach:
        return jsonify({"error": "No active coach"}), 400
        
    coach = user_team.coach
    if getattr(coach, 'badge_points', 0) <= 0:
        return jsonify({"error": "No badge points available. Win games to earn XP and level up!"}), 400
        
    data = request.get_json() or {}
    badge_name = data.get("badge_name")
    
    if not isinstance(coach.badges, dict):
        coach.badges = {
            "Rookie Developer": 0,
            "Defense Guru": 0,
            "Tactician": 0,
            "Fitness Specialist": 0,
            "Motivator": 0,
            "Clutch Master": 0
        }
        
    if badge_name not in coach.badges:
        return jsonify({"error": f"Badge '{badge_name}' is not valid"}), 400
        
    current_level = coach.badges[badge_name]
    if current_level >= 3:
        return jsonify({"error": f"Badge '{badge_name}' is already at the maximum level (Gold / Level 3)!"}), 400
        
    coach.badges[badge_name] = current_level + 1
    coach.badge_points = max(0, coach.badge_points - 1)
    
    return jsonify({
        "success": True,
        "message": f"Badge '{badge_name}' upgraded to Level {coach.badges[badge_name]}!",
        "coach": serialize_coach(coach)
    })

@app.route('/api/coaching/extend', methods=['POST'])
def extend_coach():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "League not initialized"}), 400
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team or not user_team.coach:
        return jsonify({"error": "No active coach to renew"}), 400
        
    data = request.get_json() or {}
    years = int(data.get("years", 3))
    salary = data.get("salary")
    
    if years < 1 or years > 5:
        return jsonify({"error": "The renewal length must be between 1 and 5 years"}), 400
        
    coach = user_team.coach
    
    # Evaluate the coach's request
    min_demanded_salary = _coach_salary_ask(coach)
    if salary is not None:
        try:
            offered_sal = round(float(salary), 1)
            if offered_sal < min_demanded_salary * 0.75:
                return jsonify({"error": f"Coach {coach.nome} refuses: the offer of ${offered_sal:.1f}M is too low compared to his minimum demands (${min_demanded_salary:.1f}M/year)."}), 400
            coach.salario = offered_sal
        except (ValueError, TypeError):
            pass
            
    coach.contratto_anni_rimanenti += years
    coach.contratto_totale_anni += years
    coach.job_security = min(99.0, coach.job_security + 15.0)
    
    from core.news_generator import add_news
    add_news(
        category="general",
        title=f"✍️ COACH RENEWAL: {coach.nome} extends with the {user_team.nome}",
        excerpt=f"The {user_team.nome} have locked up coach {coach.nome} with an extension of {years} years at ${coach.salario:.1f}M/year.",
        teams=[user_team.nome],
        is_breaking=False,
        season=getattr(SIMULATION_TOURNAMENT, 'season_number', 1)
    )
    
    return jsonify({
        "success": True,
        "message": f"Coach {coach.nome}'s contract successfully extended by {years} years (${coach.salario:.1f}M/year)!",
        "coach": serialize_coach(coach)
    })

@app.route('/api/coaching/fire', methods=['POST'])
def fire_coach():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "League not initialized"}), 400

    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team or not user_team.coach:
        return jsonify({"error": "No active coach to fire"}), 400

    fired_coach, buyout_amount = _fire_user_coach(SIMULATION_TOURNAMENT, user_team)
    return jsonify({
        "success": True,
        "message": f"You fired coach {fired_coach.nome}. Remaining buyout to be paid by the franchise: ${buyout_amount:.1f}M."
    })

@app.route('/api/coaching/hire', methods=['POST'])
def hire_coach():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "League not initialized"}), 400
        
    user_team = SIMULATION_TOURNAMENT.squadra_giocatore
    if not user_team:
        return jsonify({"error": "User team not defined"}), 400
        
    data = request.get_json() or {}
    coach_name = data.get("coach_name")
    years = int(data.get("years", 3))
    salary = data.get("salary")
    replace_current = bool(data.get("replace_current", False))

    if user_team.coach and not replace_current:
        return jsonify({"error": "You already have an active coach! Fire him before hiring a new one."}), 400

    unemployed = getattr(SIMULATION_TOURNAMENT, 'unemployed_coaches', [])
    target_coach = next((c for c in unemployed if c.nome == coach_name), None)

    if not target_coach:
        return jsonify({"error": "Coach not found in the free-agent market"}), 400

    offered_salary = None
    if salary is not None:
        try:
            offered_salary = round(float(salary), 1)
        except (ValueError, TypeError):
            offered_salary = None
    min_salary = round(_coach_salary_ask(target_coach) * 0.75, 1)
    if offered_salary is not None and offered_salary < min_salary:
        return jsonify({"error": f"Coach {target_coach.nome} refuses: ${offered_salary:.1f}M is too low, he wants at least ${min_salary:.1f}M/year."}), 400

    fired_note = ""
    if user_team.coach and replace_current:
        fired_coach, buyout_amount = _fire_user_coach(SIMULATION_TOURNAMENT, user_team)
        fired_note = f" {fired_coach.nome} was fired (buyout ${buyout_amount:.1f}M)."

    target_coach.contratto_totale_anni = max(1, min(5, years))
    target_coach.contratto_anni_rimanenti = target_coach.contratto_totale_anni
    target_coach.job_security = 80.0
    target_coach.years_with_current_team = 1
    if offered_salary is not None:
        target_coach.salario = offered_salary

    user_team.coach = target_coach
    unemployed.remove(target_coach)
    
    # Chemistry bonus for tactical clarity
    user_team.intesa = min(100, getattr(user_team, 'intesa', 70) + 5)
    
    from core.news_generator import add_news
    add_news(
        category="general",
        title=f"👔 OFFICIAL: {target_coach.nome} is the new Head Coach of the {user_team.nome}",
        excerpt=f"The {user_team.nome} announce the agreement with {target_coach.nome}: {target_coach.contratto_totale_anni}-year contract at ${target_coach.salario:.1f}M/year. Play philosophy: {target_coach.stile_gioco}.",
        teams=[user_team.nome],
        is_breaking=True,
        season=SIMULATION_TOURNAMENT.season_number
    )
    
    return jsonify({
        "success": True,
        "message": f"You hired coach {target_coach.nome} for {target_coach.contratto_totale_anni} years at ${target_coach.salario:.1f}M/year.{fired_note}",
        "coach": serialize_coach(target_coach)
    })

# --- COACH TACTICAL SYSTEM FIT ENDPOINT ---

@app.route('/api/coaching/system-fit', methods=['GET'])
def get_coaching_system_fit():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 400

    user_team = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    if not user_team:
        user_team = SIMULATION_TOURNAMENT.squadre[0] if SIMULATION_TOURNAMENT.squadre else None

    if not user_team:
        return jsonify({"error": "No active team found"}), 400

    coach = getattr(user_team, 'coach', None)
    if not coach:
        return jsonify({
            "success": True,
            "has_coach": False,
            "team_name": user_team.nome,
            "system_fit": None
        })

    fit_data = coach.calcola_roster_fit(user_team)

    return jsonify({
        "success": True,
        "has_coach": True,
        "team_name": user_team.nome,
        "coach": serialize_coach(coach),
        "system_fit": fit_data
    })


@app.route('/api/team-manager/game-plan', methods=['POST'])
def save_team_game_plan():
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500
    
    sq = getattr(SIMULATION_TOURNAMENT, 'squadra_giocatore', None)
    if not sq:
        sq = SIMULATION_TOURNAMENT.squadre[0] if SIMULATION_TOURNAMENT.squadre else None

    if not sq:
        return jsonify({"error": "No team found"}), 400

    data = request.get_json() or {}
    
    if "active_poe" in data:
        sq.active_poe = data["active_poe"]
        
    if "custom_lineup" in data:
        sq.user_custom_lineup = normalize_role_keys(data["custom_lineup"])

    if "minutes" in data:
        minutes_map = data["minutes"]
        for p in sq.roster:
            if p.nome in minutes_map:
                p.minuti_target = minutes_map[p.nome]
        # ALWAYS save the persistent backup of the user's custom rotations
        sq.rotazioni_personalizzate_utente = {p.nome: p.minuti_target for p in sq.roster}
        sq.rotazione = [p for p in sq.roster if p.minuti_target > 0]

    # Immediately update the starting lineup and the positions on the court
    sq.scegli_quintetto_iniziale()

    if "tactical_plan" in data:
        from core.models import TacticalPlan
        tp_data = data["tactical_plan"]
        if not hasattr(sq, 'tactical_plan') or not sq.tactical_plan:
            sq.tactical_plan = TacticalPlan()
            
        sq.tactical_plan.pnr_coverage = tp_data.get("pnr_coverage", sq.tactical_plan.pnr_coverage)
        sq.tactical_plan.defensive_scheme = tp_data.get("defensive_scheme", sq.tactical_plan.defensive_scheme)
        sq.tactical_plan.offensive_focus = tp_data.get("offensive_focus", sq.tactical_plan.offensive_focus)
        sq.tactical_plan.pace_preference = tp_data.get("pace_preference", sq.tactical_plan.pace_preference)
        sq.tactical_plan.stagger_stars = tp_data.get("stagger_stars", sq.tactical_plan.stagger_stars)
        sq.tactical_plan.offensive_first_option = tp_data.get("offensive_first_option", getattr(sq.tactical_plan, 'offensive_first_option', None))
        sq.tactical_plan.offensive_second_option = tp_data.get("offensive_second_option", getattr(sq.tactical_plan, 'offensive_second_option', None))
        sq.tactical_plan.offensive_third_option = tp_data.get("offensive_third_option", getattr(sq.tactical_plan, 'offensive_third_option', None))
        sq.tactical_plan.player_touch_modifiers = tp_data.get("player_touch_modifiers", getattr(sq.tactical_plan, 'player_touch_modifiers', {}))

    # Immediately persist the changes to the active save
    auto_save_active_game()

    return jsonify({"success": True, "message": "Game plan, lineup and rotations saved successfully!"})


# ========================================================================
# TRADE IMPACT & GRADES (Trade Center history; the old analytics page tab is gone)
# ========================================================================

def _trade_impact_list(torneo):
    """Recorded trades with pre/post records, deltas and editorial grades (core/trade_grades.py)."""
    # 3. TRADE IMPACT & DELTA ANALYTICS
    raw_trades = list(getattr(torneo, 'trade_analytics_history', []) or [])
    
    def get_trade_signature(tr):
        t_names = sorted([t.get('team_name', '').lower() for t in tr.get('teams', [])])
        p_names = []
        for t in tr.get('teams', []):
            for p in t.get('players_received', []) + t.get('players_sent', []):
                p_names.append(p.get('name', '').lower() if isinstance(p, dict) else str(p).lower())
        return (tr.get('season', 1), tuple(t_names), tuple(sorted(p_names)))

    existing_signatures = {get_trade_signature(tr) for tr in raw_trades}
    existing_ids = {tr.get('id') for tr in raw_trades if tr.get('id')}
    
    save_trade_lines = []
    # 1. Read ONLY from active save folder
    try:
        save_hist_file = get_historical_file_path("trades_history.txt")
        if os.path.exists(save_hist_file):
            with open(save_hist_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line_s = line.strip()
                    if line_s and ("TRADE:" in line_s or "SCAMBIO:" in line_s or "BLOCKBUSTER" in line_s or "gets:" in line_s or " sends " in line_s or "cede" in line_s or "<-->" in line_s):
                        if any(k in line_s for k in ["PREDRAFT", "OFFSEASON", "PRE-SEASON", "PRE_SEASON", "| DRAFT"]):
                            continue
                        save_trade_lines.append(line_s)
    except Exception:
        pass

    # 2. Tournament current in-memory offseason/midseason logs
    if hasattr(torneo, 'offseason_log_data') and torneo.offseason_log_data:
        scambi_list = torneo.offseason_log_data.get('scambi_midseason', []) + torneo.offseason_log_data.get('scambi', [])
        for s_str in scambi_list:
            if isinstance(s_str, str) and s_str not in save_trade_lines:
                save_trade_lines.append(s_str)

    def parse_item(item):
        item = item.strip()
        if not item: return None, None
        item_clean = item.strip(' [].')
        if any(k in item_clean for k in ['R1-', 'R2-', 'Pick', '200', '201', 'scelta', 'Scelta', 'round', 'Round']):
            return None, item_clean
        if '(' in item_clean:
            p_name = item_clean.split('(')[0].strip()
            inside = item_clean.split('(')[1].replace(')', '').strip()
            tokens = [t.strip() for t in inside.split(',')]
            ovr_val = 75
            ruolo_val = 'SG'
            salary_val = 0.0
            for tok in tokens:
                tok_clean = tok.replace('$', '').replace('M', '').replace('m', '').strip()
                if tok.isdigit():
                    ovr_val = int(tok)
                elif tok.upper() in ['PG', 'SG', 'SF', 'PF', 'C']:
                    ruolo_val = tok.upper()
                elif '$' in tok or 'M' in tok:
                    try:
                        salary_val = float(tok_clean)
                    except ValueError:
                        pass
                elif tok_clean.isdigit():
                    ovr_val = int(tok_clean)
            return {'name': p_name, 'ovr': ovr_val, 'ruolo': ruolo_val, 'salary': salary_val}, None
        else:
            return {'name': item_clean, 'ovr': 75, 'ruolo': 'SG', 'salary': 0.0}, None

    def parse_assets(ast_str):
        players, picks = [], []
        clean_ast = ast_str.strip(' [].')
        if not clean_ast:
            return players, picks
        items = re.split(r',\s*(?![^()]*\))', clean_ast)
        for item in items:
            item = item.strip()
            if not item: continue
            pl, pk = parse_item(item)
            if pl: players.append(pl)
            if pk: picks.append(pk)
        return players, picks

    def get_team_pre_trade_record(sq):
        if not sq:
            return 20, 20, 0.5
        tot = sq.vittorie + sq.sconfitte
        if tot <= 42:
            # At or before midseason: all games played up to deadline are PRE-TRADE
            w = sq.vittorie
            l = sq.sconfitte
            wp = round(w / max(1, tot), 3) if tot > 0 else 0.5
            return w, l, wp
        else:
            # Past midseason: deadline happened at game 41
            w = int(round((sq.vittorie / tot) * 41))
            l = 41 - w
            wp = round(w / 41, 3)
            return w, l, wp

    def parse_3_team_trade(s_line, season_num, line_id):
        team_entries = []
        reason = s_line.split("Reason:")[-1].strip() if "Reason:" in s_line else "Triangular Blockbuster"
        clean_line = s_line.replace('🔥', '')
        if ']' in clean_line and ('[3-TEAM' in clean_line or '[Season' in clean_line or '[Stagione' in clean_line):
            clean_line = clean_line.split(']', 1)[-1]
            if '[3-TEAM' in clean_line:
                clean_line = clean_line.split(']', 1)[-1]
                
        segments = clean_line.split('|')
        for seg in segments:
            seg = seg.strip()
            if not seg: continue
            if "gets:" in seg or "absorbs:" in seg:
                splitter = "gets:" if "gets:" in seg else "absorbs:"
                t_raw, rest = seg.split(splitter, 1)
                t_name = t_raw.strip(' [].:')
                
                if 'gets' in rest:
                    abs_part, get_part = rest.split('gets', 1)
                    pl1, pk1 = parse_assets(abs_part)
                    pl2, pk2 = parse_assets(get_part)
                    pl, pk = pl1 + pl2, pk1 + pk2
                else:
                    pl, pk = parse_assets(rest)
                    
                sq = next((s for s in torneo.squadre if s.nome.lower() == t_name.lower() or t_name.lower() in s.nome.lower()), None)
                w_pre, l_pre, w_pct_pre = get_team_pre_trade_record(sq)

                team_entries.append({
                    "team_name": sq.nome if sq else t_name,
                    "wins_pre": w_pre,
                    "losses_pre": l_pre,
                    "win_pct_pre": w_pct_pre,
                    "ppg_pre": 100.0,
                    "opp_ppg_pre": 100.0,
                    "off_rtg_pre": 105.0,
                    "def_rtg_pre": 105.0,
                    "net_rtg_pre": 0.0,
                    "players_sent": [],
                    "picks_sent": [],
                    "players_received": pl,
                    "picks_received": pk
                })
                
        if len(team_entries) >= 2:
            return {
                "id": line_id,
                "season": season_num,
                "game_day": 35,
                "type": "3-Team Blockbuster",
                "reason": reason,
                "date_recorded": "Regular Season",
                "teams": team_entries
            }
        return None

    # Parse and merge historical trade lines
    for idx, s_line in enumerate(save_trade_lines):
        line_id = f"hist_trade_{idx+1}"
        if line_id in existing_ids:
            continue

        season_num = torneo.season_number
        # "[Stagione N | ...]" is the legacy (Italian) prefix found in old saves' trade logs
        season_match = re.search(r"\[(?:Season|Stagione) (\d+)", s_line)
        if season_match:
            season_num = int(season_match.group(1))

        if "<-->" in s_line:
            clean = s_line
            reason = "Market Deal"
            if "Reason:" in clean:
                parts_r = clean.split("Reason:", 1)
                clean = parts_r[0].strip()
                reason = parts_r[1].strip()

            if "TRADE:" in clean:
                clean = clean.split("TRADE:", 1)[1].strip()
            elif "SCAMBIO:" in clean:  # legacy (Italian) log prefix, kept for old saves
                clean = clean.split("SCAMBIO:", 1)[1].strip()
            elif "] " in clean:
                clean = clean.split("] ", 1)[-1].strip()

            parts = clean.split("<-->")
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()

                def _split_side(side, default_name):
                    # "sends" is the current verb; "cede" is the legacy Italian one found in old saves
                    m = re.search(r"\b(?:sends|cede)\b", side)
                    return (side[:m.start()].strip(" []"), side[m.end():]) if m else (default_name, "")

                t1_name, t1_ast = _split_side(left, "Team A")
                t2_name, t2_ast = _split_side(right, "Team B")

                t1_players, t1_picks = parse_assets(t1_ast)
                t2_players, t2_picks = parse_assets(t2_ast)

                s1 = next((s for s in torneo.squadre if s.nome.lower() == t1_name.lower() or t1_name.lower() in s.nome.lower()), None)
                s2 = next((s for s in torneo.squadre if s.nome.lower() == t2_name.lower() or t2_name.lower() in s.nome.lower()), None)

                t1_w_pre, t1_l_pre, t1_wp_pre = get_team_pre_trade_record(s1)
                t2_w_pre, t2_l_pre, t2_wp_pre = get_team_pre_trade_record(s2)

                trade_entry = {
                    "id": line_id,
                    "season": season_num,
                    "game_day": 35,
                    "type": "2-Team",
                    "reason": reason,
                    "date_recorded": "Regular Season",
                    "teams": [
                        {
                            "team_name": s1.nome if s1 else t1_name,
                            "wins_pre": t1_w_pre,
                            "losses_pre": t1_l_pre,
                            "win_pct_pre": t1_wp_pre,
                            "ppg_pre": 100.0,
                            "opp_ppg_pre": 100.0,
                            "off_rtg_pre": 105.0,
                            "def_rtg_pre": 105.0,
                            "net_rtg_pre": 0.0,
                            "players_sent": t1_players,
                            "picks_sent": t1_picks,
                            "players_received": t2_players,
                            "picks_received": t2_picks
                        },
                        {
                            "team_name": s2.nome if s2 else t2_name,
                            "wins_pre": t2_w_pre,
                            "losses_pre": t2_l_pre,
                            "win_pct_pre": t2_wp_pre,
                            "ppg_pre": 100.0,
                            "opp_ppg_pre": 100.0,
                            "off_rtg_pre": 105.0,
                            "def_rtg_pre": 105.0,
                            "net_rtg_pre": 0.0,
                            "players_sent": t2_players,
                            "picks_sent": t2_picks,
                            "players_received": t1_players,
                            "picks_received": t1_picks
                        }
                    ]
                }
                sig = get_trade_signature(trade_entry)
                if sig not in existing_signatures:
                    raw_trades.append(trade_entry)
                    existing_signatures.add(sig)

        elif "3-TEAM" in s_line or "3-SQUADRE" in s_line or "BLOCKBUSTER" in s_line or "gets:" in s_line:
            res_3 = parse_3_team_trade(s_line, season_num, line_id)
            if res_3:
                sig = get_trade_signature(res_3)
                if sig not in existing_signatures:
                    raw_trades.append(res_3)
                    existing_signatures.add(sig)

    # Compute live impact deltas
    trade_impact_res = []
    for tr in reversed(raw_trades):
        t_teams = tr.get('teams', [])
        enhanced_teams = []
        best_delta = -999.0
        winner_team_name = ""

        is_curr_season = (tr.get('season', 1) == torneo.season_number)

        for t_entry in t_teams:
            t_name = t_entry.get('team_name', '')
            actual_team = next((s for s in torneo.squadre if s.nome.lower() == t_name.lower() or t_name.lower() in s.nome.lower()), None)
            
            wins_pre = t_entry.get('wins_pre', 0)
            losses_pre = t_entry.get('losses_pre', 0)
            win_pct_pre = t_entry.get('win_pct_pre', 0.5)
            net_rtg_pre = t_entry.get('net_rtg_pre', 0.0)
            ppg_pre = t_entry.get('ppg_pre', 100.0)

            if is_curr_season and actual_team:
                total_games_now = actual_team.vittorie + actual_team.sconfitte
                games_pre = wins_pre + losses_pre
                games_post = max(0, total_games_now - games_pre)
                wins_post = max(0, actual_team.vittorie - wins_pre)
                losses_post = max(0, actual_team.sconfitte - losses_pre)
                win_pct_post = round(wins_post / games_post, 3) if games_post > 0 else win_pct_pre
                delta_win_pct = round((win_pct_post - win_pct_pre) * 100, 1)

                from trades.trade_finder import team_form
                form_now = team_form(torneo, actual_team)
                curr_net = form_now["net_rtg"]
                delta_net_rtg = round(curr_net - net_rtg_pre, 1) if games_post > 0 else 0.0
                curr_ppg = form_now["ppg"] if total_games_now > 0 else ppg_pre
                delta_ppg = round(curr_ppg - ppg_pre, 1) if games_post > 0 else 0.0
            else:
                # Historical finalized or fallback
                games_post = t_entry.get('games_post', 0)
                wins_post = t_entry.get('wins_post', 0)
                losses_post = t_entry.get('losses_post', 0)
                win_pct_post = t_entry.get('win_pct_post', win_pct_pre)
                delta_win_pct = t_entry.get('delta_win_pct', 0.0)
                delta_net_rtg = t_entry.get('delta_net_rtg', 0.0)
                delta_ppg = t_entry.get('delta_ppg', 0.0)

            # Acquired player stats on new team
            players_rec_stats = []
            for p_rec in t_entry.get('players_received', []):
                p_name = p_rec.get('name', '') if isinstance(p_rec, dict) else str(p_rec)
                found_p = next((p for s in torneo.squadre for p in s.roster if p.nome.lower() == p_name.lower()), None)
                if found_p and hasattr(found_p, 'season_stats'):
                    st = found_p.season_stats
                    gp_p = getattr(st, 'partite_giocate', 0)
                    ppg_p = round(getattr(st, 'punti', 0) / max(1, gp_p), 1)
                    rpg_p = round(getattr(st, 'rimbalzi', 0) / max(1, gp_p), 1)
                    apg_p = round(getattr(st, 'assist', 0) / max(1, gp_p), 1)
                    players_rec_stats.append({
                        "name": p_name,
                        "ovr": found_p.ovr,
                        "ruolo": found_p.ruolo,
                        "gp": gp_p,
                        "ppg": ppg_p,
                        "rpg": rpg_p,
                        "apg": apg_p
                    })
                elif isinstance(p_rec, dict):
                    players_rec_stats.append(p_rec)
                else:
                    players_rec_stats.append({"name": p_rec, "ovr": 75, "ruolo": "SG"})

            # Determine Verdict
            if games_post == 0:
                verdict = "⏳ Recent (Monitoring started, 0 games post-trade)"
                verdict_type = "recent"
            elif games_post in [1, 2, 3]:
                verdict = f"⏱️ Early Returns ({wins_post}-{losses_post}, {delta_win_pct:+}%)"
                verdict_type = "positive" if delta_win_pct > 0 else ("negative" if delta_win_pct < 0 else "neutral")
            elif delta_win_pct >= 10.0:
                verdict = f"🚀 Immediate Boost (+{delta_win_pct}%)"
                verdict_type = "boost"
            elif delta_win_pct >= 3.0:
                verdict = f"📈 Positive Impact (+{delta_win_pct}%)"
                verdict_type = "positive"
            elif delta_win_pct <= -10.0:
                verdict = f"📉 Post-Trade Collapse ({delta_win_pct}%)"
                verdict_type = "negative"
            elif delta_win_pct <= -3.0:
                verdict = f"⚠️ Negative Impact ({delta_win_pct}%)"
                verdict_type = "warning"
            elif t_entry.get('picks_received') and not t_entry.get('players_received'):
                verdict = "🧱 Rebuild & Accumulo Scelte"
                verdict_type = "rebuild"
            else:
                verdict = f"⚖️ Steady Performance ({delta_win_pct:+}%)"
                verdict_type = "neutral"

            if delta_win_pct > best_delta and delta_win_pct > 0 and games_post >= 1:
                best_delta = delta_win_pct
                winner_team_name = t_name

            enhanced_teams.append({
                **t_entry,
                "team_name": actual_team.nome if actual_team else t_name,
                "games_post": games_post,
                "wins_post": wins_post,
                "losses_post": losses_post,
                "win_pct_post": win_pct_post,
                "delta_win_pct": delta_win_pct,
                "delta_net_rtg": delta_net_rtg,
                "delta_ppg": delta_ppg,
                "verdict": verdict,
                "verdict_type": verdict_type,
                "players_received_stats": players_rec_stats
            })

        # GM notebook: the structured motive, public part only (old records and text-only trades have none)
        motive_fields = {}
        if tr.get('motives'):
            from trades.motive import SideMotive
            motive_fields = {
                "why": tr.get('why', ''),
                "trade_type": tr.get('trade_type', ''),
                "phase": tr.get('phase', ''),
                "motives": [SideMotive.from_dict(m).to_dict(public=True) for m in tr['motives'] if isinstance(m, dict)],
            }

        # Computation of the Trade Grades v2.1 (A+ to F) and editorial verdict
        try:
            from core.trade_grades import calculate_trade_grades
            graded_trade = calculate_trade_grades({
                "id": tr.get('id', ''),
                "season": tr.get('season', 1),
                "game_day": tr.get('game_day', 1),
                "type": tr.get('type', '2-Team'),
                "reason": tr.get('reason', ''),
                "date_recorded": tr.get('date_recorded', ''),
                "teams": enhanced_teams
            }, torneo)
            graded_trade.update(motive_fields)
            trade_impact_res.append(graded_trade)
        except Exception as e:
            trade_impact_res.append({
                "id": tr.get('id', ''),
                "season": tr.get('season', 1),
                "game_day": tr.get('game_day', 1),
                "type": tr.get('type', '2-Team'),
                "reason": tr.get('reason', ''),
                "date_recorded": tr.get('date_recorded', ''),
                "winner_team_name": winner_team_name,
                "teams": enhanced_teams,
                **motive_fields
            })

    return trade_impact_res


@app.route('/api/trade-requests', methods=['GET'])
def get_trade_requests_api():
    """League-wide list of players who asked to be traded (core/front_office/trade_requests.py)."""
    if not SIMULATION_TOURNAMENT:
        return jsonify({"requests": []})
    return jsonify({"requests": trade_requests.request_list(SIMULATION_TOURNAMENT)})


@app.route('/api/trade-history', methods=['GET'])
def get_trade_history_api():
    """
    Returns full structured trade history with editorial grades and asset exchanges.
    """
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"trades": [], "current_season": 1})

    try:
        return jsonify({
            "current_season": SIMULATION_TOURNAMENT.season_number,
            "trades": _trade_impact_list(SIMULATION_TOURNAMENT)
        })
    except Exception as e:
        main_log.error(f"Error fetching trade history: {e}")
        return jsonify({"trades": [], "current_season": 1, "error": str(e)})


@app.route('/api/export/available-seasons', methods=['GET'])
def get_available_export_seasons():
    """
    Returns the list of available seasons for data export (completed seasons and active season).
    """
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"seasons": [], "default_season": 1, "current_season": 1})

    from core.history_view import parse_season, season_years, year_for

    torneo = SIMULATION_TOURNAMENT
    cur_season = torneo.season_number
    anno_corrente = getattr(torneo, 'anno_corrente', 2025)
    starting_year = getattr(torneo, 'starting_year', anno_corrente - (cur_season - 1))
    # Games played per team (the sum over all teams counts each game twice and reads as 2460 GP).
    cur_gp = round(sum(s.vittorie + s.sconfitte for s in torneo.squadre) / max(len(torneo.squadre), 1))

    history_file = get_historical_file_path("league_history.json")
    careers_file = get_historical_file_path("player_careers.json")

    hist_seasons = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                for item in json.load(f):
                    s_num = item.get("stagione")
                    if s_num:
                        hist_seasons[s_num] = item
        except Exception:
            pass

    career_seasons = set()
    if os.path.exists(careers_file):
        try:
            with open(careers_file, 'r', encoding='utf-8') as f:
                for entries in json.load(f).values():
                    for e in entries:
                        s_num = parse_season(e.get("stagione"))
                        if s_num:
                            career_seasons.add(s_num)
        except Exception:
            pass

    all_season_nums = sorted(list(set(list(hist_seasons.keys()) + list(career_seasons) + [cur_season])))
    years = season_years(list(hist_seasons.values()))

    completed_season_nums = [s for s, h in hist_seasons.items() if h.get("campione") and h.get("campione") != "Playoff non disputati"]
    max_completed = max(completed_season_nums) if completed_season_nums else None

    seasons_data = []
    for s_num in all_season_nums:
        cal_year = year_for(s_num, years, starting_year)
        label = f"{cal_year}-{str(cal_year + 1)[-2:]}"
        is_cur = (s_num == cur_season)
        hist_item = hist_seasons.get(s_num, {})
        champion = hist_item.get("campione") if hist_item else None
        
        has_champion = bool(champion and champion != "Playoff non disputati")
        is_completed = (s_num < cur_season) or has_champion
            
        seasons_data.append({
            "season": s_num,
            "year": cal_year,
            "label": label,
            "is_completed": is_completed,
            "is_current": is_cur,
            "gp": cur_gp if is_cur else 82,
            "champion": champion if has_champion else None
        })

    default_season = cur_season if cur_gp > 0 else (max_completed if max_completed else cur_season)

    return jsonify({
        "seasons": seasons_data,
        "default_season": default_season,
        "current_season": cur_season
    })


@app.route('/api/export/season', methods=['GET'])
def export_season_data():
    """
    Exports comprehensive season data in CSV or JSON format.
    Query params:
      - format: 'json' or 'csv' (default: 'json')
      - category: 'all', 'players', 'standings', 'team_summaries', 'awards', 'rosters', 'trades' (default: 'all')
      - season: 'all', 'current', or integer (e.g. '1', '2', '3')
    """
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    import csv
    import io
    import zipfile

    torneo = SIMULATION_TOURNAMENT
    cur_season = torneo.season_number
    anno_corrente = getattr(torneo, 'anno_corrente', 2025)
    starting_year = getattr(torneo, 'starting_year', anno_corrente - (cur_season - 1))
    cur_gp = sum(s.vittorie + s.sconfitte for s in torneo.squadre)

    export_format = request.args.get('format', 'json').lower()
    category = request.args.get('category', 'all').lower()
    season_param = request.args.get('season', 'default').strip().lower()

    history_file = get_historical_file_path("league_history.json")
    careers_file = get_historical_file_path("player_careers.json")

    hist_data = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                hist_data = json.load(f)
        except Exception:
            hist_data = []
    history_by_season = {item['stagione']: item for item in hist_data if 'stagione' in item}

    careers_data = {}
    if os.path.exists(careers_file):
        try:
            with open(careers_file, 'r', encoding='utf-8') as f:
                careers_data = json.load(f)
        except Exception:
            careers_data = {}

    all_completed_seasons = sorted(list(set(
        list(history_by_season.keys()) + 
        [e.get('stagione') for entries in careers_data.values() for e in entries if e.get('stagione')]
    )))
    max_completed = all_completed_seasons[-1] if all_completed_seasons else None

    # Determine target season
    is_multi_season = False
    if season_param == 'all':
        is_multi_season = True
        target_season = 'all'
        target_year = starting_year
        export_label = "all_seasons_history"
    elif season_param in ['default', '', 'current']:
        if cur_gp > 0:
            target_season = cur_season
            target_year = anno_corrente
            export_label = f"season_{cur_season}_{target_year}"
        elif max_completed is not None:
            target_season = max_completed
            target_year = starting_year + (max_completed - 1)
            export_label = f"season_{max_completed}_{target_year}"
        else:
            target_season = cur_season
            target_year = anno_corrente
            export_label = f"season_{cur_season}_{target_year}"
    else:
        try:
            target_season = int(season_param)
            target_year = starting_year + (target_season - 1)
            export_label = f"season_{target_season}_{target_year}"
        except ValueError:
            target_season = cur_season
            target_year = anno_corrente
            export_label = f"season_{cur_season}_{target_year}"

    # Build Player Name & Role lookup map from active tournament objects
    player_lookup = {}
    for sq in torneo.squadre:
        for p in sq.roster:
            p_id = p.nome.replace(" ", "-").lower()
            player_lookup[p_id] = {
                "nome": p.nome,
                "ruolo": p.ruolo,
                "eta": p.eta,
                "ovr": p.ovr,
                "pot": p.potenziale,
                "team": sq.nome
            }
    for p in getattr(torneo, 'free_agents_pool', []):
        p_id = p.nome.replace(" ", "-").lower()
        if p_id not in player_lookup:
            player_lookup[p_id] = {
                "nome": p.nome,
                "ruolo": p.ruolo,
                "eta": p.eta,
                "ovr": p.ovr,
                "pot": p.potenziale,
                "team": "Free Agent"
            }
    for p in getattr(torneo, 'giocatori_ritirati', []):
        p_id = p.nome.replace(" ", "-").lower()
        if p_id not in player_lookup:
            player_lookup[p_id] = {
                "nome": p.nome,
                "ruolo": p.ruolo,
                "eta": p.eta,
                "ovr": p.ovr,
                "pot": getattr(p, 'potenziale', p.ovr),
                "team": "Retired"
            }

    AWARD_ORDER = [
        "Champion", "Finals MVP", "MVP", "Defensive Player of the Year",
        "Rookie of the Year", "Sixth Man of the Year", "Most Improved Player",
        "All-NBA First Team", "All-NBA Second Team", "All-NBA Third Team",
        "All-Defensive Team", "All-Rookie Team", "All-Star Starter",
        "All-Star Reserve", "All-Star MVP", "3PT Contest Winner", "Dunk Contest Winner"
    ]

    AWARD_MAP = {
        "MVP": "MVP", "Finals MVP": "Finals MVP", "DPOY": "Defensive Player of the Year",
        "6th Man": "Sixth Man of the Year", "ROY": "Rookie of the Year", "MIP": "Most Improved Player",
        "All-NBA 1st": "All-NBA First Team", "All-NBA 2nd": "All-NBA Second Team",
        "All-NBA 3rd": "All-NBA Third Team", "All-Defensive": "All-Defensive Team",
        "All-Rookie": "All-Rookie Team", "All-Star Starter": "All-Star Starter",
        "All-Star": "All-Star Reserve", "All-Star MVP": "All-Star MVP",
        "3PT Contest Winner": "3PT Contest Winner", "Dunk Contest Winner": "Dunk Contest Winner"
    }

    # 1. Awards & All-Star History Data
    awards_rows = []
    seasons_for_awards = all_completed_seasons if is_multi_season else ([target_season] if isinstance(target_season, int) else [cur_season])
    if cur_season not in seasons_for_awards and is_multi_season:
        seasons_for_awards.append(cur_season)

    for s_num in sorted(seasons_for_awards):
        cal_yr = starting_year + (s_num - 1)
        s_lbl = f"{cal_yr}-{str(cal_yr+1)[-2:]}"
        hist_entry = history_by_season.get(s_num, {})

        # Check champion and finals MVP
        champ_name = hist_entry.get("campione")
        if not champ_name and s_num == cur_season and torneo.campione:
            champ_name = torneo.campione.nome
        if champ_name and champ_name != "Playoff non disputati":
            awards_rows.append({
                "Season": f"Season {s_num}",
                "Year": s_lbl,
                "Award": "Champion",
                "Recipient": champ_name,
                "Team": champ_name,
                "Role": "Team",
                "Details": "NBA Champions"
            })

        fmvp_name = hist_entry.get("mvp_finali")
        if not fmvp_name and s_num == cur_season and torneo.finals_mvp:
            fmvp_name = torneo.finals_mvp.nome
        if fmvp_name and fmvp_name != "N/A":
            awards_rows.append({
                "Season": f"Season {s_num}",
                "Year": s_lbl,
                "Award": "Finals MVP",
                "Recipient": fmvp_name,
                "Team": champ_name or "N/A",
                "Role": "Player",
                "Details": "Finals Most Valuable Player"
            })

        # Individual Awards
        s_awards_list = []
        for p_id, entries in careers_data.items():
            info = player_lookup.get(p_id)
            p_display = info["nome"] if info else p_id.replace('-', ' ').title()
            for e in entries:
                if e.get('stagione') == s_num:
                    t_name = e.get('squadra', 'N/A')
                    stats = e.get('stats_rs', {})
                    stat_str = f"{stats.get('ppg', 0)} PPG, {stats.get('rpg', 0)} RPG, {stats.get('apg', 0)} APG"
                    for aw in e.get('premi', []):
                        cat = AWARD_MAP.get(aw, aw)
                        if cat == "Finals MVP":
                            continue
                        s_awards_list.append({
                            "Season": f"Season {s_num}",
                            "Year": s_lbl,
                            "Award": cat,
                            "Recipient": p_display,
                            "Team": t_name,
                            "Role": "Player",
                            "Details": stat_str
                        })

        # Check for awards in hist_entry not captured in careers
        hist_premi = hist_entry.get('premi', {})
        existing_aw_names = {x['Award']: x['Recipient'] for x in s_awards_list}
        if hist_premi.get('roy') and hist_premi['roy'] != "N/A" and "Rookie of the Year" not in existing_aw_names:
            s_awards_list.append({
                "Season": f"Season {s_num}",
                "Year": s_lbl,
                "Award": "Rookie of the Year",
                "Recipient": hist_premi['roy'],
                "Team": "N/A",
                "Role": "Player",
                "Details": "Rookie of the Year"
            })

        def get_order(item):
            aw = item["Award"]
            try: return AWARD_ORDER.index(aw)
            except ValueError: return 99

        s_awards_list.sort(key=lambda x: (get_order(x), x["Recipient"]))
        awards_rows.extend(s_awards_list)

    # 2. Standings Data
    standings_rows = []
    if not is_multi_season and target_season == cur_season and cur_gp > 0:
        for sq in sorted(torneo.squadre, key=lambda s: (-s.vittorie, s.sconfitte)):
            gp = sq.vittorie + sq.sconfitte
            pts_for = getattr(sq, 'punti_fatti_stagione', getattr(sq, 'punti_fatti', 0))
            pts_against = getattr(sq, 'punti_subiti_stagione', getattr(sq, 'punti_subiti', 0))
            w_pct = round(sq.vittorie / max(1, gp), 3) if gp > 0 else 0.0
            ppg = round(pts_for / max(1, gp), 1) if gp > 0 else 0.0
            oppg = round(pts_against / max(1, gp), 1) if gp > 0 else 0.0
            diff = round(ppg - oppg, 1)
            standings_rows.append({
                "Season": f"Season {cur_season}",
                "Year": f"{anno_corrente}-{str(anno_corrente+1)[-2:]}",
                "Team": sq.nome,
                "Conference": getattr(sq, 'conference', 'N/A'),
                "Wins": sq.vittorie,
                "Losses": sq.sconfitte,
                "Win_Pct": f"{w_pct:.3f}",
                "Games_Played": gp,
                "PPG": ppg,
                "OPPG": oppg,
                "Point_Diff": diff,
                "Payroll_M": round(sq.payroll, 2),
                "Cap_Space_M": round(sq.salary_cap_space, 2)
            })
    else:
        # Load from history snapshot or compute from player careers
        seasons_for_standings = all_completed_seasons if is_multi_season else ([target_season] if isinstance(target_season, int) else [cur_season])
        for s_num in sorted(seasons_for_standings):
            cal_yr = starting_year + (s_num - 1)
            s_lbl = f"{cal_yr}-{str(cal_yr+1)[-2:]}"
            hist_entry = history_by_season.get(s_num, {})
            if hist_entry.get("standings"):
                for row in hist_entry["standings"]:
                    standings_rows.append({
                        "Season": f"Season {s_num}",
                        "Year": s_lbl,
                        "Team": row.get("team"),
                        "Conference": row.get("conference", "N/A"),
                        "Wins": row.get("wins", 0),
                        "Losses": row.get("losses", 0),
                        "Win_Pct": f"{row.get('win_pct', 0.0):.3f}",
                        "Games_Played": row.get("gp", 0),
                        "PPG": row.get("ppg", 0.0),
                        "OPPG": row.get("oppg", 0.0),
                        "Point_Diff": row.get("diff", 0.0),
                        "Payroll_M": "N/A",
                        "Cap_Space_M": "N/A"
                    })
            else:
                # Reconstruct team summaries from careers_data
                team_points = {}
                team_games = {}
                for entries in careers_data.values():
                    for e in entries:
                        if e.get("stagione") == s_num:
                            t = e.get("squadra", "Unknown")
                            gp = e.get("gp", 0)
                            ppg = e.get("stats_rs", {}).get("ppg", 0.0)
                            team_points[t] = team_points.get(t, 0.0) + (ppg * gp)
                            team_games[t] = max(team_games.get(t, 0), gp)

                for t, tot_pts in team_points.items():
                    gp = team_games.get(t, 82)
                    ppg = round(tot_pts / max(1, gp), 1)
                    standings_rows.append({
                        "Season": f"Season {s_num}",
                        "Year": s_lbl,
                        "Team": t,
                        "Conference": "N/A",
                        "Wins": "Completed",
                        "Losses": "Completed",
                        "Win_Pct": "1.000" if (hist_entry.get("campione") == t) else "N/A",
                        "Games_Played": gp,
                        "PPG": ppg,
                        "OPPG": "N/A",
                        "Point_Diff": "N/A",
                        "Payroll_M": "N/A",
                        "Cap_Space_M": "N/A"
                    })

    # 3. Team Per-Game Summaries (matching stampa_report_squadre_fine_stagione)
    team_summary_rows = []
    if not is_multi_season and target_season == cur_season and cur_gp > 0:
        pace_est_base = round(100.0 * (torneo.get_era_pace_factor() if hasattr(torneo, 'get_era_pace_factor') else 0.95), 1)
        for sq in sorted(torneo.squadre, key=lambda s: s.vittorie, reverse=True):
            gp = sq.vittorie + sq.sconfitte
            if gp == 0: continue
            pts_for = getattr(sq, 'punti_fatti_stagione', getattr(sq, 'punti_fatti', 0))
            pts_against = getattr(sq, 'punti_subiti_stagione', getattr(sq, 'punti_subiti', 0))
            ppg = round(pts_for / gp, 1)
            oppg = round(pts_against / gp, 1)
            diff = round(ppg - oppg, 1)
            possessi = gp * pace_est_base
            off_rtg = round((pts_for / possessi) * 100, 1) if possessi > 0 else 0.0
            def_rtg = round((pts_against / possessi) * 100, 1) if possessi > 0 else 0.0
            fg_att = round(sum(p.season_stats.tiri_tentati_2 + p.season_stats.tiri_tentati_3 for p in sq.roster) / gp, 1)
            p3a = round(sum(p.season_stats.tiri_tentati_3 for p in sq.roster) / gp, 1)
            apg = round(sum(p.season_stats.assist for p in sq.roster) / gp, 1)
            rpg = round(sum(p.season_stats.rimbalzi for p in sq.roster) / gp, 1)
            team_summary_rows.append({
                "Season": f"Season {cur_season}",
                "Year": f"{anno_corrente}-{str(anno_corrente+1)[-2:]}",
                "Team": sq.nome,
                "Conference": getattr(sq, 'conference', 'N/A'),
                "Record": f"{sq.vittorie}-{sq.sconfitte}",
                "Wins": sq.vittorie,
                "Losses": sq.sconfitte,
                "Win_Pct": f"{sq.vittorie / gp:.3f}",
                "PPG": ppg,
                "Opp_PPG": oppg,
                "Point_Diff": diff,
                "Off_Rating": off_rtg,
                "Def_Rating": def_rtg,
                "FGA_PG": fg_att,
                "3PA_PG": p3a,
                "APG": apg,
                "RPG": rpg
            })
    else:
        seasons_for_teams = all_completed_seasons if is_multi_season else ([target_season] if isinstance(target_season, int) else [cur_season])
        for s_num in sorted(seasons_for_teams):
            cal_yr = starting_year + (s_num - 1)
            s_lbl = f"{cal_yr}-{str(cal_yr+1)[-2:]}"
            hist_entry = history_by_season.get(s_num, {})
            if hist_entry.get("team_stats"):
                for row in hist_entry["team_stats"]:
                    team_summary_rows.append({
                        "Season": f"Season {s_num}",
                        "Year": s_lbl,
                        "Team": row.get("team"),
                        "Conference": row.get("conference", "N/A"),
                        "Record": row.get("record", f"{row.get('wins', 0)}-{row.get('losses', 0)}"),
                        "Wins": row.get("wins", 0),
                        "Losses": row.get("losses", 0),
                        "Win_Pct": f"{row.get('win_pct', 0.0):.3f}",
                        "PPG": row.get("ppg", 0.0),
                        "Opp_PPG": row.get("oppg", 0.0),
                        "Point_Diff": row.get("diff", 0.0),
                        "Off_Rating": row.get("off_rating", 0.0),
                        "Def_Rating": row.get("def_rating", 0.0),
                        "FGA_PG": row.get("fga", 0.0),
                        "3PA_PG": row.get("3pa", 0.0),
                        "APG": row.get("apg", 0.0),
                        "RPG": row.get("rpg", 0.0)
                    })
            else:
                # Aggregate per-team averages from player careers
                team_data = {}
                for entries in careers_data.values():
                    for e in entries:
                        if e.get("stagione") == s_num:
                            t = e.get("squadra", "Unknown")
                            if t not in team_data:
                                team_data[t] = {"pts": 0.0, "reb": 0.0, "ast": 0.0, "gp": 0}
                            rs = e.get("stats_rs", {})
                            gp = e.get("gp", 0)
                            team_data[t]["pts"] += rs.get("ppg", 0.0) * gp
                            team_data[t]["reb"] += rs.get("rpg", 0.0) * gp
                            team_data[t]["ast"] += rs.get("apg", 0.0) * gp
                            team_data[t]["gp"] = max(team_data[t]["gp"], gp)

                for t, data in sorted(team_data.items()):
                    gp = max(1, data["gp"])
                    team_summary_rows.append({
                        "Season": f"Season {s_num}",
                        "Year": s_lbl,
                        "Team": t,
                        "Conference": "N/A",
                        "Record": "Completed",
                        "Wins": "Completed",
                        "Losses": "Completed",
                        "Win_Pct": "1.000" if (hist_entry.get("campione") == t) else "N/A",
                        "PPG": round(data["pts"] / gp, 1),
                        "Opp_PPG": "N/A",
                        "Point_Diff": "N/A",
                        "Off_Rating": "N/A",
                        "Def_Rating": "N/A",
                        "FGA_PG": "N/A",
                        "3PA_PG": "N/A",
                        "APG": round(data["ast"] / gp, 1),
                        "RPG": round(data["reb"] / gp, 1)
                    })

    # 4. Player Statistics Data (Per-Game Averages)
    player_rows = []
    if not is_multi_season and target_season == cur_season and cur_gp > 0:
        for sq in sorted(torneo.squadre, key=lambda s: s.nome):
            for p in sorted(sq.roster, key=lambda pl: (pl.season_stats.punti / max(1, pl.season_stats.partite_giocate)), reverse=True):
                s = getattr(p, 'season_stats', None)
                gp = s.partite_giocate if s else 0
                pts = round(s.punti / max(1, gp), 1) if s and gp > 0 else 0.0
                reb = round(s.rimbalzi / max(1, gp), 1) if s and gp > 0 else 0.0
                ast = round(s.assist / max(1, gp), 1) if s and gp > 0 else 0.0
                stl = round(s.steals / max(1, gp), 1) if s and gp > 0 else 0.0
                blk = round(s.blocks / max(1, gp), 1) if s and gp > 0 else 0.0
                tov = round(s.turnover / max(1, gp), 1) if s and gp > 0 else 0.0
                minutes = round(s.minuti_giocati / max(1, gp), 1) if s and gp > 0 else 0.0
                po = getattr(p, 'playoff_stats', None)
                po_gp = po.partite_giocate if po else 0
                po_pts = round(po.punti / max(1, po_gp), 1) if po and po_gp > 0 else 0.0
                player_rows.append({
                    "Season": f"Season {cur_season}",
                    "Year": f"{anno_corrente}-{str(anno_corrente+1)[-2:]}",
                    "Team": sq.nome,
                    "Player": p.nome,
                    "Position": p.ruolo,
                    "Age": p.eta,
                    "OVR": p.ovr,
                    "POT": p.potenziale,
                    "GP": gp,
                    "MIN_PG": minutes,
                    "PPG": pts,
                    "RPG": reb,
                    "APG": ast,
                    "SPG": stl,
                    "BPG": blk,
                    "TOV_PG": tov,
                    "FG_Pct": s.fg_pct if s else 0.0,
                    "3P_Pct": s.three_pct if s else 0.0,
                    "FT_Pct": s.ft_pct if s else 0.0,
                    "Playoff_GP": po_gp,
                    "Playoff_PPG": po_pts,
                    "Awards": ", ".join(getattr(p, 'premi', []) or [])
                })
    else:
        # Load from player_careers.json
        seasons_for_players = all_completed_seasons if is_multi_season else ([target_season] if isinstance(target_season, int) else [cur_season])
        for p_id, entries in careers_data.items():
            info = player_lookup.get(p_id)
            p_display = info["nome"] if info else p_id.replace('-', ' ').title()
            p_ruolo = info["ruolo"] if info else "N/A"
            p_ovr = info["ovr"] if info else "N/A"
            p_pot = info["pot"] if info else "N/A"

            for e in entries:
                s_num = e.get("stagione")
                if s_num in seasons_for_players:
                    cal_yr = starting_year + (s_num - 1)
                    s_lbl = f"{cal_yr}-{str(cal_yr+1)[-2:]}"
                    rs = e.get("stats_rs", {})
                    po = e.get("stats_po") or {}
                    gp = e.get("gp", e.get("partite_giocate_rs", 0))
                    po_gp = e.get("gp_po", e.get("partite_giocate_po", 0))
                    player_rows.append({
                        "Season": f"Season {s_num}",
                        "Year": s_lbl,
                        "Team": e.get("squadra", "Free Agent"),
                        "Player": e.get("nome", p_display),
                        "Position": e.get("ruolo", p_ruolo),
                        "Age": e.get("eta", 0),
                        "OVR": p_ovr,
                        "POT": p_pot,
                        "GP": gp,
                        "MIN_PG": rs.get("min", rs.get("min_pg", 0.0)),
                        "PPG": rs.get("ppg", 0.0),
                        "RPG": rs.get("rpg", 0.0),
                        "APG": rs.get("apg", 0.0),
                        "SPG": rs.get("spg", 0.0),
                        "BPG": rs.get("bpg", 0.0),
                        "TOV_PG": rs.get("tov", 0.0),
                        "FG_Pct": rs.get("fg_pct", 0.0),
                        "3P_Pct": rs.get("three_pct", 0.0),
                        "FT_Pct": rs.get("ft_pct", 0.0),
                        "Playoff_GP": po_gp,
                        "Playoff_PPG": po.get("ppg", 0.0) if po else 0.0,
                        "Awards": ", ".join(e.get("premi", []))
                    })
        # Sort by Team then PPG descending
        player_rows.sort(key=lambda x: (x["Team"], -x["PPG"]))

    # 5. Rosters & Contracts Data
    contract_rows = []
    for sq in sorted(torneo.squadre, key=lambda s: s.nome):
        for p in sorted(sq.roster, key=lambda pl: pl.ovr, reverse=True):
            c = p.contract
            salary = c.salario_annuale if c else 0.0
            years = c.anni_rimanenti if c else 0
            opt = "Player Option (PO)" if (c and getattr(c, 'player_option', False)) else ("Team Option (TO)" if (c and getattr(c, 'team_option', False)) else "Guaranteed")
            contract_rows.append({
                "Team": sq.nome,
                "Player": p.nome,
                "Position": p.ruolo,
                "Age": p.eta,
                "OVR": p.ovr,
                "POT": p.potenziale,
                "Annual_Salary_M": round(salary, 2),
                "Years_Remaining": years,
                "Option_Type": opt,
                "Total_Remaining_M": round(salary * max(1, years), 2)
            })

    # 6. Trades Data
    trades_rows = []
    trade_file = get_historical_file_path("trades_history.txt")
    if not os.path.exists(trade_file) and os.path.exists("trades_history.txt"):
        trade_file = "trades_history.txt"
    if os.path.exists(trade_file):
        try:
            with open(trade_file, 'r', encoding='utf-8') as f:
                for idx, line in enumerate(f):
                    line_clean = line.strip()
                    if line_clean:
                        trades_rows.append({
                            "Trade_ID": idx + 1,
                            "Description": line_clean
                        })
        except Exception:
            pass

    def generate_csv_string(rows):
        if not rows:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    if export_format == 'json':
        export_payload = {
            "metadata": {
                "selected_season": target_season,
                "calendar_year": target_year,
                "export_label": export_label,
                "season_number_active": cur_season,
                "cba_mode": getattr(torneo, 'cba_mode', 'realistic'),
                "salary_cap": torneo.salary_cap,
                "salary_floor": getattr(torneo, 'salary_floor', 0.0),
                "luxury_tax": getattr(torneo, 'luxury_tax_threshold', 0.0),
                "first_apron": getattr(torneo, 'first_apron', 9999.0),
                "second_apron": getattr(torneo, 'second_apron', 9999.0),
                "exported_at": str(datetime.now())
            },
            "standings": standings_rows,
            "team_summaries": team_summary_rows,
            "player_stats": player_rows,
            "awards_and_all_star": awards_rows,
            "rosters_and_contracts": contract_rows,
            "trades": trades_rows
        }
        res_json = json.dumps(export_payload, indent=2, ensure_ascii=False)
        return Response(
            res_json,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename=nba_sim_{export_label}_export.json"}
        )

    if category == 'players':
        csv_data = generate_csv_string(player_rows)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=nba_sim_{export_label}_player_stats.csv"}
        )
    elif category == 'standings':
        csv_data = generate_csv_string(standings_rows)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=nba_sim_{export_label}_standings.csv"}
        )
    elif category == 'team_summaries':
        csv_data = generate_csv_string(team_summary_rows)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=nba_sim_{export_label}_team_summaries.csv"}
        )
    elif category == 'awards':
        csv_data = generate_csv_string(awards_rows)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=nba_sim_{export_label}_awards_all_star.csv"}
        )
    elif category == 'rosters':
        csv_data = generate_csv_string(contract_rows)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=nba_sim_{export_label}_rosters_contracts.csv"}
        )
    elif category == 'trades':
        csv_data = generate_csv_string(trades_rows)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=nba_sim_{export_label}_trades.csv"}
        )

    # All Categories -> ZIP Archive of CSV files
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(f"standings_{export_label}.csv", generate_csv_string(standings_rows))
        zip_file.writestr(f"player_stats_{export_label}.csv", generate_csv_string(player_rows))
        zip_file.writestr(f"team_summaries_{export_label}.csv", generate_csv_string(team_summary_rows))
        zip_file.writestr(f"awards_all_star_{export_label}.csv", generate_csv_string(awards_rows))
        zip_file.writestr(f"rosters_contracts_{export_label}.csv", generate_csv_string(contract_rows))
        if trades_rows:
            zip_file.writestr(f"trades_{export_label}.csv", generate_csv_string(trades_rows))
        
        summary_json = json.dumps({
            "selected_season": target_season,
            "export_label": export_label,
            "salary_cap": torneo.salary_cap,
            "total_teams": len(team_summary_rows) if team_summary_rows else len(torneo.squadre),
            "total_players": len(player_rows),
            "total_awards_recorded": len(awards_rows)
        }, indent=2)
        zip_file.writestr(f"{export_label}_summary.json", summary_json)

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"nba_sim_{export_label}_bundle.zip"
    )


@app.route('/api/contracts/apply-rules', methods=['POST', 'GET'])
def api_apply_contract_rules():
    """
    Applies the automated NBA logic (Years + PO / TO / Guaranteed Options)
    and optionally syncs the salaries to the active Salary Cap (default: True to scale the economy).
    """
    global SIMULATION_TOURNAMENT
    if not SIMULATION_TOURNAMENT:
        return jsonify({"error": "Simulation not initialized"}), 500

    sync_salaries = True
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        if 'sync_salaries' in data:
            sync_salaries = bool(data['sync_salaries'])
    else:
        if 'sync_salaries' in request.args:
            sync_salaries = request.args.get('sync_salaries', 'true').lower() in ['1', 'true', 'yes']

    updated_count = 0
    for s in getattr(SIMULATION_TOURNAMENT, 'squadre', []):
        for p in getattr(s, 'roster', []):
            if getattr(p, 'contract', None):
                applica_regole_anni_opzioni_contratto(p, sync_salaries=sync_salaries)
                updated_count += 1

    cap_val = getattr(SIMULATION_TOURNAMENT, 'salary_cap', 155.0)
    return jsonify({
        "success": True,
        "message": f"Contract rules successfully applied to {updated_count} players (Salaries synced to ${cap_val:.1f}M cap: {sync_salaries})",
        "updated_players": updated_count,
        "salary_cap": cap_val,
        "salaries_synced": sync_salaries
    })


# --- Built frontend (packaged build and `python server.py` without Vite) ---
# frontend/dist from the game root; module constant so tests can point it at a temp folder.
FRONTEND_DIST = paths.game_path("frontend", "dist")


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """Serves the built SPA: real files as they are, every other non-API path gets index.html.
    Unknown /api/ paths stay a JSON 404 (the frontend parses API answers as JSON)."""
    if path == 'api' or path.startswith('api/'):
        return jsonify({"error": "Not found"}), 404
    if path and os.path.isfile(os.path.join(FRONTEND_DIST, path)):
        return send_from_directory(FRONTEND_DIST, path)
    if not os.path.isfile(os.path.join(FRONTEND_DIST, 'index.html')):
        return Response("Frontend not built: run npm run build in frontend/", status=404, mimetype="text/plain")
    return send_from_directory(FRONTEND_DIST, 'index.html')


# --- Server Startup ---
def init_game_state():
    """Start-up work shared by `python server.py` and the packaged launcher: legacy migration, then the most
    recent save is restored, else the active DB is seeded from the active league (Mods screen) and a fresh league
    is set up."""
    global SIMULATION_TOURNAMENT, LEAGUE_STATE

    # 1. Handling of legacy save migration if present
    migrated_save = migrate_legacy_files()
    if migrated_save:
        print(f"INFO: Legacy historical files migrated to the folder 'saves/{migrated_save}'.")

    # 2. Restore of the last active save (if present)
    existing_saves = get_all_saves_metadata()
    if existing_saves:
        most_recent = existing_saves[0]
        active_name = most_recent['save_name']
        print(f"INFO: Automatically restoring the last save '{most_recent.get('display_name', active_name)}'...")
        try:
            loaded = load_game(active_name)
            apply_loaded_save_state(active_name, loaded)
        except Exception as e:
            print(f"WARNING: Unable to load the automatic save {active_name}: {e}")
            SIMULATION_TOURNAMENT = simulation_logic.setup_simulation()
            LEAGUE_STATE = "PRE_SEASON"
    else:
        print("INFO: No previous save found. Initializing the idle league from the active league...")
        active_db_path = os.path.join("data", "nba_sim.db")
        try:
            shutil.copyfile(league_catalog.ensure_active_league_db(), active_db_path)
        except LeagueError as e:
            print(f"WARNING: No playable league for the idle start: {e.errors}")
        except Exception as e:
            print(f"Error preparing the idle league: {e}")
        SIMULATION_TOURNAMENT = simulation_logic.setup_simulation()
        LEAGUE_STATE = "PRE_SEASON"


if __name__ == '__main__':
    print("--- Starting the Hardwood Basketball Simulator server ---")
    init_game_state()
    print(f"League initialized for Season {SIMULATION_TOURNAMENT.season_number}. Teams: {len(SIMULATION_TOURNAMENT.squadre)}")
    print("-> Open http://127.0.0.1:5000 in your browser.")

    # Start the Flask server
    app.run(debug=False, port=5000)
