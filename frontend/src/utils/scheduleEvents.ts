// Player-facing names for the calendar's special days, shared by the Schedule page and the Sim until dialog.

export const EVENT_LABELS: Record<string, string> = {
  OPENING_NIGHT: 'Opening night',
  CHRISTMAS_GAMES: 'Christmas',
  MLK_DAY: 'MLK Day',
  TRADE_DEADLINE: 'Trade deadline',
  RISING_STARS: 'All-Star',
  ALL_STAR_SATURDAY: 'All-Star',
  ALL_STAR_GAME: 'All-Star',
  REGULAR_SEASON_FINALE: 'Finale',
  FINALE_EVE_REST: 'Rest day',
};

/** Labels of a day's events, one per name ("All-Star" covers the three All-Star days). */
export const eventLabels = (events: string[]) =>
  [...new Set(events.map((e) => EVENT_LABELS[e] ?? e.replace(/_/g, ' ').toLowerCase()))];

/** "2002-12-14" -> Date in local time. */
export const parseIsoDate = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
};
