// File: frontend/src/pages/AllStar.tsx
// All-Star Weekend (GET /api/allstar[?season=n], core/all_star_view.py): event rail on the left, stage on the right.
// The current season's weekend opens night by night (steps in utils/allStarReveal.ts, kept per save and season);
// past seasons open fully revealed. Stages live in pages/allstar/.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { allRevealed, loadReveal, revealKey, saveReveal, STEPS } from '../utils/allStarReveal';
import { formatGameDate } from '../utils/format';
import { EventRail, type RailState } from './allstar/EventRail';
import { NotRecorded } from './allstar/parts';
import { SelectionsStage } from './allstar/SelectionsStage';
import { GameStage } from './allstar/GameStage';
import { ThreePointStage } from './allstar/ThreePointStage';
import { DunkStage } from './allstar/DunkStage';
import type { AllStarView, EventId, WeekendEvent } from './allstar/types';
import './dashboard/Dashboard.css'; // dash-header, shared with the Dashboard
import './allstar/AllStar.css';

type Steps = Record<EventId, number>;

/** Only the current season's played weekend is revealed step by step; names-only legacy data never is. */
const isLive = (d: AllStarView) => d.status === 'played' && d.is_current && !d.legacy;

/** Steps an event needs before it counts as seen; an event with nothing recorded needs none. */
const needed = (e: WeekendEvent) => (e.recorded ? STEPS[e.id] : 0);

const railStates = (d: AllStarView, steps: Steps): Record<EventId, RailState> => {
  const states = {} as Record<EventId, RailState>;
  let blocked = d.status !== 'played';
  for (const e of d.events) {
    if (blocked) states[e.id] = 'locked';
    else if (steps[e.id] >= needed(e)) states[e.id] = 'done';
    else { states[e.id] = 'current'; blocked = true; }
  }
  return states;
};

const firstOpen = (d: AllStarView, steps: Steps): EventId | null => {
  if (d.status !== 'played') return null;
  return (d.events.find((e) => steps[e.id] < needed(e)) ?? d.events[0])?.id ?? null;
};

const YouStrip: React.FC<{ you: NonNullable<AllStarView['you']>; showCount: boolean }> = ({ you, showCount }) => {
  const items: React.ReactNode[] = [];
  if (showCount && you.all_stars > 0) {
    items.push(<span key="n"><b>{you.team}</b>: {you.all_stars} All-Star{you.all_stars === 1 ? '' : 's'}</span>);
  }
  you.entries.forEach((entry, i) => {
    const at = entry.lastIndexOf(' in the ');
    items.push(at < 0
      ? <span key={i}>{entry}</span>
      : <span key={i}>{entry.slice(0, at)} in the <b>{entry.slice(at + 8)}</b></span>);
  });
  return items.length ? <div className="as-you">{items}</div> : null;
};

export const AllStar: React.FC = () => {
  const activeSaveName = useLeagueStore((s) => s.activeSaveName);
  const [data, setData] = useState<AllStarView | null>(null);
  const [steps, setSteps] = useState<Steps>(allRevealed);
  const [selected, setSelected] = useState<EventId | null>(null);
  // Storage key of the loaded view (save + season as of its fetch); null when the view is not revealed step by step.
  const [storeKey, setStoreKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);

  const load = useCallback(async (season?: number) => {
    const id = ++request.current;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ _t: String(Date.now()) });
      if (season !== undefined) params.set('season', String(season));
      const res = await fetch(`/api/allstar?${params}`);
      const body = await res.json();
      if (id !== request.current) return;
      if (!res.ok || body.error) {
        setError(body.error || 'Could not load the All-Star Weekend.');
        return;
      }
      const view = body as AllStarView;
      const key = isLive(view) ? revealKey(activeSaveName, view.season) : null;
      const opened = key ? loadReveal(key) : allRevealed();
      setData(view);
      setStoreKey(key);
      setSteps(opened);
      setSelected(firstOpen(view, opened));
    } catch {
      if (id === request.current) setError('Server communication error fetching All-Star data.');
    } finally {
      if (id === request.current) setLoading(false);
    }
  }, [activeSaveName]);

  useEffect(() => { load(); }, [load]);

  const store = (next: Steps) => {
    setSteps(next);
    if (storeKey) saveReveal(storeKey, next);
  };
  const reveal = (id: EventId) => store({ ...steps, [id]: Math.min(steps[id] + 1, STEPS[id]) });
  const showAll = () => store(allRevealed());

  if (!data) {
    return (
      <div>
        <div className="dash-header"><div><h1 className="dash-title">All-Star Weekend</h1></div></div>
        <div className="as-message">{error ?? (loading ? 'Loading the All-Star Weekend…' : '')}</div>
      </div>
    );
  }

  const states = railStates(data, steps);
  const anyHidden = isLive(data) && data.events.some((e) => states[e.id] !== 'done');
  const selectionsDone = states.selections === 'done';
  const event = data.events.find((e) => e.id === selected) ?? null;
  // Once this event is fully revealed and the next one is open, a button leads on (none after the last event).
  const following = event && states[event.id] === 'done'
    ? data.events[data.events.findIndex((e) => e.id === event.id) + 1]
    : undefined;
  const nextEvent = following && states[following.id] !== 'locked' ? following : null;
  const seasons = data.seasons.some((s) => s.season === data.season)
    ? data.seasons
    : [{ season: data.season, label: data.label }, ...data.seasons];

  const stage = () => {
    if (!event) return null;
    // Nothing recorded = nothing to reveal: the stage opens on its "Not recorded" parts.
    const props = { step: needed(event) ? steps[event.id] : STEPS[event.id], onReveal: () => reveal(event.id) };
    switch (event.id) {
      case 'selections':
        return <SelectionsStage selections={data.selections} {...props} />;
      case 'rookie_challenge': {
        const rc = data.rookie_challenge;
        if (!rc) return <NotRecorded />;
        return (
          <GameStage
            game={rc.game}
            mvpTitle="Rookie Challenge MVP"
            rosters={[
              { label: 'Rookies', kick: 'Rookies', lines: rc.rookies ?? [] },
              { label: 'Sophomores', kick: 'Sophomores', lines: rc.sophomores ?? [] },
            ]}
            {...props}
          />
        );
      }
      case 'three_point':
        return <ThreePointStage contest={data.three_point} {...props} />;
      case 'dunk':
        return <DunkStage contest={data.dunk} {...props} />;
      case 'game':
        if (!data.game) return <NotRecorded />;
        return (
          <GameStage
            game={data.game}
            mvpTitle="All-Star Game MVP"
            rosters={[
              { label: 'East', kick: 'East starters', lines: data.selections?.east?.starters ?? [] },
              { label: 'West', kick: 'West starters', lines: data.selections?.west?.starters ?? [] },
            ]}
            {...props}
          />
        );
    }
  };

  const breakDate = formatGameDate(data.break?.date);

  return (
    <div className="as-page">
      <div className="dash-header">
        <div>
          <h1 className="dash-title">All-Star Weekend</h1>
          <span className="dash-subtitle">{[data.label, data.host ? `${data.host} hosts` : null].filter(Boolean).join(' · ')}</span>
        </div>
        <div className="dash-badges">
          {anyHidden && <button type="button" className="as-show-all" onClick={showAll}>Show all</button>}
          {seasons.length > 0 && (
            <select
              className="as-year"
              aria-label="Season"
              value={data.season}
              disabled={loading}
              onChange={(ev) => load(Number(ev.target.value))}
            >
              {seasons.map((s) => <option key={s.season} value={s.season}>{s.label ?? `Season ${s.season}`}</option>)}
            </select>
          )}
        </div>
      </div>

      {error && <div className="as-message is-error">{error}</div>}
      {data.you && <YouStrip you={data.you} showCount={selectionsDone} />}

      {data.status === 'not_recorded' ? (
        <div className="as-message">No All-Star Weekend was recorded for {data.label ?? 'this season'}.</div>
      ) : (
        <div className="as-body">
          <EventRail events={data.events} states={states} selected={selected} onSelect={setSelected} />
          <section className="as-stage" aria-live="polite">
            {data.status === 'upcoming' ? (
              <div className="as-message">
                {data.break
                  ? <>The All-Star break starts on day {data.break.day + 1}{breakDate ? ` (${breakDate})` : ''}.</>
                  : 'The All-Star Weekend has not been played yet.'}
              </div>
            ) : event && (
              <>
                <div className="as-stage-head">
                  <span className="as-muted">{event.night}</span>
                  <h2 className="as-stage-title">{event.title}</h2>
                </div>
                {stage()}
                {nextEvent && (
                  <div className="as-next">
                    <button type="button" className="as-next-btn" onClick={() => setSelected(nextEvent.id)}>
                      Next: {nextEvent.title} →
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
};
