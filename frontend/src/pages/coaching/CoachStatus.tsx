// Coaching page, left column: your head coach (ratings, contract, owner security, record, badges, Extend / Fire).
import React from 'react';
import { Plus } from 'lucide-react';
import { BADGE_MAX_LEVEL, COACH_BADGES, money, securityTone, type Coach } from './types';

const RATINGS: { key: keyof Coach; label: string }[] = [
  { key: 'ovr_offensivo', label: 'Offense' },
  { key: 'ovr_difensivo', label: 'Defense' },
  { key: 'player_development', label: 'Player development' },
  { key: 'tactical_acumen', label: 'Adjustments' },
  { key: 'discipline_culture', label: 'Locker room' },
];

const ordinal = (n: number) => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};

interface CoachStatusProps {
  coach: Coach | null;
  teamName: string;
  spending: string | null;
  onExtend: () => void;
  onFire: () => void;
  onSpendBadge: (badge: string) => void;
  onBrowseMarket: () => void;
}

export const CoachStatus: React.FC<CoachStatusProps> = ({ coach, teamName, spending, onExtend, onFire, onSpendBadge, onBrowseMarket }) => {
  if (!coach) {
    return (
      <aside className="of-col of-status" aria-label="Head coach">
        <div className="of-card">
          <h2 className="of-card-head">No head coach</h2>
          <p className="of-text">The {teamName} bench is empty. Until you hire someone the team plays without a coach's ratings and badges.</p>
          <button type="button" className="of-btn of-btn-primary of-btn-block" onClick={onBrowseMarket}>Browse the coach market</button>
        </div>
      </aside>
    );
  }

  const tone = securityTone(coach.job_security);
  const seasons = coach.years_with_current_team || 1;
  const yearsLeft = coach.contratto_anni_rimanenti;
  const winPct = coach.career_win_pct ?? 0.5;
  const points = coach.badge_points || 0;

  return (
    <aside className="of-col of-status" aria-label="Head coach">
      <div className="of-card">
        <div className="cc-head">
          <div className="cc-head-name">
            <b>{coach.nome}</b>
            <span>Age {coach.eta} · {ordinal(seasons)} season with the {teamName}</span>
          </div>
          <div className="cc-ovr"><span>{coach.ovr_totale}</span><small>OVR</small></div>
        </div>
        <div className="of-chips">
          {coach.specialization && <span className="of-pill is-hot">{coach.specialization}</span>}
          <span className="of-pill is-info">{coach.stile_gioco}</span>
        </div>

        <div className="cc-ratings">
          {RATINGS.map((r) => {
            const v = Number(coach[r.key] ?? 75);
            return (
              <div key={r.key} className="cc-rating">
                <span>{r.label}</span>
                <b>{v}</b>
                <div className="of-meter is-thin is-hot" role="meter" aria-label={r.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={v}>
                  <i style={{ width: `${Math.min(100, Math.max(0, v))}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="of-card">
        <dl className="of-kv">
          <dt>Contract</dt>
          <dd>{money(coach.salario)} · <span className={yearsLeft <= 1 ? 'of-tone-warn' : undefined}>{yearsLeft} {yearsLeft === 1 ? 'year' : 'years'} left</span></dd>
          <dt>Owner security</dt>
          <dd><span className={`of-pill is-${tone}`}>{coach.job_security_label || 'Secure'} · {Math.round(coach.job_security)}%</span></dd>
          <dt>Career</dt>
          <dd>{coach.historical_wins}-{coach.historical_losses} · {winPct.toFixed(3).replace(/^0/, '')}</dd>
          <dt>Playoffs · titles</dt>
          <dd>{coach.playoff_appearances || 0} · {coach.championships}{coach.coty_awards ? ` · ${coach.coty_awards} COY` : ''}</dd>
        </dl>
        <div className="cc-actions">
          <button type="button" className="of-btn of-btn-primary" onClick={onExtend}>Extend</button>
          <button type="button" className="of-btn of-btn-danger" onClick={onFire}>Fire</button>
        </div>
      </div>

      <div className="of-card">
        <h3 className="of-sub-head cc-badge-head">
          Badges
          <span className={points > 0 ? 'of-pill is-ok' : 'cc-muted'}>
            {points > 0 ? `${points} ${points === 1 ? 'point' : 'points'} to spend` : `Level ${coach.level || 1}`}
          </span>
        </h3>
        <ul className="cc-badges">
          {COACH_BADGES.map((b) => {
            const level = coach.badges?.[b.key] ?? 0;
            const canSpend = points > 0 && level < BADGE_MAX_LEVEL;
            return (
              <li key={b.key} className={level > 0 ? 'is-on' : undefined}>
                <div className="cc-badge-top">
                  <b>{b.label}</b>
                  <span className="cc-pips" aria-label={`Level ${level} of ${BADGE_MAX_LEVEL}`}>
                    {Array.from({ length: BADGE_MAX_LEVEL }, (_, i) => <i key={i} className={i < level ? 'is-on' : undefined} />)}
                  </span>
                  {canSpend && (
                    <button type="button" className="cc-spend" onClick={() => onSpendBadge(b.key)} disabled={spending !== null}
                      aria-label={`Spend a point on ${b.label}`} title="Spend a point">
                      <Plus size={14} aria-hidden="true" />
                    </button>
                  )}
                </div>
                <span className="cc-badge-effect">{b.effect}</span>
              </li>
            );
          })}
        </ul>
        <p className="of-note">Your coach earns a point at each level-up (wins give experience).</p>
      </div>
    </aside>
  );
};
