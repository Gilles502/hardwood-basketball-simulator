// 3-Point Contest: the shooters, then the first round (score bars out of 30, finalists tagged), then the final
// (with the shoot-off when the final ended level).
import React from 'react';
import { NotRecorded, PlayerName, RevealButton, Tiebreak } from './parts';
import { one, whole, type StageProps, type ThreePoint } from './types';

const MAX_SCORE = 30;
const PLACES = ['Winner', '2nd', '3rd'];

export const ThreePointStage: React.FC<StageProps & { contest: ThreePoint | null }> = ({ contest, step, onReveal }) => {
  if (!contest) return <NotRecorded />;
  // The server sends the first round in finishing order: until it is revealed, list the field by name.
  const round1 = step >= 1
    ? contest.round1 ?? []
    : [...(contest.round1 ?? [])].sort((x, y) => x.name.localeCompare(y.name));
  const final = (contest.final ?? []).length > 0
    ? contest.final
    : contest.winner ? [{ name: contest.winner, team: null, score: null, is_user: false }] : [];

  return (
    <>
      <div className="as-box">
        <div className="as-kick">First round</div>
        {round1.length === 0 ? <NotRecorded /> : round1.map((s, i) => {
          const shown = step >= 1;
          const width = shown && s.score !== null ? Math.min(100, Math.max(0, (s.score / MAX_SCORE) * 100)) : 0;
          return (
            <div key={`${s.name}-${i}`} className={`as-bar-row${s.is_user ? ' is-user' : ''}`}>
              <span className="as-bar-name">
                <PlayerName name={s.name} />
                {s.tp_pct !== null && s.tp_pct !== undefined && <span className="as-muted"> {one(s.tp_pct)}%</span>}
                {shown && s.finalist && <span className="as-tag">Final</span>}
              </span>
              <div className={`as-bar${shown && s.finalist ? ' is-final' : ''}`}><i style={{ width: `${width}%` }} /></div>
              <b>{shown ? whole(s.score) : ''}</b>
            </div>
          );
        })}
        {step < 1 && <div className="as-center"><RevealButton label="Start the first round →" onClick={onReveal} /></div>}
      </div>

      {step === 1 && <div className="as-center"><RevealButton label="Shoot the final →" onClick={onReveal} /></div>}
      {step >= 2 && (final.length === 0 ? <NotRecorded what="Final" /> : (
        <div className="as-fin" style={{ gridTemplateColumns: `repeat(${final.length}, minmax(0, 1fr))` }}>
          {final.map((f, i) => (
            <div key={`${f.name}-${i}`} className={`as-fcard${f.name === contest.winner ? ' is-win' : ''}`}>
              <div className="as-muted">{PLACES[i] ?? `${i + 1}th`}</div>
              <PlayerName name={f.name} className={`as-fcard-name${f.is_user ? ' is-user' : ''}`} />
              <div className="as-big">{whole(f.score)}</div>
            </div>
          ))}
        </div>
      ))}
      {step >= 2 && <Tiebreak title="Shoot-off" entries={contest.tiebreak} winner={contest.winner} />}
    </>
  );
};
