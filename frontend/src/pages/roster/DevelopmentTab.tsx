import React, { useMemo, useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { ModalShell } from '../../components/ModalShell';
import type { PlayerDetails } from '../../store/leagueStore';
import { normalizeRole } from '../../utils/roles';

/** One row of Giocatore.ovr_history (core/models.py record_ovr_milestone). */
interface OvrEntry {
  season: number;
  year?: number;
  age?: number;
  ovr: number;
  potenziale?: number;
}

type Stage = 'rising' | 'prime' | 'vet';

interface DevRow {
  player: PlayerDetails;
  history: OvrEntry[];
  /** OVR change at the last offseason; null when the player has no earlier season to compare with. */
  change: number | null;
  pot: number;
  pastPeak: boolean;
  room: number;
  stage: Stage;
}

interface DevelopmentTabProps {
  roster: PlayerDetails[];
  onOpenPlayer: (name: string) => void;
}

const RISING_MAX_AGE = 24;
const PRIME_MAX_AGE = 30;
/** The engine never raises the OVR of a player this old (gestisci_progressione_offseason). */
const PAST_PEAK_AGE = 32;
const TREND_SEASONS = 6;
const BAR_MIN = 50;
const BAR_MAX = 99;

const STAGE_LABEL: Record<Stage, string> = { rising: 'Rising', prime: 'Prime', vet: 'Veteran' };

const ATTR_LABELS: Record<string, string> = {
  three_point_shot_rating: '3-Point',
  mid_range_shot_rating: 'Mid-range',
  close_shot_rating: 'Close shot',
  free_throw_rating: 'Free throw',
  layup_rating: 'Layup',
  dunk_rating: 'Dunk',
  post_scoring_rating: 'Post scoring',
  passing_vision: 'Passing vision',
  passing_accuracy: 'Passing accuracy',
  ball_handling: 'Ball handling',
  interior_defense_rating: 'Interior D',
  perimeter_defense_rating: 'Perimeter D',
  steal_rating: 'Steal',
  block_rating: 'Block',
  offensive_rebound_rating: 'Off. rebound',
  defensive_rebound_rating: 'Def. rebound',
  offensive_iq_rating: 'Offensive IQ',
  defensive_iq_rating: 'Defensive IQ',
  shot_iq: 'Shot IQ',
  speed: 'Speed',
  acceleration: 'Acceleration',
  vertical: 'Vertical',
  strength: 'Strength',
  stamina: 'Stamina',
};

const attrLabel = (key: string) =>
  ATTR_LABELS[key] ?? key.replace(/_rating$/, '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

const seasonLabel = (year?: number) => (year ? `${year}–${String((year + 1) % 100).padStart(2, '0')}` : '–');

const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

const barPct = (ovr: number) => Math.max(0, Math.min(100, ((ovr - BAR_MIN) / (BAR_MAX - BAR_MIN)) * 100));

const stageOf = (age: number): Stage => (age <= RISING_MAX_AGE ? 'rising' : age <= PRIME_MAX_AGE ? 'prime' : 'vet');

const ChangeChip: React.FC<{ change: number | null }> = ({ change }) => {
  if (change === null) return <span className="dv-chip is-new">New</span>;
  if (change > 0) return <span className="dv-chip is-up">▲ {signed(change)}</span>;
  if (change < 0) return <span className="dv-chip is-down">▼ {change}</span>;
  return <span className="dv-chip is-flat">= 0</span>;
};

/** OVR line over seasons; the last point is green when it went up, red when it went down. */
const Trend: React.FC<{ values: number[]; width: number; height: number; label: string }> = ({ values, width, height, label }) => {
  const pad = 4;
  // Bigger charts (the report dialog) get a thicker line and dot.
  const dot = height > 40 ? 4.5 : 3;
  const stroke = height > 40 ? 2.2 : 1.6;
  if (values.length < 2) {
    return (
      <svg width={width} height={height} role="img" aria-label={label}>
        <circle cx={width - pad} cy={height / 2} r={dot} className="dv-dot is-new" />
      </svg>
    );
  }
  const lo = Math.min(...values) - 1;
  const hi = Math.max(...values) + 1;
  const points = values.map((v, i) => [
    pad + (i * (width - 2 * pad)) / (values.length - 1),
    height - pad - ((v - lo) / (hi - lo)) * (height - 2 * pad),
  ]);
  const [lastX, lastY] = points[points.length - 1];
  const last = values[values.length - 1];
  const prev = values[values.length - 2];
  return (
    <svg width={width} height={height} role="img" aria-label={label}>
      <polyline points={points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')} className="dv-line" strokeWidth={stroke} />
      <circle cx={lastX} cy={lastY} r={dot} className={`dv-dot ${last > prev ? 'is-up' : last < prev ? 'is-down' : ''}`} />
    </svg>
  );
};

const RoomBar: React.FC<{ row: DevRow }> = ({ row }) => {
  const ovr = row.player.ovr;
  const label = row.pastPeak ? 'Past peak' : row.room > 0 ? `${row.room} points below potential` : 'At potential';
  return (
    <div className="dv-room-cell">
      <div className="dv-room" role="img" aria-label={label} title={label}>
        <i className="dv-room-fill" style={{ width: `${barPct(ovr)}%` }} />
        {row.room > 0 && <i className="dv-room-left" style={{ left: `${barPct(ovr)}%`, width: `${barPct(ovr + row.room) - barPct(ovr)}%` }} />}
      </div>
      {row.pastPeak && <span className="dv-room-note" aria-hidden="true">past peak</span>}
    </div>
  );
};

const DevelopmentReport: React.FC<{ row: DevRow; onClose: () => void; onOpenProfile: () => void }> = ({ row, onClose, onOpenProfile }) => {
  const { player, history } = row;
  const attrChanges = Object.entries((player.last_progression?.attr_changes ?? {}) as Record<string, number>)
    .filter(([, delta]) => delta !== 0)
    .sort((a, b) => b[1] - a[1]);
  return (
    <ModalShell
      isOpen
      onClose={onClose}
      title="Development report"
      subtitle={`${player.nome} · ${normalizeRole(player.ruolo)} · Age ${player.eta}`}
      icon={<TrendingUp size={20} />}
      maxWidth={760}
      footerEnd={<button type="button" className="ms-btn ms-btn-primary" onClick={onOpenProfile}>Open full profile</button>}
    >
      <div className="dv-report">
        <section className="dv-paper">
          <h3 className="dv-paper-title">OVR by season</h3>
          {history.length === 0 ? (
            <p className="dv-empty">No season recorded yet. The first entry comes at the next offseason.</p>
          ) : (
            <>
              <Trend values={history.map((e) => e.ovr)} width={320} height={90} label={`OVR by season for ${player.nome}`} />
              <table className="dv-history">
                <thead><tr><th>Season</th><th>Age</th><th>OVR</th><th>Change</th></tr></thead>
                <tbody>
                  {history.map((entry, i) => {
                    const delta = i > 0 ? entry.ovr - history[i - 1].ovr : null;
                    return (
                      <tr key={`${entry.season}-${i}`}>
                        <td>{seasonLabel(entry.year)}</td>
                        <td>{entry.age ?? '–'}</td>
                        <td className="dv-num">{entry.ovr}</td>
                        <td className={delta === null || delta === 0 ? '' : delta > 0 ? 'is-up' : 'is-down'}>{delta === null ? '–' : signed(delta)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </section>
        <section className="dv-paper">
          <h3 className="dv-paper-title">Last offseason · attribute changes</h3>
          {attrChanges.length === 0 ? (
            <p className="dv-empty">No attribute changes recorded. They are written at each offseason and now kept in the save.</p>
          ) : (
            <div className="dv-attrs">
              {attrChanges.map(([key, delta]) => (
                <span key={key}>{attrLabel(key)}<b className={delta > 0 ? 'is-up' : 'is-down'}>{signed(delta)}</b></span>
              ))}
            </div>
          )}
        </section>
      </div>
    </ModalShell>
  );
};

export const DevelopmentTab: React.FC<DevelopmentTabProps> = ({ roster, onOpenPlayer }) => {
  const [openName, setOpenName] = useState<string | null>(null);

  const rows = useMemo<DevRow[]>(() => {
    // Kept in recorded order: an old bug wrote some entries with a wrong season number.
    const histories = roster.map((p) => (Array.isArray(p.ovr_history) ? (p.ovr_history as OvrEntry[]) : []));
    const lastOffseason = Math.max(-Infinity, ...histories.flatMap((h) => h.map((e) => e.season)));
    return roster.map((player, i) => {
      const history = histories[i];
      const last = history[history.length - 1];
      const change = history.length >= 2 && last.season === lastOffseason ? last.ovr - history[history.length - 2].ovr : null;
      const pot = player.potenziale ?? player.pot ?? player.ovr;
      const pastPeak = player.eta >= PAST_PEAK_AGE;
      return { player, history, change, pot, pastPeak, room: pastPeak ? 0 : Math.max(0, pot - player.ovr), stage: stageOf(player.eta) };
    }).sort((a, b) => (a.change === null ? 1 : 0) - (b.change === null ? 1 : 0) || (b.change ?? 0) - (a.change ?? 0) || b.player.ovr - a.player.ovr);
  }, [roster]);

  const known = rows.filter((r) => r.change !== null);
  // Rows are sorted by change, so the first and last known rows are the extremes.
  const top = known.at(0);
  const bottom = known.at(-1);
  const jump = top && top.change! > 0 ? top : null;
  const drop = bottom && bottom.change! < 0 ? bottom : null;
  const net = known.reduce((sum, r) => sum + (r.change ?? 0), 0);
  const improved = known.filter((r) => (r.change ?? 0) > 0).length;
  const newcomers = rows.length - known.length;
  const fromTo = (r: DevRow) => `${r.player.nome} · ${r.history[r.history.length - 2].ovr} → ${r.history[r.history.length - 1].ovr}`;

  const openRow = rows.find((r) => r.player.nome === openName) ?? null;

  return (
    <div className="dv-root">
      <div className="dv-tiles">
        <div className="rc-tile">
          <span className="rc-label">Biggest jump</span>
          <div className={`rc-big${jump ? ' is-good' : ''}`}>{jump ? signed(jump.change!) : '–'}</div>
          <span className="rc-note">{jump ? fromTo(jump) : 'Nobody improved'}</span>
        </div>
        <div className="rc-tile">
          <span className="rc-label">Biggest drop</span>
          <div className={`rc-big${drop ? ' is-bad' : ''}`}>{drop ? drop.change : '–'}</div>
          <span className="rc-note">{drop ? fromTo(drop) : 'Nobody dropped'}</span>
        </div>
        <div className="rc-tile">
          <span className="rc-label">Roster net change</span>
          <div className={`rc-big${net > 0 ? ' is-good' : net < 0 ? ' is-bad' : ''}`}>{known.length ? `${signed(net)} OVR` : '–'}</div>
          <span className="rc-note">across {known.length} returning player{known.length === 1 ? '' : 's'}</span>
        </div>
        <div className="rc-tile">
          <span className="rc-label">Improved</span>
          <div className="rc-big">{improved} <small>/ {known.length}</small></div>
          <span className="rc-note">{newcomers} new to the league</span>
        </div>
      </div>

      <div className="dv-sheet">
        <div className="pc-checklist-band"><span>Progress report · last offseason</span><span>sorted by change</span></div>
        {known.length === 0 && <p className="dv-empty dv-sheet-note">The first progress report comes after the first offseason. Until then every player shows as new.</p>}
        <table>
          <thead>
            <tr>
              <th>Player</th><th>Pos</th><th>Age</th><th>Change</th><th>OVR</th><th>Last {TREND_SEASONS} seasons</th><th>POT</th><th>Room to grow</th><th>Stage</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.player.nome}>
                <td><button type="button" className="pc-name" onClick={() => setOpenName(row.player.nome)}>{row.player.nome}</button></td>
                <td>{normalizeRole(row.player.ruolo)}</td>
                <td>{row.player.eta}</td>
                <td><ChangeChip change={row.change} /></td>
                <td className="pc-ovr">{row.player.ovr}</td>
                <td>
                  <Trend
                    values={row.history.length ? row.history.slice(-TREND_SEASONS).map((e) => e.ovr) : [row.player.ovr]}
                    width={96}
                    height={26}
                    label={`OVR trend for ${row.player.nome}`}
                  />
                </td>
                <td className="pc-pot">{row.pastPeak ? '–' : row.pot}</td>
                <td><RoomBar row={row} /></td>
                <td><span className={`dv-stage is-${row.stage}`}>{STAGE_LABEL[row.stage]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {openRow && (
        <DevelopmentReport
          row={openRow}
          onClose={() => setOpenName(null)}
          onOpenProfile={() => { setOpenName(null); onOpenPlayer(openRow.player.nome); }}
        />
      )}
    </div>
  );
};
