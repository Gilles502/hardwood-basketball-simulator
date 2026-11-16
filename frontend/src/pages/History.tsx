// File: frontend/src/pages/History.tsx
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { DashboardTabs } from '../components/DashboardTabs';
import { TrophyRoomTab } from './history/TrophyRoomTab';
import { ChampionshipsTab } from './history/ChampionshipsTab';
import { HallOfFameTab } from './history/HallOfFameTab';
import { RecordsTab } from './history/RecordsTab';
import { LeadersTab } from './history/LeadersTab';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './history/History.css';

type HistoryTab = 'history' | 'trophy_room' | 'hof' | 'records' | 'leaders';

const TABS: { id: HistoryTab; label: string }[] = [
  { id: 'history', label: 'Championship History' },
  { id: 'trophy_room', label: 'Trophy Room & Franchises' },
  { id: 'hof', label: 'Hall of Fame' },
  { id: 'records', label: 'League Records' },
  { id: 'leaders', label: 'All-Time Leaders' },
];

export const History: React.FC = () => {
  const [activeTab, setActiveTab] = useState<HistoryTab>('history');
  const [trophyTeam, setTrophyTeam] = useState<string | undefined>(undefined);
  const pageTarget = useLeagueStore((s) => s.pageTarget);
  const openTeamPage = useLeagueStore((s) => s.openTeamPage);

  // Sent here by the team card's "Trophy Room" button
  useEffect(() => {
    if (pageTarget?.page !== 'history') return;
    setTrophyTeam(pageTarget.team);
    setActiveTab('trophy_room');
    openTeamPage(null);
  }, [pageTarget, openTeamPage]);

  return (
    <div>
      <div className="dash-header">
        <div>
          <h1 className="dash-title">History</h1>
          <span className="dash-subtitle">Champions, legends and records of your league</span>
        </div>
      </div>

      <DashboardTabs
        idPrefix="hist"
        ariaLabel="History sections"
        active={activeTab}
        onChange={(id) => setActiveTab(id as HistoryTab)}
        tabs={TABS}
      />

      <div role="tabpanel" id={`hist-panel-${activeTab}`} aria-labelledby={`hist-tab-${activeTab}`}>
        {activeTab === 'history' && <ChampionshipsTab />}
        {activeTab === 'trophy_room' && <TrophyRoomTab key={trophyTeam ?? ''} initialTeam={trophyTeam} />}
        {activeTab === 'hof' && <HallOfFameTab />}
        {activeTab === 'records' && <RecordsTab />}
        {activeTab === 'leaders' && <LeadersTab />}
      </div>
    </div>
  );
};
