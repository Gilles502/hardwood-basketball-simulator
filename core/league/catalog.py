# core/league/catalog.py
"""
League catalogue: the built-in league plus every `mods/<folder>/league.json`, which one is active,
and the starting DB generated for each (the Mods screen's "Build league" button).

The built-in league is read from the game root (read-only, shipped); mods, built DBs and the active-league
pointer live under the user root (writable), see core.paths. Every function takes `root` so tests can point
both at one temp folder. A mod's id is its folder name as is; its DB filename is a filesystem-safe slug plus
a short hash of the id, so any folder name works on Windows.
"""
import hashlib
import json
import os
import re
import unicodedata
from typing import List, Optional

from core import paths
from core.league.builder import build_league_db
from core.league.schema import LeagueData, LeagueError, load_league, validate_league

# One folder for everything when set (tests); None = the real roots from core.paths.
GAME_ROOT: Optional[str] = None

BUILTIN_LEAGUE_ID = "fictional_2002"
BUILTIN_LEAGUE_FILE = os.path.join("data", "leagues", BUILTIN_LEAGUE_ID, "league.json")
MODS_DIR = "mods"
BUILT_DIR = os.path.join("data", "leagues", "built")
ACTIVE_FILE = os.path.join("data", "leagues", "active.json")
LEAGUE_FILENAME = "league.json"
DRAFT_DIRNAME = "draft_classes"

__all__ = ["BUILTIN_LEAGUE_ID", "LeagueError", "list_leagues", "build_and_activate", "active_league",
           "ensure_active_league_db", "active_draft_dir", "active_league_data"]


def _roots(root: Optional[str]) -> tuple:
    """(game root, user root): shipped league JSON is read from the first, mods/built/active from the second."""
    one = root if root is not None else GAME_ROOT
    if one is not None:
        return (one, one)
    return (paths.game_root(), paths.user_root())


def _db_filename(league_id: str) -> str:
    ascii_id = unicodedata.normalize("NFKD", league_id).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_id).strip("_")[:40] or "league"
    digest = hashlib.sha1(league_id.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{digest}.db"


def _sources(roots: tuple) -> List[tuple]:
    """(id, source, league.json path) for the built-in league (if its file exists) and each mod."""
    out = []
    builtin = os.path.join(roots[0], BUILTIN_LEAGUE_FILE)
    if os.path.isfile(builtin):
        out.append((BUILTIN_LEAGUE_ID, "builtin", builtin))
    mods = os.path.join(roots[1], MODS_DIR)
    if os.path.isdir(mods):
        for folder in sorted(os.listdir(mods)):
            path = os.path.join(mods, folder, LEAGUE_FILENAME)
            if os.path.isfile(path):
                out.append((folder, "mod", path))
    return out


def _draft_dir(json_path: str) -> Optional[str]:
    d = os.path.join(os.path.dirname(json_path), DRAFT_DIRNAME)
    if os.path.isdir(d) and any(n.lower().endswith(".json") for n in os.listdir(d)):
        return d
    return None


def _db_path(roots: tuple, league_id: str) -> str:
    return os.path.join(roots[1], BUILT_DIR, _db_filename(league_id))


def _is_built(db_path: str, json_path: str) -> bool:
    return os.path.isfile(db_path) and os.path.getmtime(db_path) >= os.path.getmtime(json_path)


def _entry(roots: tuple, league_id: str, source: str, path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        raw, errors = None, [f"Cannot read league file '{LEAGUE_FILENAME}': {exc}"]
    else:
        errors = validate_league(raw)
    meta = raw.get("meta") if isinstance(raw, dict) and isinstance(raw.get("meta"), dict) else {}
    franchises = raw.get("franchises") if isinstance(raw, dict) else None
    return {
        "id": league_id,
        "name": str(meta.get("name") or league_id),
        "era": str(meta.get("era") or ""),
        "source": source,
        "team_count": len(franchises) if isinstance(franchises, list) else 0,
        "has_draft_classes": _draft_dir(path) is not None,
        "built": _is_built(_db_path(roots, league_id), path),
        "active": False,
        "errors": errors,
        "_path": path,
    }


def _read_active_id(roots: tuple) -> Optional[str]:
    try:
        with open(os.path.join(roots[1], ACTIVE_FILE), "r", encoding="utf-8") as fh:
            value = json.load(fh).get("league_id")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def _all_entries(roots: tuple) -> List[dict]:
    """Every entry, with `active` set and the private `_path` kept."""
    entries = [_entry(roots, *src) for src in _sources(roots)]
    valid = [e for e in entries if not e["errors"]]
    wanted = _read_active_id(roots)
    # The pointed league stays active even when it has become invalid (it is reported with its errors);
    # the default applies only when no pointer exists or the pointed league is gone.
    chosen = next((e for e in entries if e["id"] == wanted), None)
    if chosen is None:
        # Default: the built-in league, else the first valid mod (mods are already sorted by id).
        chosen = next((e for e in valid if e["source"] == "builtin"), None) or (valid[0] if valid else None)
    if chosen is not None:
        chosen["active"] = True
    return entries


def _public(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def list_leagues(root: Optional[str] = None) -> List[dict]:
    """The built-in league and every mod with a league.json; invalid ones carry their `errors`."""
    return [_public(e) for e in _all_entries(_roots(root))]


def _active_entry(roots: tuple) -> Optional[dict]:
    return next((e for e in _all_entries(roots) if e["active"]), None)


def active_league(root: Optional[str] = None) -> Optional[dict]:
    """The active league's entry (same shape as `list_leagues`); None when no league is active.
    A pointed league that became invalid stays active and carries its `errors`."""
    e = _active_entry(_roots(root))
    return _public(e) if e else None


def build_and_activate(league_id: str, root: Optional[str] = None) -> dict:
    """Validates the league, builds its DB and makes it active. On any error nothing changes."""
    roots = _roots(root)
    entry = next((e for e in _all_entries(roots) if e["id"] == league_id), None)
    if entry is None:
        return {"ok": False, "errors": [f"Unknown league '{league_id}'"]}
    try:
        league = load_league(entry["_path"])
    except LeagueError as exc:
        return {"ok": False, "errors": exc.errors}
    db_path = _db_path(roots, league_id)
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        build_league_db(league, db_path)
        active = os.path.join(roots[1], ACTIVE_FILE)
        tmp = active + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"league_id": league_id}, fh, ensure_ascii=False)
        os.replace(tmp, active)
    except Exception as exc:  # disk/sqlite failure: the builder never leaves a half DB
        return {"ok": False, "errors": [f"Building the league failed: {exc}"]}
    return {"ok": True, "errors": []}


def ensure_active_league_db(root: Optional[str] = None) -> str:
    """Path of the active league's DB, (re)built first when missing or older than its JSON.
    Raises LeagueError when no league is active or the active one is invalid (with its errors)."""
    roots = _roots(root)
    entry = _active_entry(roots)
    if entry is None:
        raise LeagueError(["No valid league found: add the built-in league or a mod with a league.json"])
    if entry["errors"]:
        raise LeagueError(entry["errors"])
    db_path = _db_path(roots, entry["id"])
    if not _is_built(db_path, entry["_path"]):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        build_league_db(load_league(entry["_path"]), db_path)
    return db_path


def active_draft_dir(root: Optional[str] = None) -> Optional[str]:
    """The active league's `draft_classes/` folder, or None (generated rookies)."""
    entry = _active_entry(_roots(root))
    return _draft_dir(entry["_path"]) if entry else None


def active_league_data(root: Optional[str] = None) -> LeagueData:
    """The active league, loaded (for its franchise registry). Raises LeagueError when none is valid."""
    entry = _active_entry(_roots(root))
    if entry is None:
        raise LeagueError(["No valid league found: add the built-in league or a mod with a league.json"])
    return load_league(entry["_path"])
