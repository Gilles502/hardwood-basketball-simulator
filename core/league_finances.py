"""Pure computations behind /api/economy: CBA lines, every team's payroll situation, league totals, contract lists.

Reads plain attributes (tournament with .salary_cap/.squadre, teams with .payroll/.roster) so it can be tested
without the Flask server. The engine marks a missing line (no aprons before 2023, no-cap mode) with 9999;
here such lines become None. Sizes and the "no line" threshold come from CONFIG.ECONOMY.
"""
from typing import Dict, List, Optional


def _line(value, cfg) -> Optional[float]:
    """A CBA line, or None when the engine uses its 'no limit' placeholder."""
    if value is None or value >= cfg.UNLIMITED_LINE:
        return None
    return round(value, 2)


def season_lines(torneo, cfg) -> Dict:
    """This season's cap, floor, tax, aprons and signing amounts."""
    cap = _line(getattr(torneo, 'salary_cap', None), cfg)
    return {
        "year": getattr(torneo, 'anno_corrente', None),
        "no_cap": cap is None,
        "salary_cap": cap,
        "salary_floor": _line(getattr(torneo, 'salary_floor', None), cfg) if cap is not None else None,
        "luxury_tax": _line(getattr(torneo, 'luxury_tax_threshold', None), cfg),
        "first_apron": _line(getattr(torneo, 'first_apron', None), cfg),
        "second_apron": _line(getattr(torneo, 'second_apron', None), cfg),
        "mle": _line(getattr(torneo, 'mle_value', None), cfg),
        "bae": round(cfg.BAE_VALUE, 2) if cap is not None else None,
        "min_salary": round(getattr(torneo, 'min_salary', cfg.MIN_SALARY), 2),
    }


def payroll_status(payroll: float, lines: Dict) -> str:
    """'second_apron' | 'first_apron' | 'tax' | 'over_cap' | 'under_cap' | 'under_floor' | 'no_cap'."""
    if lines["salary_cap"] is None:
        return "no_cap"
    for key, status in (("second_apron", "second_apron"), ("first_apron", "first_apron"), ("luxury_tax", "tax")):
        if lines[key] is not None and payroll > lines[key]:
            return status
    if payroll > lines["salary_cap"]:
        return "over_cap"
    if lines["salary_floor"] is not None and payroll < lines["salary_floor"]:
        return "under_floor"
    return "under_cap"


def league_totals(teams: List[Dict]) -> Dict:
    payrolls = [t["payroll"] for t in teams]
    count = lambda *statuses: sum(1 for t in teams if t["status"] in statuses)
    return {
        "teams": len(teams),
        "total_payroll": round(sum(payrolls), 2),
        "average_payroll": round(sum(payrolls) / len(payrolls), 2) if payrolls else 0.0,
        "highest_payroll": max(payrolls) if payrolls else 0.0,
        "lowest_payroll": min(payrolls) if payrolls else 0.0,
        "taxpayers": count("tax", "first_apron", "second_apron"),
        "over_cap": count("over_cap"),
        "under_cap": count("under_cap", "under_floor"),
        "under_floor": count("under_floor"),
    }


def contract_lists(contracts: List[Dict], size: int) -> Dict:
    """Highest salaries, bargains and overpays.

    Each contract is {name, team, salary, score}. A player's fair salary is the salary paid at the same rank in the
    league by performance score: the 10th best player "should" earn the 10th biggest salary. The gap between
    salary and fair salary ranks bargains and overpays, so a star paid like a star is neither.
    """
    if not contracts:
        return {"highest": [], "bargains": [], "overpays": []}
    salaries = sorted((c["salary"] for c in contracts), reverse=True)
    by_score = sorted(contracts, key=lambda c: (-c["score"], c["name"]))
    rated = [dict(c, fair_salary=round(salaries[rank], 2)) for rank, c in enumerate(by_score)]
    gap = lambda c: c["salary"] - c["fair_salary"]
    return {
        "highest": sorted(rated, key=lambda c: -c["salary"])[:size],
        "bargains": sorted((c for c in rated if gap(c) < 0), key=gap)[:size],
        "overpays": sorted((c for c in rated if gap(c) > 0), key=lambda c: -gap(c))[:size],
    }


def build_economy(torneo, cfg) -> Dict:
    lines = season_lines(torneo, cfg)
    teams: List[Dict] = []
    next_season: Optional[Dict] = None
    for squadra in torneo.squadre:
        payroll = round(squadra.payroll, 2)
        projection = squadra.get_multi_year_financial_projection(num_years=2)
        nxt = projection[1] if len(projection) > 1 else None
        if nxt and next_season is None:
            next_cap = _line(nxt.get("salary_cap"), cfg)
            next_season = {
                "year": nxt.get("calendar_year"),
                "salary_cap": next_cap,
                "luxury_tax": _line(nxt.get("luxury_tax"), cfg),
                "first_apron": _line(nxt.get("first_apron"), cfg),
                "second_apron": _line(nxt.get("second_apron"), cfg),
            }
        next_payroll = round(nxt["total_payroll"], 2) if nxt else None
        next_cap = next_season["salary_cap"] if next_season else None
        teams.append({
            "name": squadra.nome,
            "payroll": payroll,
            "cap_space": round(lines["salary_cap"] - payroll, 2) if lines["salary_cap"] is not None else None,
            "status": payroll_status(payroll, lines),
            "owner": getattr(squadra, 'personalita_proprietario', None),
            "roster_size": len(squadra.roster),
            "next_payroll": next_payroll,
            "next_cap_space": round(next_cap - next_payroll, 2) if next_cap is not None and next_payroll is not None else None,
            "expiring_salary": round(nxt["expiring_salary_freed"], 2) if nxt else 0.0,
        })
    teams.sort(key=lambda t: -t["payroll"])

    contracts = [
        {"name": p.nome, "team": squadra.nome, "salary": round(p.contract.salario_annuale, 2),
         "score": round(p.performance_scores.total, 1)}
        for squadra in torneo.squadre for p in squadra.roster if p.contract
    ]
    market = sorted((t for t in teams if t["next_cap_space"] is not None and t["next_cap_space"] > 0),
                    key=lambda t: -t["next_cap_space"])
    return {
        "season": lines,
        "next_season": next_season,
        "market_watch": [t["name"] for t in market[:cfg.FINANCES_LIST_SIZE]],
        "league": league_totals(teams),
        "teams": teams,
        "contracts": contract_lists(contracts, cfg.FINANCES_LIST_SIZE),
    }


def team_outlook(squadra, torneo, cfg) -> Dict:
    """A team's committed salary for the next CONFIG.ECONOMY.OUTLOOK_YEARS seasons, one row per current contract.

    Seasons carry the CBA lines of that year (floor included, which the engine projection leaves out) and the
    same status codes as the league table. A player's salaries list has None for seasons after the contract ends.
    """
    projection = squadra.get_multi_year_financial_projection(num_years=cfg.OUTLOOK_YEARS)
    current = season_lines(torneo, cfg)
    seasons = []
    for idx, year in enumerate(projection):
        cap = _line(year.get("salary_cap"), cfg)
        lines = {
            "salary_cap": cap,
            "salary_floor": current["salary_floor"] if idx == 0 else (round(cap * cfg.SALARY_FLOOR_RATIO, 2) if cap is not None else None),
            "luxury_tax": _line(year.get("luxury_tax"), cfg),
            "first_apron": _line(year.get("first_apron"), cfg),
            "second_apron": _line(year.get("second_apron"), cfg),
        }
        payroll = round(year["total_payroll"], 2)
        seasons.append(dict(lines, year=year.get("calendar_year"), payroll=payroll, status=payroll_status(payroll, lines),
                            expiring_players=list(year.get("expiring_players") or []),
                            expiring_salary=round(year.get("expiring_salary_freed") or 0.0, 2)))

    players = []
    for entry in projection[0]["player_salaries"] if projection else []:
        salaries = []
        for year in projection:
            match = next((p for p in year["player_salaries"] if p["name"] == entry["name"]), None)
            salaries.append(round(match["salary"], 2) if match else None)
        players.append({"name": entry["name"], "role": entry["role"], "ovr": entry["ovr"], "age": entry["age"],
                        "years_left": entry["years_left"], "salaries": salaries})
    return {"team": squadra.nome, "seasons": seasons, "players": players}
