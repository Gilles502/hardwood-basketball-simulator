// File: frontend/src/pages/Rotations.tsx
import React, { useState, useEffect } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { ExtensionsModal } from '../components/ExtensionsModal';
import { DashboardTabs } from '../components/DashboardTabs';
import { LineupTab } from './rotations/LineupTab';
import { MinutesTab } from './rotations/MinutesTab';
import { PlaybookTab } from './rotations/PlaybookTab';
import type { TacticalPlan } from './rotations/PlaybookTab';
import { OpponentTab } from './rotations/OpponentTab';
import { RolesTab } from './rotations/RolesTab';
import type { RoleChange } from './rotations/RolesTab';
import './dashboard/Dashboard.css'; // dash-header / dash-tabs, shared with the Dashboard
import './rotations/Rotations.css';
import {
  FileSignature,
  Save,
  Sliders,
  CheckCircle,
  AlertTriangle,
  Zap
} from 'lucide-react';

interface RosterPlayer {
  nome: string;
  ruolo: string;
  ovr: number;
  potenziale: number;
  eta: number;
  minuti_target: number;
  infortunato: boolean;
  giorni_infortunio_rimanenti: number;
  is_star: boolean;
  valutazioni_posizionali?: Record<string, number>;
  ruolo_originale?: string | null;
  ovr_if_role?: Record<string, number>;
}

interface CoachData {
  nome: string;
  stile_gioco: string;
  ovr_offensivo: number;
  ovr_difensivo: number;
  ovr_totale: number;
  eta: number;
  contratto_anni_rimanenti: number;
}

interface CoachStyle {
  name: string;
  descrizione: string;
}

// Older builds saved the full-court press as PRESS_FULL_COURT, which the engine never matched.
const normalizeScheme = (scheme: string | undefined): string =>
  !scheme ? 'MAN_TO_MAN' : scheme === 'PRESS_FULL_COURT' ? 'FULL_PRESS' : scheme;

export type RotationsTab = 'lineup' | 'minutes' | 'roles' | 'tactics' | 'opponent';

interface RotationsProps {
  initialTab?: RotationsTab;
}

export const Rotations: React.FC<RotationsProps> = ({ initialTab = 'lineup' }) => {
  const { fetchLeagueData, leagueData } = useLeagueStore();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<RotationsTab>(initialTab);
  // Unsaved changes on the Opponent tab (its plan is saved separately, per team)
  const [opponentDirty, setOpponentDirty] = useState(false);
  // Unsaved role changes on the Roles tab (saved on their own, right away)
  const [rolesDirty, setRolesDirty] = useState(false);

  // API Data States
  const [roster, setRoster] = useState<RosterPlayer[]>([]);
  const [coach, setCoach] = useState<CoachData | null>(null);
  const [coachStyles, setCoachStyles] = useState<CoachStyle[]>([]);
  const [customLineup, setCustomLineup] = useState<Record<string, string>>({});
  const [activePoe, setActivePoe] = useState<string>('Balanced Approach');
  const [teamIntesa, setTeamIntesa] = useState<number>(75);

  // Tactical Plan State
  const [tacticalPlan, setTacticalPlan] = useState<TacticalPlan>({
    pnr_coverage: 'DROP',
    defensive_scheme: 'MAN_TO_MAN',
    offensive_focus: 'BALANCED',
    pace_preference: 'BALANCED',
    stagger_stars: false,
    offensive_first_option: null,
    offensive_second_option: null,
    offensive_third_option: null,
    player_touch_modifiers: {}
  });

  // Form State
  const [minutes, setMinutes] = useState<Record<string, number>>({});

  // Modals Visibility
  const [showExtensionsModal, setShowExtensionsModal] = useState(false);

  const fetchTeamManagerInfo = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/team-manager/info?_t=${Date.now()}`);
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setRoster(data.roster || []);
        setCoach(data.coach || null);
        setCoachStyles(data.coach_styles || []);
        setCustomLineup(data.user_custom_lineup || data.custom_lineup || {});
        setActivePoe(data.active_poe || 'Balanced Approach');
        setTeamIntesa(data.intesa || 75);
        if (data.tactical_plan) {
          setTacticalPlan({
            pnr_coverage: data.tactical_plan.pnr_coverage || 'DROP',
            defensive_scheme: normalizeScheme(data.tactical_plan.defensive_scheme),
            offensive_focus: data.tactical_plan.offensive_focus || 'BALANCED',
            pace_preference: data.tactical_plan.pace_preference || 'BALANCED',
            stagger_stars: !!data.tactical_plan.stagger_stars,
            offensive_first_option: data.tactical_plan.offensive_first_option || null,
            offensive_second_option: data.tactical_plan.offensive_second_option || null,
            offensive_third_option: data.tactical_plan.offensive_third_option || null,
            player_touch_modifiers: data.tactical_plan.player_touch_modifiers || {}
          });
        }

        // Initialize minutes local state
        const initialMins: Record<string, number> = {};
        (data.roster || []).forEach((p: RosterPlayer) => {
          initialMins[p.nome] = p.minuti_target;
        });
        setMinutes(initialMins);
      }
    } catch (err) {
      setError('Failed to load team management data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeamManagerInfo();
  }, []);

  // Minute validation helper
  const totalHealthyMinutes = roster.reduce((sum, p) => {
    if (p.infortunato) return sum;
    return sum + (minutes[p.nome] || 0);
  }, 0);

  const isMinutesValid = totalHealthyMinutes === 240;

  // Preset Rotations: Playoff Heavy, Balanced 10-Man, Deep Bench
  const applyRotationPreset = (type: 'playoff' | 'balanced' | 'deep') => {
    const healthyRoster = [...roster].filter(p => !p.infortunato).sort((a, b) => b.ovr - a.ovr);
    const newMinutes: Record<string, number> = {};

    roster.forEach(p => { newMinutes[p.nome] = 0; });

    if (type === 'playoff') {
      // 8-Man Playoff Rotation (2 Stars @ 38m, 3 Starters @ 32m, 3 Bench @ 16m)
      if (healthyRoster.length >= 8) {
        newMinutes[healthyRoster[0].nome] = 38;
        newMinutes[healthyRoster[1].nome] = 38;
        newMinutes[healthyRoster[2].nome] = 32;
        newMinutes[healthyRoster[3].nome] = 32;
        newMinutes[healthyRoster[4].nome] = 32;
        newMinutes[healthyRoster[5].nome] = 24;
        newMinutes[healthyRoster[6].nome] = 24;
        newMinutes[healthyRoster[7].nome] = 20;
      }
    } else if (type === 'balanced') {
      // 10-Man Regular Season Rotation (Starters 32-34m, 5 Bench @ 14-16m)
      if (healthyRoster.length >= 10) {
        newMinutes[healthyRoster[0].nome] = 34;
        newMinutes[healthyRoster[1].nome] = 34;
        newMinutes[healthyRoster[2].nome] = 30;
        newMinutes[healthyRoster[3].nome] = 28;
        newMinutes[healthyRoster[4].nome] = 28;
        newMinutes[healthyRoster[5].nome] = 18;
        newMinutes[healthyRoster[6].nome] = 18;
        newMinutes[healthyRoster[7].nome] = 18;
        newMinutes[healthyRoster[8].nome] = 16;
        newMinutes[healthyRoster[9].nome] = 16;
      }
    } else {
      // 12-Man Deep Bench Rotation
      const count = Math.min(12, healthyRoster.length);
      const minsPer = Math.floor(240 / count);
      let rem = 240 - (minsPer * count);
      for (let i = 0; i < count; i++) {
        newMinutes[healthyRoster[i].nome] = minsPer + (rem > 0 ? 1 : 0);
        if (rem > 0) rem--;
      }
    }

    setMinutes(newMinutes);
    setSuccessMessage(`Rotation preset '${type.toUpperCase()}' applied! Remember to save.`);
    setTimeout(() => setSuccessMessage(null), 3500);
  };

  const handleSaveAllGamePlan = async () => {
    if (!isMinutesValid) return;
    setLoading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const response = await fetch('/api/team-manager/game-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          minutes: minutes,
          active_poe: activePoe,
          custom_lineup: customLineup,
          tactical_plan: tacticalPlan
        })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage('Gameplan, starting lineup, and rotations saved successfully!');
        fetchTeamManagerInfo();
        fetchLeagueData();
        setTimeout(() => setSuccessMessage(null), 4000);
      }
    } catch (err) {
      setError('Unable to save to server.');
    } finally {
      setLoading(false);
    }
  };

  const handleAutoRotate = async () => {
    setLoading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const response = await fetch('/api/team-manager/auto-rotate', { method: 'POST' });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage('Auto-rotations applied successfully!');
        setMinutes(data.rotations || {});
        fetchTeamManagerInfo();
        setTimeout(() => setSuccessMessage(null), 4000);
      }
    } catch (err) {
      setError('Communication error during auto-rotation.');
    } finally {
      setLoading(false);
    }
  };

  const handleCoachStyleChange = async (styleName: string) => {
    setLoading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const response = await fetch('/api/team-manager/change-coach-style', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stile_gioco: styleName })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setSuccessMessage(data.message);
        // Update locally instead of refetching, so unsaved lineup/minutes/playbook edits survive
        setCoach((c) => (c ? { ...c, stile_gioco: styleName } : c));
        setTimeout(() => setSuccessMessage(null), 4000);
      }
    } catch (err) {
      setError('Error updating coaching style.');
    } finally {
      setLoading(false);
    }
  };

  const handleAutoSetLineup = () => {
    const autoLineup: Record<string, string> = {};
    const used: string[] = [];
    ['PG', 'SG', 'SF', 'PF', 'C'].forEach((role) => {
      const candidates = roster.filter(p => !p.infortunato && !used.includes(p.nome));
      const best = candidates.sort((a, b) => {
        const valA = (a.valutazioni_posizionali?.[role] || a.ovr);
        const valB = (b.valutazioni_posizionali?.[role] || b.ovr);
        return valB - valA;
      })[0];
      if (best) {
        autoLineup[role] = best.nome;
        used.push(best.nome);
      }
    });
    setCustomLineup(autoLineup);
    setSuccessMessage('Optimized positional starting lineup applied!');
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  if (!leagueData?.player_team_name) {
    return (
      <div>
        <div className="top-status-bar">
          <div>
            <h1 style={{ fontSize: '28px', margin: 0, fontWeight: 700 }}>Tactics & Rotations Management</h1>
            <span style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Configure lineups, chemistry, minutes allocation & defensive matchups</span>
          </div>
        </div>
        <div className="card" style={{ padding: '40px', textAlign: 'center', background: 'rgba(255,184,0,0.02)', border: '1px solid rgba(255,184,0,0.15)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', margin: '20px 0' }}>
          <Sliders size={48} style={{ color: 'var(--primary)' }} />
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800 }}>Spectator Mode</h3>
          <p style={{ color: 'var(--text-secondary)', maxWidth: '500px', margin: 0, fontSize: '14px', lineHeight: '1.6' }}>
            No franchise selected. In Spectator Mode, rotations and lineups are autonomously managed by their respective CPU coaching staffs.
          </p>
        </div>
      </div>
    );
  }

  if (loading && roster.length === 0) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  return (
    <div>
      {/* Top Header */}
      <div className="dash-header">
        <div>
          <h1 className="dash-title">Tactical Board</h1>
          <span className="dash-subtitle">
            {leagueData.player_team_name} · Team chemistry <strong style={{ color: 'var(--success)' }}>{teamIntesa}%</strong>
            {coach && ` · Coach ${coach.nome}`}
            {coach && activeTab === 'tactics' && coachStyles.length > 0 && (
              <>
                {' · Philosophy'}
                <select
                  className="rot-philo"
                  value={coach.stile_gioco}
                  onChange={(e) => handleCoachStyleChange(e.target.value)}
                  disabled={loading}
                  aria-label="Coaching philosophy"
                  title={coachStyles.find((s) => s.name === coach.stile_gioco)?.descrizione}
                >
                  {coachStyles.map((style) => (
                    <option key={style.name} value={style.name}>{style.name}</option>
                  ))}
                </select>
              </>
            )}
          </span>
        </div>
        <div className="dash-badges">
          {activeTab === 'lineup' && (
            <button className="btn btn-secondary" onClick={handleAutoSetLineup}>
              <Zap size={16} /> Auto-pick best five
            </button>
          )}
          <button className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => setShowExtensionsModal(true)}>
            <FileSignature size={16} /> Contract Extensions
          </button>
          {activeTab !== 'opponent' && activeTab !== 'roles' && <button
            className="btn btn-primary"
            disabled={!isMinutesValid || loading}
            onClick={handleSaveAllGamePlan}
            title={isMinutesValid ? undefined : `Minutes add up to ${totalHealthyMinutes}, not 240. Fix them in the Minutes tab.`}
          >
            <Save size={16} style={{ marginRight: '6px' }} /> Save Gameplan
          </button>}
        </div>
      </div>

      {/* Sub tabs */}
      <DashboardTabs
        idPrefix="rot"
        ariaLabel="Tactical board sections"
        active={activeTab}
        onChange={(id) => {
          if (activeTab === 'opponent' && opponentDirty && !window.confirm('Leave without saving your opponent plan?')) return;
          if (activeTab === 'opponent') setOpponentDirty(false);
          if (activeTab === 'roles' && rolesDirty && !window.confirm('Leave without saving your role changes?')) return;
          if (activeTab === 'roles') setRolesDirty(false);
          setActiveTab(id as RotationsTab);
        }}
        tabs={[
          { id: 'lineup', label: 'Lineup' },
          { id: 'minutes', label: 'Minutes' },
          { id: 'roles', label: 'Roles' },
          { id: 'tactics', label: 'Playbook' },
          { id: 'opponent', label: 'Opponent' },
        ]}
      />

      {/* Alerts */}
      {successMessage && (
        <div className="card" style={{ borderColor: '#10b981', color: '#10b981', padding: '12px 20px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CheckCircle size={18} /> {successMessage}
        </div>
      )}
      {error && (
        <div className="card" style={{ borderColor: '#ef4444', color: '#ef4444', padding: '12px 20px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertTriangle size={18} /> {error}
        </div>
      )}

      {/* TAB 1: LINEUP (lineup card + bench card) */}
      {activeTab === 'lineup' && (
        <div role="tabpanel" id="rot-panel-lineup" aria-labelledby="rot-tab-lineup">
          <LineupTab
            roster={roster}
            customLineup={customLineup}
            minutes={minutes}
            onLineupChange={setCustomLineup}
          />
        </div>
      )}

      {/* TAB 2: MINUTES (minutes sheet) */}
      {activeTab === 'minutes' && (
        <div role="tabpanel" id="rot-panel-minutes" aria-labelledby="rot-tab-minutes">
          <MinutesTab
            roster={roster}
            customLineup={customLineup}
            minutes={minutes}
            onMinutesChange={setMinutes}
            onPreset={applyRotationPreset}
            onAutoCoach={handleAutoRotate}
          />
        </div>
      )}

      {/* TAB: ROLES (move a player to the role he really plays) */}
      {activeTab === 'roles' && (
        <div role="tabpanel" id="rot-panel-roles" aria-labelledby="rot-tab-roles">
          <RolesTab
            roster={roster}
            onDirtyChange={setRolesDirty}
            onSaved={(changed: RoleChange[]) => {
              // Merge locally: a refetch would drop unsaved lineup / minutes / playbook edits
              const byName = new Map(changed.map((c) => [c.nome, c]));
              setRoster((cur) => cur.map((p) => {
                const c = byName.get(p.nome);
                return c ? { ...p, ruolo: c.ruolo, ovr: c.ovr, potenziale: c.potenziale, ruolo_originale: c.ruolo_originale,
                             valutazioni_posizionali: c.valutazioni_posizionali, ovr_if_role: c.ovr_if_role } : p;
              }));
              setSuccessMessage(changed.length ? `Roles saved: ${changed.map((c) => `${c.nome} ${c.ruolo}`).join(', ')}.` : 'No role changed.');
              fetchLeagueData();
              setTimeout(() => setSuccessMessage(null), 4000);
            }}
          />
        </div>
      )}

      {/* TAB 3: PLAYBOOK (binder) */}
      {activeTab === 'tactics' && (
        <div role="tabpanel" id="rot-panel-tactics" aria-labelledby="rot-tab-tactics">
          <PlaybookTab
            roster={roster}
            customLineup={customLineup}
            minutes={minutes}
            plan={tacticalPlan}
            onPlanChange={setTacticalPlan}
          />
        </div>
      )}

      {/* TAB 4: OPPONENT (scouting report + per-team matchups) */}
      {activeTab === 'opponent' && (
        <div role="tabpanel" id="rot-panel-opponent" aria-labelledby="rot-tab-opponent">
          <OpponentTab onDirtyChange={setOpponentDirty} />
        </div>
      )}

      {/* Contract Extensions Modal Popup */}
      {showExtensionsModal && (
        <ExtensionsModal
          onClose={() => setShowExtensionsModal(false)}
          onSuccess={() => {
            fetchTeamManagerInfo();
          }}
        />
      )}
    </div>
  );
};
