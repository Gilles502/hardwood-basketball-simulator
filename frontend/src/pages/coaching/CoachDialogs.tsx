// Coaching page dialogs on ModalShell: extend your coach, fire him, make an offer to a market coach ("Fire & hire").
import React, { useState } from 'react';
import { AlertTriangle, HeartHandshake, UserMinus, UserPlus } from 'lucide-react';
import { ModalShell } from '../../components/ModalShell';
import '../../components/FrontOfficeDialogs.css';
import { fitGrade, gradeTone, marketAsk, money, type Coach } from './types';

const YEARS = [1, 2, 3, 4, 5];
const REFUSE_BELOW = 0.75; // server.py: offers below 75% of the ask are refused

/** Estimated buyout of the current contract (server.py _fire_user_coach). */
const buyout = (c: Coach) => Math.round(c.salario * Math.max(1, c.contratto_anni_rimanenti) * 0.75 * 10) / 10;

interface ContractFieldsProps {
  idPrefix: string;
  years: number;
  salary: string;
  onYears: (y: number) => void;
  onSalary: (s: string) => void;
  hint: string;
}

const ContractFields: React.FC<ContractFieldsProps> = ({ idPrefix, years, salary, onYears, onSalary, hint }) => (
  <div className="cc-form">
    <label htmlFor={`${idPrefix}-years`}>
      <span className="fd-label">Years</span>
      <select id={`${idPrefix}-years`} value={years} onChange={(e) => onYears(Number(e.target.value))}>
        {YEARS.map((y) => <option key={y} value={y}>{y} {y === 1 ? 'year' : 'years'}</option>)}
      </select>
    </label>
    <label htmlFor={`${idPrefix}-salary`}>
      <span className="fd-label">Salary per year ($M)</span>
      <input id={`${idPrefix}-salary`} type="number" min={0.5} max={20} step={0.1} value={salary} onChange={(e) => onSalary(e.target.value)} />
    </label>
    <p className="fd-muted cc-form-hint">{hint}</p>
  </div>
);

const ErrorNotice: React.FC<{ message: string | null }> = ({ message }) => (message
  ? <div className="fd-notice is-bad" role="alert"><AlertTriangle size={16} aria-hidden="true" /> <span>{message}</span></div>
  : null);

interface SubmitProps {
  onClose: () => void;
  onDone: (message: string) => void;
}

async function post(url: string, body?: object): Promise<{ ok: boolean; message: string }> {
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json();
    return res.ok && !data.error ? { ok: true, message: data.message || 'Done.' } : { ok: false, message: data.error || 'The request failed.' };
  } catch {
    return { ok: false, message: 'Could not reach the server.' };
  }
}

export const ExtendCoachDialog: React.FC<SubmitProps & { coach: Coach }> = ({ coach, onClose, onDone }) => {
  const ask = coach.extension_ask ?? coach.salario;
  const [years, setYears] = useState(2);
  const [salary, setSalary] = useState(String(Math.max(ask, coach.salario).toFixed(1)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    const r = await post('/api/coaching/extend', { years, salary: Number(salary) });
    setBusy(false);
    if (r.ok) onDone(r.message); else setError(r.message);
  };

  return (
    <ModalShell isOpen onClose={onClose} title={`Extend ${coach.nome}`} subtitle={`${coach.contratto_anni_rimanenti} ${coach.contratto_anni_rimanenti === 1 ? 'year' : 'years'} left at ${money(coach.salario)}`}
      icon={<HeartHandshake size={22} />} maxWidth={520}
      footerEnd={<>
        <button type="button" className="ms-btn ms-btn-secondary" onClick={onClose}>Cancel</button>
        <button type="button" className="ms-btn ms-btn-primary" onClick={submit} disabled={busy || !(Number(salary) > 0)}>{busy ? 'Sending…' : 'Offer extension'}</button>
      </>}>
      <div className="fd-body">
        <p className="fd-lead">The years are added to his current deal. The new salary applies from now on, and an extension raises his security with the owner.</p>
        <ContractFields idPrefix="cc-extend" years={years} salary={salary} onYears={setYears} onSalary={setSalary}
          hint={`He asks ${money(ask)} a year and refuses anything under ${money(ask * REFUSE_BELOW)}.`} />
        <ErrorNotice message={error} />
      </div>
    </ModalShell>
  );
};

export const FireCoachDialog: React.FC<SubmitProps & { coach: Coach }> = ({ coach, onClose, onDone }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    const r = await post('/api/coaching/fire');
    setBusy(false);
    if (r.ok) onDone(r.message); else setError(r.message);
  };

  return (
    <ModalShell isOpen onClose={onClose} title={`Fire ${coach.nome}?`} subtitle="The bench stays empty until you hire someone"
      icon={<UserMinus size={22} />} maxWidth={520}
      footerEnd={<>
        <button type="button" className="ms-btn ms-btn-secondary" onClick={onClose}>Keep him</button>
        <button type="button" className="ms-btn cc-btn-danger" onClick={submit} disabled={busy}>{busy ? 'Firing…' : 'Fire coach'}</button>
      </>}>
      <div className="fd-body">
        <div className="fd-facts">
          <div><span className="fd-label">Buyout</span><strong>{money(buyout(coach))}</strong></div>
          <div><span className="fd-label">Player morale</span><strong>−3 each</strong></div>
          <div><span className="fd-label">Team chemistry</span><strong>−8</strong></div>
        </div>
        <p className="fd-lead">He joins the coach market, where you or another team can hire him later. To replace him right away, pick a coach in the market instead: that fires him in the same step.</p>
        <ErrorNotice message={error} />
      </div>
    </ModalShell>
  );
};

export const HireCoachDialog: React.FC<SubmitProps & { candidate: Coach; current: Coach | null }> = ({ candidate, current, onClose, onDone }) => {
  const ask = marketAsk(candidate);
  const floor = candidate.min_salary ?? 0;
  const [years, setYears] = useState(3);
  const [salary, setSalary] = useState(ask.toFixed(1));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const grade = fitGrade(candidate.roster_fit);

  const submit = async () => {
    setBusy(true);
    const r = await post('/api/coaching/hire', { coach_name: candidate.nome, years, salary: Number(salary), replace_current: !!current });
    setBusy(false);
    if (r.ok) onDone(r.message); else setError(r.message);
  };

  return (
    <ModalShell isOpen onClose={onClose} title={candidate.nome}
      subtitle={`${candidate.specialization || 'Head coach'} · ${candidate.stile_gioco} · age ${candidate.eta}`}
      icon={<UserPlus size={22} />} maxWidth={600}
      footerEnd={<>
        <button type="button" className="ms-btn ms-btn-secondary" onClick={onClose}>Cancel</button>
        <button type="button" className="ms-btn ms-btn-primary" onClick={submit} disabled={busy || !(Number(salary) > 0)}>
          {busy ? 'Sending…' : current ? 'Fire & hire' : 'Offer contract'}
        </button>
      </>}>
      <div className="fd-body">
        <div className="fd-facts">
          <div><span className="fd-label">OVR</span><strong>{candidate.ovr_totale}{current ? <span className="fd-muted"> (yours {current.ovr_totale})</span> : null}</strong></div>
          <div><span className="fd-label">Off / Def</span><strong>{candidate.ovr_offensivo} / {candidate.ovr_difensivo}</strong></div>
          <div><span className="fd-label">Development</span><strong>{candidate.player_development ?? 75}</strong></div>
          <div><span className="fd-label">Fit with roster</span><strong><span className={`of-tone-${gradeTone(grade)}`}>{grade}</span>{candidate.roster_fit ? ` ${candidate.roster_fit.fit_score}%` : ''}</strong></div>
          <div><span className="fd-label">Career</span><strong>{candidate.historical_wins}-{candidate.historical_losses} · {candidate.championships} {candidate.championships === 1 ? 'ring' : 'rings'}</strong></div>
        </div>
        <ContractFields idPrefix="cc-hire" years={years} salary={salary} onYears={setYears} onSalary={setSalary}
          hint={`He asks ${money(ask)} a year${floor > 0 ? ` and refuses anything under ${money(floor)}` : ''}.`} />
        {current && (
          <div className="fd-notice is-bad">
            <AlertTriangle size={16} aria-hidden="true" />
            <span><strong>{current.nome} will be fired</strong> (buyout {money(buyout(current))}, player morale −3, chemistry −8). The new coach adds +5 chemistry.</span>
          </div>
        )}
        <ErrorNotice message={error} />
      </div>
    </ModalShell>
  );
};
