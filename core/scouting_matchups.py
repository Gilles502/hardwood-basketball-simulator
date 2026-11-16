"""Opponent scouting for the Opponent tab: their threats against the user's defenders.

Pure functions (no Flask, no tournament) so the numbers are testable. The frontend mirrors these rules in
frontend/src/pages/rotations/scouting.ts to react instantly when an assignment changes; keep them in sync.
"""
from typing import Any, Dict, List, Optional, Tuple

from core.roles import normalize_role

SKILLS = ("3PT", "DRIVE", "POST")
# Which shot tendency says how often a player uses each skill
TENDENCY_OF = {"3PT": "three_point_shot_tendency", "DRIVE": "drive_to_basket_tendency", "POST": "post_up_tendency"}


def skills_of(p) -> Dict[str, int]:
    """3PT, DRIVE and POST ratings (0-99) of an attacker."""
    a = p.abilita
    return {
        "3PT": a.three_point_shot_rating,
        "DRIVE": round((a.speed + a.ball_handling + a.close_shot_rating) / 3),
        "POST": round((a.post_control_rating + a.close_shot_rating + a.strength) / 3),
    }


def defense_vs(p, skill: str) -> int:
    """The defender rating that answers a skill: inside defense for POST, perimeter defense otherwise."""
    return p.abilita.interior_defense_rating if skill == "POST" else p.abilita.perimeter_defense_rating


def badge(gap: int, cfg) -> str:
    if gap <= cfg.BAD_GAP:
        return "bad"
    if gap <= cfg.WATCH_GAP:
        return "watch"
    return "fine"


def pressure(threat: int, minutes: float, tendency: int, cfg) -> float:
    """How much a player can hurt you before any defense: skill, playing time and how often he uses it."""
    return threat * (minutes / 48) * (cfg.TENDENCY_BASE + cfg.TENDENCY_SPAN * tendency / 100)


def danger(threat: int, minutes: float, tendency: int, gap: int, cfg) -> float:
    return pressure(threat, minutes, tendency, cfg) + max(0, -gap) * cfg.GAP_WEIGHT


def build_report(their_rotation: List[Tuple[Any, Optional[str]]], my_players: List[Any],
                 my_positions: Dict[str, Any], plan: Dict[str, Any], cfg) -> List[Dict[str, Any]]:
    """One row per opponent rotation player, most dangerous first.

    their_rotation: (player, court position) pairs, position None for the bench.
    my_positions: the user's starter at each position, used for the "Auto" defender like the engine does.
    plan: {"matchups": {their_name: my_name}, "double_teams": [...]} for this opponent.
    """
    healthy = {p.nome: p for p in my_players if not p.infortunato}
    matchups = plan.get("matchups") or {}

    rows = []
    for their, court_pos in their_rotation:
        skills = skills_of(their)
        threat = max(SKILLS, key=lambda k: skills[k])
        tendency = getattr(their.tendenze, TENDENCY_OF[threat], 50)
        pos = court_pos or normalize_role(their.ruolo)
        chosen = healthy.get(matchups.get(their.nome, ""))
        defender = chosen or my_positions.get(pos)
        defense = defense_vs(defender, threat) if defender else 0
        gap = defense - skills[threat]
        rows.append({
            "name": their.nome,
            "pos": pos,
            "starter": court_pos is not None,
            "minutes": their.minuti_target,
            "skills": skills,
            "threat": threat,
            "threat_value": skills[threat],
            "defender": defender.nome if defender else None,
            "auto": chosen is None,
            "defense": defense,
            "gap": gap,
            "badge": badge(gap, cfg),
            "pressure": pressure(skills[threat], their.minuti_target, tendency, cfg),
            "danger": danger(skills[threat], their.minuti_target, tendency, gap, cfg),
            "fix": None,
        })

    # Fix: the best healthy rotation defender for that skill, unless he already guards a bigger threat
    # (chosen or auto: moving him would just open a worse matchup)
    for r in rows:
        if r["badge"] == "fine":
            continue
        taken = {o["defender"] for o in rows if o is not r and o["defender"] and o["pressure"] > r["pressure"]}
        candidates = [p for p in healthy.values() if p.minuti_target > 0 and p.nome != r["defender"] and p.nome not in taken]
        best = max(candidates, key=lambda p: defense_vs(p, r["threat"]), default=None)
        if best and defense_vs(best, r["threat"]) > r["defense"]:
            r["fix"] = best.nome

    rows.sort(key=lambda r: r["danger"], reverse=True)
    return rows


def series_opponent(team_name: str, playoff_series: Dict[str, Dict[str, Any]], active_series: List[Dict[str, Any]],
                    bracket: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The user's unfinished playoff series: {"opponent", "round", "user_wins", "opp_wins"}, or None.

    Looks where each playoff mode keeps it: the Playoffs page's game-by-game series (server PLAYOFF_SERIES),
    then the tournament's active series, then the bracket.
    """
    for s in (playoff_series or {}).values():
        if not s.get("complete") and team_name in (s.get("team1_name"), s.get("team2_name")):
            first = s.get("team1_name") == team_name
            return {"opponent": s["team2_name"] if first else s["team1_name"], "round": s.get("round", "PLAYOFFS"),
                    "user_wins": s.get("wins1" if first else "wins2", 0), "opp_wins": s.get("wins2" if first else "wins1", 0)}
    for s in active_series or []:
        t1, t2 = s.get("s1"), s.get("s2")
        if t1 and t2 and team_name in (t1.nome, t2.nome) and s.get("winner_nome") is None:
            opp = t2 if t1.nome == team_name else t1
            wins = s.get("vittorie", {})
            return {"opponent": opp.nome, "round": s.get("round", "PLAYOFFS"),
                    "user_wins": wins.get(team_name, 0), "opp_wins": wins.get(opp.nome, 0)}
    for rounds in (bracket or {}).values():
        if not isinstance(rounds, dict):
            continue
        for round_name, matchups in rounds.items():
            for m in matchups or []:
                if m and not m.get("winner_nome") and team_name in (m.get("s1_nome"), m.get("s2_nome")):
                    first = m.get("s1_nome") == team_name
                    return {"opponent": m["s2_nome"] if first else m["s1_nome"], "round": round_name.upper(),
                            "user_wins": m.get("s1_vittorie" if first else "s2_vittorie", 0),
                            "opp_wins": m.get("s2_vittorie" if first else "s1_vittorie", 0)}
    return None
