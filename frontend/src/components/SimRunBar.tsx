import React from 'react';
import { Play, Square, X } from 'lucide-react';
import { useLeagueStore } from '../store/leagueStore';
import './SimRunBar.css';

/** The live run, visible on every page: where it is, where it stops, and Stop. */
export const SimRunBar: React.FC = () => {
  const simRun = useLeagueStore((s) => s.simRun);
  const currentDay = useLeagueStore((s) => s.leagueData?.current_day ?? 0);
  const stopSimRun = useLeagueStore((s) => s.stopSimRun);
  const clearSimRunError = useLeagueStore((s) => s.clearSimRunError);

  if (!simRun) return null;

  if (simRun.error) {
    return (
      <div className="sim-run-bar is-error" role="alert">
        <span className="srb-text">Simulation stopped: {simRun.error}</span>
        <button type="button" className="btn btn-secondary srb-btn" onClick={clearSimRunError}>
          <X size={14} /> Close
        </button>
      </div>
    );
  }

  const { fromDay, targetDay, label, stopRequested } = simRun;
  const span = targetDay !== null ? Math.max(targetDay - fromDay, 1) : null;
  const pct = span !== null ? Math.min(100, Math.max(0, ((currentDay - fromDay) / span) * 100)) : null;

  return (
    <div className="sim-run-bar" role="status">
      <Play size={14} className="srb-icon" />
      <span className="srb-text">
        {stopRequested ? 'Stopping after this day…' : 'Simulating…'}{' '}
        <b>Day {currentDay + 1}</b>
        {targetDay !== null && <> → Day {targetDay + 1}</>} <span className="srb-label">({label})</span>
      </span>
      <span className="srb-hint" title="Trades, signings, lineups and single games are locked until the run ends.">
        Trades and roster moves wait for Stop
      </span>
      <div className={`srb-track${pct === null ? ' is-open' : ''}`} aria-hidden="true">
        <div className="srb-fill" style={pct === null ? undefined : { width: `${pct}%` }} />
      </div>
      <button type="button" className="btn btn-secondary srb-btn" onClick={stopSimRun} disabled={stopRequested}>
        <Square size={12} /> Stop
      </button>
    </div>
  );
};
