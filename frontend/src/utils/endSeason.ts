// End of Season Hub: the 9 offseason phases and the call each phase's "Next" makes.
// The server decides which phase is current (core/end_season.py -> leagueData.end_season); keep PHASES in sync with it.

export const PHASES = [
  'Season recap',
  'Contract options',
  'Development & retirements',
  'Staff & lottery',
  'Pre-draft trades',
  'Draft',
  'Free agency',
  'Roster cuts',
  'New season',
] as const;

export interface EndSeasonStatus {
  open: boolean;
  phase: number | null;
  first: number | null;
  last: number | null;
}

/** What a phase tells the action bar. */
export interface PhaseBarState {
  /** Disables "Next" and is shown as the reason; null/undefined = enabled. */
  blocking?: string | null;
  /** Replaces the default "Next: <phase> →" text. */
  nextLabel?: string;
  /** Asked with window.confirm before advancing. */
  confirm?: string;
  /** JSON body of the phase's Next call. */
  payload?: Record<string, unknown>;
}

/** Props every phase component receives from the hub. */
export interface PhaseProps {
  /** A completed phase reopened from the rail: show results, no actions. */
  readOnly: boolean;
  onBar: (bar: PhaseBarState) => void;
  /** Re-reads league data after the phase ran a server action of its own. */
  onAdvanced: () => Promise<void>;
  onNavigate: (tab: import('../navigation').Tab) => void;
}

/** The request each phase's "Next" sends. Phases 3, 4 and 6 only move the hub marker (no server state change);
 * the Draft phase opens the draft by itself, so its Next only leaves the results for free agency. */
const NEXT_CALLS: { url: string; body?: Record<string, unknown> }[] = [
  { url: '/api/start_offseason' },
  { url: '/api/offseason/run_options_decision', body: { decisions: {} } },
  { url: '/api/offseason/hub_step', body: { step: 3 } },
  { url: '/api/offseason/hub_step', body: { step: 4 } },
  { url: '/api/run_trades' },
  { url: '/api/offseason/hub_step', body: { step: 6 } },
  { url: '/api/run_free_agency' },
  { url: '/api/run_roster_cuts' },
  { url: '/api/nuova_stagione' },
];

export function nextRequest(phase: number, payload?: Record<string, unknown>): { url: string; body: string } {
  const call = NEXT_CALLS[phase];
  return { url: call.url, body: JSON.stringify({ ...(call.body ?? {}), ...(payload ?? {}) }) };
}

export function defaultNextLabel(phase: number, year: number | null | undefined): string {
  if (phase >= PHASES.length - 1) {
    return year ? `Start ${year + 1}-${String((year + 2) % 100).padStart(2, '0')} →` : 'Start the new season →';
  }
  return `Next: ${PHASES[phase + 1]} →`;
}

export const offseasonLabel = (year: number | null | undefined) =>
  year ? `${year}-${String((year + 1) % 100).padStart(2, '0')} offseason` : 'Offseason';
