// Play-by-play helpers for Courtside Live: live box score, readable play lines and the game-flow series.

export interface PlayEvent {
  quarter: number;
  time: string;
  event_type: 'score' | 'miss' | 'block' | 'steal' | 'rebound' | 'turnover' | 'foul' | string;
  team: string;
  player: string;
  detail?: string;
  assist_by?: string;
  highlight_tag?: string | null;
  momentum?: number;
  run_info?: string | null;
  commentary?: string;
  score?: Record<string, number>;
}

/** Older logs can mix plain text lines in with the play objects. */
export type PlayLogEntry = PlayEvent | string;

export interface LivePlayerStats {
  name: string;
  team: string;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  to: number;
  fgm: number;
  fga: number;
  tpm: number;
  tpa: number;
  ftm: number;
  fta: number;
}

export const isPlay = (entry: PlayLogEntry | undefined): entry is PlayEvent => typeof entry === 'object' && entry !== null;

const isThree = (detail = '') => detail.includes('3PT') || detail.includes('3-pointer');
/** The engine sometimes names the scorer as his own assister; that is not an assist. */
const assistOf = (play: PlayEvent) => (play.assist_by && play.assist_by !== play.player ? play.assist_by : '');
const freeThrows = (detail = '') => {
  const match = detail.match(/Free Throws (\d+)\/(\d+)/);
  return match ? { made: Number(match[1]), attempts: Number(match[2]) } : null;
};

export const computeLiveBoxScore = (plays: PlayLogEntry[]): LivePlayerStats[] => {
  const stats: Record<string, LivePlayerStats> = {};
  const get = (name: string, team: string) => (stats[name] ??= {
    name, team, pts: 0, reb: 0, ast: 0, stl: 0, blk: 0, to: 0, fgm: 0, fga: 0, tpm: 0, tpa: 0, ftm: 0, fta: 0,
  });

  plays.forEach((play) => {
    if (!isPlay(play) || !play.player) return;
    const p = get(play.player, play.team);
    switch (play.event_type) {
      case 'score': {
        const ft = freeThrows(play.detail);
        if (ft) {
          p.ftm += ft.made; p.fta += ft.attempts; p.pts += ft.made;
          break;
        }
        const three = isThree(play.detail);
        p.fgm += 1; p.fga += 1; p.pts += three ? 3 : 2;
        if (three) { p.tpm += 1; p.tpa += 1; }
        const assist = assistOf(play);
        if (assist) get(assist, play.team).ast += 1;
        break;
      }
      case 'miss':
        p.fga += 1;
        if (isThree(play.detail)) p.tpa += 1;
        break;
      case 'rebound': p.reb += 1; break;
      case 'steal': p.stl += 1; break;
      case 'block': p.blk += 1; break;
      case 'turnover': p.to += 1; break;
    }
  });
  return Object.values(stats);
};

export const teamTotals = (players: LivePlayerStats[]) => players.reduce(
  (t, p) => ({
    pts: t.pts + p.pts, reb: t.reb + p.reb, ast: t.ast + p.ast, stl: t.stl + p.stl, blk: t.blk + p.blk, to: t.to + p.to,
    fgm: t.fgm + p.fgm, fga: t.fga + p.fga, tpm: t.tpm + p.tpm, tpa: t.tpa + p.tpa, ftm: t.ftm + p.ftm, fta: t.fta + p.fta,
  }),
  { pts: 0, reb: 0, ast: 0, stl: 0, blk: 0, to: 0, fgm: 0, fga: 0, tpm: 0, tpa: 0, ftm: 0, fta: 0 },
);

/** Scorer's-sheet wording of one play, e.g. "Adam Smith 3-pointer (assist Ben Jones)". */
export const playLine = (play: PlayEvent) => {
  const detail = play.detail ?? '';
  const assister = assistOf(play);
  const assist = assister ? ` (assist ${assister})` : '';
  switch (play.event_type) {
    case 'score': {
      const ft = freeThrows(detail);
      if (ft) return `${play.player} free throws ${ft.made} of ${ft.attempts}`;
      return `${play.player} ${isThree(detail) ? '3-pointer' : 'basket'}${assist}`;
    }
    case 'miss':
      return `${play.player} misses ${detail.replace(/^Missed\s*/i, '').replace('Jumpshot', 'jump shot').toLowerCase() || 'shot'}`;
    case 'block': {
      const victim = detail.match(/by (.+)$/)?.[1];
      return victim ? `${play.player} blocks ${victim}` : `${play.player} block`;
    }
    case 'steal': {
      const victim = detail.match(/from (.+)$/)?.[1];
      return victim ? `${play.player} steals from ${victim}` : `${play.player} steal`;
    }
    case 'turnover': return `${play.player} turnover`;
    case 'rebound': return `${play.player} ${detail.toLowerCase() || 'rebound'}`;
    default: return detail ? `${play.player} – ${detail}` : play.player;
  }
};

const HIGHLIGHT_LABELS: Record<string, string> = {
  clutch_shot: 'Clutch', deep_three: 'Deep three', poster_dunk: 'Dunk', fastbreak: 'Fast break', monster_block: 'Block',
};

export const highlightLabel = (tag: string) =>
  HIGHLIGHT_LABELS[tag] ?? tag.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

const QUARTER_SECONDS = 12 * 60;
const OVERTIME_SECONDS = 5 * 60;

const clockSeconds = (time: string) => {
  const [m, s] = time.split(':').map(Number);
  return (m || 0) * 60 + (s || 0);
};

/** Seconds played from tip-off at this play. */
export const elapsedSeconds = (play: PlayEvent) => {
  const left = clockSeconds(play.time);
  if (play.quarter <= 4) return (play.quarter - 1) * QUARTER_SECONDS + (QUARTER_SECONDS - left);
  return 4 * QUARTER_SECONDS + (play.quarter - 5) * OVERTIME_SECONDS + (OVERTIME_SECONDS - left);
};

/** Length of a game that reaches `quarter` periods, in seconds. */
export const gameSeconds = (quarter: number) =>
  4 * QUARTER_SECONDS + Math.max(0, quarter - 4) * OVERTIME_SECONDS;

export const periodLabel = (quarter: number) => (quarter <= 4 ? `Q${quarter}` : `OT${quarter - 4}`);
