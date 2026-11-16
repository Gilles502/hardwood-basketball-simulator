# core/league/registry.py
"""
Franchise registry: the live lookup for the active league's teams (names, divisions, branding, rivalries).

Built from a league file (`LeagueData`), stored in the save (`to_dict`/`from_dict`), and installed as the active
registry with `set_active_registry`. With nothing set, `get_active_registry` lazily loads the real-names mod league
if present, else the built-in fictional league, else an empty registry (every lookup falls back).
"""
import json
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from core import paths
from core.league.schema import Franchise, LeagueData, load_league

# Tests may set a tuple of paths; None = _default_league_paths().
_DEFAULT_LEAGUE_PATHS: Optional[Tuple[str, ...]] = None


def _default_league_paths() -> Tuple[str, ...]:
    """The real-names mod (user root, installed by hand) first, then the shipped fictional league (game root)."""
    return (
        paths.user_path("mods", "Real Names 2002", "league.json"),
        paths.game_path("data", "leagues", "fictional_2002", "league.json"),
    )


class FranchiseRegistry:
    def __init__(self, franchises: List[Franchise], rivalries: List[Tuple[str, str, float]],
                 marquee_hosts: Dict[str, List[str]], meta: Optional[dict] = None,
                 staff: Optional[dict] = None):
        self.franchises: List[Franchise] = list(franchises)
        self._rivalries: List[Tuple[str, str, float]] = [(a, b, float(w)) for a, b, w in rivalries]
        self._marquee_hosts: Dict[str, List[str]] = {k: list(v) for k, v in marquee_hosts.items()}
        self.meta: dict = dict(meta or {})
        # The league's staff names and GM roster (coach_names, owner_names, gms); {} = CONFIG fallbacks.
        self.staff: dict = json.loads(json.dumps(staff or {}))
        self._by_id = {f.id: f for f in self.franchises}
        self._by_name = {f.name: f for f in self.franchises}

    @classmethod
    def from_league(cls, data: LeagueData) -> "FranchiseRegistry":
        return cls(data.franchises, data.rivalries, data.marquee_hosts, data.meta, data.staff)

    def by_id(self, team_id: str) -> Optional[Franchise]:
        return self._by_id.get(team_id)

    def by_name(self, name: str) -> Optional[Franchise]:
        return self._by_name.get(name)

    def names(self) -> List[str]:
        return [f.name for f in self.franchises]

    def divisions(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for f in self.franchises:
            out.setdefault(f.division, []).append(f.name)
        return out

    def conference_of(self, name: str) -> Optional[str]:
        f = self.by_name(name)
        return f.conference if f else None

    def division_of(self, name: str) -> Optional[str]:
        f = self.by_name(name)
        return f.division if f else None

    def rivalries(self) -> List[Tuple[str, str, float]]:
        out = []
        for a, b, w in self._rivalries:
            fa, fb = self._by_id.get(a), self._by_id.get(b)
            if fa and fb:
                out.append((fa.name, fb.name, w))
        return out

    def market_weight(self, name: str, default: float) -> float:
        f = self.by_name(name)
        return f.market_weight if f else default

    def geo_city(self, name: str, default: str = "New York") -> str:
        f = self.by_name(name)
        return f.geo_city if f else default

    def marquee_hosts(self, key: str) -> List[str]:
        return [self._by_id[t].name for t in self._marquee_hosts.get(key, []) if t in self._by_id]

    @staticmethod
    def city_label(f: Franchise) -> str:
        """The home label the UI shows ("Portland, OR"): display_city, else "<geo_city>, <state>"."""
        if f.display_city:
            return f.display_city
        from core.config import CONFIG
        state = (CONFIG.GEO.CITIES.get(f.geo_city) or {}).get("state")
        return f"{f.geo_city}, {state}" if state else f.geo_city

    def branding(self, name: str) -> Dict[str, Any]:
        f = self.by_name(name)
        if f:
            return {"abbreviation": f.abbreviation, "arena": f.arena, "city": self.city_label(f),
                    "established": f.established, "primary": f.primary, "secondary": f.secondary}
        # Fallback for unknown franchises: identical to the legacy get_team_branding fallback.
        clean = name.strip()
        words = clean.split()
        abbr = "".join([w[0] for w in words[:3]]).upper() if len(words) >= 2 else clean[:3].upper()
        return {"abbreviation": abbr, "arena": f"{clean} Arena", "city": "NBA City",
                "established": 2000, "primary": "#1e293b", "secondary": "#ffd700"}

    def to_dict(self) -> dict:
        return {
            "meta": dict(self.meta),
            "franchises": [asdict(f) for f in self.franchises],
            "rivalries": [[a, b, w] for a, b, w in self._rivalries],
            "marquee_hosts": {k: list(v) for k, v in self._marquee_hosts.items()},
            "staff": json.loads(json.dumps(self.staff)),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FranchiseRegistry":
        return cls([Franchise(**fr) for fr in d.get("franchises", [])],
                   [(r[0], r[1], float(r[2])) for r in d.get("rivalries", [])],
                   d.get("marquee_hosts", {}), d.get("meta"), d.get("staff"))


_active: Optional[FranchiseRegistry] = None


def set_active_registry(reg: FranchiseRegistry) -> None:
    global _active
    _active = reg


def reset_active_registry() -> None:
    """Forgets the installed registry: the next get_active_registry() loads the lazy default again."""
    global _active
    _active = None


def get_active_registry() -> FranchiseRegistry:
    global _active
    if _active is None:
        candidates = _DEFAULT_LEAGUE_PATHS if _DEFAULT_LEAGUE_PATHS is not None else _default_league_paths()
        for path in candidates:
            if os.path.exists(path):
                _active = FranchiseRegistry.from_league(load_league(path))
                break
        else:
            _active = FranchiseRegistry([], [], {})
    return _active


def current_league_era() -> str:
    """The era of the active league ("2002"); "modern" when the league does not say."""
    return str(get_active_registry().meta.get("era") or "modern")


def staff_names(key: str, fallback) -> list:
    """The active league's staff name list (`coach_names` / `owner_names`), else `fallback` (a CONFIG list)."""
    names = get_active_registry().staff.get(key)
    return list(names) if isinstance(names, list) and names else list(fallback)
