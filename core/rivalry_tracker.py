# rivalry_tracker.py
"""
Rivalry Tracking System for Hardwood Basketball Simulator

Tracks and manages rivalries between teams based on:
- Head-to-head records
- Playoff history (eliminations, Finals meetings)
- Close games and blowouts
- Division/Conference matchups

Rivalries are stored in memory within the Tournament object.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


@dataclass
class RivalryEvent:
    """A single memorable moment that contributes to a rivalry."""
    season: int
    event_type: str  # 'playoff_elimination', 'finals', 'blowout', 'buzzer_beater', 'close_game', 'sweep'
    description: str
    winning_team: str
    losing_team: str
    score: Optional[str] = None  # e.g., "112-110" or "4-0" for series
    intensity_gain: float = 0.0


@dataclass
class HeadToHead:
    """Season-by-season head-to-head record between two teams."""
    season: int
    team1_wins: int = 0
    team2_wins: int = 0
    total_point_diff: int = 0  # Positive = team1 scored more overall
    close_games: int = 0  # Games decided by ≤5 points
    blowouts: int = 0  # Games decided by 25+ points


@dataclass
class Rivalry:
    """
    Represents a rivalry between two teams.
    
    Intensity scale:
    - 0-20: Mild (division rivals, occasional matchups)
    - 21-50: Moderate (multiple playoff meetings)
    - 51-80: Heated (recent playoff eliminations, close series)
    - 81-100: Legendary (Finals history, iconic moments)
    """
    team1: str
    team2: str
    intensity: float = 0.0
    rivalry_type: str = "formed"  # 'division', 'conference', 'historic', 'formed'
    
    # Historical data
    all_time_record: List[int] = field(default_factory=lambda: [0, 0])  # [team1_wins, team2_wins]
    playoff_meetings: int = 0
    finals_meetings: int = 0
    
    # Season-by-season tracking
    head_to_head_history: List[HeadToHead] = field(default_factory=list)
    events: List[RivalryEvent] = field(default_factory=list)
    
    # Metadata
    last_meeting_season: int = 0
    created_season: int = 1
    
    
    def get_intensity_level(self) -> str:
        """Return a human-readable intensity level."""
        if self.intensity >= 80:
            return "legendary"
        elif self.intensity >= 50:
            return "heated"
        elif self.intensity >= 20:
            return "moderate"
        else:
            return "mild"
    
    def get_all_time_record_str(self) -> str:
        """Return all-time record as a formatted string."""
        return f"{self.all_time_record[0]}-{self.all_time_record[1]}"


class RivalryTracker:
    """
    Manages all rivalries in the league.
    
    Stores rivalries in memory - resets when server restarts.
    Designed to be attached to the Tournament object.
    """
    
    # Intensity values for different events
    INTENSITY_VALUES = {
        'division_base': 12.0,
        'conference_base': 3.0,
        'playoff_meeting': 12.0,
        'playoff_elimination': 25.0,
        'conference_finals': 22.0,
        'finals_meeting': 35.0,
        'finals_win': 45.0,
        'sweep': 18.0,
        'game7': 22.0,
        'close_game': 0.8,
        'blowout': 1.2,
        'buzzer_beater': 6.0,
        'overtime_game': 1.5,
    }
    
    # Decay per season (0.72 base): rivalries fade progressively without playoff meetings
    INTENSITY_DECAY_RATE = 0.72
    
    def __init__(self):
        self.rivalries: Dict[Tuple[str, str], Rivalry] = {}
        self.current_season: int = 1
        
    def _get_rivalry_key(self, team1: str, team2: str) -> Tuple[str, str]:
        """Generate a consistent key for two teams."""
        return tuple(sorted([team1, team2]))
    
    def get_or_create_rivalry(self, team1: str, team2: str, rivalry_type: str = "formed") -> Rivalry:
        """Get existing rivalry or create a new one."""
        key = self._get_rivalry_key(team1, team2)
        
        if key not in self.rivalries:
            self.rivalries[key] = Rivalry(
                team1=key[0],
                team2=key[1],
                rivalry_type=rivalry_type,
                created_season=self.current_season
            )
        
        return self.rivalries[key]
    
    def get_rivalry(self, team1: str, team2: str) -> Optional[Rivalry]:
        """Get rivalry between two teams if it exists."""
        key = self._get_rivalry_key(team1, team2)
        return self.rivalries.get(key)
    
    def record_regular_season_game(self, winner: str, loser: str, winner_score: int, loser_score: int):
        """
        Record a regular season game result.
        Updates head-to-head. Intensity only grows if a division or heated rivalry already exists.
        """
        rivalry = self.get_or_create_rivalry(winner, loser)
        point_diff = winner_score - loser_score
        
        # Update all-time record
        if winner == rivalry.team1:
            rivalry.all_time_record[0] += 1
        else:
            rivalry.all_time_record[1] += 1
        
        # Update current season head-to-head
        current_h2h = self._get_current_season_h2h(rivalry)
        if winner == rivalry.team1:
            current_h2h.team1_wins += 1
            current_h2h.total_point_diff += point_diff
        else:
            current_h2h.team2_wins += 1
            current_h2h.total_point_diff -= point_diff
        
        # Track notable games
        is_close_game = point_diff <= 3
        is_blowout = point_diff >= 30
        
        # In the regular season intensity only grows if a rivalry is already active or it is a division clash
        # This keeps every random pair of teams in the league from climbing to 100
        if rivalry.rivalry_type == "division" or rivalry.intensity >= 25.0:
            if is_close_game:
                current_h2h.close_games += 1
                rivalry.intensity += 0.4
            elif is_blowout:
                current_h2h.blowouts += 1
                rivalry.intensity += 0.3
        
        rivalry.last_meeting_season = self.current_season
        rivalry.intensity = min(100.0, rivalry.intensity)
    
    def record_playoff_game(self, winner: str, loser: str, winner_score: int, loser_score: int,
                            series_score: Tuple[int, int], round_name: str):
        """
        Record a playoff game. Playoff games have bigger impact on rivalries.
        """
        rivalry = self.get_or_create_rivalry(winner, loser)
        point_diff = winner_score - loser_score
        
        # Update record
        if winner == rivalry.team1:
            rivalry.all_time_record[0] += 1
        else:
            rivalry.all_time_record[1] += 1
        
        # Playoff meeting bonus (once per series)
        if max(series_score) == 1:  # First win of series
            rivalry.playoff_meetings += 1
            rivalry.intensity += self.INTENSITY_VALUES['playoff_meeting']
        
        # Conference Finals bonus
        if 'conference' in round_name.lower() and 'finals' in round_name.lower():
            if max(series_score) == 1:
                rivalry.intensity += self.INTENSITY_VALUES['conference_finals']
        
        # NBA Finals bonus
        if 'nba finals' in round_name.lower() or round_name.lower() == 'finals':
            if max(series_score) == 1:
                rivalry.finals_meetings += 1
                rivalry.intensity += self.INTENSITY_VALUES['finals_meeting']
        
        # Check for series-ending scenarios
        if max(series_score) == 4:  # Series over
            self._record_series_end(rivalry, winner, loser, series_score, round_name)
        
        # Close/blowout games matter in playoffs
        if point_diff <= 4:
            rivalry.intensity += 1.5
        if point_diff >= 25:
            rivalry.intensity += 1.0
        
        rivalry.last_meeting_season = self.current_season
        rivalry.intensity = min(100.0, rivalry.intensity)
    
    def _record_series_end(self, rivalry: Rivalry, winner: str, loser: str, 
                           series_score: Tuple[int, int], round_name: str):
        """Record the end of a playoff series - major rivalry event."""
        was_sweep = min(series_score) == 0
        was_game7 = series_score == (4, 3)
        
        if 'finals' in round_name.lower() and 'conference' not in round_name.lower():
            event_type = 'finals'
            rivalry.intensity += self.INTENSITY_VALUES['finals_win']
            desc = f"{winner} defeat {loser} to win the NBA Championship!"
        else:
            event_type = 'playoff_elimination'
            rivalry.intensity += self.INTENSITY_VALUES['playoff_elimination']
            desc = f"{winner} eliminate {loser} in the {round_name}"
        
        if was_sweep:
            rivalry.intensity += self.INTENSITY_VALUES['sweep']
            desc += " (SWEEP)"
            event_type = 'sweep'
        elif was_game7:
            rivalry.intensity += self.INTENSITY_VALUES['game7']
            desc += " in a dramatic Game 7!"
            event_type = 'game7'
        
        event = RivalryEvent(
            season=self.current_season,
            event_type=event_type,
            description=desc,
            winning_team=winner,
            losing_team=loser,
            score=f"{max(series_score)}-{min(series_score)}",
            intensity_gain=self.INTENSITY_VALUES.get(event_type, 10.0)
        )
        rivalry.events.append(event)
    
    # [UNWIRED] Implemented but not called by the game yet; see docs/UNWIRED_FEATURES.md.
    def record_buzzer_beater(self, winner: str, loser: str, player_name: str, is_playoff: bool = False):
        """Record a buzzer-beater win - memorable rivalry moment."""
        rivalry = self.get_or_create_rivalry(winner, loser)
        
        multiplier = 2.0 if is_playoff else 0.5
        rivalry.intensity += self.INTENSITY_VALUES['buzzer_beater'] * multiplier
        
        event = RivalryEvent(
            season=self.current_season,
            event_type='buzzer_beater',
            description=f"{player_name} hits the game-winning shot against {loser}!",
            winning_team=winner,
            losing_team=loser,
            intensity_gain=self.INTENSITY_VALUES['buzzer_beater'] * multiplier
        )
        rivalry.events.append(event)
        rivalry.intensity = min(100.0, rivalry.intensity)
    
    def _get_current_season_h2h(self, rivalry: Rivalry) -> HeadToHead:
        """Get or create head-to-head record for current season."""
        for h2h in rivalry.head_to_head_history:
            if h2h.season == self.current_season:
                return h2h
        
        new_h2h = HeadToHead(season=self.current_season)
        rivalry.head_to_head_history.append(new_h2h)
        return new_h2h
    
    def apply_season_decay(self):
        """
        Applies a realistic decay to rivalry intensity at the end of every season.
        Division rivalries have a minimum intensity floor (10.0).
        Other rivalries decay progressively unless renewed in the playoffs.
        """
        for rivalry in self.rivalries.values():
            decay_factor = self.INTENSITY_DECAY_RATE
            
            # If the teams haven't met recently in the playoffs, the decay is faster
            if rivalry.last_meeting_season < self.current_season:
                decay_factor = 0.60
                
            rivalry.intensity *= decay_factor
            
            # Minimum floor for division rivalries
            if rivalry.rivalry_type == "division":
                rivalry.intensity = max(10.0, rivalry.intensity)
            else:
                rivalry.intensity = max(0.0, rivalry.intensity)
    
    # [UNWIRED] Implemented but not called by the game yet; see docs/UNWIRED_FEATURES.md.
    def advance_season(self):
        """Move to the next season. Apply decay first."""
        self.apply_season_decay()
        self.current_season += 1
    
    def initialize_division_rivalries(self, divisions: Dict[str, List[str]]):
        """
        Set up base division rivalries at simulation start.
        
        Args:
            divisions: Dict mapping division name to list of team names
        """
        for _division_name, teams in divisions.items():
            for i, team1 in enumerate(teams):
                for team2 in teams[i+1:]:
                    rivalry = self.get_or_create_rivalry(team1, team2, rivalry_type="division")
                    rivalry.intensity = self.INTENSITY_VALUES['division_base']
    
    def get_top_rivalries(self, limit: int = 10) -> List[Rivalry]:
        """Get the most intense rivalries in the league."""
        sorted_rivalries = sorted(
            self.rivalries.values(),
            key=lambda r: r.intensity,
            reverse=True
        )
        return sorted_rivalries[:limit]
    
    # [UNWIRED] Implemented but not called by the game yet; see docs/UNWIRED_FEATURES.md.
    def get_team_rivalries(self, team_name: str) -> List[Rivalry]:
        """Get all rivalries involving a specific team, sorted by intensity."""
        team_rivalries = [
            r for r in self.rivalries.values()
            if team_name in (r.team1, r.team2)
        ]
        return sorted(team_rivalries, key=lambda r: r.intensity, reverse=True)
    
    def get_matchup_context(self, team1: str, team2: str) -> Dict:
        """
        Get context for a matchup between two teams.
        Useful for generating pre-game storylines.
        """
        rivalry = self.get_rivalry(team1, team2)
        
        if not rivalry:
            return {
                "has_rivalry": False,
                "intensity": 0,
                "level": "none",
                "recent_events": [],
                "all_time_record": "0-0",
                "playoff_history": 0,
            }
        
        # Get recent events (last 3 seasons)
        recent_events = [
            e for e in rivalry.events
            if e.season >= self.current_season - 3
        ]
        
        return {
            "has_rivalry": True,
            "intensity": rivalry.intensity,
            "level": rivalry.get_intensity_level(),
            "type": rivalry.rivalry_type,
            "recent_events": recent_events[-5:],  # Last 5 events
            "all_time_record": rivalry.get_all_time_record_str(),
            "playoff_history": rivalry.playoff_meetings,
            "finals_meetings": rivalry.finals_meetings,
            "last_meeting_season": rivalry.last_meeting_season,
        }
    
    def to_dict(self) -> Dict:
        """Convert all rivalry data to a dictionary for API responses."""
        return {
            "current_season": self.current_season,
            "total_rivalries": len(self.rivalries),
            "top_rivalries": [
                {
                    "teams": [r.team1, r.team2],
                    "intensity": round(r.intensity, 1),
                    "level": r.get_intensity_level(),
                    "type": r.rivalry_type,
                    "all_time_record": r.all_time_record,
                    "playoff_meetings": r.playoff_meetings,
                    "finals_meetings": r.finals_meetings,
                    "recent_events": [
                        {
                            "season": e.season,
                            "type": e.event_type,
                            "description": e.description
                        }
                        for e in r.events[-3:]
                    ]
                }
                for r in self.get_top_rivalries(15)
            ]
        }
