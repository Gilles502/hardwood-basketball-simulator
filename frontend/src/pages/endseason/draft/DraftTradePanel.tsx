// "Build my own trade" during the draft: replaces the big board in the page (no popup). Same roster tables as the
// Trade Center; the deal goes to /api/draft/propose_custom_trade with each pick's existing protection, as the Trade
// Center does. A refusal is shown here; an accepted deal returns the new draft state.
import React, { useEffect, useState } from 'react';
import { TradeRosterTable } from '../../trades/TradeRosterTable';
import type { TeamAssets } from '../../trades/types';
import type { DraftState } from './draftRoom';
import '../../trades/TradeMachine.css';

interface DraftTradePanelProps {
  userTeam: string;
  teams: string[];
  onDone: (state: DraftState) => void;
  onClose: () => void;
}

const EMPTY: TeamAssets = { players: [], picks: [] };
const toggle = (list: string[], key: string) => (list.includes(key) ? list.filter((k) => k !== key) : [...list, key]);
const protections = (assets: TeamAssets, keys: string[]) =>
  Object.fromEntries(keys.map((k) => [k, assets.picks.find((p) => p.key === k)?.protection || 'Unprotected']));

export const DraftTradePanel: React.FC<DraftTradePanelProps> = ({ userTeam, teams, onDone, onClose }) => {
  const [partner, setPartner] = useState('');
  const [mine, setMine] = useState<TeamAssets>(EMPTY);
  const [theirs, setTheirs] = useState<TeamAssets>(EMPTY);
  const [givePlayers, setGivePlayers] = useState<string[]>([]);
  const [givePicks, setGivePicks] = useState<string[]>([]);
  const [getPlayers, setGetPlayers] = useState<string[]>([]);
  const [getPicks, setGetPicks] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setGivePlayers([]); setGivePicks([]); setGetPlayers([]); setGetPicks([]); setError(null);
    if (!partner) { setTheirs(EMPTY); return; }
    let cancelled = false;
    fetch(`/api/user-trade-info?partner_team=${encodeURIComponent(partner)}&_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.error) { setError(data.error); return; }
        setMine(data.player_team_assets ?? EMPTY);
        setTheirs(data.partner_team_assets ?? EMPTY);
      })
      .catch(() => { if (!cancelled) setError("The teams' assets could not be loaded."); });
    return () => { cancelled = true; };
  }, [partner]);

  const empty = givePlayers.length + givePicks.length === 0 || getPlayers.length + getPicks.length === 0;

  const propose = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/api/draft/propose_custom_trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          partner,
          user_gives_players: givePlayers,
          user_gives_picks: givePicks,
          user_pick_protections: protections(mine, givePicks),
          cpu_gives_players: getPlayers,
          cpu_gives_picks: getPicks,
          cpu_pick_protections: protections(theirs, getPicks),
        }),
      });
      const data = await response.json();
      if (!response.ok || data.error) { setError(data.error ?? 'The trade did not go through.'); return; }
      onDone(data);
    } catch {
      setError('The server did not answer. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="eos-sheet dr-trade">
      <div className="dr-trade-head">
        <span className="eos-kicker">Draft-night trade</span>
        <select value={partner} onChange={(e) => setPartner(e.target.value)} aria-label="Trade partner">
          <option value="">Choose a team</option>
          {teams.filter((t) => t !== userTeam).map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button type="button" className="btn btn-secondary dr-ink" onClick={onClose}>Back to the board</button>
      </div>
      {error && <p className="eos-error">{error}</p>}
      {partner ? (
        <>
          <div className="tm-grid dr-trade-grid">
            <div className="tm-panel">
              <div className="tm-panel-head">
                <span className="tm-team-name">{userTeam}</span>
                <span className="tm-panel-count">Click a row to offer</span>
              </div>
              <TradeRosterTable assets={mine} accent="you" selectedPlayers={givePlayers} selectedPicks={givePicks}
                onTogglePlayer={(k) => setGivePlayers(toggle(givePlayers, k))} onTogglePick={(k) => setGivePicks(toggle(givePicks, k))} />
            </div>
            <div className="tm-panel">
              <div className="tm-panel-head">
                <span className="tm-team-name">{partner}</span>
                <span className="tm-panel-count">Click a row to ask for</span>
              </div>
              <TradeRosterTable assets={theirs} accent="partner" selectedPlayers={getPlayers} selectedPicks={getPicks}
                onTogglePlayer={(k) => setGetPlayers(toggle(getPlayers, k))} onTogglePick={(k) => setGetPicks(toggle(getPicks, k))} />
            </div>
          </div>
          <div className="dr-trade-deal">
            <p>
              <b>You give:</b> {[...givePlayers, ...givePicks.map((k) => mine.picks.find((p) => p.key === k)?.display_name ?? k)].join(', ') || '—'}
            </p>
            <p>
              <b>You get:</b> {[...getPlayers, ...getPicks.map((k) => theirs.picks.find((p) => p.key === k)?.display_name ?? k)].join(', ') || '—'}
            </p>
            <button type="button" className="btn btn-primary" onClick={propose} disabled={busy || empty}>
              {busy ? 'Sending…' : 'Propose'}
            </button>
          </div>
        </>
      ) : (
        <p className="dr-desk-note">Choose a team to see its roster and picks.</p>
      )}
    </div>
  );
};
