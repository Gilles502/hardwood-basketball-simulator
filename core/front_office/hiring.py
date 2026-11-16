"""The GM market and the offseason hiring round: owners score the candidates, wanted GMs choose too.

Owners weigh reputation, fit to the moment (the opposite of what just failed) and their own personality, plus a
little noise. Teams propose in rounds; a GM with several offers takes the most appealing team, and a wanted GM
turns down a hopeless team while another seat is still open. Seated GMs are never poached.
"""
from typing import Dict, List

from core.config import CONFIG, normalize_owner_personality, owner_spending_tier
from core.front_office.models import CpuGM
from core.front_office.plans import _avg, _league_top8, _top8, suggest_plan
from core.front_office.roster import generated_gm
from core.front_office.state import FrontOfficeState, current_year, end_job, start_job


def add_market_newcomers(fo: FrontOfficeState, year: int) -> None:
    """A few young made-up GMs enter the market each offseason (once per year: seeds are per year)."""
    cfg = CONFIG.FRONT_OFFICE
    for i in range(cfg.MARKET_NEWCOMERS_PER_YEAR):
        gm = generated_gm(f"market|{year}|{i}", year, age_range=cfg.MARKET_NEWCOMER_AGE,
                          skill_range=cfg.MARKET_NEWCOMER_SKILLS)
        fo.gms.setdefault(gm.gm_id, gm)


def _seated(fo: FrontOfficeState, gm: CpuGM) -> bool:
    return gm.team is not None and fo.seats.get(gm.team) == gm.gm_id


def available_candidates(fo: FrontOfficeState, year: int) -> List[CpuGM]:
    """Unseated, not retired GMs free to be hired this year, plus the interims sitting in seats (vacant by
    definition in the offseason). Sorted by gm_id so the round is stable."""
    out = []
    for gm_id in sorted(fo.gms):
        gm = fo.gms[gm_id]
        if gm.retired_year is not None:
            continue
        if _seated(fo, gm):
            if gm.interim:
                out.append(gm)
        elif gm.available_from_year is None or gm.available_from_year <= year:
            out.append(gm)
    return out


def reputation(gm: CpuGM) -> float:
    """The visible record: skills average, years as GM (capped), playoff runs and titles in his jobs."""
    cfg = CONFIG.FRONT_OFFICE
    skills = _avg(gm.skills.values(), 0.0)
    playoffs = sum(int(e.get("playoffs", 0)) for e in gm.career)
    titles = sum(int(e.get("titles", 0)) for e in gm.career)
    return (skills + cfg.REP_PER_YEAR * min(gm.years_as_gm, cfg.REP_YEARS_CAP)
            + cfg.REP_PER_PLAYOFF * playoffs + cfg.REP_PER_TITLE * titles)


def fit_to_moment(gm: CpuGM, wanted: str) -> float:
    """How well his philosophy fits what the owner wants now: "WIN_NOW", "BUILD" or "ANY"."""
    cfg = CONFIG.FRONT_OFFICE
    traits = {"WIN_NOW": cfg.HIRING_WIN_NOW_TRAITS, "BUILD": cfg.HIRING_BUILD_TRAITS}.get(wanted, ())
    return cfg.FIT_PER_TRAIT * sum(1 for t in gm.traits if t in traits)


def wanted_profile(torneo, team) -> str:
    return CONFIG.FRONT_OFFICE.HIRING_WANTED_BY_PLAN.get(suggest_plan(team, torneo)[0], "ANY")


def owner_score(team, gm: CpuGM, wanted: str, rng) -> float:
    """The owner's score of a candidate: reputation and fit, weighted by the owner's personality, plus noise."""
    cfg = CONFIG.FRONT_OFFICE
    owner = normalize_owner_personality(getattr(team, "personalita_proprietario", None))
    score = (cfg.HIRING_REP_WEIGHT * cfg.HIRING_OWNER_WEIGHTS.get(owner, 1.0) * reputation(gm)
             + cfg.HIRING_FIT_WEIGHT * fit_to_moment(gm, wanted))
    if owner in cfg.HIRING_YOUNG_OWNERS and (gm.age < cfg.HIRING_YOUNG_AGE or gm.years_as_gm < cfg.HIRING_YOUNG_YEARS):
        score += cfg.HIRING_YOUNG_BONUS
    if cfg.HIRING_NOISE > 0:
        score += rng.uniform(-cfg.HIRING_NOISE, cfg.HIRING_NOISE)
    return score


def _last_wins(torneo, team) -> int:
    rows = getattr(getattr(torneo, "front_office", None), "records", {}).get(team.nome, [])
    return int(rows[-1]["wins"]) if rows else int(getattr(team, "vittorie", 0))


def team_appeal(torneo, team) -> float:
    """How attractive the job looks to a GM (~0-100): last season's wins, the top-8 talent against the league,
    and how much the owner spends."""
    cfg = CONFIG.FRONT_OFFICE
    gap = _avg((p.ovr for p in _top8(team)), 0.0) - _league_top8(torneo)
    spending = cfg.APPEAL_SPENDING.get(owner_spending_tier(getattr(team, "personalita_proprietario", None)), 0.0)
    return (cfg.APPEAL_BASE + (_last_wins(torneo, team) - cfg.EXPECTED_WINS_BASE) * cfg.APPEAL_PER_WIN
            + gap * cfg.APPEAL_PER_OVR + spending)


def _fired_by(gm: CpuGM, team: str) -> bool:
    return any(e.get("team") == team and e.get("end") == "fired" for e in gm.career)


def _note(gm: CpuGM, year: int, kind: str, team, names: List[str]) -> None:
    gm.hiring_notes.append({"year": year, "kind": kind, "team": team, "names": list(names)})
    del gm.hiring_notes[:-CONFIG.FRONT_OFFICE.HIRING_NOTES_KEEP]


def _hire(fo: FrontOfficeState, team: str, gm: CpuGM, year: int) -> None:
    """Seats `gm` at `team` for good. A replaced interim goes back to the market; a confirmed interim keeps his job."""
    current = fo.seated_gm(team)
    if current is gm:
        gm.interim = False
        return
    if current is not None:
        fo.seats.pop(team)
        end_job(current, year, "interim_end")
    if _seated(fo, gm):  # an interim elsewhere takes this job instead: his old seat stays open
        fo.seats.pop(gm.team)
        end_job(gm, year, "interim_end")
    start_job(gm, team, year)
    gm.interim = False
    fo.gms[gm.gm_id] = gm
    fo.seats[team] = gm.gm_id


def _fresh_generated(fo: FrontOfficeState, team: str, year: int) -> CpuGM:
    """A made-up GM for a team with no candidate left (the same one `_seat_generated` would pick, when free)."""
    seed, n = f"{team}|{year}", 0
    while True:
        gm = generated_gm(seed, year)
        known = fo.gms.get(gm.gm_id)
        if known is None:
            return gm
        if known.retired_year is None and (not _seated(fo, known) or known.team == team):
            return known
        n += 1
        seed = f"{team}|{year}|{n}"


def run_hiring_round(torneo, fo: FrontOfficeState, vacancies: List[str], rng) -> Dict[str, str]:
    """Fills every vacancy; returns team -> gm_id of the hired GM. See the module docstring for the rules."""
    cfg = CONFIG.FRONT_OFFICE
    year = current_year(torneo)
    teams = {t.nome: t for t in getattr(torneo, "squadre", []) if t.nome in vacancies}
    appeal = {name: team_appeal(torneo, t) for name, t in teams.items()}
    open_seats = sorted(teams, key=lambda name: (-appeal[name], name))

    candidates = available_candidates(fo, year)
    ranked = {}
    for name in open_seats:
        wanted = wanted_profile(torneo, teams[name])
        scored = [(owner_score(teams[name], gm, wanted, rng), gm.gm_id, gm)
                  for gm in candidates if not _fired_by(gm, name)]
        ranked[name] = [gm for _, _, gm in sorted(scored, key=lambda s: (-s[0], s[1]))]

    free = {gm.gm_id for gm in candidates}
    chasers: Dict[str, List[str]] = {}
    hires: Dict[str, str] = {}
    passed = {name: 0 for name in open_seats}   # how far down its list each team has gone

    while open_seats:
        proposals: Dict[str, List[str]] = {}
        for name in open_seats:
            options = ranked[name]
            while passed[name] < len(options) and options[passed[name]].gm_id not in free:
                passed[name] += 1
            if passed[name] < len(options):
                proposals.setdefault(options[passed[name]].gm_id, []).append(name)
            else:
                gm = _fresh_generated(fo, name, year)
                _hire(fo, name, gm, year)
                hires[name] = gm.gm_id
        others_open = len(open_seats) > 1
        for gm_id, proposers in proposals.items():
            gm = fo.gms[gm_id]
            seen = chasers.setdefault(gm_id, [])
            seen.extend([p for p in proposers if p not in seen])
            proposers = sorted(proposers, key=lambda name: (-appeal[name], name))
            best = proposers[0]
            refuses = (others_open and reputation(gm) >= cfg.HIRING_WANTED_REP
                       and appeal[best] < cfg.HIRING_REFUSE_APPEAL)
            turned_down = proposers if refuses else proposers[1:]
            for name in turned_down:
                _note(gm, year, "turned_down", name, [])
                passed[name] += 1
            if refuses:
                continue
            passed[best] += 1
            runner_ups = [g.name for g in ranked[best][passed[best]:] if g.gm_id in free]
            free.discard(gm_id)
            _hire(fo, best, gm, year)
            hires[best] = gm_id
            if runner_ups:
                _note(gm, year, "chosen_over", best, runner_ups[:cfg.HIRING_CHOSEN_OVER_NAMES])
        open_seats = [name for name in open_seats if name not in hires]

    for gm_id, names in chasers.items():  # "chased" means more than one team wanted him
        gm = fo.gms[gm_id]
        if len(names) > 1:
            _note(gm, year, "chased_by", gm.team if _seated(fo, gm) else None, names)
    return hires
