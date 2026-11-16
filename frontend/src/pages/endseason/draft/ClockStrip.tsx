// The draft room's top strip: the last picks made, the pick on the clock, the next ones, the controls, and the full
// order as an expanding section (no popup).
import React from 'react';
import { TeamCrest } from '../../../components/TeamCrest';
import { crestLabel } from '../../../utils/crest';
import { normalizeRole } from '../../../utils/roles';
import type { DraftState, OrderPick } from './draftRoom';

interface ClockStripProps {
  state: DraftState;
  userTeam: string;
  auto: boolean;
  busy: boolean;
  showOrder: boolean;
  onToggleAuto: () => void;
  onStep: () => void;
  onSimToUser: () => void;
  onToggleOrder: () => void;
}

const via = (p: OrderPick) => (p.current_owner === p.original_owner ? '' : `via ${crestLabel(p.original_owner)}`);

export const ClockStrip: React.FC<ClockStripProps> = ({
  state, userTeam, auto, busy, showOrder, onToggleAuto, onStep, onSimToUser, onToggleOrder,
}) => {
  const order = state.ordine ?? [];
  const history = state.history ?? [];
  const current = state.pick_corrente ?? 0;
  const clock = state.on_the_clock ?? null;
  const yourTurn = !!state.is_user_turn;
  const recent = order.filter((p) => p.pick_index < current).slice(-2);
  const upcoming = order.filter((p) => p.pick_index > current).slice(0, 3);
  const yourNext = order.find((p) => p.pick_index > current && p.current_owner === userTeam);
  const locked = busy || yourTurn || state.status !== 'DRAFT_IN_PROGRESS';

  return (
    <div className="dr-strip-wrap">
      <div className="dr-strip">
        {recent.map((p) => (
          <div key={p.pick_index} className="dr-slot is-done">
            <b>#{p.pick_index + 1}</b> {crestLabel(p.current_owner)}
            <span>{history[p.pick_index]?.nome ?? '—'}</span>
          </div>
        ))}
        {clock && (
          <div className={`dr-clock${yourTurn ? ' is-yours' : ''}`}>
            <TeamCrest name={clock.current_owner} size={34} />
            <div>
              <div className="dr-clock-title">
                #{clock.pick_index + 1} · {yourTurn ? "You're on the clock" : `${clock.current_owner} on the clock`}
              </div>
              <div className="dr-clock-sub">
                {[`Round ${clock.round}`, via(clock), yourNext ? `Your next pick: #${yourNext.pick_index + 1}` : 'No more picks for you']
                  .filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>
        )}
        {upcoming.map((p) => (
          <div key={p.pick_index} className={`dr-slot${p.current_owner === userTeam ? ' is-yours' : ''}`}>
            <b>#{p.pick_index + 1}</b> {crestLabel(p.current_owner)}
            <span>{via(p) || ' '}</span>
          </div>
        ))}
        <div className="dr-controls">
          <button type="button" className="btn btn-secondary" onClick={onStep} disabled={locked || auto}>Next pick</button>
          <button type="button" className={`btn btn-secondary${auto ? ' is-on' : ''}`} onClick={onToggleAuto} disabled={locked && !auto}>
            {auto ? 'Pause' : 'Auto ▸'}
          </button>
          <button type="button" className="btn btn-primary" onClick={onSimToUser} disabled={locked || auto || !yourNext}>
            Sim to my pick
          </button>
          <button type="button" className="btn btn-secondary" onClick={onToggleOrder} aria-expanded={showOrder}>
            {showOrder ? 'Hide order' : 'Full order'}
          </button>
        </div>
      </div>
      {showOrder && (
        <ol className="dr-order">
          {order.map((p) => {
            const made = history[p.pick_index];
            return (
              <li key={p.pick_index} className={`${p.pick_index === current ? 'is-now' : ''}${p.current_owner === userTeam ? ' is-yours' : ''}`}>
                <i>{p.pick_index + 1}</i>
                <b>{crestLabel(p.current_owner)}</b>
                {via(p) && <small>{via(p)}</small>}
                <span>{made ? `${made.nome}${made.ruolo ? ` · ${normalizeRole(made.ruolo)}` : ''}` : p.pick_index === current ? 'on the clock' : ''}</span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
};
