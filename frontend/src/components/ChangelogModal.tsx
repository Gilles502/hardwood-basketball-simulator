import React from 'react';
import { ScrollText } from 'lucide-react';
import { useSettingsStore } from '../store/settingsStore';
import { t } from '../utils/i18n';
import { formatReleaseDate, getReleases } from '../utils/changelog';
import { ChangeItems } from './WhatsNewCard';
import { ModalShell } from './ModalShell';
import './WhatsNew.css';

interface ChangelogModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ChangelogModal: React.FC<ChangelogModalProps> = ({ isOpen, onClose }) => {
  const { language } = useSettingsStore();

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title={t('changelog_title', language)}
      icon={<ScrollText size={22} />}
      maxWidth={640}
    >
      <div className="changelog-body">
        {getReleases().map((release, index) => (
          <div key={`${release.version}-${release.date}-${index}`} className="changelog-release">
            <div className="whatsnew-head">
              <span className="whatsnew-label">v{release.version}</span>
              <span className="whatsnew-meta">{formatReleaseDate(release.date)}</span>
            </div>
            <ChangeItems items={release.items} />
          </div>
        ))}
      </div>
    </ModalShell>
  );
};
