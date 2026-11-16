// Bundled changelog shown on the main menu. The data file is edited by hand for each release.
import raw from '../data/changelog.json' with { type: 'json' };

export type ChangeKind = 'new' | 'fix';
export interface ChangelogItem { kind: ChangeKind; text: string }
export interface ChangelogRelease { version: string; date: string; items: ChangelogItem[] } // date is YYYY-MM-DD

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const parseItem = (value: unknown): ChangelogItem | null => {
  if (typeof value !== 'object' || value === null) return null;
  const { kind, text } = value as Record<string, unknown>;
  if ((kind !== 'new' && kind !== 'fix') || typeof text !== 'string' || text.trim() === '') return null;
  return { kind, text };
};

const parseRelease = (value: unknown): ChangelogRelease | null => {
  if (typeof value !== 'object' || value === null) return null;
  const { version, date, items } = value as Record<string, unknown>;
  if (typeof version !== 'string' || version.trim() === '') return null;
  if (typeof date !== 'string' || !DATE_RE.test(date)) return null;
  if (!Array.isArray(items)) return null;
  const valid = items.map(parseItem).filter((item): item is ChangelogItem => item !== null);
  return valid.length > 0 ? { version, date, items: valid } : null;
};

/** Keeps only well-formed releases (and items), newest date first. Never throws. */
export function parseReleases(data: unknown): ChangelogRelease[] {
  if (!Array.isArray(data)) return [];
  return data
    .map(parseRelease)
    .filter((release): release is ChangelogRelease => release !== null)
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

export function getReleases(): ChangelogRelease[] {
  return parseReleases(raw);
}

export function latestRelease(): ChangelogRelease | null {
  return getReleases()[0] ?? null;
}

/** "2026-10-20" -> "Oct 20, 2026" (calendar date, no timezone shift). */
export function formatReleaseDate(date: string): string {
  const [year, month, day] = date.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' });
}
