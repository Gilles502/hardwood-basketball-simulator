"""The GM roster: the league file's historical GMs (`staff.gms`), and generated GMs when none is available.

`data/gm_roster_2002.json` is only the historical source the league files were exported from; no runtime code reads it.
"""
import hashlib
import json
import random

from core.config import CONFIG
from core.front_office.models import CpuGM


def load_roster(registry) -> dict:
    """The league's GM roster (`staff.gms` of the registry) as {"starting": [...], "arrivals": [...]}, each
    starting entry's `team` a franchise id; empty lists when the league brings no GMs."""
    gms = (getattr(registry, "staff", None) or {}).get("gms") or {}
    data = json.loads(json.dumps(gms))
    return {"starting": list(data.get("starting", [])), "arrivals": list(data.get("arrivals", []))}


def roster_team_id(name: str, team_id: str, registry) -> str:
    """The franchise id a game team's GM entry is keyed by: the team's stored id, else the registry's match of
    its name, else the old-save name table; "" when unknown."""
    if team_id:
        return team_id
    franchise = registry.by_name(name) if registry is not None else None
    if franchise is not None:
        return franchise.id
    return CONFIG.LEAGUE.LEGACY_TEAM_IDS.get(name, "")


def generated_gm(seed: str, year: int, age_range=None, skill_range=None) -> CpuGM:
    """A made-up GM, always the same for the same seed (e.g. "<team name>|2010"). Ranges default to
    GENERATED_AGE_RANGE / GENERATED_SKILL_RANGE."""
    fo = CONFIG.FRONT_OFFICE
    rng = random.Random(seed)
    name = f"{rng.choice(fo.GENERATED_FIRST_NAMES)} {rng.choice(fo.GENERATED_LAST_NAMES)}"
    age = rng.randint(*(age_range or fo.GENERATED_AGE_RANGE))
    skills = {skill: rng.randint(*(skill_range or fo.GENERATED_SKILL_RANGE)) for skill in fo.SKILLS}
    traits = rng.sample(sorted(fo.TRAITS), fo.GENERATED_TRAITS)
    gm_id = "gen_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return CpuGM(gm_id=gm_id, name=name, age=age, years_as_gm=0, traits=traits, skills=skills,
                 team=None, tenure=0, historical=False, available_from_year=year)
