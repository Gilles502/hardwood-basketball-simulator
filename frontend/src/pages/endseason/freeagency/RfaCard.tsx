// A CPU offer sheet on one of the user's restricted free agents: match it or let him go. The market waits for it.
import React from 'react';
import { contractLine, type RfaMatch } from './freeAgency';

interface RfaCardProps {
  match: RfaMatch;
  busy: boolean;
  onAnswer: (match: boolean) => void;
}

export const RfaCard: React.FC<RfaCardProps> = ({ match, busy, onAnswer }) => (
  <div className="eos-sheet fa-rfa">
    <div>
      <span className="eos-kicker">Restricted free agent · your decision</span>
      <p className="fa-rfa-line">
        <b>{match.team}</b> signed an offer sheet with <b>{match.player}</b>: {contractLine(match.salary, match.years, match.option_type)}.
        Match it to keep him, or let him go. The market waits for your answer.
      </p>
    </div>
    <div className="fa-rfa-actions">
      <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onAnswer(true)}>Match</button>
      <button type="button" className="btn btn-secondary fa-ink" disabled={busy} onClick={() => onAnswer(false)}>Let him go</button>
    </div>
  </div>
);
