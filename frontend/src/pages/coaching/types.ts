// Coaching page data, from /api/coaching/state and /api/coaching/system-fit (server.py serialize_coach).

export interface RosterFit {
  fit_score: number;
  grade?: string;
  rating: string;
  net_impact?: string;
}

export interface Coach {
  nome: string;
  stile_gioco: string;
  ovr_offensivo: number;
  ovr_difensivo: number;
  player_development?: number;
  tactical_acumen?: number;
  discipline_culture?: number;
  ovr_totale: number;
  eta: number;
  potenziale: number;
  contratto_anni_rimanenti: number;
  contratto_totale_anni?: number;
  job_security: number;
  job_security_label?: string;
  years_with_current_team?: number;
  level: number;
  badges: Record<string, number>;
  badge_points: number;
  salario: number;
  historical_wins: number;
  historical_losses: number;
  career_win_pct?: number;
  playoff_appearances?: number;
  championships: number;
  coty_awards?: number;
  specialization?: string;
  offensive_system?: string;
  defensive_scheme?: string;
  preferred_pace?: string;
  roster_fit?: RosterFit;
  /** Only on your coach: the yearly salary he asks for an extension. */
  extension_ask?: number;
  /** Only on market coaches: the lowest yearly salary he signs for. */
  min_salary?: number;
}

export interface LeagueCoach extends Coach {
  team_name: string;
  team_record: string;
  team_ovr?: number;
}

export interface CoachingState {
  current_coach: Coach | null;
  unemployed_coaches: Coach[];
  league_coaches?: LeagueCoach[];
  team_name: string;
}

export interface PlayerFit {
  player_id: string;
  name: string;
  position: string;
  ovr: number;
  fit_score: number;
  badge: 'Ideal Fit' | 'Solid Fit' | 'Tactical Friction' | 'Severe Mismatch' | string;
  stats_preview?: { '3PT'?: number; SPD?: number; DEF?: number };
  notes?: string;
}

export interface SystemFit {
  fit_score: number;
  grade: string;
  rating: string;
  net_impact: string;
  net_rating_mod: number;
  offensive_fit_score: number;
  defensive_fit_score: number;
  offensive_system: string;
  defensive_scheme: string;
  preferred_pace: string;
  synergies: string[];
  red_flags: string[];
  player_fits: PlayerFit[];
}

export type Tone = 'ok' | 'info' | 'warn' | 'bad';

/** Coach badges that change something in a game (core/game_engine.py); others in the save have no effect. */
export const COACH_BADGES: { key: string; label: string; effect: string }[] = [
  { key: 'Defense Guru', label: 'Defense Guru', effect: '+1 interior and perimeter defense per level' },
  { key: 'Tactician', label: 'Tactician', effect: '+1 three-point and mid-range shooting per level' },
  { key: 'Rookie Developer', label: 'Rookie Developer', effect: '+1 offensive, defensive and shot IQ per level for players 23 and under' },
  { key: 'Fitness Specialist', label: 'Fitness Specialist', effect: '+2 stamina per level' },
  { key: 'Motivator', label: 'Motivator', effect: '+5 morale per level' },
];

export const BADGE_MAX_LEVEL = 3;

export const fitGrade = (fit?: RosterFit | null): string => {
  if (!fit) return '—';
  if (fit.grade) return fit.grade;
  const s = fit.fit_score;
  return s >= 80 ? 'A' : s >= 70 ? 'B' : s >= 60 ? 'C' : s >= 50 ? 'D' : 'F';
};

export const scoreTone = (score: number): Tone => (score >= 80 ? 'ok' : score >= 65 ? 'info' : score >= 50 ? 'warn' : 'bad');

export const gradeTone = (grade: string): Tone => {
  const g = grade.charAt(0);
  return g === 'S' || g === 'A' ? 'ok' : g === 'B' ? 'info' : g === 'C' ? 'warn' : 'bad';
};

export const securityTone = (security: number): Tone =>
  (security >= 65 ? 'ok' : security >= 45 ? 'info' : security >= 28 ? 'warn' : 'bad');

export const playerFitTone = (badge: string): Tone =>
  (badge === 'Ideal Fit' ? 'ok' : badge === 'Solid Fit' ? 'info' : badge === 'Tactical Friction' ? 'warn' : 'bad');

export const money = (millions: number) => `$${millions.toFixed(1)}M`;

/** Lowest salary a market coach accepts, and the one the offer form starts from. */
export const marketAsk = (c: Coach) => Math.max(c.salario, c.min_salary ?? 0);
