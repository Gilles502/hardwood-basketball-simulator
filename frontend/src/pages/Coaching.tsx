// Coaching page (mockup A): your head coach in a status column, three tabs on the right:
// Fit with roster, Coach market, League coaches. Data from /api/coaching/state; dialogs in coaching/CoachDialogs.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { CoachStatus } from './coaching/CoachStatus';
import { FitTab } from './coaching/FitTab';
import { MarketTab } from './coaching/MarketTab';
import { LeagueCoachesTab } from './coaching/LeagueCoachesTab';
import { ExtendCoachDialog, FireCoachDialog, HireCoachDialog } from './coaching/CoachDialogs';
import type { Coach, CoachingState } from './coaching/types';
import './dashboard/Dashboard.css'; // dash-header
import './analytics/Analytics.css'; // tables and filters
import './board/Office.css'; // status column, cards, pills, segmented tabs
import './coaching/Coaching.css';

type CoachingTab = 'fit' | 'market' | 'league';
type Dialog = { kind: 'extend' } | { kind: 'fire' } | { kind: 'hire'; candidate: Coach } | null;

export const Coaching: React.FC = () => {
  const leagueData = useLeagueStore((s) => s.leagueData);
  const hasTeam = !!leagueData?.player_team_name && !leagueData?.is_spectator;
  const [state, setState] = useState<CoachingState | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [tab, setTab] = useState<CoachingTab>(hasTeam ? 'fit' : 'league');
  const [dialog, setDialog] = useState<Dialog>(null);
  const [flash, setFlash] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null);
  const [spending, setSpending] = useState<string | null>(null);
  const tabRefs = useRef<Record<CoachingTab, HTMLButtonElement | null>>({ fit: null, market: null, league: null });

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/coaching/state?_t=${Date.now()}`);
      const json = await res.json();
      if (!res.ok || json.error) setFailed(json.error || 'Could not load the coaching staff.');
      else { setState(json); setFailed(null); }
    } catch {
      setFailed('Could not reach the server.');
    }
  }, []);

  useEffect(() => { load(); }, [load, leagueData?.stagione, leagueData?.player_team_name]);

  useEffect(() => {
    if (!flash) return;
    const id = window.setTimeout(() => setFlash(null), 5000);
    return () => window.clearTimeout(id);
  }, [flash]);

  const done = (text: string) => {
    setDialog(null);
    setFlash({ tone: 'ok', text });
    load();
  };

  const spendBadge = async (badge: string) => {
    setSpending(badge);
    try {
      const res = await fetch('/api/coaching/upgrade_badge', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ badge_name: badge }),
      });
      const json = await res.json();
      setFlash(res.ok && !json.error ? { tone: 'ok', text: json.message } : { tone: 'bad', text: json.error || 'Could not upgrade the badge.' });
      if (res.ok) load();
    } catch {
      setFlash({ tone: 'bad', text: 'Could not reach the server.' });
    } finally {
      setSpending(null);
    }
  };

  const coach = state?.current_coach ?? null;
  const market = state?.unemployed_coaches ?? [];
  const league = state?.league_coaches ?? [];
  const teamName = hasTeam ? (state?.team_name ?? leagueData?.player_team_name ?? '') : null;

  const tabs: { id: CoachingTab; label: string; count?: number }[] = hasTeam
    ? [{ id: 'fit', label: 'Fit with roster' }, { id: 'market', label: 'Coach market', count: market.length }, { id: 'league', label: 'League coaches', count: league.length }]
    : [{ id: 'league', label: 'League coaches', count: league.length }];
  const activeTab = tabs.some((t) => t.id === tab) ? tab : tabs[0].id;

  const moveTab = (index: number) => {
    const next = tabs[(index + tabs.length) % tabs.length].id;
    setTab(next);
    tabRefs.current[next]?.focus();
  };
  const onTabKey = (event: React.KeyboardEvent, index: number) => {
    if (event.key === 'ArrowRight') { event.preventDefault(); moveTab(index + 1); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); moveTab(index - 1); }
    else if (event.key === 'Home') { event.preventDefault(); moveTab(0); }
    else if (event.key === 'End') { event.preventDefault(); moveTab(tabs.length - 1); }
  };

  const header = (
    <div className="dash-header">
      <div>
        <h1 className="dash-title">Coaching</h1>
        <span className="dash-subtitle">
          {hasTeam ? `${teamName} head coach, how his schemes fit the roster, the coach market and the league's coaches` : "The league's head coaches"}
        </span>
      </div>
    </div>
  );

  if (failed && !state) return <div>{header}<div className="an-empty"><h2>Coaching unavailable</h2><p>{failed}</p></div></div>;
  if (!state) return <div>{header}<div className="an-loading"><div className="spinner"></div></div></div>;

  const panel = (
    <div className="of-col">
      <div className="of-seg" role="tablist" aria-label="Coaching sections">
        {tabs.map((t, index) => (
          <button key={t.id} ref={(node) => { tabRefs.current[t.id] = node; }} type="button" role="tab" id={`cc-tab-${t.id}`}
            aria-selected={activeTab === t.id} aria-controls={`cc-panel-${t.id}`} tabIndex={activeTab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)} onKeyDown={(e) => onTabKey(e, index)}>
            {t.label}{t.count !== undefined && <small>{t.count}</small>}
          </button>
        ))}
      </div>
      <div className="of-col" role="tabpanel" id={`cc-panel-${activeTab}`} aria-labelledby={`cc-tab-${activeTab}`}>
        {activeTab === 'fit' && (coach
          ? <FitTab coachName={coach.nome} />
          : <div className="of-card of-empty">Hire a coach to see how his schemes fit your roster.</div>)}
        {activeTab === 'market' && (
          <MarketTab coaches={market} currentCoach={coach?.nome ?? null} onPick={(c) => setDialog({ kind: 'hire', candidate: c })} />
        )}
        {activeTab === 'league' && <LeagueCoachesTab coaches={league} teamName={teamName} />}
      </div>
    </div>
  );

  return (
    <div>
      {header}
      <div className="of-root">
        {flash && (
          <div className={`cc-flash is-${flash.tone}`} role={flash.tone === 'bad' ? 'alert' : 'status'}>{flash.text}</div>
        )}
        {hasTeam ? (
          <div className="of-layout">
            <CoachStatus coach={coach} teamName={teamName ?? ''} spending={spending}
              onExtend={() => setDialog({ kind: 'extend' })} onFire={() => setDialog({ kind: 'fire' })}
              onSpendBadge={spendBadge} onBrowseMarket={() => setTab('market')} />
            {panel}
          </div>
        ) : panel}
      </div>

      {dialog?.kind === 'extend' && coach && <ExtendCoachDialog coach={coach} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.kind === 'fire' && coach && <FireCoachDialog coach={coach} onClose={() => setDialog(null)} onDone={done} />}
      {dialog?.kind === 'hire' && (
        <HireCoachDialog candidate={dialog.candidate} current={coach} onClose={() => setDialog(null)} onDone={done} />
      )}
    </div>
  );
};
