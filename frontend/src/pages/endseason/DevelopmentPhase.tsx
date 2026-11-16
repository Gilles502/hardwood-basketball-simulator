// Phase 3 · Development & retirements ("progress report"): your roster as before → after bars, the league's biggest
// risers and drops, and who retired with one honour line each. Payload: core/end_season_views.development_view.
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import type { PhaseProps } from '../../utils/endSeason';

interface YourRow { name: string; age: number | null; position: string | null; before: number; after: number; delta: number }
interface Mover { name: string; team: string; age: number | null; delta: number }
interface Retiree { name: string; team: string; age: number | null; ovr: number | null; honour: string | null; yours: boolean }
interface Development {
  yours: YourRow[];
  net: { total: number; up: number; down: number; same: number };
  risers: Mover[];
  drops: Mover[];
  retired: Retiree[];
}

/** Retirees shown before "+N more". */
const RETIRED_ROWS = 4;
const signed = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n)}`;

export const DevelopmentPhase: React.FC<PhaseProps> = () => {
  const { leagueData, openPlayerProfile } = useLeagueStore();
  const team = leagueData?.player_team_name ?? null;
  const [view, setView] = useState<Development | null>(null);
  const [failed, setFailed] = useState(false);
  const [allRetired, setAllRetired] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/offseason/development?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data) => { if (!cancelled) (data && Array.isArray(data.yours) ? setView(data) : setFailed(true)); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, []);

  if (failed) return <div className="eos-sheet"><p className="eos-muted">Development could not be loaded.</p></div>;
  if (!view) return <div className="eos-sheet"><p className="eos-muted">Loading…</p></div>;

  const name = (n: string) => <button type="button" className="eos-link" onClick={() => openPlayerProfile(n)}>{n}</button>;
  const movers = (title: string, rows: Mover[], empty: string) => (
    <section className="rc-card">
      <h3 className="rc-h">{title}</h3>
      {rows.length === 0 ? <p className="eos-muted">{empty}</p> : (
        <ul className="rc-rows">
          {rows.map((m) => (
            <li key={`${m.name}-${m.team}`}>
              <span>{name(m.name)} <small className="co-dim">{m.team}{m.age != null ? ` · ${m.age}` : ''}</small></span>
              <b className={m.delta > 0 ? 'co-good' : 'co-bad'}>{signed(m.delta)}</b>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
  const retired = allRetired ? view.retired : view.retired.slice(0, RETIRED_ROWS);

  return (
    <div className={team ? 'dv-split' : 'dv-split dv-league-only'}>
      {team && (
        <section className="rc-card">
          <h3 className="rc-h">{team} · this summer</h3>
          {view.yours.length === 0 ? <p className="eos-muted">No players under contract.</p> : view.yours.map((y) => (
            <div key={y.name} className="dv-row">
              <span className="dv-name">{name(y.name)} {y.age != null && <small>{y.age}</small>}</span>
              <span className="dv-pos">{y.position}</span>
              <div className="dv-track" aria-hidden="true">
                <div className="dv-base" style={{ width: `${Math.min(y.before, y.after)}%` }} />
                {y.delta !== 0 && (
                  <div className={y.delta > 0 ? 'dv-up' : 'dv-down'}
                       style={{ left: `${Math.min(y.before, y.after)}%`, width: `${Math.abs(y.delta)}%` }} />
                )}
              </div>
              <b className={y.delta > 0 ? 'co-good' : y.delta < 0 ? 'co-bad' : 'co-dim'}>
                {y.delta === 0 ? y.after : `${y.before}→${y.after}`}
              </b>
            </div>
          ))}
          <p className="eos-muted dv-net">
            Net {signed(view.net.total)} OVR across the roster · {view.net.up} up, {view.net.down} down, {view.net.same} unchanged
          </p>
        </section>
      )}

      <div className="co-col">
        {movers('League risers', view.risers, 'Nobody improved.')}
        {movers('Biggest drops', view.drops, 'Nobody declined.')}
        <section className="rc-card">
          <h3 className="rc-h">Retired · {view.retired.length}</h3>
          {view.retired.length === 0 ? <p className="eos-muted">Nobody retired this summer.</p> : (
            <ul className="rc-rows">
              {retired.map((r) => (
                <li key={`${r.name}-${r.team}`} className={r.yours ? 'dv-yours' : undefined}>
                  <span><b className="dv-ret">{r.name}</b> <small className="co-dim">{r.team}{r.age != null ? ` · ${r.age}` : ''}</small></span>
                  <span className="co-dim">{r.honour ?? `${r.ovr} OVR`}</span>
                </li>
              ))}
            </ul>
          )}
          {view.retired.length > RETIRED_ROWS && (
            <button type="button" className="dv-more" onClick={() => setAllRetired(!allRetired)}>
              {allRetired ? 'Show fewer' : `+${view.retired.length - RETIRED_ROWS} more`}
            </button>
          )}
        </section>
      </div>
    </div>
  );
};
