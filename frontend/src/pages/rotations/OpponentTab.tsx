import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Save, X } from 'lucide-react';
import { TeamCrest } from '../../components/TeamCrest';
import { defenseVs, rebuildReport } from './scouting';
import type { MyPlayer, OpponentPlan, ReportRow, ScoutCfg, Skill, TheirPlayer } from './scouting';

interface OpponentData {
  team: { name: string; record: string; conference: string | null; rank: number | null } | null;
  context:
    | { kind: 'series'; round: string; user_wins: number; opp_wins: number; game_number: number }
    | { kind: 'game'; date: string; is_home: boolean }
    | null;
  teams: string[];
  their_players: TheirPlayer[];
  my_players: MyPlayer[];
  plan: OpponentPlan;
  config: ScoutCfg;
}

interface OpponentTabProps {
  onDirtyChange: (dirty: boolean) => void;
}

const EMPTY_PLAN: OpponentPlan = { matchups: {}, double_teams: [] };
const DEF_LABEL: Record<Skill, string> = { '3PT': 'Per D', DRIVE: 'Per D', POST: 'Int D' };
const lastName = (name: string): string => name.split(' ').slice(-1)[0];

const kindOf = (r: ReportRow): string => {
  if (r.threat === '3PT') return r.threat_value >= 85 ? 'Elite shooter' : 'Shooter';
  if (r.threat === 'DRIVE') return r.threat_value >= 85 ? 'Elite slasher' : 'Slasher';
  return r.threat_value >= 85 ? 'Dominant post scorer' : 'Post scorer';
};

const gapLabel = (r: ReportRow): string => (r.badge === 'fine' ? (r.gap >= 0 ? 'covered' : `${r.gap}`) : `${r.gap}`);

const formatDate = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

const ordinal = (n: number): string => {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  return `${n}${teen ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'}`;
};

const roundLabel = (round: string): string => round.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

export const OpponentTab: React.FC<OpponentTabProps> = ({ onDirtyChange }) => {
  const [data, setData] = useState<OpponentData | null>(null);
  const [plan, setPlan] = useState<OpponentPlan>(EMPTY_PLAN);
  const [saved, setSaved] = useState<OpponentPlan>(EMPTY_PLAN);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);

  const dirty = JSON.stringify(plan) !== JSON.stringify(saved);
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);

  const load = useCallback(async (team?: string) => {
    setLoading(true);
    setMessage(null);
    try {
      const query = team ? `?team=${encodeURIComponent(team)}&` : '?';
      const res = await fetch(`/api/team-manager/opponent${query}_t=${Date.now()}`);
      if (res.status === 404) {
        // An older backend still running without this endpoint answers with an HTML 404 page
        setMessage({ tone: 'error', text: 'The game server is out of date. Restart it to use the Opponent tab.' });
        return;
      }
      const json = await res.json();
      if (json.error) {
        setMessage({ tone: 'error', text: json.error });
      } else {
        setData(json);
        setPlan(json.plan || EMPTY_PLAN);
        setSaved(json.plan || EMPTY_PLAN);
      }
    } catch {
      setMessage({ tone: 'error', text: 'Could not load the opponent.' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const report = useMemo(
    () => (data?.team ? rebuildReport(data.their_players, data.my_players, plan, data.config) : []),
    [data, plan],
  );

  const changeTeam = (team: string) => {
    if (dirty && !window.confirm(`Discard your unsaved plan for ${data?.team?.name}?`)) return;
    load(team);
  };

  const assign = (theirName: string, myName: string) => {
    const matchups = { ...plan.matchups };
    if (myName) matchups[theirName] = myName;
    else delete matchups[theirName];
    setPlan({ ...plan, matchups });
  };

  const toggleDouble = (name: string) => {
    const doubles = plan.double_teams.includes(name) ? plan.double_teams.filter((n) => n !== name) : [...plan.double_teams, name];
    setPlan({ ...plan, double_teams: doubles });
  };

  const save = async () => {
    if (!data?.team) return;
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch('/api/team-manager/opponent-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team: data.team.name, ...plan }),
      });
      const json = await res.json();
      if (json.error) {
        setMessage({ tone: 'error', text: json.error });
      } else {
        setPlan(json.plan);
        setSaved(json.plan);
        setMessage({ tone: 'ok', text: `Plan saved. It is used in every game against ${data.team.name}.` });
      }
    } catch {
      setMessage({ tone: 'error', text: 'Unable to save to server.' });
    } finally {
      setSaving(false);
    }
  };

  if (loading && !data) {
    return <div className="op-loading"><div className="spinner" /></div>;
  }

  const picker = (
    <select className="op-picker" value={data?.team?.name ?? ''} onChange={(e) => changeTeam(e.target.value)} aria-label="Prepare for another team">
      {!data?.team && <option value="">Pick a team…</option>}
      {(data?.teams ?? []).map((t) => <option key={t} value={t}>{t}</option>)}
    </select>
  );

  // The request failed: say so instead of pretending there is no game
  if (!data) {
    return (
      <div className="lu-root">
        <div className="op-strip">
          <div className="op-who"><b>Opponent unavailable</b><span>{message?.text ?? 'Could not load the opponent.'}</span></div>
          <div className="op-actions"><button type="button" className="btn btn-secondary" onClick={() => load()}>Try again</button></div>
        </div>
      </div>
    );
  }

  if (!data.team) {
    return (
      <div className="lu-root">
        <div className="op-strip">
          <div className="op-who"><b>No game scheduled</b><span>Pick a team to prepare for.</span></div>
          <div className="op-actions">{picker}</div>
        </div>
        {message && <p className={`op-msg is-${message.tone}`}>{message.text}</p>}
      </div>
    );
  }

  const { team, context } = data;
  const mine = new Map(data.my_players.map((p) => [p.name, p]));
  const healthyMine = data.my_players.filter((p) => !p.injured);
  const bad = report.filter((r) => r.badge === 'bad').length;
  const setCount = Object.keys(plan.matchups).length;
  // Assignments: starters in court order, then the bench by minutes
  const order = ['PG', 'SG', 'SF', 'PF', 'C'];
  const assignments = [...report].sort((a, b) =>
    a.starter !== b.starter ? (a.starter ? -1 : 1)
      : a.starter ? order.indexOf(a.pos) - order.indexOf(b.pos)
        : b.minutes - a.minutes);
  const suggestions = report.filter((r) => !plan.double_teams.includes(r.name)).slice(0, 5);

  return (
    <div className="lu-root">
      <div className="op-strip">
        <TeamCrest name={team.name} size={46} />
        <div className="op-who">
          <span>
            {context?.kind === 'series'
              ? <span className="op-tag">Playoffs · {roundLabel(context.round)} · Game {context.game_number} · series {context.user_wins}-{context.opp_wins}</span>
              : context?.kind === 'game'
                ? `Next game · ${formatDate(context.date)}, ${context.is_home ? 'home' : 'away'}`
                : 'No game scheduled against them'}
          </span>
          <b>{team.name}</b>
          <span>{team.record}{team.rank ? ` · ${ordinal(team.rank)} ${team.conference}` : ''}</span>
        </div>
        <div className="op-actions">
          {picker}
          <button type="button" className="btn btn-primary" onClick={save} disabled={!dirty || saving}>
            <Save size={16} /> {dirty ? `Save plan for ${team.name}` : 'Plan saved'}
          </button>
        </div>
      </div>
      {message && <p className={`op-msg is-${message.tone}`} role="status">{message.text}</p>}

      <div className="op-cards">
        {/* Scouting report: their threats, most dangerous first */}
        <section className="lu-paper" aria-label="Scouting report">
          <div className="lu-band"><span>Scouting report · biggest threats</span><span>{bad ? `${bad} bad matchup${bad > 1 ? 's' : ''}` : 'No bad matchups'}</span></div>
          {report.map((r, i) => {
            const doubled = plan.double_teams.includes(r.name);
            return (
              <div key={r.name} className={`op-row${r.badge === 'bad' ? ' is-bad' : ''}`}>
                <span className="op-rank">{i + 1}</span>
                <div className="op-main">
                  <b className="op-name">{r.name} <small>· {r.starter ? r.pos : `bench ${r.pos}`}</small></b>
                  <span className="op-why">
                    {kindOf(r)} ({r.threat} {r.threat_value}).{' '}
                    {r.defender
                      ? <>Guarded by <b>{lastName(r.defender)}</b>{r.auto ? ' (auto)' : ''}, {DEF_LABEL[r.threat]} {r.defense}.</>
                      : 'Nobody to guard him.'}
                    {' '}<span className={`op-gap is-${r.badge}`}>{gapLabel(r)}</span>
                    {doubled && <span className="op-gap is-double">doubled</span>}
                  </span>
                </div>
                {r.fix ? (
                  <button type="button" className="op-fix" onClick={() => assign(r.name, r.fix!)}>Put {lastName(r.fix)} on him</button>
                ) : i < 3 && !doubled ? (
                  <button type="button" className="op-fix is-soft" onClick={() => toggleDouble(r.name)}>Double him</button>
                ) : <span />}
              </div>
            );
          })}
          {report.length === 0 && <p className="lu-empty">They have no healthy players in their rotation.</p>}
        </section>

        {/* Your assignments and double-teams for this team */}
        <section className="lu-paper is-kraft" aria-label="Your assignments">
          <div className="lu-band"><span>Your assignments</span><span>{setCount ? `${setCount} set` : 'All auto'}</span></div>
          {assignments.map((r) => {
            const options = [...healthyMine].sort((a, b) => defenseVs(b, r.threat) - defenseVs(a, r.threat));
            const auto = data.their_players.find((t) => t.name === r.name)?.auto_defender;
            return (
              <div key={r.name} className="op-asg">
                <span className="op-asg-who"><b>{lastName(r.name)}</b><small>{r.starter ? r.pos : 'bench'} · {r.threat}</small></span>
                <select value={plan.matchups[r.name] && mine.get(plan.matchups[r.name]) ? plan.matchups[r.name] : ''} onChange={(e) => assign(r.name, e.target.value)} aria-label={`Who guards ${r.name}`}>
                  <option value="">Auto{auto ? ` (${auto})` : ''}</option>
                  {options.map((p) => (
                    <option key={p.name} value={p.name}>{p.name} · {DEF_LABEL[r.threat]} {defenseVs(p, r.threat)}</option>
                  ))}
                </select>
                <span className={`op-gap is-${r.badge}`}>{r.gap > 0 ? `+${r.gap}` : r.gap}</span>
              </div>
            );
          })}
          <div className="lu-divider">Double-team</div>
          <div className="op-chips">
            {plan.double_teams.length === 0 && <span className="op-note">Nobody yet.</span>}
            {plan.double_teams.map((n) => (
              <button type="button" key={n} className="op-chip is-on" onClick={() => toggleDouble(n)} aria-label={`Stop doubling ${n}`}>
                {n} <X size={13} />
              </button>
            ))}
            {suggestions.map((r) => (
              <button type="button" key={r.name} className="op-chip" onClick={() => toggleDouble(r.name)}>+ {r.name}</button>
            ))}
          </div>
          <p className="op-note op-pad">A defender only takes his man while both are on the floor; the player he leaves is picked up by the teammate whose man he took. Traps come on isolations and post-ups.</p>
        </section>
      </div>
    </div>
  );
};
