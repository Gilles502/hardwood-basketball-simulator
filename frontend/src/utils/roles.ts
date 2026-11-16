// Player roles — English NBA standard, mirrors core/roles.py on the backend.
// The backend always sends PG/SG/SF/PF/C; normalizeRole also accepts legacy Italian codes
// (PM/G/AP/AG) and full names so older saves and trade logs still display correctly.

export const ROLES = ['PG', 'SG', 'SF', 'PF', 'C'] as const;
export type Role = typeof ROLES[number];

export const ROLE_LABELS: Record<Role, string> = {
  PG: 'Point Guard',
  SG: 'Shooting Guard',
  SF: 'Small Forward',
  PF: 'Power Forward',
  C: 'Center',
};

const LEGACY_ROLES: Record<string, Role> = {
  PM: 'PG', G: 'SG', AP: 'SF', AG: 'PF', P: 'PG',
  PLAYMAKER: 'PG', GUARDIA: 'SG', 'ALA PICCOLA': 'SF', 'ALA GRANDE': 'PF', CENTRO: 'C',
};

export function normalizeRole(role?: string | null): string {
  if (!role) return '';
  const clean = role.trim().toUpperCase();
  return LEGACY_ROLES[clean] ?? clean;
}

export function isRole(value: string): value is Role {
  return (ROLES as readonly string[]).includes(value);
}

/** CSS class for the colored position badge (see .pos-* in index.css). */
export function roleBadgeClass(role?: string | null): string {
  const r = normalizeRole(role);
  return isRole(r) ? `pos-badge pos-${r.toLowerCase()}` : 'pos-badge';
}
