"""The front office's offseason window: GMs retire, owners fire the failures, the open seats are filled.

Runs once per offseason at the end of the coach firing phase (`Tournament._gestisci_fase_licenziamenti`), after
the season record is closed. The user's team in gm_coach / only_gm mode has no CPU GM: never judged, never filled.
"""
import logging
import random

from core.front_office.careers import retire_gms
from core.front_office.hiring import add_market_newcomers, run_hiring_round
from core.front_office.owners import fire_gm_roll, gm_fire_reason
from core.front_office.plans import new_gm_plan
from core.front_office.state import _unseat, current_year, ensure_front_office, user_team_name

main_log = logging.getLogger("main_sim")


def _news(torneo, event: str, team, name: str, detail: str = "") -> None:
    try:   # news never break the offseason
        from core.news_generator import generate_front_office_news
        generate_front_office_news(event, team, "GM", name, detail, season=getattr(torneo, "season_number", None))
    except Exception as exc:
        main_log.warning("front office news failed: %s", exc)


def _log(torneo, line: str) -> None:
    log_data = getattr(torneo, "offseason_log_data", None)
    if isinstance(log_data, dict) and "ritiri_sviluppo" in log_data:
        log_data["ritiri_sviluppo"].append(line)
    main_log.info(line)


def front_office_offseason(torneo, rng=None) -> dict:
    """Retirements, GM firings and the hiring round; returns what happened:
    {"retired": [{"gm", "gm_id", "team"}], "fired": [{"team", "gm", "gm_id", "reason"}],
     "hired": [{"team", "gm", "gm_id", "historical", "over": [...]}]}."""
    fo = ensure_front_office(torneo)
    rng = rng if rng is not None else random.Random()
    year = current_year(torneo)
    user_team = user_team_name(torneo)
    events = {"retired": [], "fired": [], "hired": []}

    add_market_newcomers(fo, year)

    seats_before = {gm_id: team for team, gm_id in fo.seats.items()}
    for gm in retire_gms(torneo, fo, rng):
        team = seats_before.get(gm.gm_id)
        events["retired"].append({"gm": gm.name, "gm_id": gm.gm_id, "team": team})
        _log(torneo, f"GM RETIREMENT: {gm.name} retired" + (f" as GM of the {team}" if team else ""))
        if team:
            _news(torneo, "retired", team, gm.name, f"{gm.name} steps down as GM of the {team}.")

    teams = sorted(getattr(torneo, "squadre", []), key=lambda s: s.nome)
    for team in teams:
        gm = fo.seated_gm(team.nome)
        if team.nome == user_team or gm is None:
            continue
        coach_only = getattr(torneo, "user_role", None) == "only_coach" and team is getattr(torneo, "squadra_giocatore", None)
        reason = gm_fire_reason(torneo, fo, team, gm, coach_only)
        if fire_gm_roll(reason, rng):
            _unseat(fo, team.nome, year, "fired")
            events["fired"].append({"team": team.nome, "gm": gm.name, "gm_id": gm.gm_id, "reason": reason})
            _log(torneo, f"GM FIRING: The {team.nome} fired GM {gm.name} ({reason})")
            _news(torneo, "fired", team.nome, gm.name, f"The ownership lets GM {gm.name} go ({reason}).")

    vacancies = [t.nome for t in teams if t.nome != user_team
                 and (fo.seated_gm(t.nome) is None or fo.seated_gm(t.nome).interim)]
    interims = {name: fo.seats.get(name) for name in vacancies}
    hires = run_hiring_round(torneo, fo, vacancies, rng)
    for team in teams:
        gm_id = hires.get(team.nome)
        if gm_id is None:
            continue
        gm = fo.gms[gm_id]
        if gm_id != interims.get(team.nome):  # a confirmed interim keeps the plan he has been running
            new_gm_plan(torneo, team, gm, year)
        over = next((n["names"] for n in reversed(gm.hiring_notes)
                     if n["kind"] == "chosen_over" and n["year"] == year and n["team"] == team.nome), [])
        events["hired"].append({"team": team.nome, "gm": gm.name, "gm_id": gm_id, "historical": gm.historical,
                                "over": list(over)})
        _log(torneo, f"GM HIRING: The {team.nome} hired GM {gm.name}"
                     + (f", chosen over {', '.join(over)}" if over else ""))
        if gm_id != interims.get(team.nome):   # a confirmed interim is no new story
            _news(torneo, "hired", team.nome, gm.name,
                  f"{gm.name} takes over the front office" + (f", chosen over {', '.join(over)}." if over else "."))
    return events
