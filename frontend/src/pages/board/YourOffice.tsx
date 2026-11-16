// "Your Office" tab: a status column (owner, approval, job security, contract) and three tabs on the right:
// This Season, Career, Season Reports. Data from /api/board; the Board Concern dialog opens from here too.
import React, { useEffect, useRef, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { BoardConcernModal } from '../../components/BoardConcernModal';
import { OfficeStatus } from './OfficeStatus';
import { SeasonTab } from './SeasonTab';
import { CareerTab } from './CareerTab';
import { ReportsTab } from './ReportsTab';
import type { BoardDataResponse } from './officeTypes';
import './Office.css';

type OfficeTab = 'season' | 'career' | 'reports';

export const YourOffice: React.FC = () => {
  const leagueData = useLeagueStore((s) => s.leagueData);
  const [data, setData] = useState<BoardDataResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [tab, setTab] = useState<OfficeTab>('season');
  const [selectedReport, setSelectedReport] = useState<number | 'live'>('live');
  const [extensionMessage, setExtensionMessage] = useState<string | null>(null);
  const [extending, setExtending] = useState<boolean>(false);
  const [boardConcern, setBoardConcern] = useState<any>(null);
  const tabRefs = useRef<Record<OfficeTab, HTMLButtonElement | null>>({ season: null, career: null, reports: null });

  const fetchBoardData = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/board?_t=${Date.now()}`);
      const result = await res.json();
      if (!result.error) setData(result);
    } catch (err) {
      console.error('Error loading the Board Office:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchBoardConcern = async () => {
    try {
      const res = await fetch(`/api/board/concern?_t=${Date.now()}`);
      const json = await res.json();
      setBoardConcern(json.concern || null);
    } catch (err) {
      console.error('Error checking the board concern:', err);
    }
  };

  useEffect(() => {
    fetchBoardData();
    fetchBoardConcern();
  }, [leagueData?.stagione, leagueData?.player_team_name]);

  const handleExtendContract = async () => {
    setExtending(true);
    try {
      const res = await fetch('/api/board/extend_contract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const result = await res.json();
      if (result.success) {
        setExtensionMessage(result.message);
        fetchBoardData();
      } else {
        setExtensionMessage(result.error || 'Failed to extend contract.');
      }
    } catch (err) {
      console.error('Error renewing the contract:', err);
    } finally {
      setExtending(false);
    }
  };

  if (loading && !data) {
    return <div className="an-loading"><div className="spinner"></div></div>;
  }

  if (!data || !data.board_profile) {
    return (
      <div className="an-empty">
        <h2>Front office unavailable</h2>
        <p>Select a team to access the board's directives.</p>
      </div>
    );
  }

  const { board_profile, user_gm_profile } = data;
  const reports = data.annual_reports || user_gm_profile?.season_reports || [];
  const liveReport = data.live_report || null;
  const teamName = user_gm_profile?.current_team_name || leagueData?.player_team_name || '';

  const standings = [...(leagueData?.classifica?.east || []), ...(leagueData?.classifica?.west || [])];
  const ownRow = standings.find((r) => r.nome === leagueData?.player_team_name);
  const gamesPlayed = ownRow ? ownRow.v + ownRow.s : 0;

  const tabs: { id: OfficeTab; label: string; count?: number }[] = [
    { id: 'season', label: 'This Season' },
    { id: 'career', label: 'Career' },
    { id: 'reports', label: 'Season Reports', count: reports.length },
  ];

  const moveTab = (index: number) => {
    const next = tabs[(index + tabs.length) % tabs.length].id;
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  const onTabKey = (event: React.KeyboardEvent, index: number) => {
    if (event.key === 'ArrowRight') { event.preventDefault(); moveTab(index + 1); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); moveTab(index - 1); }
    else if (event.key === 'Home') { event.preventDefault(); moveTab(0); }
    else if (event.key === 'End') { event.preventDefault(); moveTab(tabs.length - 1); }
  };

  return (
    <div className="of-root">
      <div className="of-layout">
        <OfficeStatus
          board={board_profile}
          contract={user_gm_profile?.contract ?? null}
          teamName={teamName}
          extending={extending}
          extensionMessage={extensionMessage}
          onExtend={handleExtendContract}
        />

        <div className="of-col">
          <div className="of-seg" role="tablist" aria-label="Office sections">
            {tabs.map((t, index) => (
              <button
                key={t.id}
                ref={(node) => { tabRefs.current[t.id] = node; }}
                type="button"
                role="tab"
                id={`of-tab-${t.id}`}
                aria-selected={tab === t.id}
                aria-controls={`of-panel-${t.id}`}
                tabIndex={tab === t.id ? 0 : -1}
                onClick={() => setTab(t.id)}
                onKeyDown={(e) => onTabKey(e, index)}
              >
                {t.label}
                {t.count !== undefined && <small>{t.count}</small>}
              </button>
            ))}
          </div>

          <div className="of-col" role="tabpanel" id={`of-panel-${tab}`} aria-labelledby={`of-tab-${tab}`}>
            {tab === 'season' && (
              <SeasonTab
                objectives={board_profile.objectives || []}
                messages={board_profile.board_messages || []}
                season={leagueData?.stagione}
                gamesPlayed={gamesPlayed}
              />
            )}
            {tab === 'career' && (user_gm_profile
              ? <CareerTab gm={user_gm_profile} />
              : <div className="of-card of-empty">No GM profile for this save.</div>)}
            {tab === 'reports' && (
              <ReportsTab reports={reports} liveReport={liveReport} selected={selectedReport} onSelect={setSelectedReport} />
            )}
          </div>
        </div>
      </div>

      {boardConcern && (
        <BoardConcernModal
          concern={boardConcern}
          onResolved={() => {
            setBoardConcern(null);
            fetchBoardData();
          }}
          onClose={() => setBoardConcern(null)}
        />
      )}
    </div>
  );
};
