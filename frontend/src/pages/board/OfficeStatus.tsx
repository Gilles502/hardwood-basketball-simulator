// Your Office, left column: owner, approval, job security, patience and the user's GM contract (always visible).
import React from 'react';
import { Sparkles } from 'lucide-react';
import { ownerLabel } from '../../utils/owners';
import { approvalTone, securityTone, type BoardProfile, type GMContract } from './officeTypes';

const OWNER_HINTS: Record<string, string> = {
  Risparmiatore: 'Strict focus on luxury tax avoidance. Prefers dumping heavy contracts before deadlines.',
  Spendaccione: 'Win-now mentality. Willing to pay the tax, but demands immediate playoff results.',
  Ricostruttore: 'Extremely patient. Highly values accumulating first-round picks and developing youth.',
  Esigente: 'Short leash. Job security fluctuates rapidly based on short-term results.',
  Bilanciato: 'Balanced management. Realistic expectations calibrated to roster talent level.',
  Equilibrato: 'Balanced management. Realistic expectations calibrated to roster talent level.',
};

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w.charAt(0).toUpperCase()).join('') || '?';

const pct = (value: number, max: number) => `${Math.min(100, Math.max(0, (value / max) * 100))}%`;

interface OfficeStatusProps {
  board: BoardProfile;
  contract: GMContract | null;
  teamName: string;
  extending: boolean;
  extensionMessage: string | null;
  onExtend: () => void;
}

export const OfficeStatus: React.FC<OfficeStatusProps> = ({ board, contract, teamName, extending, extensionMessage, onExtend }) => {
  const tone = approvalTone(board.approval_rating);
  const hint = OWNER_HINTS[board.personality];
  const offer = contract?.can_extend ? contract.extension_offered : null;

  return (
    <aside className="of-col of-status" aria-label="Office status">
      <div className="of-card">
        <div className="of-owner">
          <div className="of-avatar" aria-hidden="true">{initials(board.owner_name)}</div>
          <div>
            <b>{board.owner_name}</b>
            <span>Owner · {ownerLabel(board.personality)}</span>
          </div>
        </div>
        {hint && <p className="of-hint">{hint}</p>}

        <div>
          <div className={`of-big of-tone-${tone}`}>{board.approval_rating}<small>/ 100 approval</small></div>
          <div className={`of-meter is-${tone}`} style={{ marginTop: 8 }} role="meter" aria-label="Owner approval"
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={board.approval_rating}>
            <i style={{ width: pct(board.approval_rating, 100) }} />
          </div>
          <div className="of-scale" style={{ marginTop: 4 }}>
            <span>0 fired</span><span>50 hot seat</span><span>100 untouchable</span>
          </div>
        </div>

        <dl className="of-kv">
          <dt>Job security</dt>
          <dd><span className={`of-pill is-${securityTone(board.status_label)}`}>{board.status_label}</span></dd>
          <dt>Patience</dt>
          <dd>{board.patience_level} / 5</dd>
        </dl>
        <div className="of-meter is-thin is-info" role="meter" aria-label="Owner patience with the front office" aria-valuemin={0}
          aria-valuemax={5} aria-valuenow={board.patience_level}>
          <i style={{ width: pct(board.patience_level, 5) }} />
        </div>
        <dl className="of-kv">
          <dt>Spending</dt>
          <dd>{board.spending_attitude} / 5</dd>
        </dl>
        <div className="of-meter is-thin" role="meter" aria-label="Owner spending willingness (budget)" aria-valuemin={0}
          aria-valuemax={5} aria-valuenow={board.spending_attitude}>
          <i style={{ width: pct(board.spending_attitude, 5) }} />
        </div>
      </div>

      {contract && (
        <div className="of-card">
          <h3 className="of-card-head">Your contract <small>{teamName}</small></h3>
          <dl className="of-kv">
            <dt>Annual salary</dt>
            <dd>${contract.salary_per_year}M</dd>
            <dt>Years remaining</dt>
            <dd>{contract.years_remaining} {contract.years_remaining === 1 ? 'year' : 'years'}</dd>
          </dl>

          {offer && (
            <div className="of-offer">
              <b><Sparkles size={15} aria-hidden="true" /> Extension offer available</b>
              <p>Ownership offers you a {offer.years}-year extension at ${offer.salary}M/yr.</p>
              <button type="button" className="of-btn of-btn-primary of-btn-block" onClick={onExtend} disabled={extending}>
                {extending ? 'Accepting extension offer...' : 'Accept contract extension'}
              </button>
            </div>
          )}

          {!offer && !extensionMessage && <p className="of-note">No extension offer from the owner right now.</p>}
          {extensionMessage && <p className="of-result" role="status">{extensionMessage}</p>}
        </div>
      )}
    </aside>
  );
};
