import { formatGameDate } from './format';

export interface TradeSide {
  team: string;
  gets: string[];
  gm?: string | null;
  plan?: string | null;
  reasons?: string[];
}

export interface SeriesGame {
  game: number;
  home: string;
  home_score: number;
  away: string;
  away_score: number;
}

/** A league news item as /api/news sends it (tier already raised for the user's team). */
export interface NewsItem {
  id: number;
  kind: string;
  tier: number;
  title: string;
  body: string;
  teams: string[];
  players: string[];
  season: number;
  day: number | null;
  date: string;
  phase: string;
  mine: boolean;
  unread: boolean;
  details: { sides?: TradeSide[]; games?: SeriesGame[]; round?: string; contract?: string };
}

const KIND_LABEL: Record<string, string> = {
  trade: 'Trade', injury: 'Injury', signing: 'Signing', cut: 'Waived', extension: 'Extension',
  free_agency: 'Free agency', draft: 'Draft', performance: 'Big game', playoffs: 'Playoffs', champion: 'Champions',
  firing: 'Fired', hiring: 'Hired', rumor: 'Rumor', award: 'Award', standings: 'Standings', rivalry: 'Rivalry',
  league: 'League',
};
const ALERT_KINDS = new Set(['injury', 'firing']);

export const kindLabel = (kind: string) => KIND_LABEL[kind] ?? 'League';

export const kindClass = (item: Pick<NewsItem, 'kind' | 'mine' | 'tier'>) =>
  `nw-kind${item.mine ? ' is-mine' : ALERT_KINDS.has(item.kind) ? ' is-alert' : item.tier <= 1 ? ' is-minor' : ''}`;

/** "Day 47 · Sun 12 Jan 2003" in the regular season, else the phase ("Playoffs · Season 3"). */
export const whenLabel = (item: Pick<NewsItem, 'day' | 'date' | 'phase' | 'season'>) =>
  item.day !== null && item.day !== undefined
    ? `Day ${item.day + 1}${item.date ? ` · ${formatGameDate(item.date)}` : ''}`
    : `${item.phase || 'League'} · Season ${item.season}`;
