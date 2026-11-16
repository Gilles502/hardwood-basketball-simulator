// Payloads of /api/database/* (core/database_view.py). A stat a season didn't save is null.
export type Stats = Record<string, number | null>;
export type Status = 'Active' | 'Free agent' | 'Retired' | 'Out of league';
export type Kind = 'rs' | 'po';

export interface Line {
  season: number | null;
  year: number | null;
  team: string | null;
  teams: string[];
  pos: string | null;
  age: number | null;
  ovr: number | null;
  pot: number | null;
  champion: boolean;
  awards: string[];
  gp: number;
  full: boolean;
  est: boolean;
  s: Stats;
}

export interface CareerLine {
  gp: number;
  seasons: number;
  full: boolean;
  est: boolean;
  s: Stats;
}

interface Identity {
  slug: string;
  name: string;
  status: Status;
  team: string | null;
  pos: string | null;
  age: number | null;
  ovr: number | null;
  pot: number | null;
  salary: number | null;
  years: number | null;
  last_year: number | null;
}

export interface DirectoryRow extends Identity {
  seasons: number;
  gp: number;
  pts_pg: number | null;
  reb_pg: number | null;
  ast_pg: number | null;
  titles: number;
  highlights: string[];
}

export interface DirectoryPayload {
  rows: DirectoryRow[];
  total: number;
  page: number;
  pages: number;
  teams: string[];
  counts: Record<Status, number>;
}

export interface Rank { stat: string; rank: number; value: number; team?: string }

export interface PlayerPayload extends Identity {
  season_count: number;
  last_seasons: number;
  retired_year: number | null;
  career: { gp: number; pts_pg: number | null; reb_pg: number | null; ast_pg: number | null; titles: number; all_star: number; awards: Record<string, number> };
  rs: Line[];
  po: Line[];
  career_rs: CareerLine | null;
  career_po: CareerLine | null;
  best: { season: number; year: number | null; pts_pg: number | null; awards: string[] } | null;
  current: Line | null;
  progression: ({ year: number | null; age: number | null; ovr: number | null; pot: number | null; champion: boolean } & Record<string, number | null | boolean>)[];
  awards: { year: number | null; award: string; team: string | null }[];
  titles: { year: number | null; team: string | null }[];
  ranks: { league: Rank[]; franchise: Rank[] };
  missing_years: (number | null)[];
}

export interface SeasonRow { slug: string; name: string; line: Line; qualified?: boolean | null }

export interface SeasonPayload {
  season: number | null;
  year: number | null;
  kind: Kind;
  seasons: { season: number; year: number | null; full: boolean }[];
  full: boolean;
  rows: SeasonRow[];
  leaders: Record<string, { slug: string; name: string; value: number }[]>;
  champion: string | null;
  user_team: string | null;
}

export interface Condition { stat: string; op: '>=' | '<='; value: number | string }

export interface FinderQuery {
  mode?: 'seasons' | 'careers';
  kind?: Kind;
  year_from?: number | string;
  year_to?: number | string;
  age_min?: number | string;
  age_max?: number | string;
  team?: string;
  pos?: string;
  status?: string;
  min_gp?: number | string;
  champion?: boolean;
  award?: string;
  conditions?: Condition[];
  rank_by?: string;
  desc?: boolean;
}

export interface CareerHit {
  slug: string;
  name: string;
  seasons: number;
  first_year: number | null;
  last_year: number | null;
  career: CareerLine;
  titles: number;
  all_star: number;
}

export interface FinderPayload {
  mode: 'seasons' | 'careers';
  kind: Kind;
  rank_by: string;
  desc: boolean;
  rows: (SeasonRow | CareerHit)[];
  total: number;
  note: string | null;
  full_from: number | null;
}

export interface Preset { id: string; label: string; query: FinderQuery }

export interface OpenPlayer { slug: string; name: string }
