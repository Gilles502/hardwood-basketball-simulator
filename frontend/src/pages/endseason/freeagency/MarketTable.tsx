// The free-agent list: every player still on the market (or only those with the user's offer). A row opens in
// place; what the open row shows (offers + why, or the offer sheet) comes from the parent through renderOpen.
import React, { useMemo, useState } from 'react';
import { normalizeRole } from '../../../utils/roles';
import { chanceOf, isBiddingWar, money, type FaPlayer } from './freeAgency';

type SortKey = 'ovr' | 'eta' | 'ask' | 'offers';

interface MarketTableProps {
  players: FaPlayer[];
  userTeam: string;
  position: string;
  search: string;
  open: string | null;
  onOpen: (name: string | null) => void;
  onFocus: (player: FaPlayer | null) => void;
  onOffer: (player: FaPlayer) => void;
  onWithdraw?: (player: FaPlayer) => void;
  renderOpen: (player: FaPlayer) => React.ReactNode;
  empty: string;
}

const COLUMNS: { key: SortKey | null; label: string }[] = [
  { key: null, label: 'Player' }, { key: 'ovr', label: 'OVR/POT' }, { key: 'eta', label: 'Age' }, { key: 'ask', label: 'Asks' },
  { key: null, label: 'Your chance' }, { key: 'offers', label: 'Offers' }, { key: null, label: '' },
];

const offersLine = (p: FaPlayer, userTeam: string) => {
  const n = p.race.offers.length;
  if (n === 0) return '0';
  const yours = p.race.offers.some((o) => o.team === userTeam);
  if (yours) return n === 1 ? '1 · only you' : `${n} · you + ${n - 1}`;
  return `${n} · ${p.race.leader} lead (${Math.round(p.race.leader_score)})`;
};

export const MarketTable: React.FC<MarketTableProps> = ({
  players, userTeam, position, search, open, onOpen, onFocus, onOffer, onWithdraw, renderOpen, empty,
}) => {
  const [sortKey, setSortKey] = useState<SortKey>('ovr');
  const [desc, setDesc] = useState(true);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const value = (p: FaPlayer) => (sortKey === 'offers' ? p.race.offers.length : p[sortKey]);
    return players
      .filter((p) => position === 'ALL' || normalizeRole(p.ruolo) === position)
      .filter((p) => !q || p.nome.toLowerCase().includes(q))
      .sort((a, b) => (desc ? value(b) - value(a) : value(a) - value(b)));
  }, [players, position, search, sortKey, desc]);

  const sortBy = (key: SortKey) => {
    if (key === sortKey) setDesc(!desc);
    else { setSortKey(key); setDesc(key !== 'eta'); }
  };

  return (
    <table className="fa-table" onMouseLeave={() => onFocus(null)}>
      <thead>
        <tr>
          {COLUMNS.map((c, i) => (
            <th key={i} aria-sort={c.key && c.key === sortKey ? (desc ? 'descending' : 'ascending') : undefined}>
              {c.key ? (
                <button type="button" onClick={() => sortBy(c.key as SortKey)}>
                  {c.label}{c.key === sortKey ? (desc ? ' ▾' : ' ▴') : ''}
                </button>
              ) : c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && <tr><td colSpan={7} className="fa-empty">{empty}</td></tr>}
        {/* The market can hold two players with the same name (a known pool bug), so rows are keyed by position too */}
        {rows.map((p, i) => {
          const isOpen = open === p.nome;
          const chance = chanceOf(p.race, userTeam);
          return (
            <React.Fragment key={`${p.nome}-${i}`}>
              <tr className={`fa-row${isOpen ? ' is-open' : ''}`} onClick={() => onOpen(isOpen ? null : p.nome)} onMouseEnter={() => onFocus(p)}>
                <td>
                  <span className="fa-pos">{normalizeRole(p.ruolo)}</span>
                  <b>{p.nome}</b>
                  {p.has_bird_rights && <em className="fa-tag">Bird rights</em>}
                  {p.is_rfa && <em className="fa-tag">RFA</em>}
                  {isBiddingWar(p.race) && <em className="fa-tag is-hot">Bidding war</em>}
                </td>
                <td className="fa-num"><b>{p.ovr}</b>/{p.potenziale}</td>
                <td className="fa-num">{p.eta}</td>
                <td className="fa-num">{money(p.ask)}</td>
                <td><span className={`fa-chance is-${chance.replace(' ', '-').toLowerCase()}`}>{chance}</span></td>
                <td>{offersLine(p, userTeam)}</td>
                <td className="fa-act">
                  {onWithdraw && p.active_user_offer && (
                    <button type="button" className="btn btn-secondary fa-ink" onClick={(e) => { e.stopPropagation(); onWithdraw(p); }}>Withdraw</button>
                  )}
                  <button
                    type="button"
                    className={`btn ${p.active_user_offer ? 'btn-secondary fa-ink' : 'btn-primary'}`}
                    onClick={(e) => { e.stopPropagation(); onOffer(p); }}
                  >
                    {p.active_user_offer ? 'Change offer' : 'Offer'}
                  </button>
                </td>
              </tr>
              {isOpen && (
                <tr className="fa-open"><td colSpan={7}>{renderOpen(p)}</td></tr>
              )}
            </React.Fragment>
          );
        })}
      </tbody>
    </table>
  );
};
