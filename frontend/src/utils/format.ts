// Small display formatters shared by the sidebar and the Dashboard.

/** "2003-01-16" -> "Thu 16 Jan 2003". Returns "" for null or invalid input. */
export function formatGameDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const [year, month, day] = iso.split('-').map(Number);
  const date = new Date(year, (month || 1) - 1, day || 1);
  if (Number.isNaN(date.getTime())) return '';
  const weekday = date.toLocaleDateString('en-GB', { weekday: 'short' });
  const monthName = date.toLocaleDateString('en-GB', { month: 'short' });
  return `${weekday} ${date.getDate()} ${monthName} ${date.getFullYear()}`;
}

/** 1 -> "1st", 2 -> "2nd", 11 -> "11th", 23 -> "23rd". */
export function ordinal(n: number): string {
  const lastTwo = n % 100;
  if (lastTwo >= 11 && lastTwo <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

/** Player-facing name of the league phase. PRE_SEASON is also the first half of the regular season once days have been played. */
export function phaseLabel(leagueState: string, currentDay: number): string {
  switch (leagueState) {
    case 'PRE_SEASON': return currentDay > 0 ? 'Regular season' : 'Pre-season';
    case 'ALL_STAR_BREAK': return 'All-Star break';
    case 'REGULAR_SEASON_END': return 'Regular season complete';
    case 'PLAYOFFS':
    case 'PLAYOFFS_IN_PROGRESS': return 'Playoffs';
    case 'PLAYOFFS_END': return 'Playoffs complete';
    case 'OFFSEASON_OPTIONS_DECISION': return 'Offseason · Contract options';
    case 'OFFSEASON_COACH_HIRING_START': return 'Offseason · Staff & lottery';
    case 'OFFSEASON_TRADES_START': return 'Offseason · Trade window';
    case 'OFFSEASON_DRAFT_START':
    case 'DRAFT_USER_PICK': return 'Offseason · Draft';
    case 'OFFSEASON_UFA_START': return 'Offseason · Free agency';
    case 'OFFSEASON_CUTDOWN_START': return 'Offseason · Roster cuts';
    case 'OFFSEASON_COMPLETE': return 'Offseason complete';
    default: {
      const words = leagueState.replace(/_/g, ' ').toLowerCase();
      return words.charAt(0).toUpperCase() + words.slice(1);
    }
  }
}

/** user_role from the server -> label. */
export function roleLabel(role: string | undefined): string {
  switch (role) {
    case 'only_gm': return 'GM';
    case 'only_coach': return 'Coach';
    case 'spectator': return 'Spectator';
    default: return 'GM & Coach';
  }
}
