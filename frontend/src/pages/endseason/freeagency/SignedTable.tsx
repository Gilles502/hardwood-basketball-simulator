// Where the free agents went: who signed with whom, the contract, the day, and the offers he turned down.
import React from 'react';
import { normalizeRole } from '../../../utils/roles';
import { contractLine, money, type Signing } from './freeAgency';

interface SignedTableProps {
  signings: Signing[];
  userTeam: string;
  position: string;
  search: string;
}

export const SignedTable: React.FC<SignedTableProps> = ({ signings, userTeam, position, search }) => {
  const q = search.trim().toLowerCase();
  const rows = [...signings]
    .filter((s) => position === 'ALL' || normalizeRole(s.role) === position)
    .filter((s) => !q || s.player.toLowerCase().includes(q))
    .sort((a, b) => b.day - a.day || b.ovr - a.ovr);
  return (
    <table className="fa-table">
      <thead>
        <tr><th>Player</th><th>OVR</th><th>Signed with</th><th>Contract</th><th>Day</th><th>Turned down</th></tr>
      </thead>
      <tbody>
        {rows.length === 0 && <tr><td colSpan={6} className="fa-empty">Nobody has signed yet.</td></tr>}
        {rows.map((s) => (
          <tr key={`${s.player}-${s.day}`} className={s.team === userTeam ? 'is-yours' : undefined}>
            <td><span className="fa-pos">{normalizeRole(s.role)}</span><b>{s.player}</b></td>
            <td className="fa-num">{s.ovr}</td>
            <td><b>{s.team === userTeam ? `${s.team} (you)` : s.team}</b></td>
            <td className="fa-num">{contractLine(s.salary, s.years, s.option_type)}</td>
            <td className="fa-num">{s.day}</td>
            <td className="fa-muted">
              {s.beat.length === 0 ? '—' : s.beat.map((b) => `${b.team === userTeam ? 'you' : b.team} ${money(b.salary)}`).join(' · ')}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
