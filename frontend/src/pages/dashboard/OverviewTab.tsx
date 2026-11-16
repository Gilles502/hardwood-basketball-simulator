import React, { useEffect, useRef, useState } from 'react';
import { Flame, Newspaper, Snowflake, Trophy } from 'lucide-react';
import { useLeagueStore } from '../../store/leagueStore';
import type { LeagueData } from '../../store/leagueStore';
import { useLiveStore } from '../../store/liveStore';
import type { DashboardSummary } from '../../store/liveStore';
import { TeamCrest } from '../../components/TeamCrest';
import { SimulationCard } from './SimulationCard';
import { leagueTable } from '../../utils/standings';
import { formatGameDate, ordinal, phaseLabel } from '../../utils/format';
import type { Tab } from '../../navigation';
import type { DashboardTab } from '../Dashboard';
import { kindClass, kindLabel, whenLabel } from '../../utils/news';
import type { NewsItem } from '../../utils/news';
import '../News.css';

const CATEGORY_LABELS: Record<string, string> = {
  punti: 'Points (PPG)', points: 'Points (PPG)',
  rimbalzi: 'Rebounds (RPG)', rebounds: 'Rebounds (RPG)',
  assist: 'Assists (APG)', assists: 'Assists (APG)',
  stoppate: 'Blocks (BPG)', blocks: 'Blocks (BPG)',
  recuperi: 'Steals (SPG)', steals: 'Steals (SPG)',
};

function leaderValue(category: string, stats: { ppg: number; rpg: number; apg: number; bpg: number; spg: number }): number {
  switch (category.toLowerCase()) {
    case 'punti': case 'points': return stats.ppg;
    case 'rimbalzi': case 'rebounds': return stats.rpg;
    case 'assist': case 'assists': return stats.apg;
    case 'stoppate': case 'blocks': return stats.bpg;
    default: return stats.spg;
  }
}

/** Opponent of the user's unfinished playoff series, if any. */
function playoffOpponent(leagueData: LeagueData, teamName: string): string | null {
  const bracket = leagueData.playoffs?.bracket;
  if (!bracket) return null;
  const all = [
    ...(bracket.east?.qf || []), ...(bracket.east?.sf || []), ...(bracket.east?.cf || []),
    ...(bracket.west?.qf || []), ...(bracket.west?.sf || []), ...(bracket.west?.cf || []),
    ...(bracket.finals || []),
  ];
  const series = all.find((s) => s && (s.s1_nome === teamName || s.s2_nome === teamName) && !s.winner_nome);
  if (!series) return null;
  return series.s1_nome === teamName ? series.s2_nome : series.s1_nome;
}

const HeroCard: React.FC<{ label: string; children: React.ReactNode; accent?: boolean }> = ({ label, children, accent }) => (
  <div className={`card dash-hero-card${accent ? ' is-accent' : ''}`}>
    <div className="dash-label">{label}</div>
    {children}
  </div>
);

const NextGameCard: React.FC<{ summary: DashboardSummary | null; leagueData: LeagueData; teamName: string }> = ({ summary, leagueData, teamName }) => {
  const next = summary?.next_game ?? null;
  if (next) {
    return (
      <HeroCard label={`Next game · ${next.is_home ? 'Home' : 'Away'}`} accent>
        <div className="dash-matchup">
          <TeamCrest name={teamName} size={40} />
          <span className="dash-vs">{next.is_home ? 'vs' : '@'}</span>
          <TeamCrest name={next.opponent} size={40} />
          <div className="dash-matchup-text">
            <div className="dash-strong" title={next.opponent}>{next.opponent}</div>
            <div className="dash-sub">
              {[next.opponent_record, next.opponent_rank && next.opponent_record !== '0-0' ? `${ordinal(next.opponent_rank)} ${next.opponent_conference ?? ''}`.trim() : null]
                .filter(Boolean).join(' · ')}
            </div>
          </div>
        </div>
        <div className="dash-sub">{formatGameDate(next.date)}</div>
      </HeroCard>
    );
  }
  const playoffOpp = playoffOpponent(leagueData, teamName);
  if (playoffOpp) {
    return (
      <HeroCard label="Playoff series" accent>
        <div className="dash-matchup">
          <TeamCrest name={teamName} size={40} />
          <span className="dash-vs">vs</span>
          <TeamCrest name={playoffOpp} size={40} />
          <div className="dash-matchup-text"><div className="dash-strong">{playoffOpp}</div></div>
        </div>
      </HeroCard>
    );
  }
  return (
    <HeroCard label="Next game">
      <div className="dash-strong">{!summary ? 'Loading…' : summary.total_days === 0 ? 'Season not started' : 'No upcoming game'}</div>
      <div className="dash-sub">{phaseLabel(leagueData.league_state, leagueData.current_day || 0)}</div>
    </HeroCard>
  );
};

const LastResultCard: React.FC<{ summary: DashboardSummary | null }> = ({ summary }) => {
  const last = summary?.last_result ?? null;
  if (!last) {
    return (
      <HeroCard label="Last result">
        <div className="dash-strong">No games played yet</div>
        <div className="dash-sub">Results appear after your first game</div>
      </HeroCard>
    );
  }
  return (
    <HeroCard label="Last result">
      <div className={`dash-big ${last.won ? 'is-win' : 'is-loss'}`}>{last.won ? 'W' : 'L'} {last.points_for}-{last.points_against}</div>
      <div className="dash-sub">{last.is_home ? 'vs' : 'at'} {last.opponent} · {formatGameDate(last.date)}</div>
    </HeroCard>
  );
};

const StandingCard: React.FC<{ summary: DashboardSummary | null; onOpen: () => void }> = ({ summary, onOpen }) => {
  const team = summary?.team ?? null;
  if (!summary || !team || !team.conference) {
    return <HeroCard label="Standing"><div className="dash-strong">—</div></HeroCard>;
  }
  const played = team.record !== '0-0';
  const rows = team.conference === 'West' ? summary.standings.west : summary.standings.east;
  const row = rows.find((candidate) => candidate.nome === team.name);
  return (
    <HeroCard label="Standing">
      <div className="dash-big">{played && team.conf_rank ? `${ordinal(team.conf_rank)} ${team.conference}` : team.conference}</div>
      <div className="dash-sub">
        {played && row ? `${row.gb === 0 ? 'Leading' : `${row.gb} GB`}${row.streak ? ` · Streak ${row.streak}` : ''}` : 'Season not started'}
      </div>
      <button className="dash-link" onClick={onOpen}>Open Standings →</button>
    </HeroCard>
  );
};

const SpectatorHero: React.FC<{ summary: DashboardSummary | null }> = ({ summary }) => {
  const rows = summary ? leagueTable(summary.standings.west, summary.standings.east) : [];
  const leader = rows[0];
  const hot = rows.find((row) => row.tag === 'hot');
  const cold = rows.find((row) => row.tag === 'cold');
  const teamLine = (row: typeof leader | undefined, empty: string) => row
    ? (<><div className="dash-strong">{row.nome}</div><div className="dash-sub">{row.v}-{row.s}{row.streak ? ` · ${row.streak}` : ''}</div></>)
    : <div className="dash-sub">{empty}</div>;
  return (
    <>
      <HeroCard label="League leader">{teamLine(leader, 'Season not started')}</HeroCard>
      <HeroCard label="Hottest team">{teamLine(hot, 'No team is hot yet')}</HeroCard>
      <HeroCard label="Coldest team">{teamLine(cold, 'No team is cold yet')}</HeroCard>
    </>
  );
};

const MiniStandingsCard: React.FC<{ summary: DashboardSummary | null; onOpen: () => void }> = ({ summary, onOpen }) => {
  const conference = summary?.team?.conference === 'East' ? 'East' : 'West';
  const rows = summary ? (conference === 'East' ? summary.standings.east : summary.standings.west) : [];
  const myName = summary?.team?.name ?? null;
  const top = rows.slice(0, 5);
  const mine = myName ? rows.find((row) => row.nome === myName) : undefined;
  const shown = mine && !top.includes(mine) ? [...top, mine] : top;
  return (
    <div className="card dash-block">
      <div className="dash-label">{conference} standings</div>
      {shown.length === 0 ? (
        <div className="dash-sub">{summary ? 'Standings appear once the season starts.' : 'Loading…'}</div>
      ) : shown.map((row, index) => (
        <React.Fragment key={row.nome}>
          {mine && row === mine && !top.includes(mine) && index === top.length && <div className="dash-gap" aria-hidden="true">···</div>}
          <div className={`dash-mini-row${row.nome === myName ? ' is-me' : ''}`}>
            <span className="dash-mini-pos">{row.pos}</span>
            <TeamCrest name={row.nome} size={20} />
            <span className="dash-mini-name">{row.nome}</span>
            {row.tag === 'hot' && <Flame size={13} className="dash-hot-icon" aria-label="Hot" />}
            {row.tag === 'cold' && <Snowflake size={13} className="dash-cold-icon" aria-label="Cold" />}
            <span className="dash-mini-record">{row.v}-{row.s}</span>
          </div>
        </React.Fragment>
      ))}
      <button className="dash-link" onClick={onOpen}>Open Standings →</button>
    </div>
  );
};

const HEADLINE_REFRESH_MS = 5_000;
const HEADLINE_COUNT = 4;

const HeadlinesCard: React.FC<{ updatedAt: number | undefined; onOpen: () => void }> = ({ updatedAt, onOpen }) => {
  const [headlines, setHeadlines] = useState<NewsItem[]>([]);
  const lastFetch = useRef(0);

  useEffect(() => {
    const now = Date.now();
    if (now - lastFetch.current < HEADLINE_REFRESH_MS) return;
    lastFetch.current = now;
    // Big stories only (a story about the user's team counts one tier higher).
    fetch(`/api/news?min_tier=3&limit=${HEADLINE_COUNT}&_t=${now}`)
      .then((response) => response.json())
      .then((data) => setHeadlines(data.news || []))
      .catch(() => { /* headlines are optional; the card just stays as it is */ });
  }, [updatedAt]);

  return (
    <div className="card dash-block">
      <div className="dash-label">Latest headlines</div>
      {headlines.length === 0 ? (
        <div className="dash-sub">No big stories yet.</div>
      ) : headlines.map((item) => (
        <div key={item.id} className="dash-headline">
          <span className={kindClass(item)}>{item.mine ? 'Your team' : kindLabel(item.kind)}</span>
          {' '}{item.title}
          {item.unread && <span className="nw-new">NEW</span>}
          <div className="nw-when">{whenLabel(item)}</div>
        </div>
      ))}
      <button className="dash-link" onClick={onOpen}><Newspaper size={12} style={{ marginRight: 4, verticalAlign: '-1px' }} />Open News →</button>
    </div>
  );
};

interface AttentionRow {
  key: string;
  tag: string;
  tone: 'danger' | 'primary' | 'warning';
  text: string;
  action?: { label: string; to: Tab };
}

const AttentionCard: React.FC<{ summary: DashboardSummary | null; leagueData: LeagueData; onNavigate: (tab: Tab) => void }> = ({ summary, leagueData, onNavigate }) => {
  const rows: AttentionRow[] = [];
  if (summary) {
    const { injuries, trade_offers, board_concern, pending_step } = summary.attention;
    injuries.slice(0, 3).forEach((injury) => rows.push({
      key: `inj-${injury.name}`, tag: 'INJURY', tone: 'danger',
      text: `${injury.name} out ~${injury.days} day${injury.days === 1 ? '' : 's'}`,
      action: { label: 'Roster', to: 'roster' },
    }));
    if (injuries.length > 3) rows.push({ key: 'inj-more', tag: 'INJURY', tone: 'danger', text: `+${injuries.length - 3} more injured`, action: { label: 'Roster', to: 'roster' } });
    if (trade_offers > 0) rows.push({
      key: 'trades', tag: 'TRADE', tone: 'primary',
      text: `${trade_offers} offer${trade_offers === 1 ? '' : 's'} on the trade block`,
      action: { label: 'Trade Center', to: 'trades' },
    });
    if (board_concern) rows.push({
      key: 'board', tag: 'BOARD', tone: 'warning', text: 'The board wants a word with you',
      action: { label: 'Front Office', to: 'board' },
    });
    if (pending_step.startsWith('OFFSEASON') || pending_step === 'DRAFT_USER_PICK') {
      rows.push({
        key: 'offseason', tag: 'OFFSEASON', tone: 'primary', text: phaseLabel(pending_step, leagueData.current_day || 0),
        action: { label: 'End of Season Hub', to: 'offseason' },
      });
    }
  }
  return (
    <div className="card dash-attention">
      <div className="dash-label">Needs your attention</div>
      {rows.length === 0 ? (
        <div className="dash-sub">{summary ? 'All clear. Nothing needs you right now.' : 'Loading…'}</div>
      ) : rows.map((row) => (
        <div key={row.key} className="dash-attn-row">
          <span className={`dash-tag dash-tag-${row.tone}`}>{row.tag}</span>
          <span className="dash-attn-text">{row.text}</span>
          {row.action && <button className="dash-link" onClick={() => onNavigate(row.action!.to)}>{row.action.label} →</button>}
        </div>
      ))}
    </div>
  );
};

interface OverviewTabProps {
  onNavigate: (tab: Tab) => void;
  onOpenTab: (tab: DashboardTab) => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({ onNavigate, onOpenTab }) => {
  const leagueData = useLeagueStore((state) => state.leagueData);
  const summary = useLiveStore((state) => state.summary);
  if (!leagueData) return null;

  const teamName = leagueData.player_team_name;
  const { classifica, playoffs, league_state } = leagueData;
  const isPlayoffs = league_state === 'PLAYOFFS';

  return (
    <div className="dash-overview">
      <div className="dash-hero">
        {teamName ? (
          <>
            <NextGameCard summary={summary} leagueData={leagueData} teamName={teamName} />
            <LastResultCard summary={summary} />
            <StandingCard summary={summary} onOpen={() => onOpenTab('standings')} />
          </>
        ) : (
          <SpectatorHero summary={summary} />
        )}
      </div>

      <div className="dash-row2">
        <SimulationCard onOpenHub={() => onNavigate('offseason')} />
        <AttentionCard summary={summary} leagueData={leagueData} onNavigate={onNavigate} />
      </div>

      {isPlayoffs && playoffs?.bracket && (
        <div className="card dash-block">
          <h3 className="card-title"><Trophy size={20} className="logo-gold" /> Playoffs Bracket</h3>
          <div className="dash-bracket">
            {([['Eastern Conference', playoffs.bracket.east.qf], ['Western Conference', playoffs.bracket.west.qf]] as const).map(([title, series]) => (
              <div key={title} className="dash-bracket-col">
                <h4>{title}</h4>
                {series.map((s, index) => (
                  <div key={index} className="dash-series">
                    <div className="flex-between">
                      <span style={{ fontWeight: s.winner_nome === s.s1_nome ? 700 : 500 }}>({s.s1_seed}) {s.s1_nome}</span>
                      <span style={{ fontWeight: 700 }}>{s.s1_vittorie}</span>
                    </div>
                    <div className="flex-between">
                      <span style={{ fontWeight: s.winner_nome === s.s2_nome ? 700 : 500 }}>({s.s2_seed}) {s.s2_nome}</span>
                      <span style={{ fontWeight: 700 }}>{s.s2_vittorie}</span>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="dash-row3">
        <MiniStandingsCard summary={summary} onOpen={() => onOpenTab('standings')} />
        <div className="card dash-block">
          <div className="dash-label">League stat leaders</div>
          {classifica.stat_leaders ? (
            <div className="dash-leaders">
              {Object.entries(classifica.stat_leaders).map(([category, leader]) => (
                <div key={category} className="dash-leader">
                  <div>
                    <div className="dash-strong">{CATEGORY_LABELS[category.toLowerCase()] || category}</div>
                    <div className="dash-sub">{leader.nome}</div>
                  </div>
                  <div className="dash-leader-value">{leaderValue(category, leader.stats)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="dash-sub">No statistical data available for this season yet.</div>
          )}
        </div>
        <HeadlinesCard updatedAt={summary?.updated_at} onOpen={() => onOpenTab('news')} />
      </div>
    </div>
  );
};
