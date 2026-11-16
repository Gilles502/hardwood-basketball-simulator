import { useLeagueStore } from '../store/leagueStore';

/** Shown on every action that changes the league while a live run is going (the server answers 409 too). */
export const SIM_LOCK_HINT = 'Stop the simulation first';

/** True while a live regular-season run is going (not once it ended with an error). */
export const useSimRunning = (): boolean =>
  useLeagueStore((s) => s.simRun !== null && s.simRun.error === null);
