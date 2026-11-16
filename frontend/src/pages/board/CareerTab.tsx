// Your Office, "Career": the user's GM record, teams managed, badges and achievements.
import React from 'react';
import { Award, Lock, Trophy } from 'lucide-react';
import type { UserProfileGM } from './officeTypes';

export const CareerTab: React.FC<{ gm: UserProfileGM }> = ({ gm }) => {
  const unlocked = gm.achievements.filter((a) => a.unlocked).length;
  return (
    <>
      <section className="of-card" aria-labelledby="of-career-head">
        <h3 className="of-card-head" id="of-career-head">
          Your career <small>{gm.seasons_managed} {gm.seasons_managed === 1 ? 'season' : 'seasons'} · {gm.teams_managed_history.length} {gm.teams_managed_history.length === 1 ? 'team' : 'teams'}</small>
        </h3>
        <div className="of-tiles">
          <div className="of-tile"><span>Career wins</span><b className="of-tone-ok">{gm.career_wins}</b></div>
          <div className="of-tile"><span>Career losses</span><b className="of-tone-bad">{gm.career_losses}</b></div>
          <div className="of-tile"><span>Titles</span><b className="of-tone-warn">{gm.titles_won}</b></div>
          <div className="of-tile"><span>Seasons managed</span><b className="of-tone-info">{gm.seasons_managed}</b></div>
        </div>
        <h4 className="of-sub-head">Teams managed</h4>
        {gm.teams_managed_history.length === 0 ? (
          <div className="of-empty">No teams on record yet.</div>
        ) : (
          <ul className="of-list">
            {gm.teams_managed_history.map((item, idx) => (
              <li key={idx} className="of-row">
                <b>{item.team}</b>
                <span>From season {item.start_season} · {item.titles} {item.titles === 1 ? 'title' : 'titles'}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="of-card" aria-labelledby="of-badges-head">
        <h3 className="of-card-head" id="of-badges-head">Badges &amp; perks <small>{gm.badges.length} earned</small></h3>
        {gm.badges.length === 0 ? (
          <div className="of-empty">No badges yet.</div>
        ) : (
          <div className="of-badges">
            {gm.badges.map((badge) => (
              <div key={badge.id} className="of-badge">
                <div className="of-badge-icon" aria-hidden="true"><Award size={17} /></div>
                <div className="of-badge-body">
                  <b>{badge.name}</b>
                  <span>{badge.description}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="of-card" aria-labelledby="of-ach-head">
        <h3 className="of-card-head" id="of-ach-head">Achievements <small>{unlocked} / {gm.achievements.length} unlocked</small></h3>
        <div className="of-badges">
          {gm.achievements.map((ach) => (
            <div key={ach.id} className={`of-badge ${ach.unlocked ? 'is-unlocked' : 'is-locked'}`}>
              <div className="of-badge-icon" aria-hidden="true">{ach.unlocked ? <Trophy size={17} /> : <Lock size={17} />}</div>
              <div className="of-badge-body">
                <b>
                  {ach.title}
                  {ach.unlocked && ach.date_unlocked && <em>{ach.date_unlocked}</em>}
                </b>
                <span>{ach.description}{!ach.unlocked && <span className="of-sr"> (locked)</span>}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
};
