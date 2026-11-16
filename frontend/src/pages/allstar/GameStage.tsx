// One stage for both exhibition games (Rookie Challenge, All-Star Game): before tip-off the two rosters,
// then the final score, the MVP spotlight and a box score per side (PTS / REB / AST / 3PM; minutes are not tracked).
import React from 'react';
import { NotRecorded, PlayerName, RevealButton } from './parts';
import { SeasonTable } from './SelectionsStage';
import { whole, type BoxLine, type Game, type Mvp, type SeasonLine, type StageProps } from './types';

interface Props extends StageProps {
  game: Game | null;
  mvpTitle: string;
  /** The two rosters shown before tip-off; `label` also names the side in the "?" score. */
  rosters: { label: string; kick: string; lines: SeasonLine[] }[];
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();

const Spotlight: React.FC<{ mvp: Mvp; title: string }> = ({ mvp, title }) => {
  const stats = mvp.pts === null || mvp.pts === undefined
    ? ''
    : [`${whole(mvp.pts)} pts`, `${whole(mvp.reb)} reb`, `${whole(mvp.ast)} ast`, `${whole(mvp.tpm)} 3PM`].join(' · ');
  const line = [stats, mvp.fact].filter(Boolean).join(' — ');
  return (
    <div className={`as-spot${mvp.is_user ? ' is-user' : ''}`}>
      <div className="as-av" aria-hidden="true">{initials(mvp.name)}</div>
      <div className="as-spot-text">
        <div className="as-muted">{title}</div>
        <PlayerName name={mvp.name} className="as-spot-name" />
        {line && <div className="as-note">{line}</div>}
      </div>
    </div>
  );
};

const BoxScore: React.FC<{ label: string; lines: BoxLine[] }> = ({ label, lines }) => (
  <div className="as-box">
    <div className="as-kick">{label}</div>
    {lines.length === 0 ? <NotRecorded /> : (
      <table className="as-table">
        <colgroup><col /><col className="as-c-n" /><col className="as-c-n" /><col className="as-c-n" /><col className="as-c-n" /></colgroup>
        <thead><tr><th>Player</th><th>PTS</th><th>REB</th><th>AST</th><th>3PM</th></tr></thead>
        <tbody>
          {lines.map((p, i) => (
            <tr key={`${p.name}-${i}`} className={p.is_user ? 'is-user' : undefined}>
              <td className="as-player"><PlayerName name={p.name} /></td>
              <td>{whole(p.pts)}</td><td>{whole(p.reb)}</td><td>{whole(p.ast)}</td><td>{whole(p.tpm)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
);

export const GameStage: React.FC<Props> = ({ game, mvpTitle, rosters, step, onReveal }) => {
  const sides = game?.sides ?? [];
  const labels = sides.length === 2 ? sides.map((s) => s.label) : rosters.map((r) => r.label);
  const hasRosters = rosters.some((r) => r.lines.length > 0);

  if (step < 1) {
    return (
      <>
        <div className="as-box">
          <div className="as-score">
            <span>{labels[0]}</span><span className="as-score-n">?</span><span className="as-muted">vs</span>
            <span className="as-score-n">?</span><span>{labels[1]}</span>
          </div>
          <div className="as-center"><RevealButton label="Tip off →" onClick={onReveal} /></div>
        </div>
        {hasRosters && (
          <div className="as-two">
            {rosters.map((r) => (
              <div key={r.label} className="as-box">
                <div className="as-kick">{r.kick}</div>
                {r.lines.length === 0 ? <NotRecorded /> : <SeasonTable groups={[{ title: '', lines: r.lines }]} />}
              </div>
            ))}
          </div>
        )}
      </>
    );
  }

  if (!game) return <NotRecorded />;
  const [a, b] = sides;
  return (
    <>
      {a && b ? (
        <div className="as-box">
          <div className="as-score">
            <span>{a.label}</span>
            <span className={`as-score-n${game.winner && game.winner !== a.label ? ' is-lost' : ''}`}>{whole(a.score)}</span>
            <span className="as-muted">–</span>
            <span className={`as-score-n${game.winner && game.winner !== b.label ? ' is-lost' : ''}`}>{whole(b.score)}</span>
            <span>{b.label}</span>
          </div>
        </div>
      ) : <NotRecorded what="Score" />}
      {game.mvp?.name ? <Spotlight mvp={game.mvp} title={mvpTitle} /> : <NotRecorded what="MVP" />}
      {a && b
        ? <div className="as-two"><BoxScore label={a.label} lines={a.lines ?? []} /><BoxScore label={b.label} lines={b.lines ?? []} /></div>
        : <NotRecorded what="Box score" />}
    </>
  );
};
