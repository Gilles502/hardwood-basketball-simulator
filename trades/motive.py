"""Structured "why" of a CPU trade: data model and English text helpers (no engine numbers in any text)."""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

# wish kind -> sentence templates (the first two are used). Fields: {team} {need} {gets} {gives}.
REASON_TEMPLATES: Dict[str, List[str]] = {
    "NEED_STARTER": ["The starting {need} spot is a hole, and this deal fills it.", "Going out for it: {gives}. Coming in: {gets}."],
    "WANT_STAR": ["{team} wants a star to build around. Coming in: {gets}.", "The price worth paying: {gives}."],
    "STAR_WANTS_OUT": ["A star asked out, so {team} moves on. Going out: {gives}.", "The return for an unhappy star: {gets}."],
    "SELL_VETERANS": ["Rebuild: no place in the long-term plan for {gives}.", "The younger direction brings in {gets}."],
    "WANT_PICKS": ["{team} wants more draft capital, and this deal adds to it.", "Spent to get it: {gives}."],
    "WANT_YOUTH": ["The youth plan brings in {gets}.", "Older and less useful to {team}: {gives}."],
    "SHED_TAX": ["{team} is over the tax line and must cut salary.", "Clearing payroll: {gives}."],
    "CLEAR_LONG_CONTRACT": ["{team} wants a long, heavy contract off the books: {gives}.", "Shorter commitments come back: {gets}."],
    "ABSORB_SALARY": ["{team} has room under the tax line, so it takes on salary in this deal.", "Picks come back as payment for the help."],
    "ROLE_CONGESTION": ["Too many good players at {need}, so the surplus goes: {gives}.", "A thinner spot gets filled by {gets}."],
    "DEPTH_NEEDED": ["{team} is thin at {need}, and this deal adds depth: {gets}.", "Spared in return: {gives}."],
    "RENT_VETERAN": ["{team} is chasing a title and rents {gets} for the run.", "The cost of that push: {gives}."],
    "SELL_EXPIRING": ["{team} is out of the race and sells an expiring deal: {gives}.", "Worth more than a free exit: {gets}."],
    "UNHAPPY_PLAYER": ["A fresh start for {gives}.", "A fair swap that keeps the room calm: {gets}."],
    "BENCH_HOLE": ["The end of the bench is weak, and this deal helps: {gets}.", "Not cutting it: {gives}."],
    "MOVE_UP_DRAFT": ["{team} wants a higher draft slot.", "The price to move up: {gives}."],
    "MOVE_DOWN_DRAFT": ["{team} prefers more picks to a high slot.", "Adding to the stash: {gets}."],
    "TARGET_PROSPECT": ["A prospect in the draft caught the eye of {team}.", "The way to get to the pick: {gives}."],
}

# wish kind -> short phrase for the "Why:" line. Fields: {team} {need}.
WHY_PHRASES: Dict[str, str] = {
    "NEED_STARTER": "{team} needed a starting {need}", "WANT_STAR": "{team} went after a star",
    "STAR_WANTS_OUT": "{team} moved a star who wanted out", "SELL_VETERANS": "{team} turns a veteran into the future",
    "WANT_PICKS": "{team} wanted more picks", "WANT_YOUTH": "{team} wanted young players",
    "SHED_TAX": "{team} cut salary under the tax", "CLEAR_LONG_CONTRACT": "{team} cleared a long contract",
    "ABSORB_SALARY": "{team} took salary for picks", "ROLE_CONGESTION": "{team} had too many at {need}",
    "DEPTH_NEEDED": "{team} needed depth at {need}",
    "RENT_VETERAN": "{team} rented a veteran for the title run", "SELL_EXPIRING": "{team} sold an expiring veteran",
    "UNHAPPY_PLAYER": "{team} gave an unhappy player a fresh start",
    "BENCH_HOLE": "{team} patched a weak bench spot", "MOVE_UP_DRAFT": "{team} moved up in the draft",
    "MOVE_DOWN_DRAFT": "{team} moved down for more picks", "TARGET_PROSPECT": "{team} targeted a prospect",
}

TRAIT_REASONS: Dict[str, str] = {
    "PICK_HOARDER": "The GM never says no to draft picks.",
    "YOUTH_FIRST": "The GM prefers young players.",
    "TRADE_HAPPY": "The GM likes to keep the roster moving.",
    "VETERAN_LOVER": "The GM trusts proven veterans.",
    "STAR_CHASER": "The GM always goes after stars.",
    "DEFENSE_FIRST": "The GM builds around defense.",
    "OFFENSE_FIRST": "The GM builds around scoring.",
    "CAP_GUARDIAN": "The GM guards the cap sheet.",
    "LOYALIST": "The GM hates to lose long-time players, but made an exception.",
    "PATIENT_BUILDER": "The GM builds slowly through picks and young talent.",
}

# Wish kinds where each trait's asset tags are in play (a trait sentence is added only then).
TRAIT_KINDS: Dict[str, tuple] = {
    "PICK_HOARDER": ("WANT_PICKS", "SELL_VETERANS", "SELL_EXPIRING", "MOVE_DOWN_DRAFT", "ABSORB_SALARY"),
    "YOUTH_FIRST": ("WANT_YOUTH", "SELL_VETERANS", "TARGET_PROSPECT"),
    "TRADE_HAPPY": ("BENCH_HOLE",),
    "VETERAN_LOVER": ("RENT_VETERAN", "NEED_STARTER", "DEPTH_NEEDED"),
    "STAR_CHASER": ("WANT_STAR",),
    "DEFENSE_FIRST": ("NEED_STARTER", "DEPTH_NEEDED", "BENCH_HOLE"),
    "OFFENSE_FIRST": ("NEED_STARTER", "DEPTH_NEEDED", "BENCH_HOLE"),
    "CAP_GUARDIAN": ("SHED_TAX", "CLEAR_LONG_CONTRACT", "SELL_EXPIRING"),
    "LOYALIST": ("STAR_WANTS_OUT", "UNHAPPY_PLAYER"),
    "PATIENT_BUILDER": ("WANT_PICKS", "WANT_YOUTH", "MOVE_DOWN_DRAFT"),
}


@dataclass
class SideMotive:
    team: str
    gm_name: Optional[str] = None
    trade_skill: Optional[int] = None
    plan: str = "MIDDLE"
    traits: List[str] = field(default_factory=list)
    wish_kind: Optional[str] = None
    need: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    value_given: float = 0.0
    value_received: float = 0.0

    def to_dict(self, public: bool = False) -> dict:
        d = asdict(self)
        if public:
            d.pop("value_given")
            d.pop("value_received")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SideMotive":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        known.setdefault("team", "")
        return cls(**known)


@dataclass
class TradeMotive:
    trade_type: str
    why: str = ""
    sides: List[SideMotive] = field(default_factory=list)
    team_count: int = 2

    def to_dict(self, public: bool = False) -> dict:
        return {"trade_type": self.trade_type, "why": self.why, "team_count": self.team_count,
                "sides": [s.to_dict(public) for s in self.sides]}

    @classmethod
    def from_dict(cls, d: dict) -> "TradeMotive":
        return cls(trade_type=d.get("trade_type", ""), why=d.get("why", ""),
                   sides=[SideMotive.from_dict(s) for s in d.get("sides", [])],
                   team_count=int(d.get("team_count", 2)))


def _join(items: List[str], fallback: str) -> str:
    return ", ".join(items) if items else fallback


def reasons_for(wish_kind: Optional[str], *, team: str, plan: str, traits: List[str], gets: List[str],
                gives: List[str], need: Optional[str]) -> List[str]:
    """2-3 short English reasons; [] when there is no wish (old saves, unknown kind)."""
    templates = REASON_TEMPLATES.get(wish_kind or "")
    if not templates:
        return []
    fields = dict(team=team, plan=plan, need=need or "rotation", gets=_join(gets, "the package"),
                  gives=_join(gives, "the outgoing players"))
    out = [t.format(**fields) for t in templates[:2]]
    for trait in traits:
        if trait in TRAIT_REASONS and wish_kind in TRAIT_KINDS.get(trait, ()):
            out.append(TRAIT_REASONS[trait])
            break
    return out


def why_line(trade_type: str, sides: List[SideMotive]) -> str:
    """One sentence joining the CPU sides' phrases with ' · '; the user side is skipped."""
    parts = []
    for s in sides:
        if s.plan == "USER":
            continue
        phrase = WHY_PHRASES.get(s.wish_kind or "")
        if phrase:
            parts.append(phrase.format(team=s.team, need=s.need or "rotation spot"))
    return " · ".join(parts)


def user_side_motive(team: str) -> SideMotive:
    return SideMotive(team=team, plan="USER")


def log_line(motive: TradeMotive, a_str_by_team: Dict[str, str]) -> str:
    """English line for trades_history.txt and news: who gets what, then the why."""
    got = "; ".join(f"{team} get {text}" for team, text in a_str_by_team.items())
    return f"{got}. Why: {motive.why}" if motive.why else got
