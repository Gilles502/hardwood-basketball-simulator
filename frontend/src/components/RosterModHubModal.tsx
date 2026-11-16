// File: frontend/src/components/RosterModHubModal.tsx
import React, { useCallback, useEffect, useState } from 'react';
import { useSettingsStore } from '../store/settingsStore';
import { t } from '../utils/i18n';
import { ModalShell } from './ModalShell';
import { Layers } from 'lucide-react';
import './RosterModHubModal.css';

interface RosterModHubModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface LeagueInfo {
  id: string;
  name: string;
  era: string;
  source: 'builtin' | 'mod';
  team_count: number;
  has_draft_classes: boolean;
  built: boolean;
  active: boolean;
  errors: string[];
}

export const RosterModHubModal: React.FC<RosterModHubModalProps> = ({ isOpen, onClose }) => {
  const { language } = useSettingsStore();
  const [leagues, setLeagues] = useState<LeagueInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [buildingId, setBuildingId] = useState<string | null>(null);
  // Errors returned by a failed build, shown under that league's card
  const [buildErrors, setBuildErrors] = useState<Record<string, string[]>>({});

  const loadLeagues = useCallback(async () => {
    try {
      const res = await fetch('/api/leagues');
      const data = await res.json();
      if (!res.ok || !Array.isArray(data.leagues)) throw new Error(data.error || `HTTP ${res.status}`);
      setLeagues(data.leagues);
      setLoadError(null);
    } catch (err: any) {
      setLoadError(err.message || String(err));
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    setLeagues(null);
    setBuildErrors({});
    loadLeagues();
  }, [isOpen, loadLeagues]);

  if (!isOpen) return null;

  const handleBuild = async (id: string) => {
    setBuildingId(id);
    setBuildErrors(prev => ({ ...prev, [id]: [] }));
    try {
      const res = await fetch('/api/leagues/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ league_id: id }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        setBuildErrors(prev => ({ ...prev, [id]: data.errors?.length ? data.errors : [`HTTP ${res.status}`] }));
      }
    } catch (err: any) {
      setBuildErrors(prev => ({ ...prev, [id]: [err.message || String(err)] }));
    } finally {
      setBuildingId(null);
      await loadLeagues();
    }
  };

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title={t('mod_hub_title', language)}
      subtitle={t('mod_hub_subtitle', language)}
      icon={<Layers size={22} />}
      maxWidth={760}
      footerStart={<span>{t('mod_hub_footer_note', language)}</span>}
      footerEnd={<button className="ms-btn ms-btn-secondary" onClick={onClose}>{t('btn_close', language)}</button>}
    >
      <div className="mods-body">
        {leagues === null && !loadError && <p className="mods-status">{t('mod_hub_loading', language)}</p>}
        {loadError && <p className="mods-status is-error">{t('mod_hub_load_error', language)}: {loadError}</p>}

        {leagues?.map(lg => {
          const errors = [...lg.errors, ...(buildErrors[lg.id] || [])];
          const invalid = lg.errors.length > 0;
          const building = buildingId === lg.id;
          return (
            <div key={lg.id} className={`mods-card${lg.active ? ' is-active' : ''}`}>
              <div className="mods-card-top">
                <p className="mods-card-name">{lg.name}</p>
                <span className="mods-pill mods-pill-src">{t(lg.source === 'builtin' ? 'mod_hub_builtin' : 'mod_hub_mod', language)}</span>
                {lg.active ? (
                  <span className="mods-pill mods-pill-active">{t('mod_hub_active', language)}</span>
                ) : invalid ? (
                  <span className="mods-pill mods-pill-error">{lg.errors.length} {t(lg.errors.length === 1 ? 'mod_hub_error' : 'mod_hub_errors', language)}</span>
                ) : lg.built ? (
                  <span className="mods-pill mods-pill-built">{t('mod_hub_built', language)}</span>
                ) : null}
                {!lg.active && (
                  <button
                    className="ms-btn ms-btn-primary"
                    disabled={invalid || buildingId !== null}
                    onClick={() => handleBuild(lg.id)}
                  >
                    {building ? t('mod_hub_building', language) : t('mod_hub_build_use', language)}
                  </button>
                )}
              </div>
              <div className="mods-meta">
                {lg.era && <span>{t('mod_hub_era', language)} {lg.era}</span>}
                <span>{lg.team_count} {t('mod_hub_teams', language)}</span>
                <span>{t(lg.has_draft_classes ? 'mod_hub_draft_custom' : 'mod_hub_draft_generated', language)}</span>
              </div>
              {errors.length > 0 && (
                <ul className="mods-errors">
                  {errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
            </div>
          );
        })}

        <p className="mods-hint">
          {t('mod_hub_folder_hint_pre', language)} <code>mods/&lt;{t('mod_hub_folder_name', language)}&gt;/league.json</code> {t('mod_hub_folder_hint_post', language)}
        </p>
      </div>
    </ModalShell>
  );
};
