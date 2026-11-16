// File: frontend/src/pages/MainMenu.tsx
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { useSettingsStore } from '../store/settingsStore';
import { t } from '../utils/i18n';
import { BRAND } from '../brand';
import { HardwoodLogo } from '../components/HardwoodLogo';
import {
  Play,
  Sparkles,
  HardDrive,
  FolderArchive,
  BookOpen,
  Cog,
  Shield
} from 'lucide-react';
import { LoadGameModal } from '../components/LoadGameModal';
import { CbaRulebookModal } from '../components/CbaRulebookModal';
import { RosterModHubModal } from '../components/RosterModHubModal';
import { SettingsModal } from '../components/SettingsModal';
import { SetupWizardModal } from '../components/SetupWizardModal';
import { ChangelogModal } from '../components/ChangelogModal';
import { TeamCrest } from '../components/TeamCrest';
import { WhatsNewCard } from '../components/WhatsNewCard';
import '../styles/ember-theme.css';
import './MainMenu.css';

interface MainMenuProps {
  onEnter: () => void;
}

interface MenuEntry {
  key: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  onClick: () => void;
  primary?: boolean;
  disabled?: boolean;
  tooltip?: string;
}

export const MainMenu: React.FC<MainMenuProps> = ({ onEnter }) => {
  const {
    leagueData,
    saves,
    activeSaveName,
    fetchSaves,
    loadGame
  } = useLeagueStore();

  const { language } = useSettingsStore();

  // Modals state
  const [showLoadModal, setShowLoadModal] = useState(false);
  const [showRulebookModal, setShowRulebookModal] = useState(false);
  const [showModHubModal, setShowModHubModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showNewCareerModal, setShowNewCareerModal] = useState(false);
  const [showChangelogModal, setShowChangelogModal] = useState(false);


  useEffect(() => {
    fetchSaves();
  }, []);

  // Determine active save for Spotlight
  const activeSave = saves.find(s => s.save_name === activeSaveName) || (saves.length > 0 ? saves[0] : null);
  const hasCareer = !!(activeSave || (leagueData && (leagueData.player_team_name || leagueData.is_spectator)));

  const handleContinue = async () => {
    if (activeSave && activeSave.save_name !== activeSaveName) {
      try {
        const data = await loadGame(activeSave.save_name);
        if (data?.warning) window.alert(data.warning);
      } catch (e) {
        console.error("Error loading save:", e);
      }
    }
    onEnter();
  };


  const formatDate = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString(language === 'it' ? 'it-IT' : 'en-US', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
      });
    } catch {
      return isoStr;
    }
  };

  const entries: MenuEntry[] = [
    {
      key: 'continue',
      icon: <Play size={18} fill={hasCareer ? 'currentColor' : 'transparent'} />,
      title: t('menu_continue', language),
      description: activeSave
        ? `${activeSave.player_team_name || activeSave.display_name} (${activeSave.player_team_record || 'N/A'})`
        : (leagueData?.player_team_name || t('menu_continue_desc', language)),
      onClick: handleContinue,
      primary: true,
      disabled: !hasCareer,
      tooltip: !hasCareer ? t('active_career_empty', language) : '',
    },
    {
      key: 'new',
      icon: <Sparkles size={18} />,
      title: t('menu_new_game', language),
      description: t('menu_new_game_desc', language),
      onClick: () => setShowNewCareerModal(true),
    },
    {
      key: 'load',
      icon: <HardDrive size={18} />,
      title: t('menu_load_game', language),
      description: t('menu_load_game_desc', language),
      onClick: () => setShowLoadModal(true),
    },
    {
      key: 'mods',
      icon: <FolderArchive size={18} />,
      title: t('menu_roster_hub', language),
      description: t('menu_roster_hub_desc', language),
      onClick: () => setShowModHubModal(true),
    },
    {
      key: 'rulebook',
      icon: <BookOpen size={18} />,
      title: t('menu_rulebook', language),
      description: t('menu_rulebook_desc', language),
      onClick: () => setShowRulebookModal(true),
    },
    {
      key: 'settings',
      icon: <Cog size={18} />,
      title: t('menu_settings', language),
      description: t('menu_settings_desc', language),
      onClick: () => setShowSettingsModal(true),
    },
  ];

  return (
    <>
      {/* Themed menu: the Hardwood & Ember tokens are scoped to this element only. */}
      <div className="mainmenu-container ember-theme">
        {/* Background Graphic Lines */}
        <div className="mainmenu-backdrop" />
        <div className="mainmenu-court-lines" />

        {/* Left Sidebar Menu */}
        <aside className="mainmenu-sidebar">
          <div className="mainmenu-brand">
            <HardwoodLogo size={52} className="mainmenu-logo" />
            <h1 className="mainmenu-wordmark">
              {BRAND.nameLines.map((line, index) => (
                <span key={line} className={index === 1 ? 'mainmenu-wordmark-accent' : undefined}>{line}</span>
              ))}
            </h1>
            <div className="mainmenu-version">{BRAND.version}</div>
          </div>

          <nav className="mainmenu-nav">
            {entries.map((entry) => (
              <button
                key={entry.key}
                className={`mainmenu-btn${entry.primary ? ' mainmenu-btn-primary' : ''}`}
                onClick={entry.onClick}
                disabled={entry.disabled}
                title={entry.tooltip}
              >
                <div className="mainmenu-btn-icon">{entry.icon}</div>
                <div className="mainmenu-btn-text">
                  <h3>{entry.title}</h3>
                  <p>{entry.description}</p>
                </div>
              </button>
            ))}
          </nav>
        </aside>

        {/* Right Spotlight / Hero Area */}
        <main className="mainmenu-main">
          {activeSave ? (
            <div className="mainmenu-spotlight-card fade-in">
              <div className="spotlight-badge">
                <Shield size={13} />
                <span>{t('active_career_spotlight', language)}</span>
              </div>

              <div className="spotlight-title-row">
                <TeamCrest name={activeSave.player_team_name || activeSave.display_name} size={56} />
                <h2 className="spotlight-team-title">
                  {activeSave.player_team_name || activeSave.display_name}
                </h2>
              </div>

              <div className="spotlight-meta-grid">
                <div className="spotlight-meta-item">
                  <span>{t('season_label', language)}</span>
                  <strong>{activeSave.season} ({activeSave.phase})</strong>
                </div>
                <div className="spotlight-meta-item">
                  <span>{t('record_label', language)}</span>
                  <strong className="spotlight-record">{activeSave.player_team_record || 'N/A'}</strong>
                </div>
                <div className="spotlight-meta-item">
                  <span>{t('last_saved_label', language)}</span>
                  <strong className="spotlight-date">{formatDate(activeSave.last_saved)}</strong>
                </div>
              </div>

              <button
                className="spotlight-btn-continue"
                onClick={handleContinue}
              >
                <Play size={16} fill="currentColor" />
                <span>{t('quick_continue', language)}</span>
              </button>
            </div>
          ) : (
            <div className="mainmenu-empty-spotlight fade-in">
              <h2 className="empty-spotlight-title">
                {BRAND.name}
              </h2>
              <p className="empty-spotlight-desc">
                Take over a franchise, manage the roster, the salary cap and the trade market, and build a dynasty.
              </p>
              <button
                className="spotlight-btn-continue"
                onClick={() => setShowNewCareerModal(true)}
              >
                <Sparkles size={16} />
                <span>{t('menu_new_game', language)}</span>
              </button>
            </div>
          )}

          <WhatsNewCard onViewAll={() => setShowChangelogModal(true)} />
        </main>

        <ChangelogModal
          isOpen={showChangelogModal}
          onClose={() => setShowChangelogModal(false)}
        />
      </div>

      {/* Existing modals live outside the themed container so they keep their current look. */}
      <SetupWizardModal
        isOpen={showNewCareerModal}
        onClose={() => setShowNewCareerModal(false)}
        onCareerStarted={onEnter}
      />

      <LoadGameModal
        isOpen={showLoadModal}
        onClose={() => setShowLoadModal(false)}
        onLoadSuccess={onEnter}
      />

      <CbaRulebookModal
        isOpen={showRulebookModal}
        onClose={() => setShowRulebookModal(false)}
      />

      <RosterModHubModal
        isOpen={showModHubModal}
        onClose={() => setShowModHubModal(false)}
      />

      <SettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
      />
    </>
  );
};
