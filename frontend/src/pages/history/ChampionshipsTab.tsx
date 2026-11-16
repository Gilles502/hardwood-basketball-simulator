// Championship History tab ("year rail + champion spread"): years down the left, the picked season fills the page
// with a poster in the champion's colours, the season awards and where the top teams finished.
import React, { useEffect, useRef, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { crestHue } from '../../utils/crest';

interface TeamRow {
  team: string;
  wins: number;
  losses: number;
  conference: string | null;
  seed: number | null;
  league_rank: number | null;
}

interface StandingRow {
  rank: number;
  team: string;
  wins: number;
  losses: number;
  tag: 'champion' | 'finals' | null;
}

interface SeasonEntry {
  season: number;
  year: number | null;
  missing?: boolean;
  champion?: TeamRow;
  runner_up?: TeamRow | null;
  finals_mvp?: string | null;
  awards?: Record<'mvp' | 'dpoy' | 'roy' | 'sixth_man' | 'mip', string | null>;
  all_league?: Record<'first' | 'second' | 'third', string[]>;
  top_standings?: StandingRow[];
  franchise_title_no?: number;
  run?: number;
  run_window?: number;
  is_user_team?: boolean;
}

const AWARDS: { key: 'mvp' | 'dpoy' | 'roy' | 'sixth_man' | 'mip'; label: string }[] = [
  { key: 'mvp', label: 'Most Valuable Player' },
  { key: 'dpoy', label: 'Defensive Player of the Year' },
  { key: 'roy', label: 'Rookie of the Year' },
  { key: 'sixth_man', label: 'Sixth Man of the Year' },
  { key: 'mip', label: 'Most Improved Player' },
];
const ALL_LEAGUE: { key: 'first' | 'second' | 'third'; label: string }[] = [
  { key: 'first', label: '1st team' },
  { key: 'second', label: '2nd team' },
  { key: 'third', label: '3rd team' },
];

const shortName = (team: string) => team.split(' ').slice(-1)[0] || team;
const ordinal = (n: number) => {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] || 'th';
  return `${n}${tail}`;
};

export const ChampionshipsTab: React.FC = () => {
  const { openPlayerProfile, openTeamProfile } = useLeagueStore();
  const [seasons, setSeasons] = useState<SeasonEntry[] | null>(null);
  const [selected, setSelected] = useState(0);
  const [showAllLeague, setShowAllLeague] = useState(false);
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    fetch(`/api/history?_t=${Date.now()}`)
      .then((res) => res.json())
      .then((data) => setSeasons(Array.isArray(data) ? data : []))
      .catch(() => setSeasons([]));
  }, []);

  if (seasons === null) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '40vh' }}><div className="spinner"></div></div>;
  }
  if (seasons.length === 0) {
    return (
      <div className="hi-empty">
        <div className="hi-empty-icon" aria-hidden="true">🏆</div>
        <h2>No champions yet</h2>
        <p>Finish your first season and its champion will hang here.</p>
      </div>
    );
  }

  const pick = (index: number) => {
    const next = Math.max(0, Math.min(seasons.length - 1, index));
    setSelected(next);
    rowRefs.current[next]?.focus();
  };
  const onRailKey = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); pick(selected + 1); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); pick(selected - 1); }
    else if (event.key === 'Home') { event.preventDefault(); pick(0); }
    else if (event.key === 'End') { event.preventDefault(); pick(seasons.length - 1); }
  };

  const entry = seasons[selected];
  const nameButton = (name: string | null | undefined, onOpen: (n: string) => void, className = 'hi-link') =>
    name ? <button type="button" className={className} onClick={() => onOpen(name)}>{name}</button> : <span className="hi-none">—</span>;

  return (
    <div className="hi-champs">
      <div className="hi-rail" role="listbox" aria-label="Seasons" onKeyDown={onRailKey}>
        {seasons.map((s, index) => (
          <button
            key={s.season}
            ref={(node) => { rowRefs.current[index] = node; }}
            type="button"
            role="option"
            aria-selected={index === selected}
            tabIndex={index === selected ? 0 : -1}
            className={`hi-rail-row${index === selected ? ' is-on' : ''}${s.missing ? ' is-missing' : ''}`}
            onClick={() => pick(index)}
          >
            <span className="hi-rail-year">{s.year ?? `Y${s.season}`}</span>
            {s.missing || !s.champion ? (
              <span className="hi-rail-team">No record</span>
            ) : (
              <>
                <span className="hi-rail-chip" style={{ background: `hsl(${crestHue(s.champion.team)} 58% 42%)` }} />
                <span className="hi-rail-team">{shortName(s.champion.team)}</span>
                {s.is_user_team && <span className="hi-rail-mine" title="Your team">●</span>}
              </>
            )}
          </button>
        ))}
      </div>

      {entry.missing || !entry.champion ? (
        <div className="hi-missing">
          <b>{entry.year ?? `Year ${entry.season}`}</b>
          <p>This season was not recorded in the league history.</p>
        </div>
      ) : (
        <div className="hi-spread">
          <div
            className="hi-hero"
            style={{
              background: `radial-gradient(ellipse at 85% 10%, rgba(255, 138, 74, 0.33), transparent 55%), linear-gradient(135deg, hsl(${crestHue(entry.champion.team)} 60% 36%), hsl(${crestHue(entry.champion.team)} 62% 12%) 75%)`,
            }}
          >
            <div className="hi-hero-year" aria-hidden="true">{entry.year}</div>
            <div className="hi-hero-kicker">
              League champions · Year {entry.season}
              {entry.is_user_team && <span className="hi-yours">Your team</span>}
            </div>
            {nameButton(entry.champion.team, openTeamProfile, 'hi-hero-name')}
            <div className="hi-hero-def">
              {entry.runner_up
                ? <>def. {nameButton(entry.runner_up.team, openTeamProfile, 'hi-link hi-link-light')} in the Finals ({entry.runner_up.wins}-{entry.runner_up.losses})</>
                : 'Finals opponent not recorded'}
            </div>
            <div className="hi-hero-line">
              <div>
                <b>{entry.champion.wins}-{entry.champion.losses}</b>
                <span>{entry.champion.conference && entry.champion.seed ? `${entry.champion.conference} #${entry.champion.seed}` : 'Record'}</span>
              </div>
              <div>
                <b>{nameButton(entry.finals_mvp, openPlayerProfile, 'hi-link hi-link-light')}</b>
                <span>Finals MVP</span>
              </div>
              {(entry.run ?? 0) >= 2 && (
                <div><b>{entry.run} in {entry.run_window}</b><span>Titles, last {entry.run_window} seasons</span></div>
              )}
              {entry.franchise_title_no && (
                <div><b>{ordinal(entry.franchise_title_no)}</b><span>Franchise title</span></div>
              )}
            </div>
          </div>

          <div className="hi-sheets">
            <div className="hi-paper">
              <div className="hi-kicker">Season awards</div>
              <table className="hi-table">
                <tbody>
                  {AWARDS.map((a) => (
                    <tr key={a.key}><td>{a.label}</td><td>{nameButton(entry.awards?.[a.key], openPlayerProfile)}</td></tr>
                  ))}
                </tbody>
              </table>
              {entry.all_league && ALL_LEAGUE.some((t) => entry.all_league![t.key].length > 0) && (
                <>
                  <button type="button" className="hi-fold" aria-expanded={showAllLeague} onClick={() => setShowAllLeague((v) => !v)}>
                    {showAllLeague ? '▾' : '▸'} All-League teams
                  </button>
                  {showAllLeague && (
                    <div className="hi-allleague">
                      {ALL_LEAGUE.map((t) => entry.all_league![t.key].length > 0 && (
                        <div key={t.key}>
                          <span className="hi-allleague-label">{t.label}</span>
                          {entry.all_league![t.key].map((name, i) => (
                            <React.Fragment key={name}>{i > 0 && ' · '}{nameButton(name, openPlayerProfile)}</React.Fragment>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="hi-paper">
              <div className="hi-kicker">Where they finished</div>
              <table className="hi-table">
                <tbody>
                  {(entry.top_standings || []).map((row) => (
                    <tr key={row.team} className={row.tag === 'champion' ? 'is-champ' : ''}>
                      <td>
                        <span className="hi-rank">{row.rank}</span>
                        {nameButton(row.team, openTeamProfile)}
                        {row.tag === 'champion' && <span className="hi-tag">Champion</span>}
                        {row.tag === 'finals' && <span className="hi-tag is-finals">Finals</span>}
                      </td>
                      <td>{row.wins}-{row.losses}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
