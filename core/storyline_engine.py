# storyline_engine.py
"""
Storyline Engine for Hardwood Basketball Simulator

Generates dynamic narratives based on:
- Rivalry context between teams
- MVP race progression
- Player milestones and records
- Team streaks (winning/losing)
- Playoff race and standings
- Revenge games (players vs former teams)

Works with RivalryTracker and provides rich pre/post-game context.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, TYPE_CHECKING
import random

if TYPE_CHECKING:
    from .models import Giocatore, Squadra
    from rivalry_tracker import RivalryTracker


@dataclass
class Storyline:
    """A narrative element to display in the game."""
    type: str  # 'rivalry', 'mvp_race', 'milestone', 'revenge', 'streak', 'playoff_race', 'historic'
    headline: str
    description: str
    intensity: str = "normal"  # 'normal', 'high', 'breaking'
    teams: List[str] = field(default_factory=list)
    players: List[str] = field(default_factory=list)
    icon: str = "📰"  # Emoji for visual display


@dataclass
class MVPCandidate:
    """Tracks a player in the MVP race."""
    player_name: str
    team_name: str
    ppg: float
    rpg: float
    apg: float
    wins: int
    games_played: int
    mvp_score: float = 0.0
    rank: int = 0
    trend: str = "steady"  # 'up', 'down', 'steady'


@dataclass
class MilestoneWatch:
    """Tracks a player approaching a milestone."""
    player_name: str
    team_name: str
    milestone_type: str  # 'career_points', 'career_assists', 'season_ppg', etc.
    current_value: float
    target_value: float
    remaining: float
    is_close: bool = False  # Within reach this season


class StorylineEngine:
    """
    Generates and manages storylines throughout a season.
    Designed to be attached to the Tournament object.
    """
    
    # Milestones to track
    CAREER_MILESTONES = {
        'career_points': [10000, 15000, 20000, 25000, 30000, 35000, 40000],
        'career_assists': [5000, 7500, 10000, 12000, 15000],
        'career_rebounds': [5000, 10000, 12000, 15000],
    }
    
    # Storyline templates
    RIVALRY_TEMPLATES = {
        'legendary': [
            "🔥 RIVALRY RENEWED: {team1} vs {team2} - A legendary clash",
            "⚔️ HISTORIC MATCHUP: The storied rivalry continues tonight",
            "🏆 TITANS COLLIDE: {team1} and {team2} write the next chapter",
        ],
        'heated': [
            "🔥 BAD BLOOD: {team1} face off against {team2} in heated rivalry",
            "⚡ TENSION RISING: Recent playoff history fuels tonight's matchup",
            "💥 SPARKS EXPECTED: These teams don't like each other",
        ],
        'moderate': [
            "📊 Rivalry Game: {team1} vs {team2} - Always competitive",
            "🏀 Familiar Foes: Another chapter in the {team1}-{team2} series",
        ],
        'mild': [
            "Division matchup: {team1} host {team2}",
        ]
    }
    
    REVENGE_TEMPLATES = [
        "⚔️ REVENGE GAME: {player} returns to face {former_team} for the first time",
        "🔙 THE RETURN: {player} looks to prove {former_team} wrong",
        "💢 CIRCLED ON THE CALENDAR: {player} faces his old team tonight",
    ]
    
    STREAK_TEMPLATES = {
        'winning_hot': [
            "🔥 ON FIRE: {team} riding a {count}-game winning streak",
            "📈 SURGING: The {team} can't be stopped right now",
        ],
        'winning_historic': [
            "🏆 HISTORIC RUN: {team} winners of {count} straight!",
        ],
        'losing_bad': [
            "📉 STRUGGLING: {team} have lost {count} in a row",
            "⚠️ CRISIS MODE: {team}'s {count}-game skid continues",
        ],
    }
    
    def __init__(self):
        self.current_season: int = 1
        self.mvp_candidates: List[MVPCandidate] = []
        self.milestone_watches: List[MilestoneWatch] = []
        self.active_storylines: List[Storyline] = []
        self.player_former_teams: Dict[str, List[str]] = {}  # Track player movement
    
    # [UNWIRED] Implemented but not called by the game yet; see docs/UNWIRED_FEATURES.md.
    def set_season(self, season: int):
        """Update the current season."""
        self.current_season = season
    
    # [UNWIRED] Implemented but not called by the game yet; see docs/UNWIRED_FEATURES.md.
    def register_player_trade(self, player_name: str, old_team: str, new_team: str):
        """Track when a player changes teams for revenge game storylines."""
        if player_name not in self.player_former_teams:
            self.player_former_teams[player_name] = []
        if old_team and old_team not in self.player_former_teams[player_name]:
            self.player_former_teams[player_name].append(old_team)
    
    def get_pregame_storylines(self, home_team: 'Squadra', away_team: 'Squadra',
                                rivalry_tracker: 'RivalryTracker') -> List[Storyline]:
        """
        Generate pre-game storylines for a matchup.
        
        Returns list of relevant storylines to display before simulation.
        """
        storylines = []
        
        # 1. Check for rivalry context
        rivalry_context = rivalry_tracker.get_matchup_context(home_team.nome, away_team.nome)
        if rivalry_context['has_rivalry'] and rivalry_context['intensity'] > 15:
            storyline = self._generate_rivalry_storyline(
                home_team.nome, away_team.nome, rivalry_context
            )
            if storyline:
                storylines.append(storyline)
        
        # 2. Check for revenge games
        revenge_storylines = self._check_revenge_games(home_team, away_team)
        storylines.extend(revenge_storylines)
        
        # 3. Check for team streaks
        streak_storylines = self._check_team_streaks(home_team, away_team)
        storylines.extend(streak_storylines)
        
        # 4. Check for playoff implications
        # (Would need standings data - can be added later)
        
        return storylines
    
    def _generate_rivalry_storyline(self, team1: str, team2: str, 
                                     context: Dict) -> Optional[Storyline]:
        """Generate a storyline based on rivalry context."""
        level = context['level']
        templates = self.RIVALRY_TEMPLATES.get(level, [])
        
        if not templates:
            return None
        
        template = random.choice(templates)
        headline = template.format(team1=team1, team2=team2)
        
        # Build description from context
        desc_parts = []
        if context['all_time_record'] != "0-0":
            desc_parts.append(f"All-time series: {context['all_time_record']}")
        if context['playoff_history'] > 0:
            desc_parts.append(f"{context['playoff_history']} playoff meetings")
        if context['finals_meetings'] > 0:
            desc_parts.append(f"{context['finals_meetings']} Finals showdowns")
        
        # Add recent event flavor
        if context['recent_events']:
            latest = context['recent_events'][-1]
            desc_parts.append(f"Last meeting: {latest.description}")
        
        description = " | ".join(desc_parts) if desc_parts else "Historic rivalry matchup"
        
        intensity = "breaking" if level == "legendary" else ("high" if level == "heated" else "normal")
        
        return Storyline(
            type="rivalry",
            headline=headline,
            description=description,
            intensity=intensity,
            teams=[team1, team2],
            icon="🔥" if level in ["legendary", "heated"] else "⚔️"
        )
    
    def _check_revenge_games(self, home_team: 'Squadra', 
                              away_team: 'Squadra') -> List[Storyline]:
        """Check if any players are facing their former teams."""
        storylines = []
        
        # Check home team players against away team
        for player in home_team.roster:
            former_teams = self.player_former_teams.get(player.nome, [])
            if away_team.nome in former_teams:
                template = random.choice(self.REVENGE_TEMPLATES)
                storylines.append(Storyline(
                    type="revenge",
                    headline=template.format(player=player.nome, former_team=away_team.nome),
                    description=f"{player.nome} will look to make a statement against his former team.",
                    intensity="high",
                    teams=[home_team.nome, away_team.nome],
                    players=[player.nome],
                    icon="⚔️"
                ))
        
        # Check away team players against home team
        for player in away_team.roster:
            former_teams = self.player_former_teams.get(player.nome, [])
            if home_team.nome in former_teams:
                template = random.choice(self.REVENGE_TEMPLATES)
                storylines.append(Storyline(
                    type="revenge",
                    headline=template.format(player=player.nome, former_team=home_team.nome),
                    description=f"{player.nome} returns to where it all began.",
                    intensity="high",
                    teams=[home_team.nome, away_team.nome],
                    players=[player.nome],
                    icon="🔙"
                ))
        
        return storylines[:2]  # Limit to 2 revenge storylines per game
    
    def _check_team_streaks(self, home_team: 'Squadra', 
                            away_team: 'Squadra') -> List[Storyline]:
        """Check for notable winning/losing streaks."""
        storylines = []
        
        for team in [home_team, away_team]:
            streak = getattr(team, 'current_streak', 0)
            streak_type = getattr(team, 'streak_type', None)  # 'W' or 'L'
            
            if streak_type == 'W' and streak >= 5:
                if streak >= 10:
                    templates = self.STREAK_TEMPLATES['winning_historic']
                else:
                    templates = self.STREAK_TEMPLATES['winning_hot']
                
                template = random.choice(templates)
                storylines.append(Storyline(
                    type="streak",
                    headline=template.format(team=team.nome, count=streak),
                    description=f"Can anyone stop the {team.nome}?",
                    intensity="high" if streak >= 8 else "normal",
                    teams=[team.nome],
                    icon="🔥"
                ))
            
            elif streak_type == 'L' and streak >= 5:
                templates = self.STREAK_TEMPLATES['losing_bad']
                template = random.choice(templates)
                storylines.append(Storyline(
                    type="streak",
                    headline=template.format(team=team.nome, count=streak),
                    description=f"The {team.nome} desperately need a win.",
                    intensity="normal",
                    teams=[team.nome],
                    icon="📉"
                ))
        
        return storylines
    
    def update_mvp_race(self, all_players: List['Giocatore']) -> List[MVPCandidate]:
        """
        Update MVP race standings based on current stats.
        Call this periodically during the season.
        """
        candidates = []
        
        for player in all_players:
            if not player.squadra or player.season_stats.partite_giocate < 10:
                continue
            
            pg = player.season_stats.partite_giocate
            ppg = player.season_stats.punti / pg
            rpg = player.season_stats.rimbalzi / pg
            apg = player.season_stats.assist / pg
            
            # Simple MVP score formula
            mvp_score = (
                ppg * 1.0 +
                rpg * 0.8 +
                apg * 1.2 +
                (player.squadra.vittorie / max(1, player.squadra.vittorie + player.squadra.sconfitte)) * 40
            )
            
            # Bonus for high-performing players on winning teams
            if player.squadra.vittorie > player.squadra.sconfitte:
                mvp_score *= 1.1
            
            candidates.append(MVPCandidate(
                player_name=player.nome,
                team_name=player.squadra.nome,
                ppg=round(ppg, 1),
                rpg=round(rpg, 1),
                apg=round(apg, 1),
                wins=player.squadra.vittorie,
                games_played=pg,
                mvp_score=round(mvp_score, 1)
            ))
        
        # Sort and rank
        candidates.sort(key=lambda c: c.mvp_score, reverse=True)
        for i, candidate in enumerate(candidates[:10]):
            candidate.rank = i + 1
            
            # Determine trend (would need previous data - simplified for now)
            candidate.trend = "steady"
        
        self.mvp_candidates = candidates[:10]
        return self.mvp_candidates
    
    # [UNWIRED] Implemented but not called by the game yet; see docs/UNWIRED_FEATURES.md.
    def get_mvp_race_storyline(self) -> Optional[Storyline]:
        """Generate a storyline about the current MVP race."""
        if len(self.mvp_candidates) < 2:
            return None
        
        leader = self.mvp_candidates[0]
        runner_up = self.mvp_candidates[1]
        
        gap = leader.mvp_score - runner_up.mvp_score
        
        if gap < 5:
            headline = f"🏆 MVP RACE: {leader.player_name} and {runner_up.player_name} neck-and-neck!"
            intensity = "breaking"
        elif gap < 15:
            headline = f"🏆 MVP WATCH: {leader.player_name} leads, {runner_up.player_name} lurking"
            intensity = "high"
        else:
            headline = f"🏆 MVP FAVORITE: {leader.player_name} pulling away in MVP race"
            intensity = "normal"
        
        return Storyline(
            type="mvp_race",
            headline=headline,
            description=f"Leader: {leader.ppg} PPG / {leader.rpg} RPG / {leader.apg} APG ({leader.wins} team wins)",
            intensity=intensity,
            players=[leader.player_name, runner_up.player_name],
            icon="🏆"
        )
    
    # [UNWIRED] Implemented but not called by the game yet; see docs/UNWIRED_FEATURES.md.
    def generate_postgame_storyline(self, winner: 'Squadra', loser: 'Squadra',
                                     winner_score: int, loser_score: int,
                                     rivalry_tracker: 'RivalryTracker') -> List[Storyline]:
        """Generate post-game storylines based on game result."""
        storylines = []
        point_diff = winner_score - loser_score
        
        # Rivalry update
        rivalry_context = rivalry_tracker.get_matchup_context(winner.nome, loser.nome)
        if rivalry_context['has_rivalry'] and rivalry_context['intensity'] > 30:
            if point_diff <= 5:
                storylines.append(Storyline(
                    type="rivalry",
                    headline=f"⚡ INSTANT CLASSIC: {winner.nome} edge {loser.nome} in thriller!",
                    description=f"Final: {winner_score}-{loser_score}. The rivalry burns hotter.",
                    intensity="high",
                    teams=[winner.nome, loser.nome],
                    icon="⚡"
                ))
            elif point_diff >= 25:
                storylines.append(Storyline(
                    type="rivalry",
                    headline=f"💥 STATEMENT WIN: {winner.nome} demolish {loser.nome}!",
                    description=f"Final: {winner_score}-{loser_score}. A dominant performance.",
                    intensity="high",
                    teams=[winner.nome, loser.nome],
                    icon="💥"
                ))
        
        return storylines
    
    def to_dict(self) -> Dict:
        """Convert storyline data to dictionary for API responses."""
        return {
            "current_season": self.current_season,
            "mvp_race": [
                {
                    "rank": c.rank,
                    "player": c.player_name,
                    "team": c.team_name,
                    "ppg": c.ppg,
                    "rpg": c.rpg,
                    "apg": c.apg,
                    "wins": c.wins,
                    "score": c.mvp_score,
                    "trend": c.trend
                }
                for c in self.mvp_candidates[:5]
            ],
            "active_storylines": [
                {
                    "type": s.type,
                    "headline": s.headline,
                    "description": s.description,
                    "intensity": s.intensity,
                    "teams": s.teams,
                    "icon": s.icon
                }
                for s in self.active_storylines[-10:]
            ]
        }
