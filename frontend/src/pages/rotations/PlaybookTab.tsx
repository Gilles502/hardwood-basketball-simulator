import React, { useMemo, useState } from 'react';
import { normalizeRole } from '../../utils/roles';
import { POSITIONS, resolveStarters } from './lineup';
import type { BoardPlayer } from './lineup';

export interface TacticalPlan {
  pnr_coverage: string;
  defensive_scheme: string;
  offensive_focus: string;
  pace_preference: string;
  stagger_stars: boolean;
  offensive_first_option?: string | null;
  offensive_second_option?: string | null;
  offensive_third_option?: string | null;
  player_touch_modifiers?: Record<string, string>;
}

interface PlaybookTabProps {
  roster: BoardPlayer[];
  customLineup: Record<string, string>;
  minutes: Record<string, number>;
  plan: TacticalPlan;
  onPlanChange: (plan: TacticalPlan) => void;
}

type Page = 'offense' | 'defense' | 'touches';
const PAGES: { id: Page; label: string }[] = [
  { id: 'offense', label: 'Offense' },
  { id: 'defense', label: 'Defense' },
  { id: 'touches', label: 'Touches' },
];

type OptionKey = 'offensive_first_option' | 'offensive_second_option' | 'offensive_third_option';
const OPTIONS: { key: OptionKey; label: string; bonus: number }[] = [
  { key: 'offensive_first_option', label: '1st option', bonus: 32 },
  { key: 'offensive_second_option', label: '2nd option', bonus: 18 },
  { key: 'offensive_third_option', label: '3rd option', bonus: 10 },
];

interface Choice { id: string; label: string; short: string; note: string; art: React.ReactNode }

// Small court diagrams for the tiles: orange = offense, blue = defense.
const O = '#ff8a4a';
const D = '#38bdf8';
const dots = (pts: [number, number][], fill: string) => pts.map(([cx, cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={4} fill={fill} />);

const STYLES: Choice[] = [
  { id: 'BALANCED', label: 'Balanced', short: 'Balanced', note: 'Mix of everything', art: dots([[20, 30], [45, 18], [75, 18], [100, 30], [60, 38]], '#c9a27a') },
  { id: 'POUND_PAINT', label: 'Pound the paint', short: 'Paint', note: 'Drives and post-ups, fewer threes', art: <><rect x={45} y={0} width={30} height={28} fill="#ff6a1a" fillOpacity={0.35} /><path d="M60 42 L60 14" stroke={O} strokeWidth={2} /><path d="M56 18 L60 12 L64 18" stroke={O} strokeWidth={2} fill="none" /></> },
  { id: 'HUNT_THREES', label: 'Hunt threes', short: 'Threes', note: 'Perimeter volume', art: <><path d="M10 0 Q60 70 110 0" stroke={O} strokeWidth={2} fill="none" />{dots([[18, 16], [102, 16]], O)}</> },
  { id: 'PACE_AND_SPACE_5OUT', label: '5-out motion', short: '5-out', note: 'Everyone spaced, more threes', art: <><path d="M10 0 Q60 70 110 0" stroke="#c9a27a" strokeWidth={1.5} fill="none" opacity={0.6} />{dots([[12, 8], [35, 30], [60, 40], [85, 30], [108, 8]], O)}</> },
];

const PACES: { id: string; label: string; short: string }[] = [
  { id: '7_SECONDS_OR_LESS', label: '7 seconds', short: 'fast' },
  { id: 'BALANCED', label: 'Standard', short: 'standard pace' },
  { id: 'GRIT_AND_GRIND', label: 'Grit & grind', short: 'slow' },
];

const COVERAGES: Choice[] = [
  { id: 'DROP', label: 'Drop', short: 'drop', note: 'Protect the rim, allow pull-ups', art: <>{dots([[30, 32]], O)}{dots([[46, 26]], '#c9a27a')}{dots([[82, 10]], D)}<path d="M82 15 L82 32" stroke={D} strokeWidth={2} strokeDasharray="3 3" /></> },
  { id: 'SWITCH', label: 'Switch', short: 'switch', note: 'Swap on every screen', art: <>{dots([[30, 32]], O)}{dots([[46, 26]], '#c9a27a')}<path d="M38 18 C52 4 68 4 76 20" stroke={D} strokeWidth={2} fill="none" /></> },
  { id: 'BLITZ_TRAP', label: 'Blitz / trap', short: 'blitz', note: 'Two on the ball handler', art: <>{dots([[40, 28]], O)}{dots([[30, 18], [50, 18]], D)}</> },
  { id: 'HEDGE', label: 'Hedge', short: 'hedge', note: 'Show and recover', art: <>{dots([[30, 32]], O)}{dots([[50, 24]], D)}<path d="M50 24 L70 30 L84 14" stroke={D} strokeWidth={2} fill="none" strokeDasharray="3 3" /></> },
];

const SCHEMES: Choice[] = [
  { id: 'MAN_TO_MAN', label: 'Man', short: 'Man', note: 'One defender each', art: dots([[20, 28], [42, 16], [60, 34], [78, 16], [100, 28]], D) },
  { id: 'ZONE_2_3', label: '2-3 zone', short: '2-3 zone', note: 'Own the paint, give up threes', art: <><rect x={42} y={0} width={36} height={30} fill="#ff6a1a" fillOpacity={0.25} />{dots([[46, 10], [74, 10], [34, 34], [60, 38], [86, 34]], D)}</> },
  { id: 'ZONE_3_2', label: '3-2 zone', short: '3-2 zone', note: 'Run shooters off the line', art: dots([[30, 12], [60, 8], [90, 12], [45, 36], [75, 36]], D) },
  { id: 'FULL_PRESS', label: 'Full press', short: 'Press', note: 'Pressure the perimeter', art: dots([[22, 8], [38, 8], [70, 22], [96, 34], [52, 40]], D) },
  { id: 'BOX_AND_ONE', label: 'Box-and-one', short: 'Box-and-one', note: 'Double their stars', art: <>{dots([[38, 12], [82, 12], [38, 36], [82, 36]], D)}{dots([[58, 24]], O)}{dots([[66, 24]], D)}</> },
];

const TOUCHES: { id: string; label: string; effect: string }[] = [
  { id: 'GO_TO_GUY', label: 'Go-to', effect: '+50% touches, takes the big shots' },
  { id: 'SECONDARY', label: '2nd', effect: '+15% touches' },
  { id: 'ROOKIE_FOCUS', label: 'Rookie', effect: '+35% touches, more shots for a young player' },
  { id: 'STANDARD', label: 'Std', effect: 'Usage from his ratings and tendencies' },
  { id: 'ROLE_PLAYER', label: 'Role', effect: '-30% touches, open catch-and-shoot looks' },
  { id: 'DEFENSE_ONLY', label: 'D only', effect: '-60% touches, screens and boards' },
];

const lastName = (name: string): string => name.split(' ').slice(-1)[0];
const pick = <T extends { id: string }>(list: T[], id: string): T | undefined => list.find((c) => c.id === id);

const Tiles: React.FC<{ choices: Choice[]; value: string; onPick: (id: string) => void; label: string; cols: number }> = ({ choices, value, onPick, label, cols }) => (
  <div className="pb-tiles" role="radiogroup" aria-label={label} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
    {choices.map((c) => (
      <button
        type="button"
        key={c.id}
        role="radio"
        aria-checked={value === c.id}
        className={`pb-tile${value === c.id ? ' is-on' : ''}`}
        onClick={() => onPick(c.id)}
      >
        <svg viewBox="0 0 120 46" aria-hidden="true">{c.art}</svg>
        <b>{c.label}</b>
        <small>{c.note}</small>
      </button>
    ))}
  </div>
);

export const PlaybookTab: React.FC<PlaybookTabProps> = ({ roster, customLineup, minutes, plan, onPlanChange }) => {
  const [page, setPage] = useState<Page>('offense');
  const [editingOption, setEditingOption] = useState<OptionKey | null>(null);

  const set = (patch: Partial<TacticalPlan>) => onPlanChange({ ...plan, ...patch });

  // Starters first (PG..C), then the bench by minutes, then OVR.
  const ordered = useMemo(() => {
    const starters = resolveStarters(roster, customLineup);
    const five = POSITIONS.filter((pos) => starters[pos]).map((pos) => ({ pos, player: starters[pos]! }));
    const names = new Set(five.map((s) => s.player.nome));
    const bench = roster
      .filter((p) => !names.has(p.nome))
      .sort((a, b) => (minutes[b.nome] || 0) - (minutes[a.nome] || 0) || b.ovr - a.ovr);
    return { five, all: [...five.map((s) => s.player), ...bench] };
  }, [roster, customLineup, minutes]);

  const mods = plan.player_touch_modifiers || {};
  // ---------- Offense ----------
  const setOption = (key: OptionKey, name: string | null) => {
    const patch: Partial<TacticalPlan> = { [key]: name };
    // Picking someone who already holds another option swaps the two.
    const holder = OPTIONS.find((o) => o.key !== key && name && plan[o.key] === name);
    if (holder) patch[holder.key] = plan[key] || null;
    set(patch);
    setEditingOption(null);
  };

  // ---------- Binder tab summaries ----------
  const offenseSummary = [
    pick(STYLES, plan.offensive_focus)?.short ?? 'Balanced',
    pick(PACES, plan.pace_preference)?.short ?? 'standard pace',
    plan.offensive_first_option ? `${lastName(plan.offensive_first_option)} 1st` : null,
  ].filter(Boolean).join(' · ');
  const defenseSummary = `${pick(SCHEMES, plan.defensive_scheme)?.short ?? 'Man'} · ${pick(COVERAGES, plan.pnr_coverage)?.short ?? 'drop'}`;
  // Saved modifiers can still name players who have left the team; count only the current roster.
  const rosterMods = roster.map((p) => mods[p.nome] || 'STANDARD');
  const goTo = rosterMods.filter((m) => m === 'GO_TO_GUY').length;
  const rookies = rosterMods.filter((m) => m === 'ROOKIE_FOCUS').length;
  const changed = rosterMods.filter((m) => m !== 'STANDARD').length;
  const touchSummary = goTo || rookies
    ? [goTo ? `${goTo} go-to` : null, rookies ? `${rookies} rookie` : null].filter(Boolean).join(' · ')
    : changed ? `${changed} changed` : 'All standard';
  const summaries: Record<Page, string> = { offense: offenseSummary, defense: defenseSummary, touches: touchSummary };

  const pageIndex = PAGES.findIndex((p) => p.id === page);

  const onTabKey = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const next = PAGES[(pageIndex + (e.key === 'ArrowDown' ? 1 : PAGES.length - 1)) % PAGES.length];
    setPage(next.id);
    document.getElementById(`pb-tab-${next.id}`)?.focus();
  };

  const playerLabel = (p: BoardPlayer) => `${normalizeRole(p.ruolo)} · ${p.nome}${p.is_star ? ' ★' : ''}`;

  return (
    <div className="pb-binder">
      <div className="pb-tabs" role="tablist" aria-label="Playbook pages" aria-orientation="vertical" onKeyDown={onTabKey}>
        {PAGES.map((p) => (
          <button
            type="button"
            key={p.id}
            id={`pb-tab-${p.id}`}
            role="tab"
            aria-selected={page === p.id}
            aria-controls="pb-page"
            tabIndex={page === p.id ? 0 : -1}
            className={`pb-tab${page === p.id ? ' is-on' : ''}`}
            onClick={() => setPage(p.id)}
          >
            {p.label}
            <small>{summaries[p.id]}</small>
          </button>
        ))}
      </div>

      <section className="lu-paper pb-page" id="pb-page" role="tabpanel" aria-labelledby={`pb-tab-${page}`}>
        <div className="lu-band"><span>{PAGES[pageIndex].label}</span><span>Page {pageIndex + 1} of {PAGES.length}</span></div>

        {page === 'offense' && (
          <>
            <div className="pb-sec"><span>Scoring order</span><span>Who gets the first look</span></div>
            <div className="pb-body">
              <div className="pb-pods">
                {OPTIONS.map((o, i) => {
                  const name = plan[o.key];
                  return (
                    <button
                      type="button"
                      key={o.key}
                      className={`pb-pod${editingOption === o.key ? ' is-on' : ''}${name ? '' : ' is-auto'}`}
                      aria-expanded={editingOption === o.key}
                      onClick={() => setEditingOption(editingOption === o.key ? null : o.key)}
                    >
                      <span className="pb-pod-no">{i + 1}</span>
                      <b>{name || 'Auto'}</b>
                      <small>{o.label} · +{o.bonus} shot priority</small>
                    </button>
                  );
                })}
              </div>
              {editingOption && (
                <div className="pb-picker" role="group" aria-label={`Choose the ${OPTIONS.find((o) => o.key === editingOption)!.label}`}>
                  <button type="button" className={`pb-chip${!plan[editingOption] ? ' is-on' : ''}`} onClick={() => setOption(editingOption, null)}>Auto · nobody</button>
                  {ordered.all.map((p) => (
                    <button
                      type="button"
                      key={p.nome}
                      className={`pb-chip${plan[editingOption] === p.nome ? ' is-on' : ''}`}
                      onClick={() => setOption(editingOption, p.nome)}
                      disabled={p.infortunato}
                      title={p.infortunato ? 'Injured' : undefined}
                    >
                      {playerLabel(p)} <em>{p.ovr}</em>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="pb-sec"><span>Style</span></div>
            <div className="pb-body">
              <Tiles label="Offense style" choices={STYLES} value={plan.offensive_focus} onPick={(id) => set({ offensive_focus: id })} cols={4} />
            </div>

            <div className="pb-sec"><span>Pace</span></div>
            <div className="pb-body">
              <div className="pb-seg3" role="radiogroup" aria-label="Pace">
                {PACES.map((p) => (
                  <button type="button" key={p.id} role="radio" aria-checked={plan.pace_preference === p.id} className={plan.pace_preference === p.id ? 'is-on' : ''} onClick={() => set({ pace_preference: p.id })}>
                    {p.label}
                  </button>
                ))}
              </div>
              <label className="pb-toggle">
                <span><b>Stagger stars</b> · keep at least one star on the floor in the 2nd and 3rd quarters</span>
                <input type="checkbox" checked={plan.stagger_stars} onChange={(e) => set({ stagger_stars: e.target.checked })} />
                <i aria-hidden="true" />
              </label>
            </div>
          </>
        )}

        {page === 'defense' && (
          <>
            <div className="pb-sec"><span>Pick &amp; roll coverage</span></div>
            <div className="pb-body">
              <Tiles label="Pick and roll coverage" choices={COVERAGES} value={plan.pnr_coverage} onPick={(id) => set({ pnr_coverage: id })} cols={4} />
            </div>
            <div className="pb-sec"><span>Team defense</span></div>
            <div className="pb-body">
              <Tiles label="Team defense" choices={SCHEMES} value={plan.defensive_scheme} onPick={(id) => set({ defensive_scheme: id })} cols={5} />
            </div>
          </>
        )}

        {page === 'touches' && (
          <>
            <div className="pb-sec"><span>Touches</span><span>Who gets the ball</span></div>
            <div className="pb-body">
              {ordered.all.map((p, i) => {
                const current = mods[p.nome] || 'STANDARD';
                return (
                  <React.Fragment key={p.nome}>
                    {i === ordered.five.length && <div className="lu-divider">Bench</div>}
                    <div className={`pb-trow${p.infortunato ? ' is-dim' : ''}`}>
                      <span className="mi-pos">{i < ordered.five.length ? ordered.five[i].pos : normalizeRole(p.ruolo)}</span>
                      <div className="mi-who">
                        <b>{p.nome}{p.is_star && <span className="lu-star"> ★</span>}</b>
                        <small>{p.eta <= 22 ? 'Young · ' : ''}{minutes[p.nome] || 0} min · {pick(TOUCHES, current)?.effect}</small>
                      </div>
                      <div className="pb-seg" role="radiogroup" aria-label={`Touches for ${p.nome}`}>
                        {TOUCHES.map((t) => (
                          <button
                            type="button"
                            key={t.id}
                            role="radio"
                            aria-checked={current === t.id}
                            className={current === t.id ? 'is-on' : ''}
                            title={t.effect}
                            onClick={() => {
                              const next = { ...mods };
                              if (t.id === 'STANDARD') delete next[p.nome];
                              else next[p.nome] = t.id;
                              set({ player_touch_modifiers: next });
                            }}
                          >
                            {t.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </React.Fragment>
                );
              })}
            </div>
          </>
        )}
      </section>
    </div>
  );
};
