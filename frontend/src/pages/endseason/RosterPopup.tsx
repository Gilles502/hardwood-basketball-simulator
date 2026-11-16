// The hub's Roster button and its read-only popup: the Roster & Contracts board (contracts, payroll, picks by year)
// for the user's team, plus open free-agent offers while the market is open. Nothing in here advances the offseason.
import React, { useEffect, useState } from 'react';
import { Users } from 'lucide-react';
import { ModalShell } from '../../components/ModalShell';
import { useLeagueStore } from '../../store/leagueStore';
import { ContractsTab } from '../roster/ContractsTab';
import type { TeamFinancials } from '../roster/ContractsTab';
import '../roster/Roster.css';

interface OpenOffer { nome: string; ovr: number; active_user_offer: { salary?: number; years?: number } | null }

const money = (v: number) => `$${v.toFixed(1)}M`;

export const RosterButton: React.FC = () => {
  const { leagueData, openPlayerProfile } = useLeagueStore();
  const [open, setOpen] = useState(false);
  const [financials, setFinancials] = useState<TeamFinancials | null>(null);
  const [offers, setOffers] = useState<OpenOffer[]>([]);
  const teamName = leagueData?.player_team_name ?? null;
  const team = leagueData?.league_database?.teams.find((t) => t.nome === teamName);
  const marketOpen = leagueData?.league_state === 'OFFSEASON_UFA_START';

  useEffect(() => {
    if (!open || !teamName) return;
    let cancelled = false;
    fetch(`/api/team-strategy-intel?team_name=${encodeURIComponent(teamName)}`)
      .then((r) => r.json())
      .then((data) => { if (!cancelled && data.team_name === teamName) setFinancials(data.financials ?? null); })
      .catch(() => undefined);
    if (marketOpen) {
      fetch(`/api/offseason/free_agency/state?_t=${Date.now()}`)
        .then((r) => r.json())
        .then((data) => { if (!cancelled) setOffers((data.players ?? []).filter((p: OpenOffer) => p.active_user_offer)); })
        .catch(() => undefined);
    }
    return () => { cancelled = true; };
  }, [open, teamName, marketOpen]);

  if (!teamName || !team) return null;
  const picks = (team.future_picks ?? []).reduce((n, year) => n + year.owned.length, 0);

  return (
    <>
      <button type="button" className="eos-roster-btn" onClick={() => setOpen(true)}>
        Roster <em>{team.roster.length}</em>
        <small>{money(team.payroll)} · {picks} {picks === 1 ? 'pick' : 'picks'}</small>
      </button>
      <ModalShell
        isOpen={open}
        onClose={() => setOpen(false)}
        title={`${teamName} · roster`}
        subtitle="Read-only · the hub stays where you left it"
        icon={<Users size={20} />}
        maxWidth={1200}
        tall
      >
        <div className="eos-roster-pop">
          {marketOpen && (
            <div className="eos-sheet">
              <span className="eos-kicker">Your open offers · {offers.length}</span>
              {offers.length ? (
                <ul className="eos-list">
                  {offers.map((o) => (
                    <li key={o.nome}>
                      <span><b>{o.nome}</b> <small>{o.ovr} OVR</small></span>
                      <span>{o.active_user_offer?.salary != null ? money(o.active_user_offer.salary) : ''}{o.active_user_offer?.years ? ` · ${o.active_user_offer.years} yrs` : ''}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="eos-muted">No offers out right now.</p>}
            </div>
          )}
          <ContractsTab team={team} financials={financials} standing={null} onOpenPlayer={openPlayerProfile} />
        </div>
      </ModalShell>
    </>
  );
};
