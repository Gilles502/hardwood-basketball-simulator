import React, { useState } from 'react';
import { AlertTriangle, ArrowRight, Briefcase, Compass, Eye } from 'lucide-react';
import { useLeagueStore } from '../store/leagueStore';
import { ModalShell } from './ModalShell';
import { ownerLabel } from '../utils/owners';
import './FrontOfficeDialogs.css';

interface JobOffer {
  team_name: string;
  owner_name: string;
  personality: string;
  salary: number;
  years: number;
  roster_avg_ovr: number;
  payroll: number;
  expectation: string;
}

interface GMJobMarketModalProps {
  isFired: boolean;
  firingMessage?: string | null;
  jobOffers: JobOffer[];
  onClose: () => void;
  onChooseManualTeam?: () => void;
}

export const GMJobMarketModal: React.FC<GMJobMarketModalProps> = ({
  isFired,
  firingMessage,
  jobOffers,
  onClose,
  onChooseManualTeam
}) => {
  const { fetchLeagueData, setPlayerTeam } = useLeagueStore();
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [message, setMessage] = useState<string | null>(null);

  const handleAcceptOffer = async (offer: JobOffer) => {
    setSubmitting(true);

    try {
      const res = await fetch('/api/board/accept_job_offer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team_name: offer.team_name,
          salary: offer.salary,
          years: offer.years
        })
      });
      const data = await res.json();
      if (data.success) {
        setMessage(data.message);
        await fetchLeagueData();
        setTimeout(() => {
          onClose();
        }, 1200);
      } else {
        setMessage(data.error || "Error accepting GM contract offer.");
      }
    } catch (err) {
      console.error("Error accepting the GM offer:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSpectatorMode = async () => {
    setSubmitting(true);
    try {
      await setPlayerTeam("");
      onClose();
    } catch (err) {
      console.error("Error switching to spectator:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell
      isOpen
      onClose={onClose}
      closable={false}
      dismissible={false}
      title={isFired ? 'Front Office Firing & GM Job Market' : 'General Manager Job Openings'}
      subtitle={isFired ? 'Your tenure has come to an end' : 'Contract proposals for your front office leadership'}
      icon={isFired ? <AlertTriangle size={22} /> : <Briefcase size={22} />}
      maxWidth={880}
      footerStart={
        <button
          type="button"
          className="ms-btn ms-btn-secondary fd-btn-sm"
          onClick={() => {
            if (onChooseManualTeam) {
              onChooseManualTeam();
            } else {
              onClose();
            }
          }}
          disabled={submitting}
        >
          <Compass size={16} aria-hidden="true" /> Choose a franchise manually
        </button>
      }
      footerEnd={
        <button type="button" className="ms-btn fd-btn-ghost fd-btn-sm" onClick={handleSpectatorMode} disabled={submitting}>
          <Eye size={16} aria-hidden="true" /> Continue as spectator (no team)
        </button>
      }
    >
      <div className="fd-body fd-root">
        <p className="fd-lead">
          {isFired
            ? 'Your tenure with your previous franchise has come to an end. Several teams have submitted proposals to hire you as their new General Manager!'
            : 'Review the contract proposals submitted by franchises seeking your front office leadership.'}
        </p>

        {firingMessage && (
          <div className="fd-notice is-bad">
            <AlertTriangle size={18} aria-hidden="true" />
            <span><strong>Official front office termination notice:</strong> {firingMessage}</span>
          </div>
        )}

        {message && <div className="fd-notice is-ok" role="status"><span>{message}</span></div>}

        <div className="fd-head-row">
          <h3><Briefcase size={18} aria-hidden="true" /> Available job openings ({jobOffers.length})</h3>
          <span className="fd-muted">Select a franchise to continue your career</span>
        </div>

        <div className="fd-offers">
          {jobOffers.map((offer, idx) => (
            <article key={idx} className="fd-offer">
              <div className="fd-offer-main">
                <h4>{offer.team_name} <span className="fd-pill is-info">{offer.expectation}</span></h4>
                <div className="fd-offer-facts">
                  <span>Owner: <strong>{offer.owner_name}</strong> ({ownerLabel(offer.personality)})</span>
                  <span>Roster avg: <strong>{offer.roster_avg_ovr} OVR</strong></span>
                  <span>Payroll: <strong>${offer.payroll}M</strong></span>
                </div>
              </div>
              <div className="fd-offer-terms">
                <div>
                  <div className="fd-big">${offer.salary}M <small>/yr</small></div>
                  <div className="fd-offer-years">{offer.years} year contract</div>
                </div>
                <button type="button" className="ms-btn ms-btn-primary fd-btn-sm" onClick={() => handleAcceptOffer(offer)} disabled={submitting}>
                  Accept offer <ArrowRight size={15} aria-hidden="true" />
                </button>
              </div>
            </article>
          ))}

          {jobOffers.length === 0 && (
            <div className="fd-empty">No automatic job offers received. You can choose a franchise manually below.</div>
          )}
        </div>
      </div>
    </ModalShell>
  );
};
