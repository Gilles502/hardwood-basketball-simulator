// The offers on the table for one player: one bar per offer with the score he gives it, a black line at tonight's
// bar, and the verdict sentence. The offer sheet passes the race of its preview, so the user's line moves live.
// CPU teams that raised show "▲ raised from $X on day N"; teams that pulled out stay greyed with the reason.
// Bar widths and the bar line are data-driven geometry, hence the only inline styles.
import React from 'react';
import { contractLine, raiseLine, verdict, type Race } from './freeAgency';

interface OffersRaceProps {
  race: Race;
  userTeam: string;
  /** Title over the bars. */
  title?: string;
}

const pct = (v: number) => `${Math.max(0, Math.min(100, v))}%`;

export const OffersRace: React.FC<OffersRaceProps> = ({ race, userTeam, title = 'Offers on the table' }) => (
  <div className="fa-race">
    <span className="eos-kicker">{title}</span>
    <p className="fa-race-sub">
      Tonight he signs with the best score if it reaches <b>{Math.round(race.bar_tonight)}</b> (the black line)
      {race.bar_tomorrow !== null && <>; tomorrow <b>{Math.round(race.bar_tomorrow)}</b></>}.
    </p>
    {(race.offers.length > 0 || (race.withdrawn?.length ?? 0) > 0) && (
      <div className="fa-race-rows">
        {race.offers.map((o) => {
          const shown = o.previous_team_bonus ? o.score + o.loyalty_bonus : o.score;
          const raised = raiseLine(o);
          return (
            <React.Fragment key={o.team}>
              <span className={`fa-race-team${o.team === userTeam ? ' is-yours' : ''}`}>
                <b>{o.team === userTeam ? 'You' : o.team}</b> · {contractLine(o.salary, o.years)}
                {raised && <small className="fa-raise">{raised}</small>}
                {o.previous_team_bonus && <small>+{Math.round(o.loyalty_bonus)} loyalty</small>}
              </span>
              <div className="fa-race-track" title={`Score ${Math.round(shown)}`}>
                <div className={`fa-race-bar${o.team === userTeam ? ' is-yours' : ''}`} style={{ width: pct(shown) }} />
                <div className="fa-race-line" style={{ left: pct(race.bar_tonight) }} />
              </div>
              <b className="fa-race-score">{Math.round(shown)}</b>
            </React.Fragment>
          );
        })}
        {(race.withdrawn ?? []).map((w) => (
          <React.Fragment key={`out-${w.team}`}>
            <span className="fa-race-team fa-out">
              <b>{w.team}</b> · {contractLine(w.salary, w.years)}
              <small>pulled out on day {w.day}: {w.reason}</small>
            </span>
            <span className="fa-out" />
            <span className="fa-out" />
          </React.Fragment>
        ))}
      </div>
    )}
    <p className={`fa-race-verdict${race.would_sign_with === userTeam ? ' is-good' : ''}`}>{verdict(race, userTeam)}</p>
    {race.offers.length > 0 && <p className="fa-race-note">New offers and raises can still arrive tonight.</p>}
  </div>
);
