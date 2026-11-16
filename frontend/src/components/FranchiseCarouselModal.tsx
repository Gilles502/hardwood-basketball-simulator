// frontend/src/components/FranchiseCarouselModal.tsx
import React, { useState, useEffect } from 'react';
import { Building, Check, UserX, Briefcase, Lock, AlertTriangle } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { ownerLabel } from '../utils/owners';
import './FrontOfficeDialogs.css';

interface JobOffer {
  team_name: string;
  conference: string;
  roster_ovr?: number;
  roster_avg_top5?: number;
  cap_space?: number;
  payroll?: number;
  owner_name?: string;
  owner_personality?: string;
  prestige_required?: number;
  min_prestige?: number;
  salary_per_year?: number;
  offered_salary?: number;
  years?: number;
  offered_years?: number;
  is_eligible?: boolean;
}

interface JobCarouselResponse {
  offers: JobOffer[];
  prestige_score: number;
}

/** Job market: offers from franchises and voluntary resignation. Renders inline (Front Office page) or, when
 *  onClose is given, inside the shared dialog shell. */
interface FranchiseCarouselModalProps {
  currentTeamName: string;
  onSwitchedTeam: (newTeamName: string) => void;
  onClose?: () => void;
}

export const FranchiseCarouselModal: React.FC<FranchiseCarouselModalProps> = ({ currentTeamName, onSwitchedTeam, onClose }) => {
  const [data, setData] = useState<JobCarouselResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [acceptingTeam, setAcceptingTeam] = useState<string | null>(null);
  const [showResignConfirm, setShowResignConfirm] = useState(false);
  const [resigning, setResigning] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchCarousel = async () => {
    try {
      setLoading(true);
      const res = await fetch(`/api/board/job_carousel?_t=${Date.now()}`);
      if (!res.ok) throw new Error('Failed to load job carousel');
      const json: JobCarouselResponse = await res.json();
      setData(json);
      setErrorMsg(null);
    } catch (err: any) {
      setErrorMsg(err.message || 'Error loading job carousel');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCarousel();
  }, []);

  const handleAcceptOffer = async (offer: JobOffer) => {
    try {
      setAcceptingTeam(offer.team_name);
      setErrorMsg(null);
      const res = await fetch('/api/board/switch_team', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_team_name: offer.team_name,
          offer: {
            salary_per_year: offer.salary_per_year ?? offer.offered_salary ?? 5.0,
            offered_salary: offer.salary_per_year ?? offer.offered_salary ?? 5.0,
            years: offer.years ?? offer.offered_years ?? 4,
            offered_years: offer.years ?? offer.offered_years ?? 4
          }
        })
      });
      const result = await res.json();
      if (!res.ok || !result.success) {
        throw new Error(result.error || 'Failed to switch franchise');
      }

      setSuccessMsg(result.message || `Welcome to the ${offer.team_name}!`);
      setTimeout(() => {
        onSwitchedTeam(offer.team_name);
      }, 1500);
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setAcceptingTeam(null);
    }
  };

  const handleResign = async () => {
    try {
      setResigning(true);
      setErrorMsg(null);
      const res = await fetch('/api/board/resign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const result = await res.json();
      if (!res.ok || !result.success) {
        throw new Error(result.error || 'Failed to resign');
      }

      setShowResignConfirm(false);
      setSuccessMsg(result.message || 'Resignation accepted. Exploring open vacancies.');
      await fetchCarousel();
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setResigning(false);
    }
  };

  const prestige = data?.prestige_score;

  const resignControls = currentTeamName && currentTeamName !== 'Free Agent GM' ? (
    !showResignConfirm ? (
      <button type="button" className="ms-btn fd-btn-danger fd-btn-sm" onClick={() => setShowResignConfirm(true)}>
        <UserX size={15} aria-hidden="true" /> Voluntarily resign as GM
      </button>
    ) : (
      <div className="fc-actions">
        <button type="button" className="ms-btn fd-btn-solid-danger fd-btn-sm" onClick={handleResign} disabled={resigning}>
          {resigning ? 'Processing...' : 'Confirm resignation'}
        </button>
        <button type="button" className="ms-btn ms-btn-secondary fd-btn-sm" onClick={() => setShowResignConfirm(false)}>
          Cancel
        </button>
      </div>
    )
  ) : null;

  const content = (
    <div className="fc-root">
      <div className="fc-banner">
        <p>
          Current franchise: <strong>{currentTeamName || 'Free Agent Executive'}</strong> · Executive prestige:{' '}
          <strong className="fc-prestige">{prestige?.toFixed(1) || '65.0'}/100</strong>
        </p>
        {resignControls}
      </div>

      {errorMsg && (
        <div className="fd-notice is-bad" role="alert"><AlertTriangle size={16} aria-hidden="true" /> <span>{errorMsg}</span></div>
      )}
      {successMsg && (
        <div className="fd-notice is-ok" role="status"><Check size={16} aria-hidden="true" /> <span>{successMsg}</span></div>
      )}

      {loading ? (
        <div className="fd-loading">
          <div className="spinner" />
          <p>Scouting available league front office vacancies...</p>
        </div>
      ) : (
        <div className="fc-grid">
          {data?.offers?.map((offer) => {
            const isAccepting = acceptingTeam === offer.team_name;
            const rosterRating = offer.roster_ovr ?? Math.round(offer.roster_avg_top5 ?? 75);
            const capVal = typeof offer.cap_space === 'number' ? offer.cap_space : Math.max(0, 155 - (offer.payroll ?? 140));
            const ownerName = offer.owner_name || 'Ownership Board';
            const ownerAttitude = offer.owner_personality || 'Bilanciato';
            const salaryVal = typeof offer.salary_per_year === 'number' ? offer.salary_per_year : (offer.offered_salary ?? 4.5);
            const termYears = offer.years ?? offer.offered_years ?? 4;
            const reqPrestige = offer.prestige_required ?? offer.min_prestige ?? 50;
            const userPrestige = data?.prestige_score ?? 65;
            const canSign = offer.is_eligible !== undefined ? Boolean(offer.is_eligible) : userPrestige >= reqPrestige;

            return (
              <article key={offer.team_name} className={`fc-card${canSign ? '' : ' is-locked'}`}>
                <div className="fc-card-head">
                  <div>
                    <span className="fd-label">{offer.conference} Conference</span>
                    <h4>{offer.team_name}</h4>
                  </div>
                  <span className={`fd-pill ${canSign ? 'is-ok' : 'is-bad'}`}>
                    {canSign ? 'Offer available' : 'Prestige insufficient'}
                  </span>
                </div>

                <div className="fc-facts">
                  <div><span>Roster rating</span><strong>{rosterRating} OVR</strong></div>
                  <div>
                    <span>Cap space</span>
                    <strong className={capVal >= 0 ? 'fd-tone-ok' : 'fd-tone-warn'}>
                      ${capVal >= 0 ? `+${capVal.toFixed(1)}M` : `${capVal.toFixed(1)}M`}
                    </strong>
                  </div>
                  <div><span>Owner</span><strong>{ownerName}</strong></div>
                  <div><span>Attitude</span><strong>{ownerLabel(ownerAttitude)}</strong></div>
                </div>

                <div className="fc-term">
                  <div>
                    <span className="fd-label">Contract term</span>
                    <b>${salaryVal.toFixed(1)}M / yr · {termYears} years</b>
                  </div>
                  <div className="fc-term-req">
                    <span className="fd-muted">Required prestige</span>
                    <b>{reqPrestige}</b>
                  </div>
                </div>

                {canSign ? (
                  <button type="button" className="ms-btn ms-btn-primary" onClick={() => handleAcceptOffer(offer)} disabled={isAccepting}>
                    <Briefcase size={16} aria-hidden="true" /> {isAccepting ? 'Finalizing contract...' : 'Accept job offer'}
                  </button>
                ) : (
                  <div className="fc-locked">
                    <Lock size={14} aria-hidden="true" /> Requires {offer.prestige_required} prestige (current: {data?.prestige_score?.toFixed(1)})
                  </div>
                )}
              </article>
            );
          })}
          {!data?.offers?.length && <div className="fd-empty">No franchise has an opening for you right now.</div>}
        </div>
      )}
    </div>
  );

  if (!onClose) return content;

  return (
    <ModalShell
      isOpen
      onClose={onClose}
      title="Franchise Carousel & Job Market"
      subtitle="Offers from franchises looking for a general manager"
      icon={<Building size={22} />}
      maxWidth={1040}
    >
      <div className="fd-body">{content}</div>
    </ModalShell>
  );
};
export default FranchiseCarouselModal;
