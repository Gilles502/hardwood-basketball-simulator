// The user's roster as a sheet beside the market: players by position, new signings tagged, an open slot where a
// position is short, and the money to spend. No "need" labels: the sheet shows the gaps. A free agent under the
// pointer shows where he would go.
import React from 'react';
import { normalizeRole } from '../../../utils/roles';
import { money, POSITIONS, type FaPlayer, type FaUserTeam } from './freeAgency';

interface RosterSheetProps {
  team: FaUserTeam;
  /** The free agent under the pointer or open in the market. */
  focus: FaPlayer | null;
  openOffers: number;
  openOffersTotal: number;
}

const MIN_PER_POSITION = 2;

export const RosterSheet: React.FC<RosterSheetProps> = ({ team, focus, openOffers, openOffersTotal }) => {
  const focusRole = focus ? normalizeRole(focus.ruolo) : null;
  return (
    <aside className="eos-sheet fa-roster">
      <span className="eos-kicker">Your roster · {team.roster_count}/{team.roster_limit}</span>
      {POSITIONS.map((pos) => {
        const players = team.roster.filter((p) => normalizeRole(p.role) === pos).sort((a, b) => b.ovr - a.ovr);
        const best = players[0]?.ovr ?? 0;
        const showFocus = focus && focusRole === pos;
        return (
          <div key={pos} className="fa-roster-pos">
            <b className="fa-roster-label">{pos}</b>
            {players.map((p) => (
              <div key={p.name} className="fa-slot">
                <span>{p.name}{p.new && <em className="fa-new">new</em>}</span>
                <b>{p.ovr}</b>
              </div>
            ))}
            {showFocus && (
              <div className="fa-slot is-focus">
                <span>→ {focus.nome} {focus.ovr > best ? 'would start' : 'off the bench'}</span>
                <b>{focus.ovr}</b>
              </div>
            )}
            {!showFocus && players.length < MIN_PER_POSITION && <div className="fa-slot is-open"><span>open spot</span></div>}
          </div>
        );
      })}
      <div className="fa-money">
        <div><span>Payroll</span><b>{money(team.payroll)}</b></div>
        <div><span>Cap space</span><b>{money(team.cap_space)}</b></div>
        <div>
          <span>{team.mle_type === 'TAXPAYER_MLE' ? 'Taxpayer MLE' : 'MLE'}</span>
          <b>{team.mle_available ? money(team.mle_amount) : 'used / none'}</b>
        </div>
        <div><span>BAE</span><b>{team.bae_available ? money(team.bae_amount) : 'used / none'}</b></div>
        <div><span>Minimum deal</span><b>{money(team.min_salary)}</b></div>
        <div>
          <span>Your offers</span>
          <b>{openOffers === 0 ? 'none' : `${openOffers} · ${money(openOffersTotal)} if all land`}</b>
        </div>
      </div>
    </aside>
  );
};
