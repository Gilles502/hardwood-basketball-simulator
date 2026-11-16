// Pure helpers for the Standings tab: filtering and the merged league table.

export type StandingsFilter = 'all' | 'playoff' | 'play_in' | 'hot' | 'cold';

export interface StandingRow {
  pos: number;
  nome: string;
  v: number;
  s: number;
  pct: number;
  gb: number;
  home: string;
  away: string;
  l10: string;
  streak: string;
  tag: 'hot' | 'cold' | null;
  zone: 'playoff' | 'play_in' | 'out';
}

export function filterRows(rows: StandingRow[], filter: StandingsFilter): StandingRow[] {
  switch (filter) {
    case 'playoff':
      return rows.filter((row) => row.zone === 'playoff');
    case 'play_in':
      return rows.filter((row) => row.zone === 'play_in');
    case 'hot':
      return rows.filter((row) => row.tag === 'hot');
    case 'cold':
      return rows.filter((row) => row.tag === 'cold');
    default:
      return rows;
  }
}

/** Both conferences in one table: pct desc, wins desc, name asc, positions renumbered. gb and zone stay per conference. */
export function leagueTable(west: StandingRow[], east: StandingRow[]): StandingRow[] {
  return [...west, ...east]
    .sort((a, b) => b.pct - a.pct || b.v - a.v || a.nome.localeCompare(b.nome))
    .map((row, index) => ({ ...row, pos: index + 1 }));
}
