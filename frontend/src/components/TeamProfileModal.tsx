// File: frontend/src/components/TeamProfileModal.tsx
// Team card (mockup A "quick look"): the popup any team name opens, built like the player quick look. Record and seed,
// payroll against the tax, the rotation, picks and the last seasons; the Trophy Room and team analytics are one button
// away. Payload from /api/team-card/<team> (core/team_card_view.py).
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { nickname } from '../utils/resultSheet';
import { ModalShell } from './ModalShell';
import './PlayerQuickLook.css';

interface CardPlayer {
  name: string;
  pos: string | null;
  age: number | null;
  ovr: number | null;
  ppg: number | null;
  salary: number | null;
  years: number | null;
  injured: boolean;
  rotation: boolean;
}

interface CardPick { year: number; round: number; kind: 'own' | 'via' | 'to'; team: string | null; protection: string | null }

interface CardSeason { year: number | null; wins: number; losses: number; seed: number | null; champion: boolean; result: string; playoffs: boolean }

interface TeamCard {
  name: string;
  conference: string | null;
  wins: number;
  losses: number;
  seed: number | null;
  is_user: boolean;
  payroll: number;
  tax_line: number | null;
  over_tax: number | null;
  roster_count: number;
  roster_limit: number;
  roster: CardPlayer[];
  picks: CardPick[];
  seasons: CardSeason[];
}

interface TeamProfileModalProps {
  teamName: string;
  onClose: () => void;
}

const ordinal = (n: number) => {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};
const money = (v: number) => `$${v.toFixed(1)}M`;

const pickLabel = (p: CardPick) => {
  const where = p.kind === 'own' ? 'own' : p.kind === 'via' ? `via ${nickname(p.team ?? '?')}` : `→ ${nickname(p.team ?? '?')}`;
  return `${p.year} R${p.round} ${where}${p.protection ? ` (${p.protection})` : ''}`;
};

export const TeamProfileModal: React.FC<TeamProfileModalProps> = ({ teamName, onClose }) => {
  const { openPlayerProfile, openTeamPage } = useLeagueStore();
  const [card, setCard] = useState<TeamCard | null>(null);
  const [failed, setFailed] = useState(false);
  const [fullRoster, setFullRoster] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`/api/team-card/${encodeURIComponent(teamName)}?_t=${Date.now()}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: TeamCard) => { if (alive) setCard(data); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [teamName]);

  const initials = teamName.split(' ').map((w) => w[0]).join('').slice(0, 3).toUpperCase();
  const subtitle = card
    ? [`${card.wins}-${card.losses}`, card.seed && card.conference ? `${ordinal(card.seed)} ${card.conference}` : null, card.is_user ? 'your team' : null]
      .filter(Boolean).join(' · ')
    : undefined;
  const roster = card ? (fullRoster ? card.roster : card.roster.filter((p) => p.rotation)) : [];
  // Bars scale to the best of these seasons so the gaps between them show
  const maxWins = Math.max(1, ...(card?.seasons ?? []).map((s) => s.wins));
  const taxNote = card?.over_tax === null || card?.over_tax === undefined ? 'No luxury tax'
    : card.over_tax > 0 ? `${money(card.over_tax)} over the tax` : `${money(-card.over_tax)} under the tax`;

  return (
    <ModalShell isOpen onClose={onClose} title={teamName} subtitle={subtitle} maxWidth={460}
      icon={<span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '14px' }}>{initials}</span>}>
      {!card ? (
        <div className="pq">
          {failed ? <p className="pq-muted">This team could not be loaded.</p> : <div className="spinner" style={{ margin: '40px auto' }} />}
        </div>
      ) : (
        <div className="pq">
          <div className="pq-grid3">
            <div className="pq-tile"><b className="pq-num">{card.wins}-{card.losses}</b><span className="pq-muted">{card.seed ? `${ordinal(card.seed)} ${card.conference ?? ''}` : 'Record'}</span></div>
            <div className="pq-tile"><b className="pq-num">{money(card.payroll)}</b><span className="pq-muted">{taxNote}</span></div>
            <div className="pq-tile"><b className="pq-num">{card.roster_count} / {card.roster_limit}</b><span className="pq-muted">Roster</span></div>
          </div>

          <div className="pq-paper">
            <div className="pq-kicker is-paper">{fullRoster ? 'Full roster' : 'Rotation'}</div>
            {card.roster.length === 0 ? <p className="pq-muted">No players under contract.</p> : (
              <table className="pq-table">
                <caption className="an-sr">{teamName} roster</caption>
                <thead><tr><th className="is-left">Player</th><th>Pos</th><th>OVR</th><th>Age</th><th>PPG</th>{fullRoster && <th>Salary</th>}</tr></thead>
                <tbody>
                  {roster.map((p) => (
                    <tr key={p.name}>
                      <td className="is-left">
                        <button type="button" className="pq-name" onClick={() => openPlayerProfile(p.name)}>{p.name}</button>
                        {p.injured && <span className="pq-flag" title="Injured">INJ</span>}
                      </td>
                      <td>{p.pos ?? '—'}</td>
                      <td><b>{p.ovr ?? '—'}</b></td>
                      <td>{p.age ?? '—'}</td>
                      <td>{p.ppg === null ? '—' : p.ppg.toFixed(1)}</td>
                      {fullRoster && <td>{p.salary ? money(p.salary) : '—'}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {card.roster.length > roster.length || fullRoster ? (
              <button type="button" className="pq-more" onClick={() => setFullRoster((v) => !v)} aria-expanded={fullRoster}>
                {fullRoster ? 'Rotation only ▴' : `Full roster (${card.roster.length}) ▾`}
              </button>
            ) : null}
          </div>

          <div className="pq-tile">
            <div className="pq-kicker">Draft picks</div>
            {card.picks.length === 0 ? <div className="pq-muted">No future picks.</div> : (
              <div className="pq-chips">
                {card.picks.map((p, i) => <span key={i} className={`pq-chip${p.kind === 'to' ? ' is-out' : ''}`}>{pickLabel(p)}</span>)}
              </div>
            )}
          </div>

          <div className="pq-tile">
            <div className="pq-kicker">Last {card.seasons.length || ''} seasons</div>
            {card.seasons.length === 0 ? <div className="pq-muted">No finished season yet.</div> : (
              <>
                <div className="pq-bars" role="img" aria-label="Wins per season">
                  {card.seasons.map((s, i) => (
                    <div key={`${s.year}-${i}`} className="pq-bar-col"
                      title={`${s.year ?? ''}: ${s.wins}-${s.losses}${s.seed ? ` · ${ordinal(s.seed)} seed` : ''} · ${s.result}`}>
                      <i className={s.champion ? 'is-ring' : s.playoffs ? 'is-po' : undefined} style={{ height: `${Math.max(4, (s.wins / maxWins) * 100)}%` }} />
                      <span>{s.year ? String(s.year).slice(-2) : ''}</span>
                    </div>
                  ))}
                </div>
                <div className="pq-muted">Bar = wins · sand = playoffs · orange = title</div>
              </>
            )}
          </div>

          <div className="pq-grid2">
            <button type="button" className="pq-ghost is-wide" onClick={() => openTeamPage({ page: 'history', team: teamName })}>Trophy Room →</button>
            <button type="button" className="pq-open" onClick={() => openTeamPage({ page: 'analytics', team: teamName })}>Team analytics →</button>
          </div>
        </div>
      )}
    </ModalShell>
  );
};
