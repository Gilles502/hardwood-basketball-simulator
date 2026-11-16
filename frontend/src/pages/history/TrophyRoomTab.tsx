// Trophy Room tab ("the rafters"): one franchise at a time. Title banners and retired jerseys hang from the arena
// ceiling, the trophy shelf sits under them, then franchise leaders and records, then every season (collapsed).
// Payload from core/trophy_room_view.py; also shown inside the team profile popup.
import React, { useEffect, useMemo, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import './History.css';

interface TeamOption { team_name: string; championships_count: number; is_user_team: boolean }
interface Banner { season: number; year: number | null; finals_mvp: string | null; runner_up: string | null; wins: number | null; losses: number | null }
interface Award { player: string; season: number | null; year: number | null }
interface Jersey { number: string; player: string; first_year: number | null; last_year: number | null }
interface Leader { name: string; value: number; first_year: number | null; last_year: number | null }
interface GameRecord { stat: string; value: number; player: string; opponent: string | null; year: number | null }
interface SeasonRecord { stat: string; value: number; player: string; year: number | null }
interface SeasonRow { season: number; year: number | null; wins?: number; losses?: number; conf_seed?: number | null; result?: string; missing?: boolean }

interface TrophyRoom {
  team_name: string;
  arena: string;
  city: string;
  established: number;
  colors: { primary: string; secondary: string };
  is_user_team: boolean;
  summary: { titles: number; finals: number; playoff_seasons: number; wins: number; losses: number; win_pct: number };
  banners: Banner[];
  cabinet: {
    titles: { season: number; year: number | null }[];
    lost_finals: { season: number; year: number | null; winner: string | null }[];
    finals_mvp: Award[]; mvp: Award[]; dpoy: Award[]; roy: Award[]; sixth_man: Award[];
  };
  retired_jerseys: Jersey[];
  leaders: Record<string, Leader[]>;
  records: { single_game: GameRecord[]; single_season: SeasonRecord[] };
  seasons: SeasonRow[];
}

/** Jerseys shown in the rafters before "+K more" (layout, not tuning). */
const RAFTER_JERSEYS = 6;

const SHELF: { key: 'titles' | 'finals_mvp' | 'mvp' | 'dpoy' | 'roy' | 'sixth_man'; label: string }[] = [
  { key: 'titles', label: 'Titles' },
  { key: 'finals_mvp', label: 'Finals MVP' },
  { key: 'mvp', label: 'MVP' },
  { key: 'dpoy', label: 'DPOY' },
  { key: 'roy', label: 'ROY' },
  { key: 'sixth_man', label: '6th Man' },
];

const LEADER_TABS = [
  { key: 'points', label: 'Points', unit: 'PTS' },
  { key: 'rebounds', label: 'Rebounds', unit: 'REB' },
  { key: 'assists', label: 'Assists', unit: 'AST' },
  { key: 'three_pointers', label: '3PM', unit: '3PM' },
  { key: 'games', label: 'Games', unit: 'GP' },
];

const STAT_LABELS: Record<string, string> = {
  points: 'Points', rebounds: 'Rebounds', assists: 'Assists', three_pointers: 'Threes', steals: 'Steals',
  blocks: 'Blocks', ppg: 'Points per game', rpg: 'Rebounds per game',
};

const RESULT_CLASS: Record<string, string> = {
  Champions: 'tr-bar-champ', 'Lost Finals': 'tr-bar-finals', Playoffs: 'tr-bar-playoffs', 'Play-In': 'tr-bar-lottery',
  Lottery: 'tr-bar-lottery', 'In Progress': 'tr-bar-playoffs',
};

const shortName = (name: string | null) => {
  if (!name) return '—';
  const parts = name.split(' ');
  return parts.length > 1 ? `${parts[0][0]}. ${parts.slice(1).join(' ')}` : name;
};
const lastName = (name: string) => name.split(' ').slice(1).join(' ') || name;
const span = (a: number | null, b: number | null) => (a == null ? '—' : a === b || b == null ? `${a}` : `${a}–${b}`);

/** True for light team colours (Spurs silver): text on them goes dark, jersey numbers use the other colour. */
const isLight = (hex: string) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return false;
  const n = parseInt(m[1], 16);
  return 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255) > 170;
};

/** "Bosh ×2, Simmons ×2" — winners grouped, most first. */
const winnersLine = (list: Award[]) => {
  const counts = new Map<string, number>();
  list.forEach((a) => counts.set(a.player, (counts.get(a.player) || 0) + 1));
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
    .map(([p, n]) => (n > 1 ? `${lastName(p)} ×${n}` : `${lastName(p)} '${String(list.find((a) => a.player === p)?.year ?? '').slice(2)}`))
    .join(', ');
};

export const TrophyRoomTab: React.FC<{ initialTeam?: string }> = ({ initialTeam }) => {
  const { leagueData, openPlayerProfile } = useLeagueStore();
  const [teams, setTeams] = useState<TeamOption[]>([]);
  const [team, setTeam] = useState<string>(initialTeam || leagueData?.player_team_name || '');
  const [room, setRoom] = useState<TrophyRoom | null>(null);
  const [failed, setFailed] = useState(false);
  const [openTile, setOpenTile] = useState<string | null>(null);
  const [allJerseys, setAllJerseys] = useState(false);
  const [leaderTab, setLeaderTab] = useState('points');
  const [recordTab, setRecordTab] = useState<'game' | 'season'>('game');
  const [showSeasons, setShowSeasons] = useState(false);

  useEffect(() => {
    fetch(`/api/franchise-legacy/teams?_t=${Date.now()}`)
      .then((res) => res.json())
      .then((data: TeamOption[]) => {
        setTeams(Array.isArray(data) ? data : []);
        if (!team && Array.isArray(data) && data.length) setTeam(data[0].team_name);
      })
      .catch(() => setTeams([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!team) return;
    setRoom(null);
    setFailed(false);
    setOpenTile(null);
    setAllJerseys(false);
    fetch(`/api/franchise-legacy/${encodeURIComponent(team)}?_t=${Date.now()}`)
      .then((res) => res.json())
      .then((data) => (data && Array.isArray(data.banners) ? setRoom(data) : setFailed(true)))
      .catch(() => setFailed(true));
  }, [team]);

  const maxWins = useMemo(() => Math.max(1, ...(room?.seasons || []).map((s) => s.wins || 0)), [room]);

  const picker = (
    <div className="tr-top">
      <select className="tr-select" value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Franchise">
        {teams.map((t) => (
          <option key={t.team_name} value={t.team_name}>
            {t.team_name}{t.is_user_team ? ' (yours)' : ''}{t.championships_count ? ` · ${t.championships_count} 🏆` : ''}
          </option>
        ))}
      </select>
      {room && (
        <>
          {room.is_user_team && <span className="hi-yours">Yours</span>}
          <span className="tr-meta">{room.arena} · {room.city} · est. {room.established}</span>
          <span className="tr-meta tr-meta-right">
            {room.summary.wins}–{room.summary.losses} all-time · {room.summary.playoff_seasons} playoff seasons · {room.summary.finals} Finals
          </span>
        </>
      )}
    </div>
  );

  if (failed) return <div>{picker}<div className="hi-empty"><h2>This franchise could not be loaded</h2></div></div>;
  if (!room) {
    return <div>{picker}<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '30vh' }}><div className="spinner"></div></div></div>;
  }

  const primary = room.colors?.primary || '#CE1141';
  const secondary = room.colors?.secondary || '#000000';
  const bannerText = isLight(primary) ? '#1a130e' : '#fff';
  const numberColour = isLight(primary) ? secondary : primary;
  const jerseys = allJerseys ? room.retired_jerseys : room.retired_jerseys.slice(0, RAFTER_JERSEYS);
  const hiddenJerseys = room.retired_jerseys.length - RAFTER_JERSEYS;
  const runnerByYear = new Map(room.banners.map((b) => [b.season, b.runner_up]));

  const tileCount = (key: string) => (key === 'titles' ? room.cabinet.titles.length : (room.cabinet as any)[key].length);
  const tileLine = (key: string) => {
    if (key === 'titles') {
      const last = room.cabinet.titles[room.cabinet.titles.length - 1];
      return last ? `last ${last.year}` : '';
    }
    return winnersLine((room.cabinet as any)[key]);
  };
  const tileList = (key: string) => (key === 'titles'
    ? room.cabinet.titles.map((t) => ({ year: t.year, text: runnerByYear.get(t.season) ? `def. ${runnerByYear.get(t.season)}` : 'Champions', player: null as string | null }))
    : ((room.cabinet as any)[key] as Award[]).map((a) => ({ year: a.year, text: a.player, player: a.player })));

  const leaders = room.leaders[leaderTab] || [];
  const unit = LEADER_TABS.find((t) => t.key === leaderTab)?.unit || '';

  return (
    <div className="tr-root">
      {picker}

      <section className="tr-rafters" aria-label="Rafters">
        <div className="tr-truss" />
        {room.banners.length === 0 && room.retired_jerseys.length === 0 ? (
          <p className="tr-rafters-empty">No banners yet</p>
        ) : (
          <div className="tr-hang">
            {room.banners.length === 0 && <span className="tr-rafters-empty">No banners yet</span>}
            {room.banners.map((b) => (
              <div key={b.season} className="tr-banner" style={{ background: primary, color: bannerText }}
                   tabIndex={0}
                   title={[b.runner_up ? `def. ${b.runner_up}` : null, b.wins != null ? `${b.wins}–${b.losses}` : null].filter(Boolean).join(' · ')}>
                <div className="tr-banner-year">{b.year ?? '—'}</div>
                <div className="tr-banner-title">Champions</div>
                {b.finals_mvp && <div className="tr-banner-mvp">Finals MVP<br />{shortName(b.finals_mvp)}</div>}
              </div>
            ))}
            {room.retired_jerseys.length > 0 && <div className="tr-divider" />}
            {jerseys.map((j) => (
              <button key={j.player} type="button" className="tr-jersey" onClick={() => openPlayerProfile(j.player)}>
                <div className="tr-jersey-no" style={{ color: numberColour }}>{j.number}</div>
                <div className="tr-jersey-name">{shortName(j.player)}</div>
                <div className="tr-jersey-years">{span(j.first_year, j.last_year)}</div>
              </button>
            ))}
            {hiddenJerseys > 0 && (
              <button type="button" className="tr-more" onClick={() => setAllJerseys(!allJerseys)}>
                {allJerseys ? 'Show fewer' : `+${hiddenJerseys} more`}
              </button>
            )}
          </div>
        )}
      </section>

      <div className="tr-shelf">
        {SHELF.map((t) => {
          const n = tileCount(t.key);
          return (
            <button key={t.key} type="button" disabled={n === 0}
                    className={`tr-tile${n === 0 ? ' tr-tile-zero' : ''}${openTile === t.key ? ' tr-tile-open' : ''}`}
                    onClick={() => setOpenTile(openTile === t.key ? null : t.key)} aria-expanded={openTile === t.key}>
              <b>{n}</b>
              <span>{t.label}</span>
              {n > 0 && <em>{tileLine(t.key)}</em>}
            </button>
          );
        })}
      </div>
      {openTile && (
        <div className="tr-tile-list">
          {tileList(openTile).map((row, i) => (
            <div key={i}>
              <b>{row.year ?? '—'}</b>
              {row.player
                ? <button type="button" className="hi-link" onClick={() => openPlayerProfile(row.player)}>{row.text}</button>
                : <span>{row.text}</span>}
            </div>
          ))}
          {openTile === 'titles' && room.cabinet.lost_finals.map((f) => (
            <div key={`lf-${f.season}`} className="tr-lost"><b>{f.year ?? '—'}</b><span>Lost Finals{f.winner ? ` to ${f.winner}` : ''}</span></div>
          ))}
        </div>
      )}

      <div className="tr-cards">
        <section className="tr-card">
          <h3 className="tr-card-title">Franchise leaders</h3>
          <div className="tr-tabs" role="tablist">
            {LEADER_TABS.map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={leaderTab === t.key}
                      className={leaderTab === t.key ? 'on' : ''} onClick={() => setLeaderTab(t.key)}>{t.label}</button>
            ))}
          </div>
          {leaders.length === 0 ? <p className="tr-none">No games played yet</p> : (
            <table className="tr-table">
              <thead><tr><th>#</th><th>Player</th><th>Years</th><th className="r">{unit}</th></tr></thead>
              <tbody>
                {leaders.map((l, i) => (
                  <tr key={l.name}>
                    <td>{i + 1}</td>
                    <td><button type="button" className="hi-link tr-strong" onClick={() => openPlayerProfile(l.name)}>{l.name}</button></td>
                    <td className="tr-dim">{span(l.first_year, l.last_year)}</td>
                    <td className="tr-val">{l.value.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="tr-card">
          <h3 className="tr-card-title">Franchise records</h3>
          <div className="tr-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={recordTab === 'game'} className={recordTab === 'game' ? 'on' : ''} onClick={() => setRecordTab('game')}>Single game</button>
            <button type="button" role="tab" aria-selected={recordTab === 'season'} className={recordTab === 'season' ? 'on' : ''} onClick={() => setRecordTab('season')}>Single season</button>
          </div>
          {(recordTab === 'game' ? room.records.single_game : room.records.single_season).length === 0 ? (
            <p className="tr-none">No records yet</p>
          ) : (
            <table className="tr-table">
              <tbody>
                {(recordTab === 'game' ? room.records.single_game : room.records.single_season).map((r) => (
                  <tr key={r.stat}>
                    <td>{STAT_LABELS[r.stat] || r.stat}</td>
                    <td>
                      <button type="button" className="hi-link tr-strong" onClick={() => openPlayerProfile(r.player)}>{r.player}</button>
                      <span className="tr-dim"> {'opponent' in r && r.opponent ? `vs ${r.opponent} · ` : '· '}{r.year ?? '—'}</span>
                    </td>
                    <td className="tr-val">{r.value.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      {room.seasons.length > 0 && (
        <section className="tr-seasons">
          <button type="button" className="tr-more" onClick={() => setShowSeasons(!showSeasons)} aria-expanded={showSeasons}>
            {showSeasons ? 'Hide seasons' : `Show all ${room.seasons.length} seasons`}
          </button>
          {showSeasons && (
            <>
              <div className="tr-chart">
                {room.seasons.map((s) => (
                  <div key={s.season} className="tr-col"
                       title={s.missing ? `${s.year ?? ''} · No record` : `${s.year} · ${s.wins}–${s.losses} · ${s.result}${s.conf_seed ? ` · seed ${s.conf_seed}` : ''}`}>
                    {s.result === 'Champions' && <span className="tr-cup">🏆</span>}
                    <i className={s.missing ? 'tr-bar-missing' : RESULT_CLASS[s.result || 'Playoffs']}
                       style={s.missing ? undefined : { height: `${Math.max(4, ((s.wins || 0) / maxWins) * 100)}%` }} />
                  </div>
                ))}
              </div>
              <div className="tr-years">{room.seasons.map((s) => <span key={s.season}>{s.year ? String(s.year).slice(2) : ''}</span>)}</div>
              <div className="tr-legend">
                <span><i className="tr-bar-lottery" />Lottery / Play-In</span><span><i className="tr-bar-playoffs" />Playoffs</span>
                <span><i className="tr-bar-finals" />Lost Finals</span><span><i className="tr-bar-champ" />Champions</span>
                <span><i className="tr-bar-missing" />No record</span>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
};
