// Coaching page, "Coach market" tab: free-agent coaches in a sortable table; a row opens the offer dialog.
import React, { useMemo, useState } from 'react';
import { StatTable, type Column } from '../analytics/StatTable';
import { fitGrade, gradeTone, marketAsk, money, type Coach } from './types';

const rating = (key: keyof Coach, label: string, title: string): Column<Coach> => ({
  key: String(key), label, title, value: (r) => Number(r[key] ?? 75), pct: (r) => Number(r[key] ?? 75),
});

const COLUMNS: Column<Coach>[] = [
  {
    key: 'name', label: 'Coach', left: true, keep: true, value: (r) => r.nome,
    format: (_v, r) => <span className="an-name"><b>{r.nome}</b><span className="cc-sub">{r.specialization || 'Tactician'}</span></span>,
  },
  { key: 'style', label: 'Style', left: true, value: (r) => r.stile_gioco },
  { key: 'age', label: 'Age', value: (r) => r.eta },
  { key: 'ovr', label: 'OVR', keep: true, value: (r) => r.ovr_totale, pct: (r) => r.ovr_totale },
  rating('ovr_offensivo', 'OFF', 'Offense'),
  rating('ovr_difensivo', 'DEF', 'Defense'),
  rating('player_development', 'DEV', 'Player development'),
  rating('tactical_acumen', 'ADJ', 'In-game adjustments'),
  rating('discipline_culture', 'ROOM', 'Locker room culture'),
  {
    key: 'fit', label: 'Fit', keep: true, title: 'Fit of his schemes with your roster', value: (r) => r.roster_fit?.fit_score ?? null,
    format: (_v, r) => {
      const g = fitGrade(r.roster_fit);
      return <span className="cc-fit"><b className={`of-tone-${gradeTone(g)}`}>{g}</b>{r.roster_fit ? ` ${r.roster_fit.fit_score}%` : ''}</span>;
    },
  },
  { key: 'record', label: 'Career', title: 'Career record', value: (r) => r.career_win_pct ?? null, format: (_v, r) => `${r.historical_wins}-${r.historical_losses}` },
  { key: 'ask', label: 'Asks', keep: true, title: 'Lowest yearly salary he signs for', value: (r) => marketAsk(r), format: (v) => money(Number(v)) },
];

interface MarketTabProps {
  coaches: Coach[];
  currentCoach: string | null;
  onPick: (coach: Coach) => void;
}

export const MarketTab: React.FC<MarketTabProps> = ({ coaches, currentCoach, onPick }) => {
  const [search, setSearch] = useState('');
  const [spec, setSpec] = useState('all');

  const specs = useMemo(() => Array.from(new Set(coaches.map((c) => c.specialization).filter(Boolean) as string[])).sort(), [coaches]);
  const rows = useMemo(() => coaches.filter((c) => {
    if (search.trim() && !c.nome.toLowerCase().includes(search.trim().toLowerCase())) return false;
    return spec === 'all' || c.specialization === spec;
  }), [coaches, search, spec]);

  return (
    <div className="of-col">
      <div className="an-filters">
        <input id="cc-market-search" type="search" placeholder="Search a coach" aria-label="Search a coach" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select id="cc-market-spec" aria-label="Specialty" value={spec} onChange={(e) => setSpec(e.target.value)}>
          <option value="all">All specialties</option>
          {specs.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="an-count">{rows.length} of {coaches.length} coaches</span>
      </div>
      <p className="of-note">
        Pick a coach to make an offer.
        {currentCoach ? ` Hiring one fires ${currentCoach} in the same step.` : ' Your bench is empty.'}
      </p>
      {rows.length === 0
        ? <div className="of-card of-empty">No coach matches these filters.</div>
        : (
          <div className="an-panel">
            <StatTable<Coach> rows={rows} columns={COLUMNS} rowKey={(r) => r.nome} defaultSort="fit"
              tintTop={82} tintBottom={68} onSelect={onPick} caption="Coaches on the market" />
          </div>
        )}
    </div>
  );
};
