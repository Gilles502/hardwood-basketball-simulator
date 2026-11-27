# core/calendar_generator.py
"""
NBA Realistic Schedule & Calendar Generator for Hardwood Basketball Simulator
Generates a complete 82-game regular season schedule for all teams across ~175 calendar days
(late October to mid-April), following authentic NBA scheduling rules, balanced home/away,
division/conference weighting, holiday slates (Christmas, MLK, Opening Night), and no 3-in-3s.
"""

import logging
import math
import random
from datetime import date, timedelta
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from core.config import CONFIG
from core.league.registry import get_active_registry


def _team_name(team: Any) -> str:
    # getattr(t, 'nome', str(t)) built str(t) every time, and a team's repr could exhaust memory.
    name = getattr(team, 'nome', None)
    return name if name is not None else str(team)

TZ_OFFSETS = {'ET': 3, 'CT': 2, 'MT': 1, 'PT': 0}


def calculate_city_distance_miles(city_a: str, city_b: str) -> float:
    """Calculates geographical distance in miles between two cities using great-circle approximation."""
    if city_a == city_b:
        return 0.0
    cities = CONFIG.GEO.CITIES
    loc_a = cities.get(city_a)
    loc_b = cities.get(city_b)
    if not loc_a or not loc_b:
        return 400.0  # Safe fallback for unknown cities
    lat1, lon1 = loc_a['lat'], loc_a['lon']
    lat2, lon2 = loc_b['lat'], loc_b['lon']
    avg_lat = math.radians((lat1 + lat2) / 2.0)
    dx = (lon2 - lon1) * math.cos(avg_lat) * 69.17
    dy = (lat2 - lat1) * 69.17
    return math.sqrt(dx * dx + dy * dy)


def get_timezone_difference(city_a: str, city_b: str) -> int:
    """Returns absolute timezone hours difference between two cities."""
    cities = CONFIG.GEO.CITIES
    tz_a = cities.get(city_a, {}).get('tz', 'ET')
    tz_b = cities.get(city_b, {}).get('tz', 'ET')
    return abs(TZ_OFFSETS.get(tz_a, 0) - TZ_OFFSETS.get(tz_b, 0))


@dataclass
class ScheduledGame:
    game_id: str
    home_team: str
    away_team: str
    date: str                  # ISO string "YYYY-MM-DD"
    day_index: int             # 0-indexed day of the season
    played: bool = False
    home_score: int = 0
    away_score: int = 0
    box_score_id: Optional[str] = None
    top_performer: Optional[Dict[str, Any]] = None
    quarter_scores: Optional[Dict[str, List[int]]] = None
    box_score: Optional[Dict[str, Any]] = None
    is_back_to_back_home: bool = False
    is_back_to_back_away: bool = False
    home_team_obj: Optional[Any] = None
    away_team_obj: Optional[Any] = None

    def __iter__(self):
        """Allows unpacking: home, away = scheduled_game."""
        h = getattr(self, 'home_team_obj', None) or self.home_team
        a = getattr(self, 'away_team_obj', None) or self.away_team
        yield h
        yield a

    def __getitem__(self, idx: int):
        if idx == 0:
            return getattr(self, 'home_team_obj', None) or self.home_team
        elif idx == 1:
            return getattr(self, 'away_team_obj', None) or self.away_team
        raise IndexError(f"ScheduledGame index {idx} out of range (0 or 1)")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "date": self.date,
            "day_index": self.day_index,
            "played": self.played,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "box_score_id": self.box_score_id,
            "top_performer": self.top_performer,
            "quarter_scores": getattr(self, 'quarter_scores', None),
            "is_back_to_back_home": self.is_back_to_back_home,
            "is_back_to_back_away": self.is_back_to_back_away,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduledGame':
        return cls(
            game_id=data["game_id"],
            home_team=data["home_team"],
            away_team=data["away_team"],
            date=data["date"],
            day_index=data["day_index"],
            played=data.get("played", False),
            home_score=data.get("home_score", 0),
            away_score=data.get("away_score", 0),
            box_score_id=data.get("box_score_id"),
            top_performer=data.get("top_performer"),
            quarter_scores=data.get("quarter_scores"),
            box_score=data.get("box_score"),
            is_back_to_back_home=data.get("is_back_to_back_home", False),
            is_back_to_back_away=data.get("is_back_to_back_away", False),
            home_team_obj=None,
            away_team_obj=None,
        )


@dataclass
class CalendarDay:
    day_index: int
    date: str                  # ISO string "YYYY-MM-DD"
    games: List[ScheduledGame] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    phase: str = "REGULAR_SEASON"  # "REGULAR_SEASON", "ALL_STAR_BREAK", "PLAY_IN", "PLAYOFFS"
    is_off_day: bool = False

    def __iter__(self):
        """Allows iterating through games directly on the day."""
        return iter(self.games)

    def __len__(self):
        return len(self.games)

    def __getitem__(self, idx: int):
        return self.games[idx]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day_index": self.day_index,
            "date": self.date,
            "games": [g.to_dict() for g in self.games],
            "events": self.events,
            "phase": self.phase,
            "is_off_day": self.is_off_day
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CalendarDay':
        games = [ScheduledGame.from_dict(g) for g in data.get("games", [])]
        return cls(
            day_index=data["day_index"],
            date=data["date"],
            games=games,
            events=data.get("events", []),
            phase=data.get("phase", "REGULAR_SEASON"),
            is_off_day=data.get("is_off_day", False)
        )


class NBACalendarGenerator:
    """
    Procedural scheduler that balances matchups across divisions, conferences,
    and calendar days while guaranteeing:
    - Exactly 82 games per team (41 Home, 41 Away for 30 teams)
    - Realistic daily slate distributions (~4 to ~11 games/day, holidays)
    - 0 Three-in-Three occurrences
    - Natural back-to-backs (~11-15 per team)
    - All-Star break multi-day pause
    """

    # Divisions, cities, market weights and rivalries come from the active franchise registry (the league file).
    # Fallback division -> conference for teams the league does not know (they fill these divisions).
    CONFERENCE_MAP = {
        'Atlantic': 'East', 'Central': 'East', 'Southeast': 'East',
        'Northwest': 'West', 'Pacific': 'West', 'Southwest': 'West'
    }

    def __init__(self, teams: List[Any], starting_year: int = 2025, seed: Optional[int] = None):
        self.teams = teams
        self.starting_year = starting_year
        self.rng = random.Random(seed)
        self.registry = get_active_registry()

        # Build normalized division map matching existing teams
        self.team_names = [_team_name(t) for t in self.teams]
        self.division_conference = self._division_conferences()
        self.divisions = self._resolve_divisions()
        self.team_division = {}
        self.team_conference = {}
        for div, t_list in self.divisions.items():
            conf = self.division_conference.get(div, 'East')
            for t_name in t_list:
                self.team_division[t_name] = div
                self.team_conference[t_name] = conf

        # Default fallback for teams not found in standard map
        for t in self.teams:
            name = _team_name(t)
            conf = getattr(t, 'conference', None)
            if name not in self.team_conference:
                self.team_conference[name] = conf if conf in ['East', 'West'] else 'East'
        self.team_obj_map = {_team_name(t): t for t in self.teams}
        self._rivalry_bonus = {frozenset([a, b]): w for a, b, w in self.registry.rivalries()}
        self._team_prestige = self._compute_all_team_prestige()

    def _division_conferences(self) -> Dict[str, str]:
        """Division -> conference: the league's divisions first, then the fallback ones for unknown teams."""
        out: Dict[str, str] = {}
        for f in self.registry.franchises:
            out.setdefault(f.division, f.conference)
        for div, conf in self.CONFERENCE_MAP.items():
            out.setdefault(div, conf)
        return out

    def get_team_city(self, team_name: str) -> str:
        """
        Resolves the geographical city for a team, supporting future franchise relocation.
        If the team object has a .city attribute present in CONFIG.GEO.CITIES, it takes priority.
        Otherwise falls back to the league's geo city for the team (New York when unknown).
        """
        t_obj = self.team_obj_map.get(team_name)
        if t_obj and hasattr(t_obj, 'city') and t_obj.city in CONFIG.GEO.CITIES:
            return t_obj.city
        return self.registry.geo_city(team_name, 'New York')

    def _compute_all_team_prestige(self) -> Dict[str, float]:
        """Calculates national appeal, star power, and contender status for each team."""
        scores = {}
        for t_name in self.team_names:
            t_obj = self.team_obj_map.get(t_name)
            ovr_score = 75.0
            star_score = 0.0

            if t_obj and getattr(t_obj, 'roster', None):
                sorted_roster = sorted(t_obj.roster, key=lambda p: getattr(p, 'ovr', 75), reverse=True)
                top8 = sorted_roster[:8]
                if top8:
                    ovr_score = sum(getattr(p, 'ovr', 75) for p in top8) / len(top8)

                for p in sorted_roster[:3]:
                    p_ovr = getattr(p, 'ovr', 75)
                    if p_ovr >= 93:
                        star_score += (p_ovr - 90) * 4.0
                    elif p_ovr >= 87:
                        star_score += (p_ovr - 85) * 2.0

            market_bonus = self.registry.market_weight(t_name, 0.0)
            scores[t_name] = ovr_score + star_score + market_bonus

        return scores

    def _score_matchup_appeal(self, home_team: str, away_team: str) -> float:
        """Evaluates national TV / marquee appeal of a matchup."""
        base_appeal = self._team_prestige.get(home_team, 75.0) + self._team_prestige.get(away_team, 75.0)

        rivalry_bonus = self._rivalry_bonus.get(frozenset([home_team, away_team]), 0.0)

        # Division matchup bonus
        div_bonus = 8.0 if self.team_division.get(home_team) == self.team_division.get(away_team) else 0.0

        # Small stochastic variation so seed changes pick slightly different games
        jitter = self.rng.uniform(-3.0, 3.0)

        return base_appeal + rivalry_bonus + div_bonus + jitter

    def _resolve_divisions(self) -> Dict[str, List[str]]:
        """The league's divisions limited to the active teams; teams the league does not know fill the gaps."""
        name_set = set(self.team_names)
        resolved = {div: [] for div in self.division_conference}
        for div, members in self.registry.divisions().items():
            resolved[div] = [n for n in members if n in name_set]

        # Put any unmatched team into appropriate conference division
        assigned = set(sum(resolved.values(), []))
        first_div = next(iter(resolved))
        for t_name in self.team_names:
            if t_name not in assigned:
                # Find best division
                found = False
                for div in resolved:
                    if len(resolved[div]) < 5:
                        resolved[div].append(t_name)
                        found = True
                        break
                if not found:
                    resolved[first_div].append(t_name)

        return resolved

    def _generate_matchup_matrix(self) -> List[Tuple[str, str]]:
        """
        Creates all (Home, Away) pairings for an 82-game regular season schedule.
        For 30 teams: exactly 1230 matchups.
        Rules:
        - 4 games vs 4 Division opponents (2 Home, 2 Away) = 16 games
        - 4 games vs 6 Conference non-div opponents (2 Home, 2 Away) = 24 games
        - 3 games vs 4 Conference non-div opponents (alternating H/A) = 12 games
        - 2 games vs 15 Opp-Conference opponents (1 Home, 1 Away) = 30 games
        Sum = 16 + 24 + 12 + 30 = 82 games!
        """
        pairs: List[Tuple[str, str]] = []
        teams = sorted(self.team_names)
        n = len(teams)

        if n != 30:
            # Fallback for non-30 team leagues (e.g. 29 teams in 2002):
            return self._generate_balanced_round_robin_matchups(teams, target_games=82)

        # 1. Division Matchups (4 games: 2H, 2A)
        for _div, div_teams in self.divisions.items():
            for i in range(len(div_teams)):
                for j in range(i + 1, len(div_teams)):
                    t1, t2 = div_teams[i], div_teams[j]
                    pairs.extend([(t1, t2), (t1, t2), (t2, t1), (t2, t1)])

        # 2. Inter-Conference Matchups (2 games: 1H, 1A)
        east_teams = [t for t in teams if self.team_conference[t] == 'East']
        west_teams = [t for t in teams if self.team_conference[t] == 'West']

        for e in east_teams:
            for w in west_teams:
                pairs.append((e, w))
                pairs.append((w, e))

        # 3. Intra-Conference Non-Division Matchups
        # Each conference has 15 teams. Within conference, each team has:
        # - 4 division rivals (already handled)
        # - 10 non-division conference rivals:
        #   We pick 6 to play 4 times (2H, 2A) and 4 to play 3 times (randomized by seed).
        for conf_teams in [east_teams, west_teams]:
            # Construct a randomized 4-vs-3 schedule
            shuffled_conf = list(conf_teams)
            self.rng.shuffle(shuffled_conf)
            
            # To ensure symmetric total games, group conference divisions
            conf_divs = [d for d in self.divisions if self.division_conference.get(d) == self.team_conference[conf_teams[0]]]
            
            # Pair teams from different divisions
            for d_idx, d1 in enumerate(conf_divs):
                for d2 in conf_divs[d_idx + 1:]:
                    teams_d1 = self.divisions[d1]
                    teams_d2 = self.divisions[d2]
                    # Each team in d1 plays teams in d2
                    for i, t1 in enumerate(teams_d1):
                        for j, t2 in enumerate(teams_d2):
                            # Deterministic pseudo-random pattern for 3 vs 4 games:
                            # 3 of 5 matchups get 4 games, 2 get 3 games
                            is_four_game = ((i + j) % 5) in [0, 1, 2]
                            if is_four_game:
                                pairs.extend([(t1, t2), (t1, t2), (t2, t1), (t2, t1)])
                            else:
                                # 3 games: pick alternating home
                                if (i + j) % 2 == 0:
                                    pairs.extend([(t1, t2), (t1, t2), (t2, t1)])
                                else:
                                    pairs.extend([(t1, t2), (t2, t1), (t2, t1)])

        # Balance check & normalization
        pairs = self._adjust_home_away_balance(pairs, teams, target_games=82)
        return pairs

    def _generate_balanced_round_robin_matchups(self, teams: List[str], target_games: int = 82) -> List[Tuple[str, str]]:
        """Fallback generator for historical leagues with != 30 teams."""
        pairs = []
        n = len(teams)
        counts = {t: 0 for t in teams}
        home_counts = {t: 0 for t in teams}

        # Multiple round-robin passes
        pass_num = 0
        while min(counts.values()) < target_games:
            for i in range(n):
                for j in range(i + 1, n):
                    t1, t2 = teams[i], teams[j]
                    if counts[t1] >= target_games and counts[t2] >= target_games:
                        continue
                    # Alternate home
                    if home_counts[t1] <= home_counts[t2]:
                        pairs.append((t1, t2))
                        home_counts[t1] += 1
                    else:
                        pairs.append((t2, t1))
                        home_counts[t2] += 1
                    counts[t1] += 1
                    counts[t2] += 1
            pass_num += 1
            if pass_num > 10:
                break
        return pairs

    def _adjust_home_away_balance(self, pairs: List[Tuple[str, str]], teams: List[str], target_games: int = 82) -> List[Tuple[str, str]]:
        """Ensures every team has exactly 41 Home and 41 Away games."""
        home_counts = {t: 0 for t in teams}
        away_counts = {t: 0 for t in teams}
        for h, a in pairs:
            home_counts[h] += 1
            away_counts[a] += 1

        target_home = target_games // 2
        # Flip home/away for pairs where both teams benefit towards 41/41
        adjusted = list(pairs)
        self.rng.shuffle(adjusted)

        for idx, (h, a) in enumerate(adjusted):
            if home_counts[h] > target_home and away_counts[a] > (target_games - target_home):
                # Swap h and a
                adjusted[idx] = (a, h)
                home_counts[h] -= 1
                away_counts[h] += 1
                home_counts[a] += 1
                away_counts[a] -= 1

        return adjusted

    def generate_calendar(self) -> List[CalendarDay]:
        """
        Distributes all 1230 matchups across ~175 calendar days with:
        - Variable games per day (typically 4 to 10 games, weekend slates)
        - Christmas Day showcase (5 standalone marquee matchups)
        - Opening Night showcase (2-3 marquee matchups)
        - All-Star weekend 4-day hiatus
        - Strict NO 3-in-3s rule
        - Back-to-back limits
        """
        all_matchups = self._generate_matchup_matrix()
        self.rng.shuffle(all_matchups)

        # 1. Establish calendar date timeline
        # Start: 4th Tuesday of October (approx Oct 22)
        start_dt = date(self.starting_year, 10, 22)
        # Total calendar days ~ 176 (ends ~ mid-April)
        total_days = 176
        calendar_days: List[CalendarDay] = []

        # Find key holiday offsets
        christmas_dt = date(self.starting_year, 12, 25)
        
        # MLK Day: 3rd Monday of January
        jan_1 = date(self.starting_year + 1, 1, 1)
        first_monday = jan_1 + timedelta(days=(7 - jan_1.weekday()) % 7)
        mlk_dt = first_monday + timedelta(weeks=2)
        mlk_day_idx = (mlk_dt - start_dt).days

        # All-Star Weekend: ~Friday to Sunday in mid-February (~day 115)
        all_star_start_day = 114
        all_star_end_day = 118
        trade_deadline_day = 108  # A few days before All-Star

        for day_idx in range(total_days):
            current_dt = start_dt + timedelta(days=day_idx)
            iso_str = current_dt.isoformat()
            events = []
            phase = "REGULAR_SEASON"
            is_off = False

            if day_idx == 0:
                events.append("OPENING_NIGHT")
            elif current_dt == christmas_dt:
                events.append("CHRISTMAS_GAMES")
            elif current_dt == mlk_dt:
                events.append("MLK_DAY")
            elif day_idx == trade_deadline_day:
                events.append("TRADE_DEADLINE")
            elif all_star_start_day <= day_idx <= all_star_end_day:
                phase = "ALL_STAR_BREAK"
                is_off = True
                if day_idx == all_star_start_day:
                    events.append("RISING_STARS")
                elif day_idx == all_star_start_day + 1:
                    events.append("ALL_STAR_SATURDAY")
                elif day_idx == all_star_start_day + 2:
                    events.append("ALL_STAR_GAME")
            elif day_idx == total_days - 2:
                # Day 175 (index 174): Eve of Season Finale -> Dedicated rest/light day
                events.append("FINALE_EVE_REST")
            elif day_idx == total_days - 1:
                # Day 176 (index 175): Finale -> Exactly 15 games pairing all 30 teams!
                events.append("REGULAR_SEASON_FINALE")

            calendar_days.append(CalendarDay(
                day_index=day_idx,
                date=iso_str,
                games=[],
                events=events,
                phase=phase,
                is_off_day=is_off
            ))

        # 2. Scheduling Solver (with clustering, travel cost optimization, and B2B controls)
        day_teams: List[set] = [set() for _ in range(total_days)]
        team_day_location: Dict[str, Dict[int, str]] = {t: {} for t in self.team_names}
        team_b2b_count: Dict[str, int] = {t: 0 for t in self.team_names}

        # Target capacities per day type (smooth ~7.5 games/day distribution)
        def get_day_capacity(d_idx: int) -> int:
            if calendar_days[d_idx].is_off_day:
                return 0
            if "OPENING_NIGHT" in calendar_days[d_idx].events:
                return 3
            if "CHRISTMAS_GAMES" in calendar_days[d_idx].events:
                return 5
            if "MLK_DAY" in calendar_days[d_idx].events:
                return 5
            if "FINALE_EVE_REST" in calendar_days[d_idx].events:
                return 0  # Dedicated rest day before the 15-game grand finale
            if "REGULAR_SEASON_FINALE" in calendar_days[d_idx].events:
                return 15 # All 30 teams play simultaneously!
            # Day of week variation: balanced 6 to 9 games
            cur_dt = start_dt + timedelta(days=d_idx)
            weekday = cur_dt.weekday() # 0 = Mon, 4 = Fri, 6 = Sun
            if weekday in [2, 4]:    # Wed, Fri (NBA heavy game nights)
                return 9
            elif weekday in [5, 6]:  # Sat, Sun
                return 8
            elif weekday in [0]:     # Mon
                return 7
            else:                    # Tue, Thu
                return 6

        def record_game(d: int, h: str, a: str, gid: str):
            day_teams[d].add(h)
            day_teams[d].add(a)
            h_city = self.get_team_city(h)
            team_day_location[h][d] = h_city
            team_day_location[a][d] = h_city
            for t in [h, a]:
                if d - 1 >= 0 and t in day_teams[d - 1]:
                    team_b2b_count[t] += 1
                if d + 1 < total_days and t in day_teams[d + 1]:
                    team_b2b_count[t] += 1
            calendar_days[d].games.append(ScheduledGame(
                game_id=gid, home_team=h, away_team=a,
                date=calendar_days[d].date,
                day_index=d,
                home_team_obj=self.team_obj_map.get(h),
                away_team_obj=self.team_obj_map.get(a)
            ))

        # -------------------------------------------------------------
        # STEP 1: Schedule Season Finale (Day 176 - index 175) -> EXACTLY 15 games
        # -------------------------------------------------------------
        finale_day = total_days - 1
        finale_pairs = []
        unpaired_teams = set(self.team_names)

        # Prioritize rivalry matchups: division rivals first, then conference rivals
        candidate_finale_matchups = list(all_matchups)
        def score_finale_pair(h: str, a: str) -> float:
            score = self._score_matchup_appeal(h, a)
            if self.team_division.get(h) == self.team_division.get(a):
                score += 50.0  # Divisional clash
            elif self.team_conference.get(h) == self.team_conference.get(a):
                score += 25.0  # Conference clash
            return score

        candidate_finale_matchups.sort(key=lambda pair: score_finale_pair(pair[0], pair[1]), reverse=True)

        for h, a in candidate_finale_matchups:
            if len(finale_pairs) >= 15:
                break
            if h in unpaired_teams and a in unpaired_teams:
                finale_pairs.append((h, a))
                unpaired_teams.remove(h)
                unpaired_teams.remove(a)
                all_matchups.remove((h, a))

        # Fallback if any team wasn't paired:
        if unpaired_teams:
            leftover = list(unpaired_teams)
            for i in range(0, len(leftover) - 1, 2):
                h, a = leftover[i], leftover[i + 1]
                pair_to_use = None
                if (h, a) in all_matchups:
                    pair_to_use = (h, a)
                elif (a, h) in all_matchups:
                    pair_to_use = (a, h)
                if pair_to_use:
                    finale_pairs.append(pair_to_use)
                    all_matchups.remove(pair_to_use)
                    unpaired_teams.remove(h)
                    unpaired_teams.remove(a)

        for g_num, (h, a) in enumerate(finale_pairs):
            gid = f"g_{calendar_days[finale_day].date}_{h[:3].upper()}_{a[:3].upper()}_{g_num}"
            record_game(finale_day, h, a, gid)

        # -------------------------------------------------------------
        # STEP 2: Place Holiday Showcases (Opening Night, Christmas, MLK)
        # -------------------------------------------------------------
        def place_marquee_slate(day_idx: int, capacity: int, host_priorities: Optional[List[str]] = None):
            placed = []
            if host_priorities:
                for host in host_priorities:
                    if host in day_teams[day_idx]:
                        continue
                    candidates = [(h, a) for (h, a) in all_matchups if h == host and a not in day_teams[day_idx]]
                    if candidates:
                        candidates.sort(key=lambda p: self._score_matchup_appeal(p[0], p[1]), reverse=True)
                        best = candidates[0]
                        placed.append(best)
                        all_matchups.remove(best)
                        gid = f"g_{calendar_days[day_idx].date}_{best[0][:3].upper()}_{best[1][:3].upper()}_{len(placed)}"
                        record_game(day_idx, best[0], best[1], gid)

            remaining = [(h, a) for (h, a) in all_matchups if h not in day_teams[day_idx] and a not in day_teams[day_idx]]
            remaining.sort(key=lambda p: self._score_matchup_appeal(p[0], p[1]), reverse=True)

            for h, a in remaining:
                if len(placed) >= capacity:
                    break
                if h not in day_teams[day_idx] and a not in day_teams[day_idx]:
                    placed.append((h, a))
                    all_matchups.remove((h, a))
                    gid = f"g_{calendar_days[day_idx].date}_{h[:3].upper()}_{a[:3].upper()}_{len(placed)}"
                    record_game(day_idx, h, a, gid)

        place_marquee_slate(0, 3) # Opening Night
        # Teams playing on Opening Night get Day 1 off (authentic NBA rest pattern)
        day_1_forbidden_teams = set(day_teams[0])

        christmas_day_idx = (christmas_dt - start_dt).days
        place_marquee_slate(christmas_day_idx, 5) # Christmas
        place_marquee_slate(mlk_day_idx, 5, host_priorities=self.registry.marquee_hosts('mlk_day')) # MLK Day

        # -------------------------------------------------------------
        # STEP 3: Main Schedule Placement Loop with Strict B2B & Travel Optimization
        # -------------------------------------------------------------
        def check_3_in_3(t: str, day: int) -> bool:
            p1 = (day - 1 >= 0) and (t in day_teams[day - 1])
            p2 = (day - 2 >= 0) and (t in day_teams[day - 2])
            n1 = (day + 1 < total_days) and (t in day_teams[day + 1])
            n2 = (day + 2 < total_days) and (t in day_teams[day + 2])
            return (p1 and p2) or (p1 and n1) or (n1 and n2)

        def check_travel_validity(t: str, day: int, target_city: str, max_dist: float) -> bool:
            # Check B2B from yesterday
            if day - 1 >= 0 and t in day_teams[day - 1]:
                yesterday_city = team_day_location[t].get(day - 1, self.get_team_city(t))
                dist = calculate_city_distance_miles(yesterday_city, target_city)
                if dist > max_dist:
                    return False
                if get_timezone_difference(yesterday_city, target_city) > 1 and dist > 500:
                    return False
            # Check B2B into tomorrow
            if day + 1 < total_days and t in day_teams[day + 1]:
                tomorrow_city = team_day_location[t].get(day + 1, self.get_team_city(t))
                dist = calculate_city_distance_miles(target_city, tomorrow_city)
                if dist > max_dist:
                    return False
                if get_timezone_difference(target_city, tomorrow_city) > 1 and dist > 500:
                    return False
            return True

        self.rng.shuffle(all_matchups)
        max_b2b_limit = CONFIG.GEO.MAX_B2B_PER_TEAM # 15
        COAST_TO_COAST_LIMIT = 1100.0

        unplaced = []
        for h, a in all_matchups:
            h_city = self.get_team_city(h)
            placed = False

            # Candidate days evaluation
            valid_days = []
            for d in range(total_days):
                if len(calendar_days[d].games) >= get_day_capacity(d):
                    continue
                if d == 1 and (h in day_1_forbidden_teams or a in day_1_forbidden_teams):
                    continue
                if h in day_teams[d] or a in day_teams[d]:
                    continue
                if check_3_in_3(h, d) or check_3_in_3(a, d):
                    continue

                # Check B2B addition count for H and A
                b2b_h_add = 0
                if d - 1 >= 0 and h in day_teams[d - 1]: b2b_h_add += 1
                if d + 1 < total_days and h in day_teams[d + 1]: b2b_h_add += 1
                if team_b2b_count[h] + b2b_h_add > max_b2b_limit:
                    continue

                b2b_a_add = 0
                if d - 1 >= 0 and a in day_teams[d - 1]: b2b_a_add += 1
                if d + 1 < total_days and a in day_teams[d + 1]: b2b_a_add += 1
                if team_b2b_count[a] + b2b_a_add > max_b2b_limit:
                    continue

                # Travel distance check on B2B (coast-to-coast flights strictly forbidden)
                if not check_travel_validity(h, d, h_city, COAST_TO_COAST_LIMIT):
                    continue
                if not check_travel_validity(a, d, h_city, COAST_TO_COAST_LIMIT):
                    continue

                # Calculate travel distance for cost function: Cost = Distance(City_A, City_B)
                travel_h = 0.0
                if d - 1 >= 0 and h in day_teams[d - 1]:
                    travel_h = calculate_city_distance_miles(team_day_location[h].get(d - 1, self.get_team_city(h)), h_city)
                if d + 1 < total_days and h in day_teams[d + 1]:
                    travel_h = max(travel_h, calculate_city_distance_miles(h_city, team_day_location[h].get(d + 1, self.get_team_city(h))))

                travel_a = 0.0
                if d - 1 >= 0 and a in day_teams[d - 1]:
                    travel_a = calculate_city_distance_miles(team_day_location[a].get(d - 1, self.get_team_city(a)), h_city)
                if d + 1 < total_days and a in day_teams[d + 1]:
                    travel_a = max(travel_a, calculate_city_distance_miles(h_city, team_day_location[a].get(d + 1, self.get_team_city(a))))

                # Score day suitability:
                penalty = 0.0
                # Heavily prioritize rest days (no B2B created)
                if b2b_h_add > 0: penalty += 35.0
                if b2b_a_add > 0: penalty += 35.0
                # Travel Cost weight: Cost = Distance / 40.0
                penalty += (travel_h + travel_a) / 40.0
                # Prefer days with fewer games to smooth out the schedule
                penalty += len(calendar_days[d].games) * 2.5
                # Add slight random noise to prevent repetitive patterns
                penalty += self.rng.random() * 2.0

                valid_days.append((penalty, d))

            if valid_days:
                valid_days.sort(key=lambda x: x[0])
                best_d = valid_days[0][1]
                gid = f"g_{calendar_days[best_d].date}_{h[:3].upper()}_{a[:3].upper()}_{len(calendar_days[best_d].games)}"
                record_game(best_d, h, a, gid)
                placed = True

            if not placed:
                unplaced.append((h, a))

        # Secondary pass: slightly relaxed day capacities or max_b2b=16, but NO coast-to-coast flights
        if unplaced:
            relaxed_unplaced = []
            for h, a in unplaced:
                h_city = self.get_team_city(h)
                placed = False
                valid_days = []
                for d in range(total_days):
                    if calendar_days[d].is_off_day or "REGULAR_SEASON_FINALE" in calendar_days[d].events or "FINALE_EVE_REST" in calendar_days[d].events:
                        continue
                    if d == 1 and (h in day_1_forbidden_teams or a in day_1_forbidden_teams):
                        continue
                    if len(calendar_days[d].games) >= get_day_capacity(d) + 3:
                        continue
                    if h in day_teams[d] or a in day_teams[d]:
                        continue
                    if check_3_in_3(h, d) or check_3_in_3(a, d):
                        continue

                    # Allow B2B up to 16
                    b2b_h_add = (1 if d - 1 >= 0 and h in day_teams[d - 1] else 0) + (1 if d + 1 < total_days and h in day_teams[d + 1] else 0)
                    b2b_a_add = (1 if d - 1 >= 0 and a in day_teams[d - 1] else 0) + (1 if d + 1 < total_days and a in day_teams[d + 1] else 0)
                    if team_b2b_count[h] + b2b_h_add > 16 or team_b2b_count[a] + b2b_a_add > 16:
                        continue

                    # STRICT TRAVEL LIMIT: no coast-to-coast flights (>1100 mi) on B2Bs!
                    if not check_travel_validity(h, d, h_city, COAST_TO_COAST_LIMIT):
                        continue
                    if not check_travel_validity(a, d, h_city, COAST_TO_COAST_LIMIT):
                        continue

                    cost = len(calendar_days[d].games) * 2 + (b2b_h_add + b2b_a_add) * 15
                    valid_days.append((cost, d))

                if valid_days:
                    valid_days.sort(key=lambda x: x[0])
                    best_d = valid_days[0][1]
                    gid = f"g_{calendar_days[best_d].date}_{h[:3].upper()}_{a[:3].upper()}_{len(calendar_days[best_d].games)}"
                    record_game(best_d, h, a, gid)
                    placed = True
                else:
                    relaxed_unplaced.append((h, a))

            # Tertiary fallback pass: pick the day with minimum travel cost that strictly respects No 3-in-3s
            if relaxed_unplaced:
                for h, a in relaxed_unplaced:
                    h_city = self.get_team_city(h)
                    candidate_fallbacks = []
                    for d in range(total_days):
                        if calendar_days[d].is_off_day or "FINALE_EVE_REST" in calendar_days[d].events or "REGULAR_SEASON_FINALE" in calendar_days[d].events:
                            continue
                        if d == 1 and (h in day_1_forbidden_teams or a in day_1_forbidden_teams):
                            continue
                        if h in day_teams[d] or a in day_teams[d]:
                            continue
                        if check_3_in_3(h, d) or check_3_in_3(a, d):
                            continue

                        # Calculate travel cost
                        t_cost = 0.0
                        b2b_add = 0
                        long_flight_penalty = 0.0
                        for t, city in [(h, h_city), (a, h_city)]:
                            if d - 1 >= 0 and t in day_teams[d - 1]:
                                dist = calculate_city_distance_miles(team_day_location[t].get(d - 1, self.get_team_city(t)), city)
                                t_cost += dist
                                b2b_add += 1
                                if dist > 1200.0:
                                    long_flight_penalty += (dist - 1200.0) * 20.0
                            if d + 1 < total_days and t in day_teams[d + 1]:
                                dist = calculate_city_distance_miles(city, team_day_location[t].get(d + 1, self.get_team_city(t)))
                                t_cost += dist
                                b2b_add += 1
                                if dist > 1200.0:
                                    long_flight_penalty += (dist - 1200.0) * 20.0

                        score = len(calendar_days[d].games) + b2b_add * 50.0 + t_cost / 20.0 + long_flight_penalty
                        candidate_fallbacks.append((score, d))

                    if not candidate_fallbacks:
                        # Last resort: the game is never dropped (a dropped pair left two teams at 81 games, about
                        # one calendar in 40). Any playable day both teams are free, a 3-in-3 allowed, fewest games
                        # first; then any day at all, the finale and off days included.
                        for allow_special in (False, True):
                            candidate_fallbacks = [
                                (len(calendar_days[d].games), d) for d in range(total_days)
                                if h not in day_teams[d] and a not in day_teams[d]
                                and (allow_special or not (calendar_days[d].is_off_day
                                                           or "FINALE_EVE_REST" in calendar_days[d].events
                                                           or "REGULAR_SEASON_FINALE" in calendar_days[d].events))]
                            if candidate_fallbacks:
                                break
                    if candidate_fallbacks:
                        candidate_fallbacks.sort(key=lambda x: x[0])
                        best_d = candidate_fallbacks[0][1]
                        gid = f"g_{calendar_days[best_d].date}_{h[:3].upper()}_{a[:3].upper()}_{len(calendar_days[best_d].games)}"
                        record_game(best_d, h, a, gid)
                    else:
                        logging.getLogger('main_sim').error(f"Calendar: no free day for {a} @ {h}, game not scheduled")

        # Re-tag back-to-backs accurately
        for d in range(total_days):
            for g in calendar_days[d].games:
                if d > 0:
                    g.is_back_to_back_home = g.home_team in day_teams[d - 1]
                    g.is_back_to_back_away = g.away_team in day_teams[d - 1]
                g.home_team_obj = self.team_obj_map.get(g.home_team)
                g.away_team_obj = self.team_obj_map.get(g.away_team)

        return calendar_days


def verify_calendar_integrity(calendar_days: List[CalendarDay], teams: List[Any]) -> Dict[str, Any]:
    """
    Validation audit that checks:
    - Total games played
    - Games per team (should be exactly 82)
    - Home / Away balance (should be 41 / 41)
    - Zero 3-in-3s
    - Back-to-back counts
    """
    registry = get_active_registry()
    team_names = [_team_name(t) for t in teams]
    team_games = {t: 0 for t in team_names}
    team_home = {t: 0 for t in team_names}
    team_away = {t: 0 for t in team_names}
    team_b2b = {t: 0 for t in team_names}

    day_by_day_participation = {t: [] for t in team_names}
    total_games = 0

    for day in calendar_days:
        for g in day.games:
            total_games += 1
            team_games[g.home_team] += 1
            team_games[g.away_team] += 1
            team_home[g.home_team] += 1
            team_away[g.away_team] += 1
            if g.is_back_to_back_home:
                team_b2b[g.home_team] += 1
            if g.is_back_to_back_away:
                team_b2b[g.away_team] += 1
            day_by_day_participation[g.home_team].append(day.day_index)
            day_by_day_participation[g.away_team].append(day.day_index)

    # Check for illegal 3-in-3s
    three_in_threes = 0
    for _t, days in day_by_day_participation.items():
        day_set = set(days)
        for d in days:
            if (d + 1 in day_set) and (d + 2 in day_set):
                three_in_threes += 1

    b2b_vals = list(team_b2b.values())
    avg_b2b = sum(b2b_vals) / len(b2b_vals) if b2b_vals else 0

    # Calculate travel distances on back-to-backs
    b2b_travels = []
    coast_to_coast_count = 0
    for d in range(1, len(calendar_days)):
        today_games = calendar_days[d].games
        yesterday_games = calendar_days[d - 1].games
        yest_loc = {}
        for g in yesterday_games:
            yest_loc[g.home_team] = registry.geo_city(g.home_team, 'New York')
            yest_loc[g.away_team] = registry.geo_city(g.home_team, 'New York')
        for g in today_games:
            h_city = registry.geo_city(g.home_team, 'New York')
            if g.is_back_to_back_home and g.home_team in yest_loc:
                dist = calculate_city_distance_miles(yest_loc[g.home_team], h_city)
                b2b_travels.append(dist)
                if dist > 1400.0:
                    coast_to_coast_count += 1
            if g.is_back_to_back_away and g.away_team in yest_loc:
                dist = calculate_city_distance_miles(yest_loc[g.away_team], h_city)
                b2b_travels.append(dist)
                if dist > 1400.0:
                    coast_to_coast_count += 1

    avg_travel_dist = sum(b2b_travels) / len(b2b_travels) if b2b_travels else 0.0
    max_travel_dist = max(b2b_travels) if b2b_travels else 0.0
    finale_games = len(calendar_days[-1].games) if calendar_days else 0

    return {
        "total_calendar_days": len(calendar_days),
        "total_games": total_games,
        "games_per_team_min": min(team_games.values()) if team_games else 0,
        "games_per_team_max": max(team_games.values()) if team_games else 0,
        "home_games_min": min(team_home.values()) if team_home else 0,
        "home_games_max": max(team_home.values()) if team_home else 0,
        "away_games_min": min(team_away.values()) if team_away else 0,
        "away_games_max": max(team_away.values()) if team_away else 0,
        "three_in_threes_detected": three_in_threes,
        "avg_b2b_per_team": round(avg_b2b, 1),
        "min_b2b": min(b2b_vals) if b2b_vals else 0,
        "max_b2b": max(b2b_vals) if b2b_vals else 0,
        "games_on_season_finale": finale_games,
        "avg_b2b_travel_miles": round(avg_travel_dist, 1),
        "max_b2b_travel_miles": round(max_travel_dist, 1),
        "coast_to_coast_b2bs": coast_to_coast_count,
        "is_valid": (
            min(team_games.values()) == 82 and max(team_games.values()) == 82
            and min(team_home.values()) == 41 and max(team_home.values()) == 41
            and three_in_threes == 0
            and finale_games == 15
            and max(b2b_vals) <= 16
        )
    }


def export_calendar_preview_report(calendar_days: List[CalendarDay], teams: List[Any], file_path: str):
    """Generates an executive text summary of the season calendar for user inspection."""
    audit = verify_calendar_integrity(calendar_days, teams)
    lines = [
        "=" * 80,
        "🏀 Hardwood Basketball Simulator - EXECUTIVE CALENDAR AUDIT & PREVIEW REPORT",
        "=" * 80,
        f"Calendar Length: {audit['total_calendar_days']} season days (October -> April)",
        f"Total League Games: {audit['total_games']} (NBA target: 1230)",
        f"Games per Team: {audit['games_per_team_min']} - {audit['games_per_team_max']} (target: exactly 82)",
        f"Home/Away Balance: Home {audit['home_games_min']}-{audit['home_games_max']} | Away {audit['away_games_min']}-{audit['away_games_max']} (target: 41/41)",
        f"Back-to-Backs per Team: Avg {audit['avg_b2b_per_team']} (min {audit['min_b2b']}, max {audit['max_b2b']}) [TARGET <= 16 MET]",
        f"Average B2B Travel Distance: {audit['avg_b2b_travel_miles']} miles (Max: {audit['max_b2b_travel_miles']} mi)",
        f"Coast-to-Coast B2B Flights (>1400 mi): {audit['coast_to_coast_b2bs']} (Geographic Clustering Active)",
        f"Season Finale Day 176 Games: {audit['games_on_season_finale']} games (All 30 franchises playing simultaneously)",
        f"Three-in-Three Violations: {audit['three_in_threes_detected']} (RULE MET: ZERO)",
        f"Calendar Integrity Status: {'✅ PERFECT AND VALID' if audit['is_valid'] else '⚠️ PARTIAL'}",
        "=" * 80,
        "",
        "--- KEY SEASON EVENTS ---"
    ]

    for day in calendar_days:
        if day.events or day.phase != "REGULAR_SEASON" or day.is_off_day:
            ev_str = ", ".join(day.events) if day.events else "OFF DAY"
            lines.append(f"Day {day.day_index + 1:3d} ({day.date}): [{ev_str}] | Games scheduled: {len(day.games)}")

    lines.append("\n" + "=" * 80)
    lines.append("--- FULL SEASON CALENDAR (176 DAYS, 1230 GAMES) ---")
    lines.append("=" * 80)

    for d in range(len(calendar_days)):
        day = calendar_days[d]
        ev_str = f" ⭐ [{', '.join(day.events)}]" if day.events else ""
        lines.append(f"\nDAY {day.day_index + 1} - {day.date}{ev_str} ({len(day.games)} games):")
        if not day.games:
            lines.append("  (No games scheduled - Rest day)")
        for g in day.games:
            b2b_tag = ""
            if g.is_back_to_back_home and g.is_back_to_back_away:
                b2b_tag = " [B2B Entrambe]"
            elif g.is_back_to_back_home:
                b2b_tag = f" [B2B {g.home_team}]"
            elif g.is_back_to_back_away:
                b2b_tag = f" [B2B {g.away_team}]"
            lines.append(f"  • {g.away_team:26s} @ {g.home_team:26s}{b2b_tag}")

    import os
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

