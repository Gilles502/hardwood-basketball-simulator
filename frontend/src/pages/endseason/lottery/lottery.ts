// Lottery night data (GET /api/lottery/details, built by core/lottery_view.py) and the small rules the page shows.
import { crestLabel } from '../../../utils/crest';

/** One lottery pick after the draw. `projected` is the seed the team entered with (1 = worst record). */
export interface LotteryPick {
  pick: number;
  team: string;
  projected: number;
  delta: number;
  record: string;
  odds_first: number;
  odds_top4: number;
  /** Who owns the pick now (after protections), who owned it before the draw, and the protection on it. */
  owner: string;
  owner_before: string;
  protection: string;
  protection_triggered: boolean;
}

/** A still-sealed seed (0-based) and its chance (%) of the #1 pick at one reveal step. */
export interface HuntEntry {
  seed: number;
  odds_first: number;
}

export interface FullOrderPick {
  round: number;
  pick: number;
  overall: number;
  team: string;
  owner: string;
  record: string;
  projected: number;
  delta: number;
}

export interface PreviewTeam {
  seed: number;
  team: string;
  owner: string;
  protection: string;
  record: string;
  odds_first: number;
  odds_top: number;
}

export interface LotteryDetails {
  picks: LotteryPick[];
  /** hunt_steps[k] = odds after the last k picks were revealed. */
  hunt_steps: HuntEntry[][];
  full_order: FullOrderPick[];
  /** How many picks the draw decides (CONFIG.OFFSEASON.LOTTERY_DRAWN_PICKS); the rest follow the seeds. */
  drawn_picks: number;
  season_year?: number;
}

/** localStorage key of the reveal progress, per season and team. */
export const revealKey = (season: number | string, team: string) => `ubs.lotteryReveal.${season}.${team}`;

/** "via MEM" when the pick belongs to someone else than the team it came from. */
export const pickLabel = (owner: string, team: string) => (owner === team ? '' : `via ${crestLabel(team)}`);

export const protectionLabel = (protection: string) =>
  protection && protection !== 'Unprotected' ? `${protection} protected` : '';

export const ordinal = (n: number) => {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${tail}`;
};

/**
 * True when every pick below the drawn ones is open and the user still holds a sealed one (as held before the draw)
 * that is sure to stay theirs: their own pick, or another team's pick without a protection. That pick can only be
 * one of the drawn picks. (A protected pick from another team may still go back, so it promises nothing.)
 */
export function userIsTopCertain(picks: LotteryPick[], revealed: number, userTeam: string, drawnPicks: number): boolean {
  const n = picks.length;
  const drawn = Math.min(drawnPicks, n);
  if (revealed < n - drawn) return false;
  const sealed = picks.filter((p) => p.pick <= n - revealed);
  return sealed.some((p) => p.owner_before === userTeam && (p.team === userTeam || !protectionLabel(p.protection)));
}
