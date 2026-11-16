import React, { useMemo } from 'react';
import { Lock, RotateCcw, Scale } from 'lucide-react';
import { normalizeRole } from '../../utils/roles';
import { POSITIONS, resolveStarters } from './lineup';
import type { BoardPlayer } from './lineup';

export const GAME_MINUTES = 240;
const MAX_PLAYER_MINUTES = 48;

type Preset = 'playoff' | 'balanced' | 'deep';

interface MinutesTabProps {
  roster: BoardPlayer[];
  customLineup: Record<string, string>;
  minutes: Record<string, number>;
  onMinutesChange: (minutes: Record<string, number>) => void;
  onPreset: (preset: Preset) => void;
  onAutoCoach: () => void;
}

const PRESETS: { id: Preset; label: string; title: string }[] = [
  { id: 'playoff', label: '8-man', title: 'Tight playoff rotation' },
  { id: 'balanced', label: '10-man', title: 'Regular-season rotation' },
  { id: 'deep', label: '12-man', title: 'Deep bench, minutes spread evenly' },
];

const clamp = (n: number): number => Math.max(0, Math.min(MAX_PLAYER_MINUTES, n));

/**
 * Moves the total to 240 one minute at a time: bench players already in the rotation first,
 * then the rest of the healthy bench, starters last. Never goes below 0 or above 48.
 */
export const balanceMinutes = (
  minutes: Record<string, number>,
  order: string[],
  total: number,
): Record<string, number> => {
  const next = { ...minutes };
  let diff = GAME_MINUTES - total;
  let moved = true;
  while (diff !== 0 && moved) {
    moved = false;
    for (const name of order) {
      if (diff === 0) break;
      const m = next[name] || 0;
      if (diff > 0 && m < MAX_PLAYER_MINUTES) { next[name] = m + 1; diff -= 1; moved = true; }
      else if (diff < 0 && m > 0) { next[name] = m - 1; diff += 1; moved = true; }
    }
  }
  return next;
};

export const MinutesTab: React.FC<MinutesTabProps> = ({ roster, customLineup, minutes, onMinutesChange, onPreset, onAutoCoach }) => {
  const starters = useMemo(() => {
    const map = resolveStarters(roster, customLineup);
    return POSITIONS.map((pos) => ({ pos, player: map[pos] })).filter((s) => s.player) as { pos: string; player: BoardPlayer }[];
  }, [roster, customLineup]);
  const starterNames = new Set(starters.map((s) => s.player.nome));

  const mins = (p: BoardPlayer): number => minutes[p.nome] || 0;
  // Bench keeps a fixed order (best first) so rows don't jump while you drag.
  const bench = roster.filter((p) => !starterNames.has(p.nome)).sort((a, b) => b.ovr - a.ovr);
  const healthyBench = bench.filter((p) => !p.infortunato);
  const injured = bench.filter((p) => p.infortunato);
  const sixthMan = [...healthyBench].sort((a, b) => mins(b) - mins(a))[0];

  const healthy = roster.filter((p) => !p.infortunato);
  const total = healthy.reduce((s, p) => s + mins(p), 0);
  const startersTotal = starters.reduce((s, { player }) => s + (player.infortunato ? 0 : mins(player)), 0);
  const diff = total - GAME_MINUTES;

  const setOne = (name: string, value: number) => onMinutesChange({ ...minutes, [name]: clamp(value) });

  const balance = () => {
    const rotation = healthyBench.filter((p) => mins(p) > 0).sort((a, b) => mins(b) - mins(a)).map((p) => p.nome);
    const rest = healthyBench.filter((p) => mins(p) === 0).map((p) => p.nome);
    const first = balanceMinutes(minutes, diff < 0 ? rotation : [...rotation, ...rest], total);
    const left = healthy.reduce((s, p) => s + (first[p.nome] || 0), 0);
    const startersOrder = starters.filter((s) => !s.player.infortunato).map((s) => s.player.nome);
    onMinutesChange(left === GAME_MINUTES ? first : balanceMinutes(first, startersOrder, left));
  };

  // Budget bar: one segment per player with minutes, scaled so 240 is a fixed mark.
  const scale = Math.max(total, GAME_MINUTES);
  const segments = [
    ...starters.filter((s) => !s.player.infortunato).map((s) => ({ p: s.player, starter: true })),
    ...healthyBench.map((p) => ({ p, starter: false })),
  ].filter((s) => mins(s.p) > 0);

  const row = (p: BoardPlayer, pos: string, dim: boolean) => {
    const value = mins(p);
    const locked = p.infortunato;
    return (
      <div key={p.nome} className={`mi-row${dim ? ' is-dim' : ''}`}>
        <span className="mi-pos">{pos}</span>
        <div className="mi-who">
          <b>{p.nome}{p.is_star && <span className="lu-star"> ★</span>}</b>
          <small>
            {locked
              ? `Injured ${p.giorni_infortunio_rimanenti}d · minutes locked`
              : sixthMan && p.nome === sixthMan.nome && value > 0
                ? '6th man'
                : value === 0 ? 'Out of rotation' : `${p.eta} yrs${p.potenziale > p.ovr + 5 ? ` · POT ${p.potenziale}` : ''}`}
          </small>
        </div>
        {locked ? (
          <div className="mi-locked"><Lock size={14} /> Out</div>
        ) : (
          <>
            <input
              type="range"
              className="mi-slider"
              min={0}
              max={MAX_PLAYER_MINUTES}
              value={value}
              onChange={(e) => setOne(p.nome, parseInt(e.target.value, 10))}
              aria-label={`${p.nome} minutes`}
              style={{ '--fill': `${(value / MAX_PLAYER_MINUTES) * 100}%` } as React.CSSProperties}
            />
            <div className="mi-step">
              <button type="button" onClick={() => setOne(p.nome, value - 1)} disabled={value <= 0} aria-label={`One minute less for ${p.nome}`}>−</button>
              <input
                type="number"
                min={0}
                max={MAX_PLAYER_MINUTES}
                value={value}
                onChange={(e) => setOne(p.nome, parseInt(e.target.value, 10) || 0)}
                aria-label={`${p.nome} minutes`}
              />
              <button type="button" onClick={() => setOne(p.nome, value + 1)} disabled={value >= MAX_PLAYER_MINUTES} aria-label={`One minute more for ${p.nome}`}>+</button>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="lu-root">
      {/* Budget */}
      <div className={`mi-budget${diff !== 0 ? ' is-off' : ''}`}>
        <div className="mi-count">
          <span>Minutes used</span>
          <b>{total}<small> / {GAME_MINUTES}</small></b>
          <em>{diff === 0 ? 'Ready to save' : diff > 0 ? `${diff} over · can't save yet` : `${-diff} short · can't save yet`}</em>
        </div>
        <div className="mi-bar-wrap">
          <div className="mi-bar" aria-hidden="true">
            {segments.map(({ p, starter }) => (
              <i
                key={p.nome}
                className={starter ? 'is-starter' : 'is-bench'}
                style={{ width: `${(mins(p) / scale) * 100}%` }}
                title={`${p.nome}: ${mins(p)} min`}
              />
            ))}
            <span className="mi-mark" style={{ left: `${(GAME_MINUTES / scale) * 100}%` }} />
          </div>
          <div className="mi-split"><span>Starters {startersTotal}</span><span>Bench {total - startersTotal}</span></div>
        </div>
        <div className="mi-actions">
          <button type="button" className="mi-btn" onClick={balance} disabled={diff === 0}><Scale size={15} /> Balance to 240</button>
          <div className="mi-presets" role="group" aria-label="Rotation presets">
            {PRESETS.map((pr) => (
              <button type="button" key={pr.id} className="mi-pill" title={pr.title} onClick={() => onPreset(pr.id)}>{pr.label}</button>
            ))}
            <button type="button" className="mi-pill" title="Let the coaching staff set the rotation" onClick={onAutoCoach}><RotateCcw size={13} /> Auto-coach</button>
          </div>
        </div>
      </div>

      <div className="lu-cards">
        <section className="lu-paper" aria-label="Starting five minutes">
          <div className="lu-band"><span>Starting five</span><span>{startersTotal} min</span></div>
          {starters.map(({ pos, player }) => row(player, pos, false))}
        </section>
        <section className="lu-paper is-kraft" aria-label="Bench minutes">
          <div className="lu-band"><span>Second unit · bench</span><span>{total - startersTotal} min</span></div>
          {healthyBench.map((p) => row(p, normalizeRole(p.ruolo), mins(p) === 0))}
          {injured.length > 0 && <div className="lu-divider">Injured</div>}
          {injured.map((p) => row(p, normalizeRole(p.ruolo), true))}
        </section>
      </div>
    </div>
  );
};

