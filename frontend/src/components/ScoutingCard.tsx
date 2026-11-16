import React, { useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { STOCK_LABELS, cardLook, cardNumber, earnedStocks, liveAwardsOf, splitName } from '../utils/playerCard';
import type { CardStock, LiveAwards } from '../utils/playerCard';
import { computePlayerBadges, computeRatingPillars } from '../utils/playerRatings';
import './ScoutingCard.css';

export interface CardSeasonRow {
  stagione: number;
  squadra: string;
  stats_rs: { ppg: number; rpg: number; apg: number };
}

interface ScoutingCardProps {
  player: any;
  /** Season-by-season rows for the back of the card (newest first). Optional. */
  seasons?: CardSeasonRow[];
  retired?: boolean;
  showStylePicker?: boolean;
  /** false for thumbnails (e.g. the roster grid): a click calls onPlayerClick instead of flipping. */
  flippable?: boolean;
  onPlayerClick?: () => void;
}

const fmt = (n: unknown) => (typeof n === 'number' ? n.toFixed(1) : '-');

function useLiveAwards(player: any): LiveAwards {
  const leagueData = useLeagueStore((state) => state.leagueData);
  return liveAwardsOf(leagueData, player);
}

export const ScoutingCard: React.FC<ScoutingCardProps> = ({ player, seasons = [], retired = false, showStylePicker = false, flippable = true, onPlayerClick }) => {
  const live = useLiveAwards(player);
  const [flipped, setFlipped] = useState(false);
  const [chosen, setChosen] = useState<CardStock | 'auto'>('auto');

  if (!player) return null;

  const look = cardLook(player, live, { retired });
  const stock: CardStock = chosen === 'auto' || !earnedStocks(look).includes(chosen) ? look.stock : chosen;
  const [first, last] = splitName(player.nome);
  // Long names shrink so each word stays on one line ("WEMBANYAMA", not "WEMBANYA / MA"); 38px is the CSS default.
  const longest = Math.max(first?.length ?? 0, last?.length ?? 0);
  const nameSize = longest <= 8 ? undefined : longest <= 10 ? 28 : longest <= 12 ? 24 : 21;
  const pillars = computeRatingPillars(player);
  const badges = computePlayerBadges(player);
  const stats = player.stats_rs || player.stats || {};
  const playedSeasons = seasons.filter((season) => season.stats_rs && (season.stats_rs.ppg || season.stats_rs.rpg || season.stats_rs.apg));
  const hasStats = [stats.ppg, stats.rpg, stats.apg].some((value) => typeof value === 'number' && value > 0);
  const ovr = player.ovr || 75;
  const pot = player.potenziale || ovr;
  const team = player.squadra || 'Free Agent';
  const isGoatStock = stock === 'black';

  const activate = () => {
    if (flippable) setFlipped((value) => !value);
    else onPlayerClick?.();
  };

  return (
    <div className="sc-wrap">
      <div
        className={`sc-flip${flipped ? ' is-flipped' : ''}`}
        role="button"
        tabIndex={0}
        aria-label={!flippable ? `Open ${player.nome}'s profile` : flipped ? `Show the front of ${player.nome}'s card` : `Flip ${player.nome}'s card`}
        onClick={activate}
        onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } }}
      >
        <div className="sc-inner">
          {/* Front */}
          <div className={`sc-card sc-stock-${stock} sc-face`}>
            {(stock === 'gold' || isGoatStock) && <div className="sc-foil" />}
            <div className="sc-band"><span>Scouting report</span><span>No. {cardNumber(player.nome)}</span></div>
            <div className="sc-body">
              <div className="sc-idrow">
                <div className="sc-name" style={nameSize ? { fontSize: nameSize } : undefined}>{first && <>{first}<br /></>}{last}</div>
                <div className="sc-ovr"><b>{ovr}</b><span>OVERALL</span></div>
              </div>
              <div className="sc-sub">{[player.ruolo, player.eta ? `Age ${player.eta}` : null, team].filter(Boolean).join(' · ')}</div>
              <div className="sc-bars">
                {pillars.map((pillar) => (
                  <div key={pillar.label}>
                    <span>{pillar.label}</span>
                    <span className="sc-track"><i className={pillar.value >= 85 ? 'is-hi' : ''} style={{ width: `${pillar.value}%` }} /></span>
                    <em>{pillar.value}</em>
                  </div>
                ))}
              </div>
            </div>
            <div className="sc-marks">
              {look.shown.map((seal) => (
                <div key={seal.id} className={`sc-seal${seal.label.length > 4 ? ' is-long' : ''}`} title={`${seal.label} x${seal.count}`}>
                  <b>{seal.label}</b>
                  {seal.count > 1 && <span>x{seal.count}</span>}
                </div>
              ))}
              {look.more > 0 && <span className="sc-more" title="More honours on the back and in the Awards tab">+{look.more}</span>}
              <span className="sc-spacer" />
              <div className={`sc-stamp${retired ? ' is-retired' : ''}`}>{look.stamp}</div>
            </div>
            <div className="sc-foot">
              <span>{hasStats ? `${fmt(stats.ppg)} PPG · ${fmt(stats.rpg)} RPG · ${fmt(stats.apg)} APG` : 'No games yet'}</span>
              <span>POT {pot}</span>
            </div>
          </div>

          {/* Back */}
          <div className={`sc-card sc-stock-${stock} sc-face sc-back`}>
            {(stock === 'gold' || isGoatStock) && <div className="sc-foil" />}
            <div className="sc-band"><span>Career file</span><span>No. {cardNumber(player.nome)}</span></div>
            <div className="sc-body">
              <div className="sc-back-title">{player.nome}</div>
              <div className="sc-sub">{team}{player.contratto ? ` · ${player.contratto}` : ''}</div>
              <div className="sc-section">Recent seasons</div>
              {playedSeasons.length === 0 ? (
                <div className="sc-empty">No season history yet.</div>
              ) : (
                <table className="sc-table">
                  <thead><tr><th>Year</th><th>Team</th><th>PPG</th><th>RPG</th><th>APG</th></tr></thead>
                  <tbody>
                    {playedSeasons.slice(0, 5).map((season) => (
                      <tr key={season.stagione}>
                        <td>S{season.stagione}</td>
                        <td title={season.squadra}>{season.squadra}</td>
                        <td>{fmt(season.stats_rs?.ppg)}</td>
                        <td>{fmt(season.stats_rs?.rpg)}</td>
                        <td>{fmt(season.stats_rs?.apg)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="sc-section">Honours</div>
              <div className="sc-honours">
                {look.seals.length === 0 ? 'None yet' : look.seals.map((seal) => `${seal.name} x${seal.count}`).join(' · ')}
              </div>
              <div className="sc-section">Badges</div>
              <div className="sc-badges">
                {badges.length === 0 ? <span className="sc-empty">None yet</span> : badges.slice(0, 6).map((badge) => (
                  <span key={badge.id + badge.name} className={`sc-badge is-${badge.tier}`}>{badge.name}</span>
                ))}
              </div>
            </div>
            <div className="sc-foot"><span>Click to flip back</span><span>{look.stamp}</span></div>
          </div>
        </div>
      </div>

      {showStylePicker && earnedStocks(look).length > 1 && (
        <label className="sc-picker">
          <span>Paper</span>
          <select value={chosen === 'auto' ? 'auto' : stock} onChange={(event) => setChosen(event.target.value as CardStock | 'auto')}>
            <option value="auto">Auto ({STOCK_LABELS[look.stock]})</option>
            {earnedStocks(look).map((option) => (
              <option key={option} value={option}>{STOCK_LABELS[option]}</option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
};
