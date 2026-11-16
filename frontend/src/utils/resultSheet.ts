// Data for the shared result sheet: the calendar box score payload, and playoff game logs turned into it.

export interface SheetPlayer {
  name: string;
  /** Missing on playoff games saved before positions were recorded. */
  pos?: string;
  is_starter?: boolean;
  min: number;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  /** null on playoff games saved before turnovers were recorded. */
  to: number | null;
  pf: number;
  fgm: number;
  fga: number;
  tpm: number;
  tpa: number;
  ftm: number;
  fta: number;
  plus_minus: number;
}

export interface SheetTeam {
  name: string;
  score: number;
  quarters: number[];
  players: SheetPlayer[];
}

export interface TopPerformer {
  name: string;
  team: string;
  pts: number;
  reb: number;
  ast: number;
  min?: number;
}

export interface SheetPayload {
  game_id: string;
  date?: string;
  day_index?: number;
  home_team: SheetTeam;
  away_team: SheetTeam;
  top_performer?: TopPerformer | null;
}

/** Box score row of playoff games saved before they carried a result sheet. */
interface LegacyRow {
  nome: string;
  min: string | number;
  pts: string | number;
  reb: string | number;
  ast: string | number;
  stl: string | number;
  blk: string | number;
  pf: string | number;
  fg: string;
  p3: string;
  ft: string;
  plus_minus: string | number;
}

interface SeriesTeamLog {
  nome: string;
  punteggio: number;
  punteggi_quarti?: number[];
  box_score?: LegacyRow[];
}

export interface SeriesGameLog {
  game_num: number;
  squadra_casa: SeriesTeamLog;
  squadra_ospite: SeriesTeamLog;
  result_sheet?: SheetPayload;
}

export interface SeriesLog {
  s1_nome: string;
  s2_nome: string;
  winner_nome: string | null;
  games: SeriesGameLog[];
}

const num = (v: string | number | undefined) => Number.parseFloat(String(v ?? 0)) || 0;
const split = (made: string) => (made || '0-0').split('-').map((n) => Number.parseInt(n, 10) || 0);

const fromLegacyRow = (row: LegacyRow): SheetPlayer => {
  const [fgm, fga] = split(row.fg);
  const [tpm, tpa] = split(row.p3);
  const [ftm, fta] = split(row.ft);
  return {
    name: row.nome, min: num(row.min), pts: num(row.pts), reb: num(row.reb), ast: num(row.ast),
    stl: num(row.stl), blk: num(row.blk), to: null, pf: num(row.pf),
    fgm, fga, tpm, tpa, ftm, fta, plus_minus: num(row.plus_minus),
  };
};

const fromLegacyTeam = (team: SeriesTeamLog): SheetTeam => ({
  name: team.nome,
  score: team.punteggio,
  quarters: team.punteggi_quarti ?? [],
  players: (team.box_score ?? []).map(fromLegacyRow),
});

export const sheetFromSeriesGame = (game: SeriesGameLog): SheetPayload => game.result_sheet ?? {
  game_id: `legacy-${game.squadra_ospite.nome}@${game.squadra_casa.nome}-G${game.game_num}`,
  home_team: fromLegacyTeam(game.squadra_casa),
  away_team: fromLegacyTeam(game.squadra_ospite),
};

/** Same pick as the server: most points, then points + rebounds + assists. */
export const topPerformerOf = (sheet: SheetPayload): TopPerformer | null => {
  if (sheet.top_performer) return sheet.top_performer;
  const all = [sheet.away_team, sheet.home_team].flatMap((team) => team.players.map((p) => ({ p, team: team.name })));
  if (all.length === 0) return null;
  const line = (p: SheetPlayer) => p.pts + p.reb + p.ast;
  const best = all.reduce((a, b) => (b.p.pts > a.p.pts || (b.p.pts === a.p.pts && line(b.p) > line(a.p)) ? b : a));
  return { name: best.p.name, team: best.team, pts: best.p.pts, reb: best.p.reb, ast: best.p.ast, min: best.p.min };
};

export const winnerOf = (sheet: SheetPayload) =>
  sheet.home_team.score > sheet.away_team.score ? sheet.home_team : sheet.away_team;

/** The last word of a team name ("Wolves" from "Metro City Wolves"). */
export const nickname = (teamName: string) => teamName.split(' ').slice(-1)[0] || teamName;

/** Series wins for each team after the first `count` games. */
export const seriesWins = (series: SeriesLog, count: number) => {
  const wins: Record<string, number> = { [series.s1_nome]: 0, [series.s2_nome]: 0 };
  series.games.slice(0, count).forEach((game) => {
    const sheet = sheetFromSeriesGame(game);
    const winner = winnerOf(sheet).name;
    wins[winner] = (wins[winner] ?? 0) + 1;
  });
  return wins;
};

/** "Raptors lead 3–1", "Series tied 2–2", "Raptors win 4–1". */
export const seriesStatus = (series: SeriesLog, count: number, winsNeeded: number) => {
  const wins = seriesWins(series, count);
  const [a, b] = [series.s1_nome, series.s2_nome].sort((x, y) => wins[y] - wins[x]);
  if (wins[a] === wins[b]) return `Series tied ${wins[a]}–${wins[b]}`;
  return `${nickname(a)} ${wins[a] >= winsNeeded ? 'win' : 'lead'} ${wins[a]}–${wins[b]}`;
};

export const pct = (made: number, attempts: number) => (attempts > 0 ? (made / attempts * 100).toFixed(1) : '–');

export const signed = (value: number) => (value > 0 ? `+${value}` : String(value));
