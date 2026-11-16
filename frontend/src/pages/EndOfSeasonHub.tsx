// File: frontend/src/pages/EndOfSeasonHub.tsx
// The End of Season Hub: the only place that advances the offseason. A route rail of the 9 phases, the current
// phase's content, and one action bar with the single "Next" button. The server says which phase is current.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import type { Tab } from '../navigation';
import { PHASES, defaultNextLabel, nextRequest, offseasonLabel } from '../utils/endSeason';
import { RecapPhase } from './endseason/RecapPhase';
import { OptionsPhase } from './endseason/OptionsPhase';
import { DevelopmentPhase } from './endseason/DevelopmentPhase';
import { LotteryPhase } from './endseason/LotteryPhase';
import { TradesPhase } from './endseason/TradesPhase';
import { DraftPhase } from './endseason/DraftPhase';
import { FreeAgencyPhase } from './endseason/FreeAgencyPhase';
import { CutsPhase } from './endseason/CutsPhase';
import { NewSeasonPhase } from './endseason/NewSeasonPhase';
import { RosterButton } from './endseason/RosterPopup';
import type { PhaseBarState, PhaseProps } from '../utils/endSeason';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './endseason/EndSeason.css';

/** One line for the action bar when the phase has nothing blocking. */
const PHASE_HINTS = [
  'The season is over. Look back at it, then open the offseason.',
  'Decide your team options, then confirm them.',
  'Progression and retirements are in.',
  'The lottery sets the order of the draft.',
  'Last chance to deal before the draft.',
  'Make your picks; the rest of the draft runs on its own.',
  'The free-agent market is open.',
  'Teams cut down to the roster limit.',
  'Everything is set for the new season.',
];

const PlaceholderPhase: React.FC<PhaseProps & { phase: number }> = ({ phase }) => (
  <div className="eos-sheet eos-placeholder">{PHASES[phase]}: coming in the next task.</div>
);

/** Phase components, filled in as they are built; missing ones show a placeholder. */
const PHASE_COMPONENTS: (React.FC<PhaseProps> | null)[] = [RecapPhase, OptionsPhase, DevelopmentPhase, LotteryPhase, TradesPhase, DraftPhase, FreeAgencyPhase, CutsPhase, NewSeasonPhase];

interface EndOfSeasonHubProps {
  onNavigate: (tab: Tab) => void;
}

export const EndOfSeasonHub: React.FC<EndOfSeasonHubProps> = ({ onNavigate }) => {
  const { leagueData, fetchLeagueData } = useLeagueStore();
  // The bar belongs to the phase that set it, so a phase's first report is never wiped by the hub's reset.
  const [barOf, setBarOf] = useState<{ phase: number | null; bar: PhaseBarState }>({ phase: null, bar: {} });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewPhase, setViewPhase] = useState<number | null>(null);
  const busyRef = useRef(false);

  const status = leagueData?.end_season;
  const current = status?.open ? status.phase : null;

  const setBar = useCallback((bar: PhaseBarState) => setBarOf({ phase: current, bar }), [current]);
  const ignoreBar = useCallback(() => undefined, []);
  const bar = barOf.phase === current ? barOf.bar : {};

  // A new phase starts with the current phase on screen and no old error.
  useEffect(() => {
    setViewPhase(null);
    setError(null);
  }, [current]);

  if (!leagueData) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  const year = leagueData.anno_corrente;
  const team = leagueData.player_team_name;
  const shown = viewPhase ?? current;
  const readOnly = viewPhase !== null && viewPhase !== current;

  const advance = async () => {
    if (current === null || busyRef.current || bar.blocking) return;
    if (bar.confirm && !window.confirm(bar.confirm)) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      const { url, body } = nextRequest(current, bar.payload);
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.error) throw new Error(data?.error || `Request failed (${response.status})`);
      await fetchLeagueData();
      if (current === PHASES.length - 1) onNavigate('dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const phaseProps: PhaseProps = { readOnly, onBar: readOnly ? ignoreBar : setBar, onAdvanced: fetchLeagueData, onNavigate };
  const Phase = shown !== null ? PHASE_COMPONENTS[shown] : null;

  return (
    <div className="eos-root">
      <div className="dash-header">
        <div>
          <h1 className="dash-title">End of Season Hub</h1>
          <span className="dash-subtitle">{[offseasonLabel(year), team].filter(Boolean).join(' · ')}</span>
        </div>
        <div className="dash-badges"><RosterButton /></div>
      </div>

      <ol className="eos-rail" aria-label="Offseason phases">
        {PHASES.map((label, i) => {
          const state = current === null ? 'is-future' : i < current ? 'is-done' : i === current ? 'is-current' : 'is-future';
          const clickable = current !== null && i <= current;
          return (
            <li key={label} className={`eos-stop ${state}${shown === i ? ' is-shown' : ''}`}>
              <button
                type="button"
                disabled={!clickable}
                onClick={() => setViewPhase(i === current ? null : i)}
                aria-current={i === current ? 'step' : undefined}
              >
                <span className="eos-dot">{current !== null && i < current ? '✓' : i + 1}</span>
                <span className="eos-stop-label">{label}</span>
              </button>
            </li>
          );
        })}
      </ol>

      {current === null ? (
        <div className="eos-sheet eos-closed">
          <h2>The offseason opens when the playoffs end</h2>
          <p>Finish the season and the playoffs; the hub then walks you through every step to the next season.</p>
        </div>
      ) : (
        <>
          {readOnly && (
            <div className="eos-viewing">
              Looking back at <b>{PHASES[shown!]}</b>.
              <button type="button" onClick={() => setViewPhase(null)}>Back to {PHASES[current]}</button>
            </div>
          )}
          <section className="eos-phase" key={shown ?? 'none'}>
            {Phase ? <Phase {...phaseProps} /> : <PlaceholderPhase {...phaseProps} phase={shown!} />}
          </section>

          {!readOnly && (
            <div className={`eos-bar${busy ? ' is-busy' : ''}`}>
              <span className={`eos-bar-text${error ? ' is-error' : ''}`}>
                {error ?? bar.blocking ?? PHASE_HINTS[current]}
              </span>
              <button
                type="button"
                className="btn btn-primary"
                onClick={advance}
                disabled={busy || Boolean(bar.blocking)}
              >
                {busy ? 'Working…' : bar.nextLabel ?? defaultNextLabel(current, year)}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};
