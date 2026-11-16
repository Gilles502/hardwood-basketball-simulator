// Phase 9 · New season ("report card + power rankings", stacked): your offseason before → after with every arrival
// and departure and how it happened, a grade, then the league's preseason power rankings and the summer's biggest
// moves. Payload: core/end_season_views.new_season_view.
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { crestHue } from '../../utils/crest';
import type { PhaseProps } from '../../utils/endSeason';

interface Move { name: string; position: string | null; age: number | null; ovr: number | null; how: string }
interface Tile { before: number | null; after: number | null }
interface NewSeason {
  report: {
    tiles: { strength: Tile; payroll: Tile; age: Tile; roster: { size: number; limit: number } };
    arrivals: Move[]; departures: Move[]; grade: string; grade_line: string; grade_note: string;
  } | null;
  rankings: { rank: number; team: string; strength: number; moved: number | null; yours: boolean }[];
  moves: string[];
}

/** Power ranking rows before "all N teams". */
const RANKING_ROWS = 10;
const money = (v: number | null) => (v == null ? '—' : `$${v.toFixed(1)}M`);

const howClass = (how: string) => {
  if (how.startsWith('Draft')) return 'is-draft';
  if (how.startsWith('FA') || how.startsWith('Signed')) return 'is-fa';
  if (how.startsWith('Trade')) return 'is-trade';
  if (how === 'Retired' || how === 'Left in FA') return 'is-gone';
  return 'is-out';
};

export const NewSeasonPhase: React.FC<PhaseProps> = () => {
  const { openPlayerProfile, openTeamProfile } = useLeagueStore();
  const [view, setView] = useState<NewSeason | null>(null);
  const [failed, setFailed] = useState(false);
  const [allTeams, setAllTeams] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/offseason/new_season?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data) => { if (!cancelled) (data && Array.isArray(data.rankings) ? setView(data) : setFailed(true)); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, []);

  if (failed) return <div className="eos-sheet"><p className="eos-muted">The new season summary could not be loaded.</p></div>;
  if (!view) return <div className="eos-sheet"><p className="eos-muted">Loading…</p></div>;

  const { report } = view;
  const tile = (label: string, t: Tile, fmt: (v: number | null) => string, note: (d: number) => string, goodUp = true) => {
    const d = t.before != null && t.after != null ? t.after - t.before : null;
    return (
      <div className="ns-tile">
        <span>{label}</span>
        <b>{t.before != null && t.before !== t.after && <s>{fmt(t.before)}</s>}{fmt(t.after)}</b>
        {d != null && d !== 0 && <em className={(d > 0) === goodUp ? 'co-good' : 'co-bad'}>{note(d)}</em>}
      </div>
    );
  };
  const moveList = (title: string, rows: Move[]) => (
    <section className="rc-card">
      <h3 className="rc-h">{title} · {rows.length}</h3>
      {rows.length === 0 ? <p className="eos-muted">Nobody.</p> : rows.map((m) => (
        <div key={m.name} className="ns-move">
          <span><button type="button" className="eos-link ns-name" onClick={() => openPlayerProfile(m.name)}>{m.name}</button> <small className="co-dim">{m.position}{m.age != null ? ` · ${m.age}` : ''}</small></span>
          <span className={`ns-how ${howClass(m.how)}`}>{m.how}</span>
          <b>{m.ovr ?? ''}</b>
        </div>
      ))}
    </section>
  );
  const rankings = allTeams ? view.rankings : view.rankings.slice(0, RANKING_ROWS);

  return (
    <div className="ns-root">
      {report ? (
        <>
          <div className="ns-tiles">
            {tile('Top-8 OVR', report.tiles.strength, (v) => (v == null ? '—' : v.toFixed(1)), (d) => `${d > 0 ? '+' : ''}${d.toFixed(1)}`)}
            {tile('Payroll', report.tiles.payroll, money, (d) => `${d > 0 ? '+' : '−'}${money(Math.abs(d))}`, false)}
            {tile('Average age', report.tiles.age, (v) => (v == null ? '—' : v.toFixed(1)), (d) => (d < 0 ? 'younger' : 'older'), false)}
            <div className="ns-tile"><span>Roster</span><b>{report.tiles.roster.size} / {report.tiles.roster.limit}</b>
              <em className="co-dim">{Math.max(0, report.tiles.roster.limit - report.tiles.roster.size)} open spot{report.tiles.roster.limit - report.tiles.roster.size === 1 ? '' : 's'}</em></div>
          </div>
          <div className="ns-inout">{moveList('Arrivals', report.arrivals)}{moveList('Departures', report.departures)}</div>
          <div className="eos-sheet ns-grade">
            <div className="ns-letter">{report.grade}</div>
            <p><b>{report.grade_line}</b> {report.grade_note}</p>
          </div>
        </>
      ) : (
        <div className="eos-sheet"><p className="eos-muted">No snapshot from the start of this offseason (older save or spectator mode). The league is set.</p></div>
      )}

      <div className="ns-league">
        <section>
          <h3 className="co-h">Preseason power rankings</h3>
          {rankings.map((r) => (
            <div key={r.team} className={`ns-rank${r.yours ? ' is-yours' : ''}`}>
              <span className="ns-r">{r.rank}</span>
              <span className="ns-crest" style={{ background: `hsl(${crestHue(r.team)} 58% 38%)` }} />
              <button type="button" className="eos-link ns-team" onClick={() => openTeamProfile(r.team)}>{r.team}</button>
              <b>{r.strength.toFixed(1)}</b>
              <span className={r.moved == null ? 'co-dim' : r.moved > 0 ? 'co-good' : r.moved < 0 ? 'co-bad' : 'co-dim'}>
                {r.moved == null ? '' : r.moved > 0 ? `▲ ${r.moved}` : r.moved < 0 ? `▼ ${-r.moved}` : '–'}
              </span>
            </div>
          ))}
          {view.rankings.length > RANKING_ROWS && (
            <button type="button" className="dv-more" onClick={() => setAllTeams(!allTeams)}>
              {allTeams ? 'Top 10 only' : `All ${view.rankings.length} teams`}
            </button>
          )}
        </section>
        <section className="rc-card">
          <h3 className="rc-h">Biggest moves around the league</h3>
          {view.moves.length === 0 ? <p className="eos-muted">A quiet summer.</p> : (
            <ul className="rc-rows td-wire">{view.moves.map((m, i) => <li key={i}>{m}</li>)}</ul>
          )}
        </section>
      </div>
    </div>
  );
};
