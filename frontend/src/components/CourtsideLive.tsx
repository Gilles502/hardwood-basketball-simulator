// Courtside Live: watch a simulated game play by play (calendar, matchday hub, playoffs).
import React, { useEffect, useRef, useState } from 'react';
import { Radio } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useLeagueStore } from '../store/leagueStore';
import { getTeamVisuals } from '../utils/teamVisuals';
import { nickname, pct } from '../utils/resultSheet';
import {
  computeLiveBoxScore, elapsedSeconds, gameSeconds, highlightLabel, isPlay, periodLabel, playLine, teamTotals,
} from '../utils/liveGame';
import type { LivePlayerStats, PlayEvent, PlayLogEntry } from '../utils/liveGame';
import './CourtsideLive.css';

export interface LiveGame {
  home: string;
  away: string;
  /** Where the game sits, e.g. "Regular season · Day 12" or "East first round · Game 3". */
  label: string;
  plays: PlayLogEntry[];
}

interface CourtsideLiveProps {
  game: LiveGame;
  onClose: () => void;
}

const SPEEDS = [
  { label: '1×', ms: 1500 },
  { label: '2×', ms: 700 },
  { label: '4×', ms: 300 },
  { label: 'Instant', ms: 40 },
];
const LEADERS_SHOWN = 3;
const FLOW_W = 400;
const FLOW_H = 100;
const FLOW_MIN_RANGE = 10;

type Pause = 'none' | 'halftime' | 'final';
type Filter = 'all' | 'scores' | 'highlights';

/** Steps through the play log: timer, single steps, skip, and the halftime / final stops. */
const usePlayback = (plays: PlayLogEntry[]) => {
  const [shown, setShown] = useState(0);
  const [playing, setPlaying] = useState(plays.length > 0);
  const [speed, setSpeed] = useState(SPEEDS[0].ms);
  const [pause, setPause] = useState<Pause>(plays.length > 0 ? 'none' : 'final');
  const halftimeSeen = useRef(false);

  const advance = () => {
    if (shown >= plays.length) return;
    const next = shown + 1;
    setShown(next);
    const last = plays[next - 1];
    const after = plays[next];
    if (!halftimeSeen.current && isPlay(last) && isPlay(after) && last.quarter === 2 && after.quarter === 3) {
      halftimeSeen.current = true;
      setPlaying(false);
      setPause('halftime');
    } else if (next >= plays.length) {
      setPlaying(false);
      setPause('final');
    }
  };

  useEffect(() => {
    if (!playing || pause !== 'none' || shown >= plays.length) return;
    const timer = window.setTimeout(advance, speed);
    return () => window.clearTimeout(timer);
  });

  const resume = () => { setPause('none'); setPlaying(true); };
  return {
    shown, playing, speed, pause,
    setSpeed,
    toggle: () => (pause === 'halftime' ? resume() : shown < plays.length && setPlaying((p) => !p)),
    step: () => { if (pause === 'halftime') setPause('none'); advance(); },
    skip: () => { halftimeSeen.current = true; setShown(plays.length); setPlaying(false); setPause('final'); },
    resume,
  };
};

const GameFlow: React.FC<{ plays: PlayEvent[]; home: string; away: string; totalSeconds: number }> = ({ plays, home, away, totalSeconds }) => {
  const points = plays.filter((p) => p.score).map((p) => ({ x: elapsedSeconds(p), m: (p.score![home] ?? 0) - (p.score![away] ?? 0) }));
  const range = Math.max(FLOW_MIN_RANGE, ...points.map((p) => Math.abs(p.m)));
  const mid = FLOW_H / 2;
  const px = (s: number) => (s / totalSeconds) * FLOW_W;
  const py = (m: number) => mid - (m / range) * (mid - 6);
  const line = [{ x: 0, m: 0 }, ...points].map((p, i) => `${i ? 'L' : 'M'}${px(p.x).toFixed(1)},${py(p.m).toFixed(1)}`).join(' ');
  const end = points.at(-1);
  const area = end ? `${line} L${px(end.x).toFixed(1)},${mid} Z` : '';
  const quarterLines = [1, 2, 3].map((q) => px(q * 12 * 60));

  return (
    <svg className="cl-flow-svg" viewBox={`0 0 ${FLOW_W} ${FLOW_H}`} role="img" aria-label={`Game flow: ${nickname(home)} ahead above the line, ${nickname(away)} below`}>
      <defs>
        <clipPath id="cl-above"><rect x="0" y="0" width={FLOW_W} height={mid} /></clipPath>
        <clipPath id="cl-below"><rect x="0" y={mid} width={FLOW_W} height={mid} /></clipPath>
      </defs>
      {quarterLines.map((x) => <line key={x} x1={x} x2={x} y1="0" y2={FLOW_H} className="cl-flow-grid" />)}
      <line x1="0" x2={FLOW_W} y1={mid} y2={mid} className="cl-flow-axis" />
      {area && <path d={area} className="cl-flow-home" clipPath="url(#cl-above)" />}
      {area && <path d={area} className="cl-flow-away" clipPath="url(#cl-below)" />}
      <path d={line} className="cl-flow-line" />
      {end && <circle cx={px(end.x)} cy={py(end.m)} r="4" className="cl-flow-dot" />}
      <text x="6" y="13" className="cl-flow-label is-home">{getTeamVisuals(home).abbr} ahead</text>
      <text x="6" y={FLOW_H - 5} className="cl-flow-label is-away">{getTeamVisuals(away).abbr} ahead</text>
    </svg>
  );
};

/** Points per period for one team, for the periods reached so far. */
const periodScores = (events: PlayEvent[], team: string) => {
  const reached = events.at(-1)?.quarter ?? 0;
  let before = 0;
  return Array.from({ length: reached }, (_, i) => {
    const end = events.filter((e) => e.quarter === i + 1 && e.score).at(-1)?.score?.[team] ?? before;
    const points = end - before;
    before = end;
    return points;
  });
};

const LineScore: React.FC<{ events: PlayEvent[]; home: string; away: string }> = ({ events, home, away }) => {
  const rows = [{ team: away, q: periodScores(events, away) }, { team: home, q: periodScores(events, home) }];
  const periods = Math.max(4, rows[0].q.length);
  return (
    <table className="cl-linescore">
      <thead>
        <tr><th aria-label="Team" />{Array.from({ length: periods }, (_, i) => <th key={i} scope="col">{periodLabel(i + 1)}</th>)}<th scope="col">T</th></tr>
      </thead>
      <tbody>
        {rows.map((row, r) => {
          const other = rows[1 - r].q;
          return (
            <tr key={row.team}>
              <th scope="row">{getTeamVisuals(row.team).abbr}</th>
              {Array.from({ length: periods }, (_, i) => (
                <td key={i} className={(row.q[i] ?? 0) > (other[i] ?? 0) ? 'is-high' : undefined}>{row.q[i] ?? '–'}</td>
              ))}
              <td className="cl-ls-total">{row.q.reduce((a, b) => a + b, 0)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

const leadersOf = (players: LivePlayerStats[]) => [...players].sort((a, b) => b.pts - a.pts).slice(0, LEADERS_SHOWN);

export const CourtsideLive: React.FC<CourtsideLiveProps> = ({ game, onClose }) => {
  const { home, away, plays } = game;
  const userTeam = useLeagueStore((s) => s.leagueData?.player_team_name ?? null);
  const openPlayerProfile = useLeagueStore((s) => s.openPlayerProfile);
  const playback = usePlayback(plays);
  const [filter, setFilter] = useState<Filter>('all');
  const [boxTab, setBoxTab] = useState<'away' | 'home' | 'matchup'>(userTeam === away ? 'away' : 'home');

  const visible = plays.slice(0, playback.shown);
  const events = visible.filter(isPlay);
  const last = events.at(-1);
  const homeScore = last?.score?.[home] ?? 0;
  const awayScore = last?.score?.[away] ?? 0;
  const lastQuarter = plays.filter(isPlay).at(-1)?.quarter ?? 4;

  const stats = computeLiveBoxScore(visible);
  const awayPlayers = stats.filter((p) => p.team === away);
  const homePlayers = stats.filter((p) => p.team === home);
  const awayTotals = teamTotals(awayPlayers);
  const homeTotals = teamTotals(homePlayers);

  const feed = visible
    .map((entry, index) => ({ entry, index }))
    .filter(({ entry }) => filter === 'all'
      || (isPlay(entry) && (filter === 'scores' ? entry.event_type === 'score' : Boolean(entry.highlight_tag))))
    .reverse();

  const clock = playback.pause === 'final' && playback.shown >= plays.length
    ? { time: 'Final', period: lastQuarter > 4 ? `After ${periodLabel(lastQuarter)}` : 'Full time' }
    : { time: last?.time ?? '12:00', period: last ? (last.quarter <= 4 ? `${ordinal(last.quarter)} quarter` : `Overtime ${last.quarter - 4}`) : '1st quarter' };

  const leader = homeScore === awayScore ? null : homeScore > awayScore ? home : away;
  const topPlayer = [...stats].sort((a, b) => b.pts - a.pts || (b.pts + b.reb + b.ast) - (a.pts + a.reb + a.ast))[0];

  const team = (name: string, side: 'away' | 'home', score: number, totals: typeof homeTotals) => (
    <div className={`cl-team is-${side}`}>
      <span className="cl-disc" style={{ background: getTeamVisuals(name).primaryColor }}>{getTeamVisuals(name).abbr}</span>
      <div className="cl-team-text">
        <b>{name}</b>
        <small>{side === 'away' ? 'Away' : 'Home'} · {pct(totals.fgm, totals.fga)}{totals.fga ? '%' : ''} FG</small>
      </div>
      <div className={`cl-digits${leader === name ? ' is-leading' : ''}`}>{score}</div>
    </div>
  );

  const statsRows = [
    { label: 'Field goal %', a: pct(awayTotals.fgm, awayTotals.fga), h: pct(homeTotals.fgm, homeTotals.fga) },
    { label: '3-point %', a: pct(awayTotals.tpm, awayTotals.tpa), h: pct(homeTotals.tpm, homeTotals.tpa) },
    { label: 'Free throw %', a: pct(awayTotals.ftm, awayTotals.fta), h: pct(homeTotals.ftm, homeTotals.fta) },
    { label: 'Rebounds', a: awayTotals.reb, h: homeTotals.reb },
    { label: 'Assists', a: awayTotals.ast, h: homeTotals.ast },
    { label: 'Steals', a: awayTotals.stl, h: homeTotals.stl },
    { label: 'Blocks', a: awayTotals.blk, h: homeTotals.blk },
    { label: 'Turnovers', a: awayTotals.to, h: homeTotals.to },
  ];

  return (
    <ModalShell
      isOpen
      onClose={onClose}
      title="Courtside Live"
      subtitle={`${away} at ${home} · ${game.label}`}
      icon={<Radio size={20} />}
      maxWidth={1240}
      tall
    >
      <div className="cl-root">
        <div className="cl-board">
          {team(away, 'away', awayScore, awayTotals)}
          <div className="cl-clock">
            <div className="cl-clock-time">{clock.time}</div>
            <div className="cl-clock-period">{clock.period}</div>
          </div>
          {team(home, 'home', homeScore, homeTotals)}
        </div>

        <div className="cl-transport">
          <button type="button" className="cl-btn is-main" onClick={playback.toggle} disabled={playback.pause === 'final'}
            aria-label={playback.playing ? 'Pause' : 'Play'}>{playback.playing ? '❚❚' : '▶'}</button>
          <button type="button" className="cl-btn" onClick={playback.step} disabled={playback.shown >= plays.length}>Next play</button>
          <button type="button" className="cl-btn" onClick={playback.skip} disabled={playback.shown >= plays.length}>Skip to final</button>
          <div className="cl-speed" role="group" aria-label="Speed">
            {SPEEDS.map((s) => (
              <button key={s.label} type="button" aria-pressed={playback.speed === s.ms} onClick={() => playback.setSpeed(s.ms)}>{s.label}</button>
            ))}
          </div>
          <div className="cl-progress" aria-hidden="true"><i style={{ width: `${plays.length ? (playback.shown / plays.length) * 100 : 0}%` }} /></div>
          <span className="cl-count">Play {playback.shown} / {plays.length}</span>
        </div>

        {playback.pause === 'halftime' && (
          <div className="cl-pause">
            <div className="cl-pause-head">
              <div><span className="cl-cap">Halftime</span><b>{nickname(away)} {awayScore}, {nickname(home)} {homeScore}</b></div>
              <button type="button" className="ms-btn ms-btn-primary" onClick={playback.resume}>Start 2nd half</button>
            </div>
            <div className="cl-pause-grid">
              {[{ name: away, players: awayPlayers }, { name: home, players: homePlayers }].map((t) => (
                <div key={t.name} className="cl-paper">
                  <div className="cl-paper-title">{t.name} leaders</div>
                  {leadersOf(t.players).map((p) => (
                    <div key={p.name} className="cl-leader"><span>{p.name}</span><span><b>{p.pts}</b> pts · {p.reb} reb · {p.ast} ast</span></div>
                  ))}
                </div>
              ))}
              <div className="cl-paper">
                <div className="cl-paper-title">First half · {getTeamVisuals(away).abbr} vs {getTeamVisuals(home).abbr}</div>
                {statsRows.filter((r) => ['Field goal %', '3-point %', 'Rebounds', 'Turnovers'].includes(r.label)).map((r) => (
                  <div key={r.label} className="cl-leader"><span>{r.label}</span><span>{r.a} – {r.h}</span></div>
                ))}
              </div>
            </div>
          </div>
        )}

        {playback.pause === 'final' && plays.length > 0 && playback.shown >= plays.length && (
          <div className="cl-pause is-final">
            <div className="cl-pause-head">
              <div>
                <span className="cl-cap">Final</span>
                <b>{leader ? `${nickname(leader)} win ${Math.max(homeScore, awayScore)}–${Math.min(homeScore, awayScore)}` : `Tied ${homeScore}–${awayScore}`}</b>
                {topPlayer && <small>Player of the game: {topPlayer.name} · {topPlayer.pts} pts, {topPlayer.reb} reb, {topPlayer.ast} ast</small>}
              </div>
              <button type="button" className="ms-btn ms-btn-primary" onClick={onClose}>Close</button>
            </div>
          </div>
        )}

        {plays.length === 0 ? (
          <div className="cl-empty">No play-by-play was recorded for this game.</div>
        ) : (
          <div className="cl-body">
            <section className="cl-paper cl-sheet" aria-label="Play-by-play">
              <div className="cl-sheet-head">
                <span>Play-by-play</span>
                <div className="cl-filters" role="group" aria-label="Show">
                  {(['all', 'scores', 'highlights'] as Filter[]).map((f) => (
                    <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>
                  ))}
                </div>
              </div>
              <div className="cl-feed">
                <table>
                  <tbody>
                    {feed.map(({ entry, index }) => (isPlay(entry) ? (
                      <tr key={index} className={`is-${entry.event_type}${index === playback.shown - 1 ? ' is-latest' : ''}`}>
                        <td className="cl-time">{periodLabel(entry.quarter)} {entry.time}</td>
                        <td className={`cl-tm${entry.team === home ? ' is-home' : ''}`}>{getTeamVisuals(entry.team).abbr}</td>
                        <td className="cl-text">
                          {playLine(entry)}
                          {entry.highlight_tag && <span className="cl-tag">{highlightLabel(entry.highlight_tag)}</span>}
                          {entry.highlight_tag && entry.commentary && <em>{entry.commentary}</em>}
                        </td>
                        <td className="cl-score">
                          {entry.event_type === 'score' && entry.score ? `${entry.score[away] ?? 0}–${entry.score[home] ?? 0}` : ''}
                        </td>
                      </tr>
                    ) : (
                      <tr key={index}><td colSpan={4} className="cl-text">{entry}</td></tr>
                    )))}
                    {feed.length === 0 && <tr><td className="cl-none">Nothing to show yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>

            <aside className="cl-side">
              <div className="cl-flow">
                <div className="cl-flow-head">
                  <span className="cl-cap">Game flow</span>
                  {last?.run_info && <span className="cl-run">{last.run_info.replace(/ for (.+)$/, (_, t) => ` ${nickname(t)}`)}</span>}
                </div>
                <GameFlow plays={events} home={home} away={away} totalSeconds={gameSeconds(lastQuarter)} />
              </div>

              <LineScore events={events} home={home} away={away} />

              <div className="cl-paper cl-box">
                <div className="cl-box-tabs" role="group" aria-label="Box score">
                  <button type="button" aria-pressed={boxTab === 'away'} onClick={() => setBoxTab('away')}>{nickname(away)}</button>
                  <button type="button" aria-pressed={boxTab === 'home'} onClick={() => setBoxTab('home')}>{nickname(home)}</button>
                  <button type="button" aria-pressed={boxTab === 'matchup'} onClick={() => setBoxTab('matchup')}>Matchup</button>
                </div>
                {boxTab === 'matchup' ? (
                  <table className="cl-table">
                    <thead><tr><th scope="col">{getTeamVisuals(away).abbr}</th><th scope="col" /><th scope="col">{getTeamVisuals(home).abbr}</th></tr></thead>
                    <tbody>
                      {statsRows.map((r) => <tr key={r.label}><td>{r.a}</td><td className="cl-label">{r.label}</td><td>{r.h}</td></tr>)}
                    </tbody>
                  </table>
                ) : (
                  <table className="cl-table">
                    <thead>
                      <tr>
                        <th scope="col" className="cl-name">Player</th><th scope="col">Pts</th><th scope="col">Reb</th><th scope="col">Ast</th>
                        <th scope="col">Stl</th><th scope="col">Blk</th><th scope="col">FG</th><th scope="col">3PT</th><th scope="col">TO</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...(boxTab === 'away' ? awayPlayers : homePlayers)].sort((a, b) => b.pts - a.pts).map((p) => (
                        <tr key={p.name}>
                          <td className="cl-name"><button type="button" onClick={() => openPlayerProfile(p.name)}>{p.name}</button></td>
                          <td className="cl-pts">{p.pts}</td><td>{p.reb}</td><td>{p.ast}</td><td>{p.stl}</td><td>{p.blk}</td>
                          <td>{p.fgm}-{p.fga}</td><td>{p.tpm}-{p.tpa}</td><td>{p.to}</td>
                        </tr>
                      ))}
                      {(boxTab === 'away' ? awayPlayers : homePlayers).length === 0 && (
                        <tr><td colSpan={9} className="cl-none">No stats yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>
            </aside>
          </div>
        )}
      </div>
    </ModalShell>
  );
};

function ordinal(n: number) {
  return ['1st', '2nd', '3rd', '4th'][n - 1] ?? `${n}th`;
}
