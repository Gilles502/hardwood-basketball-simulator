import React, { useRef } from 'react';

export interface DashboardTabDef {
  id: string;
  label: string;
  hint?: string;
}

interface DashboardTabsProps {
  tabs: DashboardTabDef[];
  active: string;
  onChange: (id: string) => void;
  idPrefix?: string;
  ariaLabel?: string;
}

/** Tab strip following the ARIA tabs pattern: roving tabindex, arrows/Home/End move and select. */
export const DashboardTabs: React.FC<DashboardTabsProps> = ({ tabs, active, onChange, idPrefix = 'dash', ariaLabel = 'Dashboard sections' }) => {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const move = (index: number) => {
    const target = tabs[(index + tabs.length) % tabs.length];
    onChange(target.id);
    refs.current[target.id]?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    if (event.key === 'ArrowRight') { event.preventDefault(); move(index + 1); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); move(index - 1); }
    else if (event.key === 'Home') { event.preventDefault(); move(0); }
    else if (event.key === 'End') { event.preventDefault(); move(tabs.length - 1); }
  };

  return (
    <div className="dash-tabs" role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          ref={(node) => { refs.current[tab.id] = node; }}
          id={`${idPrefix}-tab-${tab.id}`}
          role="tab"
          aria-selected={tab.id === active}
          aria-controls={`${idPrefix}-panel-${tab.id}`}
          tabIndex={tab.id === active ? 0 : -1}
          className={`dash-tab${tab.id === active ? ' is-active' : ''}`}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => onKeyDown(event, index)}
        >
          {tab.label}
          {tab.hint && <small>{tab.hint}</small>}
        </button>
      ))}
    </div>
  );
};
