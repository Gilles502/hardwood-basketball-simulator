"""Draft fit: what a prospect adds to a roster at his role, and the pick a CPU team makes from it.

The draft room (offseason/draft.py), the draft-night and trade-up engines and the draft wishes (MOVE_UP_DRAFT,
TARGET_PROSPECT) all read the same fit, so a team never trades up for a prospect it would not take. Thresholds come
from the era lines, numbers from CONFIG.DRAFT_AI. A CPU GM sees each prospect's potential through his draft skill
(`estimated_potential`); the user's team (no GM) sees it as it is.
"""
import random
import zlib
from typing import Iterable, List, Optional

from core.config import CONFIG
from core.front_office.era_lines import EraLines
from core.front_office.trade_brain import has_trait
from core.roles import normalize_role


def role_state(roster: Iterable, role: str, era: EraLines) -> str:
    """"hole" (no starter at the role), "blocked" (a core player in his prime, or a young talent, is there already),
    "depth" (too few rotation players) or "ok". The checks run in this order."""
    d = CONFIG.DRAFT_AI
    r = normalize_role(role)
    at_role = [p for p in roster if normalize_role(getattr(p, "ruolo", "")) == r]
    if max((int(p.ovr) for p in at_role), default=0) < era.starter:
        return "hole"
    for p in at_role:
        if int(p.ovr) >= era.core and p.eta <= d.BLOCK_MAX_AGE:
            return "blocked"
        if p.eta <= d.BLOCK_YOUNG_MAX_AGE and p.potenziale >= era.core and int(p.ovr) >= era.rotation:
            return "blocked"
    if sum(1 for p in at_role if int(p.ovr) >= era.rotation) < CONFIG.TRADES.DEPTH_MIN_ROTATION:
        return "depth"
    return "ok"


def estimated_potential(prospect, gm=None, year: int = 0) -> float:
    """The prospect's potential as this GM sees it: the true one for no GM, else off by an error that shrinks with
    his draft skill. Seeded on (GM, prospect, year), so the same GM always sees the same number."""
    if gm is None:
        return float(prospect.potenziale)
    d = CONFIG.DRAFT_AI
    skill = max(0, min(100, int(gm.skills.get("draft", 50))))
    sd = d.ESTIMATE_ERROR_MAX * (100 - skill) / 100.0
    if sd <= 0:
        return float(prospect.potenziale)
    rng = random.Random(zlib.crc32(f"{gm.gm_id}|{prospect.nome}|{year}".encode("utf-8")))
    return float(prospect.potenziale) + max(-2 * sd, min(2 * sd, rng.gauss(0.0, sd)))


def potential_weight(plan: str, gm=None) -> float:
    d = CONFIG.DRAFT_AI
    w = d.POTENTIAL_WEIGHT_BY_PLAN.get(plan, d.POTENTIAL_WEIGHT)
    if has_trait(gm, "YOUTH_FIRST"):
        w += d.UPSIDE_TRAIT_BONUS
    return max(0.0, min(1.0, w))


def prospect_score(prospect, roster: Iterable, era: EraLines, plan: str = "MIDDLE", gm=None, year: int = 0) -> float:
    d = CONFIG.DRAFT_AI
    w = potential_weight(plan, gm)
    upside = estimated_potential(prospect, gm, year) * w + prospect.ovr * (1.0 - w)
    fit = d.FIT_POINTS[role_state(roster, prospect.ruolo, era)]
    return upside + fit * d.FIT_WEIGHT_BY_PLAN.get(plan, 1.0)


def best_prospect(prospects: List, roster: Iterable, era: EraLines, plan: str = "MIDDLE", pick_in_round: int = 99,
                  gm=None, year: int = 0) -> Optional[object]:
    """The prospect a team takes from `prospects` (the top of the board, best first): a generational talent at the top
    of the board for a top pick, else the best score. None when the board is empty."""
    d = CONFIG.DRAFT_AI
    board = list(prospects)[:d.BOARD_SIZE]
    if not board:
        return None
    if pick_in_round <= d.GENERATIONAL_MAX_PICK:
        star = next((p for p in board[:d.GENERATIONAL_BOARD] if p.potenziale >= d.GENERATIONAL_POTENTIAL), None)
        if star is not None:
            return star
    roster = list(roster)
    return max(board, key=lambda p: prospect_score(p, roster, era, plan, gm, year))


def move_up_slot(board: List, made: int, own_pick: int, roster: Iterable, era: EraLines, plan: str = "MIDDLE",
                 gm=None, year: int = 0) -> Optional[int]:
    """The overall slot a team would move up to, or None.

    `board`: the remaining class, best first (prospect i projected to go at overall pick made + i + 1); `own_pick`: the
    team's first first-round pick still to come. The team looks at every prospect projected before its pick (the
    price, not this function, stops a 15th-to-1st dream) and picks the one it would take; when he scores at least MOVE_UP_MIN_GAIN more than the best
    one left at its pick, the answer is his projected slot."""
    d = CONFIG.DRAFT_AI
    roster = list(roster)
    lo = made + 1
    reachable = board[lo - made - 1:own_pick - made - 1]
    choice = best_prospect(reachable, roster, era, plan, lo, gm=gm, year=year)
    if choice is None:
        return None
    left = board[own_pick - made - 1:]
    at_pick = best_prospect(left, roster, era, plan, own_pick, gm=gm, year=year)
    if at_pick is not None and (prospect_score(choice, roster, era, plan, gm, year)
                                - prospect_score(at_pick, roster, era, plan, gm, year)) < d.MOVE_UP_MIN_GAIN:
        return None
    return lo + reachable.index(choice)


def projected_prospect(torneo, slot: int):
    """The prospect projected at overall `slot` of this draft (the remaining class by potential, after the picks
    already made), or None when the class or the slot is unknown."""
    board = sorted(getattr(torneo, 'draft_class', None) or [], key=lambda p: p.potenziale, reverse=True)
    made = int(getattr(torneo, 'draft_pick_corrente', 0) or 0)
    i = slot - made - 1
    return board[i] if 0 <= i < len(board) else None
