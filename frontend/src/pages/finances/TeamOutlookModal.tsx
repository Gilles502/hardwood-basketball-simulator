// File: frontend/src/pages/finances/TeamOutlookModal.tsx
// A team's 4-year outlook as a payroll sheet: a "right now" panel for the current season, then one row per
// contract and one column per season. A contract's last season is a hatched "expiring" cell; the next season
// shows a FREE AGENT tag and the row stays empty after that.
import React, { useEffect, useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { ModalShell } from '../../components/ModalShell';
import { useLeagueStore } from '../../store/leagueStore';
import { STATUS_STAMPS, capLines, money, outlookSentence, seasonFacts, seasonLabel } from '../../utils/finances';
import type { OutlookSeason, TeamOutlook } from '../../utils/finances';
import './TeamOutlook.css';

interface TeamOutlookModalProps {
  teamName: string;
  /** Teams offered by the picker in the header. */
  teams: string[];
  onClose: () => void;
}

/** Payroll bar against the season's lines (floor, cap, tax, aprons). The big one labels its lines. */
const CapGauge: React.FC<{ season: OutlookSeason; big?: boolean }> = ({ season, big = false }) => {
  const lines = capLines(season);
  if (lines.length === 0) return null;
  const top = Math.max(lines[lines.length - 1].value * 1.08, season.payroll * 1.05);
  const pct = (value: number) => `${Math.min(100, (value / top) * 100).toFixed(1)}%`;
  return (
    <div
      className={`to-gauge${big ? ' is-big' : ''}`}
      role="img"
      aria-label={`Payroll ${money(season.payroll)}. ${lines.map((l) => `${l.label} ${money(l.value)}`).join(', ')}.`}
    >
      <i className={`to-fill st-${season.status}`} style={{ width: pct(season.payroll) }} />
      {lines.map((line, index) => (
        <b
          key={line.key}
          className={`to-line ln-${line.key}${big && index % 2 === 0 ? ' is-low' : ''}${big && line.value / top > 0.8 ? ' is-end' : ''}`}
          style={{ left: pct(line.value) }}
        >
          {big && <span>{line.label} {money(line.value)}</span>}
        </b>
      ))}
    </div>
  );
};

const Stamp: React.FC<{ season: OutlookSeason }> = ({ season }) => (
  <span className={`to-stamp st-${season.status}`}>{STATUS_STAMPS[season.status]}</span>
);

export const TeamOutlookModal: React.FC<TeamOutlookModalProps> = ({ teamName, teams, onClose }) => {
  const { leagueData, openPlayerProfile } = useLeagueStore();
  const [team, setTeam] = useState(teamName);
  const [outlook, setOutlook] = useState<TeamOutlook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isUser = leagueData?.player_team_name === team;

  useEffect(() => {
    let cancelled = false;
    setOutlook(null);
    setError(null);
    fetch(`/api/economy/team-multi-year/${encodeURIComponent(team)}`)
      .then((response) => response.json())
      .then((data) => {
        if (cancelled) return;
        if (data.error) setError(data.error);
        else if (!Array.isArray(data.seasons)) setError('The server sent the outlook in an old format. Restart the backend and try again.');
        else setOutlook(data);
      })
      .catch(() => { if (!cancelled) setError('Failed to load the salary outlook.'); });
    return () => { cancelled = true; };
  }, [team]);

  const picker = (
    <select className="to-pick" value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Team">
      {[...teams].sort((a, b) => a.localeCompare(b)).map((name) => (
        <option key={name} value={name}>{name}</option>
      ))}
    </select>
  );

  const now = outlook?.seasons[0];
  const anyApron = outlook?.seasons.some((s) => s.first_apron !== null) ?? false;

  return (
    <ModalShell
      isOpen
      onClose={onClose}
      title={`4-year outlook · ${team}`}
      subtitle="Committed salary by season · free agents leave the sheet"
      icon={<BarChart3 size={20} />}
      headerActions={picker}
      maxWidth={1120}
    >
      {error && <div className="to-empty">{error}</div>}
      {!error && !outlook && (
        <div className="to-empty"><div className="spinner"></div></div>
      )}
      {outlook && now && (
        <div className="to-root">
          <section className={`to-now st-${now.status}`}>
            <div>
              <div className="to-kicker">Right now · {seasonLabel(now.year)}{isUser && <span className="to-you">Your team</span>}</div>
              <div className="to-pay">{money(now.payroll)}</div>
              <Stamp season={now} />
              <p className="to-sentence">{outlookSentence(outlook, isUser)}</p>
            </div>
            <div className="to-now-right">
              <div className="to-facts">
                {seasonFacts(now).map((fact) => (
                  <div key={fact.label}>
                    <b className={`tone-${fact.tone}`}>{money(fact.value)}</b>
                    <span>{fact.label}</span>
                  </div>
                ))}
              </div>
              <CapGauge season={now} big />
            </div>
          </section>

          <section className="to-sheet">
            <table>
              <colgroup>
                <col className="to-col-player" />
                {outlook.seasons.map((s) => <col key={s.year ?? 0} />)}
              </colgroup>
              <thead>
                <tr>
                  <th>Player<small>role · OVR · age now</small></th>
                  {outlook.seasons.map((s, i) => {
                    const room = s.salary_cap === null ? null : s.salary_cap - s.payroll;
                    return (
                      <th key={s.year ?? i} className={i === 0 ? 'is-now' : undefined}>
                        <div className="to-yr">{seasonLabel(s.year)}{i === 0 ? ' · now' : ''}</div>
                        <div className="to-yr-pay">{money(s.payroll)}</div>
                        <div className="to-yr-stamp"><Stamp season={s} /></div>
                        <CapGauge season={s} />
                        {room !== null && (
                          <div className={`to-yr-room ${room >= 0 ? 'tone-good' : 'tone-bad'}`}>
                            {money(Math.abs(room))} {room >= 0 ? 'room' : 'over the cap'}
                          </div>
                        )}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {outlook.players.map((p) => {
                  const firstGone = p.salaries.findIndex((s) => s === null);
                  return (
                    <tr key={p.name}>
                      <td>
                        <button type="button" className="to-player" onClick={() => openPlayerProfile(p.name)}>{p.name}</button>
                        <small>{p.role} · {p.ovr} · {p.age}</small>
                      </td>
                      {p.salaries.map((salary, i) => {
                        const nowCls = i === 0 ? ' is-now' : '';
                        if (salary === null) {
                          return <td key={i} className={nowCls.trim() || undefined}>{i === firstGone && <span className="to-fa">Free agent</span>}</td>;
                        }
                        // Last season under contract: the next season is empty, or the contract ends exactly with the sheet.
                        const last = i + 1 < p.salaries.length ? p.salaries[i + 1] === null : p.years_left === p.salaries.length;
                        return (
                          <td key={i} className={`${last ? 'is-last' : ''}${nowCls}`.trim() || undefined}>
                            {money(salary)}
                            {last && <small>expiring</small>}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
                <tr className="to-total">
                  <td>Committed</td>
                  {outlook.seasons.map((s, i) => <td key={i} className={i === 0 ? 'is-now' : undefined}>{money(s.payroll)}</td>)}
                </tr>
                <tr className="to-off">
                  <td>Comes off the books</td>
                  {outlook.seasons.map((s, i) => (
                    <td key={i} title={s.expiring_players.join(', ') || undefined}>
                      {s.expiring_players.length
                        ? `${money(s.expiring_salary)} · ${s.expiring_players.length} ${s.expiring_players.length === 1 ? 'player' : 'players'}`
                        : '—'}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
            <div className="to-legend">
              <span><i className="to-legend-last" /> final season under contract</span>
              <span><span className="to-fa">Free agent</span> first season off the books</span>
              {now.salary_cap !== null && <span>Gauge lines: floor · cap · tax{anyApron ? ' · aprons' : ''}</span>}
            </div>
          </section>
        </div>
      )}
    </ModalShell>
  );
};
