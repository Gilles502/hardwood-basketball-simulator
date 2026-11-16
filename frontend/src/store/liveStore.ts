// Live franchise summary for the sidebar and Dashboard (see /api/dashboard/summary).
import { create } from 'zustand';
import type { StandingRow } from '../utils/standings';

export interface NextGameInfo {
  game_id: string;
  date: string;
  day_index: number;
  opponent: string;
  is_home: boolean;
  opponent_record: string | null;
  opponent_rank: number | null;
  opponent_conference: string | null;
}

export interface LastResultInfo {
  opponent: string;
  date: string;
  is_home: boolean;
  won: boolean;
  points_for: number;
  points_against: number;
}

export interface TeamFormInfo {
  streak: string;
  streak_len: number;
  streak_type: 'W' | 'L' | null;
  l10: string;
  l10_wins: number;
  home: string;
  away: string;
  tag: 'hot' | 'cold' | null;
}

export interface InjuryInfo {
  name: string;
  days: number;
  ovr: number;
}

export interface DashboardSummary {
  date: string | null;
  day_index: number;
  total_days: number;
  team: { name: string; record: string; conference: 'West' | 'East' | null; conf_rank: number | null } | null;
  next_game: NextGameInfo | null;
  last_result: LastResultInfo | null;
  form: TeamFormInfo | null;
  standings: { west: StandingRow[]; east: StandingRow[] };
  attention: {
    injuries: InjuryInfo[];
    trade_offers: number;
    board_concern: boolean;
    pending_step: string;
    /** Big news stories the user has not opened the News tab for yet. */
    news_unread?: number;
  };
  updated_at: number;
}

export type LiveStatus = 'idle' | 'live' | 'offline';

interface LiveState {
  summary: DashboardSummary | null;
  status: LiveStatus;
  lastUpdated: number | null;
  refresh: () => Promise<void>;
}

let inFlight = false;

/** A request that hangs must not block every later refresh: give up and let the next poll retry. */
const REFRESH_TIMEOUT_MS = 8000;

export const useLiveStore = create<LiveState>((set) => ({
  summary: null,
  status: 'idle',
  lastUpdated: null,

  refresh: async () => {
    if (inFlight) return;
    inFlight = true;
    try {
      const response = await fetch(`/api/dashboard/summary?_t=${Date.now()}`, { signal: AbortSignal.timeout(REFRESH_TIMEOUT_MS) });
      if (!response.ok) throw new Error(`summary request failed (${response.status})`);
      const data = (await response.json()) as DashboardSummary;
      set({ summary: data, status: 'live', lastUpdated: Date.now() });
    } catch {
      // Keep the last good summary on screen; the Live dot tells the player it is stale.
      set({ status: 'offline' });
    } finally {
      inFlight = false;
    }
  },
}));
