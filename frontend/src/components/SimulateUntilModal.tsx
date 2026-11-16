// File: frontend/src/components/SimulateUntilModal.tsx
import React, { useState } from 'react';
import { FastForward } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { TeamCrest } from './TeamCrest';
import { nickname } from '../utils/resultSheet';
import { eventLabels, parseIsoDate } from '../utils/scheduleEvents';
import './SimulateUntilModal.css';

/** The bits of a calendar day the route preview needs. */
interface RouteDay {
  day_index: number;
  date: string;
  events: string[];
  games: { home_team: string; away_team: string }[];
}

interface SimulateUntilModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentDayIndex: number;
  targetDayIndex: number;
  targetDateStr: string;
  totalDays: number;
  onConfirm: (targetDayIndex: number, includeTarget: boolean) => Promise<void>;
  /** Full calendar, to preview what gets skipped; without it the dialog only shows the day range. */
  days?: RouteDay[];
  /** Team whose skipped games are listed. */
  teamName?: string | null;
}

const shortDate = (iso: string | undefined) =>
  iso ? parseIsoDate(iso).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : '';
const monthDay = (iso: string) => parseIsoDate(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

export const SimulateUntilModal: React.FC<SimulateUntilModalProps> = ({
  isOpen,
  onClose,
  currentDayIndex,
  targetDayIndex,
  targetDateStr,
  totalDays,
  onConfirm,
  days = [],
  teamName = null,
}) => {
  const [includeTarget, setIncludeTarget] = useState<boolean>(false);

  if (!isOpen) return null;

  const daysToSimulate = Math.max(0, targetDayIndex - currentDayIndex + (includeTarget ? 1 : 0));
  const lastSimDay = currentDayIndex + daysToSimulate - 1;
  const landingDay = Math.min(lastSimDay + 1, totalDays - 1);
  const target = monthDay(targetDateStr);

  // What the sim skips: every day from today up to the last simulated one.
  const skipped = days.filter((d) => d.day_index >= currentDayIndex && d.day_index <= lastSimDay);
  const gameCount = skipped.reduce((n, d) => n + d.games.length, 0);
  const span = Math.max(lastSimDay - currentDayIndex, 1);
  const at = (dayIndex: number) => ((dayIndex - currentDayIndex) / span) * 100;
  const teamGames = teamName
    ? skipped.flatMap((d) => d.games
      .filter((g) => g.home_team === teamName || g.away_team === teamName)
      .map((g) => ({ day: d, home: g.home_team === teamName, opponent: g.home_team === teamName ? g.away_team : g.home_team })))
    : [];
  const events = skipped.flatMap((d) => eventLabels(d.events).map((label) => ({ day: d, label })));
  const fromDate = days.find((d) => d.day_index === currentDayIndex)?.date;

  // The run goes on in the background (run bar with Stop on every page): start it and close at once.
  const handleStartSim = () => {
    onConfirm(targetDayIndex, includeTarget).catch((err) => console.error('Error simulating until date:', err));
    onClose();
  };

  return (
    <ModalShell
      isOpen
      onClose={onClose}
      title={`Sim until ${target}`}
      subtitle="Fast-forward the regular season"
      icon={<FastForward size={20} />}
      maxWidth={620}
      footerEnd={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={handleStartSim} disabled={daysToSimulate === 0}>
            {`Sim ${daysToSimulate} ${daysToSimulate === 1 ? 'day' : 'days'}`}
          </button>
        </>
      }
    >
      <div className="su-body">
        <div className="su-route">
          <div className="su-ends">
            <div>
              <small>From</small>
              <b>Day {currentDayIndex + 1}</b>
              <small>{shortDate(fromDate)}</small>
            </div>
            <div className="su-mid">
              {daysToSimulate} {daysToSimulate === 1 ? 'day' : 'days'}{days.length > 0 && ` · ${gameCount} games`}
            </div>
            <div className="su-end">
              <small>Land on</small>
              <b>Day {landingDay + 1}</b>
              <small>{shortDate(days.find((d) => d.day_index === landingDay)?.date)}</small>
            </div>
          </div>

          {days.length > 0 && daysToSimulate > 0 && (
            <>
              <div className="su-track" aria-hidden="true">
                <div className="su-line" />
                <span className="su-dot is-end" style={{ left: '0%' }} />
                {teamGames.map((g) => <span key={g.day.day_index} className="su-dot is-game" style={{ left: `${at(g.day.day_index)}%` }} />)}
                {events.map((e) => <span key={`${e.label}-${e.day.day_index}`} className="su-ev" style={{ left: `${at(e.day.day_index)}%` }}>{e.label}</span>)}
                <span className="su-dot is-end" style={{ left: '100%' }} />
              </div>
              {teamName && (
                <>
                  <div className="su-cap">
                    {teamGames.length === 0
                      ? `${nickname(teamName)} have no games in these days`
                      : `${nickname(teamName)} games you'll skip (${teamGames.length})`}
                  </div>
                  {teamGames.length > 0 && (
                    <div className="su-games">
                      {teamGames.map((g) => (
                        <span key={g.day.day_index} className="su-game" title={shortDate(g.day.date)}>
                          <TeamCrest name={g.opponent} size={18} />
                          <em>{g.home ? 'vs' : '@'}</em> {nickname(g.opponent)}
                        </span>
                      ))}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>

        <div className="su-switch" role="radiogroup" aria-label="Where to stop">
          <button type="button" role="radio" aria-checked={!includeTarget} onClick={() => setIncludeTarget(false)}>
            Stop the day before
            <small>{Math.max(0, targetDayIndex - currentDayIndex)} days · {target} becomes today</small>
          </button>
          <button type="button" role="radio" aria-checked={includeTarget} onClick={() => setIncludeTarget(true)}>
            Include {target}
            <small>{Math.max(0, targetDayIndex - currentDayIndex + 1)} days · land on the day after</small>
          </button>
        </div>

      </div>
    </ModalShell>
  );
};
