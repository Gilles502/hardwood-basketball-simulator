import React, { useEffect, useState } from 'react';
import { Check, Download } from 'lucide-react';
import { ModalShell } from './ModalShell';
import './ExportDataModal.css';

interface AvailableSeason {
  season: number;
  year: number;
  label: string;
  is_completed: boolean;
  is_current: boolean;
  gp: number;
  champion: string | null;
}

interface ExportDataModalProps {
  isOpen: boolean;
  onClose: () => void;
  seasonNumber?: number;
  calendarYear?: number;
}

type Category = 'all' | 'players' | 'team_summaries' | 'standings' | 'awards' | 'rosters' | 'trades';
type Format = 'csv' | 'json';

const SINGLE_FILES: { category: Category; name: string; detail: string }[] = [
  { category: 'players', name: 'Player stats', detail: 'Per-game lines, shooting, playoffs' },
  { category: 'team_summaries', name: 'Team summaries', detail: 'PPG, Opp PPG, point diff, ratings' },
  { category: 'standings', name: 'Standings', detail: 'W-L, win %, point diff' },
  { category: 'awards', name: 'Awards & All-Star', detail: 'MVP, DPOY, ROY, All-NBA, All-Stars' },
  { category: 'rosters', name: 'Rosters & contracts', detail: 'Salaries, options, years left' },
  { category: 'trades', name: 'Trades', detail: 'Every trade made' },
];

const DONE_MS = 2000;

function seasonOptionText(s: AvailableSeason): string {
  if (s.champion) return `${s.label} · Champion: ${s.champion}`;
  if (s.is_current) return s.gp > 0 ? `${s.label} · in progress · ${s.gp} GP` : `${s.label} · not started`;
  return s.label;
}

export const ExportDataModal: React.FC<ExportDataModalProps> = ({
  isOpen,
  onClose,
  seasonNumber = 1,
}) => {
  const [seasons, setSeasons] = useState<AvailableSeason[] | null>(null);
  const [selectedSeason, setSelectedSeason] = useState<string>(String(seasonNumber));
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setSeasons(null);
    setDone(null);
    fetch(`/api/export/available-seasons?_t=${Date.now()}`)
      .then(res => res.json())
      .then(data => {
        setSeasons(Array.isArray(data?.seasons) ? data.seasons : []);
        if (data?.default_season) setSelectedSeason(String(data.default_season));
      })
      .catch(() => setSeasons([]));
  }, [isOpen]);

  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => setDone(null), DONE_MS);
    return () => clearTimeout(t);
  }, [done]);

  const download = (format: Format, category: Category) => {
    const link = document.createElement('a');
    link.href = `/api/export/season?format=${format}&category=${category}&season=${selectedSeason}&_t=${Date.now()}`;
    link.setAttribute('download', '');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setDone(`${format}_${category}`);
  };

  const ready = seasons !== null && seasons.length > 0;
  const isAll = selectedSeason === 'all';

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title="Export data"
      subtitle="Spreadsheets of a season, or of every season"
      icon={<Download size={20} />}
      maxWidth={520}
      footerStart={ready ? (
        <button className="xd-link" onClick={() => download('json', 'all')}>
          {done === 'json_all' ? 'JSON downloaded ✓' : 'Download as JSON instead'}
        </button>
      ) : undefined}
    >
      <div className="xd">
        {seasons === null ? (
          <div className="spinner" style={{ margin: '32px auto' }} />
        ) : !ready ? (
          <p className="xd-muted">Start or load a career to export its data.</p>
        ) : (
          <>
            <label className="xd-field">
              <span className="xd-kicker">Season</span>
              <select className="xd-select" value={selectedSeason} onChange={(e) => setSelectedSeason(e.target.value)}>
                {[...seasons].reverse().map((s) => (
                  <option key={s.season} value={String(s.season)}>{seasonOptionText(s)}</option>
                ))}
                {seasons.length > 1 && <option value="all">All seasons · full archive</option>}
              </select>
            </label>

            <button className="xd-main" onClick={() => download('csv', 'all')}>
              <span>
                <span className="xd-main-title">
                  {done === 'csv_all' ? 'Downloaded ✓' : 'Download everything (.zip)'}
                </span>
                <span className="xd-main-detail">
                  {isAll ? 'Every season, all six files' : 'Player stats, teams, standings, awards, rosters, trades'}
                </span>
              </span>
              {done === 'csv_all' ? <Check size={22} /> : <Download size={22} />}
            </button>

            <div>
              <div className="xd-kicker">Or just one file</div>
              <ul className="xd-files">
                {SINGLE_FILES.map((f) => {
                  const isDone = done === `csv_${f.category}`;
                  return (
                    <li key={f.category} className="xd-file">
                      <div>
                        <div className="xd-file-name">{f.name}</div>
                        <div className="xd-file-detail">{f.detail}</div>
                      </div>
                      <button className={`xd-pill${isDone ? ' is-done' : ''}`} onClick={() => download('csv', f.category)}
                        aria-label={`Download ${f.name} as CSV`}>
                        {isDone ? '✓ Downloaded' : 'CSV'}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          </>
        )}
      </div>
    </ModalShell>
  );
};
