// File: frontend/src/store/leagueStore.ts
import { create } from 'zustand';
import {
  reachedAfterDay, reachedBeforeDay, targetDay, targetLabel,
  type SimMilestones, type SimRun, type SimTarget,
} from '../utils/simRun';

export interface PlayerStats {
  ppg: number;
  rpg: number;
  apg: number;
  spg: number;
  bpg: number;
  fg_pct?: number;
  three_pct?: number;
  ft_pct?: number;
}

export interface PlayerContract {
  salary: number;
  years: number;
  player_option: boolean;
  team_option: boolean;
}

export interface PlayerLore {
  role_badge: string;
  career_phase: string;
  status_narrative: string;
}

export interface PlayerDetails {
  id: string;
  nome: string;
  squadra: string;
  ruolo: string;
  eta: number;
  ovr: number;
  pot: number;
  contratto: string;
  contract_data: PlayerContract | null;
  on_trade_block: boolean;
  infortunato?: boolean;
  tipo_infortunio?: string;
  infortunio_nome?: string;
  is_day_to_day?: boolean;
  infortunio_impatto?: number;
  giorni_infortunio_rimanenti?: number;
  lore?: PlayerLore;
  gp_rs?: number;
  gp_po?: number;
  stats_rs: PlayerStats;
  stats_po: PlayerStats | null;
  last_progression?: any;
  premi?: string[];
  awards?: string[];
  anelli_vinti?: number;
  potenziale?: number;
  ovr_history?: any[];
}

export interface TeamPick {
  round: number;
  original_owner: string;
  is_own: boolean;
  protection: string;
}

export interface TradedPick {
  round: number;
  current_owner: string;
  protection: string;
}

export interface FuturePick {
  year: number;
  year_offset: number;
  owned: TeamPick[];
  traded: TradedPick[];
}

export interface TeamData {
  id: string;
  nome: string;
  record: string;
  payroll: number;
  roster: PlayerDetails[];
  future_picks: FuturePick[];
  standings_history?: any[];
}

export interface StandingTeam {
  pos: number;
  nome: string;
  v: number;
  s: number;
}

export interface StatLeader {
  nome: string;
  stats: {
    ppg: number;
    rpg: number;
    apg: number;
    bpg: number;
    spg: number;
  };
}

export interface PlayoffSeries {
  s1_nome: string;
  s1_seed: string | number;
  s1_vittorie: number;
  s2_nome: string;
  s2_seed: string | number;
  s2_vittorie: number;
  winner_nome: string | null;
  games: any[];
}

export interface PlayoffBracket {
  east: {
    qf: PlayoffSeries[];
    sf: PlayoffSeries[];
    cf: PlayoffSeries[];
  };
  west: {
    qf: PlayoffSeries[];
    sf: PlayoffSeries[];
    cf: PlayoffSeries[];
  };
  finals: PlayoffSeries[];
  next_turn: string;
}

export interface LeagueData {
  stagione: number;
  season_number?: number;
  anno_corrente?: number;
  current_day?: number;
  total_calendar_days?: number;
  calendar_progress_pct?: number;
  league_state: string;
  player_team_name: string | null;
  user_role?: 'gm_coach' | 'only_gm' | 'only_coach' | 'spectator';
  enable_play_in?: boolean;
  is_spectator?: boolean;
  is_fired?: boolean;
  firing_info?: any;
  classifica: {
    east: StandingTeam[];
    west: StandingTeam[];
    stat_leaders?: Record<string, StatLeader>;
  };
  premi: any | null;
  playoffs: {
    campione: string | null;
    mvp_finali: any | null;
    bracket: PlayoffBracket;
  } | null;
  offseason: any;
  /** End of Season Hub position, computed by the server (core/end_season.py). */
  end_season?: import('../utils/endSeason').EndSeasonStatus;
  /** Calendar days the Dashboard's "Sim until" offers (server.py _sim_milestones). */
  sim_milestones?: SimMilestones;
  league_database?: {
    teams: TeamData[];
    players_active: PlayerDetails[];
    players_fa: PlayerDetails[];
    players_retired: PlayerDetails[];
  };
  error?: string;
}

export interface SaveMetadata {
  save_name: string;
  display_name: string;
  last_saved: string;
  era: string;
  season: number;
  phase: string;
  player_team_name: string;
  player_team_record?: string;
  is_spectator: boolean;
}

export interface InitSimulationParams {
  era: string;
  saveName?: string;
  leagueSettings?: Record<string, any>;
  selectedTeam?: string;
  userRole?: string;
}

interface LeagueState {
  leagueData: LeagueData | null;
  loading: boolean;
  simulating: boolean;
  /** The live regular-season run (null when none). Kept with its error until clearSimRunError. */
  simRun: SimRun | null;
  error: string | null;
  selectedPlayerName: string | null;
  selectedTeamName: string | null;
  /** A player the Player Database should open (set by the player popup's "Open in Player Database"). */
  databaseTarget: { slug: string; name: string } | null;
  /** A team page the team card asked for (Trophy Room on History, or League Analytics' Teams tab). */
  pageTarget: { page: 'history' | 'analytics'; team: string } | null;
  saves: SaveMetadata[];
  activeSaveName: string | null;
  
  fetchLeagueData: () => Promise<void>;
  fetchLeagueDataSilent: () => Promise<void>;
  setPlayerTeam: (teamName: string) => Promise<void>;
  simulateRegularSeason: () => Promise<void>;
  simulateSecondHalf: () => Promise<void>;
  simulateCalendarDay: () => Promise<any>;
  simulateCalendarWeek: () => Promise<any>;
  simulateCalendarUntil: (targetDayIndex: number, includeTarget?: boolean) => Promise<any>;
  simulateCalendarGame: (gameId: string, enablePlayLog?: boolean) => Promise<any>;
  simulateToNextUserGame: () => Promise<boolean>;
  /** Sim day by day until the target, Stop, or an error; one save at the end. Ignored while a run is going.
   *  Resolves with true when the target itself ended the run. */
  startSimRun: (target: SimTarget) => Promise<boolean>;
  /** The day in flight finishes, then the run ends and saves. */
  stopSimRun: () => void;
  clearSimRunError: () => void;
  simulatePlayoffsTurno: (watchSeriesId?: string) => Promise<any>;
  initSimulation: (eraOrParams: string | InitSimulationParams, saveName?: string) => Promise<void>;
  openPlayerProfile: (name: string | null) => void;
  openTeamProfile: (name: string | null) => void;
  openInDatabase: (target: { slug: string; name: string } | null) => void;
  openTeamPage: (target: { page: 'history' | 'analytics'; team: string } | null) => void;
  
  fetchSaves: () => Promise<SaveMetadata[]>;
  saveGame: (saveName?: string) => Promise<any>;
  loadGame: (saveName: string) => Promise<any>;
  duplicateSave: (sourceName: string, targetName: string) => Promise<any>;
  renameSave: (oldName: string, newDisplayName: string) => Promise<any>;
  deleteSave: (saveName: string) => Promise<any>;
}

export const useLeagueStore = create<LeagueState>((set, get) => ({
  leagueData: null,
  loading: false,
  simulating: false,
  simRun: null,
  error: null,
  selectedPlayerName: null,
  selectedTeamName: null,
  databaseTarget: null,
  pageTarget: null,
  saves: [],
  activeSaveName: null,

  openPlayerProfile: (name) => set({ selectedPlayerName: name }),
  openTeamProfile: (name) => set({ selectedTeamName: name }),
  openInDatabase: (target) => set({ databaseTarget: target, selectedPlayerName: null }),
  openTeamPage: (target) => set({ pageTarget: target, selectedTeamName: null }),

  fetchLeagueData: async () => {
    set({ loading: true, error: null });
    try {
      const response = await fetch(`/api/dati_stagione?_t=${Date.now()}`);
      const data = await response.json();
      if (data.error) {
        set({ error: data.error, loading: false });
      } else {
        set({ leagueData: data, loading: false });
      }
    } catch (err) {
      set({ error: 'Failed to load league data from server.', loading: false });
    }
  },

  fetchLeagueDataSilent: async () => {
    try {
      const response = await fetch(`/api/dati_stagione?_t=${Date.now()}`);
      const data = await response.json();
      if (!data.error) {
        set({ leagueData: data });
      }
    } catch (err) {
      console.error('Silent league data update failed:', err);
    }
  },

  setPlayerTeam: async (teamName: string) => {
    set({ loading: true, error: null });
    try {
      const response = await fetch('/api/set_player_team', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team_name: teamName })
      });
      const data = await response.json();
      set({ leagueData: data, loading: false });
    } catch (err) {
      set({ error: 'Failed to select player franchise.', loading: false });
    }
  },

  simulateRegularSeason: async () => {
    set({ simulating: true, error: null });
    try {
      const response = await fetch('/api/simula_regular_season', { method: 'POST' });
      const data = await response.json();
      set({ leagueData: data, simulating: false });
    } catch (err) {
      set({ error: 'Error while simulating the first half.', simulating: false });
    }
  },

  simulateSecondHalf: async () => {
    set({ simulating: true, error: null });
    try {
      const response = await fetch('/api/simula_second_half', { method: 'POST' });
      const data = await response.json();
      set({ leagueData: data, simulating: false });
    } catch (err) {
      set({ error: 'Error while simulating the second half.', simulating: false });
    }
  },

  // Every regular-season sim button is a live run (startSimRun) with a different target.
  simulateCalendarDay: async () => get().startSimRun({ kind: 'days', count: 1 }),

  simulateCalendarWeek: async () => get().startSimRun({ kind: 'days', count: 7 }),

  // includeTarget plays the target day too, so the run aims at the day after it.
  simulateCalendarUntil: async (targetDayIndex: number, includeTarget = false) =>
    get().startSimRun({ kind: 'day', dayIndex: includeTarget ? targetDayIndex + 1 : targetDayIndex }),

  simulateCalendarGame: async (gameId: string, enablePlayLog = false) => {
    try {
      const response = await fetch('/api/calendar/simulate_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_id: gameId, enable_play_log: enablePlayLog })
      });
      const data = await response.json();
      if (data.league_data) {
        set({ leagueData: data.league_data });
      }
      return data;
    } catch (err) {
      console.error('Error while simulating the single game:', err);
      throw err;
    }
  },

  simulateToNextUserGame: async () => get().startSimRun({ kind: 'next_game' }),

  startSimRun: async (target: SimTarget) => {
    const running = get().simRun;
    if (running && running.error === null) return false;
    const start = get().leagueData;
    const run: SimRun = {
      target, label: targetLabel(target), fromDay: start?.current_day ?? 0,
      targetDay: targetDay(target, start), daysDone: 0, stopRequested: false, error: null,
    };
    set({ simRun: run, error: null });
    const update = (patch: Partial<SimRun>) => {
      const cur = get().simRun;
      if (cur) set({ simRun: { ...cur, ...patch } });
    };
    const userTeam = start?.player_team_name ?? null;
    let reached = false;
    let error: string | null = null;
    try {
      while (!get().simRun?.stopRequested) {
        if (reachedBeforeDay(target, get().leagueData, get().simRun?.daysDone ?? 0)) { reached = true; break; }
        const response = await fetch('/api/calendar/simulate_day', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ autosave: false, lean: true }),
        });
        const data = await response.json().catch(() => null);
        // A payload that failed to serialize leaves current_day stale: a day/deadline target could overshoot.
        if (!response.ok || !data || data.error || data.league_data?.error) {
          error = data?.error || data?.league_data?.error || `The simulation stopped (server error ${response.status}).`;
          break;
        }
        if (data.league_data) {
          // The lean payload has no league_database: keep the last one until the run end sends the full data.
          const prev = get().leagueData;
          set({ leagueData: { ...prev, ...data.league_data,
                              league_database: data.league_data.league_database ?? prev?.league_database } });
        }
        update({ daysDone: (get().simRun?.daysDone ?? 0) + 1 });
        if (reachedAfterDay(target, data, userTeam)) { reached = true; break; }
      }
    } catch (err: any) {
      error = err?.message || 'The simulation stopped with an error.';
    }
    try {
      const response = await fetch('/api/calendar/sim_run_end', { method: 'POST' });
      const data = await response.json();
      if (data.league_data && !data.league_data.error) set({ leagueData: data.league_data });
    } catch (err: any) {
      error = error || 'The game could not be saved after the simulation.';
    }
    if (error) update({ error });
    else set({ simRun: null });
    return reached && !error;
  },

  stopSimRun: () => {
    const cur = get().simRun;
    if (cur && cur.error === null) set({ simRun: { ...cur, stopRequested: true } });
  },

  clearSimRunError: () => set({ simRun: null }),

  simulatePlayoffsTurno: async (watchSeriesId?: string) => {
    const watchId = typeof watchSeriesId === 'string' ? watchSeriesId : undefined;
    set({ simulating: true, error: null });
    try {
      const response = await fetch('/api/simula_playoff_turno', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ watch_series_id: watchId })
      });
      const data = await response.json();
      set({ leagueData: data, simulating: false });
      return data;
    } catch (err) {
      set({ error: 'Error while simulating the playoff round.', simulating: false });
      throw err;
    }
  },

  initSimulation: async (eraOrParams: string | InitSimulationParams, saveName?: string) => {
    set({ loading: true, error: null });
    try {
      let body: any = {};
      if (typeof eraOrParams === 'object') {
        body = {
          start_era: eraOrParams.era,
          save_name: eraOrParams.saveName,
          league_settings: eraOrParams.leagueSettings,
          selected_team: eraOrParams.selectedTeam,
          user_role: eraOrParams.userRole
        };
      } else {
        body = { start_era: eraOrParams, save_name: saveName };
      }

      const response = await fetch('/api/init_simulation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!response.ok) {
        let errMessage = `Unable to initialize the simulation (Status: ${response.status})`;
        try {
          const text = await response.text();
          try {
            const errData = JSON.parse(text);
            errMessage = errData.error || errData.message || errMessage;
          } catch {
            if (text && !text.startsWith('<')) {
              errMessage = text;
            }
          }
        } catch (_) {}
        throw new Error(errMessage);
      }
      const data = await response.json();
      set({ 
        leagueData: data, 
        activeSaveName: body.save_name || (data ? data.active_save_name : null),
        loading: false 
      });
      await get().fetchSaves();
    } catch (err: any) {
      set({ error: err.message || 'Failed to initialize simulation era.', loading: false });
      throw err;
    }
  },

  fetchSaves: async () => {
    try {
      const res = await fetch('/api/saves');
      const data = await res.json();
      if (data.success) {
        set({ saves: data.saves || [], activeSaveName: data.active_save_name });
        return data.saves;
      }
      return [];
    } catch (err) {
      console.error("Error fetching saves:", err);
      return [];
    }
  },

  saveGame: async (saveName?: string) => {
    set({ loading: true });
    try {
      const res = await fetch('/api/saves/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ save_name: saveName })
      });
      const data = await res.json();
      set({ loading: false });
      if (data.success) {
        get().fetchSaves();
      }
      return data;
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  loadGame: async (saveName: string) => {
    set({ loading: true, error: null });
    try {
      const res = await fetch('/api/saves/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ save_name: saveName })
      });
      const data = await res.json();
      if (data.success && data.payload) {
        set({ leagueData: data.payload, activeSaveName: saveName, loading: false });
      } else {
        set({ error: data.error || "Failed to load save file.", loading: false });
      }
      return data;
    } catch (err) {
      set({ error: "Failed to load save file.", loading: false });
      throw err;
    }
  },

  duplicateSave: async (sourceName: string, targetName: string) => {
    set({ loading: true });
    try {
      const res = await fetch('/api/saves/duplicate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_save_name: sourceName, target_save_name: targetName })
      });
      const data = await res.json();
      set({ loading: false });
      if (data.success) {
        get().fetchSaves();
      }
      return data;
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  renameSave: async (oldName: string, newDisplayName: string) => {
    set({ loading: true });
    try {
      const res = await fetch('/api/saves/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_save_name: oldName, new_display_name: newDisplayName })
      });
      const data = await res.json();
      set({ loading: false });
      if (data.success) {
        get().fetchSaves();
      }
      return data;
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  deleteSave: async (saveName: string) => {
    set({ loading: true });
    try {
      const res = await fetch('/api/saves/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ save_name: saveName })
      });
      const data = await res.json();
      set({ loading: false });
      if (data.success) {
        get().fetchSaves();
      }
      return data;
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  }
}));
