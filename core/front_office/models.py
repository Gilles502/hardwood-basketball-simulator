"""The CPU GM: a person with a team link (never a field on Squadra)."""
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class CpuGM:
    gm_id: str
    name: str
    age: int
    years_as_gm: int
    traits: List[str]
    skills: Dict[str, int]
    team: Optional[str] = None
    tenure: int = 0
    historical: bool = False
    available_from_year: Optional[int] = None
    # Jobs held, oldest first: {"team", "from_year", "to_year" (None = open), "end" (None, "fired", "retired",
    # "user_took_over", "interim_end"), "wins", "losses", "playoffs", "titles"}.
    career: List[dict] = field(default_factory=list)
    interim: bool = False          # seated mid-season until the owner decides
    retired_year: Optional[int] = None
    # {"year", "kind": "turned_down" | "chosen_over" | "chased_by", "team", "names": [...]}
    hiring_notes: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = asdict(self)
        out["traits"] = list(self.traits)
        out["skills"] = dict(self.skills)
        out["career"] = [dict(c) for c in self.career]
        out["hiring_notes"] = [{**n, "names": list(n.get("names", []))} for n in self.hiring_notes]
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "CpuGM":
        return cls(
            gm_id=str(d["gm_id"]),
            name=str(d["name"]),
            age=int(d["age"]),
            years_as_gm=int(d.get("years_as_gm", 0)),
            traits=list(d.get("traits", [])),
            skills={k: int(v) for k, v in dict(d.get("skills", {})).items()},
            team=d.get("team"),
            tenure=int(d.get("tenure", 0)),
            historical=bool(d.get("historical", False)),
            available_from_year=d.get("available_from_year"),
            career=[dict(c) for c in d.get("career", [])],
            interim=bool(d.get("interim", False)),
            retired_year=d.get("retired_year"),
            hiring_notes=[{**n, "names": list(n.get("names", []))} for n in d.get("hiring_notes", [])],
        )


@dataclass
class TeamPlan:
    """A team's plan with memory: changed only at the season start or a deadline emergency, always with a reason.
    history entries: {"year", "from", "to", "reason", "checkpoint"} ("from" None = the first plan)."""
    state: str
    since_year: int
    seasons_held: int
    reason: str
    history: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"state": self.state, "since_year": self.since_year, "seasons_held": self.seasons_held,
                "reason": self.reason, "history": [dict(h) for h in self.history]}

    @classmethod
    def from_dict(cls, d: dict) -> "TeamPlan":
        return cls(state=str(d["state"]), since_year=int(d.get("since_year", 0)),
                   seasons_held=int(d.get("seasons_held", 1)), reason=str(d.get("reason", "")),
                   history=[dict(h) for h in d.get("history", [])])
