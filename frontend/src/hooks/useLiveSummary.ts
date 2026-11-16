import { useEffect } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { useLiveStore } from '../store/liveStore';

export const LIVE_POLL_MS = 10_000;

/** Keeps the live summary current: on mount, every 10 s while visible, on focus, and after any league data update. */
export function useLiveSummary(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;

    const refresh = () => {
      void useLiveStore.getState().refresh();
    };
    refresh();

    const timer = setInterval(() => {
      const { simulating, simRun } = useLeagueStore.getState();
      if (document.visibilityState === 'visible' && !simulating && !(simRun && simRun.error === null)) refresh();
    }, LIVE_POLL_MS);

    const onVisibility = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisibility);

    // Every sim, save and load action replaces leagueData, so this covers all of them.
    const unsubscribe = useLeagueStore.subscribe((state, previous) => {
      if (state.leagueData !== previous.leagueData) refresh();
    });

    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
      unsubscribe();
    };
  }, [enabled]);
}
