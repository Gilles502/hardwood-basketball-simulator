// The one result sheet for every finished game: calendar, matchday hub, playoff series and play-in.
import React, { useEffect, useState } from 'react';
import { ClipboardList } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useLeagueStore } from '../store/leagueStore';
import { getTeamVisuals } from '../utils/teamVisuals';
import {
  nickname, pct, seriesStatus, sheetFromSeriesGame, signed, topPerformerOf, winnerOf,
} from '../utils/resultSheet';
import type { SeriesLog, SheetPayload, SheetPlayer, SheetTeam } from '../utils/resultSheet';
import './ResultSheet.css';

const HOT_POINTS = 25;
const FOUL_TROUBLE = 5;

interface GamePreview {
  home_team: string;
  away_team: string;
}

type ResultSheetProps = { onClose: () => void } & (
  | { gameId: string; preview?: GamePreview; series?: never; label?: never; winsNeeded?: never }
  /** `label` names the round ("East semifinals"); `winsNeeded` is 1 for a play-in game. */
  | { series: SeriesLog; label: string; winsNeeded: number; gameId?: never; preview?: never }
);

const formatDate = (iso?: string) => {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
};

const totalsOf = (team: SheetTeam) => {
  const sum = (key: keyof SheetPlayer) => team.players.reduce((acc, p) => acc + (Number(p[key]) || 0), 0);
  return {
    min: Math.round(sum('min')), reb: sum('reb'), ast: sum('ast'), stl: sum('stl'), blk: sum('blk'),
    to: team.players.some((p) => p.to === null) ? null : sum('to'), pf: sum('pf'),
    fgm: sum('fgm'), fga: sum('fga'), tpm: sum('tpm'), tpa: sum('tpa'), ftm: sum('ftm'), fta: sum('fta'),
  };
};

/** Loads a calendar game's sheet from the server; does nothing for series games. */
const useCalendarSheet = (gameId?: string) => {
  const [sheet, setSheet] = useState<SheetPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!gameId) return;
    let alive = true;
    setSheet(null);
    setError(null);
    fetch(`/api/calendar/box_score/${encodeURIComponent(gameId)}?_t=${Date.now()}`)
      .then((res) => res.json())
      .then((json) => {
        if (!alive) return;
        if (json.success && json.box_score) setSheet(json.box_score);
        else setError(json.error || 'This result sheet is not available.');
      })
      .catch(() => alive && setError('Could not load the result sheet.'));
    return () => { alive = false; };
  }, [gameId]);

  return { sheet, error };
};

const LineScore: React.FC<{ sheet: SheetPayload }> = ({ sheet }) => {
  const { away_team: away, home_team: home } = sheet;
  const periods = Math.max(away.quarters.length, home.quarters.length, 4);
  const row = (team: SheetTeam, other: SheetTeam) => (
    <tr className={team === winnerOf(sheet) ? 'is-winner' : undefined}>
      <th scope="row">{getTeamVisuals(team.name).abbr}</th>
      {Array.from({ length: periods }, (_, i) => (
        <td key={i} className={(team.quarters[i] ?? 0) > (other.quarters[i] ?? 0) ? 'is-high' : undefined}>{team.quarters[i] ?? '–'}</td>
      ))}
      <td className="rs-ls-total">{team.score}</td>
    </tr>
  );
  return (
    <table className="rs-linescore">
      <thead>
        <tr>
          <th aria-label="Team" />
          {Array.from({ length: periods }, (_, i) => <th key={i} scope="col">{i < 4 ? `Q${i + 1}` : `OT${i - 3}`}</th>)}
          <th scope="col">T</th>
        </tr>
      </thead>
      <tbody>{row(away, home)}{row(home, away)}</tbody>
    </table>
  );
};

const Comparison: React.FC<{ sheet: SheetPayload }> = ({ sheet }) => {
  const { away_team: away, home_team: home } = sheet;
  const a = totalsOf(away);
  const h = totalsOf(home);
  const rows: { label: string; away: number; home: number; isPct?: boolean; lowerIsBetter?: boolean }[] = [
    { label: 'Field goal %', away: a.fga ? a.fgm / a.fga * 100 : 0, home: h.fga ? h.fgm / h.fga * 100 : 0, isPct: true },
    { label: '3-point %', away: a.tpa ? a.tpm / a.tpa * 100 : 0, home: h.tpa ? h.tpm / h.tpa * 100 : 0, isPct: true },
    { label: 'Free throw %', away: a.fta ? a.ftm / a.fta * 100 : 0, home: h.fta ? h.ftm / h.fta * 100 : 0, isPct: true },
    { label: 'Rebounds', away: a.reb, home: h.reb },
    { label: 'Assists', away: a.ast, home: h.ast },
    { label: 'Steals', away: a.stl, home: h.stl },
    { label: 'Blocks', away: a.blk, home: h.blk },
    ...(a.to !== null && h.to !== null ? [{ label: 'Turnovers', away: a.to, home: h.to, lowerIsBetter: true }] : []),
  ];
  const show = (v: number, isPct?: boolean) => (isPct ? `${v.toFixed(1)}%` : v);

  return (
    <div className="rs-paper rs-compare">
      <div className="rs-compare-head">
        <span className="is-away">{getTeamVisuals(away.name).abbr}</span><span>Team comparison</span><span className="is-home">{getTeamVisuals(home.name).abbr}</span>
      </div>
      {rows.map((r) => {
        const awayShare = Math.round(r.away / ((r.away + r.home) || 1) * 100);
        const awayBetter = r.lowerIsBetter ? r.away < r.home : r.away > r.home;
        const homeBetter = r.lowerIsBetter ? r.home < r.away : r.home > r.away;
        return (
          <div key={r.label} className="rs-compare-row">
            <b className={awayBetter ? 'is-better' : undefined}>{show(r.away, r.isPct)}</b>
            <div>
              <span>{r.label}</span>
              <div className="rs-compare-track">
                <i className="is-away" style={{ width: `${awayShare}%` }} />
                <i className="is-home" style={{ width: `${100 - awayShare}%` }} />
              </div>
            </div>
            <b className={homeBetter ? 'is-better' : undefined}>{show(r.home, r.isPct)}</b>
          </div>
        );
      })}
    </div>
  );
};

const BoxTable: React.FC<{ team: SheetTeam; onPlayer: (name: string) => void }> = ({ team, onPlayer }) => {
  const t = totalsOf(team);
  const hasLineups = team.players.some((p) => p.is_starter);
  const groups = hasLineups
    ? [{ label: 'Starters', players: team.players.filter((p) => p.is_starter) }, { label: 'Bench', players: team.players.filter((p) => !p.is_starter) }]
    : [{ label: '', players: team.players }];

  const row = (p: SheetPlayer) => {
    const hot = p.pts >= HOT_POINTS;
    return (
      <tr key={p.name}>
        <td className="rs-col-player">
          <i>{p.pos ?? ''}</i>
          <button type="button" className={hot ? 'is-hot' : undefined} onClick={() => onPlayer(p.name)}>{p.name}</button>
        </td>
        <td>{Math.round(p.min)}</td>
        <td className={`rs-pts${hot ? ' is-hot' : ''}`}>{p.pts}</td>
        <td>{p.reb}</td><td>{p.ast}</td><td>{p.stl}</td><td>{p.blk}</td>
        <td>{p.to ?? '–'}</td>
        <td className={p.pf >= FOUL_TROUBLE ? 'is-fouls' : undefined}>{p.pf}</td>
        <td>{p.fgm}-{p.fga}</td><td className="rs-pct">{pct(p.fgm, p.fga)}</td>
        <td>{p.tpm}-{p.tpa}</td><td className="rs-pct">{pct(p.tpm, p.tpa)}</td>
        <td>{p.ftm}-{p.fta}</td><td className="rs-pct">{pct(p.ftm, p.fta)}</td>
        <td className={p.plus_minus > 0 ? 'is-up' : p.plus_minus < 0 ? 'is-down' : undefined}>{signed(p.plus_minus)}</td>
      </tr>
    );
  };

  return (
    <table className="rs-box">
      <thead>
        <tr>
          <th scope="col" className="rs-col-player">Player</th>
          <th scope="col" title="Minutes">Min</th><th scope="col" title="Points">Pts</th>
          <th scope="col" title="Rebounds">Reb</th><th scope="col" title="Assists">Ast</th>
          <th scope="col" title="Steals">Stl</th><th scope="col" title="Blocks">Blk</th>
          <th scope="col" title="Turnovers">TO</th><th scope="col" title="Personal fouls">PF</th>
          <th scope="col" title="Field goals made-attempted">FG</th><th scope="col">FG%</th>
          <th scope="col" title="3-pointers made-attempted">3PT</th><th scope="col">3P%</th>
          <th scope="col" title="Free throws made-attempted">FT</th><th scope="col">FT%</th>
          <th scope="col" title="Plus / minus">+/-</th>
        </tr>
      </thead>
      <tbody>
        {groups.map((group) => (
          <React.Fragment key={group.label || 'all'}>
            {group.label && <tr className="rs-box-section"><td colSpan={16}>{group.label}</td></tr>}
            {group.players.map(row)}
          </React.Fragment>
        ))}
        <tr className="rs-box-totals">
          <td className="rs-col-player">Team totals</td>
          <td>{t.min}</td><td className="rs-pts">{team.score}</td>
          <td>{t.reb}</td><td>{t.ast}</td><td>{t.stl}</td><td>{t.blk}</td><td>{t.to ?? '–'}</td><td>{t.pf}</td>
          <td>{t.fgm}-{t.fga}</td><td className="rs-pct">{pct(t.fgm, t.fga)}</td>
          <td>{t.tpm}-{t.tpa}</td><td className="rs-pct">{pct(t.tpm, t.tpa)}</td>
          <td>{t.ftm}-{t.fta}</td><td className="rs-pct">{pct(t.ftm, t.fta)}</td>
          <td />
        </tr>
      </tbody>
    </table>
  );
};

const SeriesBar: React.FC<{
  series: SeriesLog; label: string; winsNeeded: number; selected: number; perspective: string; onSelect: (index: number) => void;
}> = ({ series, label, winsNeeded, selected, perspective, onSelect }) => {
  const maxGames = winsNeeded * 2 - 1;
  const unplayed = series.winner_nome ? 0 : Math.max(0, maxGames - series.games.length);
  return (
    <div className="rs-series">
      <div className="rs-series-label">
        <span>{label}</span>
        {winsNeeded > 1 && <b>{seriesStatus(series, series.games.length, winsNeeded)}</b>}
      </div>
      {winsNeeded > 1 && (
        <div className="rs-tickets" role="group" aria-label="Games in this series">
          {series.games.map((game, index) => {
            const sheet = sheetFromSeriesGame(game);
            const winner = winnerOf(sheet);
            const loser = winner === sheet.home_team ? sheet.away_team : sheet.home_team;
            return (
              <button
                key={game.game_num}
                type="button"
                className={`rs-ticket ${winner.name === perspective ? 'is-won' : 'is-lost'}`}
                aria-pressed={index === selected}
                onClick={() => onSelect(index)}
              >
                <b>G{game.game_num}</b>
                <small>{getTeamVisuals(winner.name).abbr} {winner.score}–{loser.score}</small>
              </button>
            );
          })}
          {Array.from({ length: unplayed }, (_, i) => (
            <span key={i} className="rs-ticket is-unplayed"><b>G{series.games.length + i + 1}</b><small>Not played</small></span>
          ))}
        </div>
      )}
    </div>
  );
};

export const ResultSheet: React.FC<ResultSheetProps> = (props) => {
  const { onClose, series, label = '', winsNeeded = 1 } = props;
  const userTeam = useLeagueStore((s) => s.leagueData?.player_team_name ?? null);
  const openPlayerProfile = useLeagueStore((s) => s.openPlayerProfile);
  const openTeamProfile = useLeagueStore((s) => s.openTeamProfile);
  const [gameIndex, setGameIndex] = useState(series ? series.games.length - 1 : 0);
  const [teamTab, setTeamTab] = useState<string | null>(null);
  const calendar = useCalendarSheet(props.gameId);

  const seriesGame = series?.games[gameIndex];
  const sheet = seriesGame ? sheetFromSeriesGame(seriesGame) : calendar.sheet;
  const awayName = sheet?.away_team.name ?? props.preview?.away_team ?? '';
  const homeName = sheet?.home_team.name ?? props.preview?.home_team ?? '';

  let body: React.ReactNode;
  if (!sheet) {
    body = <div className="rs-state">{calendar.error ?? 'Loading the result sheet…'}</div>;
  } else {
    const winner = winnerOf(sheet);
    const loser = winner === sheet.home_team ? sheet.away_team : sheet.home_team;
    const teams = [sheet.away_team, sheet.home_team];
    const shown = teams.find((t) => t.name === teamTab)
      ?? teams.find((t) => t.name === userTeam)
      ?? winner;
    const top = topPerformerOf(sheet);
    const overtime = Math.max(sheet.home_team.quarters.length, sheet.away_team.quarters.length) > 4;
    const margin = `${nickname(winner.name)} win by ${winner.score - loser.score}${overtime ? ' in overtime' : ''}`;
    const caption = series && seriesGame
      ? `Final · Game ${seriesGame.game_num}`
      : ['Final', sheet.day_index !== undefined ? `Day ${sheet.day_index + 1}` : '', formatDate(sheet.date)].filter(Boolean).join(' · ');
    const story = series && winsNeeded > 1 ? seriesStatus(series, gameIndex + 1, winsNeeded) : margin;
    const hasPlayers = teams.some((t) => t.players.length > 0);
    const oldPlayoffGame = hasPlayers && teams.every((t) => t.players.every((p) => p.is_starter === undefined));

    body = (
      <div className="rs-layout">
        <aside className="rs-side">
          <div>
            <div className="rs-caption">{caption}</div>
            <h3 className="rs-headline">
              {nickname(winner.name)} <em>{winner.score}</em>, {nickname(loser.name)} {loser.score}
            </h3>
            <p className="rs-story">{story}</p>
          </div>
          <LineScore sheet={sheet} />
          {top && (
            <div className="rs-paper rs-pog">
              <div className="rs-paper-title">Player of the game · {getTeamVisuals(top.team).abbr}</div>
              <button type="button" onClick={() => openPlayerProfile(top.name)}>{top.name}</button>
              <div className="rs-pog-line">
                <div><strong>{top.pts}</strong><span>Pts</span></div>
                <div><strong>{top.reb}</strong><span>Reb</span></div>
                <div><strong>{top.ast}</strong><span>Ast</span></div>
                {top.min !== undefined && <div><strong>{Math.round(top.min)}</strong><span>Min</span></div>}
              </div>
            </div>
          )}
          {hasPlayers && <Comparison sheet={sheet} />}
        </aside>

        <section className="rs-main" aria-label="Box score">
          <div className="rs-folders" role="group" aria-label="Team">
            {teams.map((team) => (
              <button key={team.name} type="button" aria-pressed={team === shown} onClick={() => setTeamTab(team.name)}>
                {team.name}<small>{team.score}</small>
              </button>
            ))}
          </div>
          <div className="rs-paper rs-box-paper">
            {shown.players.length > 0
              ? <BoxTable team={shown} onPlayer={openPlayerProfile} />
              : <p className="rs-empty">Player stats weren't recorded for this game.</p>}
          </div>
          <div className="rs-main-foot">
            <span>{oldPlayoffGame ? 'Older playoff game: starters, positions and turnovers were not recorded.' : ''}</span>
            <button type="button" className="rs-link" onClick={() => openTeamProfile(shown.name)}>{shown.name} profile</button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <ModalShell
      isOpen
      onClose={onClose}
      title="Result sheet"
      subtitle={awayName && homeName ? `${awayName} at ${homeName}` : undefined}
      icon={<ClipboardList size={20} />}
      maxWidth={1180}
      headerExtra={series && (
        <SeriesBar
          series={series}
          label={label}
          winsNeeded={winsNeeded}
          selected={gameIndex}
          perspective={userTeam && [series.s1_nome, series.s2_nome].includes(userTeam) ? userTeam : series.s1_nome}
          onSelect={setGameIndex}
        />
      )}
    >
      {body}
    </ModalShell>
  );
};
