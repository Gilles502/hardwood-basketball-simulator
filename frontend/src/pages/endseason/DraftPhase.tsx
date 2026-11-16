// Phase 6 · Draft: the draft room (layout "on-the-clock strip + wide big board"). The phase opens the draft by
// itself; the strip runs the CPU picks, the big board shows the class as the user's scouts see it, the desk column
// holds the offers for the user's pick, the way into the trade panel and the draft wire. After the last pick the hub
// stays here (core/end_season.py) on the summary until Next.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import type { PhaseProps } from '../../utils/endSeason';
import { ClockStrip } from './draft/ClockStrip';
import { BigBoard } from './draft/BigBoard';
import { DraftWire } from './draft/DraftWire';
import { DraftDesk } from './draft/DraftDesk';
import { DraftTradePanel } from './draft/DraftTradePanel';
import { DraftSummary } from './draft/DraftSummary';
import { picksPerRound, type DraftState } from './draft/draftRoom';
import './Draft.css';

const AUTO_MS = 1500;

export const DraftPhase: React.FC<PhaseProps> = ({ readOnly, onBar }) => {
  const { leagueData, fetchLeagueData } = useLeagueStore();
  const leagueState: string | undefined = leagueData?.league_state;
  const userTeam: string = leagueData?.player_team_name ?? '';
  const [state, setState] = useState<DraftState | null>(null);
  const [busy, setBusy] = useState(false);
  const [auto, setAuto] = useState(false);
  const [showOrder, setShowOrder] = useState(false);
  const [trading, setTrading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tradesSeen = useRef(0);

  const loadState = useCallback(async () => {
    try {
      const data: DraftState = await (await fetch(`/api/draft/state?_t=${Date.now()}`)).json();
      setState(data);
    } catch {
      setError('The draft room could not be loaded.');
    }
  }, []);

  /** Runs one draft action; the answer is the new draft state (or an error to show). */
  const act = useCallback(async (url: string, body?: unknown): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data: DraftState = await response.json();
      if (!response.ok || data.error) {
        setError(data.error ?? 'That did not work. Try again.');
        return false;
      }
      setState(data);
      if (data.status === 'COMPLETED') await fetchLeagueData();
      return true;
    } catch {
      setError('The server did not answer. Try again.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [fetchLeagueData]);

  // The phase opens the draft by itself (once: effects run twice in development).
  const startedRef = useRef(false);
  useEffect(() => {
    if (readOnly || startedRef.current || leagueState !== 'OFFSEASON_DRAFT_START') return;
    startedRef.current = true;
    (async () => {
      await fetch('/api/run_draft', { method: 'POST' }).catch(() => undefined);
      await fetchLeagueData();
    })();
  }, [readOnly, leagueState, fetchLeagueData]);

  useEffect(() => {
    if (leagueState && leagueState !== 'OFFSEASON_DRAFT_START') loadState();
  }, [leagueState, loadState]);

  const status = state?.status;
  useEffect(() => {
    onBar(status === 'COMPLETED' ? {} : { blocking: 'Finish the draft to continue.' });
  }, [status, onBar]);

  // Auto: one CPU pick every AUTO_MS until it is the user's turn, the draft ends or a CPU trade breaks the news.
  const tradeCount = state?.trades?.length ?? 0;
  useEffect(() => {
    if (tradeCount > tradesSeen.current) setAuto(false);
    tradesSeen.current = tradeCount;
  }, [tradeCount]);
  useEffect(() => {
    if (!auto) return;
    if (!state || state.is_user_turn || state.status !== 'DRAFT_IN_PROGRESS') { setAuto(false); return; }
    const id = window.setTimeout(() => { act('/api/draft/step'); }, AUTO_MS);
    return () => window.clearTimeout(id);
  }, [auto, state, act]);

  const draftPlayer = async (name: string) => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/api/make_draft_pick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: name }),
      });
      if (!response.ok) throw new Error();
      await fetchLeagueData();
      await loadState();
    } catch {
      setError('The pick could not be made. Try again.');
    } finally {
      setBusy(false);
    }
  };

  if (!leagueData) return null;
  if (!state || state.status === 'NOT_STARTED') {
    return <div className="eos-sheet"><p className={error ? 'eos-error' : 'eos-muted'}>{error ?? 'Opening the draft room…'}</p></div>;
  }

  if (state.status === 'COMPLETED') return <DraftSummary state={state} userTeam={userTeam} />;

  const perRound = picksPerRound(state);
  const teams: string[] = (leagueData.league_database?.teams ?? []).map((t: { nome: string }) => t.nome);

  return (
    <div className="dr-room">
      <ClockStrip
        state={state}
        userTeam={userTeam}
        auto={auto}
        busy={busy}
        showOrder={showOrder}
        onToggleAuto={() => setAuto(!auto)}
        onStep={() => act('/api/draft/step')}
        onSimToUser={() => act('/api/draft/sim_to_user')}
        onToggleOrder={() => setShowOrder(!showOrder)}
      />
      {error && <p className="dr-error">{error}</p>}
      <div className="dr-grid">
        {trading ? (
          <DraftTradePanel
            userTeam={userTeam}
            teams={teams}
            onDone={(next) => { setState(next); setTrading(false); }}
            onClose={() => setTrading(false)}
          />
        ) : (
          <BigBoard prospects={state.prospects ?? []} canDraft={!!state.is_user_turn && !readOnly} busy={busy} onDraft={draftPlayer} />
        )}
        <div className="dr-desk">
          <DraftDesk
            state={state}
            busy={busy}
            onAccept={(offerId) => { act('/api/draft/accept_cpu_offer', { offer_id: offerId }); }}
            onBuildTrade={() => { setAuto(false); setTrading(true); }}
          />
          <DraftWire state={state} perRound={perRound} userTeam={userTeam} />
        </div>
      </div>
    </div>
  );
};
