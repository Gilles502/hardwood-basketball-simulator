// After the last pick: the user's draft class (true ratings — the rookies are on the roster now) and every pick of
// every round. Also what a look back at the Draft phase shows.
import React from 'react';
import { TeamCrest } from '../../../components/TeamCrest';
import { crestLabel } from '../../../utils/crest';
import { normalizeRole } from '../../../utils/roles';
import { overallPick, parseScelta, picksPerRound, tradeLine, type DraftState } from './draftRoom';

interface DraftSummaryProps {
  state: DraftState;
  userTeam: string;
}

export const DraftSummary: React.FC<DraftSummaryProps> = ({ state, userTeam }) => {
  const history = state.history ?? [];
  const perRound = picksPerRound(state);
  const yours = history.filter((h) => h.squadra === userTeam);
  const rounds = [...new Set(history.map((h) => parseScelta(h.scelta).round))];
  const trades = state.trades ?? [];

  return (
    <div className="dr-summary">
      <div className="eos-sheet">
        <span className="eos-kicker">Your draft class</span>
        {yours.length === 0 ? (
          <p className="eos-big-muted">You made no pick in this draft.</p>
        ) : (
          <table className="dr-table">
            <thead>
              <tr><th>Pick</th><th>Player</th><th>OVR</th><th>POT</th><th>From</th><th>Profile</th></tr>
            </thead>
            <tbody>
              {yours.map((h) => (
                <tr key={h.scelta}>
                  <td className="dr-mock">#{overallPick(h.scelta, perRound)}</td>
                  <td>{h.ruolo && <span className="dr-pos">{normalizeRole(h.ruolo)}</span>}<b className="dr-name">{h.nome}</b></td>
                  <td className="dr-val">{h.valutazione ?? '—'}</td>
                  <td className="dr-val">{h.potenziale ?? '—'}</td>
                  <td className="dr-from">{h.provenance ?? ''}</td>
                  <td className="dr-from">{h.pedigree ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {trades.length > 0 && (
          <p className="dr-summary-trades">
            {trades.length} draft-night {trades.length === 1 ? 'trade' : 'trades'} around the league: {trades.map(tradeLine).join(' · ')}.
          </p>
        )}
      </div>

      <div className="eos-sheet">
        <span className="eos-kicker">Every pick</span>
        <div className="dr-results">
          {rounds.map((round) => (
            <section key={round}>
              <h3 className="eos-h3">Round {round}</h3>
              <ol className="dr-results-list">
                {history.filter((h) => parseScelta(h.scelta).round === round).map((h) => (
                  <li key={h.scelta} className={h.squadra === userTeam ? 'is-yours' : undefined}>
                    <i>{overallPick(h.scelta, perRound)}</i>
                    <TeamCrest name={h.squadra} size={20} />
                    <b>{crestLabel(h.squadra)}</b>
                    {h.original_owner && h.original_owner !== h.squadra && <small>via {crestLabel(h.original_owner)}</small>}
                    <span>{h.nome}{h.ruolo ? ` · ${normalizeRole(h.ruolo)}` : ''}</span>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
};
