"""When the user may trade: the window closes at the deadline and reopens in the offseason."""
from typing import Tuple


def deadline_passed(torneo) -> bool:
    """True once the trade deadline has been handled or its calendar day is behind us."""
    if getattr(torneo, "_trade_deadline_completed", False):
        return True
    today = getattr(torneo, "_current_gameday", 0)
    for index, day in enumerate(getattr(torneo, "calendario", None) or []):
        if index >= today:
            break
        if "TRADE_DEADLINE" in (getattr(day, "events", None) or []):
            return True
    return False


def user_trade_window(torneo, league_state: str) -> Tuple[bool, str]:
    """(open, message) for user-initiated trades in the given league state."""
    if league_state == "OFFSEASON_TRADES_START":
        return True, ""
    if league_state in ("PRE_SEASON", "ALL_STAR_BREAK"):
        if deadline_passed(torneo):
            return False, "The trade deadline has passed"
        return True, ""
    return False, f"The trade window is closed ({league_state.replace('_', ' ')})"
