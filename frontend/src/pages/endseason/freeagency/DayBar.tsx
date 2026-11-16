// The market's day bar: day N of M, "Next day", and what happened last night (the user's signings first).
import React, { useState } from 'react';
import type { NightMove, Signing } from './freeAgency';
import { NightReport } from './NightReport';

interface DayBarProps {
  day: number;
  daysTotal: number;
  completed: boolean;
  lastNight: Signing[];
  /** Last night's raises and pull-outs (CPU bidding). */
  moves?: NightMove[];
  /** OVR of a player still on the market (for a battle nobody has won yet). */
  ovrOf?: (name: string) => number | undefined;
  userTeam: string;
  busy: boolean;
  blocked: boolean;
  onNextDay: () => void;
}

export const DayBar: React.FC<DayBarProps> = ({ day, daysTotal, completed, lastNight, moves = [], ovrOf = () => undefined, userTeam, busy, blocked, onNextDay }) => {
  const [open, setOpen] = useState(true);
  const mine = lastNight.filter((s) => s.team === userTeam);
  const wars = new Set(moves.filter((m) => m.type === 'raise' || m.type === 'out').map((m) => m.player)).size;
  const hasReport = lastNight.length > 0 || wars > 0;
  return (
    <>
      <div className="fa-daybar">
        <span className="fa-day">{completed ? 'Free agency is over' : `Day ${day} / ${daysTotal}`}</span>
        <span className="fa-recap">
          {!hasReport ? (
            day <= 1 && !completed ? 'The market opens: teams make their first offers tonight.' : 'Nobody signed last night.'
          ) : (
            <>
              <b>Last night:</b> {lastNight.length} {lastNight.length === 1 ? 'signing' : 'signings'}
              {wars > 0 && <>, {wars} {wars === 1 ? 'bidding war' : 'bidding wars'}</>}
              {mine.length > 0 && <span className="is-yours"> · you signed {mine.map((s) => s.player).join(', ')}</span>}
              {' '}
              <button type="button" className="fa-night-toggle" onClick={() => setOpen((v) => !v)}>{open ? 'Hide report ▴' : 'Show report ▾'}</button>
            </>
          )}
        </span>
        {!completed && (
          <button type="button" className="btn btn-primary" onClick={onNextDay} disabled={busy || blocked}>
            {busy ? 'Working…' : 'Next day ▸'}
          </button>
        )}
      </div>
      {hasReport && open && <NightReport moves={moves} signings={lastNight} userTeam={userTeam} ovrOf={ovrOf} />}
    </>
  );
};
