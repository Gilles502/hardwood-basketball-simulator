// Generated team crest: initials plus a stable color, so the UI never needs real team logos.

/** Initials of up to the first 3 words, uppercase. "Los Angeles Clippers" -> "LAC". Empty name -> "?". */
export function crestLabel(teamName: string): string {
  const words = teamName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  return words.slice(0, 3).map((word) => word[0]).join('').toUpperCase();
}

/** Deterministic hue (0-359) derived from the team name. */
export function crestHue(teamName: string): number {
  let hash = 7;
  for (const char of teamName) {
    hash = (hash * 31 + (char.codePointAt(0) ?? 0)) % 360;
  }
  return hash;
}
