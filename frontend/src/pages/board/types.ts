// Payloads of the front-office routes (core/front_office/view.py): /api/front_office/gms | gm | market.

export interface GMSkills {
  trade: number;
  contracts: number;
  draft: number;
}

export interface LeagueGMRow {
  team: string;
  gm_id: string | null;
  name: string;
  age: number | null;
  is_user: boolean;
  plan: string | null;
  plan_label: string | null;
  seasons_held: number | null;
  traits: string[];
  skills: GMSkills | null;
  interim: boolean;
  new_this_year: boolean;
}

export interface LeagueGMsPayload {
  season: number;
  year: number;
  rows: LeagueGMRow[];
}

export interface PlanChange {
  year: number;
  from: string | null;
  to: string;
  reason: string;
  checkpoint: 'start' | 'new_season' | 'deadline' | string;
}

export interface TeamMove {
  season: number;
  year: number;
  window: string;
  kind: 'trade' | 'signing' | 'let_walk' | 'draft' | string;
  text: string;
  plan: string | null;
  when: string;
}

export interface CareerJob {
  team: string;
  from_year: number;
  to_year: number | null;
  end: 'fired' | 'retired' | 'user_took_over' | 'interim_end' | null;
  end_label: string;
  wins: number;
  losses: number;
  playoffs: number;
  titles: number;
  awards: string[];
}

export interface HiringNote {
  year: number;
  kind: 'turned_down' | 'chosen_over' | 'chased_by' | string;
  team: string | null;
  names: string[];
  text: string;
}

export interface GMCardPayload {
  team: string;
  is_user: boolean;
  user_name: string | null;
  gm: {
    gm_id: string;
    name: string;
    age: number;
    years_as_gm: number;
    tenure: number;
    historical: boolean;
    traits: { code: string; label: string }[];
    skills: GMSkills;
    interim: boolean;
    career: CareerJob[];
    hiring_notes: HiringNote[];
  } | null;
  plan: {
    state: string;
    label: string;
    seasons_held: number;
    expected_seasons: number | null;
    reason: string;
    since_year: number;
    history: PlanChange[];
  } | null;
  coach: { name: string | null; style: string | null; wants: string | null } | null;
  owner: { personality: string; patience: number | null; spending: number | null };
  moves: TeamMove[];
}

export interface MarketGM {
  gm_id: string;
  name: string;
  age: number;
  years_as_gm: number;
  traits: string[];
  skills: GMSkills;
  historical: boolean;
  available_from_year: number | null;
  jobs: number;
  titles: number;
  playoffs: number;
}

export interface GMMarketPayload {
  year: number;
  unemployed: MarketGM[];
}
