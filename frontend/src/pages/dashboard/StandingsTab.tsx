import React, { useState } from 'react';
import { Flame, Snowflake } from 'lucide-react';
import { useLeagueStore } from '../../store/leagueStore';
import { useLiveStore } from '../../store/liveStore';
import { TeamCrest } from '../../components/TeamCrest';
import { filterRows, leagueTable } from '../../utils/standings';
import type { StandingRow, StandingsFilter } from '../../utils/standings';

type Scope = 'west' | 'east' | 'league';

const SCOPES: { id: Scope; label: string }[] = [
  { id: 'west', label: 'West' },
  { id: 'east', label: 'East' },
  { id: 'league', label: 'League' },
];

const FILTERS: { id: StandingsFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'playoff', label: 'Playoff' },
  { id: 'play_in', label: 'Play-in' },
  { id: 'hot', label: 'Hot' },
  { id: 'cold', label: 'Cold' },
];

const formatPct = (pct: number) => pct.toFixed(3).replace(/^0/, '');
const formatGb = (gb: number) => (gb === 0 ? '-' : gb.toFixed(1));

export const StandingsTab: React.FC = () => {
  const summary = useLiveStore((state) => state.summary);
  const openTeamProfile = useLeagueStore((state) => state.openTeamProfile);
  const myConference = summary?.team?.conference === 'East' ? 'east' : 'west';
  const [scope, setScope] = useState<Scope>(myConference);
  const [filter, setFilter] = useState<StandingsFilter>('all');

  if (!summary) {
    return <div className="dash-placeholder">Standings appear once the season starts.</div>;
  }

  const isLeague = scope === 'league';
  const rows: StandingRow[] = isLeague
    ? leagueTable(summary.standings.west, summary.standings.east)
    : summary.standings[scope];
  const visible = filterRows(rows, filter);
  const myName = summary.team?.name ?? null;

  return (
    <div className="dash-standings">
      <div className="dash-toolbar">
        <div className="dash-chips" role="group" aria-label="Conference">
          {SCOPES.map((item) => (
            <button key={item.id} className={`dash-chip${scope === item.id ? ' is-on' : ''}`} aria-pressed={scope === item.id} onClick={() => setScope(item.id)}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="dash-chips" role="group" aria-label="Filter">
          {FILTERS.map((item) => (
            <button key={item.id} className={`dash-chip${filter === item.id ? ' is-on' : ''}`} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>
              {item.id === 'hot' && <Flame size={12} />}
              {item.id === 'cold' && <Snowflake size={12} />}
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card dash-table-card">
        {visible.length === 0 ? (
          <div className="dash-placeholder">No teams match this filter.</div>
        ) : (
          <div className="dash-table-wrap">
            <table className="dash-table">
              <thead>
                <tr>
                  <th className="n">#</th>
                  <th>Team</th>
                  <th className="n">W</th>
                  <th className="n">L</th>
                  <th className="n">PCT</th>
                  <th className="n">GB</th>
                  <th className="n">Home</th>
                  <th className="n">Away</th>
                  <th className="n">L10</th>
                  <th className="n">Streak</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((row, index) => {
                  const next = visible[index + 1];
                  const cutPlayoff = !isLeague && filter === 'all' && row.zone === 'playoff' && next && next.zone !== 'playoff';
                  const cutPlayIn = !isLeague && filter === 'all' && row.zone === 'play_in' && next && next.zone === 'out';
                  const classes = [
                    row.nome === myName ? 'is-me' : '',
                    row.tag ? `is-${row.tag}` : '',
                    cutPlayoff ? 'cut-playoff' : '',
                    cutPlayIn ? 'cut-playin' : '',
                  ].filter(Boolean).join(' ');
                  return (
                    <tr
                      key={row.nome}
                      className={classes}
                      tabIndex={0}
                      onClick={() => openTeamProfile(row.nome)}
                      onKeyDown={(event) => { if (event.key === 'Enter') openTeamProfile(row.nome); }}
                    >
                      <td className="n">{row.pos}</td>
                      <td>
                        <span className="dash-team-cell"><TeamCrest name={row.nome} size={22} />{row.nome}</span>
                      </td>
                      <td className="n">{row.v}</td>
                      <td className="n">{row.s}</td>
                      <td className="n">{formatPct(row.pct)}</td>
                      <td className="n">{formatGb(row.gb)}</td>
                      <td className="n">{row.home}</td>
                      <td className="n">{row.away}</td>
                      <td className="n">{row.l10}</td>
                      <td className="n">{row.streak || '-'}</td>
                      <td>
                        <div className="dash-tags">
                          {row.nome === myName && <span className="dash-tag dash-tag-primary">YOU</span>}
                          {row.tag === 'hot' && <span className="dash-tag dash-tag-hot"><Flame size={11} /> HOT</span>}
                          {row.tag === 'cold' && <span className="dash-tag dash-tag-cold"><Snowflake size={11} /> COLD</span>}
                          {!isLeague && row.zone === 'play_in' && <span className="dash-tag dash-tag-warning">PLAY-IN</span>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="dash-legend">
        {isLeague
          ? 'League view ranks all teams together; playoff lines are per conference.'
          : 'Dashed orange line: end of the direct playoff spots · dashed yellow line: end of the play-in · colored edge: hot (orange) or cold (blue) team'}
      </div>
    </div>
  );
};
