// Sidebar structure for the in-game shell. Pure data: no React state here.
import {
  Award, ArrowLeftRight, BarChart2, Briefcase, Building, Calendar, Cog, Database, Eye, Landmark, Sparkles, Trophy, Users,
  History as HistoryIcon, CalendarClock,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type Tab =
  | 'dashboard' | 'calendar' | 'roster' | 'rotations' | 'coaching' | 'board' | 'economy'
  | 'trades' | 'scouting' | 'explore' | 'analytics'
  | 'playoffs' | 'allstar' | 'awards' | 'history' | 'offseason';

export type BadgeKey = 'injuries' | 'trade_offers' | 'board' | 'offseason';

export interface NavItem {
  id: Tab;
  label: string;
  icon: LucideIcon;
  badge?: BadgeKey;
}

export interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
  defaultOpen: boolean;
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'franchise',
    label: 'Franchise',
    defaultOpen: true,
    items: [
      { id: 'calendar', label: 'Schedule', icon: Calendar },
      { id: 'roster', label: 'Roster & Contracts', icon: Users, badge: 'injuries' },
      { id: 'rotations', label: 'Rotations & Minutes', icon: Cog },
      { id: 'coaching', label: 'Coaching & Strategy', icon: Briefcase },
      { id: 'board', label: 'Front Office & Board', icon: Building, badge: 'board' },
      { id: 'economy', label: 'Finances & CBA', icon: Landmark },
    ],
  },
  {
    id: 'league',
    label: 'League',
    defaultOpen: true,
    items: [
      { id: 'trades', label: 'Trade Center', icon: ArrowLeftRight, badge: 'trade_offers' },
      { id: 'scouting', label: 'Scouting & Draft', icon: Eye },
      { id: 'explore', label: 'Player Database', icon: Database },
      { id: 'analytics', label: 'League Analytics', icon: BarChart2 },
    ],
  },
  {
    id: 'seasons',
    label: 'Seasons & History',
    defaultOpen: false,
    items: [
      { id: 'playoffs', label: 'Playoffs', icon: Trophy },
      { id: 'allstar', label: 'All-Star Weekend', icon: Sparkles },
      { id: 'awards', label: 'Season Awards', icon: Award },
      { id: 'history', label: 'Hall of Fame & History', icon: HistoryIcon },
      { id: 'offseason', label: 'End of Season Hub', icon: CalendarClock, badge: 'offseason' },
    ],
  },
];

/** Id of the group that contains a tab, or null for Dashboard. */
export function groupOfTab(tab: Tab): string | null {
  const group = NAV_GROUPS.find((candidate) => candidate.items.some((item) => item.id === tab));
  return group ? group.id : null;
}
