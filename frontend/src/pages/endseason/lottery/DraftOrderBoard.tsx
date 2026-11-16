// The whole draft order after the lottery: every round, every pick with its current owner ("via" the team it came
// from) and the lottery moves on the first round.
import React from 'react';
import { TeamCrest } from '../../../components/TeamCrest';
import { pickLabel, type FullOrderPick } from './lottery';

interface DraftOrderBoardProps {
  order: FullOrderPick[];
  userTeam: string;
}

export const DraftOrderBoard: React.FC<DraftOrderBoardProps> = ({ order, userTeam }) => {
  const rounds = [...new Set(order.map((p) => p.round))];
  const yours = order.filter((p) => p.owner === userTeam);
  return (
    <div className="eos-sheet lot-order">
      <div className="lot-order-head">
        <div>
          <span className="eos-kicker">The draft order</span>
          <h2 className="lot-title">{order.length} picks · {rounds.length} rounds</h2>
        </div>
        <p className="lot-sub">
          {yours.length === 0
            ? 'You hold no pick in this draft.'
            : `Your picks: ${yours.map((p) => `#${p.overall}`).join(', ')}.`}
        </p>
      </div>
      <div className="lot-rounds">
        {rounds.map((round) => (
          <section key={round}>
            <h3 className="eos-h3">Round {round}</h3>
            <ol className="lot-order-list">
              {order.filter((p) => p.round === round).map((p) => {
                const via = pickLabel(p.owner, p.team);
                return (
                  <li key={p.overall} className={p.owner === userTeam ? 'is-yours' : undefined}>
                    <i>{p.overall}</i>
                    <TeamCrest name={p.owner} size={22} />
                    <b>{p.owner}</b>
                    {via && <small>{via}</small>}
                    <span className="lot-rec">{p.record}</span>
                    {p.delta !== 0 && (
                      <span className={p.delta > 0 ? 'eos-up' : 'eos-down'}>{p.delta > 0 ? '▲' : '▼'} {Math.abs(p.delta)}</span>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
};
