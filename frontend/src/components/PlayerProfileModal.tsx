// File: frontend/src/components/PlayerProfileModal.tsx
// Player quick look (mockup C): the popup any player name opens. One narrow scrolling column — who he is right now
// (status, form, this season, contract, ratings, latest moments); his history lives in the Player Database, one button
// away. Pressing the card thumbnail shows the full scouting card (flip + paper picker).
import React, { useEffect, useMemo, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { ModalShell } from './ModalShell';
import { ScoutingCard } from './ScoutingCard';
import { computePlayerBadges, ratingGroups } from '../utils/playerRatings';
import type { PlayerPayload } from '../pages/database/types';
import './PlayerQuickLook.css';

interface StatsGroup {
  ppg: number;
  rpg: number;
  apg: number;
  spg: number;
  bpg: number;
  fg_pct?: number;
  three_pct?: number;
  ft_pct?: number;
}

interface CareerEntry {
  stagione: number;
  squadra: string;
  eta: number;
  is_champion: boolean;
  partite_giocate_rs: number;
  partite_giocate_po?: number;
  stats_rs: StatsGroup;
  stats_po?: StatsGroup | null;
  premi: string[];
}

interface TimelineEvent {
  type?: string;
  icon?: string;
  title?: string;
  description?: string;
  season?: number;
  day?: number;
  team?: string;
}

interface PlayerProfileModalProps {
  playerName: string;
  onClose: () => void;
}

const LATEST_EVENTS = 5;
// Header chips after the title count, in this order.
const CHIP_AWARDS = ['MVP', 'Finals MVP', 'DPOY', 'ROY', '6th Man', 'MIP', 'All-NBA 1st', 'All-NBA 2nd', 'All-NBA 3rd', 'All-Star'];
// lore.role_badge the server sends when it has nothing better.
const PLACEHOLDER_ROLES = new Set(['Giocatore', '']);

const slugOf = (name: string) => name.replace(/ /g, '-').toLowerCase();
const fmt1 = (v: number | null | undefined) => (v === null || v === undefined ? '—' : v.toFixed(1));

/** Today's season row for the card back (the archive only holds finished seasons). */
function withCurrentSeason(careerStats: CareerEntry[], player: any, season: number): CareerEntry[] {
  if (!player) return [...careerStats].sort((a, b) => b.stagione - a.stagione);
  const rs = player.stats_rs || player.stats || {};
  const po = player.stats_po;
  const current: CareerEntry = {
    stagione: season,
    squadra: player.squadra || 'Free Agent',
    eta: player.eta,
    is_champion: false,
    partite_giocate_rs: rs.partite_giocate || 0,
    partite_giocate_po: po?.partite_giocate || 0,
    stats_rs: { ppg: rs.ppg ?? 0, rpg: rs.rpg ?? 0, apg: rs.apg ?? 0, spg: rs.spg ?? 0, bpg: rs.bpg ?? 0, fg_pct: rs.fg_pct, three_pct: rs.three_pct, ft_pct: rs.ft_pct },
    stats_po: po ? { ppg: po.ppg || 0, rpg: po.rpg || 0, apg: po.apg || 0, spg: po.spg || 0, bpg: po.bpg || 0, fg_pct: po.fg_pct, three_pct: po.three_pct, ft_pct: po.ft_pct } : null,
    premi: player.premi || [],
  };
  return [current, ...careerStats.filter((s) => s.stagione !== season)].sort((a, b) => b.stagione - a.stagione);
}

const Meter: React.FC<{ label: string; value: number; note: string; tone: 'ember' | 'cream' }> = ({ label, value, note, tone }) => (
  <div className="pq-tile">
    <div className="pq-kicker">{label} <b>{Math.round(value)}%</b></div>
    <div className={`pq-meter is-${tone}`}><i style={{ width: `${Math.min(100, Math.max(3, value))}%` }} /></div>
    <div className="pq-muted">{note}</div>
  </div>
);

const staminaNote = (v: number) => (v >= 80 ? 'Fresh' : v >= 60 ? 'Feeling the schedule' : 'Tired: losing sharpness late');
const moraleNote = (v: number) => (v >= 80 ? 'Happy, great chemistry' : v >= 60 ? 'Content' : 'Unhappy');

export const PlayerProfileModal: React.FC<PlayerProfileModalProps> = ({ playerName, onClose }) => {
  const { leagueData, openInDatabase } = useLeagueStore();
  const [careerStats, setCareerStats] = useState<CareerEntry[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [liveDetails, setLiveDetails] = useState<any | null>(null);
  const [db, setDb] = useState<PlayerPayload | null>(null);
  const [showCard, setShowCard] = useState(false);
  const [allRatings, setAllRatings] = useState(false);
  const [allEvents, setAllEvents] = useState(false);

  const listed = useMemo(() => {
    const ldb = leagueData?.league_database;
    if (!ldb) return null;
    for (const t of ldb.teams || []) {
      const match = t.roster?.find((p: any) => p.nome === playerName);
      if (match) return match;
    }
    return ldb.players_fa?.find((p: any) => p.nome === playerName) || ldb.players_retired?.find((p: any) => p.nome === playerName) || null;
  }, [leagueData, playerName]);
  const player = liveDetails || listed;
  const isRetired = !!leagueData?.league_database?.players_retired?.some((p: any) => p.nome === playerName);

  useEffect(() => {
    let alive = true;
    fetch(`/api/player/${encodeURIComponent(playerName)}/career`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!alive || !data) return;
        setCareerStats(data.carriera || []);
        setTimeline(data.timeline || []);
        if (data.giocatore) setLiveDetails(data.giocatore);
      })
      .catch(() => {});
    fetch(`/api/database/player/${encodeURIComponent(slugOf(playerName))}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (alive && data) setDb(data); })
      .catch(() => {});
    return () => { alive = false; };
  }, [playerName]);

  const season = leagueData?.stagione || (leagueData as any)?.season_number || 1;
  const cardSeasons = useMemo(() => withCurrentSeason(careerStats, player, season), [careerStats, player, season]);
  const groups = useMemo(() => ratingGroups(player), [player]);
  const badges = useMemo(() => computePlayerBadges(player), [player]);
  const yearOf = useMemo(() => new Map((db?.rs ?? []).map((ln) => [ln.season, ln.year])), [db]);
  const events = useMemo(() => [...timeline].sort((a, b) => (b.season ?? 0) - (a.season ?? 0) || (b.day ?? 0) - (a.day ?? 0)), [timeline]);

  const team = player?.squadra && player.squadra !== 'Free Agent' ? player.squadra : null;
  const onTeam = !!team && !isRetired;
  const status = isRetired ? 'Retired' : team ?? 'Free agent';
  const role = player?.lore?.role_badge && !PLACEHOLDER_ROLES.has(player.lore.role_badge) ? player.lore.role_badge : null;
  const subtitle = [player?.ruolo, player?.eta ? `${player.eta} yrs` : null, status, role].filter(Boolean).join(' · ');
  const awards = db?.career.awards ?? {};
  const titles = db?.career.titles ?? careerStats.filter((s) => s.is_champion).length;
  const chips = CHIP_AWARDS.filter((a) => awards[a]).map((a) => (awards[a] > 1 ? `${awards[a]}× ${a}` : a)).slice(0, 4);
  const contract = player?.contract_data;
  const yearsInTeam = player?.anni_nella_squadra ?? 1;
  const bird = yearsInTeam >= 3 ? 'Full Bird rights' : yearsInTeam >= 2 ? 'Early Bird rights' : 'Non-Bird';
  const cur = db?.current ?? null;
  const injured = player?.infortunato || player?.is_day_to_day;
  const shownEvents = allEvents ? events : events.slice(0, LATEST_EVENTS);
  const initials = (playerName || '?').split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <ModalShell isOpen onClose={onClose} title={playerName} subtitle={subtitle} maxWidth={460}
      icon={<span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '15px' }}>{initials}</span>}>
      {showCard ? (
        <div className="pq-cardview">
          <button type="button" className="pq-ghost" onClick={() => setShowCard(false)}>← Back to quick look</button>
          <ScoutingCard player={{ ...player, carriera: careerStats.length ? careerStats : player?.carriera || [] }}
            seasons={cardSeasons} retired={isRetired} showStylePicker />
        </div>
      ) : (
        <div className="pq">
          <div className="pq-head">
            <button type="button" className="pq-thumb" onClick={() => setShowCard(true)} aria-label="Show the full scouting card">
              <span className="pq-thumb-ovr">{player?.ovr ?? '—'}</span>
              <span className="pq-thumb-sub">POT {player?.pot ?? player?.potenziale ?? '—'}</span>
              <span className="pq-thumb-sub">Card ↗</span>
            </button>
            <div className="pq-head-info">
              <div className="pq-chips">
                {titles > 0 && <span className="pq-chip is-ring">🏆 ×{titles}</span>}
                {chips.map((c) => <span key={c} className="pq-chip">{c}</span>)}
                {player?.trade_request && <span className="pq-chip is-warn">Asked for a trade</span>}
                {player?.on_trade_block && <span className="pq-chip is-warn">On the block</span>}
              </div>
              {player?.lore?.status_narrative && <p className="pq-note" title={player.lore.status_narrative}>“{player.lore.status_narrative}”</p>}
              {badges.length > 0 && <div className="pq-muted">{badges.map((b) => b.name).join(' · ')}</div>}
            </div>
          </div>

          {injured && (
            <div className={`pq-injury${player.is_day_to_day ? ' is-dtd' : ''}`} role="status">
              <b>{player.is_day_to_day ? 'Day-to-day' : 'Out'}</b>
              {' · '}{player.infortunio_nome || player.tipo_infortunio || 'Injury'}
              {player.giorni_infortunio_rimanenti ? ` · ${player.giorni_infortunio_rimanenti} days left` : ''}
            </div>
          )}

          {onTeam && (
            <div className="pq-grid2">
              <Meter label="Stamina" value={player?.stamina_stagionale ?? 100} note={staminaNote(player?.stamina_stagionale ?? 100)} tone="ember" />
              <Meter label="Morale" value={player?.morale ?? 85} note={moraleNote(player?.morale ?? 85)} tone="cream" />
            </div>
          )}

          <div className="pq-tile">
            <div className="pq-kicker">This season{contract || onTeam ? ' · contract' : ''}</div>
            <div className="pq-line">
              {cur && cur.gp ? <>
                <b>{fmt1(cur.s.pts_pg)} / {fmt1(cur.s.reb_pg)} / {fmt1(cur.s.ast_pg)}</b>
                <span className="pq-muted"> · {cur.gp} GP{cur.s.ts_pct !== null ? ` · ${fmt1(cur.s.ts_pct)} TS%` : ''}{cur.s.per !== null ? ` · PER ${fmt1(cur.s.per)}` : ''}</span>
              </> : <span className="pq-muted">{isRetired ? `Retired${db?.retired_year ? ` after ${db.retired_year}` : ''}` : 'No games yet this season'}</span>}
            </div>
            {contract && contract.salary > 0 && (
              <div className="pq-line">
                <b>${contract.salary.toFixed(1)}M × {contract.years} yr{contract.years === 1 ? '' : 's'}</b>
                <span className="pq-muted"> · {[onTeam ? bird : null, contract.player_option ? 'player option' : null, contract.team_option ? 'team option' : null].filter(Boolean).join(' · ')}</span>
              </div>
            )}
          </div>

          <div className="pq-paper">
            <div className="pq-kicker is-paper">Ratings</div>
            {groups.map((g) => (
              <React.Fragment key={g.label}>
                <div className="pq-bar">
                  <span>{g.label}</span>
                  <span className="pq-track"><i className={g.value !== null && g.value >= 85 ? 'is-hot' : undefined} style={{ width: `${g.value ?? 0}%` }} /></span>
                  <b>{g.value ?? '—'}</b>
                </div>
                {allRatings && g.ratings.map((r) => (
                  <div key={r.label} className="pq-bar is-sub">
                    <span>{r.label}</span>
                    <span className="pq-track"><i style={{ width: `${r.value ?? 0}%` }} /></span>
                    <b>{r.value ?? '—'}</b>
                  </div>
                ))}
              </React.Fragment>
            ))}
            <button type="button" className="pq-more" onClick={() => setAllRatings((v) => !v)} aria-expanded={allRatings}>
              {allRatings ? 'Groups only ▴' : 'All ratings ▾'}
            </button>
          </div>

          <div className="pq-tile">
            <div className="pq-kicker">Latest</div>
            {events.length === 0 ? <div className="pq-muted">Injuries, 40-point nights, triple-doubles and awards show up here as the season runs.</div> : (
              <ul className="pq-events">
                {shownEvents.map((e, i) => (
                  <li key={`${e.season}-${e.day}-${i}`}>
                    <span className="pq-when">{(e.season && yearOf.get(e.season)) ?? (e.season ? `Season ${e.season}` : '')}</span>
                    <span><span aria-hidden="true">{e.icon || '•'}</span> <b>{e.title}</b>{e.description ? <span className="pq-muted"> · {e.description}</span> : null}</span>
                  </li>
                ))}
              </ul>
            )}
            {events.length > LATEST_EVENTS && (
              <button type="button" className="pq-more" onClick={() => setAllEvents((v) => !v)} aria-expanded={allEvents}>
                {allEvents ? 'Latest only ▴' : `All ${events.length} moments ▾`}
              </button>
            )}
          </div>

          <button type="button" className="pq-open" onClick={() => openInDatabase({ slug: slugOf(playerName), name: playerName })}>
            Open in Player Database →
          </button>
        </div>
      )}
    </ModalShell>
  );
};
