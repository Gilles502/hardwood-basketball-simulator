// File: frontend/src/components/SettingsModal.tsx
// Settings: only what really works. Interface size (this computer), the real saves folder, the version.
import React, { useEffect, useState } from 'react';
import { Cog, FolderOpen } from 'lucide-react';
import { UI_SCALES, useSettingsStore } from '../store/settingsStore';
import { ModalShell } from './ModalShell';
import './SettingsModal.css';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface AppInfo {
  version: string;
  saves_dir: string;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const { uiScale, setUiScale } = useSettingsStore();
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setOpenError(null);
    fetch('/api/app_info')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setInfo(data))
      .catch(() => setInfo(null));
  }, [isOpen]);

  const openSavesFolder = async () => {
    setOpenError(null);
    try {
      const res = await fetch('/api/open_saves_folder', { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) setOpenError(data.error || 'Could not open the folder.');
    } catch {
      setOpenError('Could not open the folder.');
    }
  };

  if (!isOpen) return null;

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title="Settings"
      subtitle="Interface size is kept on this computer; league rules live in each save."
      icon={<Cog size={22} />}
      maxWidth={620}
      footerEnd={<button className="ms-btn ms-btn-secondary" onClick={onClose}>Close</button>}
    >
      <div className="st-body">
        <section className="st-section">
          <h3 className="st-heading">Interface</h3>
          <div className="st-row">
            <div className="st-label">
              <span>Interface size</span>
              <small>Scales text and panels. Large suits big or high-resolution screens.</small>
            </div>
            <div className="st-seg" role="radiogroup" aria-label="Interface size">
              {UI_SCALES.map((s) => (
                <button
                  key={s.value}
                  role="radio"
                  aria-checked={uiScale === s.value}
                  className={`st-seg-btn${uiScale === s.value ? ' is-active' : ''}`}
                  onClick={() => setUiScale(s.value)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="st-section">
          <h3 className="st-heading">Game files</h3>
          <div className="st-row">
            <div className="st-label">
              <span>Saves folder</span>
              <code className="st-path">{info ? info.saves_dir : '…'}</code>
              {openError && <small className="st-error">{openError}</small>}
            </div>
            <button className="ms-btn ms-btn-secondary st-open" onClick={openSavesFolder} disabled={!info}>
              <FolderOpen size={15} />
              <span>Open</span>
            </button>
          </div>
          <div className="st-row">
            <div className="st-label">
              <span>Version</span>
            </div>
            <span className="st-value">{info ? info.version : '…'}</span>
          </div>
        </section>
      </div>
    </ModalShell>
  );
};
