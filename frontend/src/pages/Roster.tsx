import React, { useState, useEffect } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { DashboardTabs } from '../components/DashboardTabs';
import { ContractsTab } from './roster/ContractsTab';
import { StrategyTab } from './roster/StrategyTab';
import { CardsTab } from './roster/CardsTab';
import { DevelopmentTab } from './roster/DevelopmentTab';
import type { TeamIntel } from './roster/StrategyTab';
import type { TradeTarget } from './Trades';
import { ordinal } from '../utils/format';
import './dashboard/Dashboard.css'; // dash-header / dash-tabs, shared with the Dashboard
import './roster/Roster.css';

type RosterTab = 'roster' | 'strategy' | 'cards' | 'development';

interface RosterProps {
  onTradeFor: (target: TradeTarget) => void;
}

export const Roster: React.FC<RosterProps> = ({ onTradeFor }) => {
  const { leagueData, loading, fetchLeagueData, openPlayerProfile } = useLeagueStore();
  const [selectedTeamName, setSelectedTeamName] = useState<string>('');
  const [activeTab, setActiveTab] = useState<RosterTab>('roster');
  const [teamIntel, setTeamIntel] = useState<TeamIntel | null>(null);
  const [loadingIntel, setLoadingIntel] = useState<boolean>(false);

  useEffect(() => {
    if (!leagueData) {
      fetchLeagueData();
    } else if (leagueData && !selectedTeamName) {
      setSelectedTeamName(leagueData.player_team_name || leagueData.league_database?.teams[0]?.nome || '');
    }
  }, [leagueData, selectedTeamName, fetchLeagueData]);

  useEffect(() => {
    if (selectedTeamName) {
      // Switching teams quickly must not let an older response overwrite the newer one.
      let cancelled = false;
      setLoadingIntel(true);
      fetch(`/api/team-strategy-intel?team_name=${encodeURIComponent(selectedTeamName)}`)
        .then(res => res.json())
        .then(data => {
          if (cancelled) return;
          setTeamIntel(data);
          setLoadingIntel(false);
        })
        .catch(err => {
          if (cancelled) return;
          console.error("Error fetching team strategy intel:", err);
          setLoadingIntel(false);
        });
      return () => { cancelled = true; };
    }
  }, [selectedTeamName]);

  if (loading && !leagueData) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  const teams = leagueData?.league_database?.teams || [];
  const selectedTeam = teams.find(t => t.nome === selectedTeamName);

  // Intel only counts once it belongs to the team on screen.
  const intelForTeam = teamIntel && teamIntel.team_name === selectedTeamName ? teamIntel : null;
  const financials = intelForTeam?.financials ?? null;

  const year = leagueData?.anno_corrente;
  const seasonLabel = year ? `${year}–${String((year + 1) % 100).padStart(2, '0')}` : null;

  const standing = (() => {
    if (!selectedTeam || selectedTeam.record === '0-0') return null;
    for (const [conf, label] of [['east', 'East'], ['west', 'West']] as const) {
      const row = leagueData?.classifica?.[conf]?.find(t => t.nome === selectedTeam.nome);
      if (row) return `${ordinal(row.pos)} in the ${label}`;
    }
    return null;
  })();

  return (
    <div>
      <div className="dash-header">
        <div>
          <h1 className="dash-title">Roster &amp; Strategy</h1>
          <span className="dash-subtitle">
            {selectedTeam ? `${selectedTeam.nome} · ${selectedTeam.record.replace('-', '–')}${standing ? ` · ${standing}` : ''}` : 'Contracts, picks, team direction and player development'}
          </span>
        </div>
        <div className="dash-badges">
          <select
            className="rs-team-select"
            value={selectedTeamName}
            onChange={(e) => setSelectedTeamName(e.target.value)}
            aria-label="Team"
          >
            {teams.map(t => (
              <option key={t.nome} value={t.nome}>
                {t.nome}{leagueData?.player_team_name === t.nome ? ' (You)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      <DashboardTabs
        idPrefix="rs"
        ariaLabel="Roster sections"
        active={activeTab}
        onChange={(id) => setActiveTab(id as RosterTab)}
        tabs={[
          { id: 'roster', label: 'Roster & Contracts' },
          { id: 'strategy', label: 'Strategy & Intel' },
          { id: 'cards', label: 'Player Cards' },
          { id: 'development', label: 'Development' },
        ]}
      />

      {selectedTeam && activeTab === 'roster' && (
        <div role="tabpanel" id="rs-panel-roster" aria-labelledby="rs-tab-roster">
          <ContractsTab
            team={selectedTeam}
            financials={financials}
            standing={standing}
            onOpenPlayer={openPlayerProfile}
          />
        </div>
      )}

      {selectedTeam && activeTab === 'strategy' && (
        <div role="tabpanel" id="rs-panel-strategy" aria-labelledby="rs-tab-strategy">
          {intelForTeam ? (
            <StrategyTab
              intel={intelForTeam}
              isOwnTeam={selectedTeam.nome === leagueData?.player_team_name}
              seasonLabel={seasonLabel}
              onOpenPlayer={openPlayerProfile}
              onTradeFor={(player) => onTradeFor({ team: selectedTeam.nome, player })}
            />
          ) : loadingIntel ? (
            <div className="st-state"><div className="spinner"></div></div>
          ) : (
            <div className="st-state">Couldn't load the scouting intel for {selectedTeam.nome}.</div>
          )}
        </div>
      )}

      {selectedTeam && activeTab === 'development' && (
        <div role="tabpanel" id="rs-panel-development" aria-labelledby="rs-tab-development">
          <DevelopmentTab roster={selectedTeam.roster} onOpenPlayer={openPlayerProfile} />
        </div>
      )}

      {selectedTeam && activeTab === 'cards' && (
        <div role="tabpanel" id="rs-panel-cards" aria-labelledby="rs-tab-cards">
          <CardsTab teamName={selectedTeam.nome} roster={selectedTeam.roster} onOpenPlayer={openPlayerProfile} />
        </div>
      )}

    </div>
  );
};

