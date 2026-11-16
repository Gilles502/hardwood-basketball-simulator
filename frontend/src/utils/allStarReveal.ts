// All-Star Weekend reveal progress: how many steps of each event the viewer has opened, per save and season.
// Kept in localStorage as a convenience. When storage fails, everything counts as revealed.

export type EventId = 'rookie_challenge' | 'selections' | 'three_point' | 'dunk' | 'game';

/** Reveal steps per event: selections East then West, contests first round then final, games one tip-off. */
export const STEPS: Record<EventId, number> = {
  selections: 2,
  three_point: 2,
  dunk: 2,
  rookie_challenge: 1,
  game: 1,
};

const EVENT_IDS = Object.keys(STEPS) as EventId[];

/** One key per save and season, so two saves never share a reveal. */
export const revealKey = (save: string | null, season: number): string =>
  `allstar-reveal:${save ?? '(no save)'}:${season}`;

export const allRevealed = (): Record<EventId, number> => ({ ...STEPS });

export function loadReveal(key: string): Record<EventId, number> {
  try {
    const raw = window.localStorage.getItem(key);
    const stored: Partial<Record<EventId, unknown>> = raw === null ? {} : JSON.parse(raw);
    const steps = {} as Record<EventId, number>;
    for (const id of EVENT_IDS) {
      const n = Math.floor(Number(stored?.[id]) || 0);
      steps[id] = Math.min(Math.max(n, 0), STEPS[id]);
    }
    return steps;
  } catch {
    return allRevealed();
  }
}

export function saveReveal(key: string, steps: Record<EventId, number>): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(steps));
  } catch {
    // Progress is a convenience: without storage the page shows everything next time.
  }
}
