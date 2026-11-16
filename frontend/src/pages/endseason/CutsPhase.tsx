// Phase 8 · Roster cuts ("cut sheet — you choose"): your roster in cut order with the game's picks pre-marked;
// swap Release / Keep until you're at the limit. The list travels with the hub's "Next" call and the server applies
// it before cutting every other team (core/roster_cuts.py). Payload: core/end_season_views.cut_sheet_view.
import React, { useEffect, useMemo, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import type { PhaseProps } from '../../utils/endSeason';

interface Row {
  name: string; position: string; age: number; ovr: number; potential: number; salary: number;
  protected: boolean; new: boolean; engine_pick: boolean;
}
interface Sheet {
  target: number; size: number; to_release: number; payroll: number; rows: Row[];
  league: { team: string; name: string; ovr: number; age: number }[];
}

const money = (v: number) => `$${v.toFixed(1)}M`;
/** League cuts shown before "+N more". */
const LEAGUE_ROWS = 6;

export const CutsPhase: React.FC<PhaseProps> = ({ readOnly, onBar }) => {
  const { leagueData, openPlayerProfile } = useLeagueStore();
  const userTeam = leagueData?.player_team_name ?? null;
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [released, setReleased] = useState<Set<string>>(new Set());
  const released_log: string[] = leagueData?.offseason?.user_releases ?? [];

  useEffect(() => {
    if (readOnly) return;
    let cancelled = false;
    fetch(`/api/offseason/cut_preview?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data: Sheet) => {
        if (cancelled || !data || !Array.isArray(data.rows)) return;
        setSheet(data);
        setReleased(new Set(data.rows.filter((r) => r.engine_pick).map((r) => r.name)));
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [readOnly]);

  const remaining = sheet ? sheet.size - released.size : 0;
  useEffect(() => {
    if (readOnly) return;
    if (!sheet) { onBar({ blocking: 'Loading the cut sheet…' }); return; }
    if (!userTeam) { onBar({}); return; }
    const more = remaining - sheet.target;
    onBar(more > 0
      ? { blocking: `Release ${more} more` }
      : { nextLabel: released.size ? `Release ${released.size} · Next: New season →` : undefined, payload: { releases: [...released] } });
  }, [sheet, released, remaining, userTeam, readOnly, onBar]);

  const positions = useMemo(() => {
    const count: Record<string, number> = {};
    sheet?.rows.filter((r) => !released.has(r.name)).forEach((r) => { count[r.position] = (count[r.position] || 0) + 1; });
    return ['PG', 'SG', 'SF', 'PF', 'C'].map((p) => `${p} ${count[p] || 0}`).join(' · ');
  }, [sheet, released]);

  if (readOnly) {
    return (
      <div className="eos-sheet">
        <span className="eos-kicker">Cut-down day is over</span>
        <p className="eos-line">{released_log.length ? `You released ${released_log.join(', ')}.` : 'You released nobody.'} Every roster is within the limit.</p>
      </div>
    );
  }
  if (!sheet) return <div className="eos-sheet"><p className="eos-muted">Loading the cut sheet…</p></div>;

  const toggle = (name: string) => setReleased((prev) => {
    const next = new Set(prev);
    if (next.has(name)) next.delete(name); else next.add(name);
    return next;
  });
  const payrollAfter = sheet.rows.filter((r) => !released.has(r.name)).reduce((sum, r) => sum + r.salary, 0);
  const over = remaining - sheet.target;

  return (
    <div className="cs-root">
      {userTeam && (
        <div className="cs-count">
          <div className="cs-big">{sheet.size} → {remaining}</div>
          <div className="cs-dots" aria-hidden="true">
            {sheet.rows.map((r, i) => (
              <i key={r.name} className={`${released.has(r.name) ? 'is-out' : ''}${i === sheet.target - 1 ? ' is-limit' : ''}`} />
            ))}
          </div>
          <div className="cs-status">
            Limit {sheet.target} · {over > 0 ? <span className="co-bad">release {over} more</span> : <span className="co-good">ready</span>}
          </div>
        </div>
      )}

      <div className="dv-split">
        {userTeam ? (
          <section className="rc-card">
            <table className="cs-table">
              <thead><tr><th>Player</th><th>Pos</th><th>Age</th><th>OVR</th><th>Pot</th><th className="r">Salary</th><th className="r" /></tr></thead>
              <tbody>
                {sheet.rows.map((r) => {
                  const out = released.has(r.name);
                  return (
                    <tr key={r.name} className={out ? 'is-out' : undefined}>
                      <td className="cs-name">
                        <button type="button" className="eos-link" onClick={() => openPlayerProfile(r.name)}>{r.name}</button>
                        {r.new && <span className="cs-tag is-new">new</span>}
                      </td>
                      <td>{r.position}</td><td>{r.age}</td><td className="cs-ovr">{r.ovr}</td><td>{r.potential}</td>
                      <td className="r">{money(r.salary)}</td>
                      <td className="r cs-act">
                        {r.engine_pick && <span className="cs-tag is-auto">game's pick</span>}
                        {r.protected && !out && <span className="cs-tag is-prot">protected</span>}
                        <button type="button" className={`cs-btn ${out ? 'is-keep' : 'is-release'}`} onClick={() => toggle(r.name)}>
                          {out ? 'Keep' : 'Release'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        ) : <div className="eos-sheet"><p className="eos-muted">Spectator mode: every team cuts down by itself.</p></div>}

        <div className="co-col">
          {userTeam && (
            <section className="rc-card">
              <h3 className="rc-h">After your cuts</h3>
              <ul className="rc-rows">
                <li><span>Roster</span><b>{remaining} / {sheet.target}</b></li>
                <li><span>Payroll</span><b>{money(payrollAfter)}</b></li>
                <li><span>By position</span><span className="co-dim">{positions}</span></li>
              </ul>
            </section>
          )}
          <section className="rc-card">
            <h3 className="rc-h">Around the league · {sheet.league.length} cuts</h3>
            {sheet.league.length === 0 ? <p className="eos-muted">Every other team is within the limit.</p> : (
              <ul className="rc-rows">
                {sheet.league.slice(0, LEAGUE_ROWS).map((p) => (
                  <li key={`${p.team}-${p.name}`}>
                    <span><button type="button" className="eos-link" onClick={() => openPlayerProfile(p.name)}>{p.name}</button> <small className="co-dim">{p.ovr} · {p.team}</small></span>
                    <span className="co-dim">→ FA</span>
                  </li>
                ))}
              </ul>
            )}
            {sheet.league.length > LEAGUE_ROWS && <p className="eos-muted co-more">+{sheet.league.length - LEAGUE_ROWS} more · they join the free-agent pool</p>}
          </section>
        </div>
      </div>
    </div>
  );
};
