// Finances & CBA page: payload of /api/economy (core/league_finances.py) and the words written from it.

export type PayrollStatus = 'second_apron' | 'first_apron' | 'tax' | 'over_cap' | 'under_cap' | 'under_floor' | 'no_cap';

/** A CBA line is null when it does not exist (no aprons before 2023, no-cap mode). */
export interface SeasonLines {
  year: number | null;
  no_cap: boolean;
  salary_cap: number | null;
  salary_floor: number | null;
  luxury_tax: number | null;
  first_apron: number | null;
  second_apron: number | null;
  mle: number | null;
  bae: number | null;
  min_salary: number;
}

export interface NextSeasonLines {
  year: number | null;
  salary_cap: number | null;
  luxury_tax: number | null;
  first_apron: number | null;
  second_apron: number | null;
}

export interface LeagueTotals {
  teams: number;
  total_payroll: number;
  average_payroll: number;
  highest_payroll: number;
  lowest_payroll: number;
  taxpayers: number;
  over_cap: number;
  under_cap: number;
  under_floor: number;
}

export interface TeamFinances {
  name: string;
  payroll: number;
  cap_space: number | null;
  status: PayrollStatus;
  owner: string | null;
  roster_size: number;
  next_payroll: number | null;
  next_cap_space: number | null;
  expiring_salary: number;
}

export interface ContractLine {
  name: string;
  team: string;
  salary: number;
  score: number;
  fair_salary: number;
}

export interface EconomyData {
  season: SeasonLines;
  next_season: NextSeasonLines | null;
  league: LeagueTotals;
  teams: TeamFinances[];
  /** Teams with the most cap room next summer, most first. */
  market_watch: string[];
  contracts: { highest: ContractLine[]; bargains: ContractLine[]; overpays: ContractLine[] };
}

/** Table groups, most expensive first. */
export const STATUS_ORDER: PayrollStatus[] = ['second_apron', 'first_apron', 'tax', 'over_cap', 'under_cap', 'under_floor', 'no_cap'];

export const STATUS_LABELS: Record<PayrollStatus, string> = {
  second_apron: 'Over the second apron',
  first_apron: 'Over the first apron',
  tax: 'Taxpayers',
  over_cap: 'Over the cap',
  under_cap: 'Under the cap',
  under_floor: 'Under the floor',
  no_cap: 'No cap',
};

export const money = (value: number) => `$${value.toFixed(1)}M`;

export const seasonLabel = (year: number | null | undefined) =>
  year ? `${year}-${String((year + 1) % 100).padStart(2, '0')}` : '';

const lastWord = (name: string) => name.split(' ').slice(-1)[0] || name;
const teamsWord = (n: number) => (n === 1 ? '1 team' : `${n} teams`);

/** Front-page headline: the biggest story in the numbers. */
export function headline(data: EconomyData): { lead: string; rest: string } {
  const top = data.teams[0];
  if (!top) return { lead: 'No payrolls', rest: 'on file yet' };
  const topName = lastWord(top.name);
  const { taxpayers } = data.league;
  const apron2 = data.teams.filter((t) => t.status === 'second_apron').length;

  if (data.season.no_cap) return { lead: 'No cap, no limits:', rest: `${topName} spend ${money(top.payroll)}` };
  if (apron2 > 0) return { lead: `${teamsWord(apron2)} over the second apron`, rest: `as ${topName} hit ${money(top.payroll)}` };
  if (taxpayers === 0) return { lead: 'Nobody pays the tax;', rest: `${topName} lead the league at ${money(top.payroll)}` };
  if (taxpayers === 1) return { lead: `${topName} alone in the tax`, rest: `at ${money(top.payroll)}` };
  return { lead: `${teamsWord(taxpayers)} pay the tax`, rest: `as ${topName} hit ${money(top.payroll)}` };
}

/** The paragraph under the headline. */
export function standfirst(data: EconomyData): string {
  const { season, next_season: next, league } = data;
  const total = league.total_payroll >= 1000 ? `$${(league.total_payroll / 1000).toFixed(2)}B` : money(league.total_payroll);
  const sentences = [`League payroll stands at ${total}, an average of ${money(league.average_payroll)} a team`];

  if (season.salary_cap !== null) {
    const gap = league.average_payroll - season.salary_cap;
    sentences[0] += `, ${money(Math.abs(gap))} ${gap >= 0 ? 'over' : 'under'} the cap.`;
    const roomy = league.under_cap === 0 ? 'No team has room under the cap'
      : `${league.under_cap * 2 < league.teams ? 'Only ' : ''}${teamsWord(league.under_cap)} ${league.under_cap === 1 ? 'has' : 'have'} room under the cap`;
    const floor = season.salary_floor === null ? ''
      : league.under_floor === 0 ? `, and nobody is below the ${money(season.salary_floor)} floor`
      : `, and ${league.under_floor} ${league.under_floor === 1 ? 'sits' : 'sit'} below the ${money(season.salary_floor)} floor`;
    sentences.push(`${roomy}${floor}.`);
    if (season.first_apron !== null) {
      const a1 = data.teams.filter((t) => t.status === 'first_apron' || t.status === 'second_apron').length;
      const a2 = data.teams.filter((t) => t.status === 'second_apron').length;
      sentences.push(`${teamsWord(a1)} ${a1 === 1 ? 'is' : 'are'} over the first apron, ${a2} over the second.`);
    }
  } else {
    sentences[0] += '.';
    sentences.push('This league plays without a salary cap, a luxury tax or aprons.');
  }

  if (next && next.salary_cap !== null && season.salary_cap !== null) {
    const move = next.salary_cap > season.salary_cap + 0.05 ? `rises to ${money(next.salary_cap)}`
      : next.salary_cap < season.salary_cap - 0.05 ? `falls to ${money(next.salary_cap)}` : `stays at ${money(next.salary_cap)}`;
    const aprons = season.first_apron === null && next.first_apron !== null ? ' and the first aprons arrive' : '';
    sentences.push(`Next summer the cap ${move}${aprons}.`);
  }
  return sentences.join(' ');
}

// ---- 4-year outlook (/api/economy/team-multi-year/<team>) ----

export interface OutlookSeason {
  year: number | null;
  payroll: number;
  status: PayrollStatus;
  salary_cap: number | null;
  salary_floor: number | null;
  luxury_tax: number | null;
  first_apron: number | null;
  second_apron: number | null;
  expiring_players: string[];
  expiring_salary: number;
}

export interface OutlookPlayer {
  name: string;
  role: string;
  ovr: number;
  age: number;
  years_left: number;
  /** One per season; null once the contract has run out. */
  salaries: (number | null)[];
}

export interface TeamOutlook {
  team: string;
  seasons: OutlookSeason[];
  players: OutlookPlayer[];
}

/** Stamp text for a season's situation. */
export const STATUS_STAMPS: Record<PayrollStatus, string> = {
  second_apron: 'Over 2nd apron',
  first_apron: 'Over 1st apron',
  tax: 'Taxpayer',
  over_cap: 'Over the cap',
  under_cap: 'Under the cap',
  under_floor: 'Under the floor',
  no_cap: 'No cap',
};

export interface CapLine { key: 'floor' | 'cap' | 'tax' | 'apron1' | 'apron2'; label: string; value: number }

/** The lines that exist in a season, lowest first. */
export function capLines(s: OutlookSeason): CapLine[] {
  const lines: (CapLine | null)[] = [
    s.salary_floor !== null ? { key: 'floor', label: 'Floor', value: s.salary_floor } : null,
    s.salary_cap !== null ? { key: 'cap', label: 'Cap', value: s.salary_cap } : null,
    s.luxury_tax !== null ? { key: 'tax', label: 'Tax', value: s.luxury_tax } : null,
    s.first_apron !== null ? { key: 'apron1', label: '1st apron', value: s.first_apron } : null,
    s.second_apron !== null ? { key: 'apron2', label: '2nd apron', value: s.second_apron } : null,
  ];
  return lines.filter((l): l is CapLine => l !== null);
}

export interface SeasonFact { label: string; value: number; tone: 'good' | 'bad' | 'floor' | 'plain' }

/** How far the payroll sits from each line, as "Cap room $16.7M" / "Into the tax by $3.0M". */
export function seasonFacts(s: OutlookSeason): SeasonFact[] {
  const facts: SeasonFact[] = [];
  const pay = s.payroll;
  if (s.salary_floor !== null && pay < s.salary_floor) facts.push({ label: 'Short of the floor', value: s.salary_floor - pay, tone: 'floor' });
  if (s.salary_cap !== null) {
    facts.push(pay <= s.salary_cap
      ? { label: 'Cap room', value: s.salary_cap - pay, tone: 'good' }
      : { label: 'Over the cap by', value: pay - s.salary_cap, tone: 'bad' });
  }
  if (s.luxury_tax !== null) {
    facts.push(pay <= s.luxury_tax
      ? { label: 'Below the tax', value: s.luxury_tax - pay, tone: 'plain' }
      : { label: 'Into the tax by', value: pay - s.luxury_tax, tone: 'bad' });
  }
  if (s.first_apron !== null) {
    facts.push(pay <= s.first_apron
      ? { label: 'Below the 1st apron', value: s.first_apron - pay, tone: 'plain' }
      : { label: 'Over the 1st apron by', value: pay - s.first_apron, tone: 'bad' });
  }
  return facts;
}

const namesList = (names: string[]) =>
  names.length <= 2 ? names.join(' and ') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;

/** One plain sentence about where the team stands now and what happens next summer. */
export function outlookSentence(outlook: TeamOutlook, isUser: boolean): string {
  const [now, next] = outlook.seasons;
  if (!now) return '';
  const you = isUser ? 'You' : 'They';
  const are = isUser ? 'You are' : 'They are';
  const n = outlook.players.length;
  const parts = [`${n} ${n === 1 ? 'contract' : 'contracts'}.`];
  const pay = now.payroll;

  if (now.salary_cap === null) {
    parts.push('No cap in this league: any signing fits.');
  } else if (pay <= now.salary_cap) {
    const short = now.salary_floor !== null && pay < now.salary_floor ? `${are} ${money(now.salary_floor - pay)} short of the floor, so ` : '';
    parts.push(`${short}${short ? you.toLowerCase() : you} can sign anyone up to ${money(now.salary_cap - pay)} with cap space.`);
  } else if (now.luxury_tax === null || pay <= now.luxury_tax) {
    const tax = now.luxury_tax !== null ? ` and ${money(now.luxury_tax - pay)} below the tax` : '';
    parts.push(`${are} over the cap${tax}: new players come through exceptions, minimum deals or trades.`);
  } else {
    const apron = now.first_apron !== null && pay > now.first_apron ? `, over the first apron by ${money(pay - now.first_apron)}` : '';
    parts.push(`${are} ${money(pay - now.luxury_tax)} into the luxury tax${apron}.`);
  }

  if (next) {
    parts.push(next.expiring_players.length
      ? `Next summer ${money(next.expiring_salary)} comes off the books (${namesList(next.expiring_players)}).`
      : 'Nobody comes off the books next summer.');
  }
  return parts.join(' ');
}
