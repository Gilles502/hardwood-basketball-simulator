// Splits & Logs tab (mockup "A — the folder"): pick a player or team; left = cream split tables (splits, months,
// opponents, season highs), right = the full game log (press a game for its result sheet). /api/analytics/splits.
import React, { useMemo, useState } from 'react';
import { ResultSheet } from '../../components/ResultSheet';
import { nickname } from '../../utils/resultSheet';
import type { LogRow, PlayersPayload, SplitRow, SplitsPayload, SplitsTarget, TeamsPayload } from './types';
import { fmt, fmtSigned, useAnalyticsData } from './useAnalyticsData';

const shortDate = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return y && m && d ? new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : iso;
};

type LogSort = 'date' | 'pts' | 'reb' | 'ast' | 'gmsc' | 'pm';

interface SplitsTabProps {
  target: SplitsTarget | null;
  onTarget: (target: SplitsTarget) => void;
}

export const SplitsTab: React.FC<SplitsTabProps> = ({ target, onTarget }) => {
  const players = useAnalyticsData<PlayersPayload>('/api/analytics/players').data;
  const teams = useAnalyticsData<TeamsPayload>('/api/analytics/teams').data;
  const [kind, setKind] = useState<SplitsTarget['kind']>(target?.kind ?? 'player');
  const [query, setQuery] = useState('');
  const [sheet, setSheet] = useState<string | null>(null);
  const [logSort, setLogSort] = useState<{ key: LogSort; asc: boolean }>({ key: 'date', asc: false });

  // Nothing picked: the user's team's top scorer (or the league's).
  const fallback = useMemo<SplitsTarget | null>(() => {
    const list = players?.players ?? [];
    const user = players?.meta.user_team;
    const pick = list.find((p) => p.team === user) ?? list[0];
    return pick ? { kind: 'player', name: pick.name } : null;
  }, [players]);
  const current = target ?? fallback;
  const path = current ? `/api/analytics/splits?${current.kind}=${encodeURIComponent(current.name)}` : null;
  const { data, failed } = useAnalyticsData<SplitsPayload>(path);

  const options = kind === 'player' ? (players?.players ?? []).map((p) => p.name) : (teams?.teams ?? []).map((t) => t.name);
  const choose = (name: string) => {
    if (!options.includes(name)) return;
    setQuery('');
    onTarget({ kind, name });
  };

  if (players && players.meta.games === 0) return <div className="an-empty"><h2>No games played yet this season</h2></div>;

  const log = data ? sortLog(data.log, logSort) : [];
  const split = data?.meta.split_tint ?? 0.06;

  return (
    <div className="an-root">
      <div className="an-filters an-pick">
        <div className="an-views" role="group" aria-label="Look at">
          {(['player', 'team'] as const).map((k) => (
            <button key={k} type="button" aria-pressed={kind === k} onClick={() => { setKind(k); setQuery(''); }}>{k === 'player' ? 'Player' : 'Team'}</button>
          ))}
        </div>
        <input type="search" list="an-pick-list" aria-label={`Find ${kind}`} placeholder={kind === 'player' ? 'Find player…' : 'Find team…'}
          value={query} onChange={(e) => { setQuery(e.target.value); if (options.includes(e.target.value)) choose(e.target.value); }}
          onKeyDown={(e) => { if (e.key === 'Enter') choose(query); }} />
        <datalist id="an-pick-list">{options.map((o) => <option key={o} value={o} />)}</datalist>
        {data && (
          <span className="an-pick-meta">
            <b>{data.name}</b>{data.kind === 'player' ? ` · ${data.pos ?? '—'} · ${data.team}` : ''} · {data.season_line.gp} GP
            {data.kind === 'player'
              ? ` · ${fmt(data.season_line.pts)} / ${fmt(data.season_line.reb)} / ${fmt(data.season_line.ast)} · ${fmt(data.season_line.ts_pct)} TS%`
              : ` · ${data.season_line.w}-${data.season_line.l} · ${fmtSigned(data.season_line.pm)} margin`}
          </span>
        )}
        {data?.meta.season && <span className="an-count">Season {data.meta.season}</span>}
      </div>

      {!current ? <div className="an-empty"><h2>Pick a player or a team</h2></div>
        : !data && !failed ? <div className="an-loading"><div className="spinner"></div></div>
        : !data ? <div className="an-empty"><h2>No games found for {current.name}</h2><p>They have not played a game this season.</p></div>
        : (
          <div className="an-folder">
            <div className="an-stack">
              <SplitTable title="Split" rows={[data.season_line, ...data.splits]} base={data.season_line} team={data.kind === 'team'} share={split} />
              {data.quarters && (
                <div className="an-sheet">
                  <div className="an-kicker">Average margin by quarter</div>
                  <div className="an-figures">{data.quarters.map((q, i) => <div key={i}><b>{fmtSigned(q)}</b><span>Q{i + 1}</span></div>)}</div>
                </div>
              )}
              <SplitTable title="Month" rows={data.months} base={data.season_line} team={data.kind === 'team'} share={split} />
              <SplitTable title="Opponent" rows={data.opponents} base={data.season_line} team={data.kind === 'team'} share={split} short />
              <div className="an-sheet">
                <div className="an-kicker">Season highs</div>
                <div className="an-figures">
                  {data.highs.map((h) => (
                    <button key={h.stat} type="button" className="an-high" onClick={() => setSheet(h.game_id)} title="Open the result sheet">
                      <b>{h.value}</b><span>{h.label}</span><small>{h.home ? 'vs' : '@'} {nickname(h.opp)} · {shortDate(h.date)}</small>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="an-panel an-log">
              <table className="an-table">
                <caption className="an-sr">Game log</caption>
                <thead>
                  <tr>
                    <LogHead k="date" label="Date" sort={logSort} set={setLogSort} left />
                    <th className="is-left" scope="col"><button type="button" disabled>Opp</button></th>
                    <th className="is-left" scope="col"><button type="button" disabled>Result</button></th>
                    {data.kind === 'player' && <th scope="col"><button type="button" disabled>MIN</button></th>}
                    <LogHead k="pts" label="PTS" sort={logSort} set={setLogSort} />
                    <LogHead k="reb" label="REB" sort={logSort} set={setLogSort} />
                    <LogHead k="ast" label="AST" sort={logSort} set={setLogSort} />
                    <th scope="col"><button type="button" disabled>STL</button></th>
                    <th scope="col"><button type="button" disabled>BLK</button></th>
                    <th scope="col"><button type="button" disabled>TO</button></th>
                    <th scope="col"><button type="button" disabled>FG</button></th>
                    <th scope="col"><button type="button" disabled>3P</button></th>
                    <th scope="col"><button type="button" disabled>FT</button></th>
                    <LogHead k="pm" label={data.kind === 'player' ? '+/-' : 'MARGIN'} sort={logSort} set={setLogSort} />
                    {data.kind === 'player' && <LogHead k="gmsc" label="GmSc" sort={logSort} set={setLogSort} />}
                  </tr>
                </thead>
                <tbody>
                  {log.map((r) => <LogLine key={r.game_id} row={r} player={data.kind === 'player'} onOpen={() => setSheet(r.game_id)} />)}
                </tbody>
              </table>
            </div>
          </div>
        )}

      {sheet && <ResultSheet gameId={sheet} onClose={() => setSheet(null)} />}
    </div>
  );
};

function sortLog(rows: LogRow[], sort: { key: LogSort; asc: boolean }): LogRow[] {
  const dir = sort.asc ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (sort.key === 'date') return (a.date.localeCompare(b.date) || a.game_id.localeCompare(b.game_id)) * dir;
    const va = a[sort.key];
    const vb = b[sort.key];
    if (va === null) return vb === null ? 0 : 1;
    if (vb === null) return -1;
    return (va - vb) * dir;
  });
}

const LogHead: React.FC<{ k: LogSort; label: string; sort: { key: LogSort; asc: boolean }; set: (s: { key: LogSort; asc: boolean }) => void; left?: boolean }> = ({ k, label, sort, set, left }) => (
  <th scope="col" className={left ? 'is-left' : undefined} aria-sort={sort.key === k ? (sort.asc ? 'ascending' : 'descending') : undefined}>
    <button type="button" onClick={() => set(sort.key === k ? { key: k, asc: !sort.asc } : { key: k, asc: false })}>
      {label}{sort.key === k && (sort.asc ? ' ▴' : ' ▾')}
    </button>
  </th>
);

const made = (m: number | null, a: number | null) => (m === null || a === null ? '—' : `${m}-${a}`);

const LogLine: React.FC<{ row: LogRow; player: boolean; onOpen: () => void }> = ({ row, player, onOpen }) => {
  const head = (
    <>
      <td className="is-left">{shortDate(row.date)}{row.b2b && <span className="an-tag" title="Second night of a back-to-back">B2B</span>}</td>
      <td className="is-left">{row.home ? 'vs' : '@'} {nickname(row.opp)}</td>
      <td className={`is-left ${row.win ? 'an-win' : 'an-loss'}`}>{row.win ? 'W' : 'L'} {row.score_for}-{row.score_against}</td>
    </>
  );
  if (row.dnp) {
    return (
      <tr className="is-pick is-dnp" onClick={onOpen} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') onOpen(); }}>
        {head}
        <td colSpan={12} className="is-left an-muted">Did not play</td>
      </tr>
    );
  }
  return (
    <tr className="is-pick" onClick={onOpen} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') onOpen(); }}>
      {head}
      {player && <td>{fmt(row.min, 0)}</td>}
      <td className={player && (row.pts ?? 0) >= 40 ? 'is-top' : undefined}>{row.pts}</td>
      <td>{row.reb}</td><td>{row.ast}</td><td>{row.stl}</td><td>{row.blk}</td><td>{row.to}</td>
      <td>{made(row.fgm, row.fga)}</td><td>{made(row.tpm, row.tpa)}</td><td>{made(row.ftm, row.fta)}</td>
      <td>{fmtSigned(row.pm, 0)}</td>{player && <td>{fmt(row.gmsc)}</td>}
    </tr>
  );
};

const SplitTable: React.FC<{ title: string; rows: SplitRow[]; base: SplitRow; team: boolean; share: number; short?: boolean }> = ({ title, rows, base, team, share, short }) => {
  if (rows.length === 0) return null;
  const tint = (v: number | null, b: number | null, isBase: boolean) =>
    isBase || v === null || b === null || !b ? undefined : v > b * (1 + share) ? 'is-up' : v < b * (1 - share) ? 'is-down' : undefined;
  return (
    <div className="an-sheet">
      <table className="an-paper-table">
        <caption className="an-sr">{title}</caption>
        <thead>
          <tr>
            <th className="is-left" scope="col">{title}</th><th scope="col">GP</th>{team ? <th scope="col">W-L</th> : <th scope="col">MIN</th>}
            <th scope="col">PTS</th><th scope="col">REB</th><th scope="col">AST</th><th scope="col">TS%</th><th scope="col">{team ? 'MARGIN' : '+/-'}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isBase = r === base;
            return (
              <tr key={`${r.label}-${i}`} className={isBase ? 'is-base' : undefined}>
                <td className="is-left">{short ? nickname(r.label) : r.label}</td>
                <td>{r.gp}</td>
                <td>{team ? `${r.w}-${r.l}` : fmt(r.min)}</td>
                <td className={tint(r.pts, base.pts, isBase)}>{fmt(r.pts)}</td>
                <td>{fmt(r.reb)}</td><td>{fmt(r.ast)}</td>
                <td className={tint(r.ts_pct, base.ts_pct, isBase)}>{fmt(r.ts_pct)}</td>
                <td>{fmtSigned(r.pm)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
