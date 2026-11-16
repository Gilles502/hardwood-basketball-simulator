import React, { useMemo, useState } from 'react';
import type { FuturePick, PlayerDetails, TeamData } from '../../store/leagueStore';
import { normalizeRole } from '../../utils/roles';

/** Cap lines from /api/team-strategy-intel; the page may not have them yet. */
export interface TeamFinancials {
  payroll: number;
  salary_cap: number;
  luxury_tax_threshold: number;
  salary_floor: number;
}

interface ContractsTabProps {
  team: TeamData;
  financials: TeamFinancials | null;
  standing: string | null;
  onOpenPlayer: (name: string) => void;
}

type SortKey = 'name' | 'pos' | 'age' | 'ovr' | 'pot' | 'salary' | 'years' | 'gp' | 'pts' | 'reb' | 'ast';
type StatView = 'rs' | 'po';

const ROSTER_LIMIT = 15;
const YEAR_PIPS = 5;
const POSITION_ORDER = ['PG', 'SG', 'SF', 'PF', 'C'];

const money = (value: number) => `$${value.toFixed(1)}M`;

const ovrTier = (ovr: number) => (ovr >= 90 ? 't90' : ovr >= 84 ? 't80' : ovr >= 77 ? 't70' : 't0');

const isFinalYear = (p: PlayerDetails) => Boolean(p.contract_data && p.contract_data.years <= 1);

const gamesPlayed = (p: PlayerDetails, view: StatView) => (view === 'rs' ? p.gp_rs ?? 0 : p.gp_po ?? 0);

const statLine = (p: PlayerDetails, view: StatView) => {
  if (gamesPlayed(p, view) === 0) return null;
  return view === 'rs' ? p.stats_rs : p.stats_po;
};

const sortValue = (p: PlayerDetails, key: SortKey, view: StatView): number | string => {
  const stats = statLine(p, view);
  switch (key) {
    case 'name': return p.nome;
    case 'pos': return POSITION_ORDER.indexOf(normalizeRole(p.ruolo));
    case 'age': return p.eta;
    case 'ovr': return p.ovr;
    case 'pot': return p.pot;
    case 'salary': return p.contract_data?.salary ?? 0;
    case 'years': return p.contract_data?.years ?? 0;
    case 'gp': return gamesPlayed(p, view);
    // Players with no line sort below everyone who has one.
    case 'pts': return stats ? stats.ppg : -1;
    case 'reb': return stats ? stats.rpg : -1;
    case 'ast': return stats ? stats.apg : -1;
  }
};

// Name and position read naturally A→Z / PG→C; everything else starts with the biggest number.
const ASCENDING_FIRST: SortKey[] = ['name', 'pos'];

const COLUMNS: { key: SortKey; label: string; width: string; className?: string }[] = [
  { key: 'name', label: 'Player', width: '27%', className: 'is-left' },
  { key: 'pos', label: 'Pos', width: '6%' },
  { key: 'age', label: 'Age', width: '6%' },
  { key: 'ovr', label: 'OVR', width: '7%' },
  { key: 'pot', label: 'POT', width: '7%' },
  { key: 'salary', label: 'Salary', width: '11%', className: 'is-money' },
  { key: 'years', label: 'Years', width: '12%' },
  { key: 'gp', label: 'GP', width: '6%' },
  { key: 'pts', label: 'PTS', width: '6%' },
  { key: 'reb', label: 'REB', width: '6%' },
  { key: 'ast', label: 'AST', width: '6%' },
];

const isProtected = (protection: string) => Boolean(protection) && protection !== 'Unprotected' && protection !== 'None';

/** Payroll tile: payroll against the floor, cap and luxury tax lines. */
const PayrollTile: React.FC<{ payroll: number; financials: TeamFinancials | null }> = ({ payroll, financials }) => {
  if (!financials) {
    return (
      <div className="rc-tile">
        <span className="rc-label">Payroll</span>
        <div className="rc-big">{money(payroll)}</div>
        <span className="rc-note">Cap figures unavailable</span>
      </div>
    );
  }

  const { salary_cap: cap, luxury_tax_threshold: tax, salary_floor: floor } = financials;
  // The bar starts just under the floor so the three lines stay readable apart.
  const low = Math.min(floor * 0.8, payroll);
  const high = Math.max(tax * 1.1, payroll * 1.05);
  const pct = (value: number) => `${Math.min(100, Math.max(0, ((value - low) / (high - low)) * 100))}%`;

  let status: string;
  let bad = false;
  if (payroll < floor) {
    status = `${money(floor - payroll)} below the salary floor`;
    bad = true;
  } else if (payroll <= cap) {
    status = `${money(cap - payroll)} of cap space`;
  } else if (payroll <= tax) {
    status = `over the cap · ${money(tax - payroll)} under the tax`;
  } else {
    status = `${money(payroll - tax)} over the luxury tax`;
    bad = true;
  }

  return (
    <div className="rc-tile">
      <div className="rc-pay-head">
        <span className="rc-label">Payroll</span>
        <span><span className="rc-big">{money(payroll)}</span> <span className={`rc-pay-status${bad ? ' is-bad' : ''}`}>· {status}</span></span>
      </div>
      <div
        className="rc-capbar"
        role="img"
        aria-label={`Payroll ${money(payroll)}. Floor ${money(floor)}, cap ${money(cap)}, luxury tax ${money(tax)}.`}
      >
        <i className={payroll > tax ? 'is-tax' : undefined} style={{ width: pct(payroll) }} />
        {[['Floor', floor], ['Cap', cap], ['Tax', tax]].map(([label, value]) => (
          <div key={label} className="rc-mark" style={{ left: pct(value as number) }}>
            <span>{label}</span>
            <em>{money(value as number)}</em>
          </div>
        ))}
      </div>
    </div>
  );
};

const YearPips: React.FC<{ player: PlayerDetails }> = ({ player }) => {
  const contract = player.contract_data;
  if (!contract) return <span>–</span>;
  const left = Math.max(0, contract.years);
  const option = contract.player_option ? 'PO' : contract.team_option ? 'TO' : null;
  return (
    <span title={`${left} ${left === 1 ? 'season' : 'seasons'} left${option ? ` · ${option === 'PO' ? 'player' : 'team'} option` : ''}`}>
      <span className="rc-pips" aria-label={`${left} ${left === 1 ? 'season' : 'seasons'} left`}>
        <b>{'●'.repeat(Math.min(left, YEAR_PIPS))}</b>{'●'.repeat(Math.max(0, YEAR_PIPS - left))}
      </span>
      {option && <span className="rc-opt">{option}</span>}
    </span>
  );
};

const InjuryChip: React.FC<{ player: PlayerDetails }> = ({ player }) => {
  const games = player.giorni_infortunio_rimanenti ?? 0;
  const injury = player.infortunio_nome || player.tipo_infortunio;
  if (player.is_day_to_day) {
    return <span className="rc-chip is-dtd" title={`Day-to-day: ${injury || 'minor injury'} (${games} games)`}>DTD</span>;
  }
  if (player.infortunato) {
    return <span className="rc-chip is-out" title={`Injured: ${injury || 'out'} (${games} games)`}>Out {games}g</span>;
  }
  return null;
};

/** One kraft folder per future draft: owned tickets, picks coming in via trades, and picks owed out. */
const DraftFolder: React.FC<{ draft: FuturePick }> = ({ draft }) => {
  const owned = [...draft.owned].sort((a, b) => a.round - b.round || Number(b.is_own) - Number(a.is_own));
  const owed = [...(draft.traded ?? [])].sort((a, b) => a.round - b.round);
  return (
    <div className="rc-folder">
      <span className="rc-folder-year">{draft.year}{draft.year_offset === 1 && <small>next</small>}</span>
      {owned.map((pick) => (
        <div key={`own-${pick.round}-${pick.original_owner}`} className={`rc-ticket${pick.round === 2 ? ' is-r2' : ''}`}>
          <div className="rc-ticket-round"><small>RD</small>{pick.round}</div>
          <div className="rc-ticket-body" title={pick.is_own ? undefined : `Originally ${pick.original_owner}'s pick`}>
            <b>{pick.is_own ? 'Own' : pick.original_owner}</b>
            {isProtected(pick.protection)
              ? <small className="is-prot">{pick.protection} prot.</small>
              : <small>{pick.is_own ? ' ' : 'from a trade'}</small>}
          </div>
          {!pick.is_own && <span className="rc-stamp is-via">VIA</span>}
        </div>
      ))}
      {owed.map((pick) => (
        <div key={`owed-${pick.round}`} className={`rc-ticket is-owed${pick.round === 2 ? ' is-r2' : ''}`}>
          <div className="rc-ticket-round"><small>RD</small>{pick.round}</div>
          <div className="rc-ticket-body" title={`Owed to ${pick.current_owner}`}>
            <b>{pick.current_owner}</b>
            <small className={isProtected(pick.protection) ? 'is-prot' : undefined}>
              {isProtected(pick.protection) ? `${pick.protection} prot.` : 'has it'}
            </small>
          </div>
          <span className="rc-stamp">OWED</span>
        </div>
      ))}
      {owned.length === 0 && owed.length === 0 && <div className="rc-folder-empty">No picks</div>}
    </div>
  );
};

export const ContractsTab: React.FC<ContractsTabProps> = ({ team, financials, standing, onOpenPlayer }) => {
  const [view, setView] = useState<StatView>('rs');
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: 'ovr', asc: false });

  const players = useMemo(() => {
    const dir = sort.asc ? 1 : -1;
    return [...team.roster].sort((a, b) => {
      const av = sortValue(a, sort.key, view);
      const bv = sortValue(b, sort.key, view);
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : av - (bv as number);
      return cmp * dir || b.ovr - a.ovr;
    });
  }, [team.roster, sort, view]);

  const onSort = (key: SortKey) => {
    setSort((prev) => (prev.key === key ? { key, asc: !prev.asc } : { key, asc: ASCENDING_FIRST.includes(key) }));
  };

  const [wins, losses] = team.record.split('-').map(Number);
  const played = wins + losses;
  const winPct = played > 0 ? (wins / played).toFixed(3).replace(/^0/, '') : '.000';

  const expiring = team.roster.filter(isFinalYear);
  const expiringMoney = expiring.reduce((sum, p) => sum + (p.contract_data?.salary ?? 0), 0);
  const spotsLeft = ROSTER_LIMIT - team.roster.length;
  const rosterNote = spotsLeft > 0
    ? `${spotsLeft} open ${spotsLeft === 1 ? 'spot' : 'spots'}`
    : spotsLeft === 0 ? 'Roster full' : `${-spotsLeft} over the limit`;

  const drafts = team.future_picks ?? [];
  const firsts = drafts.reduce((n, d) => n + d.owned.filter((p) => p.round === 1).length, 0);
  const seconds = drafts.reduce((n, d) => n + d.owned.filter((p) => p.round === 2).length, 0);
  const owedOut = drafts.reduce((n, d) => n + (d.traded?.length ?? 0), 0);

  return (
    <div className="rc-root">
      <div className="rc-tiles">
        <div className="rc-tile">
          <span className="rc-label">Roster</span>
          <div className="rc-big">{team.roster.length}<small> / {ROSTER_LIMIT}</small></div>
          <span className={`rc-note${spotsLeft < 0 ? ' is-bad' : ''}`}>{rosterNote}</span>
        </div>
        <PayrollTile payroll={team.payroll} financials={financials} />
        <div className="rc-tile">
          <span className="rc-label">Record</span>
          <div className="rc-big">{team.record.replace('-', '–')}</div>
          <span className="rc-note">{winPct}{standing ? ` · ${standing}` : ''}</span>
        </div>
        <div className="rc-tile">
          <span className="rc-label">Expiring</span>
          <div className="rc-big is-hot">{money(expiringMoney)}</div>
          <span className="rc-note">{expiring.length === 0 ? 'No deals end this summer' : `${expiring.length} ${expiring.length === 1 ? 'deal ends' : 'deals end'} this summer`}</span>
        </div>
      </div>

      <div className="rc-card">
        <div className="rc-card-head">
          <span className="rc-card-title">Contracted players</span>
          <div className="rc-seg" role="group" aria-label="Stats shown">
            <button type="button" aria-pressed={view === 'rs'} onClick={() => setView('rs')}>Season</button>
            <button type="button" aria-pressed={view === 'po'} onClick={() => setView('po')}>Playoffs</button>
          </div>
        </div>
        {players.length === 0 ? (
          <div className="rc-empty">No players under contract.</div>
        ) : (
          <table className="rc-table">
            <colgroup>{COLUMNS.map((c) => <col key={c.key} style={{ width: c.width }} />)}</colgroup>
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    className={c.className}
                    aria-sort={sort.key === c.key ? (sort.asc ? 'ascending' : 'descending') : undefined}
                  >
                    <button type="button" onClick={() => onSort(c.key)}>
                      {view === 'po' && ['gp', 'pts', 'reb', 'ast'].includes(c.key) ? `PO ${c.label}` : c.label}
                      {sort.key === c.key && (sort.asc ? ' ▴' : ' ▾')}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {players.map((p) => {
                const stats = statLine(p, view);
                const statClass = view === 'po' && stats ? 'is-po' : undefined;
                return (
                  <tr key={p.nome}>
                    <td className="is-left">
                      <button type="button" className="rc-name" onClick={() => onOpenPlayer(p.nome)}>{p.nome}</button>
                      <InjuryChip player={p} />
                      {isFinalYear(p) && <span className="rc-chip is-final" title="Contract ends this summer">Final yr</span>}
                    </td>
                    <td className="rc-pos">{normalizeRole(p.ruolo)}</td>
                    <td>{p.eta}</td>
                    <td className={`rc-ovr ${ovrTier(p.ovr)}`}>{p.ovr}</td>
                    <td>{p.pot}</td>
                    <td className="rc-money">{p.contract_data ? money(p.contract_data.salary) : '–'}</td>
                    <td><YearPips player={p} /></td>
                    <td>{gamesPlayed(p, view)}</td>
                    <td className={statClass}>{stats ? stats.ppg.toFixed(1) : '–'}</td>
                    <td className={statClass}>{stats ? stats.rpg.toFixed(1) : '–'}</td>
                    <td className={statClass}>{stats ? stats.apg.toFixed(1) : '–'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div>
        <div className="rc-picks-head">
          <span className="rc-card-title">Draft picks</span>
          <span className="rc-note">
            {firsts} {firsts === 1 ? 'first' : 'firsts'} · {seconds} {seconds === 1 ? 'second' : 'seconds'}
            {owedOut > 0 && ` · ${owedOut} owed to other teams`}
          </span>
        </div>
        {drafts.length === 0 ? (
          <div className="rc-empty">No draft picks on record.</div>
        ) : (
          <div className="rc-folders">
            {drafts.map((d) => <DraftFolder key={d.year} draft={d} />)}
          </div>
        )}
      </div>
    </div>
  );
};
