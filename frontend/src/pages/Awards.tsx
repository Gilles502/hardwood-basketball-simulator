// File: frontend/src/pages/Awards.tsx
import React, { useEffect } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { TeamCrest } from '../components/TeamCrest';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './awards/Awards.css';

interface AwardStats {
  ppg: number;
  rpg: number;
  apg: number;
  spg: number;
  bpg: number;
}

interface AwardWinner {
  nome: string;
  squadra: string;
  stats: AwardStats;
}

interface AllTeamPlayer {
  ruolo: string;
  nome: string;
  squadra: string;
}

interface FrontOfficeWinner {
  nome: string;
  squadra: string;
  wins: number;
  losses: number;
  expected: number;
  last_wins: number | null;
}

/** The two front-office awards: people, not players, so no profile button. */
const FRONT_OFFICE_AWARDS: { key: string; title: string; short: string }[] = [
  { key: 'coy', title: 'Coach of the Year', short: 'COY' },
  { key: 'gm_of_the_year', title: 'GM of the Year', short: 'GMOY' },
];

const signed = (n: number) => `${n >= 0 ? '+' : '-'}${Math.abs(Math.round(n))}`;

type StatKey = keyof AwardStats;
const STAT_KEYS: StatKey[] = ['ppg', 'rpg', 'apg', 'spg', 'bpg'];

/** The four awards shown as plaques next to the MVP, with the two numbers that best explain each one. */
const PLAQUES: { key: string; title: string; short: string; stats: StatKey[] }[] = [
  { key: 'dpoy', title: 'Defensive Player of the Year', short: 'DPOY', stats: ['spg', 'bpg'] },
  { key: 'roy', title: 'Rookie of the Year', short: 'ROY', stats: ['ppg', 'rpg'] },
  { key: 'sesto_uomo', title: 'Sixth Man of the Year', short: '6MOY', stats: ['ppg', 'rpg'] },
  { key: 'mip', title: 'Most Improved Player', short: 'MIP', stats: ['ppg', 'rpg'] },
];

const TEAM_TITLES = ['1st team', '2nd team', '3rd team'];
const lastWord = (name: string) => name.split(' ').slice(-1)[0] || name;

export const Awards: React.FC = () => {
  const { leagueData, fetchLeagueData, openPlayerProfile } = useLeagueStore();

  useEffect(() => {
    if (!leagueData) {
      fetchLeagueData();
    }
  }, [leagueData, fetchLeagueData]);

  if (!leagueData) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  const { premi } = leagueData;
  const userTeam = leagueData.player_team_name;
  const year = leagueData.anno_corrente;
  const seasonLabel = year ? `${year}–${String((year + 1) % 100).padStart(2, '0')}` : '';

  const header = (
    <div className="dash-header">
      <div>
        <h1 className="dash-title">Season awards</h1>
        <span className="dash-subtitle">{seasonLabel ? `${seasonLabel} regular season · ` : ''}announced after the last day</span>
      </div>
    </div>
  );

  if (!premi || !premi.mvp) {
    const seasonOver = !['PRE_SEASON', 'ALL_STAR_BREAK'].includes(leagueData.league_state);
    return (
      <div className="aw-root">
        {header}
        <div className="aw-empty">
          <div className="aw-empty-icon" aria-hidden="true">🏆</div>
          <h2>{seasonOver ? 'No awards on record' : 'Not announced yet'}</h2>
          <p>
            {seasonOver
              ? "This season's awards weren't kept in this save. Next season's are handed out after the last regular-season day."
              : 'MVP, Defensive Player, Rookie, Sixth Man, Most Improved and the All-League teams are handed out after the last regular-season day.'}
          </p>
        </div>
      </div>
    );
  }

  const mvp: AwardWinner = premi.mvp;
  const allLeague: AllTeamPlayer[][] = premi.all_nba || [];
  const allDefensive: AllTeamPlayer[] = premi.all_defensive || [];
  const allRookie: AllTeamPlayer[] = premi.all_rookie || [];

  // Your team's honours: individual awards first, then team selections.
  const honours: { label: string; name: string }[] = [];
  if (userTeam) {
    if (mvp.squadra === userTeam) honours.push({ label: 'MVP', name: mvp.nome });
    PLAQUES.forEach(({ key, short }) => {
      const w: AwardWinner | null = premi[key];
      if (w && w.squadra === userTeam) honours.push({ label: short, name: w.nome });
    });
    allLeague.forEach((team, i) => team.filter((p) => p.squadra === userTeam)
      .forEach((p) => honours.push({ label: `All-League ${TEAM_TITLES[i].replace(' team', '')}`, name: p.nome })));
    allDefensive.filter((p) => p.squadra === userTeam).forEach((p) => honours.push({ label: 'All-Defensive', name: p.nome }));
    allRookie.filter((p) => p.squadra === userTeam).forEach((p) => honours.push({ label: 'All-Rookie', name: p.nome }));
  }

  // The MVP's two strongest numbers get the highlight: points plus the better of rebounds and assists.
  const mvpKeys: StatKey[] = ['ppg', mvp.stats.apg >= mvp.stats.rpg ? 'apg' : 'rpg'];

  const playerButton = (name: string, className: string) => (
    <button type="button" className={className} onClick={() => openPlayerProfile(name)}>{name}</button>
  );

  const roster = (title: string, note: string, players: AllTeamPlayer[]) => (
    <section className="aw-roster" aria-label={title}>
      <div className="aw-roster-head"><b>{title}</b>{note && <span>{note}</span>}</div>
      {players.map((p) => (
        <div key={`${title}-${p.nome}`} className={`aw-roster-row${p.squadra === userTeam ? ' is-me' : ''}`}>
          <i>{p.ruolo}</i>
          <TeamCrest name={p.squadra} size={20} />
          {playerButton(p.nome, 'aw-roster-name')}
          <small title={p.squadra}>{lastWord(p.squadra)}</small>
        </div>
      ))}
    </section>
  );

  return (
    <div className="aw-root">
      {header}

      {userTeam && (
        <div className="aw-honours">
          <b>{lastWord(userTeam)} honours</b>
          {honours.length === 0
            ? <span className="aw-honours-none">No awards or All-League picks this season.</span>
            : honours.map((h) => <span key={`${h.label}-${h.name}`} className="aw-chip"><em>{h.label}</em> {h.name}</span>)}
        </div>
      )}

      <div className="aw-top">
        <section className="aw-mvp" aria-label="Most Valuable Player">
          <div className="aw-seal" aria-hidden="true"><b>MVP</b><small>{seasonLabel}</small></div>
          <div className="aw-kicker">Most Valuable Player</div>
          {playerButton(mvp.nome, 'aw-mvp-name')}
          <div className="aw-mvp-team">
            <TeamCrest name={mvp.squadra} size={24} />{mvp.squadra}
            {mvp.squadra === userTeam && <span className="aw-yours">Your team</span>}
          </div>
          <div className="aw-stats">
            {STAT_KEYS.map((k) => (
              <div key={k} className={mvpKeys.includes(k) ? 'is-key' : undefined}>
                <b>{mvp.stats[k].toFixed(1)}</b><span>{k}</span>
              </div>
            ))}
          </div>
        </section>

        <div className="aw-plaques">
          {PLAQUES.map(({ key, title, short, stats }) => {
            const w: AwardWinner | null = premi[key];
            if (!w) {
              return (
                <section key={key} className="aw-plaque is-empty" aria-label={title}>
                  <div className="aw-plaque-head"><span>{title}</span><em>{short}</em></div>
                  <p>Not awarded this season.</p>
                </section>
              );
            }
            return (
              <section key={key} className={`aw-plaque${w.squadra === userTeam ? ' is-me' : ''}`} aria-label={title}>
                <div className="aw-plaque-head"><span>{title}</span><em>{short}</em></div>
                {playerButton(w.nome, 'aw-plaque-name')}
                <div className="aw-plaque-team"><TeamCrest name={w.squadra} size={18} />{w.squadra}</div>
                <div className="aw-plaque-line">
                  {stats.map((k, i) => (
                    <React.Fragment key={k}>{i > 0 && ' · '}<b>{w.stats[k].toFixed(1)}</b> {k}</React.Fragment>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>

      <h2 className="aw-sec">Front office <span>Beat the expectation</span></h2>
      <div className="aw-plaques">
        {FRONT_OFFICE_AWARDS.map(({ key, title, short }) => {
          const w: FrontOfficeWinner | null = premi[key] ?? null;
          if (!w) {
            return (
              <section key={key} className="aw-plaque is-empty" aria-label={title}>
                <div className="aw-plaque-head"><span>{title}</span><em>{short}</em></div>
                <p>Not awarded this season.</p>
              </section>
            );
          }
          return (
            <section key={key} className={`aw-plaque${w.squadra === userTeam ? ' is-me' : ''}`} aria-label={title}>
              <div className="aw-plaque-head"><span>{title}</span><em>{short}</em></div>
              <div className="aw-plaque-name is-static">{w.nome}</div>
              <div className="aw-plaque-team"><TeamCrest name={w.squadra} size={18} />{w.squadra}</div>
              <div className="aw-plaque-line">
                <b>{w.wins}-{w.losses}</b> · {signed(w.wins - w.expected)} vs expected
                {w.last_wins != null && <> · {signed(w.wins - w.last_wins)} from last season</>}
              </div>
            </section>
          );
        })}
      </div>

      {allLeague.length > 0 && (
        <>
          <h2 className="aw-sec">All-League teams <span>Picked at the end of the regular season</span></h2>
          <div className="aw-grid-3">
            {allLeague.map((team, i) => (
              <React.Fragment key={i}>{roster(TEAM_TITLES[i] ?? `Team ${i + 1}`, '', team)}</React.Fragment>
            ))}
          </div>
        </>
      )}

      {(allDefensive.length > 0 || allRookie.length > 0) && (
        <div className="aw-grid-2">
          {allDefensive.length > 0 && roster('All-Defensive', 'Defense', allDefensive)}
          {allRookie.length > 0 && roster('All-Rookie', 'First-year players', allRookie)}
        </div>
      )}
    </div>
  );
};
