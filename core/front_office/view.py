"""What the Front Office & Board page shows: the league's GMs, one GM's card, the GM market. Pure reads."""
from typing import Optional

from core.config import CONFIG, normalize_owner_personality
from core.front_office.models import CpuGM
from core.front_office.state import current_year, ensure_front_office, user_gm_name, user_team_name


def _trait_labels(gm: CpuGM) -> list:
    return [CONFIG.FRONT_OFFICE.TRAITS.get(code, code) for code in gm.traits]


def _user_name(torneo) -> str:
    return user_gm_name(torneo)


def _gm_row(gm: CpuGM) -> dict:
    return {"gm_id": gm.gm_id, "name": gm.name, "age": gm.age, "years_as_gm": gm.years_as_gm,
            "traits": _trait_labels(gm), "skills": dict(gm.skills), "historical": gm.historical,
            "available_from_year": gm.available_from_year}


_END_LABELS = {"fired": "Fired", "retired": "Retired", "user_took_over": "Left: user took over",
               "interim_end": "Interim"}


def _career_rows(gm: CpuGM) -> list:
    """Newest job first; the open job reads "Current" (the Interim tag sits on the GM)."""
    rows = []
    for job in reversed(gm.career):
        end = job.get("end")
        label = "Current" if end is None else _END_LABELS.get(end, end)
        rows.append({"team": job["team"], "from_year": job["from_year"], "to_year": job.get("to_year"),
                     "end": end, "end_label": label, "wins": job.get("wins", 0), "losses": job.get("losses", 0),
                     "playoffs": job.get("playoffs", 0), "titles": job.get("titles", 0),
                     "awards": list(job.get("awards", []))})
    return rows


def _new_this_year(gm: CpuGM, year: int) -> bool:
    """An offseason hire is stored with the finished season's year, so "new" covers the year before too."""
    if not gm.career:
        return False
    job = gm.career[-1]
    return job.get("to_year") is None and job["from_year"] >= year - 1


def _note_text(note: dict) -> str:
    kind, year, names = note.get("kind"), note.get("year"), ", ".join(note.get("names", []))
    if kind == "turned_down":
        return f"Turned down the {note.get('team')} ({year})"
    if kind == "chased_by":
        return f"Chased by {names} ({year})"
    if kind == "chosen_over":
        return f"Chosen over {names} ({year})"
    return f"{kind} ({year})"


def _move_when(move: dict) -> str:
    """Deadline, draft, free agency and the offseason fall in the calendar year after the season starts."""
    year = int(move.get("year") or 0)
    window = move.get("window", "Season")
    return f"{window} {year if window == 'Season' else year + 1}"


def league_table(torneo) -> dict:
    fo = ensure_front_office(torneo)
    year = current_year(torneo)
    labels = CONFIG.FRONT_OFFICE.PLAN_LABELS
    user_team = user_team_name(torneo)
    rows = []
    for team in sorted(s.nome for s in torneo.squadre):
        plan = fo.plans.get(team)
        row = {"team": team, "is_user": team == user_team,
               "plan": plan.state if plan else None,
               "plan_label": labels.get(plan.state, plan.state) if plan else None,
               "seasons_held": plan.seasons_held if plan else None, "interim": False, "new_this_year": False}
        gm = fo.seated_gm(team)
        if row["is_user"]:
            row.update({"gm_id": None, "name": _user_name(torneo), "age": None, "traits": [], "skills": None})
        elif gm is not None:
            row.update({"gm_id": gm.gm_id, "name": gm.name, "age": gm.age, "traits": _trait_labels(gm),
                        "skills": dict(gm.skills), "interim": gm.interim,
                        "new_this_year": _new_this_year(gm, year)})
        else:
            row.update({"gm_id": None, "name": "Vacant", "age": None, "traits": [], "skills": None})
        rows.append(row)
    return {"season": int(getattr(torneo, "season_number", 1)), "year": year, "rows": rows}


def gm_card(torneo, team_name: str) -> Optional[dict]:
    team = next((s for s in torneo.squadre if s.nome == team_name), None)
    if team is None:
        return None
    fo = ensure_front_office(torneo)
    fo_cfg = CONFIG.FRONT_OFFICE
    is_user = team_name == user_team_name(torneo)

    gm = None if is_user else fo.seated_gm(team_name)
    gm_block = None
    if gm is not None:
        gm_block = {"gm_id": gm.gm_id, "name": gm.name, "age": gm.age, "years_as_gm": gm.years_as_gm,
                    "tenure": gm.tenure, "historical": gm.historical,
                    "traits": [{"code": c, "label": fo_cfg.TRAITS.get(c, c)} for c in gm.traits],
                    "skills": dict(gm.skills), "interim": gm.interim, "career": _career_rows(gm),
                    "hiring_notes": [dict(n, text=_note_text(n)) for n in reversed(gm.hiring_notes)]}

    plan = fo.plans.get(team_name)
    plan_block = None
    if plan is not None:
        plan_block = {"state": plan.state, "label": fo_cfg.PLAN_LABELS.get(plan.state, plan.state),
                      "seasons_held": plan.seasons_held,
                      "expected_seasons": fo_cfg.PLAN_EXPECTED_SEASONS.get(plan.state),
                      "reason": plan.reason, "since_year": plan.since_year,
                      "history": [dict(h) for h in reversed(plan.history)]}

    coach = getattr(team, "coach", None)
    coach_block = None
    if coach is not None:
        style = getattr(coach, "stile_gioco", None)
        coach_block = {"name": getattr(coach, "nome", None), "style": style,
                       "wants": fo_cfg.COACH_STYLE_TARGETS.get(style)}

    personality = normalize_owner_personality(getattr(team, "personalita_proprietario", None)) or "Bilanciato"
    eco = CONFIG.ECONOMY
    owner_block = {"personality": personality, "patience": eco.OWNER_BOARD_PATIENCE.get(personality),
                   "spending": eco.OWNER_BOARD_SPENDING.get(personality)}

    moves = [dict(m, when=_move_when(m)) for m in reversed(fo.moves.get(team_name, []))]
    return {"team": team_name, "is_user": is_user, "user_name": _user_name(torneo) if is_user else None,
            "gm": gm_block, "plan": plan_block, "coach": coach_block, "owner": owner_block, "moves": moves}


def gm_market(torneo) -> dict:
    """Unemployed GMs that can be hired now (historical arrivals only from their real arrival year)."""
    fo = ensure_front_office(torneo)
    year = current_year(torneo)
    rows = []
    for gm in fo.gms.values():
        if gm.team is not None or gm.retired_year is not None:
            continue
        if gm.available_from_year is not None and gm.available_from_year > year:
            continue
        rows.append(dict(_gm_row(gm), jobs=len(gm.career), titles=sum(j.get("titles", 0) for j in gm.career),
                         playoffs=sum(j.get("playoffs", 0) for j in gm.career)))
    rows.sort(key=lambda r: (-sum(r["skills"].values()), r["name"]))
    return {"year": year, "unemployed": rows}
