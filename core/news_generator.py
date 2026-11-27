# news_generator.py
"""League news: a store of structured facts (kind, game day, tier, teams, players, details).

`add_news` keeps its old positional signature, so every legacy caller still works: the kind is inferred from
the legacy category and the tier from `is_breaking`. Callers that know more pass kind/tier/players/details.
Tiers: 3 = big, 2 = medium, 1 = minor (CONFIG.NEWS). Design: docs/superpowers/specs/2026-11-15-news-rebuild-design.md
"""
import random
import re
from typing import Any, Dict, List, Optional

from core.config import CONFIG

# Global news storage (newest first)
NEWS_FEED: List[Dict[str, Any]] = []
NEWS_ID_COUNTER = 0
LAST_SEEN_ID = 0

# Game clock stamped on every item. The server registers a provider that reads the running league; without one
# (scripts, tests) the values of set_clock are used.
_CLOCK: Dict[str, Any] = {"season": None, "day": None, "date": "", "phase": ""}
_CLOCK_PROVIDER = None

KINDS = ("trade", "injury", "signing", "cut", "extension", "free_agency", "draft", "performance", "playoffs", "champion",
         "firing", "hiring", "rumor", "award", "standings", "rivalry", "league")
_META_KEY = "_news_meta"
_LEADING_JUNK = re.compile(r"^[^\w#(\"']+", re.UNICODE)


def set_clock(season: Optional[int] = None, day: Optional[int] = None, date: str = "", phase: str = "") -> None:
    """Sets the game moment for the next news items. `day` is the 0-based calendar day (None outside the
    regular season), `date` its ISO date, `phase` a short label such as 'Playoffs' or 'Offseason'."""
    _CLOCK.update({"season": season, "day": day, "date": date or "", "phase": phase or ""})


def set_clock_provider(provider) -> None:
    """Registers a function returning {"season", "day", "date", "phase"} for the current game moment."""
    global _CLOCK_PROVIDER
    _CLOCK_PROVIDER = provider


def get_clock() -> Dict[str, Any]:
    if _CLOCK_PROVIDER is not None:
        try:
            now = _CLOCK_PROVIDER()
            if now:
                return {"season": now.get("season"), "day": now.get("day"), "date": now.get("date") or "",
                        "phase": now.get("phase") or ""}
        except Exception:
            pass
    return dict(_CLOCK)


def _clean_title(title: str) -> str:
    return _LEADING_JUNK.sub("", title or "").strip()


def _infer_kind(category: str, title: str) -> str:
    cat = (category or "").lower()
    up = (title or "").upper()
    if cat == "trades":
        return "trade"
    if cat == "injuries":
        return "injury"
    if cat == "signings":
        if "CUT" in up or "WAIVE" in up:
            return "cut"
        if any(word in up for word in ("NOT RE-SIGN", "REFUSE", " LET ", "FREE AGENCY")):
            return "free_agency"
        if "EXTEN" in up or "RE-SIGN" in up or "RENEW" in up:
            return "extension"
        return "signing"
    if cat in ("draft", "playoffs", "rivalry", "rumor"):
        return cat
    if cat == "power_rankings":
        return "standings"
    if "CHAMPION" in up:
        return "champion"
    if any(word in up for word in ("FIRED", "FIRE ", "DISMISS", "RESIGN")):
        return "firing"
    if any(word in up for word in ("HIRE", "NEW COACH", "NEW HEAD COACH", "NEW GM", "APPOINT")):
        return "hiring"
    if any(word in up for word in ("PLAYOFF", "SWEEP", "GAME 7", "UPSET", "COMEBACK", "COME BACK", "ADVANCE")):
        return "playoffs"
    if any(word in up for word in ("MVP", "AWARD", "ROOKIE OF", "OF THE YEAR", "ALL-STAR", "HALL OF FAME")):
        return "award"
    if "CONFERENCE" in up or "RANKING" in up:
        return "standings"
    if cat == "highlights":
        return "performance"
    return "league"


def _default_tier(kind: str, is_breaking: bool) -> int:
    if kind in ("champion", "firing"):
        return 3
    return 2 if is_breaking else 1


def add_news(category, title, excerpt, teams=None, is_breaking=False, season=None, *, kind=None, tier=None,
             players=None, details=None):
    """Adds a news item. Legacy callers pass category/title/excerpt; structured callers add kind, tier,
    players (names) and details (free dict shown when the story is opened)."""
    global NEWS_ID_COUNTER

    NEWS_ID_COUNTER += 1
    now = get_clock()
    title = _clean_title(title)
    kind = kind if kind in KINDS else _infer_kind(category, title)
    tier = int(tier) if tier else _default_tier(kind, bool(is_breaking))
    item = {
        "id": NEWS_ID_COUNTER,
        "kind": kind,
        "tier": max(1, min(3, tier)),
        "title": title,
        "body": excerpt or "",
        "teams": [t for t in (teams or []) if t],
        "players": [p for p in (players or []) if p],
        "season": season if season is not None else (now["season"] or 1),
        "day": now["day"],
        "date": now["date"],
        "phase": now["phase"],
        "details": details or {},
        "category": category,
    }
    NEWS_FEED.insert(0, item)
    limit = CONFIG.NEWS.MAX_ITEMS
    if len(NEWS_FEED) > limit:
        del NEWS_FEED[limit:]
    return item


def get_news_feed():
    """The current news feed, newest first."""
    return NEWS_FEED


def get_last_seen_id() -> int:
    return LAST_SEEN_ID


def mark_all_seen() -> int:
    """The user opened the news: everything up to the newest item counts as read."""
    global LAST_SEEN_ID
    LAST_SEEN_ID = NEWS_ID_COUNTER
    return LAST_SEEN_ID


def view_item(item: Dict[str, Any], user_team: Optional[str] = None) -> Dict[str, Any]:
    """Copy of an item as the UI shows it: `mine` and the tier raised for the user's team, `unread`."""
    shown = dict(item)
    mine = bool(user_team) and user_team in item.get("teams", [])
    shown["mine"] = mine
    if mine:
        shown["tier"] = min(3, item.get("tier", 1) + CONFIG.NEWS.USER_TEAM_TIER_BONUS)
    shown["unread"] = item.get("id", 0) > LAST_SEEN_ID
    return shown


def unread_big_count(user_team: Optional[str] = None) -> int:
    """How many big stories (after the user-team raise) the user has not seen yet."""
    count = 0
    for item in NEWS_FEED:
        if item.get("id", 0) <= LAST_SEEN_ID:
            break  # newest first: everything after this is read
        if view_item(item, user_team)["tier"] >= 3:
            count += 1
    return count


def export_raw_news() -> list:
    """The feed for the save file, plus one meta entry (last seen id)."""
    return list(NEWS_FEED) + [{_META_KEY: True, "last_seen_id": LAST_SEEN_ID}]


def _normalize_loaded(item: Dict[str, Any]) -> Dict[str, Any]:
    """Brings an item of any older format to the current one (old saves hold social posts)."""
    title = _clean_title(item.get("title", ""))
    category = item.get("category", "general")
    kind = item.get("kind") if item.get("kind") in KINDS else _infer_kind(category, title)
    return {
        "id": item.get("id", 0),
        "kind": kind,
        "tier": int(item.get("tier") or _default_tier(kind, bool(item.get("is_breaking")))),
        "title": title,
        "body": item.get("body", item.get("excerpt", "")) or "",
        "teams": list(item.get("teams") or []),
        "players": list(item.get("players") or []),
        "season": item.get("season", 1),
        "day": item.get("day"),
        "date": item.get("date", ""),
        "phase": item.get("phase", ""),
        "details": item.get("details") or {},
        "category": category,
    }


def import_raw_news(news_data: list):
    """Restores the feed from a save (any older format)."""
    global NEWS_ID_COUNTER, LAST_SEEN_ID
    NEWS_FEED.clear()  # in place: other modules hold a reference to the list
    NEWS_ID_COUNTER = 0
    LAST_SEEN_ID = 0
    if not isinstance(news_data, list):
        return
    meta = None
    for item in news_data:
        if not isinstance(item, dict):
            continue
        if item.get(_META_KEY):
            meta = item
        elif str(item.get("category")) != "user":  # posts the user wrote in the old social feed
            NEWS_FEED.append(_normalize_loaded(item))
    NEWS_ID_COUNTER = max([item["id"] for item in NEWS_FEED], default=0)
    # A save from before the rebuild has no meta: its news all count as read.
    LAST_SEEN_ID = int(meta.get("last_seen_id", 0)) if meta else NEWS_ID_COUNTER


def reset_news() -> None:
    """Empties the feed (new career)."""
    global NEWS_ID_COUNTER, LAST_SEEN_ID
    NEWS_FEED.clear()
    NEWS_ID_COUNTER = 0
    LAST_SEEN_ID = 0
    set_clock()


# --- Tier rules (CONFIG.NEWS) ---

def trade_tier(best_ovr: Optional[int]) -> int:
    cfg = CONFIG.NEWS
    if best_ovr is None:
        return 2
    return 3 if best_ovr >= cfg.TRADE_BIG_OVR else 2 if best_ovr >= cfg.TRADE_MEDIUM_OVR else 1


def injury_tier(days: int, ovr: Optional[int]) -> int:
    cfg = CONFIG.NEWS
    star = ovr is not None and ovr >= cfg.INJURY_STAR_OVR
    long_out = days >= cfg.INJURY_LONG_DAYS
    return 3 if star and long_out else 2 if star or long_out else 1


def firing_tier(coach_name: str) -> int:
    """A head coach fired is a medium story (big for the user's team, raised when read); an interim is minor."""
    return 1 if (coach_name or "").lower().startswith("interim") else 2


def _weeks(days: int) -> str:
    if days < 14:
        return f"{days} days"
    weeks = round(days / 7)
    return f"about {weeks} weeks" if weeks < 9 else f"about {round(days / 30)} months"


# --- News generation ---

def generate_game_performance_news(player_stats, player_name, team_name, opponent_name, season=None):
    """News for the rare single-game performances only."""
    cfg = CONFIG.NEWS
    pts = player_stats.punti
    reb = player_stats.rimbalzi
    ast = player_stats.assist
    stl = getattr(player_stats, 'steals', 0)
    blk = getattr(player_stats, 'blocks', 0)
    line = f"{pts} points, {reb} rebounds, {ast} assists"
    common = dict(teams=[team_name, opponent_name], season=season, kind="performance", players=[player_name],
                  details={"line": {"pts": pts, "reb": reb, "ast": ast, "stl": stl, "blk": blk},
                           "opponent": opponent_name})

    if pts >= cfg.PERF_POINTS:
        add_news("highlights", f"{player_name} scores {pts} against the {opponent_name}",
                 f"{line} for the {team_name}.", tier=3 if pts >= cfg.PERF_BIG_POINTS else 2, **common)
        return True
    if pts >= 10 and reb >= 10 and ast >= 5 and stl >= 5 and blk >= 5:
        add_news("highlights", f"{player_name} records a five-by-five",
                 f"{line}, {stl} steals, {blk} blocks against the {opponent_name}.", tier=2, **common)
        return True
    if pts >= 20 and reb >= 15 and ast >= 15:
        add_news("highlights", f"{player_name} posts a {pts}-{reb}-{ast} triple-double",
                 f"Against the {opponent_name}, for the {team_name}.", tier=2, **common)
        return True
    return False


def generate_injury_news(player_name, team_name, injury_days, is_serious=False, season=None, ovr=None):
    """News for an injury that keeps a player out at least CONFIG.NEWS.INJURY_MIN_DAYS calendar days."""
    if injury_days < CONFIG.NEWS.INJURY_MIN_DAYS:
        return
    # The same injury is not told twice (the caller's memory of it is lost when a save is reloaded).
    now = get_clock()
    for item in NEWS_FEED:
        if (item["kind"] == "injury" and player_name in item["players"] and item["season"] == now["season"]
                and item["day"] is not None and now["day"] is not None
                and now["day"] < item["day"] + int(item["details"].get("days") or 0)):
            return
    add_news("injuries", f"{player_name} out {_weeks(injury_days)}",
             f"The {team_name} lose {player_name} for {injury_days} days.",
             teams=[team_name], season=season, kind="injury", tier=injury_tier(injury_days, ovr),
             players=[player_name], details={"days": injury_days, "ovr": ovr})


def generate_regular_season_news(east_teams, west_teams, mvp=None, season=None):
    """Conference leaders (and the MVP when known) at the All-Star break and at the end of the season."""
    for conference, ranked in (("East", east_teams), ("West", west_teams)):
        if ranked:
            top = ranked[0]
            add_news("highlights", f"{top.nome} lead the {conference}",
                     f"{top.vittorie}-{top.sconfitte}, the best record in the conference.",
                     teams=[top.nome], season=season, kind="standings", tier=1)
    if mvp:
        team = mvp.squadra.nome if getattr(mvp, 'squadra', None) else ""
        add_news("highlights", f"{mvp.nome} is the regular season MVP", f"The {team} star takes the award.",
                 teams=[team], season=season, kind="award", tier=3, players=[mvp.nome])


def generate_draft_news(picks, season=None):
    """The first three picks of the draft."""
    for i, pick in enumerate((picks or [])[:3]):
        read = pick.get if isinstance(pick, dict) else (lambda key, default=None, p=pick: getattr(p, key, default))
        nome, squadra = read('nome', 'Unknown'), read('squadra', '')
        ovr = read('ovr', None) or read('valutazione', '?')
        pot = read('pot', None) or read('potenziale', '?')
        add_news("draft", f"{squadra} select {nome} with the No. {i + 1} pick",
                 f"Overall {ovr}, potential {pot}.",
                 teams=[squadra], season=season, kind="draft", tier=3 if i == 0 else 2, players=[nome],
                 details={"pick": i + 1})


def generate_signing_news(player_name, team_name, contract_info=None, is_star=False, season=None, ovr=None):
    """A free agent signing. Big when the caller knows the OVR and it is high, else medium for a star."""
    if ovr is not None and ovr >= CONFIG.NEWS.SIGNING_BIG_OVR:
        tier = 3
    else:
        tier = 2 if is_star else 1
    body = f"{player_name} signs with the {team_name}."
    if contract_info:
        body += f" Contract: {contract_info}."
    add_news("signings", f"{player_name} signs with the {team_name}", body, teams=[team_name], season=season,
             kind="signing", tier=tier, players=[player_name], details={"contract": contract_info or ""})


def generate_trade_news(trade_description, teams_involved, season=None):
    """A trade described in one line (the user's own trades); CPU trades go through trades/execution.py."""
    teams = list(teams_involved or [])
    title = f"{teams[0]} and {teams[1]} complete a trade" if len(teams) >= 2 else "Trade completed"
    add_news("trades", title, trade_description, teams=teams, season=season, kind="trade", tier=2)


def generate_rivalry_postgame_news(winner, loser, winner_score, loser_score, rivalry_context, season=None):
    """A thriller or a blowout between two heated rivals."""
    if not rivalry_context.get('has_rivalry') or rivalry_context.get('level', 'mild') not in ('legendary', 'heated'):
        return
    margin = winner_score - loser_score
    if margin <= 5:
        title = f"{winner} edge rival {loser} {winner_score}-{loser_score}"
    elif margin >= 25:
        title = f"{winner} rout rival {loser} {winner_score}-{loser_score}"
    else:
        return
    pair = {winner, loser}
    told = sum(1 for item in NEWS_FEED if item["kind"] == "rivalry" and item["season"] == season
               and set(item["teams"]) == pair)
    if told >= CONFIG.NEWS.RIVALRY_MAX_PER_PAIR_SEASON:
        return
    add_news("rivalry", title, "Another chapter in a heated rivalry.", teams=[winner, loser], season=season,
             kind="rivalry", tier=1)


def generate_front_office_news(event: str, team: str, role: str, name: str, detail: str = "", season=None):
    """A head coach or GM fired, hired or retired in the offseason. event: 'fired' | 'hired' | 'retired';
    role: 'coach' | 'GM'. Firings and hirings are medium stories, retirements minor."""
    label = "head coach" if role == "coach" else "GM"
    if event == "fired":
        title, kind, tier = f"{team} fire {label} {name}", "firing", firing_tier(name)
    elif event == "hired":
        title, kind, tier = f"{team} hire {name} as {label}", "hiring", 2
    else:
        title, kind, tier = f"{label[0].upper() + label[1:]} {name} retires", "league", 1
    add_news("general", title, detail or title + ".", teams=[team] if team else [], season=season, kind=kind,
             tier=tier, details={"role": role, "event": event})


def generate_playoff_elimination_news(winner, loser, series_score, round_name, season=None):
    """A playoff series ending, when only the final score is known."""
    won, lost = max(series_score), min(series_score)
    finals = 'finals' in round_name.lower() and 'conference' not in round_name.lower()
    if finals:
        add_news("playoffs", f"{winner} are champions", f"They beat the {loser} {won}-{lost} in the Finals.",
                 teams=[winner, loser], season=season, kind="champion", tier=3)
        return
    add_news("playoffs", f"{winner} eliminate {loser} {won}-{lost}", f"Series over in the {round_name}.",
             teams=[winner, loser], season=season, kind="playoffs", tier=3 if lost == 3 else 2)


def generate_power_rankings_news(teams_ranked, week_number, season=None):
    """The five best records in the league."""
    if not teams_ranked or len(teams_ranked) < 5:
        return
    top5 = teams_ranked[:5]
    add_news("power_rankings", "The league's top five",
             " · ".join(f"{i + 1}. {t['name']} ({t.get('record', '')})" for i, t in enumerate(top5)),
             teams=[top5[0]['name']], season=season, kind="standings", tier=1)


def generate_trade_deadline_news(days_remaining, notable_players=None, season=None):
    """The trade deadline is one week away."""
    if days_remaining == 7:
        add_news("trades", "Trade deadline one week away", "Front offices have seven days left to make a deal.",
                 season=season, kind="league", tier=1)


def generate_rumor_news(torneo, rng=random) -> int:
    """Leaks about unhappy players: low morale and enough OVR, CONFIG.NEWS.RUMOR_CHANCE each, one rumor per
    player per season and one candidate per team at each check. Returns how many rumors were published."""
    cfg = CONFIG.NEWS
    season = getattr(torneo, 'season_number', 1)
    already = {name for item in NEWS_FEED if item["kind"] == "rumor" and item["season"] == season
               for name in item["players"]}
    published = 0
    for squadra in getattr(torneo, 'squadre', []):
        # One story per team at a time: its best unhappy player is the one reporters talk about.
        unhappy = [p for p in squadra.roster
                   if getattr(p, 'ovr', 0) >= cfg.RUMOR_MIN_OVR and getattr(p, 'morale', 75) <= cfg.RUMOR_MORALE_MAX
                   and p.nome not in already]
        for player in sorted(unhappy, key=lambda p: p.ovr, reverse=True)[:1]:
            ovr = player.ovr
            morale = getattr(player, 'morale', 75)
            if rng.random() >= cfg.RUMOR_CHANCE:
                continue
            years_left = getattr(getattr(player, 'contract', None), 'anni_rimanenti', None)
            record = f"{squadra.vittorie}-{squadra.sconfitte}"
            if years_left is not None and years_left <= 1:
                body = (f"Sources say {player.nome} is frustrated with the {squadra.nome} ({record}). "
                        f"He is in the last year of his contract and could leave in free agency.")
            else:
                body = (f"Sources say {player.nome} is frustrated with the {squadra.nome} ({record}) "
                        f"and may ask for a trade.")
            add_news("rumor", f"{player.nome} unhappy with the {squadra.nome}", body, teams=[squadra.nome],
                     season=season, kind="rumor", tier=3 if ovr >= cfg.RUMOR_BIG_OVR else 2,
                     players=[player.nome], details={"morale": morale, "contract_year": bool(
                         years_left is not None and years_left <= 1)})
            already.add(player.nome)
            published += 1
    return published
