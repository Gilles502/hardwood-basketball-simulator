// Asset shapes shared by the Trade Machine and its roster table.
export interface PlayerAsset {
  name: string;
  position: string;
  age: number;
  ovr: number;
  potential: number;
  salary: number;
  contract_years: number;
  trade_value: number;
  on_trade_block: boolean;
}

export interface PickAsset {
  year: number;
  key: string;
  display_name: string;
  protection: string;
  /** The user can name a protection on this pick in the deal being built. */
  can_protect?: boolean;
}

export interface TeamAssets {
  players: PlayerAsset[];
  picks: PickAsset[];
}

/** One result of the Trade Finder: a 2-team deal, a 3-team triangle or a multi-team chain. */
export interface TradeOffer {
  trade_type?: '2-team' | '3-team' | 'multi-team';
  partner_team: string;
  partner_strategy?: string;
  value_differential?: number;
  likelihood?: string;
  receiving_players?: any[];
  receiving_picks?: string[];
  giving_players?: any[];
  giving_picks?: string[];
  is_fair?: boolean;
  /** The CPU side's reason for the deal ("Denver needed a starting C"). */
  why?: string;

  // 3-Team fields
  third_team?: string;
  fit_description?: string;
  user_gives_to_b?: any[];
  user_gives_to_c?: any[];
  user_receives?: any[];
  team_b_receives?: any[];
  team_c_receives?: any[];
  full_trade_payload?: any;

  // Multi-Team Chain fields
  chain_length?: number;
  teams?: string[];
  summary?: string;
  flow?: { from: string; to: string; player: string; role: string; ovr: number; salary: number }[];
}

/** One player who asked to be traded (GET /api/trade-requests). */
export interface TradeRequestRow {
  player: string;
  team: string;
  role: string;
  ovr: number;
  age: number;
  salary: number;
  years: number;
  /** "Season 2004" / "Summer 2004" */
  since: string;
  is_user_team: boolean;
}

/** One incoming offer on the user's Trade Block. */
export interface TradeBlockOffer {
  id: string;
  offering_team: string;
  likelihood?: string;
  value_differential?: number;
  reason?: string;
  /** The offering team's reason for the offer. */
  why?: string;
  giving_players: { name: string; position: string; ovr: number; salary: number }[];
  giving_picks: string[];
  receiving_players: { name: string; position: string; ovr: number; salary: number }[];
  receiving_picks: string[];
  strategic_assessment?: string;
}
