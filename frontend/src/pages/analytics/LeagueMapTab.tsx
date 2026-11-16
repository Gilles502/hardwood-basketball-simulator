// League Map tab (mockup "A — the map first"): efficiency matrix (ORTG × DRTG) beside the expected-wins board, the
// league's pulse month by month, then the league baseline and how every number is calculated. /api/analytics/league.
import React, { useState } from 'react';
import { nickname } from '../../utils/resultSheet';
import type { LeaguePayload, MapTeam, MonthPulse } from './types';
import { fmt, fmtSigned, useAnalyticsData } from './useAnalyticsData';

const W = 640;
const H = 440;
const PAD = { l: 44, r: 14, t: 30, b: 56 };   // quadrant labels sit in the top and bottom bands, outside the dots

export const LeagueMapTab: React.FC<{ onOpenTeam: (name: string) => void }> = ({ onOpenTeam }) => {
  const { data, failed } = useAnalyticsData<LeaguePayload>('/api/analytics/league');
  if (!data && !failed) return <div className="an-loading"><div className="spinner"></div></div>;
  if (!data) return <div className="an-empty"><h2>The league map could not be loaded</h2></div>;
  if (data.meta.games === 0) return <div className="an-empty"><h2>No games played yet this season</h2></div>;

  const { meta, exponent, baseline } = data;
  return (
    <div className="an-root">
      <div className="an-map">
        <div className="an-panel an-pad"><Matrix data={data} onOpenTeam={onOpenTeam} /></div>
        <div className="an-panel an-pad">
          <div className="an-hd">Expected wins vs real</div>
          <LuckBoard teams={data.teams} onOpenTeam={onOpenTeam} />
        </div>
      </div>

      <div className="an-pulse">
        <Spark label="Points per team-game" months={data.months} pick={(m) => m.ppg} />
        <Spark label="Pace (possessions)" months={data.months} pick={(m) => m.pace} />
        <Spark label="eFG%" months={data.months} pick={(m) => m.efg} />
        <Spark label="3PA rate %" months={data.months} pick={(m) => m.tpa_rate} />
        <Spark label="Home win %" months={data.months} pick={(m) => m.home_win_pct} />
      </div>

      <div className="an-sheet an-baseline">
        <div className="an-kicker">League baseline{meta.season ? ` ${meta.season}` : ''} · {meta.games} games</div>
        <div className="an-figures">
          {([['PTS / team-game', baseline.ppg], ['ORTG (avg)', baseline.ortg], ['Pace', baseline.pace], ['eFG%', baseline.efg],
            ['TS%', baseline.ts], ['TOV%', baseline.tov_pct], ['3PA rate', baseline.tpa_rate], ['Home win %', baseline.home_win_pct]] as const).map(([l, v]) => (
            <div key={l}><b>{fmt(v)}</b><span>{l}</span></div>
          ))}
        </div>
        <div className="an-card-sub">How it's calculated</div>
        <ul className="an-how">
          <li><b>Possessions</b> = FGA + {meta.fta_weight} × FTA + turnovers, averaged with the opponent. The game does not record offensive rebounds, so ratings (points per 100 possessions) run lower than real-world numbers.</li>
          <li><b>Expected wins</b> use the Pythagorean formula (points scored and allowed) with an exponent {exponent.fitted
            ? <>fitted to this season's results: <b>{exponent.value.toFixed(1)}</b> (typical error ±{fmt(exponent.rmse)} wins)</>
            : <>of <b>{exponent.value.toFixed(1)}</b> until every team has played enough games to fit one</>}. Luck = wins − expected wins.</li>
          <li><b>Game Score</b> and <b>PER (est.)</b> assume {Math.round(meta.oreb_share * 100)}% of rebounds are offensive (only totals are recorded). PER is scaled so the league average is {meta.per_avg}. A close game is decided by {meta.close_margin} points or fewer.</li>
          <li><b>Percentiles</b> compare qualified players (at least {Math.round(meta.qualify_gp_share * 100)}% of their team's games and {meta.qualify_mpg} minutes per game) and all 30 teams. Cells are tinted in the top {100 - meta.tint_top}% and bottom {meta.tint_bottom}%.</li>
          <li><b>Usage, AST% and per-100 stats</b> use the team totals of the games each player actually played. Regular season only.</li>
        </ul>
      </div>
    </div>
  );
};

const Matrix: React.FC<{ data: LeaguePayload; onOpenTeam: (name: string) => void }> = ({ data, onOpenTeam }) => {
  const [hover, setHover] = useState<MapTeam | null>(null);
  const teams = data.teams.filter((t) => t.ortg !== null && t.drtg !== null);
  if (teams.length === 0) return null;
  const xs = teams.map((t) => t.ortg as number);
  const ys = teams.map((t) => t.drtg as number);
  const [x0, x1] = [Math.min(...xs) - 1, Math.max(...xs) + 1];
  const [y0, y1] = [Math.min(...ys) - 1, Math.max(...ys) + 1];
  const X = (v: number) => PAD.l + ((v - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + ((v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);   // low DRTG (good) at the top
  const byNet = [...teams].sort((a, b) => (b.net ?? 0) - (a.net ?? 0));
  const labelled = new Set([...byNet.slice(0, 4), ...byNet.slice(-2), ...teams.filter((t) => t.is_user_team)].map((t) => t.name));
  // Label placement: try right, left, below, above the dot; keep the first spot that covers no other dot or label.
  const dots = teams.map((t) => ({ x: X(t.ortg as number), y: Y(t.drtg as number) }));
  const boxes: { x0: number; x1: number; y0: number; y1: number }[] = [];
  const labels = new Map<string, { x: number; y: number; anchor: 'start' | 'middle' | 'end' }>();
  for (const t of byNet.filter((b) => labelled.has(b.name))) {
    const cx = X(t.ortg as number);
    const cy = Y(t.drtg as number);
    const w = nickname(t.name).length * 7 + 4;
    const spots = [
      { x: cx + 9, y: cy + 4, anchor: 'start' as const, x0: cx + 8, x1: cx + 8 + w },
      { x: cx - 9, y: cy + 4, anchor: 'end' as const, x0: cx - 8 - w, x1: cx - 8 },
      { x: cx, y: cy + 19, anchor: 'middle' as const, x0: cx - w / 2, x1: cx + w / 2 },
      { x: cx, y: cy - 10, anchor: 'middle' as const, x0: cx - w / 2, x1: cx + w / 2 },
      { x: cx + 6, y: cy + 19, anchor: 'end' as const, x0: cx + 6 - w, x1: cx + 6 },
      { x: cx + 6, y: cy - 10, anchor: 'end' as const, x0: cx + 6 - w, x1: cx + 6 },
    ].map((sp) => ({ ...sp, y0: sp.y - 11, y1: sp.y + 3 }));
    type Box = { x0: number; x1: number; y0: number; y1: number };
    const inside = (b: Box) => b.x0 >= PAD.l && b.x1 <= W - PAD.r && b.y0 >= PAD.t - 4 && b.y1 <= H - PAD.b + 4;
    const clearOfLabels = (b: Box) => !boxes.some((o) => b.x0 < o.x1 && b.x1 > o.x0 && b.y0 < o.y1 && b.y1 > o.y0);
    const dotsUnder = (b: Box) =>
      dots.filter((d) => !(d.x === cx && d.y === cy) && d.x > b.x0 - 5 && d.x < b.x1 + 5 && d.y > b.y0 - 5 && d.y < b.y1 + 5).length;
    // Inside the plot and clear of other labels, covering as few dots as possible (ties keep the order above).
    const fits = spots.filter((b) => inside(b) && clearOfLabels(b));
    const spot = fits.length ? fits.reduce((best, b) => (dotsUnder(b) < dotsUnder(best) ? b : best)) : spots.find(inside) ?? spots[0];
    boxes.push(spot);
    labels.set(t.name, { x: spot.x, y: spot.y, anchor: spot.anchor });
  }
  const avg = data.league_avg;

  return (
    <div className="an-matrix">
      <div className="an-hd">Efficiency matrix</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Offensive rating against defensive rating for every team">
        {avg.ortg !== null && <line className="an-mid" x1={X(avg.ortg)} x2={X(avg.ortg)} y1={PAD.t} y2={H - PAD.b} />}
        {avg.drtg !== null && <line className="an-mid" x1={PAD.l} x2={W - PAD.r} y1={Y(avg.drtg)} y2={Y(avg.drtg)} />}
        <text className="an-q" x={W - PAD.r - 4} y={PAD.t - 12} textAnchor="end">CONTENDERS ↗</text>
        <text className="an-q" x={PAD.l + 6} y={PAD.t - 12}>↖ DEFENSE FIRST</text>
        <text className="an-q" x={W - PAD.r - 4} y={H - PAD.b + 20} textAnchor="end">OFFENSE ONLY ↘</text>
        <text className="an-q" x={PAD.l + 6} y={H - PAD.b + 20}>↙ REBUILDING</text>
        <text className="an-ax" x={(W + PAD.l) / 2} y={H - 8} textAnchor="middle">Offensive rating → better</text>
        <text className="an-ax" x={14} y={(H - PAD.b + PAD.t) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(H - PAD.b + PAD.t) / 2})`}>Defensive rating → better</text>
        {[...teams].sort((a, b) => Number(a.is_user_team) - Number(b.is_user_team)).map((t) => {
          const cx = X(t.ortg as number);
          const cy = Y(t.drtg as number);
          return (
            <g key={t.name} className="an-dot-g" tabIndex={0} role="button" aria-label={`${t.name}: ORTG ${fmt(t.ortg)}, DRTG ${fmt(t.drtg)}, net ${fmtSigned(t.net)}`}
              onMouseEnter={() => setHover(t)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(t)} onBlur={() => setHover(null)}
              onClick={() => onOpenTeam(t.name)} onKeyDown={(e) => { if (e.key === 'Enter') onOpenTeam(t.name); }}>
              <circle cx={cx} cy={cy} r={12} className="an-hit" />
              <circle cx={cx} cy={cy} r={t.is_user_team ? 7 : 5} className={t.is_user_team ? 'an-dot is-mine' : 'an-dot'} />
              {labels.has(t.name) && (
                <text x={labels.get(t.name)!.x} y={labels.get(t.name)!.y} textAnchor={labels.get(t.name)!.anchor}
                  className={t.is_user_team ? 'an-lbl is-mine' : 'an-lbl'}>{nickname(t.name)}</text>
              )}
            </g>
          );
        })}
      </svg>
      {hover && (
        <div className="an-tip" style={{ left: `${(X(hover.ortg as number) / W) * 100}%`, top: `${(Y(hover.drtg as number) / H) * 100}%` }}>
          <b>{hover.name}</b><span>ORTG {fmt(hover.ortg)} · DRTG {fmt(hover.drtg)} · Net {fmtSigned(hover.net)}</span>
        </div>
      )}
    </div>
  );
};

const LuckBoard: React.FC<{ teams: MapTeam[]; onOpenTeam: (name: string) => void }> = ({ teams, onOpenTeam }) => {
  const rows = [...teams].filter((t) => t.luck !== null).sort((a, b) => (b.luck as number) - (a.luck as number));
  const max = Math.max(1, ...rows.map((t) => Math.abs(t.luck as number)));
  return (
    <div className="an-luck">
      <div className="an-luck-row an-luck-head"><span>Team</span><span>W</span><span>EXP</span><span className="an-luck-axis">◀ fewer wins than points say · more ▶</span><span>LUCK</span></div>
      {rows.map((t) => {
        const w = (Math.abs(t.luck as number) / max) * 100;
        return (
          <button key={t.name} type="button" className={`an-luck-row${t.is_user_team ? ' is-mine' : ''}`} onClick={() => onOpenTeam(t.name)}>
            <span className="an-luck-name">{nickname(t.name)}</span>
            <span>{t.w}</span><span>{fmt(t.exp_w)}</span>
            <span className="an-luck-bars">
              <span className="an-luck-neg">{(t.luck as number) < 0 && <i style={{ width: `${w}%` }} />}</span>
              <span className="an-luck-pos">{(t.luck as number) > 0 && <i style={{ width: `${w}%` }} />}</span>
            </span>
            <span>{fmtSigned(t.luck)}</span>
          </button>
        );
      })}
    </div>
  );
};

const Spark: React.FC<{ label: string; months: MonthPulse[]; pick: (m: MonthPulse) => number | null }> = ({ label, months, pick }) => {
  const pts = months.map((m) => ({ m, v: pick(m) })).filter((p): p is { m: MonthPulse; v: number } => p.v !== null);
  const last = pts[pts.length - 1];
  const first = pts[0];
  const lo = Math.min(...pts.map((p) => p.v));
  const hi = Math.max(...pts.map((p) => p.v));
  const span = hi - lo || 1;
  const w = 160;
  const h = 40;
  const at = (i: number) => (pts.length > 1 ? 5 + (i * (w - 10)) / (pts.length - 1) : w / 2);
  const line = pts.map((p, i) => `${at(i).toFixed(1)},${(6 + ((hi - p.v) / span) * (h - 12)).toFixed(1)}`).join(' ');
  return (
    <div className="an-spark" title={pts.map((p) => `${p.m.label} ${p.v.toFixed(1)} (${p.m.games} games)`).join('\n')}>
      <div className="an-hd">{label}</div>
      <div className="an-spark-v">{last ? last.v.toFixed(1) : '—'}{first && last && pts.length > 1 && <small> {first.v.toFixed(1)} → {last.v.toFixed(1)}</small>}</div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
        {pts.length > 1 ? <polyline points={line} /> : <circle cx={w / 2} cy={h / 2} r={3} />}
      </svg>
      <div className="an-spark-x"><span>{first?.m.label ?? ''}</span><span>{last?.m.label ?? ''}</span></div>
    </div>
  );
};
