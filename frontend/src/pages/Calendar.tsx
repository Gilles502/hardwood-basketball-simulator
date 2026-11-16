// File: frontend/src/pages/Calendar.tsx
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { ResultSheet } from '../components/ResultSheet';
import { TodayGamesHubModal } from '../components/TodayGamesHubModal';
import { SimulateUntilModal } from '../components/SimulateUntilModal';
import { useSimRunning, SIM_LOCK_HINT } from '../hooks/useSimRunning';
import { CourtsideLive, type LiveGame } from '../components/CourtsideLive';
import { TeamCrest } from '../components/TeamCrest';
import { nickname } from '../utils/resultSheet';
import { ordinal, phaseLabel } from '../utils/format';
import { eventLabels, parseIsoDate } from '../utils/scheduleEvents';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './schedule/Schedule.css';

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

interface CalendarDayData {
  day_index: number;
  date: string;
  games: ScheduledGameData[];
  events: string[];
  phase: string;
  is_off_day: boolean;
}

type StatusFilter = 'ALL' | 'PLAYED' | 'UPCOMING';

/** Events marked on the season bar, in the order they happen. */
const RULER_EVENTS: [string, string][] = [
  ['OPENING_NIGHT', 'Opening night'],
  ['CHRISTMAS_GAMES', 'Christmas'],
  ['TRADE_DEADLINE', 'Trade deadline'],
  ['ALL_STAR_GAME', 'All-Star'],
  ['REGULAR_SEASON_FINALE', 'Finale'],
];

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const parseDate = parseIsoDate;
const isoOf = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const monthKey = (iso: string) => iso.slice(0, 7);
const dayLabel = (iso: string, opts: Intl.DateTimeFormatOptions) => parseDate(iso).toLocaleDateString('en-US', opts);

/** The given team's game on a day, from its point of view. */
const teamGame = (day: CalendarDayData | undefined, team: string) => {
  const game = day?.games.find((g) => g.home_team === team || g.away_team === team);
  if (!game) return null;
  const home = game.home_team === team;
  const own = home ? game.home_score : game.away_score;
  const opp = home ? game.away_score : game.home_score;
  return {
    game,
    home,
    opponent: home ? game.away_team : game.home_team,
    result: game.played ? (own > opp ? 'W' : 'L') as 'W' | 'L' : null,
    score: game.played ? `${own}–${opp}` : '',
    b2b: home ? game.is_back_to_back_home : game.is_back_to_back_away,
  };
};

export const CalendarView: React.FC = () => {
  const {
    leagueData,
    openPlayerProfile,
    openTeamProfile,
    simulateCalendarGame,
    simulateCalendarDay,
    simulateCalendarUntil
  } = useLeagueStore();

  const [calendarDays, setCalendarDays] = useState<CalendarDayData[]>([]);
  const [loadingCalendar, setLoadingCalendar] = useState<boolean>(true);
  const userTeamName = leagueData?.player_team_name || null;
  const [teamFilter, setTeamFilter] = useState<string>(userTeamName ?? 'ALL');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [selectedDayIndex, setSelectedDayIndex] = useState<number | null>(null);
  const [selectedBoxScoreGame, setSelectedBoxScoreGame] = useState<ScheduledGameData | null>(null);

  const [simUntilTarget, setSimUntilTarget] = useState<CalendarDayData | null>(null);
  const [showMatchdayHub, setShowMatchdayHub] = useState<boolean>(false);
  const [simulatingSingleGameId, setSimulatingSingleGameId] = useState<string | null>(null);
  const [simulatingRemainingToday, setSimulatingRemainingToday] = useState<boolean>(false);

  const [liveGame, setLiveGame] = useState<LiveGame | null>(null);
  const dayPanelRef = useRef<HTMLElement | null>(null);

  const currentDayIndex = leagueData?.current_day || 0;
  const totalDays = leagueData?.total_calendar_days || 176;

  // Full calendar from the API (spinner only on the first load)
  const loadCalendar = async (silent = false) => {
    try {
      if (!silent) setLoadingCalendar(true);
      const res = await fetch('/api/calendar');
      const data = await res.json();
      if (data && data.days) {
        setCalendarDays(data.days);
      }
    } catch (err) {
      console.error('Error loading calendar:', err);
    } finally {
      setLoadingCalendar(false);
    }
  };

  useEffect(() => {
    loadCalendar();
  }, [leagueData?.season_number, leagueData?.stagione]);

  const byDate = useMemo(() => new Map(calendarDays.map((d) => [d.date, d])), [calendarDays]);
  const months = useMemo(() => [...new Set(calendarDays.map((d) => monthKey(d.date)))], [calendarDays]);

  // "Today" is the next day to play; past the last day it stays on the finale.
  const todayDay = calendarDays.find((d) => d.day_index === currentDayIndex) ?? calendarDays[calendarDays.length - 1];
  const todayIndex = todayDay?.day_index ?? 0;

  const shownMonth = selectedMonth ?? (todayDay ? monthKey(todayDay.date) : months[0]);
  const selectedDay = calendarDays.find((d) => d.day_index === (selectedDayIndex ?? todayIndex));

  const jumpToToday = () => {
    setSelectedMonth(null);
    setSelectedDayIndex(null);
  };

  const pickMonth = (key: string) => {
    setSelectedMonth(key);
    if (todayDay && monthKey(todayDay.date) === key) setSelectedDayIndex(null);
    else setSelectedDayIndex(calendarDays.find((d) => monthKey(d.date) === key && d.games.length > 0)?.day_index ?? null);
  };

  const handleSimulateSingleGame = async (gameId: string) => {
    if (simulatingSingleGameId || simulatingRemainingToday) return;
    setSimulatingSingleGameId(gameId);
    try {
      await simulateCalendarGame(gameId);
      await loadCalendar(true);
    } catch (err) {
      console.error('Error while simulating the game:', err);
    } finally {
      setSimulatingSingleGameId(null);
    }
  };

  const handleSimulateRemainingToday = async () => {
    if (simulatingRemainingToday) return;
    setSimulatingRemainingToday(true);
    try {
      await simulateCalendarDay();
      await loadCalendar(true);
    } catch (err) {
      console.error('Day simulation error:', err);
    } finally {
      setSimulatingRemainingToday(false);
    }
  };

  const handleWatchLiveCalendar = async (game: ScheduledGameData) => {
    if (simulatingSingleGameId || simulatingRemainingToday) return;
    setSimulatingSingleGameId(game.game_id);
    try {
      const result = await simulateCalendarGame(game.game_id, true);
      setLiveGame({
        home: result?.home_team || game.home_team,
        away: result?.away_team || game.away_team,
        label: `Regular season · Day ${game.day_index + 1}`,
        plays: result?.play_log || [],
      });
      await loadCalendar(true);
    } catch (err) {
      console.error('Error starting live watch game from calendar:', err);
    } finally {
      setSimulatingSingleGameId(null);
    }
  };

  const handleConfirmSimUntil = async (targetDayIndex: number, includeTarget: boolean) => {
    await simulateCalendarUntil(targetDayIndex, includeTarget);
    await loadCalendar(true);
    jumpToToday();
  };

  const allTeamsList = useMemo(() => {
    if (!leagueData?.classifica) return [];
    const east = leagueData.classifica.east?.map(t => t.nome) || [];
    const west = leagueData.classifica.west?.map(t => t.nome) || [];
    return [...east, ...west].sort();
  }, [leagueData]);

  const gamesPlayed = useMemo(() => {
    let total = 0;
    let played = 0;
    calendarDays.forEach((day) => day.games.forEach((g) => { total += 1; if (g.played) played += 1; }));
    return { total, played };
  }, [calendarDays]);

  const standing = useMemo(() => {
    if (!userTeamName) return null;
    for (const [conf, label] of [['east', 'East'], ['west', 'West']] as const) {
      const row = leagueData?.classifica?.[conf]?.find((t) => t.nome === userTeamName) as { pos: number; v?: number; s?: number } | undefined;
      if (row) return { record: `${row.v ?? 0}–${row.s ?? 0}`, place: `${ordinal(row.pos)} in the ${label}` };
    }
    return null;
  }, [leagueData, userTeamName]);

  // Season bar: first day of each marked event, plus today.
  const rulerMarks = useMemo(() => {
    const span = Math.max(totalDays - 1, 1);
    const marks = RULER_EVENTS.flatMap(([key, label]) => {
      const day = calendarDays.find((d) => d.events.includes(key));
      return day ? [{ pos: (day.day_index / span) * 100, label, now: false }] : [];
    });
    marks.push({ pos: (Math.min(currentDayIndex, span) / span) * 100, label: 'Today', now: true });
    marks.sort((a, b) => a.pos - b.pos);
    // Labels closer than 7% apart take turns above and below the bar.
    let lastBelow = -100;
    return marks.map((m) => {
      const up = !m.now && m.pos - lastBelow < 7;
      if (!up) lastBelow = m.pos;
      return { ...m, up };
    });
  }, [calendarDays, currentDayIndex, totalDays]);

  // Month grid: whole weeks, Sunday first.
  const monthCells = useMemo(() => {
    if (!shownMonth) return [];
    const first = parseDate(`${shownMonth}-01`);
    const last = new Date(first.getFullYear(), first.getMonth() + 1, 0);
    const start = new Date(first); start.setDate(first.getDate() - first.getDay());
    const end = new Date(last); end.setDate(last.getDate() + (6 - last.getDay()));
    const cells: { iso: string; inMonth: boolean }[] = [];
    for (const d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      cells.push({ iso: isoOf(d), inMonth: d.getMonth() === first.getMonth() });
    }
    return cells;
  }, [shownMonth]);

  const monthTeamLine = useMemo(() => {
    if (teamFilter === 'ALL' || !shownMonth) return null;
    let w = 0; let l = 0; let left = 0;
    calendarDays.filter((d) => monthKey(d.date) === shownMonth).forEach((d) => {
      const tg = teamGame(d, teamFilter);
      if (!tg) return;
      if (tg.result === 'W') w += 1; else if (tg.result === 'L') l += 1; else left += 1;
    });
    if (w + l + left === 0) return `${nickname(teamFilter)}: no games this month`;
    const parts = [w + l > 0 && `${w}–${l}`, left > 0 && `${left} to play`].filter(Boolean);
    return `${nickname(teamFilter)} this month: ${parts.join(' · ')}`;
  }, [calendarDays, shownMonth, teamFilter]);

  const panelGames = (selectedDay?.games ?? []).filter((g) =>
    statusFilter === 'ALL' || (statusFilter === 'PLAYED' ? g.played : !g.played));
  const isTodaySelected = selectedDay?.day_index === todayIndex && currentDayIndex <= todayIndex;
  const remainingToday = isTodaySelected ? (selectedDay?.games.filter((g) => !g.played).length ?? 0) : 0;
  const canSimUntil = !!selectedDay && selectedDay.day_index > currentDayIndex && !selectedDay.is_off_day;
  const runGoing = useSimRunning();
  // A live run locks every sim action here; the run bar has Stop.
  const busy = runGoing || !!simulatingSingleGameId || simulatingRemainingToday;
  const lockHint = runGoing ? SIM_LOCK_HINT : undefined;

  const seasonYear = leagueData?.anno_corrente;
  const seasonLabel = seasonYear ? `${seasonYear}–${String((seasonYear + 1) % 100).padStart(2, '0')}` : null;

  return (
    <div className="sch-root">
      <div className="dash-header">
        <div>
          <h1 className="dash-title">Schedule</h1>
          <span className="dash-subtitle">
            {[seasonLabel && `${seasonLabel} ${phaseLabel(leagueData?.league_state ?? '', currentDayIndex).toLowerCase()}`,
              `Day ${Math.min(currentDayIndex + 1, totalDays)} of ${totalDays}`,
              todayDay && dayLabel(todayDay.date, { weekday: 'short', month: 'short', day: 'numeric' })].filter(Boolean).join(' · ')}
          </span>
        </div>
        <div className="dash-badges">
          <button type="button" className="btn btn-primary" onClick={() => setShowMatchdayHub(true)} disabled={runGoing} title={lockHint}>▶ Gameday Hub</button>
          <button type="button" className="btn btn-secondary" onClick={jumpToToday}>Jump to today</button>
        </div>
      </div>

      <div className="sch-ruler" aria-label="Season progress">
        <div className="sch-ruler-track"><i style={{ width: `${(Math.min(currentDayIndex, totalDays - 1) / Math.max(totalDays - 1, 1)) * 100}%` }} /></div>
        {rulerMarks.map((m) => (
          <div key={`${m.label}-${m.pos}`} className={`sch-mark${m.now ? ' is-now' : ''}${m.up ? ' is-up' : ''}`} style={{ left: `${Math.min(Math.max(m.pos, 2), 98)}%` }}>
            <span>{m.label}</span>
          </div>
        ))}
      </div>
      <div className="sch-ruler-meta">
        <span><b>{gamesPlayed.played.toLocaleString('en-US')}</b> of {gamesPlayed.total.toLocaleString('en-US')} games played</span>
        {userTeamName && standing && <span>{nickname(userTeamName)} <b>{standing.record}</b> · {standing.place}</span>}
      </div>

      <div className="sch-bar">
        <div className="sch-months" role="group" aria-label="Month">
          {months.map((key) => (
            <button key={key} type="button" aria-pressed={key === shownMonth} onClick={() => pickMonth(key)}>
              {parseDate(`${key}-01`).toLocaleDateString('en-US', { month: 'short' })}
            </button>
          ))}
        </div>
        <div className="sch-filters">
          <select className="sch-select" value={teamFilter} onChange={(e) => setTeamFilter(e.target.value)} aria-label="Team shown on the calendar">
            {userTeamName && <option value={userTeamName}>My team: {nickname(userTeamName)}</option>}
            <option value="ALL">League only (no team)</option>
            {allTeamsList.filter((t) => t !== userTeamName).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="sch-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as StatusFilter)} aria-label="Games listed for the day">
            <option value="ALL">All games</option>
            <option value="PLAYED">Results only</option>
            <option value="UPCOMING">Upcoming only</option>
          </select>
        </div>
      </div>

      {loadingCalendar ? (
        <div className="sch-empty">Loading the schedule…</div>
      ) : calendarDays.length === 0 ? (
        <div className="sch-empty">No schedule yet: it is drawn when the season starts.</div>
      ) : (
        <div className="sch-wrap">
          <section className="sch-cal" aria-label="Month calendar">
            <div className="sch-cal-head">
              <b>{parseDate(`${shownMonth}-01`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</b>
              {monthTeamLine && <span>{monthTeamLine}</span>}
            </div>
            <div className="sch-grid">
              {WEEKDAYS.map((w) => <div key={w} className="sch-wd">{w}</div>)}
              {monthCells.map(({ iso, inMonth }) => {
                const day = byDate.get(iso);
                if (!inMonth || !day) {
                  return <div key={iso} className="sch-cell is-out"><span className="sch-dn"><b>{parseDate(iso).getDate()}</b></span></div>;
                }
                const tg = teamFilter !== 'ALL' ? teamGame(day, teamFilter) : null;
                const isToday = day.day_index === todayIndex;
                const cls = ['sch-cell',
                  day.day_index < currentDayIndex && 'is-past',
                  isToday && 'is-today',
                  day.day_index === selectedDay?.day_index && 'is-selected'].filter(Boolean).join(' ');
                const labels = eventLabels(day.events);
                return (
                  <button
                    key={iso}
                    type="button"
                    className={cls}
                    onClick={() => {
                      setSelectedDayIndex(day.day_index);
                      // Bring the day's games into view when they sit below the fold.
                      requestAnimationFrame(() => dayPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
                    }}
                    aria-pressed={day.day_index === selectedDay?.day_index}
                    aria-label={`${dayLabel(iso, { weekday: 'long', month: 'long', day: 'numeric' })}, ${day.games.length} games${tg ? `, ${tg.home ? 'home to' : 'at'} ${tg.opponent}${tg.result ? `, ${tg.result === 'W' ? 'won' : 'lost'} ${tg.score}` : ''}` : ''}`}
                  >
                    <span className="sch-dn">
                      <b>{parseDate(iso).getDate()}</b>
                      {isToday ? <span className="sch-tag is-hot">Today</span> : labels[0] && <span className="sch-tag">{labels[0]}</span>}
                    </span>
                    {tg && (
                      <span className="sch-gm">
                        <em>{tg.home ? 'vs' : '@'}</em><TeamCrest name={tg.opponent} size={18} /><span>{nickname(tg.opponent)}</span>
                      </span>
                    )}
                    {tg?.result && <span className={`sch-res is-${tg.result.toLowerCase()}`}>{tg.result} {tg.score}</span>}
                    {tg && !tg.result && tg.b2b && <span className="sch-b2b" title="Back-to-back: played the day before">B2B</span>}
                    <span className="sch-lg">{day.is_off_day && day.games.length === 0 ? 'Rest day' : `${day.games.length} games`}</span>
                  </button>
                );
              })}
            </div>
          </section>

          {selectedDay && (
            <section className="sch-day" aria-label="Games of the selected day" ref={dayPanelRef}>
              <div className="sch-day-head">
                <div>
                  <b>{dayLabel(selectedDay.date, { weekday: 'short', month: 'short', day: 'numeric' })}</b>
                  <small>
                    Day {selectedDay.day_index + 1} · {selectedDay.games.length} games
                    {selectedDay.games.some((g) => g.played) && ` · ${selectedDay.games.filter((g) => g.played).length} final`}
                  </small>
                </div>
                {selectedDay.day_index === todayIndex && <span className="sch-tag is-hot">Today</span>}
              </div>
              {(eventLabels(selectedDay.events).length > 0 || isTodaySelected || canSimUntil) && (
                <div className="sch-day-acts">
                  {eventLabels(selectedDay.events).map((l) => <span key={l} className="sch-tag">{l}</span>)}
                  {isTodaySelected && (
                    <>
                      <button type="button" className="btn btn-primary sch-btn-sm" onClick={() => setShowMatchdayHub(true)} disabled={runGoing} title={lockHint}>▶ Gameday Hub</button>
                      {remainingToday > 0 && (
                        <button type="button" className="sch-btn-ink" onClick={handleSimulateRemainingToday} disabled={busy} title={lockHint}>
                          {simulatingRemainingToday ? 'Simulating…' : `Sim remaining (${remainingToday})`}
                        </button>
                      )}
                    </>
                  )}
                  {canSimUntil && (
                    <button type="button" className="sch-btn-ink" onClick={() => setSimUntilTarget(selectedDay)} disabled={busy} title={lockHint}>
                      Sim until here
                    </button>
                  )}
                </div>
              )}
              {panelGames.length === 0 ? (
                <div className="sch-day-empty">{selectedDay.games.length === 0 ? 'No games on this day.' : 'No games match the filter.'}</div>
              ) : (
              <div className="sch-day-list">
              {panelGames.map((game) => {
                const mine = !!userTeamName && (game.home_team === userTeamName || game.away_team === userTeamName);
                const awayWon = game.played && game.away_score > game.home_score;
                const lines = [
                  { team: game.away_team, score: game.away_score, won: awayWon, b2b: game.is_back_to_back_away },
                  { team: game.home_team, score: game.home_score, won: game.played && !awayWon, b2b: game.is_back_to_back_home },
                ];
                const canPlay = isTodaySelected && !game.played;
                return (
                  <div key={game.game_id} className={`sch-row${mine ? ' is-me' : ''}${game.played ? ' is-final' : ''}`}>
                    <div className="sch-row-teams">
                      {lines.map((ln, i) => (
                        <div key={ln.team} className={`sch-row-line${game.played && !ln.won ? ' is-lo' : ''}`}>
                          <button type="button" className="sch-team-link" onClick={() => openTeamProfile(ln.team)} title={`${ln.team} profile`}>
                            <TeamCrest name={ln.team} size={20} />{nickname(ln.team)}
                          </button>
                          {i === 1 && <em className="sch-home">home</em>}
                          {ln.b2b && !game.played && <span className="sch-b2b" title="Back-to-back: played the day before">B2B</span>}
                          <span className="sch-score">{game.played ? ln.score : ''}</span>
                        </div>
                      ))}
                      {game.played && game.top_performer && (
                        <button type="button" className="sch-top" onClick={() => openPlayerProfile(game.top_performer!.name)}>
                          👑 {game.top_performer.name} · {game.top_performer.pts} pts · {game.top_performer.reb} reb · {game.top_performer.ast} ast
                        </button>
                      )}
                    </div>
                    <div className="sch-row-acts">
                      {game.played ? (
                        <button type="button" className="sch-link" onClick={() => setSelectedBoxScoreGame(game)}>Box score</button>
                      ) : canPlay ? (
                        <>
                          <button type="button" className="sch-btn-ghost" onClick={() => handleWatchLiveCalendar(game)} disabled={busy}>
                            {simulatingSingleGameId === game.game_id ? 'Tip-off…' : '▶ Live'}
                          </button>
                          <button type="button" className="sch-btn-ghost" onClick={() => handleSimulateSingleGame(game.game_id)} disabled={busy}>
                            Quick sim
                          </button>
                        </>
                      ) : null}
                    </div>
                  </div>
                );
              })}
              </div>
              )}
            </section>
          )}
        </div>
      )}

      {selectedBoxScoreGame && (
        <ResultSheet
          gameId={selectedBoxScoreGame.game_id}
          preview={selectedBoxScoreGame}
          onClose={() => setSelectedBoxScoreGame(null)}
        />
      )}

      {showMatchdayHub && (
        <TodayGamesHubModal
          isOpen={showMatchdayHub}
          onClose={() => setShowMatchdayHub(false)}
          dayIndex={currentDayIndex}
          dateStr={calendarDays.find(d => d.day_index === currentDayIndex)?.date || ""}
          games={calendarDays.find(d => d.day_index === currentDayIndex)?.games || []}
          onRefreshCalendar={() => loadCalendar(true)}
        />
      )}

      {simUntilTarget && (
        <SimulateUntilModal
          isOpen={!!simUntilTarget}
          onClose={() => setSimUntilTarget(null)}
          currentDayIndex={currentDayIndex}
          targetDayIndex={simUntilTarget.day_index}
          targetDateStr={simUntilTarget.date}
          totalDays={totalDays}
          days={calendarDays}
          teamName={userTeamName}
          onConfirm={handleConfirmSimUntil}
        />
      )}

      {liveGame && (
        <CourtsideLive game={liveGame} onClose={() => { setLiveGame(null); loadCalendar(true); }} />
      )}
    </div>
  );
};
