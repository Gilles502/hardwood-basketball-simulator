// Dunk Contest: the dunkers, then each dunk with its score out of 50 and the total, then the final head-to-head
// (with the dunk-off when it ended level).
import React from 'react';
import { NotRecorded, PlayerName, RevealButton, TeamCode, Tiebreak } from './parts';
import { whole, type Dunk, type StageProps } from './types';

const PLACES = ['Winner', 'Runner-up'];

export const DunkStage: React.FC<StageProps & { contest: Dunk | null }> = ({ contest, step, onReveal }) => {
  if (!contest) return <NotRecorded />;
  // The server sends the first round in finishing order: until it is revealed, list the field by name.
  const round1 = step >= 1
    ? contest.round1 ?? []
    : [...(contest.round1 ?? [])].sort((x, y) => x.name.localeCompare(y.name));
  const final = (contest.final ?? []).length > 0
    ? contest.final
    : contest.winner ? [{ name: contest.winner, team: null, dunk: null, score: null, is_user: false }] : [];

  return (
    <>
      <div className="as-kick">First round</div>
      {round1.length === 0 ? <NotRecorded /> : (
        <div className="as-two">
          {round1.map((d, i) => (
            <div key={`${d.name}-${i}`} className={`as-box${d.is_user ? ' is-user' : ''}`}>
              <div className="as-box-title as-dunker"><PlayerName name={d.name} /><TeamCode team={d.team} dot={false} /></div>
              {step >= 1 && (
                <>
                  {(d.dunks ?? []).map((k, j) => (
                    <div key={j} className="as-dunk"><span>{k.name}</span><b>{whole(k.score)}</b></div>
                  ))}
                  <div className="as-dunk is-total">
                    <span className="as-muted">Total</span>
                    <b>{whole(d.total)}{d.finalist ? ' · to the final' : ''}</b>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
      {step < 1 && <div className="as-center"><RevealButton label="Start the contest →" onClick={onReveal} /></div>}
      {step === 1 && <div className="as-center"><RevealButton label="Go to the final →" onClick={onReveal} /></div>}
      {step >= 2 && (
        <>
          <div className="as-kick">Final</div>
          {final.length === 0 ? <NotRecorded /> : (
            <div className="as-fin" style={{ gridTemplateColumns: `repeat(${final.length}, minmax(0, 1fr))` }}>
              {final.map((f, i) => (
                <div key={`${f.name}-${i}`} className={`as-fcard${f.name === contest.winner ? ' is-win' : ''}`}>
                  <div className="as-muted">{PLACES[i] ?? `${i + 1}th`}</div>
                  <PlayerName name={f.name} className={`as-fcard-name${f.is_user ? ' is-user' : ''}`} />
                  {f.dunk && <div className="as-note">{f.dunk}</div>}
                  <div className="as-big">{whole(f.score)}</div>
                </div>
              ))}
            </div>
          )}
          <Tiebreak title="Dunk-off" entries={contest.tiebreak} winner={contest.winner} />
        </>
      )}
    </>
  );
};
