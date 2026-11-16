// File: frontend/src/components/TradeHistoryLog.tsx
import React, { useState, useEffect, useMemo } from 'react';
import { Search, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import { TeamCrest } from './TeamCrest';
import { crestLabel } from '../utils/crest';
// Pills, chips and empty states are shared with the Trade pages
import '../pages/trades/TradeMachine.css';
import '../pages/trades/TradeTabs.css';
import './TradeHistoryLog.css';
import { normalizeRole, isRole } from '../utils/roles';

export interface TradePlayerItem {
  name: string;
  ovr?: number;
  ruolo?: string;
  salary?: number;
  trade_value?: number;
  gp?: number;
  ppg?: number;
  rpg?: number;
  apg?: number;
}

export interface TradeTeamEntry {
  team_name: string;
  grade?: string;
  grade_color?: string;
  grade_bg?: string;
  grade_explanation?: string;
  players_sent?: TradePlayerItem[];
  picks_sent?: string[];
  players_received?: TradePlayerItem[];
  picks_received?: string[];
  players_received_stats?: TradePlayerItem[];
  wins_pre?: number;
  losses_pre?: number;
  win_pct_pre?: number;
  games_post?: number;
  wins_post?: number;
  losses_post?: number;
  win_pct_post?: number;
  delta_win_pct?: number;
  delta_net_rtg?: number;
  delta_ppg?: number;
  verdict?: string;
  verdict_type?: string;
}

export interface StructuredTrade {
  id: string;
  season: number;
  game_day?: number;
  type: string;
  reason?: string;
  date_recorded?: string;
  winner_team_name?: string;
  editorial_headline?: string;
  why?: string;
  trade_type?: string;
  motives?: SideMotiveView[];
  teams: TradeTeamEntry[];
}

// The GM notebook: one entry per side, sent by the server without engine numbers
export interface SideMotiveView {
  team: string;
  gm_name: string | null;
  trade_skill: number | null;
  plan: string;
  traits: string[];
  need: string | null;
  reasons: string[];
}

// Same labels as CONFIG.FRONT_OFFICE.TRAITS; an unknown code is shown as plain words
const TRAIT_LABELS: Record<string, string> = {
  PICK_HOARDER: 'Pick hoarder',
  YOUTH_FIRST: 'Youth first',
  TRADE_HAPPY: 'Trade happy',
  VETERAN_LOVER: 'Veteran lover',
  STAR_CHASER: 'Star chaser',
  DEFENSE_FIRST: 'Defense first',
  OFFENSE_FIRST: 'Offense first',
  CAP_GUARDIAN: 'Cap guardian',
  LOYALIST: 'Loyalist',
  PATIENT_BUILDER: 'Patient builder',
};
const traitLabel = (code: string): string =>
  TRAIT_LABELS[code] || (code.charAt(0) + code.slice(1).toLowerCase()).replace(/_/g, ' ');
const planLabel = (plan: string): string => `Plan: ${plan.charAt(0)}${plan.slice(1).toLowerCase().replace(/_/g, ' ')}`;

interface TradeHistoryLogProps {
  initialRawTrades?: string[];
  currentTeamName?: string | null;
  currentSeason?: number;
}

const formatPosition = (pos: string): string => normalizeRole(pos);

// Fallback Parser for raw text strings from older logs
const parseRawTradeString = (s_line: string, idx: number): StructuredTrade | null => {
  if (!s_line) return null;
  try {
    let clean = s_line;
    let reason = "Market Deal";
    if (clean.includes("Reason:")) {
      const parts = clean.split("Reason:");
      clean = parts[0].trim();
      reason = parts[1].trim();
    }
    // "SCAMBIO:" is the legacy (Italian) prefix, kept so old saves still parse
    if (clean.includes("TRADE:")) {
      clean = clean.split("TRADE:")[1].trim();
    } else if (clean.includes("SCAMBIO:")) {
      clean = clean.split("SCAMBIO:")[1].trim();
    }

    if (clean.includes("<-->")) {
      const parts = clean.split("<-->");
      if (parts.length === 2) {
        const parseSide = (str: string) => {
          // "sends" is the current verb; "cede" is the legacy Italian one found in old saves
          const verb = /\b(sends|cede)\b/.exec(str);
          const tName = verb ? str.slice(0, verb.index).trim().replace(/[\[\]]/g, '') : "Team A";
          const assetStr = verb ? str.slice(verb.index + verb[0].length).trim() : "";
          const cleanAst = assetStr.replace(/[\[\]]/g, '');
          const items = cleanAst.split(',').map(s => s.trim()).filter(Boolean);

          const players: TradePlayerItem[] = [];
          const picks: string[] = [];

          items.forEach(item => {
            if (item.includes('R1') || item.includes('R2') || item.includes('Pick') || item.includes('Scelta') || item.includes('200') || item.includes('201')) {
              picks.push(item);
            } else {
              let pName = item;
              let ovr = 78;
              let ruolo = 'SG';
              let sal = 0;
              if (item.includes('(')) {
                pName = item.split('(')[0].trim();
                const ins = item.split('(')[1].replace(')', '');
                ins.split(',').forEach(tok => {
                  const t = tok.trim();
                  if (!isNaN(Number(t))) ovr = Number(t);
                  else if (isRole(normalizeRole(t))) ruolo = normalizeRole(t);
                  else if (t.includes('$') || t.includes('M')) sal = parseFloat(t.replace('$', '').replace('M', '')) || 0;
                });
              }
              players.push({ name: pName, ovr, ruolo, salary: sal });
            }
          });

          return { team_name: tName, players, picks };
        };

        const side1 = parseSide(parts[0]);
        const side2 = parseSide(parts[1]);

        return {
          id: `raw_trade_${idx + 1}`,
          season: 1,
          type: "2-Team",
          reason,
          date_recorded: "Regular Season",
          teams: [
            {
              team_name: side1.team_name,
              players_sent: side1.players,
              picks_sent: side1.picks,
              players_received: side2.players,
              picks_received: side2.picks
            },
            {
              team_name: side2.team_name,
              players_sent: side2.players,
              picks_sent: side2.picks,
              players_received: side1.players,
              picks_received: side1.picks
            }
          ]
        };
      }
    }
  } catch (e) {
    console.error("Error parsing raw trade string:", e);
  }
  return null;
};

export const TradeHistoryLog: React.FC<TradeHistoryLogProps> = ({
  initialRawTrades = [],
  currentTeamName,
  currentSeason = 1
}) => {
  const [trades, setTrades] = useState<StructuredTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null);

  // Filters State
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTeam, setFilterTeam] = useState<string>('all');
  const [filterType, setFilterType] = useState<'all' | '2-team' | '3-team'>('all');
  const [filterSeason, setFilterSeason] = useState<string>('all');

  const fetchTradeHistory = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/trade-history?_t=${Date.now()}`);
      const data = await response.json();
      if (data.trades && data.trades.length > 0) {
        setTrades(data.trades);
      } else if (initialRawTrades.length > 0) {
        const parsed = initialRawTrades
          .map((s, idx) => parseRawTradeString(s, idx))
          .filter(Boolean) as StructuredTrade[];
        setTrades(parsed);
      } else {
        setTrades([]);
      }
    } catch (err) {
      if (initialRawTrades.length > 0) {
        const parsed = initialRawTrades
          .map((s, idx) => parseRawTradeString(s, idx))
          .filter(Boolean) as StructuredTrade[];
        setTrades(parsed);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTradeHistory();
  }, [initialRawTrades]);

  // Extract all unique teams for filter dropdown
  const allTeams = useMemo(() => {
    const teamsSet = new Set<string>();
    trades.forEach(tr => {
      tr.teams.forEach(t => {
        if (t.team_name) teamsSet.add(t.team_name);
      });
    });
    return Array.from(teamsSet).sort();
  }, [trades]);

  // Extract all unique seasons for filter dropdown
  const allSeasons = useMemo(() => {
    const seasonsSet = new Set<number>();
    if (currentSeason) seasonsSet.add(currentSeason);
    trades.forEach(tr => {
      if (tr.season) seasonsSet.add(tr.season);
    });
    return Array.from(seasonsSet).sort((a, b) => b - a);
  }, [trades, currentSeason]);

  // Filtered trades list
  const filteredTrades = useMemo(() => {
    return trades.filter(tr => {
      // Team filter
      if (filterTeam !== 'all') {
        const hasTeam = tr.teams.some(t => t.team_name?.toLowerCase() === filterTeam.toLowerCase());
        if (!hasTeam) return false;
      }

      // Type filter
      if (filterType === '2-team' && tr.type?.includes('3-Team')) return false;
      if (filterType === '3-team' && !tr.type?.includes('3-Team')) return false;

      // Season filter
      if (filterSeason !== 'all' && String(tr.season) !== filterSeason) return false;

      // Text search
      if (searchTerm.trim()) {
        const q = searchTerm.toLowerCase();
        const matchesHeadline = tr.editorial_headline?.toLowerCase().includes(q) || tr.reason?.toLowerCase().includes(q);
        const matchesTeam = tr.teams.some(t => t.team_name?.toLowerCase().includes(q));
        const matchesPlayer = tr.teams.some(t =>
          (t.players_sent || []).some(p => p.name?.toLowerCase().includes(q)) ||
          (t.players_received || []).some(p => p.name?.toLowerCase().includes(q))
        );
        const matchesPick = tr.teams.some(t =>
          (t.picks_sent || []).some(pk => pk?.toLowerCase().includes(q)) ||
          (t.picks_received || []).some(pk => pk?.toLowerCase().includes(q))
        );
        if (!matchesHeadline && !matchesTeam && !matchesPlayer && !matchesPick) {
          return false;
        }
      }

      return true;
    });
  }, [trades, filterTeam, filterType, filterSeason, searchTerm]);

  // Header numbers for the stat strip
  const stats = useMemo(() => {
    const perTeam = new Map<string, number>();
    let topPlayer: { name: string; ovr: number } | null = null;
    trades.forEach((tr) => {
      tr.teams.forEach((t) => {
        if (t.team_name) perTeam.set(t.team_name, (perTeam.get(t.team_name) || 0) + 1);
        (t.players_sent || []).forEach((p) => {
          if (p.ovr !== undefined && (!topPlayer || p.ovr > topPlayer.ovr)) topPlayer = { name: p.name, ovr: p.ovr };
        });
      });
    });
    const busiest = [...perTeam.entries()].sort((a, b) => b[1] - a[1])[0];
    return {
      total: trades.length,
      threeTeam: trades.filter((t) => t.type?.includes('3-Team')).length,
      busiest: busiest ? `${busiest[0]} · ${busiest[1]}` : '—',
      topPlayer: topPlayer ? `${(topPlayer as { name: string; ovr: number }).name} · ${(topPlayer as { name: string; ovr: number }).ovr}` : '—',
    };
  }, [trades]);

  // Group consecutive trades that share a season and date label
  const groups = useMemo(() => {
    const out: { key: string; trades: StructuredTrade[] }[] = [];
    filteredTrades.forEach((tr) => {
      const key = `Season ${tr.season} · ${tr.date_recorded || 'Trade deadline'}`;
      const last = out[out.length - 1];
      if (last && last.key === key) last.trades.push(tr);
      else out.push({ key, trades: [tr] });
    });
    return out;
  }, [filteredTrades]);

  const renderAssets = (entry: TradeTeamEntry, side: 'in' | 'out') => {
    const players = (side === 'in' ? entry.players_received : entry.players_sent) || [];
    const picks = (side === 'in' ? entry.picks_received : entry.picks_sent) || [];
    if (players.length + picks.length === 0) {
      return <div className="tw-none">{side === 'in' ? 'Nothing (salary absorption)' : 'Nothing (cap space)'}</div>;
    }
    return (
      <>
        {players.map((p, i) => (
          <div className="tw-player" key={`${p.name}-${i}`}>
            <div>
              <b>{p.name}</b>
              {p.ruolo && <span className="tw-pos">{formatPosition(p.ruolo)}</span>}
            </div>
            <div className="tw-player-meta">
              {p.ovr ? <span className="tw-ovr">{p.ovr} OVR</span> : null}
              <span>{p.salary !== undefined && p.salary > 0 ? `$${p.salary.toFixed(1)}M/yr` : 'Contract on roster'}</span>
              {side === 'in' && p.ppg !== undefined && p.ppg > 0 && <span>{p.ppg} PPG · {p.rpg || 0} RPG · {p.apg || 0} APG</span>}
            </div>
          </div>
        ))}
        {picks.map((pk, i) => <div className="tw-pick" key={`${pk}-${i}`}>{pk}</div>)}
      </>
    );
  };

  return (
    <div className="tw-root">
      {/* Stat strip */}
      <div className="tw-stats">
        <div className="tw-stat"><span>Trades logged</span><b>{stats.total}</b></div>
        <div className="tw-stat"><span>3-team deals</span><b>{stats.threeTeam}</b></div>
        <div className="tw-stat"><span>Most active</span><b className="is-text">{stats.busiest}</b></div>
        <div className="tw-stat"><span>Top player moved</span><b className="is-text">{stats.topPlayer}</b></div>
      </div>

      {/* Filters */}
      <div className="tw-filters">
        <label className="tw-search">
          <Search size={16} aria-hidden="true" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search player, team or pick"
            aria-label="Search trades"
          />
        </label>
        <div className="tf-pills" role="group" aria-label="Trade type">
          {([['all', 'All'], ['2-team', '2-team'], ['3-team', '3-team']] as const).map(([id, label]) => (
            <button type="button" key={id} className={`tf-pill${filterType === id ? ' is-on' : ''}`} aria-pressed={filterType === id} onClick={() => setFilterType(id)}>{label}</button>
          ))}
        </div>
        <select className="tw-select" value={filterSeason} onChange={(e) => setFilterSeason(e.target.value)} aria-label="Season">
          <option value="all">All seasons</option>
          {allSeasons.map((s) => <option key={s} value={String(s)}>Season {s}</option>)}
        </select>
        <select className="tw-select" value={filterTeam} onChange={(e) => setFilterTeam(e.target.value)} aria-label="Team">
          <option value="all">All teams</option>
          {allTeams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button type="button" className="tw-refresh" onClick={fetchTradeHistory} title="Refresh trade log" aria-label="Refresh trade log">
          <RefreshCw size={15} />
        </button>
      </div>

      {loading ? (
        <div className="tm-empty"><div className="spinner" /></div>
      ) : filteredTrades.length === 0 ? (
        <div className="tm-empty">
          {trades.length === 0 ? 'No trades yet. Finished trades will show up here.' : 'No trades match these filters.'}
        </div>
      ) : (
        groups.map((group) => (
          <section key={group.key}>
            <div className="tw-day">{group.key}</div>
            {group.trades.map((trade, trIdx) => {
              const is3Team = !!trade.type?.includes('3-Team');
              const isExpanded = expandedTradeId === trade.id;
              const toggle = () => setExpandedTradeId(isExpanded ? null : trade.id);
              const mine = !!currentTeamName && trade.teams.some((t) => t.team_name === currentTeamName);
              const headline = trade.editorial_headline
                || (trade.teams.length === 2
                  ? `${trade.teams[0].team_name} and ${trade.teams[1].team_name} swap assets`
                  : `${trade.teams.map((t) => t.team_name).join(', ')} complete a blockbuster`);
              return (
                <div key={trade.id || trIdx} className={`tw-item${is3Team ? ' is-three' : ''}${isExpanded ? ' is-open' : ''}`}>
                  <div
                    className="tw-wire"
                    role="button"
                    tabIndex={0}
                    aria-expanded={isExpanded}
                    onClick={toggle}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } }}
                  >
                    <div className="tw-crests">
                      {trade.teams.map((t, i) => <TeamCrest key={`${t.team_name}-${i}`} name={t.team_name} size={34} />)}
                    </div>
                    <div className="tw-main">
                      <div className="tw-headline">
                        {headline}
                        <span className={`tw-tag${is3Team ? ' is-three' : ''}`}>{is3Team ? '3-team' : '2-team'}</span>
                        {mine && <span className="tw-tag is-mine">Your trade</span>}
                        {trade.winner_team_name && <span className="tw-tag is-winner">Winner · {trade.winner_team_name}</span>}
                      </div>
                      {trade.why && <div className="tw-why">Why: {trade.why}</div>}
                      <div className="tw-assets">
                        {trade.teams.map((t, i) => (
                          <span className="tw-gets" key={`${t.team_name}-${i}`}>
                            <em>{crestLabel(t.team_name)} gets</em>
                            {(t.players_received || []).map((p, pi) => <span className="tm-chip" key={`p${pi}`}>{p.name}{p.ovr ? <small>{p.ovr}</small> : null}</span>)}
                            {(t.picks_received || []).map((pk, pi) => <span className="tm-chip" key={`k${pi}`}>{pk}</span>)}
                            {(t.players_received || []).length + (t.picks_received || []).length === 0 && <small>nothing</small>}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="tw-side">
                      <div className="tw-grades">
                        {trade.teams.filter((t) => t.grade).map((t, i) => (
                          <span key={i} className={`tw-grade is-${(t.grade || 'B').charAt(0).toLowerCase()}`} title={`${t.team_name}: grade ${t.grade}`}>
                            {crestLabel(t.team_name)} {t.grade}
                          </span>
                        ))}
                      </div>
                      <span className="tw-more">{isExpanded ? 'Hide' : 'Details'} {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</span>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="tw-detail">
                      {trade.reason && <p className="tw-reason">“{trade.reason}”</p>}
                      {(trade.motives || []).some((m) => m.plan !== 'USER') && (
                        <div className="tw-notebook">
                          {(trade.motives || []).filter((m) => m.plan !== 'USER').map((m, mi) => (
                            <div className="tw-gm" key={`${m.team}-${mi}`}>
                              <b>{m.gm_name || `${m.team} GM`}</b>
                              <div className="tw-gm-who">
                                {m.team} GM{m.trade_skill !== null && m.trade_skill !== undefined ? ` · trade skill ${m.trade_skill}` : ''}
                              </div>
                              <div className="tw-gm-chips">
                                <span className="tw-chip is-plan">{planLabel(m.plan)}</span>
                                {(m.traits || []).map((t) => <span className="tw-chip is-trait" key={t}>{traitLabel(t)}</span>)}
                                {m.need && <span className="tw-chip is-need">Need: {m.need}</span>}
                              </div>
                              {(m.reasons || []).length > 0 && (
                                <ul className="tw-gm-reasons">
                                  {m.reasons.map((r, ri) => <li key={ri}>{r}</li>)}
                                </ul>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="tw-teams">
                        {trade.teams.map((t, i) => (
                          <div className="tw-team" key={`${t.team_name}-${i}`}>
                            <div className="tw-team-head">
                              <TeamCrest name={t.team_name} size={28} />
                              <b>{t.team_name}</b>
                              {t.grade && <span className={`tw-grade is-${t.grade.charAt(0).toLowerCase()}`}>Grade {t.grade}</span>}
                            </div>
                            <div className="tw-cap is-in">Receives</div>
                            {renderAssets(t, 'in')}
                            <div className="tw-cap is-out">Gives</div>
                            {renderAssets(t, 'out')}
                            {t.games_post !== undefined && t.games_post > 0 && (
                              <div className="tw-post">
                                <span>Since the trade: <b>{t.wins_post}-{t.losses_post}</b></span>
                                <span className={(t.delta_win_pct || 0) >= 0 ? 'is-up' : 'is-down'}>
                                  {(t.delta_win_pct || 0) >= 0 ? '+' : ''}{t.delta_win_pct}% win rate
                                </span>
                              </div>
                            )}
                            {(t.grade_explanation || t.verdict) && <p className="tw-verdict">{t.grade_explanation || t.verdict}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </section>
        ))
      )}
    </div>
  );
};
