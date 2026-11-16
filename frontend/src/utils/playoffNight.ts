import type { PlayoffBracket, PlayoffSeries } from '../store/leagueStore';
import type { SeriesLog } from './resultSheet';

/** A game that is played on the next playoff night. */
export interface NightGame {
  key: string;
  s1: string;
  s2: string;
  w1: number;
  w2: number;
  gameNum: number;
  home: string;
  away: string;
  /** "East semifinals", "Finals", "East play-in · 7 vs 8". */
  label: string;
  /** Round the winner reaches next ("East finals", "Finals", "the title"); null for play-in. */
  nextStage: string | null;
  isPlayIn: boolean;
}

/** A series of the current round that is already decided, so it has no game tonight. */
export interface IdleSeries {
  series: PlayoffSeries;
  label: string;
}

export interface LatestResult {
  key: string;
  series: SeriesLog;
  label: string;
  winsNeeded: number;
}

export interface PlayInData {
  state: string;
  game_index: number;
  east?: PlayInConference;
  west?: PlayInConference;
}

interface PlayInConference {
  play_in_teams: string[];
  results?: { game1?: { winner: string; loser: string } | null; game2?: { winner: string; loser: string } | null };
  games?: (SeriesLog | null)[];
}

type Conf = 'east' | 'west';
const CONF_NAME: Record<Conf, string> = { east: 'East', west: 'West' };
const ROUND_ORDER = ['qf', 'sf', 'cf', 'finals'] as const;
type RoundKey = (typeof ROUND_ORDER)[number];

/** In every series the first-listed team is at home in games 1, 2, 5 and 7 (same rule as the engine). */
export const homeOf = (s1: string, s2: string, gameNum: number) => ([1, 2, 5, 7].includes(gameNum) ? s1 : s2);

const roundLabel = (round: RoundKey, conf: Conf | null) => {
  if (round === 'finals' || !conf) return 'Finals';
  return `${CONF_NAME[conf]} ${{ qf: 'first round', sf: 'semifinals', cf: 'finals' }[round]}`;
};

const nextStageOf = (round: RoundKey, conf: Conf | null) => {
  if (round === 'finals' || !conf) return 'the title';
  return { qf: `${CONF_NAME[conf]} semifinals`, sf: `${CONF_NAME[conf]} finals`, cf: 'Finals' }[round];
};

const winner = (s: PlayoffSeries | null | undefined) => s?.winner_nome ?? null;

/** Conference seed per team, read from the first round (later rounds arrive without seeds). */
export const seedsFromBracket = (bracket: PlayoffBracket) => {
  const seedOf: Record<string, string | number> = {};
  [...(bracket.east.qf ?? []), ...(bracket.west.qf ?? [])].forEach((s) => {
    if (!s) return;
    seedOf[s.s1_nome] = s.s1_seed;
    seedOf[s.s2_nome] = s.s2_seed;
  });
  return seedOf;
};

/** The matchups of a round in the server's order: drawn series, or the pairs the finished feeders produce. */
const roundSlots = (bracket: PlayoffBracket, round: RoundKey): { conf: Conf | null; series: PlayoffSeries | null; pair: [string, string] | null }[] => {
  const slot = (conf: Conf | null, series: PlayoffSeries | null | undefined, a: string | null, b: string | null) => ({
    conf, series: series ?? null, pair: a && b ? [a, b] as [string, string] : null,
  });
  if (round === 'finals') {
    return [slot(null, bracket.finals?.[0], winner(bracket.east.cf?.[0]), winner(bracket.west.cf?.[0]))];
  }
  return (['east', 'west'] as Conf[]).flatMap((conf) => {
    const side = bracket[conf];
    if (round === 'qf') return [0, 1, 2, 3].map((i) => slot(conf, side.qf?.[i], null, null));
    if (round === 'sf') return [0, 1].map((i) => slot(conf, side.sf?.[i], winner(side.qf?.[i * 2]), winner(side.qf?.[i * 2 + 1])));
    return [slot(conf, side.cf?.[0], winner(side.sf?.[0]), winner(side.sf?.[1]))];
  });
};

/** Games of the next playoff night for the round the server will play (`next_turn`). */
export const playoffNight = (bracket: PlayoffBracket, nextTurn: string): { games: NightGame[]; idle: IdleSeries[] } => {
  const round = nextTurn.toLowerCase() as RoundKey;
  if (!ROUND_ORDER.includes(round)) return { games: [], idle: [] };
  const games: NightGame[] = [];
  const idle: IdleSeries[] = [];
  roundSlots(bracket, round).forEach(({ conf, series, pair }, i) => {
    const label = roundLabel(round, conf);
    if (series?.winner_nome) {
      idle.push({ series, label });
      return;
    }
    const [s1, s2] = series ? [series.s1_nome, series.s2_nome] : pair ?? [null, null];
    if (!s1 || !s2) return;
    const gameNum = (series?.games?.length ?? 0) + 1;
    const home = homeOf(s1, s2, gameNum);
    games.push({
      key: `${round}-${i}`, s1, s2,
      w1: series?.s1_vittorie ?? 0, w2: series?.s2_vittorie ?? 0,
      gameNum, home, away: home === s1 ? s2 : s1,
      label, nextStage: nextStageOf(round, conf), isPlayIn: false,
    });
  });
  return { games, idle };
};

const PLAY_IN_LABELS = ['7 vs 8', '9 vs 10', 'final'];

/** The single play-in game the server plays next (play-in games go one at a time, East first). */
export const nextPlayInGame = (data: PlayInData | null): NightGame | null => {
  if (!data || data.state !== 'PLAY_IN' || data.game_index > 5) return null;
  const conf: Conf = data.game_index < 3 ? 'east' : 'west';
  const g = data.game_index % 3;
  const c = data[conf];
  const teams = c?.play_in_teams ?? [];
  const pair = g === 0 ? [teams[0], teams[1]]
    : g === 1 ? [teams[2], teams[3]]
      : [c?.results?.game1?.loser, c?.results?.game2?.winner];
  const [s1, s2] = pair;
  if (!s1 || !s2) return null;
  return {
    key: `playin-${data.game_index}`, s1, s2, w1: 0, w2: 0, gameNum: 1, home: s1, away: s2,
    label: `${CONF_NAME[conf]} play-in · ${PLAY_IN_LABELS[g]}`, nextStage: null, isPlayIn: true,
  };
};

/**
 * Last game of each series in the newest round that has games, so the strip shows what just happened.
 * Falls back to the play-in while the first round has not started.
 */
export const latestResults = (bracket: PlayoffBracket | null, playIn: PlayInData | null): LatestResult[] => {
  if (bracket) {
    for (const round of [...ROUND_ORDER].reverse()) {
      const found = roundSlots(bracket, round)
        .filter(({ series }) => (series?.games?.length ?? 0) > 0)
        .map(({ conf, series }, i) => ({
          key: `${round}-${i}`, series: series as SeriesLog, label: roundLabel(round, conf), winsNeeded: 4,
        }));
      if (found.length > 0) return found;
    }
  }
  const out: LatestResult[] = [];
  (['east', 'west'] as Conf[]).forEach((conf) => {
    playIn?.[conf]?.games?.forEach((log, g) => {
      if (log?.games?.length) out.push({ key: `${conf}-pi-${g}`, series: log, label: `${CONF_NAME[conf]} play-in · ${PLAY_IN_LABELS[g]}`, winsNeeded: 1 });
    });
  });
  return out;
};
