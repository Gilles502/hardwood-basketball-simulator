"""Era-aware salary matching for trades (money in millions)."""
from typing import Tuple

from core.config import CONFIG


def _era_rule(year: int) -> str:
    for first, last, rule in CONFIG.TRADES.SALARY_MATCH_ERAS:
        if first <= year <= last:
            return rule
    return CONFIG.TRADES.SALARY_MATCH_ERAS[-1][2]


def salary_match_ok(*, payroll: float, incoming: float, outgoing: float, cap: float,
                    second_apron: float, year: int, cba_mode: str) -> Tuple[bool, str]:
    """Can a team at `payroll` take back `incoming` salary for `outgoing` salary?"""
    cfg = CONFIG.TRADES
    if cba_mode == "no_cap" or cap >= cfg.NO_CAP_THRESHOLD:
        return True, "Under Cap (No Cap Mode)"
    if payroll - outgoing + incoming <= cap:
        return True, "Under Cap"

    rule = _era_rule(year)
    if rule == "PCT_125":
        max_incoming = outgoing * cfg.PCT_125_RATIO + cfg.PCT_125_PLUS
    elif cba_mode == "realistic" and payroll > second_apron:
        # Second apron (modern era only): tighter than the mid-size band.
        max_incoming = outgoing * cfg.SECOND_APRON_RATIO
    else:
        scale = cap / cfg.REFERENCE_CAP
        max_incoming = outgoing
        for up_to, ratio, plus in cfg.MODERN_BANDS:
            if outgoing <= up_to * scale:
                max_incoming = outgoing * ratio + plus * scale
                break

    if incoming <= max_incoming:
        return True, f"Within limit (Max: {max_incoming:.2f}M)"
    return False, (f"Salary mismatch: Out {outgoing:.2f}M vs In {incoming:.2f}M "
                   f"(Allowed In: {max_incoming:.2f}M)")
