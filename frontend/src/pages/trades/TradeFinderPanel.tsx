import React from 'react';
import { DollarSign, Target } from 'lucide-react';
import { BoardingPass } from './BoardingPass';
import { TradeRosterTable } from './TradeRosterTable';
import type { PickAsset, PlayerAsset, TradeOffer } from './types';

export type FinderFilter = 'all' | '2-team' | '3-team' | 'multi-team';

interface TradeFinderPanelProps {
  userTeam: string;
  players: PlayerAsset[];
  picks: PickAsset[];
  selectedPlayers: string[];
  selectedPicks: string[];
  onTogglePlayer: (name: string) => void;
  onTogglePick: (key: string) => void;
  onClear: () => void;
  onFind: () => void;
  onOpenAskingPrice: () => void;
  loading: boolean;

  targetRole: string;
  onTargetRole: (role: string) => void;
  minOvr: number;
  onMinOvr: (ovr: number) => void;
  onSearchByNeed: () => void;
  needLoading: boolean;

  offers: TradeOffer[];
  filter: FinderFilter;
  onFilter: (mode: FinderFilter) => void;
  onAccept: (offer: TradeOffer) => void;
  onOpen: (offer: TradeOffer) => void;
}

const ROLES = ['PG', 'SG', 'SF', 'PF', 'C'];

const isThree = (o: TradeOffer): boolean => o.trade_type === '3-team';
const isChain = (o: TradeOffer): boolean => o.trade_type === 'multi-team';

export const TradeFinderPanel: React.FC<TradeFinderPanelProps> = ({
  userTeam, players, picks, selectedPlayers, selectedPicks, onTogglePlayer, onTogglePick, onClear, onFind, onOpenAskingPrice, loading,
  targetRole, onTargetRole, minOvr, onMinOvr, onSearchByNeed, needLoading,
  offers, filter, onFilter, onAccept, onOpen,
}) => {
  const hasPackage = selectedPlayers.length + selectedPicks.length > 0;
  const packageSalary = players.filter((p) => selectedPlayers.includes(p.name)).reduce((sum, p) => sum + p.salary, 0);

  const counts = {
    all: offers.length,
    '2-team': offers.filter((o) => !isThree(o) && !isChain(o)).length,
    '3-team': offers.filter(isThree).length,
    'multi-team': offers.filter(isChain).length,
  };
  const shown = offers.filter((o) => {
    if (filter === '2-team') return !isThree(o) && !isChain(o);
    if (filter === '3-team') return isThree(o);
    if (filter === 'multi-team') return isChain(o);
    return true;
  });

  const pills: { id: FinderFilter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: '2-team', label: 'Direct' },
    { id: '3-team', label: 'Connecting' },
    { id: 'multi-team', label: 'Chains' },
  ];

  return (
    <div className="tf-layout">
      {/* Tray */}
      <div className="tf-tray">
        <div className="tm-panel tf-package">
          <div className="tm-team-label">Your package</div>
          <div className="tf-chips">
            {selectedPlayers.map((name) => {
              const p = players.find((x) => x.name === name);
              return (
                <span className="tm-chip" key={name}>
                  {name}{p && <small>${p.salary.toFixed(1)}M</small>}
                  <button type="button" aria-label={`Remove ${name}`} onClick={() => onTogglePlayer(name)}>×</button>
                </span>
              );
            })}
            {selectedPicks.map((key) => (
              <span className="tm-chip" key={key}>
                {picks.find((x) => x.key === key)?.display_name || key}
                <button type="button" aria-label={`Remove ${key}`} onClick={() => onTogglePick(key)}>×</button>
              </span>
            ))}
            {!hasPackage && <p className="tm-hint">Click players or picks below to build a package.</p>}
          </div>
          {hasPackage && (
            <div className="tf-total">{selectedPlayers.length} players · {selectedPicks.length} picks · ${packageSalary.toFixed(1)}M</div>
          )}
          <button type="button" className="tm-btn is-primary tf-find" onClick={onFind} disabled={!hasPackage || loading}>
            {loading ? 'Searching...' : 'Find offers'}
          </button>
          <div className="tf-row">
            <button type="button" className="tm-btn" onClick={onOpenAskingPrice}><DollarSign size={15} /> Asking price</button>
            {hasPackage && <button type="button" className="tm-btn" onClick={onClear}>Clear</button>}
          </div>
        </div>

        <div className="tm-panel tf-need">
          <div className="tm-team-label">Looking for a… (optional)</div>
          <div className="tf-pills">
            <button type="button" className={`tf-pill${targetRole === 'all' ? ' is-on' : ''}`} onClick={() => onTargetRole('all')}>Any</button>
            {ROLES.map((r) => (
              <button type="button" key={r} className={`tf-pill${targetRole === r ? ' is-on' : ''}`} onClick={() => onTargetRole(r)}>{r}</button>
            ))}
          </div>
          <label className="tf-ovr">
            <span>Minimum OVR</span>
            <b>{minOvr}</b>
            <input type="range" min={70} max={99} value={minOvr} onChange={(e) => onMinOvr(parseInt(e.target.value, 10) || 70)} />
          </label>
          {targetRole !== 'all' && (
            <button type="button" className="tm-btn" onClick={onSearchByNeed} disabled={needLoading}>
              <Target size={15} /> {needLoading ? 'Searching...' : `Search the league for a ${targetRole}`}
            </button>
          )}
        </div>

        <div className="tm-panel">
          <div className="tm-panel-head"><span className="tm-team-label">Your assets</span><span className="tm-panel-count">Click to add</span></div>
          <TradeRosterTable
            compact
            assets={{ players, picks }}
            accent="you"
            selectedPlayers={selectedPlayers}
            selectedPicks={selectedPicks}
            onTogglePlayer={onTogglePlayer}
            onTogglePick={onTogglePick}
          />
        </div>
      </div>

      {/* Results */}
      <div className="tf-results">
        {offers.length > 0 && (
          <div className="tf-bar">
            <div className="tf-pills" role="group" aria-label="Trade type">
              {pills.map((pill) => (
                <button type="button" key={pill.id} className={`tf-pill${filter === pill.id ? ' is-on' : ''}`} aria-pressed={filter === pill.id} onClick={() => onFilter(pill.id)}>
                  {pill.label} · {counts[pill.id]}
                </button>
              ))}
            </div>
            <span className="tm-panel-count">Best match first</span>
          </div>
        )}

        {loading ? (
          <div className="tm-empty"><div className="spinner" /></div>
        ) : offers.length > 0 ? (
          shown.length > 0
            ? shown.map((offer, idx) => (
                <BoardingPass
                  key={idx}
                  offer={offer}
                  userTeam={userTeam}
                  onAccept={() => onAccept(offer)}
                  onOpen={isChain(offer) ? undefined : () => onOpen(offer)}
                />
              ))
            : <div className="tm-empty">No proposals of this type. Try "All".</div>
        ) : hasPackage ? (
          <div className="tm-empty">No offers for this package yet. Press Find offers, or add a pick or another player.</div>
        ) : (
          <div className="tm-empty">Build a package on the left to see which franchises want to talk.</div>
        )}
      </div>
    </div>
  );
};
