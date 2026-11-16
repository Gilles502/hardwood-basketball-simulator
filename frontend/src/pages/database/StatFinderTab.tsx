// Stat Finder: search every season in the save (POST /api/database/finder). Presets only fill the form.
import React, { useEffect, useState } from 'react';
import { ROLES } from '../../utils/roles';
import { nickname } from '../../utils/resultSheet';
import { StatTable, type Column } from '../analytics/StatTable';
import { fmt, useAnalyticsData } from '../analytics/useAnalyticsData';
import { FINDER_STATS, statColumns } from './columns';
import type { CareerHit, Condition, DirectoryPayload, FinderPayload, FinderQuery, Preset, SeasonRow } from './types';

const AWARDS = ['MVP', 'Finals MVP', 'DPOY', 'ROY', '6th Man', 'MIP', 'All-NBA 1st', 'All-NBA 2nd', 'All-NBA 3rd',
  'All-Star', 'All-Defensive', 'All-Rookie'];
const STATUSES = ['All', 'Active', 'Free agent', 'Retired', 'Out of league'];
const MAX_CONDITIONS = 4;
const EMPTY: FinderQuery = { mode: 'seasons', kind: 'rs', rank_by: 'pts_pg', desc: true, conditions: [] };
const CAREER_STATS = [{ key: 'seasons', label: 'Seasons' }, { key: 'titles', label: 'Titles' }, { key: 'all_star', label: 'All-Star selections' }];

const statLabel = (key: string) => [...FINDER_STATS, ...CAREER_STATS].find((s) => s.key === key)?.label ?? key;

export const StatFinderTab: React.FC<{ onOpenPlayer: (slug: string, name: string) => void }> = ({ onOpenPlayer }) => {
  const { data: presets } = useAnalyticsData<Preset[]>('/api/database/presets');
  const { data: dir } = useAnalyticsData<DirectoryPayload>('/api/database/players?status=Active');
  const [form, setForm] = useState<FinderQuery>(EMPTY);
  const [preset, setPreset] = useState<string | null>(null);
  const [result, setResult] = useState<FinderPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const run = (query: FinderQuery) => {
    setBusy(true);
    setFailed(false);
    fetch('/api/database/finder', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(query) })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((payload: FinderPayload) => setResult(payload))
      .catch(() => setFailed(true))
      .finally(() => setBusy(false));
  };

  useEffect(() => { run(EMPTY); }, []);

  const set = (patch: Partial<FinderQuery>) => { setForm((f) => ({ ...f, ...patch })); setPreset(null); };
  const conditions = form.conditions ?? [];
  const setCondition = (i: number, patch: Partial<Condition>) =>
    set({ conditions: conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  const careers = form.mode === 'careers';
  const statOptions = careers ? [...FINDER_STATS, ...CAREER_STATS] : FINDER_STATS;
  const pickPreset = (p: Preset) => {
    const query = { ...EMPTY, ...p.query };
    setForm(query);
    setPreset(p.id);
    run(query);
  };

  const field = (label: string, el: React.ReactNode) => <label className="db-field"><span>{label}</span>{el}</label>;
  const num = (key: keyof FinderQuery, placeholder: string) => (
    <input type="number" placeholder={placeholder} value={(form[key] as string | number | undefined) ?? ''}
      onChange={(e) => set({ [key]: e.target.value === '' ? undefined : e.target.value } as Partial<FinderQuery>)} />
  );

  return (
    <div className="an-root">
      {presets && presets.length > 0 && (
        <div className="an-views" role="group" aria-label="Ready-made searches">
          {presets.map((p) => <button key={p.id} type="button" aria-pressed={preset === p.id} onClick={() => pickPreset(p)}>{p.label}</button>)}
        </div>
      )}

      <form className="db-finder" onSubmit={(e) => { e.preventDefault(); run(form); }}>
        <div className="db-finder-row">
          <div className="an-views" role="group" aria-label="Result type">
            <button type="button" aria-pressed={!careers} onClick={() => set({ mode: 'seasons', rank_by: 'pts_pg' })}>Single seasons</button>
            <button type="button" aria-pressed={careers} onClick={() => set({ mode: 'careers', rank_by: 'pts_tot' })}>Careers</button>
          </div>
          <div className="an-views" role="group" aria-label="Season type">
            <button type="button" aria-pressed={form.kind !== 'po'} onClick={() => set({ kind: 'rs' })}>Regular season</button>
            <button type="button" aria-pressed={form.kind === 'po'} onClick={() => set({ kind: 'po' })}>Playoffs</button>
          </div>
        </div>
        <div className="db-finder-grid">
          {field('Years', <span className="db-pair">{num('year_from', 'from')}{num('year_to', 'to')}</span>)}
          {field('Age', <span className="db-pair">{num('age_min', 'min')}{num('age_max', 'max')}</span>)}
          {field('Min games', num('min_gp', 'any'))}
          {field('Team', (
            <select value={form.team ?? ''} onChange={(e) => set({ team: e.target.value || undefined })}>
              <option value="">Any team</option>
              <option value="__user__">My team</option>
              {(dir?.teams ?? []).map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          ))}
          {field('Position', (
            <select value={form.pos ?? ''} onChange={(e) => set({ pos: e.target.value || undefined })}>
              <option value="">Any</option>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          ))}
          {field('Status now', (
            <select value={form.status ?? 'All'} onChange={(e) => set({ status: e.target.value })}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          ))}
          {field('Award that season', (
            <select value={form.award ?? ''} onChange={(e) => set({ award: e.target.value || undefined })}>
              <option value="">Any</option>
              {AWARDS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          ))}
          <label className="db-check"><input type="checkbox" checked={!!form.champion} onChange={(e) => set({ champion: e.target.checked || undefined })} /> Title seasons only</label>
        </div>

        <div className="db-conditions">
          {conditions.map((c, i) => (
            <div key={i} className="db-condition">
              <select aria-label="Stat" value={c.stat} onChange={(e) => setCondition(i, { stat: e.target.value })}>
                {statOptions.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
              <select aria-label="Comparison" value={c.op} onChange={(e) => setCondition(i, { op: e.target.value as Condition['op'] })}>
                <option value=">=">at least</option>
                <option value="<=">at most</option>
              </select>
              <input type="number" aria-label="Value" value={c.value} onChange={(e) => setCondition(i, { value: e.target.value })} />
              <button type="button" className="db-back" aria-label="Remove condition" onClick={() => set({ conditions: conditions.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          {conditions.length < MAX_CONDITIONS && (
            <button type="button" className="db-back" onClick={() => set({ conditions: [...conditions, { stat: 'pts_pg', op: '>=', value: '' }] })}>+ Add a stat condition</button>
          )}
        </div>

        <div className="db-finder-row">
          {field('Rank by', (
            <select value={form.rank_by} onChange={(e) => set({ rank_by: e.target.value })}>
              {statOptions.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          ))}
          {field('Order', (
            <select value={form.desc === false ? 'asc' : 'desc'} onChange={(e) => set({ desc: e.target.value === 'desc' })}>
              <option value="desc">Highest first</option>
              <option value="asc">Lowest first</option>
            </select>
          ))}
          <button type="submit" className="db-search" disabled={busy}>{busy ? 'Searching…' : 'Search'}</button>
          <button type="button" className="db-back" onClick={() => { setForm(EMPTY); setPreset(null); }}>Clear</button>
        </div>
      </form>

      {failed && <p className="db-note">The search could not run. Check the backend is up and try again.</p>}
      {result?.note && <p className="db-note">{result.note}</p>}
      {result && <Results result={result} onOpenPlayer={onOpenPlayer} />}
    </div>
  );
};

const Results: React.FC<{ result: FinderPayload; onOpenPlayer: (slug: string, name: string) => void }> = ({ result, onOpenPlayer }) => {
  const count = <span className="an-count">{result.total > result.rows.length ? `Top ${result.rows.length} of ${result.total}` : `${result.total} found`}</span>;
  if (result.rows.length === 0) return <div className="an-panel"><p className="an-none">Nothing in this save matches that search.</p></div>;
  const rank = result.rank_by;
  if (result.mode === 'careers') {
    const rows = result.rows as CareerHit[];
    const value = (r: CareerHit) => (rank in r ? (r as unknown as Record<string, number>)[rank] : r.career.s[rank] ?? null);
    const columns: Column<CareerHit>[] = [
      { key: 'name', label: 'Player', left: true, keep: true, value: (r) => r.name, format: (_v, r) => <span className="an-name"><b>{r.name}</b></span> },
      { key: 'rank', label: statLabel(rank), keep: true, value, format: (v) => (typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString() : fmt(v)) : '—') },
      { key: 'years', label: 'Years', keep: true, value: (r) => r.first_year, format: (_v, r) => `${r.first_year ?? '—'}–${r.last_year ?? '—'}` },
      { key: 'seasons', label: 'Seasons', keep: true, value: (r) => r.seasons },
      { key: 'gp', label: 'GP', keep: true, value: (r) => r.career.gp },
      { key: 'pts_pg', label: 'PTS', keep: true, value: (r) => r.career.s.pts_pg, format: (v) => fmt(v as number | null) },
      { key: 'reb_pg', label: 'REB', keep: true, value: (r) => r.career.s.reb_pg, format: (v) => fmt(v as number | null) },
      { key: 'ast_pg', label: 'AST', keep: true, value: (r) => r.career.s.ast_pg, format: (v) => fmt(v as number | null) },
      { key: 'titles', label: 'Titles', keep: true, value: (r) => r.titles },
      { key: 'all_star', label: 'All-Star', keep: true, value: (r) => r.all_star },
    ];
    return (
      <div className="an-panel">
        <div className="an-filters db-pad">{count}</div>
        <StatTable<CareerHit> key={`c-${rank}-${result.desc}`} rows={rows} columns={columns} rowKey={(r) => r.slug} defaultSort="rank" defaultAsc={result.desc === false}
          tintTop={101} tintBottom={-1} onSelect={(r) => onOpenPlayer(r.slug, r.name)} caption="Matching careers" />
      </div>
    );
  }
  const rows = result.rows as SeasonRow[];
  const columns: Column<SeasonRow>[] = [
    { key: 'name', label: 'Player', left: true, keep: true, value: (r) => r.name,
      format: (_v, r) => <span className="an-name"><b>{r.name}</b>{r.line.champion && ' 🏆'}{r.line.awards.slice(0, 2).map((a) => <span key={a} className="an-tag">{a}</span>)}</span> },
    { key: 'year', label: 'Season', keep: true, value: (r) => r.line.year },
    { key: 'team', label: 'Team', left: true, keep: true, value: (r) => r.line.team, format: (_v, r) => (r.line.team ? nickname(r.line.team) : '—') },
    { key: 'age', label: 'Age', keep: true, value: (r) => r.line.age },
    { key: 'rank', label: statLabel(rank), keep: true, value: (r) => r.line.s[rank] ?? null, format: (v) => (typeof v === 'number' ? fmt(v) : '—') },
    ...statColumns<SeasonRow>('pg', (r) => r.line.s).filter((c) => c.key !== rank),
  ];
  return (
    <div className="an-panel">
      <div className="an-filters db-pad">{count}</div>
      <StatTable<SeasonRow> key={`s-${rank}-${result.desc}`} rows={rows} columns={columns} rowKey={(r) => `${r.slug}-${r.line.season}-${r.line.team}`}
        defaultSort="rank" defaultAsc={result.desc === false} tintTop={101} tintBottom={-1} onSelect={(r) => onOpenPlayer(r.slug, r.name)} caption="Matching seasons" />
    </div>
  );
};
