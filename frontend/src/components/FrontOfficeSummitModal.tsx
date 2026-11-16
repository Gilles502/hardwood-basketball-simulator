// File: frontend/src/components/FrontOfficeSummitModal.tsx
import React, { useState, useEffect } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { useSettingsStore } from '../store/settingsStore';
import { Building, Briefcase, Target, CheckCircle2, Flame, Sprout } from 'lucide-react';
import { ModalShell } from './ModalShell';
import './FrontOfficeDialogs.css';

interface FrontOfficeSummitModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const FrontOfficeSummitModal: React.FC<FrontOfficeSummitModalProps> = ({ isOpen, onClose }) => {
  const { language } = useSettingsStore();
  const { leagueData, fetchLeagueData } = useLeagueStore();

  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [summitData, setSummitData] = useState<any>(null);
  const [selectedChoice, setSelectedChoice] = useState<'consensus' | 'ambitious' | 'patient_dev'>('consensus');
  const [resolutionSuccess, setResolutionSuccess] = useState<boolean>(false);
  const [resolvedRecord, setResolvedRecord] = useState<any>(null);

  const fetchSummit = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/front_office/summit?_t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setSummitData(data);
        if (data.completed && data.summit) {
          setResolvedRecord(data.summit);
          setResolutionSuccess(true);
        }
      }
    } catch (err) {
      console.error("Error loading front office summit:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchSummit();
    }
  }, [isOpen]);

  const proposal = summitData?.proposal;

  const handleConfirmDecision = async () => {
    setSubmitting(true);
    try {
      const res = await fetch('/api/front_office/summit/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ choice: selectedChoice })
      });
      if (res.ok) {
        const resData = await res.json();
        if (resData.success && resData.summit) {
          setResolvedRecord(resData.summit);
          setResolutionSuccess(true);
          await fetchLeagueData();
        }
      }
    } catch (err) {
      console.error("Error responding to GM summit:", err);
    } finally {
      setSubmitting(false);
    }
  };

  // Goal of a proposal or option: label and a theme tone for its pill.
  const getGoalBadge = (goal: string) => {
    switch (goal) {
      case 'CHAMPIONSHIP':
      case 'DOMINANCE':
        return { label: language === 'it' ? 'Titolo NBA' : 'Championship', tone: 'warn' };
      case 'PLAYOFFS':
        return { label: language === 'it' ? 'Playoff Garantiti' : 'Guaranteed Playoffs', tone: 'info' };
      case 'PLAY_IN':
        return { label: language === 'it' ? 'Qualificazione Play-In' : 'Play-In Contention', tone: 'quiet' };
      case 'PLAYOFF_HUNT':
        return { label: language === 'it' ? 'Corsa 8° Posto' : 'Playoff Hunt', tone: 'info' };
      case 'TANKING':
      case 'ASSET_GROWTH':
      default:
        return { label: language === 'it' ? 'Ricostruzione & Asset' : 'Rebuild & Development', tone: 'ok' };
    }
  };

  const showFooter = !!proposal && !resolutionSuccess;

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title={language === 'it' ? 'Summit Pre-Stagionale Front Office' : 'Pre-Season Front Office Summit'}
      subtitle={`GM & Coach Meeting · ${proposal?.team_name || leagueData?.player_team_name || ''} · ${language === 'it' ? 'Confronto strategico sulla rotta stagionale' : 'Seasonal strategic mandate alignment'}`}
      icon={<Building size={22} />}
      maxWidth={840}
      footerStart={showFooter ? (
        <span>{language === 'it' ? 'La decisione allineerà le aspettative della dirigenza e il mercato scambi.' : 'This mandate aligns Front Office expectations and trade deadline posture.'}</span>
      ) : undefined}
      footerEnd={showFooter ? (
        <>
          <button type="button" className="ms-btn ms-btn-secondary fd-btn-sm" onClick={onClose} disabled={submitting}>
            {language === 'it' ? 'Rimanda' : 'Postpone'}
          </button>
          <button type="button" className="ms-btn ms-btn-primary fd-btn-sm" onClick={handleConfirmDecision} disabled={submitting}>
            {submitting ? (language === 'it' ? 'Ratifica in corso...' : 'Ratifying...') : (language === 'it' ? 'Ratifica Obiettivo con il GM' : 'Ratify Mandate with GM')}
          </button>
        </>
      ) : undefined}
    >
      <div className="fd-body fd-root">
        {loading ? (
          <div className="fd-loading">
            <div className="spinner" />
            <p>{language === 'it' ? 'Convocazione del General Manager in corso...' : 'Convening Front Office Executive Summit...'}</p>
          </div>
        ) : resolutionSuccess && resolvedRecord ? (
          /* Completed: the agreed mandate */
          <div className="fd-center fd-done">
            <div className="fd-done-icon" aria-hidden="true"><CheckCircle2 size={30} /></div>
            <h3 className="fd-done-title">{language === 'it' ? 'Accordo di Franchigia Ratificato' : 'Franchise Mandate Ratified'}</h3>
            <p className="fd-lead fd-narrow">{resolvedRecord.feedback_msg}</p>

            <div className="fd-facts fd-narrow">
              <div><span className="fd-label">General Manager</span><strong>{resolvedRecord.gm_name}</strong></div>
              <div>
                <span className="fd-label">Agreed Target</span>
                <span className="fd-big">{resolvedRecord.target_wins} W</span>
                <span className="fd-muted">{resolvedRecord.agreed_goal}</span>
              </div>
              <div><span className="fd-label">Trade Posture</span><strong>{resolvedRecord.deadline_posture}</strong></div>
            </div>

            <div className="fd-quote fd-narrow fd-left">
              <span className="fd-label">{language === 'it' ? 'La risposta del Coach al GM:' : 'Head Coach statement to GM:'}</span>
              <p><em>"{resolvedRecord.coach_speech}"</em></p>
            </div>

            <div>
              <button type="button" className="ms-btn ms-btn-primary" onClick={onClose}>
                {language === 'it' ? 'Avvia la Stagione' : 'Proceed to Season'}
              </button>
            </div>
          </div>
        ) : proposal ? (
          /* Open summit: the GM's proposal and the coach's possible answers */
          <>
            <div className="fd-facts">
              <div>
                <span className="fd-label">General Manager</span>
                <strong><Briefcase size={12} aria-hidden="true" /> {proposal.gm_name}</strong>
              </div>
              <div><span className="fd-label">Average Top 5 OVR</span><strong>{proposal.avg_top5_ovr} OVR</strong></div>
              <div><span className="fd-label">Reference Star</span><strong>{proposal.star_player?.name} ({proposal.star_player?.ovr})</strong></div>
              <div>
                <span className="fd-label">GM Proposal</span>
                <span><span className={`fd-pill is-${getGoalBadge(proposal.proposed_goal).tone}`}>
                  {getGoalBadge(proposal.proposed_goal).label} ({proposal.proposed_wins} W)
                </span></span>
              </div>
            </div>

            <div className="fd-quote">
              <span className="fd-label">
                {language === 'it' ? `Messaggio Ufficiale del GM ${proposal.gm_name}:` : `Official Briefing from GM ${proposal.gm_name}:`}
              </span>
              <p><em>"{proposal.gm_statement}"</em></p>
            </div>

            <div className="fd-choices" role="radiogroup" aria-labelledby="fs-choice-label">
              <div className="fd-head-row">
                <h3 id="fs-choice-label"><Target size={16} aria-hidden="true" /> {language === 'it' ? 'Qual è la tua visione come Head Coach? (Seleziona la tua risposta al GM):' : 'What is your vision as Head Coach? (Select your response to the GM):'}</h3>
              </div>
              {proposal.options?.map((opt: any) => {
                const isSelected = selectedChoice === opt.key;
                const badge = getGoalBadge(opt.resulting_goal);
                return (
                  <button
                    type="button"
                    key={opt.key}
                    role="radio"
                    aria-checked={isSelected}
                    className="fd-choice"
                    onClick={() => setSelectedChoice(opt.key)}
                  >
                    <span className="fd-choice-body">
                      <span className="fd-choice-title">
                        {opt.key === 'consensus' && <CheckCircle2 size={16} aria-hidden="true" className="fd-tone-ok" />}
                        {opt.key === 'ambitious' && <Flame size={16} aria-hidden="true" className="fd-tone-warn" />}
                        {opt.key === 'patient_dev' && <Sprout size={16} aria-hidden="true" className="fd-tone-info" />}
                        {opt.label}
                        <span className={`fd-pill is-${badge.tone}`}>{badge.label} · {opt.target_wins} W</span>
                      </span>
                      <span className="fd-choice-desc"><em>"{opt.coach_speech}"</em></span>
                      <span className="fd-choice-meta">
                        <span><strong>GM Trust:</strong> {opt.board_impact}</span>
                        <span><strong>Deadline Trades:</strong> {opt.deadline_posture}</span>
                      </span>
                    </span>
                    <span className="fd-radio" aria-hidden="true" />
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <div className="fd-empty">{language === 'it' ? 'Nessun summit disponibile.' : 'No summit available.'}</div>
        )}
      </div>
    </ModalShell>
  );
};
