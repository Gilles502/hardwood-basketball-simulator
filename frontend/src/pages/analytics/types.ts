// Payloads of /api/analytics/* (core/analytics_view.py). Stat values are numbers or null when undefined.

export type Stats = Record<string, number | null>;

export interface AnalyticsMeta {
  season: string | null;
  games: number;
  tint_top: number;
  tint_bottom: number;
  split_tint: number;
  qualify_gp_share: number;
  qualify_mpg: number;
  oreb_share: number;
  close_margin: number;
  fta_weight: number;
  per_avg: number;
  leaders_per_tile: number;
  user_team: string | null;
}

export interface Exponent {
  value: number;
  rmse: number | null;
  fitted: boolean;
}

export interface PlayerRow {
  name: string;
  team: string;
  teams: string[];
  pos: string | null;
  gp: number;
  team_gp: number;
  qualified: boolean;
  in_league: boolean;
  is_user_team: boolean;
  s: Stats;
  pct: Stats;
}

export interface PlayersPayload {
  meta: AnalyticsMeta;
  players: PlayerRow[];
}

export interface TeamRow {
  name: string;
  conference: string | null;
  is_user_team: boolean;
  w: number;
  l: number;
  gp: number;
  s: Stats;
  pct: Stats;
  quarters: (number | null)[];
  home: [number, number];
  away: [number, number];
  close: [number, number];
}

export interface TeamsPayload {
  meta: AnalyticsMeta;
  exponent: Exponent;
  teams: TeamRow[];
}

export interface MapTeam {
  name: string;
  ortg: number | null;
  drtg: number | null;
  net: number | null;
  w: number;
  exp_w: number | null;
  luck: number | null;
  is_user_team: boolean;
}

export interface MonthPulse {
  month: string;
  label: string;
  games: number;
  ppg: number | null;
  pace: number | null;
  efg: number | null;
  tpa_rate: number | null;
  home_win_pct: number | null;
}

export interface LeaguePayload {
  meta: AnalyticsMeta;
  exponent: Exponent;
  league_avg: { ortg: number | null; drtg: number | null };
  teams: MapTeam[];
  months: MonthPulse[];
  baseline: Record<'ppg' | 'ortg' | 'pace' | 'efg' | 'ts' | 'tov_pct' | 'tpa_rate' | 'home_win_pct', number | null>;
}

export interface SplitRow {
  label: string;
  gp: number;
  min: number | null;
  pts: number | null;
  reb: number | null;
  ast: number | null;
  ts_pct: number | null;
  pm: number | null;
  w: number;
  l: number;
}

export interface LogRow {
  game_id: string;
  date: string;
  home: boolean;
  opp: string;
  win: boolean;
  score_for: number;
  score_against: number;
  b2b: boolean;
  dnp: boolean;
  min: number | null;
  pts: number | null;
  reb: number | null;
  ast: number | null;
  stl: number | null;
  blk: number | null;
  to: number | null;
  pf: number | null;
  fgm: number | null;
  fga: number | null;
  tpm: number | null;
  tpa: number | null;
  ftm: number | null;
  fta: number | null;
  pm: number | null;
  gmsc: number | null;
}

export interface SeasonHigh {
  stat: string;
  label: string;
  value: number;
  opp: string;
  home: boolean;
  date: string;
  game_id: string;
}

export interface SplitsPayload {
  meta: AnalyticsMeta;
  kind: 'player' | 'team';
  name: string;
  team: string;
  pos: string | null;
  season_line: SplitRow;
  splits: SplitRow[];
  months: SplitRow[];
  opponents: SplitRow[];
  quarters: (number | null)[] | null;
  highs: SeasonHigh[];
  log: LogRow[];
}

export type SplitsTarget = { kind: 'player' | 'team'; name: string };
