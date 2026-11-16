// Seasons: every player line of one season (/api/database/season), leaders strip on top like League Analytics.
import React, { useMemo, useState } from 'react';
import { ROLES } from '../../utils/roles';
import { nickname } from '../../utils/resultSheet';
import { LeadersStrip, type LeaderTile } from '../analytics/LeadersStrip';
import { StatTable, type Column } from '../analytics/StatTable';
import { fmt, useAnalyticsData } from '../analytics/useAnalyticsData';
import { FULL_ONLY, STAT_VIEWS, statColumns, type StatView } from './columns';
import type { Kind, SeasonPayload, SeasonRow } from './types';

const LEADER_TILES: [string, string, string][] = [
  ['Points', 'pts_pg', ''], ['Rebounds', 'reb_pg', ''], ['Assists', 'ast_pg', ''], ['Steals', 'stl_pg', ''],
  ['Blocks', 'blk_pg', ''], ['Field goal %', 'fg_pct', '%'],
];

const lastName = (name: string) => name.split(' ').slice(1).join(' ') || name;

export const SeasonsTab: React.FC<{ onOpenPlayer: (slug: string, name: string) => void }> = ({ onOpenPlayer }) => {
  const [season, setSeason] = useState<number | null>(null);
  const [kind, setKind] = useState<Kind>('rs');
  const [view, setView] = useState<StatView>('pg');
  const [team, setTeam] = useState('');
  const [pos, setPos] = useState('');
  const [minGp, setMinGp] = useState('');
  const [qualifiedOnly, setQualifiedOnly] = useState(false);
  const path = `/api/database/season?kind=${kind}${season !== null ? `&season=${season}` : ''}`;
  const { data, failed } = useAnalyticsData<SeasonPayload>(path);

  const rows = useMemo(() => (data?.rows ?? []).filter((r) =>
    (!team || r.line.team === team) && (!pos || r.line.pos === pos)
    && (!minGp || r.line.gp >= Number(minGp)) && (!qualifiedOnly || !data?.full || r.qualified)), [data, team, pos, minGp, qualifiedOnly]);
  const teams = useMemo(() => [...new Set((data?.rows ?? []).map((r) => r.line.team).filter((t): t is string => !!t))].sort(), [data]);

  if (!data && !failed) return <div className="an-loading"><div className="spinner"></div></div>;
  if (!data) return <div className="an-empty"><h2>This season could not be loaded</h2></div>;
  if (data.seasons.length === 0) return <div className="an-empty"><h2>No seasons yet</h2><p>Every season played in this save shows up here.</p></div>;

  const full = data.full;
  const activeView = !full && FULL_ONLY.includes(view) ? 'pg' : view;
  const bySlug = (name: string) => data.rows.find((r) => r.name === name);
  const tiles: LeaderTile[] = LEADER_TILES.map(([label, key, sfx]) => ({
    label,
    items: (data.leaders[key] ?? []).map((x) => ({ name: x.name, short: lastName(x.name), value: `${fmt(x.value)}${sfx}` })),
  }));

  const nameCol: Column<SeasonRow> = {
    key: 'name', label: 'Player', left: true, keep: true, value: (r) => r.name,
    format: (_v, r) => (
      <span className="an-name">
        <b>{r.name}</b> <span className="an-team-short">{r.line.team ? nickname(r.line.team) : ''}</span>
        {r.line.champion && <span title="Champion"> 🏆</span>}
        {r.line.awards.slice(0, 3).map((a) => <span key={a} className="an-tag">{a}</span>)}
      </span>
    ),
  };
  const columns: Column<SeasonRow>[] = [
    nameCol,
    { key: 'pos', label: 'Pos', value: (r) => r.line.pos, keep: true },
    { key: 'age', label: 'Age', value: (r) => r.line.age, keep: true },
    { key: 'ovr', label: 'OVR', value: (r) => r.line.ovr, keep: true },
    ...statColumns<SeasonRow>(activeView, (r) => r.line.s),
  ];

  return (
    <div className="an-root">
      <div className="an-filters">
        <select aria-label="Season" value={data.season ?? ''} onChange={(e) => setSeason(Number(e.target.value))}>
          {data.seasons.map((s) => <option key={s.season} value={s.season}>{s.year ?? `Season ${s.season}`}{s.full ? ' · full stats' : ''}</option>)}
        </select>
        <div className="an-views" role="group" aria-label="Season type">
          <button type="button" aria-pressed={kind === 'rs'} onClick={() => setKind('rs')}>Regular season</button>
          <button type="button" aria-pressed={kind === 'po'} onClick={() => setKind('po')}>Playoffs</button>
        </div>
        {data.champion && <span className="an-count">🏆 {data.champion}</span>}
      </div>

      <div className="an-views" role="group" aria-label="Stat view">
        {STAT_VIEWS.map((v) => {
          const off = !full && FULL_ONLY.includes(v.id);
          return (
            <button key={v.id} type="button" aria-pressed={activeView === v.id} disabled={off}
              title={off ? 'Not saved for this season' : undefined} onClick={() => setView(v.id)}>{v.label}</button>
          );
        })}
      </div>

      {rows.length > 0 && <LeadersStrip tiles={tiles} onPick={(name) => { const r = bySlug(name); if (r) onOpenPlayer(r.slug, r.name); }} />}

      <div className="an-filters">
        <select aria-label="Team" value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="">All teams</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select aria-label="Position" value={pos} onChange={(e) => setPos(e.target.value)}>
          <option value="">All positions</option>
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <input type="number" min={0} placeholder="Min games" aria-label="Minimum games" value={minGp} onChange={(e) => setMinGp(e.target.value)} />
        <label className="db-check" title={full ? undefined : 'Needs minutes, saved for seasons played from now on'}>
          <input type="checkbox" checked={qualifiedOnly && full} disabled={!full} onChange={(e) => setQualifiedOnly(e.target.checked)} /> Qualified only
        </label>
        <span className="an-count">{rows.length} of {data.rows.length} players</span>
      </div>

      <div className="an-panel">
        {rows.length === 0 ? <p className="an-none">{data.rows.length ? 'No player matches these filters.' : 'Nobody played in this part of the season.'}</p> : (
          <StatTable<SeasonRow> key={`${data.season}-${kind}-${activeView}`} rows={rows} columns={columns}
            rowKey={(r) => `${r.slug}-${r.line.team}`} defaultSort={activeView === 'tot' ? 'pts_tot' : activeView === 'adv' ? 'per' : `pts_${activeView === 'pg' ? 'pg' : activeView}`}
            tintTop={101} tintBottom={-1} highlight={(r) => !!data.user_team && r.line.team === data.user_team}
            onSelect={(r) => onOpenPlayer(r.slug, r.name)} caption={`Player lines, ${data.year ?? ''}`} />
        )}
      </div>
    </div>
  );
};
