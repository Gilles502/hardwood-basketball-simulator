// League percentile bars for the player / team cards (orange = top, slate = bottom).
import React from 'react';

export const PercentileBars: React.FC<{ items: { label: string; pct: number | null }[] }> = ({ items }) => (
  <div className="an-bars">
    {items.map((it) => {
      const p = it.pct;
      const cls = p === null ? '' : p >= 90 ? ' is-top' : p <= 20 ? ' is-bottom' : '';
      return (
        <div key={it.label} className="an-bar">
          <span className="an-bar-label">{it.label}</span>
          <span className="an-bar-track" role="img" aria-label={`${it.label}: ${p === null ? 'no percentile' : `${Math.round(p)}th percentile`}`}>
            <span className={`an-bar-fill${cls}`} style={{ width: `${p ?? 0}%` }} />
          </span>
          <span className="an-bar-num">{p === null ? '—' : Math.round(p)}</span>
        </div>
      );
    })}
  </div>
);
