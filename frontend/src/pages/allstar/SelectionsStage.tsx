// All-Star Selections: East, then West. Starters, reserves and the best players left out, with season stats.
import React from 'react';
import { NotRecorded, PlayerName, RevealButton, TeamCode } from './parts';
import { one, type Conference, type SeasonLine, type Selections, type StageProps } from './types';

const Rows: React.FC<{ title: string; lines: SeasonLine[]; out?: boolean }> = ({ title, lines, out }) => (
  <>
    {title && <tr className="as-kick-row"><td colSpan={5}>{title}</td></tr>}
    {lines.map((p, i) => (
      <tr key={`${p.name}-${i}`} className={p.is_user ? 'is-user' : out ? 'is-out' : undefined}>
        <td className="as-player"><PlayerName name={p.name} /><TeamCode team={p.team} /></td>
        <td>{p.pos ?? '—'}</td>
        <td>{one(p.ppg)}</td>
        <td>{one(p.rpg)}</td>
        <td>{one(p.apg)}</td>
      </tr>
    ))}
  </>
);

/** A season-stats table (Player · team, Pos, PPG, RPG, APG) split in titled groups (empty title = no group row). */
export const SeasonTable: React.FC<{ groups: { title: string; lines: SeasonLine[]; out?: boolean }[] }> = ({ groups }) => (
  <table className="as-table">
    <colgroup><col /><col className="as-c-pos" /><col className="as-c-n" /><col className="as-c-n" /><col className="as-c-n" /></colgroup>
    <thead><tr><th>Player</th><th>Pos</th><th>PPG</th><th>RPG</th><th>APG</th></tr></thead>
    <tbody>
      {groups.filter((g) => g.lines.length > 0).map((g, i) => <Rows key={i} {...g} />)}
    </tbody>
  </table>
);

const ConferenceBox: React.FC<{ label: string; conf: Conference | undefined }> = ({ label, conf }) => {
  const starters = conf?.starters ?? [];
  const reserves = conf?.reserves ?? [];
  const leftOut = conf?.left_out ?? [];
  return (
    <div className="as-box">
      <div className="as-box-title">{label}</div>
      {starters.length + reserves.length === 0
        ? <NotRecorded />
        : <SeasonTable groups={[
            { title: 'Starters', lines: starters },
            { title: 'Reserves', lines: reserves },
            { title: 'Left out', lines: leftOut, out: true },
          ]} />}
    </div>
  );
};

const Waiting: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="as-box as-box-waiting">
    <div className="as-box-title">{label}</div>
    <div className="as-waiting">{children}</div>
  </div>
);

export const SelectionsStage: React.FC<StageProps & { selections: Selections | null }> = ({ selections, step, onReveal }) => {
  if (!selections) return <NotRecorded />;
  return (
    <div className="as-two">
      {step >= 1
        ? <ConferenceBox label="East" conf={selections.east} />
        : <Waiting label="East"><RevealButton label="Reveal the East →" onClick={onReveal} /></Waiting>}
      {step >= 2
        ? <ConferenceBox label="West" conf={selections.west} />
        : step === 1
          ? <Waiting label="West"><RevealButton label="Reveal the West →" onClick={onReveal} /></Waiting>
          : <Waiting label="West"><span className="as-muted">After the East</span></Waiting>}
    </div>
  );
};
