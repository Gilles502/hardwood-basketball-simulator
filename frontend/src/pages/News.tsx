import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { useLiveStore } from '../store/liveStore';
import { kindClass, kindLabel, whenLabel } from '../utils/news';
import type { NewsItem } from '../utils/news';
import './News.css';

interface NewsClock {
  season: number | null;
  day: number | null;
  date: string;
  phase: string;
}

type Period = 'new' | 'week' | 'season' | 'all';
type Filter = 'all' | 'mine' | 'trade' | 'injury' | 'contracts' | 'rumor';

const CONTRACT_KINDS = new Set(['signing', 'extension', 'free_agency', 'cut']);
const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' }, { id: 'mine', label: 'My team' }, { id: 'trade', label: 'Trades' },
  { id: 'injury', label: 'Injuries' }, { id: 'contracts', label: 'Signings' }, { id: 'rumor', label: 'Rumors' },
];
const PLAN_LABEL: Record<string, string> = {
  CONTENDER: 'contending', PLAYOFF: 'playoff team', MIDDLE: 'in the middle', REBUILDER: 'rebuilding',
};
const GROUPS_PER_PAGE = 20;
const SIDE_ROWS = 5;

const groupKey = (item: NewsItem) => `${item.season}|${item.day ?? item.phase}`;

const matchesFilter = (item: NewsItem, filter: Filter) => {
  if (filter === 'all') return true;
  if (filter === 'mine') return item.mine;
  if (filter === 'contracts') return CONTRACT_KINDS.has(item.kind);
  return item.kind === filter;
};

const StoryDetails: React.FC<{ item: NewsItem }> = ({ item }) => {
  const openPlayerProfile = useLeagueStore((s) => s.openPlayerProfile);
  const openTeamProfile = useLeagueStore((s) => s.openTeamProfile);
  const sides = item.details?.sides ?? [];
  const games = item.details?.games ?? [];

  return (
    <div className="nw-open">
      {item.body && <p>{item.body}</p>}
      {sides.map((side) => (
        <div key={side.team}>
          <p><b>{side.team}</b> get {side.gets.length ? side.gets.join(', ') : 'nothing back'}.</p>
          {(side.reasons?.length ?? 0) > 0 && (
            <div className="nw-quote">
              "{side.reasons!.join('; ')}" — {side.gm || `${side.team} GM`}
              {side.plan && PLAN_LABEL[side.plan] ? ` (${PLAN_LABEL[side.plan]})` : ''}
            </div>
          )}
        </div>
      ))}
      {games.length > 0 && (
        <div className="nw-games">
          {games.map((g) => (
            <span key={g.game}>G{g.game}: {g.away} {g.away_score} – {g.home_score} {g.home}</span>
          ))}
        </div>
      )}
      {(item.players.length > 0 || item.teams.length > 0) && (
        <div className="nw-links">
          {item.players.map((name) => (
            <button key={`p-${name}`} type="button" className="nw-btn" onClick={() => openPlayerProfile(name)}>{name}</button>
          ))}
          {item.teams.map((name) => (
            <button key={`t-${name}`} type="button" className="nw-btn" onClick={() => openTeamProfile(name)}>{name}</button>
          ))}
        </div>
      )}
    </div>
  );
};

export const News: React.FC = () => {
  const updatedAt = useLiveStore((state) => state.summary?.updated_at);
  const [items, setItems] = useState<NewsItem[]>([]);
  const [clock, setClock] = useState<NewsClock | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [openId, setOpenId] = useState<number | null>(null);
  const [unfolded, setUnfolded] = useState<Set<string>>(new Set());
  const [pages, setPages] = useState(1);
  // What was read before the page opened: "new" keeps meaning "after that" for the whole visit.
  const [baseline, setBaseline] = useState(0);
  const marked = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/news?limit=1500&_t=${Date.now()}`)
      .then((response) => response.json())
      .then((data) => {
        if (cancelled) return;
        if (data.error) { setError(data.error); return; }
        if (!marked.current) {
          marked.current = true;
          setBaseline(data.last_seen_id ?? 0);
          fetch('/api/news/seen', { method: 'POST' }).catch(() => { /* the unread mark is a convenience */ });
        }
        setItems(data.news || []);
        setClock(data.clock || null);
        setError(null);
        setLoaded(true);
      })
      .catch(() => { if (!cancelled) setError('Could not load the news.'); });
    return () => { cancelled = true; };
  }, [updatedAt]);

  const inPeriod = useMemo(() => {
    return (item: NewsItem, which: Period) => {
      if (which === 'all') return true;
      if (which === 'new') return item.id > baseline;
      if (!clock || item.season !== clock.season) return false;
      if (which === 'season') return true;
      if (clock.day !== null && item.day !== null) return item.day >= clock.day - 6;
      return clock.day === null && item.phase === clock.phase;
    };
  }, [clock, baseline]);

  const newCount = useMemo(() => items.filter((item) => inPeriod(item, 'new')).length, [items, inPeriod]);
  // Default period: what is new, else the last week, else the season.
  const activePeriod: Period = period
    ?? (newCount > 0 ? 'new' : items.some((item) => inPeriod(item, 'week')) ? 'week' : 'season');

  const shown = useMemo(
    () => items.filter((item) => inPeriod(item, activePeriod) && matchesFilter(item, filter)),
    [items, inPeriod, activePeriod, filter],
  );

  const top = useMemo(
    () => [...shown].filter((item) => item.tier >= 2).sort((a, b) => b.tier - a.tier || b.id - a.id).slice(0, 3),
    [shown],
  );

  const groups = useMemo(() => {
    const list: { key: string; label: string; items: NewsItem[] }[] = [];
    for (const item of shown) {
      const key = groupKey(item);
      const last = list[list.length - 1];
      if (last && last.key === key) last.items.push(item);
      else list.push({ key, label: whenLabel(item), items: [item] });
    }
    return list;
  }, [shown]);

  const seasonItems = useMemo(() => items.filter((item) => inPeriod(item, 'season')), [items, inPeriod]);
  const mine = seasonItems.filter((item) => item.mine).slice(0, SIDE_ROWS);
  const rumors = seasonItems.filter((item) => item.kind === 'rumor').slice(0, SIDE_ROWS);

  const periods: { id: Period; label: string }[] = [
    ...(newCount > 0 ? [{ id: 'new' as Period, label: `Since last visit · ${newCount}` }] : []),
    { id: 'week', label: 'This week' }, { id: 'season', label: 'Season' }, { id: 'all', label: 'All' },
  ];

  const toggleFold = (key: string) => setUnfolded((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const focusStory = (item: NewsItem) => {
    setOpenId(item.id);
    setUnfolded((current) => new Set(current).add(groupKey(item)));
    requestAnimationFrame(() => document.getElementById(`nw-item-${item.id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  };

  const renderLine = (item: NewsItem) => {
    const size = item.tier >= 3 ? ' is-big' : item.tier === 2 ? ' is-medium' : ' is-minor';
    const isOpen = openId === item.id;
    return (
      <React.Fragment key={item.id}>
        <button
          type="button"
          id={`nw-item-${item.id}`}
          className={`nw-line${size}`}
          aria-expanded={isOpen}
          onClick={() => setOpenId(isOpen ? null : item.id)}
        >
          <span className={kindClass(item)}>{item.mine ? 'Your team' : kindLabel(item.kind)}</span>
          <span className="nw-title">
            {item.title}
            {item.id > baseline && activePeriod !== 'new' && <span className="nw-new">NEW</span>}
          </span>
          <span className="nw-caret">{isOpen ? '▾' : '▸'}</span>
        </button>
        {isOpen && <StoryDetails item={item} />}
      </React.Fragment>
    );
  };

  if (error) return <div className="card nw-empty">{error}</div>;
  if (!loaded) return <div className="card nw-empty">Loading the news…</div>;

  return (
    <div className="nw">
      <div className="nw-toolbar">
        <div className="nw-chips" role="group" aria-label="Period">
          {periods.map((p) => (
            <button key={p.id} type="button" className={`nw-chip${activePeriod === p.id ? ' is-active' : ''}`}
              aria-pressed={activePeriod === p.id} onClick={() => { setPeriod(p.id); setPages(1); }}>{p.label}</button>
          ))}
        </div>
        <div className="nw-chips" role="group" aria-label="Kind of news">
          {FILTERS.map((f) => (
            <button key={f.id} type="button" className={`nw-chip${filter === f.id ? ' is-active' : ''}`}
              aria-pressed={filter === f.id} onClick={() => { setFilter(f.id); setPages(1); }}>{f.label}</button>
          ))}
        </div>
      </div>

      {top.length > 0 && (
        <>
          <div className="nw-label">Top stories</div>
          <div className="nw-heroes">
            {top.map((item) => (
              <button key={item.id} type="button" className="card nw-hero" onClick={() => focusStory(item)}>
                <span className={kindClass(item)}>{item.mine ? `Your team · ${kindLabel(item.kind)}` : kindLabel(item.kind)}</span>
                <h3>{item.title}</h3>
                {item.body && <p>{item.body}</p>}
                <div className="nw-when">{whenLabel(item)}</div>
              </button>
            ))}
          </div>
        </>
      )}

      <div className="nw-grid">
        <div className="card">
          <div className="nw-label">League feed</div>
          {groups.length === 0 && <div className="nw-empty">No news for this selection yet.</div>}
          {groups.slice(0, pages * GROUPS_PER_PAGE).map((group) => {
            const main = group.items.filter((item) => item.tier >= 2);
            const minor = group.items.filter((item) => item.tier < 2);
            // A filter already narrows the list: fold minor stories only in the full view.
            const fold = filter === 'all' && main.length > 0 && !unfolded.has(group.key);
            return (
              <section key={group.key}>
                <h4 className="nw-day">{group.label}</h4>
                {main.map(renderLine)}
                {fold ? (
                  minor.length > 0 && (
                    <button type="button" className="nw-fold" onClick={() => toggleFold(group.key)}>
                      ▸ {minor.length} minor {minor.length === 1 ? 'story' : 'stories'}
                    </button>
                  )
                ) : minor.map(renderLine)}
              </section>
            );
          })}
          {groups.length > pages * GROUPS_PER_PAGE && (
            <button type="button" className="nw-fold" onClick={() => setPages(pages + 1)}>Show older news</button>
          )}
        </div>

        <div className="nw-side">
          <div className="card">
            <div className="nw-label">Your team · this season</div>
            {mine.length === 0 && <div className="nw-empty">Nothing about your team yet.</div>}
            {mine.map((item) => (
              <div key={item.id} className="nw-side-row">
                {item.title}
                <div className="nw-when">{whenLabel(item)}</div>
              </div>
            ))}
          </div>
          <div className="card">
            <div className="nw-label">Rumor mill</div>
            {rumors.length === 0 && <div className="nw-empty">The league is quiet.</div>}
            {rumors.map((item) => (
              <div key={item.id} className="nw-side-row">
                {item.title}
                <div className="nw-when">{whenLabel(item)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
