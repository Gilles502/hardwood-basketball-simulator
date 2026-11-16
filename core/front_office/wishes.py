"""GM wishes: what a team wants from a trade, when a deal fulfils it, and the plan's hard no's.

Pure: everything is read from the team (duck-typed: `nome`, `roster`, `payroll`) and the `WishContext`.
Picks are strings ("2003:R1-Team" or the legacy "R1-Team"); everything else in a deal is a player.
"""
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.config import CONFIG, owner_spending_tier
from core.front_office.era_lines import EraLines
from core.front_office.trade_brain import has_trait
from core.roles import normalize_role

__all__ = ["Wish", "WishContext", "KINDS", "build_wishes", "fulfils", "plan_hard_no", "wants_out"]

KINDS: Tuple[str, ...] = (
    "NEED_STARTER", "WANT_STAR", "STAR_WANTS_OUT", "SELL_VETERANS", "WANT_PICKS", "WANT_YOUTH", "SHED_TAX",
    "CLEAR_LONG_CONTRACT", "ABSORB_SALARY", "ROLE_CONGESTION", "DEPTH_NEEDED", "RENT_VETERAN",
    "SELL_EXPIRING", "UNHAPPY_PLAYER", "BENCH_HOLE", "MOVE_UP_DRAFT", "MOVE_DOWN_DRAFT",
    "TARGET_PROSPECT",
)

_BAND_RANK = {"fringe": 0, "bench": 1, "rotation": 2, "starter": 3, "core": 4, "star": 5}
_WIN_PLANS = ("CONTENDER", "PLAYOFF")


@dataclass(frozen=True)
class Wish:
    kind: str
    team: str
    priority: float
    reason: str
    role: Optional[str] = None
    player: Optional[str] = None
    data: Tuple[Tuple[str, Any], ...] = ()

    def get(self, key: str, default: Any = None) -> Any:
        return dict(self.data).get(key, default)


@dataclass
class WishContext:
    era: EraLines
    plan: str
    gm: Any
    owner: str
    window: str            # "deadline" | "predraft" | "draft" | "user"
    win_pct: float
    games: int
    has_r1_this_year: bool
    # Draft window only: (role, pick key) of prospects projected above their own pick.
    prospects: Tuple[Tuple[str, str], ...] = ()
    # Predraft and draft windows: the overall slot the team would move up to for a prospect it wants (draft_fit).
    move_up_slot: Optional[int] = None
    move_up_pick: Optional[str] = None   # that slot's first, in wish format ("2003:R1-Team")


# ---------------------------------------------------------------- small helpers
def _is_pick(asset) -> bool:
    return isinstance(asset, str)


def _players(assets) -> list:
    return [a for a in assets if not _is_pick(a)]


def _picks(assets) -> List[str]:
    return [a for a in assets if _is_pick(a)]


def _role(p) -> str:
    return normalize_role(getattr(p, "ruolo", ""))


def _years(p) -> int:
    return int(p.contract.anni_rimanenti)


def _salary(p) -> float:
    return float(p.contract.salario_annuale)


def _pick_weight(pick: str) -> float:
    tail = pick.split(":", 1)[-1]
    return float(CONFIG.TRADES.PICK_WEIGHTS.get(tail.split("-", 1)[0], 0.0))


def _is_r1_this_year(pick: str, era: EraLines) -> bool:
    if pick.startswith("R1-"):   # legacy key without a year
        return True
    return pick.startswith(f"{era.year}:R1-")


def _best_at(roster, role: str) -> int:
    return max((int(p.ovr) for p in roster if _role(p) == role), default=0)


def _top_names(roster) -> set:
    ranked = sorted(roster, key=lambda p: -int(p.ovr))
    return {p.nome for p in ranked[:CONFIG.FRONT_OFFICE.BENCH_SHUFFLE_TOP_KEEP]}


# ---------------------------------------------------------------- trade demand
def young_future(team, era: EraLines) -> bool:
    """The team has a young core that could turn it around (DEMAND_YOUNG_* / DEMAND_FUTURE_* lines)."""
    t = CONFIG.TRADES
    young = [q for q in team.roster if q.eta < t.DEMAND_YOUNG_AGE and q.potenziale >= era.ovr_at(t.DEMAND_YOUNG_POT_OLD)]
    return len(young) >= t.DEMAND_FUTURE_COUNT or any(
        q.eta < t.DEMAND_FUTURE_AGE and q.potenziale >= era.ovr_at(t.DEMAND_FUTURE_POT_OLD) for q in team.roster)


def wants_out(player, team, ctx: WishContext) -> bool:
    """Today's star trade demand (trade_finder.get_tradeable_players), on this league's OVR lines."""
    t, era = CONFIG.TRADES, ctx.era
    if int(player.ovr) < era.star:
        return False
    win_rate = ctx.win_pct if ctx.games > t.DEMAND_MIN_GAMES else t.DEMAND_NEUTRAL_WIN_PCT
    is_happy = player.morale >= t.DEMAND_HAPPY_MORALE
    is_loyal_vet = player.morale >= t.DEMAND_LOYAL_MORALE and player.anni_nella_squadra >= t.DEMAND_LOYAL_YEARS
    if is_happy or is_loyal_vet:
        return False
    has_young_future = young_future(team, era)
    if (int(player.ovr) >= era.ovr_at(t.DEMAND_SUPERSTAR_OLD) and win_rate < t.DEMAND_SUPERSTAR_WIN_PCT
            and player.eta >= t.DEMAND_SUPERSTAR_MIN_AGE):
        tenure_bonus = player.anni_nella_squadra * t.DEMAND_TENURE_FACTOR
        threshold = t.DEMAND_MORALE_BASE - tenure_bonus
        if has_young_future and player.eta < t.DEMAND_PATIENT_AGE:
            threshold = t.DEMAND_MORALE_PATIENT - tenure_bonus
        return player.morale < threshold
    if ctx.plan == "REBUILDER" and player.eta >= t.DEMAND_REBUILD_MIN_AGE:
        threshold = t.DEMAND_REBUILD_MORALE
        if has_young_future and player.eta <= t.DEMAND_REBUILD_MENTOR_MAX_AGE:
            threshold = t.DEMAND_REBUILD_MENTOR_MORALE
        return player.morale < threshold
    return False


# ---------------------------------------------------------------- building wishes
def _shed_trigger(team, ctx: WishContext, saver_gm: bool) -> Optional[float]:
    """The payroll above which the team wants to shed salary, or None (no cap, or an owner who pays the tax).

    With aprons: the second apron, for every owner. Before them: the tax plus a share of the cap that follows the
    owner's spending tier (a CAP_GUARDIAN GM sheds like a saver owner)."""
    t, era = CONFIG.TRADES, ctx.era
    if era.no_cap:
        return None
    if era.has_aprons and t.SHED_TAX_OVER_SECOND_APRON:
        return era.second_apron
    share = t.SHED_TAX_OVER_SHARE_BY_TIER.get("low" if saver_gm else owner_spending_tier(ctx.owner))
    return None if share is None else era.tax + share * era.cap


def build_wishes(team, ctx: WishContext, rng=None) -> List[Wish]:
    """Every wish of `team` in this context, highest priority first.

    Deterministic for a given input except two chances drawn from `rng` (default: the `random` module): the
    PICK_HOARDER veteran sale (a hoarder that is not rebuilding and has veterans) and the TRADE_HAPPY bench shuffle
    in a CPU window.
    """
    rng = rng if rng is not None else random
    t, fo, era = CONFIG.TRADES, CONFIG.FRONT_OFFICE, ctx.era
    roster = list(team.roster)
    plan, gm, name = ctx.plan, ctx.gm, team.nome
    hoarder, saver_gm = has_trait(gm, "PICK_HOARDER"), has_trait(gm, "CAP_GUARDIAN")
    wishes: List[Wish] = []

    def add(kind, reason, role=None, player=None, data=(), bonus=0.0):
        wishes.append(Wish(kind, name, float(t.WISH_PRIORITY[kind]) + bonus, reason, role, player, tuple(data)))

    by_role = {r: [p for p in roster if _role(p) == r] for r in t.WISH_ROLES}
    payroll = float(team.payroll)
    under_tax = era.no_cap or payroll <= era.tax

    if plan in _WIN_PLANS:
        for role in t.WISH_ROLES:
            if _best_at(roster, role) < era.starter:
                add("NEED_STARTER", f"There is no starter-level {role} on the roster.", role=role)
    if (has_trait(gm, "STAR_CHASER") and plan in _WIN_PLANS) or (
            plan == "CONTENDER" and not any(int(p.ovr) >= era.star for p in roster)):
        add("WANT_STAR", "The team wants a star to build around.")

    demanders = set()
    for p in roster:
        if wants_out(p, team, ctx) or getattr(p, 'walks_away', ''):   # a player who will not re-sign wants out too
            demanders.add(p.nome)
            add("STAR_WANTS_OUT", f"{p.nome} asked to be traded.", player=p.nome)

    vets = [p for p in roster if p.eta >= t.VETERAN_MIN_AGE and int(p.ovr) >= era.rotation]
    hoard_vets = [p for p in roster if p.eta >= fo.PICK_HOARDER_SELL_MIN_AGE and int(p.ovr) >= era.rotation]
    if plan == "REBUILDER" and vets:
        add("SELL_VETERANS", "Veterans do not fit a rebuild.")
    elif hoarder and hoard_vets and rng.random() < fo.PICK_HOARDER_SELL_CHANCE:
        add("SELL_VETERANS", "The GM sells veterans for picks.")

    if plan == "REBUILDER" or hoarder:
        add("WANT_PICKS", "The GM wants more draft capital.")
    if plan == "REBUILDER" or has_trait(gm, "YOUTH_FIRST"):
        add("WANT_YOUTH", "The team wants young players with upside.")

    saver_owner = ctx.owner == t.SAVER_OWNER
    trigger = _shed_trigger(team, ctx, saver_gm)
    if trigger is not None and payroll > trigger:
        # Next season's money (contracts that run past this one): a team that gets under by itself waits.
        min_years = 2 if ctx.window in ("deadline", "user") else 1
        committed = sum(_salary(p) for p in roster if _years(p) >= min_years)
        if not (t.SHED_TAX_LOOK_AHEAD and committed <= trigger):
            bonus = (t.TAX_PRIORITY_BONUS if saver_owner else 0.0) + (t.TAX_PRIORITY_BONUS if saver_gm else 0.0)
            reason = "Payroll is over the second apron." if era.has_aprons else "Payroll is far over the tax line."
            add("SHED_TAX", reason, bonus=bonus)

    if saver_gm or plan == "REBUILDER":
        bad_band = _BAND_RANK[t.CLEAR_LONG_MAX_BAND]
        for p in roster:
            if (_BAND_RANK[era.band_of(int(p.ovr))] <= bad_band and p.eta > t.YOUNG_MAX_AGE
                    and era.is_high_contract(_salary(p), _years(p))):
                add("CLEAR_LONG_CONTRACT", f"{p.nome} has a long, heavy contract.", player=p.nome)

    if (plan in ("REBUILDER", "MIDDLE") or hoarder) and under_tax:
        add("ABSORB_SALARY", "There is room under the tax line to take on salary.")

    for role in t.WISH_ROLES:
        group = by_role[role]
        if sum(1 for p in group if int(p.ovr) >= era.starter) >= t.CONGESTION_COUNT:
            add("ROLE_CONGESTION", f"Too many good players at {role}.", role=role)
        if sum(1 for p in group if int(p.ovr) >= era.rotation) < t.DEPTH_MIN_ROTATION:
            add("DEPTH_NEEDED", f"The team is thin at {role}.", role=role)

    if ctx.window == "deadline" and plan in _WIN_PLANS:
        add("RENT_VETERAN", "The team is chasing a title and can use a short-term veteran.")
    if ctx.window == "deadline" and (plan == "REBUILDER" or (
            ctx.win_pct < t.OUT_OF_RACE_WIN_PCT and ctx.games >= fo.PLAN_DEADLINE_MIN_GAMES)):
        for p in roster:
            if _years(p) == 1 and p.eta >= t.RENT_MIN_AGE and int(p.ovr) >= era.rotation:
                add("SELL_EXPIRING", f"{p.nome} is on an expiring deal for a team going nowhere.", player=p.nome)

    if t.UNHAPPY_MIN_BAND not in _BAND_RANK:
        raise ValueError(f"CONFIG.TRADES.UNHAPPY_MIN_BAND {t.UNHAPPY_MIN_BAND!r} is not a band: {list(_BAND_RANK)}")
    unhappy_floor = _BAND_RANK[t.UNHAPPY_MIN_BAND]
    for p in roster:
        if (p.morale < t.MORALE_UNHAPPY and p.nome not in demanders
                and _BAND_RANK[era.band_of(int(p.ovr))] >= unhappy_floor):
            add("UNHAPPY_PLAYER", f"{p.nome} is unhappy.", player=p.nome)

    top = _top_names(roster)
    for p in roster:
        if p.nome not in top and int(p.ovr) < era.bench:
            add("BENCH_HOLE", f"{p.nome} is a weak spot at the end of the bench.", player=p.nome, data=(("ovr", int(p.ovr)),))

    if ctx.window in ("predraft", "draft") and ctx.has_r1_this_year:
        if (plan in CONFIG.DRAFT_AI.MOVE_UP_PLANS and not hoarder
                and ctx.move_up_slot is not None):   # only for a prospect it wants; a hoarder only moves down
            add("MOVE_UP_DRAFT", f"The team wants a prospect projected to go at #{ctx.move_up_slot}.",
                data=(("slot", ctx.move_up_slot),))
        if hoarder:
            add("MOVE_DOWN_DRAFT", "The GM would rather have more picks than a high slot.")
    if ctx.window == "draft" and ctx.move_up_pick:   # the prospect it would take, a few slots above its pick
        role = next((normalize_role(r) for r, pick in ctx.prospects if pick == ctx.move_up_pick), None)
        add("TARGET_PROSPECT", f"A {role or 'top'} prospect it wants is projected at #{ctx.move_up_slot}.", role=role,
            data=(("pick", ctx.move_up_pick),))

    wishes.sort(key=lambda w: -w.priority)
    return wishes


# ---------------------------------------------------------------- fulfilment
def fulfils(wish: Wish, receives: list, gives: list, team, era: EraLines) -> bool:
    """True when the deal (`receives` / `gives` are what `team` gets and sends: players and pick strings) meets the wish."""
    t = CONFIG.TRADES
    p_in, p_out = _players(receives), _players(gives)
    k_in, k_out = _picks(receives), _picks(gives)
    kind = wish.kind
    roster = list(team.roster)

    if kind == "NEED_STARTER":
        best = _best_at(roster, wish.role)
        return any(_role(p) == wish.role and int(p.ovr) >= era.starter and int(p.ovr) > best for p in p_in)
    if kind == "WANT_STAR":
        return any(int(p.ovr) >= era.star for p in p_in)
    if kind in ("STAR_WANTS_OUT", "UNHAPPY_PLAYER"):
        return any(p.nome == wish.player for p in p_out)
    if kind == "SELL_VETERANS":   # for a first or a young player: seconds are not "the future"
        sold = any(p.eta >= t.VETERAN_MIN_AGE and int(p.ovr) >= era.rotation for p in p_out)
        return sold and (any(_pick_weight(k) > 0 for k in k_in) or any(p.eta <= t.YOUNG_MAX_AGE for p in p_in))
    if kind == "WANT_PICKS":
        return sum(map(_pick_weight, k_in)) > sum(map(_pick_weight, k_out))
    if kind == "WANT_YOUTH":
        return any(p.eta <= t.YOUNG_MAX_AGE and p.potenziale >= era.starter for p in p_in)
    if kind == "SHED_TAX":
        need = min(float(team.payroll) - era.shed_line, t.TAX_DUMP_MIN_CUT_SHARE * era.cap)
        return sum(map(_salary, p_out)) - sum(map(_salary, p_in)) >= need
    if kind == "CLEAR_LONG_CONTRACT":
        return (any(p.nome == wish.player for p in p_out)
                and not any(_years(p) >= t.LONG_CONTRACT_YEARS for p in p_in))
    if kind == "ABSORB_SALARY":
        after = float(team.payroll) + sum(map(_salary, p_in)) - sum(map(_salary, p_out))
        return bool(k_in) and (era.no_cap or after <= era.tax)
    if kind == "ROLE_CONGESTION":
        return any(_role(p) == wish.role for p in p_out)
    if kind == "DEPTH_NEEDED":
        return any(_role(p) == wish.role and int(p.ovr) >= era.rotation for p in p_in)
    if kind == "RENT_VETERAN":
        return any(_years(p) == 1 and p.eta >= t.RENT_MIN_AGE and int(p.ovr) >= era.rotation for p in p_in)
    if kind == "SELL_EXPIRING":
        return (any(p.nome == wish.player for p in p_out)
                and (bool(k_in) or any(p.eta <= t.YOUNG_MAX_AGE for p in p_in)))
    if kind == "BENCH_HOLE":
        return any(int(p.ovr) > int(wish.get("ovr", 0)) for p in p_in)
    if kind == "MOVE_UP_DRAFT":
        return bool(k_out) and any(_is_r1_this_year(k, era) for k in k_in)
    if kind == "MOVE_DOWN_DRAFT":
        return sum(1 for k in k_out if _is_r1_this_year(k, era)) == 1 and len(k_in) >= 2
    if kind == "TARGET_PROSPECT":
        want = wish.get("pick")
        return want is not None and any(k == want or k.endswith(f":{want}") for k in k_in)
    return False


# ---------------------------------------------------------------- hard no's
def plan_hard_no(team, ctx: WishContext, receives: list, gives: list) -> Optional[str]:
    """The plan question's veto: an English refusal sentence, or None."""
    t, era = CONFIG.TRADES, ctx.era
    p_in, p_out = _players(receives), _players(gives)
    name, roster = team.nome, list(team.roster)

    if ctx.plan == "REBUILDER":
        old = any(p.eta >= t.VETERAN_MIN_AGE and _years(p) >= 2 for p in p_in)
        if old:
            absorb = Wish("ABSORB_SALARY", name, 0.0, "")
            if not fulfils(absorb, receives, gives, team, era):
                return f"{name} is rebuilding: they won't take on {t.VETERAN_MIN_AGE}+ veterans"

    asked_out = lambda p: bool(getattr(p, '_wants_out', False))
    if ctx.plan == "REBUILDER":   # a young player who is already good is the rebuild: it keeps him
        keep_line = era.ovr_at(t.REBUILDER_KEEP_YOUNG_MIN_OVR)
        for p in p_out:
            for_his_man = ctx.move_up_pick is not None and ctx.move_up_pick in receives   # the prospect it wants
            if (p.eta <= t.REBUILDER_KEEP_YOUNG_MAX_AGE and int(p.ovr) >= keep_line and not asked_out(p)
                    and not for_his_man):
                return f"{name} is rebuilding: {p.nome} is young and good, he is the future"

    if ctx.plan == "CONTENDER" and roster and p_out:
        best = max(roster, key=lambda p: int(p.ovr))
        if any(p.nome == best.nome for p in p_out):
            floor = _BAND_RANK[era.band_of(int(best.ovr))]
            if not any(_BAND_RANK[era.band_of(int(p.ovr))] >= floor for p in p_in):
                return f"{name} is going for the title: they won't give up their best player"

    if has_trait(ctx.gm, "CAP_GUARDIAN") and not era.no_cap:
        before = float(team.payroll)
        after = before + sum(map(_salary, p_in)) - sum(map(_salary, p_out))
        if before <= era.tax < after:
            return f"{name}'s GM won't go over the tax"

    for role in t.WISH_ROLES:
        group = [p for p in roster if _role(p) == role]
        if sum(1 for p in group if int(p.ovr) >= era.starter) >= t.CONGESTION_COUNT:
            if sum(1 for p in p_in if _role(p) == role) > sum(1 for p in p_out if _role(p) == role):
                return f"{name} already has too many {role}s"
    return None
