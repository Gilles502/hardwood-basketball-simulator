// Phase 1 · Season recap ("your season beside the league"): left your record, playoff run, honours and leaders;
// right the champion, the trophies and the honour teams. Payload from core/end_season_views.season_recap_view.
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { crestHue } from '../../utils/crest';
import type { PhaseProps } from '../../utils/endSeason';

interface RunRow { round: string; opponent: string; opponent_seed: number | string | null; won: number; lost: number; result: 'won' | 'lost' }
interface Leader { player: string; value: number }
interface Recap {
  season: number;
  year: number | null;
  yours: {
    team: string; wins: number; losses: number; seed: number | null; conference: string | null; league_rank: number | null;
    off_rating: number | null; off_rank: number | null; def_rating: number | null; def_rank: number | null; margin: number | null;
    verdict: string; run: RunRow[]; beaten_by: string | null; beaten_by_result: string | null;
    honours: { player: string; honours: string[] }[];
    leaders: { points: Leader | null; rebounds: Leader | null; assists: Leader | null };
  } | null;
  league: {
    champion: { team: string | null; wins: number | null; losses: number | null; seed: number | null; conference: string | null };
    runner_up: string | null;
    finals_mvp: string | null;
    trophies: { key: string; label: string; winner: string | null; team: string | null }[];
    all_star_extra: { three_point: string | null; dunk: string | null };
    honour_teams: { key: string; label: string; players: { name: string; yours: boolean }[] }[];
  };
}

const ordinal = (n: number | null) => {
  if (n == null) return '—';
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};
const signed = (n: number | null) => (n == null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(1)}`);
const teamGradient = (team: string | null, strong = 42) =>
  `linear-gradient(110deg, hsl(${crestHue(team || '')} 62% ${strong}%) 0%, hsl(${crestHue(team || '')} 60% 14%) 60%, #1a130e 100%)`;

export const RecapPhase: React.FC<PhaseProps> = () => {
  const { openPlayerProfile, openTeamProfile } = useLeagueStore();
  const [recap, setRecap] = useState<Recap | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/offseason/recap?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data) => { if (!cancelled) (data && data.league ? setRecap(data) : setFailed(true)); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, []);

  if (failed) return <div className="eos-sheet"><p className="eos-muted">The season recap could not be loaded.</p></div>;
  if (!recap) return <div className="eos-sheet"><p className="eos-muted">Loading…</p></div>;

  const { yours, league } = recap;
  const player = (name: string | null, cls = 'eos-link') => (name
    ? <button type="button" className={cls} onClick={() => openPlayerProfile(name)}>{name}</button>
    : <em className="eos-muted">Not awarded</em>);
  const team = (name: string | null, cls = 'eos-link') => (name
    ? <button type="button" className={cls} onClick={() => openTeamProfile(name)}>{name}</button> : null);

  return (
    <div className={`rc-split${yours ? '' : ' rc-league-only'}`}>
      {yours && (
        <div className="rc-col">
          <section className="rc-band" style={{ background: teamGradient(yours.team) }}>
            <div>
              <div className="rc-kicker">{recap.year} · {yours.team}</div>
              <div className="rc-record">{yours.wins}–{yours.losses}</div>
              <div className="rc-verdict">{yours.verdict}</div>
            </div>
            <div className="rc-stats">
              <div><b>#{yours.seed ?? '—'}</b><span>{yours.conference ?? ''}</span></div>
              <div><b>{yours.off_rating ?? '—'}</b><span>Off rtg · {ordinal(yours.off_rank)}</span></div>
              <div><b>{yours.def_rating ?? '—'}</b><span>Def rtg · {ordinal(yours.def_rank)}</span></div>
              <div><b>{signed(yours.margin)}</b><span>Margin</span></div>
            </div>
          </section>

          <section className="rc-card">
            <h3 className="rc-h">Playoff run</h3>
            {yours.run.length === 0 ? <p className="eos-muted">No playoff series this year.</p> : (
              <div className="rc-run">
                {yours.run.map((r, i) => (
                  <div key={i} className={`rc-series is-${r.result}`}>
                    <span className="rc-round">{r.round}</span>
                    <span>vs {team(r.opponent)}{r.opponent_seed != null ? ` (${r.opponent_seed})` : ''}</span>
                    <b>{r.won}–{r.lost}</b>
                  </div>
                ))}
              </div>
            )}
            {yours.beaten_by && yours.beaten_by_result && (
              <p className="eos-muted rc-after">{yours.beaten_by} went on: {yours.beaten_by_result.toLowerCase()}.</p>
            )}
          </section>

          <section className="rc-card">
            <h3 className="rc-h">Your honours</h3>
            {yours.honours.length === 0 ? <p className="eos-muted">No awards or honour teams this season.</p> : (
              <ul className="rc-rows">
                {yours.honours.map((h) => (
                  <li key={h.player}>{player(h.player)}<span className="rc-chips">{h.honours.map((x) => <span key={x} className={`rc-chip${x.startsWith('All-League') || !x.startsWith('All') ? ' is-gold' : ''}`}>{x}</span>)}</span></li>
                ))}
              </ul>
            )}
          </section>

          <section className="rc-card">
            <h3 className="rc-h">Your leaders</h3>
            <ul className="rc-rows">
              {([['points', 'Points'], ['rebounds', 'Rebounds'], ['assists', 'Assists']] as const).map(([key, label]) => {
                const l = yours.leaders[key];
                return <li key={key}><span>{label}</span>{l ? <span>{player(l.player)} <b>{l.value}</b></span> : <span className="eos-muted">—</span>}</li>;
              })}
            </ul>
          </section>
        </div>
      )}

      <div className="rc-col">
        <section className="rc-poster" style={{ background: teamGradient(league.champion.team, 38) }}>
          <div className="rc-kicker">{recap.year} champions</div>
          <div className="rc-champ">{team(league.champion.team, 'eos-link rc-champ-link') ?? 'No champion'}</div>
          <div className="rc-def">
            {league.runner_up ? <>def. {league.runner_up} in the Finals</> : 'Finals'}
            {league.champion.wins != null && <> · {league.champion.wins}–{league.champion.losses}, #{league.champion.seed} {league.champion.conference}</>}
          </div>
          {league.finals_mvp && <div className="rc-fmvp">Finals MVP {player(league.finals_mvp, 'eos-link rc-fmvp-name')}</div>}
          <div className="rc-poster-year">{recap.year}</div>
        </section>

        <div className="rc-trophies">
          {league.trophies.map((t) => (
            <div key={t.key} className={`rc-trophy${t.key === 'mvp' ? ' is-gold' : ''}`}>
              <div className="rc-trophy-label">{t.label}</div>
              <div className="rc-trophy-winner">{player(t.winner)}</div>
              <div className="rc-trophy-team">
                {t.key === 'all_star_mvp'
                  ? [league.all_star_extra.three_point && `3PT: ${league.all_star_extra.three_point}`, league.all_star_extra.dunk && `Dunk: ${league.all_star_extra.dunk}`].filter(Boolean).join(' · ')
                  : t.team ?? ''}
              </div>
            </div>
          ))}
        </div>

        <div className="rc-teams">
          {league.honour_teams.map((t) => (
            <div key={t.key} className="eos-sheet rc-team">
              <h4>{t.label}</h4>
              {t.players.length === 0 ? <p className="eos-muted">—</p> : t.players.map((p) => (
                <div key={p.name} className={p.yours ? 'is-yours' : undefined}>
                  <button type="button" className="eos-link" onClick={() => openPlayerProfile(p.name)}>{p.name}</button>{p.yours ? ' ★' : ''}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
