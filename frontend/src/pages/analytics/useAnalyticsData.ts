import { useEffect, useState } from 'react';

/** GETs an analytics payload; `null` path = idle. Refetches when the path changes. */
export function useAnalyticsData<T>(path: string | null): { data: T | null; failed: boolean } {
  const [state, setState] = useState<{ path: string | null; data: T | null; failed: boolean }>({ path: null, data: null, failed: false });

  useEffect(() => {
    if (!path) return;
    let alive = true;
    const sep = path.includes('?') ? '&' : '?';
    fetch(`${path}${sep}_t=${Date.now()}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data) => { if (alive) setState({ path, data, failed: false }); })
      .catch(() => { if (alive) setState({ path, data: null, failed: true }); });
    return () => { alive = false; };
  }, [path]);

  // While a new path loads, the previous payload is not shown as if it belonged to it.
  if (state.path !== path) return { data: null, failed: false };
  return { data: state.data, failed: state.failed };
}

export const fmt = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(digits);

export const fmtSigned = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(digits)}`;
