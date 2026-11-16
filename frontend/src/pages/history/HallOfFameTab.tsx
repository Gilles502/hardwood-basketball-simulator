// Hall of Fame tab ("podium + tiers"): inductees above the score bar (CONFIG.HISTORY on the server), ranked by
// Hall of Fame score. Top three on a podium, everyone else in named tiers.
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';

interface Accolades {
  titles: number;
  mvp: number;
  finals_mvp: number;
  dpoy: number;
  all_league_1st: number;
  all_league: number;
  all_star: number;
}

interface Inductee {
  rank: number;
  id: string;
  name: string;
  score: number;
  class_season: number | null;
  accolades: Accolades;
  stats: { ppg: number | null; rpg: number | null; apg: number | null; peak_ppg: number | null } | null;
  position: string | null;
  main_team: string | null;
  played_for_user: boolean;
}

interface HallOfFameView {
  total_inductees: number;
  shown: number;
  min_score: number;
  latest_class: { season: number; names: string[] } | null;
  podium: Inductee[];
  tiers: { name: string; min_score: number; players: Inductee[] }[];
}

/** Honours in the order they count most; a chip shows only when the player has at least one. */
const HONOURS: { key: keyof Accolades; one: string; many: string }[] = [
  { key: 'titles', one: 'ring', many: 'rings' },
  { key: 'mvp', one: 'MVP', many: 'MVP' },
  { key: 'finals_mvp', one: 'Finals MVP', many: 'Finals MVP' },
  { key: 'dpoy', one: 'DPOY', many: 'DPOY' },
  { key: 'all_league', one: 'All-League', many: 'All-League' },
  { key: 'all_star', one: 'All-Star', many: 'All-Star' },
];

const honourChips = (p: Inductee, limit?: number) => {
  const chips = HONOURS.filter((h) => p.accolades[h.key] > 0).map((h) => {
    const n = p.accolades[h.key];
    return <span key={h.key} className="hi-chip"><b>{n}</b> {n === 1 ? h.one : h.many}</span>;
  });
  if (chips.length === 0 && p.stats?.ppg != null) {
    chips.push(<span key="ppg" className="hi-chip"><b>{p.stats.ppg}</b> ppg</span>);
  }
  return limit ? chips.slice(0, limit) : chips;
};

const meta = (p: Inductee) => [p.position, p.main_team].filter(Boolean).join(' · ');

export const HallOfFameTab: React.FC = () => {
  const { openPlayerProfile } = useLeagueStore();
  const [view, setView] = useState<HallOfFameView | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(`/api/hall-of-fame?_t=${Date.now()}`)
      .then((res) => res.json())
      .then((data) => setView(data && Array.isArray(data.podium) ? data : null))
      .catch(() => setFailed(true));
  }, []);

  if (!view && !failed) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '40vh' }}><div className="spinner"></div></div>;
  }
  if (!view) {
    return <div className="hi-empty"><h2>The Hall of Fame could not be loaded</h2></div>;
  }
  if (view.shown === 0) {
    return (
      <div className="hi-empty">
        <div className="hi-empty-icon" aria-hidden="true">🏛️</div>
        <h2>No one has reached the Hall yet</h2>
        <p>
          Retired players are listed here once their Hall of Fame score reaches {view.min_score}.
          {view.total_inductees > 0 && ` ${view.total_inductees} inducted so far, all below that mark.`}
        </p>
      </div>
    );
  }

  const hidden = view.total_inductees - view.shown;
  // Podium order on screen: #2, #1, #3.
  const podium = [view.podium[1], view.podium[0], view.podium[2]].filter(Boolean) as Inductee[];

  return (
    <div className="hof-root">
      <div className="hof-top">
        <b>{view.shown} Hall of Famers</b>
        {view.latest_class && (
          <span>Latest class · Year {view.latest_class.season}: {view.latest_class.names.join(', ')}</span>
        )}
        {hidden > 0 && <span className="hof-hidden">{hidden} more inducted below a score of {view.min_score}</span>}
      </div>

      <div className={`hof-podium is-${podium.length}`}>
        {podium.map((p) => (
          <div key={p.id} className={`hof-pod${p.rank === 1 ? ' is-first' : ''}`}>
            <div className="hof-pod-rank" aria-label={`Rank ${p.rank}`}>{p.rank}</div>
            <div className="hi-kicker">
              {p.rank === 1 ? 'Greatest of all time · ' : ''}Class of Year {p.class_season}
            </div>
            <button type="button" className="hof-pod-name" onClick={() => openPlayerProfile(p.name)}>{p.name}</button>
            <div className="hof-pod-meta">
              {meta(p)}
              {p.played_for_user && <span className="hi-yours">Yours</span>}
            </div>
            <div className="hof-pod-score">
              Score <b>{p.score}</b>
              {p.stats?.ppg != null && <> · {p.stats.ppg} pts · {p.stats.rpg} reb</>}
            </div>
            <div className="hi-chips">{honourChips(p)}</div>
          </div>
        ))}
      </div>

      {view.tiers.filter((t) => t.players.length > 0).map((tier) => (
        <section key={tier.name} className="hof-tier">
          <h3>{tier.name} · {tier.min_score}+<i aria-hidden="true" /></h3>
          {tier.players.map((p) => (
            <button key={p.id} type="button" className="hof-row" onClick={() => openPlayerProfile(p.name)}>
              <span className="hof-row-rank">{p.rank}</span>
              <span className="hof-row-who">
                <span className="hof-row-name">{p.name}</span>
                <span className="hof-row-meta">
                  {meta(p)}
                  {p.played_for_user && <span className="hi-yours">Yours</span>}
                </span>
              </span>
              <span className="hof-row-class">Yr {p.class_season}</span>
              <span className="hi-chips">{honourChips(p, 3)}</span>
              <span className="hof-row-score">{p.score}</span>
            </button>
          ))}
        </section>
      ))}
    </div>
  );
};
