import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { useLiveStore } from '../store/liveStore';
import { DashboardTabs } from '../components/DashboardTabs';
import { OverviewTab } from './dashboard/OverviewTab';
import { StandingsTab } from './dashboard/StandingsTab';
import { News } from './News';
import { phaseLabel, roleLabel, ordinal } from '../utils/format';
import type { Tab } from '../navigation';
import './dashboard/Dashboard.css';

export type DashboardTab = 'overview' | 'standings' | 'news';

// The chosen tab survives switching to other pages and back (in memory only).
let lastTab: DashboardTab = 'overview';

interface DashboardProps {
  onNavigate: (tab: Tab) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const { leagueData, loading, simulating, error, fetchLeagueData, fetchLeagueDataSilent } = useLeagueStore();
  const summary = useLiveStore((state) => state.summary);
  const [tab, setTabState] = useState<DashboardTab>(lastTab);

  const setTab = (next: DashboardTab) => {
    lastTab = next;
    setTabState(next);
  };

  useEffect(() => {
    fetchLeagueData();
    // Silent refresh keeps the heavy league data (rosters, bracket) in sync while this page is open.
    const interval = setInterval(() => {
      // A live run sends fresh data every day; a full refresh mid-run would race it.
      const run = useLeagueStore.getState().simRun;
      if (!simulating && !(run && run.error === null)) fetchLeagueDataSilent();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchLeagueData, fetchLeagueDataSilent, simulating]);

  if (loading && !leagueData) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--danger)', color: 'var(--danger)', margin: '20px 0' }}>
        <h3 style={{ margin: 0 }}>Error</h3>
        <p>{error}</p>
        <button className="btn btn-secondary" style={{ marginTop: '12px' }} onClick={fetchLeagueData}>
          Retry
        </button>
      </div>
    );
  }

  if (!leagueData) return null;

  const { stagione, league_state, player_team_name, user_role } = leagueData;
  const team = summary?.team ?? null;
  const played = team ? team.record !== '0-0' : false;
  const standingHint = team && played && team.conf_rank ? ordinal(team.conf_rank) : undefined;
  const newsUnread = summary?.attention.news_unread ?? 0;

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'standings', label: 'Standings', hint: standingHint },
    { id: 'news', label: 'News', hint: tab !== 'news' && newsUnread > 0 ? String(newsUnread) : undefined },
  ];

  return (
    <div className="dash">
      <header className="dash-header">
        <div>
          <h1 className="dash-title">Dashboard</h1>
          <span className="dash-subtitle">{phaseLabel(league_state, leagueData.current_day || 0)}</span>
        </div>
        <div className="dash-badges">
          <span className="season-badge">Season {stagione}</span>
          {player_team_name && <span className="team-badge">{roleLabel(user_role)} · {player_team_name}</span>}
        </div>
      </header>

      <DashboardTabs tabs={tabs} active={tab} onChange={(id) => setTab(id as DashboardTab)} />

      <div role="tabpanel" id={`dash-panel-${tab}`} aria-labelledby={`dash-tab-${tab}`} className="dash-panel">
        {tab === 'overview' && <OverviewTab onNavigate={onNavigate} onOpenTab={setTab} />}
        {tab === 'standings' && <StandingsTab />}
        {tab === 'news' && <News />}
      </div>
    </div>
  );
};
