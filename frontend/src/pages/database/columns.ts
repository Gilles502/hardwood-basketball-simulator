// Stat column sets shared by the player page, Seasons and Stat Finder. Keys are League Analytics' (core/analytics_view).
import type { Column } from '../analytics/StatTable';
import { fmt, fmtSigned } from '../analytics/useAnalyticsData';
import type { Stats } from './types';

export type StatView = 'pg' | 'tot' | '36' | '100' | 'adv';

export const STAT_VIEWS: { id: StatView; label: string }[] = [
  { id: 'pg', label: 'Per game' }, { id: 'tot', label: 'Totals' }, { id: '36', label: 'Per 36' },
  { id: '100', label: 'Per 100' }, { id: 'adv', label: 'Advanced' },
];

/** Views that only seasons with a full box-score line can fill. */
export const FULL_ONLY: StatView[] = ['36', '100', 'adv'];

export interface StatDef { key: string; label: string; digits?: number; signed?: boolean; title?: string }

const counting = (sfx: string, digits: number): StatDef[] =>
  [['pts', 'PTS'], ['reb', 'REB'], ['ast', 'AST'], ['stl', 'STL'], ['blk', 'BLK'], ['to', 'TO']]
    .map(([k, label]) => ({ key: `${k}${sfx}`, label, digits }));

export const STAT_DEFS: Record<StatView, StatDef[]> = {
  pg: [
    { key: 'gp', label: 'GP', digits: 0 }, { key: 'mpg', label: 'MIN' }, ...counting('_pg', 1),
    { key: 'fg_pct', label: 'FG%' }, { key: 'tp_pct', label: '3P%' }, { key: 'ft_pct', label: 'FT%' }, { key: 'ts_pct', label: 'TS%' },
  ],
  tot: [
    { key: 'gp', label: 'GP', digits: 0 }, { key: 'min', label: 'MIN', digits: 0 }, ...counting('_tot', 0),
    { key: 'fgm_tot', label: 'FGM', digits: 0 }, { key: 'fga_tot', label: 'FGA', digits: 0 },
    { key: 'tpm_tot', label: '3PM', digits: 0 }, { key: 'tpa_tot', label: '3PA', digits: 0 },
    { key: 'ftm_tot', label: 'FTM', digits: 0 }, { key: 'fta_tot', label: 'FTA', digits: 0 },
  ],
  '36': [{ key: 'gp', label: 'GP', digits: 0 }, { key: 'mpg', label: 'MIN' }, ...counting('_36', 1)],
  '100': [{ key: 'gp', label: 'GP', digits: 0 }, { key: 'mpg', label: 'MIN' }, ...counting('_100', 1)],
  adv: [
    { key: 'gp', label: 'GP', digits: 0 }, { key: 'mpg', label: 'MIN' },
    { key: 'ts_pct', label: 'TS%' }, { key: 'efg_pct', label: 'eFG%' }, { key: 'two_pct', label: '2P%' },
    { key: 'usg_pct', label: 'USG%', title: 'Share of team plays used while on court' },
    { key: 'ast_pct', label: 'AST%', title: 'Share of teammate baskets he assisted while on court' },
    { key: 'ato', label: 'A/TO', digits: 2 },
    { key: 'per', label: 'PER (est.)', title: 'Hollinger PER, estimated: league average 15' },
    { key: 'gmsc', label: 'GmSc', title: 'Game Score per game' },
    { key: 'pm_pg', label: '+/-', signed: true, title: 'On-court plus/minus per game' },
  ],
};

/** Every stat the Stat Finder can filter or rank on, labelled. */
export const FINDER_STATS: { key: string; label: string }[] = [
  ...['pts', 'reb', 'ast', 'stl', 'blk', 'to'].flatMap((k) => [
    { key: `${k}_pg`, label: `${k.toUpperCase()} per game` }, { key: `${k}_tot`, label: `${k.toUpperCase()} total` },
  ]),
  { key: 'gp', label: 'Games' }, { key: 'mpg', label: 'Minutes per game' },
  { key: 'fg_pct', label: 'FG%' }, { key: 'tp_pct', label: '3P%' }, { key: 'ft_pct', label: 'FT%' },
  { key: 'ts_pct', label: 'TS%' }, { key: 'efg_pct', label: 'eFG%' }, { key: 'usg_pct', label: 'USG%' },
  { key: 'ast_pct', label: 'AST%' }, { key: 'per', label: 'PER (est.)' }, { key: 'gmsc', label: 'Game Score' },
  { key: 'pm_pg', label: '+/- per game' }, { key: 'tpm_tot', label: '3PM total' },
];

export const formatStat = (d: StatDef, v: number | null | undefined): string =>
  d.signed ? fmtSigned(v ?? null, d.digits ?? 1) : fmt(v ?? null, d.digits ?? 1);

/** StatTable columns for one view, reading the stats through `get`. */
export function statColumns<Row>(view: StatView, get: (row: Row) => Stats): Column<Row>[] {
  return STAT_DEFS[view].map((d) => ({
    key: d.key, label: d.label, title: d.title, keep: true,
    value: (row: Row) => get(row)[d.key] ?? null,
    format: (v) => (typeof v === 'number' ? formatStat(d, v) : '—'),
  }));
}

export const money = (salary: number | null, years: number | null): string =>
  salary === null ? '—' : `$${salary.toFixed(1)}M${years ? ` · ${years} yr${years === 1 ? '' : 's'}` : ''}`;
