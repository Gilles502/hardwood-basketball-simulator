// Free agency data (GET /api/offseason/free_agency/state, built by offseason/free_agency.py) and the sentences the
// page writes from it. The scores, bars and rankings are the market's own (classifica_offerte / dettaglio_punteggio).

export interface RaceOffer {
  team: string;
  salary: number;
  years: number | null;
  option_type: string;
  score: number;
  is_user: boolean;
  /** His old team's offer leads: the market adds his loyalty (seasons with the team and morale) on top. */
  previous_team_bonus: boolean;
  /** That loyalty, in points (0 unless previous_team_bonus). */
  loyalty_bonus: number;
  /** A CPU offer's first salary and day, and its raises (the bidding). */
  first?: { day: number; salary: number };
  history?: { day: number; salary: number }[];
}

export interface WithdrawnOffer { team: string; salary: number; years: number | null; day: number; reason: string }

export interface Race {
  offers: RaceOffer[];
  leader: string | null;
  leader_score: number;
  bar_tonight: number;
  bar_tomorrow: number | null;
  would_sign_with: string | null;
  /** CPU teams that pulled out (no longer in the race). */
  withdrawn?: WithdrawnOffer[];
}

export interface ScorePart { key: string; value: number }

export interface ScoreDetail {
  /** below_pct: a low-ball offer; walks: he will not go back to his old team (the reason). */
  rejected: { below_pct?: number; walks?: string } | null;
  /** His market value (option-adjusted): the money part compares the offer with this. */
  value: number;
  parts: ScorePart[];
  raw: number;
  total: number;
}

export interface UserOffer { team: string; salary: number; years: number; option_type?: string; raise_pct?: number; tool?: string }

export interface FaPlayer {
  nome: string;
  ruolo: string;
  ovr: number;
  potenziale: number;
  eta: number;
  prev_team: string;
  is_own_fa?: boolean;
  has_bird_rights?: boolean;
  is_rfa: boolean;
  /** Today's asking price (drops day by day). */
  ask: number;
  active_user_offer: UserOffer | null;
  race: Race;
  /** The player's score for the user's offer, or at his ask when there is none. */
  score: ScoreDetail;
}

export interface Signing {
  player: string;
  role: string;
  ovr: number;
  team: string;
  salary: number;
  years: number;
  option_type: string;
  day: number;
  beat: { team: string; salary: number; years: number }[];
}

export interface RosterPlayer { name: string; role: string; ovr: number; new: boolean }

export interface FaUserTeam {
  nome: string;
  payroll: number;
  cap_space: number;
  salary_cap: number | null;
  mle_type: string;
  mle_available: boolean;
  mle_amount: number;
  bae_amount: number;
  bae_available: boolean;
  min_salary: number;
  roster_count: number;
  roster_limit: number;
  team_goal: string;
  roster: RosterPlayer[];
}

export interface RfaMatch { player: string; team: string; salary: number; years: number; option_type?: string }

export interface FaState {
  success?: boolean;
  error?: string;
  current_day: number;
  days_total: number;
  completed: boolean;
  signings: Signing[];
  user_team: FaUserTeam;
  user_offers: Record<string, UserOffer>;
  pending_rfa_match: RfaMatch | null;
  players: FaPlayer[];
  /** Last night's raises, pull-outs and signings. */
  night_moves?: NightMove[];
}

export interface NightMove { type: 'raise' | 'out' | 'signed'; team: string; player: string; salary?: number; reason?: string; day: number }

/** "▲ raised from $21.0M on day 4" for a raised CPU offer, else null. */
export function raiseLine(o: RaceOffer): string | null {
  if (!o.history || o.history.length === 0 || !o.first) return null;
  return `▲ raised from ${money(o.first.salary)} on day ${o.history[o.history.length - 1].day}`;
}

/** Two or more live offers and at least one raised: a bidding war. */
export const isBiddingWar = (race: Race) => race.offers.length >= 2 && race.offers.some((o) => (o.history?.length ?? 0) > 0);

export const POSITIONS = ['PG', 'SG', 'SF', 'PF', 'C'] as const;

export const money = (m: number) => (m < 0 ? `−$${Math.abs(m).toFixed(1)}M` : `$${m.toFixed(1)}M`);

const OPTION_LABEL: Record<string, string> = { PO: 'player option', TO: 'team option' };
export const contractLine = (salary: number, years: number | null, option?: string) =>
  `${money(salary)}${years ? ` × ${years}` : ''}${option && OPTION_LABEL[option] ? ` · ${OPTION_LABEL[option]}` : ''}`;

export type Chance = 'Leading' | 'Behind' | 'No offer';

export function chanceOf(race: Race, userTeam: string): Chance {
  if (!race.offers.some((o) => o.team === userTeam)) return 'No offer';
  return race.leader === userTeam ? 'Leading' : 'Behind';
}

/** Tonight as things stand — new CPU offers can still arrive before the night is resolved. */
export function verdict(race: Race, userTeam: string): string {
  const bar = Math.round(race.bar_tonight);
  if (race.offers.length === 0) return `No offers yet. Tonight he would sign for a score of ${bar}.`;
  if (race.would_sign_with) {
    return race.would_sign_with === userTeam
      ? 'As things stand, he signs with you tonight.'
      : `As things stand, he signs with ${race.would_sign_with} tonight.`;
  }
  return race.bar_tomorrow === null
    ? `Last day: nobody reaches tonight's bar (${bar}).`
    : `As things stand, nobody reaches tonight's bar (${bar}). Tomorrow it drops to ${Math.round(race.bar_tomorrow)}.`;
}

/** Plain-English label of one part of the score. */
export function partLabel(key: string, value: number, ctx: { offer: number; worth: number; role: string; teamGoal: string; day: number }): string {
  switch (key) {
    case 'money': return `Money: ${money(ctx.offer)} vs his ${money(ctx.worth)} value`;
    case 'money_bonus': return 'Big-contract excitement (25%+ over his value)';
    case 'morale': return 'His morale';
    case 'stars': return 'Stars already on your roster';
    case 'role':
      return value > 0 ? `Starting spot open at ${ctx.role}` : value < 0 ? `A star already starts at ${ctx.role}` : `No starting-spot bonus at ${ctx.role}`;
    case 'team_state': return `Your team: ${ctx.teamGoal}`;
    case 'age': return value > 0 ? 'Veteran looking for a last home' : value < 0 ? 'Young star who wants the spotlight' : 'Age';
    case 'market_day': return `Day ${ctx.day} of the market (players get less picky)`;
    default: return key;
  }
}

export const signed = (v: number) => (v > 0 ? `+${Math.round(v)}` : v < 0 ? `−${Math.abs(Math.round(v))}` : '±0');
