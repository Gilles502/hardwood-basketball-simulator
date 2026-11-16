// Tactical Board · Roles: the user moves a player to another role. In games he plays that role (who brings the ball
// up, who helps inside, who rebounds), and his OVR becomes his rating there. Ratings per role come from the engine
// (valutazioni_posizionali); POST /api/team-manager/change-roles applies them (Giocatore.change_role).
import React, { useEffect, useMemo, useState } from 'react';
import { RotateCcw, Save } from 'lucide-react';
import { normalizeRole } from '../../utils/roles';
import { POSITIONS, ratingAt } from './lineup';
import type { BoardPlayer } from './lineup';

export interface RolePlayer extends BoardPlayer {
  ruolo_originale?: string | null;
  /** His OVR after a move to each role (the server's Giocatore.ovr_at_role: capped at +2 over his original OVR). */
  ovr_if_role?: Record<string, number>;
}

export interface RoleChange {
  nome: string;
  ruolo: string;
  ovr: number;
  potenziale: number;
  ruolo_originale: string | null;
  valutazioni_posizionali: Record<string, number>;
  ovr_if_role: Record<string, number>;
}

interface RolesTabProps {
  roster: RolePlayer[];
  onSaved: (changed: RoleChange[]) => void;
  onDirtyChange: (dirty: boolean) => void;
}

export const RolesTab: React.FC<RolesTabProps> = ({ roster, onSaved, onDirtyChange }) => {
  const [pending, setPending] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const players = useMemo(() => [...roster].sort((a, b) => b.ovr - a.ovr), [roster]);
  const roleOf = (p: RolePlayer) => pending[p.nome] ?? normalizeRole(p.ruolo);
  const changes = Object.entries(pending).filter(([name, role]) => {
    const p = roster.find((x) => x.nome === name);
    return p && normalizeRole(p.ruolo) !== role;
  });

  useEffect(() => { onDirtyChange(changes.length > 0); }, [changes.length, onDirtyChange]);

  const pick = (p: RolePlayer, role: string) => setPending((cur) => ({ ...cur, [p.nome]: role }));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/api/team-manager/change-roles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roles: Object.fromEntries(changes) }),
      });
      const data = await response.json();
      if (!response.ok || data.error) { setError(data.error ?? 'The roles could not be saved.'); return; }
      setPending({});
      onSaved(data.changed ?? []);
    } catch {
      setError('The roles could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ro-root">
      <p className="lu-help">
        Move a player to the role he really plays. In games he plays it (<b>ball handling, help defense, rebounds,
        fouls</b>), and his OVR becomes his rating there, at most <b>+2</b> over his original OVR. Moving him back
        gives his old OVR.
      </p>
      <section className="lu-paper" aria-label="Player roles">
        <div className="lu-band"><span>Roles</span><span>Rating at each role (vs the players who play it)</span></div>
        <div className="ro-row ro-head" aria-hidden="true">
          <span>Player</span><span>Role</span><span className="ro-num">OVR</span>
          {POSITIONS.map((pos) => <span key={pos} className="ro-num">{pos}</span>)}
        </div>
        {players.map((p) => {
          const role = roleOf(p);
          const current = normalizeRole(p.ruolo);
          const moved = role !== current;
          const newOvr = moved ? (p.ovr_if_role?.[role] ?? ratingAt(p, role)) : p.ovr;
          const origin = p.ruolo_originale ? normalizeRole(p.ruolo_originale) : null;
          return (
            <div key={p.nome} className={`ro-row${moved ? ' is-moved' : ''}`}>
              <span className="lu-who">
                <b>{p.nome}</b>
                <small>
                  {p.eta} y · POT {p.potenziale}
                  {origin && origin !== role && <> · originally {origin}</>}
                  {moved && <> · <span className="ro-change">{current} → {role} · OVR {p.ovr} → {newOvr}</span></>}
                </small>
              </span>
              <select className="ro-select" value={role} onChange={(e) => pick(p, e.target.value)}
                      aria-label={`Role of ${p.nome}`} disabled={busy}>
                {POSITIONS.map((pos) => <option key={pos} value={pos}>{pos}</option>)}
              </select>
              <span className="ro-num ro-ovr">{newOvr}</span>
              {POSITIONS.map((pos) => (
                <button key={pos} type="button" className={`ro-num ro-rating${pos === role ? ' is-picked' : ''}`}
                        onClick={() => pick(p, pos)} disabled={busy} title={`Play ${p.nome} as ${pos}`}>
                  {ratingAt(p, pos)}
                </button>
              ))}
            </div>
          );
        })}
      </section>
      {error && <p className="fa-error ro-error">{error}</p>}
      <div className="ro-actions">
        <button type="button" className="btn btn-secondary" onClick={() => setPending({})} disabled={busy || changes.length === 0}>
          <RotateCcw size={16} /> Undo changes
        </button>
        <button type="button" className="btn btn-primary" onClick={save} disabled={busy || changes.length === 0}>
          <Save size={16} /> {busy ? 'Saving…' : `Save roles${changes.length ? ` (${changes.length})` : ''}`}
        </button>
      </div>
    </div>
  );
};
