// Career progression (mockup B "Progression"): OVR solid and POT dashed on the left scale, one per-game stat on the
// right scale, a trophy over title seasons, gaps where a season has no record. Inline SVG like the League Map.
import React from 'react';
import type { PlayerPayload } from './types';

const W = 720, H = 240, L = 40, R = 44, T = 22, B = 30;

type Point = { year: number; ovr: number | null; pot: number | null; stat: number | null; champion: boolean };

/** Polyline paths, broken wherever a year has no value. */
function segments(points: Point[], value: (p: Point) => number | null, x: (y: number) => number, y: (v: number) => number): string[] {
  const out: string[] = [];
  let run: string[] = [];
  let prevYear: number | null = null;
  for (const p of points) {
    const v = value(p);
    if (v === null || (prevYear !== null && p.year !== prevYear + 1)) {
      if (run.length > 1) out.push(run.join(' '));
      run = [];
    }
    if (v !== null) run.push(`${x(p.year).toFixed(1)},${y(v).toFixed(1)}`);
    prevYear = p.year;
  }
  if (run.length > 1) out.push(run.join(' '));
  return out;
}

export const ProgressionChart: React.FC<{ progression: PlayerPayload['progression']; stat: string; statLabel: string }> = ({ progression, stat, statLabel }) => {
  const points: Point[] = progression
    .filter((p) => p.year !== null)
    .map((p) => ({ year: p.year as number, ovr: p.ovr, pot: p.pot, stat: (p[stat] as number | null) ?? null, champion: p.champion }));
  if (points.length === 0) return <p className="an-none">No seasons to chart yet.</p>;

  const first = points[0].year, last = points[points.length - 1].year;
  const span = Math.max(1, last - first);
  const x = (yr: number) => L + ((yr - first) / span) * (W - L - R);
  const ratings = points.flatMap((p) => [p.ovr, p.pot]).filter((v): v is number => v !== null);
  const lo = Math.max(0, Math.floor((Math.min(...ratings, 100) - 5) / 10) * 10), hi = 100;
  const yL = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const statMax = Math.max(1, ...points.map((p) => p.stat ?? 0)) * 1.1;
  const yR = (v: number) => T + (1 - v / statMax) * (H - T - B);
  const years = Array.from({ length: last - first + 1 }, (_, i) => first + i);
  const step = Math.ceil(years.length / 12);
  const ticks = [lo, Math.round((lo + hi) / 2), hi];

  return (
    <div className="db-chart">
      <div className="db-legend">
        <span><i className="is-ovr" />OVR</span><span><i className="is-pot" />POT</span><span><i className="is-stat" />{statLabel} (right scale)</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`OVR, POT and ${statLabel} by season`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={yL(t)} y2={yL(t)} className="db-grid" />
            <text x={L - 8} y={yL(t) + 4} textAnchor="end" className="db-axis">{t}</text>
          </g>
        ))}
        {[0, statMax / 2.2, statMax / 1.1].map((v) => (
          <text key={v} x={W - R + 8} y={yR(v) + 4} className="db-axis">{v.toFixed(v < 10 ? 1 : 0)}</text>
        ))}
        {years.map((yr, i) => (i % step === 0 || yr === last) && (
          <text key={yr} x={x(yr)} y={H - 8} textAnchor="middle" className="db-axis">{yr}</text>
        ))}
        {segments(points, (p) => p.pot, x, yL).map((d) => <polyline key={`p${d}`} points={d} className="db-line is-pot" />)}
        {segments(points, (p) => p.ovr, x, yL).map((d) => <polyline key={`o${d}`} points={d} className="db-line is-ovr" />)}
        {segments(points, (p) => p.stat, x, yR).map((d) => <polyline key={`s${d}`} points={d} className="db-line is-stat" />)}
        {points.map((p) => p.ovr !== null && (
          <g key={p.year}>
            <circle cx={x(p.year)} cy={yL(p.ovr)} r={p.champion ? 4 : 2.5} className="db-dot" />
            {p.champion && <text x={x(p.year)} y={yL(p.ovr) - 8} textAnchor="middle" fontSize="12">🏆</text>}
          </g>
        ))}
      </svg>
    </div>
  );
};
