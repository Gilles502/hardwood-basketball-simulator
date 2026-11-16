import React, { useMemo, useState } from 'react';
import { normalizeRole } from '../../utils/roles';
import type { TeamAssets } from './types';

export interface RouteOption {
  code: string;
  label: string;
  title: string;
}

interface TradeRosterTableProps {
  assets: TeamAssets;
  /** Colors the selected rows: you, the partner or the third team. */
  accent: 'you' | 'partner' | 'third';
  /** Narrow variant for side panels: drops POT, age and years. */
  compact?: boolean;
  /** Selection mode: click a row to add or remove it from the deal. */
  selectedPlayers?: string[];
  selectedPicks?: string[];
  onTogglePlayer?: (name: string) => void;
  onTogglePick?: (key: string) => void;
  /** Routing mode (3-team): each row has one button per destination instead of being clickable. */
  routing?: {
    options: RouteOption[];
    value: Record<string, string | undefined>;
    onRoute: (key: string, code: string) => void;
  };
}

type SortKey = 'position' | 'name' | 'ovr' | 'potential' | 'age' | 'salary' | 'contract_years';

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: 'position', label: 'Pos', numeric: false },
  { key: 'name', label: 'Player', numeric: false },
  { key: 'ovr', label: 'OVR', numeric: true },
  { key: 'potential', label: 'POT', numeric: true },
  { key: 'age', label: 'Age', numeric: true },
  { key: 'salary', label: 'Salary', numeric: true },
  { key: 'contract_years', label: 'Yrs', numeric: true },
];

export const TradeRosterTable: React.FC<TradeRosterTableProps> = ({
  assets, accent, compact = false, selectedPlayers = [], selectedPicks = [], onTogglePlayer, onTogglePick, routing,
}) => {
  const [view, setView] = useState<'players' | 'picks'>('players');
  const [sortKey, setSortKey] = useState<SortKey>('ovr');
  const [sortDesc, setSortDesc] = useState(true);
  const columns = compact ? COLUMNS.filter((c) => ['position', 'name', 'ovr', 'salary'].includes(c.key)) : COLUMNS;

  const sorted = useMemo(() => {
    const rows = [...assets.players];
    rows.sort((a, b) => {
      const av = sortKey === 'position' ? normalizeRole(a.position) : a[sortKey];
      const bv = sortKey === 'position' ? normalizeRole(b.position) : b[sortKey];
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortDesc ? -cmp : cmp;
    });
    return rows;
  }, [assets.players, sortKey, sortDesc]);

  const changeSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(COLUMNS.find((c) => c.key === key)?.numeric ?? false);
    }
  };

  const isOn = (key: string, picks: boolean): boolean =>
    routing ? !!routing.value[key] : (picks ? selectedPicks : selectedPlayers).includes(key);

  const countPlayers = routing ? assets.players.filter((p) => routing.value[p.name]).length : selectedPlayers.length;
  const countPicks = routing ? assets.picks.filter((p) => routing.value[p.key]).length : selectedPicks.length;

  const routeButtons = (key: string) => routing && (
    <td className="tm-route-cell">
      {routing.options.map((opt) => (
        <button
          key={opt.code}
          type="button"
          className={`tm-route${routing.value[key] === opt.code ? ' is-on' : ''}`}
          title={`Send to ${opt.title}`}
          aria-pressed={routing.value[key] === opt.code}
          onClick={() => routing.onRoute(key, opt.code)}
        >
          {opt.label}
        </button>
      ))}
    </td>
  );

  const rowProps = (key: string, picks: boolean, toggle?: () => void) => ({
    className: `tm-row${isOn(key, picks) ? ' is-on' : ''}${routing ? '' : ' is-clickable'}`,
    ...(routing ? {} : {
      tabIndex: 0,
      role: 'checkbox' as const,
      'aria-checked': isOn(key, picks),
      onClick: toggle,
      onKeyDown: (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle?.(); }
      },
    }),
  });

  return (
    <div className={`tm-roster tm-accent-${accent}${compact ? ' is-compact' : ''}`}>
      <div className="tm-ptabs" role="tablist">
        <button type="button" role="tab" aria-selected={view === 'players'} className={view === 'players' ? 'is-active' : ''} onClick={() => setView('players')}>
          Players{countPlayers > 0 && <b>{countPlayers}</b>}
        </button>
        <button type="button" role="tab" aria-selected={view === 'picks'} className={view === 'picks' ? 'is-active' : ''} onClick={() => setView('picks')}>
          Picks ({assets.picks.length}){countPicks > 0 && <b>{countPicks}</b>}
        </button>
      </div>

      <div className="tm-scroll">
        {view === 'players' ? (
          <table className="tm-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className={col.numeric ? 'n' : ''}
                    aria-sort={sortKey === col.key ? (sortDesc ? 'descending' : 'ascending') : 'none'}
                  >
                    <button type="button" onClick={() => changeSort(col.key)}>
                      {col.label}{sortKey === col.key ? (sortDesc ? ' ▾' : ' ▴') : ''}
                    </button>
                  </th>
                ))}
                {routing && <th className="n">Send to</th>}
              </tr>
            </thead>
            <tbody>
              {sorted.map((p) => (
                <tr key={p.name} {...rowProps(p.name, false, () => onTogglePlayer?.(p.name))}>
                  <td><span className="tm-pos">{normalizeRole(p.position)}</span></td>
                  <td className="tm-name">{p.name}{p.on_trade_block && <span className="tm-block-tag">Block</span>}</td>
                  <td className="n tm-ovr">{p.ovr}</td>
                  {!compact && <td className="n">{p.potential}</td>}
                  {!compact && <td className="n">{p.age}</td>}
                  <td className="n">${p.salary.toFixed(1)}M</td>
                  {!compact && <td className="n">{p.contract_years}</td>}
                  {routeButtons(p.name)}
                </tr>
              ))}
              {sorted.length === 0 && <tr><td colSpan={routing ? columns.length + 1 : columns.length} className="tm-none">No players.</td></tr>}
            </tbody>
          </table>
        ) : (
          <table className="tm-table">
            <thead>
              <tr><th>Pick</th><th>Protection</th>{routing && <th className="n">Send to</th>}</tr>
            </thead>
            <tbody>
              {assets.picks.map((pick) => (
                <tr key={pick.key} {...rowProps(pick.key, true, () => onTogglePick?.(pick.key))}>
                  <td className="tm-name">{pick.display_name}</td>
                  <td>{pick.protection || 'Unprotected'}</td>
                  {routeButtons(pick.key)}
                </tr>
              ))}
              {assets.picks.length === 0 && <tr><td colSpan={routing ? 3 : 2} className="tm-none">No tradable picks.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
