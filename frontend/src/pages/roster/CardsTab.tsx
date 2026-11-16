import React, { useMemo, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import type { PlayerDetails } from '../../store/leagueStore';
import { ScoutingCard } from '../../components/ScoutingCard';
import { STOCK_LABELS, cardLook, liveAwardsOf } from '../../utils/playerCard';
import type { CardLook, CardStock } from '../../utils/playerCard';
import { normalizeRole } from '../../utils/roles';

type Filter = 'all' | 'awards' | 'champions' | 'allstars' | 'young';
type View = 'cards' | 'checklist';

interface CardsTabProps {
  teamName: string;
  roster: PlayerDetails[];
  onOpenPlayer: (name: string) => void;
}

const YOUNG_MAX_AGE = 23;

const FILTERS: { id: Filter; label: string; test: (p: PlayerDetails, look: CardLook) => boolean }[] = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'awards', label: 'Award winners', test: (_, { counts: c }) => c.mvp + c.finalsMvp + c.dpoy > 0 || c.roy },
  { id: 'champions', label: 'Champions', test: (_, { counts }) => counts.rings > 0 },
  { id: 'allstars', label: 'All-Star picks', test: (_, { counts }) => counts.allStar > 0 },
  { id: 'young', label: `Young (${YOUNG_MAX_AGE} and under)`, test: (p) => (p.eta ?? 99) <= YOUNG_MAX_AGE },
];

/** Album sections follow the card paper, so a section and the cards in it always agree. */
const GROUPS: { title: string; stocks: CardStock[] }[] = [
  { title: 'Hall of fame', stocks: ['black'] },
  { title: 'Superstars', stocks: ['gold'] },
  { title: 'All-Stars', stocks: ['cream'] },
  { title: 'Starters', stocks: ['cream_copper', 'pewter'] },
  { title: 'Prospects & role players', stocks: ['kraft'] },
];

const honoursOf = (look: CardLook) =>
  look.seals.map((seal) => `${seal.name}${seal.count > 1 ? ` ×${seal.count}` : ''}`).join(' · ') || '–';

export const CardsTab: React.FC<CardsTabProps> = ({ teamName, roster, onOpenPlayer }) => {
  const leagueData = useLeagueStore((state) => state.leagueData);
  const [filter, setFilter] = useState<Filter>('all');
  const [view, setView] = useState<View>('cards');

  const entries = useMemo(
    () => roster
      .map((player) => ({ player, look: cardLook(player, liveAwardsOf(leagueData, player), {}) }))
      .sort((a, b) => (b.player.ovr || 0) - (a.player.ovr || 0)),
    [roster, leagueData],
  );

  const active = FILTERS.find((f) => f.id === filter) ?? FILTERS[0];
  const shown = entries.filter(({ player, look }) => active.test(player, look));

  return (
    <div className="pc-root">
      <div className="pc-bar">
        <div className="pc-chips" role="group" aria-label="Filter cards">
          {FILTERS.map((f) => (
            <button key={f.id} type="button" className="pc-chip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
              {f.label}<i>{entries.filter(({ player, look }) => f.test(player, look)).length}</i>
            </button>
          ))}
        </div>
        <div className="rc-seg" role="group" aria-label="View">
          <button type="button" aria-pressed={view === 'cards'} onClick={() => setView('cards')}>Cards</button>
          <button type="button" aria-pressed={view === 'checklist'} onClick={() => setView('checklist')}>Checklist</button>
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="st-state">No {teamName} player matches “{active.label}”.</div>
      ) : view === 'cards' ? (
        <div className="pc-groups">
          {GROUPS.map((group) => {
            const cards = shown.filter(({ look }) => group.stocks.includes(look.stock));
            if (cards.length === 0) return null;
            return (
              <section key={group.title} className="pc-group" aria-label={group.title}>
                <div className="pc-divider"><b>{group.title}</b><span>{cards.length} card{cards.length === 1 ? '' : 's'}</span></div>
                <div className="pc-row">
                  {cards.map(({ player }) => (
                    <div key={player.nome} className="pc-card">
                      <ScoutingCard player={player} flippable={false} onPlayerClick={() => onOpenPlayer(player.nome)} />
                    </div>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <div className="pc-checklist">
          <div className="pc-checklist-band"><span>Team checklist · {teamName}</span><span>{shown.length} card{shown.length === 1 ? '' : 's'}</span></div>
          <table>
            <thead>
              <tr>
                <th aria-label="Paper" />
                <th>Player</th><th>Pos</th><th>Age</th><th>Honours</th><th>Stamp</th><th>OVR</th><th>POT</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(({ player, look }) => (
                <tr key={player.nome}>
                  <td><span className={`pc-swatch is-${look.stock}`} title={STOCK_LABELS[look.stock]} /></td>
                  <td><button type="button" className="pc-name" onClick={() => onOpenPlayer(player.nome)}>{player.nome}</button></td>
                  <td>{normalizeRole(player.ruolo)}</td>
                  <td>{player.eta}</td>
                  <td>{honoursOf(look)}</td>
                  <td><span className="pc-stamp">{look.stamp}</span></td>
                  <td className="pc-ovr">{player.ovr}</td>
                  <td className="pc-pot">{player.potenziale ?? player.ovr}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
