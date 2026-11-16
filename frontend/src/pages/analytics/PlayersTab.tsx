// Players tab (mockup "C + B"): leaders strip + full sortable table; pressing a player opens his scouting card on the
// right (league percentiles, shooting profile, jump to Splits & Logs). Payload from /api/analytics/players.
import React, { useEffect, useMemo, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { ROLES } from '../../utils/roles';
import { nickname } from '../../utils/resultSheet';
import { LeadersStrip, type LeaderTile } from './LeadersStrip';
import { PercentileBars } from './PercentileBars';
import { StatTable, type Column } from './StatTable';
import type { PlayerRow, PlayersPayload } from './types';
import { fmt, fmtSigned, useAnalyticsData } from './useAnalyticsData';
import type { SeasonKind } from '../Analytics';

type View = 'pg' | 'tot' | '36' | '100' | 'shooting' | 'rebounding' | 'advanced' | 'clutch' | 'impact';

const VIEWS: { id: View; label: string }[] = [
  { id: 'pg', label: 'Per game' }, { id: 'tot', label: 'Totals' }, { id: '36', label: 'Per 36' }, { id: '100', label: 'Per 100' },
  { id: 'shooting', label: 'Shooting' }, { id: 'rebounding', label: 'Rebounding' }, { id: 'advanced', label: 'Advanced' },
  { id: 'clutch', label: 'Clutch' }, { id: 'impact', label: 'Impact' },
];

const stat = (key: string, label: string, opts: Partial<Column<PlayerRow>> & { digits?: number; signed?: boolean; pctKey?: string } = {}): Column<PlayerRow> => ({
  key, label,
  value: (r) => r.s[key] ?? null,
  format: (v) => (typeof v === 'number' ? (opts.signed ? fmtSigned(v, opts.digits ?? 1) : fmt(v, opts.digits ?? 1)) : '—'),
  pct: opts.pctKey ? (r) => r.pct[opts.pctKey as string] ?? null : undefined,
  ...opts,
});

const countingCols = (suffix: string, digits: number): Column<PlayerRow>[] => [
  stat('gp', 'GP', { digits: 0, keep: true }),
  suffix === '_tot' ? stat('min', 'MIN', { digits: 0 }) : stat('mpg', 'MIN', { keep: true }),
  stat(`pts${suffix}`, 'PTS', { digits, keep: true, pctKey: suffix === '_pg' ? 'pts_pg' : undefined }),
  stat(`reb${suffix}`, 'REB', { digits, keep: true, pctKey: suffix === '_pg' ? 'reb_pg' : undefined }),
  stat(`ast${suffix}`, 'AST', { digits, keep: true }),
  stat(`stl${suffix}`, 'STL', { digits, pctKey: suffix === '_pg' ? 'stl_pg' : undefined }),
  stat(`blk${suffix}`, 'BLK', { digits, pctKey: suffix === '_pg' ? 'blk_pg' : undefined }),
  stat(`to${suffix}`, 'TO', { digits }),
  stat('fg_pct', 'FG%'), stat('tp_pct', '3P%'), stat('ft_pct', 'FT%'),
  stat('ts_pct', 'TS%', { keep: true, pctKey: 'ts_pct' }),
];

const COLUMNS: Record<View, Column<PlayerRow>[]> = {
  pg: countingCols('_pg', 1),
  tot: countingCols('_tot', 0),
  '36': countingCols('_36', 1),
  '100': countingCols('_100', 1),
  shooting: [
    stat('fgm_tot', 'FGM', { digits: 0 }), stat('fga_tot', 'FGA', { digits: 0, keep: true }), stat('fg_pct', 'FG%', { keep: true }),
    stat('two_pct', '2P%'), stat('tpm_tot', '3PM', { digits: 0 }), stat('tpa_tot', '3PA', { digits: 0 }),
    stat('tp_pct', '3P%', { keep: true }), stat('ftm_tot', 'FTM', { digits: 0 }), stat('fta_tot', 'FTA', { digits: 0 }),
    stat('ft_pct', 'FT%'), stat('efg_pct', 'eFG%', { keep: true }), stat('ts_pct', 'TS%', { keep: true, pctKey: 'ts_pct' }),
    stat('tpa_rate', '3PA RATE', { title: 'Share of shots that are threes' }), stat('ft_rate', 'FT RATE', { title: 'FTA per FGA' }),
    stat('rim_fga_pg', 'CLOSE FGA', { title: 'Close shots (at the rim, in the paint, post-ups) per game. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('rim_fg_pct', 'CLOSE%', { title: 'FG% on close shots. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('mid_fg_pct', 'MID%', { title: 'FG% on 2-point jumpers. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('mid_rate', 'MID RATE', { title: 'Share of shots that are 2-point jumpers. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('ast_fgm_pct', "AST'D%", { title: 'Share of his made shots that were assisted. Counted from games played since the 2026-11-15 update; empty for older games' }),
  ],
  rebounding: [
    stat('gp', 'GP', { digits: 0, keep: true }), stat('mpg', 'MIN', { keep: true }),
    stat('reb_pg', 'REB', { keep: true, pctKey: 'reb_pg' }),
    stat('oreb_pg', 'OREB', { keep: true, title: 'Offensive rebounds per game. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('dreb_pg', 'DREB', { keep: true, title: 'Defensive rebounds per game. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('orb_pct', 'ORB%', { keep: true, title: 'Share of available offensive rebounds he grabbed while on court. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('drb_pct', 'DRB%', { keep: true, title: 'Share of available defensive rebounds he grabbed while on court. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('oreb_tot', 'OREB TOT', { digits: 0 }), stat('dreb_tot', 'DREB TOT', { digits: 0 }),
  ],
  clutch: [
    stat('gp', 'GP', { digits: 0, keep: true }),
    stat('clutch_min', 'CLUTCH MIN', { keep: true, title: 'Minutes in the clutch: 4th quarter or OT, last 5 minutes, score within 5. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('clutch_pts_tot', 'CLUTCH PTS', { digits: 0, keep: true, title: 'Points in the clutch. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('clutch_pts_pg', 'PTS / G', { title: 'Clutch points per game. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('clutch_fg_pct', 'CLUTCH FG%', { keep: true, title: 'FG% in the clutch. Counted from games played since the 2026-11-15 update; empty for older games' }),
    stat('pts_pg', 'PTS', { pctKey: 'pts_pg' }), stat('ts_pct', 'TS%', { pctKey: 'ts_pct' }),
  ],
  advanced: [
    stat('gp', 'GP', { digits: 0 }), stat('mpg', 'MIN'),
    stat('usg_pct', 'USG%', { keep: true, pctKey: 'usg_pct', title: 'Share of team plays used while on court' }),
    stat('ts_pct', 'TS%', { keep: true, pctKey: 'ts_pct' }), stat('efg_pct', 'eFG%'),
    stat('ast_pct', 'AST%', { keep: true, pctKey: 'ast_pct', title: 'Share of teammate baskets he assisted while on court' }),
    stat('ato', 'A/TO', { digits: 2, pctKey: 'ato' }),
    stat('per', 'PER (est.)', { keep: true, title: 'Hollinger PER, estimated: league average 15' }),
    stat('gmsc', 'GmSc', { keep: true, pctKey: 'gmsc', title: 'Game Score per game' }),
    stat('pm_pg', '+/-', { signed: true, pctKey: 'pm_pg', title: 'On-court plus/minus per game' }),
  ],
  impact: [
    stat('gp', 'GP', { digits: 0, keep: true }), stat('mpg', 'MIN', { keep: true }),
    stat('gmsc', 'GmSc', { keep: true, pctKey: 'gmsc' }), stat('per', 'PER (est.)', { keep: true }),
    stat('pm_pg', '+/- PER GAME', { signed: true, keep: true, pctKey: 'pm_pg' }), stat('pm_tot', '+/- TOTAL', { signed: true, digits: 0 }),
    stat('pts_pg', 'PTS', { pctKey: 'pts_pg' }), stat('usg_pct', 'USG%', { pctKey: 'usg_pct' }),
  ],
};

// Leader tiles per view: (label, stat key, digits, suffix)
const TILES: Record<View, [string, string, number, string][]> = {
  pg: [['Points', 'pts_pg', 1, ''], ['Rebounds', 'reb_pg', 1, ''], ['Assists', 'ast_pg', 1, ''], ['Steals', 'stl_pg', 1, ''], ['Blocks', 'blk_pg', 1, ''], ['True shooting', 'ts_pct', 1, '%']],
  tot: [['Points', 'pts_tot', 0, ''], ['Rebounds', 'reb_tot', 0, ''], ['Assists', 'ast_tot', 0, ''], ['Steals', 'stl_tot', 0, ''], ['Blocks', 'blk_tot', 0, ''], ['Minutes', 'min', 0, '']],
  '36': [['Points / 36', 'pts_36', 1, ''], ['Rebounds / 36', 'reb_36', 1, ''], ['Assists / 36', 'ast_36', 1, ''], ['Steals / 36', 'stl_36', 1, ''], ['Blocks / 36', 'blk_36', 1, ''], ['True shooting', 'ts_pct', 1, '%']],
  '100': [['Points / 100', 'pts_100', 1, ''], ['Rebounds / 100', 'reb_100', 1, ''], ['Assists / 100', 'ast_100', 1, ''], ['Steals / 100', 'stl_100', 1, ''], ['Blocks / 100', 'blk_100', 1, ''], ['True shooting', 'ts_pct', 1, '%']],
  shooting: [['True shooting', 'ts_pct', 1, '%'], ['eFG%', 'efg_pct', 1, '%'], ['3P%', 'tp_pct', 1, '%'], ['Threes made', 'tpm_tot', 0, ''], ['Close FG%', 'rim_fg_pct', 1, '%'], ['Mid-range FG%', 'mid_fg_pct', 1, '%']],
  rebounding: [['Rebounds', 'reb_pg', 1, ''], ['Offensive', 'oreb_pg', 1, ''], ['Defensive', 'dreb_pg', 1, ''], ['ORB%', 'orb_pct', 1, '%'], ['DRB%', 'drb_pct', 1, '%'], ['Offensive total', 'oreb_tot', 0, '']],
  clutch: [['Clutch points', 'clutch_pts_tot', 0, ''], ['Clutch PPG', 'clutch_pts_pg', 1, ''], ['Clutch FG%', 'clutch_fg_pct', 1, '%'], ['Clutch minutes', 'clutch_min', 1, ''], ['Points', 'pts_pg', 1, ''], ['True shooting', 'ts_pct', 1, '%']],
  advanced: [['Points', 'pts_pg', 1, ''], ['True shooting', 'ts_pct', 1, '%'], ['Usage', 'usg_pct', 1, '%'], ['Assist %', 'ast_pct', 1, '%'], ['Game Score', 'gmsc', 1, ''], ['On-court +/-', 'pm_pg', 1, '±']],
  impact: [['Game Score', 'gmsc', 1, ''], ['PER (est.)', 'per', 1, ''], ['On-court +/-', 'pm_pg', 1, '±'], ['Total +/-', 'pm_tot', 0, '±'], ['Minutes', 'min', 0, ''], ['Usage', 'usg_pct', 1, '%']],
};

const lastName = (name: string) => name.split(' ').slice(1).join(' ') || name;

interface PlayersTabProps {
  kind: SeasonKind;
  onOpenSplits: (name: string) => void;
}

export const PlayersTab: React.FC<PlayersTabProps> = ({ kind, onOpenSplits }) => {
  const { openPlayerProfile } = useLeagueStore();
  const { data, failed } = useAnalyticsData<PlayersPayload>(`/api/analytics/players?kind=${kind}`);
  const [view, setView] = useState<View>('pg');
  const [team, setTeam] = useState('');
  const [pos, setPos] = useState('');
  const [everyone, setEveryone] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelected(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected]);

  const players = useMemo(() => data?.players ?? [], [data]);
  const teams = useMemo(() => [...new Set(players.map((p) => p.team))].sort(), [players]);
  const rows = useMemo(() => players.filter((p) =>
    (everyone || p.qualified) && (!team || p.team === team) && (!pos || p.pos === pos)
    && (!query || p.name.toLowerCase().includes(query.trim().toLowerCase()))), [players, everyone, team, pos, query]);

  if (!data && !failed) return <div className="an-loading"><div className="spinner"></div></div>;
  if (!data) return <div className="an-empty"><h2>Player stats could not be loaded</h2></div>;
  if (data.meta.games === 0) return kind === 'po'
    ? <div className="an-empty"><h2>No playoff games yet this season</h2><p>Playoff numbers appear here as soon as the first playoff game is played.</p></div>
    : <div className="an-empty"><h2>No games played yet this season</h2><p>Every number here comes from the season's box scores. Play a few games and come back.</p></div>;

  const meta = data.meta;
  const qualified = players.filter((p) => p.qualified);
  const tiles: LeaderTile[] = TILES[view].map(([label, key, digits, suffix]) => ({
    label,
    items: [...qualified].filter((p) => p.s[key] !== null)
      .sort((a, b) => (b.s[key] as number) - (a.s[key] as number)).slice(0, meta.leaders_per_tile)
      .map((p) => ({ name: p.name, short: lastName(p.name),
        value: suffix === '±' ? fmtSigned(p.s[key], digits) : `${fmt(p.s[key], digits)}${suffix}` })),
  }));
  const card = selected ? players.find((p) => p.name === selected) ?? null : null;

  const nameCol: Column<PlayerRow> = {
    key: 'name', label: 'Player', left: true, keep: true,
    value: (r) => r.name,
    format: (_v, r) => (
      <span className="an-name">
        <b>{r.name}</b> <span className="an-team-short">{nickname(r.team)}</span>
        {r.teams.length > 1 && <span className="an-tag">{r.teams.length} teams</span>}
        {!r.in_league && <span className="an-tag is-gone">left the league</span>}
      </span>
    ),
  };
  const posCol: Column<PlayerRow> = { key: 'pos', label: 'Pos', value: (r) => r.pos };

  return (
    <div className="an-root">
      <div className="an-views" role="group" aria-label="Stat view">
        {VIEWS.map((v) => (
          <button key={v.id} type="button" aria-pressed={view === v.id} onClick={() => setView(v.id)}>{v.label}</button>
        ))}
      </div>

      <LeadersStrip tiles={tiles} onPick={setSelected} />

      <div className="an-filters">
        <select aria-label="Team" value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="">All teams</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select aria-label="Position" value={pos} onChange={(e) => setPos(e.target.value)}>
          <option value="">All positions</option>
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select aria-label="Who to list" value={everyone ? 'all' : 'q'} onChange={(e) => setEveryone(e.target.value === 'all')}>
          <option value="q">Qualified ({Math.round(meta.qualify_gp_share * 100)}% of games, {meta.qualify_mpg} MPG)</option>
          <option value="all">Everyone who played</option>
        </select>
        <input type="search" placeholder="Find player…" aria-label="Find player" value={query} onChange={(e) => setQuery(e.target.value)} />
        <span className="an-count">{qualified.length} qualified · {players.length} played{meta.season ? ` · ${meta.season}` : ''}</span>
      </div>

      <div className={card ? 'an-split' : undefined}>
        <div className="an-panel">
          {rows.length === 0 ? <p className="an-none">No player matches these filters.</p> : (
            <StatTable<PlayerRow> rows={rows} columns={[nameCol, posCol, ...COLUMNS[view]]} rowKey={(r) => r.name}
              defaultSort={COLUMNS[view].find((c) => c.key.startsWith('pts'))?.key ?? COLUMNS[view][2].key}
              key={view} tintTop={meta.tint_top} tintBottom={meta.tint_bottom} selectedKey={selected}
              highlight={(r) => r.is_user_team} onSelect={(r) => setSelected(r.name === selected ? null : r.name)}
              compact={!!card} caption="League players" />
          )}
        </div>
        {card && (
          <aside className="an-card" aria-label={`${card.name} scouting card`}>
            <div className="an-card-top">
              <span className="an-kicker">{card.pos ?? '—'} · {card.team}{card.teams.length > 1 ? ` (also ${card.teams.slice(0, -1).join(', ')})` : ''}</span>
              <button type="button" className="an-close" aria-label="Close card" onClick={() => setSelected(null)}>✕</button>
            </div>
            {card.in_league
              ? <button type="button" className="an-card-name an-link" onClick={() => openPlayerProfile(card.name)}>{card.name}</button>
              : <div className="an-card-name">{card.name} <span className="an-tag is-gone">left the league</span></div>}
            <div className="an-card-line">{card.gp} GP · {fmt(card.s.mpg)} MIN · {fmt(card.s.pts_pg)} / {fmt(card.s.reb_pg)} / {fmt(card.s.ast_pg)}</div>
            <div className="an-card-sub">League percentile {card.qualified ? `(${qualified.length} qualified)` : '— not qualified'}</div>
            <PercentileBars items={[
              { label: 'Scoring', pct: card.pct.pts_pg }, { label: 'True shooting', pct: card.pct.ts_pct },
              { label: 'Usage', pct: card.pct.usg_pct }, { label: 'Playmaking (AST%)', pct: card.pct.ast_pct },
              { label: 'Ball security (A/TO)', pct: card.pct.ato }, { label: 'Rebounding', pct: card.pct.reb_pg },
              { label: 'Steals', pct: card.pct.stl_pg }, { label: 'Blocks', pct: card.pct.blk_pg },
              { label: 'Game Score', pct: card.pct.gmsc }, { label: 'On-court +/-', pct: card.pct.pm_pg },
            ]} />
            <div className="an-card-sub">Shooting profile</div>
            <div className="an-figures">
              {([['FG%', card.s.fg_pct], ['3P%', card.s.tp_pct], ['FT%', card.s.ft_pct], ['3PA rate', card.s.tpa_rate], ['FT rate', card.s.ft_rate]] as const).map(([l, v]) => (
                <div key={l}><b>{fmt(v)}</b><span>{l}</span></div>
              ))}
            </div>
            <div className="an-figures">
              {([['PER (est.)', fmt(card.s.per)], ['GmSc', fmt(card.s.gmsc)], ['USG%', fmt(card.s.usg_pct)], ['+/-', fmtSigned(card.s.pm_pg)]] as const).map(([l, v]) => (
                <div key={l}><b>{v}</b><span>{l}</span></div>
              ))}
            </div>
            <button type="button" className="an-card-btn" onClick={() => onOpenSplits(card.name)}>Open splits &amp; logs →</button>
          </aside>
        )}
      </div>
    </div>
  );
};
