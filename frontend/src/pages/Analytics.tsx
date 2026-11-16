// File: frontend/src/pages/Analytics.tsx
// League Analytics: a stat lab built from the season's box scores (core/analytics_view.py). Tabs in pages/analytics/.
import React, { useEffect, useState } from 'react';
import { DashboardTabs } from '../components/DashboardTabs';
import { useLeagueStore } from '../store/leagueStore';
import { LeagueMapTab } from './analytics/LeagueMapTab';
import { PlayersTab } from './analytics/PlayersTab';
import { SplitsTab } from './analytics/SplitsTab';
import { TeamsTab } from './analytics/TeamsTab';
import type { SplitsTarget } from './analytics/types';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './analytics/Analytics.css';

type AnalyticsTab = 'players' | 'teams' | 'splits' | 'map';
/** Regular season or playoffs: Players and Teams only (Splits and the League Map read dates the playoffs lack). */
export type SeasonKind = 'rs' | 'po';

const TABS: { id: AnalyticsTab; label: string }[] = [
  { id: 'players', label: 'Players' },
  { id: 'teams', label: 'Teams' },
  { id: 'splits', label: 'Splits & Logs' },
  { id: 'map', label: 'League Map' },
];

export const Analytics: React.FC = () => {
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('players');
  const [splitsTarget, setSplitsTarget] = useState<SplitsTarget | null>(null);
  const [focusTeam, setFocusTeam] = useState<string | null>(null);
  const [kind, setKind] = useState<SeasonKind>('rs');

  const openSplits = (kind: SplitsTarget['kind'], name: string) => {
    setSplitsTarget({ kind, name });
    setActiveTab('splits');
  };

  const openTeam = (name: string) => {
    setFocusTeam(name);
    setActiveTab('teams');
  };

  // Sent here by the team card's "Team analytics" button
  const pageTarget = useLeagueStore((s) => s.pageTarget);
  const openTeamPage = useLeagueStore((s) => s.openTeamPage);
  useEffect(() => {
    if (pageTarget?.page !== 'analytics') return;
    setFocusTeam(pageTarget.team);
    setActiveTab('teams');
    openTeamPage(null);
  }, [pageTarget, openTeamPage]);

  return (
    <div>
      <div className="dash-header">
        <div>
          <h1 className="dash-title">League Analytics</h1>
          <span className="dash-subtitle">Every number the season has produced, from every box score</span>
        </div>
        {(activeTab === 'players' || activeTab === 'teams') && (
          <div className="an-views" role="group" aria-label="Season type">
            <button type="button" aria-pressed={kind === 'rs'} onClick={() => setKind('rs')}>Regular season</button>
            <button type="button" aria-pressed={kind === 'po'} onClick={() => setKind('po')}>Playoffs</button>
          </div>
        )}
      </div>

      <DashboardTabs
        idPrefix="an"
        ariaLabel="League Analytics sections"
        active={activeTab}
        onChange={(id) => setActiveTab(id as AnalyticsTab)}
        tabs={TABS}
      />

      <div role="tabpanel" id={`an-panel-${activeTab}`} aria-labelledby={`an-tab-${activeTab}`}>
        {activeTab === 'players' && <PlayersTab kind={kind} onOpenSplits={(name) => openSplits('player', name)} />}
        {activeTab === 'teams' && <TeamsTab kind={kind} focusTeam={focusTeam} onOpenSplits={(name) => openSplits('team', name)} />}
        {activeTab === 'splits' && <SplitsTab target={splitsTarget} onTarget={setSplitsTarget} />}
        {activeTab === 'map' && <LeagueMapTab onOpenTeam={openTeam} />}
      </div>
    </div>
  );
};
