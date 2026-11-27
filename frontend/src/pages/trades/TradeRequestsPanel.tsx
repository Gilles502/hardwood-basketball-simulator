import React from 'react';
import { TeamCrest } from '../../components/TeamCrest';
import { normalizeRole } from '../../utils/roles';
import type { TradeRequestRow } from './types';

interface TradeRequestsPanelProps {
  rows: TradeRequestRow[];
  loading: boolean;
  onTradeFor: (team: string, player: string) => void;
}

const money = (millions: number): string => `$${millions.toFixed(1)}M`;

/** Every player in the league who asked to be traded (GET /api/trade-requests), best first. */
export const TradeRequestsPanel: React.FC<TradeRequestsPanelProps> = ({ rows, loading, onTradeFor }) => {
  if (loading) {
    return <div className="tb-empty"><div className="spinner" /></div>;
  }
  if (rows.length === 0) {
    return <div className="tm-empty">No player has asked for a trade.</div>;
  }
  return (
    <div className="tm-panel">
      <div className="tm-panel-head">
        <span className="tm-team-name">Asked for a trade</span>
        <span className="tm-panel-count">Fed up with their team: no longer untouchable, their teams are listening</span>
      </div>
      <div className="trq-scroll">
        <table className="trq-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Team</th>
              <th className="is-num">OVR</th>
              <th className="is-num">Age</th>
              <th>Contract</th>
              <th>Since</th>
              <th aria-label="Action" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.team}-${r.player}`} className={r.is_user_team ? 'is-mine' : undefined}>
                <td><span className="tm-pos">{normalizeRole(r.role)}</span> <b>{r.player}</b></td>
                <td><span className="trq-team"><TeamCrest name={r.team} size={20} />{r.team}</span></td>
                <td className="is-num"><span className="tm-ovr">{r.ovr}</span></td>
                <td className="is-num">{r.age}</td>
                <td>{money(r.salary)} x{r.years}</td>
                <td>{r.since || '-'}</td>
                <td className="is-action">
                  {r.is_user_team ? (
                    <span className="trq-mine" title="Offers for him arrive on your Trade Block">Your player</span>
                  ) : (
                    <button type="button" className="tm-btn is-primary trq-btn" onClick={() => onTradeFor(r.team, r.player)}>
                      Trade for
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
