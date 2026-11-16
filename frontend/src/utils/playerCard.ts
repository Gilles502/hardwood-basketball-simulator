// Pure logic behind the Scouting Report player card: tier, paper stock, stamp and award seals.
// Award names follow the save data vocabulary (it still mixes English and Italian words).

import type { LeagueData } from '../store/leagueStore';

export type CardTier = 'prospect' | 'starter' | 'all_star' | 'superstar';
export type CardStock = 'kraft' | 'cream_copper' | 'cream' | 'gold' | 'pewter' | 'black';

/** Display names of the paper stocks. */
export const STOCK_LABELS: Record<CardStock, string> = {
  kraft: 'Kraft',
  cream_copper: 'Copper',
  cream: 'Cream',
  gold: 'Gold foil',
  pewter: 'Pewter',
  black: 'Black & gold',
};

export type SealId = 'mvp' | 'finals_mvp' | 'champion' | 'dpoy' | 'roy' | 'all_star';

export interface AwardCounts {
  mvp: number;
  finalsMvp: number;
  rings: number;
  dpoy: number;
  roy: boolean;
  allStar: number;
}

/** Awards of the season in progress that may not be archived in the career history yet. */
export interface LiveAwards {
  season: number | undefined;
  mvp: boolean;
  finalsMvp: boolean;
  dpoy: boolean;
  roy: boolean;
  champion: boolean;
}

export interface Seal {
  id: SealId;
  label: string;
  /** Full name for text lists (the label is short enough for a round seal). */
  name: string;
  count: number;
}

export interface CardLook {
  tier: CardTier;
  stock: CardStock;
  stamp: string;
  goat: boolean;
  counts: AwardCounts;
  seals: Seal[];
  shown: Seal[];
  more: number;
}

const MAX_SEALS_SHOWN = 2;

const TIER_STAMPS: Record<CardTier, string> = {
  prospect: 'PROSPECT',
  starter: 'STARTER',
  all_star: 'ALL-STAR',
  superstar: 'SUPERSTAR',
};

const TIER_RANK: Record<CardTier, number> = { prospect: 0, starter: 1, all_star: 2, superstar: 3 };

/** Reads this season's award winners and champion for one player out of the league data. */
export function liveAwardsOf(leagueData: LeagueData | null | undefined, player: any): LiveAwards {
  const name = (player?.nome || '').trim().toLowerCase();
  const same = (candidate?: string) => !!candidate && candidate.trim().toLowerCase() === name;
  const champion = leagueData?.playoffs?.campione;
  return {
    season: leagueData?.stagione ?? leagueData?.season_number,
    mvp: same(leagueData?.premi?.mvp?.nome),
    dpoy: same(leagueData?.premi?.dpoy?.nome),
    roy: same(leagueData?.premi?.roy?.nome),
    finalsMvp: same(leagueData?.playoffs?.mvp_finali?.nome),
    champion: !!champion && !!player?.squadra && champion.trim().toLowerCase() === String(player.squadra).trim().toLowerCase(),
  };
}

type Season = { stagione?: number; is_champion?: boolean; premi?: unknown };

function tallyAward(text: string, counts: AwardCounts): void {
  const lower = text.toLowerCase();
  if (lower.includes('finals mvp') || lower.includes('mvp finali')) counts.finalsMvp++;
  else if (lower.includes('mvp') && !lower.includes('all-star')) counts.mvp++;
  if (lower.includes('dpoy') || lower.includes('difensore')) counts.dpoy++;
  if (lower.includes('roy') || lower.includes('rookie')) counts.roy = true;
  if (lower.includes('all-star')) counts.allStar++;
}

export function countAwards(player: any, live: LiveAwards): AwardCounts {
  const counts: AwardCounts = { mvp: 0, finalsMvp: 0, rings: typeof player?.anelli_vinti === 'number' ? player.anelli_vinti : 0, dpoy: 0, roy: false, allStar: 0 };
  const career: Season[] = Array.isArray(player?.carriera) ? player.carriera : [];

  if (career.length > 0) {
    // Season-by-season history is authoritative for rings and awards.
    let careerRings = 0;
    for (const season of career) {
      if (season.is_champion) careerRings++;
      if (Array.isArray(season.premi)) {
        for (const award of season.premi) {
          if (typeof award === 'string' && award) tallyAward(award, counts);
        }
      }
    }
    counts.rings = Math.max(counts.rings, careerRings);

    const archived = live.season !== undefined && career.some((season) => season.stagione === live.season);
    if (!archived) {
      if (live.mvp) counts.mvp++;
      if (live.finalsMvp) counts.finalsMvp++;
      if (live.dpoy) counts.dpoy++;
      if (live.roy) counts.roy = true;
      if (live.champion) counts.rings++;
    }
    return counts;
  }

  const source: unknown[] = Array.isArray(player?.premi) && player.premi.length > 0
    ? player.premi
    : (Array.isArray(player?.awards) ? player.awards : []);
  for (const award of source) {
    if (typeof award !== 'string' || !award) continue;
    tallyAward(award, counts);
    const lower = award.toLowerCase();
    if ((lower.includes('campione') || lower.includes('anello') || lower.includes('champion')) && !player?.anelli_vinti) counts.rings++;
  }
  if (live.mvp && counts.mvp === 0) counts.mvp = 1;
  if (live.finalsMvp && counts.finalsMvp === 0) counts.finalsMvp = 1;
  if (live.dpoy && counts.dpoy === 0) counts.dpoy = 1;
  if (live.roy) counts.roy = true;
  if (live.champion && counts.rings === 0) counts.rings = 1;
  return counts;
}

export function isGoat(c: AwardCounts): boolean {
  return (c.rings >= 3 && c.mvp >= 1) || (c.rings >= 2 && c.mvp >= 2) || c.rings >= 4;
}

export function tierOf(ovr: number, allStarCount: number): CardTier {
  if (ovr >= 90) return 'superstar';
  if (ovr >= 84 || allStarCount > 0) return 'all_star';
  if (ovr >= 78) return 'starter';
  return 'prospect';
}

export function stampOf(tier: CardTier, o: { age: number; pot: number; retired: boolean; goat: boolean }): string {
  if (o.goat) return 'G.O.A.T.';
  if (o.retired) return 'RETIRED';
  if ((tier === 'prospect' || tier === 'starter') && o.age <= 22 && o.pot >= 88) return 'PHENOM';
  return TIER_STAMPS[tier];
}

export function stockOf(tier: CardTier, c: AwardCounts, goat: boolean): CardStock {
  if (goat) return 'black';
  if (c.mvp > 0 || c.finalsMvp > 0 || tier === 'superstar') return 'gold';
  if (c.dpoy > 0) return 'pewter';
  if (tier === 'all_star') return 'cream';
  if (tier === 'starter') return 'cream_copper';
  return 'kraft';
}

const SEAL_ORDER: { id: SealId; label: string; name: string; count: (c: AwardCounts) => number }[] = [
  { id: 'mvp', label: 'MVP', name: 'MVP', count: (c) => c.mvp },
  { id: 'finals_mvp', label: 'FMVP', name: 'Finals MVP', count: (c) => c.finalsMvp },
  { id: 'champion', label: 'CHAMP', name: 'Champion', count: (c) => c.rings },
  { id: 'dpoy', label: 'DPOY', name: 'Defensive Player', count: (c) => c.dpoy },
  { id: 'roy', label: 'ROY', name: 'Rookie of the Year', count: (c) => (c.roy ? 1 : 0) },
  { id: 'all_star', label: 'STAR', name: 'All-Star', count: (c) => c.allStar },
];

export function sealsOf(c: AwardCounts): Seal[] {
  return SEAL_ORDER
    .map((entry) => ({ id: entry.id, label: entry.label, name: entry.name, count: entry.count(c) }))
    .filter((seal) => seal.count > 0);
}

export function cardLook(player: any, live: LiveAwards, opts: { retired?: boolean }): CardLook {
  const counts = countAwards(player, live);
  const goat = isGoat(counts);
  const tier = tierOf(player?.ovr || 75, counts.allStar);
  const seals = sealsOf(counts);
  const shown = seals.slice(0, MAX_SEALS_SHOWN);
  const more = seals.slice(MAX_SEALS_SHOWN).reduce((sum, seal) => sum + seal.count, 0);
  return {
    tier,
    stock: stockOf(tier, counts, goat),
    stamp: stampOf(tier, { age: player?.eta ?? 25, pot: player?.potenziale ?? player?.ovr ?? 75, retired: !!opts.retired, goat }),
    goat,
    counts,
    seals,
    shown,
    more,
  };
}

/** Looks the player can pick by hand: every tier up to their own, plus the special stocks they have earned. */
export function earnedStocks(look: CardLook): CardStock[] {
  const rank = TIER_RANK[look.tier];
  const out: CardStock[] = ['kraft'];
  if (rank >= TIER_RANK.starter) out.push('cream_copper');
  if (rank >= TIER_RANK.all_star) out.push('cream');
  if (look.tier === 'superstar' || look.counts.mvp > 0 || look.counts.finalsMvp > 0) out.push('gold');
  if (look.counts.dpoy > 0) out.push('pewter');
  if (look.goat) out.push('black');
  return out;
}

/** "Marcus Vale" -> ["Marcus", "Vale"]; keeps suffixes with the surname ("Gary Smith Jr." -> ["Gary", "Smith Jr."]). */
export function splitName(fullName: string): [string, string] {
  const parts = (fullName || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return ['', '?'];
  if (parts.length === 1) return ['', parts[0]];
  const suffix = /^(jr\.?|sr\.?|ii|iii|iv)$/i;
  const surnameWords = suffix.test(parts[parts.length - 1]) && parts.length > 2 ? 2 : 1;
  return [parts.slice(0, parts.length - surnameWords).join(' '), parts.slice(parts.length - surnameWords).join(' ')];
}

/** Stable four-digit file number for the report header, derived from the name. */
export function cardNumber(name: string): string {
  let hash = 17;
  for (const char of name || '') hash = (hash * 31 + (char.codePointAt(0) ?? 0)) % 9973;
  return String(hash + 1).padStart(4, '0');
}
