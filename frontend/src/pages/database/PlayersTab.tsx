// Players: the directory of everyone in the save, filtered, sorted and paged on the server (/api/database/players).
import React, { useEffect, useState } from 'react';
import { ROLES } from '../../utils/roles';
import { fmt, useAnalyticsData } from '../analytics/useAnalyticsData';
import { money } from './columns';
import type { DirectoryPayload, DirectoryRow, Status } from './types';

const STATUSES: (Status | 'All')[] = ['All', 'Active', 'Free agent', 'Retired', 'Out of league'];

interface Col { key: string; label: string; left?: boolean; render: (r: DirectoryRow) => React.ReactNode }

const statusCell = (r: DirectoryRow) => {
  if (r.status === 'Active') return r.team ?? '—';
  if (r.status === 'Retired') return <span className="an-muted">Retired{r.last_year ? ` ${r.last_year}` : ''}</span>;
  if (r.status === 'Free agent') return <span className="db-fa">Free agent</span>;
  return <span className="an-muted">Out of league{r.team ? ` · last ${r.team}` : ''}</span>;
};

const COLS: Col[] = [
  { key: 'team', label: 'Team / status', left: true, render: statusCell },
  { key: 'pos', label: 'Pos', render: (r) => r.pos ?? '—' },
  { key: 'age', label: 'Age', render: (r) => r.age ?? '—' },
  { key: 'ovr', label: 'OVR', render: (r) => (r.ovr === null ? '—' : <b>{r.ovr}</b>) },
  { key: 'pot', label: 'POT', render: (r) => r.pot ?? '—' },
  { key: 'salary', label: 'Contract', render: (r) => money(r.salary, r.years) },
  { key: 'seasons', label: 'Seasons', render: (r) => r.seasons },
  { key: 'gp', label: 'GP', render: (r) => r.gp },
  { key: 'pts_pg', label: 'PPG', render: (r) => fmt(r.pts_pg) },
  { key: 'reb_pg', label: 'RPG', render: (r) => fmt(r.reb_pg) },
  { key: 'ast_pg', label: 'APG', render: (r) => fmt(r.ast_pg) },
  { key: 'titles', label: 'Titles', render: (r) => (r.titles ? `🏆 ${r.titles}` : '—') },
];

/** Text columns sort A→Z first, numbers high→low first. */
const TEXT_SORTS = new Set(['name', 'team', 'pos', 'status']);

export const PlayersTab: React.FC<{ onOpenPlayer: (slug: string, name: string) => void }> = ({ onOpenPlayer }) => {
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<Status | 'All'>('Active');
  const [pos, setPos] = useState('');
  const [team, setTeam] = useState('');
  const [sort, setSort] = useState({ key: 'ovr', desc: true });
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = window.setTimeout(() => { setQ(text.trim()); setPage(1); }, 250);
    return () => window.clearTimeout(t);
  }, [text]);

  const params = new URLSearchParams({ status, sort: sort.key, desc: sort.desc ? '1' : '0', page: String(page) });
  if (q) params.set('q', q);
  if (pos) params.set('pos', pos);
  if (team) params.set('team', team);
  const { data, failed } = useAnalyticsData<DirectoryPayload>(`/api/database/players?${params.toString()}`);
  const [last, setLast] = useState<DirectoryPayload | null>(null);
  useEffect(() => { if (data) setLast(data); }, [data]);
  const shown = data ?? last;

  const onSort = (key: string) => {
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: !TEXT_SORTS.has(key) }));
    setPage(1);
  };
  const filter = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };

  if (!shown && failed) return <div className="an-empty"><h2>The database could not be loaded</h2></div>;
  if (!shown) return <div className="an-loading"><div className="spinner"></div></div>;

  const header = (key: string, label: string, left?: boolean) => (
    <th key={key} scope="col" className={left ? 'is-left' : undefined}
      aria-sort={sort.key === key ? (sort.desc ? 'descending' : 'ascending') : undefined}>
      <button type="button" onClick={() => onSort(key)}>{label}{sort.key === key && (sort.desc ? ' ▾' : ' ▴')}</button>
    </th>
  );

  return (
    <div className="an-root">
      <div className="an-views" role="group" aria-label="Status">
        {STATUSES.map((s) => (
          <button key={s} type="button" aria-pressed={status === s} onClick={() => filter(setStatus)(s)}>
            {s === 'All' ? 'All' : s === 'Free agent' ? 'Free agents' : s}
            {s !== 'All' && <span className="db-count">{shown.counts[s] ?? 0}</span>}
          </button>
        ))}
      </div>

      <div className="an-filters">
        <input type="search" placeholder="Find player…" aria-label="Find player" value={text} onChange={(e) => setText(e.target.value)} />
        <select aria-label="Position" value={pos} onChange={(e) => filter(setPos)(e.target.value)}>
          <option value="">All positions</option>
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select aria-label="Team" value={team} onChange={(e) => filter(setTeam)(e.target.value)}>
          <option value="">All teams</option>
          {shown.teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="an-count">{shown.total} player{shown.total === 1 ? '' : 's'}</span>
      </div>

      <div className="an-panel">
        {shown.rows.length === 0 ? <p className="an-none">No player matches these filters.</p> : (
          <table className="an-table">
            <caption className="an-sr">Players in this save</caption>
            <thead>
              <tr>{header('name', 'Player', true)}{COLS.map((c) => header(c.key, c.label, c.left))}</tr>
            </thead>
            <tbody>
              {shown.rows.map((r) => (
                <tr key={r.slug} className="is-pick" tabIndex={0} onClick={() => onOpenPlayer(r.slug, r.name)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenPlayer(r.slug, r.name); } }}>
                  <td className="is-left">
                    <span className="an-name"><b>{r.name}</b>{r.highlights.map((h) => <span key={h} className="an-tag">{h}</span>)}</span>
                  </td>
                  {COLS.map((c) => <td key={c.key} className={c.left ? 'is-left' : undefined}>{c.render(r)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {shown.pages > 1 && (
        <div className="db-pager">
          <button type="button" disabled={shown.page <= 1} onClick={() => setPage(shown.page - 1)}>← Prev</button>
          <span>Page {shown.page} of {shown.pages}</span>
          <button type="button" disabled={shown.page >= shown.pages} onClick={() => setPage(shown.page + 1)}>Next →</button>
        </div>
      )}
    </div>
  );
};
