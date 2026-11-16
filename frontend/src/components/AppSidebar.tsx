import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, Download, HardDrive, LayoutDashboard, LogOut, Save, Settings } from 'lucide-react';
import { BRAND } from '../brand';
import { useLeagueStore } from '../store/leagueStore';
import { useLiveStore } from '../store/liveStore';
import { NAV_GROUPS, groupOfTab } from '../navigation';
import type { BadgeKey, Tab } from '../navigation';
import { formatGameDate, ordinal } from '../utils/format';
import { TeamCrest } from './TeamCrest';
import { HardwoodLogo } from './HardwoodLogo';
import { LiveDot } from './LiveDot';
import { useSimRunning, SIM_LOCK_HINT } from '../hooks/useSimRunning';
import './AppSidebar.css';

const STORAGE_KEY = 'ubs_sidebar_groups';

const BADGE_LABEL: Record<BadgeKey, string> = {
  injuries: 'injured players',
  trade_offers: 'open trade offers',
  board: 'open board concern',
  offseason: 'offseason step waiting',
};

function loadGroupState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveGroupState(state: Record<string, boolean>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Remembering open groups is a convenience only.
  }
}

interface AppSidebarProps {
  activeTab: Tab;
  onSelect: (tab: Tab) => void;
  onQuickSave: () => void;
  onOpenSaves: () => void;
  onOpenExport: () => void;
  onOpenSettings: () => void;
  onMainMenu: () => void;
}

export const AppSidebar: React.FC<AppSidebarProps> = ({
  activeTab, onSelect, onQuickSave, onOpenSaves, onOpenExport, onOpenSettings, onMainMenu,
}) => {
  const summary = useLiveStore((state) => state.summary);
  // Saving, loading and leaving the game wait for the live sim run to end (the server refuses them meanwhile).
  const runGoing = useSimRunning();
  const status = useLiveStore((state) => state.status);
  const leagueData = useLeagueStore((state) => state.leagueData);
  const [groupState, setGroupState] = useState<Record<string, boolean>>(loadGroupState);
  const navRef = useRef<HTMLElement>(null);

  // On small windows the nav list scrolls: keep the active page in view.
  useEffect(() => {
    navRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: 'nearest' });
  }, [activeTab]);

  const activeGroup = groupOfTab(activeTab);
  const isOpen = (id: string, defaultOpen: boolean) => id === activeGroup || (groupState[id] ?? defaultOpen);

  const toggleGroup = (id: string, defaultOpen: boolean) => {
    const next = { ...groupState, [id]: !(groupState[id] ?? defaultOpen) };
    setGroupState(next);
    saveGroupState(next);
  };

  const badgeCount = (key: BadgeKey | undefined): number => {
    if (key === 'offseason') return leagueData?.end_season?.open ? 1 : 0;
    if (!key || !summary) return 0;
    if (key === 'injuries') return summary.attention.injuries.length;
    if (key === 'trade_offers') return summary.attention.trade_offers;
    return summary.attention.board_concern ? 1 : 0;
  };

  const team = summary?.team ?? null;
  const teamName = team?.name ?? leagueData?.player_team_name ?? null;
  const played = team ? team.record !== '0-0' : false;
  const standingText = team && team.conference
    ? (played && team.conf_rank ? `${ordinal(team.conf_rank)} ${team.conference}` : team.conference)
    : '';
  const dateText = formatGameDate(summary?.date);

  return (
    <aside className="sidebar as-sidebar">
      <div className="as-brand">
        <HardwoodLogo size={30} className="as-logo" />
        <div className="as-wordmark">
          {BRAND.nameLines.map((line, index) => (
            <span key={line} className={index === 1 ? 'as-wordmark-accent' : undefined}>{line}</span>
          ))}
        </div>
      </div>

      <div className="as-team">
        {teamName ? (
          <>
            <TeamCrest name={teamName} size={38} />
            <div className="as-team-text">
              <div className="as-team-name" title={teamName}>{teamName}</div>
              <div className="as-team-meta">{team ? `${team.record}${standingText ? ` · ${standingText}` : ''}` : ''}</div>
            </div>
          </>
        ) : (
          <div className="as-team-text">
            <div className="as-team-name">Spectator</div>
            <div className="as-team-meta">Season {leagueData?.stagione ?? ''}</div>
          </div>
        )}
      </div>
      <div className="as-dateline">
        <span>{dateText}</span>
        <LiveDot status={status} />
      </div>

      <nav className="as-nav" aria-label="Main navigation" ref={navRef}>
        <button
          className={`as-item${activeTab === 'dashboard' ? ' is-active' : ''}`}
          onClick={() => onSelect('dashboard')}
          aria-current={activeTab === 'dashboard' ? 'page' : undefined}
        >
          <LayoutDashboard size={16} />
          <span>Dashboard</span>
        </button>

        {NAV_GROUPS.map((group) => {
          const open = isOpen(group.id, group.defaultOpen);
          return (
            <div key={group.id} className="as-group">
              <button
                className="as-group-head"
                onClick={() => toggleGroup(group.id, group.defaultOpen)}
                aria-expanded={open}
                aria-controls={`as-group-${group.id}`}
              >
                <span>{group.label}</span>
                <ChevronDown size={14} className={open ? 'as-chevron' : 'as-chevron is-closed'} />
              </button>
              {open && (
                <div id={`as-group-${group.id}`}>
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const count = badgeCount(item.badge);
                    return (
                      <button
                        key={item.id}
                        className={`as-item${activeTab === item.id ? ' is-active' : ''}`}
                        onClick={() => onSelect(item.id)}
                        aria-current={activeTab === item.id ? 'page' : undefined}
                      >
                        <Icon size={16} />
                        <span>{item.label}</span>
                        {count > 0 && item.badge && (
                          <span
                            className={`as-badge${item.badge === 'injuries' ? ' as-badge-danger' : ''}`}
                            aria-label={`${count} ${BADGE_LABEL[item.badge]}`}
                          >
                            {item.badge === 'board' || item.badge === 'offseason' ? '!' : count}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="as-footer">
        <div className="as-footer-actions">
          <button className="as-quicksave" onClick={onQuickSave} disabled={runGoing} title={runGoing ? SIM_LOCK_HINT : 'Quick save active game'}>
            <Save size={15} />
            <span>Quick Save</span>
          </button>
          <button className="as-icon-btn" onClick={onOpenSaves} disabled={runGoing} title={runGoing ? SIM_LOCK_HINT : 'Save Manager'} aria-label="Save Manager">
            <HardDrive size={16} />
          </button>
          <button className="as-icon-btn" onClick={onOpenExport} title="Export data" aria-label="Export data">
            <Download size={16} />
          </button>
          <button className="as-icon-btn" onClick={onOpenSettings} title="Settings" aria-label="Settings">
            <Settings size={16} />
          </button>
        </div>
        <button className="as-mainmenu" onClick={onMainMenu} disabled={runGoing} title={runGoing ? SIM_LOCK_HINT : undefined}>
          <LogOut size={14} />
          <span>Main menu</span>
        </button>
        <div className="as-version">{BRAND.version}</div>
      </div>
    </aside>
  );
};
