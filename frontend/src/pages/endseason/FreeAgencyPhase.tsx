// Phase 7 · Free agency (layout "market + roster sheet"): one list of every free agent; a row opens in place on the
// offers on the table (each scored by the player, against tonight's bar) and why he likes the user's offer; the
// user's roster sits beside it as a sheet; "Offer" turns the open row into the offer sheet. The numbers are the market's own (offseason/free_agency.py), nothing here
// recomputes them. Day by day with "Next day"; the hub's Next finishes the market.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import type { PhaseProps } from '../../utils/endSeason';
import { DayBar } from './freeagency/DayBar';
import { RfaCard } from './freeagency/RfaCard';
import { MarketTable } from './freeagency/MarketTable';
import { OffersRace } from './freeagency/OffersRace';
import { ScoreWhy } from './freeagency/ScoreWhy';
import { SignedTable } from './freeagency/SignedTable';
import { RosterSheet } from './freeagency/RosterSheet';
import { OfferSheet } from './freeagency/OfferSheet';
import { POSITIONS, type FaPlayer, type FaState } from './freeagency/freeAgency';
import './FreeAgency.css';

type View = 'available' | 'signed' | 'mine';

export const FreeAgencyPhase: React.FC<PhaseProps> = ({ readOnly, onBar }) => {
  const { leagueData, fetchLeagueData } = useLeagueStore();
  const [state, setState] = useState<FaState | null>(null);
  const [closed, setClosed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>('available');
  const [position, setPosition] = useState('ALL');
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [focus, setFocus] = useState<FaPlayer | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`/api/offseason/free_agency/state?_t=${Date.now()}`);
      const data: FaState = await response.json();
      if (!response.ok || data.error) { setClosed(true); return; }
      setState(data);
      if (data.completed) setView((v) => (v === 'available' ? 'signed' : v));
    } catch {
      setError('The market could not be loaded.');
    }
  }, []);

  useEffect(() => { load(); }, [load, leagueData?.league_state]);

  const post = async (url: string, body?: unknown): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok || data.error || data.success === false) { setError(data.error ?? 'That did not work. Try again.'); return false; }
      await load();
      await fetchLeagueData();
      return true;
    } catch {
      setError('The server did not answer. Try again.');
      return false;
    } finally {
      setBusy(false);
    }
  };

  // The hub's Next finishes the market: say how many days that skips and ask first.
  const daysLeft = state ? Math.max(0, state.days_total - state.current_day + (state.completed ? 0 : 1)) : null;
  useEffect(() => {
    if (readOnly) return;
    if (state?.pending_rfa_match) { onBar({ blocking: 'Answer the offer sheet first.' }); return; }
    if (daysLeft === null || state?.completed || daysLeft === 0) { onBar({ nextLabel: 'Close free agency →' }); return; }
    onBar({ nextLabel: `Finish free agency (${daysLeft} days left) →`, confirm: `Sim the remaining ${daysLeft} days of free agency?` });
  }, [readOnly, daysLeft, state?.completed, state?.pending_rfa_match, onBar]);

  const userTeam = state?.user_team.nome ?? '';
  const lastNight = useMemo(() => {
    if (!state) return [];
    const night = state.completed ? state.current_day : state.current_day - 1;
    return state.signings.filter((s) => s.day === night);
  }, [state]);
  const myOffers = useMemo(() => (state?.players ?? []).filter((p) => p.active_user_offer), [state]);

  if (!leagueData) return null;
  if (closed || (readOnly && !state)) {
    return <div className="eos-sheet"><p className="eos-muted">Free agency is closed. New signings are on the rosters.</p></div>;
  }
  if (!state) {
    return <div className="eos-sheet"><p className={error ? 'eos-error' : 'eos-muted'}>{error ?? 'Opening the market…'}</p></div>;
  }

  const team = state.user_team;
  // The server refuses more than 35% of the cap for one player (check_user_offer_validity).
  const maxSalary = (p: FaPlayer) => (team.salary_cap ? team.salary_cap * 0.35 : Math.max(p.ask * 2, 30));
  const openPlayer = (p: FaPlayer) => {
    if (editing === p.nome && !readOnly && !state.completed) {
      return (
        <OfferSheet
          player={p}
          userTeam={userTeam}
          teamGoal={team.team_goal}
          day={state.current_day}
          minSalary={team.min_salary}
          maxSalary={maxSalary(p)}
          busy={busy}
          onSend={(body) => post('/api/offseason/free_agency/offer', body)}
          onWithdraw={async () => { if (await post('/api/offseason/free_agency/cancel_offer', { player_name: p.nome })) setEditing(null); }}
          onClose={() => setEditing(null)}
        />
      );
    }
    const mine = p.race.offers.find((o) => o.team === userTeam);
    const rival = p.race.offers.find((o) => o.team !== userTeam);
    const offer = p.active_user_offer?.salary ?? p.ask;
    const bonus = mine?.previous_team_bonus ? mine.loyalty_bonus : 0;
    const shown = Math.round(p.score.total + bonus);
    return (
      <div className="fa-open-grid">
        <div>
          <OffersRace race={p.race} userTeam={userTeam} />
          {mine && rival && (
            <p className="fa-rival">
              {p.race.leader === userTeam
                ? `${rival.team} are ${Math.round(mine.score - rival.score)} behind you: a better offer from them could flip it.`
                : `${p.race.leader} lead you by ${Math.round(p.race.leader_score - mine.score)}.`}
            </p>
          )}
        </div>
        <ScoreWhy
          detail={p.score}
          offer={offer}
          role={p.ruolo}
          teamGoal={team.team_goal}
          day={state.current_day}
          oldTeamBonus={bonus}
          userTeam={userTeam}
          title={p.active_user_offer ? `Why your offer scores ${shown}` : `At his asking price he would score ${shown}`}
        />
      </div>
    );
  };

  const views: { key: View; label: string }[] = [
    { key: 'available', label: `Available · ${state.players.length}` },
    { key: 'signed', label: `Signed · ${state.signings.length}` },
    { key: 'mine', label: `My offers · ${myOffers.length}` },
  ];

  return (
    <div className="fa-root">
      <DayBar
        day={state.current_day}
        daysTotal={state.days_total}
        completed={state.completed}
        lastNight={lastNight}
        moves={(state.night_moves ?? []).filter((m) => m.type !== 'signed')}
        ovrOf={(name) => state.players.find((p) => p.nome === name)?.ovr}
        userTeam={userTeam}
        busy={busy}
        blocked={readOnly || !!state.pending_rfa_match}
        onNextDay={() => post('/api/offseason/free_agency/simulate_day')}
      />
      {state.pending_rfa_match && !readOnly && (
        <RfaCard match={state.pending_rfa_match} busy={busy}
          onAnswer={(match) => post('/api/offseason/free_agency/match_rfa', { player_name: state.pending_rfa_match!.player, match })} />
      )}
      {error && <p className="fa-error">{error}</p>}

      <div className="fa-grid">
        <div className="eos-sheet fa-market">
          <div className="fa-tools">
            <div className="fa-views" role="group" aria-label="View">
              {views.map((v) => (
                <button key={v.key} type="button" aria-pressed={view === v.key} onClick={() => { setView(v.key); setOpen(null); }}>{v.label}</button>
              ))}
            </div>
            <div className="fa-views" role="group" aria-label="Position">
              {['ALL', ...POSITIONS].map((pos) => (
                <button key={pos} type="button" aria-pressed={position === pos} onClick={() => setPosition(pos)}>{pos === 'ALL' ? 'All' : pos}</button>
              ))}
            </div>
            <input className="fa-search" type="search" placeholder="Search a player" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>

          {view === 'signed' ? (
            <SignedTable signings={state.signings} userTeam={userTeam} position={position} search={search} />
          ) : (
            <MarketTable
              players={view === 'mine' ? myOffers : state.players}
              userTeam={userTeam}
              position={position}
              search={search}
              open={open}
              onOpen={(name) => { setOpen(name); setEditing(null); }}
              onFocus={setFocus}
              onOffer={(p) => { setOpen(p.nome); setEditing(p.nome); }}
              onWithdraw={view === 'mine' && !readOnly ? (p) => post('/api/offseason/free_agency/cancel_offer', { player_name: p.nome }) : undefined}
              renderOpen={openPlayer}
              empty={view === 'mine' ? 'You have no offer out.' : 'Nobody left at this position.'}
            />
          )}
        </div>
        <RosterSheet
          team={team}
          focus={focus ?? state.players.find((p) => p.nome === open) ?? null}
          openOffers={myOffers.length}
          openOffersTotal={myOffers.reduce((sum, p) => sum + (p.active_user_offer?.salary ?? 0), 0)}
        />
      </div>
    </div>
  );
};
