// Last night's report under the day bar: the bidding wars first (one card per player: who won, who raised, who pulled
// out), then the other signings. The user's own battles and signings come first; long lists stop at a few rows with
// "Show all". Built from the night's moves (raises, pull-outs) and the signings of that night.
import React, { useMemo, useState } from 'react';
import { contractLine, money, type NightMove, type Signing } from './freeAgency';

const SHOWN_BATTLES = 5;
const SHOWN_DEALS = 6;

interface Side { team: string; raised: number; salary: number | null; out: boolean }
interface Battle { player: string; ovr: number | null; sides: Side[]; signing: Signing | null; yours: boolean }

export function buildBattles(moves: NightMove[], signings: Signing[], userTeam: string, ovrOf: (name: string) => number | undefined): Battle[] {
  const byPlayer = new Map<string, Side[]>();
  for (const m of moves) {
    if (m.type === 'signed') continue;
    const sides = byPlayer.get(m.player) ?? [];
    let side = sides.find((s) => s.team === m.team);
    if (!side) { side = { team: m.team, raised: 0, salary: null, out: false }; sides.push(side); }
    if (m.type === 'raise') { side.raised += 1; side.salary = m.salary ?? side.salary; } else side.out = true;
    byPlayer.set(m.player, sides);
  }
  const battles: Battle[] = [];
  byPlayer.forEach((sides, player) => {
    const signing = signings.find((s) => s.player === player) ?? null;
    if (signing) {
      // The winner and the rivals he beat who made no move tonight still belong to the card.
      if (!sides.some((s) => s.team === signing.team)) sides.unshift({ team: signing.team, raised: 0, salary: null, out: false });
      for (const b of signing.beat) if (!sides.some((s) => s.team === b.team)) sides.push({ team: b.team, raised: 0, salary: null, out: false });
    }
    const ordered = [...sides].sort((a, b) => Number(b.team === signing?.team) - Number(a.team === signing?.team));
    battles.push({
      player, ovr: signing?.ovr ?? ovrOf(player) ?? null, sides: ordered, signing,
      yours: ordered.some((s) => s.team === userTeam),
    });
  });
  return battles.sort((a, b) => Number(b.yours) - Number(a.yours) || (b.ovr ?? 0) - (a.ovr ?? 0));
}

interface NightReportProps {
  moves: NightMove[];
  signings: Signing[];
  userTeam: string;
  ovrOf: (name: string) => number | undefined;
}

export const NightReport: React.FC<NightReportProps> = ({ moves, signings, userTeam, ovrOf }) => {
  const [allBattles, setAllBattles] = useState(false);
  const [allDeals, setAllDeals] = useState(false);
  const battles = useMemo(() => buildBattles(moves, signings, userTeam, ovrOf), [moves, signings, userTeam, ovrOf]);
  const fought = new Set(battles.map((b) => b.player));
  const deals = useMemo(() => signings.filter((s) => !fought.has(s.player))
    .sort((a, b) => Number(b.team === userTeam) - Number(a.team === userTeam) || b.ovr - a.ovr),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [signings, battles, userTeam]);

  if (battles.length === 0 && deals.length === 0) return null;
  const shownBattles = allBattles ? battles : battles.slice(0, SHOWN_BATTLES);
  const shownDeals = allDeals ? deals : deals.slice(0, SHOWN_DEALS);

  return (
    <div className="fa-night">
      {shownBattles.map((b) => (
        <div key={b.player} className={`fa-battle${b.yours ? ' is-yours' : ''}`}>
          <div className="fa-battle-head">
            <b>⚔ {b.player}{b.ovr != null ? ` (${b.ovr})` : ''}</b>
            {b.signing
              ? <span> → {b.signing.team === userTeam ? 'you' : b.signing.team} · {contractLine(b.signing.salary, b.signing.years)}</span>
              : <span className="fa-night-muted"> · still unsigned</span>}
          </div>
          <div className="fa-battle-sides">
            {b.sides.map((s, i) => (
              <React.Fragment key={s.team}>
                {i > 0 && ' · '}
                <span className={s.team === userTeam ? 'is-yours' : undefined}>
                  {s.team === userTeam ? 'You' : s.team}
                  {s.raised > 0 && ` ▲${s.raised > 1 ? `×${s.raised}` : ''}${s.salary != null ? ` ${money(s.salary)}` : ''}`}
                  {s.out && ' ✕ out'}
                </span>
              </React.Fragment>
            ))}
          </div>
        </div>
      ))}
      {battles.length > SHOWN_BATTLES && (
        <button type="button" className="fa-night-more" onClick={() => setAllBattles((v) => !v)}>
          {allBattles ? 'Fewer battles' : `Show all ${battles.length} battles`}
        </button>
      )}
      {deals.length > 0 && (
        <div className="fa-deals">
          <div className="fa-night-title">Other signings · {deals.length}</div>
          {shownDeals.map((s) => (
            <div key={s.player} className={s.team === userTeam ? 'is-yours' : undefined}>
              {s.player} ({s.ovr}) → {s.team === userTeam ? 'you' : s.team} · {contractLine(s.salary, s.years)}
            </div>
          ))}
          {deals.length > SHOWN_DEALS && (
            <button type="button" className="fa-night-more" onClick={() => setAllDeals((v) => !v)}>
              {allDeals ? 'Fewer signings' : `Show all ${deals.length} signings`}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
