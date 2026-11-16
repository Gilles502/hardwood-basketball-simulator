// League Records tab ("the record book"): single-game highs and single-season per-game bests as printed record
// lines, with the career triple-doubles ladder beside them. Payload from core/records_view.py.
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';

interface RecordLine {
  stat: string;
  value: number;
  player: string;
  team: string | null;
  opponent?: string | null;
  year: number | null;
  is_user_team: boolean;
}

interface RecordsView {
  single_game: RecordLine[];
  single_season: RecordLine[];
  triple_doubles: { player: string; count: number; played_for_user: boolean }[];
}

const LABELS: Record<string, string> = {
  points: 'Points', rebounds: 'Rebounds', assists: 'Assists', three_pointers: 'Threes', steals: 'Steals',
  blocks: 'Blocks', ppg: 'Points per game', rpg: 'Rebounds per game', apg: 'Assists per game',
  spg: 'Steals per game', bpg: 'Blocks per game',
};

export const RecordsTab: React.FC = () => {
  const { openPlayerProfile } = useLeagueStore();
  const [view, setView] = useState<RecordsView | null>(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<'game' | 'season'>('game');

  useEffect(() => {
    fetch(`/api/records?_t=${Date.now()}`)
      .then((res) => res.json())
      .then((data) => (data && Array.isArray(data.single_game) ? setView(data) : setFailed(true)))
      .catch(() => setFailed(true));
  }, []);

  if (!view && !failed) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '40vh' }}><div className="spinner"></div></div>;
  }
  if (!view) return <div className="hi-empty"><h2>The record book could not be loaded</h2></div>;

  const lines = tab === 'game' ? view.single_game : view.single_season;
  const topTd = view.triple_doubles[0]?.count || 1;

  return (
    <div className="rb-root">
      <div className="tr-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === 'game'} className={tab === 'game' ? 'on' : ''} onClick={() => setTab('game')}>Single game</button>
        <button type="button" role="tab" aria-selected={tab === 'season'} className={tab === 'season' ? 'on' : ''} onClick={() => setTab('season')}>Single season</button>
      </div>
      <div className="hi-paper rb-book">
        <div>
          <div className="hi-kicker">League record book</div>
          {lines.length === 0 ? (
            <p className="rb-none">{tab === 'game' ? 'No games played yet.' : `No season finished yet.`}</p>
          ) : lines.map((r) => (
            <div key={r.stat} className="rb-line">
              <div className="rb-value">{r.value}</div>
              <div>
                <div className="rb-stat">{LABELS[r.stat] || r.stat} · {tab === 'game' ? 'game' : 'season'}</div>
                <div className="rb-player">
                  <button type="button" className="hi-link" onClick={() => openPlayerProfile(r.player)}>{r.player}</button>
                  {r.is_user_team && <span className="hi-yours">Yours</span>}
                </div>
                <div className="rb-where">{r.team}{r.opponent ? ` vs ${r.opponent}` : ''} · {r.year ?? '—'}</div>
              </div>
            </div>
          ))}
          {tab === 'season' && lines.length > 0 && <p className="rb-note">Per-game averages, minimum games played applies.</p>}
        </div>
        <div>
          <div className="hi-kicker">Career triple-doubles</div>
          {view.triple_doubles.length === 0 ? <p className="rb-none">None yet.</p> : (
            <div className="rb-ladder">
              {view.triple_doubles.map((t, i) => (
                <div key={t.player} className="rb-rung">
                  <span className="rb-rank">{i + 1}</span>
                  <span>
                    <button type="button" className="hi-link" onClick={() => openPlayerProfile(t.player)}>{t.player}</button>
                    {t.played_for_user && <span className="hi-yours">Yours</span>}
                  </span>
                  <b>{t.count}</b>
                  <div className="rb-bar"><i style={{ width: `${(t.count / topTd) * 100}%` }} /></div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
