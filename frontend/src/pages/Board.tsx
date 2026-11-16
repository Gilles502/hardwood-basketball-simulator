// frontend/src/pages/Board.tsx
import React, { useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { DashboardTabs } from '../components/DashboardTabs';
import { YourOffice } from './board/YourOffice';
import { LeagueGMs } from './board/LeagueGMs';
import { JobsPanel } from './board/JobsPanel';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './analytics/Analytics.css'; // tables and cards shared with Analytics
import './board/Board.css';

type BoardTab = 'office' | 'league' | 'market';

const TABS: { id: BoardTab; label: string }[] = [
  { id: 'office', label: 'Your office' },
  { id: 'league', label: 'League GMs' },
  { id: 'market', label: 'GM market & jobs' },
];

/** Front Office & Board: your office, the league's 30 front offices, the GM market and your job offers (AI GM). */
export const Board: React.FC = () => {
  const hasTeam = useLeagueStore((s) => !!s.leagueData?.player_team_name && !s.leagueData?.is_spectator);
  const [activeTab, setActiveTab] = useState<BoardTab>(hasTeam ? 'office' : 'league');
  const [visited, setVisited] = useState<Set<BoardTab>>(() => new Set([hasTeam ? 'office' : 'league']));

  const pickTab = (id: BoardTab) => {
    setActiveTab(id);
    setVisited((v) => (v.has(id) ? v : new Set(v).add(id)));
  };

  return (
    <div>
      <div className="dash-header">
        <div>
          <h1 className="dash-title">Front Office &amp; Board</h1>
          <span className="dash-subtitle">Your office, the league's general managers, the GM market and your job offers</span>
        </div>
      </div>

      <DashboardTabs
        idPrefix="fo"
        ariaLabel="Front office sections"
        active={activeTab}
        onChange={(id) => pickTab(id as BoardTab)}
        tabs={TABS}
      />

      <div role="tabpanel" id={`fo-panel-${activeTab}`} aria-labelledby={`fo-tab-${activeTab}`}>
        <div hidden={activeTab !== 'office'}>{visited.has('office') && <YourOffice />}</div>
        <div hidden={activeTab !== 'league'}>{visited.has('league') && <LeagueGMs />}</div>
        <div hidden={activeTab !== 'market'}>{visited.has('market') && <JobsPanel />}</div>
      </div>
    </div>
  );
};
