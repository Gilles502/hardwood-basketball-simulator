import React, { useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { Trophy, Play, FastForward, Building, Briefcase, Target, SkipForward, Tv, Square } from 'lucide-react';
import { FrontOfficeSummitModal } from '../../components/FrontOfficeSummitModal';
import { TodayGamesHubModal } from '../../components/TodayGamesHubModal';
import { PHASES } from '../../utils/endSeason';
import type { SimTarget } from '../../utils/simRun';
import './Dashboard.css';

/** Phase-aware simulation controls: the one place where the season is advanced from the Dashboard. */
interface SimulationCardProps {
  /** Opens the End of Season Hub, the only place that advances the offseason. */
  onOpenHub: () => void;
}

export const SimulationCard: React.FC<SimulationCardProps> = ({ onOpenHub }) => {
  const {
    leagueData,
    simulating,
    fetchLeagueData,
    fetchLeagueDataSilent,
    simRun,
    startSimRun,
    stopSimRun,
    simulatePlayoffsTurno,
  } = useLeagueStore();
  const runGoing = !!simRun && simRun.error === null;

  const [actionLoading, setActionLoading] = useState(false);
  const [simSeasons, setSimSeasons] = useState<number>(1);
  const [milestone, setMilestone] = useState<SimTarget['kind'] | null>(null);

  const [showSummitModal, setShowSummitModal] = useState(false);

  // Stato per Matchday Hub (simulazione singole partite odierne)
  const [todayGamesData, setTodayGamesData] = useState<{ dayIndex: number; dateStr: string; games: any[] } | null>(null);
  const [showMatchdayHub, setShowMatchdayHub] = useState<boolean>(false);

  const handleOpenMatchdayHub = async () => {
    try {
      const res = await fetch('/api/calendar/today');
      const data = await res.json();
      if (data && data.day) {
        setTodayGamesData({
          dayIndex: data.current_day,
          dateStr: data.day.date,
          games: data.day.games || []
        });
        setShowMatchdayHub(true);
      }
    } catch (err) {
      console.error('Error opening matchday hub:', err);
    }
  };

  const handleSimulateEntireSeason = async () => {
    setActionLoading(true);
    useLeagueStore.setState({ simulating: true });
    try {
      const response = await fetch('/api/simulate_entire_season', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ num_seasons: simSeasons })
      });
      const data = await response.json();
      if (!data.error) {
        useLeagueStore.setState({ leagueData: data });
      }
    } catch (err) {
      console.error(err);
    } finally {
      setActionLoading(false);
      useLeagueStore.setState({ simulating: false });
    }
  };

  if (!leagueData) return null;

  const { league_state, player_team_name, playoffs } = leagueData;
  const currentDay = leagueData.current_day || 0;
  const totalDays = leagueData.total_calendar_days || 176;

  // Regular-season deck: every button starts the same live run (store startSimRun) with its own target.
  const milestones = leagueData.sim_milestones;
  const milestoneOptions: { kind: SimTarget['kind']; label: string }[] = [];
  if (milestones && milestones.trade_deadline_day !== null && !milestones.trade_deadline_done
      && currentDay < milestones.trade_deadline_day) {
    milestoneOptions.push({ kind: 'deadline', label: 'Trade deadline' });
  }
  if (league_state === 'PRE_SEASON' && milestones && milestones.all_star_day !== null) {
    milestoneOptions.push({ kind: 'all_star', label: 'All-Star break' });
  }
  milestoneOptions.push({ kind: 'season_end', label: 'End of regular season' });
  const chosenMilestone = milestoneOptions.find((o) => o.kind === milestone) ?? milestoneOptions[0];
  const seasonDone = currentDay >= totalDays;

  const renderRegularSeasonDeck = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', width: '100%' }}>
      <div className="flex-between" style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>
        <span>Day {Math.min(currentDay + 1, totalDays)} of {totalDays}</span>
        <span>{Math.round((currentDay / totalDays) * 100)}% of season played</span>
      </div>
      <div style={{ height: '6px', background: 'rgba(255,255,255,0.06)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ width: `${(currentDay / totalDays) * 100}%`, height: '100%', background: 'linear-gradient(90deg, #ff6a1a, #ff8a4a)', transition: 'width 0.4s ease' }} />
      </div>
      {runGoing ? (
        <div className="flex-between" style={{ gap: '12px', padding: '10px 12px', borderRadius: '8px', background: 'rgba(255, 106, 26, 0.08)', border: '1px solid rgba(255, 106, 26, 0.35)' }}>
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {simRun?.stopRequested ? 'Stopping after this day…' : 'Simulating…'} <b style={{ color: 'var(--text-primary)' }}>{simRun?.label}</b>
          </span>
          <button className="btn btn-secondary" onClick={stopSimRun} disabled={simRun?.stopRequested}>
            <Square size={14} style={{ marginRight: '6px' }} /> Stop
          </button>
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: player_team_name ? 'repeat(3, 1fr)' : 'repeat(2, 1fr)', gap: '10px' }}>
            <button className="btn btn-secondary" onClick={() => startSimRun({ kind: 'days', count: 1 })} disabled={seasonDone}>
              <Play size={16} style={{ marginRight: '6px' }} /> Sim Day
            </button>
            <button className="btn btn-secondary" onClick={() => startSimRun({ kind: 'days', count: 7 })} disabled={seasonDone}>
              <FastForward size={16} style={{ marginRight: '6px' }} /> Sim 7 Days
            </button>
            {player_team_name && (
              <button className="btn btn-secondary" onClick={() => startSimRun({ kind: 'next_game' })} disabled={seasonDone}>
                <Target size={16} style={{ marginRight: '6px' }} /> Next Game
              </button>
            )}
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, whiteSpace: 'nowrap' }}>Sim until</span>
            <select
              value={chosenMilestone.kind}
              onChange={(e) => setMilestone(e.target.value as SimTarget['kind'])}
              style={{ flex: 1, backgroundColor: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border)', padding: '8px 12px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, cursor: 'pointer', outline: 'none', height: '38px' }}
            >
              {milestoneOptions.map((o) => <option key={o.kind} value={o.kind}>{o.label}</option>)}
            </select>
            <button className="btn btn-primary" onClick={() => startSimRun({ kind: chosenMilestone.kind } as SimTarget)} disabled={seasonDone}>
              <SkipForward size={18} style={{ marginRight: '6px' }} /> Start
            </button>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Pick a date in the Calendar to stop on a specific day.</span>
        </>
      )}
      <button
        className="btn btn-secondary"
        onClick={handleOpenMatchdayHub}
        disabled={seasonDone || runGoing}
        title={runGoing ? 'Stop the simulation first' : undefined}
        style={{
          background: 'rgba(255, 106, 26, 0.08)',
          border: '1px solid rgba(255, 106, 26, 0.35)',
          color: 'var(--primary-hover)',
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px'
        }}
      >
        <Tv size={16} /> Gameday Hub (Daily Games)
      </button>
    </div>
  );

  const renderSimControls = () => {
    if (simulating) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', padding: '16px 0' }}>
          <div className="spinner"></div>
          <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Simulation in progress...</span>
        </div>
      );
    }

    // The offseason is driven only from the End of Season Hub; here we just point there.
    const endSeason = leagueData.end_season;
    if (endSeason?.open && endSeason.phase !== null) {
      return (
        <div className="sim-controls" style={{ flexDirection: 'column', gap: '10px' }}>
          <div style={{ padding: '8px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center' }}>
            Offseason · {PHASES[endSeason.phase]}
          </div>
          <button className="btn btn-primary" onClick={onOpenHub}>
            <Play size={18} style={{ marginRight: '6px' }} />
            {league_state === 'PLAYOFFS_END' ? 'Enter the End of Season Hub' : 'Open End of Season Hub'}
          </button>
        </div>
      );
    }
    switch (league_state) {
      case 'PRE_SEASON':
        return (
          <div className="sim-controls" style={{ flexDirection: 'column', gap: '12px' }}>
            {player_team_name && (
              <div style={{
                background: 'linear-gradient(90deg, rgba(255, 106, 26, 0.12) 0%, rgba(20, 24, 36, 0.7) 100%)',
                border: '1px solid rgba(255, 106, 26, 0.35)',
                borderRadius: '10px',
                padding: '12px 18px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                width: '100%',
                boxSizing: 'border-box',
                gap: '16px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    background: 'rgba(255, 106, 26, 0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    border: '1px solid rgba(255, 106, 26, 0.3)'
                  }}>
                    <Building size={18} style={{ color: '#ff6a1a' }} />
                  </div>
                  <div>
                    <strong style={{ fontSize: '13px', color: '#f5ede1', display: 'block' }}>
                      {leagueData?.user_role === 'only_coach' ? 'Pre-Season Meeting with General Manager' : 'Franchise Strategic Summit (GM & Coach)'}
                    </strong>
                    <span style={{ fontSize: '11px', color: '#c9a27a' }}>
                      {leagueData?.user_role === 'only_coach' 
                        ? 'Align or discuss seasonal strategy and trade objectives with front office.' 
                        : 'Define seasonal objectives and front office expectations.'}
                    </span>
                  </div>
                </div>
                <button 
                  className="btn btn-secondary" 
                  onClick={() => setShowSummitModal(true)}
                  style={{ fontSize: '12px', padding: '7px 16px', borderColor: '#ff6a1a', color: '#ff6a1a', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Briefcase size={14} />
                  {leagueData?.user_role === 'only_coach' ? 'Meet the GM' : 'Executive Summit'}
                </button>
              </div>
            )}
            {renderRegularSeasonDeck()}
          </div>
        );
      case 'ALL_STAR_BREAK':
        return (
          <div className="sim-controls" style={{ flexDirection: 'column', gap: '12px' }}>
            <div style={{ padding: '8px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center', width: '100%', boxSizing: 'border-box' }}>
              All-Star Break. Visit the All-Star Weekend tab, then continue day by day or finish the regular season.
            </div>
            {renderRegularSeasonDeck()}
          </div>
        );
      case 'REGULAR_SEASON_END':
        return (
          <div className="sim-controls">
            <div style={{ padding: '8px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px', textAlign: 'center' }}>
              The Regular Season has finished. Advance to the postseason and Playoffs.
            </div>
            <button className="btn btn-primary" onClick={() => simulatePlayoffsTurno()}>
              <Trophy size={18} style={{ marginRight: '6px' }} /> Enter the Playoffs
            </button>
          </div>
        );
      case 'PLAYOFFS':
      case 'PLAYOFFS_IN_PROGRESS':
        {
          const isPlayinActive = (leagueData?.enable_play_in !== false) && (
            playoffs?.bracket?.next_turn === 'PLAY_IN' || 
            (league_state === 'PLAYOFFS_IN_PROGRESS' && playoffs && (!playoffs.bracket.east.qf || playoffs.bracket.east.qf.length === 0))
          );
          if (isPlayinActive) {
            return (
              <div className="sim-controls" style={{ flexDirection: 'column', gap: '12px' }}>
                <div style={{ padding: '8px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px', textAlign: 'center' }}>
                  The Play-In Tournament is underway. Simulate individual matchups or advance the entire tournament. Visit the Playoffs tab to view brackets and game box scores.
                </div>
                <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
                  <button className="btn btn-primary" onClick={() => simulatePlayoffsTurno()}>
                    <Trophy size={18} style={{ marginRight: '6px' }} /> Simulate Play-In Game
                  </button>
                  <button className="btn btn-secondary" onClick={async () => {
                    setActionLoading(true);
                    try {
                      await fetch('/api/simula_playoff_turno', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ bulk: true })
                      });
                      fetchLeagueData();
                    } catch (e) {
                      console.error(e);
                    } finally {
                      setActionLoading(false);
                    }
                  }} disabled={actionLoading}>
                    {actionLoading ? 'Simulation in progress...' : 'Simulate Entire Play-In'}
                  </button>
                </div>
              </div>
            );
          }
          return (
            <div className="sim-controls">
              <button className="btn btn-primary" onClick={() => simulatePlayoffsTurno()}>
                <Trophy size={18} style={{ marginRight: '6px' }} /> Simulate Playoff Round
              </button>
            </div>
          );
        }
      default:
        return null;
    }
  };

  return (
    <>
        <div className="card dash-sim-card">
          <h3 className="card-title">
            <Play size={20} className="logo-gold" />
            Simulation Control Deck
          </h3>
          {renderSimControls()}
          {/* Multi-season sim only before the season starts: gone from the first simulated day. */}
          {!simulating && !simRun && league_state === 'PRE_SEASON' && currentDay === 0 && (
            <div style={{ marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '16px', display: 'flex', gap: '12px', alignItems: 'center' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Duration
                </span>
                <select
                  value={simSeasons}
                  onChange={(e) => setSimSeasons(Number(e.target.value))}
                  style={{
                    backgroundColor: 'var(--bg-card)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border)',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    width: '135px',
                    outline: 'none',
                    height: '38px'
                  }}
                >
                  <option value={1}>1 Season</option>
                  <option value={3}>3 Seasons</option>
                  <option value={5}>5 Seasons</option>
                  <option value={10}>10 Seasons</option>
                  <option value={15}>15 Seasons</option>
                  <option value={20}>20 Seasons</option>
                  <option value={25}>25 Seasons</option>
                  <option value={30}>30 Seasons</option>
                  <option value={40}>40 Seasons</option>
                  <option value={50}>50 Seasons</option>
                </select>
              </div>

              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Fast Multi-Season Sim
                </span>
                <button 
                  className="btn btn-secondary" 
                  onClick={handleSimulateEntireSeason} 
                  disabled={actionLoading}
                  style={{
                    width: '100%',
                    background: 'linear-gradient(135deg, rgba(255,184,0,0.05) 0%, rgba(255,255,255,0.02) 100%)',
                    border: '1px solid rgba(255,184,0,0.2)',
                    color: 'var(--primary)',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    padding: '10px 16px',
                    height: '38px',
                    borderRadius: '8px'
                  }}
                >
                  <FastForward size={16} /> Simulate {simSeasons} {simSeasons === 1 ? 'Season' : 'Seasons'}
                </button>
              </div>
            </div>
          )}
        </div>

      {/* Pre-Season Front Office Summit Modal */}
      <FrontOfficeSummitModal
        isOpen={showSummitModal}
        onClose={() => setShowSummitModal(false)}
      />

      {/* Matchday Live Hub Modal Popup */}
      {showMatchdayHub && todayGamesData && (
        <TodayGamesHubModal
          isOpen={showMatchdayHub}
          onClose={() => setShowMatchdayHub(false)}
          dayIndex={todayGamesData.dayIndex}
          dateStr={todayGamesData.dateStr}
          games={todayGamesData.games}
          onRefreshCalendar={async () => {
            await fetchLeagueDataSilent();
            try {
              const res = await fetch('/api/calendar/today');
              const data = await res.json();
              if (data && data.day) {
                setTodayGamesData({
                  dayIndex: data.current_day,
                  dateStr: data.day.date,
                  games: data.day.games || []
                });
              }
            } catch (err) {
              console.error(err);
            }
          }}
        />
      )}
    </>
  );
};
