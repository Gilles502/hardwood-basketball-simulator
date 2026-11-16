// Phase 4 · Staff & lottery ("Lottery night"): before the draw, the lottery teams with their pick's owner and odds;
// "Hold the lottery" runs the coaching carousel and the draw on the server; then the envelopes open live (stage +
// still in the hunt) and the full draft order closes the phase. Next is free once the draw exists.
import React, { useCallback, useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import type { PhaseProps } from '../../utils/endSeason';
import { LotteryPreview } from './lottery/LotteryPreview';
import { LotteryReveal } from './lottery/LotteryReveal';
import { DraftOrderBoard } from './lottery/DraftOrderBoard';
import { revealKey, type LotteryDetails, type PreviewTeam } from './lottery/lottery';
import './Lottery.css';

interface Mover { team: string; delta: number }

const readProgress = (key: string): number | null => {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? null : Number(raw);
  } catch {
    return null;
  }
};

const writeProgress = (key: string, value: number) => {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Progress is a convenience: without storage the reveal simply starts over.
  }
};

export const LotteryPhase: React.FC<PhaseProps> = ({ readOnly, onBar, onAdvanced }) => {
  const { leagueData } = useLeagueStore();
  const held = leagueData?.league_state !== 'OFFSEASON_COACH_HIRING_START';
  const userTeam: string = leagueData?.player_team_name ?? '';
  const season = leagueData?.anno_corrente ?? '';
  const [preview, setPreview] = useState<PreviewTeam[] | null>(null);
  const [drawnPicks, setDrawnPicks] = useState(4);
  const [details, setDetails] = useState<(LotteryDetails & { biggest_winner?: Mover | null; biggest_loser?: Mover | null }) | null>(null);
  const [revealed, setRevealed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onBar(held ? {} : { blocking: 'Hold the lottery to continue.' });
  }, [held, onBar]);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/lottery/details?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.available) {
          const d: LotteryDetails = data.data;
          const stored = readProgress(revealKey(season, userTeam));
          setRevealed(readOnly ? d.picks.length : Math.min(d.picks.length, Math.max(0, stored ?? 0)));
          setDetails(d);
        } else {
          setPreview(data.preview?.teams ?? []);
          if (data.preview?.drawn_picks) setDrawnPicks(data.preview.drawn_picks);
        }
      })
      .catch(() => { if (!cancelled) setError('The lottery could not be loaded.'); });
    return () => { cancelled = true; };
  }, [held, readOnly, season, userTeam]);

  const reveal = useCallback((value: number) => {
    const total = details?.picks.length ?? 0;
    const next = Math.max(0, Math.min(total, value));
    setRevealed(next);
    writeProgress(revealKey(season, userTeam), next);
  }, [details, season, userTeam]);

  const holdLottery = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/api/run_coach_hiring', { method: 'POST' });
      if (!response.ok) throw new Error();
      writeProgress(revealKey(season, userTeam), 0);
      await onAdvanced();
    } catch {
      setError('The lottery could not be held. Try again.');
    } finally {
      setBusy(false);
    }
  };

  if (!held) {
    return <LotteryPreview teams={preview} drawnPicks={drawnPicks} userTeam={userTeam} readOnly={readOnly} busy={busy} error={error} onHold={holdLottery} />;
  }
  if (!details) {
    return <div className="eos-sheet"><p className={error ? 'eos-error' : 'eos-muted'}>{error ?? 'Loading the lottery…'}</p></div>;
  }
  if (details.picks.length === 0) {
    return <DraftOrderBoard order={details.full_order} userTeam={userTeam} />;
  }
  if (revealed < details.picks.length) {
    return <LotteryReveal details={details} userTeam={userTeam} revealed={revealed} onReveal={reveal} />;
  }

  const winner = details.biggest_winner;
  const loser = details.biggest_loser;
  return (
    <div className="lot-done">
      <div className="eos-sheet lot-recap">
        <span className="eos-kicker">The lottery is over</span>
        <p className="eos-line">
          {winner ? <>Big winner: <b>{winner.team}</b> (up {winner.delta}). </> : 'Nobody jumped up. '}
          {loser && <>Biggest drop: <b>{loser.team}</b> (down {Math.abs(loser.delta)}).</>}
        </p>
        {!readOnly && <button type="button" className="eos-link" onClick={() => reveal(0)}>Replay the draw</button>}
      </div>
      <DraftOrderBoard order={details.full_order} userTeam={userTeam} />
    </div>
  );
};
