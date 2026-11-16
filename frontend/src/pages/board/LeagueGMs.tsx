// League GMs tab (mockup "table of all 30 GMs"): sortable table + team picker; a row opens that team's GM card.
import React, { useCallback, useEffect, useState } from 'react';
import { TeamCrest } from '../../components/TeamCrest';
import { useLeagueStore } from '../../store/leagueStore';
import { StatTable, type Column } from '../analytics/StatTable';
import { GMCard } from './GMCard';
import type { LeagueGMRow, LeagueGMsPayload } from './types';

const skill = (key: 'trade' | 'contracts' | 'draft', label: string, title: string): Column<LeagueGMRow> => ({
  key, label, title,
  value: (r) => r.skills?.[key] ?? null,
  pct: (r) => r.skills?.[key] ?? null,
});

const COLUMNS: Column<LeagueGMRow>[] = [
  {
    key: 'team', label: 'Team', left: true, keep: true, value: (r) => r.team,
    format: (_v, r) => <span className="an-name an-team-cell"><TeamCrest name={r.team} size={22} /><b>{r.team}</b></span>,
  },
  {
    key: 'gm', label: 'GM', left: true, keep: true, value: (r) => r.name,
    format: (_v, r) => <span className="an-name"><b>{r.name}</b>{r.is_user && <span className="an-tag fo-you">You</span>}{r.new_this_year && <span className="an-tag">New</span>}{r.interim && <span className="an-tag">Interim</span>}</span>,
  },
  { key: 'age', label: 'Age', value: (r) => r.age },
  {
    key: 'plan', label: 'Plan', left: true, keep: true, value: (r) => r.plan_label,
    format: (_v, r) => (r.plan_label
      ? <span className={`fo-plan fo-plan-${(r.plan ?? '').toLowerCase()}`}>{r.plan_label}<span className="fo-plan-yr"> · S{r.seasons_held}</span></span>
      : '—'),
  },
  {
    key: 'traits', label: 'Philosophy', left: true, value: (r) => r.traits.join(', '),
    format: (_v, r) => (r.traits.length ? <span className="fo-traits">{r.traits.join(' · ')}</span> : '—'),
  },
  skill('trade', 'TRD', 'Trade skill'),
  skill('contracts', 'CTR', 'Contracts skill (free agency, extensions)'),
  skill('draft', 'DRF', 'Draft evaluation skill'),
];

export const LeagueGMs: React.FC = () => {
  const leagueData = useLeagueStore((s) => s.leagueData);
  const [data, setData] = useState<LeagueGMsPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch(`/api/front_office/gms?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((json) => { if (json.error) setFailed(json.error); else { setData(json); setFailed(null); } })
      .catch(() => setFailed('Could not load the league front offices.'));
  }, []);

  useEffect(() => { load(); }, [load, leagueData?.stagione, leagueData?.player_team_name]);

  if (failed) return <div className="an-empty"><h2>Front offices unavailable</h2><p>{failed}</p></div>;
  if (!data) return <div className="an-loading"><div className="spinner"></div></div>;

  return (
    <div className="an-root">
      <div className="an-filters">
        <select aria-label="Open a team's front office" value={selected ?? ''}
          onChange={(e) => setSelected(e.target.value || null)}>
          <option value="">Pick a team…</option>
          {data.rows.map((r) => <option key={r.team} value={r.team}>{r.team}</option>)}
        </select>
        <span className="an-count">{data.rows.length} front offices · {data.year}-{String((data.year + 1) % 100).padStart(2, '0')}</span>
      </div>

      <div className={selected ? 'an-split' : undefined}>
        <div className="an-panel">
          <StatTable<LeagueGMRow> rows={data.rows} columns={COLUMNS} rowKey={(r) => r.team} defaultSort="team" defaultAsc
            tintTop={75} tintBottom={49} selectedKey={selected} highlight={(r) => r.is_user}
            onSelect={(r) => setSelected(r.team === selected ? null : r.team)} compact={!!selected}
            caption="General managers of the league" />
        </div>
        {selected && <GMCard team={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
};
