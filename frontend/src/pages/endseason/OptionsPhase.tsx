// Phase 2 · Contract options ("player cards + ledger"): a card per option (team options are your call, player
// options the player's), next season's money adding up live on the right, and other teams' opt-outs.
// The choices travel with the hub's "Next" call. Payload: /api/offseason/options (server.py + core/end_season_views).
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import type { PhaseProps } from '../../utils/endSeason';

interface OptionItem {
  nome: string;
  ruolo: string;
  ovr: number;
  eta: number;
  salario: number;
  player_option: boolean;
  team_option: boolean;
  market_value: number;
  player_decision: 'ACCEPT' | 'DECLINE' | null;
  decision_reason: string | null;
  season: { ppg: number | null; rpg: number | null; apg: number | null; mpg: number | null };
  take: string | null;
}
interface Money {
  guaranteed: number; cap: number | null; tax: number | null; apron1: number | null; apron2: number | null;
  no_cap: boolean; exceptions: { above: number | null; label: string }[];
}
interface Around { name: string; team: string; ovr: number; salary: number; decision: 'in' | 'out' }

type Decision = 'PICKUP' | 'DECLINE';
const money = (v: number) => `$${v.toFixed(1)}M`;
const signedMoney = (v: number) => `${v >= 0 ? '+' : '−'}${money(Math.abs(v))}`;

export const OptionsPhase: React.FC<PhaseProps> = ({ readOnly, onBar }) => {
  const { leagueData, openPlayerProfile } = useLeagueStore();
  const [options, setOptions] = useState<OptionItem[] | null>(null);
  const [cash, setCash] = useState<Money | null>(null);
  const [around, setAround] = useState<{ list: Around[]; total: number }>({ list: [], total: 0 });
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [error, setError] = useState<string | null>(null);
  const hasTeam = Boolean(leagueData?.player_team_name);

  useEffect(() => {
    if (!hasTeam || readOnly) { setOptions([]); return; }
    let cancelled = false;
    fetch(`/api/offseason/options?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (!data.success) { setError(data.error || 'Could not load the contract options.'); setOptions([]); return; }
        const list: OptionItem[] = data.options || [];
        setOptions(list);
        setCash(data.money ?? null);
        setAround({ list: data.around_league || [], total: data.around_league_total || 0 });
        const initial: Record<string, Decision> = {};
        list.forEach((o) => { if (o.team_option) initial[o.nome] = 'PICKUP'; });
        setDecisions(initial);
      })
      .catch(() => { if (!cancelled) { setError('Could not load the contract options.'); setOptions([]); } });
    return () => { cancelled = true; };
  }, [hasTeam, readOnly]);

  useEffect(() => {
    onBar(options === null ? { blocking: 'Loading your contract options…' } : { payload: { decisions } });
  }, [options, decisions, onBar]);

  if (readOnly) {
    return <div className="eos-sheet"><p className="eos-muted">Options were settled when you moved on; the results are in Development &amp; retirements and on your roster.</p></div>;
  }
  if (options === null) return <div className="eos-sheet"><p className="eos-muted">Loading…</p></div>;

  const teamOptions = options.filter((o) => o.team_option);
  const playerOptions = options.filter((o) => o.player_option && !o.team_option);
  const kept = (o: OptionItem) => (o.team_option ? decisions[o.nome] === 'PICKUP' : o.player_decision !== 'DECLINE');
  const payroll = (cash?.guaranteed ?? 0) + options.filter(kept).reduce((sum, o) => sum + o.salario, 0);
  const exception = cash?.exceptions.filter((e) => e.above == null || payroll > e.above).pop()?.label ?? null;

  const seasonLine = (o: OptionItem) => {
    const s = o.season;
    const second = s.rpg != null && s.apg != null && s.apg > s.rpg ? ['APG', s.apg] : ['RPG', s.rpg];
    return (
      <div className="co-line">
        <div><b>{s.ppg ?? '—'}</b><span>PPG</span></div>
        <div><b>{second[1] ?? '—'}</b><span>{second[0]}</span></div>
        <div><b>{s.mpg != null ? Math.round(s.mpg) : '—'}</b><span>MPG</span></div>
      </div>
    );
  };
  const header = (o: OptionItem) => (
    <div className="co-top">
      <div>
        <div className="eos-kicker co-kick">{o.ruolo} · {o.eta} · {o.ovr} OVR</div>
        <button type="button" className="eos-link co-name" onClick={() => openPlayerProfile(o.nome)}>{o.nome}</button>
      </div>
      <span className="co-salary">{money(o.salario)}</span>
    </div>
  );

  return (
    <div className="co-split">
      <div className="co-col">
        {error && <p className="eos-error">{error}</p>}
        {options.length === 0 && <div className="eos-sheet"><p className="eos-big-muted">No options to decide this summer.</p></div>}

        {teamOptions.length > 0 && (
          <>
            <h3 className="co-h">Team options <small>your call</small></h3>
            <div className="co-cards">
              {teamOptions.map((o) => (
                <div key={o.nome} className="eos-sheet co-card">
                  {header(o)}
                  {seasonLine(o)}
                  {o.take && <p className="co-take">“{o.take}”</p>}
                  <div className="co-choice" role="group" aria-label={`Team option for ${o.nome}`}>
                    {(['PICKUP', 'DECLINE'] as const).map((d) => (
                      <button key={d} type="button" aria-pressed={decisions[o.nome] === d}
                        onClick={() => setDecisions((prev) => ({ ...prev, [o.nome]: d }))}>
                        {d === 'PICKUP' ? 'Exercise · 1 yr' : 'Decline → free agent'}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {playerOptions.length > 0 && (
          <>
            <h3 className="co-h">Player options <small>they decide</small></h3>
            <div className="co-cards">
              {playerOptions.map((o) => (
                <div key={o.nome} className="eos-sheet co-card">
                  {header(o)}
                  <p className="co-take">{o.decision_reason} Market ≈ {money(o.market_value)}.</p>
                  <div className={`co-verdict ${o.player_decision === 'DECLINE' ? 'is-out' : 'is-in'}`}>
                    {o.player_decision === 'DECLINE' ? 'Opts out → free agent' : 'Opts in · 1 yr'}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="co-col">
        {cash && (
          <section className="rc-card">
            <h3 className="rc-h">Next season's money</h3>
            <ul className="co-ledger">
              <li><span>Guaranteed</span><b>{money(cash.guaranteed)}</b></li>
              {options.map((o) => (
                <li key={o.nome}>
                  <span>{kept(o) ? '+' : '−'} {o.nome} ({o.team_option ? (kept(o) ? 'exercise' : 'decline') : (kept(o) ? 'opts in' : 'opts out')})</span>
                  <b className={kept(o) ? undefined : 'co-dim'}>{kept(o) ? money(o.salario) : '—'}</b>
                </li>
              ))}
              <li className="co-total"><span>Payroll</span><b>{money(payroll)}</b></li>
              {!cash.no_cap && cash.tax != null && (
                <li><span>vs tax line {money(cash.tax)}</span><b className={payroll > cash.tax ? 'co-bad' : 'co-good'}>{signedMoney(payroll - cash.tax)}</b></li>
              )}
              {!cash.no_cap && cash.apron1 != null && (
                <li><span>Room under 1st apron</span><b>{payroll < cash.apron1 ? money(cash.apron1 - payroll) : 'Over'}</b></li>
              )}
              {exception && <li><span>Signing tools left</span><b className="co-small">{exception}</b></li>}
              {cash.no_cap && <li><span>No salary cap in this era</span><b /></li>}
            </ul>
          </section>
        )}
        <section className="rc-card">
          <h3 className="rc-h">Around the league</h3>
          {around.list.length === 0 ? <p className="eos-muted">No other player options this summer.</p> : (
            <ul className="rc-rows">
              {around.list.map((a) => (
                <li key={`${a.name}-${a.team}`}>
                  <span><button type="button" className="eos-link" onClick={() => openPlayerProfile(a.name)}>{a.name}</button> <small className="co-dim">{a.team} · {a.ovr}</small></span>
                  <span className={`co-tag ${a.decision === 'out' ? 'is-out' : 'is-in'}`}>{a.decision === 'out' ? 'Opts out' : 'Opts in'}</span>
                </li>
              ))}
            </ul>
          )}
          {around.total > around.list.length && <p className="eos-muted co-more">+{around.total - around.list.length} more · opt-outs join the free-agent pool</p>}
        </section>
      </div>
    </div>
  );
};
