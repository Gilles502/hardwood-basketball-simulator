// Opponent tab maths. Mirrors core/scouting_matchups.py (build_report) so the page reacts instantly
// when an assignment changes; keep the two in sync.

export type Skill = '3PT' | 'DRIVE' | 'POST';
export const SKILLS: Skill[] = ['3PT', 'DRIVE', 'POST'];
export type Badge = 'bad' | 'watch' | 'fine';

export interface ScoutCfg {
  BAD_GAP: number;
  WATCH_GAP: number;
  GAP_WEIGHT: number;
  TENDENCY_BASE: number;
  TENDENCY_SPAN: number;
}

export interface TheirPlayer {
  name: string;
  pos: string | null; // court position for starters, null for the bench
  ruolo: string;
  minutes: number;
  skills: Record<Skill, number>;
  tendencies: Record<Skill, number>;
  auto_defender: string | null;
}

export interface MyPlayer {
  name: string;
  ruolo: string;
  minutes: number;
  injured: boolean;
  per_d: number;
  int_d: number;
}

export interface OpponentPlan {
  matchups: Record<string, string>;
  double_teams: string[];
}

export interface ReportRow {
  name: string;
  pos: string;
  starter: boolean;
  minutes: number;
  skills: Record<Skill, number>;
  threat: Skill;
  threat_value: number;
  defender: string | null;
  auto: boolean;
  defense: number;
  gap: number;
  badge: Badge;
  pressure: number;
  danger: number;
  fix: string | null;
}

export const defenseVs = (p: MyPlayer, skill: Skill): number => (skill === 'POST' ? p.int_d : p.per_d);

export const badgeOf = (gap: number, cfg: ScoutCfg): Badge =>
  gap <= cfg.BAD_GAP ? 'bad' : gap <= cfg.WATCH_GAP ? 'watch' : 'fine';

const pressureOf = (threat: number, minutes: number, tendency: number, cfg: ScoutCfg): number =>
  threat * (minutes / 48) * (cfg.TENDENCY_BASE + (cfg.TENDENCY_SPAN * tendency) / 100);

/** Same rows as the server's build_report for the same plan. */
export const rebuildReport = (their: TheirPlayer[], mine: MyPlayer[], plan: OpponentPlan, cfg: ScoutCfg): ReportRow[] => {
  const healthy = new Map(mine.filter((p) => !p.injured).map((p) => [p.name, p]));
  const rows: ReportRow[] = their.map((t) => {
    const threat = SKILLS.reduce((best, k) => (t.skills[k] > t.skills[best] ? k : best), SKILLS[0]);
    const chosen = healthy.get(plan.matchups[t.name] ?? '');
    const defender = chosen ?? (t.auto_defender ? healthy.get(t.auto_defender) : undefined);
    const defense = defender ? defenseVs(defender, threat) : 0;
    const gap = defense - t.skills[threat];
    const pressure = pressureOf(t.skills[threat], t.minutes, t.tendencies[threat] ?? 50, cfg);
    return {
      name: t.name,
      pos: t.pos ?? t.ruolo,
      starter: t.pos !== null,
      minutes: t.minutes,
      skills: t.skills,
      threat,
      threat_value: t.skills[threat],
      defender: defender?.name ?? null,
      auto: !chosen,
      defense,
      gap,
      badge: badgeOf(gap, cfg),
      pressure,
      danger: pressure + Math.max(0, -gap) * cfg.GAP_WEIGHT,
      fix: null,
    };
  });

  // Fix: the best healthy rotation defender for that skill, unless he already guards a bigger threat
  // (chosen or auto: moving him would just open a worse matchup)
  rows.forEach((r) => {
    if (r.badge === 'fine') return;
    const taken = new Set(rows.filter((o) => o !== r && o.defender && o.pressure > r.pressure).map((o) => o.defender));
    let best: MyPlayer | null = null;
    healthy.forEach((p) => {
      if (p.minutes <= 0 || p.name === r.defender || taken.has(p.name)) return;
      if (!best || defenseVs(p, r.threat) > defenseVs(best, r.threat)) best = p;
    });
    const pick = best as MyPlayer | null;
    if (pick && defenseVs(pick, r.threat) > r.defense) r.fix = pick.name;
  });

  return rows.sort((a, b) => b.danger - a.danger);
};
