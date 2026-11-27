from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class Fatigue:
    """Configuration for energy, fatigue and recovery. (v17.0 - Real Stamina Engine)"""

    # RECOVERY is also tied to stamina.
    END_OF_QUARTER_RECOVERY_FACTOR: float = 0.4 # Recovers 40% of max energy
    
@dataclass(frozen=True)
class SyntheticStamina:
    """Configuration for the 'synthetic' stamina calculation."""
    # The base stamina everyone starts from. A high value makes the league more durable.
    BASE_STAMINA: int = 270
    
    # Penalty for every year above a certain age.
    AGE_PENALTY_THRESHOLD: int = 32
    AGE_PENALTY_PER_YEAR: float = 1.5  # For every year after 29, loses 1.5 stamina points.
    
    # Bonus/Malus based on role.
    ROLE_MODIFIER: dict = field(default_factory=lambda: {
        'C': -20,
        'PF': -10,
        'SF': 0,
        'SG': +5,
        'PG': +10,
    })
    
    # Impact of athleticism (speed and acceleration).
    ATHLETICISM_IMPACT_FACTOR: float = 0.1 # For every athleticism point above 80, gains 0.1 stamina.

@dataclass(frozen=True)
class Shooting:
    """Configuration for the shooting mechanics. (v17.4 - Final Tuning)"""
    
    

    FATIGUE_PENALTY_FACTOR: float = 0.35
    GOOD_STREAK_LIMIT: int = 5
    GOOD_STREAK_BONUS: float = 3.0
    BAD_STREAK_LIMIT: int = 5
    BAD_STREAK_PENALTY: float = 3.5
@dataclass(frozen=True)
class Offseason:
    """Configuration for off-season events such as the Draft."""
    # How many rookies are generated each year
    DRAFT_CLASS_SIZE: int = 60
    # How many rounds the draft has (2 rounds like the NBA)
    DRAFT_ROUNDS: int = 2
    
    # How many days the offseason free-agent market lasts
    FREE_AGENCY_DAYS: int = 12

    # How many teams take part in the draft lottery
    LOTTERY_TEAMS_COUNT: int = 14
    # Lottery weights by seed (worst record first); seeds past the list get LOTTERY_ODDS_EXTRA_TEAM.
    LOTTERY_ODDS: Tuple[float, ...] = (14.0, 14.0, 14.0, 12.5, 10.5, 9.0, 7.5, 6.0, 4.5, 3.0, 2.0, 1.5, 1.0, 0.5)
    LOTTERY_ODDS_EXTRA_TEAM: float = 0.1
    # How many picks the lottery draws; the other lottery teams follow in seed order.
    LOTTERY_DRAWN_PICKS: int = 4
    
    # Generated rookies (classes without a league file): OVR on a triangle, POT = OVR + a gap on a triangle.
    # Calibrated on the curated 2003-2023 classes: mean ~68 OVR / ~75 POT, 5-13 prospects at POT 85+, 2-5 at
    # OVR 75+ per class. The old ranges (OVR 67-78, POT 76-94) gave ~28 at POT 85+ and inflated a long save.
    ROOKIE_RATING_MIN: int = 58
    ROOKIE_RATING_MAX: int = 78
    ROOKIE_RATING_MODE: int = 67
    ROOKIE_POT_GAP_MIN: int = 1
    ROOKIE_POT_GAP_MAX: int = 26
    ROOKIE_POT_GAP_MODE: int = 5
    # Age of a generated prospect (weights) and the share of his POT gap he keeps at that age: a 23-year-old senior
    # is closer to his ceiling than a 19-year-old (the age was 18-23 flat, half a class at 22-23 with any POT).
    ROOKIE_AGE_WEIGHTS: dict = field(default_factory=lambda: {19: 30, 20: 26, 21: 20, 22: 14, 23: 10})
    ROOKIE_POT_GAP_AGE_SCALE: dict = field(default_factory=lambda: {19: 1.0, 20: 0.9, 21: 0.8, 22: 0.65, 23: 0.5})
    GENERATIONAL_TALENT_AGES: tuple = (18, 19)

    # Probability (%) of a generational talent (POT 95-99) per generated rookie (~1 class in 4 has one)
    GENERATIONAL_TALENT_CHANCE: float = 0.4

    ROSTER_SIZE_LIMIT: int = 18
    ROSTER_SIZE_MIN: int = 15
    # Hard floor a trade may leave a roster at (the regular minimum above is enforced later by cut-down day)
    TRADE_ROSTER_MIN_SIZE: int = 10
    # ...unless their OVR is above this immunity threshold.
    CUT_OVR_IMMUNITY_THRESHOLD: int = 76
    # Or unless they are a young prospect with potential above this threshold.
    CUT_POTENTIAL_IMMUNITY_THRESHOLD: int = 80
@dataclass(frozen=True)
class Fouls:
    """Configuration for fouls and free throws. (v14.0 - Realistic FT & Foul Frequency)."""
    
    # Base foul probability on drives, to produce ~22-26 team free throws per game
    BASE_CHANCE_DRIVE: float = 10.5
    
    JUMP_SHOT_FOUL_DIVISOR: float = 4.5
    
    
@dataclass(frozen=True)
class Events:
    '''
    ### REWORKED (v21.0 - Balanced Steals & Defense) ###
    Rebalances the steals logic to avoid defensive monsters with 3.0+ SPG.
    '''
    BLOCK_ATTEMPT_RATING_FACTOR: float = 0.50
    BLOCK_SUCCESS_BASE_MODIFIER: float = 0.30
    BLOCK_SUCCESS_SKILL_DIFF_FACTOR: float = 0.35

    PERIMETER_BLOCK_CHANCE: float = 5.0
    PERIMETER_BLOCK_RATING_IMPACT: float = 3.0
    BLOCKS_PER_GAME_CAP: int = 999 # No artificial cap, the frequency is regulated organically by the formulas
    HELP_DEFENSE_CHANCE: float = 45.0
    STEAL_ATTEMPT_BASE_CHANCE: float = 4.0 # Base probability per possession (calibrated for 7-8 team steals per game)
    STEAL_ABILITY_FACTOR: float = 16.0 # Diminishing returns naturale sui rating 90+
    MAX_STEALS_PER_GAME: int = 999 # No artificial cap on steals
    # Who gets a rebound: rating ** exponent x role multiplier. Was 1.52 with C 1.48 / PG 0.62 inside: starting
    # guards took 2.8 a game (NBA ~4) and the leader 17-19. Engine lab, 450 games: 2002 starters C 9.4, PF 6.7,
    # SF 4.1, SG 4.2, PG 3.6, leader 13.5.
    REBOUND_RATING_EXPONENT: float = 1.35
    # Multipliers by type of missed shot: centers and power forwards control interior glass; long rebounds disperse more
    REBOUND_ROLE_MULTIPLIER_INTERIOR: dict = field(default_factory=lambda: {
        'C': 1.35, 'PF': 1.15, 'SF': 0.95, 'SG': 0.85, 'PG': 0.80,
    })
    REBOUND_ROLE_MULTIPLIER_PERIMETER: dict = field(default_factory=lambda: {
        'C': 1.15, 'PF': 1.08, 'SF': 1.00, 'SG': 0.95, 'PG': 0.92,
    })
    TURNOVER_MODIFIER_FACTOR: float = 10.0
    PASS_TURNOVER_ABILITY_FACTOR: float = 20.0

@dataclass(frozen=True)
class Assist:
    """Configuration for assists."""
    MAX_PER_GAME: int = 999

@dataclass(frozen=True)
class Playmaking:
    """Score-or-pass choices in the possession engine (core/game_engine.Partita helpers). Each used to be a hard
    threshold (touch <= 70 to pass on a drive, -30 extra-pass chance for any good shooter...): passers like Nash
    finished every drive and scorer-passers like Luka passed first on every DROP pick and roll."""
    # Drive with no help (_drive_dish_chance): playmaking x PLAY + dish x DISH + (vision - 50) x VISION
    # - hero ball x HERO - (touch - TOUCH_FROM) x TOUCH - (close/dunk - FINISHER_FROM) x FINISHER - OFFSET, 0..MAX.
    DRIVE_DISH_PLAY: float = 0.45
    DRIVE_DISH_DISH: float = 0.30
    DRIVE_DISH_VISION: float = 0.35
    DRIVE_DISH_HERO: float = 0.40
    DRIVE_DISH_TOUCH_FROM: float = 65.0
    DRIVE_DISH_TOUCH: float = 0.50
    DRIVE_DISH_FINISHER_FROM: float = 78.0
    DRIVE_DISH_FINISHER: float = 1.0
    DRIVE_DISH_OFFSET: float = 15.0
    DRIVE_DISH_MAX: float = 95.0
    # Kick-out on help (_kickout_chance): vision/pass-out/playmaking minus the finisher malus (close/dunk over 78)
    # and hero ball over HERO_FROM (it read touch, which is how often a player gets the ball, not how he uses it).
    KICKOUT_HERO_FROM: float = 55.0
    KICKOUT_HERO: float = 0.60
    # Extra pass on the perimeter (_extra_pass_chance): an open good shooter loses (best shot - FROM) x PER_POINT
    # of pass chance, up to MAX, reduced by (vision - VISION_FROM) x VISION_RELIEF (at most VISION_RELIEF_MAX).
    # It was a flat -30 for anyone with 3PT >= 78 or MID >= 80: Nash and Curry stopped moving the ball.
    EXTRA_PASS_SHOOTER_FROM: float = 70.0
    EXTRA_PASS_PER_POINT: float = 2.0
    EXTRA_PASS_MAX: float = 32.0
    EXTRA_PASS_VISION_FROM: float = 70.0
    EXTRA_PASS_VISION_RELIEF: float = 0.015
    EXTRA_PASS_VISION_RELIEF_MAX: float = 0.50
    # P&R against a DROP big (_drop_pull_up_share): the handler keeps it (pull-up) with a logistic share of
    # (max(3PT, MID) + hero x HERO) - (playmaking x PLAY + vision x VISION), over SCALE, clamped MIN..MAX. Handlers
    # under SKILL_FLOOR at both shooting and playmaking keep the old weak read. Before, playmaking >= 75 was tested
    # first: Luka passed to the roller on 63% of DROP picks whatever his jumper.
    DROP_HERO: float = 0.50
    DROP_PLAY: float = 0.80
    DROP_VISION: float = 0.60
    DROP_SCALE: float = 15.0
    DROP_SHARE_MIN: float = 0.05
    DROP_SHARE_MAX: float = 0.85
    DROP_SKILL_FLOOR: float = 70.0
    # Who starts a possession (_initiation_factor): (1 + skill/130) x (1 + CREATOR_MAX x ramp) x label, where skill
    # = vision .40 + handling .30 + shot IQ .15 + playmaking .15 and ramp goes 0 -> 1 as handling .4 + vision .4 +
    # playmaking .2 goes CREATOR_FROM -> CREATOR_TO. The label keeps a share (PG / SG). It was PG x1.40 then steps
    # by vision: creators not labeled PG (Harden, LeBron, Jokic) ran far fewer possessions.
    INIT_CREATOR_FROM: float = 60.0
    INIT_CREATOR_TO: float = 90.0
    INIT_CREATOR_MAX: float = 0.55
    INIT_LABEL: dict = field(default_factory=lambda: {'PG': 1.20, 'SG': 1.05})
    # Shot volume is paid in percentage (_volume_tax), never with a cap on shots: jump shots lose (FGA - FROM) x
    # PER_FGA points of make chance up to HIGH_FROM FGA in the game, then HIGH_PER_FGA more per shot, up to MAX;
    # shots at the rim lose INTERIOR_SHARE of it. It stopped at -6 and spared the rim: 20-shot stars shot ~50%.
    # The rim paid half: lone bigs (Embiid, Giannis) took 24 shots a night at 65% TS.
    VOLUME_TAX_FROM: int = 14
    VOLUME_TAX_PER_FGA: float = 0.5
    VOLUME_TAX_HIGH_FROM: int = 18
    VOLUME_TAX_HIGH_PER_FGA: float = 1.0
    VOLUME_TAX_MAX: float = 12.0
    VOLUME_TAX_INTERIOR_SHARE: float = 0.75
    # Focus of a solo-carry star (Squadra.focus_rank_weights): up to this many points of focus chance move to the #1.
    # 14 (2026-11-26) gave 7 players 30+ PPG in a modern league, lone stars 28 PPG on a higher TS% than shared ones.
    SOLO_CARRY_P1_BONUS: float = 8.0
    # Crowded paint at the rim (Partita._crowded_paint_malus): from CROWD_FGA_FROM shots in the game, a shooter loses
    # PER_POINT x weakness (max MAX) of make chance, weakness = the larger of (MATES_OVR - teammates' average OVR) and
    # (own OVR - teammates' average - STAR_GAP). Only guards and wings paid it, on an absolute line: a 95 big with
    # 79-rated teammates never did.
    CROWD_FGA_FROM: int = 16
    CROWD_MATES_OVR: float = 74.5
    CROWD_STAR_GAP: float = 10.0
    CROWD_PER_POINT: float = 0.6
    CROWD_MAX: float = 3.0
    # Post-up finish (Partita._post_fade_chance): a post scorer who shoots and loves the mid-range (rating >= MID_FROM,
    # tendency >= TEND_FROM) turns into a fadeaway jumper with BASE + PER_TEND x (tendency - TEND_FROM) + PER_EDGE x
    # (mid rating - best of post control / close shot) percent, from 0 to MAX. Every post-up ended at the rim:
    # Dirk (mid 93) took 16 shots a night at the rim and 3.6 from mid-range.
    POST_FADE_MID_FROM: float = 78.0
    POST_FADE_TEND_FROM: float = 55.0
    POST_FADE_BASE: float = 10.0
    POST_FADE_PER_TEND: float = 1.0
    POST_FADE_PER_EDGE: float = 1.0
    POST_FADE_MAX: float = 65.0

@dataclass(frozen=True)
class HomeCourt:
    """Configuration for the home-court advantage."""
    # Fixed percentage bonus added to the home team's shooting probability (~1.5% NBA standard)
    SHOOTING_BONUS: float = 1.5

    # Multiplier applied to the foul probability.
    # > 1.0 favors the home attacker, < 1.0 favors the home defender.
    FOUL_CHANCE_MODIFIER: float = 1.05 # A standard 5% referee "favor"


# << NEW CLASS >>
@dataclass(frozen=True)
class Progression:
    """## CHANGED: Stronger regression and development tied to experience."""

    # Share of the gap to potential a young player (<= 25) closes in a year with full minutes. 0.30 took everyone
    # who played to his ceiling by 25: a progression-only lab (20 offseasons, 8 seeds) had 85+ players 32 -> 48 at
    # year 10; 0.25 keeps the talent curve near the start (top-8 77.6 -> 77.4, 85+ 32 -> 30 at year 20).
    DEV_FACTOR_POTENTIAL_GAP: float = 0.25
    DEV_POINT_MAX_GAIN_PER_YEAR: int = 7
    DEV_SKILL_POINT_MULTIPLIER: int = 7

    AGE_RETIREMENT_THRESHOLD: int = 36
    RETIREMENT_BASE_CHANCE: float = 6.0
    RETIREMENT_AGE_FACTOR: float = 2.0
    RETIREMENT_LOW_RATING_FACTOR: float = 1.1
    BUST_THRESHOLD_OVR: int = 75
    BUST_THRESHOLD_POTENZIALE: int = 80

    # Variable potential (Phase 2b): every offseason a player up to POT_DRIFT_MAX_AGE sees his potential move.
    # A breakout (POT_BREAKOUT_CHANCE, more after a strong season with real minutes) raises it, a setback
    # (POT_SETBACK_CHANCE) lowers it, otherwise it drifts by -1/0/+1. Before, everyone who played reached his
    # birth potential by 25: no busts, no steals, and a long save filled with 85+ players.
    POT_DRIFT_MAX_AGE: int = 24
    POT_BREAKOUT_CHANCE: float = 0.05
    POT_BREAKOUT_STRONG_SEASON_BONUS: float = 0.07   # added when the season was >= 3 over his OVR with 18+ minutes
    POT_BREAKOUT_RANGE: tuple = (3, 8)
    POT_SETBACK_CHANCE: float = 0.14
    POT_SETBACK_RANGE: tuple = (2, 5)
    POT_NOISE: tuple = (-1, 0, 0, 1)
    # Era-neutral performance (core/models.py league_season_scales): a season's PVS and the per-game totals that
    # push progression (24/28 PPG, 9 APG, 11.5 RPG) are measured against these league means of players with
    # PVS_SCALE_MIN_MINUTES (2002 seasons of a long save: offense / defense index, points, assists, rebounds per 36).
    # Without it the PVS minus OVR of the league went from -0.6 (2002) to +2.1 (2026): OVR inflation.
    PVS_REFERENCE: dict = field(default_factory=lambda: {'off': 12.5, 'def': 13.9, 'pts': 12.9, 'ast': 2.95, 'reb': 6.3})
    PVS_SCALE_MIN_MINUTES: float = 500.0
    PVS_SCALE_MIN_PLAYERS: int = 60
    # Aging stars: from 32 a player with OVR >= AGING_STAR_MIN_OVR whose season PVS is at least his OVR +
    # AGING_STAR_GOOD_SEASON_DELTA (about the best quarter of veteran star seasons) loses at most the AGING_STAR_LOSS
    # of his age ((max age, change), first match). Before, everyone lost 2-7 a year from 33: nobody played past 37.
    AGING_STAR_MIN_OVR: int = 84
    AGING_STAR_GOOD_SEASON_DELTA: float = -2.0
    AGING_STAR_LOSS: tuple = ((34, 0), (36, -1), (38, -2), (99, -3))
    # Usage tendencies move with every OVR point a player under 33 gains or loses (the curated league's slope).
    USAGE_TENDENCY_PER_OVR: dict = field(default_factory=lambda: {'touch_tendency': 1.5, 'hero_ball_tendency': 0.8})
    # ...a gain only up to the tendency's place on that slope for the new OVR (ROOKIEGEN line) + this margin.
    USAGE_TARGET_MARGIN: float = 10.0   # curated 2002 stars sit up to ~9 above it (Kobe +7, Iverson +9, Shaq +7)


@dataclass(frozen=True)
class Simulation:
    """General simulation configuration. (v14.3 - Calibrated Pace)"""
    QUARTERS: int = 4
    
    
    MVP_WIN_BONUS: float = 1.8
    # Veterans lose touches in Partita._simula_possesso from these ages (elite = star, OVR >= ELITE_OVR or the 1st
    # option). Non-elite players started at 30: Nash at 31 and 84 OVR lost the ball next to a 27-year-old Dirk.
    VETERAN_TOUCH_START_AGE: int = 33
    VETERAN_TOUCH_START_AGE_ELITE: int = 35
    VETERAN_TOUCH_ELITE_OVR: int = 86
    # Playoff half-court: the chance a playoff possession takes one extra second to set up. It was +1-2 s on every
    # possession: ~12% fewer possessions than the regular season (NBA playoffs play ~2-4% slower).
    PLAYOFF_EXTRA_SECOND_CHANCE: float = 0.35
    # Load management by era (main.py Tournament._load_management_factor): the rest chances of tired stars are
    # scaled by EARLY_FACTOR up to the first ramp year, then rise linearly to the full chance at the second.
    # It was the full chance in every era: 85+ players averaged ~71 GP in 2002 as in 2026.
    LOAD_MANAGEMENT_EARLY_FACTOR: float = 0.25
    LOAD_MANAGEMENT_RAMP_YEARS: tuple = (2012, 2019)
@dataclass(frozen=True)
class Coaching:
    """Configuration for coach logic and substitutions. (v16.0 - Smart Coach)"""
    # How many game seconds pass before the coach reconsiders substitutions
    SUBSTITUTION_CHECK_INTERVAL_SECONDS: int = 300 # Every 5 game minutes (reduced from 360)

    SUBSTITUTION_CRITICAL_ENERGY_LIMIT: int = 20 # Very low energy

    # Thresholds for a "rotation" substitution
    SUBSTITUTION_LOW_ENERGY_LIMIT: int = 60 # Low energy, a good moment for a change


    # Foul limits
    FOUL_OUT_LIMIT: int = 6
    
    MINUTES_TARGET_TOLERANCE: int = 4

    # Coach development, once per offseason (Tournament._gestisci_progressione_coach). Ratings grow only after a
    # season over expectations: +1 per GROWTH_WINS_PER_POINT wins above the expected, at most
    # GROWTH_MAX_PER_SEASON, up to the coach's potential and before GROWTH_MAX_AGE. From DECLINE_AGE offense and
    # defense fall 1 a year (floor DECLINE_FLOOR). It was +1 a year for almost everyone plus +1 per level-up
    # in games: after 25 seasons the 30 head coaches averaged 90.5 OFF / 91.1 DEF.
    # Regular-season minutes cap of a rotation player's target, by season start year ((last year, cap), ...): stars
    # played 41-42 minutes in 2002 and rarely 37 in the 2020s. Played minutes run ~1.5 over the target.
    # Playoff targets may go PLAYOFF_MINUTES_EXTRA higher.
    MINUTES_CAP_BY_YEAR: tuple = ((2009, 40), (2016, 38), (9999, 36))
    PLAYOFF_MINUTES_EXTRA: int = 3
    GROWTH_WINS_PER_POINT: int = 8
    GROWTH_MAX_PER_SEASON: int = 2
    GROWTH_MAX_AGE: int = 60
    DECLINE_AGE: int = 62
    DECLINE_FLOOR: int = 60
    # A CPU head coach under contract retires by age (main.coach_retires_now): from RETIRE_MIN_AGE with
    # RETIRE_BASE_CHANCE + RETIRE_CHANCE_PER_YEAR per year over it, always at RETIRE_MAX_AGE (one coached at 84).
    RETIRE_MIN_AGE: int = 66
    RETIRE_BASE_CHANCE: float = 0.15
    RETIRE_CHANCE_PER_YEAR: float = 0.10
    RETIRE_MAX_AGE: int = 75

@dataclass(frozen=True)
class Economy:
    SALARY_CAP: float = 155.0
    SALARY_FLOOR_RATIO: float = 0.90
    LUXURY_TAX_THRESHOLD: float = 185.0
    FIRST_APRON: float = 195.0
    SECOND_APRON: float = 205.0
    MLE_VALUE: float = 12.5
    BAE_VALUE: float = 4.5  # Biannual Exception — secondary signing tool
    # Finances & CBA page: CBA lines at or above this value mean "no limit" (no aprons before 2023, no-cap mode)
    UNLIMITED_LINE: float = 9000.0
    FINANCES_LIST_SIZE: int = 5  # rows in Top salaries / Bargains / Overpays / Market watch
    OUTLOOK_YEARS: int = 4  # seasons shown in a team's salary outlook
    
    # --- Owner personalities (shared by economy, trades, coaching and the Board) ---
    OWNER_TYPES: Tuple[str, ...] = ("Spendaccione", "Esigente", "Bilanciato", "Ricostruttore", "Risparmiatore")
    # Random owners for teams without a curated owner in the era DB
    OWNER_DISTRIBUTION: Tuple[str, ...] = tuple(["Spendaccione"] * 6 + ["Bilanciato"] * 18 + ["Risparmiatore"] * 6)
    # Legacy names still found in old saves / data
    OWNER_TYPE_ALIASES: dict = field(default_factory=lambda: {"Equilibrato": "Bilanciato"})
    # Payroll ceiling tier used by FA and extensions: 'low' | 'mid' | 'high'
    OWNER_SPENDING_TIER: dict = field(default_factory=lambda: {
        "Spendaccione": "high", "Esigente": "high", "Bilanciato": "mid",
        "Ricostruttore": "low", "Risparmiatore": "low",
    })
    # A 'low' spending owner (saver, rebuilder) pays at most this share of the cap over the luxury tax, in free
    # agency (Bird rights) and in extensions. It was tax + $30M flat: savers ended over the second apron.
    LOW_OWNER_OVER_TAX_SHARE: float = 0.05
    # Board profile scales (1 = low, 5 = high)
    OWNER_BOARD_PATIENCE: dict = field(default_factory=lambda: {
        "Esigente": 1, "Spendaccione": 2, "Risparmiatore": 3, "Bilanciato": 4, "Ricostruttore": 5,
    })
    OWNER_BOARD_SPENDING: dict = field(default_factory=lambda: {
        "Risparmiatore": 1, "Ricostruttore": 2, "Bilanciato": 3, "Esigente": 4, "Spendaccione": 5,
    })
    # Invented owner names for the Board profile when the league file brings none (league staff.owner_names wins)
    OWNER_NAMES: tuple = (
        "Harold Whitcomb", "Diane Ashby", "Richard Vanterpool", "Margaret Ellsworth", "Leonard Krantz",
        "Theodore Banning", "Victoria Halloran", "Samuel Oyelaran", "Gerald Fairbanks", "Catherine Dunmore",
        "Raymond Kessinger", "Eleanor Voss", "Martin Delgado", "Frederick Hale", "Patricia Lindgren",
        "Howard Brightwater", "Nathan Goldfarb", "Conrad Weatherby", "Lillian Marsh", "Douglas Prentiss",
        "Arthur Kingsley", "Beatrice Coulter", "Franklin Mercer", "Josephine Albrecht", "Warren Talbot",
        "Irene Castellanos", "Charles Wexley", "Monica Fairweather", "Edmund Rourke", "Sylvia Northcott",
    )


    
    ROOKIE_SALARY_SCALE: dict = field(default_factory=lambda: {
        1: 15.0, 5: 11.0, 10: 8.0, 20: 5.0, 30: 3.5
    })

    
    AWARD_SALARY_BONUSES: dict = field(default_factory=lambda: {
        "MVP": 4.0,
        "Finals MVP": 3.0,
        "All-NBA 1st": 2.5,
        "All-NBA 2nd": 2.0,
        "All-NBA 3rd": 1.5,
        "DPOY": 2.0,
        "Campione NBA": 1.5,
        "All-Star": 1.5,
        "6th Man": 1.0,
        "6MOY": 1.0,
        "MIP": 1.0,
        "ROY": 1.5
    })

    MIN_SALARY: float = 3.5
    MAX_SALARY_THEORETICAL: float = 60.0
    # Max contract: share of the cap one player can earn in year 1 (user and CPU, every FA path).
    MAX_CONTRACT_CAP_PCT: float = 0.35

    YEARLY_CAPS: dict = field(default_factory=lambda: {
        2002: 40.27, 2003: 43.84, 2004: 43.87, 2005: 49.50,
        2006: 53.13, 2007: 55.63, 2008: 58.68, 2009: 57.70,
        2010: 58.04, 2011: 58.04, 2012: 58.04, 2013: 58.68,
        2014: 63.06, 2015: 70.00, 2016: 94.14, 2017: 99.09,
        2018: 101.87, 2019: 109.14, 2020: 109.14, 2021: 112.41,
        2022: 123.65, 2023: 136.02, 2024: 140.58, 2025: 155.00
    })

    def get_cap_for_year(self, year: int, raw_cap: float = 155.0, is_no_cap: bool = False) -> float:
        """Returns the appropriate salary cap for the given year, taking into account No-Cap mode."""
        if is_no_cap:
            return self.YEARLY_CAPS.get(year, self.SALARY_CAP)
        return raw_cap

@dataclass(frozen=True)
class CoachingStyles:
    """ ## EXPANDED VERSION: More styles and coaches for greater strategic variety. ## """
    # We define the play styles and their modifiers.
    # 'tendenze': { 'tendency_name': multiplier } -> Changes the player's decisions.
    # 'abilita': { 'ability_name': flat_bonus } -> Improves the players' attributes.
    STYLES: dict = field(default_factory=lambda: {
    # --- REWORKED v5.0: Ogni stile ha trade-off chiari ---
    # Net budget: ~8-10 ability points per style
    # Principle: if you gain on offense, you lose on defense and vice versa
    
    # --- Offense-Oriented Styles ---
    "Pace & Space": {
        "descrizione": "High pace, open floor, three-pointers and drives. Modern and efficient.",
        "tendenze": {"three_point_shot_tendency": 1.30, "drive_to_basket_tendency": 1.15, "pass_out_of_shot_tendency": 1.1},
        "abilita": {"speed": 3, "acceleration": 3, "stamina": 2, "interior_defense_rating": -2, "strength": -1},
        "schemi": {"PICK_AND_ROLL": 35, "SPOT_UP_SHOT": 30, "ISOLATION": 15, "CUT_TO_BASKET": 12, "DHO": 8, "POST_UP": 0}
    },
    "Run and Gun": {
        "descrizione": "Frenetic offense, fast transition and quick shots, often driven by individual stars.",
        "tendenze": {"three_point_shot_tendency": 1.20, "touch_tendency": 1.25},
        "abilita": {"speed": 4, "shot_iq": -3, "passing_accuracy": -2, "interior_defense_rating": -2},
        "schemi": {"ISOLATION": 35, "SPOT_UP_SHOT": 25, "PICK_AND_ROLL": 25, "CUT_TO_BASKET": 10, "DHO": 5, "POST_UP": 0}
    },
    "Triangle Offense": {
        "descrizione": "Thoughtful play based on spacing, cuts and multiple options, with a focus on the post and mid-range shots.",
        "tendenze": {"mid_range_shot_tendency": 1.35, "post_up_tendency": 1.2, "pass_out_of_shot_tendency": 1.25},
        "abilita": {"passing_accuracy": 3, "shot_iq": 3, "close_shot_rating": 2, "speed": -2, "acceleration": -1},
        "schemi": {"POST_UP": 25, "DHO": 15, "CUT_TO_BASKET": 25, "SPOT_UP_SHOT": 15, "PICK_AND_ROLL": 12, "ISOLATION": 8}
    },
    "Perimeter-centric": {
        "descrizione": "An offense obsessed with the perimeter. Threes or drives, nothing else.",
        "tendenze": {"three_point_shot_tendency": 1.45, "drive_to_basket_tendency": 1.2, "mid_range_shot_tendency": 0.7},
        "abilita": {"three_point_shot_rating": 3, "ball_handling": 2, "interior_defense_rating": -3, "offensive_rebound_rating": -2},
        "schemi": {"SPOT_UP_SHOT": 35, "PICK_AND_ROLL": 30, "ISOLATION": 18, "CUT_TO_BASKET": 10, "DHO": 7, "POST_UP": 0}
    },
    "Post Play Dominance": {
        "descrizione": "The offense revolves around a dominant big man in the low post, slowing the pace.",
        "tendenze": {"post_up_tendency": 1.20, "three_point_shot_tendency": 0.85, "pass_out_of_shot_tendency": 1.10},
        "abilita": {"strength": 3, "close_shot_rating": 3, "offensive_rebound_rating": 2, "speed": -2, "acceleration": -2},
        "schemi": {"POST_UP": 45, "DHO": 15, "CUT_TO_BASKET": 15, "SPOT_UP_SHOT": 10, "PICK_AND_ROLL": 8, "ISOLATION": 7}
    },

    # --- Defense-Oriented Styles ---
    "Grit & Grind": {
        "descrizione": "Physical defense, slow pace and offense based on isolations and post play. Won in the mud.",
        "tendenze": {"post_up_tendency": 1.2, "drive_to_basket_tendency": 1.15, "mid_range_shot_tendency": 1.1},
        "abilita": {"strength": 3, "perimeter_defense_rating": 3, "interior_defense_rating": 3, "speed": -2, "three_point_shot_rating": -2},
        "schemi": {"ISOLATION": 30, "POST_UP": 25, "PICK_AND_ROLL": 25, "SPOT_UP_SHOT": 12, "CUT_TO_BASKET": 8, "DHO": 0}
    },
    "Defensive Minded": {
        "descrizione": "Defense first. The offense is secondary, often conservative and not specialized.",
        "tendenze": {},
        "abilita": {"perimeter_defense_rating": 4, "interior_defense_rating": 4, "steal_rating": 2, "shot_iq": -2, "passing_vision": -2},
        "schemi": {"PICK_AND_ROLL": 28, "SPOT_UP_SHOT": 22, "ISOLATION": 18, "POST_UP": 15, "CUT_TO_BASKET": 12, "DHO": 5}
    },
    "Man-to-Man Lockdown": {
        "descrizione": "Aggressive, suffocating man-to-man defense all over the court.",
        "tendenze": {},
        "abilita": {"perimeter_defense_rating": 4, "interior_defense_rating": 3, "steal_rating": 2, "stamina": 2, "shot_iq": -3, "passing_accuracy": -2},
        "schemi": {"ISOLATION": 25, "PICK_AND_ROLL": 30, "SPOT_UP_SHOT": 20, "POST_UP": 12, "CUT_TO_BASKET": 8, "DHO": 5}
    },
    "Twin Towers": {
        "descrizione": "Dominates the paint on both sides of the floor with two bigs. Slow pace and rim protection.",
        "tendenze": {"post_up_tendency": 1.2, "drive_to_basket_tendency": 0.85},
        "abilita": {"interior_defense_rating": 3, "block_rating": 3, "strength": 2, "defensive_rebound_rating": 3, "speed": -3, "three_point_shot_rating": -2},
        "schemi": {"POST_UP": 40, "DHO": 18, "CUT_TO_BASKET": 18, "PICK_AND_ROLL": 12, "SPOT_UP_SHOT": 7, "ISOLATION": 5}
    },

    # --- Balanced / System Styles ---
    "Balanced Offense": {
        "descrizione": "A balanced approach that tries to exploit every offensive option without specializing.",
        "tendenze": {},
        "abilita": {"shot_iq": 2, "free_throw_rating": 2, "passing_accuracy": 2, "passing_vision": 2},
        "schemi": {"PICK_AND_ROLL": 25, "ISOLATION": 20, "SPOT_UP_SHOT": 20, "POST_UP": 12, "CUT_TO_BASKET": 15, "DHO": 8}
    },
    "System Basketball": {
        "descrizione": "Ball and player movement is king. Always looking for the best shot, not the best shooter.",
        "tendenze": {"dish_to_open_man_tendency": 1.4, "pass_out_of_shot_tendency": 1.3},
        "abilita": {"shot_iq": 4, "passing_vision": 3, "passing_accuracy": 2, "ball_handling": -2},
        "schemi": {"CUT_TO_BASKET": 25, "SPOT_UP_SHOT": 22, "DHO": 22, "PICK_AND_ROLL": 20, "ISOLATION": 6, "POST_UP": 5}
    },
    "Fast Break Offense": {
        "descrizione": "Push the ball in transition at every opportunity to attack before the defense sets up.",
        "tendenze": {"three_point_shot_tendency": 1.25, "drive_to_basket_tendency": 1.20, "touch_tendency": 1.15, "post_up_tendency": 0.7},
        "abilita": {"speed": 3, "acceleration": 3, "passing_vision": 2, "interior_defense_rating": -2, "strength": -2},
        "schemi": {"ISOLATION": 28, "SPOT_UP_SHOT": 28, "PICK_AND_ROLL": 22, "CUT_TO_BASKET": 15, "DHO": 7, "POST_UP": 0}
    },
    "Point Guard Maestro": {
        "descrizione": "The whole offense runs through the point guard's hands, who orchestrates the game mainly through the Pick and Roll.",
        "tendenze": {"dish_to_open_man_tendency": 1.40, "pass_out_of_shot_tendency": 1.30, "touch_tendency": 1.35},
        "abilita": {"passing_vision": 3, "passing_accuracy": 3, "ball_handling": 2, "shot_iq": 2, "interior_defense_rating": -2, "strength": -2},
        "schemi": {"PICK_AND_ROLL": 45, "SPOT_UP_SHOT": 22, "ISOLATION": 15, "DHO": 10, "CUT_TO_BASKET": 8, "POST_UP": 0}
    },
    "Small Ball Strategy": {
        "descrizione": "Sacrifices size for speed, versatility and three-point shooting. The goal is to create mismatches and open up the floor.",
        "tendenze": {"three_point_shot_tendency": 1.30, "drive_to_basket_tendency": 1.25, "post_up_tendency": 0.65},
        "abilita": {"speed": 3, "acceleration": 2, "three_point_shot_rating": 2, "ball_handling": 2, "interior_defense_rating": -3, "block_rating": -2, "defensive_rebound_rating": -2},
        "schemi": {"SPOT_UP_SHOT": 32, "PICK_AND_ROLL": 28, "ISOLATION": 22, "CUT_TO_BASKET": 10, "DHO": 8, "POST_UP": 0}
    }
})
    
    # Invented coach names (initial coaches and generated candidates) when the league file brings none
    # (league staff.coach_names wins). Candidates mix first and last names once every full name is in use.
    COACH_NAMES: list = field(default_factory=lambda: [
        "Walt Kessler", "Ron Dorsey", "Glen Hadley", "Marty Pruitt", "Hank Lindqvist",
        "Dale Whitaker", "Gene Marchetti", "Russ Abernathy", "Lou Castellano", "Vern Osgood",
        "Stan Hollister", "Ed Brannigan", "Phil Gustafson", "Norm Riordan", "Carl Vandermeer",
        "Ted Okonkwo", "Barry Lindell", "Mitch Calloway", "Roy Fennimore", "Jim Haskell",
        "Kurt Ellingson", "Dwight Pemberton", "Lyle Garrity", "Neil Ashcroft", "Gordon Faulk",
        "Rex Tolliver", "Duane Merriweather", "Clint Radcliffe", "Mel Sorensen", "Art Delacroix",
        "Ray Whitfield", "Bud Kowalczyk", "Sid Marlowe", "Frank Iverstad", "Wes Harrington",
        "Les Gallagher", "Jerry Vantassel", "Tom Brackett", "Hal Prescott", "Doug Ainsworth",
        "Murray Klein", "Rich Tavares", "Pat Donnegan", "Bobby Lomax", "Chuck Severin",
        "Dennis Albright", "Keith Ramsdell", "Mike Stavros", "Joe Hennessey", "Andre Lucien",
        "Greg Upshaw", "Rod Castillo", "Bill Thorsen", "Terrence Wilkes", "Paul Okerlund",
        "Steve Ransome",
    ])
    PLAYOFF_ROTATION_SIZES: dict = field(default_factory=lambda: {
        # Styles that rely on a narrow core
        "Grit & Grind": 8,
        "Defensive Minded": 8,
        "Man-to-Man Lockdown": 8,
        "Triangle Offense": 8,
        
        # Styles that keep a bit more depth
        "Pace & Space": 9,
        "Balanced Offense": 9,
        "System Basketball": 9,
        "Point Guard Maestro": 9,

        # Styles that can benefit from fresh, specialized bodies
        "Run and Gun": 10,
        "Small Ball Strategy": 10,
        "Fast Break Offense": 10
    })
@dataclass(frozen=True)
class CoachingTactics:
    """Defines the in-game tactical adjustments (Points of Emphasis) a coach can make."""
    POINTS_OF_EMPHASIS: dict = field(default_factory=lambda: {
        # --- Offensive POEs ---
        "Pound the Paint": {
            "description": "Focus on driving to the basket and post-ups.",
            "tendency_mods": {"drive_to_basket_tendency": 1.4, "post_up_tendency": 1.3, "three_point_shot_tendency": 0.7}
        },
        "Hunt for Threes": {
            "description": "Prioritize finding and taking three-point shots.",
            "tendency_mods": {"three_point_shot_tendency": 1.5, "mid_range_shot_tendency": 0.6}
        },
        "Feed the Hot Hand": {
            "description": "Get the ball to the player who is currently on a hot streak.",
            "tendency_mods": {} # This is a special case handled in game logic
        },
        "Push the Pace": {
            "description": "Play faster, look for quick shots.",
            "ability_mods": {"speed": 2, "acceleration": 2} # This will require a small engine change
        },
        
        # --- Defensive POEs ---
        "Protect the Paint": {
            "description": "Collapse the defense to prevent inside scoring.",
            # This will be handled by logic (e.g., increased help defense chance)
            "logic_mods": {"help_defense_chance_modifier": 1.25}
        },
        "Run Shooters Off the Line": {
            "description": "Aggressively close out on perimeter shooters.",
            "ability_mods": {"perimeter_defense_rating": 3, "strength": -2} # Trade-off: better closeouts, but more vulnerable to drives
        },
        "Full-Court Press": {
            "description": "Apply pressure the full length of the court to force turnovers.",
            # This will be handled by logic (e.g., increased steal/turnover chance)
            "logic_mods": {"steal_attempt_modifier": 1.5, "fatigue_increase_modifier": 1.3}
        },

        # --- Default State ---
        "Balanced Approach": {
            "description": "Standard, balanced game plan.",
            "tendency_mods": {}
        }
    })
@dataclass(frozen=True)
class Injuries:
    """Configuration for the realistic NBA injury logic. (v6.1 - Rebalanced NBA Rates)"""
    # Check at every substitution interval (~16 times per game)
    # Calibrated for realistic NBA rates (~3-4 injuries per franchise per season, 90-110 league-wide, 70% Day-to-Day)
    BASE_INJURY_CHANCE: float = 0.075
    # Injuries are counted in calendar days (giorni_infortunio_rimanenti). The catalog in game_engine lists games:
    # a length is games x DAYS_PER_GAME. Regular season: one day off per calendar day; playoffs (no calendar days):
    # DAYS_PER_GAME per team game; the offseason heals OFFSEASON_HEAL_DAYS.
    DAYS_PER_GAME: float = 2.0
    OFFSEASON_HEAL_DAYS: int = 150
    # Share (%) of injuries by tier: day-to-day, minor, moderate, severe; the rest is season-ending. Was 72 / 19 /
    # 6.5 / 1.8 (0.7 season-ending): in 3 seasons not one 80+ player missed 22 games.
    SEVERITY_SHARES: tuple = (58.0, 24.0, 10.0, 5.0)

    # Wear and fatigue factors
    STAMINA_IMPACT_FACTOR: float = 0.0010
    FATIGUE_IMPACT_FACTOR: float = 0.0010


@dataclass(frozen=True)
class Dashboard:
    """Thresholds for the Dashboard form tags and the playoff picture shown in Standings."""
    # A team is HOT on a win streak of this length, or on this many wins in its last 10.
    HOT_STREAK_MIN: int = 5
    HOT_L10_WINS_MIN: int = 8
    # A team is COLD on a loss streak of this length, or on at most this many wins in its last 10.
    COLD_STREAK_MIN: int = 4
    COLD_L10_WINS_MAX: int = 2
    # Conference seeds: direct playoff spots, last play-in seed, and playoff spots when the play-in is off.
    PLAYOFF_SEEDS: int = 6
    PLAY_IN_LAST_SEED: int = 10
    PLAYOFF_SEEDS_WITHOUT_PLAY_IN: int = 8
    # Stat leaders: a player needs this share of the most games anyone has played (was a fixed 40 games).
    LEADERS_MIN_GP_SHARE: float = 0.5


@dataclass(frozen=True)
class History:
    """What the History page shows, and the Hall of Fame election bar (Tournament Hall of Fame vote)."""
    # Hall of Fame: the score to be elected and listed; tiers are (name, min score), highest first.
    HOF_MIN_SCORE: int = 300     # also the election bar: a class may be empty (it took 110, or 45 in a weak year)
    HOF_MAX_CLASS: int = 6
    # A title's worth by the player's share in it (contribution = PPG + 1.2 RPG + 1.5 APG, main.calcola_hof_score):
    # (min contribution, points), highest first; below the last, nothing. MVP / Finals MVP / All-NBA that season = a
    # leader. Only leader titles count for the 3- and 5-title bonuses. The old bars (18 -> 75, 10 -> 35, 5 -> 10, all
    # counting for the bonus) elected 5-ring bench players (5.6 PPG) above Curry and Nowitzki.
    HOF_TITLE_POINTS: tuple = ((30.0, 75), (20.0, 25), (12.0, 10))
    HOF_TITLES_BONUS: tuple = ((3, 60), (5, 80))
    HOF_TIERS: tuple = (("Legends", 600), ("Hall of Famers", 300))
    # Championships: league standings rows shown per season, and the window for the "N in M" title run.
    TOP_STANDINGS: int = 3
    RUN_WINDOW: int = 4
    # Leaders and records: rows per league board, per franchise board, triple-doubles ladder.
    LEADERS_TOP_N: int = 25
    FRANCHISE_LEADERS_TOP_N: int = 10
    TRIPLE_DOUBLES_TOP_N: int = 10
    # A single-season per-game record needs at least this many games that season.
    SEASON_RECORD_MIN_GAMES: int = 50


@dataclass(frozen=True)
class EndSeason:
    """End of Season Hub pages: rows shown and the thresholds behind their verdicts (display only)."""
    OPTIONS_AROUND_LEAGUE: int = 8  # other teams' player options listed on Contract options
    DEV_LEAGUE_ROWS: int = 5  # league risers / drops on Development & retirements
    # Pre-draft offers: value gained as a share of the value you give (trade engine points); at or above GOOD reads
    # "good for you", at or below BAD "bad for you".
    TRADE_VALUE_GOOD: float = 0.10
    TRADE_VALUE_BAD: float = -0.10
    # New season grade: change in team strength (mean OVR of the top TOP_N_STRENGTH) -> letter; below the last step "D".
    GRADE_STEPS: tuple = ((2.0, "A"), (1.0, "A-"), (0.5, "B+"), (0.0, "B"), (-0.5, "C+"), (-1.0, "C"))
    TOP_N_STRENGTH: int = 8
    POWER_RANKING_ROWS: int = 10
    LEAGUE_MOVES: int = 5

@dataclass(frozen=True)
class ScoutingMatchups:
    """Opponent tab: how threats are ranked and when a matchup counts as bad."""
    # Gap = defender's matching defense minus the attacker's skill. At or below BAD_GAP it is a bad
    # matchup, at or below WATCH_GAP it is worth watching.
    BAD_GAP: int = -20
    WATCH_GAP: int = -10
    # Danger = skill * minutes/48 * (TENDENCY_BASE + TENDENCY_SPAN * tendency/100) + max(0, -gap) * GAP_WEIGHT
    GAP_WEIGHT: float = 1.0
    TENDENCY_BASE: float = 0.6
    TENDENCY_SPAN: float = 0.4


@dataclass(frozen=True)
class Analytics:
    """League Analytics page: formulas and display thresholds (all numbers come from the season's box scores)."""
    # Free-throw weight in possession estimates: FGA + FTA_WEIGHT * FTA + TOV.
    FTA_WEIGHT: float = 0.44
    # Assumed offensive share of total rebounds, for box scores saved before offensive rebounds were counted
    # (2026-11-15); used by Game Score and PER.
    OREB_SHARE: float = 0.25
    # Clutch (NBA definition): 4th quarter or overtime, last CLUTCH_LAST_SECONDS, score within CLUTCH_MARGIN.
    CLUTCH_LAST_SECONDS: int = 300
    CLUTCH_MARGIN: int = 5
    # Clutch FG% shows only from this many clutch shots (1 of 1 is not a 100% shooter).
    CLUTCH_FG_MIN_FGA: int = 5
    # Qualified players: at least this share of their team's games and this many minutes per game.
    QUALIFY_GP_SHARE: float = 0.5
    QUALIFY_MPG: float = 20.0
    # Table cells are tinted at or above TINT_TOP_PCT / at or below TINT_BOTTOM_PCT league percentile.
    TINT_TOP_PCT: int = 90
    TINT_BOTTOM_PCT: int = 15
    # Splits are tinted when they differ from the season line by more than this share.
    SPLIT_TINT_SHARE: float = 0.06
    # Expected wins: Pythagorean exponent fitted each season over this grid; fallback until every team has played
    # PYTH_MIN_GAMES games.
    PYTH_EXP_MIN: float = 4.0
    PYTH_EXP_MAX: float = 20.0
    PYTH_EXP_STEP: float = 0.1
    PYTH_FALLBACK_EXP: float = 10.0
    PYTH_MIN_GAMES: int = 10
    # A game decided by this many points or fewer is a close game.
    CLOSE_GAME_MARGIN: int = 5
    # PER is scaled so the minutes-weighted league average equals this.
    PER_LEAGUE_AVG: float = 15.0
    # Names shown per leaders tile.
    LEADERS_PER_TILE: int = 3

@dataclass(frozen=True)
class TeamCard:
    """Team card popup (core/team_card_view.py)."""
    # Players listed as the rotation before "Full roster"; past seasons in the bar strip.
    ROTATION_SIZE: int = 10
    SEASONS_SHOWN: int = 10

@dataclass(frozen=True)
class Database:
    """Player Database page: every player and season in the save (display only)."""
    # Directory rows per page.
    PAGE_SIZE: int = 50
    # Stat Finder: rows returned, stat conditions read from a query.
    FINDER_LIMIT: int = 100
    FINDER_MAX_CONDITIONS: int = 4
    # Player page "In this save": ranks shown down to this place; per-game ranks need this many career games.
    RANK_TOP_N: int = 25
    RANK_MIN_GP: int = 100
    # Player page Overview: the last N seasons table.
    LAST_SEASONS: int = 3
    # Seasons view leaders and "qualified": at least LEADER_GP_SHARE of a full season's games, read as this
    # percentile of games played (not the maximum: two players saved under one name add up their games).
    LEADER_GP_SHARE: float = 0.5
    GAMES_BASE_PERCENTILE: float = 0.95
    # Stat Finder ready-made searches (they only fill the form). "__user__" = the user's team.
    PRESETS: tuple = (
        {'id': 'best-22', 'label': 'Best seasons by a 22-year-old',
         'query': {'mode': 'seasons', 'age_min': 22, 'age_max': 22, 'min_gp': 50, 'rank_by': 'pts_pg'}},
        {'id': '25-10', 'label': '25/10 seasons',
         'query': {'mode': 'seasons', 'min_gp': 50, 'rank_by': 'pts_pg',
                   'conditions': [{'stat': 'pts_pg', 'op': '>=', 'value': 25},
                                  {'stat': 'reb_pg', 'op': '>=', 'value': 10}]}},
        {'id': '50-40-90', 'label': '50/40/90 seasons',
         'query': {'mode': 'seasons', 'min_gp': 50, 'rank_by': 'pts_pg',
                   'conditions': [{'stat': 'fg_pct', 'op': '>=', 'value': 50},
                                  {'stat': 'tp_pct', 'op': '>=', 'value': 40},
                                  {'stat': 'ft_pct', 'op': '>=', 'value': 90}]}},
        {'id': 'best-user-team', 'label': 'Best seasons for my team',
         'query': {'mode': 'seasons', 'team': '__user__', 'min_gp': 40, 'rank_by': 'pts_pg'}},
        {'id': 'most-all-star', 'label': 'Most All-Star selections',
         'query': {'mode': 'careers', 'rank_by': 'all_star'}},
    )

@dataclass(frozen=True)
class RookieGeneration:
    PROVENANCES: dict = field(default_factory=lambda: {
        "American (NCAA)": 50,
        "European": 30,
        "African": 8,
        "Asian": 5,
        "South American": 3,
        "Oceanian": 3
    })

    PEDIGREES: dict = field(default_factory=lambda: {
        "Generational Talent": {"chance": 2, "min_pot": 94, "bonus_ovr": (4, 7)},
        "Defensive Anchor": {"chance": 6, "min_pot": 88, "bonus_ovr": (0, 3)},
        "Elite Scorer": {"chance": 6, "min_pot": 90, "bonus_ovr": (2, 5)},
        "Raw Athletic Prospect": {"chance": 12, "min_pot": 88, "bonus_ovr": (-4, 0)},
        "High IQ Playmaker": {"chance": 5, "min_pot": 82, "bonus_ovr": (0, 3)},
        "NBA Ready Prospect": {"chance": 8, "min_pot": 80, "bonus_ovr": (3, 6)}, # High Floor, Low Ceiling
        "Injury Prone": {"chance": 5, "min_pot": 86, "bonus_ovr": (-3, -1)}
    })

    # Role profile of a generated prospect (offseason/draft.py _genera_attributi_per_archetipo): each skill starts at
    # OVR + this offset, the mean gap of the curated 2002 league (data/leagues/fictional_2002) for that role. Skills
    # the archetype names (defining / supporting / negative) are then raised or lowered. Before, every unnamed skill
    # was OVR - 10 at every role: centers shot threes like guards, guards posted up and blocked like bigs.
    # Speed, acceleration, strength and vertical keep their absolute ranges per role (a young athlete is fast).
    ROLE_SKILL_OFFSETS: dict = field(default_factory=lambda: {
        'PG': {'close_shot_rating': -4, 'mid_range_shot_rating': -1, 'three_point_shot_rating': -13, 'free_throw_rating': -5,
               'draw_foul_rating': -3, 'shot_iq': 2, 'offensive_iq_rating': 1, 'defensive_iq_rating': -1,
               'passing_accuracy': 3, 'passing_vision': 3, 'offensive_rebound_rating': -28, 'defensive_rebound_rating': -6,
               'perimeter_defense_rating': 0, 'interior_defense_rating': -5, 'block_rating': -45, 'steal_rating': -13,
               'stamina': 8, 'ball_handling': 4, 'dunk_rating': -27, 'post_control_rating': -38},
        'SG': {'close_shot_rating': -1, 'mid_range_shot_rating': 1, 'three_point_shot_rating': -11, 'free_throw_rating': -6,
               'draw_foul_rating': -2, 'shot_iq': 2, 'offensive_iq_rating': 2, 'defensive_iq_rating': -1,
               'passing_accuracy': -3, 'passing_vision': -4, 'offensive_rebound_rating': -21, 'defensive_rebound_rating': -5,
               'perimeter_defense_rating': -1, 'interior_defense_rating': -5, 'block_rating': -45, 'steal_rating': -14,
               'stamina': 8, 'ball_handling': 1, 'dunk_rating': -23, 'post_control_rating': -39},
        'SF': {'close_shot_rating': -1, 'mid_range_shot_rating': 0, 'three_point_shot_rating': -12, 'free_throw_rating': -6,
               'draw_foul_rating': -3, 'shot_iq': 2, 'offensive_iq_rating': 1, 'defensive_iq_rating': 0,
               'passing_accuracy': -4, 'passing_vision': -4, 'offensive_rebound_rating': -5, 'defensive_rebound_rating': -4,
               'perimeter_defense_rating': 0, 'interior_defense_rating': -4, 'block_rating': -25, 'steal_rating': -20,
               'stamina': 8, 'ball_handling': 0, 'dunk_rating': -24, 'post_control_rating': -37},
        'PF': {'close_shot_rating': 1, 'mid_range_shot_rating': -2, 'three_point_shot_rating': -37, 'free_throw_rating': -6,
               'draw_foul_rating': -4, 'shot_iq': 0, 'offensive_iq_rating': 0, 'defensive_iq_rating': 1,
               'passing_accuracy': -10, 'passing_vision': -15, 'offensive_rebound_rating': 0, 'defensive_rebound_rating': 2,
               'perimeter_defense_rating': -5, 'interior_defense_rating': 0, 'block_rating': -18, 'steal_rating': -45,
               'stamina': 8, 'ball_handling': -2, 'dunk_rating': -11, 'post_control_rating': -13},
        'C':  {'close_shot_rating': 1, 'mid_range_shot_rating': -2, 'three_point_shot_rating': -47, 'free_throw_rating': -6,
               'draw_foul_rating': -3, 'shot_iq': 0, 'offensive_iq_rating': 0, 'defensive_iq_rating': 2,
               'passing_accuracy': -10, 'passing_vision': -15, 'offensive_rebound_rating': 1, 'defensive_rebound_rating': 4,
               'perimeter_defense_rating': -4, 'interior_defense_rating': 2, 'block_rating': -8, 'steal_rating': -43,
               'stamina': 9, 'ball_handling': -1, 'dunk_rating': -10, 'post_control_rating': -14},
    })
    # How often each archetype is drawn at its role (it was one in three each: a third of the centers were
    # three-point shooting Unicorns and two SGs in three did not shoot threes).
    ARCHETYPE_WEIGHTS: dict = field(default_factory=lambda: {
        'PG': {"Floor General": 40, "Luka-Esque": 25, "Tiratore dal Dribbling": 35},
        'SG': {"3&D Guard": 50, "Mid-Range Specialist": 25, "Slasher Puro": 25},
        'SF': {"Ala Rimbalzista": 25, "Tiratrice Pura": 35, "Two-Way Wing": 40},
        'PF': {"Difensore/Rimbalzista": 40, "Scoring Forward": 35, "Stretch Four": 25},
        'C':  {"Centro Puro": 55, "Unicorno": 20, "Point Center": 25},
    })
    ROLE_SKILL_NOISE: float = 4.0      # sd of the random spread around the role profile
    ROLE_SKILL_FLOOR: int = 25
    # Mean tendencies of the curated 2002 league per role. Shot tendencies then follow the prospect's own ratings
    # (a good shooter shoots more), usage (touch, hero ball, playmaking, rebounding) his OVR.
    ROLE_TENDENCIES: dict = field(default_factory=lambda: {
        'PG': {'touch_tendency': 49, 'spot_up_shot_tendency': 65, 'mid_range_shot_tendency': 68, 'drive_to_basket_tendency': 71,
               'post_up_tendency': 21, 'pass_out_of_shot_tendency': 52, 'dish_to_open_man_tendency': 62, 'dunk_tendency': 31,
               'hero_ball_tendency': 29, 'putback_tendency': 20, 'roll_vs_pop_tendency': 50, 'foul_tendency': 45,
               'rebound_tendency': 57, 'playmaking_tendency': 74},
        'SG': {'touch_tendency': 52, 'spot_up_shot_tendency': 66, 'mid_range_shot_tendency': 71, 'drive_to_basket_tendency': 72,
               'post_up_tendency': 21, 'pass_out_of_shot_tendency': 46, 'dish_to_open_man_tendency': 56, 'dunk_tendency': 32,
               'hero_ball_tendency': 33, 'putback_tendency': 20, 'roll_vs_pop_tendency': 50, 'foul_tendency': 45,
               'rebound_tendency': 60, 'playmaking_tendency': 54},
        'SF': {'touch_tendency': 51, 'spot_up_shot_tendency': 67, 'mid_range_shot_tendency': 70, 'drive_to_basket_tendency': 70,
               'post_up_tendency': 23, 'pass_out_of_shot_tendency': 46, 'dish_to_open_man_tendency': 56, 'dunk_tendency': 32,
               'hero_ball_tendency': 30, 'putback_tendency': 22, 'roll_vs_pop_tendency': 50, 'foul_tendency': 45,
               'rebound_tendency': 51, 'playmaking_tendency': 50},
        'PF': {'touch_tendency': 50, 'spot_up_shot_tendency': 44, 'mid_range_shot_tendency': 66, 'drive_to_basket_tendency': 46,
               'post_up_tendency': 49, 'pass_out_of_shot_tendency': 47, 'dish_to_open_man_tendency': 57, 'dunk_tendency': 66,
               'hero_ball_tendency': 29, 'putback_tendency': 60, 'roll_vs_pop_tendency': 66, 'foul_tendency': 45,
               'rebound_tendency': 64, 'playmaking_tendency': 37},
        'C':  {'touch_tendency': 46, 'spot_up_shot_tendency': 40, 'mid_range_shot_tendency': 63, 'drive_to_basket_tendency': 45,
               'post_up_tendency': 44, 'pass_out_of_shot_tendency': 46, 'dish_to_open_man_tendency': 55, 'dunk_tendency': 67,
               'hero_ball_tendency': 25, 'putback_tendency': 60, 'roll_vs_pop_tendency': 71, 'foul_tendency': 45,
               'rebound_tendency': 78, 'playmaking_tendency': 37},
    })
    ROLE_TENDENCY_NOISE: float = 4.0
    # Usage tendencies grow with OVR (points per OVR point over ROLE_TENDENCY_PIVOT_OVR, the curated league's mean).
    USAGE_TENDENCY_PER_OVR: dict = field(default_factory=lambda: {
        'touch_tendency': 1.5, 'hero_ball_tendency': 0.8, 'playmaking_tendency': 0.6, 'rebound_tendency': 0.6,
    })
    ROLE_TENDENCY_PIVOT_OVR: int = 74
    # Three-point tendency from the three-point rating: slope * (rating - zero). Curated 2002: C 26 -> 1, PG 61 -> 48.
    THREE_TENDENCY_SLOPE: float = 1.33
    THREE_TENDENCY_ZERO_RATING: int = 25
    # A prospect drafted in a later year shoots more threes: added at CONFIG.ERA.END_YEAR, linear from START_YEAR.
    MODERN_THREE_RATING_SHIFT: dict = field(default_factory=lambda: {'PG': 5, 'SG': 5, 'SF': 6, 'PF': 14, 'C': 14})
    MODERN_THREE_TENDENCY_SHIFT: int = 15
    # Each archetype moves its tendencies from the role profile. These were absolute clamps (hero ball 5 and touch
    # at most 50 for four wing archetypes, touch 90 for a Luka-Esque rookie): wings who became stars never took
    # over a game, bench rookies did.
    ARCHETYPE_TENDENCY_PUSHES: dict = field(default_factory=lambda: {
        "Floor General": {'dish_to_open_man_tendency': 15, 'playmaking_tendency': 12, 'pass_out_of_shot_tendency': 10, 'touch_tendency': -5},
        "Luka-Esque": {'touch_tendency': 12, 'hero_ball_tendency': 12, 'playmaking_tendency': 8},
        "Tiratore dal Dribbling": {'three_point_shot_tendency': 8, 'hero_ball_tendency': 6},
        "3&D Guard": {'touch_tendency': -8, 'hero_ball_tendency': -8, 'drive_to_basket_tendency': -12, 'spot_up_shot_tendency': 15},
        "Mid-Range Specialist": {'mid_range_shot_tendency': 15, 'three_point_shot_tendency': -15, 'touch_tendency': 6},
        "Slasher Puro": {'drive_to_basket_tendency': 12, 'dunk_tendency': 12, 'three_point_shot_tendency': -10},
        "Ala Rimbalzista": {'touch_tendency': -8, 'hero_ball_tendency': -8, 'rebound_tendency': 15, 'putback_tendency': 10},
        "Tiratrice Pura": {'spot_up_shot_tendency': 15, 'three_point_shot_tendency': 10, 'drive_to_basket_tendency': -10, 'touch_tendency': -5},
        "Two-Way Wing": {'touch_tendency': -6, 'hero_ball_tendency': -6},
        "Difensore/Rimbalzista": {'touch_tendency': -10, 'spot_up_shot_tendency': -15, 'putback_tendency': 12, 'rebound_tendency': 12},
        "Scoring Forward": {'touch_tendency': 8, 'post_up_tendency': 8, 'dunk_tendency': 8},
        "Stretch Four": {'spot_up_shot_tendency': 15, 'roll_vs_pop_tendency': 15, 'post_up_tendency': -10},
        "Centro Puro": {'touch_tendency': -10, 'spot_up_shot_tendency': -15, 'putback_tendency': 12, 'rebound_tendency': 12},
        "Unicorno": {'post_up_tendency': -15, 'roll_vs_pop_tendency': 20, 'putback_tendency': -15, 'rebound_tendency': -8},
        "Point Center": {'touch_tendency': 8, 'dish_to_open_man_tendency': 15, 'playmaking_tendency': 25, 'post_up_tendency': 12},
    })


    NAMES_BY_PROVENANCE: dict = field(default_factory=lambda: {
    "American (NCAA)": (
        [
            # American First Names (300) - Mixture of popular, common, and diverse origins
            "Aaron", "Adam", "Aidan", "Alan", "Albert", "Alden", "Alex", "Alexander", "Allen", "Alton",
            "Andrew", "Anthony", "Archer", "Arthur", "Asher", "Austin", "Benjamin", "Bennett", "Blake", "Brandon",
            "Brendan", "Brent", "Brett", "Brian", "Brock", "Brooks", "Bruce", "Bryan", "Caleb", "Calvin",
            "Cameron", "Carl", "Carson", "Carter", "Casey", "Cody", "Cole", "Colin", "Connor", "Cooper",
            "Corey", "Craig", "Curtis", "Dakota", "Dale", "Dallas", "Daniel", "Darius", "Darren", "David",
            "Dean", "Dennis", "Derek", "Devin", "Diego", "Dillon", "Dominic", "Donovan", "Douglas", "Drew",
            "Dustin", "Dylan", "Earl", "Edward", "Edwin", "Eli", "Elias", "Elijah", "Elliott", "Ellis",
            "Emmett", "Eric", "Ethan", "Evan", "Everett", "Ezra", "Felix", "Fernando", "Finn", "Forrest",
            "Frank", "Franklin", "Gabe", "Gabriel", "Gage", "Garrett", "Gary", "Gavin", "George", "Gerald",
            "Glenn", "Gordon", "Graham", "Grant", "Gregory", "Harold", "Harry", "Hayden", "Henry", "Hunter",
            "Ian", "Isaac", "Isaiah", "Ivan", "Jackson", "Jacob", "Jake", "Jalen", "James", "Jared",
            "Jaxon", "Jayden", "Jeffrey", "Jeremy", "Jerome", "Jerry", "Jesse", "Jessie", "Joel", "John",
            "Jonah", "Jonathan", "Jordan", "Jose", "Joseph", "Josh", "Joshua", "Julian", "Justin", "Kai",
            "Kameron", "Kareem", "Keith", "Kelly", "Kenneth", "Kevin", "Kyle", "Landon", "Lawrence", "Lee",
            "Leo", "Leon", "Levi", "Liam", "Lincoln", "Logan", "Louis", "Lucas", "Luke", "Malcolm",
            "Manuel", "Marc", "Marcus", "Mark", "Martin", "Mason", "Matthew", "Maurice", "Max", "Maxwell",
            "Michael", "Micah", "Miles", "Mitchell", "Nathan", "Nathaniel", "Neal", "Neil", "Nicholas", "Noah",
            "Nolan", "Oliver", "Oscar", "Owen", "Parker", "Patrick", "Paul", "Peter", "Philip", "Preston",
            "Quinn", "Ralph", "Randall", "Raymond", "Reed", "Reginald", "Rhys", "Richard", "Riley", "Robert",
            "Rodney", "Roger", "Ronald", "Randy", "Ross", "Roy", "Ruben", "Russell", "Ryan", "Sam",
            "Samuel", "Scott", "Sean", "Seth", "Shane", "Shannon", "Shawn", "Silas", "Simon", "Spencer",
            "Stanley", "Stephen", "Sterling", "Steven", "Stuart", "Taylor", "Terence", "Terry", "Theodore", "Thomas",
            "Timothy", "Todd", "Travis", "Trent", "Trevor", "Troy", "Tyler", "Tyrell", "Victor", "Vincent",
            "Walter", "Warren", "Wayne", "Wesley", "Weston", "William", "Willie", "Wyatt", "Zachary", "Adam",
            "Adrian", "Alfred", "Archie", "Ben", "Bill", "Buster", "Chad", "Chandler", "Chase", "Clay",
            "Clifford", "Cliff", "Clinton", "Clyde", "Conrad", "Courtney", "Dallas", "Damon", "Dane", "Dante",
            "Darrell", "Dean", "Desmond", "Dexter", "Don", "Earl", "Ernie", "Floyd", "Foster", "Francisco",
            "Fred", "Frederick", "Gideon", "Glen", "Hugh", "Jay", "Jimmy", "Jon", "Kenny", "Lance",
            "Larry", "Lenny", "Lonnie", "Lorenzo", "Louis", "Lowell", "Marshall", "Morton", "Ned", "Nelson",
            "Nick", "Omar", "Perry", "Pete", "Phillip", "Pierre", "Ray", "Rhett", "Rich", "Rick",
            "Rod", "Rudy", "Russ", "Sal", "Saul", "Scotty", "Sidney", "Sonny", "Tab", "Ted",
            "Tony", "Trace", "Vaughn", "Vernon", "Vince", "Wallace", "Walt", "Wendell", "Willis", "Woody"
        ],
        [
            # American Last Names (300) - Most common surnames in the U.S., reflecting its diverse population
            "Adams", "Allen", "Anderson", "Andrews", "Armstrong", "Arnold", "Austin", "Baker", "Ball", "Banks",
            "Barnes", "Bell", "Bennett", "Berry", "Black", "Blair", "Bond", "Bowman", "Boyd", "Bradley",
            "Brooks", "Brown", "Bryant", "Burke", "Burns", "Butler", "Campbell", "Carey", "Carlson", "Carpenter",
            "Carter", "Casey", "Chambers", "Chang", "Chapman", "Clark", "Clay", "Cole", "Coleman", "Collins",
            "Cook", "Cooper", "Cox", "Craig", "Crawford", "Cruz", "Cunningham", "Dalton", "Daniels", "Davis",
            "Dean", "Dixon", "Dominguez", "Douglas", "Duncan", "Edwards", "Elliott", "Ellis", "Evans", "Fields",
            "Fisher", "Ford", "Foster", "Fox", "Francis", "Freeman", "Gardner", "Garner", "Garrett", "George",
            "Gibson", "Gomez", "Gonzalez", "Goodman", "Gordon", "Graham", "Grant", "Gray", "Green", "Greene",
            "Griffin", "Hall", "Hamilton", "Hanson", "Harris", "Harrison", "Hart", "Harvey", "Hayes", "Henderson",
            "Henry", "Hernandez", "Herrera", "Hill", "Hoffman", "Holland", "Holmes", "Howard", "Hudson", "Hughes",
            "Hunter", "Jackson", "James", "Jenkins", "Jensen", "Jimenez", "Johnson", "Jones", "Jordan", "Kelly",
            "Kennedy", "King", "Knight", "Lane", "Larson", "Lawrence", "Lee", "Lewis", "Little", "Long",
            "Lopez", "Love", "Lowe", "Lucas", "Lynch", "Mack", "Mann", "Marshall", "Martin", "Martinez",
            "Mason", "Matthews", "May", "McCarthy", "McDaniel", "McDonald", "McFarland", "McGee", "McKinney", "Medina",
            "Mendez", "Miller", "Mitchell", "Montgomery", "Moore", "Morales", "Morgan", "Morris", "Morrison", "Mullins",
            "Munoz", "Murphy", "Murray", "Myers", "Nash", "Nelson", "Newman", "Newton", "Nguyen", "Nichols",
            "Oliver", "Olson", "Ortiz", "Owens", "Palmer", "Parker", "Patterson", "Payne", "Pearson", "Perez",
            "Perkins", "Perry", "Peters", "Phelps", "Phillips", "Pierce", "Porter", "Powell", "Price", "Quinn",
            "Ramirez", "Ramsey", "Ray", "Reed", "Reid", "Reynolds", "Rice", "Richards", "Richardson", "Riley",
            "Rivera", "Roberts", "Robertson", "Robinson", "Rodriguez", "Rogers", "Romero", "Rose", "Ross", "Ruiz",
            "Russell", "Ryan", "Sanchez", "Sanders", "Santiago", "Schmidt", "Scott", "Sharp", "Shaw", "Sherman",
            "Simmons", "Simpson", "Singh", "Smith", "Snyder", "Spencer", "Stanley", "Stephens", "Sterling", "Stevens",
            "Stewart", "Stone", "Sullivan", "Sutton", "Taylor", "Thomas", "Thompson", "Thornton", "Todd", "Torres",
            "Townsend", "Tucker", "Turner", "Underwood", "Valdez", "Vance", "Vaughn", "Vega", "Velez", "Wagner",
            "Walker", "Wallace", "Walters", "Ward", "Warren", "Washington", "Watkins", "Watson", "Weaver", "Webb",
            "Weeks", "Wells", "West", "Wheeler", "White", "Williams", "Williamson", "Willis", "Wilson", "Wood",
            "Woods", "Wright", "Young", "Ziegler", "Zuniga", "Abbott", "Acosta", "Aguilar", "Alvarado", "Arevalo",
            "Armstead", "Ashley", "Atkins", "Augustine", "Baldwin", "Barry", "Beasley", "Beck", "Bellamy", "Benson",
            "Berg", "Beverly", "Bird", "Bishop", "Blackburn", "Blake", "Blanchard", "Boggs", "Bowers", "Bradford",
            "Brewer", "Bridges", "Britt", "Brock", "Brooks", "Browning", "Buchanan", "Buckley", "Bullock", "Burton",
            "Byrd", "Calhoun", "Callahan", "Cameron", "Cannon", "Carr", "Carroll", "Cash", "Cervantes", "Chan",
            "Chase", "Cherry", "Church", "Clayton", "Cleveland", "Clifford", "Cochran", "Coffee", "Collinsworth", "Combs",
            "Conner", "Conrad", "Cordova", "Correa", "Cortez", "Cosby", "Costa", "Craig", "Crane", "Crosby",
            "Crowley", "Cruz", "Culver", "Curtis", "Daly", "Davidson", "Decker", "Dempsey", "Dennis", "Dickerson",
            "Dillon", "Dixon", "Dodd", "Dorsey", "Downs", "Duke", "Eaton", "Elias", "English", "Espinoza",
            "Estes", "Farley", "Faulkner", "Fields", "Finley", "Fletcher", "Flores", "Floyd", "Flynn", "Foley",
            "Foster", "Fowler", "Franklin", "Frazier", "Freeman", "French", "Fuller", "Fulton", "Gaines", "Gallagher",
            "Galloway", "Gamboa", "Garcia", "Garrison", "Gentry", "Gibbs", "Gilmore", "Glass", "Glenn", "Glover",
            "Goodwin", "Grady", "Gray", "Gregory", "Gresham", "Griffin", "Gross", "Guess", "Hale", "Haley",
            "Halloran", "Hampton", "Hardin", "Hardy", "Harmon", "Harper", "Harrigan", "Harrington", "Harvey", "Hatfield"
        ]
    ),
    "European": (
        [
            # European First Names (100) - Broad coverage across various European countries
            "Adrian", "Aleksandar", "Alexei", "Andrei", "Anton", "Artur", "Axel", "Benedikt", "Boris", "Boyan",
            "Cem", "Christian", "Christoph", "Damian", "Daniel", "Danil", "Dario", "Denis", "Dimitri", "Dominik",
            "Dragan", "Eduard", "Egor", "Emil", "Enes", "Fabian", "Felix", "Filip", "Florian", "Franz",
            "Frederik", "Gabriel", "Georgi", "Gerard", "Giulio", "Grzegorz", "Guillaume", "Gustav", "Hans", "Hendrik",
            "Ignas", "Igor", "Ion", "Ivan", "Jakob", "Jan", "Janko", "Jens", "Joakim", "Johannes",
            "Jonas", "Josef", "Julian", "Jurgen", "Kacper", "Karl", "Kaspars", "Konstantin", "Krzysztof", "Lars",
            "Lauri", "Leon", "Louis", "Lukas", "Maciej", "Marcel", "Marius", "Marko", "Martin", "Matej",
            "Matthias", "Maxim", "Mihai", "Mikhail", "Milan", "Milos", "Mirko", "Nikita", "Nikolai", "Nils",
            "Oleg", "Oskar", "Otto", "Pavel", "Piotr", "Rafael", "Rasmus", "Remi", "Riccardo", "Robin",
            "Roman", "Ruben", "Sergei", "Soren", "Stefan", "Sven", "Tadeas", "Theo", "Timo", "Titus",
            "Tomas", "Uros", "Valentin", "Vasil", "Viktor", "Vincent", "Vladimir", "Vladislav", "Wojciech", "Yannick"
        ],
        [
            # European Last Names (100) - Common surnames from various European linguistic families
            "Andersson", "Antonov", "Bauer", "Becker", "Berg", "Berger", "Braun", "Cerny", "Davies", "Demir",
            "Dimitrov", "Dubois", "Eriksson", "Fischer", "Garcia", "Gauthier", "Glaser", "Gonzales", "Goranov", "Ivanov",
            "Jakobsen", "Jankovic", "Jensen", "Johansen", "Johansson", "Jovanovic", "Karlsson", "Kaufmann", "Keller", "Klein",
            "Knezevic", "Kovac", "Kowalski", "Kramer", "Kristensen", "Kuznetsov", "Larsen", "Larsson", "Leclerc", "Lehman",
            "Lindberg", "Lindstrom", "Meyer", "Mihailov", "Moller", "Morozov", "Muller", "Nielsen", "Novak", "Olsen",
            "Pedersen", "Petersen", "Petrov", "Popov", "Poulain", "Ramirez", "Rasmussen", "Rau", "Reid", "Ricci",
            "Richter", "Ristic", "Rodriguez", "Russo", "Sanchez", "Schmidt", "Schneider", "Schulz", "Schwarz", "Sergeev",
            "Silva", "Simon", "Sokolov", "Solovyov", "Svensson", "Szabo", "Todorov", "Traore", "Valentin", "Vasiljev",
            "Volkov", "Wagner", "Weber", "Weiss", "Westergaard", "Widmer", "Wolff", "Wunderlich", "Yilmaz", "Zaytsev",
            "Zimmermann", "Zivkovic", "Zupančič", "Galli", "Kuzmin", "Pereira", "Santos", "Costa", "Oliveira", "Martel",
            "Durand", "Leroy", "Moreau", "Dubois", "Bernard", "Thomas", "Robert", "Petit", "Richard", "Garcia"
        ]
    ),
    "African": (
        [
            # African First Names (100) - Diverse representation across the continent
            "Abdi", "Abdoul", "Ahmed", "Akash", "Amadou", "Anas", "Baba", "Babatunde", "Brahim", "Chinedu",
            "Christian", "Daniel", "David", "Didier", "Elijah", "Emmanuel", "Eric", "Femi", "Gabriel", "Gideon",
            "Hassan", "Ibrahim", "Idris", "Ismail", "Issa", "Jacques", "Japhet", "Jean", "Jonathan", "Joseph",
            "Junior", "Karim", "Kehinde", "Kevin", "Kofi", "Kwame", "Lamine", "Mamadou", "Malick", "Matthew",
            "Mohammed", "Moussa", "Musa", "Mustafa", "Ndubuisi", "Noah", "Obinna", "Oluwasegun", "Omar", "Osman",
            "Pascal", "Patrick", "Paul", "Peter", "Pierre", "Prince", "Rashid", "Ridwan", "Samuel", "Sekou",
            "Sherif", "Souleymane", "Stephen", "Sunday", "Taiwo", "Tariq", "Umar", "Victor", "Vincent", "Yahya",
            "Yusuf", "Yves", "Zakaria", "Zola", "Adebayo", "Ahmedu", "Akpan", "Alhaji", "Amara", "Ayo",
            "Bello", "Chukwu", "Dada", "Ekene", "Etim", "Fofana", "Habib", "Ifeanyi", "Kabba", "Kolawole",
            "Kwasi", "Musa", "Nuru", "Ola", "Olaide", "Osagie", "Oluwaseun", "Rauf", "Sadiq", "Sani",
            "Shola", "Tunde", "Uche", "Ugo", "Wahab", "Yakubu"
        ],
        [
            # African Last Names (100) - Common surnames reflecting diverse origins (West, North, East, Central, South)
            "Abdullahi", "Adama", "Adeyemi", "Ahmed", "Akpan", "Ali", "Balogun", "Bangura", "Camara", "Diakite",
            "Diallo", "Diarra", "Diop", "Diouf", "Dosso", "Doumbia", "Eze", "Fall", "Fofana", "Gueye",
            "Hassan", "Ibrahim", "Jalloh", "Kamara", "Keita", "Kone", "Koulibaly", "Mohammed", "Mor", "Moussa",
            "Ndiaye", "Njie", "Nwachukwu", "Okafor", "Okoro", "Oladipo", "Olatunji", "Oumarou", "Ouédraogo", "Sarr",
            "Sidibe", "Sissoko", "Soumare", "Sylla", "Thiam", "Traore", "Ubong", "Ugwu", "Umar", "Umoh",
            "Yacoubou", "Yaya", "Zongo", "Biyombo", "Bol", "Dieng", "Embiid", "Garuba", "Ibaka", "Kuminga",
            "Mbah", "Metu", "Mutombo", "Olajuwon", "Okeke", "Okpala", "Siakam", "Achiuwa", "Bassey", "Bonga",
            "Fernando", "Okongwu", "Azubuike", "Chukwuma", "Essien", "Kalu", "Odunze", "Ojo", "Okonkwo", "Onyeka",
            "Udeze", "Adewale", "Akin", "Bello", "Chukwuemeka", "Dada", "Eboh", "Gbolahan", "Ifeanyi", "Jimoh",
            "Kolawole", "Musa", "Nuru", "Ojo", "Olayinka", "Owolabi", "Popoola", "Sadiq", "Usman", "Yahaya"
        ]
    ),
    "Asian": (
        [
            # Asian First Names (100) - Broad coverage from East, Southeast, South, and West Asia
            "Akira", "Ali", "Amir", "Arjun", "Byron", "Chen", "Chul", "Daiki", "David", "Do-hyun",
            "Eito", "Fahad", "Haruto", "Hassan", "Hiroki", "Hong", "Hu", "Irfan", "Jae-hyun", "Jai",
            "Jian", "Jianjun", "Jin", "Ji-hoon", "Joaquin", "Jun", "Kaito", "Kai", "Kenji", "Keisuke",
            "Kevin", "Kian", "Ki-moon", "Kishore", "Koji", "Kuan", "Kunal", "Lakshya", "Lian", "Liang",
            "Ling", "Long", "Lu", "Mahmoud", "Masato", "Mehmood", "Min-jun", "Mohammad", "Muhammad", "Naoki",
            "Naveen", "Nayan", "Nguyen", "Osamu", "Patrick", "Pranav", "Qiang", "Rahul", "Rajesh", "Ranjit",
            "Ren", "Riku", "Ryo", "Sam", "Sandeep", "Seo-jun", "Shahid", "Shan", "Shinji", "Siddharth",
            "Sung-min", "Takeshi", "Tao", "Thien", "Tomohiro", "Vijay", "Wei", "Xia", "Xiao", "Xin",
            "Yang", "Yasuhiro", "Yuki", "Yusuke", "Zachary", "Zhang", "Zhi", "Zhou", "Ziad", "Zhihao",
            "Abdul", "Ahmad", "Ankit", "Arun", "Chandra", "Deepak", "Devin", "Gaurav", "Harish", "Jagdish",
            "Kapil", "Manoj", "Prakash", "Praveen", "Rakesh", "Sanjay", "Subhash", "Sunil", "Vivek", "Ashish"
        ],
        [
            # Asian Last Names (100) - Most common surnames from diverse Asian cultures
            "Ahn", "Ali", "Aziz", "Cao", "Chai", "Chan", "Chang", "Cheung", "Choi", "Chong",
            "Chou", "Chow", "Chu", "Chung", "Dai", "Deng", "Fam", "Fan", "Fukuda", "Gao",
            "Guo", "Han", "Hasan", "Honda", "Ho", "Hsieh", "Hsu", "Huang", "Huynh", "Im",
            "Jiang", "Kawasaki", "Kim", "Ko", "Kwon", "Lam", "Lee", "Lei", "Li", "Liao",
            "Lim", "Lin", "Liu", "Lo", "Lu", "Ma", "Min", "Mohamed", "Nakamura", "Nguyen",
            "Oh", "Park", "Pham", "Qian", "Qiu", "Saito", "Sato", "Shah", "Sharma", "Singh",
            "So", "Song", "Suzuki", "Tan", "Tanaka", "Tang", "Tran", "Tsai", "Ueda", "Wang",
            "Watanabe", "Wei", "Wong", "Woo", "Wu", "Xiao", "Xu", "Yamada", "Yamamoto", "Yang",
            "Yao", "Yoshida", "Yu", "Yuan", "Zhang", "Zhao", "Zheng", "Zhou", "Zhu", "Adhikari",
            "Begum", "Devi", "Khan", "Kumar", "Patel", "Rahman", "Rani", "Shah", "Siddiqui", "Verma"
        ]
    ),
    "South American": (
        [
            # South American First Names (100) - Common Portuguese and Spanish names
            "Agustín", "Alejandro", "Alexandre", "Alvaro", "André", "Andrés", "Antonio", "Arturo", "Benito", "Bruno",
            "Carlos", "Cesar", "Christian", "Daniel", "Davi", "Diego", "Eduardo", "Emiliano", "Enzo", "Fabio",
            "Facundo", "Felipe", "Fernando", "Francisco", "Gabriel", "Gastón", "Gonzalo", "Guilherme", "Gustavo", "Hector",
            "Hernán", "Hugo", "Ignacio", "Ismael", "Javier", "João", "Jorge", "José", "Juan", "Julián",
            "Leonardo", "Leandro", "Lucas", "Luciano", "Luís", "Manuel", "Marcelo", "Marco", "Marcos", "Mario",
            "Mateo", "Matías", "Mauricio", "Maximiliano", "Miguel", "Nicolás", "Pablo", "Patricio", "Paulo", "Pedro",
            "Rafael", "Ramiro", "Raul", "Renato", "Ricardo", "Roberto", "Rodrigo", "Ronaldo", "Salvador", "Santiago",
            "Sebastián", "Sergio", "Thiago", "Tiago", "Tomás", "Valentin", "Victor", "Vicente", "Vinícius", "Walter",
            "Wilfredo", "Xavier", "Yago", "Yuri", "Adolfo", "Augusto", "Blas", "Cristian", "Dante", "Elías",
            "Ezequiel", "Federico", "Gerardo", "Guillermo", "Horacio", "Julio", "Lázaro", "Lorenzo", "Oscar", "Pablo",
            "Rafael", "Ramiro", "Ramón", "Renzo", "Rubén", "Santiago", "Silvio", "Tobías", "Ulises", "Vicente"
        ],
        [
            # South American Last Names (100) - Common Portuguese and Spanish surnames
            "Almeida", "Alves", "Andrade", "Barbosa", "Benítez", "Cardozo", "Carrasco", "Castillo", "Castro", "Cáceres",
            "Correa", "Costa", "Da Cruz", "Da Silva", "De Almeida", "De Lima", "Diaz", "Domínguez", "Dos Santos", "Fernández",
            "Ferreira", "Ferrer", "Flores", "Franco", "Garcia", "Giménez", "Gómez", "Gonçalves", "González", "Guerrero",
            "Gutiérrez", "Hernández", "Herrera", "Ibarra", "Lima", "López", "Machado", "Maia", "Martínez", "Mendes",
            "Miranda", "Monteiro", "Morales", "Moreno", "Nascimento", "Navarro", "Nunes", "Oliveira", "Ortiz", "Paredes",
            "Pereira", "Perez", "Pinto", "Ramírez", "Reyes", "Ribeiro", "Rivera", "Rodrigues", "Rodriguez", "Romero",
            "Rosa", "Ruiz", "Salas", "Sanchez", "Santana", "Santiago", "Santos", "Silva", "Souza", "Suarez",
            "Tavares", "Toledo", "Torres", "Vargas", "Vasquez", "Vega", "Vieira", "Villar", "Acosta", "Aguilar",
            "Alonso", "Arellano", "Barrera", "Basurto", "Bustos", "Caballero", "Campos", "Cano", "Carrillo", "Castañeda",
            "Ceballos", "Cisneros", "Cordero", "Cortez", "Cuellar", "Delgado", "Escobar", "Espinoza", "Estrada", "Fajardo"
        ]
    ),
    "Oceanian": (
        # Oceanian First Names (100 Male) - Blend of common Australian/NZ and Pacific Islander names
        [
            "Aaron", "Adam", "Aiden", "Alex", "Alexander", "Andrew", "Anthony", "Arthur", "Ashton", "Bailey",
            "Ben", "Benjamin", "Blake", "Brayden", "Brody", "Caleb", "Callum", "Cameron", "Charlie", "Christian",
            "Christopher", "Cody", "Colin", "Connor", "Cooper", "Daniel", "Darcy", "David", "Declan", "Dylan",
            "Edward", "Elijah", "Ethan", "Finn", "Fraser", "Gabriel", "George", "Gus", "Hamish", "Harrison",
            "Harry", "Hayden", "Henry", "Hugh", "Isaac", "Jack", "Jackson", "Jacob", "James", "Jaxon",
            "Jesse", "Joel", "John", "Jonathan", "Joseph", "Joshua", "Jude", "Kai", "Kian", "Lachlan",
            "Leo", "Liam", "Logan", "Louis", "Lucas", "Luke", "Mark", "Mason", "Matthew", "Max",
            "Michael", "Miles", "Mitchell", "Nathan", "Nicholas", "Niko", "Noah", "Oliver", "Oscar", "Owen",
            "Patrick", "Paul", "Peter", "Philip", "Rhys", "Riley", "Robert", "Ruben", "Ryan", "Samuel",
            "Sean", "Semi", "Simon", "Sione", "Solomone", "Spencer", "Stephen", "Tahi", "Taika", "Tasman",
            "Tevita", "Thomas", "Toby", "Tomasi", "Tua", "Viliami", "William", "Zane"
        ],
        # Oceanian Last Names (100) - Common Anglo-Celtic, Maori, and Pacific Islander surnames
        [
            "Adams", "Anderson", "Bailey", "Baker", "Bell", "Bennett", "Brown", "Campbell", "Carter", "Clark",
            "Clarke", "Collins", "Cook", "Cooper", "Cox", "Davies", "Davis", "Edwards", "Evans", "Faiumu",
            "Fainga'a", "Fifita", "Fisher", "Fotu", "Gibson", "Gray", "Green", "Greenwood", "Hall", "Harris",
            "Henderson", "Hill", "Hopkins", "Hopoate", "Howard", "Hughes", "Ioane", "Jackson", "James", "Johnson",
            "Jones", "Kahui", "Kelly", "King", "Kingston", "Kumar", "Latu", "Leaupepe", "Lewis", "Little",
            "Lomu", "Martin", "Miller", "Mitchell", "Moore", "Morris", "Murphy", "Nanai", "Nash", "Ngata",
            "Nielsen", "Nofoaluma", "O'Connor", "O'Neill", "Parker", "Phillips", "Price", "Reed", "Riley", "Roberts",
            "Robertson", "Robinson", "Ross", "Russell", "Ryan", "Scott", "Sharma", "Shaw", "Silva", "Simpson",
            "Singh", "Smith", "Stewart", "Sutton", "Taylor", "Thomas", "Thompson", "Tuilagi", "Turner", "Vaipulu",
            "Vunivalu", "Walker", "Ward", "Watson", "Webb", "West", "White", "Wilkinson", "Williams", "Wilson",
            "Wood", "Woods", "Wright", "Young"
        ]
    )
})

@dataclass(frozen=True)
class GeoConfig:
    """Geographic coordinates, timezones, and travel constraints for NBA scheduling."""
    MAX_B2B_PER_TEAM: int = 15
    
    CITIES: dict = field(default_factory=lambda: {
        'Atlanta': {'state': 'GA', 'lat': 33.75, 'lon': -84.39, 'tz': 'ET'},
        'Boston': {'state': 'MA', 'lat': 42.36, 'lon': -71.06, 'tz': 'ET'},
        'Brooklyn': {'state': 'NY', 'lat': 40.68, 'lon': -73.97, 'tz': 'ET'},
        'Charlotte': {'state': 'NC', 'lat': 35.22, 'lon': -80.84, 'tz': 'ET'},
        'Chicago': {'state': 'IL', 'lat': 41.88, 'lon': -87.67, 'tz': 'CT'},
        'Cleveland': {'state': 'OH', 'lat': 41.50, 'lon': -81.69, 'tz': 'ET'},
        'Dallas': {'state': 'TX', 'lat': 32.79, 'lon': -96.81, 'tz': 'CT'},
        'Denver': {'state': 'CO', 'lat': 39.75, 'lon': -105.01, 'tz': 'MT'},
        'Detroit': {'state': 'MI', 'lat': 42.34, 'lon': -83.05, 'tz': 'ET'},
        'San Francisco': {'state': 'CA', 'lat': 37.77, 'lon': -122.39, 'tz': 'PT'},
        'Houston': {'state': 'TX', 'lat': 29.75, 'lon': -95.36, 'tz': 'CT'},
        'Indianapolis': {'state': 'IN', 'lat': 39.76, 'lon': -86.15, 'tz': 'ET'},
        'Inglewood': {'state': 'CA', 'lat': 33.95, 'lon': -118.34, 'tz': 'PT'},
        'Los Angeles': {'state': 'CA', 'lat': 34.04, 'lon': -118.27, 'tz': 'PT'},
        'Memphis': {'state': 'TN', 'lat': 35.14, 'lon': -90.05, 'tz': 'CT'},
        'Miami': {'state': 'FL', 'lat': 25.78, 'lon': -80.19, 'tz': 'ET'},
        'Milwaukee': {'state': 'WI', 'lat': 43.04, 'lon': -87.92, 'tz': 'CT'},
        'Minneapolis': {'state': 'MN', 'lat': 44.98, 'lon': -93.27, 'tz': 'CT'},
        'New Orleans': {'state': 'LA', 'lat': 29.95, 'lon': -90.08, 'tz': 'CT'},
        'New York': {'state': 'NY', 'lat': 40.75, 'lon': -73.99, 'tz': 'ET'},
        'Newark': {'state': 'NJ', 'lat': 40.73, 'lon': -74.17, 'tz': 'ET'},
        'Oklahoma City': {'state': 'OK', 'lat': 35.46, 'lon': -97.51, 'tz': 'CT'},
        'Orlando': {'state': 'FL', 'lat': 28.54, 'lon': -81.38, 'tz': 'ET'},
        'Philadelphia': {'state': 'PA', 'lat': 39.90, 'lon': -75.17, 'tz': 'ET'},
        'Phoenix': {'state': 'AZ', 'lat': 33.44, 'lon': -112.07, 'tz': 'MT'},
        'Portland': {'state': 'OR', 'lat': 45.53, 'lon': -122.67, 'tz': 'PT'},
        'Sacramento': {'state': 'CA', 'lat': 38.58, 'lon': -121.50, 'tz': 'PT'},
        'San Antonio': {'state': 'TX', 'lat': 29.43, 'lon': -98.44, 'tz': 'CT'},
        'Salt Lake City': {'state': 'UT', 'lat': 40.77, 'lon': -111.90, 'tz': 'MT'},
        'Toronto': {'state': 'ON', 'lat': 43.64, 'lon': -79.38, 'tz': 'ET'},
        'Washington': {'state': 'DC', 'lat': 38.90, 'lon': -77.02, 'tz': 'ET'},
        # Potential Relocation & Expansion Hubs
        'Seattle': {'state': 'WA', 'lat': 47.62, 'lon': -122.35, 'tz': 'PT'},
        'Las Vegas': {'state': 'NV', 'lat': 36.17, 'lon': -115.14, 'tz': 'PT'},
        'Vancouver': {'state': 'BC', 'lat': 49.28, 'lon': -123.12, 'tz': 'PT'},
        'Montreal': {'state': 'QC', 'lat': 45.50, 'lon': -73.57, 'tz': 'ET'},
        'Kansas City': {'state': 'MO', 'lat': 39.10, 'lon': -94.58, 'tz': 'CT'},
        'Louisville': {'state': 'KY', 'lat': 38.25, 'lon': -85.76, 'tz': 'ET'},
    })

@dataclass(frozen=True)
class AllStar:
    """All-Star Weekend (core/all_star_weekend.py, core/all_star_view.py)."""
    # Team score range of the All-Star game and the Rising Stars game (before the OVR nudge).
    ALL_STAR_TOTAL_RANGE: tuple = (140, 165)
    ROOKIE_TOTAL_RANGE: tuple = (115, 140)
    # Per-player noise on the scoring share. Box stats (reb/ast/3PM) scale the season per-game by BOX_STAT_SCALE
    # (below 1: an All-Star plays ~20 minutes), times their own per-stat noise BOX_NOISE.
    SHARE_NOISE: tuple = (0.5, 1.6)
    BOX_STAT_SCALE: float = 0.75
    BOX_NOISE: tuple = (0.5, 1.6)
    # Weight of OVR against PPG in the scoring share, and the power the share is raised to (above 1 the stars
    # take the shots: MVP ~25-30 points, the last man on the bench a few).
    OVR_SHARE_WEIGHT: float = 0.1
    SHARE_POWER: float = 3.0
    # Dunk contest judges' score: floor, base, skill scale, noise, weight of dunk rating vs athleticism.
    DUNK_MIN: int = 30
    DUNK_BASE: int = 35
    DUNK_SKILL_SCALE: float = 0.25
    DUNK_NOISE: int = 4
    DUNK_RATING_WEIGHT: float = 0.6
    # Rising Stars: players per side; sophomore age fallback when last year's rookies are unknown.
    ROOKIE_CHALLENGE_SIZE: int = 9
    SOPHOMORE_FALLBACK_AGE: int = 22
    # Snubbed players shown; host cities not repeated within this many years.
    LEFT_OUT_SHOWN: int = 3
    HOST_NO_REPEAT: int = 5
    # Exhibition: share of the mean-OVR gap added to a side's total; floor of a player's share weight (a guard for
    # empty or zero lines, e.g. 0 PPG and 0 OVR: any real line weighs far more after SHARE_POWER, so it never bites
    # otherwise); points added to the better side's top scorer to break a tie. DUNK_MAX: the per-dunk judges' ceiling.
    OVR_TOTAL_NUDGE: float = 0.5
    MIN_SHARE_WEIGHT: float = 0.1
    TIE_BREAK_POINTS: int = 2
    DUNK_MAX: int = 50
    # Dunk contest: dunk names, dunks per player in round 1, finalists.
    DUNK_NAMES: tuple = ("360 Windmill", "Between the Legs", "Behind the Back", "Free Throw Line",
                         "Double Pump", "Eastbay", "Reverse Jam")
    DUNKS_ROUND1: int = 2
    DUNK_FINALISTS: int = 2
    # 3-Point contest: random range + (r3 - 70) / divisor, clamped; finalists count.
    THREE_PT_ROUND1_RANGE: tuple = (12, 20)
    THREE_PT_ROUND1_DIVISOR: int = 5
    THREE_PT_ROUND1_CLAMP: tuple = (5, 30)
    THREE_PT_FINAL_RANGE: tuple = (15, 25)
    THREE_PT_FINAL_DIVISOR: int = 4
    THREE_PT_FINAL_CLAMP: tuple = (10, 30)
    THREE_PT_RATING_BASE: int = 70
    THREE_PT_FINALISTS: int = 3
    # Tied contest final: the tied leaders shoot off / dunk off (same scoring rules) at most this many times;
    # still level, the better round-1 rank wins.
    TIEBREAK_MAX_ROUNDS: int = 3

@dataclass(frozen=True)
class Era:
    """How the league's style evolves with the year (main.py Tournament.get_era_*, core/game_engine.py).

    Calibration, real NBA (league team averages): 2002-03 95 PPG / 91 pace / 14.7 3PA / 34.9 3P%;
    2010-11 99.6 / 92 / 18 / 35.8; 2020-21 112 / 99 / 34.6 / 36.7; 2024-25 ~114 / ~99.5 / ~37.5 / ~36.
    """
    # Pace (possessions) logistic curve: floor + span / (1 + exp(-rate * (year - inflection))), clamped.
    PACE_FLOOR: float = 0.910
    PACE_SPAN: float = 0.125
    PACE_INFLECTION: float = 2016.5
    PACE_RATE: float = 0.28
    PACE_CLAMP: tuple = (0.900, 1.070)
    # Three-point volume multiplier, same logistic shape. A long 2002 save keeps more old-school shooters than
    # the real league, so the span is wider than the raw real-world ratio to reach modern volume.
    THREE_FLOOR: float = 0.800
    THREE_SPAN: float = 1.250
    THREE_INFLECTION: float = 2015.5
    THREE_RATE: float = 0.24
    THREE_CLAMP: tuple = (0.78, 2.20)
    # Random walk of pace / 3PT volume from DRIFT_FROM_YEAR on: step range, mean reversion, clamps.
    DRIFT_FROM_YEAR: int = 2025
    PACE_DRIFT_STEP: float = 0.006
    THREE_DRIFT_STEP: float = 0.008
    DRIFT_REVERSION: float = 0.15
    PACE_DRIFT_CLAMP: tuple = (-0.030, 0.035)
    THREE_DRIFT_CLAMP: tuple = (-0.060, 0.120)
    # Game-engine constants, linear from START_YEAR (first value) to END_YEAR (second value), flat outside.
    START_YEAR: int = 2002
    END_YEAR: int = 2025
    PERIMETER_FOUL_CHANCE: tuple = (3.8, 3.00)  # % chance per action of a perimeter foul (hand-check, holding)
    DRAW_FOUL_MULT: tuple = (0.18, 0.125)        # draw-foul rating weight on shooting fouls
    DRIVE_FOUL_MULT: tuple = (0.12, 0.075)       # drive tendency weight on shooting fouls
    SPEED_FOUL_MULT: tuple = (0.08, 0.03)        # speed weight on shooting fouls
    THREE_MAKE_BASE: tuple = (36.2, 38.8)        # base make % of a three: rises to offset the extra volume
    CLOSE_MAKE_BASE: tuple = (52.5, 56.5)        # base make % at the rim (spacing opens the paint)
    FT_BOOST: tuple = (5.0, 6.5)                 # added to the free-throw rating (real FT% 75.7 -> ~78)
    ASSIST_BASE: tuple = (80.0, 88.0)            # base % that a made basket is assisted
    # Inverse era curve for traditional center dominance (peak in 2002, tapering toward 2025 pace-and-space):
    CENTER_FOCUS_MULT: tuple = (1.14, 0.96)      # offensive focus weight boost for interior bigs (C/PF)
    POST_UP_ELITE_MULT: tuple = (4.6, 2.4)       # scheme multiplier for elite post scorers (post_up_tendency > 75)
    POST_UP_SUB_MULT: tuple = (2.6, 1.5)         # scheme multiplier for secondary post bigs (post_up_tendency > 65)
    CENTER_REBOUND_ERA_BOOST: tuple = (1.10, 0.96) # interior rebound presence multiplier for centers across eras
    # Turnovers per possession fall with the era (real TOV% ~14.5 in 2002, ~12.8 in 2025). Without these the
    # turnovers grew with the pace: 17 a game in a long save against ~14 in the real league.
    STEAL_MULT: tuple = (1.0, 0.95)              # steal attempts and pass interceptions
    UNFORCED_TURNOVER_MULT: tuple = (1.0, 0.82)  # lost dribbles, travels, out of bounds
    # A league that STARTS at END_YEAR or later (modern database) has rosters that already shoot like today's
    # league, so it keeps these values instead: three-point volume span / inflection, end make % and FT boost.
    MODERN_START_THREE_SPAN: float = 0.650
    MODERN_START_THREE_INFLECTION: float = 2016.5
    MODERN_START_THREE_MAKE_END: float = 32.8
    MODERN_START_CLOSE_MAKE_END: float = 52.8
    MODERN_START_FT_BOOST_END: float = -0.8
    # Play-In Tournament: first season it is played when the league setting asks for the historical default.
    PLAY_IN_DEFAULT_START_YEAR: int = 2020

@dataclass(frozen=True)
class FrontOffice:
    """AI GM (core/front_office): CPU GMs, team plans and their move logs."""
    # Philosophy traits: code -> label shown in the UI. A GM keeps his traits for his whole career.
    TRAITS: dict = field(default_factory=lambda: {
        "PICK_HOARDER": "Pick hoarder",
        "YOUTH_FIRST": "Youth first",
        "TRADE_HAPPY": "Trade happy",
        "VETERAN_LOVER": "Veteran lover",
        "STAR_CHASER": "Star chaser",
        "DEFENSE_FIRST": "Defense first",
        "OFFENSE_FIRST": "Offense first",
        "CAP_GUARDIAN": "Cap guardian",
        "LOYALIST": "Loyalist",
        "PATIENT_BUILDER": "Patient builder",
    })
    # The three skills, 0-100.
    SKILLS: tuple = ("trade", "contracts", "draft")
    # Historical GMs start squeezed toward the middle: nobody at the extremes.
    SKILL_START_MIN: int = 50
    SKILL_START_MAX: int = 82
    # Generated GMs (no historical one available): age and skill ranges, traits per GM.
    GENERATED_SKILL_RANGE: tuple = (45, 70)
    GENERATED_AGE_RANGE: tuple = (34, 46)
    GENERATED_TRAITS: int = 2
    GENERATED_FIRST_NAMES: tuple = (
        "Aaron", "Brent", "Calvin", "Dale", "Eric", "Frank", "Grant", "Hank", "Ian", "Jared", "Keith", "Lance",
        "Marty", "Neil", "Owen", "Phil", "Quinn", "Russ", "Seth", "Todd", "Vince", "Wade", "Gary", "Doug",
        "Mark", "Ross", "Dean", "Kurt", "Brad", "Glen",
    )
    GENERATED_LAST_NAMES: tuple = (
        "Ashford", "Bellamy", "Carver", "Dorsey", "Ellison", "Fairbanks", "Gaffney", "Holloway", "Ingram",
        "Jessup", "Kessler", "Lindqvist", "Merriman", "Norwood", "Oakes", "Pruitt", "Quarles", "Rendell",
        "Sayers", "Thibault", "Underhill", "Vickers", "Whitlock", "Yardley", "Zeller", "Brannigan", "Colfax",
        "Dunmore", "Harlan", "Stroud",
    )
    # Expected wins from the top-8 OVR average against the league average, clamped to the range.
    EXPECTED_WINS_BASE: int = 41
    EXPECTED_WINS_PER_OVR: float = 1.5
    EXPECTED_WINS_RANGE: tuple = (15, 65)
    EXPECTED_WINS_EMPTY_ROSTER: int = 20
    # Coach of the Year: wins over expected plus this share of the jump from last season.
    COY_JUMP_WEIGHT: float = 0.5
    # GM of the Year: jump and wins over expected, multiplied up by how much of the top 8 is new.
    GMOY_JUMP_WEIGHT: float = 1.0
    GMOY_EXPECTED_WEIGHT: float = 0.5
    GMOY_TURNOVER_WEIGHT: float = 0.5
    # Season rows kept per team in the saved front office (oldest dropped).
    RECORDS_KEEP_PER_TEAM: int = 20
    # Deep-save catch-up only in layer 1: an original GM aged past this is replaced on load.
    RETIREMENT_AGE: int = 64
    # Team plan states.
    PLAN_STATES: tuple = ("CONTENDER", "PLAYOFF", "MIDDLE", "REBUILDER")
    PLAN_LABELS: dict = field(default_factory=lambda: {
        "CONTENDER": "Contender",
        "PLAYOFF": "Playoff push",
        "MIDDLE": "Middle",
        "REBUILDER": "Rebuild",
    })
    # A plan changes at the season start only after it has run this many seasons (CONTENDER <-> REBUILDER: at once).
    PLAN_MIN_SEASONS: int = 2
    # Deadline emergency: only after this many games, below/above these win rates.
    PLAN_DEADLINE_MIN_GAMES: int = 40
    PLAN_COLLAPSE_WIN_PCT: float = 0.30
    PLAN_SURPRISE_WIN_PCT: float = 0.65
    # How long each plan usually runs, shown as "season 2 of ~3".
    PLAN_EXPECTED_SEASONS: dict = field(default_factory=lambda: {
        "CONTENDER": 3, "PLAYOFF": 3, "MIDDLE": 2, "REBUILDER": 4,
    })
    # Rising Star roster: a playoff plan when its top-8 rating is within this of the league's top-8 average.
    PLAN_RISING_STAR_MARGIN: float = 1.0
    # ---- Layer 3: coach firings (Black Monday, mid-season, daily drift) ----
    COACH_JSS_BASE: float = 70.0            # Job security before the season's evidence
    COACH_JSS_PER_WIN: float = 1.5          # Per win above/below the season's expected wins
    COACH_GRACE_NEW_DEAL: float = 20.0      # Coach in year 1 of a 3+ year deal
    COACH_GRACE_SECOND_YEAR: float = 10.0   # Coach in year 2 of a 4+ year deal
    COACH_PLAYOFF_BONUS: float = 12.0
    COACH_NO_PLAYOFF_PENALTY: float = 8.0
    COACH_REBUILD_PATIENCE: float = 25.0    # Added when the team's rebuild is on schedule
    COACH_REBUILD_GRACE: int = 1            # Seasons past PLAN_EXPECTED_SEASONS["REBUILDER"] still counted on schedule
    COACH_OWNER_PATIENCE_STEP: float = 5.0  # Per step of OWNER_BOARD_PATIENCE away from neutral, when far below expectations
    COACH_OWNER_NEUTRAL_PATIENCE: int = 3   # The OWNER_BOARD_PATIENCE value that neither adds nor takes rope
    COACH_OWNER_DELTA: float = -6.0         # "Far below expectations": wins minus expected under this
    COACH_FIRE_JSS: float = 18.0
    COACH_FIRE_MIN_SEASONS: int = 2
    COACH_CATASTROPHE_WINS: int = 20        # Fewer wins than this with COACH_CATASTROPHE_EXPECTED expected: fired at once
    COACH_CATASTROPHE_EXPECTED: float = 48.0
    # Mid-season collapse (after the deadline): a CONTENDER under this win rate after this many games fires a coach
    # with at least this many seasons in charge, and names an interim.
    COACH_MIDSEASON_WIN_PCT: float = 0.30
    COACH_MIDSEASON_MIN_GAMES: int = 42
    COACH_MIDSEASON_MIN_SEASONS: int = 2
    # Daily job-security drift: from this many games, change = (win rate - expected win rate) x PER_WIN_PCT x owner
    # patience; a rebuilding team's coach falls slower (x REBUILD_FALL) and climbs faster (x REBUILD_RISE).
    COACH_DRIFT_MIN_GAMES: int = 15
    COACH_DRIFT_PER_WIN_PCT: float = 15.0
    COACH_DRIFT_REBUILD_FALL: float = 0.3
    COACH_DRIFT_REBUILD_RISE: float = 1.2
    # Daily job-security drift: multiplier on a falling coach's change, by owner type.
    COACH_DRIFT_PATIENCE: dict = field(default_factory=lambda: {
        "Spendaccione": 1.5, "Risparmiatore": 0.7, "Esigente": 1.0, "Bilanciato": 1.0, "Ricostruttore": 1.0,
    })
    # GM <-> coach link: what the GM looks for to fit his coach's style (one entry per CONFIG.COACHINGSTYLES style).
    COACH_STYLE_TARGETS: dict = field(default_factory=lambda: {
        "Pace & Space": "Shooters and quick guards who can attack closeouts",
        "Run and Gun": "Fast scorers who shoot early in the clock",
        "Triangle Offense": "Smart passers, post scorers and mid-range shooters",
        "Perimeter-centric": "Three-point shooters and ball handlers",
        "Post Play Dominance": "A dominant low-post big and shooters around him",
        "Grit & Grind": "Defensive wings and physical bigs",
        "Defensive Minded": "Stoppers at every position, offense second",
        "Man-to-Man Lockdown": "Quick, long on-ball defenders",
        "Twin Towers": "Two big men who rebound and protect the rim",
        "Balanced Offense": "Versatile two-way players, no weak spots",
        "System Basketball": "High-IQ role players who move the ball",
        "Fast Break Offense": "Athletes who run the floor and rebounders who push",
        "Point Guard Maestro": "An elite playmaker and finishers around him",
        "Small Ball Strategy": "Switchable forwards and stretch bigs",
    })
    # ---- Layer 3: GM growth, retirement and the owner's GM firing ----
    # Skill growth per season while seated: base points scaled by years as GM (first matching lower bound from
    # the top), fractions resolved by chance. Result bonus is added per skill.
    GROWTH_BASE: float = 1.0
    GROWTH_BY_YEARS: tuple = ((0, 2.0), (5, 1.0), (10, 0.5))
    GROWTH_RESULT_BEAT_EXPECTED_BY: int = 5   # Wins over expected for the bonus
    GROWTH_RESULT_BEAT_EXPECTED: int = 1
    GROWTH_RESULT_PLAYOFFS: int = 1
    GROWTH_RESULT_TITLE: int = 2
    SKILL_FLOOR: int = 20
    SKILL_CEILING: int = 95
    GROWTH_STOP_AGE: int = 55
    DECLINE_AGE: int = 58
    DECLINE_CHANCE: float = 0.3               # Per skill per season, -1
    # Retirement: (age, chance) points, linear between, 0 below the first age, the last chance from the last age.
    RETIRE_CHANCE_POINTS: tuple = ((58, 0.04), (62, 0.12), (65, 0.30), (68, 0.60), (70, 1.0))
    MARKET_IDLE_RETIRE_YEARS: int = 4         # Unseated non-historical GMs: idle years since his last job (or since
                                              # available_from_year when he never had one)
    # Owner's GM firing.
    GM_FIRE_MIN_TENURE: int = 2
    GM_FIRE_AFTER_COACH_SEASONS: int = 2
    GM_FIRE_BELOW_BY: int = 4                 # Wins under expected that count as a failed season
    GM_FIRE_LONG_RUN: int = 4
    GM_FIRE_PATIENCE_SHIFT: dict = field(default_factory=lambda: {"Esigente": -1, "Ricostruttore": 1})
    GM_FIRE_CHANCE: float = 0.7
    # GM market: made-up GMs entering each offseason so there is always a credible pool (young, mid-to-low).
    MARKET_NEWCOMERS_PER_YEAR: int = 2
    MARKET_NEWCOMER_AGE: tuple = (29, 40)
    MARKET_NEWCOMER_SKILLS: tuple = (40, 62)
    # Reputation (what the owners see): skills average + years as GM (capped) + playoff runs and titles in his jobs.
    REP_PER_YEAR: float = 0.5
    REP_YEARS_CAP: int = 10
    REP_PER_PLAYOFF: float = 0.5
    REP_PER_TITLE: float = 3.0
    # Owner's score of a candidate: reputation x weight + fit to the moment x weight + young bonus + noise.
    HIRING_REP_WEIGHT: float = 1.0
    HIRING_FIT_WEIGHT: float = 1.0
    FIT_PER_TRAIT: float = 4.0
    HIRING_WIN_NOW_TRAITS: tuple = ("STAR_CHASER", "VETERAN_LOVER", "TRADE_HAPPY")
    HIRING_BUILD_TRAITS: tuple = ("PICK_HOARDER", "YOUTH_FIRST", "PATIENT_BUILDER")
    # Reputation multiplier by owner type (others 1.0): these owners chase names.
    HIRING_OWNER_WEIGHTS: dict = field(default_factory=lambda: {"Esigente": 1.3, "Spendaccione": 1.3})
    # These owners bet on a young or new GM: bonus for age < HIRING_YOUNG_AGE or under HIRING_YOUNG_YEARS as GM.
    HIRING_YOUNG_OWNERS: tuple = ("Ricostruttore", "Risparmiatore")
    HIRING_YOUNG_BONUS: float = 6.0
    HIRING_YOUNG_AGE: int = 40
    HIRING_YOUNG_YEARS: int = 3
    HIRING_NOISE: float = 4.0                 # Uniform +- on every owner score
    # Team appeal (~0-100): 50 + (last wins - 41) x APPEAL_PER_WIN + top-8 OVR gap to the league x APPEAL_PER_OVR
    # + the owner's spending tier.
    APPEAL_BASE: float = 50.0
    APPEAL_PER_WIN: float = 1.0
    APPEAL_PER_OVR: float = 3.0
    APPEAL_SPENDING: dict = field(default_factory=lambda: {"low": -5.0, "mid": 0.0, "high": 5.0})
    # A wanted GM (reputation at least this) turns down a team under HIRING_REFUSE_APPEAL while another seat is open.
    HIRING_WANTED_REP: float = 72.0
    HIRING_REFUSE_APPEAL: float = 45.0
    HIRING_CHOSEN_OVER_NAMES: int = 2         # Runner-ups kept in the hired GM's "chosen over" note
    HIRING_NOTES_KEEP: int = 12               # Hiring notes kept per GM (newest)
    # What the owner looks for in a new GM, by the roster's plan read: "WIN_NOW", "BUILD" or "ANY".
    HIRING_WANTED_BY_PLAN: dict = field(default_factory=lambda: {
        "CONTENDER": "WIN_NOW", "PLAYOFF": "WIN_NOW", "REBUILDER": "BUILD", "MIDDLE": "ANY",
    })
    # A new GM re-reads a MIDDLE roster through his philosophy: this many build / win-now traits tip it.
    NEW_GM_LEAN_TRAITS: int = 2
    # ---- Layer 2a: trades go through the GM (core/front_office/trade_brain.py) ----
    # Philosophy: what a GM is willing to pay for an asset. trait -> asset tag -> multiplier on its trade value.
    TRAIT_VALUE: dict = field(default_factory=lambda: {
        "PICK_HOARDER": {"pick_r1": 1.20, "pick_r2": 1.25, "player_30_plus": 0.92},
        "YOUTH_FIRST": {"player_24_minus": 1.12, "player_30_plus": 0.88},
        "VETERAN_LOVER": {"player_29_plus_75": 1.12, "player_22_minus_raw": 0.90},
        "STAR_CHASER": {"player_star": 1.12, "pick_r1": 0.92, "pick_r2": 0.92},
        "CAP_GUARDIAN": {"expiring": 1.15, "long_heavy": 0.80},
        "DEFENSE_FIRST": {"defender": 1.08},
        "OFFENSE_FIRST": {"scorer": 1.08},
        "LOYALIST": {"own_long_tenure": 1.15},
        "PATIENT_BUILDER": {"pick_r1": 1.08, "own_young": 1.10},
        "TRADE_HAPPY": {},
    })
    # The product of every matching trait tag stays inside this range.
    TRAIT_MULT_RANGE: tuple = (0.75, 1.40)
    # "Long heavy" deal: 3+ years left at this share of the cap or more (stars excepted).
    LONG_HEAVY_CAP_SHARE: float = 0.20
    # GM <-> coach link: a player in the league's top share on his coach's style attributes is worth this much more.
    COACH_FIT_BONUS: float = 1.06
    # Profile lines (coach styles, defender, scorer): the league's top share on those attributes.
    PROFILE_TOP_SHARE: float = 0.25
    PROFILE_ATTRIBUTES: dict = field(default_factory=lambda: {
        "DEFENSE": ("interior_defense_rating", "perimeter_defense_rating", "defensive_iq_rating"),
        "OFFENSE": ("close_shot_rating", "mid_range_shot_rating", "three_point_shot_rating", "shot_iq",
                    "offensive_iq_rating"),
    })
    # The abilities each coaching style wants (one entry per CONFIG.COACHINGSTYLES style).
    COACH_STYLE_ATTRIBUTES: dict = field(default_factory=lambda: {
        "Pace & Space": ("three_point_shot_rating", "speed", "ball_handling"),
        "Run and Gun": ("speed", "acceleration", "three_point_shot_rating"),
        "Triangle Offense": ("passing_vision", "post_control_rating", "mid_range_shot_rating"),
        "Perimeter-centric": ("three_point_shot_rating", "ball_handling"),
        "Post Play Dominance": ("post_control_rating", "close_shot_rating", "strength"),
        "Grit & Grind": ("perimeter_defense_rating", "interior_defense_rating", "strength"),
        "Defensive Minded": ("perimeter_defense_rating", "interior_defense_rating", "defensive_iq_rating"),
        "Man-to-Man Lockdown": ("perimeter_defense_rating", "steal_rating", "speed"),
        "Twin Towers": ("interior_defense_rating", "block_rating", "defensive_rebound_rating"),
        "Balanced Offense": ("offensive_iq_rating", "defensive_iq_rating", "shot_iq"),
        "System Basketball": ("offensive_iq_rating", "passing_accuracy", "shot_iq"),
        "Fast Break Offense": ("speed", "acceleration", "defensive_rebound_rating"),
        "Point Guard Maestro": ("passing_vision", "passing_accuracy", "ball_handling"),
        "Small Ball Strategy": ("speed", "three_point_shot_rating", "perimeter_defense_rating"),
    })
    # Trade skill -> price: (skill, multiplier on the acceptance threshold), linear in between. 60 = fair.
    SKILL_PRICE_POINTS: tuple = ((20, 0.88), (35, 0.94), (50, 0.97), (60, 1.00), (70, 1.025), (82, 1.05), (95, 1.07))
    # A skilled GM squeezes the user harder: + this per trade-skill point above 60, at most USER_SQUEEZE_MAX.
    USER_SQUEEZE_PER_POINT: float = 0.002
    USER_SQUEEZE_MAX: float = 0.06
    # Disasters: only below this trade skill, a random misjudgement of up to this much per point below it.
    DISASTER_SKILL_BELOW: int = 35
    DISASTER_SPREAD_PER_POINT: float = 0.012
    # Vulture: from this trade skill a GM is first in line when a team dumps a player or salary.
    VULTURE_SKILL: int = 70
    # ...but only this many vultures get a guaranteed seat at an auction / dump; the rest of the field is random.
    VULTURE_GUARANTEED_SLOTS: int = 2
    # Protection lines relative to the league: OVR at this top share of rostered players, never below the floor.
    STAR_LINE_TOP_SHARE: float = 0.075
    STAR_LINE_FLOOR: int = 85
    CORE_LINE_TOP_SHARE: float = 0.15
    CORE_LINE_FLOOR: int = 80
    # Trade-happy GMs love to deal: the acceptance threshold is multiplied by this (he says yes a little sooner).
    # BENCH_SHUFFLE_TOP_KEEP: a team's top players by OVR, never a "weak bench spot" (BENCH_HOLE).
    TRADE_HAPPY_THRESHOLD_MULT: float = 0.97
    BENCH_SHUFFLE_TOP_KEEP: int = 9
    BENCH_SHUFFLE_VALUE_GAP: float = 0.08
    # Pick hoarders: absorb salary for picks up to this payroll share of the cap; sell vets this old, this often.
    PICK_HOARDER_ABSORB_PAYROLL_SHARE: float = 0.90
    PICK_HOARDER_SELL_CHANCE: float = 0.35
    PICK_HOARDER_SELL_MIN_AGE: int = 30
    # A rebuilding team's chance to package picks for a young star instead of selling (by GM trait; first match wins).
    AGGRESSIVE_REBUILD_CHANCE: float = 0.25
    # Star chasers on a winning plan target anyone this close to the star line, whatever the position need.
    STAR_CHASER_TARGET_GAP: int = 3
    AGGRESSIVE_REBUILD_CHANCE_BY_TRAIT: dict = field(default_factory=lambda: {
        "STAR_CHASER": 0.50, "PATIENT_BUILDER": 0.0,
    })
    # Moves kept in each team's log (oldest dropped first).
    MOVES_KEEP_PER_TEAM: int = 40
    # The user's team: a completed pre-season summit goal sets the plan (same mapping as the trade AI).
    SUMMIT_GOAL_PLANS: dict = field(default_factory=lambda: {
        "TANKING": "REBUILDER", "ASSET_GROWTH": "REBUILDER",
        "CHAMPIONSHIP": "CONTENDER", "DOMINANCE": "CONTENDER",
        "PLAYOFFS": "PLAYOFF", "SUSTAINABLE_CONTENDER": "PLAYOFF",
        "PLAY_IN": "MIDDLE", "PLAYOFF_HUNT": "MIDDLE",
    })

@dataclass(frozen=True)
class Trades:
    """Trade system rework: league-relative lines (core/front_office/era_lines.py) and shared trade numbers."""
    # Money scale reference: the game's own cap scale in main.py (the 155.0 "modern" cap).
    REFERENCE_CAP: float = 155.0
    NO_CAP_THRESHOLD: float = 9000.0   # a salary cap this big means "no cap" (same convention as main.py)
    # Salary matching by era: (first year, last year, rule). Cap 40.27 era = 125% + $100k; modern bands after.
    SALARY_MATCH_ERAS: Tuple[Tuple[int, int, str], ...] = ((0, 2022, "PCT_125"), (2023, 9999, "MODERN"))
    PCT_125_RATIO: float = 1.25
    PCT_125_PLUS: float = 0.1
    # (outgoing up to, ratio, plus) at REFERENCE_CAP; scaled by cap / REFERENCE_CAP.
    MODERN_BANDS: Tuple[Tuple[float, float, float], ...] = ((6.5, 1.75, 0.25), (19.6, 1.0, 5.0), (float("inf"), 1.25, 0.25))
    SECOND_APRON_RATIO: float = 1.10
    # OVR lines below the core line: OVR at the top share of rostered players.
    BAND_SHARES: dict = field(default_factory=lambda: {"starter": 0.33, "rotation": 0.60, "bench": 0.85})
    # Salary percentiles of rostered players kept in EraLines.salary_pcts.
    SALARY_PERCENTILES: Tuple[float, ...] = (0.60, 0.90)
    HIGH_SALARY_PCT: float = 0.90   # a "high" contract is at or above this salary percentile...
    MID_SALARY_PCT: float = 0.60
    LONG_CONTRACT_YEARS: int = 3    # ...and runs at least this many years
    # Mean trade_value of rostered players on a 2002 league (the old step curve gave 83.93 on a fresh league;
    # the value-over-replacement curve gives 43.57, measured 2026-11-03 on the s42_deadline trade-lab fixture,
    # season 1 of 2002). A league whose players are worth more than this makes picks worth proportionally more
    # (EraLines.pick_scale). Re-measure when the VALUE_CURVE_* numbers change.
    PICK_VALUE_REFERENCE_AVG: float = 43.57
    PICK_SCALE_RANGE: Tuple[float, float] = (0.7, 1.5)
    # Health check only: a CPU side that gets back less than this share of what it gave (in its own GM's value)
    # is a "gift" trade (trade_demand and tax_dump are priced low on purpose and excluded).
    GIFT_SHARE: float = 0.6
    # --- Player trade value curve (Giocatore.trade_value) ---
    # value = curve(rating) - curve(REPLACEMENT_OVR), curve(r) = ANCHOR_VALUE * exp((r - ANCHOR_OVR) / SCALE):
    # every SCALE OVR points multiply the curve by e, and a player is worth what he adds over the kind of player
    # any team finds for free, so two role players never add up to a starter by accident. Under 25 the rating
    # also counts YOUNG_POTENTIAL_SHARE of the gap to potential. SCALE <= 0 restores the old step curve
    # (value = OVR below 82, x1.4/x2.0/x2.6... above, +1.4 per potential point under 25).
    VALUE_CURVE_ANCHOR_OVR: float = 75.0
    VALUE_CURVE_ANCHOR_VALUE: float = 75.0
    VALUE_CURVE_SCALE: float = 12.2
    VALUE_CURVE_REPLACEMENT_OVR: float = 69.0
    VALUE_YOUNG_POTENTIAL_SHARE: float = 0.5
    VALUE_FLOOR: float = 2.0
    # Picks on the player curve (trade values; the rule lines still read the old 40-150 first-round scale): a
    # first's old base value maps linearly to the OVR of the player it is worth, through these two (base, OVR)
    # points, and is priced like that player before the year discount, protection and pick_scale.
    PICK_CURVE_POINTS: Tuple[Tuple[float, float], Tuple[float, float]] = ((40.0, 70.5), (150.0, 88.0))
    # Base trade value of a second-round pick before year discount and pick_scale: next to nothing, as in the real
    # league. Seconds still pay for a salary dump or a deadline rental, never sweeten a player package.
    PICK_R2_BASE_VALUE: float = 0.5
    PICK_YEAR_DISCOUNT: float = 0.85   # what a pick loses per year of waiting
    # The price question counts the players a team receives at these shares, best first (the last share for the
    # rest): a roster spot has a cost, so three role players never add up to the starter they replace. A young
    # second player with POT >= the old 82 line counts in full.
    RECEIVED_PLAYER_SHARES: Tuple[float, ...] = (1.0, 0.5, 0.25)
    # What a player is worth to a rebuilding team (get_strategic_value), as a share of his trade value: young
    # (<= 24) a bit more, a star still most of it, a veteran role player (REBUILDER_VET_AGE+) and a prime role player
    # (25 up to the veteran age) less. A veteran the rebuild wants gone anyway (last contract year, or a long heavy
    # contract) is cheap (REBUILDER_DUMP_VET_SHARE); any other veteran is not given away (REBUILDER_VET_SHARE; the
    # old flat 0.45 sold an 80 OVR starter for one far first). These shares price both its own players and the
    # ones it receives.
    REBUILDER_YOUTH_MULT: float = 1.15
    REBUILDER_STAR_SHARE: float = 0.85
    REBUILDER_VET_AGE: int = 28
    REBUILDER_VET_SHARE: float = 0.75
    REBUILDER_DUMP_VET_SHARE: float = 0.45
    REBUILDER_PRIME_SHARE: float = 0.85
    # ...and a veteran role player it receives counts at this share on top: it sells veterans for picks and youth,
    # not for more veterans.
    REBUILDER_RECEIVED_VET_SHARE: float = 0.25
    # --- GM wishes (core/front_office/wishes.py) ---
    WISH_PRIORITY: dict = field(default_factory=lambda: {
        "STAR_WANTS_OUT": 95.0, "SHED_TAX": 90.0, "WANT_STAR": 85.0, "NEED_STARTER": 80.0, "RENT_VETERAN": 75.0,
        "SELL_EXPIRING": 72.0, "CLEAR_LONG_CONTRACT": 70.0, "SELL_VETERANS": 68.0, "ROLE_CONGESTION": 65.0,
        "UNHAPPY_PLAYER": 62.0, "TARGET_PROSPECT": 60.0, "MOVE_UP_DRAFT": 58.0,
        "WANT_YOUTH": 52.0, "WANT_PICKS": 50.0, "MOVE_DOWN_DRAFT": 48.0, "DEPTH_NEEDED": 45.0,
        "ABSORB_SALARY": 40.0, "BENCH_HOLE": 30.0})
    TAX_PRIORITY_BONUS: float = 10.0   # SHED_TAX priority bonus for a saver owner, and again for a CAP_GUARDIAN GM
    SAVER_OWNER: str = "Risparmiatore"
    VETERAN_MIN_AGE: int = 30
    YOUNG_MAX_AGE: int = 24
    PRIME_VET_AGES: Tuple[int, int] = (27, 33)
    RENT_MIN_AGE: int = 30
    # A deadline rental is paid with a second or a young player, and the salary is matched only with real surplus:
    # players at or under this OVR (2002 scale, era.ovr_at), older than YOUNG_MAX_AGE, on an expiring contract when
    # RENT_FILLER_EXPIRING_ONLY. Never a player as good as the rental.
    RENT_FILLER_MAX_OVR: int = 70
    RENT_FILLER_EXPIRING_ONLY: bool = True
    # The seller of an expiring veteran (SELL_EXPIRING) takes back an expiring bench contract at least this many OVR
    # below the rental (RENT_PAY_FILLER_GAP) on top of the second; no young player and no first is the price.
    RENT_PAY_FILLER_GAP: int = 3
    # The seller of an expiring veteran takes the cheap price (a second, no value check) only for a rental at or under
    # this OVR (2002 scale, era.ovr_at); a better veteran is priced in full. Every rental includes a draft pick.
    RENT_WAIVE_MAX_OVR: int = 77
    # A rebuilding team keeps a player this young (<= REBUILDER_KEEP_YOUNG_MAX_AGE) and this good: he is the future.
    REBUILDER_KEEP_YOUNG_MAX_AGE: int = 26
    REBUILDER_KEEP_YOUNG_MIN_OVR: int = 78
    # A CPU team that sells a player at or above STAR_SALE_MIN_OVR gets a first-round pick, or a player at or above
    # STAR_RETURN_MIN_OVR, back: two or three role players never add up to a star. (2002 scale, era.ovr_at.)
    STAR_SALE_MIN_OVR: int = 81
    STAR_RETURN_MIN_OVR: int = 79
    # A CPU team gives a first-round pick only for a player at or above this OVR (2002 scale, era.ovr_at), or for
    # another first (pick swaps, trade-downs). A team paying on purpose (tax dump) is exempt.
    FIRST_PICK_MIN_OVR: int = 78
    # ...but a player below FIRST_PICK_OLD_MIN_OVR who is older than FIRST_PICK_MAX_AGE_BELOW does not earn a first.
    FIRST_PICK_OLD_MIN_OVR: int = 80
    FIRST_PICK_MAX_AGE_BELOW: int = 29
    # A team that sends a starter-band player in a deal adds at most this many picks to it: a swap of two starters
    # is evened out with one pick, never two.
    STARTER_SWAP_MAX_PICKS: int = 1
    # --- The user's manual trades (TradeFinder(manual=True)); CPU-to-CPU deals never read these ---
    # A CPU team with no need for the deal names a higher price instead of refusing (hard no's stay): this multiplier
    # on its threshold. A young cornerstone it would never sell to another CPU team costs MANUAL_CORNERSTONE_PREMIUM.
    MANUAL_PLAN_PREMIUM: float = 1.15
    MANUAL_CORNERSTONE_PREMIUM: float = 1.25
    MANUAL_STARTER_SWAP_MAX_PICKS: int = 4   # picks a team sending a starter can add to a manual trade
    PICK_PROTECTIONS: Tuple[str, ...] = ("Unprotected", "Top 3", "Top 5", "Lottery")   # the terms a first can carry
    MANUAL_R2_VALUE: float = 4.0             # a second closes a deal that is almost there
    # Nobody knows how good a team will be years from now: the record sets the value of its next first, and each later
    # first moves toward an average one (MANUAL_PICK_AVERAGE_BASE on the old 40-150 scale), reached
    # MANUAL_PICK_REGRESSION_YEARS out. Strong and weak teams alike.
    MANUAL_PICK_AVERAGE_BASE: float = 60.0
    MANUAL_PICK_REGRESSION_YEARS: int = 5
    MANUAL_PICK_YEAR_DISCOUNT: float = 0.95
    # The search: return packages are filled up to MANUAL_RETURN_TARGET of the market value of what the user gives
    # (trade value and pick value, whoever the team is), and an offer under MANUAL_MIN_RETURN_SHARE of it is not shown
    # (multi-team deals too, in the user's own valuation).
    MANUAL_RETURN_TARGET: float = 0.95
    MANUAL_MIN_RETURN_SHARE: float = 0.60
    MANUAL_MAX_RETURN_PICKS: int = 4
    MANUAL_MAX_RETURN_SECONDS: int = 2
    MANUAL_SEARCH_CANDIDATES: int = 8        # best players per team combined into return packages
    MANUAL_SPARE_CONTRACTS: int = 6          # the user's cheapest players tried to make the salaries match
    MANUAL_OFFERS_PER_TEAM: int = 2
    MANUAL_SEARCH_RESULTS: int = 25
    MANUAL_MULTI_MAX_USER_PICKS: int = 1     # picks a 3- or 4-team deal can ask the user to add
    # An untouchable who does not ask out moves only when his team's price threshold is this much higher (and the
    # deal fulfils a wish of that team). Once per deal; never waived by a tax dump.
    UNTOUCHABLE_PREMIUM: float = 1.30
    # Squadra.designa_intoccabili: above UNTOUCHABLE_FREE_AGE a player stays untouchable only as a real franchise
    # player: OVR >= UNTOUCHABLE_VET_OVR, or >= UNTOUCHABLE_VET_CONTENDER_OVR on a contender (plan or champion).
    # Younger rookies and prospects keep their own rule.
    UNTOUCHABLE_FREE_AGE: int = 26
    UNTOUCHABLE_VET_OVR: int = 88
    UNTOUCHABLE_VET_CONTENDER_OVR: int = 86
    MORALE_UNHAPPY: int = 50
    UNHAPPY_MIN_BAND: str = "core"     # an unhappy player starts a change of scenery only at this era band or above
    OUT_OF_RACE_WIN_PCT: float = 0.40
    TAX_DUMP_MIN_CUT_SHARE: float = 0.15   # of the cap
    # SHED_TAX before the aprons (no second apron in the league): payroll over the tax by more than this share of the
    # cap, by the owner's spending tier (ECONOMY.OWNER_SPENDING_TIER; a CAP_GUARDIAN GM counts as "low"). None: that
    # owner pays the tax. Before 2023 the tax hardly mattered: only a team far over it sells.
    SHED_TAX_OVER_SHARE_BY_TIER: dict = field(default_factory=lambda: {"low": 0.15, "mid": 0.40, "high": None})
    # With aprons every team over the second apron sheds down to it, whatever the owner.
    SHED_TAX_OVER_SECOND_APRON: bool = True
    # A team whose payroll next season (in season: contracts with 2+ years left; offseason: 1+) is already under
    # the trigger waits instead of selling.
    SHED_TAX_LOOK_AHEAD: bool = True
    # CLEAR_LONG_CONTRACT: a long heavy contract is a bad one only for a player of this band or lower, and never for
    # a young player (YOUNG_MAX_AGE).
    CLEAR_LONG_MAX_BAND: str = "rotation"
    DEPTH_MIN_ROTATION: int = 2
    CONGESTION_COUNT: int = 3
    WISH_ROLES: Tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")
    PICK_WEIGHTS: dict = field(default_factory=lambda: {"R1": 3.0, "R2": 0.0})   # "more picks" (WANT_PICKS): seconds don't count
    # A young core worth waiting for (wishes.young_future; OVR lines come from EraLines): trade requests and walks.
    DEMAND_YOUNG_AGE: int = 24            # young prospect: younger than this with potential >= ovr_at(84)
    DEMAND_YOUNG_POT_OLD: int = 84
    DEMAND_FUTURE_COUNT: int = 2
    DEMAND_FUTURE_AGE: int = 23           # or one younger than this with potential >= ovr_at(87)
    DEMAND_FUTURE_POT_OLD: int = 87
    # --- Acceptance price (trades/trade_finder.py would_accept_trade_with_reason) ---
    # trade_difficulty -> (threshold multiplier, minimum allowed threshold)
    DIFFICULTY: dict = field(default_factory=lambda: {
        "easy": (0.80, 0.65), "realistic": (0.97, 0.85), "hardcore": (1.22, 1.05)})
    # Main piece rule: the best asset received must be worth this share of the best asset given.
    # Tiers are (offset from the era star line, share), first match wins; None = any OVR.
    MAIN_PIECE: dict = field(default_factory=lambda: {
        "easy": ((None, 0.25),),
        "realistic": ((3, 0.38), (-2, 0.42), (None, 0.45)),
        "hardcore": ((3, 0.50), (-2, 0.52), (None, 0.55))})
    # ...when the star given asks out, or the team is rebuilding
    MAIN_PIECE_SELLER: dict = field(default_factory=lambda: {"easy": 0.25, "realistic": 0.35, "hardcore": 0.45})
    # Star premium: threshold multiplier for giving up a star (OVR >= era star line) without a near-equal back.
    STAR_PREMIUM: dict = field(default_factory=lambda: {
        "easy": ((None, 1.05),),
        "realistic": ((10, 1.20), (7, 1.16), (4, 1.12), (None, 1.08)),
        "hardcore": ((10, 1.35), (7, 1.30), (4, 1.25), (2, 1.18), (None, 1.12))})
    STAR_PREMIUM_MATCH_GAP: int = 2   # no premium when the best player back is at most this many OVR below
    # --- Trade engines (trades/engines/) ---
    MAX_DEAL_TEAMS: int = 4   # the 3/4-team extension adds teams up to this many (one third, then one fourth)
    # Positional swap: 1-for-1 between two teams with crossed hole and surplus (2002 OVR numbers, era.ovr_at).
    POSITIONAL_SWAP_OVR_RANGE_OLD: Tuple[int, int] = (76, 84)   # both players in this band
    POSITIONAL_SWAP_MAX_GAP: int = 4                          # OVR gap between the two players
    POSITIONAL_SWAP_SURPLUS_OVR_OLD: int = 75                 # surplus at a role: this many players at this OVR
    POSITIONAL_SWAP_SURPLUS_COUNT: int = 2
    # Star upgrade: what the buyer offers (picks / young players) and how many contracts it may add to match salaries.
    STAR_UPGRADE_MAX_SWEETENERS: int = 3
    # NEED_STARTER: the target must beat the buyer's best player at the role by at least this many OVR points.
    STAR_UPGRADE_MIN_GAP: int = 5
    TOP_KEPT_BY_OVR: int = 5               # a team keeps its best players by OVR out of filler and expiring packages
    STAR_UPGRADE_MAX_FILLERS: int = 2     # salary fillers: rotation contracts outside the buyer's top 5 by OVR (3-for-1 at most)
    # Offers for the user's pick on the clock: what the CPU package must be worth to the user, as a share of the pick.
    DRAFT_OFFER_PICK_SHARE: float = 0.95   # a lower pick with a player, or future picks
    DRAFT_OFFER_STAR_SHARE: float = 0.85   # a star alone
    # Win-now for youth (2002 OVR numbers, era.ovr_at): prospect for a prime veteran of the same role.
    WIN_NOW_PROSPECT_POT_OLD: int = 80     # the prospect's potential is at least this...
    WIN_NOW_PROSPECT_MAX_OVR_OLD: int = 78  # ...and his OVR at most this
    WIN_NOW_VET_OVR_RANGE_OLD: Tuple[int, int] = (78, 83)
    # Auctions (trades/engines/auction.py): bids for a player among the teams that want him.
    AUCTION_MAX_BIDDERS: int = 8           # seats at the table; vultures keep FRONT_OFFICE.VULTURE_GUARANTEED_SLOTS
    AUCTION_ZONE_SHARE: float = 0.85       # a bid under this share of the seller's minimum is out; finalists are within it of the best
    # Seller's minimum value as a share of the player's value, by the seller's plan (default for any other plan).
    AUCTION_SELLER_THRESHOLD: dict = field(default_factory=lambda: {"CONTENDER": 0.90, "REBUILDER": 1.05, None: 1.0})
    # A star the seller keeps is priced higher: (2002 OVR, multiplier), highest first; none when he asks out.
    AUCTION_STAR_PRICE_OLD: Tuple[Tuple[int, float], ...] = ((95, 1.30), (92, 1.25), (89, 1.20), (87, 1.15), (85, 1.10))
    # Tax dump (trades/engines/tax_dump.py): the price of a contract handed to a team with room under the tax.
    TAX_DUMP_R1_IF_HIGH_CONTRACT: bool = True   # a high long contract (era.is_high_contract) costs a first-rounder
    TAX_DUMP_R2_COUNT: int = 1                  # any other contract costs this many second-rounders
    # A team short of seconds may not pay an ordinary contract with a first: the absorber took the first and passed
    # the contract on with a second (first-for-second arbitrage, a first for $5.6M in a 30-season save).
    TAX_DUMP_R1_FALLBACK: bool = False
    TAX_DUMP_KEEP_TOP: int = 6                  # a tax cut never sends one of the team's best by OVR: the bench goes
    # Draft night (trades/engines/draft_night.py): how many slots a team on the clock will drop for the prospect it
    # needs, added to that prospect's place on the board, by the team's plan (none listed: no change). At least 1.
    DRAFT_NIGHT_DROP_BONUS: dict = field(default_factory=lambda: {"REBUILDER": 1, "CONTENDER": -1})
    DRAFT_NIGHT_MIN_DROP: int = 1


@dataclass(frozen=True)
class Contracts:
    """Contracts and free agency with a brain (core/front_office/contracts.py, offseason/contract_extensions.py,
    offseason/free_agency.py). OVR lines come from the era (EraLines); these are the player's and the GM's numbers."""
    # Loyalty to his team (replaces the old flat +20): points per season with the team (up to LOYALTY_MAX_YEARS) plus
    # (morale - LOYALTY_MORALE_PIVOT) x LOYALTY_MORALE_WEIGHT, clamped to [LOYALTY_MIN, LOYALTY_MAX].
    LOYALTY_PER_YEAR: float = 4.0
    LOYALTY_MAX_YEARS: int = 5
    LOYALTY_MORALE_PIVOT: int = 70
    LOYALTY_MORALE_WEIGHT: float = 0.3
    LOYALTY_MIN: float = 0.0
    LOYALTY_MAX: float = 25.0
    # A star (era star line) at least WALK_MIN_AGE walks away from a hopeless team: a rebuild, or a team under
    # WALK_HOPELESS_WIN_PCT after WALK_MIN_GAMES games, with no young core (wishes.young_future).
    WALK_MIN_AGE: int = 26
    WALK_HOPELESS_WIN_PCT: float = 0.35
    WALK_MIN_GAMES: int = 30
    # CPU renewals by plan (contracts.renewal_offer): a star's offer is his market value times RENEW_STAR_MULT[plan];
    # a rebuilder keeps a prime (not young, not veteran) starter with REBUILDER_PRIME_RENEW_CHANCE; a bench player
    # that is not a young prospect is kept with RENEW_BENCH_CHANCE (never by a rebuilder once a veteran).
    RENEW_STAR_MULT: dict = field(default_factory=lambda: {"CONTENDER": 1.10, "PLAYOFF": 1.05, "MIDDLE": 1.0,
                                                           "REBUILDER": 1.0})
    RENEW_BENCH_CHANCE: float = 0.40
    REBUILDER_PRIME_RENEW_CHANCE: float = 0.5
    # Free agency bidding (offseason/free_agency.py _raise_or_withdraw): a CPU team that really wants a player (its
    # fit bonus >= FA_WANT_FIT) and is not leading raises by FA_RAISE_STEP x his asking price each day, up to its first
    # offer x FA_RAISE_CEILING[plan] and what its money allows; at the ceiling and still behind it pulls out.
    FA_RAISE_STEP: float = 0.06
    FA_RAISE_CEILING: dict = field(default_factory=lambda: {"CONTENDER": 1.25, "PLAYOFF": 1.15, "MIDDLE": 1.10,
                                                            "REBUILDER": 1.05})
    FA_WANT_FIT: float = 1.25
    # Each night, before the players choose, the outbid teams bid again round after round until nobody raises (every
    # team stops at its ceiling or pulls out, so it ends by itself). This is only a safety bound on the rounds.
    FA_NIGHT_MAX_ROUNDS: int = 40
    # CPU contract extensions (offseason/contract_extensions.py): yearly raise on the new years of the deal.
    EXTENSION_RAISE_PCT: float = 0.05
    # Early-market salary floor (free_agency.dettaglio_punteggio), at any age: on days 1..FA_EARLY_FLOOR_DAYS a player
    # at least the OVR key turns down an offer under that share of his asking price. A ring chaser
    # (contender/superteam) at least FA_EARLY_FLOOR_RING_AGE only asks min(floor, full MLE). Below the lowest key
    # (rotation veterans) the old rules hold: the true minimum / BAE ring chase.
    FA_EARLY_FLOOR_DAYS: int = 7
    FA_EARLY_FLOOR: dict = field(default_factory=lambda: {84: 0.70, 80: 0.40})
    FA_EARLY_FLOOR_RING_AGE: int = 34
    # A star (OVR >= FA_WALK_LIFT_OVR, age >= FA_WALK_LIFT_AGE) who walked away from his team takes him back from
    # day FA_WALK_LIFT_DAY when no other team can pay him FA_WALK_LIFT_MARKET_PCT of his asking price (the teams with
    # cap space are rebuilding): his old team re-signs him with Bird rights instead of a contender getting him cheap.
    FA_WALK_LIFT_DAY: int = 5
    FA_WALK_LIFT_OVR: int = 84
    FA_WALK_LIFT_AGE: int = 32
    FA_WALK_LIFT_MARKET_PCT: float = 0.60
    # No piling up: a team signs at most FA_PILEUP_MAX veterans (OVR >= FA_PILEUP_OVR, age >= FA_PILEUP_AGE) with an
    # exception or the minimum (not cap space, not Bird rights) in one summer.
    FA_PILEUP_MAX: int = 1
    FA_PILEUP_OVR: int = 82
    FA_PILEUP_AGE: int = 30


@dataclass(frozen=True)
class DraftAI:
    """How a CPU team picks in the draft (core/front_office/draft_fit.py, offseason/draft.py). A prospect's score is
    his upside (POTENTIAL_WEIGHT of potential, the rest OVR) plus what he adds to THIS roster at his role. The roster
    fit is read off the era lines: a "hole" is no starter at the role, "blocked" a core player in his prime or a young
    talent already there, "depth" fewer than TRADES.DEPTH_MIN_ROTATION rotation players. A rebuilding team cares less."""
    BOARD_SIZE: int = 20               # prospects a team looks at (the top of the remaining class)
    POTENTIAL_WEIGHT: float = 0.8
    GENERATIONAL_POTENTIAL: int = 96   # a prospect this good among the first GENERATIONAL_BOARD is taken by a top pick
    GENERATIONAL_BOARD: int = 3
    GENERATIONAL_MAX_PICK: int = 5
    FIT_POINTS: dict = field(default_factory=lambda: {"hole": 5.0, "depth": 2.0, "ok": 0.0, "blocked": -7.0})
    FIT_WEIGHT_BY_PLAN: dict = field(default_factory=lambda: {"REBUILDER": 0.5})   # not listed: 1.0
    BLOCK_MAX_AGE: int = 32            # a core player older than this no longer blocks a rookie
    BLOCK_YOUNG_MAX_AGE: int = 25      # a young talent (age at most this, potential at the core line) blocks him
    # The plan moves the weight between upside and readiness (not listed: POTENTIAL_WEIGHT); a YOUTH_FIRST GM adds
    # UPSIDE_TRAIT_BONUS to it.
    POTENTIAL_WEIGHT_BY_PLAN: dict = field(default_factory=lambda: {"REBUILDER": 0.9, "CONTENDER": 0.65})
    UPSIDE_TRAIT_BONUS: float = 0.1
    # Draft skill (GM skills["draft"], 0-100): the GM sees a prospect's potential with an error of standard deviation
    # ESTIMATE_ERROR_MAX x (100 - skill) / 100 (capped at 2 deviations), the same every time for the same GM and prospect.
    ESTIMATE_ERROR_MAX: float = 8.0
    # MOVE_UP_DRAFT: a team wants to move up only for a prospect it would take among those projected before its own
    # pick (any of them: the price stops the dreams), when he scores at least MOVE_UP_MIN_GAIN more than the best one left at its pick.
    MOVE_UP_MIN_GAIN: float = 3.0
    # Plans that may want to move up (a contender plays for now; a PICK_HOARDER GM only moves down).
    MOVE_UP_PLANS: tuple = ("REBUILDER", "MIDDLE", "PLAYOFF")
    # Paying to move up with players (trades/engines/pick_trade_up.py): one player at most this old (a 29+ star is
    # worth less than a top prospect), at least a starter, never worth more than MOVE_UP_MAX_OVERPAY x the pick he buys.
    PICK_PAY_MAX_AGE: int = 28
    MOVE_UP_MAX_OVERPAY: float = 1.35
    # A first of this draft is worth the prospect projected at its slot (the class by potential, his own trade
    # value), not a fixed price per slot: the #1 with a LeBron costs a young 90, a #1 in a weak class much less.
    PICK_VALUE_FROM_PROSPECT: bool = True


@dataclass(frozen=True)
class Positions:
    """Ratings at each role (Giocatore._calibra_e_calcola_posizioni) and the user's role changes (Giocatore.change_role).

    A player's raw score at a role (the role's ability weights) is compared with the players who really play that role:
    z = (raw - mean) / sd from RAW_REFERENCE (measured on the 2002 league, natives only). His rating there is his OVR
    at his original role plus OVR_SPREAD x (z there - z at his original role), so the original role keeps his OVR and
    a big man is no longer rated as a point guard because every player has high IQ and passing numbers."""
    RAW_REFERENCE: dict = field(default_factory=lambda: {"PG": (75.0, 6.24), "SG": (72.2, 6.37), "SF": (71.2, 4.53),
                                                         "PF": (68.7, 6.78), "C": (69.5, 6.98)})
    # Ability weights of each role's raw score (the role's skills).
    ROLE_WEIGHTS: dict = field(default_factory=lambda: {
        'PG': {
            'ball_handling': 0.20, 'passing_vision': 0.20, 'speed': 0.15,
            'passing_accuracy': 0.10, 'shot_iq': 0.10, 'offensive_iq_rating': 0.10, 'perimeter_defense_rating': 0.08,
            'close_shot_rating': 0.05, 'stamina': 0.02
        },
        'SG': {
            'mid_range_shot_rating': 0.20, 'three_point_shot_rating': 0.20, 'close_shot_rating': 0.10,
            'ball_handling': 0.12, 'shot_iq': 0.10, 'perimeter_defense_rating': 0.08,
            'speed': 0.10, 'offensive_iq_rating': 0.05, 'defensive_iq_rating': 0.05
        },
        'SF': {
            'mid_range_shot_rating': 0.15, 'close_shot_rating': 0.12, 'perimeter_defense_rating': 0.12,
            'strength': 0.10, 'speed': 0.10, 'shot_iq': 0.10, 'defensive_iq_rating': 0.11,
            'three_point_shot_rating': 0.10, 'defensive_rebound_rating': 0.05, 'ball_handling': 0.05
        },
        'PF': {
            'strength': 0.18, 'interior_defense_rating': 0.15, 'defensive_rebound_rating': 0.13,
            'close_shot_rating': 0.12, 'mid_range_shot_rating': 0.08, 'block_rating': 0.08,
            'offensive_rebound_rating': 0.08, 'post_control_rating': 0.10, 'defensive_iq_rating': 0.08
        },
        'C': {
            'interior_defense_rating': 0.20, 'strength': 0.20, 'block_rating': 0.12,
            'defensive_rebound_rating': 0.12, 'offensive_rebound_rating': 0.10,
            'close_shot_rating': 0.08, 'post_control_rating': 0.10, 'defensive_iq_rating': 0.08
        }
    })
    OVR_SPREAD: float = 6.4
    RATING_MIN: int = 25
    # A role change sets the OVR to the rating at the new role, but never more than this above his original OVR.
    ROLE_CHANGE_MAX_GAIN: int = 2


@dataclass(frozen=True)
class League:
    """Leagues and saves (core/league/). Old saves (made before league files) store only team names."""
    # Team name stored in an old save -> its franchise id (the 2002 league, plus old aliases). The only real-name
    # table in shipped code: old saves need it to find their franchises (scripts/check_real_names.py whitelists it).
    LEGACY_TEAM_IDS: dict = field(default_factory=lambda: {
        "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Charlotte Bobcats": "CHA",
        "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL",
        "Denver Nuggets": "DEN", "Detroit Pistons": "DET", "Golden State Warriors": "GSW",
        "Houston Rockets": "HOU", "Indiana Pacers": "IND", "LA Clippers": "LAC",
        "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
        "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Jersey Nets": "NJN",
        "New Orleans Hornets": "NOH", "New York Knicks": "NYK", "Orlando Magic": "ORL",
        "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHO", "Portland Trail Blazers": "POR",
        "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Seattle SuperSonics": "SEA",
        "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
        "Los Angeles Clippers": "LAC",
    })
    # League file checks (core/league/schema.py::validate_league): a mod outside these limits is refused with
    # plain-English errors instead of crashing mid-season.
    PLAYER_RATING_RANGE: tuple = (1, 99)      # overall and potential
    PLAYER_SKILL_RANGE: tuple = (0, 100)      # every ability and tendency
    PLAYER_AGE_RANGE: tuple = (15, 50)
    # Fewest players a team may start with: the hard floor the game ever plays a roster at
    # (OFFSEASON.TRADE_ROSTER_MIN_SIZE); free agency and cut-down day then fill rosters up to ROSTER_SIZE_MIN.
    MIN_ROSTER_SIZE: int = 10
    # Season 1 rookies when the league has no draft file for its starting year (league files carry no draft year):
    # players this young in their first year on the team (main.tag_season1_rookies). They play for Rookie of the Year.
    SEASON1_ROOKIE_MAX_AGE: int = 22
    SEASON1_ROOKIE_MAX_YEARS_ON_TEAM: int = 1

@dataclass(frozen=True)
class Saves:
    """Save slots (core/save_store.py, core/save_manager.py, launcher close)."""
    # A file move that fails with PermissionError (Windows antivirus/indexer holding a fresh file) is retried.
    FILE_RETRY_COUNT: int = 5
    FILE_RETRY_DELAY_S: float = 0.2
    # Window close: wait this long for running game requests (a sim day...) before the close save.
    CLOSE_WAIT_TIMEOUT_S: float = 20.0
    # The close save itself: past this the game exits anyway and the slot keeps its previous good save.
    CLOSE_SAVE_TIMEOUT_S: float = 60.0

@dataclass(frozen=True)
class LiveSim:
    """Live day-by-day simulation runs (server.py run flag)."""
    # A run with no sim-day request for this long (window reloaded mid-run) no longer locks the game routes.
    RUN_STALE_S: float = 30.0

@dataclass(frozen=True)
class News:
    """League news (core/news_generator.py): how many items are kept and what makes a story big.
    Tiers: 3 = big (top stories, dashboard headlines), 2 = medium, 1 = minor (folded in the feed)."""
    MAX_ITEMS: int = 1500
    # A story about the user's team is shown this many tiers higher (applied when the feed is read).
    USER_TEAM_TIER_BONUS: int = 1
    # Trade: tier from the best player moved (OVR).
    TRADE_BIG_OVR: int = 84
    TRADE_MEDIUM_OVR: int = 77
    # Injury: reported from INJURY_MIN_DAYS out. Big = a star out long; medium = a star, or anyone out long.
    INJURY_MIN_DAYS: int = 14   # injury lengths are calendar days (CONFIG.INJURIES)
    INJURY_LONG_DAYS: int = 42
    INJURY_STAR_OVR: int = 82
    # Single-game scoring: medium from PERF_POINTS, big from PERF_BIG_POINTS.
    PERF_POINTS: int = 50
    PERF_BIG_POINTS: int = 60
    # Signing / extension: big from this OVR when the caller knows it (else a star signing is medium).
    SIGNING_BIG_OVR: int = 84
    # Rumors about unhappy players: checked every RUMOR_INTERVAL_DAYS in the regular season. A player at or
    # under RUMOR_MORALE_MAX with at least RUMOR_MIN_OVR leaks with RUMOR_CHANCE; one rumor per player per season,
    # and only a team's best unhappy player is a candidate at each check.
    RUMOR_INTERVAL_DAYS: int = 7
    RUMOR_MORALE_MAX: int = 50
    RUMOR_MIN_OVR: int = 78
    RUMOR_CHANCE: float = 0.15
    RUMOR_BIG_OVR: int = 85
    # Rivalry game stories: regular season only, at most this many per pair of teams per season (in a long save
    # most pairs turn heated and rivalry stories were 67% of the feed).
    RIVALRY_MAX_PER_PAIR_SEASON: int = 1
    # A rivalry game makes the news from this intensity ("heated", RivalryTracker levels). At 30 a 30-season save had
    # 163 of 435 pairs telling a story every season (50% of the feed).
    RIVALRY_NEWS_MIN_INTENSITY: float = 50.0

@dataclass(frozen=True)
class TradeRequests:
    """Trade requests (core/front_office/trade_requests.py): a saved frustration meter per player, 0-100.

    Every TICK_DAYS of the regular season a player who is "stuck" (morale under UNHAPPY_MORALE on a team that is
    losing after MIN_GAMES, or rebuilding, with no young future) gains RISE_PER_TICK. Otherwise he loses
    FALL_PER_TICK when he is happy (HAPPY_MORALE) or the team wins (WINNING_WIN_PCT), DRIFT_PER_TICK when neither.
    At season end: +MISSED_PLAYOFFS_BUMP or -PLAYOFFS_RELIEF. The meter is not reset by the new season.
    At REQUEST_AT a player of OVR >= ovr_at(REQUEST_MIN_OVR_OLD) asks to be traded; the request holds until he is
    traded or the meter falls under WITHDRAW_BELOW. Under that line a player at WALK_FRUSTRATION refuses to re-sign.
    Target: about one full bad season to reach REQUEST_AT, half a season is not enough."""
    TICK_DAYS: int = 7
    UNHAPPY_MORALE: int = 50
    HAPPY_MORALE: int = 65
    LOSING_WIN_PCT: float = 0.45
    WINNING_WIN_PCT: float = 0.55
    MIN_GAMES: int = 15
    RISE_PER_TICK: float = 5.0
    FALL_PER_TICK: float = 4.0
    DRIFT_PER_TICK: float = 1.0
    MISSED_PLAYOFFS_BUMP: float = 15.0
    PLAYOFFS_RELIEF: float = 20.0
    REQUEST_AT: float = 100.0
    WITHDRAW_BELOW: float = 40.0
    REQUEST_MIN_OVR_OLD: int = 84      # 2002 scale, mapped by EraLines.ovr_at (about 86 in an inflated league)
    WALK_FRUSTRATION: float = 100.0
    # A team getting a player who asked out may send a starter plus this many picks (TRADES.STARTER_SWAP_MAX_PICKS
    # keeps a plain swap of two starters at one pick): the usual price of a star who wants out, up to three firsts.
    STARTER_SWAP_MAX_PICKS: int = 3   # as many as a bid may carry (_build_bid_for_player stops at 3 picks)
    # What a player who asked out is worth to the team he wants to leave (TradeFinder.get_strategic_value): it has
    # lost its leverage, so its price, its auction minimum and the bids it waits for all come down. Others value him
    # as before.
    OWN_VALUE_SHARE: float = 0.75
    # ...and it keeps falling while he waits: OWN_VALUE_DECAY_PER_WEEK per weekly check with the request open, down to
    # OWN_VALUE_FLOOR. A young star nobody can pay at first goes in the end for the best package on the market.
    OWN_VALUE_DECAY_PER_WEEK: float = 0.02
    OWN_VALUE_FLOOR: float = 0.40
    # Assets a bid for a player who asked out may hold (TradeFinder._build_bid_for_player; others stop at 4): a young
    # star asking out fetches two or three players and several firsts.
    BID_MAX_ASSETS: int = 6

@dataclass(frozen=True)
class Awards:
    """Season award rules (main.Tournament._calcola_*)."""
    # Most Improved: a real role now (MIP_MIN_MPG minutes a game) and a real season before (MIP_PREV_MIN_GP games);
    # never the MVP or a rookie. It went to the MVP in season 1 and often to bench players whose raw PTS+REB+AST
    # jumped from a few minutes a game.
    MIP_MIN_MPG: float = 24.0
    MIP_PREV_MIN_GP: int = 40
    # Defensive Player of the Year (main.Tournament._calcola_defensive_player_of_the_year): stocks and defensive
    # rebounds per game, the team's record (WIN_BASE + win% x WIN_WEIGHT) and its points allowed against the league
    # (+-1% of points allowed = +-TEAM_DEFENSE_WEIGHT %), voter fatigue like the MVP. Steals 2.2 / blocks 2.5 /
    # rebounds 0.5 with no fatigue and a +-4% record: one center won 14 in a row, twice on a .500 team. Then steals
    # 3.0 / blocks 2.0 on 70% of all rebounds: a 4-block center never won in 25 seasons. The season's MVP gets
    # MVP_SHARE of his score: voters spread the awards (MVP and DPOY went to one player in 6 of 25 seasons).
    DPOY_STEAL_WEIGHT: float = 2.5
    DPOY_BLOCK_WEIGHT: float = 2.5
    DPOY_DREB_WEIGHT: float = 0.25
    DPOY_WIN_BASE: float = 0.75
    DPOY_WIN_WEIGHT: float = 0.5
    DPOY_TEAM_DEFENSE_WEIGHT: float = 2.0
    DPOY_FATIGUE_REPEAT: float = 0.08
    DPOY_FATIGUE_THREE_PEAT: float = 0.10
    DPOY_FATIGUE_CAREER_EACH: float = 0.015
    DPOY_FATIGUE_CAREER_MAX: float = 0.06
    DPOY_FATIGUE_FLOOR: float = 0.75
    DPOY_MVP_SHARE: float = 0.90

@dataclass(frozen=True)
class Config:
    FATIGUE: Fatigue = Fatigue()
    SHOOTING: Shooting = Shooting()
    FOULS: Fouls = Fouls()
    EVENTS: Events = Events()
    ASSIST: Assist = Assist()
    PLAYMAKING: Playmaking = Playmaking()
    PROGRESSION: Progression = Progression()
    SIM: Simulation = Simulation()
    COACHING: Coaching = Coaching()
    OFFSEASON: Offseason = Offseason() 
    ECONOMY: Economy = Economy()
    INJURIES: Injuries = Injuries()
    HOMECOURT: HomeCourt = HomeCourt()
    COACHINGSTYLES: CoachingStyles = CoachingStyles()
    COACHINGTACTICS: CoachingTactics = CoachingTactics()
    ROOKIEGEN: RookieGeneration = RookieGeneration()
    SYNTHETICSTAMINA: SyntheticStamina = SyntheticStamina()
    GEO: GeoConfig = GeoConfig()
    DASHBOARD: Dashboard = Dashboard()
    HISTORY: History = History()
    END_SEASON: EndSeason = EndSeason()
    SCOUTING_MATCHUPS: ScoutingMatchups = ScoutingMatchups()
    ANALYTICS: Analytics = Analytics()
    DATABASE: Database = Database()
    TEAM_CARD: TeamCard = TeamCard()
    ALL_STAR: AllStar = AllStar()
    ERA: Era = Era()
    FRONT_OFFICE: FrontOffice = FrontOffice()
    TRADES: Trades = Trades()
    TRADE_REQUESTS: TradeRequests = TradeRequests()
    AWARDS: Awards = Awards()
    CONTRACTS: Contracts = Contracts()
    DRAFT_AI: DraftAI = DraftAI()
    POSITIONS: Positions = Positions()
    LEAGUE: League = League()
    SAVES: Saves = Saves()
    NEWS: News = News()
    LIVE_SIM: LiveSim = LiveSim()

CONFIG = Config()
# --- Helpers reading CONFIG (no data here: every value lives in the sections above) ---

def normalize_owner_personality(personality):
    """Returns the canonical owner personality (CONFIG.ECONOMY.OWNER_TYPES), or None if unknown/empty."""
    if not personality:
        return None
    eco = CONFIG.ECONOMY
    p = eco.OWNER_TYPE_ALIASES.get(personality, personality)
    return p if p in eco.OWNER_TYPES else None

def owner_spending_tier(personality) -> str:
    """'low' | 'mid' | 'high' spending attitude of an owner personality (unknown -> 'mid')."""
    return CONFIG.ECONOMY.OWNER_SPENDING_TIER.get(normalize_owner_personality(personality), "mid")
