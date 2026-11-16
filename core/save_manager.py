# core/save_manager.py
"""
Save Manager for Hardwood Basketball Simulator VERSION2.0
Handles the organization of saves in sub-folders inside `saves/`.
Keeps full persistence of:
- SQLite database
- Historical files (hall_of_fame, player_careers, league_history, retired_players_ids)
- Save metadata (save_metadata.json)
- In-memory state of the Tournament (tournament_state.json): standings, calendar, playoff bracket, play-in, draft class, user team.
"""

import os
import json
import shutil
import re
import datetime
import logging
from typing import List, Dict, Any, Optional

from core import paths
from core import version as game_version

logger = logging.getLogger('main_sim')


class SaveError(Exception):
    """Raised when a save cannot be written or a save's state cannot be read."""


# The writable user root (the project folder in dev, Documents/Hardwood in the packaged build), see core.paths.
BASE_DIR = paths.user_root()
# HARDWOOD_SAVES_DIR redirects every save read/write (the unit tests point it at a temp folder so they
# can never touch the real saves/). Unset, the game uses <user root>/saves/ (VERSION2.0/saves/ in dev).
SAVES_DIR = os.environ.get('HARDWOOD_SAVES_DIR') or os.path.join(BASE_DIR, 'saves')
ACTIVE_SAVE_NAME: Optional[str] = None

# History files of a career. During play they live in the session copy (<saves>/.session/), like the
# active database lives in data/nba_sim.db; save_game commits them into the slot together with the rest.
HISTORY_FILES = ("player_careers.json", "hall_of_fame.json", "league_history.json",
                 "retired_players_ids.json", "franchise_records.json", "trades_history.txt")
SESSION_DIRNAME = ".session"
# Save the session copy belongs to in this process (None = not bound yet: the first bind always copies the
# slot, so history written and never saved by an earlier run is never picked up).
_SESSION_OWNER: Optional[str] = None


def get_session_dir() -> str:
    return os.path.join(get_saves_dir(), SESSION_DIRNAME)


def open_session(save_name: str) -> None:
    """Fills the session copy with the slot's saved history files (anything unsaved in it is dropped)."""
    global _SESSION_OWNER
    from core import save_store
    session = get_session_dir()
    if os.path.isdir(session):
        shutil.rmtree(session)
    os.makedirs(session)
    slot = get_save_path(save_name)
    if os.path.isdir(slot):
        save_store.roll_forward(slot)
        for filename in HISTORY_FILES:
            src = os.path.join(slot, filename)
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(session, filename))
    with open(os.path.join(session, "OWNER"), "w", encoding="utf-8") as f:
        f.write(sanitize_save_name(save_name))
    _SESSION_OWNER = sanitize_save_name(save_name)


def _close_session() -> None:
    global _SESSION_OWNER
    _SESSION_OWNER = None
    session = get_session_dir()
    if os.path.isdir(session):
        shutil.rmtree(session, ignore_errors=True)


def set_active_save_name(name: Optional[str]):
    """Sets the name of the active save slot; the session copy follows it."""
    global ACTIVE_SAVE_NAME
    ACTIVE_SAVE_NAME = name
    if name and _SESSION_OWNER != sanitize_save_name(name):
        open_session(name)

def get_active_save_name() -> Optional[str]:
    """Returns the name of the active save slot."""
    return ACTIVE_SAVE_NAME

def atomic_write_json(filepath: str, data: Any, indent: int = 4):
    """
    Writes the JSON data to a temporary file (.tmp) and then performs an atomic
    replacement via os.replace, so the file is never corrupted by sudden
    interruptions or crashes while writing.
    """
    dir_name = os.path.dirname(filepath)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False, default=lambda o: getattr(o, 'nome', str(o)),
                  separators=(',', ':') if indent is None else None)
    os.replace(tmp_path, filepath)

def get_historical_file_path(filename: str) -> str:
    """
    Returns the absolute path of a history file of the active save: its session copy
    (saves/.session/<filename>), committed into the slot by save_game.
    """
    if not ACTIVE_SAVE_NAME:
        # If it is not explicitly set, the most recent save becomes the active one.
        saves = get_all_saves_metadata()
        if saves:
            set_active_save_name(saves[0]['save_name'])
    if ACTIVE_SAVE_NAME:
        if _SESSION_OWNER != sanitize_save_name(ACTIVE_SAVE_NAME):
            open_session(ACTIVE_SAVE_NAME)
        return os.path.join(get_session_dir(), filename)
        
    # Default fallback in saves/default_save/
    default_dir = os.path.join(get_saves_dir(), "default_save")
    os.makedirs(default_dir, exist_ok=True)
    return os.path.join(default_dir, filename)

def _current_save_version() -> int:
    from core import save_store
    return save_store.SAVE_VERSION

def get_saves_dir() -> str:
    """Returns the path of the saves folder, creating it if it does not exist."""
    if not os.path.exists(SAVES_DIR):
        os.makedirs(SAVES_DIR, exist_ok=True)
    return SAVES_DIR

def sanitize_save_name(name: str) -> str:
    """Cleans the save name, making it safe for the filesystem."""
    clean = re.sub(r'[^\w\s-]', '', name).strip()
    clean = re.sub(r'[\s]+', '_', clean)
    return clean or "Save_Default"

def default_save_name(team_name: Optional[str], era: str) -> str:
    """The name a new career gets when the player types none: 'Toronto Northmen · 2002' (team and starting era)."""
    era_label = "2002" if str(era) == "2002" else str(era or "").strip().capitalize() or "Modern"
    return f"{(team_name or '').strip() or 'League'} · {era_label}"

def unique_save_name(name: str) -> str:
    """`name`, or 'name (2)', 'name (3)'... so a new career never overwrites an existing save. A folder with no
    save_metadata.json is not a save (a leftover): it is reused and cleaned by the new career."""
    candidate, n = name.strip(), 2
    while os.path.isfile(os.path.join(get_save_path(candidate), "save_metadata.json")):
        candidate, n = f"{name.strip()} ({n})", n + 1
    return candidate

def get_save_path(save_name: str) -> str:
    """Returns the full path for a specific save."""
    safe_name = sanitize_save_name(save_name)
    return os.path.join(get_saves_dir(), safe_name)

def get_all_saves_metadata() -> List[Dict[str, Any]]:
    """Scans the saves/ folder and returns the metadata of all the saves found."""
    saves_dir = get_saves_dir()
    saves_list = []
    
    if not os.path.exists(saves_dir):
        return []
        
    for folder in os.listdir(saves_dir):
        folder_path = os.path.join(saves_dir, folder)
        if folder.startswith("."):
            continue  # the session copy, not a save
        if os.path.isdir(folder_path):
            meta_file = os.path.join(folder_path, "save_metadata.json")
            if os.path.exists(meta_file):
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        meta['save_name'] = folder
                        meta['incompatible'] = _save_version(meta) > _current_save_version()
                        meta.setdefault('player_team_record', 'N/A')
                        saves_list.append(meta)
                except Exception as e:
                    logger.warning("Could not read metadata for save folder %s: %s", folder, e)
            else:
                meta = {
                    "save_name": folder,
                    "display_name": folder.replace("_", " "),
                    "last_saved": datetime.datetime.fromtimestamp(os.path.getmtime(folder_path)).isoformat(),
                    "era": "Modern Era 2026",
                    "season": 1,
                    "phase": "PRE_SEASON",
                    "player_team_name": "Spettatore",
                    "player_team_record": "N/A",
                    "is_spectator": True
                }
                saves_list.append(meta)
                
    saves_list.sort(key=lambda x: x.get("last_saved", ""), reverse=True)
    return saves_list

from core.models import (
    Giocatore, Coach, Contract, Abilita, Tendenze, TacticalPlan,
    PerformanceScores, BoardProfile, BoardObjective, UserProfileGM, GMContract,
    GMBadge, GMAchievement
)
from core.records import export_raw_records, import_raw_records
from core.config import normalize_owner_personality
from core.roles import normalize_role, normalize_role_keys
from core.news_generator import export_raw_news, import_raw_news

def serialize_tactical_plan(tp: Any) -> Dict[str, Any]:
    """Serializes a TacticalPlan object into a JSON dictionary."""
    if not tp:
        return {}
    if isinstance(tp, dict):
        return tp
    return {
        "defensive_matchups": getattr(tp, 'defensive_matchups', {}),
        "double_team_targets": getattr(tp, 'double_team_targets', []),
        "pnr_coverage": getattr(tp, 'pnr_coverage', 'DROP'),
        "defensive_scheme": getattr(tp, 'defensive_scheme', 'MAN_TO_MAN'),
        "offensive_focus": getattr(tp, 'offensive_focus', 'BALANCED'),
        "pace_preference": getattr(tp, 'pace_preference', 'BALANCED'),
        "stagger_stars": getattr(tp, 'stagger_stars', False),
        "foul_trouble_bench_threshold": getattr(tp, 'foul_trouble_bench_threshold', 3),
        "offensive_first_option": getattr(tp, 'offensive_first_option', None),
        "offensive_second_option": getattr(tp, 'offensive_second_option', None),
        "offensive_third_option": getattr(tp, 'offensive_third_option', None),
        "player_touch_modifiers": getattr(tp, 'player_touch_modifiers', {}),
        "opponent_plans": getattr(tp, 'opponent_plans', {})
    }

def deserialize_tactical_plan(data: Optional[Dict[str, Any]]) -> TacticalPlan:
    """Rebuilds a TacticalPlan object from a serialized dictionary."""
    if not data or not isinstance(data, dict):
        return TacticalPlan()
    return TacticalPlan(
        defensive_matchups=data.get("defensive_matchups", {}),
        double_team_targets=data.get("double_team_targets", []),
        pnr_coverage=data.get("pnr_coverage", "DROP"),
        defensive_scheme=data.get("defensive_scheme", "MAN_TO_MAN"),
        offensive_focus=data.get("offensive_focus", "BALANCED"),
        pace_preference=data.get("pace_preference", "BALANCED"),
        stagger_stars=data.get("stagger_stars", False),
        foul_trouble_bench_threshold=data.get("foul_trouble_bench_threshold", 3),
        offensive_first_option=data.get("offensive_first_option", None),
        offensive_second_option=data.get("offensive_second_option", None),
        offensive_third_option=data.get("offensive_third_option", None),
        player_touch_modifiers=data.get("player_touch_modifiers", {}),
        opponent_plans=data.get("opponent_plans", {})
    )

def serialize_player(player: Any) -> Dict[str, Any]:
    """Serializes a Giocatore object into a JSON-friendly dictionary with every attribute."""
    if isinstance(player, dict):
        return player
    if not hasattr(player, 'nome'):
        return {}
        
    data = {
        "db_id": getattr(player, 'db_id', None),
        "nome": getattr(player, 'nome', 'Giocatore'),
        "ruolo": getattr(player, 'ruolo', 'SG'),
        "ruolo_secondario": getattr(player, 'ruolo_secondario', None),
        "ruolo_originale": getattr(player, 'ruolo_originale', None),   # set when the user changed his role
        "role_ovr_shift": int(getattr(player, 'role_ovr_shift', 0) or 0),   # OVR now - OVR at the original role
        "eta": getattr(player, 'eta', 20),
        "valutazione": getattr(player, 'valutazione', getattr(player, 'ovr', 70)),
        "potenziale": getattr(player, 'potenziale', 75),
        "provenance": getattr(player, 'provenance', 'N/A'),
        "pedigree": getattr(player, 'pedigree', 'Veteran'),
        "is_rookie": getattr(player, 'is_rookie', False),
        "on_trade_block": getattr(player, 'on_trade_block', False),
        "is_untouchable": getattr(player, 'is_untouchable', False),
        "anni_nella_squadra": getattr(player, 'anni_nella_squadra', 0),
        "morale": getattr(player, 'morale', 75),
        "fvs": getattr(player, 'fvs', 70),
        "infortunato": getattr(player, 'infortunato', False),
        "giorni_infortunio_rimanenti": getattr(player, 'giorni_infortunio_rimanenti', 0),
        "tipo_infortunio": getattr(player, 'infortunio_nome', getattr(player, 'tipo_infortunio', None)),
        "infortunio_nome": getattr(player, 'infortunio_nome', None),
        "is_day_to_day": getattr(player, 'is_day_to_day', False),
        "infortunio_impatto": getattr(player, 'infortunio_impatto', 0.0),
        "scouting_progress": getattr(player, 'scouting_progress', 10.0),
        "draft_stock_mod": getattr(player, 'draft_stock_mod', 0.0),
        "valutazioni_posizionali": getattr(player, 'valutazioni_posizionali', {}),
        "college_stats": getattr(player, 'college_stats', None),
        "giorni_cooldown_scambio": getattr(player, 'giorni_cooldown_scambio', 0),
        "is_flight_risk": getattr(player, 'is_flight_risk', False),
        "walks_away": getattr(player, 'walks_away', ""),
        "stamina_stagionale": getattr(player, 'stamina_stagionale', 100.0),
        "minuti_target": getattr(player, 'minuti_target', 0),
        "secondi_in_panchina_consecutivi": getattr(player, 'secondi_in_panchina_consecutivi', 0),
        "plus_minus": getattr(player, 'plus_minus', 0),
        "is_resting_today": getattr(player, 'is_resting_today', False),
        "premi": list(getattr(player, 'premi', [])),
        "anelli_vinti": getattr(player, 'anelli_vinti', 0),
        "career_log": list(getattr(player, 'career_log', [])),
        "ovr_history": list(getattr(player, 'ovr_history', [])),
        # Last offseason's OVR and attribute changes, shown in the Development tab.
        "last_progression": getattr(player, 'last_progression', None),
    }

    ps = getattr(player, 'performance_scores', None)
    if ps:
        if isinstance(ps, dict):
            data['performance_scores'] = ps
        elif hasattr(ps, '__dict__'):
            data['performance_scores'] = {
                "offensive": getattr(ps, 'offensive', 75.0),
                "defensive": getattr(ps, 'defensive', 75.0),
                "total": getattr(ps, 'total', 75.0)
            }

    abilita_obj = getattr(player, 'abilita', None)
    if abilita_obj:
        if isinstance(abilita_obj, dict):
            data['abilita'] = abilita_obj
        elif hasattr(abilita_obj, '__dict__'):
            data['abilita'] = vars(abilita_obj)

    tendenze_obj = getattr(player, 'tendenze', None)
    if tendenze_obj:
        if isinstance(tendenze_obj, dict):
            data['tendenze'] = tendenze_obj
        elif hasattr(tendenze_obj, '__dict__'):
            data['tendenze'] = vars(tendenze_obj)

    c = getattr(player, 'contract', None)
    if c:
        if isinstance(c, dict):
            data['contract'] = c
        elif hasattr(c, '__dict__'):
            data['contract'] = {
                "anni_rimanenti": getattr(c, 'anni_rimanenti', 1),
                "salario_annuale": getattr(c, 'salario_annuale', 2.0),
                "salari_per_anno": getattr(c, 'salari_per_anno', []),
                "player_option": getattr(c, 'player_option', False),
                "team_option": getattr(c, 'team_option', False)
            }

    s_stats = getattr(player, 'season_stats', None)
    if s_stats:
        if isinstance(s_stats, dict):
            data['season_stats'] = s_stats
        elif hasattr(s_stats, '__dict__'):
            data['season_stats'] = vars(s_stats)

    p_stats = getattr(player, 'playoff_stats', None)
    if p_stats:
        if isinstance(p_stats, dict):
            data['playoff_stats'] = p_stats
        elif hasattr(p_stats, '__dict__'):
            data['playoff_stats'] = vars(p_stats)

    adv_stats = getattr(player, 'advanced_game_stats', None)
    if adv_stats:
        if isinstance(adv_stats, dict):
            data['advanced_game_stats'] = adv_stats
        elif hasattr(adv_stats, '__dict__'):
            data['advanced_game_stats'] = vars(adv_stats)

    return data


def deserialize_player(data: Dict[str, Any], squadra_obj: Optional[Any] = None) -> Giocatore:
    """Rebuilds a complete Giocatore object from a serialized dictionary."""
    if not isinstance(data, dict):
        return data

    abilita_data = data.get("abilita", {})
    tendenze_data = data.get("tendenze", {})

    if isinstance(abilita_data, dict) and abilita_data:
        valid_ab = {k: v for k, v in abilita_data.items() if k in Abilita.__dataclass_fields__}
        ab = Abilita(**valid_ab)
    else:
        ab = Abilita(
            close_shot_rating=60, mid_range_shot_rating=60, three_point_shot_rating=60, free_throw_rating=60,
            shot_iq=60, passing_accuracy=60, ball_handling=60, passing_vision=60, interior_defense_rating=60,
            perimeter_defense_rating=60, steal_rating=60, block_rating=60, strength=60, speed=60,
            acceleration=60, vertical=60, stamina=60, offensive_rebound_rating=60, defensive_rebound_rating=60
        )

    if isinstance(tendenze_data, dict) and tendenze_data:
        valid_td = {k: v for k, v in tendenze_data.items() if k in Tendenze.__dataclass_fields__}
        td = Tendenze(**valid_td)
    else:
        td = Tendenze(
            touch_tendency=50, spot_up_shot_tendency=50, mid_range_shot_tendency=50, three_point_shot_tendency=50,
            drive_to_basket_tendency=50, post_up_tendency=50, pass_out_of_shot_tendency=50, dish_to_open_man_tendency=50
        )

    valutazione = data.get("valutazione", data.get("ovr", 70))
    g = Giocatore(
        nome=data.get("nome", "Prospect"),
        ruolo=normalize_role(data.get("ruolo")) or "SG",
        eta=data.get("eta", 19),
        valutazione=valutazione,
        potenziale=data.get("potenziale", 80),
        abilita=ab,
        tendenze=td,
        squadra=squadra_obj,
        provenance=data.get("provenance", "N/A"),
        pedigree=data.get("pedigree", "Veteran"),
        db_id=data.get("db_id")
    )

    if "ruolo_secondario" in data:
        g.ruolo_secondario = normalize_role(data["ruolo_secondario"]) or None
    if data.get("ruolo_originale"):
        g.ruolo_originale = normalize_role(data["ruolo_originale"]) or None
    g.role_ovr_shift = int(data.get("role_ovr_shift", 0) or 0)
    g.is_rookie = data.get("is_rookie", False)
    g.on_trade_block = data.get("on_trade_block", False)
    g.is_untouchable = data.get("is_untouchable", False)
    g.anni_nella_squadra = data.get("anni_nella_squadra", 0)
    g.morale = data.get("morale", 75)
    g.fvs = data.get("fvs", 70)
    g.infortunato = data.get("infortunato", False)
    g.giorni_infortunio_rimanenti = data.get("giorni_infortunio_rimanenti", 0)
    inf_nome = data.get("infortunio_nome", data.get("tipo_infortunio"))
    g.infortunio_nome = inf_nome
    g.tipo_infortunio = inf_nome
    g.is_day_to_day = data.get("is_day_to_day", False)
    g.infortunio_impatto = data.get("infortunio_impatto", 0.0)

    g.scouting_progress = data.get("scouting_progress", 10.0)
    g.draft_stock_mod = data.get("draft_stock_mod", 0.0)
    g._calibra_e_calcola_posizioni()   # from the abilities (CONFIG.POSITIONS): old saves carried the old, PG-heavy ratings
    g.college_stats = data.get("college_stats", None)
    g.giorni_cooldown_scambio = data.get("giorni_cooldown_scambio", 0)
    g.is_flight_risk = data.get("is_flight_risk", False)
    g.walks_away = data.get("walks_away", "")
    g.stamina_stagionale = data.get("stamina_stagionale", 100.0)
    g.minuti_target = data.get("minuti_target", 0)
    g.secondi_in_panchina_consecutivi = data.get("secondi_in_panchina_consecutivi", 0)
    g.plus_minus = data.get("plus_minus", 0)
    g.is_resting_today = data.get("is_resting_today", False)
    g.premi = list(data.get("premi", []))
    g.anelli_vinti = int(data.get("anelli_vinti", 0))
    g.career_log = list(data.get("career_log", []))
    g.ovr_history = list(data.get("ovr_history", []))
    if data.get("last_progression"):
        g.last_progression = data["last_progression"]

    # Contratto
    c_data = data.get("contract")
    if c_data and isinstance(c_data, dict):
        g.contract = Contract(
            anni_rimanenti=c_data.get("anni_rimanenti", 1),
            salario_annuale=c_data.get("salario_annuale", 2.0),
            salari_per_anno=c_data.get("salari_per_anno", []),
            player_option=c_data.get("player_option", False),
            team_option=c_data.get("team_option", False)
        )

    # Season Stats
    s_data = data.get("season_stats")
    if s_data and isinstance(s_data, dict):
        for k, v in s_data.items():
            if hasattr(g.season_stats, k):
                setattr(g.season_stats, k, v)

    # Playoff Stats
    p_data = data.get("playoff_stats")
    if p_data and isinstance(p_data, dict):
        for k, v in p_data.items():
            if hasattr(g.playoff_stats, k):
                setattr(g.playoff_stats, k, v)

    adv_data = data.get("advanced_game_stats")
    if adv_data and isinstance(adv_data, dict):
        for k, v in adv_data.items():
            if hasattr(g.advanced_game_stats, k):
                setattr(g.advanced_game_stats, k, v)

    ps_data = data.get("performance_scores")
    if ps_data and isinstance(ps_data, dict):
        g.performance_scores = PerformanceScores(
            offensive=float(ps_data.get("offensive", 75.0)),
            defensive=float(ps_data.get("defensive", 75.0)),
            total=float(ps_data.get("total", 75.0))
        )
    elif hasattr(g, 'calcola_pvs'):
        g.calcola_pvs()

    return g


def serialize_coach(coach: Any) -> Dict[str, Any]:
    if not coach:
        return {}
    if isinstance(coach, dict):
        return coach

    return {
        "nome": getattr(coach, 'nome', 'Coach'),
        "stile_gioco": getattr(coach, 'stile_gioco', 'Balanced Offense'),
        "ovr_offensivo": getattr(coach, 'ovr_offensivo', 75),
        "ovr_difensivo": getattr(coach, 'ovr_difensivo', 75),
        "player_development": getattr(coach, 'player_development', 75),
        "tactical_acumen": getattr(coach, 'tactical_acumen', 75),
        "discipline_culture": getattr(coach, 'discipline_culture', 75),
        "eta": getattr(coach, 'eta', 45),
        "potenziale": getattr(coach, 'potenziale', 80),
        "contratto_anni_rimanenti": getattr(coach, 'contratto_anni_rimanenti', 3),
        "contratto_totale_anni": getattr(coach, 'contratto_totale_anni', 3),
        "job_security": getattr(coach, 'job_security', 75.0),
        "years_with_current_team": getattr(coach, 'years_with_current_team', 1),
        "xp": getattr(coach, 'xp', 0),
        "level": getattr(coach, 'level', 1),
        "badges": getattr(coach, 'badges', {}),
        "salario": getattr(coach, 'salario', 3.5),
        "historical_wins": getattr(coach, 'historical_wins', 0),
        "historical_losses": getattr(coach, 'historical_losses', 0),
        "playoff_appearances": getattr(coach, 'playoff_appearances', 0),
        "championships": getattr(coach, 'championships', 0),
        "coty_awards": getattr(coach, 'coty_awards', 0),
        "badge_points": getattr(coach, 'badge_points', 0),
        "rpg_xp": getattr(coach, 'rpg_xp', getattr(coach, 'xp', 0)),
        "rpg_level": getattr(coach, 'rpg_level', getattr(coach, 'level', 1)),
        "skill_points": getattr(coach, 'skill_points', getattr(coach, 'badge_points', 0)),
        "unlocked_nodes": getattr(coach, 'unlocked_nodes', []),
        "past_teams": getattr(coach, 'past_teams', []),
        "specialization": getattr(coach, 'specialization', 'Tactical Strategist'),
        "offensive_system": getattr(coach, 'offensive_system_label', getattr(coach, 'offensive_system', '')),
        "defensive_scheme": getattr(coach, 'defensive_scheme_label', getattr(coach, 'defensive_scheme', '')),
        "preferred_pace": getattr(coach, 'preferred_pace_label', getattr(coach, 'preferred_pace', ''))
    }


def deserialize_coach(data: Dict[str, Any]) -> Optional[Coach]:
    if not data or not isinstance(data, dict):
        return None

    return Coach(
        nome=data.get("nome", "Coach"),
        stile_gioco=data.get("stile_gioco", "Balanced Offense"),
        ovr_offensivo=data.get("ovr_offensivo", 75),
        ovr_difensivo=data.get("ovr_difensivo", 75),
        player_development=data.get("player_development", 75),
        tactical_acumen=data.get("tactical_acumen", 75),
        discipline_culture=data.get("discipline_culture", 75),
        eta=data.get("eta", 45),
        potenziale=data.get("potenziale", 80),
        contratto_anni_rimanenti=data.get("contratto_anni_rimanenti", 3),
        contratto_totale_anni=data.get("contratto_totale_anni", 3),
        job_security=data.get("job_security", 75.0),
        years_with_current_team=data.get("years_with_current_team", 1),
        xp=data.get("xp", 0),
        level=data.get("level", 1),
        badges=data.get("badges", {
            "Rookie Developer": 0,
            "Defense Guru": 0,
            "Tactician": 0,
            "Fitness Specialist": 0,
            "Motivator": 0,
            "Clutch Master": 0
        }),
        salario=data.get("salario", 3.5),
        historical_wins=data.get("historical_wins", 0),
        historical_losses=data.get("historical_losses", 0),
        playoff_appearances=data.get("playoff_appearances", 0),
        championships=data.get("championships", 0),
        coty_awards=data.get("coty_awards", 0),
        badge_points=data.get("badge_points", 0),
        rpg_xp=data.get("rpg_xp", data.get("xp", 0)),
        rpg_level=data.get("rpg_level", data.get("level", 1)),
        skill_points=data.get("skill_points", data.get("badge_points", 0)),
        unlocked_nodes=data.get("unlocked_nodes", []),
        past_teams=data.get("past_teams", []),
        specialization=data.get("specialization", "Tactical Strategist"),
        offensive_system=data.get("offensive_system", ""),
        defensive_scheme=data.get("defensive_scheme", ""),
        preferred_pace=data.get("preferred_pace", "")
    )


def serialize_board_profile(profile: Any) -> Optional[Dict[str, Any]]:
    if not profile:
        return None
    from dataclasses import asdict
    try:
        return {
            "owner_name": getattr(profile, 'owner_name', 'Owner'),
            "personality": getattr(profile, 'personality', 'Bilanciato'),
            "patience_level": getattr(profile, 'patience_level', 3),
            "spending_attitude": getattr(profile, 'spending_attitude', 3),
            "approval_rating": getattr(profile, 'approval_rating', 75.0),
            "status_label": getattr(profile, 'status_label', 'Stable'),
            "objectives": [asdict(obj) if hasattr(obj, '__dataclass_fields__') else obj for obj in getattr(profile, 'objectives', [])],
            "board_messages": getattr(profile, 'board_messages', []),
            "seasons_with_team": getattr(profile, 'seasons_with_team', 1)
        }
    except Exception:
        return None

def deserialize_board_profile(data: Optional[Dict[str, Any]]) -> Optional[Any]:
    if not data:
        return None
    try:
        objs = []
        for o in data.get("objectives", []):
            if isinstance(o, dict):
                objs.append(BoardObjective(**o))
            else:
                objs.append(o)
        return BoardProfile(
            owner_name=data.get("owner_name", "Owner"),
            personality=normalize_owner_personality(data.get("personality")) or "Bilanciato",
            patience_level=data.get("patience_level", 3),
            spending_attitude=data.get("spending_attitude", 3),
            approval_rating=data.get("approval_rating", 75.0),
            status_label=data.get("status_label", "Stable"),
            objectives=objs,
            board_messages=data.get("board_messages", []),
            seasons_with_team=data.get("seasons_with_team", 1)
        )
    except Exception:
        return None

def serialize_user_gm_profile(gm: Any) -> Optional[Dict[str, Any]]:
    if not gm:
        return None
    from dataclasses import asdict
    try:
        contract_dict = asdict(gm.contract) if hasattr(gm, 'contract') and gm.contract else {}
        badges = [asdict(b) if hasattr(b, '__dataclass_fields__') else b for b in getattr(gm, 'badges', [])]
        achievements = [asdict(a) if hasattr(a, '__dataclass_fields__') else a for a in getattr(gm, 'achievements', [])]
        return {
            "name": getattr(gm, 'name', 'General Manager'),
            "reputation_style": getattr(gm, 'reputation_style', 'Balanced Builder'),
            "contract": contract_dict,
            "badges": badges,
            "achievements": achievements,
            "career_wins": getattr(gm, 'career_wins', 0),
            "career_losses": getattr(gm, 'career_losses', 0),
            "titles_won": getattr(gm, 'titles_won', 0),
            "seasons_managed": getattr(gm, 'seasons_managed', 0),
            "teams_managed_history": getattr(gm, 'teams_managed_history', []),
            "current_team_name": getattr(gm, 'current_team_name', 'Unknown'),
            "season_reports": getattr(gm, 'season_reports', []),
            "rpg_xp": getattr(gm, 'rpg_xp', 0),
            "rpg_level": getattr(gm, 'rpg_level', 1),
            "skill_points": getattr(gm, 'skill_points', 2),
            "unlocked_nodes": getattr(gm, 'unlocked_nodes', []),
            "prestige_score": getattr(gm, 'prestige_score', 65.0)
        }
    except Exception:
        return None

def deserialize_user_gm_profile(data: Optional[Dict[str, Any]]) -> Optional[Any]:
    if not data:
        return None
    try:
        contract_data = data.get("contract", {})
        contract = GMContract(**contract_data) if contract_data else GMContract(salary_per_year=4.5, years_remaining=4, total_years=4)
        
        badges = [GMBadge(**b) if isinstance(b, dict) else b for b in data.get("badges", [])]
        achievements = [GMAchievement(**a) if isinstance(a, dict) else a for a in data.get("achievements", [])]
        
        return UserProfileGM(
            name=data.get("name", "General Manager"),
            reputation_style=data.get("reputation_style", "Balanced Builder"),
            contract=contract,
            badges=badges,
            achievements=achievements,
            career_wins=data.get("career_wins", 0),
            career_losses=data.get("career_losses", 0),
            titles_won=data.get("titles_won", 0),
            seasons_managed=data.get("seasons_managed", 0),
            teams_managed_history=data.get("teams_managed_history", []),
            current_team_name=data.get("current_team_name", "Unknown"),
            season_reports=data.get("season_reports", []),
            rpg_xp=data.get("rpg_xp", 0),
            rpg_level=data.get("rpg_level", 1),
            skill_points=data.get("skill_points", 2),
            unlocked_nodes=data.get("unlocked_nodes", []),
            prestige_score=data.get("prestige_score", 65.0)
        )
    except Exception:
        return None

def serialize_team(s: Any) -> Dict[str, Any]:
    roster_serialized = [serialize_player(p) for p in getattr(s, 'roster', [])]
    coach_serialized = serialize_coach(getattr(s, 'coach', None))
    rotazione_serialized = [serialize_player(p) for p in getattr(s, 'rotazione', [])]
    board_profile_serialized = serialize_board_profile(getattr(s, 'board_profile', None))
    tactical_plan_serialized = serialize_tactical_plan(getattr(s, 'tactical_plan', None))

    # Draft picks keys can be ints, convert to str keys for JSON safe serialization
    raw_draft_picks = getattr(s, 'draft_picks', {})
    draft_picks_serialized = {}
    if isinstance(raw_draft_picks, dict):
        for yr, p_list in raw_draft_picks.items():
            draft_picks_serialized[str(yr)] = p_list

    return {
        "nome": s.nome,
        "team_id": getattr(s, 'team_id', '') or '',
        "conference": getattr(s, 'conference', 'East'),
        "division": getattr(s, 'division', 'Atlantic'),
        "vittorie": getattr(s, 'vittorie', 0),
        "sconfitte": getattr(s, 'sconfitte', 0),
        "punti_fatti": getattr(s, 'punti_fatti', 0),
        "punti_subiti": getattr(s, 'punti_subiti', 0),
        "vittorie_casa": getattr(s, 'vittorie_casa', 0),
        "sconfitte_casa": getattr(s, 'sconfitte_casa', 0),
        "vittorie_trasferta": getattr(s, 'vittorie_trasferta', 0),
        "sconfitte_trasferta": getattr(s, 'sconfitte_trasferta', 0),
        "vittorie_conf": getattr(s, 'vittorie_conf', 0),
        "sconfitte_conf": getattr(s, 'sconfitte_conf', 0),
        "striscia_tipo": getattr(s, 'striscia_tipo', 'V'),
        "striscia_numero": getattr(s, 'striscia_numero', 0),
        "ultime_10": list(getattr(s, 'ultime_10', [])),
        "team_goal": getattr(s, 'team_goal', 'Contender'),
        "personalita_proprietario": getattr(s, 'personalita_proprietario', None),
        "vittorie_attese": getattr(s, 'vittorie_attese', 0.0),
        "intesa": getattr(s, 'intesa', 70),
        "strategia": getattr(s, 'strategia', 'normale'),
        "ha_usato_mle": getattr(s, 'ha_usato_mle', False),
        "ha_usato_bae": getattr(s, 'ha_usato_bae', False),
        "anni_in_luxury_tax": getattr(s, 'anni_in_luxury_tax', 0),
        "active_poe": getattr(s, 'active_poe', 'Balanced Approach'),
        "tactical_plan": tactical_plan_serialized,
        "user_custom_lineup": {pos: (p.nome if hasattr(p, 'nome') else str(p)) for pos, p in getattr(s, 'user_custom_lineup', {}).items()} if isinstance(getattr(s, 'user_custom_lineup', None), dict) else {},
        "posizione_in_campo": {pos: (p.nome if hasattr(p, 'nome') else str(p)) for pos, p in getattr(s, 'posizione_in_campo', {}).items()} if isinstance(getattr(s, 'posizione_in_campo', None), dict) else {},
        "rotazioni_personalizzate_utente": getattr(s, 'rotazioni_personalizzate_utente', None),
        "draft_picks": draft_picks_serialized,
        "financial_summary": getattr(s, 'financial_summary', {}),
        "quintetto_names": [p.nome for p in getattr(s, 'quintetto', []) if hasattr(p, 'nome')],
        "panchina_names": [p.nome for p in getattr(s, 'panchina', []) if hasattr(p, 'nome')],
        "coach": coach_serialized,
        "roster": roster_serialized,
        "rotazione": rotazione_serialized,
        "board_profile": board_profile_serialized,
        "standings_history": list(getattr(s, 'standings_history', [])),
        "front_office_summit": getattr(s, 'front_office_summit', None),
        "pending_board_concern": getattr(s, 'pending_board_concern', None)
    }

def serialize_active_playoff_series(raw_series: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_series, list):
        return []
    out = []
    for s in raw_series:
        if isinstance(s, dict):
            s_clean = dict(s)
            if "s1" in s_clean:
                s_clean["s1"] = s_clean["s1"].nome if hasattr(s_clean["s1"], 'nome') else str(s_clean["s1"])
            if "s2" in s_clean:
                s_clean["s2"] = s_clean["s2"].nome if hasattr(s_clean["s2"], 'nome') else str(s_clean["s2"])
            out.append(s_clean)
        else:
            out.append(s)
    return out

def serialize_play_in_results(raw_pir: Any) -> Dict[str, Any]:
    if not isinstance(raw_pir, dict):
        return {'east': {}, 'west': {}}
    out = {}
    for conf, cdata in raw_pir.items():
        if isinstance(cdata, dict):
            out[conf] = {}
            for k, v in cdata.items():
                if isinstance(v, dict):
                    v_clean = {}
                    for vk, vv in v.items():
                        if vk in ('winner_obj', 'loser_obj'):
                            v_clean[vk] = vv.nome if hasattr(vv, 'nome') else str(vv)
                        elif hasattr(vv, 'nome'):
                            v_clean[vk] = vv.nome
                        else:
                            v_clean[vk] = vv
                    out[conf][k] = v_clean
                elif isinstance(v, list):
                    out[conf][k] = [item.nome if hasattr(item, 'nome') else item for item in v]
                elif hasattr(v, 'nome'):
                    out[conf][k] = v.nome
                else:
                    out[conf][k] = v
        else:
            out[conf] = cdata
    return out

def serialize_tournament_state(tournament_instance: Any, extra_playoff_data: Optional[Dict] = None) -> Dict[str, Any]:
    """Serializes the complete dynamic in-memory state of the league (standings, rosters, FA, calendar, playoffs, draft class, records, news)."""
    if not tournament_instance:
        return {}

    squadre_data = [serialize_team(s) for s in getattr(tournament_instance, 'squadre', [])]

    # We also keep squadre_stats for backwards compatibility
    squadre_stats = []
    for s in getattr(tournament_instance, 'squadre', []):
        squadre_stats.append({
            "nome": s.nome,
            "vittorie": getattr(s, 'vittorie', 0),
            "sconfitte": getattr(s, 'sconfitte', 0),
            "punti_fatti": getattr(s, 'punti_fatti', 0),
            "punti_subiti": getattr(s, 'punti_subiti', 0),
            "vittorie_casa": getattr(s, 'vittorie_casa', 0),
            "sconfitte_casa": getattr(s, 'sconfitte_casa', 0),
            "vittorie_trasferta": getattr(s, 'vittorie_trasferta', 0),
            "sconfitte_trasferta": getattr(s, 'sconfitte_trasferta', 0),
            "vittorie_conf": getattr(s, 'vittorie_conf', 0),
            "sconfitte_conf": getattr(s, 'sconfitte_conf', 0),
            "striscia_tipo": getattr(s, 'striscia_tipo', 'V'),
            "striscia_numero": getattr(s, 'striscia_numero', 0),
            "ultime_10": list(getattr(s, 'ultime_10', []))
        })

    calendario_serialized = []
    for giornata in getattr(tournament_instance, 'calendario', []):
        if hasattr(giornata, 'to_dict'):
            calendario_serialized.append(giornata.to_dict())
        elif isinstance(giornata, list):
            giornata_data = []
            for match in giornata:
                if isinstance(match, (tuple, list)) and len(match) >= 2:
                    s1, s2 = match[0], match[1]
                    s1_nome = s1.nome if hasattr(s1, 'nome') else str(s1)
                    s2_nome = s2.nome if hasattr(s2, 'nome') else str(s2)
                    giornata_data.append({"s1": s1_nome, "s2": s2_nome})
                elif isinstance(match, dict):
                    s1 = match.get('s1')
                    s2 = match.get('s2')
                    s1_nome = s1.nome if hasattr(s1, 'nome') else str(s1)
                    s2_nome = s2.nome if hasattr(s2, 'nome') else str(s2)
                    giornata_data.append({
                        "s1": s1_nome,
                        "s2": s2_nome,
                        "giocata": match.get('giocata', False),
                        "punti_s1": match.get('punti_s1', 0),
                        "punti_s2": match.get('punti_s2', 0)
                    })
            calendario_serialized.append(giornata_data)

    draft_class_serialized = [serialize_player(p) for p in getattr(tournament_instance, 'draft_class', [])]
    free_agents_serialized = [serialize_player(p) for p in getattr(tournament_instance, 'free_agents_pool', [])]
    giocatori_ritirati_serialized = [serialize_player(p) for p in getattr(tournament_instance, 'giocatori_ritirati', [])]
    nuovi_free_agents_serialized = [serialize_player(p) for p in getattr(tournament_instance, 'nuovi_free_agents', [])]
    unemployed_coaches_serialized = [serialize_coach(c) for c in getattr(tournament_instance, 'unemployed_coaches', [])]

    user_team = getattr(tournament_instance, 'squadra_giocatore', None)
    team_name = user_team.nome if user_team else "Spettatore"
    is_spec = getattr(tournament_instance, 'is_spectator', False)
    if user_team is None:
        is_spec = True

    campione_obj = getattr(tournament_instance, 'campione', None)
    campione_nome = campione_obj.nome if (campione_obj and hasattr(campione_obj, 'nome')) else (campione_obj if isinstance(campione_obj, str) else None)

    awards = {
        "regular_season_mvp": getattr(getattr(tournament_instance, 'regular_season_mvp', None), 'nome', None),
        "defensive_player_of_the_year": getattr(getattr(tournament_instance, 'defensive_player_of_the_year', None), 'nome', None),
        "sesto_uomo": getattr(getattr(tournament_instance, 'sesto_uomo', None), 'nome', None),
        "rookie_of_the_year": getattr(getattr(tournament_instance, 'rookie_of_the_year', None), 'nome', None),
        "most_improved_player": getattr(getattr(tournament_instance, 'most_improved_player', None), 'nome', None),
        "coach_of_the_year": getattr(tournament_instance, 'coach_of_the_year', None),
        "gm_of_the_year": getattr(tournament_instance, 'gm_of_the_year', None),
        "all_nba_teams": [[getattr(p, 'nome', str(p)) for p in team] for team in getattr(tournament_instance, 'all_nba_teams', [])],
        "all_defensive_team": [getattr(p, 'nome', str(p)) for p in getattr(tournament_instance, 'all_defensive_team', [])],
        "all_rookie_team": [getattr(p, 'nome', str(p)) for p in getattr(tournament_instance, 'all_rookie_team', [])]
    }

    all_star_state = {
        "all_star_rosters": {
            "east": [getattr(p, 'nome', str(p)) for p in getattr(tournament_instance, 'all_star_rosters', {}).get('east', [])],
            "west": [getattr(p, 'nome', str(p)) for p in getattr(tournament_instance, 'all_star_rosters', {}).get('west', [])]
        },
        "all_star_starters": {
            "east": [getattr(p, 'nome', str(p)) for p in getattr(tournament_instance, 'all_star_starters', {}).get('east', [])],
            "west": [getattr(p, 'nome', str(p)) for p in getattr(tournament_instance, 'all_star_starters', {}).get('west', [])]
        },
        "all_star_reserves": {
            "east": [getattr(p, 'nome', str(p)) for p in getattr(tournament_instance, 'all_star_reserves', {}).get('east', [])],
            "west": [getattr(p, 'nome', str(p)) for p in getattr(tournament_instance, 'all_star_reserves', {}).get('west', [])]
        },
        "all_star_game_log": getattr(tournament_instance, 'all_star_game_log', None),
        "all_star_mvp": getattr(tournament_instance, 'all_star_mvp', None),
        "three_point_contest": getattr(tournament_instance, 'three_point_contest', {}),
        "dunk_contest": getattr(tournament_instance, 'dunk_contest', {}),
        "all_star_weekend_complete": getattr(tournament_instance, 'all_star_weekend_complete', False),
        "weekend": getattr(tournament_instance, 'all_star_weekend', None),
        "last_season_rookies": list(getattr(tournament_instance, 'last_season_rookies', []) or []),
        "hosts": list(getattr(tournament_instance, 'all_star_hosts', []) or [])
    }

    # Extract dynamic salary cap economy
    salary_cap = getattr(tournament_instance, 'salary_cap', 136.0)
    luxury_tax_threshold = getattr(tournament_instance, 'luxury_tax_threshold', 165.0)
    first_apron_threshold = getattr(tournament_instance, 'first_apron', getattr(tournament_instance, 'first_apron_threshold', 172.0))
    second_apron_threshold = getattr(tournament_instance, 'second_apron', getattr(tournament_instance, 'second_apron_threshold', 182.0))
    mle_amount = getattr(tournament_instance, 'mle_value', getattr(tournament_instance, 'mle_amount', 12.0))
    bae_amount = getattr(tournament_instance, 'bae_amount', 4.5)
    minimum_salary = getattr(tournament_instance, 'min_salary', getattr(tournament_instance, 'minimum_salary', 1.1))

    cur_gameday = getattr(tournament_instance, '_current_gameday', getattr(tournament_instance, 'current_day', 0))
    front_office = getattr(tournament_instance, 'front_office', None)
    state = {
        "season_number": getattr(tournament_instance, 'season_number', 1),
        "current_day": cur_gameday,
        "_current_gameday": cur_gameday,
        "_trade_deadline_completed": bool(getattr(tournament_instance, '_trade_deadline_completed', False)),
        "starting_year": getattr(tournament_instance, 'starting_year', 2025),
        "anno_corrente": getattr(tournament_instance, 'anno_corrente', 2025),
        "league_state": getattr(tournament_instance, 'league_state', 'PRE_SEASON'),
        "fase_torneo": getattr(tournament_instance, 'fase_torneo', 'SEASON'),
        "player_team_name": team_name,
        "is_spectator": is_spec,
        "salary_cap": salary_cap,
        "luxury_tax_threshold": luxury_tax_threshold,
        "first_apron_threshold": first_apron_threshold,
        "second_apron_threshold": second_apron_threshold,
        "mle_amount": mle_amount,
        "bae_amount": bae_amount,
        "minimum_salary": minimum_salary,
        "squadre_data": squadre_data,
        "league": {
            "meta": dict(getattr(tournament_instance, 'league_meta', None) or {}),
            "registry": (tournament_instance.franchise_registry.to_dict()
                         if getattr(tournament_instance, 'franchise_registry', None) is not None else None),
        },
        "squadre_stats": squadre_stats,
        "free_agents_pool": free_agents_serialized,
        "giocatori_ritirati": giocatori_ritirati_serialized,
        "nuovi_free_agents": nuovi_free_agents_serialized,
        "unemployed_coaches": unemployed_coaches_serialized,
        "calendario": calendario_serialized,
        "playoff_bracket_data": getattr(tournament_instance, 'playoff_bracket_data', None),
        "playoff_state": getattr(tournament_instance, 'playoff_state', 'NOT_STARTED'),
        "play_in_teams": {
            "east": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'play_in_teams', {}).get('east', [])],
            "west": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'play_in_teams', {}).get('west', [])]
        },
        "direct_qualifiers": {
            "east": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'direct_qualifiers', {}).get('east', [])],
            "west": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'direct_qualifiers', {}).get('west', [])]
        },
        "play_in_results": serialize_play_in_results(getattr(tournament_instance, 'play_in_results', None)),
        "play_in_game_index": getattr(tournament_instance, 'play_in_game_index', 0),
        "playoff_teams": {
            "east": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'playoff_teams', {}).get('east', [])],
            "west": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'playoff_teams', {}).get('west', [])]
        },
        "next_round_teams": {
            "east": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'next_round_teams', {}).get('east', [])],
            "west": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'next_round_teams', {}).get('west', [])]
        } if isinstance(getattr(tournament_instance, 'next_round_teams', None), dict) else ([t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'next_round_teams', [])] if isinstance(getattr(tournament_instance, 'next_round_teams', None), list) else {}),
        "active_playoff_series": serialize_active_playoff_series(getattr(tournament_instance, 'active_playoff_series', None)),
        "campione": campione_nome,
        "finals_mvp": tournament_instance.finals_mvp.nome if hasattr(getattr(tournament_instance, 'finals_mvp', None), 'nome') else (str(tournament_instance.finals_mvp) if getattr(tournament_instance, 'finals_mvp', None) else None),
        "finals_series_log": getattr(tournament_instance, 'finals_series_log', []),
        "draft_class": draft_class_serialized,
        "scout_staff": getattr(tournament_instance, 'scout_staff', []),
        "ordine_draft": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'draft_lottery_order', getattr(tournament_instance, 'ordine_draft', []))],
        "draft_lottery_order": [t.nome if hasattr(t, 'nome') else str(t) for t in getattr(tournament_instance, 'draft_lottery_order', getattr(tournament_instance, 'ordine_draft', []))],
        "draft_pick_corrente": getattr(tournament_instance, 'draft_pick_corrente', 0),
        "draft_risultati": getattr(tournament_instance, 'draft_risultati', []),
        "pick_ownership": getattr(tournament_instance, 'pick_ownership', {}),
        "pick_protections": getattr(tournament_instance, 'pick_protections', {}),
        "trade_analytics_history": getattr(tournament_instance, 'trade_analytics_history', []),
        "awards": awards,
        "all_star_state": all_star_state,
        "offseason_log_data": getattr(tournament_instance, 'offseason_log_data', {}),
        "pending_trade_block_offers": getattr(tournament_instance, 'pending_trade_block_offers', []),
        "user_gm_profile": serialize_user_gm_profile(getattr(tournament_instance, 'user_gm_profile', None)),
        "records": export_raw_records(),
        "news_feed": export_raw_news(),
        "league_settings": getattr(tournament_instance, 'league_settings', {}),
        "box_scores": getattr(tournament_instance, 'box_scores', {}),
        "front_office": front_office.to_dict() if front_office is not None else None
    }
    
    if extra_playoff_data:
        state["extra_playoff_data"] = extra_playoff_data
        
    return state

def _restored_team_id(saved: Optional[str], current: str) -> str:
    """The franchise id after a restore: the saved one, but an empty saved id (old save) keeps the current one."""
    return saved or current or ""


def saved_league_registry(state_data: Dict[str, Any]):
    """The franchise registry a save plays with: the one it stores, else (old save) a legacy registry
    built from its stored team names (core/league/draft_source.py). Builds it only; nothing is installed."""
    from core.league.draft_source import legacy_registry_for
    from core.league.registry import FranchiseRegistry
    league_state = (state_data or {}).get("league") or {}
    if league_state.get("registry"):
        return FranchiseRegistry.from_dict(league_state["registry"])
    names = [d.get("nome") for d in (state_data or {}).get("squadre_data") or [] if d.get("nome")]
    return legacy_registry_for(names)


def _legacy_team_id(name: str, registry: Any) -> str:
    """Franchise id of a team in an old save: CONFIG.LEAGUE.LEGACY_TEAM_IDS, else the registry's name match."""
    from core.config import CONFIG
    team_id = CONFIG.LEAGUE.LEGACY_TEAM_IDS.get(name)
    if team_id:
        return team_id
    franchise = registry.by_name(name) if registry is not None else None
    return franchise.id if franchise else ""


def restore_tournament_state(tournament_instance: Any, state_data: Dict[str, Any]):
    """Restores the in-memory state of the league (standings, rosters, calendar, playoffs, draft class, user team, records, news)."""
    if not tournament_instance or not state_data:
        return
        
    if "starting_year" in state_data:
        tournament_instance.starting_year = state_data["starting_year"]
    if "anno_corrente" in state_data:
        tournament_instance.anno_corrente = state_data["anno_corrente"]

    if "season_number" in state_data:
        tournament_instance.season_number = state_data["season_number"]
        if hasattr(tournament_instance, 'update_dynamic_economy'):
            tournament_instance.update_dynamic_economy()
            
    cur_day = state_data.get("_current_gameday", state_data.get("current_day", 0))
    tournament_instance.current_day = cur_day
    tournament_instance._current_gameday = cur_day
    tournament_instance._trade_deadline_completed = state_data.get("_trade_deadline_completed", False)
        
    if "league_state" in state_data:
        tournament_instance.league_state = state_data["league_state"]
    if "fase_torneo" in state_data:
        tournament_instance.fase_torneo = state_data["fase_torneo"]

    if "salary_cap" in state_data:
        tournament_instance.salary_cap = state_data["salary_cap"]
    if "luxury_tax_threshold" in state_data:
        tournament_instance.luxury_tax_threshold = state_data["luxury_tax_threshold"]
    if "first_apron_threshold" in state_data:
        tournament_instance.first_apron_threshold = state_data["first_apron_threshold"]
        tournament_instance.first_apron = state_data["first_apron_threshold"]
    if "second_apron_threshold" in state_data:
        tournament_instance.second_apron_threshold = state_data["second_apron_threshold"]
        tournament_instance.second_apron = state_data["second_apron_threshold"]
    if "mle_amount" in state_data:
        tournament_instance.mle_amount = state_data["mle_amount"]
        tournament_instance.mle_value = state_data["mle_amount"]
    if "bae_amount" in state_data:
        tournament_instance.bae_amount = state_data["bae_amount"]
    if "minimum_salary" in state_data:
        tournament_instance.minimum_salary = state_data["minimum_salary"]
        tournament_instance.min_salary = state_data["minimum_salary"]

    # League identity. Old saves have no registry: they get a legacy one (Real Names 2002 mod, else the
    # fictional league renamed by team id), never the one of the career played before in this process.
    league_state = state_data.get("league") or {}
    tournament_instance.league_meta = dict(league_state.get("meta") or {})
    from core.league.registry import set_active_registry
    legacy_league = not league_state.get("registry")
    tournament_instance.franchise_registry = saved_league_registry(state_data)
    set_active_registry(tournament_instance.franchise_registry)

    team_dict = {s.nome: s for s in getattr(tournament_instance, 'squadre', [])}

    # Restore teams, rosters and coaches if present
    if "squadre_data" in state_data and state_data["squadre_data"]:
        for s_data in state_data["squadre_data"]:
            nome = s_data.get("nome")
            if nome in team_dict:
                s = team_dict[nome]
                s.team_id = _restored_team_id(s_data.get("team_id"), getattr(s, "team_id", ""))
                # Old save: the conference it was played with (the registry active at setup may not know the name)
                if legacy_league and s_data.get("conference") in ("East", "West"):
                    s.conference = s_data["conference"]
                s.vittorie = s_data.get("vittorie", 0)
                s.sconfitte = s_data.get("sconfitte", 0)
                s.punti_fatti = s_data.get("punti_fatti", 0)
                s.punti_subiti = s_data.get("punti_subiti", 0)
                s.vittorie_casa = s_data.get("vittorie_casa", 0)
                s.sconfitte_casa = s_data.get("sconfitte_casa", 0)
                s.vittorie_trasferta = s_data.get("vittorie_trasferta", 0)
                s.sconfitte_trasferta = s_data.get("sconfitte_trasferta", 0)
                s.vittorie_conf = s_data.get("vittorie_conf", 0)
                s.sconfitte_conf = s_data.get("sconfitte_conf", 0)
                s.striscia_tipo = s_data.get("striscia_tipo", "V")
                s.striscia_numero = s_data.get("striscia_numero", 0)
                if "ultime_10" in s_data:
                    s.ultime_10 = s_data["ultime_10"]
                if "team_goal" in s_data:
                    s.team_goal = s_data["team_goal"]
                # Older saves did not store the owner: keep the one assigned by setup_simulation
                saved_owner = normalize_owner_personality(s_data.get("personalita_proprietario"))
                if saved_owner:
                    s.personalita_proprietario = saved_owner
                if "vittorie_attese" in s_data:
                    s.vittorie_attese = s_data["vittorie_attese"]
                if "intesa" in s_data:
                    s.intesa = s_data["intesa"]
                if "strategia" in s_data:
                    s.strategia = s_data["strategia"]
                if "ha_usato_mle" in s_data:
                    s.ha_usato_mle = s_data["ha_usato_mle"]
                if "ha_usato_bae" in s_data:
                    s.ha_usato_bae = s_data["ha_usato_bae"]
                if "anni_in_luxury_tax" in s_data:
                    s.anni_in_luxury_tax = s_data["anni_in_luxury_tax"]
                if "active_poe" in s_data:
                    s.active_poe = s_data["active_poe"]
                if "tactical_plan" in s_data:
                    s.tactical_plan = deserialize_tactical_plan(s_data["tactical_plan"])
                if "user_custom_lineup" in s_data:
                    s.user_custom_lineup = normalize_role_keys(s_data["user_custom_lineup"])
                if "rotazioni_personalizzate_utente" in s_data:
                    s.rotazioni_personalizzate_utente = s_data["rotazioni_personalizzate_utente"]
                if "draft_picks" in s_data and s_data["draft_picks"]:
                    try:
                        s.draft_picks = {int(k): v for k, v in s_data["draft_picks"].items()}
                    except (ValueError, TypeError):
                        pass
                if "financial_summary" in s_data:
                    s.financial_summary = s_data["financial_summary"]
                if "standings_history" in s_data:
                    s.standings_history = list(s_data["standings_history"])

                if "coach" in s_data and s_data["coach"]:
                    s.coach = deserialize_coach(s_data["coach"])

                if "roster" in s_data:
                    restored_roster = []
                    for p_data in s_data["roster"]:
                        p_obj = deserialize_player(p_data, s)
                        restored_roster.append(p_obj)
                    s.roster = restored_roster

                roster_by_name = {p.nome: p for p in s.roster}

                if "rotazione" in s_data and s_data["rotazione"]:
                    restored_rot = []
                    for item in s_data["rotazione"]:
                        p_name = item.get("nome") if isinstance(item, dict) else str(item)
                        if p_name in roster_by_name:
                            restored_rot.append(roster_by_name[p_name])
                    if restored_rot:
                        s.rotazione = restored_rot

                if "quintetto_names" in s_data and s_data["quintetto_names"]:
                    s.quintetto = [roster_by_name[n] for n in s_data["quintetto_names"] if n in roster_by_name]
                if "panchina_names" in s_data and s_data["panchina_names"]:
                    s.panchina = [roster_by_name[n] for n in s_data["panchina_names"] if n in roster_by_name]

                if "posizione_in_campo" in s_data and isinstance(s_data["posizione_in_campo"], dict):
                    s.posizione_in_campo = {normalize_role(pos): roster_by_name[n] for pos, n in s_data["posizione_in_campo"].items() if n in roster_by_name}

                if "user_custom_lineup" in s_data and isinstance(s_data["user_custom_lineup"], dict):
                    s.user_custom_lineup = normalize_role_keys(s_data["user_custom_lineup"])

                if "board_profile" in s_data and s_data["board_profile"]:
                    s.board_profile = deserialize_board_profile(s_data["board_profile"])

                if "front_office_summit" in s_data:
                    s.front_office_summit = s_data.get("front_office_summit")

                if "pending_board_concern" in s_data:
                    s.pending_board_concern = s_data.get("pending_board_concern")
    elif "squadre_stats" in state_data:
        for s_data in state_data.get("squadre_stats", []):
            nome = s_data.get("nome")
            if nome in team_dict:
                s = team_dict[nome]
                s.vittorie = s_data.get("vittorie", 0)
                s.sconfitte = s_data.get("sconfitte", 0)
                s.punti_fatti = s_data.get("punti_fatti", 0)
                s.punti_subiti = s_data.get("punti_subiti", 0)
                s.vittorie_casa = s_data.get("vittorie_casa", 0)
                s.sconfitte_casa = s_data.get("sconfitte_casa", 0)
                s.vittorie_trasferta = s_data.get("vittorie_trasferta", 0)
                s.sconfitte_trasferta = s_data.get("sconfitte_trasferta", 0)
                s.vittorie_conf = s_data.get("vittorie_conf", 0)
                s.sconfitte_conf = s_data.get("sconfitte_conf", 0)
                s.striscia_tipo = s_data.get("striscia_tipo", "V")
                s.striscia_numero = s_data.get("striscia_numero", 0)
                if "ultime_10" in s_data:
                    s.ultime_10 = s_data["ultime_10"]

    if legacy_league:
        # Old save: every team gets its franchise id, and the conference lists follow the restored conferences.
        from core.config import CONFIG
        for s in getattr(tournament_instance, 'squadre', []):
            if not getattr(s, 'team_id', ''):
                s.team_id = _legacy_team_id(s.nome, tournament_instance.franchise_registry)
            if s.nome not in CONFIG.LEAGUE.LEGACY_TEAM_IDS:
                # One line per renamed team, so a missing division/rivalry/branding is explained in the log.
                logger.warning("Old save: team '%s' is not in CONFIG.LEAGUE.LEGACY_TEAM_IDS; %s", s.nome,
                               f"matched by name to franchise '{s.team_id}'" if s.team_id else
                               "it has no franchise id, so its division, rivalries and branding use the defaults")
        if hasattr(tournament_instance, 'squadre_est'):
            tournament_instance.squadre_est = [s for s in tournament_instance.squadre if s.conference == 'East']
        if hasattr(tournament_instance, 'squadre_ovest'):
            tournament_instance.squadre_ovest = [s for s in tournament_instance.squadre if s.conference == 'West']

    if "free_agents_pool" in state_data:
        tournament_instance.free_agents_pool = [deserialize_player(p_data, None) for p_data in state_data["free_agents_pool"]]
    if "giocatori_ritirati" in state_data:
        tournament_instance.giocatori_ritirati = [deserialize_player(p_data, None) for p_data in state_data["giocatori_ritirati"]]
    if "nuovi_free_agents" in state_data:
        tournament_instance.nuovi_free_agents = [deserialize_player(p_data, None) for p_data in state_data["nuovi_free_agents"]]
    if "unemployed_coaches" in state_data:
        tournament_instance.unemployed_coaches = [deserialize_coach(c_data) for c_data in state_data["unemployed_coaches"] if c_data]

    # Restore calendar results and matchups
    cal_data = state_data.get("calendario", [])
    if cal_data:
        new_calendario = []
        for _day_idx, giornata in enumerate(cal_data):
            if isinstance(giornata, dict) and "day_index" in giornata and "games" in giornata:
                from core.calendar_generator import CalendarDay
                c_day = CalendarDay.from_dict(giornata)
                for g in c_day.games:
                    g.home_team_obj = team_dict.get(g.home_team)
                    g.away_team_obj = team_dict.get(g.away_team)
                new_calendario.append(c_day)
            elif isinstance(giornata, list):
                giornata_matches = []
                for m_data in giornata:
                    if isinstance(m_data, dict):
                        s1_name = m_data.get('s1')
                        s2_name = m_data.get('s2')
                        s1_obj = team_dict.get(s1_name)
                        s2_obj = team_dict.get(s2_name)
                        if s1_obj and s2_obj:
                            giornata_matches.append((s1_obj, s2_obj))
                    elif isinstance(m_data, (tuple, list)) and len(m_data) >= 2:
                        s1_name = m_data[0] if isinstance(m_data[0], str) else getattr(m_data[0], 'nome', str(m_data[0]))
                        s2_name = m_data[1] if isinstance(m_data[1], str) else getattr(m_data[1], 'nome', str(m_data[1]))
                        s1_obj = team_dict.get(s1_name)
                        s2_obj = team_dict.get(s2_name)
                        if s1_obj and s2_obj:
                            giornata_matches.append((s1_obj, s2_obj))
        tournament_instance.calendario = new_calendario
        # If _current_gameday is 0 but there are already played games, sync it with the first game day to be played
        if tournament_instance.calendario and getattr(tournament_instance, '_current_gameday', 0) == 0:
            for d_idx, day in enumerate(tournament_instance.calendario):
                games_list = getattr(day, 'games', []) if hasattr(day, 'games') else (day if isinstance(day, list) else [])
                if any(not getattr(g, 'played', False) for g in games_list):
                    if d_idx > 0:
                        tournament_instance._current_gameday = d_idx
                        tournament_instance.current_day = d_idx
                    break

    # Restore box scores
    tournament_instance.box_scores = state_data.get("box_scores", {})

    # Restore playoffs and play-in
    if "playoff_bracket_data" in state_data:
        tournament_instance.playoff_bracket_data = state_data["playoff_bracket_data"]
    if "playoff_state" in state_data:
        tournament_instance.playoff_state = state_data["playoff_state"]
    if "play_in_results" in state_data and isinstance(state_data["play_in_results"], dict):
        restored_pir = {}
        for conf, cdata in state_data["play_in_results"].items():
            if isinstance(cdata, dict):
                restored_pir[conf] = {}
                for k, v in cdata.items():
                    if isinstance(v, dict):
                        v_copy = dict(v)
                        if "winner_obj" in v_copy and isinstance(v_copy["winner_obj"], str) and v_copy["winner_obj"] in team_dict:
                            v_copy["winner_obj"] = team_dict[v_copy["winner_obj"]]
                        if "loser_obj" in v_copy and isinstance(v_copy["loser_obj"], str) and v_copy["loser_obj"] in team_dict:
                            v_copy["loser_obj"] = team_dict[v_copy["loser_obj"]]
                        restored_pir[conf][k] = v_copy
                    else:
                        restored_pir[conf][k] = v
            else:
                restored_pir[conf] = cdata
        tournament_instance.play_in_results = restored_pir

    if "play_in_game_index" in state_data:
        tournament_instance.play_in_game_index = state_data["play_in_game_index"]

    if "active_playoff_series" in state_data and isinstance(state_data["active_playoff_series"], list):
        restored_series = []
        for s in state_data["active_playoff_series"]:
            if isinstance(s, dict):
                s_copy = dict(s)
                if "s1" in s_copy and isinstance(s_copy["s1"], str) and s_copy["s1"] in team_dict:
                    s_copy["s1"] = team_dict[s_copy["s1"]]
                if "s2" in s_copy and isinstance(s_copy["s2"], str) and s_copy["s2"] in team_dict:
                    s_copy["s2"] = team_dict[s_copy["s2"]]
                restored_series.append(s_copy)
            else:
                restored_series.append(s)
        tournament_instance.active_playoff_series = restored_series
        
    if "playoff_teams" in state_data:
        p_teams = state_data["playoff_teams"]
        tournament_instance.playoff_teams = {
            'east': [team_dict[n] for n in p_teams.get('east', []) if n in team_dict],
            'west': [team_dict[n] for n in p_teams.get('west', []) if n in team_dict]
        }
    if "direct_qualifiers" in state_data:
        d_teams = state_data["direct_qualifiers"]
        tournament_instance.direct_qualifiers = {
            'east': [team_dict[n] for n in d_teams.get('east', []) if n in team_dict],
            'west': [team_dict[n] for n in d_teams.get('west', []) if n in team_dict]
        }
    if "play_in_teams" in state_data:
        pi_teams = state_data["play_in_teams"]
        tournament_instance.play_in_teams = {
            'east': [team_dict[n] for n in pi_teams.get('east', []) if n in team_dict],
            'west': [team_dict[n] for n in pi_teams.get('west', []) if n in team_dict]
        }
    if "next_round_teams" in state_data and isinstance(state_data["next_round_teams"], dict):
        nr_teams = state_data["next_round_teams"]
        tournament_instance.next_round_teams = {
            'east': [team_dict[n] for n in nr_teams.get('east', []) if n in team_dict],
            'west': [team_dict[n] for n in nr_teams.get('west', []) if n in team_dict]
        }

    if state_data.get("campione") and state_data["campione"] in team_dict:
        tournament_instance.campione = team_dict[state_data["campione"]]
    if "finals_mvp" in state_data:
        restore_finals_mvp(tournament_instance, state_data["finals_mvp"])
    if "finals_series_log" in state_data:
        tournament_instance.finals_series_log = state_data["finals_series_log"]
    if state_data.get("awards"):
        restore_awards(tournament_instance, state_data["awards"])
    restore_all_star(tournament_instance, state_data.get("all_star_state"))

    # Ripristina classe draft e scouting
    if "draft_class" in state_data and state_data["draft_class"]:
        restored_class = []
        for item in state_data["draft_class"]:
            if isinstance(item, dict):
                p_obj = deserialize_player(item, None)
                restored_class.append(p_obj)
            else:
                restored_class.append(item)
        tournament_instance.draft_class = restored_class

    if "scout_staff" in state_data and state_data["scout_staff"]:
        tournament_instance.scout_staff = state_data["scout_staff"]
    if "draft_lottery_order" in state_data:
        tournament_instance.draft_lottery_order = state_data["draft_lottery_order"]
        tournament_instance.ordine_draft = state_data["draft_lottery_order"]
    elif "ordine_draft" in state_data:
        tournament_instance.draft_lottery_order = state_data["ordine_draft"]
        tournament_instance.ordine_draft = state_data["ordine_draft"]
    if "draft_pick_corrente" in state_data:
        tournament_instance.draft_pick_corrente = state_data["draft_pick_corrente"]
    if "draft_risultati" in state_data:
        tournament_instance.draft_risultati = state_data["draft_risultati"]

    if "pick_ownership" in state_data and state_data["pick_ownership"]:
        try:
            tournament_instance.pick_ownership = {int(k): v for k, v in state_data["pick_ownership"].items()}
        except (ValueError, TypeError):
            pass
    if "pick_protections" in state_data and state_data["pick_protections"]:
        try:
            tournament_instance.pick_protections = {int(k): v for k, v in state_data["pick_protections"].items()}
        except (ValueError, TypeError):
            pass

    if "offseason_log_data" in state_data:
        tournament_instance.offseason_log_data = state_data["offseason_log_data"]
    if "trade_analytics_history" in state_data:
        tournament_instance.trade_analytics_history = state_data["trade_analytics_history"]
    if "pending_trade_block_offers" in state_data:
        tournament_instance.pending_trade_block_offers = state_data["pending_trade_block_offers"]

    if "user_gm_profile" in state_data and state_data["user_gm_profile"]:
        tournament_instance.user_gm_profile = deserialize_user_gm_profile(state_data["user_gm_profile"])

    # Restore the league's historical records and news feed
    if "records" in state_data:
        import_raw_records(state_data["records"])
    if "news_feed" in state_data:
        import_raw_news(state_data["news_feed"])

    # Restore the user team
    player_team_name = state_data.get("player_team_name")
    is_spec = state_data.get("is_spectator", False)
    if player_team_name and player_team_name != "Spettatore" and player_team_name in team_dict:
        tournament_instance.squadra_giocatore = team_dict[player_team_name]
        tournament_instance.is_spectator = False
    elif is_spec:
        tournament_instance.squadra_giocatore = None
        tournament_instance.is_spectator = True

    # Restore league settings and sandbox
    if "league_settings" in state_data:
        tournament_instance.league_settings = state_data["league_settings"]
        if hasattr(tournament_instance, 'resolve_play_in'):
            tournament_instance.resolve_play_in()
        else:
            tournament_instance.enable_play_in = state_data["league_settings"].get("enable_play_in", True)
        tournament_instance.cba_mode = state_data["league_settings"].get("cba_mode", "realistic")
        tournament_instance.injury_frequency = state_data["league_settings"].get("injury_frequency", "realistic")
        tournament_instance.trade_difficulty = state_data["league_settings"].get("trade_difficulty", "realistic")
        tournament_instance.scouting_fog_of_war = state_data["league_settings"].get("scouting_fog_of_war", True)
        tournament_instance.gm_firing_enabled = state_data["league_settings"].get("gm_firing_enabled", True)
        tournament_instance.user_role = state_data["league_settings"].get("user_role", "gm_coach")

    # CPU GMs, team plans and move logs. Saves from before the AI GM get them built now, from the teams and the
    # season (deterministic), replacing whatever setup_simulation built for a fresh league.
    from core.front_office.state import FrontOfficeState, build_front_office, fill_careers, sync_user_seat, current_year
    from core.front_office.plans import seed_missing_plans
    from core.front_office.seasons import ensure_season_marks
    if state_data.get("front_office"):
        tournament_instance.front_office = FrontOfficeState.from_dict(state_data["front_office"])
        fill_careers(tournament_instance.front_office, current_year(tournament_instance))
        sync_user_seat(tournament_instance)  # no-op unless the seats disagree with the user's team
        seed_missing_plans(tournament_instance, tournament_instance.front_office)
    else:
        tournament_instance.front_office = build_front_office(tournament_instance)
    # Saves from before the season marks: this season's expectation is set now (no-op when the mark exists)
    ensure_season_marks(tournament_instance, tournament_instance.front_office)

    # Sync historical awards and rings for all players from player_careers.json
    sync_player_awards_from_careers(tournament_instance)

def restore_finals_mvp(tournament_instance: Any, name: Optional[str]):
    """The Finals MVP is saved by name; look the player up again in the restored rosters and free agents.
    Unknown names (e.g. retired since) give None so the league payload never sees a bare string."""
    found = None
    if name:
        pools = [getattr(s, 'roster', []) for s in getattr(tournament_instance, 'squadre', [])]
        pools.append(getattr(tournament_instance, 'free_agents_pool', []))
        found = next((p for pool in pools for p in pool if p.nome == name), None)
    tournament_instance.finals_mvp = found


def restore_awards(tournament_instance: Any, awards: Dict[str, Any]):
    """
    Puts the season awards back after a load. They are saved as player names, so each winner is looked up
    again in the restored rosters (and the free-agent pool). The awards payload needs MVP, DPOY and Sixth Man
    together, so if one of them cannot be found the individual awards stay empty instead of half-filled.
    """
    players: Dict[str, Any] = {}
    for squadra in getattr(tournament_instance, 'squadre', []):
        for p in getattr(squadra, 'roster', []):
            players.setdefault(p.nome, p)
    for p in getattr(tournament_instance, 'free_agents_pool', []):
        players.setdefault(p.nome, p)

    def find(name: Optional[str]):
        return players.get(name) if name else None

    winners = {attr: find(awards.get(attr)) for attr in (
        "regular_season_mvp", "defensive_player_of_the_year", "sesto_uomo", "rookie_of_the_year", "most_improved_player")}
    if all(winners[k] for k in ("regular_season_mvp", "defensive_player_of_the_year", "sesto_uomo")):
        for attr, player in winners.items():
            setattr(tournament_instance, attr, player)
    tournament_instance.coach_of_the_year = awards.get("coach_of_the_year")
    tournament_instance.gm_of_the_year = awards.get("gm_of_the_year")
    tournament_instance.all_nba_teams = [[players[n] for n in team if n in players] for team in awards.get("all_nba_teams", [])]
    tournament_instance.all_defensive_team = [players[n] for n in awards.get("all_defensive_team", []) if n in players]
    tournament_instance.all_rookie_team = [players[n] for n in awards.get("all_rookie_team", []) if n in players]


def restore_all_star(tournament_instance: Any, state: Optional[Dict[str, Any]]):
    """
    Puts the All-Star weekend back after a load. Players are saved as names, so each one is looked up again in
    the restored rosters and free agents; unknown names are dropped. Old saves may lack the newer keys
    (weekend, hosts, last_season_rookies) and may hold the old game-log shape, which is kept as it is.
    """
    state = state or {}
    players: Dict[str, Any] = {}
    for squadra in getattr(tournament_instance, 'squadre', []):
        for p in getattr(squadra, 'roster', []):
            players.setdefault(p.nome, p)
    for p in getattr(tournament_instance, 'free_agents_pool', []):
        players.setdefault(p.nome, p)

    def by_conf(key: str) -> Dict[str, list]:
        saved = state.get(key) or {}
        return {conf: [players[n] for n in (saved.get(conf) or []) if n in players] for conf in ('east', 'west')}

    def contest(key: str) -> Dict[str, Any]:
        saved = state.get(key)
        if not isinstance(saved, dict):
            return {'participants': [], 'results': [], 'winner': None}
        restored = dict(saved)
        restored['participants'] = [players[n] for n in (saved.get('participants') or []) if n in players]
        restored.setdefault('results', [])
        restored.setdefault('winner', None)
        return restored

    tournament_instance.all_star_rosters = by_conf('all_star_rosters')
    tournament_instance.all_star_starters = by_conf('all_star_starters')
    tournament_instance.all_star_reserves = by_conf('all_star_reserves')
    tournament_instance.all_star_game_log = state.get('all_star_game_log')
    tournament_instance.all_star_mvp = state.get('all_star_mvp')
    tournament_instance.three_point_contest = contest('three_point_contest')
    tournament_instance.dunk_contest = contest('dunk_contest')
    tournament_instance.all_star_weekend = state.get('weekend')
    tournament_instance.all_star_weekend_complete = bool(state.get('all_star_weekend_complete', False))
    tournament_instance.last_season_rookies = list(state.get('last_season_rookies') or [])
    tournament_instance.all_star_hosts = list(state.get('hosts') or [])


def sync_player_awards_from_careers(tournament_instance: Any, specific_save_path: Optional[str] = None):
    """
    Retroactively syncs the awards and rings won by all the players in memory
    starting from player_careers.json, ensuring old saves also recover their trophies.
    """
    if not tournament_instance:
        return
        
    career_file = None
    if specific_save_path:
        cand = os.path.join(specific_save_path, 'player_careers.json')
        if os.path.exists(cand):
            career_file = cand
    if not career_file:
        cand = os.path.join(BASE_DIR, 'player_careers.json')
        if os.path.exists(cand):
            career_file = cand
            
    if not career_file or not os.path.exists(career_file):
        return
        
    try:
        with open(career_file, 'r', encoding='utf-8') as f:
            all_careers = json.load(f)
        if not isinstance(all_careers, dict):
            return

        all_players = []
        for s in getattr(tournament_instance, 'squadre', []):
            all_players.extend(getattr(s, 'roster', []))
        all_players.extend(getattr(tournament_instance, 'free_agents_pool', []))
        all_players.extend(getattr(tournament_instance, 'giocatori_ritirati', []))

        player_map = {}
        for p in all_players:
            if hasattr(p, 'nome'):
                norm_name = p.nome.replace(" ", "-").lower()
                clean_name = ''.join(c for c in p.nome.lower() if c.isalnum())
                player_map[norm_name] = p
                player_map[clean_name] = p

        for c_key, seasons in all_careers.items():
            clean_ckey = ''.join(c for c in c_key.lower() if c.isalnum())
            p = player_map.get(c_key) or player_map.get(clean_ckey)
            if p:
                rings = 0
                awards_list = []
                for entry in seasons:
                    if isinstance(entry, dict):
                        if entry.get("is_champion"):
                            rings += 1
                        for aw in entry.get("premi", []):
                            awards_list.append(aw)
                if awards_list or seasons:
                    p.premi = awards_list
                p.anelli_vinti = max(getattr(p, 'anelli_vinti', 0), rings)
    except Exception as e:
        logger.warning("Could not sync career awards: %s", e)

# Older save formats -> current: version -> fn(metadata, state_data) bringing a save of that version to the next.
# Version 1 (no save_version field) and 2 hold the same content: nothing to migrate yet.
MIGRATIONS: Dict[int, Any] = {}

_DEFAULT_HISTORY = {"player_careers.json": {}, "franchise_records.json": {}, "trades_history.txt": ""}


def _write_default_history(path: str, filename: str) -> None:
    default = _DEFAULT_HISTORY.get(filename, [])
    if isinstance(default, str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(default)
    else:
        atomic_write_json(path, default, indent=2)


def _display_name(save_name: str, save_path: str, old_meta: Dict[str, Any]) -> str:
    """A save called by its folder name ('Toronto_Raptors_2002', after a load) keeps the name it was given."""
    old = str(old_meta.get("display_name") or "").strip()
    if save_name.strip() == os.path.basename(save_path) and old and sanitize_save_name(old) == os.path.basename(save_path):
        return old
    return save_name.strip()

def save_game(save_name: str, tournament_instance: Any, extra_metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """Saves the whole current league into saves/<save_name>/ in one all-or-nothing commit (core/save_store):
    the state, the database, the metadata and the session's history files always come from the same moment."""
    global _SESSION_OWNER
    from core import save_store
    save_path = get_save_path(save_name)
    os.makedirs(save_path, exist_ok=True)
    save_store.roll_forward(save_path)

    user_team = getattr(tournament_instance, 'squadra_giocatore', None) if tournament_instance else None
    team_name = user_team.nome if user_team else "Spettatore"
    is_spec = getattr(tournament_instance, 'is_spectator', False) if tournament_instance else True
    if user_team is None:
        is_spec = True
    team_record = f"{getattr(user_team, 'vittorie', 0)}-{getattr(user_team, 'sconfitte', 0)}" if user_team else "N/A"

    season_num = getattr(tournament_instance, 'season_number', 1) if tournament_instance else 1
    era_name = getattr(tournament_instance, 'era_name', 'Modern Era 2026') if tournament_instance else 'Modern Era 2026'
    league_phase = getattr(tournament_instance, 'league_state', 'PRE_SEASON') if tournament_instance else 'PRE_SEASON'

    now_iso = datetime.datetime.now().isoformat()
    # Serialize first: if it fails nothing on disk has been touched yet.
    try:
        tournament_state = serialize_tournament_state(tournament_instance, extra_playoff_data=extra_metadata)
    except Exception as e:
        logger.exception("Could not serialize tournament state for save '%s'", save_name)
        raise SaveError(f"Could not serialize the league state: {e}") from e

    staging = os.path.join(save_path, ".staging")
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)
    session_bound = _SESSION_OWNER is not None
    same_slot = _SESSION_OWNER == os.path.basename(save_path)
    try:
        staged: Dict[str, str] = {}

        try:
            state_tmp = os.path.join(staging, "tournament_state.json")
            atomic_write_json(state_tmp, tournament_state, indent=None)
            staged["tournament_state.json"] = state_tmp
        except Exception as e:
            logger.exception("Could not write tournament_state.json for save '%s'", save_name)
            raise SaveError(f"Could not write the league state: {e}") from e

        db_active = os.path.join(BASE_DIR, 'data', 'nba_sim.db')
        if os.path.exists(db_active):
            try:
                db_tmp = os.path.join(staging, "nba_sim.db")
                shutil.copyfile(db_active, db_tmp)
                staged["nba_sim.db"] = db_tmp
            except Exception as e:
                logger.exception("Could not copy the database into '%s'", save_path)
                raise SaveError(f"Could not copy the league database: {e}") from e

        # History: the session copy is the truth when it belongs to this game. A file the last save already
        # holds unchanged is not copied again (player_careers alone is 15 MB in a long career).
        old_meta = {}
        meta_live = os.path.join(save_path, "save_metadata.json")
        if os.path.isfile(meta_live):
            try:
                with open(meta_live, 'r', encoding='utf-8') as f:
                    old_meta = json.load(f)
            except Exception:
                old_meta = {}
        old_digests = old_meta.get("digests") if isinstance(old_meta.get("digests"), dict) else {}
        digests: Dict[str, str] = {}
        for filename in HISTORY_FILES:
            live = os.path.join(save_path, filename)
            src = os.path.join(get_session_dir(), filename) if session_bound else None
            if src and os.path.isfile(src):
                digest = save_store.file_digest(src)
                if same_slot and os.path.isfile(live) and old_digests.get(filename) == digest:
                    digests[filename] = digest
                    continue
                staged[filename] = src
                digests[filename] = digest
            elif not os.path.isfile(live):
                tmp = os.path.join(staging, filename)
                _write_default_history(tmp, filename)
                staged[filename] = tmp
                digests[filename] = save_store.file_digest(tmp)
            else:
                digests[filename] = old_digests.get(filename) or save_store.file_digest(live)

        metadata = {
            "save_name": os.path.basename(save_path),
            "display_name": _display_name(save_name, save_path, old_meta),
            "last_saved": now_iso,
            "era": era_name,
            "season": season_num,
            "phase": league_phase,
            "player_team_name": team_name,
            "player_team_record": team_record,
            "is_spectator": is_spec,
            "user_role": getattr(tournament_instance, 'user_role', 'gm_coach'),
            "league_settings": getattr(tournament_instance, 'league_settings', {})
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        metadata["save_version"] = save_store.SAVE_VERSION
        metadata["game_version"] = game_version.VERSION
        metadata["digests"] = digests
        meta_tmp = os.path.join(staging, "save_metadata.json")
        atomic_write_json(meta_tmp, metadata, indent=4)
        staged["save_metadata.json"] = meta_tmp

        try:
            save_store.commit(save_path, staged)
        except Exception as e:
            logger.exception("Could not commit save '%s'", save_name)
            raise SaveError(f"Could not write the save: {e}") from e
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if session_bound and not same_slot:
        # "Save as": the game now goes on in this slot, the session copy follows it.
        _SESSION_OWNER = os.path.basename(save_path)
        with open(os.path.join(get_session_dir(), "OWNER"), "w", encoding="utf-8") as f:
            f.write(_SESSION_OWNER)
    return metadata


def _save_version(metadata: Dict[str, Any]) -> int:
    try:
        return int(metadata.get("save_version", 1))
    except (TypeError, ValueError):
        return 1


def _read_state(state_file: str) -> Dict[str, Any]:
    if not os.path.exists(state_file):
        return {}
    with open(state_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_game(save_name: str) -> Dict[str, Any]:
    """Loads the files and tournament state associated with the specified save. A save whose state is
    unreadable falls back to the previous save kept in the slot (`recovered_from_backup` in the result)."""
    from core import save_store
    save_path = get_save_path(save_name)
    if not os.path.exists(save_path):
        raise FileNotFoundError(f"Save '{save_name}' not found.")
    save_store.roll_forward(save_path)

    meta_file = os.path.join(save_path, "save_metadata.json")
    metadata = {}
    if os.path.exists(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    if _save_version(metadata) > save_store.SAVE_VERSION:
        raise SaveError(f"Save '{save_name}' was made with a newer version of the game and cannot be opened.")

    state_file = os.path.join(save_path, "tournament_state.json")
    recovered = False
    try:
        state_data = _read_state(state_file)
    except Exception as e:
        # A missing file is a legacy save; an unreadable one must not become an empty league.
        logger.exception("Could not read %s", state_file)
        if not save_store.restore_backup(save_path):
            raise SaveError(f"The league state of save '{save_name}' is unreadable: {e}") from e
        try:
            state_data = _read_state(state_file)
        except Exception as e2:
            raise SaveError(f"The league state of save '{save_name}' and its backup are unreadable: {e2}") from e2
        recovered = True
        logger.warning("Save '%s' was damaged: the previous save was loaded from its backup", save_name)
        if os.path.exists(meta_file):
            with open(meta_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

    version = _save_version(metadata)
    while version < save_store.SAVE_VERSION:
        migrate = MIGRATIONS.get(version)
        if migrate:
            migrate(metadata, state_data)
        version += 1

    set_active_save_name(save_name)
    open_session(save_name)  # always from the slot: unsaved history of this save is dropped like the rest

    # Restore the save's SQLite database
    db_save_src = os.path.join(save_path, 'nba_sim.db')
    db_active = os.path.join(BASE_DIR, 'data', 'nba_sim.db')
    if os.path.exists(db_save_src):
        try:
            os.makedirs(os.path.dirname(db_active), exist_ok=True)
            shutil.copyfile(db_save_src, db_active)
        except Exception as e:
            logger.exception("Could not restore the database of save '%s'", save_name)
            raise SaveError(f"Could not restore the league database of save '{save_name}': {e}") from e

    return {
        "metadata": metadata,
        "state_data": state_data,
        "save_path": save_path,
        "recovered_from_backup": recovered,
    }

def duplicate_save(source_save_name: str, target_save_name: str) -> Dict[str, Any]:
    """Duplicates a whole save folder, creating an exact copy for testing."""
    source_path = get_save_path(source_save_name)
    target_path = get_save_path(target_save_name)
    
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source save '{source_save_name}' not found.")
        
    if os.path.exists(target_path):
        raise FileExistsError(f"The destination save '{target_save_name}' already exists.")
        
    from core import save_store
    save_store.roll_forward(source_path)
    shutil.copytree(source_path, target_path,
                    ignore=shutil.ignore_patterns(".pending", ".backup*", ".staging"))
    
    meta_file = os.path.join(target_path, "save_metadata.json")
    metadata = {}
    if os.path.exists(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            
    safe_target = os.path.basename(target_path)
    metadata['save_name'] = safe_target
    metadata['display_name'] = target_save_name.strip()
    metadata['last_saved'] = datetime.datetime.now().isoformat()
    
    atomic_write_json(meta_file, metadata, indent=4)
        
    return metadata

def rename_save(old_save_name: str, new_display_name: str) -> Dict[str, Any]:
    """Renames a save by changing the folder and the display_name in the metadata."""
    old_path = get_save_path(old_save_name)
    if not os.path.exists(old_path):
        raise FileNotFoundError(f"Save '{old_save_name}' not found.")
        
    new_safe_name = sanitize_save_name(new_display_name)
    new_path = os.path.join(get_saves_dir(), new_safe_name)
    
    if old_path != new_path:
        if os.path.exists(new_path):
            raise FileExistsError(f"A save named '{new_display_name}' already exists.")
        os.rename(old_path, new_path)
        global _SESSION_OWNER
        if _SESSION_OWNER == os.path.basename(old_path):
            _SESSION_OWNER = new_safe_name
            with open(os.path.join(get_session_dir(), "OWNER"), "w", encoding="utf-8") as f:
                f.write(new_safe_name)
        
    meta_file = os.path.join(new_path, "save_metadata.json")
    metadata = {}
    if os.path.exists(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    metadata['save_name'] = new_safe_name
    metadata['display_name'] = new_display_name.strip()
    metadata['last_saved'] = datetime.datetime.now().isoformat()
    
    atomic_write_json(meta_file, metadata, indent=4)
        
    return metadata

def delete_save(save_name: str) -> bool:
    """Deletes the save folder."""
    save_path = get_save_path(save_name)
    if os.path.exists(save_path):
        shutil.rmtree(save_path)
        if _SESSION_OWNER == os.path.basename(save_path):
            _close_session()
        return True
    return False

def migrate_legacy_files() -> Optional[str]:
    """If historical files exist in the root and the saves/ folder is empty, migrates them into Legacy_Save."""
    saves_dir = get_saves_dir()
    existing_saves = [f for f in os.listdir(saves_dir) if os.path.isdir(os.path.join(saves_dir, f))]
    
    historical_files = ["player_careers.json", "hall_of_fame.json", "league_history.json", "retired_players_ids.json", "franchise_records.json"]
    has_legacy = any(os.path.exists(os.path.join(BASE_DIR, f)) for f in historical_files)
    
    if has_legacy and not existing_saves:
        legacy_path = os.path.join(saves_dir, "Legacy_Save")
        os.makedirs(legacy_path, exist_ok=True)
        
        meta = {
            "save_name": "Legacy_Save",
            "display_name": "Previous Career",
            "last_saved": datetime.datetime.now().isoformat(),
            "era": "Modern Era 2026",
            "season": 1,
            "phase": "PRE_SEASON",
            "player_team_name": "Spettatore",
            "is_spectator": True
        }
        atomic_write_json(os.path.join(legacy_path, "save_metadata.json"), meta, indent=4)
            
        for f in historical_files:
            rf = os.path.join(BASE_DIR, f)
            sf = os.path.join(legacy_path, f)
            if os.path.exists(rf):
                try:
                    shutil.move(rf, sf)
                except Exception as e:
                    logger.warning("Could not migrate legacy file %s: %s", f, e)
        return "Legacy_Save"
    return None
