"""Cut-down day: which players a team drops to get back under the roster limit.

Shared by the engine (Tournament._gestisci_fase_tagli_roster) and the End of Season Hub preview, so the preview
always names the players the engine will actually cut. Thresholds come from CONFIG.OFFSEASON.
"""
from typing import List, Optional


def cut_target(cfg) -> int:
    """Roster size teams are cut down to."""
    return cfg.ROSTER_SIZE_LIMIT - 1


def _cut_score(p, cfg) -> float:
    score = p.ovr
    if p.eta <= 24 and p.potenziale >= cfg.CUT_POTENTIAL_IMMUNITY_THRESHOLD:
        score += (p.potenziale - p.ovr) * 0.6
    return score


def is_protected(p, cfg) -> bool:
    """Players the AI never cuts while someone expendable is left: untouchables, OVR at the immunity line, and young
    players with high potential. Binds the AI only; the user may release anyone on his own roster."""
    return (p.is_untouchable or p.ovr >= cfg.CUT_OVR_IMMUNITY_THRESHOLD
            or (p.potenziale >= cfg.CUT_POTENTIAL_IMMUNITY_THRESHOLD and p.eta <= 25))


def cut_order(roster: List, cfg) -> List:
    """The whole roster from first to last to go: lowest cut score first, untouchables at the end."""
    return sorted(roster, key=lambda p: (bool(p.is_untouchable), _cut_score(p, cfg)))


def validate_releases(roster_names: List[str], releases: List[str], target: int) -> Optional[str]:
    """Why the user's cut list can't be applied, or None: every name must be on the roster and the roster must end at
    or under the target size."""
    for name in releases:
        if name not in roster_names:
            return f"{name} is not on your roster"
    remaining = len(roster_names) - len(set(releases))
    if remaining > target:
        return f"Release {remaining - target} more to reach {target}"
    return None


def pick_cuts(roster: List, limit: int, cfg) -> List:
    """Players to cut, in cut order. Expendable players go first by score; if everyone is protected,
    the lowest trade value goes. Does not change the roster."""
    remaining = list(roster)
    cuts = []
    while len(remaining) > limit:
        expendable = [p for p in remaining if not is_protected(p, cfg)]
        if expendable:
            victim = min(expendable, key=lambda p: _cut_score(p, cfg))
        else:
            victim = min(remaining, key=lambda p: p.trade_value)
        remaining.remove(victim)
        cuts.append(victim)
    return cuts
