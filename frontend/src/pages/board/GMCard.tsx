// One team's front office (mockup "GM card"): the GM, the plan and why, the coach and what the GM looks for him,
// the owner, and the moves made for the plan. Payload from /api/front_office/gm?team=.
import React, { useEffect, useState } from 'react';
import { ownerLabel } from '../../utils/owners';
import { TeamCrest } from '../../components/TeamCrest';
import type { CareerJob, GMCardPayload, GMSkills } from './types';

const SKILL_LABELS: [keyof GMSkills, string][] = [['trade', 'Trades'], ['contracts', 'Contracts'], ['draft', 'Draft']];
const MOVE_KIND: Record<string, string> = { trade: 'Trade', signing: 'Signing', let_walk: 'Let go', draft: 'Draft' };

export const SkillBars: React.FC<{ skills: GMSkills }> = ({ skills }) => (
  <div className="an-bars">
    {SKILL_LABELS.map(([key, label]) => (
      <div key={key} className="an-bar">
        <span className="an-bar-label">{label}</span>
        <span className="an-bar-track" role="img" aria-label={`${label} skill ${skills[key]} out of 100`}>
          <span className={`an-bar-fill${skills[key] >= 75 ? ' is-top' : skills[key] < 50 ? ' is-bottom' : ''}`}
            style={{ width: `${skills[key]}%` }} />
        </span>
        <span className="an-bar-num">{skills[key]}</span>
      </div>
    ))}
  </div>
);

const yearsOf = (j: CareerJob) => (j.to_year === null || j.to_year === j.from_year ? `${j.from_year}` : `${j.from_year}-${j.to_year}`);

const CareerList: React.FC<{ career: CareerJob[] }> = ({ career }) => (
  <ul className="fo-career" aria-label="Career">
    {career.map((j, i) => (
      <li key={i}>
        <TeamCrest name={j.team} size={20} />
        <span className="fo-career-main">
          <b>{j.team}</b> <span className="fo-career-years">{yearsOf(j)}</span>
          <span className="fo-career-rec">
            {j.wins}-{j.losses}
            {j.playoffs > 0 && ` · ${j.playoffs} playoff${j.playoffs === 1 ? '' : 's'}`}
            {j.titles > 0 && ` · ${j.titles} title${j.titles === 1 ? '' : 's'}`}
          </span>
          {j.awards.length > 0 && <span className="fo-career-awards">{j.awards.join(' · ')}</span>}
        </span>
        <span className={`an-tag fo-chip${j.end === null ? ' is-current' : ''}`}>{j.end_label}</span>
      </li>
    ))}
  </ul>
);

const scale = (value: number | null) => (value === null ? '—' : `${value}/5`);

export const GMCard: React.FC<{ team: string; onClose: () => void }> = ({ team, onClose }) => {
  const [card, setCard] = useState<GMCardPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setCard(null);
    setFailed(null);
    fetch(`/api/front_office/gm?team=${encodeURIComponent(team)}&_t=${Date.now()}`)
      .then((r) => r.json())
      .then((json) => { if (alive) { if (json.error) setFailed(json.error); else setCard(json); } })
      .catch(() => { if (alive) setFailed('Could not load this front office.'); });
    return () => { alive = false; };
  }, [team]);

  return (
    <aside className="an-card fo-card" aria-label={`${team} front office`}>
      <div className="an-card-top">
        <span className="an-kicker">{team} · front office</span>
        <button type="button" className="an-close" aria-label="Close card" onClick={onClose}>✕</button>
      </div>
      {failed && <p className="an-card-text">{failed}</p>}
      {!card && !failed && <div className="an-loading fo-card-loading"><div className="spinner"></div></div>}
      {card && <CardBody card={card} />}
    </aside>
  );
};

const CardBody: React.FC<{ card: GMCardPayload }> = ({ card }) => {
  const { gm, plan, coach, owner } = card;
  return (
    <>
      {card.is_user ? (
        <>
          <div className="an-card-name">{card.user_name}</div>
          <div className="an-card-line">You are the GM here: your office is in the first tab.</div>
        </>
      ) : gm ? (
        <>
          <div className="an-card-name">{gm.name}{gm.interim && <span className="an-tag fo-chip fo-tag-gap">Interim</span>}</div>
          <div className="an-card-line">
            Age {gm.age} · {gm.years_as_gm} {gm.years_as_gm === 1 ? 'year' : 'years'} as GM · {gm.tenure} with the team
          </div>
          <div className="fo-chips" aria-label="Philosophy">
            {gm.traits.map((t) => <span key={t.code} className="an-tag fo-chip">{t.label}</span>)}
          </div>
          <div className="an-card-sub">Skills</div>
          <SkillBars skills={gm.skills} />
          {gm.career.length > 0 && (
            <>
              <div className="an-card-sub">Career</div>
              <CareerList career={gm.career} />
            </>
          )}
          {gm.hiring_notes.length > 0 && (
            <ul className="fo-notes" aria-label="Hiring notes">
              {gm.hiring_notes.map((n, i) => <li key={i}>{n.text}</li>)}
            </ul>
          )}
        </>
      ) : (
        <div className="an-card-line">No GM in this seat.</div>
      )}

      {plan && (
        <>
          <div className="an-card-sub">The plan</div>
          <div className="fo-plan-head">
            <b>{plan.label}</b>
            <span>season {plan.seasons_held}{plan.expected_seasons ? ` of ~${plan.expected_seasons}` : ''}</span>
          </div>
          <p className="an-card-text">{plan.reason}</p>
          {plan.history.length > 1 && (
            <ol className="fo-history" aria-label="Plan history">
              {plan.history.map((h, i) => (
                <li key={i}>
                  <b>{h.year}</b>
                  <span>{h.from ? `${h.from} → ${h.to}` : `Started as ${h.to}`}{h.checkpoint === 'deadline' ? ' (deadline)' : ''}</span>
                  <em>{h.reason}</em>
                </li>
              ))}
            </ol>
          )}
        </>
      )}

      {coach && (
        <>
          <div className="an-card-sub">The coach</div>
          <p className="an-card-text">
            <b>{coach.name ?? 'Unknown'}</b>{coach.style ? ` · ${coach.style}` : ''}
            {coach.wants && <><br />The GM looks for: {coach.wants}</>}
          </p>
        </>
      )}

      <div className="an-card-sub">The owner</div>
      <div className="an-figures">
        <div><b>{ownerLabel(owner.personality)}</b><span>Owner</span></div>
        <div><b>{scale(owner.patience)}</b><span>Patience</span></div>
        <div><b>{scale(owner.spending)}</b><span>Spending</span></div>
      </div>

      <div className="an-card-sub">Moves for the plan</div>
      {card.moves.length === 0 ? (
        <p className="an-card-text fo-quiet">{card.is_user ? 'Your moves are in your office.' : 'No moves yet.'}</p>
      ) : (
        <ul className="fo-moves">
          {card.moves.map((m, i) => (
            <li key={i}>
              <span className="fo-move-when">{m.when}</span>
              <span className="fo-move-text"><span className="an-tag fo-chip">{MOVE_KIND[m.kind] ?? m.kind}</span> {m.text}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
};
