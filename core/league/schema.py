# core/league/schema.py
"""
League JSON schema (v1): the single source of truth for a league's starting data.

One file per league (the built-in league, or `mods/<Mod Name>/league.json`). It holds everything the
starting database holds, so building the DB from it is deterministic.

Raw (JSON) shape, as produced by `league_to_dict`:
    {"schema_version": 1,
     "meta": {"name", "era", "start_year"},
     "franchises": [ {Franchise fields} x 30 ],
     "players": {team_id: [player dict, ...]},
     "free_agents": [player dict, ...],
     "rivalries": [[team_id, team_id, weight], ...],
     "marquee_hosts": {key: [team_id, ...]},
     "staff": {"coach_names": [...], "owner_names": [...], "gms": {"starting": [...], "arrivals": [...]}}}

Franchise.name is the full display name (normally city + " " + nickname). Player ids ("p0001"..) are
assigned once by the exporter or the league author and never derived from a name.
"""
import json
import os
from dataclasses import dataclass, field, asdict, fields
from typing import Any, Dict, List, Tuple

from core.config import CONFIG
from core.roles import ROLES

SCHEMA_VERSION = 1

CONFERENCES = ("East", "West")
TEAM_COUNT = 30
OWNER_PERSONALITIES = ("Spendaccione", "Bilanciato", "Risparmiatore")  # Italian data words, kept on purpose

META_KEYS = ("name", "era", "start_year")

PLAYER_KEYS = (
    "id", "name", "role", "age", "overall", "potential", "provenance", "pedigree", "morale", "fvs",
    "is_untouchable", "years_on_team", "teams_drafted", "abilities", "tendencies",
)

ABILITY_KEYS = (
    "close_shot_rating", "mid_range_shot_rating", "three_point_shot_rating", "free_throw_rating", "shot_iq",
    "passing_accuracy", "ball_handling", "passing_vision", "interior_defense_rating", "perimeter_defense_rating",
    "steal_rating", "block_rating", "strength", "speed", "acceleration", "vertical", "stamina",
    "offensive_rebound_rating", "defensive_rebound_rating", "dunk_rating", "draw_foul_rating",
    "offensive_iq_rating", "defensive_iq_rating", "post_control_rating",
)

TENDENCY_KEYS = (
    "touch_tendency", "spot_up_shot_tendency", "mid_range_shot_tendency", "three_point_shot_tendency",
    "drive_to_basket_tendency", "post_up_tendency", "pass_out_of_shot_tendency", "dish_to_open_man_tendency",
    "dunk_tendency", "hero_ball_tendency", "putback_tendency", "roll_vs_pop_tendency", "foul_tendency",
    "rebound_tendency", "playmaking_tendency",
)


class LeagueError(Exception):
    """A league file is invalid. `errors` lists every problem in plain English."""

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        shown = "; ".join(self.errors[:5])
        more = f" (+{len(self.errors) - 5} more)" if len(self.errors) > 5 else ""
        super().__init__(f"Invalid league: {shown}{more}")


@dataclass
class Franchise:
    id: str
    name: str
    city: str
    nickname: str
    abbreviation: str
    conference: str
    division: str
    geo_city: str
    primary: str
    secondary: str
    arena: str
    established: int
    market_weight: float
    owner_personality: str
    # Optional UI label for the team's home ("Portland, OR"); empty -> "<geo_city>, <state>".
    display_city: str = ""


@dataclass
class LeagueData:
    schema_version: int
    meta: Dict[str, Any]
    franchises: List[Franchise]
    players: Dict[str, List[dict]]
    free_agents: List[dict] = field(default_factory=list)
    rivalries: List[Tuple[str, str, float]] = field(default_factory=list)
    marquee_hosts: Dict[str, List[str]] = field(default_factory=dict)
    staff: Dict[str, Any] = field(default_factory=dict)


_FRANCHISE_KEYS = tuple(f.name for f in fields(Franchise))
_OPTIONAL_FRANCHISE_KEYS = {"display_city": ""}


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate_player(p: Any, where: str, errors: List[str]) -> None:
    if not isinstance(p, dict):
        errors.append(f"{where}: player entry is not an object")
        return
    label = f"{where} player {p.get('name') or p.get('id') or '?'}"
    for key in PLAYER_KEYS:
        if key not in p:
            errors.append(f"{label}: missing field '{key}'")
    if "name" in p and (not isinstance(p["name"], str) or not p["name"].strip()):
        errors.append(f"{label}: name must be a non-empty string")
    if "role" in p and p["role"] not in ROLES:
        errors.append(f"{label}: unknown role '{p['role']}' (use one of {', '.join(ROLES)})")
    limits = CONFIG.LEAGUE
    for key, (lo, hi) in (("age", limits.PLAYER_AGE_RANGE), ("overall", limits.PLAYER_RATING_RANGE),
                          ("potential", limits.PLAYER_RATING_RANGE)):
        if key not in p:
            continue
        if not _is_int(p[key]):
            errors.append(f"{label}: '{key}' must be an integer")
        elif not lo <= p[key] <= hi:
            errors.append(f"{label}: {key} {p[key]} is outside {lo}-{hi}")
    for key in ("morale", "fvs", "years_on_team"):
        if key in p and not _is_num(p[key]):
            errors.append(f"{label}: '{key}' must be a number")
    skill_lo, skill_hi = limits.PLAYER_SKILL_RANGE
    for key, expected in (("abilities", ABILITY_KEYS), ("tendencies", TENDENCY_KEYS)):
        if key not in p:
            continue
        block = p[key]
        if not isinstance(block, dict) or not block:
            errors.append(f"{label}: {key} missing or empty")
            continue
        for sub in expected:
            if sub not in block:
                errors.append(f"{label}: {key} lacks '{sub}'")
            elif not _is_num(block[sub]):
                errors.append(f"{label}: {key}.{sub} must be a number")
            elif not skill_lo <= block[sub] <= skill_hi:
                errors.append(f"{label}: {key}.{sub} {block[sub]} is outside {skill_lo}-{skill_hi}")


def validate_league(raw: dict) -> List[str]:
    """Returns the problems found (empty = valid). Each message names the team/player at fault."""
    errors: List[str] = []
    if not isinstance(raw, dict):
        return ["League file must be a JSON object"]

    if raw.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}, found {raw.get('schema_version')!r}")

    meta = raw.get("meta")
    if not isinstance(meta, dict):
        errors.append("meta is missing")
    else:
        for key in META_KEYS:
            if key not in meta:
                errors.append(f"meta lacks '{key}'")

    franchises = raw.get("franchises")
    if not isinstance(franchises, list):
        errors.append("franchises is missing")
        franchises = []
    if len(franchises) != TEAM_COUNT:
        errors.append(f"League must have exactly {TEAM_COUNT} teams, found {len(franchises)}")
    team_ids: List[str] = []
    seen_ids, seen_names = set(), set()
    conf_count = {c: 0 for c in CONFERENCES}
    team_names: Dict[str, str] = {}
    div_confs: Dict[str, set] = {}
    div_size: Dict[str, int] = {}
    for i, fr in enumerate(franchises):
        if not isinstance(fr, dict):
            errors.append(f"franchise #{i + 1} is not an object")
            continue
        fid = fr.get("id", f"#{i + 1}")
        for key in _FRANCHISE_KEYS:
            if key not in fr and key not in _OPTIONAL_FRANCHISE_KEYS:
                errors.append(f"team {fid}: missing field '{key}'")
        for key in ("established", "market_weight"):
            if key in fr and not _is_num(fr[key]):
                errors.append(f"team {fid}: '{key}' must be a number")
        if fid in seen_ids:
            errors.append(f"team {fid}: duplicate team id")
        seen_ids.add(fid)
        team_ids.append(fid)
        name = fr.get("name")
        team_names[fid] = str(name or fid)
        if name in seen_names:
            errors.append(f"team {fid}: duplicate team name '{name}'")
        seen_names.add(name)
        conf = fr.get("conference")
        if conf in conf_count:
            conf_count[conf] += 1
        else:
            errors.append(f"team {fid}: conference must be East or West, found {conf!r}")
        if fr.get("owner_personality") not in OWNER_PERSONALITIES:
            errors.append(f"team {fid}: unknown owner_personality {fr.get('owner_personality')!r}")
        if "geo_city" in fr and fr["geo_city"] not in CONFIG.GEO.CITIES:
            errors.append(f"team {fid}: geo_city {fr['geo_city']!r} is not a known city "
                          f"(use one of CONFIG.GEO.CITIES, e.g. {', '.join(list(CONFIG.GEO.CITIES)[:3])})")
        div = fr.get("division")
        if isinstance(div, str) and div:
            div_confs.setdefault(div, set()).add(conf)
            div_size[div] = div_size.get(div, 0) + 1
    if len(franchises) == TEAM_COUNT and any(n != TEAM_COUNT // 2 for n in conf_count.values()):
        errors.append(f"Conferences must have 15 teams each, found East {conf_count['East']}, West {conf_count['West']}")
    for div, confs in sorted(div_confs.items()):
        if len(confs) > 1:
            errors.append(f"division {div} mixes conferences ({', '.join(sorted(str(c) for c in confs))}): "
                          f"each division holds teams of one conference")
    if len(set(div_size.values())) > 1:
        sizes = ", ".join(f"{d} {n}" for d, n in sorted(div_size.items()))
        errors.append(f"All divisions must have the same number of teams, found {sizes}")

    id_set = set(team_ids)
    all_names: Dict[str, str] = {}
    all_ids: Dict[str, str] = {}

    def _track(p: Any, where: str) -> None:
        if not isinstance(p, dict):
            return
        n, pid = p.get("name"), p.get("id")
        if isinstance(n, str):
            if n in all_names:
                errors.append(f"duplicate player name '{n}' ({all_names[n]} and {where})")
            else:
                all_names[n] = where
        if pid is not None:
            if pid in all_ids:
                errors.append(f"duplicate player id '{pid}' ({n})")
            else:
                all_ids[pid] = where

    players = raw.get("players")
    if not isinstance(players, dict):
        errors.append("players is missing")
    else:
        for tid in team_ids:
            if tid not in players:
                errors.append(f"team {tid}: no player list")
        for tid, plist in players.items():
            if tid not in id_set:
                errors.append(f"players lists unknown team id '{tid}'")
                continue
            if not isinstance(plist, list):
                errors.append(f"team {tid}: player list is not an array")
                continue
            if len(plist) < CONFIG.LEAGUE.MIN_ROSTER_SIZE:
                errors.append(f"team {tid} ({team_names.get(tid, tid)}) has {len(plist)} players, "
                              f"needs at least {CONFIG.LEAGUE.MIN_ROSTER_SIZE}")
            for p in plist:
                _validate_player(p, f"team {tid}", errors)
                _track(p, f"team {tid}")
    fas = raw.get("free_agents", [])
    if not isinstance(fas, list):
        errors.append("free_agents must be an array")
    else:
        for p in fas:
            _validate_player(p, "free agents", errors)
            _track(p, "free agents")

    seen_pairs = set()
    for r in raw.get("rivalries") or []:
        if not (isinstance(r, (list, tuple)) and len(r) == 3 and _is_num(r[2])):
            errors.append(f"rivalry {r!r} must be [team_id, team_id, weight]")
            continue
        for tid in r[:2]:
            if tid not in id_set:
                errors.append(f"rivalry {r[0]}-{r[1]} names unknown team id '{tid}'")
        if r[0] == r[1]:
            errors.append(f"rivalry {r[0]}-{r[1]} pairs team {r[0]} with itself")
            continue
        pair = frozenset((str(r[0]), str(r[1])))
        if pair in seen_pairs:
            errors.append(f"rivalry {r[0]}-{r[1]} is listed more than once (A-B and B-A are the same pair)")
        seen_pairs.add(pair)

    hosts = raw.get("marquee_hosts") or {}
    if not isinstance(hosts, dict):
        errors.append("marquee_hosts must be an object")
    else:
        for key, ids in hosts.items():
            for tid in ids if isinstance(ids, list) else []:
                if tid not in id_set:
                    errors.append(f"marquee_hosts '{key}' names unknown team id '{tid}'")

    staff = raw.get("staff")
    if not isinstance(staff, dict):
        errors.append("staff is missing")
    else:
        for key in ("coach_names", "owner_names"):
            if not isinstance(staff.get(key), list) or not staff.get(key):
                errors.append(f"staff.{key} must be a non-empty list")
        gms = staff.get("gms")
        if not isinstance(gms, dict) or not isinstance(gms.get("starting"), list):
            errors.append("staff.gms must hold a 'starting' list")
        else:
            gm_teams = set()
            for gm in gms["starting"]:
                gm = gm if isinstance(gm, dict) else {}
                gt = gm.get("team")
                if gt not in id_set:
                    errors.append(f"GM {gm.get('name')!r} names unknown team id {gt!r}")
                elif gt in gm_teams:
                    errors.append(f"team {gt}: more than one starting GM")
                gm_teams.add(gt)
            for tid in team_ids:
                if tid not in gm_teams:
                    errors.append(f"team {tid}: no starting GM")
    return errors


def league_from_dict(raw: dict) -> LeagueData:
    """Validates and converts a raw dict. Raises LeagueError when invalid."""
    errors = validate_league(raw)
    if errors:
        raise LeagueError(errors)
    return LeagueData(
        schema_version=raw["schema_version"],
        meta=dict(raw["meta"]),
        franchises=[Franchise(**{k: fr.get(k, _OPTIONAL_FRANCHISE_KEYS.get(k)) for k in _FRANCHISE_KEYS})
                    for fr in raw["franchises"]],
        players={tid: [dict(p) for p in plist] for tid, plist in raw["players"].items()},
        free_agents=[dict(p) for p in raw.get("free_agents", [])],
        rivalries=[(r[0], r[1], float(r[2])) for r in raw.get("rivalries") or []],
        marquee_hosts={k: list(v) for k, v in (raw.get("marquee_hosts") or {}).items()},
        staff=json.loads(json.dumps(raw["staff"])),
    )


def load_league(path: str) -> LeagueData:
    """Reads a league JSON file. Raises LeagueError (plain-English list) if unreadable or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LeagueError([f"Cannot read league file '{os.path.basename(path)}': {exc}"])
    return league_from_dict(raw)


def _franchise_to_dict(fr: Franchise) -> dict:
    """asdict, minus optional fields left at their default (so files without them round-trip unchanged)."""
    out = asdict(fr)
    for key, default in _OPTIONAL_FRANCHISE_KEYS.items():
        if out.get(key) == default:
            del out[key]
    return out


def league_to_dict(data: LeagueData) -> dict:
    """Inverse of loading: the raw JSON-shaped dict."""
    return {
        "schema_version": data.schema_version,
        "meta": dict(data.meta),
        "franchises": [_franchise_to_dict(fr) for fr in data.franchises],
        "players": {tid: [dict(p) for p in plist] for tid, plist in data.players.items()},
        "free_agents": [dict(p) for p in data.free_agents],
        "rivalries": [[a, b, w] for a, b, w in data.rivalries],
        "marquee_hosts": {k: list(v) for k, v in data.marquee_hosts.items()},
        "staff": json.loads(json.dumps(data.staff)),
    }
