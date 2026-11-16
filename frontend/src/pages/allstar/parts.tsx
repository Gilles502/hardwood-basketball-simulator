// Small pieces shared by the All-Star stages: player name (opens the player popup), team code, reveal button,
// contest tiebreak.
import React from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { getTeamVisuals } from '../../utils/teamVisuals';

export const PlayerName: React.FC<{ name: string; className?: string }> = ({ name, className }) => {
  const openPlayerProfile = useLeagueStore((s) => s.openPlayerProfile);
  return (
    <button type="button" className={`as-name${className ? ` ${className}` : ''}`} title={name} onClick={() => openPlayerProfile(name)}>
      {name}
    </button>
  );
};

/** " · TOR" after a name; nothing when the team is unknown (old seasons). */
export const TeamCode: React.FC<{ team: string | null | undefined; dot?: boolean }> = ({ team, dot = true }) =>
  team ? <span className="as-tcode">{dot ? ' · ' : ''}{getTeamVisuals(team).abbr}</span> : null;

export const RevealButton: React.FC<{ label: string; onClick: () => void }> = ({ label, onClick }) => (
  <button type="button" className="as-reveal" onClick={onClick}>{label}</button>
);

export const NotRecorded: React.FC<{ what?: string }> = ({ what }) => (
  <div className="as-none">{what ? `${what}: not recorded` : 'Not recorded'}</div>
);

/** Shoot-off / dunk-off between the tied leaders of a contest final, winner first; nothing without a tie. */
export const Tiebreak: React.FC<{
  title: string;
  entries: { name: string; score: number; dunk?: string }[] | null | undefined;
  winner: string | null;
}> = ({ title, entries, winner }) => {
  if (!entries || entries.length === 0) return null;
  return (
    <div className="as-box as-tiebreak">
      <div className="as-kick">{title}</div>
      {entries.map((e, i) => (
        <div key={`${e.name}-${i}`} className={`as-dunk${e.name === winner ? ' is-win' : ''}`}>
          <span><PlayerName name={e.name} />{e.dunk && <span className="as-muted"> · {e.dunk}</span>}</span>
          <b>{e.score}</b>
        </div>
      ))}
    </div>
  );
};
