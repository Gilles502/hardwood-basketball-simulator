// File: frontend/src/pages/Economy.tsx
// Finances & CBA as the league's business pages: a headline written from the numbers, every team's payroll
// as a stock listing grouped by cap situation, and side columns for the rules, next summer's market and contracts.
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { crestLabel } from '../utils/crest';
import { ownerLabel } from '../utils/owners';
import { STATUS_LABELS, STATUS_ORDER, headline, money, seasonLabel, standfirst } from '../utils/finances';
import type { ContractLine, EconomyData, TeamFinances } from '../utils/finances';
import { TeamOutlookModal } from './finances/TeamOutlookModal';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './finances/Finances.css';

/** "+12.3" / "−4.5" with the sign kept for zero-width alignment in the table. */
const signed = (value: number) => `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(1)}`;

const LedgerRow: React.FC<{ team: TeamFinances; isUser: boolean; onOpen: () => void }> = ({ team, isUser, onOpen }) => {
  const overCap = team.cap_space === null ? null : -team.cap_space;
  const change = team.next_payroll === null ? null : team.next_payroll - team.payroll;
  return (
    <tr className={isUser ? 'fin-me' : undefined} onClick={onOpen}>
      <td>
        <button type="button" className="fin-team" onClick={(e) => { e.stopPropagation(); onOpen(); }} title={`${team.name}: 4-year outlook`}>
          {team.name}
        </button>
        {isUser && <span className="fin-you">You</span>}
      </td>
      <td>{money(team.payroll)}</td>
      <td className={overCap === null ? undefined : overCap > 0 ? 'fin-up' : 'fin-down'}>{overCap === null ? '—' : signed(overCap)}</td>
      <td>{team.next_payroll === null ? '—' : money(team.next_payroll)}</td>
      <td className={change === null ? undefined : change > 0.05 ? 'fin-up' : change < -0.05 ? 'fin-down' : undefined}>
        {change === null ? '—' : `${change > 0.05 ? '▲' : change < -0.05 ? '▼' : '•'} ${Math.abs(change).toFixed(1)}`}
      </td>
      <td className="fin-owner">{ownerLabel(team.owner)}</td>
    </tr>
  );
};

const ContractBox: React.FC<{ title: string; rows: ContractLine[]; tone?: 'good' | 'bad'; onPlayer: (name: string) => void }> = ({ title, rows, tone, onPlayer }) => (
  <section className="fin-box">
    <h4>{title}</h4>
    {rows.length === 0 && <p className="fin-none">Nothing to report.</p>}
    {rows.map((c) => (
      <div className="fin-line" key={`${c.name}-${c.team}`}>
        <span>
          <button type="button" className="fin-player" onClick={() => onPlayer(c.name)}>{c.name}</button>
          <small>{crestLabel(c.team)}</small>
          {tone && <small className="fin-fair" title="The salary paid at this player's rank in the league by performance">fair {money(c.fair_salary)}</small>}
        </span>
        <em className={tone === 'good' ? 'fin-down' : tone === 'bad' ? 'fin-up' : undefined}>{money(c.salary)}</em>
      </div>
    ))}
  </section>
);

export const Economy: React.FC = () => {
  const { leagueData, openPlayerProfile } = useLeagueStore();
  const [data, setData] = useState<EconomyData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outlookTeam, setOutlookTeam] = useState<string | null>(null);
  const userTeam = leagueData?.player_team_name ?? null;

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/economy?_t=${Date.now()}`)
      .then((response) => response.json())
      .then((payload) => {
        if (cancelled) return;
        if (payload.error) setError(payload.error);
        else if (!payload.season || !Array.isArray(payload.teams)) setError('The server sent finances in an old format. Restart the backend and reopen this page.');
        else setData(payload);
      })
      .catch(() => { if (!cancelled) setError('Failed to load the league finances.'); });
    return () => { cancelled = true; };
  }, []);

  const season = data ? seasonLabel(data.season.year) : '';
  const header = (
    <div className="dash-header">
      <div>
        <h1 className="dash-title">Finances &amp; CBA</h1>
        <span className="dash-subtitle">{season ? `Season ${season} · ` : ''}the league's business pages</span>
      </div>
      <div className="dash-badges">
        {userTeam && (
          <button type="button" className="btn btn-primary" onClick={() => setOutlookTeam(userTeam)}>Your 4-year outlook</button>
        )}
        <a
          href="/api/export/season?format=csv&category=rosters"
          download
          className="btn btn-secondary"
          title="Download all league contracts and payrolls as a CSV spreadsheet"
        >
          Export CSV
        </a>
      </div>
    </div>
  );

  if (error) {
    return (
      <div className="fin-root">
        {header}
        <div className="fin-empty">{error}</div>
      </div>
    );
  }
  if (!data) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  const { season: lines, next_season: next } = data;
  const title = headline(data);
  const groups = STATUS_ORDER
    .map((status) => ({ status, teams: data.teams.filter((t) => t.status === status) }))
    .filter((g) => g.teams.length > 0);
  const market = data.market_watch
    .map((name) => data.teams.find((t) => t.name === name))
    .filter((t): t is TeamFinances => Boolean(t));
  const nextYear = next?.year ? String(next.year) : 'next season';
  const apronText = (value: number | null) =>
    value !== null ? money(value) : next?.first_apron != null && next.year ? `from ${next.year}` : 'none';
  const rules: [string, string][] = lines.no_cap
    ? [['Salary cap', 'none'], ['Luxury tax', 'none'], ['Aprons', 'none'], ['Minimum', money(lines.min_salary)]]
    : [
        ['Salary cap', money(lines.salary_cap ?? 0)],
        ['Floor', lines.salary_floor !== null ? money(lines.salary_floor) : 'none'],
        ['Luxury tax', lines.luxury_tax !== null ? money(lines.luxury_tax) : 'none'],
        ...(lines.first_apron === null && lines.second_apron === null
          ? [['Aprons', apronText(null)] as [string, string]]
          : [['First apron', apronText(lines.first_apron)] as [string, string], ['Second apron', apronText(lines.second_apron)] as [string, string]]),
        ['Mid-level', lines.mle !== null ? money(lines.mle) : 'none'],
        ['Biannual', lines.bae !== null ? money(lines.bae) : 'none'],
        ['Minimum', money(lines.min_salary)],
      ];

  return (
    <div className="fin-root">
      {header}

      <article className="fin-paper">
        <div className="fin-mast">
          <b>The Ledger · League business</b>
          <span>
            {[season && `Season ${season}`, lines.salary_cap !== null && `cap ${money(lines.salary_cap)}`, lines.luxury_tax !== null && `tax ${money(lines.luxury_tax)}`]
              .filter(Boolean).join(' · ')}
          </span>
        </div>
        <h2 className="fin-headline"><em>{title.lead}</em> {title.rest}</h2>
        <p className="fin-dek">{standfirst(data)}</p>

        <div className="fin-grid">
          <div className="fin-listing">
            <table className="fin-table">
              <colgroup>
                <col className="fin-col-team" /><col /><col /><col /><col /><col className="fin-col-owner" />
              </colgroup>
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Payroll</th>
                  <th title="Payroll minus the salary cap">vs cap</th>
                  <th title={`Salary already committed for ${nextYear}`}>Next yr</th>
                  <th title="Next year's committed payroll minus this year's">Change</th>
                  <th>Owner</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <React.Fragment key={g.status}>
                    <tr className={`fin-group fin-group-${g.status}`}>
                      <td colSpan={6}>{STATUS_LABELS[g.status]} · {g.teams.length}</td>
                    </tr>
                    {g.teams.map((t) => (
                      <LedgerRow key={t.name} team={t} isUser={t.name === userTeam} onOpen={() => setOutlookTeam(t.name)} />
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
            <p className="fin-foot">Click a team for its 4-year outlook. Next year counts only salary already under contract.</p>
          </div>

          <aside className="fin-side">
            <section className="fin-box">
              <h4>The rulebook</h4>
              {rules.map(([label, value]) => (
                <div className="fin-line" key={label}><span>{label}</span><em>{value}</em></div>
              ))}
            </section>

            {!lines.no_cap && next && (
              <section className="fin-box">
                <h4>Market watch: summer {nextYear}</h4>
                {market.length === 0 && <p className="fin-none">Nobody has cap room yet.</p>}
                {market.map((t) => (
                  <div className={`fin-line${t.name === userTeam ? ' fin-me' : ''}`} key={t.name}>
                    <span>
                      <button type="button" className="fin-player" onClick={() => setOutlookTeam(t.name)}>{t.name}</button>
                      {t.expiring_salary > 0 && <small>{money(t.expiring_salary)} expiring</small>}
                    </span>
                    <em className="fin-down">{money(t.next_cap_space ?? 0)}</em>
                  </div>
                ))}
              </section>
            )}

            <ContractBox title="Top salaries" rows={data.contracts.highest} onPlayer={openPlayerProfile} />
            <ContractBox title="Bargains" rows={data.contracts.bargains} tone="good" onPlayer={openPlayerProfile} />
            <ContractBox title="Overpays" rows={data.contracts.overpays} tone="bad" onPlayer={openPlayerProfile} />
          </aside>
        </div>
      </article>

      {outlookTeam && (
        <TeamOutlookModal teamName={outlookTeam} teams={data.teams.map((t) => t.name)} onClose={() => setOutlookTeam(null)} />
      )}
    </div>
  );
};
