from __future__ import annotations
# models.py (EXPERIENCE-BASED DEVELOPMENT VERSION)

import math
import random
from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict, Tuple

from .config import CONFIG
from .roles import normalize_role, normalize_role_keys

# Import Partita and Tournament for type hinting
from typing import TYPE_CHECKING


def trade_curve_value(rating: float) -> float:
    """Value over replacement of a player rated `rating` (CONFIG.TRADES.VALUE_CURVE_*): can be negative."""
    t = CONFIG.TRADES
    at = lambda r: t.VALUE_CURVE_ANCHOR_VALUE * math.exp((r - t.VALUE_CURVE_ANCHOR_OVR) / t.VALUE_CURVE_SCALE)
    return at(rating) - at(t.VALUE_CURVE_REPLACEMENT_OVR)
if TYPE_CHECKING:
    from game_engine import Tournament

ACTIVE_TOURNAMENT = None

# Rating penalty when a player (row = his role) plays another position (column). Roles: core/roles.py
POSITION_COMPATIBILITY_PENALTY = {
    'PG': {'PG': 0, 'SG': 4, 'SF': 15, 'PF': 28, 'C': 40},
    'SG': {'PG': 5, 'SG': 0, 'SF': 5,  'PF': 22, 'C': 40},
    'SF': {'PG': 25, 'SG': 6, 'SF': 0,  'PF': 6,  'C': 22},
    'PF': {'PG': 35, 'SG': 25, 'SF': 8,  'PF': 0,  'C': 4},
    'C':  {'PG': 40, 'SG': 35, 'SF': 20, 'PF': 5,  'C': 0},
}

MATCHUP_FALLBACK_MAP: Dict[str, Tuple[str, ...]] = {
    'PG': ('PG', 'SG', 'SF'),
    'SG': ('SG', 'PG', 'SF'),
    'SF': ('SF', 'SG', 'PF'),
    'PF': ('PF', 'SF', 'C'),
    'C':  ('C', 'PF'),
}

@dataclass
class Contract:
    anni_rimanenti: int
    salario_annuale: float
    salari_per_anno: List[float] = field(default_factory=list)
    player_option: bool = False
    team_option: bool = False

    def __post_init__(self):
        if not self.salari_per_anno and self.anni_rimanenti > 0:
            self.salari_per_anno = [round(self.salario_annuale * (1.0 + 0.05 * i), 2) for i in range(self.anni_rimanenti)]
        elif self.salari_per_anno:
            self.salario_annuale = round(self.salari_per_anno[0], 2)


    def __str__(self):
        base = f"${self.salario_annuale}M/{self.anni_rimanenti}y"
        if self.player_option: base += " [PO]"
        if self.team_option: base += " [TO]"
        return base

def _retired_key(player: Any) -> tuple:
    """Same player = same name, DB id, age and ratings (generated names repeat across classes)."""
    return (getattr(player, 'nome', None), getattr(player, 'db_id', None), getattr(player, 'eta', None),
            getattr(player, 'valutazione', None), getattr(player, 'potenziale', None))


def add_retired_player(torneo: Any, player: Any) -> bool:
    """Adds `player` to torneo.giocatori_ritirati once. A 25-season save held 504 copies of players already there
    (one player went through two retirement paths). Returns True when added."""
    retired = getattr(torneo, 'giocatori_ritirati', None)
    if retired is None:
        return False
    key = _retired_key(player)
    if any(r is player or _retired_key(r) == key for r in retired):
        return False
    retired.append(player)
    return True


def unique_retired_players(players: list) -> list:
    """`players` without repeats (first copy kept): cleans the retired list of saves written before the fix."""
    seen, out = set(), []
    for p in players:
        key = _retired_key(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def league_season_scales(torneo: Any) -> Dict[str, float]:
    """How this season's production compares with the reference era (CONFIG.PROGRESSION.PVS_REFERENCE): a factor
    per measure that brings a player's numbers back to that level (1.0 = same as 2002). The modern pace lifted
    every PVS and every per-game total, so progression handed out OVR points to the whole league. Cached per season;
    all 1.0 when too few players have real minutes (preseason, tests)."""
    cfg = CONFIG.PROGRESSION
    neutral = {key: 1.0 for key in ('off', 'def', 'pts', 'ast', 'reb')}
    if torneo is None:
        return neutral
    season = getattr(torneo, 'season_number', None)
    cached = getattr(torneo, '_league_season_scales', None)
    if cached and cached[0] == season:
        return cached[1]
    players = [p for s in getattr(torneo, 'squadre', None) or [] for p in getattr(s, 'roster', None) or []]
    players += list(getattr(torneo, 'free_agents_pool', None) or [])
    sums = {key: 0.0 for key in neutral}
    count = 0
    for p in players:
        stats = getattr(p, 'season_stats', None)
        if stats is None or stats.minuti_giocati < cfg.PVS_SCALE_MIN_MINUTES:
            continue
        off_index, def_index = p.production_indexes()
        per36 = 36.0 / stats.minuti_giocati
        sums['off'] += off_index
        sums['def'] += def_index
        sums['pts'] += stats.punti * per36
        sums['ast'] += stats.assist * per36
        sums['reb'] += stats.rimbalzi * per36
        count += 1
    if count < cfg.PVS_SCALE_MIN_PLAYERS:
        return neutral
    scales = {key: (cfg.PVS_REFERENCE[key] / (sums[key] / count)) if sums[key] > 0 else 1.0 for key in neutral}
    torneo._league_season_scales = (season, scales)
    return scales


def applica_regole_anni_opzioni_contratto(giocatore: Any, sync_salaries: bool = False):
    """
    Applies the automated NBA logic for Years Remaining and Options (PO / TO / Guaranteed):
    1. Veterans' golden rule (end of career):
       - Players aged 38+ (Stockton, Jordan, Malone, Robinson, Sabonis): 1 year remaining (all Guaranteed).
       - Players aged 35 to 37: at most 2 years remaining (if they had 3 or 4, they are reduced to 2; all Guaranteed).
    2. Rookie Scale rule (Team Option):
       - Players aged 23 or younger with 3- or 4-year contracts: must have a Team Option (TO).
    3. Superstar rule (Player Option):
       - Players with OVR >= 84 in their prime (26-32 years old) with at least 2 or 3 years of contract: Player Option (PO).
    4. The rest of the league:
       - All standard contracts for rotation players and ordinary veterans: Guaranteed (no PO, no TO).
    5. sync_salaries option:
       - Re-syncs the annual salary to the current salary cap according to the new realistic NBA tiers.
    """
    if not giocatore or not getattr(giocatore, 'contract', None):
        return
        
    c = giocatore.contract
    
    # 0. Optional syncing of salaries to the active Salary Cap
    if sync_salaries:
        is_rookie_scale = (giocatore.ovr < 84) and (giocatore.eta <= 22 or getattr(giocatore, 'is_rookie', False))
        if not is_rookie_scale or giocatore.ovr >= 84:
            new_sal = giocatore._calcola_valore_di_mercato()
            c.salario_annuale = round(new_sal, 2)
            c.salari_per_anno = [round(c.salario_annuale * (1.05 ** i), 2) for i in range(max(1, c.anni_rimanenti))]
    
    # 1. Veterans' golden rule (end of career)
    if giocatore.eta >= 38:
        c.anni_rimanenti = 1
        if hasattr(c, 'salari_per_anno') and c.salari_per_anno:
            c.salari_per_anno = c.salari_per_anno[:1]
        c.player_option = False
        c.team_option = False
        return
    elif 35 <= giocatore.eta <= 37:
        if c.anni_rimanenti > 2:
            c.anni_rimanenti = 2
            if hasattr(c, 'salari_per_anno') and c.salari_per_anno:
                c.salari_per_anno = c.salari_per_anno[:2]
        c.player_option = False
        c.team_option = False
        return

    # 2. Rookie Scale rule (Team Option)
    if giocatore.eta <= 23 and c.anni_rimanenti in [3, 4]:
        c.team_option = True
        c.player_option = False
        return

    # 3. Superstar rule (Player Option)
    if giocatore.ovr >= 84 and (26 <= giocatore.eta <= 32) and c.anni_rimanenti >= 2:
        c.player_option = True
        c.team_option = False
        return

    # 4. The rest of the league: all standard contracts for rotation players and ordinary veterans: Guaranteed
    c.player_option = False
    c.team_option = False

@dataclass
class Abilita:
    close_shot_rating: int; mid_range_shot_rating: int; three_point_shot_rating: int; free_throw_rating: int; shot_iq: int; passing_accuracy: int; ball_handling: int; passing_vision: int; interior_defense_rating: int; perimeter_defense_rating: int; steal_rating: int; block_rating: int; strength: int; speed: int; acceleration: int; vertical: int; stamina: int; offensive_rebound_rating: int; defensive_rebound_rating: int; dunk_rating: int = 40; draw_foul_rating: int = 50
    offensive_iq_rating: int = 65; defensive_iq_rating: int = 65; post_control_rating: int = 40
@dataclass
class Tendenze:
    touch_tendency: int; spot_up_shot_tendency: int; mid_range_shot_tendency: int; three_point_shot_tendency: int; drive_to_basket_tendency: int; post_up_tendency: int; pass_out_of_shot_tendency: int; dish_to_open_man_tendency: int; dunk_tendency: int = 25
    hero_ball_tendency: int = 50; putback_tendency: int = 50; roll_vs_pop_tendency: int = 50; foul_tendency: int = 50
    rebound_tendency: int = 50; playmaking_tendency: int = 50
    shot_tendency: int = 50

    def __getattr__(self, name: str):
        if name == 'shot_tendency':
            return getattr(self, 'touch_tendency', 50)
        raise AttributeError(f"'Tendenze' object has no attribute '{name}'")
@dataclass
class GameStats:
    punti: int = 0; rimbalzi: int = 0; assist: int = 0; punti_liberi: int = 0; tiri_tentati_2: int = 0; tiri_fatti_2: int = 0; tiri_tentati_3: int = 0; tiri_fatti_3: int = 0; tiri_liberi_tentati: int = 0; turnover: int = 0; steals: int = 0; blocks: int = 0; falli_commessi: int = 0; minuti_giocati: float = 0.0; secondi_giocati: int = 0; mvp_points: float = 0.0
    # Counted since 2026-11-15 (older games have none): offensive rebounds, made shots that drew an assist, shot
    # zones (rim = close shots and post-ups, mid = 2-point jumpers; 3s are tiri_*_3), clutch (CONFIG.ANALYTICS).
    oreb: int = 0; ast_fgm: int = 0; rim_fga: int = 0; rim_fgm: int = 0; mid_fga: int = 0; mid_fgm: int = 0
    clutch_pts: int = 0; clutch_fga: int = 0; clutch_fgm: int = 0; clutch_sec: int = 0
    def reset(self):
        for f in self.__dataclass_fields__: setattr(self, f, self.__class__.__dataclass_fields__[f].default)
@dataclass
class CumulativeStats:
    partite_giocate: int = 0; punti: int = 0; rimbalzi: int = 0; assist: int = 0; punti_liberi: int = 0; tiri_liberi_tentati: int = 0; tiri_tentati_2: int = 0; tiri_fatti_2: int = 0; tiri_tentati_3: int = 0; tiri_fatti_3: int = 0; turnover: int = 0; steals: int = 0; blocks: int = 0; falli_commessi: int = 0; minuti_giocati: float = 0.0; mvp_points: float = 0.0
    # Counted since 2026-11-15 (older games have none): offensive rebounds, made shots that drew an assist, shot
    # zones (rim = close shots and post-ups, mid = 2-point jumpers; 3s are tiri_*_3), clutch (CONFIG.ANALYTICS).
    oreb: int = 0; ast_fgm: int = 0; rim_fga: int = 0; rim_fgm: int = 0; mid_fga: int = 0; mid_fgm: int = 0
    clutch_pts: int = 0; clutch_fga: int = 0; clutch_fgm: int = 0; clutch_sec: int = 0
    def aggregate(self, game_stats: GameStats):
        self.partite_giocate += 1; self.minuti_giocati += game_stats.secondi_giocati / 60.0
        for key, value in game_stats.__dict__.items():
            if hasattr(self, key) and key not in ['partite_giocate', 'minuti_giocati', 'secondi_giocati']:
                setattr(self, key, getattr(self, key) + value)
    def reset(self):
        for f in self.__dataclass_fields__: setattr(self, f, self.__class__.__dataclass_fields__[f].default)

    @property
    def fg_pct(self) -> float:
        fga = self.tiri_tentati_2 + self.tiri_tentati_3
        fgm = self.tiri_fatti_2 + self.tiri_fatti_3
        return round((fgm / fga * 100), 1) if fga > 0 else 0.0

    @property
    def three_pct(self) -> float:
        return round((self.tiri_fatti_3 / self.tiri_tentati_3 * 100), 1) if self.tiri_tentati_3 > 0 else 0.0

    @property
    def ft_pct(self) -> float:
        return round((self.punti_liberi / self.tiri_liberi_tentati * 100), 1) if self.tiri_liberi_tentati > 0 else 0.0
@dataclass
class AdvancedStats:
    true_shooting_percentage: float = 0.0
    usage_rate: float = 0.0

    def reset(self):
        for f in self.__dataclass_fields__:
            setattr(self, f, self.__class__.__dataclass_fields__[f].default)
@dataclass
class PerformanceScores:
    offensive: float = 75.0
    defensive: float = 75.0
    total: float = 75.0
@dataclass
class Coach:
    nome: str
    stile_gioco: str
    ovr_offensivo: int
    ovr_difensivo: int
    eta: int
    potenziale: int # The maximum OVR this coach can reach
    player_development: int = 75 # Rating 50-99: Young player development and rookie progression
    tactical_acumen: int = 75    # Rating 50-99: Aggiustamenti in-game, clutch execution, timeout
    discipline_culture: int = 75 # Rating 50-99: Locker room management, chemistry, morale
    contratto_anni_rimanenti: int = 3
    contratto_totale_anni: int = 3
    salario: float = 3.5 # In millions of $ (e.g. 3.5 = $3.5M/year)
    job_security: float = 75.0 # 0-100 score
    years_with_current_team: int = 1
    xp: int = 0
    level: int = 1
    badge_points: int = 0
    rpg_xp: int = 0
    rpg_level: int = 1
    skill_points: int = 0
    unlocked_nodes: list = field(default_factory=list)
    badges: dict = field(default_factory=lambda: {
        "Rookie Developer": 0,
        "Defense Guru": 0,
        "Tactician": 0,
        "Fitness Specialist": 0,
        "Motivator": 0,
        "Clutch Master": 0
    })
    historical_wins: int = 0
    historical_losses: int = 0
    playoff_appearances: int = 0
    championships: int = 0
    coty_awards: int = 0
    past_teams: list = field(default_factory=list)
    specialization: str = "Tactical Strategist"
    offensive_system: str = ""
    defensive_scheme: str = ""
    preferred_pace: str = ""

    def __post_init__(self):
        if not self.offensive_system:
            self.offensive_system = self.offensive_system_label
        if not self.defensive_scheme:
            self.defensive_scheme = self.defensive_scheme_label
        if not self.preferred_pace:
            self.preferred_pace = self.preferred_pace_label

    @property
    def ovr_totale(self) -> int:
        return round((self.ovr_offensivo * 0.35 + self.ovr_difensivo * 0.35 + self.player_development * 0.15 + self.tactical_acumen * 0.15))

    @property
    def career_win_pct(self) -> float:
        tot = self.historical_wins + self.historical_losses
        return round(self.historical_wins / tot, 3) if tot > 0 else 0.500

    @property
    def job_security_label(self) -> str:
        if self.job_security >= 85: return "Rock Solid"
        if self.job_security >= 65: return "Secure"
        if self.job_security >= 45: return "Stable"
        if self.job_security >= 28: return "Moderate Pressure"
        if self.job_security >= 15: return "Hot Seat"
        return "Severe Danger"

    @property
    def offensive_system_label(self) -> str:
        if self.offensive_system:
            return self.offensive_system
        presets = {
            "Pace & Space": "Pace & Space 5-Out Motion",
            "Run and Gun": "Seven Seconds or Less / Fast Break",
            "Fast Break Offense": "Seven Seconds or Less / Transition Attack",
            "Triangle Offense": "Triangle Continuity & Mid-Post Reads",
            "Perimeter-centric": "Spread Pick-and-Roll & Perimeter Blitz",
            "Post Play Dominance": "Inside-Out Low Post Feeds & Cutters",
            "Twin Towers": "Twin Towers Paint Overload & High-Low",
            "Grit & Grind": "Half-Court Physical Grinding & Post Isolation",
            "Defensive Minded": "Conservative Ball Control & Clock Management",
            "Man-to-Man Lockdown": "Secondary Break & PnR Execution",
            "Point Guard Maestro": "High Pick-and-Roll PG Orchestration",
            "Small Ball Strategy": "5-Out Drive & Kick / Mismatch Hunting",
            "System Basketball": "Motion Equalizer & Continuous Ball Movement",
            "Balanced Offense": "Balanced Motion & Versatile Sets"
        }
        return presets.get(self.stile_gioco, "Balanced Motion & Versatile Sets")

    @property
    def defensive_scheme_label(self) -> str:
        if self.defensive_scheme:
            return self.defensive_scheme
        presets = {
            "Pace & Space": "Switch Everything & Perimeter Lockdown",
            "Run and Gun": "Aggressive Pressure & Transition Deny",
            "Fast Break Offense": "Pressure Trap & Turnover Havoc",
            "Triangle Offense": "Disciplined Help & Strong-Side Overload",
            "Perimeter-centric": "Drop Coverage & Corner Help",
            "Post Play Dominance": "Drop Coverage & Paint Wall",
            "Twin Towers": "Dual Rim Protection & Paint Lockdown",
            "Grit & Grind": "Grit & Grind Physical Half-Court Lockdown",
            "Defensive Minded": "Aggressive Man-to-Man Half-Court Lockdown",
            "Man-to-Man Lockdown": "Full-Court Ball Denial & Man Lockdown",
            "Point Guard Maestro": "Drop Coverage & Wing Help",
            "Small Ball Strategy": "Aggressive Switch & Blitz Scheme",
            "System Basketball": "Disciplined Help & Recover",
            "Balanced Offense": "Standard Man-to-Man Fundamentals"
        }
        return presets.get(self.stile_gioco, "Standard Man-to-Man Fundamentals")

    @property
    def preferred_pace_label(self) -> str:
        if self.preferred_pace:
            return self.preferred_pace
        presets = {
            "Pace & Space": "Fast (101-103 Pace)",
            "Run and Gun": "Very Fast (104+ Pace)",
            "Fast Break Offense": "Very Fast (104+ Pace)",
            "Triangle Offense": "Methodical / Slow (93-95 Pace)",
            "Perimeter-centric": "Fast (100-102 Pace)",
            "Post Play Dominance": "Methodical / Slow (92-94 Pace)",
            "Twin Towers": "Methodical / Slow (92-94 Pace)",
            "Grit & Grind": "Very Slow (90-93 Pace)",
            "Defensive Minded": "Slow (93-96 Pace)",
            "Man-to-Man Lockdown": "Moderate (96-98 Pace)",
            "Point Guard Maestro": "Moderate (97-99 Pace)",
            "Small Ball Strategy": "Fast (101-104 Pace)",
            "System Basketball": "Moderate (97-100 Pace)",
            "Balanced Offense": "Balanced Tempo (96-99 Pace)"
        }
        return presets.get(self.stile_gioco, "Balanced Tempo (96-99 Pace)")

    def add_xp(self, amount: int) -> int:
        """Legacy helper for coach progression."""
        self.xp += amount
        leveled_up = 0
        while self.xp >= self.level * 500 and self.level < 20:
            self.xp -= self.level * 500
            self.level += 1
            self.badge_points += 1
            leveled_up += 1
        return leveled_up

    def calcola_roster_fit(self, squadra: Any) -> dict:
        """
        Computes the real tactical compatibility between the Head Coach's philosophy and the roster.
        Evaluates offensive schemes, defensive schemes, pace and player-by-player fit.
        """
        if not squadra or not getattr(squadra, 'roster', None):
            return {
                "fit_score": 75,
                "grade": "B",
                "rating": "Solid Fit",
                "label": f"{self.stile_gioco} (75%)",
                "net_impact": "+0.8 Net Rtg",
                "net_rating_mod": 0.8,
                "offensive_fit_score": 75,
                "defensive_fit_score": 75,
                "offensive_system": self.offensive_system_label,
                "defensive_scheme": self.defensive_scheme_label,
                "preferred_pace": self.preferred_pace_label,
                "synergies": ["Baseline system execution"],
                "red_flags": [],
                "player_fits": []
            }

        roster = squadra.roster
        # Starters: top 5 by minutes if defined, otherwise top 5 by ovr
        sorted_by_min = sorted(roster, key=lambda p: getattr(p, 'minutaggio', 0), reverse=True)
        if sum(getattr(p, 'minutaggio', 0) for p in sorted_by_min[:5]) > 100:
            starters = sorted_by_min[:5]
        else:
            starters = sorted(roster, key=lambda p: p.ovr, reverse=True)[:5]

        rotation = sorted(roster, key=lambda p: p.ovr, reverse=True)[:10]

        fit_score = 72
        off_fit = 72
        def_fit = 72
        synergies = []
        red_flags = []

        stile = self.stile_gioco

        # --- 1. EVALUATION: HIGH-TEMPO TRANSITION / RUN AND GUN / 7 SECONDS OR LESS ---
        if stile in ["Run and Gun", "Fast Break Offense", "Small Ball Strategy"]:
            # Demands transition speed; slow, heavy low-post bigs are a severe tactical bottleneck
            starting_slow_bigs = [
                p for p in starters
                if getattr(p, 'ruolo', '') in ['C', 'PF']
                and getattr(getattr(p, 'abilita', None), 'speed', 70) <= 66
            ]

            if len(starting_slow_bigs) >= 2:
                fit_score -= 26
                off_fit -= 28
                p1_spd = getattr(starting_slow_bigs[0].abilita, 'speed', 60)
                p2_spd = getattr(starting_slow_bigs[1].abilita, 'speed', 62)
                red_flags.append(
                    f"Pace Drag: Starting frontcourt ({starting_slow_bigs[0].nome} SPD {p1_spd}, {starting_slow_bigs[1].nome} SPD {p2_spd}) cannot sustain a 7-Seconds-or-Less transition tempo."
                )
            elif len(starting_slow_bigs) == 1:
                fit_score -= 12
                off_fit -= 14
                p_spd = getattr(starting_slow_bigs[0].abilita, 'speed', 62)
                red_flags.append(
                    f"Transition Friction: Starting big {starting_slow_bigs[0].nome} (Speed {p_spd}) trails fast breaks and slows early offensive flow."
                )

            fast_guards = [
                p for p in rotation
                if getattr(p, 'ruolo', '') in ['PG', 'SG']
                and getattr(getattr(p, 'abilita', None), 'speed', 70) >= 80
            ]
            if len(fast_guards) >= 2:
                fit_score += 16
                off_fit += 18
                synergies.append(
                    f"Fast-Break Engine: Electric backcourt ({', '.join(g.nome for g in fast_guards[:2])}) pushes the break before opposing defenses set up."
                )

        # --- 2. EVALUATION: PACE & SPACE / PERIMETER-CENTRIC ---
        elif stile in ["Pace & Space", "Perimeter-centric"]:
            shooters = [
                p for p in rotation
                if getattr(getattr(p, 'abilita', None), 'three_point_shot_rating', 70) >= 78
            ]
            non_shooters = [
                p for p in starters
                if getattr(getattr(p, 'abilita', None), 'three_point_shot_rating', 70) < 70
            ]

            if len(shooters) >= 4:
                fit_score += 20
                off_fit += 22
                synergies.append(
                    f"Floor Spacing: {len(shooters)} rotation players shoot with high perimeter gravity, maximizing driving lanes."
                )
            elif len(shooters) <= 1:
                fit_score -= 18
                off_fit -= 20
                red_flags.append("Insufficient Perimeter Gravity: Lack of reliable 3PT threats lets opponents pack the paint.")

            if len(non_shooters) >= 2:
                fit_score -= 14
                off_fit -= 16
                red_flags.append(
                    f"Spacing Clog: Multiple starters ({', '.join(p.nome for p in non_shooters[:2])}) lack outside shooting threat."
                )

        # --- 3. EVALUATION: TWIN TOWERS / POST PLAY DOMINANCE ---
        elif stile in ["Twin Towers", "Post Play Dominance"]:
            dominant_bigs = [
                p for p in rotation
                if getattr(p, 'ruolo', '') in ['C', 'PF']
                and getattr(getattr(p, 'abilita', None), 'close_shot_rating', 70) >= 80
                and getattr(getattr(p, 'abilita', None), 'strength', 70) >= 78
            ]
            if len(dominant_bigs) >= 2:
                fit_score += 25
                off_fit += 22
                def_fit += 24
                synergies.append(
                    f"Interior Hegemony: Dominant low-post duo ({dominant_bigs[0].nome} & {dominant_bigs[1].nome}) overwhelms opponents inside and controls the paint."
                )
            elif len(dominant_bigs) == 0:
                fit_score -= 25
                off_fit -= 24
                red_flags.append(
                    "Lacks Low-Post Anchor: Tactical scheme is built around low-post gravity, but roster has no dominant post bigs."
                )

        # --- 4. EVALUATION: POINT GUARD MAESTRO ---
        elif stile in ["Point Guard Maestro"]:
            maestros = [
                p for p in rotation
                if getattr(p, 'ruolo', '') in ['PG']
                and getattr(getattr(p, 'abilita', None), 'passing_vision', 70) >= 80
                and getattr(getattr(p, 'abilita', None), 'ball_handling', 70) >= 80
            ]
            if maestros:
                fit_score += 18
                off_fit += 20
                synergies.append(
                    f"Floor General Maestro: {maestros[0].nome} conducts high pick-and-roll sets with elite poise and court vision."
                )
            else:
                fit_score -= 16
                off_fit -= 18
                red_flags.append("Playmaking Deficit: No elite floor general to orchestrate heavy pick-and-roll volume.")

        # --- 5. EVALUATION: GRIT & GRIND / DEFENSIVE MINDED / MAN-TO-MAN LOCKDOWN ---
        elif stile in ["Grit & Grind", "Defensive Minded", "Man-to-Man Lockdown"]:
            stoppers = [
                p for p in starters
                if getattr(getattr(p, 'abilita', None), 'perimeter_defense_rating', 70) >= 78
                or getattr(getattr(p, 'abilita', None), 'interior_defense_rating', 70) >= 80
            ]
            defensive_turnstiles = [
                p for p in starters
                if getattr(getattr(p, 'abilita', None), 'perimeter_defense_rating', 70) < 68
                and getattr(getattr(p, 'abilita', None), 'interior_defense_rating', 70) < 68
            ]
            if len(stoppers) >= 3:
                fit_score += 20
                def_fit += 24
                synergies.append(
                    f"Lockdown Defensive Identity: Physical stoppers ({', '.join(s.nome for s in stoppers[:3])}) enforce a stifling half-court presence."
                )
            if len(defensive_turnstiles) >= 2:
                fit_score -= 16
                def_fit -= 20
                red_flags.append(
                    f"Defensive Vulnerability: {', '.join(w.nome for w in defensive_turnstiles[:2])} are vulnerable to being hunted in physical matchups."
                )

        # --- 6. EVALUATION: SYSTEM BASKETBALL / TRIANGLE OFFENSE ---
        elif stile in ["Triangle Offense", "System Basketball"]:
            high_iq_passers = [
                p for p in rotation
                if getattr(getattr(p, 'abilita', None), 'shot_iq', 70) >= 78
                and getattr(getattr(p, 'abilita', None), 'passing_accuracy', 70) >= 76
            ]
            if len(high_iq_passers) >= 4:
                fit_score += 18
                off_fit += 20
                synergies.append("System Discipline: High Shot IQ and crisp passing across positions keep the ball moving.")
            else:
                fit_score -= 10
                red_flags.append("Ball-Stopping Tendencies: Several key players lack the continuous motion and passing instincts required.")

        # --- 7. EVALUATION: BALANCED OFFENSE ---
        else:
            fit_score = 78
            synergies.append("Tactical Adaptability: Balanced scheme flexes to maximize roster strengths without severe structural liabilities.")

        # Ensure at least 1 synergy if none added
        if not synergies:
            synergies.append("Standard Tactical Execution: Players are performing system assignments reliably.")

        fit_score = max(35, min(99, fit_score))
        off_fit = max(35, min(99, off_fit))
        def_fit = max(35, min(99, def_fit))

        # Assign Grade and Net Rating Impact
        if fit_score >= 90:
            grade = "S"
            rating_txt = "Elite Synergy"
            net_mod = 2.4
        elif fit_score >= 80:
            grade = "A"
            rating_txt = "Strong Fit"
            net_mod = 1.8
        elif fit_score >= 70:
            grade = "B"
            rating_txt = "Solid Fit"
            net_mod = 0.8
        elif fit_score >= 60:
            grade = "C"
            rating_txt = "Neutral Fit"
            net_mod = 0.0
        elif fit_score >= 50:
            grade = "D"
            rating_txt = "Tactical Friction"
            net_mod = -1.4
        else:
            grade = "F"
            rating_txt = "Severe Mismatch"
            net_mod = -2.5

        # --- PLAYER-BY-PLAYER BREAKDOWN ---
        player_fits = []
        for p in roster:
            abil = getattr(p, 'abilita', None)
            p_3pt = getattr(abil, 'three_point_shot_rating', 70) if abil else 70
            p_spd = getattr(abil, 'speed', 70) if abil else 70
            p_str = getattr(abil, 'strength', 70) if abil else 70
            p_int = getattr(abil, 'interior_defense_rating', 70) if abil else 70
            p_per = getattr(abil, 'perimeter_defense_rating', 70) if abil else 70
            p_close = getattr(abil, 'close_shot_rating', 70) if abil else 70
            p_vis = getattr(abil, 'passing_vision', 70) if abil else 70

            p_fit = 75
            p_note = "Standard system execution."

            is_big = getattr(p, 'ruolo', '') in ['C', 'PF']
            is_guard = getattr(p, 'ruolo', '') in ['PG', 'SG']

            if stile in ["Run and Gun", "Fast Break Offense", "Small Ball Strategy"]:
                if is_big and p_spd <= 66:
                    p_fit = 42
                    p_note = f"Severe pace drag: low speed ({p_spd}) cannot keep up with high-octane 7SOL transition."
                elif p_spd >= 80:
                    p_fit = 92
                    p_note = f"Ideal transition runner: high speed ({p_spd}) punishes backpedaling defenses."
                else:
                    p_fit = 74
            elif stile in ["Pace & Space", "Perimeter-centric"]:
                if p_3pt >= 80:
                    p_fit = 96
                    p_note = f"Elite spacing gravity: 3PT rating ({p_3pt}) bends defenses outward."
                elif p_3pt < 68 and not is_big:
                    p_fit = 48
                    p_note = f"Spacing liability: non-shooter ({p_3pt} 3PT) allows defenses to pack the paint."
                elif is_big and p_3pt < 65:
                    p_fit = 68
                    p_note = "Traditional interior presence; provides roll-gravity but no pick-and-pop spacing."
                else:
                    p_fit = 78
            elif stile in ["Twin Towers", "Post Play Dominance"]:
                if is_big and p_close >= 80 and p_str >= 78:
                    p_fit = 96
                    p_note = f"Ideal interior force: dominant low-post scoring ({p_close}) and physical strength ({p_str})."
                elif is_big and p_str < 70:
                    p_fit = 54
                    p_note = "Undersized/lacks physical strength for low-post battles."
                elif is_guard and p_vis >= 78:
                    p_fit = 88
                    p_note = "Entry-pass distributor: excels at feeding bigs on high-low reads."
                else:
                    p_fit = 72
            elif stile in ["Point Guard Maestro"]:
                if is_guard and p_vis >= 80:
                    p_fit = 95
                    p_note = f"Floor general: exceptional passing vision ({p_vis}) orchestrating high PnR sets."
                elif is_guard and p_vis < 72:
                    p_fit = 58
                    p_note = "Secondary scorer; lacks elite playmaking vision to conduct full offense."
                else:
                    p_fit = 76
            elif stile in ["Grit & Grind", "Defensive Minded", "Man-to-Man Lockdown"]:
                if (p_per >= 78 or p_int >= 80) and p_str >= 74:
                    p_fit = 94
                    p_note = "Defensive stopper: physical containment and high-effort half-court resistance."
                elif p_per < 68 and p_int < 68:
                    p_fit = 46
                    p_note = "Defensive liability in physical man-to-man half-court schemes."
                else:
                    p_fit = 75
            else:
                p_fit = 78
                p_note = "Adaptable versatility in balanced system sets."

            p_fit = max(40, min(99, p_fit))

            if p_fit >= 85:
                badge = "Ideal Fit"
                badge_color = "#10b981"
            elif p_fit >= 70:
                badge = "Solid Fit"
                badge_color = "#3b82f6"
            elif p_fit >= 55:
                badge = "Tactical Friction"
                badge_color = "#f59e0b"
            else:
                badge = "Severe Mismatch"
                badge_color = "#ef4444"

            player_fits.append({
                "player_id": getattr(p, 'id', p.nome),
                "name": p.nome,
                "position": getattr(p, 'ruolo', 'F'),
                "ovr": p.ovr,
                "fit_score": p_fit,
                "badge": badge,
                "badge_color": badge_color,
                "stats_preview": {
                    "3PT": p_3pt,
                    "SPD": p_spd,
                    "DEF": p_int if is_big else p_per
                },
                "notes": p_note
            })

        # Sort player fits by starter status / OVR
        player_fits.sort(key=lambda x: x["ovr"], reverse=True)

        return {
            "fit_score": fit_score,
            "grade": grade,
            "rating": rating_txt,
            "label": f"{self.stile_gioco} ({fit_score}%)",
            "net_impact": f"{'+' if net_mod >= 0 else ''}{net_mod:.1f} Net Rtg",
            "net_rating_mod": net_mod,
            "offensive_fit_score": off_fit,
            "defensive_fit_score": def_fit,
            "offensive_system": self.offensive_system_label,
            "defensive_scheme": self.defensive_scheme_label,
            "preferred_pace": self.preferred_pace_label,
            "synergies": synergies,
            "red_flags": red_flags,
            "player_fits": player_fits
        }


@dataclass
class TacticalPlan:
    """Advanced tactical game plan for the match."""
    defensive_matchups: Dict[str, str] = field(default_factory=dict) # opponent_player_id/name -> defender_player_id/name
    double_team_targets: List[str] = field(default_factory=list) # opponent_player_ids/names to double team
    pnr_coverage: str = "DROP" # DROP, SWITCH, BLITZ, HEDGE
    defensive_scheme: str = "MAN_TO_MAN" # MAN_TO_MAN, ZONE_2_3, FULL_PRESS
    offensive_focus: str = "BALANCED" # POUND_PAINT, HUNT_THREES, PACE_AND_SPACE_5OUT, POST_FEED, FEED_HOT_HAND, BALANCED
    pace_preference: str = "BALANCED" # 7_SECONDS_OR_LESS, BALANCED, GRIT_AND_GRIND
    stagger_stars: bool = False
    foul_trouble_bench_threshold: int = 3
    # Offensive Hierarchy & Shot Options
    offensive_first_option: Optional[str] = None   # 1st designated shot option
    offensive_second_option: Optional[str] = None  # 2nd designated shot option
    offensive_third_option: Optional[str] = None   # 3rd designated shot option
    player_touch_modifiers: Dict[str, str] = field(default_factory=dict) # player_name -> "GO_TO_GUY" | "ROOKIE_FOCUS" | "SECONDARY" | "ROLE_PLAYER" | "DEFENSE_ONLY"
    # Per-opponent defense, set on the Opponent tab and used only against that team:
    # team name -> {"matchups": {their_player_name: my_defender_name}, "double_teams": [their_player_name, ...]}
    opponent_plans: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def plan_vs(self, team_name: str) -> Dict[str, Any]:
        """Matchups and double-teams against one team (empty when none were set)."""
        plan = self.opponent_plans.get(team_name) or {}
        return {"matchups": dict(plan.get("matchups") or {}), "double_teams": list(plan.get("double_teams") or [])}

@dataclass
class BoardObjective:
    id: str
    title: str
    description: str
    category: str = "Competitive" # "Financial", "Competitive", "Roster", "Draft"
    target_value: float = 0.0
    current_value: float = 0.0
    status: str = "Pending" # "Pending", "Completed", "Failed"
    impact_approval: float = 10.0

@dataclass
class GMContract:
    salary_per_year: float = 5.0
    years_remaining: int = 4
    total_years: int = 4
    can_extend: bool = False
    extension_offered: Optional[Dict] = None

@dataclass
class GMBadge:
    id: str
    name: str
    description: str
    icon: str = "Award"
    level: int = 1 # 1: Bronze, 2: Silver, 3: Gold

@dataclass
class GMAchievement:
    id: str
    title: str
    description: str
    icon: str = "Trophy"
    unlocked: bool = False
    date_unlocked: Optional[str] = None

@dataclass
class UserProfileGM:
    name: str = "General Manager"
    reputation_style: str = "Balanced Builder"
    contract: GMContract = field(default_factory=GMContract)
    badges: List[GMBadge] = field(default_factory=list)
    achievements: List[GMAchievement] = field(default_factory=list)
    career_wins: int = 0
    career_losses: int = 0
    titles_won: int = 0
    seasons_managed: int = 0
    teams_managed_history: List[Dict] = field(default_factory=list)
    current_team_name: Optional[str] = None
    season_reports: List[Dict] = field(default_factory=list)
    rpg_xp: int = 0
    rpg_level: int = 1
    skill_points: int = 2
    unlocked_nodes: List[str] = field(default_factory=list)
    prestige_score: float = 65.0

@dataclass
class BoardProfile:
    owner_name: str = "Team Ownership"
    personality: str = "Bilanciato" # one of CONFIG.ECONOMY.OWNER_TYPES
    patience_level: int = 3 # 1 (Low) - 5 (Very high)
    spending_attitude: int = 3 # 1 (Frugal) - 5 (Unlimited)
    approval_rating: float = 75.0
    status_label: str = "Stable" # "Untouchable", "Stable", "Under Review", "Hot Seat", "Fired"
    objectives: List[BoardObjective] = field(default_factory=list)
    board_messages: List[Dict] = field(default_factory=list)
    seasons_with_team: int = 0


@dataclass
class Giocatore:
    
    nome: str; ruolo: str;  eta:int; potenziale:int; abilita: Abilita; tendenze: Tendenze
    valutazione: int
     # This value will be overwritten, but is needed for the initial load
    squadra: Optional['Squadra'] 
    valutazioni_posizionali: Dict[str, int] = field(default_factory=dict) # Esempio: {'PG': 75, 'SG': 88, ...}
    provenance: str = "N/A"
    pedigree: str = "Veteran"
    db_id: Optional[int] = None
    secondi_in_panchina_consecutivi: int = field(init=False, default=0)
    is_flight_risk: bool = field(init=False, default=False)
    walks_away: str = field(init=False, default="")   # why he will not re-sign ("asked out" / "hopeless team"), or ""
    # Trade requests (core/front_office/trade_requests.py): saved, NOT reset by reset_for_season.
    frustration: float = field(init=False, default=0.0)
    trade_request: bool = field(init=False, default=False)
    trade_request_since: str = field(init=False, default="")   # "Season 2004" / "Summer 2004", or ""
    trade_request_weeks: int = field(init=False, default=0)      # weekly checks with the request open
    trade_block_by_request: bool = field(init=False, default=False)   # the request put him on the user's block
    morale: int = field(init=False, default=75) # Starts from a neutral-positive value
    fvs: int = field(init=False, default=70) # Franchise Value Score
    contract: Optional[Contract] = None; game_stats: GameStats = field(default_factory=GameStats)
    season_stats: CumulativeStats = field(default_factory=CumulativeStats); playoff_stats: CumulativeStats = field(default_factory=CumulativeStats);advanced_game_stats: AdvancedStats = field(default_factory=AdvancedStats)
    minuti_target: int = field(init=False, default=0); energia: int = field(init=False); fatica: int = field(init=False, default=0)
    infortunato: bool = field(init=False, default=False); giorni_infortunio_rimanenti: int = field(init=False, default=0)
    infortunio_nome: Optional[str] = field(init=False, default=None)
    is_day_to_day: bool = field(init=False, default=False)
    infortunio_impatto: float = field(init=False, default=0.0)
    serie_tiro: int = field(init=False, default=0); serie_errore: int = field(init=False, default=0)
    temp_abilita: Optional[Abilita] = field(init=False, default=None)
    temp_tendenze: Optional[Tendenze] = field(init=False, default=None)
    performance_scores: PerformanceScores = field(default_factory=PerformanceScores)
    plus_minus: int = field(init=False, default=0)
    game_form_factor: float = field(init=False, default=1.0) # <-- NEW LINE
    _score_at_check_in: int = field(init=False, default=0) # Score of the player's own team
    _score_at_check_in_opp: int = field(init=False, default=0) # Opponent's score
    stamina_stagionale: float = field(init=False, default=100.0)
    # We also add a flag to handle forced rest ("Load Management")
    is_resting_today: bool = field(init=False, default=False)
     # ## NEW ATTRIBUTES ##
    is_untouchable: bool = False
    anni_nella_squadra: int = 0
    is_rookie: bool = False
    on_trade_block: bool = False
    college_stats: Optional[dict] = field(default=None)
    scouting_progress: float = 10.0
    draft_stock_mod: float = 0.0
    giorni_cooldown_scambio: int = 0
    premi: List[str] = field(default_factory=list)
    anelli_vinti: int = 0
    career_log: List[Dict[str, Any]] = field(default_factory=list)
    ovr_history: List[Dict[str, Any]] = field(default_factory=list)
    _trade_value_cache: Optional[float] = field(init=False, default=None)

    def __repr__(self):
        # The generated dataclass repr walked the team, career logs and history and ran out of memory.
        team = getattr(getattr(self, 'squadra', None), 'nome', None)
        return f"Giocatore({self.nome!r}, {self.ruolo}, OVR {self.valutazione}, team={team!r})"

    def record_ovr_milestone(self, season: int, year: Optional[int] = None, note: str = ""):
        """Records the player's OVR progression year after year."""
        if not hasattr(self, 'ovr_history') or self.ovr_history is None:
            self.ovr_history = []
            
        team_name = self.squadra.nome if hasattr(self, 'squadra') and self.squadra else 'Free Agent'
        
        # If the season is already present, update the values
        for entry in self.ovr_history:
            if entry.get('season') == season:
                entry['ovr'] = self.valutazione
                entry['potenziale'] = self.potenziale
                entry['age'] = self.eta
                entry['team'] = team_name
                if note: entry['note'] = note
                return
                
        prev_ovr = self.ovr_history[-1]['ovr'] if self.ovr_history else self.valutazione
        delta = self.valutazione - prev_ovr
        
        self.ovr_history.append({
            "season": season,
            "year": year or (2024 + season),
            "age": self.eta,
            "ovr": self.valutazione,
            "potenziale": self.potenziale,
            "team": team_name,
            "delta": delta,
            "note": note
        })

    def add_career_log(self, event_type: str, title: str, description: str, season: int = 1, day: int = 0, icon: str = '📌', team: Optional[str] = None):
        """Records a memorable moment or historical event in the player's career."""
        if not hasattr(self, 'career_log') or self.career_log is None:
            self.career_log = []
        team_name = team or (self.squadra.nome if hasattr(self, 'squadra') and self.squadra else 'Free Agent')
        self.career_log.append({
            "season": season,
            "day": day,
            "type": event_type,  # 'injury', 'performance', 'clutch', 'award', 'trade', 'contract', 'milestone'
            "title": title,
            "description": description,
            "icon": icon,
            "team": team_name,
            "age": self.eta
        })

    def invalidate_trade_value_cache(self):
        """Invalidates cached trade value when player ratings, contract or team changes."""
        self._trade_value_cache = None
    @property
    def ovr(self) -> int:
        """
        This property is now just an alias for `valutazione`.
        All the code that needs a "general" OVR (trades, awards, etc.)
        will use this, which is the stable and correct value.
        """
        return self.valutazione

    @property
    def has_fouled_out(self) -> bool: return self.game_stats.falli_commessi >= CONFIG.COACHING.FOUL_OUT_LIMIT
    @property
    def energia_iniziale(self) -> int: return int(self.abilita.stamina * 3.8)

    def __post_init__(self): 
        self.energia = self.energia_iniziale
        self._calibra_e_calcola_posizioni()
        
    def production_indexes(self) -> Tuple[float, float]:
        """This season's offense and defense production per 36 minutes (the raw inputs of the PVS)."""
        stats = self.season_stats
        minuti = stats.minuti_giocati if stats.minuti_giocati > 0 else 1
        pts_36 = (stats.punti / minuti) * 36
        ast_36 = (stats.assist / minuti) * 36
        to_36 = (stats.turnover / minuti) * 36
        # Season TS% from the totals (advanced_game_stats only holds the last game: one cold night moved the PVS)
        shots = (stats.tiri_tentati_2 + stats.tiri_tentati_3) + 0.44 * stats.tiri_liberi_tentati
        ts_pct = (stats.punti / (2 * shots) * 100) if shots > 0 else 0.0
        ts_factor = (ts_pct / 58.0) if ts_pct > 0 else 0.85
        off_index = (pts_36 * ts_factor) + (ast_36 * 1.6) - (to_36 * 1.8)
        stocks_36 = ((stats.steals + stats.blocks) / minuti) * 36
        def_reb_36 = ((stats.rimbalzi * 0.75) / minuti) * 36
        def_index = (stocks_36 * 4.5) + (def_reb_36 * 1.5)
        return off_index, def_index

    def calcola_pvs(self, scales: Optional[Dict[str, float]] = None):
        """Performance score of the season. `scales` (league_season_scales) puts the production on the reference
        era's level: without it a modern season's pace lifted every PVS over the OVR and fed OVR inflation."""
        stats = self.season_stats
        if stats.partite_giocate < 5 or stats.minuti_giocati < 100:
            base_score = float(self.ovr)
            self.performance_scores = PerformanceScores(base_score, base_score, base_score)
            return

        off_index, def_index = self.production_indexes()
        if scales:
            off_index *= scales.get('off', 1.0)
            def_index *= scales.get('def', 1.0)

        # --- 1. Offense Production Index (OPI) ---
        if off_index > 20.0:
            off_pvs = 85.0 + (off_index - 20.0) * 1.20
        elif off_index > 13.0:
            off_pvs = 75.0 + (off_index - 13.0) * 1.40
        else:
            off_pvs = 70.0 + max(0.0, off_index - 8.0) * 1.00
        
        # --- 2. Defense Production Index (DPI) ---
        raw_def_pvs = 75.0 + (def_index - 13.0) * 0.90
        
        base_def_rating = max(self.abilita.perimeter_defense_rating, self.abilita.interior_defense_rating)
        def_pvs = max(raw_def_pvs, float(base_def_rating) - 4.0)
        
        # --- 3. Final Score Assignment ---
        self.performance_scores.offensive = max(40, min(99, round(off_pvs, 1)))
        self.performance_scores.defensive = max(40, min(99, round(def_pvs, 1)))
        
        # Total PVS: OVR sets the base (20%), Production makes the difference (55% OFF, 25% DEF)
        total_pvs = (self.ovr * 0.20) + (self.performance_scores.offensive * 0.55) + (self.performance_scores.defensive * 0.25)
        self.performance_scores.total = max(40, min(99, round(total_pvs, 1)))

    def change_role(self, new_role: str) -> None:
        """The user moves the player to another role (Rotations > Roles): he plays it in games, and his OVR becomes
        `ovr_at_role` (his rating there, at most CONFIG.POSITIONS.ROLE_CHANGE_MAX_GAIN above his original OVR).
        Potential moves by the same amount. `ruolo_originale` and `role_ovr_shift` (OVR now - OVR at the original role)
        keep the way back exact, through progression too."""
        from core.roles import ROLES
        role = normalize_role(new_role)
        if role not in ROLES:
            raise ValueError(f"Unknown role: {new_role!r}")
        if role == self.ruolo:
            return
        base = int(self.valutazione) - int(getattr(self, 'role_ovr_shift', 0) or 0)
        new = self.ovr_at_role(role)
        if not getattr(self, 'ruolo_originale', None):
            self.ruolo_originale = self.ruolo
        self.potenziale = max(40, min(99, int(self.potenziale) + new - int(self.valutazione)))
        self.valutazione = new
        self.ruolo = role
        self.role_ovr_shift = new - base
        if self.ruolo_originale == role:   # back where he started
            self.ruolo_originale = None
            self.role_ovr_shift = 0
        self._calibra_e_calcola_posizioni()
        self.invalidate_trade_value_cache()

    def _calibra_e_calcola_posizioni(self):
        """The ratings at all five roles (_role_ratings, CONFIG.POSITIONS); the current role shows his OVR."""
        if self.ruolo:
            self.ruolo = normalize_role(self.ruolo)
        if getattr(self, 'ruolo_secondario', None):
            self.ruolo_secondario = normalize_role(self.ruolo_secondario)

        self.valutazioni_posizionali = self._role_ratings()

        # Drop legacy Italian keys (PM/G/AP/AG) that older saves may still carry
        for legacy in ('PM', 'G', 'AP', 'AG'):
            self.valutazioni_posizionali.pop(legacy, None)

        self.valutazioni_posizionali[self.ruolo] = self.valutazione

    def _role_ratings(self) -> Dict[str, int]:
        """His rating at each role, anchored on his OVR at his original role (CONFIG.POSITIONS): base OVR plus
        OVR_SPREAD x (how he compares with the real players at that role - how he compares at his original role)."""
        pos_cfg = CONFIG.POSITIONS
        weights = pos_cfg.ROLE_WEIGHTS
        origin = normalize_role(getattr(self, 'ruolo_originale', None) or self.ruolo) or 'SF'
        base = int(self.valutazione) - int(getattr(self, 'role_ovr_shift', 0) or 0)

        def z(role):
            mean, sd = pos_cfg.RAW_REFERENCE[role]
            raw = sum(getattr(self.abilita, ab, 50) * w for ab, w in weights[role].items())
            return (raw - mean) / sd if sd > 0 else 0.0

        z_origin = z(origin if origin in weights else 'SF')
        return {role: max(pos_cfg.RATING_MIN, min(99, int(round(base + pos_cfg.OVR_SPREAD * (z(role) - z_origin)))))
                for role in weights}

    def ovr_at_role(self, role: str) -> int:
        """The OVR he would have at `role` after a role change: his rating there, at most ROLE_CHANGE_MAX_GAIN above his
        OVR at his original role (and exactly that OVR back at the original role)."""
        role = normalize_role(role)
        base = int(self.valutazione) - int(getattr(self, 'role_ovr_shift', 0) or 0)
        origin = normalize_role(getattr(self, 'ruolo_originale', None) or self.ruolo)
        if role == origin:
            return base
        rating = self._role_ratings().get(role, base)
        return min(rating, base + CONFIG.POSITIONS.ROLE_CHANGE_MAX_GAIN)

    def is_star(self) -> bool:
        # A star or rising star is defined by:
        # 1. Established star OVR 83+
        if self.ovr >= 83:
            return True
        # 2. Developing rising star (age <= 25, potential >= 86 and OVR >= 75)
        if self.eta <= 25 and self.potenziale >= 86 and self.ovr >= 75:
            return True
        # 3. Generational elite prospect (potential >= 90 and OVR >= 76)
        if self.potenziale >= 90 and self.ovr >= 76:
            return True
        return False
    def reset_for_game(self):
        self.energia = self.energia_iniziale; self.fatica = 0
        if self.giorni_infortunio_rimanenti <= 0: self.infortunato = False
        self.serie_tiro = 0; self.serie_errore = 0; self.game_stats.reset()
        self.advanced_game_stats.reset()
        self.plus_minus = 0
        self._score_at_check_in = 0
        self._score_at_check_in_opp = 0
        self.secondi_in_panchina_consecutivi = 0
    def reset_for_playoffs(self): self.reset_for_game(); self.playoff_stats.reset()
    def calcola_punti_mvp_partita(self) -> float:
        gs = self.game_stats; fgm = gs.tiri_fatti_2 + gs.tiri_fatti_3; fga = gs.tiri_tentati_2 + gs.tiri_tentati_3
        orb_approx = gs.rimbalzi * 0.33; drb_approx = gs.rimbalzi * 0.67
        game_score = (gs.punti + (orb_approx * 0.7) + (drb_approx * 0.3) + (gs.assist * 0.7) + (gs.steals * 1.5) + (gs.blocks * 0.7) - ((fga - fgm) * 0.7) - ((gs.tiri_liberi_tentati - gs.punti_liberi) * 0.4) - (gs.turnover * 1.0))
        return max(0, game_score)
    def get_tier(self) -> str:
        """Categorizes a player into a value tier for the AI. More detailed version."""
        if self.potenziale >= 95 and self.eta < 23: return "Franchise Cornerstone"
        if self.ovr >= 92: return "Superstar"
        if self.ovr >= 87: return "Star"
        if self.eta < 24 and self.potenziale >= 85: return "Top Prospect"
        if self.ovr >= 80: return "Starter"
        if self.ovr >= 75: return "Role Player"
        return "Bench Player"

    @property
    def trade_value(self) -> float:
        """
        ### REWORKED (v13.0 - Exponential Value Curve + Fast Caching) ###
        Calculates a trade value that increases exponentially for elite players,
        especially young ones, to prevent illogical trades of top prospects.
        Uses cached float evaluation to avoid redundant recalculations.
        """
        # The cache is keyed on every input, so a new contract (FA, extension), a rating change or
        # a birthday never serves a stale value (it used to be cleared only on trades/progression).
        contract = self.contract
        cache_key = (self.ovr, self.eta, self.potenziale,
                     contract.salario_annuale if contract else None)
        if getattr(self, '_trade_value_cache', None) is not None and getattr(self, '_trade_value_cache_key', None) == cache_key:
            return self._trade_value_cache

        t = CONFIG.TRADES
        curve = t.VALUE_CURVE_SCALE > 0
        if curve:
            # A young player is priced partly on what he will become, on the same curve.
            rating = float(self.ovr)
            if self.eta < 25:
                rating += max(0, self.potenziale - self.ovr) * t.VALUE_YOUNG_POTENTIAL_SHARE
            base_value = trade_curve_value(rating)
        else:   # the old step curve
            base_value = float(self.ovr)
            if self.ovr >= 95: base_value *= 4.0
            elif self.ovr >= 92: base_value *= 3.2
            elif self.ovr >= 89: base_value *= 2.6
            elif self.ovr >= 85: base_value *= 2.0  # All-Stars / Fringe All-Stars (85+)
            elif self.ovr >= 82: base_value *= 1.4  # Solid Starters (82-84)

        # Age and Potential Factor (now more impactful for young players)
        if self.eta < 25 and not curve:
            potential_gap = self.potenziale - self.ovr
            # Every point of unrealized potential is worth a lot for a young player
            base_value += potential_gap * 1.4 
        elif self.eta > 32:
            # Harsher penalty for veterans
            base_value *= (1 - (self.eta - 32) * 0.05) 

        # Contract Factor (high-performance deterministic calculation)
        if self.contract:
            cap = 155.0
            if getattr(self, 'squadra', None) and getattr(self.squadra, 'torneo', None):
                cap = getattr(self.squadra.torneo, 'salary_cap', 155.0)
            
            neg_ovr = self.ovr
            if neg_ovr >= 94: min_p, max_p = (0.28, 0.33)
            elif neg_ovr >= 89: min_p, max_p = (0.21, 0.26)
            elif neg_ovr >= 84: min_p, max_p = (0.13, 0.18)
            elif neg_ovr >= 79: min_p, max_p = (0.075, 0.115)
            elif neg_ovr >= 75: min_p, max_p = (0.045, 0.070)
            elif neg_ovr >= 71: min_p, max_p = (0.025, 0.040)
            else: min_p, max_p = (0.012, 0.020)
            
            salario_mercato = cap * ((min_p + max_p) / 2.0)
            contract_value_ratio = self.contract.salario_annuale / salario_mercato if salario_mercato > 0 else 1
            if contract_value_ratio < 0.7: base_value *= 1.1 # Favorable contract
            elif contract_value_ratio > 1.4: base_value *= 0.9 # Heavy contract

        tv = max(t.VALUE_FLOOR if curve else 10.0, round(base_value, 1))
        self._trade_value_cache = tv
        self._trade_value_cache_key = cache_key
        return tv

    @property
    def effective_ovr(self) -> float:
        """
        Calculates a player's effective OVR for salary/contract negotiations.
        Combines their raw OVR (reputation/potential) with their season performance (PVS).
        """
        pvs = self.performance_scores.total
        # If PVS is not yet calculated or at default value (75) but player is not 75 OVR, fallback to OVR
        if pvs <= 0 or (pvs == 75.0 and self.ovr != 75):
            return float(self.ovr)
        
        # 75% OVR and 25% PVS total
        return round((self.ovr * 0.75) + (pvs * 0.25), 1)

    def get_extension_willingness(self) -> float:
        """
        Computes the player's willingness to re-sign with the current team (0-100),
        aligned with the parameters and weights of the Free Agency system.
        """
        punteggio = 50.0

        # 1. Loyalty to the current team: earned with seasons and morale (core/front_office/contracts.py)
        from core.front_office.contracts import loyalty
        punteggio += loyalty(self, self.squadra)

        # 2. Morale factor
        punteggio += (self.morale - 70) * 0.4
        
        # 3. Superteam and presence of All-Star teammates
        if self.squadra:
            superstars = [p for p in self.squadra.roster if p.ovr >= 87 and p.nome != self.nome]
            stars = [p for p in self.squadra.roster if 82 <= p.ovr < 87 and p.nome != self.nome]
            if len(superstars) >= 2 or (len(superstars) >= 1 and len(stars) >= 2):
                punteggio += 30.0 if (self.ovr >= 80 or self.eta >= 29) else 15.0
            elif len(superstars) >= 1 or len(stars) >= 2:
                punteggio += 15.0 if (self.ovr >= 80 or self.eta >= 28) else 8.0

            # 4. Room in the role / Starter
            same_role = [p for p in self.squadra.roster if p.ruolo == self.ruolo and p.nome != self.nome]
            best_same = max([p.ovr for p in same_role], default=0)
            if (not same_role or best_same <= 76) and self.ovr >= 77:
                punteggio += 18.0
            elif best_same >= 87 and self.ovr >= 80 and self.eta < 34:
                punteggio -= 28.0

            # 5. Team success/status factor
            if self.squadra.torneo:
                goal_squadra = self.squadra.torneo._determina_stato_squadra(self.squadra)
                is_star = self.ovr >= 85
                win_mult = 2.5 if is_star else 1.0
                
                if goal_squadra == "Defending Champion":
                    punteggio += 25 * win_mult
                elif goal_squadra == "Contender":
                    punteggio += 15 * win_mult
                elif goal_squadra == "Playoff Team":
                    punteggio += 8
                elif goal_squadra == "Rising Star":
                    punteggio += 5
                elif goal_squadra == "Rebuilding":
                    young_core = [p for p in self.squadra.roster if p.eta < 24 and p.potenziale >= 84]
                    has_future = len(young_core) >= 2 or any(p.eta < 23 and p.potenziale >= 87 for p in self.squadra.roster)
                    penalty = 3 if has_future else 15
                    punteggio -= penalty * win_mult
                elif goal_squadra == "Mediocre":
                    punteggio -= 10 * win_mult
                    
        # 6. Age and ambition factor
        if self.eta < 28 and self.ovr >= 85:
            punteggio -= 10
        elif self.eta > 32:
            punteggio += 10
            
        return max(0.0, min(100.0, punteggio))

    def get_extension_willingness_breakdown(self) -> List[Dict[str, str]]:
        """Returns the list of positive and negative factors for the UI."""
        from core.front_office.contracts import loyalty
        if getattr(self, 'walks_away', ''):
            return [{"label": f"Won't negotiate: {self.walks_away}", "val": "-", "type": "negative"}]
        factors = [{"label": f"Team Loyalty ({getattr(self, 'anni_nella_squadra', 0)} yrs)",
                    "val": f"+{loyalty(self, self.squadra):.0f}", "type": "positive"}]
        
        # Morale
        if self.morale >= 80:
            factors.append({"label": f"High Morale ({self.morale})", "val": f"+{(self.morale - 70)*0.4:.1f}", "type": "positive"})
        elif self.morale <= 60:
            factors.append({"label": f"Low Morale ({self.morale})", "val": f"{(self.morale - 70)*0.4:.1f}", "type": "negative"})

        if self.squadra:
            superstars = [p for p in self.squadra.roster if p.ovr >= 87 and p.nome != self.nome]
            stars = [p for p in self.squadra.roster if 82 <= p.ovr < 87 and p.nome != self.nome]
            if len(superstars) >= 2 or (len(superstars) >= 1 and len(stars) >= 2):
                factors.append({"label": "Superteam Allure", "val": "+30", "type": "positive"})
            elif len(superstars) >= 1 or len(stars) >= 2:
                factors.append({"label": "Star Pairing", "val": "+15", "type": "positive"})

            if self.squadra.torneo:
                goal = self.squadra.torneo._determina_stato_squadra(self.squadra)
                if goal in ["Defending Champion", "Contender"]:
                    factors.append({"label": f"Status: {goal}", "val": "+15-25", "type": "positive"})
                elif goal == "Playoff Team":
                    factors.append({"label": "Playoff Team", "val": "+8", "type": "positive"})
                elif goal == "Rebuilding":
                    factors.append({"label": "Rebuilding Project", "val": "-15", "type": "negative"})

        if self.eta < 28 and self.ovr >= 85:
            factors.append({"label": "Prime Star (Market Ambition)", "val": "-10", "type": "negative"})
        elif self.eta > 32:
            factors.append({"label": "Veteran (Seeking Stability)", "val": "+10", "type": "positive"})

        return factors

    def get_willingness_tier(self) -> str:
        """
        Returns the textual description of the player's willingness to renew.
        """
        if getattr(self, 'walks_away', ''):
            return "Won't negotiate"
        w = self.get_extension_willingness()
        if w >= 80:
            return "Very High"
        elif w >= 65:
            return "High"
        elif w >= 48:
            return "Medium"
        elif w >= 32:
            return "Low"
        else:
            return "Very Low"

    def _calcola_valore_di_mercato(self) -> float:
        """
        REWORKED: Dynamic market value calibrated for the Historical Era (2002-2022) and the Modern Era (2023+).
        Protects against sentinel values (no_cap / 9999), guaranteeing realistic contracts that grow
        naturally along with the historical evolution of the NBA Salary Cap.
        """
        cfg_eco = CONFIG.ECONOMY
        
        # Retrieve the Tournament
        torneo = getattr(self.squadra, 'torneo', None) if getattr(self, 'squadra', None) else ACTIVE_TOURNAMENT
        raw_cap = torneo.salary_cap if torneo else cfg_eco.SALARY_CAP
        anno = getattr(torneo, 'anno_corrente', 2025) if torneo else 2025
        is_no_cap = (torneo and getattr(torneo, 'cba_mode', '') == 'no_cap') or (raw_cap >= 9000.0)
        
        # In case of No Cap (9999), use the standard cap of the year as a rational economic reference
        cap = cfg_eco.get_cap_for_year(anno, raw_cap, is_no_cap)
        
        is_historical = (anno < 2023)
        negotiation_ovr = self.effective_ovr

        # 1. Realistic NBA salary tiers calibrated by percentage of the Salary Cap
        if is_historical:
            # Classic Era / Pre-Apron (2002-2022)
            if negotiation_ovr >= 93:
                tier_pct = (0.32, 0.38)   # Franchise Supermax (Shaq, Duncan, Garnett, Kobe, LeBron)
            elif negotiation_ovr >= 88:
                tier_pct = (0.26, 0.32)   # All-Star Max (T-Mac, Iverson, Wade, Dirk, Durant, Harden)
            elif negotiation_ovr >= 84:
                tier_pct = (0.20, 0.26)   # All-Star / High-End Starter (20% - 26%)
            elif negotiation_ovr >= 80:
                tier_pct = (0.15, 0.20)   # Solid Starter (15% - 20%)
            elif negotiation_ovr >= 76:
                tier_pct = (0.09, 0.14)   # 6th Man / Key Rotation (9% - 14%)
            elif negotiation_ovr >= 72:
                tier_pct = (0.05, 0.085)  # Rotation Bench (5.0% - 8.5%)
            elif negotiation_ovr >= 68:
                tier_pct = (0.028, 0.048) # Deep Bench (2.8% - 4.8%)
            else:
                tier_pct = (0.015, 0.026) # Salary Minimum
        else:
            # Modern Era (2023+ CBA with Aprons)
            if negotiation_ovr >= 93:
                tier_pct = (0.30, 0.35)   # Modern supermax (30% - 35%)
            elif negotiation_ovr >= 88:
                tier_pct = (0.25, 0.30)   # Max Player (25% - 30%)
            elif negotiation_ovr >= 84:
                tier_pct = (0.20, 0.25)   # Star / Borderline All-Star (20% - 25%)
            elif negotiation_ovr >= 80:
                tier_pct = (0.15, 0.20)   # Starter (15% - 20%)
            elif negotiation_ovr >= 76:
                tier_pct = (0.09, 0.14)   # 6th Man / Key Rotation (9% - 14%)
            elif negotiation_ovr >= 72:
                tier_pct = (0.05, 0.085)  # Bench (5.0% - 8.5%)
            elif negotiation_ovr >= 68:
                tier_pct = (0.028, 0.048) # Deep Bench (2.8% - 4.8%)
            else:
                tier_pct = (0.015, 0.024) # Deep Bench / Minimo

        min_pct, max_pct = tier_pct
        
        # 2. Market elasticity if the league is under heavy cap strain
        market_deflator = 1.0
        if torneo and hasattr(torneo, 'squadre') and len(torneo.squadre) >= 20 and not is_no_cap:
            over_cap_count = sum(1 for s in torneo.squadre if getattr(s, 'salary_cap_space', 0.0) <= 0.5)
            if (over_cap_count / len(torneo.squadre)) >= 0.70 and negotiation_ovr < 89:
                market_deflator = 0.90
        
        # 3. Salary assignment proportional to the Cap with continuous grading
        tier_bounds = {
            93: (93, 99),
            88: (88, 92),
            84: (84, 87),
            80: (80, 83),
            76: (76, 79),
            72: (72, 75),
            68: (68, 71),
            0: (50, 67)
        }
        target_pct = random.uniform(min_pct, max_pct)
        for min_ovr, (b_low, b_high) in tier_bounds.items():
            if negotiation_ovr >= min_ovr:
                prog = (negotiation_ovr - b_low) / max(1, (b_high - b_low))
                target_pct = min_pct + (max_pct - min_pct) * (0.25 + 0.50 * prog + random.uniform(-0.10, 0.10))
                target_pct = max(min_pct, min(max_pct, target_pct))
                break

        salario_base = cap * target_pct * market_deflator

        # 4. Age and Potential Modifiers
        if self.eta <= 24 and self.potenziale > self.ovr + 5:
            salario_base *= 1.06  # Prospect premium
        elif self.eta >= 34 and self.ovr < 85:
            salario_base *= 0.80  # Discount for role-player veterans (non-superstars)
            
        # 5. Absolute Safety Limits
        min_salary = torneo.min_salary if (torneo and getattr(torneo, 'min_salary', 3.5) < 9000) else round(1.5 * (cap / 155.0), 1)
        min_salary = max(0.8, min_salary)
        salario_finale = max(min_salary, salario_base)
        max_pct = 0.40 if is_historical else 0.35
        salario_finale = min(cap * max_pct, salario_finale)
        
        return round(salario_finale, 1)

    def valuta_player_option(self, squadra: Optional['Squadra'] = None, torneo: Optional[Any] = None) -> Tuple[str, str]:
        """
        Evaluates whether to exercise (PICKUP) or decline (DECLINE) the Player Option.
        Returns: (decision, reason) where decision is 'PICKUP' or 'DECLINE'.
        """
        team = squadra or getattr(self, 'squadra', None)
        active_torneo = torneo or (team.torneo if team and hasattr(team, 'torneo') else None)
        
        current_salary = self.contract.salario_annuale if self.contract else 5.0
        try:
            market_val = self._calcola_valore_di_mercato()
        except Exception:
            market_val = self.valutazione * 0.5
            
        ratio_mercato = market_val / max(0.5, current_salary)
        
        # 1. Overpaid players or clearly declining relative to the current contract
        if ratio_mercato < 0.85:
            return "PICKUP", f"Earns more than market value (${current_salary:.1f}M vs ${market_val:.1f}M)"
            
        # 2. Older veterans (34+ years): prefer guaranteed financial security
        if self.eta >= 34:
            if self.ovr >= 85 and ratio_mercato >= 1.20:
                return "DECLINE", f"Veteran superstar seeks one last rich multi-year contract (${market_val:.1f}M)"
            return "PICKUP", f"Veteran ({self.eta} years old) chooses financial certainty (${current_salary:.1f}M)"
            
        # 3. Young players and Superstars in their prime (<= 29 years old, OVR >= 82)
        # They decline to cash in on a 4-5 year Max / Big Money deal
        if self.eta <= 29 and self.ovr >= 82:
            if ratio_mercato >= 0.90:
                return "DECLINE", f"Prime star ({self.ovr} OVR, {self.eta} years old) seeks a long max multi-year contract"
                
        # 4. Established Starters and Role Players (30-33 years old, OVR >= 77)
        if 30 <= self.eta <= 33 and self.ovr >= 77:
            if ratio_mercato >= 1.05:
                return "DECLINE", f"Seeks a new multi-year deal at a higher figure (${market_val:.1f}M)"
                
        # 5. Competitiveness / Discontent factor on rebuilding teams
        if team and active_torneo and self.ovr >= 80:
            stato_squadra = active_torneo._determina_stato_squadra(team)
            if stato_squadra in ["Rebuilding", "Mediocre"] and (self.morale < 75 or ratio_mercato >= 0.95):
                return "DECLINE", "Prefers to test Free Agency to chase a title"
                
        # 6. General default on the economic ratio
        if ratio_mercato >= 1.15:
            return "DECLINE", f"Market value above the current salary (${market_val:.1f}M vs ${current_salary:.1f}M)"
        else:
            return "PICKUP", f"Economically favorable or aligned option (${current_salary:.1f}M)"

    def valuta_team_option(self, squadra: Optional['Squadra'] = None, torneo: Optional[Any] = None) -> Tuple[str, str]:
        """
        Evaluates whether the team should exercise (PICKUP) or decline (DECLINE) the Team Option.
        Returns: (decision, reason) where decision is 'PICKUP' or 'DECLINE'.
        """
        current_salary = self.contract.salario_annuale if self.contract else 5.0
        try:
            market_val = self._calcola_valore_di_mercato()
        except Exception:
            market_val = self.valutazione * 0.5
            
        # Rookie or young contracts (<= 24 years old) are almost always picked up
        if self.eta <= 24 and self.potenziale >= 75:
            return "PICKUP", f"Young prospect to keep on the roster ({self.potenziale} POT)"
            
        if market_val >= current_salary * 0.85:
            return "PICKUP", f"Favorable value for the team (${market_val:.1f}M vs ${current_salary:.1f}M)"
        else:
            return "DECLINE", f"Player does not justify the optioned salary (${market_val:.1f}M vs ${current_salary:.1f}M)"

    def aggiorna_stamina_stagionale(self, giorni_di_riposo: int):
        """
        Computes the wear from the game just played and the recovery from the days of rest.
        This method is called AFTER every game.
        """
        # --- PHASE 1: COMPUTE THE CONSUMPTION SINCE THE LAST GAME ---
        
        consumo = 0.0
        # If the player did not play (e.g. he was injured or resting), he does not consume stamina.
        if self.game_stats.minuti_giocati > 0:
            # Base consumption for having played a game
            consumo += 0.4
            
            # Extra consumption for playing many minutes (> 30 minutes)
            if self.game_stats.minuti_giocati > 30:
                consumo += 0.4
            
            # Extra consumption for a high usage rate
            if self.advanced_game_stats.usage_rate > 30:
                consumo += (self.advanced_game_stats.usage_rate - 30) * 0.03 # 0.03 for every % point above 30
            
            # Age accelerates wear
            if self.eta > 32:
                consumo *= 1.0 + ((self.eta - 32) * 0.08) # 8% more wear for every year after 32

        # --- PHASE 2: COMPUTE THE RECOVERY ---
        
        # Base recovery for every day of rest
        recupero = giorni_di_riposo * 0.3
        
        # Younger players with higher stamina recover faster
        if self.eta < 25:
            recupero *= 1.2
        
        recupero *= (self.abilita.stamina / 85.0) # A player with stamina 99 recovers more than one with 70

        # --- PHASE 3: FINAL UPDATE ---
        
        self.stamina_stagionale -= consumo
        self.stamina_stagionale += recupero
        
        # Stamina cannot exceed 100 or drop below a critical minimum
        self.stamina_stagionale = max(20.0, min(100.0, self.stamina_stagionale))
    def recupera_stamina_offseason(self):
        """
        Simulates recovery during the offseason. It is not a total reset,
        but a significant recovery.
        """
        # Recovers a large share of the lost stamina, but not all of it.
        # E.g. if he ends at 30, he recovers (100-30)*0.8 = 56 points, reaching 86.
        stamina_persa = 100.0 - self.stamina_stagionale
        recupero = stamina_persa * 0.95 # Recovers 85% of the wear

        # Young players recover better
        if self.eta < 26:
            recupero *= 1.1

        self.stamina_stagionale = min(100.0, self.stamina_stagionale + recupero)
    def _evolvi_potenziale(self, performance_delta: float, minuti_per_partita: float) -> int:
        """Variable potential (CONFIG.PROGRESSION POT_*): a young player's ceiling moves each offseason.
        Returns the change."""
        cfg = CONFIG.PROGRESSION
        if self.eta > cfg.POT_DRIFT_MAX_AGE:
            return 0
        breakout = cfg.POT_BREAKOUT_CHANCE
        if performance_delta >= 3.0 and minuti_per_partita >= 18.0:
            breakout += cfg.POT_BREAKOUT_STRONG_SEASON_BONUS
        roll = random.random()
        if roll < breakout:
            change = random.randint(*cfg.POT_BREAKOUT_RANGE)
        elif roll < breakout + cfg.POT_SETBACK_CHANCE:
            change = -random.randint(*cfg.POT_SETBACK_RANGE)
        else:
            change = random.choice(cfg.POT_NOISE)
        before = self.potenziale
        self.potenziale = max(self.valutazione, min(99, self.potenziale + change))
        return self.potenziale - before

    def _aging_star_holds(self, performance_delta: float) -> bool:
        """A veteran star (CONFIG.PROGRESSION.AGING_STAR_MIN_OVR) whose season was close to his OVR."""
        cfg = CONFIG.PROGRESSION
        return self.valutazione >= cfg.AGING_STAR_MIN_OVR and performance_delta >= cfg.AGING_STAR_GOOD_SEASON_DELTA

    def gestisci_progressione_offseason(self) -> Dict[str, int]:
        """
        REWORKED (v22.2 - User Audio Feedback):
        1. Harsh, merit-based development of young players:
           - Development toward potential requires real minutes (>= 24 min/g for 100%, < 6 min/g almost 0%).
           - If a 22-26 year-old finds no playing time (< 12 min/g or few games), his potential decays gradually (-1/-2 per year).
        2. Relentless aging regression:
           - Biological age always dominates: for players aged >= 33, it is STRICTLY FORBIDDEN to have cambio_valutazione > 0.
           - At 35+ and 38+ the decline is mandatory and continuous (at least -1 or -2 OVR per year).
           - Shooting tendencies (shot_tendency, touch_tendency), stamina and target minutes drop after age 34 to avoid old stars dominating with 38 PPG.
        """
        self.eta += 1
        if self.contract:
            self.contract.anni_rimanenti -= 1
            if getattr(self.contract, 'salari_per_anno', None) and len(self.contract.salari_per_anno) > 0:
                self.contract.salari_per_anno.pop(0)
                if len(self.contract.salari_per_anno) > 0:
                    self.contract.salario_annuale = round(self.contract.salari_per_anno[0], 2)
        
        cfg = CONFIG.PROGRESSION
        valutazione_precedente = self.valutazione
        pvs = self.performance_scores.total
        gp = self.season_stats.partite_giocate
        minuti = self.season_stats.minuti_giocati

        # 1. Experience / Minutes / Games Played Factor (Playing Time Factor)
        # Merit-based ("harsh") development: a young player who only plays garbage time or 5 minutes a game
        # does not magically grow toward his potential. Real minutes and impact are needed.
        minuti_per_partita = (minuti / gp) if gp > 0 else 0.0

        if gp >= 50 and minuti_per_partita >= 24.0:
            pt_factor = 1.00  # Starter or key 6th man: 100% potential development
        elif gp >= 40 and minuti_per_partita >= 18.0:
            pt_factor = 0.70  # Stable rotation (18-23 min)
        elif gp >= 30 and minuti_per_partita >= 12.0:
            pt_factor = 0.40  # Limited-rotation bench player (12-17 min)
        elif gp >= 20 and minuti_per_partita >= 6.0:
            pt_factor = 0.15  # Third wheel / marginal minutes (6-11 min)
        else:
            pt_factor = 0.05  # Garbage time (< 6 min) or fewer than 20 games: growth almost entirely zeroed

        # 2. Computation of the base change (Age + Potential modulated by pt_factor and performance)
        cambio_valutazione = 0
        performance_delta = pvs - self.valutazione
        star_holds = self._aging_star_holds(performance_delta)   # read on the OVR before this summer's change
        self._evolvi_potenziale(performance_delta, minuti_per_partita)
        # Per-game totals on the reference era's level (a 28 PPG season in a 116-point league is not 2002's)
        torneo = getattr(self.squadra, 'torneo', None) if self.squadra else None
        era = league_season_scales(torneo or ACTIVE_TOURNAMENT)
        pts_per_game = (self.season_stats.punti / gp) * era['pts'] if gp > 0 else 0.0
        ast_per_game = (self.season_stats.assist / gp) * era['ast'] if gp > 0 else 0.0
        reb_per_game = (self.season_stats.rimbalzi / gp) * era['reb'] if gp > 0 else 0.0
        gap = self.potenziale - self.valutazione

        if self.eta <= 25:
            # PHASE 1: Rapid Youth Development (<= 24 years old in season, now raised to 25)
            if gap > 0:
                if self.eta <= 21 and self.potenziale >= 85:
                    dev_multiplier = 0.85 if performance_delta <= -4.0 else 1.00
                else:
                    if performance_delta <= -6.0:
                        dev_multiplier = 0.25
                    elif performance_delta <= -3.0:
                        dev_multiplier = 0.60
                    else:
                        dev_multiplier = 1.00
                    
                guadagno_base = gap * cfg.DEV_FACTOR_POTENTIAL_GAP * pt_factor * dev_multiplier
                # Half-up: Python's round(0.5) is 0 and froze 23-year-olds two points from their ceiling
                cambio_valutazione = min(cfg.DEV_POINT_MAX_GAIN_PER_YEAR, math.floor(guadagno_base + 0.5))

            # Potential erosion for chronic bench players who never play
            if 22 <= self.eta <= 25 and gap > 0:
                if gp < 25 or minuti_per_partita < 10.0:
                    self.potenziale = max(self.valutazione, self.potenziale - random.randint(1, 2))

        elif 26 <= self.eta <= 29:
            # PHASE 2: Prime Development & Late Bloomers (25-28 years old in season)
            # In the NBA many champions (Curry, Durant, Jokic, Kawhi, Butler, Nash) reach
            # their peak between 25 and 28, perfecting their shooting, reads and efficiency.
            if gap > 0:
                dev_multiplier = 0.50 if performance_delta <= -4.0 else 1.00
                guadagno_base = gap * 0.22 * pt_factor * dev_multiplier
                base_gain = math.floor(guadagno_base + 0.5)
                if gap >= 4 and pt_factor >= 0.70 and base_gain < 1:
                    base_gain = 1
                cambio_valutazione = min(3, base_gain)

        elif 30 <= self.eta <= 31:
            # PHASE 3: Apex Peak (29-30 years old in season)
            # Maximum basketball maturity: no huge jump, but high-performing stars
            # can still close the last points toward their potential.
            if gap > 0:
                if performance_delta >= 1.0 or pts_per_game >= 20.0 or ast_per_game >= 7.0 or reb_per_game >= 10.0 or pvs > self.valutazione:
                    cambio_valutazione = 1
                else:
                    cambio_valutazione = 0

        elif self.eta == 32:
            # PHASE 3B: End-of-Peak Transition (played at 31, now 32)
            # Absolute end of growth. If the season was MVP/superstar level, he stays stable (0),
            # otherwise the physiological -1 begins.
            if performance_delta >= 3.0 or self._aging_star_holds(performance_delta):
                cambio_valutazione = 0
            else:
                cambio_valutazione = -1

        elif self.eta >= 33:
            # PHASE 4: RELENTLESS BIOLOGICAL REGRESSION (32+ years old in season)
            # Biological age always wins: the decline is guaranteed and great statistics
            # can only mitigate it by 1 point, NEVER zero it or give growth.
            if self.eta == 33:
                perdita_base = 2
                min_loss = -1
            elif self.eta == 34:
                perdita_base = 3
                min_loss = -2
            elif self.eta == 35:
                perdita_base = 4
                min_loss = -3
            elif self.eta == 36:
                perdita_base = 5
                min_loss = -4
            elif self.eta == 37:
                perdita_base = 6
                min_loss = -4
            else: # 38+
                perdita_base = 7
                min_loss = -5

            cambio_valutazione = -perdita_base

            # If a veteran overperforms, we mitigate the decline by AT MOST +1 (e.g. from -3 to -2),
            # while strictly respecting min_loss (father time is undefeated)
            if performance_delta >= 2.5:
                cambio_valutazione = min(min_loss, cambio_valutazione + 1)
            elif performance_delta <= -4.0:
                cambio_valutazione -= 1

            cambio_valutazione = min(min_loss, cambio_valutazione)

            # A star who still plays at his level ages slowly (LeBron, Nash, Duncan): stable to 34, then small losses
            if self._aging_star_holds(performance_delta):
                star_loss = next(loss for age, loss in CONFIG.PROGRESSION.AGING_STAR_LOSS if self.eta <= age)
                cambio_valutazione = max(cambio_valutazione, star_loss)

        # 3. MERIT-BASED PUSH FROM REAL STATISTICAL PRODUCTION (Exclusive to players under 32)
        # If a young/prime player puts up true superstar numbers (e.g. 28-32 PPG) and has remaining potential,
        # he climbs toward the top of the league!
        if self.eta < 32 and gap > 0:
            if pts_per_game >= 28.0:
                stat_gain = 3 if gap >= 8 else 2
                cambio_valutazione = max(cambio_valutazione, stat_gain)
            elif pts_per_game >= 24.0:
                stat_gain = 2 if gap >= 6 else 1
                cambio_valutazione = max(cambio_valutazione, stat_gain)
            elif ast_per_game >= 9.0 or reb_per_game >= 11.5:
                stat_gain = 2 if gap >= 6 else 1
                cambio_valutazione = max(cambio_valutazione, stat_gain)

        # 4. ACTUAL PERFORMANCE MODIFIER (PVS vs OVR)
        if self.eta < 32:
            if performance_delta >= 4.5: # Breakout season / Monster year
                bonus = min(2, max(1, round(performance_delta / 2.5)))
                cambio_valutazione += bonus
            elif performance_delta >= 1.5: # Good year above rating
                cambio_valutazione += 1
            else:
                # Penalty only for real underperformance (e.g. benched players, busts, terrible efficiency).
                # Never punish a prime player (age < 30) who puts up star numbers (>= 18 PPG or >= 7 APG or >= 9 RPG).
                is_established_producer = (self.eta < 30) and (pts_per_game >= 18.0 or ast_per_game >= 7.0 or reb_per_game >= 9.0)
                if not is_established_producer:
                    if performance_delta <= -5.0: # Severe underperformance
                        malus = 0 if (self.eta <= 21 and self.potenziale >= 85) else max(-2, round(performance_delta / 3.5))
                        cambio_valutazione += malus
                    elif performance_delta <= -2.5: # Mild underperformance
                        malus = 0 if (self.eta <= 21 and self.potenziale >= 85) else -1
                        cambio_valutazione += malus
        else:
            # Absolute guarantee: no veteran aged 32+ can have a positive cambio_valutazione
            cambio_valutazione = min(0, cambio_valutazione)

        # Record snapshot of attributes prior to progression
        old_attrs = {k: getattr(self.abilita, k) for k in self.abilita.__dict__.keys() if isinstance(getattr(self.abilita, k), (int, float))}

        # 4. Applying the change and handling the Potential Limit (Breakout vs Hard Cap)
        if cambio_valutazione != 0:
            self.valutazione += cambio_valutazione
            
            if self.eta < 33:
                if performance_delta >= 6.0:
                    limite_pot = self.potenziale + 4
                elif performance_delta >= 3.0:
                    limite_pot = self.potenziale + 2
                else:
                    limite_pot = self.potenziale
            else:
                limite_pot = self.potenziale

            self.valutazione = min(limite_pot, self.valutazione)
            self.valutazione = max(40, min(99, self.valutazione))
            # A breakout past the ceiling moves the ceiling (a quarter of a long save's league showed OVR > POT)
            self.potenziale = max(self.potenziale, self.valutazione)
            
            self._distribuisci_cambio_abilita(self.valutazione - valutazione_precedente, star_holds=star_holds)
            self._calibra_e_calcola_posizioni()

        # Compute attribute deltas for player development UI
        new_attrs = {k: getattr(self.abilita, k) for k in self.abilita.__dict__.keys() if isinstance(getattr(self.abilita, k), (int, float))}
        attr_changes = {}
        for k, new_v in new_attrs.items():
            diff = new_v - old_attrs.get(k, new_v)
            if diff != 0:
                attr_changes[k] = diff

        ovr_diff = self.valutazione - valutazione_precedente
        
        # Record a progression milestone in the player's OVR history
        cur_season = 1
        cur_year = 2025
        if self.squadra and getattr(self.squadra, 'torneo', None):
            cur_season = getattr(self.squadra.torneo, 'season_number', 1)
            cur_year = getattr(self.squadra.torneo, 'anno_corrente', 2025)
        
        note_str = f"Progression (+{ovr_diff})" if ovr_diff > 0 else (f"Regression ({ovr_diff})" if ovr_diff < 0 else "Stable")
        self.record_ovr_milestone(season=cur_season, year=cur_year, note=note_str)

        self.last_progression = {
            "old_ovr": valutazione_precedente,
            "new_ovr": self.valutazione,
            "ovr_change": ovr_diff,
            "potenziale": self.potenziale,
            "pvs": round(pvs, 1),
            "partite_giocate": gp,
            "minuti_giocati": minuti,
            "reps_factor": round(pt_factor * 100),
            "attr_changes": attr_changes
        }

        return {'valutazione': ovr_diff}


    def _distribuisci_cambio_abilita(self, cambio_ovr: int, star_holds: bool = False):
        """`star_holds`: an aging star who still plays at his level (_aging_star_holds) keeps his usage tendencies
        and target minutes after 33; only his stamina still declines."""
        if cambio_ovr == 0: return
        punti_da_distribuire = abs(cambio_ovr) * CONFIG.PROGRESSION.DEV_SKILL_POINT_MULTIPLIER
        
        # We categorize the skills by development logic
        fisico = ['speed', 'acceleration', 'vertical', 'stamina']
        
        # We simulate the player's real weapons (his stats > 75)
        core_skills = [k for k, v in self.abilita.__dict__.items() if v > 75 and k not in fisico]
        if not core_skills: # If he is poor, he grows in the basics
            core_skills = ['close_shot_rating', 'mid_range_shot_rating', 'perimeter_defense_rating']

        for _ in range(punti_da_distribuire):
            if cambio_ovr > 0:
                # GROWTH: 60% on his main weapons, 40% random to round out
                if random.random() < 0.60 and core_skills:
                    attr = random.choice(core_skills)
                else:
                    attr = random.choice(list(self.abilita.__annotations__.keys()))
                
                valore_attuale = getattr(self.abilita, attr)
                if valore_attuale < 99:
                    setattr(self.abilita, attr, valore_attuale + 1)
                    
            elif cambio_ovr < 0:
                # REGRESSION (Aging or Wash-out)
                if self.eta >= 32:
                    # If he ages, he loses ESPECIALLY athleticism (75% chance)
                    if random.random() < 0.75:
                        attr = random.choice(fisico)
                    else:
                        attr = random.choice(list(self.abilita.__annotations__.keys()))
                else:
                    # If he is a young player who busts, he loses random technique
                    attr = random.choice(list(self.abilita.__annotations__.keys()))
                
                valore_attuale = getattr(self.abilita, attr)
                if valore_attuale > 30:
                    setattr(self.abilita, attr, valore_attuale - 1)

        # Targeted decline for veterans over 33 to lower the accumulation of unrealistic shots/possessions
        if self.eta >= 33 and star_holds:
            if hasattr(self.abilita, 'stamina'):
                self.abilita.stamina = max(40, self.abilita.stamina - random.randint(3, 5))
        elif self.eta >= 33:
            calo_tendenza = random.randint(3, 5)
            if hasattr(self.tendenze, 'touch_tendency'):
                self.tendenze.touch_tendency = max(30, self.tendenze.touch_tendency - calo_tendenza)
            if hasattr(self.tendenze, 'hero_ball_tendency'):
                self.tendenze.hero_ball_tendency = max(25, self.tendenze.hero_ball_tendency - calo_tendenza)
            if hasattr(self.tendenze, 'shot_tendency'):
                self.tendenze.shot_tendency = max(30, self.tendenze.shot_tendency - calo_tendenza)
            # Progressive stamina decline (biological fatigue)
            if hasattr(self.abilita, 'stamina'):
                self.abilita.stamina = max(40, self.abilita.stamina - random.randint(3, 5))
            
            # Organic reduction of the coach's target minutes: natural transition toward sixth man or bench
            if hasattr(self, 'minuti_target') and self.minuti_target:
                if self.eta >= 37:
                    self.minuti_target = min(14, self.minuti_target)
                elif self.eta >= 36:
                    self.minuti_target = min(18, self.minuti_target)
                elif self.eta >= 35:
                    self.minuti_target = min(22, self.minuti_target)
                elif self.eta >= 34:
                    self.minuti_target = min(26, self.minuti_target)

        # ---- TENDENCY PROGRESSION ----
        # Tendencies develop proportionally to overall growth
        # Usage (touch, hero ball) is left to the usage step below: these points pushed every star to touch 99.
        usage_keys = CONFIG.PROGRESSION.USAGE_TENDENCY_PER_OVR
        punti_tendenze = abs(cambio_ovr) * max(1, (CONFIG.PROGRESSION.DEV_SKILL_POINT_MULTIPLIER // 2))
        core_tendencies = [k for k, v in self.tendenze.__dict__.items() if v > 65 and k not in usage_keys]
        if not core_tendencies: # Fallback if the player has no marked tendencies
            core_tendencies = ['spot_up_shot_tendency', 'pass_out_of_shot_tendency', 'drive_to_basket_tendency']
        other_tendencies = [k for k in self.tendenze.__annotations__.keys() if k not in usage_keys]

        for _ in range(punti_tendenze):
            if cambio_ovr > 0:
                if random.random() < 0.65 and core_tendencies:
                    t_attr = random.choice(core_tendencies)
                else:
                    t_attr = random.choice(other_tendencies)
                
                t_val_attuale = getattr(self.tendenze, t_attr)
                if t_val_attuale < 99:
                    setattr(self.tendenze, t_attr, t_val_attuale + 1)
            elif cambio_ovr < 0:
                # Tendencies decline more slowly than physical abilities
                if random.random() < 0.40:
                    t_attr = random.choice(list(self.tendenze.__annotations__.keys()))
                    t_val_attuale = getattr(self.tendenze, t_attr)
                    if t_val_attuale > 20:
                        setattr(self.tendenze, t_attr, t_val_attuale - 1)

        # Usage follows talent (the curated league's slope): a role player who becomes a star takes over games
        # too. Generated prospects are born with a bench player's usage; veterans 33+ lose usage above.
        if self.eta < 33:
            for t_attr, per_ovr in usage_keys.items():
                if hasattr(self.tendenze, t_attr):
                    nuovo = getattr(self.tendenze, t_attr) + self._usage_step(t_attr, cambio_ovr, per_ovr)
                    setattr(self.tendenze, t_attr, max(5, min(99, nuovo)))
        self.invalidate_trade_value_cache()

    def _usage_target(self, t_attr: str):
        """Where a usage tendency sits at this OVR on the curated league's slope (the rookie generator's line:
        role mean + per-OVR points over the pivot), or None for a tendency the line does not cover."""
        cfg = CONFIG.ROOKIEGEN
        mean = cfg.ROLE_TENDENCIES.get(self.ruolo, {}).get(t_attr)
        per_ovr = cfg.USAGE_TENDENCY_PER_OVR.get(t_attr)
        if mean is None or per_ovr is None:
            return None
        return mean + per_ovr * (self.valutazione - cfg.ROLE_TENDENCY_PIVOT_OVR)

    def _usage_step(self, t_attr: str, cambio_ovr: int, per_ovr: float) -> int:
        """Points a usage tendency moves for an OVR change. A gain lifts it only up to its slope target +
        CONFIG.PROGRESSION.USAGE_TARGET_MARGIN: a real player of a mod is born with his adult usage (Embiid 88, Love
        74) and the full slope on top took both to 99, with 31 of the top 40 at touch 95+ after 25 seasons."""
        step = round(abs(cambio_ovr) * per_ovr)
        if cambio_ovr < 0:
            return -step
        target = self._usage_target(t_attr)
        if target is None:
            return step
        room = target + CONFIG.PROGRESSION.USAGE_TARGET_MARGIN - getattr(self.tendenze, t_attr)
        return max(0, min(step, round(room)))

    def decide_ritiro(self) -> bool:
        cfg = CONFIG.PROGRESSION
        
        # 1. Hard caps for age and for very poor players (avoids unrealistic 42+ year-olds on the roster)
        if self.eta >= 41: return True
        if self.eta >= 39 and self.ovr < 82: return True
        if self.eta >= 37 and self.ovr < 75: return True
        if self.eta >= 35 and self.ovr < 68: return True
        if self.ovr < 45: return True
        
        # 2. Situational variance for 32-36 year-old veterans with marginal minutes (e.g. Jeremy Lin)
        # If a 32-36 year-old plays little or shuttles at the end of the bench without serious injuries
        if 32 <= self.eta <= 36:
            gp = getattr(self.season_stats, 'partite_giocate', 0)
            min_pg = (self.season_stats.minuti_giocati / gp) if gp > 0 else 0.0
            ppg = (self.season_stats.punti / gp) if gp > 0 else 0.0
            if getattr(self, 'giorni_infortunio_rimanenti', 0) < 20:
                if gp < 25 or min_pg < 10.0 or ppg < 6.0:
                    # Progressive probability of hanging up the sneakers
                    chance_marginale = 20.0 + (self.eta - 32) * 15.0 # 20% a 32, 35% a 33, 50% a 34, 65% a 35, 80% a 36
                    if random.uniform(0, 100) < chance_marginale:
                        return True
        
        # 3. Special logic for Free Agents without a team
        if self.squadra is None:
            if self.eta >= 32:
                # Veteran without a team at 32+: very high probability of retiring
                chance_fa = 45.0 + (self.eta - 32) * 15.0
                if random.uniform(0, 100) < chance_fa:
                    return True
            elif self.eta >= 29 and self.ovr < 76:
                if random.uniform(0, 100) < 35.0:
                    return True
            
            if self.is_young_bust():
                if random.uniform(0, 100) < 40.0:
                    return True

        # 4. Standard logic for players under contract or high-level FAs
        if self.eta < cfg.AGE_RETIREMENT_THRESHOLD: return False
        
        prob = cfg.RETIREMENT_BASE_CHANCE + (self.eta - cfg.AGE_RETIREMENT_THRESHOLD) * cfg.RETIREMENT_AGE_FACTOR
        if self.ovr < 78: prob *= cfg.RETIREMENT_LOW_RATING_FACTOR 
        if self.eta >= 38: prob += 25.0
        if self.eta >= 39: prob += 35.0
        
        return random.uniform(0, 100) < prob
    def is_young_bust(self) -> bool:
        """Determines whether a young player is a 'bust' (failure)."""
        # A bust is a 24-26 year-old player who has not exceeded a certain OVR and has low potential
        cfg=CONFIG.PROGRESSION
        if 23 <= self.eta <= 27:
            if self.ovr < cfg.BUST_THRESHOLD_OVR and self.potenziale < cfg.BUST_THRESHOLD_POTENZIALE:
                return True
        return False
    def reset_for_season(self):
        """Resets the statistics and morale for a new season."""
        self.season_stats.reset()
        self.playoff_stats.reset()
        self.morale = 75
        self.is_flight_risk = False
        self.walks_away = ""
        # NOTE: is_rookie is NOT reset here.
        # It is explicitly reset at the start of the offseason (after the awards).
        self.recupera_stamina_offseason()
@dataclass
class Squadra:
    nome: str
    vittorie_attese: float = 0.0
    intesa: int = field(init=False, default=70) # Starts from a neutral value
    roster: List[Giocatore] = field(default_factory=list)
    coach: Optional[Coach] = field(init=False, default=None)
    strategia: str = "normale"; vittorie: int = 0; sconfitte: int = 0
    punti_fatti_stagione: int = 0
    punti_subiti_stagione: int = 0
    conference: Optional[str] = None
    team_id: str = ""  # franchise id from the league file; stable across renames
    partita: Optional[object] = field(init=False, default=None)
    quintetto: List[Giocatore] = field(default_factory=list); panchina: List[Giocatore] = field(default_factory=list)
    draft_picks: Dict[int, List[Dict[str, str]]] = field(default_factory=dict)
    ha_usato_mle: bool = field(init=False, default=False)
    ha_usato_bae: bool = field(init=False, default=False)
    personalita_proprietario: str = field(init=False, default="Bilanciato")
    anni_in_luxury_tax: int = field(init=False, default=0)
    active_poe: str = "Balanced Approach"
    tactical_plan: TacticalPlan = field(default_factory=TacticalPlan)
    user_custom_lineup: Dict[str, str] = field(default_factory=dict)
    posizione_in_campo: Dict[str, Giocatore] = field(default_factory=dict, init=False)
    season_number: int = field(init=False, default=0)
    torneo: Optional[Tournament] = field(init=False, default=None) # Reference to the current tournament
    financial_summary: Dict = field(default_factory=dict, init=False)
    board_profile: Optional[BoardProfile] = None
    standings_history: List[Dict[str, Any]] = field(default_factory=list)
    pending_board_concern: Optional[Dict[str, Any]] = None

    def __repr__(self):
        # The generated dataclass repr walked the roster and the tournament and ran out of memory.
        return f"Squadra({self.nome!r}, {self.vittorie}-{self.sconfitte}, {len(self.roster or [])} players)"

    def record_season_standing(self, season: int, year: int, conf_seed: int, league_rank: int, wins: int, losses: int, ppg: float, oppg: float, is_champion: bool = False, playoff_round: str = ""):
        """Records the snapshot of the regular season standing for the franchise."""
        if not hasattr(self, 'standings_history') or self.standings_history is None:
            self.standings_history = []
            
        # Avoid duplicates for the same season
        for entry in self.standings_history:
            if entry.get("season") == season:
                entry.update({
                    "year": year,
                    "conference": getattr(self, 'conference', 'East'),
                    "conf_seed": conf_seed,
                    "league_rank": league_rank,
                    "wins": wins,
                    "losses": losses,
                    "win_pct": round(wins / max(1, wins + losses), 3),
                    "ppg": round(ppg, 1),
                    "oppg": round(oppg, 1),
                    "diff": round(ppg - oppg, 1),
                    "is_champion": is_champion,
                    "playoff_round": playoff_round
                })
                return
                
        self.standings_history.append({
            "season": season,
            "year": year,
            "conference": getattr(self, 'conference', 'East'),
            "conf_seed": conf_seed,
            "league_rank": league_rank,
            "wins": wins,
            "losses": losses,
            "win_pct": round(wins / max(1, wins + losses), 3),
            "ppg": round(ppg, 1),
            "oppg": round(oppg, 1),
            "diff": round(ppg - oppg, 1),
            "is_champion": is_champion,
            "playoff_round": playoff_round
        })

    def __post_init__(self):
        self.rotazioni_personalizzate_utente = None
        for year in range(1, 7):
            self.draft_picks[year] = [{'round': 1, 'original': self.nome}]
            self.draft_picks[year].append({'round': 2, 'original': self.nome}) # At the start, every team has its own pick

    def log_financial_event(self, event_name: str, payroll_change: float, details: str):
        """Logs a significant financial event for the offseason summary."""
        if not hasattr(self, 'financial_summary') or not isinstance(self.financial_summary, dict):
            self.financial_summary = {}
        if 'events' not in self.financial_summary:
            self.financial_summary['events'] = []
        
        self.financial_summary['events'].append({
            "event": event_name,
            "change": round(payroll_change, 1),
            "details": details
        })

    @property
    def payroll(self) -> float: return sum(g.contract.salario_annuale for g in self.roster if g.contract)
    @property
    def salary_cap_space(self) -> float:
        # ### CHANGE 2: Use the tournament's dynamic salary cap ###
        if not self.torneo: return 0.0 # Safety fallback
        return self.torneo.salary_cap - self.payroll
    @property
    def salary_floor(self) -> float:
        if not self.torneo: return (CONFIG.ECONOMY.SALARY_CAP * CONFIG.ECONOMY.SALARY_FLOOR_RATIO)
        return getattr(self.torneo, 'salary_floor', round(self.torneo.salary_cap * CONFIG.ECONOMY.SALARY_FLOOR_RATIO, 1))
    @property
    def is_below_salary_floor(self) -> bool:
        return self.payroll < self.salary_floor
    @property
    def salary_floor_deficit(self) -> float:
        return max(0.0, round(self.salary_floor - self.payroll, 1))

    def get_multi_year_financial_projection(self, num_years: int = 4) -> List[Dict]:
        """
        Computes the financial projection for the next num_years years (Year 1, 2, 3, 4).
        Takes into account the scaled salaries in `contract.salari_per_anno` and the expiring players.
        """
        base_cap = getattr(self.torneo, 'salary_cap', 155.0) if self.torneo else 155.0
        base_tax = getattr(self.torneo, 'luxury_tax_threshold', 185.0) if self.torneo else 185.0
        base_apron1 = getattr(self.torneo, 'first_apron', getattr(self.torneo, 'first_apron_threshold', 195.0)) if self.torneo else 195.0
        base_apron2 = getattr(self.torneo, 'second_apron', getattr(self.torneo, 'second_apron_threshold', 205.0)) if self.torneo else 205.0
        start_year = getattr(self.torneo, 'anno_corrente', 2025) if self.torneo else 2025
        is_no_cap = (self.torneo and getattr(self.torneo, 'cba_mode', '') == 'no_cap') or (base_cap >= 9000.0)

        projections = []
        for y_idx in range(num_years):
            year_num = start_year + y_idx
            
            if is_no_cap:
                proj_cap = 9999.0
                proj_tax = 9999.0
                proj_apron1 = 9999.0
                proj_apron2 = 9999.0
            elif year_num in CONFIG.ECONOMY.YEARLY_CAPS:
                proj_cap = CONFIG.ECONOMY.YEARLY_CAPS[year_num]
                scale = proj_cap / 155.0
                proj_tax = round(185.0 * scale, 1)
                if year_num >= 2023:
                    proj_apron1 = round(CONFIG.ECONOMY.FIRST_APRON * scale, 1)
                    proj_apron2 = round(CONFIG.ECONOMY.SECOND_APRON * scale, 1)
                else:
                    proj_apron1 = 9999.0
                    proj_apron2 = 9999.0
            else:
                cap_growth = (1.03 ** y_idx)
                proj_cap = round(base_cap * cap_growth, 1)
                proj_tax = round(base_tax * cap_growth, 1)
                if year_num >= 2023 and base_apron1 < 9000:
                    proj_apron1 = round(base_apron1 * cap_growth, 1)
                    proj_apron2 = round(base_apron2 * cap_growth, 1)
                else:
                    proj_apron1 = 9999.0
                    proj_apron2 = 9999.0

            player_salaries = []
            expiring_this_year = []
            expiring_salary_freed = 0.0
            total_committed = 0.0

            for p in sorted(self.roster, key=lambda x: -x.contract.salario_annuale if x.contract else 0):
                if not p.contract:
                    continue
                if p.contract.anni_rimanenti > y_idx:
                    sal = p.contract.salario_annuale
                    if getattr(p.contract, 'salari_per_anno', None) and len(p.contract.salari_per_anno) > y_idx:
                        sal = p.contract.salari_per_anno[y_idx]
                    total_committed += sal
                    player_salaries.append({
                        "id": p.db_id or p.nome,
                        "name": p.nome,
                        "role": p.ruolo,
                        "ovr": p.ovr,
                        "age": p.eta + y_idx,
                        "salary": round(sal, 2),
                        "years_left": p.contract.anni_rimanenti - y_idx,
                        "is_last_year": (p.contract.anni_rimanenti - y_idx == 1)
                    })
                elif p.contract.anni_rimanenti == y_idx and y_idx > 0:
                    expiring_this_year.append(p.nome)
                    prev_sal = p.contract.salario_annuale
                    if getattr(p.contract, 'salari_per_anno', None) and len(p.contract.salari_per_anno) >= y_idx:
                        prev_sal = p.contract.salari_per_anno[y_idx - 1]
                    expiring_salary_freed += prev_sal

            total_payroll = round(total_committed, 2)
            cap_space = 0.0 if is_no_cap else max(0.0, round(proj_cap - total_payroll, 2))
            tax_room = 0.0 if is_no_cap else max(0.0, round(proj_tax - total_payroll, 2))
            
            if is_no_cap:
                tax_status = "No Cap (Unlimited)"
            elif proj_apron2 < 9000 and total_payroll > proj_apron2:
                tax_status = "2nd Apron"
            elif proj_apron1 < 9000 and total_payroll > proj_apron1:
                tax_status = "1st Apron"
            elif proj_tax < 9000 and total_payroll > proj_tax:
                tax_status = "Luxury Tax"
            elif total_payroll > proj_cap:
                tax_status = "Over Cap"
            else:
                tax_status = "Under Cap"

            season_label = f"Season {year_num}-{str(year_num+1)[-2:]}" if y_idx == 0 else f"+{y_idx}a ({year_num}-{str(year_num+1)[-2:]})"

            projections.append({
                "year_index": y_idx + 1,
                "calendar_year": year_num,
                "season_label": season_label,
                "total_payroll": total_payroll,
                "projected_cap": proj_cap,
                "salary_cap": proj_cap,
                "projected_tax": proj_tax,
                "luxury_tax": proj_tax,
                "projected_apron1": proj_apron1,
                "first_apron": proj_apron1,
                "projected_apron2": proj_apron2,
                "second_apron": proj_apron2,
                "cap_space": cap_space,
                "tax_room": tax_room,
                "is_no_cap": is_no_cap,
                "has_aprons": (proj_apron1 < 9000),
                "is_over_cap": (not is_no_cap and total_payroll > proj_cap),
                "is_in_tax": (not is_no_cap and proj_tax < 9000 and total_payroll > proj_tax),
                "is_in_first_apron": (not is_no_cap and proj_apron1 < 9000 and total_payroll > proj_apron1),
                "is_in_second_apron": (not is_no_cap and proj_apron2 < 9000 and total_payroll > proj_apron2),
                "tax_status": tax_status,
                "player_salaries": player_salaries,
                "expiring_players": expiring_this_year,
                "expiring_salary_freed": round(expiring_salary_freed, 2)
            })

        return projections
    
    def check_trade_salary_match(self, incoming_salary: float, outgoing_salary: float) -> Tuple[bool, str]:
        """
        Era-aware salary matching (see trades/salary_rules.py): 125% + $0.1M until 2022, banded rule after.
        Returns: (is_valid, reason)
        """
        if getattr(self, 'torneo', None) is None: 
            return True, "No tournament context"
        
        from trades.salary_rules import salary_match_ok
        return salary_match_ok(
            payroll=self.payroll, incoming=incoming_salary, outgoing=outgoing_salary,
            cap=self.torneo.salary_cap, second_apron=self.torneo.second_apron,
            year=self.torneo.anno_corrente, cba_mode=getattr(self.torneo, 'cba_mode', 'realistic'))

    def get_starter_at_position(self, posizione: str) -> Optional[Giocatore]:
        if not self.quintetto: self.scegli_quintetto_iniziale()
        if not self.quintetto: return None
        
        best_fit = max(self.quintetto, key=lambda p: p.valutazioni_posizionali.get(posizione, 0), default=None)
        return best_fit
    

    def ha_bisogno_di_ruolo(self, ruolo: str) -> bool:
        """
        Determines whether the team needs a player in a given role.
        Evaluates the needs based on 'Positional Groups' (Ball Handlers, Wings, Bigs)
        to allow flexibility (e.g. Twin Towers or Small Ball).
        """
        # Role map
        ball_handlers = ['PG', 'SG']
        wings = ['SG', 'SF', 'PF']
        bigs = ['PF', 'C']
        
        ruolo = normalize_role(ruolo)
        # 1. Check whether we already have a SUPERSTAR in that exact role
        giocatori_nel_ruolo = sorted([g for g in self.roster if g.ruolo == ruolo], key=lambda g: g.ovr, reverse=True)
        if giocatori_nel_ruolo and giocatori_nel_ruolo[0].ovr >= 85:
            # If we already have a superstar, we do NOT "need" another strong player in this role.
            # (In free agency this will return False, avoiding signing two Jokics).
            # If we have fewer than 2 players in the role overall, we need bench depth, but the FA logic
            # will only look for low-tier players.
            if len(giocatori_nel_ruolo) < 2:
                return True
            return False

        # 2. Evaluation by Positional Groups
        roster_bh = [g for g in self.roster if g.ruolo in ball_handlers]
        roster_wings = [g for g in self.roster if g.ruolo in wings]
        roster_bigs = [g for g in self.roster if g.ruolo in bigs]
        
        def evaluate_group(group_roster, min_starters, min_total):
            starters = [g for g in group_roster if g.ovr >= 78]
            if len(starters) < min_starters:
                return True # Need for Starters
            if len(group_roster) < min_total:
                return True # Need for Depth
            return False

        if ruolo in ['PG']:
            return evaluate_group(roster_bh, min_starters=2, min_total=4)
        elif ruolo in ['C']:
            return evaluate_group(roster_bigs, min_starters=1, min_total=3)
        elif ruolo in ['SF']:
            return evaluate_group(roster_wings, min_starters=2, min_total=4)
        elif ruolo in ['SG', 'PF']:
            # Hybrid positions control both relevant groups
            if ruolo in ['SG']:
                return evaluate_group(roster_bh, 2, 4) or evaluate_group(roster_wings, 2, 4)
            if ruolo in ['PF']:
                return evaluate_group(roster_wings, 2, 4) or evaluate_group(roster_bigs, 1, 3)

        return False

    def giocatori_in_campo(self) -> List[Giocatore]:
        """
        ### FIX v20.4 + v22.1 Performance: O(1) Cache ###
        Returns the players on the court, also excluding those on "load management".
        """
        if getattr(self, '_in_campo_cache', None) is not None:
            return self._in_campo_cache
        c = [g for g in self.quintetto if not g.has_fouled_out and not g.infortunato and not g.is_resting_today]
        self._in_campo_cache = c
        return c
    
    def reset_for_game(self):
        self._in_campo_cache = None
        self.strategia = "normale"
        self.giocatori_espulsi = []
        for giocatore in self.roster: giocatore.reset_for_game()
        self.scegli_quintetto_iniziale()
    
    @staticmethod
    def focus_rank_weights(gap1_2: float) -> list:
        """Focus chances (%) of the 5 ranked players. A gap between #1 and #2 from 6 to 28 points of focus value moves
        up to CONFIG.PLAYMAKING.SOLO_CARRY_P1_BONUS points to the #1 (a quarter from each of the others): Iverson
        and T-Mac carry, Dallas and the Kings share. 8 (25% -> 33%); 14 for one day gave every lone star 30+ PPG
        (Luka's assists came from the drive and kick-out passes, fixed in the engine)."""
        ratio = min(1.0, max(0.0, (gap1_2 - 6.0) / 22.0))
        bonus = ratio * CONFIG.PLAYMAKING.SOLO_CARRY_P1_BONUS
        return [25.0 + bonus] + [w - bonus / 4.0 for w in (23.0, 20.0, 17.0, 15.0)]

    def _determina_focus_offensivo(self) -> Giocatore:
        """
        Determines the target player by penalizing those who already have a high shot volume
        and integrating the hierarchical tactical options (1st/2nd/3rd Option and Touch Modifiers).
        """
        giocatori_in_campo = self.giocatori_in_campo()
        if not giocatori_in_campo: return None

        tp = getattr(self, 'tactical_plan', None)
        first_opt = getattr(tp, 'offensive_first_option', None) if tp else None
        second_opt = getattr(tp, 'offensive_second_option', None) if tp else None
        third_opt = getattr(tp, 'offensive_third_option', None) if tp else None
        touch_mods = getattr(tp, 'player_touch_modifiers', {}) if tp else {}

        anno_curr = ACTIVE_TOURNAMENT.anno_corrente if ACTIVE_TOURNAMENT else 2002
        era_cfg = CONFIG.ERA
        era_ratio = min(1.0, max(0.0, (anno_curr - era_cfg.START_YEAR) / (era_cfg.END_YEAR - era_cfg.START_YEAR)))
        era_center_focus = era_cfg.CENTER_FOCUS_MULT[0] + (era_cfg.CENTER_FOCUS_MULT[1] - era_cfg.CENTER_FOCUS_MULT[0]) * era_ratio

        gerarchia_pesata = []
        for p in giocatori_in_campo:
            touch_val = getattr(p.temp_tendenze, 'touch_tendency', 50)
            if p.ruolo in ['C', 'PF']:
                inside_skill = max(
                    p.temp_abilita.shot_iq,
                    p.temp_abilita.close_shot_rating * 0.55 + p.temp_abilita.post_control_rating * 0.45,
                )
                valore_base = p.ovr * 0.6 + inside_skill * 0.4 + (touch_val * 0.3)
                if getattr(p.temp_tendenze, 'post_up_tendency', 50) >= 65 or p.temp_abilita.close_shot_rating >= 84:
                    role_era_mult = era_center_focus if p.ruolo == 'C' else (1.0 + (era_center_focus - 1.0) * 0.6)
                    valore_base *= role_era_mult
            else:
                valore_base = p.ovr * 0.6 + p.temp_abilita.shot_iq * 0.4 + (touch_val * 0.3)
            
            is_first_opt = bool(first_opt and (p.nome == first_opt or getattr(p, 'id', '') == first_opt))
            # Application of 1st / 2nd / 3rd Option
            if is_first_opt:
                valore_base += 24.0
            elif second_opt and (p.nome == second_opt or getattr(p, 'id', '') == second_opt):
                valore_base += 14.0
            elif third_opt and (p.nome == third_opt or getattr(p, 'id', '') == third_opt):
                valore_base += 8.0
                
            # Custom role/touch modifiers
            pmod = touch_mods.get(p.nome) or touch_mods.get(getattr(p, 'id', ''), "STANDARD")
            if pmod == "GO_TO_GUY":
                valore_base += 10.0 if is_first_opt else 18.0
            elif pmod == "ROOKIE_FOCUS":
                valore_base += 16.0
            elif pmod == "SECONDARY":
                valore_base += 10.0
            elif pmod == "ROLE_PLAYER":
                valore_base -= 18.0
            elif pmod == "DEFENSE_ONLY":
                valore_base -= 35.0

            # Natural penalty only for pure passers with low scoring volume (pure point guards)
            dish_tend = getattr(p.temp_tendenze, 'dish_to_open_man_tendency', 50)
            pass_vis = getattr(p.temp_abilita, 'passing_vision', 50)
            playmaking_tend = getattr(p.temp_tendenze, 'playmaking_tendency', 50)
            if (dish_tend >= 85 or playmaking_tend >= 85) and pass_vis >= 80 and touch_val <= 70:
                valore_base -= 16.0 + max(0, (playmaking_tend - 80) * 0.4)

            # Defensive specialists (rim protectors, stoppers) do not get isolation calls
            if touch_val <= 42:
                valore_base -= 28.0

            tiri = p.game_stats.tiri_tentati_2 + p.game_stats.tiri_tentati_3
            if p.is_star() or is_first_opt:
                valore_base += 10.0
                if tiri <= 10:
                    tassa_volume = tiri * 0.75
                elif tiri <= 17:
                    tassa_volume = 7.5 + (tiri - 10) * 1.85
                elif tiri <= 22:
                    tassa_volume = 20.45 + (tiri - 17) * 2.85
                else:
                    tassa_volume = 34.7 + ((tiri - 22) ** 1.40) * 4.0
            else:
                touch_val = getattr(p.temp_tendenze, 'touch_tendency', 50)
                if touch_val >= 72:
                    if tiri <= 10:
                        tassa_volume = tiri * 0.85
                    elif tiri <= 16:
                        tassa_volume = 8.5 + (tiri - 10) * 1.9
                    else:
                        tassa_volume = 19.9 + ((tiri - 16) ** 1.3) * 3.4
                else:
                    if tiri <= 6:
                        tassa_volume = tiri * 1.3
                    elif tiri <= 10:
                        tassa_volume = 7.8 + (tiri - 6) * 2.2
                    else:
                        tassa_volume = 16.6 + ((tiri - 10) ** 1.3) * 3.6
                
            valore_finale = valore_base - tassa_volume
            gerarchia_pesata.append((p, valore_finale))
        
        giocatori_ordinati = [item[0] for item in sorted(gerarchia_pesata, key=lambda x: x[1], reverse=True)]
        valori_ordinati = [item[1] for item in sorted(gerarchia_pesata, key=lambda x: x[1], reverse=True)]

        # Dynamic computation of the hierarchy based on the lineup's depth/talent gap (Stacked vs Solo Carry)
        if len(valori_ordinati) >= 2:
            gap1_2 = max(0.0, valori_ordinati[0] - valori_ordinati[1])
            # If gap1_2 is small (<10): deep/stacked team (Dallas, Kings, Boston, Spurs) -> shared possessions
            # If gap1_2 is large (>24): solo carry (Iverson in Philly, T-Mac in Orlando) -> volume centralized on the 1st option
            prob_base = self.focus_rank_weights(gap1_2)
        else:
            prob_base = [28, 23, 20, 16, 13]

        if self.coach:
            stile = self.coach.stile_gioco
            if stile in ["Run and Gun", "Grit & Grind", "Man-to-Man Lockdown"]:
                prob_base[0] += 4.0
                prob_base[1] = max(10.0, prob_base[1] - 2.0)
                prob_base[2] = max(8.0, prob_base[2] - 2.0)
            elif stile in ["System Basketball", "Triangle Offense"]:
                prob_base[0] = max(18.0, prob_base[0] - 4.0)
                prob_base[3] += 2.0
                prob_base[4] += 2.0
        
        num_opzioni_disponibili = min(len(giocatori_ordinati), 5)
        popolazione_dinamica = giocatori_ordinati[:num_opzioni_disponibili]
        pesi_dinamici = prob_base[:num_opzioni_disponibili]

        if not popolazione_dinamica:
            return giocatori_in_campo[0] if giocatori_in_campo else None

        scelta_gerarchica = random.choices(
            population=popolazione_dinamica,
            weights=pesi_dinamici,
            k=1
        )[0]
        
        return scelta_gerarchica

    def scegli_difensore(self, attaccante: Giocatore) -> Optional[Giocatore]:
        disponibili = self.giocatori_in_campo()
        if not disponibili: return None
        
        # 0. EXPLICIT TACTICAL PLAN MATCHUP (User / Coach Custom Matchup)
        tp = getattr(self, 'tactical_plan', None)
        att_sq = getattr(attaccante, 'squadra', None)
        # Matchups are set per opponent (by player name) and only apply against that team
        matchups = tp.plan_vs(att_sq.nome)["matchups"] if tp and att_sq else {}
        if matchups:
            # A. Direct assignment (e.g. "Player A" -> "Player B")
            assigned_target = matchups.get(attaccante.nome)
            if assigned_target:
                for defender in disponibili:
                    if defender.nome == assigned_target:
                        return defender

            # B. Reciprocal cross-matching (e.g. hiding Bosh: Davis goes on Duncan, so Bosh takes Davis's man).
            # Only while the target is on the floor, otherwise the moved defender stays on his own man.
            my_natural_for_att = self.posizione_in_campo.get(getattr(attaccante, 'ruolo', ''))
            if my_natural_for_att:
                on_floor = att_sq.giocatori_in_campo()
                for opp_name, my_def_name in matchups.items():
                    if my_natural_for_att.nome != my_def_name:
                        continue
                    opp_player = next((p for p in on_floor if p.nome == opp_name), None)
                    if opp_player:
                        freed_up_defender = self.posizione_in_campo.get(getattr(opp_player, 'ruolo', ''))
                        if freed_up_defender and freed_up_defender in disponibili:
                            return freed_up_defender

        # 1. SHADOWING LOCKDOWN MATCHUP (Only if the user has not set manual assignments)
        has_custom_matchups = bool(matchups)
        if not has_custom_matchups:
            att_tendenze = getattr(attaccante, 'temp_tendenze', attaccante.tendenze)
            if att_tendenze.touch_tendency >= 80:
                att_abilita = getattr(attaccante, 'temp_abilita', attaccante.abilita)
                if att_abilita.close_shot_rating >= 82 or att_abilita.mid_range_shot_rating >= 82 or att_abilita.three_point_shot_rating >= 82:
                    if random.random() < 0.75:
                        if attaccante.ruolo in ['C', 'PF']:
                            best_def = max(disponibili, key=lambda g: getattr(g, 'temp_abilita', g.abilita).interior_defense_rating)
                            if getattr(best_def, 'temp_abilita', best_def.abilita).interior_defense_rating >= 82:
                                return best_def
                        else:
                            best_def = max(disponibili, key=lambda g: getattr(g, 'temp_abilita', g.abilita).perimeter_defense_rating)
                            if getattr(best_def, 'temp_abilita', best_def.abilita).perimeter_defense_rating >= 82:
                                return best_def

        # 2. DIRECT POSITION MATCHUP ON COURT (Instant O(1))
        ruolo_att = None
        att_sq = getattr(attaccante, 'squadra', None)
        if att_sq and hasattr(att_sq, 'posizione_in_campo'):
            for pos, p in att_sq.posizione_in_campo.items():
                if p == attaccante:
                    ruolo_att = pos
                    break
        if not ruolo_att:
            ruolo_att = attaccante.ruolo

        # If the direct defender at the same position is available on the court, take him right away
        direct_defender = self.posizione_in_campo.get(ruolo_att)
        if direct_defender and direct_defender in disponibili:
            return direct_defender

        possible_matchups = MATCHUP_FALLBACK_MAP.get(ruolo_att, (ruolo_att,))
        for ruolo_cercato in possible_matchups:
            difensori_ruolo = [g for g in disponibili if g.ruolo == ruolo_cercato]
            if difensori_ruolo:
                return difensori_ruolo[0] if len(difensori_ruolo) == 1 else difensori_ruolo[random.randint(0, len(difensori_ruolo) - 1)]
        return disponibili[0]

    def scegli_quintetto_iniziale(self):
        """
        Chooses the starting lineup supporting custom user overrides
        and optimizing the positioning with a lightning-fast algorithm and memoization of the availability state.
        Respects the rule that players with minuti_target == 0 do not start,
        except for injuries or a short roster.
        """
        custom_lineup = getattr(self, 'user_custom_lineup', None)
        if custom_lineup:
            custom_lineup = normalize_role_keys(custom_lineup)
        posizioni = ['PG', 'SG', 'SF', 'PF', 'C']
        roster_sano = [g for g in self.roster if not g.infortunato and not g.is_resting_today]
        
        if len(roster_sano) < 5:
            self.quintetto = roster_sano.copy()
            self.panchina = [g for g in self.roster if g not in self.quintetto]
            self.posizione_in_campo = {}
            for i, g in enumerate(self.quintetto):
                if i < len(posizioni):
                    self.posizione_in_campo[posizioni[i]] = g
            return

        # 0. Fast-Path: Roster Health & Lineup Cache
        custom_tuple = tuple(sorted(custom_lineup.items())) if custom_lineup else ()
        cache_key = (tuple(id(g) for g in roster_sano), custom_tuple)
        cached_five = getattr(self, '_cached_starting_five', None)
        cached_key = getattr(self, '_cached_starting_key', None)

        if cached_five and cached_key == cache_key and all(g in roster_sano for g in cached_five.values()):
            self.quintetto = [cached_five[p] for p in posizioni if p in cached_five]
            self.posizione_in_campo = cached_five.copy()
            quintetto_ids = set(id(g) for g in self.quintetto)
            self.panchina = [g for g in self.roster if id(g) not in quintetto_ids]
            return

        # Filter the candidates: they must have minuti_target > 0, unless there are fewer than 5 players available
        candidati_disponibili = [g for g in roster_sano if g.minuti_target > 0]
        if len(candidati_disponibili) < 5:
            candidati_disponibili = roster_sano.copy()

        quintetto_pos: Dict[str, Giocatore] = {}
        usati_ids = set()

        # 1. Custom user override (if valid and healthy)
        if custom_lineup:
            for pos in posizioni:
                player_name = custom_lineup.get(pos)
                if player_name:
                    found_player = next((g for g in roster_sano if g.nome == player_name), None)
                    if found_player and id(found_player) not in usati_ids:
                        quintetto_pos[pos] = found_player
                        usati_ids.add(id(found_player))

        # 2. Ultra-fast optimizer for the positions not yet assigned
        posizioni_da_riempire = [p for p in posizioni if p not in quintetto_pos]
        if posizioni_da_riempire:
            rimasti_candidati = [c for c in candidati_disponibili if id(c) not in usati_ids]
            if len(rimasti_candidati) < len(posizioni_da_riempire):
                rimasti_candidati = [c for c in roster_sano if id(c) not in usati_ids]
            
            # Limit to at most 2 best candidates per position (2^N <= 32 combinations max, ultra-fast)
            candidati_per_pos = {}
            for pos in posizioni_da_riempire:
                sorted_cands = sorted(
                    rimasti_candidati,
                    key=lambda g: (g.valutazioni_posizionali.get(pos, g.valutazione) - POSITION_COMPATIBILITY_PENALTY.get(g.ruolo, {}).get(pos, 0)),
                    reverse=True
                )[:2]
                candidati_per_pos[pos] = sorted_cands
            
            best_assignment: Dict[str, Giocatore] = {}
            best_score = -999999
            
            def fast_backtrack(idx: int, current_assignment: Dict[str, Giocatore], current_score: float, used_set: set):
                nonlocal best_assignment, best_score
                if idx == len(posizioni_da_riempire):
                    if current_score > best_score:
                        best_score = current_score
                        best_assignment = current_assignment.copy()
                    return
                
                pos = posizioni_da_riempire[idx]
                candidates = candidati_per_pos.get(pos, [])
                for cand in candidates:
                    cand_id = id(cand)
                    if cand_id not in used_set:
                        val = cand.valutazioni_posizionali.get(pos, cand.valutazione) - POSITION_COMPATIBILITY_PENALTY.get(cand.ruolo, {}).get(pos, 0)
                        current_assignment[pos] = cand
                        used_set.add(cand_id)
                        fast_backtrack(idx + 1, current_assignment, current_score + val, used_set)
                        used_set.remove(cand_id)
                        del current_assignment[pos]
            
            fast_backtrack(0, {}, 0.0, set(usati_ids))
            
            for pos, cand in best_assignment.items():
                quintetto_pos[pos] = cand
                usati_ids.add(id(cand))
                
            # Failsafe for positions still empty
            for pos in posizioni:
                if pos not in quintetto_pos:
                    rimasti = [c for c in roster_sano if id(c) not in usati_ids]
                    if rimasti:
                        best_cand = max(
                            rimasti,
                            key=lambda g: g.valutazioni_posizionali.get(pos, g.valutazione) - POSITION_COMPATIBILITY_PENALTY.get(g.ruolo, {}).get(pos, 0)
                        )
                        quintetto_pos[pos] = best_cand
                        usati_ids.add(id(best_cand))

        self.quintetto = [quintetto_pos[p] for p in posizioni if p in quintetto_pos]
        self.posizione_in_campo = {pos: player for pos, player in quintetto_pos.items()}
        quintetto_ids = set(id(g) for g in self.quintetto)
        self.panchina = [g for g in self.roster if id(g) not in quintetto_ids]
        self._in_campo_cache = None

        # Save to cache
        self._cached_starting_five = self.posizione_in_campo.copy()
        self._cached_starting_key = cache_key

        # If the team is the user's and does not yet have a saved custom_lineup, stabilize it
        is_user_team = hasattr(self, 'torneo') and getattr(self.torneo, 'squadra_giocatore', None) == self
        if is_user_team and not self.user_custom_lineup and len(self.quintetto) == 5:
            self.user_custom_lineup = {pos: player.nome for pos, player in self.posizione_in_campo.items()}

    def prepara_partita(self):
        """
        Orchestrator method that resets and prepares the team's state before every game.
        1. Aligns the rotations and target minutes faithfully respecting the user's choices.
        2. Sets the starting lineup without arbitrarily reshuffling roles and starters.
        """
        if hasattr(self, 'torneo') and self.torneo:
            self.torneo.imposta_rotazioni_stagione_per_squadra(self, force_user=False)
        self.scegli_quintetto_iniziale()
    def _get_sostituto_ideale(self, giocatore_out: 'Giocatore', candidati: List['Giocatore']) -> Optional['Giocatore']:
        """Helper method to find the best available substitute, considering the active position on the court and the secondary roles."""
        if not candidati: return None
        
        # Find the active position occupied by the player who is leaving
        ruolo_da_coprire = None
        for pos, player in self.posizione_in_campo.items():
            if player == giocatore_out:
                ruolo_da_coprire = pos
                break
        if not ruolo_da_coprire:
            ruolo_da_coprire = giocatore_out.ruolo
        
        def get_effective_ovr(p: 'Giocatore') -> float:
            penalty = POSITION_COMPATIBILITY_PENALTY.get(p.ruolo, {}).get(ruolo_da_coprire, 0)
            if p.ruolo == ruolo_da_coprire:
                # Natural role: full value
                return p.ovr + (p.energia * 0.2)
            else:
                # Out of role: use positional rating with a compatibility penalty
                val_out_of_pos = p.valutazioni_posizionali.get(ruolo_da_coprire, 0)
                if val_out_of_pos > 0:
                    return (val_out_of_pos - penalty) + (p.energia * 0.2)
                else:
                    return p.ovr - penalty - 20 + (p.energia * 0.2) # Extreme penalty if the role is incompatible

        return max(candidati, key=get_effective_ovr)

    def decidi_sostituzioni(self):
        """### REWORK v18.0: Hierarchical substitution logic based on iron-clad rules. ###"""
        cfg = CONFIG.COACHING
        if not self.partita: return

        # --- REGOLA FERREA #1: "CLOSING TIME" ---
        is_clutch_time = (self.partita.quarto_attuale >= 4 and self.partita.tempo_rimanente_secondi <= 180 and
                        abs(self.partita.punteggio[self.nome] - self.partita.punteggio[self.partita.squadra_avversaria(self).nome]) <= 8)

        # If it is clutch time, make sure the best players are on the court
        if is_clutch_time:
            candidati_clutch = sorted([p for p in self.panchina if not p.infortunato and not p.has_fouled_out and not p.is_resting_today], key=lambda x: x.ovr, reverse=True)
            for p_in in candidati_clutch:
                peggiore_in_campo = min(self.quintetto, key=lambda x: x.ovr)
                if p_in.ovr > peggiore_in_campo.ovr + 3:
                    self._esegui_sostituzione(peggiore_in_campo, p_in)

        # --- STAGGER STARS IDENTIFICATION ---
        tp = getattr(self, 'tactical_plan', None)
        stagger_active = getattr(tp, 'stagger_stars', False) if tp else False
        top_stars = []
        if stagger_active:
            sani_stars = sorted([g for g in self.roster if not g.infortunato and not g.is_resting_today], key=lambda g: g.ovr, reverse=True)[:2]
            if len(sani_stars) == 2 and (sani_stars[0].is_star() or sani_stars[0].ovr >= 82):
                top_stars = sani_stars

        sostituzioni_rotazione_fatte = 0
        MAX_SOSTITUZIONI_ROTATIVE = 2 # Prevents the "5 in, 5 out" mass-sub

        # --- LOOP OVER THE PLAYERS ON THE COURT (STARTERS) ---
        for p_out in list(self.quintetto): 
            
            # --- IRON-CLAD RULE #2: MANDATORY SUBSTITUTIONS (ALWAYS ACTIVE) ---
            foul_limit = {1: 3, 2: 4, 3: 5, 4: 6}.get(self.partita.quarto_attuale, 6) 
            is_in_emergenza = (p_out.energia < cfg.SUBSTITUTION_CRITICAL_ENERGY_LIMIT or 
                            p_out.game_stats.falli_commessi >= foul_limit)

            if is_in_emergenza:
                candidati = [p for p in self.panchina if not p.infortunato and not p.has_fouled_out and not p.is_resting_today]
                sostituto = self._get_sostituto_ideale(p_out, candidati)
                if sostituto:
                    self._esegui_sostituzione(p_out, sostituto)
                    continue

            # If we are in "clutch time" and the player is not in an emergency, he is NOT TOUCHED.
            if is_clutch_time:
                continue

            # --- STAGGER STARS CHECK ---
            # If staggering is active in the 2nd or 3rd quarter, avoid both superstars sitting together
            if stagger_active and p_out in top_stars and self.partita.quarto_attuale in [2, 3]:
                altra_stella = top_stars[1] if p_out == top_stars[0] else top_stars[0]
                if altra_stella in self.panchina and altra_stella.energia < 60:
                    # The other star is still resting, keep this star on the court unless fatigue is critical
                    if p_out.energia > cfg.SUBSTITUTION_CRITICAL_ENERGY_LIMIT + 10:
                        continue

            # --- RULE #3: ROTATION SUBSTITUTIONS (NOT IN CLUTCH TIME) ---
            minuti_giocati = p_out.game_stats.secondi_giocati / 60.0
            percentuale_partita_giocata = self.partita.secondi_totali_giocati / (48 * 60) if self.partita.secondi_totali_giocati > 0 else 0
            target_a_questo_punto = p_out.minuti_target * percentuale_partita_giocata

            # Superstars and heavy starters have a more permissive fatigue threshold (38 instead of 60) to last 36-39 min
            is_star_player = p_out.is_star() or p_out.ovr >= 85 or p_out.minuti_target >= 33
            low_energy_limit = 38 if is_star_player else cfg.SUBSTITUTION_LOW_ENERGY_LIMIT
            is_stanco = p_out.energia < low_energy_limit
            tolleranza_individuale = cfg.MINUTES_TARGET_TOLERANCE + (hash(p_out.nome) % 3)
            if is_star_player: tolleranza_individuale += 2
            ha_giocato_troppo = minuti_giocati > target_a_questo_punto + tolleranza_individuale

            minuti_gara_attuali = self.partita.secondi_totali_giocati / 60.0
            mai_riposato = (minuti_giocati >= minuti_gara_attuali - 1)
            if mai_riposato and minuti_gara_attuali >= 16 and self.partita.quarto_attuale <= 3:
                ha_giocato_troppo = True

            if (is_stanco or ha_giocato_troppo) and sostituzioni_rotazione_fatte < MAX_SOSTITUZIONI_ROTATIVE:
                candidati_panchina = [p for p in self.panchina if not p.infortunato and not p.has_fouled_out and not p.is_resting_today]
                
                # If stagger stars is active and a superstar comes out, prefer to bring back the other star if he has enough energy
                if stagger_active and p_out in top_stars:
                    altra_stella = top_stars[1] if p_out == top_stars[0] else top_stars[0]
                    if altra_stella in candidati_panchina and altra_stella.energia >= 65:
                        self._esegui_sostituzione(p_out, altra_stella)
                        sostituzioni_rotazione_fatte += 1
                        continue

                candidati_buona_energia = [p for p in candidati_panchina if p.energia > 40]
                
                candidati_ideali = []
                for p_in in candidati_buona_energia:
                    target_in_a_questo_punto = p_in.minuti_target * percentuale_partita_giocata
                    if (p_in.game_stats.secondi_giocati / 60.0) < target_in_a_questo_punto:
                        candidati_ideali.append(p_in)
                
                sostituto = self._get_sostituto_ideale(p_out, candidati_ideali)
                
                if not sostituto:
                    sostituto = self._get_sostituto_ideale(p_out, candidati_buona_energia)
                    
                if not sostituto and (is_stanco or ha_giocato_troppo):
                    candidati_emergenza = [p for p in candidati_panchina if p.energia > p_out.energia - 20]
                    if not candidati_emergenza:
                        candidati_emergenza = candidati_panchina
                    sostituto = self._get_sostituto_ideale(p_out, candidati_emergenza)
                    
                if sostituto:
                    self._esegui_sostituzione(p_out, sostituto)
                    sostituzioni_rotazione_fatte += 1

    def _gestisci_garbage_time(self):
        """
        Empties the bench during a blowout (garbage time),
        replacing all the starters with the available second/third units.
        """
        roster_disponibile = [g for g in self.roster if not g.infortunato and not g.has_fouled_out and not g.is_resting_today]
        if len(roster_disponibile) < 5: return
        
        # Sort the players by lowest target minutes and seconds played (second and third units)
        giocatori_con_meno_minuti = sorted(roster_disponibile, key=lambda g: (g.minuti_target, g.game_stats.secondi_giocati))
        nuovo_quintetto = giocatori_con_meno_minuti[:5]
        
        for giocatore in nuovo_quintetto:
            if giocatore in self.panchina:
                giocatore_da_sostituire = next((g for g in self.quintetto if g not in nuovo_quintetto), None)
                if giocatore_da_sostituire:
                    self._esegui_sostituzione(giocatore_da_sostituire, giocatore)

    def _esegui_sostituzione(self, giocatore_out: Giocatore, giocatore_in: Giocatore):
        """Handles ONLY standard rotations (swaps between court and bench) while keeping track of the active position."""
        if giocatore_out not in self.quintetto or giocatore_in not in self.panchina:
            return

        if self.partita:
            punteggio_attuale = self.partita.punteggio[self.nome]
            punteggio_attuale_opp = self.partita.punteggio[self.partita.squadra_avversaria(self).nome]
            diff_squadra = punteggio_attuale - giocatore_out._score_at_check_in
            diff_opp = punteggio_attuale_opp - giocatore_out._score_at_check_in_opp
            giocatore_out.plus_minus += (diff_squadra - diff_opp)
        
        # Update the position on the court
        pos_da_coprire = None
        for pos, player in self.posizione_in_campo.items():
            if player == giocatore_out:
                pos_da_coprire = pos
                break
        if pos_da_coprire:
            self.posizione_in_campo[pos_da_coprire] = giocatore_in

        self.quintetto.remove(giocatore_out)
        self.panchina.append(giocatore_out)
        self.panchina.remove(giocatore_in)
        self.quintetto.append(giocatore_in)
        self._in_campo_cache = None
        if self.partita:
            giocatore_in._score_at_check_in = punteggio_attuale
            giocatore_in._score_at_check_in_opp = punteggio_attuale_opp

    def gestisci_uscita_giocatore(self, giocatore_da_rimuovere: Giocatore):
        """Handles permanent exits (fouls/injury) while keeping track of the active position."""
        if giocatore_da_rimuovere not in self.quintetto:
            return

        punteggio_attuale = self.partita.punteggio[self.nome]
        punteggio_attuale_opp = self.partita.punteggio[self.partita.squadra_avversaria(self).nome]
        diff_squadra = punteggio_attuale - giocatore_da_rimuovere._score_at_check_in
        diff_opp = punteggio_attuale_opp - giocatore_da_rimuovere._score_at_check_in_opp
        giocatore_da_rimuovere.plus_minus += (diff_squadra - diff_opp)

        # Find and keep the active position on the court
        pos_da_coprire = None
        for pos, player in self.posizione_in_campo.items():
            if player == giocatore_da_rimuovere:
                pos_da_coprire = pos
                break

        self.quintetto.remove(giocatore_da_rimuovere)
        self.giocatori_espulsi.append(giocatore_da_rimuovere)
        self._in_campo_cache = None
        
        candidati_sostituti = [p for p in self.panchina if not p.has_fouled_out and not p.infortunato and not p.is_resting_today]
        
        if candidati_sostituti:
            # Choose the ideal substitute specific to the vacant position
            sostituto = self._get_sostituto_ideale(giocatore_da_rimuovere, candidati_sostituti)
            if not sostituto:
                sostituto = max(candidati_sostituti, key=lambda p: p.ovr)
                
            if pos_da_coprire:
                self.posizione_in_campo[pos_da_coprire] = sostituto
                
            self.panchina.remove(sostituto)
            self.quintetto.append(sostituto)
            self._in_campo_cache = None
            sostituto._score_at_check_in = punteggio_attuale
            sostituto._score_at_check_in_opp = punteggio_attuale_opp
            self.partita.log.append(f"FORCED SUBSTITUTION: {giocatore_da_rimuovere.nome} out, {sostituto.nome} in.")
        else:
            if pos_da_coprire:
                del self.posizione_in_campo[pos_da_coprire]
            self.partita.log.append(f"WARNING: {self.nome} could not find a valid substitute and is now playing a man down!")

            
    def sesto_uomo(self) -> Optional['Giocatore']:
        """Returns the best player on the bench."""
        if len(self.roster) <= 5:
            return None
        panchina = sorted(self.roster, key=lambda p: p.valutazione, reverse=True)[5:]
        return panchina[0] if panchina else None

    def reset_record_stagionale(self):
        heal = CONFIG.INJURIES.OFFSEASON_HEAL_DAYS   # the summer heals: a spring torn ACL can still cost some autumn
        for p in self.roster:
            left = max(0, int(getattr(p, 'giorni_infortunio_rimanenti', 0) or 0) - heal)
            p.giorni_infortunio_rimanenti = left
            if left == 0:
                p.infortunato, p.infortunio_nome, p.is_day_to_day, p.infortunio_impatto = False, None, False, 0.0
        self.vittorie = 0; self.sconfitte = 0
        self.punti_fatti_stagione = 0 
        self.punti_subiti_stagione = 0
        self.ha_usato_mle = False
        self.ha_usato_bae = False
        self.intesa = 70 # Chemistry resets at the start of the season
        for g in self.roster: 
            g.reset_for_season()
        self.financial_summary = {
            "start_offseason_payroll": 0.0,
            "end_offseason_payroll": 0.0,
            "events": []
        }
    def designa_intoccabili(self, torneo: 'Tournament'):
        """
        Protects the untouchable core of each franchise:
        1. Champion team: the best 7 players are sacred.
        2. Rookies & young prospects (<= 23 years old, POT >= 80 or OVR >= 76): unavailable for all teams.
        3. Franchise player: the team's best player (if >= 82 OVR) or stars >= 86 OVR.
        4. MVP or All-NBA First Team award winners.
        """
        from core.front_office.wishes import asked_out   # a saved trade request, not only this window's cache
        # Step 0: Reset the state for a clean new evaluation
        for g in self.roster:
            g.is_untouchable = False

        # 1. Reigning Champions rule: their core is sacred
        champion_team = getattr(torneo, 'campione', None) if torneo else None
        if champion_team and champion_team.nome == self.nome:
            nucleo_campione = sorted(self.roster, key=lambda p: p.ovr, reverse=True)[:7]
            for player in nucleo_campione:
                player.is_untouchable = True
            self._limit_veteran_untouchables(torneo)
            return

        # 2. Protection of Rookies and Young Prospects for ALL teams
        # No NBA franchise gives away its freshly drafted talents (e.g. Iguodala, LeBron, Wade, Bosh, Howard)
        for g in self.roster:
            if g.eta <= 23 and (g.potenziale >= 80 or g.ovr >= 76):
                if not asked_out(g) and not g.is_flight_risk:
                    g.is_untouchable = True

        # 3. Protection of Superstars and Franchise Faces
        for g in self.roster:
            tier = g.get_tier()
            if tier in ["Franchise Cornerstone", "Superstar"]:
                is_expiring = g.contract and g.contract.anni_rimanenti <= 1
                if not g.is_flight_risk and not asked_out(g) and not is_expiring:
                    g.is_untouchable = True

        # 4. The best player of each franchise (if OVR >= 82) is the cornerstone
        if self.roster:
            top_player = max(self.roster, key=lambda p: p.ovr)
            if top_player.ovr >= 82 and not asked_out(top_player) and not top_player.is_flight_risk:
                top_player.is_untouchable = True

        # 5. Protect the winners of major individual awards
        if torneo:
            mvp = getattr(torneo, 'regular_season_mvp', None)
            mvp_name = mvp.nome if mvp else None
            all_nba = getattr(torneo, 'all_nba_teams', None)
            all_nba_1st_team_names = {p.nome for p in all_nba[0]} if all_nba else set()
            for g in self.roster:
                if g.nome == mvp_name or g.nome in all_nba_1st_team_names:
                    g.is_untouchable = True

        self._limit_veteran_untouchables(torneo)

    def _limit_veteran_untouchables(self, torneo: 'Tournament'):
        """Above CONFIG.TRADES.UNTOUCHABLE_FREE_AGE only a real franchise player stays untouchable: OVR >=
        UNTOUCHABLE_VET_OVR, or >= UNTOUCHABLE_VET_CONTENDER_OVR on a contender (its plan, or the reigning champion)."""
        t = CONFIG.TRADES
        plan = None
        fo = getattr(torneo, 'front_office', None) if torneo else None
        if fo is not None:
            plan = getattr(fo.plans.get(self.nome), 'state', None)
        champion_team = getattr(torneo, 'campione', None)
        champion = bool(champion_team and champion_team.nome == self.nome)
        line = t.UNTOUCHABLE_VET_CONTENDER_OVR if (plan == "CONTENDER" or champion) else t.UNTOUCHABLE_VET_OVR
        for g in self.roster:
            if g.is_untouchable and g.eta > t.UNTOUCHABLE_FREE_AGE and g.ovr < line:
                g.is_untouchable = False

    def analizza_roster_per_upgrade(self) -> List[str]:
        """
        ### REINVENTED (v5.1) ###
        Analyzes the roster to identify the weakest positional groups.
        Returns a simple, ranked list of position names (e.g., ['C', 'PF', 'PG']).
        """
        roster_sano = [g for g in self.roster if not g.infortunato]
        if len(roster_sano) < 5: return ['PG', 'SG', 'SF', 'PF', 'C']

        position_scores = {'PG': 0, 'SG': 0, 'SF': 0, 'PF': 0, 'C': 0}
        for pos in position_scores:
            # Sort all players by their strength at THIS specific position
            top_players_at_pos = sorted([p for p in roster_sano], key=lambda g: g.valutazioni_posizionali.get(pos, 0), reverse=True)
            
            score = 0
            # The starter's quality is weighted heavily
            if top_players_at_pos:
                score += top_players_at_pos[0].valutazioni_posizionali.get(pos, 0) * 1.5
            # The backup's quality matters, but less so. Depth is key.
            if len(top_players_at_pos) > 1:
                score += top_players_at_pos[1].valutazioni_posizionali.get(pos, 0) * 0.8
            
            position_scores[pos] = score
        
        # Return the positions sorted by the LOWEST score (i.e., the biggest need) first
        return sorted(position_scores, key=position_scores.get)

