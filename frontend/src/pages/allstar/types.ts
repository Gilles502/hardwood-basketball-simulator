// Shape of GET /api/allstar[?season=n] (core/all_star_view.py). Old names-only seasons leave stats and team null,
// and any section can be null on its own.
import type { EventId } from '../../utils/allStarReveal';

export type { EventId };

export type Status = 'upcoming' | 'played' | 'not_recorded';

/** A season line: All-Star selections, Rookie Challenge rosters. */
export interface SeasonLine {
  name: string;
  team: string | null;
  pos: string | null;
  ppg: number | null;
  rpg: number | null;
  apg: number | null;
  tp_pct?: number | null;
  is_user: boolean;
}

export interface BoxLine {
  name: string;
  team?: string | null;
  pts: number | null;
  reb: number | null;
  ast: number | null;
  tpm: number | null;
  is_user: boolean;
}

export interface GameSide {
  label: string;
  score: number | null;
  lines: BoxLine[];
}

export interface Mvp {
  name: string;
  team?: string | null;
  label?: string | null;
  pts?: number | null;
  reb?: number | null;
  ast?: number | null;
  tpm?: number | null;
  is_user: boolean;
  fact: string | null;
}

export interface Game {
  sides: GameSide[];
  winner: string | null;
  mvp: Mvp | null;
}

export interface Conference {
  starters?: SeasonLine[];
  reserves?: SeasonLine[];
  left_out?: SeasonLine[];
}

export interface Selections {
  east?: Conference;
  west?: Conference;
}

export interface RookieChallenge {
  rookies?: SeasonLine[];
  sophomores?: SeasonLine[];
  game: Game | null;
}

export interface ThreePoint {
  round1: { name: string; team: string | null; tp_pct: number | null; score: number | null; finalist: boolean; is_user: boolean }[];
  final: { name: string; team: string | null; score: number | null; is_user: boolean }[];
  /** Shoot-off between the tied leaders of the final (winner first); null or missing without a tie. */
  tiebreak?: { name: string; score: number }[] | null;
  winner: string | null;
}

export interface Dunk {
  round1: {
    name: string; team: string | null; dunks: { name: string; score: number | null }[];
    total: number | null; finalist: boolean; is_user: boolean;
  }[];
  final: { name: string; team: string | null; dunk: string | null; score: number | null; is_user: boolean }[];
  /** Dunk-off between the tied leaders of the final (winner first); null or missing without a tie. */
  tiebreak?: { name: string; dunk: string; score: number }[] | null;
  winner: string | null;
}

export interface WeekendEvent {
  id: EventId;
  night: string;
  title: string;
  summary: string | null;
  recorded: boolean;
}

export interface AllStarView {
  season: number;
  label: string | null;
  host: string | null;
  status: Status;
  is_current: boolean;
  /** Names-only data from old history: shown fully revealed, never step by step. */
  legacy: boolean;
  break: { day: number; date: string | null } | null;
  you: { team: string; all_stars: number; entries: string[] } | null;
  events: WeekendEvent[];
  selections: Selections | null;
  rookie_challenge: RookieChallenge | null;
  three_point: ThreePoint | null;
  dunk: Dunk | null;
  game: Game | null;
  seasons: { season: number; label: string | null }[];
}

/** What every stage gets: steps opened so far and the button that opens the next one. */
export interface StageProps {
  step: number;
  onReveal: () => void;
}

/** "24.8", or "—" when the value is missing. */
export const one = (v: number | null | undefined): string => (v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(1));

/** "31", or "—" when the value is missing. */
export const whole = (v: number | null | undefined): string => (v === null || v === undefined || Number.isNaN(v) ? '—' : String(Math.round(v)));
