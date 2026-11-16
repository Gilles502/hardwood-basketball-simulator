// File: frontend/src/pages/Database.tsx
// Player Database: every player and every season in the save (core/database_view.py). Views in pages/database/.
// A player opens inside the page (breadcrumb + Back); the views stay mounted so their filters survive the trip.
import React, { useEffect, useState } from 'react';
import { DashboardTabs } from '../components/DashboardTabs';
import { useLeagueStore } from '../store/leagueStore';
import { PlayerPage } from './database/PlayerPage';
import { PlayersTab } from './database/PlayersTab';
import { SeasonsTab } from './database/SeasonsTab';
import { StatFinderTab } from './database/StatFinderTab';
import type { OpenPlayer } from './database/types';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './analytics/Analytics.css';
import './database/Database.css';

type DatabaseTab = 'players' | 'seasons' | 'finder';

const TABS: { id: DatabaseTab; label: string }[] = [
  { id: 'players', label: 'Players' },
  { id: 'seasons', label: 'Seasons' },
  { id: 'finder', label: 'Stat Finder' },
];

export const Database: React.FC = () => {
  const [activeTab, setActiveTab] = useState<DatabaseTab>('players');
  const [visited, setVisited] = useState<Set<DatabaseTab>>(() => new Set(['players']));
  const [player, setPlayer] = useState<OpenPlayer | null>(null);
  const databaseTarget = useLeagueStore((s) => s.databaseTarget);
  const openInDatabase = useLeagueStore((s) => s.openInDatabase);

  // Sent here by the player popup: open that player, then clear the request
  useEffect(() => {
    if (!databaseTarget) return;
    setPlayer(databaseTarget);
    openInDatabase(null);
  }, [databaseTarget, openInDatabase]);

  const pickTab = (id: DatabaseTab) => {
    setActiveTab(id);
    setPlayer(null);
    setVisited((v) => (v.has(id) ? v : new Set(v).add(id)));
  };
  const openPlayer = (slug: string, name: string) => {
    setPlayer({ slug, name });
    window.scrollTo({ top: 0 });
  };
  const tabLabel = TABS.find((t) => t.id === activeTab)?.label;

  return (
    <div>
      <div className="dash-header">
        <div>
          <h1 className="dash-title">Player Database</h1>
          <span className="dash-subtitle">Every player and every season in this save</span>
        </div>
      </div>

      <DashboardTabs
        idPrefix="db"
        ariaLabel="Player Database sections"
        active={activeTab}
        onChange={(id) => pickTab(id as DatabaseTab)}
        tabs={TABS}
      />

      <div role="tabpanel" id={`db-panel-${activeTab}`} aria-labelledby={`db-tab-${activeTab}`}>
        {player && (
          <>
            <nav className="db-crumb" aria-label="Breadcrumb">
              <button type="button" className="db-back" onClick={() => setPlayer(null)}>← Back</button>
              <span>Player Database</span><span aria-hidden="true">›</span>
              <button type="button" className="an-link" onClick={() => setPlayer(null)}>{tabLabel}</button>
              <span aria-hidden="true">›</span><b>{player.name}</b>
            </nav>
            <PlayerPage key={player.slug} slug={player.slug} onOpenPlayer={openPlayer} />
          </>
        )}
        <div hidden={!!player || activeTab !== 'players'}>{visited.has('players') && <PlayersTab onOpenPlayer={openPlayer} />}</div>
        <div hidden={!!player || activeTab !== 'seasons'}>{visited.has('seasons') && <SeasonsTab onOpenPlayer={openPlayer} />}</div>
        <div hidden={!!player || activeTab !== 'finder'}>{visited.has('finder') && <StatFinderTab onOpenPlayer={openPlayer} />}</div>
      </div>
    </div>
  );
};
