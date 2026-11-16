"""Era lines: the OVR, money and pick-value thresholds of the trade system, read off the league.

Every number the trade code used to hard-code (an 83 OVR "star", a $15M "big contract") is written for a 2002
league. `EraLines` maps those numbers onto the league being played: star/core come from
`trade_brain.protection_lines`, the lower bands from the same top-share cut, money scales on the cap.
At a 2002 start every old OVR maps to itself.
"""
from dataclasses import dataclass
from typing import Dict, Iterable

from core.config import CONFIG
from core.front_office.trade_brain import _cut, protection_lines

__all__ = ["EraLines", "build_era_lines", "era_lines_for"]

_STAR_OLD = 85                 # the 2002 anchors of ovr_at; the star/core floors
_STAR_SWITCH = 83              # old thresholds from here up hang on the star line, below on the core line
_CORE_OLD = 80


@dataclass(frozen=True)
class EraLines:
    year: int
    cap: float
    tax: float
    minimum: float
    mle: float
    no_cap: bool
    star: int
    core: int
    starter: int
    rotation: int
    bench: int
    salary_pcts: Dict[float, float]
    pick_scale: float
    second_apron: float = 9999.0   # 9999 (ECONOMY.UNLIMITED_LINE or above): no aprons in this league (before 2023)

    @property
    def has_aprons(self) -> bool:
        return not self.no_cap and self.second_apron < CONFIG.ECONOMY.UNLIMITED_LINE

    @property
    def shed_line(self) -> float:
        """The payroll line a team over it trades salary to get under: the second apron once the league has one,
        else the tax."""
        return self.second_apron if self.has_aprons else self.tax

    def ovr_at(self, old_threshold: int) -> int:
        """A 2002-era OVR threshold expressed on this league's scale."""
        n = int(old_threshold)
        if n >= _STAR_SWITCH:
            return self.star + (n - _STAR_OLD)
        return self.core + (n - _CORE_OLD)

    def money(self, amount_at_ref_cap: float) -> float:
        """A dollar amount written for the reference cap, scaled to this league's cap."""
        if self.no_cap:
            return amount_at_ref_cap
        return amount_at_ref_cap * self.cap / CONFIG.TRADES.REFERENCE_CAP

    def band_of(self, ovr: int) -> str:
        if ovr >= self.star:
            return "star"
        if ovr >= self.core:
            return "core"
        if ovr >= self.starter:
            return "starter"
        if ovr >= self.rotation:
            return "rotation"
        if ovr >= self.bench:
            return "bench"
        return "fringe"

    def is_high_contract(self, salary: float, years_left: int) -> bool:
        t = CONFIG.TRADES
        return salary >= self.salary_pcts[t.HIGH_SALARY_PCT] and years_left >= t.LONG_CONTRACT_YEARS


def _percentile(values_asc: list, share: float) -> float:
    """The value `share` of the way up a list sorted low to high (0.9 = the 90th percentile)."""
    return values_asc[min(len(values_asc) - 1, int(share * len(values_asc)))]


def build_era_lines(players: Iterable, *, year: int, cap: float, tax: float, minimum: float, mle: float,
                    no_cap: bool, second_apron: float = 9999.0) -> EraLines:
    t = CONFIG.TRADES
    players = list(players)
    star, core = protection_lines(players)
    ovrs = sorted((int(p.ovr) for p in players), reverse=True)
    bands = {name: (min(core, _cut(ovrs, share)) if ovrs else core) for name, share in t.BAND_SHARES.items()}
    # keep the bands ordered even on odd distributions
    starter = bands["starter"]
    rotation = min(starter, bands["rotation"])
    bench = min(rotation, bands["bench"])

    salaries = sorted(float(p.contract.salario_annuale) for p in players if getattr(p, "contract", None))
    pcts = {share: (_percentile(salaries, share) if salaries else 0.0)
            for share in {*t.SALARY_PERCENTILES, t.HIGH_SALARY_PCT, t.MID_SALARY_PCT}}

    pick_scale = 1.0
    if players:
        mean_value = sum(float(p.trade_value) for p in players) / len(players)
        lo, hi = t.PICK_SCALE_RANGE
        pick_scale = max(lo, min(hi, mean_value / t.PICK_VALUE_REFERENCE_AVG))
    return EraLines(year=year, cap=cap, tax=tax, minimum=minimum, mle=mle, no_cap=no_cap, star=star, core=core,
                    starter=starter, rotation=rotation, bench=bench, salary_pcts=pcts, pick_scale=pick_scale,
                    second_apron=second_apron)


def era_lines_for(torneo) -> EraLines:
    players = [p for team in torneo.squadre for p in team.roster]
    cap = float(torneo.salary_cap)
    no_cap = getattr(torneo, "cba_mode", "") == "no_cap" or cap >= CONFIG.TRADES.NO_CAP_THRESHOLD
    return build_era_lines(players, year=torneo.anno_corrente, cap=cap,
                           tax=float(torneo.luxury_tax_threshold), minimum=float(torneo.min_salary),
                           mle=float(torneo.mle_value), no_cap=no_cap,
                           second_apron=float(getattr(torneo, 'second_apron', 9999.0) or 9999.0))
