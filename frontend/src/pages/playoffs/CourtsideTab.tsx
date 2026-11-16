import React from 'react';
import { crestLabel } from '../../utils/crest';
import { nickname, seriesStatus, sheetFromSeriesGame, topPerformerOf, winnerOf } from '../../utils/resultSheet';
import type { SeriesLog } from '../../utils/resultSheet';
import type { IdleSeries, LatestResult, NightGame } from '../../utils/playoffNight';
import { TeamDisc } from './BracketTab';

interface CourtsideTabProps {
  games: NightGame[];
  idle: IdleSeries[];
  latest: LatestResult[];
  userTeam: string | null;
  seedOf: Record<string, string | number>;
  champion: string | null;
  /** True while the playoffs (or play-in) are running. */
  inProgress: boolean;
  busy: boolean;
  onWatch: (game: NightGame) => void;
  onOpenSeries: (series: SeriesLog, label: string, winsNeeded: number) => void;
}

const isMine = (g: NightGame, team: string | null) => !!team && (g.s1 === team || g.s2 === team);
const abbr = crestLabel;

/** Yours first; otherwise the biggest game: a Game 7, then a closeout game, then the closest series. */
const pickFeatured = (games: NightGame[], userTeam: string | null) => {
  const mine = games.find((g) => isMine(g, userTeam));
  if (mine) return mine;
  const weight = (g: NightGame) => (g.w1 === 3 && g.w2 === 3 ? 0 : Math.max(g.w1, g.w2) === 3 ? 1 : 2 + Math.abs(g.w1 - g.w2));
  return [...games].sort((a, b) => weight(a) - weight(b))[0] ?? null;
};

const winsOf = (g: NightGame, team: string) => (team === g.s1 ? [g.w1, g.w2] : [g.w2, g.w1]);

/** "#1 · lead 3–1" under a team on the featured card. */
const teamLine = (g: NightGame, team: string, seedOf: Record<string, string | number>) => {
  const seed = seedOf[team] ? `#${seedOf[team]}` : '';
  if (g.isPlayIn || g.gameNum === 1) return seed ? `${seed} seed` : '';
  const [mine, theirs] = winsOf(g, team);
  const state = mine === theirs ? `tied ${mine}–${theirs}` : mine > theirs ? `lead ${mine}–${theirs}` : `down ${mine}–${theirs}`;
  return [seed, state].filter(Boolean).join(' · ');
};

/** One line on what tonight's game decides. */
const stakes = (g: NightGame, userTeam: string | null): React.ReactNode => {
  if (g.isPlayIn) return 'One game: win or go home.';
  const toTitle = g.nextStage === 'the title';
  if (isMine(g, userTeam)) {
    const [mine, theirs] = winsOf(g, userTeam!);
    const win = toTitle ? <>Win tonight and you're the <b>champions</b>.</> : <>Win tonight and you're in the <b>{g.nextStage}</b>.</>;
    if (mine === 3 && theirs === 3) return <>Game 7. {win} Lose and the season is over.</>;
    if (mine === 3) return win;
    if (theirs === 3) return 'Lose tonight and the season is over.';
    if (g.gameNum === 1) return `Game 1 of the ${g.label}.`;
    return mine === theirs ? `Series tied ${mine}–${theirs}.` : mine > theirs ? `You lead the series ${mine}–${theirs}.` : `You trail the series ${mine}–${theirs}.`;
  }
  if (g.w1 === 3 && g.w2 === 3) return <>Game 7: the winner goes {toTitle ? <>home with <b>the title</b></> : <>to the <b>{g.nextStage}</b></>}.</>;
  if (g.w1 === 3 || g.w2 === 3) return <>The {nickname(g.w1 === 3 ? g.s1 : g.s2)} can close it out tonight.</>;
  return g.gameNum === 1 ? `Game 1 of the ${g.label}.` : g.w1 === g.w2 ? `Series tied ${g.w1}–${g.w2}.` : `${nickname(g.w1 > g.w2 ? g.s1 : g.s2)} lead ${Math.max(g.w1, g.w2)}–${Math.min(g.w1, g.w2)}.`;
};

/** Series state for a row in "Also tonight". */
const rowStatus = (g: NightGame) => {
  if (g.isPlayIn) return { text: 'Win or go home', hot: true };
  if (g.w1 === 3 && g.w2 === 3) return { text: 'Series 3–3 · winner takes all', hot: true };
  if (g.gameNum === 1) return { text: 'Series starts', hot: false };
  if (g.w1 === g.w2) return { text: `Series tied ${g.w1}–${g.w2}`, hot: false };
  const lead = g.w1 > g.w2 ? g.s1 : g.s2;
  return { text: `${abbr(lead)} lead ${Math.max(g.w1, g.w2)}–${Math.min(g.w1, g.w2)}`, hot: Math.max(g.w1, g.w2) === 3 };
};

const ResultCard: React.FC<{ result: LatestResult; onOpen: CourtsideTabProps['onOpenSeries'] }> = ({ result, onOpen }) => {
  const { series, label, winsNeeded } = result;
  const last = series.games[series.games.length - 1];
  const sheet = sheetFromSeriesGame(last);
  const win = winnerOf(sheet);
  const lose = win === sheet.home_team ? sheet.away_team : sheet.home_team;
  const top = topPerformerOf(sheet);
  const story = winsNeeded > 1 ? seriesStatus(series, series.games.length, winsNeeded) : `${nickname(win.name)} win`;
  const gameTag = winsNeeded > 1 ? ` · G${series.games.length}` : '';
  return (
    <button
      type="button"
      className="cs-result"
      onClick={() => onOpen(series, label, winsNeeded)}
      aria-label={`${label}${gameTag}: ${win.name} ${win.score}, ${lose.name} ${lose.score}. Open result sheet`}
    >
      <span className="cs-result-head"><span>{label}{gameTag}</span><span>Final</span></span>
      <span className="cs-result-line"><TeamDisc name={win.name} /><b>{nickname(win.name)}</b><em>{win.score}</em></span>
      <span className="cs-result-line is-lo"><TeamDisc name={lose.name} /><b>{nickname(lose.name)}</b><em>{lose.score}</em></span>
      <span className="cs-result-foot">{top ? `${top.name} ${top.pts} pts · ` : ''}{story}</span>
    </button>
  );
};

export const CourtsideTab: React.FC<CourtsideTabProps> = ({
  games, idle, latest, userTeam, seedOf, champion, inProgress, busy, onWatch, onOpenSeries,
}) => {
  const featured = pickFeatured(games, userTeam);
  const others = games.filter((g) => g !== featured);
  const featuredIsMine = !!featured && isMine(featured, userTeam);

  return (
    <div className="cs-root">
      {featured ? (
        <section className="cs-feat" aria-label="Featured game">
          <div className="cs-feat-body">
            <div className="cs-feat-meta">
              <span className="cs-pill">{featuredIsMine ? 'Your game tonight' : 'Game of the night'}</span>
              <span className="po-cap">
                {featured.label}{featured.isPlayIn ? '' : ` · Game ${featured.gameNum}`}{featured.isPlayIn ? '' : ` · at ${nickname(featured.home)}`}
              </span>
            </div>
            <div className="cs-vs">
              {[featured.away, featured.home].map((team, i) => (
                <React.Fragment key={team}>
                  {i === 1 && <span className="cs-at">{featured.isPlayIn ? 'vs' : 'at'}</span>}
                  <div className={`cs-team${team === userTeam ? ' is-me' : ''}`}>
                    <TeamDisc name={team} size="lg" />
                    <div>
                      <div className="cs-team-name">{nickname(team)}</div>
                      <div className="cs-team-line">{teamLine(featured, team, seedOf)}</div>
                    </div>
                  </div>
                </React.Fragment>
              ))}
            </div>
            <p className="cs-stakes">{stakes(featured, userTeam)}</p>
          </div>
          <div className="cs-feat-go">
            <button type="button" className="btn btn-primary cs-watch" onClick={() => onWatch(featured)} disabled={busy}>
              {busy ? 'Tip-off…' : '▶ Watch live'}
            </button>
            <small>
              {featured.isPlayIn
                ? 'Play-In games are played one at a time'
                : others.length === 0
                  ? "It's the only game tonight"
                  : `The other ${others.length === 1 ? 'game' : `${others.length} games`} tonight ${others.length === 1 ? 'is' : 'are'} played at the same time`}
            </small>
          </div>
        </section>
      ) : (
        <section className="cs-feat is-quiet">
          <div className="cs-feat-body">
            <span className="po-cap">{champion ? 'Season over' : 'No games tonight'}</span>
            <div className="cs-quiet-title">
              {champion
                ? <><TeamDisc name={champion} size="lg" /> {champion} are the champions</>
                : inProgress
                  ? 'The next round is not drawn yet'
                  : 'Courtside Live opens with the playoffs'}
            </div>
            <p className="cs-stakes">
              {champion
                ? 'Every game of the run is still here: open any series from the Bracket tab.'
                : inProgress
                  ? 'Sim the next game from the Bracket tab and tonight’s games show up here.'
                  : 'When the regular season ends, every playoff night shows up here and you pick the game to watch.'}
            </p>
          </div>
        </section>
      )}

      {(others.length > 0 || idle.length > 0) && (
        <section aria-labelledby="cs-also">
          <h2 className="cs-sec" id="cs-also">Also tonight <span>Pick one of these to watch instead</span></h2>
          <div className="cs-list">
            {others.map((g) => {
              const st = rowStatus(g);
              return (
                <div key={g.key} className={`cs-row${isMine(g, userTeam) ? ' is-me' : ''}`}>
                  <div className="cs-row-game">{g.isPlayIn ? 'Play-In' : `Game ${g.gameNum}`}<small>{g.label}</small></div>
                  <div className="cs-row-teams">
                    <TeamDisc name={g.away} />{nickname(g.away)} <em>at</em> <TeamDisc name={g.home} />{nickname(g.home)}
                  </div>
                  <div className={`cs-row-status${st.hot ? ' is-hot' : ''}`}>{st.text}</div>
                  <button type="button" className="cs-btn-ghost" onClick={() => onWatch(g)} disabled={busy}>▶ Watch this one</button>
                </div>
              );
            })}
            {idle.map(({ series, label }) => {
              const won = series.winner_nome!;
              const lost = won === series.s1_nome ? series.s2_nome : series.s1_nome;
              const [w, l] = won === series.s1_nome ? [series.s1_vittorie, series.s2_vittorie] : [series.s2_vittorie, series.s1_vittorie];
              return (
                <div key={`${series.s1_nome}-${series.s2_nome}`} className="cs-row is-off">
                  <div className="cs-row-game">No game<small>{label}</small></div>
                  <div className="cs-row-teams"><TeamDisc name={won} />{nickname(won)} <em>beat</em> <TeamDisc name={lost} />{nickname(lost)}</div>
                  <div className="cs-row-status">Won {w}–{l} · waiting</div>
                  <button type="button" className="cs-btn-ghost" onClick={() => onOpenSeries(series as SeriesLog, label, 4)}>Results</button>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {latest.length > 0 && (
        <section aria-labelledby="cs-latest">
          <h2 className="cs-sec" id="cs-latest">Latest results <span>Click a game for its result sheet</span></h2>
          <div className="cs-results">
            {latest.map((r) => <ResultCard key={r.key} result={r} onOpen={onOpenSeries} />)}
          </div>
        </section>
      )}
    </div>
  );
};
