// Payload of /api/board (the user's office): board profile, GM career and season reports.

export interface BoardObjective {
  id: string;
  title: string;
  description: string;
  category: string;
  target_value: number;
  current_value: number;
  status: 'Pending' | 'Completed' | 'Failed';
  impact_approval: number;
}

export interface BoardMessage {
  date: string;
  sender: string;
  title: string;
  content: string;
  type: 'info' | 'warning' | 'success' | 'danger';
}

export interface BoardProfile {
  owner_name: string;
  personality: string;
  patience_level: number;
  spending_attitude: number;
  approval_rating: number;
  status_label: string;
  objectives: BoardObjective[];
  board_messages: BoardMessage[];
  seasons_with_team: number;
}

export interface GMContract {
  salary_per_year: number;
  years_remaining: number;
  total_years: number;
  can_extend: boolean;
  extension_offered: {
    years: number;
    salary: number;
    team_name: string;
  } | null;
}

export interface GMBadge {
  id: string;
  name: string;
  description: string;
  icon: string;
  level: number;
}

export interface GMAchievement {
  id: string;
  title: string;
  description: string;
  icon: string;
  unlocked: boolean;
  date_unlocked?: string;
}

export interface AnnualSeasonReport {
  season_number: number;
  year: number;
  team_name: string;
  record: string;
  win_pct: number;
  conference_rank: string;
  playoff_result: string;
  approval_rating: number;
  status_label: string;
  owner_name: string;
  owner_personality: string;
  owner_letter_title: string;
  owner_letter_content: string;
  objectives_completed_count: number;
  objectives_total_count: number;
  objectives: {
    title: string;
    category: string;
    description: string;
    target: number;
    current: number;
    status: string;
    impact: number;
  }[];
  top_players: {
    name: string;
    role: string;
    ovr: number;
    ppg: number;
    rpg: number;
    apg: number;
  }[];
  awards: string[];
  narrative_story: string;
  is_live: boolean;
  created_at: string;
}

export interface UserProfileGM {
  name: string;
  reputation_style: string;
  contract: GMContract;
  badges: GMBadge[];
  achievements: GMAchievement[];
  career_wins: number;
  career_losses: number;
  titles_won: number;
  seasons_managed: number;
  teams_managed_history: { team: string; start_season: number; titles: number }[];
  current_team_name: string;
  season_reports?: AnnualSeasonReport[];
}

export interface BoardDataResponse {
  board_profile: BoardProfile;
  user_gm_profile: UserProfileGM;
  is_fired: boolean;
  job_offers: any[];
  annual_reports?: AnnualSeasonReport[];
  live_report?: AnnualSeasonReport;
  error?: string;
}

/** Tone of a status: maps to a theme token (success, info, warning, primary, danger). */
export type Tone = 'ok' | 'info' | 'warn' | 'hot' | 'bad';

/** Approval 0-100 to a tone, same bands as the old gauge colours. */
export const approvalTone = (rating: number): Tone => {
  if (rating >= 80) return 'ok';
  if (rating >= 60) return 'info';
  if (rating >= 40) return 'warn';
  if (rating >= 25) return 'hot';
  return 'bad';
};

/** Job security label from the board engine (Untouchable, Stable, Under Review, Hot Seat, Fired). */
export const securityTone = (label: string): Tone => {
  const l = (label || '').toLowerCase();
  if (l.includes('untouchable') || l.includes('stable')) return 'ok';
  if (l.includes('review')) return 'warn';
  if (l.includes('hot')) return 'hot';
  if (l.includes('fired')) return 'bad';
  return 'info';
};
