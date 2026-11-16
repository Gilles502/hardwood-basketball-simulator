"""How a CPU GM trades (AI GM layer 2a): pure numbers from a GM, an asset and the league.

Philosophy (traits) decides what he wants: value multipliers on asset tags. Trade skill decides the price:
a multiplier on the acceptance threshold, a squeeze on the user, rare disasters at very low skill.
The coach's style tilts who he targets. Protection and profile lines follow the league, not fixed numbers.
Neutral (no GM, no trait, skill 60) = the trade AI as it was before the GM existed.
"""
import math
from typing import Iterable, Optional, Set, Tuple

from core.config import CONFIG

__all__ = ["protection_lines", "profile_lines", "profile_score", "asset_tags", "trait_multiplier",
           "coach_fit_multiplier", "skill_price_multiplier", "user_squeeze", "disaster_factor",
           "has_trait", "is_vulture"]


def _cut(values_desc: list, share: float):
    """The value at the top `share` of a list sorted high to low."""
    return values_desc[max(0, math.ceil(share * len(values_desc)) - 1)]


def protection_lines(players: Iterable) -> Tuple[int, int]:
    """(star line, core line): OVR at the league's top shares, never below the floors."""
    fo = CONFIG.FRONT_OFFICE
    ovrs = sorted((int(p.ovr) for p in players), reverse=True)
    if not ovrs:
        return fo.STAR_LINE_FLOOR, fo.CORE_LINE_FLOOR
    return (max(fo.STAR_LINE_FLOOR, _cut(ovrs, fo.STAR_LINE_TOP_SHARE)),
            max(fo.CORE_LINE_FLOOR, _cut(ovrs, fo.CORE_LINE_TOP_SHARE)))


def profile_score(player, attrs: Tuple[str, ...]) -> Optional[float]:
    abilita = getattr(player, "abilita", None)
    if abilita is None or not attrs:
        return None
    try:
        return sum(float(getattr(abilita, a)) for a in attrs) / len(attrs)
    except (AttributeError, TypeError, ValueError):
        return None


def _profiles() -> dict:
    fo = CONFIG.FRONT_OFFICE
    return {**fo.COACH_STYLE_ATTRIBUTES, **fo.PROFILE_ATTRIBUTES}


def profile_lines(players: Iterable) -> dict:
    """Per coach style plus "DEFENSE"/"OFFENSE": the score at the league's top share (inf = nobody fits)."""
    share = CONFIG.FRONT_OFFICE.PROFILE_TOP_SHARE
    players = list(players)
    lines = {}
    for key, attrs in _profiles().items():
        scores = sorted((s for s in (profile_score(p, attrs) for p in players) if s is not None), reverse=True)
        lines[key] = _cut(scores, share) if scores else float("inf")
    return lines


def _fits(player, key: str, lines: dict) -> bool:
    attrs = _profiles().get(key)
    score = profile_score(player, attrs) if attrs else None
    return score is not None and score >= lines.get(key, float("inf"))


def asset_tags(asset, *, own: bool, star_line: int, cap: float, lines: dict) -> Set[str]:
    """The tags of TRAIT_VALUE an asset carries. A pick is a str ("1:R1-Team" or "R2-Team"), a player has `ovr`."""
    if isinstance(asset, str):
        key = asset.split(":", 1)[1] if ":" in asset else asset
        if key.startswith("R1"):
            return {"pick_r1"}
        if key.startswith("R2"):
            return {"pick_r2"}
        return set()
    if not hasattr(asset, "ovr"):
        return set()
    ovr, age = int(asset.ovr), int(getattr(asset, "eta", 27))
    out = set()
    if age >= 30:
        out.add("player_30_plus")
    if age <= 24:
        out.add("player_24_minus")
    if age >= 29 and ovr >= 75:
        out.add("player_29_plus_75")
    if age <= 22 and ovr < 72:
        out.add("player_22_minus_raw")
    if ovr >= star_line:
        out.add("player_star")
    contract = getattr(asset, "contract", None)
    if contract is not None:
        years = int(getattr(contract, "anni_rimanenti", 0) or 0)
        salary = float(getattr(contract, "salario_annuale", 0.0) or 0.0)
        if years == 1:
            out.add("expiring")
        if years >= 3 and salary >= cap * CONFIG.FRONT_OFFICE.LONG_HEAVY_CAP_SHARE and ovr < star_line:
            out.add("long_heavy")
    if _fits(asset, "DEFENSE", lines):
        out.add("defender")
    if _fits(asset, "OFFENSE", lines):
        out.add("scorer")
    if own:
        if int(getattr(asset, "anni_nella_squadra", 0) or 0) >= 4:
            out.add("own_long_tenure")
        if age <= 23:
            out.add("own_young")
    return out


def trait_multiplier(gm, tags: Set[str]) -> float:
    if gm is None:
        return 1.0
    fo = CONFIG.FRONT_OFFICE
    mult = 1.0
    for trait in gm.traits:
        for tag, value in fo.TRAIT_VALUE.get(trait, {}).items():
            if tag in tags:
                mult *= value
    low, high = fo.TRAIT_MULT_RANGE
    return min(high, max(low, mult))


def coach_fit_multiplier(style: Optional[str], player, lines: dict) -> float:
    if not style or style not in CONFIG.FRONT_OFFICE.COACH_STYLE_ATTRIBUTES or not hasattr(player, "ovr"):
        return 1.0
    return CONFIG.FRONT_OFFICE.COACH_FIT_BONUS if _fits(player, style, lines) else 1.0


def skill_price_multiplier(skill: Optional[int]) -> float:
    if skill is None:
        return 1.0
    points = CONFIG.FRONT_OFFICE.SKILL_PRICE_POINTS
    if skill <= points[0][0]:
        return points[0][1]
    for (s0, m0), (s1, m1) in zip(points, points[1:]):
        if skill <= s1:
            return m0 + (m1 - m0) * (skill - s0) / (s1 - s0)
    return points[-1][1]


def user_squeeze(skill: Optional[int]) -> float:
    if skill is None:
        return 0.0
    fo = CONFIG.FRONT_OFFICE
    return min(fo.USER_SQUEEZE_MAX, max(0, skill - 60) * fo.USER_SQUEEZE_PER_POINT)


def disaster_factor(skill: Optional[int], rng) -> float:
    fo = CONFIG.FRONT_OFFICE
    if skill is None or skill >= fo.DISASTER_SKILL_BELOW:
        return 1.0
    return rng.uniform(1.0 - (fo.DISASTER_SKILL_BELOW - skill) * fo.DISASTER_SPREAD_PER_POINT, 1.0)


def has_trait(gm, trait: str) -> bool:
    return gm is not None and trait in gm.traits


def is_vulture(gm) -> bool:
    return gm is not None and int(gm.skills.get("trade", 0)) >= CONFIG.FRONT_OFFICE.VULTURE_SKILL
