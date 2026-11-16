// Six cream mini-leaderboards above the Players / Teams tables; pressing a name opens its card.
import React from 'react';

export interface LeaderTile {
  label: string;
  items: { name: string; short: string; value: string }[];
}

export const LeadersStrip: React.FC<{ tiles: LeaderTile[]; onPick: (name: string) => void }> = ({ tiles, onPick }) => (
  <div className="an-tiles">
    {tiles.map((t) => (
      <div key={t.label} className="an-tile">
        <div className="an-kicker">{t.label}</div>
        {t.items.length === 0 ? <div className="an-tile-row an-muted">—</div> : t.items.map((it, i) => (
          <button key={it.name} type="button" className="an-tile-row" onClick={() => onPick(it.name)} title={it.name}>
            <span><span className="an-tile-rank">{i + 1}</span>{it.short}</span>
            <b>{it.value}</b>
          </button>
        ))}
      </div>
    ))}
  </div>
);
