// Teams tab (mockup "A", same pattern as Players): leaders strip + table of 30 teams; pressing a team opens its card
// (offense / defense percentiles, quarter margins, situations, expected wins). Payload from /api/analytics/teams.
import React, { useEffect, useMemo, useState } from 'react';
import { TeamCrest } from '../../components/TeamCrest';
import { useLeagueStore } from '../../store/leagueStore';
import { nickname } from '../../utils/resultSheet';
import { LeadersStrip, type LeaderTile } from './LeadersStrip';
import { PercentileBars } from './PercentileBars';
import { StatTable, type Column } from './StatTable';
import type { TeamRow, TeamsPayload } from './types';
import { fmt, fmtSigned, useAnalyticsData } from './useAnalyticsData';
import type { SeasonKind } from '../Analytics';

type View = 'ratings' | 'offense' | 'defense' | 'factors' | 'shooting' | 'opponent' | 'splits';

const VIEWS: { id: View; label: string }[] = [
  { id: 'ratings', label: 'Ratings' }, { id: 'offense', label: 'Offense' }, { id: 'defense', label: 'Defense' },
  { id: 'factors', label: 'Four factors' }, { id: 'shooting', label: 'Shooting' }, { id: 'opponent', label: 'Opponent' },
  { id: 'splits', label: 'Splits' },
];

const stat = (key: string, label: string, opts: Partial<Column<TeamRow>> & { signed?: boolean; pctKey?: string } = {}): Column<TeamRow> => ({
  key, label,
  value: (r) => r.s[key] ?? null,
  format: (v) => (typeof v === 'number' ? (opts.signed ? fmtSigned(v) : fmt(v)) : '—'),
  pct: opts.pctKey ? (r) => r.pct[opts.pctKey as string] ?? null : undefined,
  ...opts,
});

const record = (key: string, label: string, pick: (r: TeamRow) => [number, number], keep = false): Column<TeamRow> => ({
  key, label, keep,
  value: (r) => { const [w, l] = pick(r); return w + l ? w / (w + l) : null; },
  format: (_v, r) => { const [w, l] = pick(r); return `${w}-${l}`; },
});

const quarter = (q: number): Column<TeamRow> => ({
  key: `q${q + 1}`, label: `Q${q + 1}`, title: `Average margin in quarter ${q + 1}`,
  value: (r) => r.quarters[q] ?? null,
  format: (v) => (typeof v === 'number' ? fmtSigned(v) : '—'),
});

const COLUMNS: Record<View, Column<TeamRow>[]> = {
  ratings: [
    record('wl', 'W-L', (r) => [r.w, r.l], true), stat('net', 'NET', { signed: true, keep: true, pctKey: 'net' }),
    stat('ortg', 'ORTG', { keep: true, pctKey: 'ortg', title: 'Points per 100 possessions' }),
    stat('drtg', 'DRTG', { keep: true, pctKey: 'drtg', title: 'Points allowed per 100 possessions' }),
    stat('pace', 'PACE', { title: 'Possessions per game' }), stat('ppg', 'PPG'), stat('opp_ppg', 'OPP PPG'),
    stat('exp_w', 'EXP W', { title: 'Expected wins from points scored and allowed' }),
    stat('luck', 'LUCK', { signed: true, title: 'Wins minus expected wins' }),
  ],
  offense: [
    stat('ppg', 'PPG', { keep: true }), stat('ortg', 'ORTG', { keep: true, pctKey: 'ortg' }),
    stat('efg', 'eFG%', { keep: true, pctKey: 'efg' }), stat('tov_pct', 'TOV%', { pctKey: 'tov_pct' }),
    stat('ft_rate', 'FT RATE', { pctKey: 'ft_rate', title: 'FTA per FGA' }), stat('fg_pct', 'FG%'), stat('tp_pct', '3P%'),
    stat('tpa_rate', '3PA RATE'), stat('ast_pg', 'AST'), stat('ast_rate', 'AST RATE', { title: 'Share of baskets assisted' }),
  ],
  defense: [
    stat('opp_ppg', 'OPP PPG', { keep: true }), stat('drtg', 'DRTG', { keep: true, pctKey: 'drtg' }),
    stat('opp_efg', 'OPP eFG%', { keep: true, pctKey: 'opp_efg' }),
    stat('opp_tov_pct', 'FORCED TOV%', { pctKey: 'opp_tov_pct' }), stat('opp_ft_rate', 'OPP FT RATE'),
    stat('opp_fg_pct', 'OPP FG%'), stat('opp_tp_pct', 'OPP 3P%'), stat('stl_pg', 'STL'), stat('blk_pg', 'BLK'),
  ],
  factors: [
    stat('efg', 'eFG%', { keep: true, pctKey: 'efg' }), stat('tov_pct', 'TOV%', { keep: true, pctKey: 'tov_pct' }),
    stat('ft_rate', 'FT RATE', { pctKey: 'ft_rate' }),
    stat('orb_pct', 'ORB%', { keep: true, pctKey: 'orb_pct', title: 'Share of its own misses it rebounds (games since the 2026-11-15 update)' }),
    stat('reb_diff', 'REB DIFF', { signed: true, pctKey: 'reb_diff', title: 'Rebounds per game minus opponents' }),
    stat('opp_efg', 'OPP eFG%', { keep: true, pctKey: 'opp_efg' }), stat('opp_tov_pct', 'OPP TOV%', { keep: true, pctKey: 'opp_tov_pct' }),
    stat('opp_ft_rate', 'OPP FT RATE'),
    stat('drb_pct', 'DRB%', { keep: true, pctKey: 'drb_pct', title: 'Share of opponent misses it rebounds (games since the 2026-11-15 update)' }),
  ],
  shooting: [
    stat('fg_pct', 'FG%', { keep: true }), stat('tp_pct', '3P%', { keep: true }), stat('ft_pct', 'FT%'),
    stat('efg', 'eFG%', { keep: true, pctKey: 'efg' }), stat('tpa_rate', '3PA RATE'), stat('ft_rate', 'FT RATE', { pctKey: 'ft_rate' }),
    stat('opp_fg_pct', 'OPP FG%'), stat('opp_tp_pct', 'OPP 3P%'), stat('opp_tpa_rate', 'OPP 3PA RATE'),
  ],
  opponent: [
    stat('opp_ppg', 'PTS', { keep: true }), stat('opp_reb_pg', 'REB', { keep: true }), stat('opp_to_pg', 'TO'),
    stat('opp_fg_pct', 'FG%', { keep: true }), stat('opp_tp_pct', '3P%'), stat('opp_tpa_rate', '3PA RATE'),
    stat('opp_efg', 'eFG%', { pctKey: 'opp_efg' }), stat('opp_ft_rate', 'FT RATE'),
  ],
  splits: [
    record('wl', 'W-L', (r) => [r.w, r.l], true), record('home', 'HOME', (r) => r.home, true),
    record('away', 'AWAY', (r) => r.away, true), record('close', 'CLOSE', (r) => r.close),
    quarter(0), quarter(1), quarter(2), quarter(3),
  ],
};

const TILES: [string, string, boolean, boolean][] = [   // label, key, lower is better, signed
  ['Net rating', 'net', false, true], ['Offense (ORTG)', 'ortg', false, false], ['Defense (DRTG)', 'drtg', true, false],
  ['Fastest pace', 'pace', false, false], ['Opp eFG% (low)', 'opp_efg', true, false], ['Luckiest', 'luck', false, true],
];

interface TeamsTabProps {
  kind: SeasonKind;
  focusTeam: string | null;
  onOpenSplits: (name: string) => void;
}

export const TeamsTab: React.FC<TeamsTabProps> = ({ kind, focusTeam, onOpenSplits }) => {
  const { openTeamProfile } = useLeagueStore();
  const { data, failed } = useAnalyticsData<TeamsPayload>(`/api/analytics/teams?kind=${kind}`);
  const [view, setView] = useState<View>('ratings');
  const [conference, setConference] = useState('');
  const [selected, setSelected] = useState<string | null>(focusTeam);

  useEffect(() => { if (focusTeam) setSelected(focusTeam); }, [focusTeam]);
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelected(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected]);

  const teams = useMemo(() => data?.teams ?? [], [data]);
  const conferences = useMemo(() => [...new Set(teams.map((t) => t.conference).filter(Boolean) as string[])].sort(), [teams]);

  if (!data && !failed) return <div className="an-loading"><div className="spinner"></div></div>;
  if (!data) return <div className="an-empty"><h2>Team stats could not be loaded</h2></div>;
  if (data.meta.games === 0) return <div className="an-empty"><h2>{kind === 'po' ? 'No playoff games yet this season' : 'No games played yet this season'}</h2></div>;

  const meta = data.meta;
  const rows = teams.filter((t) => !conference || t.conference === conference);
  const tiles: LeaderTile[] = TILES.map(([label, key, low, signed]) => ({
    label,
    items: teams.filter((t) => t.s[key] !== null)
      .sort((a, b) => ((a.s[key] as number) - (b.s[key] as number)) * (low ? 1 : -1)).slice(0, meta.leaders_per_tile)
      .map((t) => ({ name: t.name, short: nickname(t.name), value: signed ? fmtSigned(t.s[key]) : fmt(t.s[key]) })),
  }));
  const card = selected ? teams.find((t) => t.name === selected) ?? null : null;

  const nameCol: Column<TeamRow> = {
    key: 'name', label: 'Team', left: true, keep: true, value: (r) => r.name,
    format: (_v, r) => <span className="an-name an-team-cell"><TeamCrest name={r.name} size={22} /><b>{r.name}</b></span>,
  };

  return (
    <div className="an-root">
      <div className="an-views" role="group" aria-label="Stat view">
        {VIEWS.map((v) => <button key={v.id} type="button" aria-pressed={view === v.id} onClick={() => setView(v.id)}>{v.label}</button>)}
      </div>

      <LeadersStrip tiles={tiles} onPick={setSelected} />

      <div className="an-filters">
        <select aria-label="Conference" value={conference} onChange={(e) => setConference(e.target.value)}>
          <option value="">Both conferences</option>
          {conferences.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="an-count">{teams.length} teams · {meta.games} games{meta.season ? ` · ${meta.season}` : ''}</span>
      </div>

      <div className={card ? 'an-split' : undefined}>
        <div className="an-panel">
          <StatTable<TeamRow> rows={rows} columns={[nameCol, ...COLUMNS[view]]} rowKey={(r) => r.name} key={view}
            defaultSort={view === 'splits' || view === 'ratings' ? (view === 'ratings' ? 'net' : 'wl') : COLUMNS[view][1].key}
            tintTop={meta.tint_top} tintBottom={meta.tint_bottom} selectedKey={selected} highlight={(r) => r.is_user_team}
            onSelect={(r) => setSelected(r.name === selected ? null : r.name)} compact={!!card} caption="League teams" />
        </div>
        {card && <TeamCard team={card} closeMargin={meta.close_margin} onClose={() => setSelected(null)}
          onOpenProfile={() => openTeamProfile(card.name)} onOpenSplits={() => onOpenSplits(card.name)} />}
      </div>
    </div>
  );
};

const TeamCard: React.FC<{ team: TeamRow; closeMargin: number; onClose: () => void; onOpenProfile: () => void; onOpenSplits: () => void }> = ({ team, closeMargin, onClose, onOpenProfile, onOpenSplits }) => {
  const s = team.s;
  return (
    <aside className="an-card" aria-label={`${team.name} team card`}>
      <div className="an-card-top">
        <span className="an-kicker">{team.conference ?? '—'}{team.is_user_team ? ' · your team' : ''}</span>
        <button type="button" className="an-close" aria-label="Close card" onClick={onClose}>✕</button>
      </div>
      <button type="button" className="an-card-name an-link" onClick={onOpenProfile}>{team.name}</button>
      <div className="an-card-line">{team.w}-{team.l} · Net {fmtSigned(s.net)} · Pace {fmt(s.pace)}</div>
      <div className="an-card-sub">Offense — league percentile</div>
      <PercentileBars items={[
        { label: `ORTG ${fmt(s.ortg)}`, pct: team.pct.ortg }, { label: `eFG% ${fmt(s.efg)}`, pct: team.pct.efg },
        { label: `TOV% ${fmt(s.tov_pct)} (low)`, pct: team.pct.tov_pct }, { label: `FT rate ${fmt(s.ft_rate)}`, pct: team.pct.ft_rate },
      ]} />
      <div className="an-card-sub">Defense — league percentile</div>
      <PercentileBars items={[
        { label: `DRTG ${fmt(s.drtg)} (low)`, pct: team.pct.drtg }, { label: `Opp eFG% ${fmt(s.opp_efg)}`, pct: team.pct.opp_efg },
        { label: `Forced TOV% ${fmt(s.opp_tov_pct)}`, pct: team.pct.opp_tov_pct }, { label: `Reb diff ${fmtSigned(s.reb_diff)}`, pct: team.pct.reb_diff },
      ]} />
      <div className="an-card-sub">Average margin by quarter</div>
      <div className="an-figures">
        {team.quarters.map((q, i) => <div key={i}><b>{fmtSigned(q)}</b><span>Q{i + 1}</span></div>)}
      </div>
      <div className="an-card-sub">Situations</div>
      <div className="an-figures">
        <div><b>{team.home[0]}-{team.home[1]}</b><span>Home</span></div>
        <div><b>{team.away[0]}-{team.away[1]}</b><span>Away</span></div>
        <div><b>{team.close[0]}-{team.close[1]}</b><span>Within {closeMargin} pts</span></div>
      </div>
      <div className="an-card-sub">Expected wins</div>
      <p className="an-card-text">
        Points say <b>{fmt(s.exp_w)}</b> wins, they won <b>{team.w}</b> → <b>{fmtSigned(s.luck)}</b>
        {s.luck !== null && Math.abs(s.luck) >= 2 ? (s.luck > 0 ? ' (winning the close ones)' : ' (losing the close ones)') : ''}
      </p>
      <button type="button" className="an-card-btn" onClick={onOpenSplits}>Open splits &amp; logs →</button>
    </aside>
  );
};
