// File: frontend/src/App.tsx
import { useState, useEffect } from 'react';
import { Dashboard } from './pages/Dashboard';
import { TeamSelection } from './pages/TeamSelection';
import { Roster } from './pages/Roster';
import { Database } from './pages/Database';
import { Analytics } from './pages/Analytics';
import { History } from './pages/History';
import { Economy } from './pages/Economy';
import { Trades } from './pages/Trades';
import type { TradeTarget } from './pages/Trades';
import { Rotations } from './pages/Rotations';
import type { RotationsTab } from './pages/Rotations';
import { Awards } from './pages/Awards';
import { Playoffs } from './pages/Playoffs';
import { AllStar } from './pages/AllStar';
import { EndOfSeasonHub } from './pages/EndOfSeasonHub';
import { MainMenu } from './pages/MainMenu';
import { Scouting } from './pages/Scouting';
import { Coaching } from './pages/Coaching';
import { Board } from './pages/Board';
import { CalendarView } from './pages/Calendar';
import { GMJobMarketModal } from './components/GMJobMarketModal';
import { useLeagueStore } from './store/leagueStore';
import { useSettingsStore } from './store/settingsStore';
import { PlayerProfileModal } from './components/PlayerProfileModal';
import { TeamProfileModal } from './components/TeamProfileModal';
import { LoadGameModal } from './components/LoadGameModal';
import { SettingsModal } from './components/SettingsModal';
import { ExportDataModal } from './components/ExportDataModal';
import { Save } from 'lucide-react';
import { AppSidebar } from './components/AppSidebar';
import { SimRunBar } from './components/SimRunBar';
import { useSimRunning } from './hooks/useSimRunning';
import { useLiveSummary } from './hooks/useLiveSummary';
import type { Tab } from './navigation';
import './styles/ember-theme.css';
import './App.css';


function App() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  // Which Tactical Board tab opens next (the playoff page jumps straight to Opponent)
  const [rotationsTab, setRotationsTab] = useState<RotationsTab>('lineup');
  useEffect(() => {
    if (activeTab !== 'rotations') setRotationsTab('lineup');
  }, [activeTab]);
  // Player the Trade Machine opens on ("Trade for" on Roster > Strategy & Intel)
  const [tradeTarget, setTradeTarget] = useState<TradeTarget | null>(null);
  useEffect(() => {
    if (activeTab !== 'trades') setTradeTarget(null);
  }, [activeTab]);
  const [hasStarted, setHasStarted] = useState(false);
  const [showSavesModal, setShowSavesModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [saveToast, setSaveToast] = useState<string | null>(null);
  const [showGMJobMarketModal, setShowGMJobMarketModal] = useState(false);
  const [gmJobOffers, setGmJobOffers] = useState<any[]>([]);
  const [isGMFired, setIsGMFired] = useState(false);
  const [firingMessage, setFiringMessage] = useState<string | null>(null);
  const [showManualTeamSelection, setShowManualTeamSelection] = useState(false);
  const { leagueData, loading, selectedPlayerName, selectedTeamName, openPlayerProfile, openTeamProfile, fetchLeagueData, saveGame } = useLeagueStore();
  const { initSettings } = useSettingsStore();
  const databaseTarget = useLeagueStore((s) => s.databaseTarget);
  const pageTarget = useLeagueStore((s) => s.pageTarget);

  // The player popup's "Open in Player Database" asks for the database page; the page opens the player itself
  useEffect(() => {
    if (databaseTarget) setActiveTab('explore');
  }, [databaseTarget]);

  // The team card's Trophy Room / Team analytics buttons; the page opens the team itself
  useEffect(() => {
    if (pageTarget) setActiveTab(pageTarget.page);
  }, [pageTarget]);

  useEffect(() => {
    initSettings();
  }, [initSettings]);

  useLiveSummary(hasStarted);
  // During a live sim run leagueData changes every day: the board check waits for the run's final full payload.
  const runGoing = useSimRunning();

  useEffect(() => {
    if (!leagueData) {
      fetchLeagueData();
    } else if (leagueData && !runGoing) {
      if (leagueData.player_team_name) {
        setShowManualTeamSelection(false);
      }
      // Verifica se il GM è licenziato
      if (leagueData.is_fired) {
        fetch('/api/board')
          .then(res => res.json())
          .then(data => {
            if (data && (data.is_fired || leagueData.is_fired)) {
              setIsGMFired(true);
              setGmJobOffers(data.job_offers || []);
              setFiringMessage(data.firing_info?.message || leagueData.firing_info?.message || "The franchise Board of Governors has relieved you of your duties as General Manager. Review incoming front office offers or choose a new franchise.");
              setShowGMJobMarketModal(true);
            }
          })
          .catch(err => console.error("Error checking GM Board status:", err));
      } else if (leagueData.player_team_name) {
        fetch('/api/board')
          .then(res => res.json())
          .then(data => {
            if (data && (data.is_fired || (data.job_offers && data.job_offers.length > 0 && data.user_gm_profile?.contract?.years_remaining <= 0))) {
              setIsGMFired(!!data.is_fired);
              setGmJobOffers(data.job_offers || []);
              setFiringMessage(data.firing_info?.message || (data.is_fired ? "The franchise Board of Governors has terminated your tenure as General Manager." : "Your front office executive contract has expired."));
              setShowGMJobMarketModal(true);
            }
          })
          .catch(err => console.error("Error checking GM Board status:", err));
      } else {
        setIsGMFired(false);
        setShowGMJobMarketModal(false);
      }
    }
  }, [leagueData, fetchLeagueData, runGoing]);


  if (loading && !leagueData) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100vh / var(--ui-zoom, 1))', width: 'calc(100vw / var(--ui-zoom, 1))', backgroundColor: '#09090b' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  if (!hasStarted) {
    return <MainMenu onEnter={() => setHasStarted(true)} />;
  }

  if ((leagueData && !leagueData.player_team_name && !leagueData.is_spectator && !showGMJobMarketModal) || showManualTeamSelection) {
    return <TeamSelection />;
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard onNavigate={setActiveTab} />;
      case 'roster':
        return <Roster onTradeFor={(target) => { setTradeTarget(target); setActiveTab('trades'); }} />;
      case 'rotations':
        return <Rotations initialTab={rotationsTab} />;
      case 'economy':
        return <Economy />;
      case 'trades':
        return <Trades initialTarget={tradeTarget} />;
      case 'explore':
        return <Database />;
      case 'analytics':
        return <Analytics />;
      case 'awards':
        return <Awards />;
      case 'playoffs':
        return <Playoffs onOpenGameplan={() => { setRotationsTab('opponent'); setActiveTab('rotations'); }} onOpenHub={() => setActiveTab('offseason')} />;
      case 'allstar':
        return <AllStar />;
      case 'offseason':
        return <EndOfSeasonHub onNavigate={setActiveTab} />;
      case 'scouting':
        return <Scouting />;
      case 'coaching':
        return <Coaching />;
      case 'board':
        return <Board />;
      case 'history':
        return <History />;
      case 'calendar':
        return <CalendarView />;

      default:
        return <Dashboard onNavigate={setActiveTab} />;
    }
  };

  const handleQuickSave = async () => {
    try {
      const res = await saveGame();
      if (res.success) {
        setSaveToast(`Save '${res.metadata?.display_name || 'League'}' completed!`);
        setTimeout(() => setSaveToast(null), 3500);
      }
    } catch (err) {
      console.error("Quick save error:", err);
    }
  };

  return (
    <div className="app-container ember-theme">
      {/* Toast Notification for Quick Save */}
      {saveToast && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          background: 'var(--success)',
          color: '#06210f',
          padding: '12px 20px',
          borderRadius: '10px',
          fontWeight: 600,
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.45)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          animation: 'fadeIn 0.3s ease'
        }}>
          <Save size={18} />
          <span>{saveToast}</span>
        </div>
      )}

      {/* Left Sidebar Navigation */}
      <AppSidebar
        activeTab={activeTab}
        onSelect={setActiveTab}
        onQuickSave={handleQuickSave}
        onOpenSaves={() => setShowSavesModal(true)}
        onOpenExport={() => setShowExportModal(true)}
        onOpenSettings={() => setShowSettingsModal(true)}
        onMainMenu={() => setHasStarted(false)}
      />

      {/* Main Content Area */}
      <main className="main-content">
        <SimRunBar />
        {renderContent()}
      </main>

      {/* Global Profile Modals */}
      {selectedPlayerName && (
        <PlayerProfileModal
          playerName={selectedPlayerName}
          onClose={() => openPlayerProfile(null)}
        />
      )}

      {selectedTeamName && (
        <TeamProfileModal
          teamName={selectedTeamName}
          onClose={() => openTeamProfile(null)}
        />
      )}


      {/* Save & Load Manager Modal */}
      <LoadGameModal
        isOpen={showSavesModal}
        onClose={() => setShowSavesModal(false)}
        onLoadSuccess={() => {
          fetchLeagueData();
        }}
      />

      {/* In-Game Settings Modal */}
      <SettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
      />

      {/* Season Data Exporter Modal */}
      <ExportDataModal
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
        seasonNumber={leagueData?.season_number ?? 1}
        calendarYear={leagueData?.anno_corrente ?? 2025}
      />

      {/* GM Job Market / Firing Modal */}
      {showGMJobMarketModal && (
        <GMJobMarketModal
          isFired={isGMFired}
          firingMessage={firingMessage}
          jobOffers={gmJobOffers}
          onClose={() => setShowGMJobMarketModal(false)}
          onChooseManualTeam={() => {
            setShowGMJobMarketModal(false);
            setShowManualTeamSelection(true);
          }}
        />
      )}
    </div>
  );
}


export default App;
