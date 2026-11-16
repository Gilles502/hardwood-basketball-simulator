// The draft wire: every pick made and every CPU trade, newest first, in plain league voice (no fake tweets).
import React, { useState } from 'react';
import { tradeLine, wireLine, type DraftState } from './draftRoom';

interface DraftWireProps {
  state: DraftState;
  perRound: number;
  userTeam: string;
}

const SHORT = 10;

type WireItem = { key: string; at: number; trade: boolean; text: string; yours: boolean };

export const DraftWire: React.FC<DraftWireProps> = ({ state, perRound, userTeam }) => {
  const [all, setAll] = useState(false);
  const picks: WireItem[] = (state.history ?? []).map((h, i) => ({
    key: `p${i}`, at: i, trade: false, text: wireLine(h, perRound), yours: h.squadra === userTeam,
  }));
  // A trade happens before the pick it moved, so it sorts just ahead of that pick.
  const trades: WireItem[] = (state.trades ?? []).map((t, i) => ({
    key: `t${i}`, at: (t.pick_index ?? 0) - 0.5, trade: true, text: tradeLine(t), yours: false,
  }));
  const items = [...picks, ...trades].sort((a, b) => b.at - a.at);
  const shown = all ? items : items.slice(0, SHORT);

  return (
    <div className="dr-wire">
      <span className="dr-wire-title">Draft wire</span>
      {items.length === 0 ? (
        <p className="dr-wire-empty">The first pick is on the clock.</p>
      ) : (
        <ul>
          {shown.map((item) => (
            <li key={item.key} className={`${item.trade ? 'is-trade' : ''}${item.yours ? ' is-yours' : ''}`}>
              {item.trade && <b className="dr-wire-tag">Trade</b>}
              {item.text}
            </li>
          ))}
        </ul>
      )}
      {items.length > SHORT && (
        <button type="button" className="dr-wire-more" onClick={() => setAll(!all)}>
          {all ? 'Show the latest only' : `Show all ${items.length}`}
        </button>
      )}
    </div>
  );
};
