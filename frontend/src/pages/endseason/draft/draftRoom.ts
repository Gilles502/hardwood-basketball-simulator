// Draft room data (GET /api/draft/state and the draft actions, built by offseason/draft.py) and the wire sentences.
import { normalizeRole } from '../../../utils/roles';

export interface OrderPick {
  pick_index: number;
  round: number;
  pick: number;
  original_owner: string;
  current_owner: string;
}

/** A prospect as the user's scouts see them (core/scouting_view.py): values are exact, a range or "?". */
export interface Prospect {
  name: string;
  role: string;
  age: number;
  provenance: string;
  scouting_progress: number;
  assigned_scout: string | null;
  projection: string;
  /** Mock-draft rank among the prospects still on the board. */
  pos: number;
  ovr_display: string;
  pot_display: string;
  archetype: string;
  attributes: Record<string, string>;
}

/** One pick made. `scelta` is "R2 P8"; ratings are the true ones (the player is on a roster now). */
export interface HistoryPick {
  scelta: string;
  squadra: string;
  original_owner?: string;
  nome: string;
  ruolo?: string;
  valutazione?: number;
  potenziale?: number;
  provenance?: string;
  pedigree?: string;
}

/** A CPU-to-CPU trade: `team_on_clock` gave pick #pick_given to `partner`, dropped to #pick_received, got a player. */
export interface DraftTrade {
  team_on_clock: string;
  partner: string;
  player_involved: string;
  player_ovr: number;
  pick_given: number;
  pick_received: number;
  pick_index?: number;
}

export interface DraftState {
  status: 'DRAFT_IN_PROGRESS' | 'COMPLETED' | 'NOT_STARTED';
  pick_corrente?: number;
  scelte_totali?: number;
  on_the_clock?: OrderPick | null;
  ordine?: OrderPick[];
  is_user_turn?: boolean;
  history?: HistoryPick[];
  prospects?: Prospect[];
  ultimo_scambio?: DraftTrade | null;
  trades?: DraftTrade[];
  user_team?: string | null;
  league_state?: string;
  error?: string;
}

export const parseScelta = (scelta: string): { round: number; pick: number } => {
  const match = /R(\d+)\s*P(\d+)/.exec(scelta);
  return match ? { round: Number(match[1]), pick: Number(match[2]) } : { round: 1, pick: 0 };
};

/** Picks per round, from the order when there is one, else from the first-round results. */
export const picksPerRound = (state: DraftState): number => {
  const fromOrder = (state.ordine ?? []).filter((p) => p.round === 1).length;
  if (fromOrder) return fromOrder;
  return Math.max(0, ...(state.history ?? []).map((h) => parseScelta(h.scelta)).filter((s) => s.round === 1).map((s) => s.pick));
};

/** "R2 P8" with 30 picks a round -> 38. */
export const overallPick = (scelta: string, perRound: number): number => {
  const { round, pick } = parseScelta(scelta);
  return (round - 1) * perRound + pick;
};

/** "#8 Team Name take Alex Smith (PF, State)"; missing parts are left out, never an empty "()". */
export const wireLine = (pick: HistoryPick, perRound: number): string => {
  const details = [pick.ruolo ? normalizeRole(pick.ruolo) : '', pick.provenance ?? ''].filter(Boolean).join(', ');
  return `#${overallPick(pick.scelta, perRound)} ${pick.squadra} take ${pick.nome}${details ? ` (${details})` : ''}`;
};

export const tradeLine = (t: DraftTrade): string =>
  `${t.partner} move up to #${t.pick_given}; ${t.team_on_clock} drop to #${t.pick_received} and get ${t.player_involved}${t.player_ovr ? ` (${t.player_ovr} OVR)` : ''}`;
