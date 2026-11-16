// frontend/src/components/BoardConcernModal.tsx
import React, { useState } from 'react';
import { ShieldAlert, Shield, Sliders, UserX, AlertTriangle } from 'lucide-react';
import { ModalShell } from './ModalShell';
import './FrontOfficeDialogs.css';

interface BoardConcernData {
  owner_name: string;
  coach_name: string;
  reason: string;
  trigger_time?: string;
  options: Array<{
    action: string;
    label: string;
    description: string;
    consequences: string;
  }>;
}

interface BoardConcernModalProps {
  concern: BoardConcernData;
  onResolved: () => void;
  onClose?: () => void;
}

export const BoardConcernModal: React.FC<BoardConcernModalProps> = ({ concern, onResolved, onClose }) => {
  const [resolving, setResolving] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleResolve = async (action: string) => {
    try {
      setResolving(action);
      setErrorMsg(null);
      const res = await fetch('/api/board/concern/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to resolve concern');
      }

      onResolved();
    } catch (err: any) {
      setErrorMsg(err.message || 'Error resolving concern');
    } finally {
      setResolving(null);
    }
  };

  const busy = (action: string) => (resolving === action ? ' is-busy' : '');

  return (
    <ModalShell
      isOpen
      onClose={onClose ?? (() => {})}
      closable={!!onClose}
      dismissible={!!onClose}
      title="Board Concern: Head Coach Scrutiny"
      subtitle="Urgent executive summit"
      icon={<ShieldAlert size={22} />}
      maxWidth={680}
    >
      <div className="fd-body fd-root">
        <div className="fd-quote is-bad">
          <p><strong>Message from Principal Owner {concern.owner_name}:</strong></p>
          <p><em>"{concern.reason || `Our recent trajectory under Head Coach ${concern.coach_name} has fallen drastically below franchise standards. The ownership group is questioning this tactical direction. As General Manager, you have complete authority—tell us how you intend to handle this.`}"</em></p>
        </div>

        {errorMsg && (
          <div className="fd-notice is-bad" role="alert"><AlertTriangle size={16} aria-hidden="true" /> <span>{errorMsg}</span></div>
        )}

        <div className="fd-choices" role="group" aria-labelledby="bc-actions-label">
          <span className="fd-label" id="bc-actions-label">Select executive action</span>

          <button type="button" className={`fd-choice is-ok${busy('protect')}`} onClick={() => handleResolve('protect')} disabled={resolving !== null}>
            <span className="fd-choice-icon" aria-hidden="true"><Shield size={20} /></span>
            <span className="fd-choice-body">
              <span className="fd-choice-title">Stake Reputation & Protect Coach {concern.coach_name}</span>
              <span className="fd-choice-desc">Give Coach {concern.coach_name} your complete executive backing. Guarantees 100% job immunity from ownership firing.</span>
              <span className="fd-consequence">Consequence: +25% Coach Security. If performance does not recover within 15 games, GM Approval takes a penalty.</span>
            </span>
          </button>

          <button type="button" className={`fd-choice is-warn${busy('mandate_tactics')}`} onClick={() => handleResolve('mandate_tactics')} disabled={resolving !== null}>
            <span className="fd-choice-icon" aria-hidden="true"><Sliders size={20} /></span>
            <span className="fd-choice-body">
              <span className="fd-choice-title">Mandate Tactical Overhaul & Restructure Playbook</span>
              <span className="fd-choice-desc">Order an immediate alteration to offensive and defensive Points of Emphasis. Temporarily reassures the board.</span>
              <span className="fd-consequence">Consequence: +6% Board Approval immediately, resets ownership patience clock by 10 games.</span>
            </span>
          </button>

          <button type="button" className={`fd-choice is-bad${busy('authorize_firing')}`} onClick={() => handleResolve('authorize_firing')} disabled={resolving !== null}>
            <span className="fd-choice-icon" aria-hidden="true"><UserX size={20} /></span>
            <span className="fd-choice-body">
              <span className="fd-choice-title">Authorize Immediate Head Coach Dismissal</span>
              <span className="fd-choice-desc">Agree with the Board to part ways with Coach {concern.coach_name} and initiate a search in the coach market.</span>
              <span className="fd-consequence">Consequence: Coach is released immediately. Board Approval is preserved (+4%) and coaching market opens.</span>
            </span>
          </button>
        </div>
      </div>
    </ModalShell>
  );
};
export default BoardConcernModal;
