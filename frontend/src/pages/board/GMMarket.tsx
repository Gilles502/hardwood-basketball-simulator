// GM market tab: GMs without a team who could be hired now (historical arrivals show up from their real year).
// Retired GMs are gone from the list.
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../../store/leagueStore';
import { StatTable, type Column } from '../analytics/StatTable';
import type { GMMarketPayload, MarketGM } from './types';

const skill = (key: 'trade' | 'contracts' | 'draft', label: string, title: string): Column<MarketGM> => ({
  key, label, title, value: (r) => r.skills[key], pct: (r) => r.skills[key],
});

const COLUMNS: Column<MarketGM>[] = [
  {
    key: 'name', label: 'GM', left: true, value: (r) => r.name,
    format: (_v, r) => <span className="an-name"><b>{r.name}</b>{!r.historical && <span className="an-tag is-gone">New face</span>}</span>,
  },
  { key: 'age', label: 'Age', value: (r) => r.age },
  { key: 'exp', label: 'Years as GM', value: (r) => r.years_as_gm },
  {
    key: 'jobs', label: 'Previous jobs', title: 'Jobs held before; titles and playoff runs in brackets', value: (r) => r.jobs,
    format: (_v, r) => (r.jobs === 0 ? '0' : <span>{r.jobs}<span className="fo-career-years"> ({r.titles} {r.titles === 1 ? 'title' : 'titles'}, {r.playoffs} {r.playoffs === 1 ? 'playoff' : 'playoffs'})</span></span>),
  },
  {
    key: 'traits', label: 'Philosophy', left: true, value: (r) => r.traits.join(', '),
    format: (_v, r) => <span className="fo-traits">{r.traits.join(' · ')}</span>,
  },
  skill('trade', 'TRD', 'Trade skill'),
  skill('contracts', 'CTR', 'Contracts skill (free agency, extensions)'),
  skill('draft', 'DRF', 'Draft evaluation skill'),
];

export const GMMarket: React.FC = () => {
  const leagueData = useLeagueStore((s) => s.leagueData);
  const [data, setData] = useState<GMMarketPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/front_office/market?_t=${Date.now()}`)
      .then((r) => r.json())
      .then((json) => { if (json.error) setFailed(json.error); else { setData(json); setFailed(null); } })
      .catch(() => setFailed('Could not load the GM market.'));
  }, [leagueData?.stagione, leagueData?.player_team_name]);

  if (failed) return <div className="an-empty"><h2>GM market unavailable</h2><p>{failed}</p></div>;
  if (!data) return <div className="an-loading"><div className="spinner"></div></div>;

  return (
    <div className="an-root">
      <p className="fo-note">
        GMs without a job in {data.year}. Teams hire from here when a seat opens; GMs who arrived later in real life join
        the market around their real first year.
      </p>
      {data.unemployed.length === 0 ? (
        <div className="an-empty"><h2>Nobody on the market</h2><p>Every available GM has a job right now.</p></div>
      ) : (
        <div className="an-panel">
          <StatTable<MarketGM> rows={data.unemployed} columns={COLUMNS} rowKey={(r) => r.gm_id} defaultSort="trade"
            tintTop={75} tintBottom={49} caption="Unemployed general managers" />
        </div>
      )}
    </div>
  );
};
