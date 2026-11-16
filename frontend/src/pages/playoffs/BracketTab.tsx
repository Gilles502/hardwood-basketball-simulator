import React from 'react';
import { Shield } from 'lucide-react';
import type { PlayoffBracket, PlayoffSeries } from '../../store/leagueStore';
import { TeamCrest } from '../../components/TeamCrest';
import { crestLabel } from '../../utils/crest';
import { nickname } from '../../utils/resultSheet';
import type { SeriesLog } from '../../utils/resultSheet';
import { seedsFromBracket } from '../../utils/playoffNight';

const WINS_NEEDED = 4;

/** Round names keyed by the server's `next_turn`. */
export const ROUND_LABELS: Record<string, string> = {
  QF: 'First round',
  SF: 'Conference semifinals',
  CF: 'Conference finals',
  FINALS: 'The Finals',
};

/** First-round slots top to bottom, in the server's order: 1v8, 4v5, 3v6, 2v7 (winners of 0+1 and 2+3 meet). */
const FIRST_ROUND_SEEDS = [[1, 8], [4, 5], [3, 6], [2, 7]];

type Side = 'east' | 'west';
type RoundKey = 'qf' | 'sf' | 'cf' | 'finals';

interface FinalsMvp {
  nome: string;
  stats: { ppg: number; rpg: number; apg: number; spg: number; bpg: number };
}

interface BracketTabProps {
  bracket: PlayoffBracket;
  champion: string | null;
  finalsMvp: FinalsMvp | null;
  userTeam: string | null;
  /** Round being played, null once the playoffs are over. */
  liveRound: string | null;
  busy: boolean;
  onSimulate: (bulk: boolean) => void;
  onGoToPlayIn: () => void;
  onOpenGameplan: () => void;
  onOpenSeries: (series: SeriesLog, label: string, winsNeeded: number) => void;
}

const isDone = (s: PlayoffSeries | null | undefined) => !!s?.winner_nome;
const seedNum = (seed: string | number) => Number.parseInt(String(seed), 10);

/** What a not-yet-drawn slot shows for one of its two teams. */
const feederLabel = (s: PlayoffSeries | null | undefined, fallback: string): { name: string | null; text: string } => {
  if (s?.winner_nome) return { name: s.winner_nome, text: nickname(s.winner_nome) };
  if (s) return { name: null, text: `${nickname(s.s1_nome)} / ${nickname(s.s2_nome)}` };
  return { name: null, text: fallback };
};

const footerOf = (s: PlayoffSeries, isNow: boolean, isFinals: boolean, seedOf: Record<string, string | number>) => {
  const v1 = crestLabel(s.s1_nome);
  const v2 = crestLabel(s.s2_nome);
  if (isDone(s)) {
    const won = s.winner_nome === s.s1_nome;
    const [w, l] = won ? [s.s1_vittorie, s.s2_vittorie] : [s.s2_vittorie, s.s1_vittorie];
    const [ws, ls] = [s.winner_nome!, won ? s.s2_nome : s.s1_nome].map((n) => (n === s.s1_nome ? s.s1_seed : s.s2_seed) || seedOf[n]);
    const upset = !isFinals && seedNum(ws) > seedNum(ls);
    return { left: `${upset ? 'Upset' : 'Won'} ${w}–${l}`, right: '', tone: '' };
  }
  const played = s.s1_vittorie + s.s2_vittorie;
  const next = played + 1;
  if (s.s1_vittorie === WINS_NEEDED - 1 && s.s2_vittorie === WINS_NEEDED - 1) {
    return { left: 'Game 7 next', right: '', tone: 'is-g7' };
  }
  if (played === 0) return { left: isNow ? 'Game 1 next' : 'Upcoming', right: '', tone: '' };
  const left = s.s1_vittorie === s.s2_vittorie
    ? `Tied ${s.s1_vittorie}–${s.s2_vittorie}`
    : s.s1_vittorie > s.s2_vittorie
      ? `${v1} leads ${s.s1_vittorie}–${s.s2_vittorie}`
      : `${v2} leads ${s.s2_vittorie}–${s.s1_vittorie}`;
  return { left, right: isNow ? `G${next} next` : '', tone: '' };
};

interface TicketProps {
  series: PlayoffSeries | null | undefined;
  /** Shown instead of teams while the series isn't drawn yet. */
  placeholder: [{ name: string | null; text: string }, { name: string | null; text: string }];
  caption: string;
  label: string;
  isNow: boolean;
  isFinals?: boolean;
  userTeam: string | null;
  /** Conference seed per team, from the first round (later rounds arrive without seeds). */
  seedOf: Record<string, string | number>;
  onOpen: (series: SeriesLog, label: string, winsNeeded: number) => void;
}

/** Generated crest (initials + stable colour), the app's stand-in for team logos. */
export const TeamDisc: React.FC<{ name: string; size?: 'lg' }> = ({ name, size }) => (
  <TeamCrest name={name} size={size === 'lg' ? 52 : 22} />
);

const Ticket: React.FC<TicketProps> = ({ series, placeholder, caption, label, isNow, isFinals = false, userTeam, seedOf, onOpen }) => {
  if (!series) {
    return (
      <div className="po-tkt is-tbd">
        {placeholder.map((p, i) => (
          <div key={i} className="po-row">
            <i />
            {p.name && <TeamDisc name={p.name} />}
            <b className={p.name ? 'is-known' : ''}>{p.text}</b>
            <em>–</em>
          </div>
        ))}
        <div className="po-ft"><span>{caption}</span></div>
      </div>
    );
  }

  const done = isDone(series);
  const foot = footerOf(series, isNow, isFinals, seedOf);
  const mine = !!userTeam && (series.s1_nome === userTeam || series.s2_nome === userTeam);
  const hasGames = (series.games?.length ?? 0) > 0;
  const rows = [
    { name: series.s1_nome, seed: series.s1_seed || seedOf[series.s1_nome], wins: series.s1_vittorie },
    { name: series.s2_nome, seed: series.s2_seed || seedOf[series.s2_nome], wins: series.s2_vittorie },
  ];
  const cls = ['po-tkt', mine && 'is-me', isNow && !done && 'is-now', foot.tone].filter(Boolean).join(' ');
  const body = (
    <>
      {rows.map((r) => (
        <div key={r.name} className={`po-row${done ? (r.name === series.winner_nome ? ' is-win' : ' is-out') : ''}`}>
          <i>{r.seed}</i>
          <TeamDisc name={r.name} />
          <b title={r.name}>{nickname(r.name)}</b>
          <em>{r.wins}</em>
        </div>
      ))}
      <div className="po-ft"><span>{foot.left}</span>{foot.right && <span>{foot.right}</span>}</div>
    </>
  );

  if (!hasGames) return <div className={cls}>{body}</div>;
  return (
    <button
      type="button"
      className={cls}
      onClick={() => onOpen(series as SeriesLog, label, WINS_NEEDED)}
      aria-label={`${label}: ${series.s1_nome} ${series.s1_vittorie}, ${series.s2_nome} ${series.s2_vittorie}. Open result sheet`}
    >
      {body}
    </button>
  );
};

export const BracketTab: React.FC<BracketTabProps> = ({
  bracket, champion, finalsMvp, userTeam, liveRound, busy, onSimulate, onGoToPlayIn, onOpenGameplan, onOpenSeries,
}) => {
  const liveKey = liveRound?.toLowerCase() as RoundKey | undefined;
  const seedOf = seedsFromBracket(bracket);

  const ticket = (side: Side | 'finals', round: RoundKey, idx: number, label: string, placeholder: TicketProps['placeholder'], caption: string) => {
    const list = side === 'finals' ? bracket.finals : bracket[side][round as 'qf' | 'sf' | 'cf'];
    return (
      <Ticket
        series={list?.[idx]}
        placeholder={placeholder}
        caption={caption}
        label={label}
        isNow={liveKey === round}
        isFinals={side === 'finals'}
        userTeam={userTeam}
        seedOf={seedOf}
        onOpen={onOpenSeries}
      />
    );
  };

  const conference = (side: Side) => {
    const conf = side === 'east' ? 'East' : 'West';
    const { qf, sf } = bracket[side];
    const firstRound = FIRST_ROUND_SEEDS.map(([a, b], i) =>
      ticket(side, 'qf', i, `${conf} first round`, [{ name: null, text: `#${a} seed` }, { name: null, text: `#${b} seed` }], 'First round'));
    const semis = [0, 1].map((i) =>
      ticket(side, 'sf', i, `${conf} semifinals`, [feederLabel(qf?.[i * 2], 'First-round winner'), feederLabel(qf?.[i * 2 + 1], 'First-round winner')], 'Semifinal'));
    const final = ticket(side, 'cf', 0, `${conf} finals`, [feederLabel(sf?.[0], 'Semifinal winner'), feederLabel(sf?.[1], 'Semifinal winner')], `${conf} finals`);
    return { firstRound, semis, final };
  };

  const east = conference('east');
  const west = conference('west');
  const finals = ticket('finals', 'finals', 0, 'Finals',
    [feederLabel(bracket.east.cf?.[0], 'East champion'), feederLabel(bracket.west.cf?.[0], 'West champion')], 'Best of 7');

  // The user's opponent in the round being played, for the Gameplan button.
  const liveSeries: PlayoffSeries[] = liveKey === 'finals'
    ? bracket.finals ?? []
    : liveKey ? [...(bracket.east[liveKey] ?? []), ...(bracket.west[liveKey] ?? [])] : [];
  const mySeries = liveSeries.find((s) => s && !isDone(s) && (s.s1_nome === userTeam || s.s2_nome === userTeam));
  const opponent = mySeries ? (mySeries.s1_nome === userTeam ? mySeries.s2_nome : mySeries.s1_nome) : null;

  return (
    <div className="po-bracket">
      {liveRound === 'PLAY_IN' ? (
        <div className="po-sim">
          <span className="po-cap">Now playing</span>
          <b>Play-In Tournament</b>
          <span className="po-sim-gap" />
          <button type="button" className="btn btn-primary" onClick={onGoToPlayIn}>Go to Play-In</button>
        </div>
      ) : liveRound && ROUND_LABELS[liveRound] ? (
        <div className="po-sim">
          <span className="po-cap">Now playing</span>
          <b>{ROUND_LABELS[liveRound]}</b>
          <span className="po-sim-gap" />
          <button type="button" className="btn btn-primary" onClick={() => onSimulate(false)} disabled={busy}>
            {busy ? 'Simulating…' : 'Sim next game'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => onSimulate(true)} disabled={busy}>
            {busy ? 'Simulating…' : 'Sim whole round'}
          </button>
          <button
            type="button"
            className="btn btn-secondary po-gameplan"
            onClick={onOpenGameplan}
            disabled={busy}
            title="Scout this opponent and set who guards whom for the series"
          >
            <Shield size={15} aria-hidden="true" /> {opponent ? `Gameplan vs ${nickname(opponent)}` : 'Gameplan'}
          </button>
        </div>
      ) : null}

      <div className="po-wall">
        <div className="po-heads" aria-hidden="true">
          <div className="po-conf">Eastern Conference</div>
          <div />
          <div className="po-conf">Western Conference</div>
          {['First round', 'Semifinals', 'Conf. finals', 'Finals', 'Conf. finals', 'Semifinals', 'First round'].map((h, i) => (
            <div key={i} className={`po-cap${i === 3 ? ' is-finals' : ''}`}>{h}</div>
          ))}
        </div>

        <div className="po-grid">
          <div className="po-col is-east">
            <div className="po-pair">{east.firstRound[0]}{east.firstRound[1]}</div>
            <div className="po-pair">{east.firstRound[2]}{east.firstRound[3]}</div>
          </div>
          <div className="po-col is-east"><div className="po-pair">{east.semis[0]}{east.semis[1]}</div></div>
          <div className="po-col is-east">{east.final}</div>

          <div className="po-center">
            <div className={`po-plaque${champion ? ' is-crowned' : ''}`}>
              <div className="po-trophy" aria-hidden="true">🏆</div>
              {champion ? (
                <>
                  <span className="po-cap">Champions</span>
                  <div className="po-champ"><TeamDisc name={champion} /> {champion}</div>
                  {finalsMvp && (
                    <div className="po-mvp">
                      <span className="po-cap">Finals MVP</span>
                      <b>{finalsMvp.nome}</b>
                      <span className="po-mvp-line">
                        {[['PPG', finalsMvp.stats.ppg], ['RPG', finalsMvp.stats.rpg], ['APG', finalsMvp.stats.apg], ['SPG', finalsMvp.stats.spg], ['BPG', finalsMvp.stats.bpg]].map(([k, v]) => (
                          <span key={k}><strong>{v}</strong>{k}</span>
                        ))}
                      </span>
                    </div>
                  )}
                </>
              ) : (
                <div className="po-plaque-title">The Finals</div>
              )}
              {finals}
            </div>
            {!champion && <span className="po-cap">Champion is crowned here</span>}
          </div>

          <div className="po-col is-west">{west.final}</div>
          <div className="po-col is-west"><div className="po-pair">{west.semis[0]}{west.semis[1]}</div></div>
          <div className="po-col is-west">
            <div className="po-pair">{west.firstRound[0]}{west.firstRound[1]}</div>
            <div className="po-pair">{west.firstRound[2]}{west.firstRound[3]}</div>
          </div>
        </div>

        <div className="po-legend">
          <span><i className="is-me" />Your team</span>
          <span><i className="is-now" />Being played now</span>
          <span><i className="is-g7" />Game 7</span>
          <span><i className="is-out" />Eliminated</span>
          <span>Click a series for its result sheet</span>
        </div>
      </div>
    </div>
  );
};
