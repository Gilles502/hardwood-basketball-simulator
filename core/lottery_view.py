"""Lottery night: odds, owners and the draft order the End of Season Hub shows around the lottery draw.

The draw itself lives in Tournament.esegui_draft_lottery (weighted draw of LOTTERY_DRAWN_PICKS seeds without
replacement, the rest in seed order); the odds here are exact for that model. Pure: no Flask.
"""
from itertools import permutations
from typing import Dict, List, Optional, Tuple

from core.config import CONFIG


def lottery_weights(n: int) -> List[float]:
    cfg = CONFIG.OFFSEASON
    weights = list(cfg.LOTTERY_ODDS[:n])
    return weights + [cfg.LOTTERY_ODDS_EXTRA_TEAM] * (n - len(weights))


def _draws(weights: List[float]) -> List[Tuple[Tuple[int, ...], float]]:
    """Every possible outcome as (full pick order of seed indexes, probability)."""
    n = len(weights)
    drawn_count = min(CONFIG.OFFSEASON.LOTTERY_DRAWN_PICKS, n)
    total = sum(weights)
    outcomes = []
    for drawn in permutations(range(n), drawn_count):
        prob, left = 1.0, total
        for seed in drawn:
            prob *= weights[seed] / left
            left -= weights[seed]
        taken = set(drawn)
        outcomes.append((drawn + tuple(s for s in range(n) if s not in taken), prob))
    return outcomes


def odds_table(weights: List[float]) -> List[Dict]:
    """Per seed: chance (%) of the #1 pick and of a drawn pick."""
    total = sum(weights)
    drawn_count = min(CONFIG.OFFSEASON.LOTTERY_DRAWN_PICKS, len(weights))
    top = [0.0] * len(weights)
    for order, prob in _draws(weights):
        for seed in order[:drawn_count]:
            top[seed] += prob
    return [{"odds_first": round(100 * w / total, 1), "odds_top": round(100 * top[i], 1)} for i, w in enumerate(weights)]


def hunt_steps(weights: List[float], final_order: List[int]) -> List[List[Dict]]:
    """Entry k = after the last k picks are revealed: each still-sealed seed's chance (%) of the #1 pick."""
    n = len(weights)
    final = tuple(final_order)
    outcomes = _draws(weights)
    steps = []
    for k in range(n + 1):
        tail = final[n - k:]
        firsts: Dict[int, float] = {}
        total = 0.0
        for order, prob in outcomes:
            if order[n - k:] == tail:
                total += prob
                firsts[order[0]] = firsts.get(order[0], 0.0) + prob
        sealed = [s for s in range(n) if s not in tail]
        steps.append([{"seed": s, "odds_first": round(100 * firsts.get(s, 0.0) / total, 1) if total else 0.0} for s in sealed])
    return steps


def pick_owner(torneo, round_num: int, team: str) -> str:
    return ((getattr(torneo, 'pick_ownership', None) or {}).get(1) or {}).get(f"R{round_num}-{team}", team)


def pick_protection(torneo, team: str) -> str:
    return ((getattr(torneo, 'pick_protections', None) or {}).get(1) or {}).get(f"R1-{team}", "Unprotected")


def lottery_teams(torneo) -> List:
    """The teams that missed the playoffs, worst record first (the lottery seeds)."""
    playoff = {s.nome for s in torneo.get_playoff_teams(torneo.squadre)}
    return sorted([s for s in torneo.squadre if s.nome not in playoff], key=lambda s: s.vittorie)


def _record(team) -> str:
    return f"{getattr(team, 'vittorie', 0)}-{getattr(team, 'sconfitte', 0)}"


def lottery_preview(torneo) -> Optional[Dict]:
    """Before the draw: the lottery teams with their pick's owner, protection and odds."""
    teams = lottery_teams(torneo) if getattr(torneo, 'squadre', None) else []
    if not teams:
        return None
    table = odds_table(lottery_weights(len(teams)))
    return {"drawn_picks": CONFIG.OFFSEASON.LOTTERY_DRAWN_PICKS, "teams": [{
        "seed": i + 1,
        "team": t.nome,
        "owner": pick_owner(torneo, 1, t.nome),
        "protection": pick_protection(torneo, t.nome),
        "record": _record(t),
        "odds_first": table[i]["odds_first"],
        "odds_top": table[i]["odds_top"],
    } for i, t in enumerate(teams)]}


def annotate_owners(picks: List[Dict], owners_before: Dict[str, str], torneo) -> None:
    """Adds who owns each lottery pick after protections were resolved, and who owned it before."""
    for pick in picks:
        team = pick["team"]
        owner = pick_owner(torneo, 1, team)
        before = owners_before.get(team, owner)
        pick.update(owner=owner, owner_before=before, protection=pick_protection(torneo, team),
                    protection_triggered=before != owner)


def full_draft_order(torneo, lottery_picks: List[Dict]) -> List[Dict]:
    """Every pick of every round with its current owner; lottery moves on the first round."""
    order = list(getattr(torneo, 'draft_lottery_order', None) or [])
    teams = {t.nome: t for t in getattr(torneo, 'squadre', [])}
    lottery = {p["team"]: p for p in lottery_picks}
    rows = []
    for round_num in range(1, CONFIG.OFFSEASON.DRAFT_ROUNDS + 1):
        for i, team in enumerate(order):
            moved = lottery.get(team) if round_num == 1 else None
            rows.append({
                "round": round_num,
                "pick": i + 1,
                "overall": len(rows) + 1,
                "team": team,
                "owner": pick_owner(torneo, round_num, team),
                "record": _record(teams.get(team)),
                "projected": moved["projected"] if moved else i + 1,
                "delta": moved["delta"] if moved else 0,
            })
    return rows


def complete_details(details: Dict, torneo) -> Dict:
    """The stored lottery details as the page needs them: the draft order with today's owners, and owners / odds steps
    filled in for details saved before they existed (owners are then read as they stand now). The stored dict is
    left untouched."""
    picks = [dict(p) for p in details.get("picks") or []]
    for p in picks:
        if "owner" not in p:
            owner = pick_owner(torneo, 1, p["team"])
            p.update(owner=owner, owner_before=owner, protection=pick_protection(torneo, p["team"]), protection_triggered=False)
    steps = details.get("hunt_steps")
    if steps is None:
        by_seed = sorted(picks, key=lambda p: p["projected"])
        seed_of = {p["team"]: i for i, p in enumerate(by_seed)}
        steps = hunt_steps(lottery_weights(len(picks)), [seed_of[p["team"]] for p in sorted(picks, key=lambda p: p["pick"])])
    return {**details, "picks": picks, "hunt_steps": steps, "drawn_picks": CONFIG.OFFSEASON.LOTTERY_DRAWN_PICKS,
            "full_order": full_draft_order(torneo, picks)}
