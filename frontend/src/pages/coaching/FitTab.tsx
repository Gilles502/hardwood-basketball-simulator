// Coaching page, "Fit with roster" tab: how the coach's schemes fit the roster, then player by player.
import React, { useEffect, useMemo, useState } from 'react';
import { StatTable, type Column } from '../analytics/StatTable';
import { gradeTone, playerFitTone, scoreTone, type PlayerFit, type SystemFit } from './types';

type Filter = 'all' | 'problems' | 'good';

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All players' },
  { id: 'problems', label: 'Problems' },
  { id: 'good', label: 'Good fits' },
];

const STATUS_LABEL: Record<string, string> = {
  'Ideal Fit': 'Ideal fit',
  'Solid Fit': 'Solid fit',
  'Tactical Friction': 'Friction',
  'Severe Mismatch': 'Mismatch',
};

const isProblem = (p: PlayerFit) => p.badge === 'Tactical Friction' || p.badge === 'Severe Mismatch';

const stat = (key: '3PT' | 'SPD' | 'DEF'): Column<PlayerFit> => ({
  key, label: key, value: (r) => r.stats_preview?.[key] ?? null, pct: (r) => r.stats_preview?.[key] ?? null,
});

const COLUMNS: Column<PlayerFit>[] = [
  { key: 'name', label: 'Player', left: true, keep: true, value: (r) => r.name, format: (_v, r) => <span className="an-name"><b>{r.name}</b></span> },
  { key: 'pos', label: 'Role', left: true, value: (r) => r.position },
  { key: 'ovr', label: 'OVR', value: (r) => r.ovr },
  { key: 'fit', label: 'Fit', keep: true, value: (r) => r.fit_score, pct: (r) => r.fit_score },
  {
    key: 'status', label: 'Status', left: true, keep: true, value: (r) => r.fit_score,
    format: (_v, r) => <span className={`of-pill is-${playerFitTone(r.badge)}`}>{STATUS_LABEL[r.badge] ?? r.badge}</span>,
  },
  stat('3PT'),
  stat('SPD'),
  stat('DEF'),
  { key: 'note', label: 'Note', left: true, value: (r) => r.notes ?? '', format: (v) => <span className="cc-note">{v || '—'}</span> },
];

interface FitTabProps {
  coachName: string;
}

export const FitTab: React.FC<FitTabProps> = ({ coachName }) => {
  const [fit, setFit] = useState<SystemFit | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');

  useEffect(() => {
    let alive = true;
    fetch(`/api/coaching/system-fit?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((json) => {
        if (!alive) return;
        if (json.error) setFailed(json.error);
        else { setFit(json.system_fit || null); setFailed(null); }
      })
      .catch(() => alive && setFailed('Could not load the scheme fit.'));
    return () => { alive = false; };
  }, [coachName]);

  const rows = useMemo(() => {
    const all = fit?.player_fits || [];
    if (filter === 'problems') return all.filter(isProblem);
    if (filter === 'good') return all.filter((p) => !isProblem(p));
    return all;
  }, [fit, filter]);

  if (failed) return <div className="of-card of-empty">{failed}</div>;
  if (!fit) return <div className="an-loading"><div className="spinner"></div></div>;

  const problems = (fit.player_fits || []).filter(isProblem).length;
  const net = fit.net_rating_mod ?? 0;

  return (
    <div className="of-col">
      <div className="of-grid2">
        <div className="of-card">
          <h3 className="of-sub-head">Overall fit</h3>
          <div className="cc-grade-row">
            <span className={`cc-grade of-tone-${gradeTone(fit.grade)}`}>{fit.grade}</span>
            <div>
              <b className="cc-grade-score">{fit.fit_score}%</b>
              <span className="cc-muted">{fit.rating}</span>
            </div>
            <span className={`of-pill is-${net > 0 ? 'ok' : net < 0 ? 'bad' : 'info'}`}>{fit.net_impact}</span>
          </div>
          <div className="cc-ratings">
            <div className="cc-rating">
              <span>Offense · {fit.offensive_system}</span>
              <b>{fit.offensive_fit_score}</b>
              <div className={`of-meter is-thin is-${scoreTone(fit.offensive_fit_score)}`}><i style={{ width: `${fit.offensive_fit_score}%` }} /></div>
            </div>
            <div className="cc-rating">
              <span>Defense · {fit.defensive_scheme}</span>
              <b>{fit.defensive_fit_score}</b>
              <div className={`of-meter is-thin is-${scoreTone(fit.defensive_fit_score)}`}><i style={{ width: `${fit.defensive_fit_score}%` }} /></div>
            </div>
          </div>
          <p className="of-note">Pace: {fit.preferred_pace}</p>
        </div>

        <div className="of-card">
          <h3 className="of-sub-head">What works, what doesn't</h3>
          {fit.synergies.length === 0 && fit.red_flags.length === 0 && <p className="of-note">Nothing stands out either way.</p>}
          <ul className="cc-flags">
            {fit.red_flags.map((f, i) => <li key={`r${i}`} className="is-bad">{f}</li>)}
            {fit.synergies.map((f, i) => <li key={`s${i}`} className="is-ok">{f}</li>)}
          </ul>
        </div>
      </div>

      <div className="of-card">
        <div className="cc-table-head">
          <h3 className="of-sub-head">Player by player</h3>
          <div className="of-seg" role="group" aria-label="Show players">
            {FILTERS.map((f) => (
              <button key={f.id} type="button" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
                {f.label}{f.id === 'problems' && <small>{problems}</small>}
              </button>
            ))}
          </div>
        </div>
        {rows.length === 0
          ? <p className="of-note">No player in this group.</p>
          : (
            <div className="an-panel">
              <StatTable<PlayerFit> rows={rows} columns={COLUMNS} rowKey={(r) => r.player_id || r.name} defaultSort="fit"
                defaultAsc tintTop={80} tintBottom={50} caption="Scheme fit of each player" />
            </div>
          )}
      </div>
    </div>
  );
};
