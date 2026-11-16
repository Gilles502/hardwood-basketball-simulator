// Your Office, "Season Reports": the live report of the current season, the archived annual reports and the
// selected report in full (owner's letter, chronicle, objectives outcome, leaders and awards).
import React from 'react';
import { ChevronRight, Trophy } from 'lucide-react';
import { ownerLabel } from '../../utils/owners';
import { approvalTone, type AnnualSeasonReport } from './officeTypes';

const isChampion = (rep: AnnualSeasonReport) =>
  rep.playoff_result.includes('Campione') || rep.playoff_result.includes('Champion');

const outcomePill = (status: string) =>
  status === 'Completed' ? <span className="of-pill is-ok">Completed</span>
    : status === 'Failed' ? <span className="of-pill is-bad">Failed</span>
    : <span className="of-pill is-warn">In progress</span>;

interface ReportsTabProps {
  reports: AnnualSeasonReport[];
  liveReport: AnnualSeasonReport | null;
  selected: number | 'live';
  onSelect: (key: number | 'live') => void;
}

export const ReportsTab: React.FC<ReportsTabProps> = ({ reports, liveReport, selected, onSelect }) => {
  const shown: AnnualSeasonReport | null =
    selected === 'live' ? liveReport : (reports[selected] || liveReport || null);

  return (
    <div className="of-reports">
      <section className="of-card" aria-labelledby="of-timeline-head">
        <h3 className="of-card-head" id="of-timeline-head">Seasons <small>{reports.length} archived</small></h3>
        <div className="of-rep-list">
          <button type="button" className="of-rep" aria-pressed={selected === 'live'} onClick={() => onSelect('live')}>
            <b><i className="of-live-dot" aria-hidden="true" /> Current season (live)</b>
            <span>{liveReport ? `${liveReport.record} · ${liveReport.conference_rank}` : 'Underway'}</span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
          {reports.map((rep, idx) => (
            <button key={idx} type="button" className={`of-rep${isChampion(rep) ? ' is-champion' : ''}`}
              aria-pressed={selected === idx} onClick={() => onSelect(idx)}>
              <b>{isChampion(rep) && <Trophy size={14} aria-label="Champion" />} {rep.year} · {rep.team_name}</b>
              <span>{rep.record} · {rep.playoff_result}</span>
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          ))}
          {reports.length === 0 && (
            <p className="of-note">No past season reports archived. Finish your first season to unlock the archive.</p>
          )}
        </div>
      </section>

      {shown ? (
        <div className="of-detail">
          <section className="of-card">
            <div className="of-detail-head">
              <div>
                <span className="of-eyebrow">{shown.is_live ? 'Live season report' : `Official ${shown.year} review`}</span>
                <h3>{shown.team_name}</h3>
                <div className="of-chips">
                  <span className="of-pill">Record {shown.record} ({Math.round(shown.win_pct * 100)}% W)</span>
                  <span className="of-pill is-info">{shown.conference_rank}</span>
                  <span className="of-pill is-ok">{shown.playoff_result}</span>
                </div>
              </div>
              <div className="of-detail-approval">
                <span className="of-note">Ownership approval</span>
                <div className={`of-big of-tone-${approvalTone(shown.approval_rating)}`}>{shown.approval_rating}%</div>
                <span className="of-note">{shown.status_label}</span>
              </div>
            </div>
          </section>

          <section className="of-card">
            <h3 className="of-card-head">{shown.owner_letter_title}</h3>
            <p className="of-note">Signed by <strong>{shown.owner_name}</strong> (Owner · {ownerLabel(shown.owner_personality)})</p>
            <p className="of-letter">"{shown.owner_letter_content}"</p>
          </section>

          <section className="of-card">
            <h3 className="of-card-head">Season chronicle</h3>
            <p className="of-text">{shown.narrative_story}</p>
          </section>

          <div className="of-grid2">
            <section className="of-card">
              <h3 className="of-card-head">Objectives <small>{shown.objectives_completed_count} / {shown.objectives_total_count} completed</small></h3>
              <ul className="of-list">
                {shown.objectives.map((obj, i) => (
                  <li key={i} className="of-row of-row-col">
                    <div><b>{obj.title}</b>{outcomePill(obj.status)}</div>
                    <small>{obj.description}</small>
                  </li>
                ))}
              </ul>
            </section>

            <section className="of-card">
              <h3 className="of-card-head">Leaders &amp; awards</h3>
              {shown.awards && shown.awards.length > 0 && (
                <div className="of-chips">
                  {shown.awards.map((aw, i) => <span key={i} className="of-pill is-warn">{aw}</span>)}
                </div>
              )}
              <ul className="of-list">
                {shown.top_players.map((tp, i) => (
                  <li key={i} className="of-row of-row-col">
                    <div><b>{tp.name}</b><small>{tp.role} · {tp.ovr} OVR</small></div>
                    <span className="of-stat-line">{tp.ppg} PPG · {tp.rpg} RPG · {tp.apg} APG</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      ) : (
        <div className="of-card of-empty">Select a season from the list to view its board evaluation report.</div>
      )}
    </div>
  );
};
