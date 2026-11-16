// Shared lineup rules for the Tactical Board tabs (Lineup and Minutes).
import { normalizeRole } from '../../utils/roles';

export interface BoardPlayer {
  nome: string;
  ruolo: string;
  ovr: number;
  potenziale: number;
  eta: number;
  infortunato: boolean;
  giorni_infortunio_rimanenti: number;
  is_star: boolean;
  valutazioni_posizionali?: Record<string, number>;
}

export const POSITIONS = ['PG', 'SG', 'SF', 'PF', 'C'] as const;
export type Pos = typeof POSITIONS[number];

/** Rating at a position: the engine's positional rating, or OVR minus 8 out of position. */
export const ratingAt = (p: BoardPlayer, pos: string): number =>
  p.valutazioni_posizionali?.[pos] ?? (normalizeRole(p.ruolo) === pos ? p.ovr : p.ovr - 8);

export const gradeOf = (rating: number): string => {
  if (rating >= 90) return 'A+';
  if (rating >= 84) return 'A';
  if (rating >= 78) return 'B+';
  if (rating >= 72) return 'B';
  if (rating >= 65) return 'C';
  return 'D';
};

/** The five starters: the saved lineup first, then the best healthy unused player at each open spot. */
export const resolveStarters = <T extends BoardPlayer>(roster: T[], customLineup: Record<string, string>): Partial<Record<Pos, T>> => {
  const used = new Set<string>();
  const map: Partial<Record<Pos, T>> = {};
  POSITIONS.forEach((pos) => {
    const chosen = roster.find((p) => p.nome === customLineup[pos]);
    if (chosen && !used.has(chosen.nome)) {
      map[pos] = chosen;
      used.add(chosen.nome);
    }
  });
  POSITIONS.forEach((pos) => {
    if (map[pos]) return;
    const best = roster
      .filter((p) => !p.infortunato && !used.has(p.nome))
      .sort((a, b) => ratingAt(b, pos) - ratingAt(a, pos))[0];
    if (best) {
      map[pos] = best;
      used.add(best.nome);
    }
  });
  return map;
};
