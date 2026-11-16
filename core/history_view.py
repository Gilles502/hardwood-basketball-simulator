"""History page views: the season-by-season championship list and the ranked Hall of Fame.

Pure functions over the saved files (league_history.json, hall_of_fame.json, player_careers.json), no Flask.
The saved data uses Italian keys and playoff labels; they are read only here, the page gets English.
"""
from collections import Counter

from core.config import CONFIG

CHAMPION_LABEL = "Campione"  # playoff_round starts with it ("Campione NBA 🏆")
FINALS_LABEL = "Finali"      # playoff_round of the finals loser ("Finali NBA")

AWARD_KEYS = {"mvp": "mvp", "dpoy": "dpoy", "roy": "roy", "sixth_man": "sesto_uomo", "mip": "mip"}
ALL_LEAGUE_KEYS = {"first": "all_nba_1st", "second": "all_nba_2nd", "third": "all_nba_3rd"}
ACCOLADE_KEYS = {"titles": "titoli", "mvp": "mvp", "finals_mvp": "finals_mvp", "dpoy": "dpoy",
                 "all_league_1st": "all_nba_1st", "all_league": "all_nba_total", "all_star": "all_star"}


def season_years(history):
    """Season number -> year, from the seasons on file that carry one."""
    return {item["stagione"]: item["anno"] for item in history or []
            if isinstance(item, dict) and item.get("stagione") and item.get("anno")}


def year_for(season, years, starting_year):
    """The year of a season: on file, else counted from the nearest season on file, else from the starting year."""
    if season is None:
        return None
    if season in years:
        return years[season]
    if years:
        nearest = min(years, key=lambda n: abs(n - season))
        return years[nearest] + (season - nearest)
    return starting_year + season - 1 if starting_year else None


def parse_season(label):
    """5 from 5 or "Season 5"; None from "-", "" or None (old saves store season labels as text)."""
    if isinstance(label, int):
        return label
    digits = "".join(ch for ch in str(label or "") if ch.isdigit())
    return int(digits) if digits else None


def playoff_label(raw):
    """A saved playoff_round ("Campione NBA 🏆", "Finali NBA", "Playoff", …) in English."""
    text = str(raw or "")
    if text.startswith(CHAMPION_LABEL):
        return "Champions"
    if text.startswith(FINALS_LABEL):
        return "Lost Finals"
    for label in ("Play-In", "Lottery", "In Progress"):
        if text == label:
            return label
    return "Playoffs"


def _name(value):
    """A saved award winner, or None when the season has none ("N/A", empty)."""
    if not value or not isinstance(value, str) or value.strip().upper() == "N/A":
        return None
    return value


def _team_row(standing):
    if not standing:
        return None
    return {"team": standing.get("team"), "wins": standing.get("wins", 0), "losses": standing.get("losses", 0),
            "conference": standing.get("conference"), "seed": standing.get("conf_seed"),
            "league_rank": standing.get("league_rank")}


def _season_entry(item, titles_so_far, champions_by_season, user_team):
    cfg = CONFIG.HISTORY
    number = item["stagione"]
    champion_name = item.get("campione")
    standings = item.get("standings") or []
    champion = next((s for s in standings if s.get("team") == champion_name), None)
    runner_up = next((s for s in standings if str(s.get("playoff_round", "")).startswith(FINALS_LABEL)), None)

    def tag(s):
        if s.get("team") == champion_name:
            return "champion"
        if runner_up is not None and s.get("team") == runner_up.get("team"):
            return "finals"
        return None

    ranked = sorted((s for s in standings if s.get("league_rank")), key=lambda s: s["league_rank"])
    top = ranked[:cfg.TOP_STANDINGS]
    if champion is not None and champion not in top:
        top = top + [champion]
    premi = item.get("premi") or {}
    window = range(number - cfg.RUN_WINDOW + 1, number + 1)
    return {
        "season": number,
        "year": item.get("anno"),
        "champion": _team_row(champion) or {"team": champion_name, "wins": 0, "losses": 0, "conference": None,
                                            "seed": None, "league_rank": None},
        "runner_up": _team_row(runner_up),
        "finals_mvp": _name(item.get("mvp_finali")),
        "awards": {key: _name(premi.get(saved)) for key, saved in AWARD_KEYS.items()},
        "all_league": {key: [n for n in (premi.get(saved) or []) if _name(n)] for key, saved in ALL_LEAGUE_KEYS.items()},
        "top_standings": [{"rank": s.get("league_rank"), "team": s.get("team"), "wins": s.get("wins", 0),
                           "losses": s.get("losses", 0), "tag": tag(s)} for s in top],
        "franchise_title_no": titles_so_far,
        "run": sum(1 for n in window if champions_by_season.get(n) == champion_name),
        "run_window": min(cfg.RUN_WINDOW, number),
        "is_user_team": bool(user_team) and champion_name == user_team,
    }


def championship_history(history, user_team):
    """One entry per season number from 1 to the last on file, newest first; absent seasons are placeholders."""
    seasons = {item["stagione"]: item for item in history or [] if isinstance(item, dict) and item.get("stagione")}
    if not seasons:
        return []
    champions_by_season = {n: s.get("campione") for n, s in seasons.items()}
    titles = Counter()
    out = []
    for number in range(1, max(seasons) + 1):
        item = seasons.get(number)
        if item is None:
            nearest = min(seasons, key=lambda n: abs(n - number))
            year = seasons[nearest].get("anno")
            out.append({"season": number, "year": year + (number - nearest) if year else None, "missing": True})
            continue
        titles[item.get("campione")] += 1
        out.append(_season_entry(item, titles[item.get("campione")], champions_by_season, user_team))
    return out[::-1]


def _career_facts(seasons, user_team):
    seasons = [s for s in seasons or [] if isinstance(s, dict)]
    positions = Counter(s.get("ruolo") for s in seasons if s.get("ruolo"))
    teams = Counter(s.get("squadra") for s in seasons if s.get("squadra"))
    return {"position": positions.most_common(1)[0][0] if positions else None,
            "main_team": teams.most_common(1)[0][0] if teams else None,
            "played_for_user": bool(user_team) and user_team in teams}


def _inductee(raw, class_season, careers, user_team):
    highlights = raw.get("highlights")
    detailed = isinstance(highlights, dict)
    accolades = (highlights.get("accolades") or {}) if detailed else {}
    stats = highlights.get("stats") if detailed else None
    player = {
        "id": raw.get("id"),
        "name": raw.get("nome"),
        "score": int(round(raw.get("score") or 0)),
        "class_season": class_season,
        "accolades": {key: int(accolades.get(saved) or 0) for key, saved in ACCOLADE_KEYS.items()},
        "stats": {"ppg": stats.get("career_ppg"), "rpg": stats.get("career_rpg"), "apg": stats.get("career_apg"),
                  "peak_ppg": stats.get("peak_ppg")} if stats else None,
    }
    player.update(_career_facts(careers.get(raw.get("id")), user_team))
    return player


def hall_of_fame_view(classes, careers, user_team):
    """Inductees at or above CONFIG.HISTORY.HOF_MIN_SCORE, ranked by score: top three on the podium, the rest in tiers."""
    cfg = CONFIG.HISTORY
    careers = careers or {}
    everyone = [_inductee(raw, c.get("stagione_elezione"), careers, user_team)
                for c in classes or [] for raw in c.get("inductees") or []]
    shown = [p for p in everyone if p["score"] >= cfg.HOF_MIN_SCORE]
    shown.sort(key=lambda p: (-p["score"], -p["accolades"]["titles"], p["name"] or ""))
    for rank, player in enumerate(shown, start=1):
        player["rank"] = rank

    tiers = [{"name": name, "min_score": minimum, "players": []} for name, minimum in cfg.HOF_TIERS]
    for player in shown[3:]:
        tier = next((t for t in tiers if player["score"] >= t["min_score"]), tiers[-1] if tiers else None)
        if tier is not None:
            tier["players"].append(player)

    latest = max((p["class_season"] for p in shown if p["class_season"] is not None), default=None)
    return {
        "total_inductees": len(everyone),
        "shown": len(shown),
        "min_score": cfg.HOF_MIN_SCORE,
        "latest_class": None if latest is None else {
            "season": latest, "names": [p["name"] for p in shown if p["class_season"] == latest]},
        "podium": shown[:3],
        "tiers": tiers,
    }
