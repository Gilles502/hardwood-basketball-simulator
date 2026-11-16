// The five events down the left, grouped by night: ✓ when revealed, the next one current, the rest locked.
import React from 'react';
import type { EventId, WeekendEvent } from './types';

export type RailState = 'done' | 'current' | 'locked';

interface Props {
  events: WeekendEvent[];
  states: Record<EventId, RailState>;
  selected: EventId | null;
  onSelect: (id: EventId) => void;
}

export const EventRail: React.FC<Props> = ({ events, states, selected, onSelect }) => {
  const nights = events.reduce<{ night: string; events: WeekendEvent[] }[]>((acc, e) => {
    const last = acc[acc.length - 1];
    if (last && last.night === e.night) last.events.push(e);
    else acc.push({ night: e.night, events: [e] });
    return acc;
  }, []);

  return (
    <nav className="as-rail" aria-label="All-Star Weekend events">
      {nights.map((n) => (
        <div key={n.night} className="as-night">
          <div className="as-night-label">{n.night}</div>
          <ul>
            {n.events.map((e) => {
              const state = states[e.id];
              const small = state === 'done' ? (e.summary ?? 'Not recorded') : state === 'current' ? 'Up next' : 'Locked';
              return (
                <li key={e.id}>
                  <button
                    type="button"
                    className={`as-ev is-${state}${selected === e.id ? ' is-selected' : ''}`}
                    disabled={state === 'locked'}
                    aria-current={selected === e.id ? 'step' : undefined}
                    onClick={() => onSelect(e.id)}
                  >
                    <span className="as-dot" aria-hidden="true">{state === 'done' ? '✓' : ''}</span>
                    <span className="as-ev-text">
                      {e.title}
                      <small>{small}</small>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
};
