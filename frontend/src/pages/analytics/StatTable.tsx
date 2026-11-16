// Sortable stat table shared by the Players and Teams tabs: tinted cells from league percentiles, press a row to pick it.
import React, { useMemo, useState } from 'react';

export interface Column<Row> {
  key: string;
  label: string;
  title?: string;
  value: (row: Row) => number | string | null;
  format?: (value: number | string | null, row: Row) => React.ReactNode;
  /** League percentile (0-100, higher = better) used to tint the cell. */
  pct?: (row: Row) => number | null;
  /** Still shown when the table is compact (a card is open beside it). */
  keep?: boolean;
  left?: boolean;
}

interface StatTableProps<Row> {
  rows: Row[];
  columns: Column<Row>[];
  rowKey: (row: Row) => string;
  defaultSort: string;
  /** Start with the lowest values first (default: highest first). */
  defaultAsc?: boolean;
  tintTop: number;
  tintBottom: number;
  selectedKey?: string | null;
  highlight?: (row: Row) => boolean;
  onSelect?: (row: Row) => void;
  compact?: boolean;
  caption: string;
}

export function StatTable<Row>({ rows, columns, rowKey, defaultSort, defaultAsc, tintTop, tintBottom, selectedKey, highlight, onSelect, compact, caption }: StatTableProps<Row>) {
  const [sort, setSort] = useState<{ key: string; asc: boolean }>({ key: defaultSort, asc: !!defaultAsc });
  const shown = compact ? columns.filter((c) => c.keep) : columns;
  const sortCol = columns.find((c) => c.key === sort.key) ?? columns.find((c) => c.key === defaultSort);

  const sorted = useMemo(() => {
    if (!sortCol) return rows;
    const dir = sort.asc ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = sortCol.value(a);
      const vb = sortCol.value(b);
      if (va === null || va === undefined) return vb === null || vb === undefined ? 0 : 1;
      if (vb === null || vb === undefined) return -1;
      if (typeof va === 'string' || typeof vb === 'string') return String(va).localeCompare(String(vb)) * dir;
      return (va - vb) * dir;
    });
  }, [rows, sortCol, sort.asc]);

  const onSort = (key: string) =>
    setSort((s) => (s.key === key ? { key, asc: !s.asc } : { key, asc: columns.find((c) => c.key === key)?.left ?? false }));

  return (
    <table className={`an-table${compact ? ' is-compact' : ''}`}>
      <caption className="an-sr">{caption}</caption>
      <thead>
        <tr>
          <th className="an-rank" scope="col">#</th>
          {shown.map((c) => (
            <th key={c.key} scope="col" className={c.left ? 'is-left' : undefined} title={c.title}
              aria-sort={sortCol?.key === c.key ? (sort.asc ? 'ascending' : 'descending') : undefined}>
              <button type="button" onClick={() => onSort(c.key)}>
                {c.label}{sortCol?.key === c.key && (sort.asc ? ' ▴' : ' ▾')}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row, i) => {
          const key = rowKey(row);
          const cls = [key === selectedKey ? 'is-sel' : '', highlight?.(row) ? 'is-mine' : '', onSelect ? 'is-pick' : ''].join(' ').trim();
          return (
            <tr key={key} className={cls || undefined} onClick={onSelect ? () => onSelect(row) : undefined}
              tabIndex={onSelect ? 0 : undefined} aria-selected={onSelect ? key === selectedKey : undefined}
              onKeyDown={onSelect ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(row); } } : undefined}>
              <td className="an-rank">{i + 1}</td>
              {shown.map((c) => {
                const v = c.value(row);
                const p = c.pct?.(row);
                const tint = p === null || p === undefined ? '' : p >= tintTop ? 'is-top' : p <= tintBottom ? 'is-bottom' : '';
                return (
                  <td key={c.key} className={[c.left ? 'is-left' : '', tint].join(' ').trim() || undefined}>
                    {c.format ? c.format(v, row) : v === null || v === undefined ? '—' : v}
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
