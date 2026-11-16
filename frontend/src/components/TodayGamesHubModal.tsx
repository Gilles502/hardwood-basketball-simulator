import React, { useMemo, useState } from 'react';
import { Play } from 'lucide-react';
import { useLeagueStore } from '../store/leagueStore';
import { useSimRunning, SIM_LOCK_HINT } from '../hooks/useSimRunning';
import { ModalShell } from './ModalShell';
import { TeamCrest } from './TeamCrest';
import { ResultSheet } from './ResultSheet';
import { CourtsideLive, type LiveGame } from './CourtsideLive';
import './TodayGamesHubModal.css';

interface ScheduledGameData {
  game_id: string;
  home_team: string;
  away_team: string;
  date: string;
  day_index: number;
  played: boolean;
  home_score: number;
  away_score: number;
  box_score_id?: string;
  top_performer?: {
    name: string;
    team: string;
    pts: number;
    reb: number;
    ast: number;
  };
  quarter_scores?: {
    home?: number[];
    away?: number[];
  };
  is_back_to_back_home: boolean;
  is_back_to_back_away: boolean;
}

interface TodayGamesHubModalProps {
  isOpen: boolean;
  onClose: () => void;
  dayIndex: number;
  dateStr: string;
  games: ScheduledGameData[];
  onRefreshCalendar?: () => void;
}

/** Tonight's games as one scorer's sheet: your game first, then the rest; watch, sim or open the box score. */
export const TodayGamesHubModal: React.FC<TodayGamesHubModalProps> = ({
  isOpen,
  onClose,
  dayIndex,
  dateStr,
  games,
  onRefreshCalendar
}) => {
  const {
    leagueData,
    simulateCalendarGame,
    simulateCalendarDay,
    openPlayerProfile,
    openTeamProfile
  } = useLeagueStore();

  const [simulatingGameId, setSimulatingGameId] = useState<string | null>(null);
  const [simulatingAll, setSimulatingAll] = useState(false);
  const [selectedBoxScoreGame, setSelectedBoxScoreGame] = useState<ScheduledGameData | null>(null);
  const [liveGame, setLiveGame] = useState<LiveGame | null>(null);
  const runGoing = useSimRunning();

  const userTeamName = leagueData?.player_team_name;

  const records = useMemo(() => {
    const map: Record<string, string> = {};
    [...(leagueData?.classifica?.east ?? []), ...(leagueData?.classifica?.west ?? [])].forEach((row) => {
      const r = row as { nome: string; v?: number; s?: number };
      map[r.nome] = `${r.v ?? 0}–${r.s ?? 0}`;
    });
    return map;
  }, [leagueData?.classifica]);

  const ordered = useMemo(() => {
    const mine = (g: ScheduledGameData) => g.home_team === userTeamName || g.away_team === userTeamName;
    return [...games].sort((a, b) => Number(mine(b)) - Number(mine(a)));
  }, [games, userTeamName]);

  if (!isOpen) return null;

  const playedCount = games.filter(g => g.played).length;
  const totalCount = games.length;
  const remaining = totalCount - playedCount;
  const busy = runGoing || !!simulatingGameId || simulatingAll;

  const formattedDate = (() => {
    const [y, m, d] = dateStr.split('-').map(Number);
    const date = new Date(y, (m || 1) - 1, d || 1);
    return Number.isNaN(date.getTime())
      ? dateStr
      : date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  })();

  const handleWatchLive = async (game: ScheduledGameData) => {
    if (busy) return;
    setSimulatingGameId(game.game_id);
    try {
      const result = await simulateCalendarGame(game.game_id, true);
      setLiveGame({
        home: result?.home_team || game.home_team,
        away: result?.away_team || game.away_team,
        label: `Regular season · Day ${dayIndex + 1}`,
        plays: result?.play_log || [],
      });
      if (onRefreshCalendar) onRefreshCalendar();
    } catch (err) {
      console.error('Error starting live watch game:', err);
    } finally {
      setSimulatingGameId(null);
    }
  };

  const handleSimSingle = async (gameId: string) => {
    if (busy) return;
    setSimulatingGameId(gameId);
    try {
      await simulateCalendarGame(gameId);
      if (onRefreshCalendar) onRefreshCalendar();
    } catch (err) {
      console.error('Error simulating game:', err);
    } finally {
      setSimulatingGameId(null);
    }
  };

  const handleSimRemaining = async () => {
    if (simulatingAll || remaining === 0) return;
    setSimulatingAll(true);
    try {
      await simulateCalendarDay();
      if (onRefreshCalendar) onRefreshCalendar();
    } catch (err) {
      console.error('Error simulating day:', err);
    } finally {
      setSimulatingAll(false);
    }
  };

  const strip = (
    <div className="gh-strip">
      <span className="gh-cap">Tonight</span>
      <b>{playedCount} of {totalCount} final</b>
      <div className="gh-progress" aria-hidden="true">
        <i style={{ width: `${totalCount > 0 ? (playedCount / totalCount) * 100 : 0}%` }} />
      </div>
      {remaining > 0 ? (
        <button type="button" className="btn btn-primary gh-sim-all" onClick={handleSimRemaining} disabled={busy} title={runGoing ? SIM_LOCK_HINT : undefined}>
          {simulatingAll ? 'Simulating…' : `Sim remaining (${remaining})`}
        </button>
      ) : totalCount > 0 && <span className="gh-done">All games final</span>}
    </div>
  );

  return (
    // Sits one step below other dialogs so profiles opened from the sheet show on top of it.
    <div className="gh-layer">
      <ModalShell
        isOpen
        onClose={onClose}
        title="Gameday Hub"
        subtitle={`${formattedDate} · Day ${dayIndex + 1}`}
        icon={<Play size={20} />}
        headerExtra={strip}
        maxWidth={1100}
        dismissible={!selectedBoxScoreGame && !liveGame}
      >
        {totalCount === 0 ? (
          <div className="gh-empty">No games today: it's a league-wide rest day.</div>
        ) : (
          <div className="gh-sheet">
            <table className="gh-table">
              <thead>
                <tr>
                  <th>Matchup</th>
                  <th className="gh-num">Score</th>
                  <th>Status</th>
                  <th>Top scorer</th>
                  <th><span className="gh-sr">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {ordered.map((game) => {
                  const mine = game.home_team === userTeamName || game.away_team === userTeamName;
                  const awayWon = game.played && game.away_score > game.home_score;
                  const lines = [
                    { team: game.away_team, score: game.away_score, won: awayWon, b2b: game.is_back_to_back_away, home: false },
                    { team: game.home_team, score: game.home_score, won: game.played && !awayWon, b2b: game.is_back_to_back_home, home: true },
                  ];
                  const thisBusy = simulatingGameId === game.game_id;
                  return (
                    <tr key={game.game_id} className={mine ? 'is-me' : undefined}>
                      <td>
                        <div className="gh-teams">
                          {lines.map((ln) => (
                            <div key={ln.team} className={`gh-team${game.played && !ln.won ? ' is-lo' : ''}`}>
                              <button type="button" className="gh-team-link" onClick={() => openTeamProfile(ln.team)} title={`${ln.team} profile`}>
                                <TeamCrest name={ln.team} size={22} />{ln.team}
                              </button>
                              <small>{[records[ln.team], ln.home && 'home'].filter(Boolean).join(' · ')}</small>
                              {ln.b2b && !game.played && <span className="gh-b2b" title="Back-to-back: played the day before">B2B</span>}
                            </div>
                          ))}
                        </div>
                      </td>
                      <td className="gh-num gh-score">
                        {game.played && <>{game.away_score}<br />{game.home_score}</>}
                      </td>
                      <td className={`gh-status${game.played ? ' is-final' : ''}`}>{game.played ? 'Final' : 'Upcoming'}</td>
                      <td className="gh-top">
                        {game.played && game.top_performer && (
                          <button type="button" className="gh-top-link" onClick={() => openPlayerProfile(game.top_performer!.name)}>
                            👑 {game.top_performer.name} · {game.top_performer.pts} pts · {game.top_performer.reb} reb · {game.top_performer.ast} ast
                          </button>
                        )}
                      </td>
                      <td className="gh-acts">
                        {game.played ? (
                          <button type="button" className="gh-link" onClick={() => setSelectedBoxScoreGame(game)}>Box score</button>
                        ) : (
                          <>
                            <button type="button" className="gh-btn" onClick={() => handleWatchLive(game)} disabled={busy}>
                              {thisBusy ? 'Tip-off…' : '▶ Live'}
                            </button>
                            <button type="button" className="gh-btn" onClick={() => handleSimSingle(game.game_id)} disabled={busy}>
                              Quick sim
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </ModalShell>

      {selectedBoxScoreGame && (
        <ResultSheet
          gameId={selectedBoxScoreGame.game_id}
          preview={selectedBoxScoreGame}
          onClose={() => setSelectedBoxScoreGame(null)}
        />
      )}

      {liveGame && (
        <CourtsideLive game={liveGame} onClose={() => { setLiveGame(null); if (onRefreshCalendar) onRefreshCalendar(); }} />
      )}
    </div>
  );
};
