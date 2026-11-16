// Live regular-season run: targets and stop rules (the loop itself lives in store/leagueStore.ts).

export type SimTarget =
  | { kind: 'days'; count: number }
  | { kind: 'next_game' }
  | { kind: 'deadline' }
  | { kind: 'all_star' }
  | { kind: 'season_end' }
  | { kind: 'day'; dayIndex: number }; // run until current_day === dayIndex

export interface SimRun {
  target: SimTarget;
  label: string;
  fromDay: number;
  targetDay: number | null;
  daysDone: number;
  stopRequested: boolean;
  error: string | null;
}

export interface SimMilestones {
  trade_deadline_day: number | null;
  trade_deadline_done: boolean;
  all_star_day: number | null;
}

const REGULAR_SEASON = ['PRE_SEASON', 'ALL_STAR_BREAK'];

export function targetLabel(t: SimTarget): string {
  switch (t.kind) {
    case 'days': return t.count === 1 ? '1 day' : `${t.count} days`;
    case 'next_game': return 'Next game';
    case 'deadline': return 'Trade deadline';
    case 'all_star': return 'All-Star break';
    case 'season_end': return 'End of regular season';
    case 'day': return 'Calendar day';
  }
}

/** Day the run lands on, for the progress bar; null when it is not known in advance. */
export function targetDay(t: SimTarget, data: any): number | null {
  const cur = data?.current_day ?? 0;
  const total = data?.total_calendar_days ?? null;
  const m: SimMilestones | undefined = data?.sim_milestones;
  switch (t.kind) {
    case 'days': return total === null ? cur + t.count : Math.min(cur + t.count, total);
    case 'next_game': return null;
    case 'deadline': return m?.trade_deadline_day ?? null;
    case 'all_star': return m?.all_star_day ?? null;
    case 'season_end': return total;
    case 'day': return t.dayIndex;
  }
}

/** The league is out of the regular season (or the calendar is over): every run ends. */
export function regularSeasonOver(data: any): boolean {
  if (!data) return true;
  if (!REGULAR_SEASON.includes(data.league_state)) return true;
  const total = data.total_calendar_days;
  return typeof total === 'number' && (data.current_day ?? 0) >= total;
}

/** Checked before each day request: true means the run has nothing left to do. */
export function reachedBeforeDay(t: SimTarget, data: any, daysDone: number): boolean {
  if (regularSeasonOver(data)) return true;
  const cur = data.current_day ?? 0;
  const m: SimMilestones | undefined = data.sim_milestones;
  switch (t.kind) {
    case 'days': return daysDone >= t.count;
    case 'next_game': return false;
    case 'deadline':
      // Today = the deadline day is the last day the user can still trade.
      return !m || m.trade_deadline_day === null || m.trade_deadline_done || cur >= m.trade_deadline_day;
    case 'all_star': return data.league_state === 'ALL_STAR_BREAK';
    case 'season_end': return false;
    case 'day': return cur >= t.dayIndex;
  }
}

/** Checked after each day response: the response itself ends the run. */
export function reachedAfterDay(t: SimTarget, dayResult: any, userTeam: string | null): boolean {
  if (!dayResult || dayResult.error || dayResult.completed) return true;
  if (dayResult.league_state && !REGULAR_SEASON.includes(dayResult.league_state)) return true;
  if (t.kind === 'next_game') {
    return !!userTeam && !!dayResult.simulated_day?.games?.some(
      (g: any) => g.home_team === userTeam || g.away_team === userTeam);
  }
  if (t.kind === 'all_star') return dayResult.league_state === 'ALL_STAR_BREAK';
  return false;
}
