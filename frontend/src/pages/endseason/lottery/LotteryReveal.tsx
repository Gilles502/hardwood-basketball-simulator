// Lottery night, the reveal (layout "stage + still in the hunt"): envelopes open from the last lottery pick to #1.
// The stage shows the envelope just opened, the strip every slot, and the side column the teams still sealed with
// their chance of the #1 pick given what has been revealed (exact odds computed on the server).
import React, { useEffect, useState } from 'react';
import { TeamCrest } from '../../../components/TeamCrest';
import { crestLabel } from '../../../utils/crest';
import { ordinal, pickLabel, protectionLabel, userIsTopCertain, type LotteryDetails, type LotteryPick } from './lottery';

interface LotteryRevealProps {
  details: LotteryDetails;
  userTeam: string;
  revealed: number;
  onReveal: (revealed: number) => void;
}

const AUTO_MS = 1500;

const Move: React.FC<{ delta: number }> = ({ delta }) =>
  delta > 0 ? <span className="eos-up">▲ up {delta}</span>
    : delta < 0 ? <span className="eos-down">▼ down {Math.abs(delta)}</span>
      : <span className="lot-same">no change</span>;

const Stage: React.FC<{ pick: LotteryPick | null; next: number; total: number }> = ({ pick, next, total }) => {
  if (!pick) {
    return (
      <div className="lot-stage is-sealed">
        <span className="eos-kicker">The draw is in</span>
        <div className="lot-stage-num">{total}</div>
        <p className="lot-stage-line">{total} envelopes, opened from pick #{next} up to the first overall pick.</p>
      </div>
    );
  }
  const via = pickLabel(pick.owner, pick.team);
  return (
    <div className="lot-stage" key={pick.pick}>
      <span className="eos-kicker">Envelope · pick</span>
      <div className="lot-stage-num">#{pick.pick}</div>
      <div className="lot-stage-team">
        <TeamCrest name={pick.owner} size={44} />
        <span>{pick.owner}</span>
      </div>
      {via && <div className="lot-stage-via">{via}</div>}
      <p className="lot-stage-line">
        Entered as the <b>{ordinal(pick.projected)} seed</b> · <Move delta={pick.delta} />
      </p>
      {pick.protection_triggered && (
        <p className="lot-stage-prot">
          {pick.protection} protected: the pick stays with {pick.owner} ({pick.owner_before} lose it).
        </p>
      )}
    </div>
  );
};

export const LotteryReveal: React.FC<LotteryRevealProps> = ({ details, userTeam, revealed, onReveal }) => {
  const picks = details.picks;
  const n = picks.length;
  const [auto, setAuto] = useState(false);
  const nextPick = n - revealed; // the envelope the next click opens
  const shown = revealed > 0 ? picks.find((p) => p.pick === nextPick + 1) ?? null : null;
  const drawn = Math.min(details.drawn_picks, n);
  const sealedOnly = Math.max(0, n - drawn);

  useEffect(() => {
    if (!auto) return;
    if (revealed >= n) { setAuto(false); return; }
    const id = window.setTimeout(() => onReveal(revealed + 1), AUTO_MS);
    return () => window.clearTimeout(id);
  }, [auto, revealed, n, onReveal]);

  const bySeed = new Map(picks.map((p) => [p.projected - 1, p]));
  const hunt = [...(details.hunt_steps[revealed] ?? [])].sort((a, b) => b.odds_first - a.odds_first);

  return (
    <div className="lot-reveal">
      <div className="lot-main">
        <Stage pick={shown} next={n} total={n} />
        <ol className="lot-strip">
          {picks.map((p) => {
            const open = p.pick > nextPick;
            const cls = !open ? 'is-sealed' : p.pick === nextPick + 1 ? 'is-new' : 'is-open';
            return (
              <li key={p.pick} className={`${cls}${open && p.owner === userTeam ? ' is-yours' : ''}`} title={open ? p.owner : `Pick #${p.pick}`}>
                <small>{p.pick}</small>
                <b>{open ? crestLabel(p.owner) : '·'}</b>
              </li>
            );
          })}
        </ol>
        <div className="lot-controls">
          <button type="button" className="btn btn-secondary" onClick={() => onReveal(sealedOnly)} disabled={revealed >= sealedOnly}>
            Skip to top {drawn}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => setAuto(!auto)}>
            {auto ? 'Pause' : 'Auto ▸'}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => { setAuto(false); onReveal(revealed + 1); }}>
            Open pick #{nextPick}
          </button>
        </div>
      </div>

      <aside className="eos-sheet lot-hunt">
        <span className="eos-kicker">Still in the hunt · {n - revealed} {n - revealed === 1 ? 'envelope' : 'envelopes'} left</span>
        <p className="lot-hunt-sub">Chance of the #1 pick among the teams still sealed</p>
        <ul>
          {hunt.map((h) => {
            const p = bySeed.get(h.seed);
            if (!p) return null;
            // A sealed pick still belongs to whoever held it before the draw: a protection is only settled when it opens.
            const holder = p.owner_before;
            const yours = holder === userTeam;
            const via = pickLabel(holder, p.team);
            const note = [yours ? 'your pick' : '', via, protectionLabel(p.protection), `seed ${p.projected}`].filter(Boolean).join(' · ');
            return (
              <li key={h.seed} className={yours ? 'is-yours' : undefined}>
                <TeamCrest name={holder} size={26} />
                <span className="lot-hunt-team">
                  <b>{holder}</b>
                  <small>{note}</small>
                </span>
                <span className="lot-hunt-odds">{h.odds_first.toFixed(1)}%</span>
              </li>
            );
          })}
        </ul>
        {userIsTopCertain(picks, revealed, userTeam, details.drawn_picks) && (
          <p className="lot-hunt-good">Your pick is guaranteed a top {drawn} spot.</p>
        )}
      </aside>
    </div>
  );
};
