// File: frontend/src/pages/Playoffs.tsx
import React, { useState, useEffect } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { Trophy } from 'lucide-react';
import { CourtsideLive, type LiveGame } from '../components/CourtsideLive';
import { ResultSheet } from '../components/ResultSheet';
import type { SeriesLog } from '../utils/resultSheet';
import { DashboardTabs } from '../components/DashboardTabs';
import { BracketTab, ROUND_LABELS } from './playoffs/BracketTab';
import { CourtsideTab } from './playoffs/CourtsideTab';
import { latestResults, nextPlayInGame, playoffNight, seedsFromBracket } from '../utils/playoffNight';
import type { NightGame } from '../utils/playoffNight';
import './dashboard/Dashboard.css'; // dash-header / dash-tabs, shared with the Dashboard
import './playoffs/Playoffs.css';

type PlayoffTab = 'playin' | 'bracket' | 'live';

interface PlayoffsProps {
  /** Opens the Tactical Board on the Opponent tab to set matchups for the series. */
  onOpenGameplan: () => void;
  /** Opens the End of Season Hub once the Finals are over. */
  onOpenHub: () => void;
}

export const Playoffs: React.FC<PlayoffsProps> = ({ onOpenGameplan, onOpenHub }) => {
  const { leagueData, simulating } = useLeagueStore();
  const [activeTab, setActiveTab] = useState<PlayoffTab>('bracket');
  
  const [playinData, setPlayinData] = useState<any>(null);
  const [watching, setWatching] = useState(false);
  const [loadingPlayin, setLoadingPlayin] = useState(false);
  const [simulatingPlayin, setSimulatingPlayin] = useState(false);

  const [openSeries, setOpenSeries] = useState<{ series: SeriesLog; label: string; winsNeeded: number } | null>(null);

  const [liveGame, setLiveGame] = useState<LiveGame | null>(null);

  const fetchPlayinData = async () => {
    setLoadingPlayin(true);
    try {
      const response = await fetch(`/api/playin?_t=${Date.now()}`);
      if (!response.ok) {
        setPlayinData(null);
        return;
      }
      const data = await response.json();
      if (!data.error) {
        setPlayinData(data);
      }
    } catch (err) {
      console.error('Errore nel recupero dati playin:', err);
    } finally {
      setLoadingPlayin(false);
    }
  };

  // Jump to the Play-In tab when it starts and back to the bracket when it ends; only on that change,
  // so refreshed league data never pulls the user off the tab they picked.
  const playInOff = leagueData?.enable_play_in === false;
  const playInPhase = !playInOff && leagueData?.league_state === 'PLAYOFFS_IN_PROGRESS' && leagueData?.playoffs?.bracket?.next_turn === 'PLAY_IN';
  useEffect(() => {
    setActiveTab((tab) => (playInPhase ? 'playin' : tab === 'playin' && playInOff ? 'bracket' : tab));
  }, [playInPhase, playInOff]);

  useEffect(() => {
    if (leagueData?.enable_play_in !== false && (leagueData?.league_state === 'PLAYOFFS_IN_PROGRESS' || leagueData?.league_state === 'PLAYOFFS_END' || leagueData?.playoffs)) {
      fetchPlayinData();
    }
  }, [leagueData]);

  /** Plays the next night (or the next play-in game) and opens the chosen game in Courtside Live. */
  const handleWatch = async (game: NightGame) => {
    setWatching(true);
    try {
      const response = await fetch(game.isPlayIn ? '/api/simula_playin_game' : '/api/simula_playoff_turno', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(game.isPlayIn ? { watch_series_id: game.s1 } : { bulk: false, watch_series_id: game.s1 }),
      });
      const data = await response.json();
      const watchData = data.watch_game;
      if (watchData) {
        setLiveGame({
          home: watchData.home_team || game.home,
          away: watchData.away_team || game.away,
          label: game.isPlayIn ? game.label : `${game.label} · Game ${game.gameNum}`,
          plays: watchData.play_log || [],
        });
      }
      await useLeagueStore.getState().fetchLeagueDataSilent();
      await fetchPlayinData();
    } catch (err) {
      console.error('Error simulating the live game:', err);
    } finally {
      setWatching(false);
    }
  };

  const [simulatingBracket, setSimulatingBracket] = useState(false);

  const handleSimulatePlayoffs = async (bulk: boolean) => {
    setSimulatingBracket(true);
    try {
      const response = await fetch('/api/simula_playoff_turno', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bulk })
      });
      await response.json();
      await useLeagueStore.getState().fetchLeagueDataSilent();
      await fetchPlayinData();
    } catch (err) {
      console.error(err);
    } finally {
      setSimulatingBracket(false);
    }
  };

  const handleSimulatePlayinGame = async () => {
    setSimulatingPlayin(true);
    try {
      const response = await fetch('/api/simula_playin_game', { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        await fetchPlayinData();
        await useLeagueStore.getState().fetchLeagueDataSilent();
      } else {
        alert(data.error || 'Error simulating Play-In game');
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSimulatingPlayin(false);
    }
  };

  const handleSimulatePlayinBulk = async () => {
    setSimulatingPlayin(true);
    try {
      const response = await fetch('/api/simula_playoff_turno', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bulk: true })
      });
      await response.json();
      await fetchPlayinData();
      await useLeagueStore.getState().fetchLeagueDataSilent();
    } catch (err) {
      console.error(err);
    } finally {
      setSimulatingPlayin(false);
    }
  };

  const openResultSheet = (series: SeriesLog | null, label: string, winsNeeded: number) => {
    if (!series?.games?.length) return;
    setOpenSeries({ series, label, winsNeeded });
  };

  const getPlayinGameScore = (seriesLog: any, teamName: string) => {
    if (!seriesLog || !seriesLog.games || seriesLog.games.length === 0) return '-';
    const game = seriesLog.games[0];
    if (game.squadra_casa.nome === teamName) return game.squadra_casa.punteggio;
    if (game.squadra_ospite.nome === teamName) return game.squadra_ospite.punteggio;
    return '-';
  };

  const renderPlayinConferenceBracket = (confData: any, conf: 'east' | 'west') => {
    if (!confData || !confData.play_in_teams || confData.play_in_teams.length < 4) {
      return <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '20px' }}>No teams configured for Play-In.</div>;
    }

    const teams = confData.play_in_teams;
    const results = confData.results || {};
    
    const g1 = results.game1 || {};
    const g2 = results.game2 || {};
    const g3 = results.game3 || {};
    
    const g3Team1 = g1.loser || 'Game 1 Loser';
    const g3Team2 = g2.winner || 'Game 2 Winner';

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Game 1 */}
        <div 
          className="card" 
          style={{
            padding: '16px', 
            cursor: g1.winner ? 'pointer' : 'default',
            background: g1.winner ? 'rgba(255, 184, 0, 0.03)' : 'var(--bg-card)',
            border: g1.winner ? '1px solid var(--primary)' : '1px solid var(--border)',
            borderRadius: '10px'
          }}
          onClick={() => g1.winner && openResultSheet(confData.games[0], `${conf === 'east' ? 'East' : 'West'} play-in · 7 vs 8`, 1)}
        >
          <div style={{ fontSize: '11px', color: 'var(--primary)', marginBottom: '8px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            GAME 1: 7 vs 8 (Winner earns #7 Seed)
          </div>
          <div className="flex-between" style={{ padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
            <span style={{ fontWeight: g1.winner === teams[0] ? 800 : 500, color: g1.winner === teams[0] ? 'var(--primary)' : 'inherit' }}>
              (7) {teams[0]}
            </span>
            <span style={{ fontWeight: 800, fontSize: '15px' }}>
              {g1.winner ? getPlayinGameScore(confData.games[0], teams[0]) : '-'}
            </span>
          </div>
          <div className="flex-between" style={{ padding: '6px 0' }}>
            <span style={{ fontWeight: g1.winner === teams[1] ? 800 : 500, color: g1.winner === teams[1] ? 'var(--primary)' : 'inherit' }}>
              (8) {teams[1]}
            </span>
            <span style={{ fontWeight: 800, fontSize: '15px' }}>
              {g1.winner ? getPlayinGameScore(confData.games[0], teams[1]) : '-'}
            </span>
          </div>
          {g1.winner && (
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '8px', textAlign: 'center', borderTop: '1px dashed var(--border)', paddingTop: '6px' }}>
              Winner: <strong>{g1.winner}</strong> (#7 Seed) • Click for Box Score
            </div>
          )}
        </div>

        {/* Game 2 */}
        <div 
          className="card" 
          style={{
            padding: '16px', 
            cursor: g2.winner ? 'pointer' : 'default',
            background: g2.winner ? 'rgba(255, 184, 0, 0.03)' : 'var(--bg-card)',
            border: g2.winner ? '1px solid var(--primary)' : '1px solid var(--border)',
            borderRadius: '10px'
          }}
          onClick={() => g2.winner && openResultSheet(confData.games[1], `${conf === 'east' ? 'East' : 'West'} play-in · 9 vs 10`, 1)}
        >
          <div style={{ fontSize: '11px', color: 'var(--primary)', marginBottom: '8px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            GAME 2: 9 vs 10 (Loser is eliminated)
          </div>
          <div className="flex-between" style={{ padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
            <span style={{ fontWeight: g2.winner === teams[2] ? 800 : 500, color: g2.winner === teams[2] ? 'var(--primary)' : 'inherit' }}>
              (9) {teams[2]}
            </span>
            <span style={{ fontWeight: 800, fontSize: '15px' }}>
              {g2.winner ? getPlayinGameScore(confData.games[1], teams[2]) : '-'}
            </span>
          </div>
          <div className="flex-between" style={{ padding: '6px 0' }}>
            <span style={{ fontWeight: g2.winner === teams[3] ? 800 : 500, color: g2.winner === teams[3] ? 'var(--primary)' : 'inherit' }}>
              (10) {teams[3]}
            </span>
            <span style={{ fontWeight: 800, fontSize: '15px' }}>
              {g2.winner ? getPlayinGameScore(confData.games[1], teams[3]) : '-'}
            </span>
          </div>
          {g2.winner && (
            <div style={{ fontSize: '10px', color: '#ef4444', marginTop: '8px', textAlign: 'center', borderTop: '1px dashed var(--border)', paddingTop: '6px' }}>
              Eliminated: <strong>{g2.loser}</strong> • Click for Box Score
            </div>
          )}
        </div>

        {/* Game 3 */}
        <div 
          className="card" 
          style={{
            padding: '16px', 
            cursor: g3.winner ? 'pointer' : 'default',
            background: g3.winner ? 'rgba(255, 184, 0, 0.03)' : 'var(--bg-card)',
            border: g3.winner ? '1px solid var(--primary)' : '1px solid var(--border)',
            opacity: g1.winner && g2.winner ? 1 : 0.5,
            borderRadius: '10px'
          }}
          onClick={() => g3.winner && openResultSheet(confData.games[2], `${conf === 'east' ? 'East' : 'West'} play-in · final`, 1)}
        >
          <div style={{ fontSize: '11px', color: 'var(--primary)', marginBottom: '8px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            GAME 3: Game 1 Loser vs Game 2 Winner (#8 Seed)
          </div>
          <div className="flex-between" style={{ padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
            <span style={{ fontWeight: g3.winner === g3Team1 ? 800 : 500, color: g3.winner === g3Team1 ? 'var(--primary)' : 'inherit' }}>
              {g3Team1}
            </span>
            <span style={{ fontWeight: 800, fontSize: '15px' }}>
              {g3.winner ? getPlayinGameScore(confData.games[2], g3Team1) : '-'}
            </span>
          </div>
          <div className="flex-between" style={{ padding: '6px 0' }}>
            <span style={{ fontWeight: g3.winner === g3Team2 ? 800 : 500, color: g3.winner === g3Team2 ? 'var(--primary)' : 'inherit' }}>
              {g3Team2}
            </span>
            <span style={{ fontWeight: 800, fontSize: '15px' }}>
              {g3.winner ? getPlayinGameScore(confData.games[2], g3Team2) : '-'}
            </span>
          </div>
          {g3.winner && (
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '8px', textAlign: 'center', borderTop: '1px dashed var(--border)', paddingTop: '6px' }}>
              Winner: <strong>{g3.winner}</strong> (#8 Seed) • Click for Box Score
            </div>
          )}
        </div>
      </div>
    );
  };

  if (!leagueData) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  const { playoffs } = leagueData;
  const year = leagueData.anno_corrente;
  const playoffYear = year ? year + 1 : null;
  const inProgress = leagueData.league_state === 'PLAYOFFS' || leagueData.league_state === 'PLAYOFFS_IN_PROGRESS';
  const liveRound = inProgress ? playoffs?.bracket?.next_turn ?? null : null;
  const seriesLeft = playoffs
    ? 15 - [...playoffs.bracket.east.qf, ...playoffs.bracket.east.sf, ...playoffs.bracket.east.cf,
        ...playoffs.bracket.west.qf, ...playoffs.bracket.west.sf, ...playoffs.bracket.west.cf,
        ...(playoffs.bracket.finals ?? [])].filter((s) => s?.winner_nome).length
    : null;
  const subtitle = !playoffs
    ? 'Bracket, Play-In and Courtside Live'
    : playoffs.campione
      ? `${playoffs.campione} are the champions`
      : liveRound === 'PLAY_IN'
        ? 'Play-In Tournament'
        : `${ROUND_LABELS[liveRound ?? ''] ?? 'Playoffs'} · ${seriesLeft} series left`;

  const playInGame = liveRound === 'PLAY_IN' ? nextPlayInGame(playinData) : null;
  const night = playInGame
    ? { games: [playInGame], idle: [] }
    : playoffs && liveRound ? playoffNight(playoffs.bracket, liveRound) : { games: [], idle: [] };

  return (
    <div>
      <div className="dash-header">
        <div>
          <h1 className="dash-title">Playoffs{playoffYear ? ` ${playoffYear}` : ''}</h1>
          <span className="dash-subtitle">{subtitle}</span>
        </div>
        {leagueData?.end_season?.open && (
          <div className="dash-badges">
            <button type="button" className="btn btn-primary" onClick={onOpenHub}>Enter the End of Season Hub</button>
          </div>
        )}
      </div>

      <DashboardTabs
        idPrefix="po"
        ariaLabel="Playoff sections"
        active={activeTab}
        onChange={(id) => setActiveTab(id as PlayoffTab)}
        tabs={[
          ...(leagueData?.enable_play_in !== false ? [{ id: 'playin', label: 'Play-In' }] : []),
          { id: 'bracket', label: 'Bracket' },
          { id: 'live', label: 'Courtside Live' },
        ]}
      />

      {/* RENDER TAB 1: Play-In Tournament */}
      {activeTab === 'playin' && leagueData?.enable_play_in !== false && (
        <div>
          {loadingPlayin && !playinData ? (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '40vh' }}>
              <div className="spinner"></div>
            </div>
          ) : !playinData || playinData.state === 'NOT_STARTED' ? (
            <div className="card" style={{ padding: '60px 40px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
              <Trophy size={48} className="logo-gold" style={{ opacity: 0.5 }} />
              <h2 style={{ margin: 0 }}>Play-In Tournament Not Started</h2>
              <p style={{ color: 'var(--text-secondary)', maxWidth: '500px', margin: '0 auto', fontSize: '14px', lineHeight: '1.6' }}>
                The Play-In Tournament will be scheduled and launched at the conclusion of the Regular Season.
              </p>
            </div>
          ) : (
            <div>
              {playinData.state === 'PLAY_IN' && (
                <div className="card flex-between" style={{
                  padding: '16px 24px',
                  marginBottom: '24px',
                  background: 'linear-gradient(90deg, rgba(212,175,55,0.06) 0%, rgba(24,27,36,0.8) 100%)',
                  borderColor: 'var(--primary)'
                }}>
                  <div>
                    <h3 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: 800, color: 'var(--primary)' }}>
                      Play-In Tournament In Progress
                    </h3>
                    <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      Game {playinData.game_index + 1} of 6
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    <button className="btn btn-primary" onClick={handleSimulatePlayinGame} disabled={simulatingPlayin}>
                      {simulatingPlayin ? 'Simulating...' : 'Simulate Next Game'}
                    </button>
                    <button className="btn btn-secondary" onClick={handleSimulatePlayinBulk} disabled={simulatingPlayin}>
                      {simulatingPlayin ? 'Simulating...' : 'Simulate Entire Play-In'}
                    </button>
                  </div>
                </div>
              )}

              <div className="grid-2" style={{ gap: '24px' }}>
                <div className="card" style={{ padding: '20px', borderLeft: '4px solid #60a5fa' }}>
                  <h3 style={{ color: '#60a5fa', textAlign: 'center', marginBottom: '20px', fontSize: '16px', fontWeight: 800 }}>
                    Eastern Conference Play-In
                  </h3>
                  {renderPlayinConferenceBracket(playinData.east, 'east')}
                </div>
                <div className="card" style={{ padding: '20px', borderLeft: '4px solid #a78bfa' }}>
                  <h3 style={{ color: '#a78bfa', textAlign: 'center', marginBottom: '20px', fontSize: '16px', fontWeight: 800 }}>
                    Western Conference Play-In
                  </h3>
                  {renderPlayinConferenceBracket(playinData.west, 'west')}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'bracket' && (
        <div role="tabpanel" id="po-panel-bracket" aria-labelledby="po-tab-bracket">
          {!playoffs ? (
            <div className="po-empty">
              <div className="po-empty-icon" aria-hidden="true">🏆</div>
              <h2>Playoffs have not started</h2>
              <p>The bracket is drawn when the regular season{leagueData?.enable_play_in !== false ? ' and the Play-In Tournament are' : ' is'} over.</p>
            </div>
          ) : (
            <BracketTab
              bracket={playoffs.bracket}
              champion={playoffs.campione}
              finalsMvp={playoffs.mvp_finali}
              userTeam={leagueData.player_team_name}
              liveRound={liveRound}
              busy={simulating || simulatingBracket}
              onSimulate={handleSimulatePlayoffs}
              onGoToPlayIn={() => setActiveTab('playin')}
              onOpenGameplan={onOpenGameplan}
              onOpenSeries={openResultSheet}
            />
          )}
        </div>
      )}

      {activeTab === 'live' && (
        <div role="tabpanel" id="po-panel-live" aria-labelledby="po-tab-live">
          <CourtsideTab
            games={night.games}
            idle={night.idle}
            latest={latestResults(playoffs?.bracket ?? null, playinData)}
            userTeam={leagueData.player_team_name}
            seedOf={playoffs ? seedsFromBracket(playoffs.bracket) : {}}
            champion={playoffs?.campione ?? null}
            inProgress={inProgress}
            busy={watching || simulating || simulatingBracket}
            onWatch={handleWatch}
            onOpenSeries={openResultSheet}
          />
        </div>
      )}

      {liveGame && (
        <CourtsideLive game={liveGame} onClose={() => setLiveGame(null)} />
      )}

      {openSeries && (
        <ResultSheet
          series={openSeries.series}
          label={openSeries.label}
          winsNeeded={openSeries.winsNeeded}
          onClose={() => setOpenSeries(null)}
        />
      )}

    </div>
  );
};
