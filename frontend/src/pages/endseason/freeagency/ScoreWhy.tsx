// Why a player scores the user's offer as he does: the parts of the market's own score, or the low-ball refusal.
import React from 'react';
import { normalizeRole } from '../../../utils/roles';
import { partLabel, signed, type ScoreDetail } from './freeAgency';

interface ScoreWhyProps {
  detail: ScoreDetail;
  offer: number;
  role: string;
  teamGoal: string;
  day: number;
  /** "Why your offer scores 62" / "At his asking price he would score 58". */
  title: string;
  /** The user's offer leads and the user is his previous team: the market adds his loyalty on top (its own line). */
  oldTeamBonus?: number;
  /** The user's team, for the walk-away sentence. */
  userTeam?: string;
}

export const ScoreWhy: React.FC<ScoreWhyProps> = ({ detail, offer, role, teamGoal, day, title, oldTeamBonus = 0, userTeam }) => {
  if (detail.rejected) {
    return (
      <div className="fa-why">
        <span className="eos-kicker">{title}</span>
        <p className="fa-why-reject">
          {detail.rejected.walks
            ? `He will not go back to the ${userTeam ?? 'old team'}: ${detail.rejected.walks}.`
            : `He won't consider less than ${detail.rejected.below_pct}% of his value ($${detail.value.toFixed(1)}M).`}
        </p>
      </div>
    );
  }
  const ctx = { offer, worth: detail.value, role: normalizeRole(role), teamGoal, day };
  return (
    <div className="fa-why">
      <span className="eos-kicker">{title}</span>
      <dl>
        {detail.parts.filter((p) => p.key !== 'base' && (p.value !== 0 || p.key === 'money' || p.key === 'role')).map((p) => (
          <div key={p.key}>
            <dt>{partLabel(p.key, p.value, ctx)}</dt>
            <dd className={p.value > 0 ? 'eos-up' : p.value < 0 ? 'eos-down' : undefined}>{signed(p.value)}</dd>
          </div>
        ))}
        {oldTeamBonus > 0 && (
          <div><dt>Loyalty to his old team, and your offer leads</dt><dd className="eos-up">{signed(oldTeamBonus)}</dd></div>
        )}
      </dl>
      <p className="fa-why-foot">
        Everyone starts at 50{detail.raw > 100 ? ` · ${Math.round(detail.raw)} is capped at 100` : detail.raw < 0 ? ' · capped at 0' : ''}.
      </p>
    </div>
  );
};
