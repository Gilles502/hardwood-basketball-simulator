// Your Office, "This Season": the board's objectives with progress, and the owner's messages.
import React from 'react';
import type { BoardMessage, BoardObjective, Tone } from './officeTypes';

const SEASON_GAMES = 82;

interface ObjectiveState {
  label: string;
  tone: Tone;
  /** True when the page estimated the state itself (not decided by the board yet). */
  projected?: boolean;
}

/** Done / Failed come from the board engine; for open objectives the page judges the pace itself:
 *  wins against the pace of the target, payroll against the limit, counts against the target. */
const objectiveState = (obj: BoardObjective, gamesPlayed: number): ObjectiveState => {
  if (obj.status === 'Completed') return { label: 'Done', tone: 'ok' };
  if (obj.status === 'Failed') return { label: 'Failed', tone: 'bad' };
  const isWins = obj.category === 'Competitive' || obj.id.includes('obj_comp');
  const isPayroll = obj.category === 'Financial' || obj.id.includes('obj_fin_tax') || obj.id.includes('obj_fin_budget');
  const isYouth = obj.id.includes('obj_youth');
  let onTrack: boolean;
  if (isWins) {
    onTrack = gamesPlayed === 0 || obj.current_value >= Math.floor((obj.target_value * gamesPlayed) / SEASON_GAMES);
  } else if (isPayroll) {
    onTrack = obj.current_value <= obj.target_value;
  } else if (isYouth) {
    // Player growth mostly lands between seasons: nothing to judge mid-season.
    return { label: 'In progress', tone: 'info' };
  } else {
    onTrack = obj.current_value >= obj.target_value;
  }
  return onTrack ? { label: 'On track', tone: 'info', projected: true } : { label: 'Behind', tone: 'warn', projected: true };
};

const progressText = (obj: BoardObjective) =>
  obj.category === 'Financial'
    ? `$${obj.current_value}M / $${obj.target_value}M`
    : `${Math.round(obj.current_value)} / ${obj.target_value}`;

/** Older saves can hold the season-start letter twice in a row (sent by both the profile and the objectives).
 *  Only an exact repeat right after the same message is hidden: letters of other seasons may read the same. */
const uniqueMessages = (messages: BoardMessage[]) =>
  messages.filter((m, i) => {
    const prev = messages[i - 1];
    return !prev || prev.date !== m.date || prev.title !== m.title || prev.content !== m.content;
  });

interface SeasonTabProps {
  objectives: BoardObjective[];
  messages: BoardMessage[];
  season?: number;
  gamesPlayed: number;
}

export const SeasonTab: React.FC<SeasonTabProps> = ({ objectives, messages: rawMessages, season, gamesPlayed }) => {
  const messages = uniqueMessages(rawMessages);
  return (
  <>
    <section className="of-card" aria-labelledby="of-objectives-head">
      <h3 className="of-card-head" id="of-objectives-head">
        Objectives <small>{objectives.length} this season{season ? ` · season ${season}` : ''}</small>
      </h3>
      {objectives.length === 0 && <div className="of-empty">The board has not set any objectives yet.</div>}
      {objectives.map((obj) => {
        const state = objectiveState(obj, gamesPlayed);
        const targetVal = obj.target_value || 1;
        const fill = Math.min(100, Math.max(0, (obj.current_value / targetVal) * 100));
        const meterTone: Tone = state.tone === 'info' ? 'ok' : state.tone;
        const impact = obj.status === 'Completed' ? `+${obj.impact_approval}% approval`
          : obj.status === 'Failed' ? `-${obj.impact_approval}% approval`
          : `worth ${obj.impact_approval}% approval`;
        return (
          <div className="of-obj" key={obj.id}>
            <div className="of-obj-top">
              <div className="of-obj-title">
                <b>{obj.title}</b>
                <span className="of-pill is-quiet">{obj.category}</span>
              </div>
              <span className={`of-pill is-${state.tone}`} title={state.projected ? 'Projected from the current pace' : undefined}>
                {state.label}{state.projected && <span className="of-sr"> (projected from the current pace)</span>}
              </span>
            </div>
            <p>{obj.description}</p>
            <div className="of-nums">
              <span>Progress <strong>{progressText(obj)}</strong></span>
              <span>{impact}</span>
            </div>
            <div className={`of-meter is-thin is-${meterTone}`} aria-hidden="true">
              <i style={{ width: `${fill}%` }} />
            </div>
          </div>
        );
      })}
    </section>

    <section className="of-card" aria-labelledby="of-messages-head">
      <h3 className="of-card-head" id="of-messages-head">Messages <small>from the owner</small></h3>
      {messages.length === 0 ? (
        <div className="of-empty">No messages from the owner yet.</div>
      ) : (
        <div className="of-msgs" tabIndex={0} aria-label="Owner messages">
          {messages.map((msg, index) => (
            <div key={index} className={`of-msg is-${msg.type}`}>
              <div className="of-msg-top"><b>{msg.title}</b><span>{msg.date}</span></div>
              <p>{msg.content}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  </>
  );
};
