import React from 'react';
import { RefreshCw } from 'lucide-react';
import { TeamCrest } from '../../components/TeamCrest';
import { normalizeRole } from '../../utils/roles';
import type { PlayerDetails } from '../../store/leagueStore';
import type { TradeBlockOffer } from './types';

interface TradeBlockPanelProps {
  roster: PlayerDetails[];
  offers: TradeBlockOffer[];
  loading: boolean;
  onToggle: (playerName: string) => void;
  onGenerate: () => void;
  onRespond: (offerId: string, action: 'ACCEPT' | 'DECLINE') => void;
}

const STAMP: Record<string, { label: string; tone: 'ok' | 'mid' | 'low' }> = {
  High: { label: 'Likely', tone: 'ok' },
  Medium: { label: 'Possible', tone: 'mid' },
  Low: { label: 'Long shot', tone: 'low' },
};

const money = (millions: number): string => `$${millions.toFixed(1)}M`;

export const TradeBlockPanel: React.FC<TradeBlockPanelProps> = ({ roster, offers, loading, onToggle, onGenerate, onRespond }) => {
  const sorted = [...roster].sort((a, b) => b.ovr - a.ovr);
  const onBlock = roster.filter((p) => p.on_trade_block).length;

  return (
    <div className="tb-root">
      <div className="tb-stats">
        <div className="tb-stat"><span>On the block</span><b className="is-hot">{onBlock}</b></div>
        <div className="tb-stat"><span>Offers waiting</span><b>{offers.length}</b></div>
        <div className="tb-stat tb-stat-action">
          <div><span>Shop your block</span><small>Ask the league for new offers</small></div>
          <button type="button" className="tm-btn is-primary" onClick={onGenerate} disabled={loading}>
            <RefreshCw size={15} className={loading ? 'spinner' : ''} /> Generate offers
          </button>
        </div>
      </div>

      <div className="tb-layout">
        <div className="tm-panel">
          <div className="tm-panel-head"><span className="tm-team-name">My roster</span><span className="tm-panel-count">Flip a switch to put a player up for sale</span></div>
          <div className="tb-roster">
            {sorted.map((p) => (
              <div key={p.id} className={`tb-player${p.on_trade_block ? ' is-sale' : ''}`}>
                <span className="tm-pos">{normalizeRole(p.ruolo)}</span>
                <div className="tb-player-info">
                  <b>{p.nome}</b>
                  {p.on_trade_block && <span className="tb-tag">For sale</span>}
                  <div>{p.eta} yrs · {p.contratto}</div>
                </div>
                <span className="tm-ovr">{p.ovr}</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={p.on_trade_block}
                  aria-label={`${p.nome} on the trade block`}
                  className={`tb-switch${p.on_trade_block ? ' is-on' : ''}`}
                  onClick={() => onToggle(p.nome)}
                />
              </div>
            ))}
            {sorted.length === 0 && <p className="tm-hint">No players on your roster.</p>}
          </div>
        </div>

        <div className="tb-offers">
          {loading ? (
            <div className="tb-empty"><div className="spinner" /></div>
          ) : offers.length === 0 ? (
            <div className="tm-empty">No offers yet. Put players on the block and press Generate offers.</div>
          ) : (
            offers.map((offer, idx) => {
              const stamp = offer.likelihood ? STAMP[offer.likelihood] : undefined;
              const note = offer.why ? `Why they'd do it: ${offer.why}` : (offer.strategic_assessment || offer.reason);
              return (
                <article className="os-sheet" key={offer.id}>
                  <div className="os-band">
                    <span><TeamCrest name={offer.offering_team} size={24} />Offer · {offer.offering_team}</span>
                    <span>No. {String(idx + 1).padStart(4, '0')}</span>
                  </div>
                  <div className="os-body">
                    <div>
                      <div className="os-sub">You receive</div>
                      {offer.giving_players.map((p, i) => (
                        <div className="os-line" key={`g${i}`}>{p.name} <small>{normalizeRole(p.position)} · {p.ovr} · {money(p.salary)}</small></div>
                      ))}
                      {offer.giving_picks.map((pk, i) => <div className="os-line" key={`gp${i}`}>{pk} <small>pick</small></div>)}
                    </div>
                    <div>
                      <div className="os-sub">You send</div>
                      {offer.receiving_players.map((p, i) => (
                        <div className="os-line" key={`r${i}`}>{p.name} <small>{normalizeRole(p.position)} · {p.ovr} · {money(p.salary)}</small></div>
                      ))}
                      {offer.receiving_picks.map((pk, i) => <div className="os-line" key={`rp${i}`}>{pk} <small>pick</small></div>)}
                    </div>
                  </div>
                  {stamp && <div className={`os-stamp is-${stamp.tone}`}>{stamp.label}</div>}
                  <div className="os-foot">
                    <span className="os-note">{note ? `“${note}”` : ''}</span>
                    <button type="button" className="os-btn" onClick={() => onRespond(offer.id, 'DECLINE')}>Decline</button>
                    <button type="button" className="os-btn is-primary" onClick={() => onRespond(offer.id, 'ACCEPT')}>Accept</button>
                  </div>
                </article>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
