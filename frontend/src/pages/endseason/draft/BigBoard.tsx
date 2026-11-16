// The big board: every prospect still available as the user's scouts see them. A row opens its scouting detail right
// under it; on the user's turn "Draft" asks once more on the same row ("Confirm") before the pick is made.
import React, { useEffect, useState } from 'react';
import { normalizeRole } from '../../../utils/roles';
import type { Prospect } from './draftRoom';

interface BigBoardProps {
  prospects: Prospect[];
  canDraft: boolean;
  busy: boolean;
  onDraft: (name: string) => void;
}

const FILTERS = ['ALL', 'PG', 'SG', 'SF', 'PF', 'C'] as const;

export const BigBoard: React.FC<BigBoardProps> = ({ prospects, canDraft, busy, onDraft }) => {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('ALL');
  const [open, setOpen] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  // A prospect who has just been drafted leaves the board, and so does an open detail or a pending confirm.
  useEffect(() => {
    const names = new Set(prospects.map((p) => p.name));
    if (open && !names.has(open)) setOpen(null);
    if (confirming && !names.has(confirming)) setConfirming(null);
  }, [prospects, open, confirming]);
  useEffect(() => { if (!canDraft) setConfirming(null); }, [canDraft]);

  const shown = filter === 'ALL' ? prospects : prospects.filter((p) => normalizeRole(p.role) === filter);

  return (
    <div className="eos-sheet dr-board">
      <div className="dr-board-head">
        <span className="eos-kicker">Big board · {prospects.length} available</span>
        <div className="dr-filters" role="group" aria-label="Position">
          {FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {f === 'ALL' ? 'All' : f}
            </button>
          ))}
        </div>
      </div>
      <table className="dr-table">
        <thead>
          <tr>
            <th>Mock</th>
            <th>Prospect</th>
            <th>Age</th>
            <th>From</th>
            <th>OVR</th>
            <th>POT</th>
            <th>Scouted</th>
            <th aria-label="Draft" />
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 && (
            <tr><td colSpan={8} className="dr-empty">No prospect left at this position.</td></tr>
          )}
          {shown.map((p) => {
            const isOpen = open === p.name;
            const progress = Math.round(p.scouting_progress);
            return (
              <React.Fragment key={p.name}>
                <tr className={`dr-row${isOpen ? ' is-open' : ''}`} onClick={() => setOpen(isOpen ? null : p.name)}>
                  <td className="dr-mock">{p.pos}</td>
                  <td>
                    <span className="dr-pos">{normalizeRole(p.role)}</span>
                    <b className="dr-name">{p.name}</b>
                  </td>
                  <td>{p.age}</td>
                  <td className="dr-from">{p.provenance}</td>
                  <td className="dr-val">{p.ovr_display}</td>
                  <td className="dr-val">{p.pot_display}</td>
                  <td>
                    <progress className="dr-bar" max={100} value={progress} aria-hidden="true" />
                    <span className="dr-pct">{progress}%</span>
                  </td>
                  <td className="dr-act">
                    {canDraft && (
                      <button
                        type="button"
                        className={`btn btn-primary dr-draft${confirming === p.name ? ' is-confirm' : ''}`}
                        disabled={busy}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirming === p.name) onDraft(p.name);
                          else setConfirming(p.name);
                        }}
                      >
                        {confirming === p.name ? 'Confirm' : 'Draft'}
                      </button>
                    )}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="dr-detail">
                    <td colSpan={8}>
                      <div className="dr-detail-line">
                        <span><b>Archetype:</b> {p.archetype}</span>
                        <span><b>Projection:</b> {p.projection}</span>
                        {p.assigned_scout && <span><b>Scout:</b> {p.assigned_scout}</span>}
                      </div>
                      <dl className="dr-attrs">
                        {Object.entries(p.attributes).map(([label, value]) => (
                          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
                        ))}
                      </dl>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
