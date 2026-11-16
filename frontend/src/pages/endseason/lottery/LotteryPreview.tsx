// Lottery night, before the draw: who is in the lottery, who owns each pick and the odds, then "Hold the lottery".
import React from 'react';
import { TeamCrest } from '../../../components/TeamCrest';
import { pickLabel, protectionLabel, type PreviewTeam } from './lottery';

interface LotteryPreviewProps {
  teams: PreviewTeam[] | null;
  /** How many picks the draw decides (from the server). */
  drawnPicks: number;
  userTeam: string;
  readOnly: boolean;
  busy: boolean;
  error: string | null;
  onHold: () => void;
}

export const LotteryPreview: React.FC<LotteryPreviewProps> = ({ teams, drawnPicks, userTeam, readOnly, busy, error, onHold }) => (
  <div className="eos-sheet lot-preview">
    <div className="lot-preview-head">
      <div>
        <span className="eos-kicker">Lottery night</span>
        <h2 className="lot-title">Before the draw</h2>
        <p className="lot-sub">
          Coaches change jobs around the league, then the lottery draws the top {Math.min(drawnPicks, teams?.length ?? drawnPicks)} picks. The
          rest follow the standings.
        </p>
      </div>
      {!readOnly && (
        <button type="button" className="btn btn-primary eos-cta" onClick={onHold} disabled={busy}>
          {busy ? 'Drawing…' : 'Hold the lottery'}
        </button>
      )}
    </div>
    {error && <p className="eos-error">{error}</p>}
    {teams ? (
      <table className="lot-table">
        <thead>
          <tr>
            <th>Seed</th>
            <th>Pick owner</th>
            <th>Record</th>
            <th className="num">#1 pick</th>
            <th className="num">Top {drawnPicks}</th>
          </tr>
        </thead>
        <tbody>
          {teams.map((t) => (
            <tr key={t.team} className={t.owner === userTeam ? 'is-yours' : undefined}>
              <td className="lot-seed">{t.seed}</td>
              <td>
                <span className="lot-owner">
                  <TeamCrest name={t.owner} size={24} />
                  <b>{t.owner}</b>
                  {pickLabel(t.owner, t.team) && <small>{pickLabel(t.owner, t.team)}</small>}
                  {protectionLabel(t.protection) && <span className="lot-prot">{protectionLabel(t.protection)}</span>}
                </span>
              </td>
              <td>{t.record}</td>
              <td className="num">{t.odds_first.toFixed(1)}%</td>
              <td className="num">{t.odds_top.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    ) : (
      <p className="eos-muted">Loading the lottery teams…</p>
    )}
  </div>
);
