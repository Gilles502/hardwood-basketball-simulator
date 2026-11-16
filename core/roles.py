# core/roles.py
"""
Player roles / positions — single source of truth.

The game uses the English NBA standard everywhere (same as the datasets and Draft_Classes):
    PG  Point Guard     SG  Shooting Guard     SF  Small Forward     PF  Power Forward     C  Center

Older data and saves may still contain the legacy Italian codes (PM, G, AP, AG): every entry
point (DB loading, draft classes, save loading, API input) passes through `normalize_role`.
"""
from typing import Optional

ROLES = ("PG", "SG", "SF", "PF", "C")

ROLE_NAMES = {
    "PG": "Point Guard",
    "SG": "Shooting Guard",
    "SF": "Small Forward",
    "PF": "Power Forward",
    "C": "Center",
}

# Legacy Italian codes -> English standard
LEGACY_ROLE_MAP = {"PM": "PG", "G": "SG", "AP": "SF", "AG": "PF"}

# Positional groups
GUARDS = ("PG", "SG")
WINGS = ("SG", "SF", "PF")
FORWARDS = ("SF", "PF")
BIGS = ("PF", "C")
PERIMETER = ("PG", "SG", "SF")
FRONTCOURT = ("SF", "PF", "C")


def normalize_role(role: Optional[str]) -> str:
    """Returns the English role code for any known code (English or legacy Italian).
    Unknown values are returned upper-cased; empty values return ''."""
    if not role:
        return ""
    clean = str(role).strip().upper()
    return LEGACY_ROLE_MAP.get(clean, clean)


def normalize_role_keys(mapping: Optional[dict]) -> dict:
    """Returns a copy of a {role: value} dict with English keys (English keys win on conflicts)."""
    if not isinstance(mapping, dict):
        return {}
    out = {}
    for key, value in mapping.items():
        en = normalize_role(key)
        if en not in out or en == str(key).strip().upper():
            out[en] = value
    return out
