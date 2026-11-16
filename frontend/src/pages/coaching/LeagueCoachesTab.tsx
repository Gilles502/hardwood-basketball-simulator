// Coaching page, "League coaches" tab: every team's head coach in a sortable table (yours highlighted).
import React, { useMemo, useState } from 'react';
import { TeamCrest } from '../../components/TeamCrest';
import { StatTable, type Column } from '../analytics/StatTable';
import { securityTone, type LeagueCoach } from './types';

const COLUMNS: Column<LeagueCoach>[] = [
  {
    key: 'team', label: 'Team', left: true, keep: true, value: (r) => r.team_name,
    format: (_v, r) => <span className="an-name an-team-cell"><TeamCrest name={r.team_name} size={22} /><b>{r.team_name}</b></span>,
  },
  { key: 'record', label: 'W-L', title: 'This season', value: (r) => Number(r.team_record.split('-')[0]) || 0, format: (_v, r) => r.team_record },
  {
    key: 'coach', label: 'Coach', left: true, keep: true, value: (r) => r.nome,
    format: (_v, r) => <span className="an-name"><b>{r.nome}</b></span>,
  },
  { key: 'style', label: 'Style', left: true, value: (r) => r.stile_gioco },
  { key: 'age', label: 'Age', value: (r) => r.eta },
  { key: 'ovr', label: 'OVR', keep: true, value: (r) => r.ovr_totale, pct: (r) => r.ovr_totale },
  { key: 'off', label: 'OFF', title: 'Offense', value: (r) => r.ovr_offensivo, pct: (r) => r.ovr_offensivo },
  { key: 'def', label: 'DEF', title: 'Defense', value: (r) => r.ovr_difensivo, pct: (r) => r.ovr_difensivo },
  { key: 'rings', label: 'Rings', value: (r) => r.championships },
  {
    key: 'security', label: 'Security', left: true, title: "Owner's trust", value: (r) => r.job_security,
    format: (_v, r) => <span className={`of-pill is-${securityTone(r.job_security)}`}>{r.job_security_label || 'Secure'}</span>,
  },
];

interface LeagueCoachesTabProps {
  coaches: LeagueCoach[];
  teamName: string | null;
}

export const LeagueCoachesTab: React.FC<LeagueCoachesTabProps> = ({ coaches, teamName }) => {
  const [search, setSearch] = useState('');
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return coaches;
    return coaches.filter((c) => c.nome.toLowerCase().includes(q) || c.team_name.toLowerCase().includes(q) || c.stile_gioco.toLowerCase().includes(q));
  }, [coaches, search]);

  return (
    <div className="of-col">
      <div className="an-filters">
        <input id="cc-league-search" type="search" placeholder="Search a coach, team or style" aria-label="Search a coach, team or style"
          value={search} onChange={(e) => setSearch(e.target.value)} />
        <span className="an-count">{rows.length} head coaches</span>
      </div>
      {rows.length === 0
        ? <div className="of-card of-empty">No coach matches this search.</div>
        : (
          <div className="an-panel">
            <StatTable<LeagueCoach> rows={rows} columns={COLUMNS} rowKey={(r) => r.team_name} defaultSort="ovr"
              tintTop={82} tintBottom={68} highlight={(r) => r.team_name === teamName} caption="Head coaches of the league" />
          </div>
        )}
    </div>
  );
};
