// Phase 5 · Pre-draft trades ("offer cards"): each offer as you give → you get with a value read and its money /
// draft-slot effect; your picks, trade block and the league's wire on the right. Accept / Decline answer the offer
// here, Counter opens the Trade Center. Payload: core/end_season_views.trade_desk_view.
import React, { useCallback, useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { crestHue } from '../../utils/crest';
import type { PhaseProps } from '../../utils/endSeason';

interface OfferPlayer { name: string; ovr: number; position: string; age: number; salary: number }
interface Pick { year?: number | null; round?: number; original?: string; slot?: number | null; label?: string }
interface Offer {
  id: string;
  team: string;
  reason: string | null;
  why?: string | null;
  give: { players: OfferPlayer[]; picks: Pick[] };
  get: { players: OfferPlayer[]; picks: Pick[] };
  value: number | null;
  verdict: 'good' | 'fair' | 'bad' | null;
  summary: string;
}
interface Desk { offers: Offer[]; picks: Pick[]; block: { name: string; position: string; ovr: number; offers: number }[]; wire: string[] }

const money = (v: number) => `$${v.toFixed(1)}M`;
const pickText = (p: Pick) => (p.label ? p.label : `${p.year ?? ''} R${p.round}${p.slot ? ` #${p.slot}` : ''}`.trim());
const VERDICT: Record<string, string> = { good: 'Good for you', fair: 'Fair', bad: 'Bad for you' };
/** Meter position (0-100) for a value share; ±0.3 fills the bar. */
const meterAt = (v: number) => 50 + Math.max(-50, Math.min(50, (v / 0.3) * 50));

export const TradesPhase: React.FC<PhaseProps> = ({ readOnly, onBar, onNavigate, onAdvanced }) => {
  const { leagueData, openPlayerProfile } = useLeagueStore();
  const [desk, setDesk] = useState<Desk | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const hasTeam = Boolean(leagueData?.player_team_name);

  const load = useCallback(() => {
    fetch(`/api/offseason/trade_desk?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data) => setDesk(data && Array.isArray(data.offers) ? data : { offers: [], picks: [], block: [], wire: [] }))
      .catch(() => setDesk({ offers: [], picks: [], block: [], wire: [] }));
  }, []);

  useEffect(() => { if (hasTeam) load(); }, [hasTeam, load]);

  const open = readOnly ? 0 : desk?.offers.length ?? 0;
  useEffect(() => {
    onBar({ nextLabel: 'Close window · Next: Draft →' });
  }, [onBar]);

  const respond = async (offer: Offer, action: 'ACCEPT' | 'DECLINE') => {
    setBusy(offer.id);
    setMessage(null);
    try {
      const response = await fetch('/api/trade-block/respond', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ offer_id: offer.id, action }),
      });
      const data = await response.json();
      if (data.error) throw new Error(data.error);
      setMessage(action === 'ACCEPT' ? `Deal done with ${offer.team}.` : `Offer from ${offer.team} declined.`);
      if (action === 'ACCEPT') await onAdvanced();
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'The offer could not be answered.');
    } finally {
      setBusy(null);
    }
  };

  if (!hasTeam) return <div className="eos-sheet"><p className="eos-muted">Spectator mode: the teams trade among themselves when the window closes.</p></div>;
  if (!desk) return <div className="eos-sheet"><p className="eos-muted">Loading…</p></div>;

  const side = (title: string, s: { players: OfferPlayer[]; picks: Pick[] }) => (
    <div className="td-side">
      <h5>{title}</h5>
      {s.players.length === 0 && s.picks.length === 0 && <div className="eos-muted">Nothing</div>}
      {s.players.map((p) => (
        <div key={p.name}>
          <span><button type="button" className="eos-link" onClick={() => openPlayerProfile(p.name)}>{p.name}</button> · {p.position} · {p.ovr} · {p.age}</span>
          <b>{money(p.salary)}</b>
        </div>
      ))}
      {s.picks.map((p, i) => <div key={i}><span className="td-pick">{pickText(p)}</span>{p.original && <small className="eos-muted">{p.original}</small>}</div>)}
    </div>
  );

  return (
    <div className="td-split">
      <div className="co-col">
        {message && <p className="td-message">{message}</p>}
        {readOnly || desk.offers.length === 0 ? (
          <div className="eos-sheet">
            <p className="eos-muted">{readOnly ? 'The pre-draft window is closed.' : 'No offers on the table. Put players on your trade block to draw some, or build a deal in the Trade Center.'}</p>
            {!readOnly && <button type="button" className="btn btn-secondary eos-cta" onClick={() => onNavigate('trades')}>Open Trade Center</button>}
          </div>
        ) : desk.offers.map((o) => (
          <div key={o.id} className="eos-sheet td-offer">
            <div className="td-top">
              <span className="td-crest" style={{ background: `hsl(${crestHue(o.team)} 58% 38%)` }}>{o.team.split(' ').map((w) => w[0]).join('').slice(0, 3)}</span>
              <b>{o.team}</b>
              {o.why ? <span className="td-why">Why they'd do it: {o.why}</span> : o.reason && <span className="td-why">“{o.reason}”</span>}
            </div>
            <div className="td-sides">{side('You give', o.give)}<div className="td-arrow">→</div>{side('You get', o.get)}</div>
            {o.value != null && o.verdict && (
              <div className="td-meter">
                <span>Value</span>
                <div className="td-bar"><i style={{ left: `${meterAt(o.value)}%` }} /></div>
                <span className={`td-verdict is-${o.verdict}`}><b>{VERDICT[o.verdict]}</b>{o.summary ? ` · ${o.summary}` : ''}</span>
              </div>
            )}
            <div className="td-actions">
              <button type="button" className="btn btn-secondary" onClick={() => onNavigate('trades')} disabled={busy !== null}>Counter in Trade Center</button>
              <button type="button" className="btn btn-secondary" onClick={() => respond(o, 'DECLINE')} disabled={busy !== null}>Decline</button>
              <button type="button" className="btn btn-primary" onClick={() => respond(o, 'ACCEPT')} disabled={busy !== null}>Accept</button>
            </div>
          </div>
        ))}
        {open > 0 && <p className="eos-muted td-hint">{open} offer{open === 1 ? '' : 's'} open · closing the window declines them</p>}
      </div>

      <div className="co-col">
        <section className="rc-card">
          <h3 className="rc-h">Your picks</h3>
          {desk.picks.length === 0 ? <p className="eos-muted">No picks owned.</p> : (
            <ul className="rc-rows">{desk.picks.map((p, i) => (
              <li key={i}><span className="td-pick">{pickText(p)}</span><span className="co-dim">{p.original === leagueData?.player_team_name ? 'own' : `via ${p.original ?? ''}`}</span></li>
            ))}</ul>
          )}
        </section>
        <section className="rc-card">
          <h3 className="rc-h">On your trade block</h3>
          {desk.block.length === 0 ? <p className="eos-muted">Nobody on the block.</p> : (
            <ul className="rc-rows">{desk.block.map((b) => (
              <li key={b.name}><span><b className="dv-ret">{b.name}</b> <small className="co-dim">{b.position} · {b.ovr}</small></span>
                <span className="co-dim">{b.offers ? `${b.offers} offer${b.offers === 1 ? '' : 's'}` : 'none yet'}</span></li>
            ))}</ul>
          )}
          {!readOnly && <button type="button" className="dv-more" onClick={() => onNavigate('trades')}>Edit block in Trade Center →</button>}
        </section>
        <section className="rc-card">
          <h3 className="rc-h">Wire</h3>
          {desk.wire.length === 0 ? <p className="eos-muted">Fills in when you close the window.</p> : (
            <ul className="rc-rows td-wire">{desk.wire.map((w, i) => <li key={i}>{w}</li>)}</ul>
          )}
        </section>
      </div>
    </div>
  );
};
