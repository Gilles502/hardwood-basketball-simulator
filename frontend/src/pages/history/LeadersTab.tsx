// All-Time Leaders tab ("one board at a time"): pick a career total or an honour; the selected player gets a card,
// everyone else is a ranked bar list. Payload from core/records_view.py (top CONFIG.HISTORY.LEADERS_TOP_N).
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';

interface Card {
  ppg: number; rpg: number; apg: number; peak_ppg: number;
  titles: number; mvp: number; finals_mvp: number; dpoy: number; all_star: number; all_league: number;
}

interface Row {
  rank: number;
  name: string;
  value: number;
  games: number;
  seasons: number;
  first_year: number | null;
  last_year: number | null;
  last_team: string | null;
  per_game?: number;
  played_for_user: boolean;
  card: Card;
}

interface LeadersView { total_players: number; boards: Record<string, Row[]> }

const TOTALS = [
  { key: 'points', label: 'Points', per: 'PPG' },
  { key: 'rebounds', label: 'Rebounds', per: 'RPG' },
  { key: 'assists', label: 'Assists', per: 'APG' },
  { key: 'steals', label: 'Steals', per: 'SPG' },
  { key: 'blocks', label: 'Blocks', per: 'BPG' },
];
const HONOURS = [
  { key: 'titles', label: 'Titles' },
  { key: 'mvp', label: 'MVP' },
  { key: 'finals_mvp', label: 'Finals MVP' },
  { key: 'dpoy', label: 'DPOY' },
  { key: 'all_star', label: 'All-Star' },
  { key: 'all_league', label: 'All-League' },
];
const CHIPS: { key: keyof Card; one: string; many: string }[] = [
  { key: 'titles', one: 'title', many: 'titles' }, { key: 'mvp', one: 'MVP', many: 'MVP' },
  { key: 'finals_mvp', one: 'Finals MVP', many: 'Finals MVP' }, { key: 'dpoy', one: 'DPOY', many: 'DPOY' },
  { key: 'all_star', one: 'All-Star', many: 'All-Star' }, { key: 'all_league', one: 'All-League', many: 'All-League' },
];

const years = (r: Row) => (r.first_year == null ? '' : r.first_year === r.last_year ? `${r.first_year}` : `${r.first_year}–${r.last_year}`);

export const LeadersTab: React.FC = () => {
  const { openPlayerProfile } = useLeagueStore();
  const [view, setView] = useState<LeadersView | null>(null);
  const [failed, setFailed] = useState(false);
  const [board, setBoard] = useState('points');
  const [picked, setPicked] = useState(0);

  useEffect(() => {
    fetch(`/api/career-leaders?_t=${Date.now()}`)
      .then((res) => res.json())
      .then((data) => (data && data.boards ? setView(data) : setFailed(true)))
      .catch(() => setFailed(true));
  }, []);

  if (!view && !failed) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '40vh' }}><div className="spinner"></div></div>;
  }
  if (!view) return <div className="hi-empty"><h2>The leaders could not be loaded</h2></div>;

  const rows = view.boards[board] || [];
  const sel = rows[Math.min(picked, rows.length - 1)];
  const total = TOTALS.find((t) => t.key === board);
  const label = (total || HONOURS.find((h) => h.key === board))?.label || board;
  const top = rows[0]?.value || 1;
  const choose = (key: string) => { setBoard(key); setPicked(0); };

  const chips = (keys: { key: string; label: string }[]) => keys.map((k) => (
    <button key={k.key} type="button" role="tab" aria-selected={board === k.key} className={board === k.key ? 'on' : ''}
            onClick={() => choose(k.key)}>{k.label}</button>
  ));

  return (
    <div className="lb-root">
      <div className="lb-groups">
        <span className="lb-group-label">Totals</span><div className="tr-tabs" role="tablist">{chips(TOTALS)}</div>
        <span className="lb-group-label">Honours</span><div className="tr-tabs" role="tablist">{chips(HONOURS)}</div>
      </div>

      {rows.length === 0 || !sel ? (
        <div className="hi-empty"><h2>No {label.toLowerCase()} yet</h2><p>Finish a season to fill the boards.</p></div>
      ) : (
        <div className="lb-layout">
          <div className="hi-paper lb-card">
            <div className="hi-kicker">#{sel.rank} all-time · {label}</div>
            <button type="button" className="hi-link lb-card-name" onClick={() => openPlayerProfile(sel.name)}>{sel.name}</button>
            {sel.played_for_user && <span className="hi-yours">Yours</span>}
            <div className="lb-card-big">{sel.value.toLocaleString()}</div>
            <div className="lb-stat4">
              <div><b>{sel.games.toLocaleString()}</b><span>Games</span></div>
              {total ? <div><b>{sel.per_game}</b><span>{total.per}</span></div> : <div><b>{sel.card.ppg}</b><span>PPG</span></div>}
              <div><b>{sel.card.peak_ppg}</b><span>Peak PPG</span></div>
              <div><b>{sel.seasons}</b><span>Seasons</span></div>
            </div>
            <div className="hi-chips">
              {CHIPS.filter((c) => sel.card[c.key] > 0).map((c) => (
                <span key={c.key} className="hi-chip"><b>{sel.card[c.key]}</b> {sel.card[c.key] === 1 ? c.one : c.many}</span>
              ))}
            </div>
            <div className="lb-card-meta">{years(sel)}{sel.last_team ? ` · last team ${sel.last_team}` : ''}</div>
          </div>

          <div className="lb-list">
            {rows.map((r, i) => (
              <div key={r.name} className={`lb-row${i === picked ? ' on' : ''}`} role="button" tabIndex={0}
                   onClick={() => setPicked(i)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setPicked(i); } }}>
                <span className="lb-rank">{r.rank}</span>
                <span className="lb-who">
                  <span className="lb-name">{r.name}{r.played_for_user && <span className="hi-yours">Yours</span>}</span>
                  <span className="lb-meta">{[r.last_team, `${r.seasons} seasons`].filter(Boolean).join(' · ')}</span>
                </span>
                <span className="lb-bar"><i style={{ width: `${(r.value / top) * 100}%` }} /></span>
                <span className="lb-value">{r.value.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
