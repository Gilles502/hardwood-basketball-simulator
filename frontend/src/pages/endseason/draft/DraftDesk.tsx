// "Your desk": on the user's turn the CPU offers for the pick, each with Accept / Decline, and the way into the
// in-page trade panel. Declining only hides the offer here; making the pick lets the rest lapse.
import React, { useEffect, useState } from 'react';
import { normalizeRole } from '../../../utils/roles';
import type { DraftState } from './draftRoom';

interface OfferPlayer {
  nome: string;
  ruolo: string;
  ovr: number;
  eta: number;
  salario: number;
  anni_contratto: number;
}

interface DraftOffer {
  id: string;
  partner: string;
  type: string;
  description: string;
  why?: string;
  gives_players_info: OfferPlayer[];
}

interface DraftDeskProps {
  state: DraftState;
  busy: boolean;
  onAccept: (offerId: string) => void;
  onBuildTrade: () => void;
}

export const DraftDesk: React.FC<DraftDeskProps> = ({ state, busy, onAccept, onBuildTrade }) => {
  const [offers, setOffers] = useState<DraftOffer[]>([]);
  const [declined, setDeclined] = useState<string[]>([]);
  const yourTurn = !!state.is_user_turn;
  const pick = state.pick_corrente ?? 0;

  useEffect(() => {
    setDeclined([]);
    if (!yourTurn) { setOffers([]); return; }
    let cancelled = false;
    fetch(`/api/draft/cpu_offers?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data) => { if (!cancelled) setOffers(Array.isArray(data) ? data : []); })
      .catch(() => { if (!cancelled) setOffers([]); });
    return () => { cancelled = true; };
  }, [yourTurn, pick]);

  const open = offers.filter((o) => !declined.includes(o.id));

  return (
    <div className="eos-sheet dr-deskcard">
      <span className="eos-kicker">
        Your desk{yourTurn && open.length > 0 ? ` · ${open.length} ${open.length === 1 ? 'offer' : 'offers'} for #${pick + 1}` : ''}
      </span>
      {yourTurn ? (
        open.length === 0 ? (
          <p className="dr-desk-note">No offers on the table for this pick.</p>
        ) : (
          <ul className="dr-offers">
            {open.map((o) => (
              <li key={o.id} className="dr-offer">
                <b className="dr-offer-team">{o.partner}</b>
                <p>{o.description.replace(/\*\*/g, '')}</p>
                {o.why && <p className="dr-offer-player">Why they'd do it: {o.why}</p>}
                {o.gives_players_info.map((p) => (
                  <p key={p.nome} className="dr-offer-player">
                    {p.nome} · {normalizeRole(p.ruolo)} · {p.eta} · {p.ovr} OVR · ${p.salario.toFixed(1)}M × {p.anni_contratto}
                  </p>
                ))}
                <div className="dr-offer-actions">
                  <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onAccept(o.id)}>Accept</button>
                  <button type="button" className="btn btn-secondary dr-ink" onClick={() => setDeclined([...declined, o.id])}>Decline</button>
                </div>
              </li>
            ))}
          </ul>
        )
      ) : (
        <p className="dr-desk-note">Offers for your pick arrive when you are on the clock.</p>
      )}
      <button type="button" className="btn btn-secondary dr-ink dr-build" onClick={onBuildTrade} disabled={busy}>
        Build my own trade
      </button>
    </div>
  );
};
