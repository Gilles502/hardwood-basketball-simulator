// Player page (mockup B "poster header + sections"): header band, then Overview · Stats · Progression · Awards & ranks.
// Payload from /api/database/player/<slug>. A stat the season didn't save shows "—"; estimated totals carry a *.
import React, { useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { fmt, useAnalyticsData } from '../analytics/useAnalyticsData';
import { FULL_ONLY, STAT_DEFS, STAT_VIEWS, formatStat, money, type StatView } from './columns';
import { ProgressionChart } from './ProgressionChart';
import type { CareerLine, Kind, Line, PlayerPayload, Rank } from './types';

type Section = 'overview' | 'stats' | 'progression' | 'awards';

const SECTIONS: { id: Section; label: string }[] = [
  { id: 'overview', label: 'Overview' }, { id: 'stats', label: 'Stats' },
  { id: 'progression', label: 'Progression' }, { id: 'awards', label: 'Awards & ranks' },
];

// Header chips, in this order (counts from career.awards).
const AWARD_ORDER = ['MVP', 'Finals MVP', 'DPOY', 'ROY', '6th Man', 'MIP', 'All-NBA 1st', 'All-NBA 2nd', 'All-NBA 3rd',
  'All-Star', 'All-Defensive', 'All-Rookie', 'All-Star MVP'];

const RANK_LABELS: Record<string, string> = {
  gp: 'games', pts_tot: 'points', reb_tot: 'rebounds', ast_tot: 'assists', stl_tot: 'steals', blk_tot: 'blocks',
  pts_pg: 'points per game', reb_pg: 'rebounds per game', ast_pg: 'assists per game', stl_pg: 'steals per game',
  blk_pg: 'blocks per game',
};

const CHART_STATS: [string, string][] = [['pts_pg', 'PPG'], ['reb_pg', 'RPG'], ['ast_pg', 'APG'], ['stl_pg', 'SPG'], ['blk_pg', 'BPG']];

const ordinal = (n: number) => {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};

const awardChip = (award: string, n: number) => (n > 1 ? `${n}× ${award}` : award);

const triple = (ln: Line | CareerLine) => `${fmt(ln.s.pts_pg)} / ${fmt(ln.s.reb_pg)} / ${fmt(ln.s.ast_pg)}`;

const rankText = (r: Rank) => `${ordinal(r.rank)} in ${RANK_LABELS[r.stat] ?? r.stat}`;

export const PlayerPage: React.FC<{ slug: string; onOpenPlayer: (slug: string, name: string) => void }> = ({ slug }) => {
  const { openPlayerProfile } = useLeagueStore();
  const { data, failed } = useAnalyticsData<PlayerPayload>(`/api/database/player/${encodeURIComponent(slug)}`);
  const [section, setSection] = useState<Section>('overview');
  const [view, setView] = useState<StatView>('pg');
  const [kind, setKind] = useState<Kind>('rs');
  const [chartStat, setChartStat] = useState('pts_pg');

  if (!data && !failed) return <div className="an-loading"><div className="spinner"></div></div>;
  if (!data) return <div className="an-empty"><h2>This player could not be loaded</h2></div>;

  const p = data;
  const live = p.status === 'Active' || p.status === 'Free agent';
  const where = p.status === 'Active' ? p.team : p.status === 'Retired' ? `Retired ${p.retired_year ?? ''}`.trim()
    : p.status === 'Free agent' ? 'Free agent' : `Out of league${p.team ? ` · last ${p.team}` : ''}`;
  const kicker = [p.pos, where, p.age !== null ? `Age ${p.age}` : null, p.season_count ? (live ? `${ordinal(p.season_count)} season` : `${p.season_count} season${p.season_count === 1 ? '' : 's'}`) : null]
    .filter(Boolean).join(' · ');
  const chips = AWARD_ORDER.filter((a) => p.career.awards[a]).map((a) => awardChip(a, p.career.awards[a]));

  return (
    <div className="an-root">
      <header className="db-band">
        <div>
          <div className="db-band-kicker">{kicker}</div>
          <h2 className="db-band-name">{p.name}</h2>
          <div className="db-chips">
            {p.career.titles > 0 && <span className="db-chip is-ring">🏆 ×{p.career.titles}</span>}
            {chips.map((c) => <span key={c} className="db-chip">{c}</span>)}
          </div>
        </div>
        <div className="db-bignums">
          {p.ovr !== null && <div><b>{p.ovr}</b><span>OVR</span></div>}
          <div><b>{fmt(p.career.pts_pg)}</b><span>PPG</span></div>
          <div><b>{fmt(p.career.reb_pg)}</b><span>RPG</span></div>
          <div><b>{fmt(p.career.ast_pg)}</b><span>APG</span></div>
          <div><b>{p.career.gp}</b><span>GP</span></div>
        </div>
      </header>

      <div className="an-views" role="group" aria-label="Player page section">
        {SECTIONS.map((s) => <button key={s.id} type="button" aria-pressed={section === s.id} onClick={() => setSection(s.id)}>{s.label}</button>)}
      </div>

      {section === 'overview' && <Overview p={p} live={live} onScout={() => openPlayerProfile(p.name)} />}
      {section === 'stats' && <StatsSection p={p} view={view} setView={setView} kind={kind} setKind={setKind} />}
      {section === 'progression' && (
        <div className="an-panel db-pad">
          <div className="an-filters">
            <select aria-label="Stat line" value={chartStat} onChange={(e) => setChartStat(e.target.value)}>
              {CHART_STATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <span className="an-count">{p.missing_years.length ? `No record: ${p.missing_years.join(', ')}` : ''}</span>
          </div>
          <ProgressionChart progression={p.progression} stat={chartStat} statLabel={CHART_STATS.find(([k]) => k === chartStat)?.[1] ?? ''} />
        </div>
      )}
      {section === 'awards' && <AwardsSection p={p} />}
    </div>
  );
};

const Overview: React.FC<{ p: PlayerPayload; live: boolean; onScout: () => void }> = ({ p, live, onScout }) => {
  const cur = p.current;
  const ranks = [...p.ranks.league.map((r) => `${rankText(r)} (all-time)`),
    ...p.ranks.franchise.map((r) => `${rankText(r)} for ${r.team}`)];
  const recent = p.rs.slice(-p.last_seasons).reverse();
  return (
    <>
      <div className="db-grid3">
        <div className="db-box">
          <div className="an-kicker">This season</div>
          {cur ? (
            <>
              <div className="db-box-big">{triple(cur)}</div>
              <div>{cur.gp} GP{cur.s.mpg !== null ? ` · ${fmt(cur.s.mpg)} MPG` : ''}{cur.s.ts_pct !== null ? ` · ${fmt(cur.s.ts_pct)} TS%` : ''}{cur.s.per !== null ? ` · PER ${fmt(cur.s.per)}` : ''}</div>
            </>
          ) : <div className="an-muted">{p.status === 'Retired' ? `Retired after ${p.retired_year ?? 'his last season'}` : live ? 'No games yet this season' : 'Not in the league this season'}</div>}
          {live && <button type="button" className="db-link-btn" onClick={onScout}>Scouting report →</button>}
        </div>
        <div className="db-box">
          <div className="an-kicker">Best season</div>
          {p.best ? (
            <>
              <div className="db-box-big">{p.best.year ?? '—'} · {fmt(p.best.pts_pg)} PPG</div>
              <div>{p.best.awards.join(', ') || 'No awards that year'}</div>
            </>
          ) : <div className="an-muted">No games played yet</div>}
        </div>
        <div className="db-box">
          <div className="an-kicker">In this save</div>
          {ranks.length ? <ul className="db-list">{ranks.slice(0, 5).map((r) => <li key={r}>{r}</li>)}</ul>
            : <div className="an-muted">Not in any all-time top list yet</div>}
        </div>
      </div>
      <div className="an-panel">
        <div className="an-kicker db-pad">Last {recent.length} season{recent.length === 1 ? '' : 's'}</div>
        <SeasonTable lines={recent} view="pg" career={null} missing={[]} />
      </div>
    </>
  );
};

const StatsSection: React.FC<{ p: PlayerPayload; view: StatView; setView: (v: StatView) => void; kind: Kind; setKind: (k: Kind) => void }> = ({ p, view, setView, kind, setKind }) => {
  const lines = kind === 'rs' ? p.rs : p.po;
  const anyFull = lines.some((l) => l.full);
  return (
    <>
      <div className="an-filters">
        <div className="an-views" role="group" aria-label="Stat view">
          {STAT_VIEWS.map((v) => <button key={v.id} type="button" aria-pressed={view === v.id} onClick={() => setView(v.id)}>{v.label}</button>)}
        </div>
        <div className="an-views" role="group" aria-label="Season type">
          <button type="button" aria-pressed={kind === 'rs'} onClick={() => setKind('rs')}>Regular season</button>
          <button type="button" aria-pressed={kind === 'po'} onClick={() => setKind('po')}>Playoffs</button>
        </div>
      </div>
      {FULL_ONLY.includes(view) && !anyFull && (
        <p className="db-note">These numbers come from full box-score lines, saved for seasons played from now on. None of this player's {kind === 'rs' ? '' : 'playoff '}seasons has one yet.</p>
      )}
      <div className="an-panel">
        {lines.length === 0 ? <p className="an-none">{kind === 'po' ? 'No playoff games.' : 'No seasons yet.'}</p>
          : <SeasonTable lines={lines} view={view} career={kind === 'rs' ? p.career_rs : p.career_po} missing={kind === 'rs' ? p.missing_years : []} showAwards />}
      </div>
      <p className="db-foot">— not saved for that season. * total estimated from the per-game average × games. Orange = career best.</p>
    </>
  );
};

/** One row per season (plus "No record" rows and the career row); orange marks the career best of each column. */
const SeasonTable: React.FC<{ lines: Line[]; view: StatView; career: CareerLine | null; missing: (number | null)[]; showAwards?: boolean }> = ({ lines, view, career, missing, showAwards }) => {
  const defs = STAT_DEFS[view];
  const best: Record<string, number> = {};
  if (lines.length > 1) {
    for (const d of defs) {
      if (d.key === 'gp' || d.key.startsWith('to_')) continue;
      const vals = lines.map((l) => l.s[d.key]).filter((v): v is number => v !== null);
      if (vals.length > 1) best[d.key] = Math.max(...vals);
    }
  }
  const rows: ({ kind: 'line'; line: Line } | { kind: 'gap'; year: number })[] = lines.map((line) => ({ kind: 'line' as const, line }));
  for (const yr of missing) {
    if (yr === null) continue;
    const at = rows.findIndex((r) => r.kind === 'line' && (r.line.year ?? 0) > yr);
    rows.splice(at < 0 ? rows.length : at, 0, { kind: 'gap', year: yr });
  }
  const cell = (s: Line['s'], key: string, est: boolean) => {
    const d = defs.find((x) => x.key === key)!;
    const v = s[key];
    return `${formatStat(d, v)}${est && v !== null && key.endsWith('_tot') ? '*' : ''}`;
  };
  return (
    <table className="an-table db-seasons">
      <caption className="an-sr">Season by season</caption>
      <thead>
        <tr>
          <th scope="col" className="is-left"><span className="db-th">Year</span></th>
          <th scope="col" className="is-left"><span className="db-th">Team</span></th>
          <th scope="col"><span className="db-th">Age</span></th>
          <th scope="col"><span className="db-th">OVR</span></th>
          {defs.map((d) => <th key={d.key} scope="col" title={d.title}><span className="db-th">{d.label}</span></th>)}
          {showAwards && <th scope="col" className="is-left"><span className="db-th">Awards</span></th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => r.kind === 'gap' ? (
          <tr key={`gap-${r.year}`} className="db-gap">
            <td className="is-left">{r.year}</td>
            <td className="is-left" colSpan={3 + defs.length + (showAwards ? 1 : 0)}>No record</td>
          </tr>
        ) : (
          <tr key={`${r.line.season}-${r.line.team}`}>
            <td className="is-left">{r.line.year ?? '—'}{r.line.champion ? ' 🏆' : ''}</td>
            <td className="is-left">
              {r.line.team ?? '—'}
              {r.line.teams.length > 1 && <div className="db-teams">{r.line.teams.join(' → ')}</div>}
            </td>
            <td>{r.line.age ?? '—'}</td>
            <td>{r.line.ovr ?? '—'}</td>
            {defs.map((d) => (
              <td key={d.key} className={best[d.key] !== undefined && r.line.s[d.key] === best[d.key] ? 'is-top' : undefined}>
                {cell(r.line.s, d.key, r.line.est)}
              </td>
            ))}
            {showAwards && <td className="is-left db-awards">{r.line.awards.join(', ')}</td>}
          </tr>
        ))}
        {career && (
          <tr className="db-career">
            <td className="is-left">Career</td>
            <td className="is-left">{career.seasons} season{career.seasons === 1 ? '' : 's'}</td>
            <td></td><td></td>
            {defs.map((d) => <td key={d.key}>{cell(career.s, d.key, career.est)}</td>)}
            {showAwards && <td></td>}
          </tr>
        )}
      </tbody>
    </table>
  );
};

const AwardsSection: React.FC<{ p: PlayerPayload }> = ({ p }) => {
  const teams = [...new Set(p.ranks.franchise.map((r) => r.team as string))];
  return (
    <div className="db-grid2">
      <div className="an-panel db-pad">
        <div className="an-kicker">Titles</div>
        {p.titles.length ? <ul className="db-list">{p.titles.map((t) => <li key={`${t.year}`}>🏆 {t.year} · {t.team}</li>)}</ul>
          : <p className="an-muted">No titles.</p>}
        <div className="an-kicker db-gap-top">Awards</div>
        {p.awards.length ? (
          <table className="an-table">
            <caption className="an-sr">Awards by year</caption>
            <tbody>{p.awards.map((a, i) => <tr key={i}><td className="is-left">{a.year}</td><td className="is-left"><b>{a.award}</b></td><td className="is-left an-muted">{a.team}</td></tr>)}</tbody>
          </table>
        ) : <p className="an-muted">No awards.</p>}
      </div>
      <div className="an-panel db-pad">
        <div className="an-kicker">League, all-time in this save</div>
        {p.ranks.league.length ? <ul className="db-list">{p.ranks.league.map((r) => <li key={r.stat}><b>{ordinal(r.rank)}</b> in {RANK_LABELS[r.stat]} <span className="an-muted">({r.stat.endsWith('_pg') ? fmt(r.value) : r.value.toLocaleString()})</span></li>)}</ul>
          : <p className="an-muted">Not in any all-time top list yet.</p>}
        {teams.map((team) => (
          <React.Fragment key={team}>
            <div className="an-kicker db-gap-top">{team}, all-time</div>
            <ul className="db-list">{p.ranks.franchise.filter((r) => r.team === team).map((r) => <li key={r.stat}><b>{ordinal(r.rank)}</b> in {RANK_LABELS[r.stat]} <span className="an-muted">({r.value.toLocaleString()})</span></li>)}</ul>
          </React.Fragment>
        ))}
        {p.salary !== null && <><div className="an-kicker db-gap-top">Contract</div><p>{money(p.salary, p.years)}</p></>}
      </div>
    </div>
  );
};
