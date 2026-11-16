// The offer sheet inside the open market row: salary, years, raise and option. Every change asks the market what the
// offer would do (POST /api/offseason/free_agency/preview_offer, nothing is saved) and the user's bar moves among the
// rival offers against tonight's bar. "Paid with" is the money the server would use, or why the offer is not allowed.
import React, { useEffect, useState } from 'react';
import { OffersRace } from './OffersRace';
import { ScoreWhy } from './ScoreWhy';
import { money, type FaPlayer, type Race, type ScoreDetail } from './freeAgency';

interface Preview {
  allowed: boolean;
  tool: string | null;
  reason: string | null;
  total_value: number;
  score: ScoreDetail | null;
  race: Race | null;
}

interface OfferSheetProps {
  player: FaPlayer;
  userTeam: string;
  teamGoal: string;
  day: number;
  minSalary: number;
  maxSalary: number;
  busy: boolean;
  onSend: (body: { player_name: string; salary: number; years: number; option_type: string; raise_pct: number }) => Promise<boolean>;
  onWithdraw: () => void;
  onClose: () => void;
}

const DEBOUNCE_MS = 250;
const TOOL_LABEL: Record<string, string> = {
  CAP_SPACE: 'your cap space', BIRD_RIGHTS: 'Bird rights', MINIMUM: 'the minimum exception', MLE: 'the MLE',
  FULL_MLE: 'the MLE', TAXPAYER_MLE: 'the taxpayer MLE', BAE: 'the BAE',
};
const RAISES = [0, 0.05, 0.08];
const OPTIONS: { value: string; label: string }[] = [
  { value: 'None', label: 'None' }, { value: 'PO', label: 'Player option' }, { value: 'TO', label: 'Team option' },
];

const round1 = (v: number) => Math.round(v * 10) / 10;

export const OfferSheet: React.FC<OfferSheetProps> = ({
  player, userTeam, teamGoal, day, minSalary, maxSalary, busy, onSend, onWithdraw, onClose,
}) => {
  const existing = player.active_user_offer;
  const [salary, setSalary] = useState(round1(existing?.salary ?? player.ask));
  const [years, setYears] = useState(existing?.years ?? 2);
  const [raise, setRaise] = useState(existing?.raise_pct ?? 0.05);
  const [option, setOption] = useState(existing?.option_type ?? 'None');
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = window.setTimeout(() => {
      fetch('/api/offseason/free_agency/preview_offer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: player.nome, salary, years, option_type: option, raise_pct: raise }),
      })
        .then((r) => r.json())
        .then((data) => { if (!cancelled && data.success) setPreview(data); })
        .catch(() => undefined);
    }, DEBOUNCE_MS);
    return () => { cancelled = true; window.clearTimeout(id); };
  }, [player.nome, salary, years, raise, option]);

  const value = preview?.score?.value ?? player.score.value;
  const send = async () => {
    if (await onSend({ player_name: player.nome, salary, years, option_type: option, raise_pct: raise })) onClose();
  };

  return (
    <div className="fa-open-grid fa-sheet">
      <div>
        <span className="eos-kicker">{existing ? 'Change your offer' : 'Your offer'} · {money(salary)} a year</span>
        <input
          className="fa-slider"
          type="range"
          min={round1(minSalary)}
          max={round1(maxSalary)}
          step={0.1}
          value={salary}
          onChange={(e) => setSalary(round1(Number(e.target.value)))}
          aria-label="Salary per year"
        />
        <div className="fa-slider-marks">
          <span>min {money(minSalary)}</span>
          <button type="button" onClick={() => setSalary(round1(player.ask))}>his ask {money(player.ask)}</button>
          <button type="button" onClick={() => setSalary(round1(value))}>his value {money(value)}</button>
          <span>max {money(maxSalary)}</span>
        </div>
        <div className="fa-controls">
          <div>
            <span className="eos-kicker">Years</span>
            <div className="fa-views">
              {[1, 2, 3, 4, 5].map((y) => <button key={y} type="button" aria-pressed={years === y} onClick={() => setYears(y)}>{y}</button>)}
            </div>
          </div>
          <div>
            <span className="eos-kicker">Raise / year</span>
            <div className="fa-views">
              {RAISES.map((r) => <button key={r} type="button" aria-pressed={raise === r} onClick={() => setRaise(r)}>{r === 0 ? 'Flat' : `+${Math.round(r * 100)}%`}</button>)}
            </div>
          </div>
          <div>
            <span className="eos-kicker">Option, last year</span>
            <div className="fa-views">
              {OPTIONS.map((o) => <button key={o.value} type="button" aria-pressed={option === o.value} onClick={() => setOption(o.value)}>{o.label}</button>)}
            </div>
          </div>
        </div>
        <p className={`fa-paid${preview && !preview.allowed ? ' is-bad' : ''}`}>
          {!preview ? 'Checking…'
            : preview.allowed ? <>Paid with <b>{TOOL_LABEL[preview.tool ?? ''] ?? preview.tool}</b> · {money(preview.total_value)} over {years} {years === 1 ? 'year' : 'years'}.</>
              : <>Not allowed: {preview.reason}</>}
        </p>
        <div className="fa-sheet-actions">
          <button type="button" className="btn btn-primary" onClick={send} disabled={busy || !preview?.allowed}>
            {existing ? 'Update offer' : 'Send offer'}
          </button>
          {existing && <button type="button" className="btn btn-secondary fa-ink" onClick={onWithdraw} disabled={busy}>Withdraw</button>}
          <button type="button" className="btn btn-secondary fa-ink" onClick={onClose}>Cancel</button>
        </div>
      </div>
      <div>
        {preview?.race && <OffersRace race={preview.race} userTeam={userTeam} title="The race with this offer" />}
        {preview?.score && (() => {
          const mine = preview.race?.offers.find((o) => o.is_user);
          const bonus = mine?.previous_team_bonus ? mine.loyalty_bonus : 0;
          return (
            <ScoreWhy detail={preview.score} offer={salary} role={player.ruolo} teamGoal={teamGoal} day={day} oldTeamBonus={bonus}
              userTeam={userTeam} title={`Why he scores it ${Math.round(preview.score.total + bonus)}`} />
          );
        })()}
      </div>
    </div>
  );
};
