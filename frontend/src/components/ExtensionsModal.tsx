// File: frontend/src/components/ExtensionsModal.tsx
// Contract extensions (mockup A): one popup, players you can extend on the left (last contract year), the offer sheet
// for the picked one on the right. Every change asks the server how he would react (POST /api/contracts/evaluate-offer,
// nothing is saved); "Offer extension" sends it (POST /api/team-manager/extensions/offer, 3 tries per player).
import React, { useCallback, useEffect, useState } from 'react';
import { ModalShell } from './ModalShell';
import './ExtensionsModal.css';

interface ExpiringPlayer {
  nome: string;
  ruolo: string;
  ovr: number;
  potenziale: number;
  eta: number;
  salario_attuale: number;
  option_type: string;
  valore_mercato: number;
  willingness: string;
  willingness_score?: number;
  attempts: number;
  is_closed: boolean;
}

interface Factor {
  name: string;
  label: string;
  value: string;
  score_impact: number;
  type: 'positive' | 'negative' | 'neutral';
}

interface Evaluation {
  willingness_score: number;
  tier: string;
  agent_reaction: string;
  market_value: number;
  factors: Factor[];
  projected_salaries: number[];
  total_value: number;
  can_accept: boolean;
  team_payroll?: number;
  team_cap?: number;
  team_tax?: number;
  cap_space_after?: number;
  is_over_cap?: boolean;
}

interface ExtensionsModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

// The server allows this many offers per player before talks close (server.py NEGOTIATION_ATTEMPTS).
const MAX_TRIES = 3;
const SALARY_MIN = 0.5;
const SALARY_MAX = 55;
const YEARS = [1, 2, 3, 4, 5];
const RAISES: [number, string][] = [[-0.05, '-5%'], [0, 'Flat'], [0.05, '+5%'], [0.08, '+8% (Bird)']];
const OPTIONS: [string, string][] = [['None', 'None'], ['PO', 'Player'], ['TO', 'Team']];
const STEPS = [-1, -0.1, 0.1, 1];
const clampSalary = (v: number) => Math.round(Math.min(SALARY_MAX, Math.max(SALARY_MIN, v)) * 10) / 10;

const money = (v: number | undefined | null) => (v === undefined || v === null ? '—' : `$${v.toFixed(1)}M`);
// "Won't negotiate" (a player who walks away) looks like a rejection
const tierClass = (tier: string) => (tier === "Won't negotiate" ? 'ex-tier is-rejected' : `ex-tier is-${tier.toLowerCase().replace(/\s+/g, '-')}`);

export const ExtensionsModal: React.FC<ExtensionsModalProps> = ({ onClose, onSuccess }) => {
  const [players, setPlayers] = useState<ExpiringPlayer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/team-manager/extensions?_t=${Date.now()}`);
      const data = await res.json();
      if (!data.success) { setError(data.error || 'Could not load contract extensions.'); return; }
      const list: ExpiringPlayer[] = data.players || [];
      setPlayers(list);
      setSelected((cur) => (cur && list.some((p) => p.nome === cur) ? cur : list.find((p) => !p.is_closed)?.nome ?? list[0]?.nome ?? null));
    } catch {
      setError('Could not reach the server.');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const player = players?.find((p) => p.nome === selected) ?? null;

  return (
    <ModalShell isOpen onClose={onClose} title="Contract extensions" maxWidth={1040} tall
      subtitle="Players in the last year of their deal can extend before free agency"
      icon={<span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: '14px' }}>EXT</span>}>
      <div className="ex">
        {message && <div className={`ex-message${message.ok ? ' is-ok' : ''}`} role="status">{message.text}</div>}
        {error ? <p className="ex-muted">{error}</p> : !players ? <div className="spinner" style={{ margin: '40px auto' }} /> : (
          <div className="ex-split">
            <div className="ex-list">
              <div className="ex-kicker">Can extend ({players.length})</div>
              {players.length === 0 && <p className="ex-muted">Nobody on your roster is in the last year of his contract.</p>}
              {players.map((p) => (
                <button key={p.nome} type="button" className={`ex-row${p.nome === selected ? ' is-on' : ''}`}
                  onClick={() => { setSelected(p.nome); setMessage(null); }} aria-pressed={p.nome === selected}>
                  <span className="ex-row-main">
                    <b>{p.nome}</b>
                    <span className="ex-muted">{p.ruolo} · {p.eta} · {money(p.salario_attuale)} now · market {money(p.valore_mercato)}</span>
                  </span>
                  <span className="ex-row-side">
                    <b className="ex-ovr">{p.ovr}</b>
                    {p.is_closed ? <span className="ex-tier is-rejected">Closed</span> : <span className={tierClass(p.willingness)}>{p.willingness}</span>}
                  </span>
                </button>
              ))}
            </div>
            {player ? (
              <OfferSheet key={player.nome} player={player}
                onSent={async (res) => {
                  setMessage({ ok: res.success, text: res.message });
                  await load();
                  if (res.success) onSuccess();
                }} />
            ) : <div className="ex-muted ex-empty">Pick a player to make an offer.</div>}
          </div>
        )}
      </div>
    </ModalShell>
  );
};

const OfferSheet: React.FC<{ player: ExpiringPlayer; onSent: (res: { success: boolean; message: string }) => Promise<void> }> = ({ player, onSent }) => {
  const [salary, setSalary] = useState(Math.round(player.valore_mercato * 10) / 10);
  const [years, setYears] = useState(player.eta <= 28 ? 3 : 2);
  const [raise, setRaise] = useState(0.05);
  const [option, setOption] = useState('None');
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    const timer = window.setTimeout(() => {
      fetch('/api/contracts/evaluate-offer', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: player.nome, offer_salary: salary, years, option_type: option, raise_pct: raise, mode: 'extension' }),
      })
        .then((res) => res.json())
        .then((data) => { if (alive && data.success && data.evaluation) setEvaluation(data.evaluation); })
        .catch(() => {});
    }, 180);
    return () => { alive = false; window.clearTimeout(timer); };
  }, [player.nome, salary, years, raise, option]);

  const send = async (force: boolean) => {
    setBusy(true);
    try {
      const res = await fetch('/api/team-manager/extensions/offer', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: player.nome, years, salary, option_type: option, raise_pct: raise, force_sign: force }),
      });
      const data = await res.json();
      await onSent({ success: !!data.success, message: data.message || (data.success ? 'Extension signed.' : 'Offer refused.') });
    } catch {
      await onSent({ success: false, message: 'Could not reach the server.' });
    } finally {
      setBusy(false);
    }
  };

  const market = evaluation?.market_value ?? player.valore_mercato;
  const pct = (v: number) => `${((Math.min(SALARY_MAX, Math.max(SALARY_MIN, v)) - SALARY_MIN) / (SALARY_MAX - SALARY_MIN)) * 100}%`;
  const triesLeft = Math.max(0, MAX_TRIES - player.attempts);
  const score = evaluation?.willingness_score ?? null;

  return (
    <div className="ex-sheet">
      <div className="ex-grid2">
        <div className="ex-tile">
          <div className="ex-kicker">Your offer</div>
          <div className="ex-salary-row">
            <span className="ex-big" aria-live="polite">{money(salary)}</span>
            <span className="ex-muted">market {money(market)}</span>
          </div>
          <div className="ex-range">
            <input type="range" min={SALARY_MIN} max={SALARY_MAX} step={0.1} value={salary} aria-label="Salary per year"
              onChange={(e) => setSalary(clampSalary(Number(e.target.value)))} />
            <span className="ex-market" style={{ left: pct(market) }} title={`Market value ${money(market)}`} />
          </div>
          <div className="ex-seg" role="group" aria-label="Adjust salary">
            {STEPS.map((d) => (
              <button key={d} type="button" onClick={() => setSalary((s) => clampSalary(s + d))}>{d > 0 ? '+' : '−'}{Math.abs(d)}</button>
            ))}
          </div>
          <div className="ex-kicker">Years</div>
          <div className="ex-seg" role="group" aria-label="Years">
            {YEARS.map((y) => <button key={y} type="button" aria-pressed={years === y} onClick={() => setYears(y)}>{y}</button>)}
          </div>
          <div className="ex-kicker">Yearly raise</div>
          <div className="ex-seg" role="group" aria-label="Yearly raise">
            {RAISES.map(([v, l]) => <button key={l} type="button" aria-pressed={raise === v} onClick={() => setRaise(v)}>{l}</button>)}
          </div>
          <div className="ex-kicker">Option</div>
          <div className="ex-seg" role="group" aria-label="Option">
            {OPTIONS.map(([v, l]) => <button key={v} type="button" aria-pressed={option === v} onClick={() => setOption(v)}>{l}</button>)}
          </div>
        </div>

        <div className="ex-paper">
          <div className="ex-reaction-top">
            <span className="ex-kicker is-paper">His reaction</span>
            {evaluation && <span className={tierClass(evaluation.tier)}>{evaluation.tier}</span>}
          </div>
          <div className="ex-score">{score === null ? '—' : Math.round(score)}</div>
          <div className="ex-meter"><b style={{ left: `${Math.min(100, Math.max(0, score ?? 0))}%` }} /></div>
          {evaluation && <p className="ex-quote">“{evaluation.agent_reaction}”</p>}
          {evaluation?.factors.map((f) => (
            <div key={f.name} className="ex-factor">
              <span><b>{f.label}</b><span className="ex-muted-p"> · {f.value}</span></span>
              <span className={f.score_impact > 0 ? 'is-pos' : f.score_impact < 0 ? 'is-neg' : 'ex-muted-p'}>
                {f.score_impact > 0 ? '+' : ''}{Math.round(f.score_impact)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {evaluation && (
        <>
          <div className="ex-years">
            {evaluation.projected_salaries.map((s, i) => (
              <div key={i}><span className="ex-muted">Year {i + 1}</span><b>{money(s)}</b></div>
            ))}
          </div>
          <div className="ex-foot">
            <span className="ex-muted">
              Total <b>{money(evaluation.total_value)}</b>
              {evaluation.cap_space_after !== undefined && <> · cap space after <b className={evaluation.cap_space_after < 0 ? 'is-neg' : undefined}>{money(evaluation.cap_space_after)}</b></>}
              {evaluation.team_payroll !== undefined && evaluation.team_tax ? <> · payroll {money(evaluation.team_payroll)} / tax {money(evaluation.team_tax)}</> : null}
            </span>
          </div>
        </>
      )}

      <div className="ex-actions">
        <button type="button" className="ex-force" disabled={busy || player.is_closed} onClick={() => send(true)}
          title="Signs him on these terms whatever he thinks (GM override)">Force signing</button>
        <span className="ex-muted">{player.is_closed ? 'He closed the talks.' : `${triesLeft} of ${MAX_TRIES} tries left`}</span>
        <button type="button" className="ex-send" disabled={busy || player.is_closed} onClick={() => send(false)}>
          {busy ? 'Sending…' : 'Offer extension'}
        </button>
      </div>
    </div>
  );
};
