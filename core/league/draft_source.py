# core/league/draft_source.py
"""
Per-save league sources: which draft-class file a season reads, and the franchise registry of an old save.

A save started from a league file carries its own `<save>/draft_classes/` copy (none = generated rookies).
Old saves (made before league files: empty `league_meta`) read the Real Names 2002 mod's classes at read time
and get a legacy registry; nothing is written into the save on load.
"""
import os
import shutil
from dataclasses import replace
from typing import Any, List, Optional

from core import paths
from core.league import catalog
from core.league.registry import FranchiseRegistry
from core.league.schema import LeagueError, load_league

# One folder for everything when set (tests); None = the real roots (mods under the user root,
# the built-in league under the game root), see core.paths.
GAME_ROOT: Optional[str] = None
# The mod that holds the real 2002 league (the league old saves were made from).
REAL_NAMES_MOD = "Real Names 2002"


def _mod_dir() -> str:
    return os.path.join(GAME_ROOT or paths.user_root(), catalog.MODS_DIR, REAL_NAMES_MOD)


def draft_class_file(torneo: Any, year: int) -> Optional[str]:
    """The draft-class JSON for `year`: the active save's own copy; for an old save (empty league_meta) the
    Real Names 2002 mod's file; otherwise None (the class is generated). No other folder is read."""
    from core.save_manager import get_active_save_name, get_save_path
    filename = f"DRAFT_{int(year)}.json"
    save_name = get_active_save_name()
    if save_name:
        own = os.path.join(get_save_path(save_name), catalog.DRAFT_DIRNAME, filename)
        if os.path.isfile(own):
            return own
    if not getattr(torneo, "league_meta", None):
        legacy = os.path.join(_mod_dir(), catalog.DRAFT_DIRNAME, filename)
        if os.path.isfile(legacy):
            return legacy
    return None


def copy_league_draft_classes(league_draft_dir: Optional[str], save_dir: str) -> None:
    """Gives a new save its own copy of the league's draft classes in <save>/draft_classes/.
    Replaces any folder left there by an older career with the same name; no league folder = none copied."""
    dest = os.path.join(save_dir, catalog.DRAFT_DIRNAME)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    if league_draft_dir:
        shutil.copytree(league_draft_dir, dest)


def _load(path: str):
    if not os.path.isfile(path):
        return None
    try:
        return load_league(path)
    except LeagueError:
        return None


def legacy_registry_for(team_names: List[str]) -> FranchiseRegistry:
    """The registry of an old save: the Real Names 2002 league if the mod is installed, else the built-in
    fictional league. Each franchise whose id matches a stored old name (CONFIG.LEAGUE.LEGACY_TEAM_IDS) takes
    that name, so the save's teams keep their names and find their division, rivalries and branding.
    Neither league present: an empty registry (every lookup falls back)."""
    from core.config import CONFIG
    league = _load(os.path.join(_mod_dir(), catalog.LEAGUE_FILENAME)) \
        or _load(os.path.join(GAME_ROOT or paths.game_root(), catalog.BUILTIN_LEAGUE_FILE))
    if league is None:
        return FranchiseRegistry([], [], {})
    ids = CONFIG.LEAGUE.LEGACY_TEAM_IDS
    stored_by_id = {ids[n]: n for n in team_names if n in ids}
    franchises = [replace(f, name=stored_by_id.get(f.id, f.name)) for f in league.franchises]
    return FranchiseRegistry(franchises, league.rivalries, league.marquee_hosts, league.meta, league.staff)
