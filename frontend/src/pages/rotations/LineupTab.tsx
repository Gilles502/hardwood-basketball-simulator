import React, { useMemo, useState } from 'react';
import { normalizeRole } from '../../utils/roles';
import { POSITIONS, gradeOf, ratingAt, resolveStarters } from './lineup';
import type { BoardPlayer, Pos } from './lineup';

export type LineupPlayer = BoardPlayer;

interface LineupTabProps {
  roster: LineupPlayer[];
  customLineup: Record<string, string>;
  minutes: Record<string, number>;
  onLineupChange: (lineup: Record<string, string>) => void;
}

const Grade: React.FC<{ rating: number; title?: string }> = ({ rating, title }) => {
  const g = gradeOf(rating);
  return <span className={`lu-grade is-${g.charAt(0).toLowerCase()}`} title={title}>{g}</span>;
};

/** Mini PG..C strip showing a player's grade at every position. */
const Covers: React.FC<{ player: LineupPlayer }> = ({ player }) => (
  <span className="lu-covers" aria-label={`Fit by position: ${POSITIONS.map((pos) => `${pos} ${gradeOf(ratingAt(player, pos))}`).join(', ')}`}>
    {POSITIONS.map((pos) => (
      <span key={pos} className={`is-${gradeOf(ratingAt(player, pos)).charAt(0).toLowerCase()}`}>{pos}</span>
    ))}
  </span>
);

type Selection = { kind: 'slot'; pos: Pos } | { kind: 'bench'; name: string } | null;

export const LineupTab: React.FC<LineupTabProps> = ({ roster, customLineup, minutes, onLineupChange }) => {
  const [selection, setSelection] = useState<Selection>(null);

  const starters = useMemo(() => resolveStarters(roster, customLineup), [roster, customLineup]);

  const starterNames = new Set(Object.values(starters).map((p) => p!.nome));
  const mins = (p: LineupPlayer): number => minutes[p.nome] || 0;

  // Bench in rotation order: most minutes first, then OVR; injured and 0-minute players drop to "out of rotation".
  const bench = roster
    .filter((p) => !starterNames.has(p.nome))
    .sort((a, b) => mins(b) - mins(a) || b.ovr - a.ovr);
  const inRotation = bench.filter((p) => !p.infortunato && mins(p) > 0);
  const outOfRotation = bench.filter((p) => p.infortunato || mins(p) === 0);
  const sixthMan = inRotation[0]?.nome;

  // Lineup chemistry (same rules the page used before)
  const five = POSITIONS.map((pos) => starters[pos]).filter(Boolean) as LineupPlayer[];
  const playmaker = five.some((p) => normalizeRole(p.ruolo) === 'PG' && p.ovr >= 82);
  const shooters = five.filter((p) => ['PG', 'SG', 'SF'].includes(normalizeRole(p.ruolo)) && p.ovr >= 80).length;
  const rimProtector = five.some((p) => ['PF', 'C'].includes(normalizeRole(p.ruolo)) && p.ovr >= 82);
  const synergy = Math.min(100, (playmaker ? 25 : 10) + shooters * 15 + (rimProtector ? 20 : 5) + five.length * 5);
  const avg = (list: LineupPlayer[]): number => (list.length ? Math.round(list.reduce((s, p) => s + p.ovr, 0) / list.length) : 0);
  const weakSpot = !playmaker ? 'playmaking' : shooters < 2 ? 'shooting' : !rimProtector ? 'rim protection' : null;
  const stamp = synergy >= 80 ? { label: 'Elite five', tone: 'ok' } : synergy >= 60 ? { label: 'Solid five', tone: 'ok' } : { label: 'Needs work', tone: 'low' };

  const assign = (pos: Pos, name: string) => {
    const current: Record<string, string> = {};
    POSITIONS.forEach((p) => { if (starters[p]) current[p] = starters[p]!.nome; });
    const fromPos = POSITIONS.find((p) => current[p] === name);
    if (fromPos) current[fromPos] = current[pos];
    current[pos] = name;
    onLineupChange(current);
    setSelection(null);
  };

  const onStarterClick = (pos: Pos) => {
    if (selection?.kind === 'bench') {
      assign(pos, selection.name);
    } else if (selection?.kind === 'slot' && selection.pos !== pos) {
      assign(selection.pos, starters[pos]!.nome);
    } else {
      setSelection(selection?.kind === 'slot' && selection.pos === pos ? null : { kind: 'slot', pos });
    }
  };

  const onBenchClick = (p: LineupPlayer) => {
    if (p.infortunato) return;
    if (selection?.kind === 'slot') assign(selection.pos, p.nome);
    else setSelection(selection?.kind === 'bench' && selection.name === p.nome ? null : { kind: 'bench', name: p.nome });
  };

  const keyActivate = (fn: () => void) => (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); }
    if (e.key === 'Escape') setSelection(null);
  };

  // Hints while something is selected
  const slotPos = selection?.kind === 'slot' ? selection.pos : null;
  const slotRanking = slotPos
    ? roster.filter((p) => !p.infortunato && p.nome !== starters[slotPos]?.nome).sort((a, b) => ratingAt(b, slotPos) - ratingAt(a, slotPos))
    : [];
  const bestBackup = slotPos ? slotRanking.find((p) => !starterNames.has(p.nome))?.nome : null;
  const benchPick = selection?.kind === 'bench' ? roster.find((p) => p.nome === selection.name) : undefined;

  const benchRow = (p: LineupPlayer, index: number, dim: boolean) => {
    const selected = selection?.kind === 'bench' && selection.name === p.nome;
    let hint: React.ReactNode = <>{normalizeRole(p.ruolo)} · {p.eta} yrs{p.potenziale > p.ovr + 5 ? ` · POT ${p.potenziale}` : ''}</>;
    if (slotPos && !p.infortunato) {
      const g = gradeOf(ratingAt(p, slotPos));
      if (p.nome === bestBackup) hint = <b className="lu-hint is-best">Best {slotPos} backup ({g})</b>;
      else if (g !== 'D') hint = <b className="lu-hint">Could cover {slotPos} ({g})</b>;
    }
    return (
      <div
        key={p.nome}
        className={`lu-bench-row${dim ? ' is-dim' : ''}${selected ? ' is-selected' : ''}${p.nome === bestBackup ? ' is-best' : ''}`}
        role="button"
        tabIndex={p.infortunato ? -1 : 0}
        aria-disabled={p.infortunato}
        aria-pressed={selected}
        onClick={() => onBenchClick(p)}
        onKeyDown={keyActivate(() => onBenchClick(p))}
      >
        <span className="lu-no">{index}</span>
        <div className="lu-who">
          <b>
            {p.nome}
            {p.nome === sixthMan && <span className="lu-role is-sixth">6th man</span>}
            {p.infortunato
              ? <span className="lu-role is-injured">Injured {p.giorni_infortunio_rimanenti}d</span>
              : mins(p) > 0 && p.nome !== sixthMan && <span className="lu-role">{mins(p)} min</span>}
          </b>
          <small>{hint}</small>
        </div>
        <Covers player={p} />
        <span className="lu-ovr">{p.ovr}</span>
      </div>
    );
  };

  return (
    <div className="lu-root" onKeyDown={(e) => { if (e.key === 'Escape') setSelection(null); }}>
      {/* Chemistry strip */}
      <div className="lu-strip">
        <div className="lu-score"><span>Lineup synergy</span><b>{synergy}<small>/100</small></b></div>
        <div className="lu-factor">
          <span>Playmaking</span>
          <div className="lu-meter"><i className={playmaker ? 'is-ok' : 'is-mid'} style={{ width: playmaker ? '100%' : '40%' }} /></div>
          <small>{playmaker ? 'Elite floor general' : 'No elite playmaker'}</small>
        </div>
        <div className="lu-factor">
          <span>Shooting</span>
          <div className="lu-meter"><i className={shooters >= 2 ? 'is-ok' : shooters === 1 ? 'is-mid' : 'is-low'} style={{ width: `${Math.max(8, (shooters / 3) * 100)}%` }} /></div>
          <small>{shooters} of 3 perimeter shooters</small>
        </div>
        <div className="lu-factor">
          <span>Rim protection</span>
          <div className="lu-meter"><i className={rimProtector ? 'is-ok' : 'is-low'} style={{ width: rimProtector ? '100%' : '25%' }} /></div>
          <small>{rimProtector ? 'Rim protector anchors the paint' : 'No rim protector'}</small>
        </div>
        <div className="lu-avgs"><span>Starters <b>{avg(five)}</b></span><span>Bench <b>{avg(inRotation)}</b></span></div>
      </div>

      <p className="lu-help">
        {slotPos
          ? <>Pick who starts at <b>{slotPos}</b>: click a bench player, or another starter to swap spots. Esc to cancel.</>
          : benchPick
            ? <>Where should <b>{benchPick.nome}</b> start? Click a spot on the starting five. Esc to cancel.</>
            : 'Click a starter to see his best backups, or a bench player to see where he would start.'}
      </p>

      <div className="lu-cards">
        {/* Starting five: cream lineup card */}
        <section className="lu-paper" aria-label="Starting five">
          <div className="lu-band"><span>Starting five</span><span>{five.reduce((s, p) => s + mins(p), 0)} min</span></div>
          {POSITIONS.map((pos, i) => {
            const p = starters[pos];
            if (!p) return <div key={pos} className="lu-line is-empty"><span className="lu-no">{i + 1}</span><span className="lu-pos">{pos}</span><div className="lu-who"><small>No healthy player</small></div></div>;
            const selected = slotPos === pos;
            const target = benchPick ? <span className="lu-target">{benchPick.nome.split(' ').slice(-1)[0]} here <Grade rating={ratingAt(benchPick, pos)} /></span> : null;
            return (
              <div
                key={pos}
                className={`lu-line${selected ? ' is-selected' : ''}${benchPick || (slotPos && !selected) ? ' is-target' : ''}`}
                role="button"
                tabIndex={0}
                aria-pressed={selected}
                onClick={() => onStarterClick(pos)}
                onKeyDown={keyActivate(() => onStarterClick(pos))}
              >
                <span className="lu-no">{i + 1}</span>
                <span className="lu-pos">{pos}</span>
                <div className="lu-who">
                  <b>{p.nome}{p.is_star && <span className="lu-star" aria-label="star"> ★</span>}</b>
                  <small>{mins(p)} min{p.infortunato ? ' · injured' : ''}</small>
                </div>
                {target || <Grade rating={ratingAt(p, pos)} title={`Fit at ${pos}`} />}
                <span className="lu-ovr">{p.ovr}</span>
              </div>
            );
          })}
          <div className={`lu-stamp is-${stamp.tone}`}>{stamp.label}</div>
          <div className="lu-foot">
            <span>Avg OVR <b>{avg(five)}</b></span>
            {weakSpot ? <span className="is-warn">Weak spot: {weakSpot}</span> : <span className="is-ok">No weak spot</span>}
          </div>
        </section>

        {/* Bench: kraft second-unit card */}
        <section className="lu-paper is-kraft" aria-label="Bench">
          <div className="lu-band"><span>Second unit · bench</span><span>{inRotation.reduce((s, p) => s + mins(p), 0)} min</span></div>
          {inRotation.map((p, i) => benchRow(p, i + 6, false))}
          {inRotation.length === 0 && <p className="lu-empty">Nobody on the bench has minutes. Set them in the Minutes tab.</p>}
          {outOfRotation.length > 0 && <div className="lu-divider">Out of rotation</div>}
          {outOfRotation.map((p, i) => benchRow(p, inRotation.length + i + 6, true))}
        </section>
      </div>
    </div>
  );
};
