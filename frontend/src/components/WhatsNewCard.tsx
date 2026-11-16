import React from 'react';
import { useSettingsStore } from '../store/settingsStore';
import { t } from '../utils/i18n';
import { formatReleaseDate, latestRelease } from '../utils/changelog';
import type { ChangelogItem } from '../utils/changelog';
import './WhatsNew.css';

export const ChangeItems: React.FC<{ items: ChangelogItem[] }> = ({ items }) => (
  <ul className="whatsnew-list">
    {items.map((item, index) => (
      <li key={index} className="whatsnew-item">
        <span className={`whatsnew-chip whatsnew-chip-${item.kind}`}>{item.kind === 'new' ? 'NEW' : 'FIX'}</span>
        <span>{item.text}</span>
      </li>
    ))}
  </ul>
);

interface WhatsNewCardProps {
  onViewAll: () => void;
}

export const WhatsNewCard: React.FC<WhatsNewCardProps> = ({ onViewAll }) => {
  const { language } = useSettingsStore();
  const release = latestRelease();
  if (!release) return null;

  return (
    <section className="whatsnew-card">
      <div className="whatsnew-head">
        <span className="whatsnew-label">{t('whats_new', language)}</span>
        <span className="whatsnew-meta">v{release.version} · {formatReleaseDate(release.date)}</span>
      </div>
      <div className="whatsnew-scroll">
        <ChangeItems items={release.items} />
      </div>
      <button className="whatsnew-link" onClick={onViewAll}>
        {t('view_full_changelog', language)} →
      </button>
    </section>
  );
};
