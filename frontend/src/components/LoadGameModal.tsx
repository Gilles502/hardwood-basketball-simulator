// File: frontend/src/components/LoadGameModal.tsx
import React, { useEffect, useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import type { SaveMetadata } from '../store/leagueStore';
import { useSettingsStore } from '../store/settingsStore';
import { t } from '../utils/i18n';
import { ModalShell } from './ModalShell';
import { BRAND } from '../brand';
import { 
  Folder, 
  Play, 
  Copy, 
  Edit3, 
  Trash2, 
  Clock, 
  Trophy, 
  ShieldAlert, 
  HardDrive, 
  Search, 
  AlertTriangle,
  Save,
  CheckCircle2
} from 'lucide-react';

interface LoadGameModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLoadSuccess: () => void;
}

export const LoadGameModal: React.FC<LoadGameModalProps> = ({
  isOpen,
  onClose,
  onLoadSuccess
}) => {
  const { 
    leagueData,
    saves, 
    activeSaveName, 
    fetchSaves, 
    loadGame, 
    saveGame,
    duplicateSave, 
    renameSave, 
    deleteSave 
  } = useLeagueStore();

  const { language } = useSettingsStore();

  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);

  // States for duplicate / rename / delete modals inside
  const [duplicatingTarget, setDuplicatingTarget] = useState<SaveMetadata | null>(null);
  const [newDuplicateName, setNewDuplicateName] = useState('');

  const [renamingTarget, setRenamingTarget] = useState<SaveMetadata | null>(null);
  const [newRenameTitle, setNewRenameTitle] = useState('');

  const [deletingTarget, setDeletingTarget] = useState<SaveMetadata | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchSaves();
      setErrorMsg(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleLoad = async (saveName: string) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await loadGame(saveName);
      setLoading(false);
      if (!data?.success) {
        setErrorMsg(data?.error || "Failed to load save slot.");
        return;
      }
      if (data.warning) window.alert(data.warning);
      onLoadSuccess();
      onClose();
    } catch (err: any) {
      setLoading(false);
      setErrorMsg(err?.message || "Failed to load save slot.");
    }
  };

  const handleSaveCurrentGame = async () => {
    setLoading(true);
    setErrorMsg(null);
    setSaveSuccessMsg(null);
    try {
      await saveGame(activeSaveName || undefined);
      await fetchSaves();
      setLoading(false);
      setSaveSuccessMsg('Active franchise saved successfully!');
      setTimeout(() => setSaveSuccessMsg(null), 3000);
    } catch (err: any) {
      setLoading(false);
      setErrorMsg(err?.message || "Failed to save active franchise.");
    }
  };

  const handleConfirmDuplicate = async () => {
    if (!duplicatingTarget || !newDuplicateName.trim()) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await duplicateSave(duplicatingTarget.save_name, newDuplicateName.trim());
      setLoading(false);
      if (res.error) {
        setErrorMsg(res.error);
      } else {
        setDuplicatingTarget(null);
        setNewDuplicateName('');
      }
    } catch (err: any) {
      setLoading(false);
      setErrorMsg(err?.message || "Error while duplicating.");
    }
  };

  const handleConfirmRename = async () => {
    if (!renamingTarget || !newRenameTitle.trim()) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await renameSave(renamingTarget.save_name, newRenameTitle.trim());
      setLoading(false);
      if (res.error) {
        setErrorMsg(res.error);
      } else {
        setRenamingTarget(null);
        setNewRenameTitle('');
      }
    } catch (err: any) {
      setLoading(false);
      setErrorMsg(err?.message || "Error while renaming.");
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingTarget) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await deleteSave(deletingTarget.save_name);
      setLoading(false);
      if (res.error) {
        setErrorMsg(res.error);
      } else {
        setDeletingTarget(null);
      }
    } catch (err: any) {
      setLoading(false);
      setErrorMsg(err?.message || "Error while deleting.");
    }
  };

  const filteredSaves = saves.filter(s => {
    const term = searchTerm.toLowerCase();
    return (
      s.display_name.toLowerCase().includes(term) ||
      s.save_name.toLowerCase().includes(term) ||
      s.player_team_name.toLowerCase().includes(term) ||
      s.era.toLowerCase().includes(term)
    );
  });

  const formatDate = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString(language === 'it' ? 'it-IT' : 'en-US', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return isoStr;
    }
  };

  return (
    <>
      <ModalShell
        isOpen={isOpen}
        onClose={onClose}
        title={t('load_game_title', language)}
        subtitle={t('load_game_subtitle', language)}
        icon={<HardDrive size={22} />}
        maxWidth={960}
        dismissible={!renamingTarget && !duplicatingTarget && !deletingTarget}
        headerActions={<>
            {leagueData && (
              <button
                onClick={handleSaveCurrentGame}
                disabled={loading}
                style={{
                  padding: '8px 16px',
                  borderRadius: '8px',
                  backgroundColor: 'rgba(34, 197, 94, 0.15)',
                  border: '1px solid rgba(34, 197, 94, 0.35)',
                  color: '#4ade80',
                  fontWeight: 700,
                  fontSize: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onMouseOver={(e) => (e.currentTarget.style.backgroundColor = 'rgba(34, 197, 94, 0.25)')}
                onMouseOut={(e) => (e.currentTarget.style.backgroundColor = 'rgba(34, 197, 94, 0.15)')}
              >
                <Save size={14} />
                <span>{language === 'it' ? 'Salva Partita Attiva' : 'Save Active Game'}</span>
              </button>
            )}
        </>}
        headerExtra={
        <div style={{
          padding: '14px 24px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          backgroundColor: '#0e0a07'
        }}>
          <div style={{
            flex: 1,
            position: 'relative',
            display: 'flex',
            alignItems: 'center'
          }}>
            <Search size={16} color="#9a7f62" style={{ position: 'absolute', left: '12px' }} />
            <input 
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={t('search_saves_placeholder', language)}
              style={{
                width: '100%',
                padding: '9px 12px 9px 36px',
                borderRadius: '8px',
                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                color: '#f5ede1',
                fontSize: '13px',
                outline: 'none'
              }}
            />
          </div>
          <span style={{ fontSize: '12px', color: '#9a7f62', fontWeight: 600 }}>
            {filteredSaves.length} {language === 'it' ? 'Salvataggi' : 'Saves'}
          </span>
        </div>
        }
        footerStart={<span>{BRAND.name} Multi-Save Geofence • Isolated JSON Filesystem</span>}
        footerEnd={<span>{language === 'it' ? 'Salvataggi atomici con protezione da crash' : 'Crash-proof atomic save writes'}</span>}
      >
        {/* Success Banner */}
        {saveSuccessMsg && (
          <div style={{
            margin: '12px 24px 0',
            padding: '10px 14px',
            borderRadius: '8px',
            backgroundColor: 'rgba(34, 197, 94, 0.15)',
            border: '1px solid rgba(34, 197, 94, 0.3)',
            color: '#4ade80',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <CheckCircle2 size={16} />
            <span>{saveSuccessMsg}</span>
          </div>
        )}
        {/* Error Toast */}
        {errorMsg && (
          <div style={{
            margin: '12px 24px 0',
            padding: '10px 14px',
            borderRadius: '8px',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#f87171',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <AlertTriangle size={16} />
            <span>{errorMsg}</span>
          </div>
        )}
        <div style={{
          padding: '20px 24px',
          overflowY: 'auto',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          {filteredSaves.length === 0 ? (
            <div style={{
              textAlign: 'center',
              padding: '48px 16px',
              color: '#9a7f62'
            }}>
              <Folder size={40} strokeWidth={1.5} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
              <p style={{ margin: 0, fontSize: '14px' }}>{t('no_saves_found', language)}</p>
            </div>
          ) : (
            filteredSaves.map((save) => {
              const isActive = activeSaveName === save.save_name;
              return (
                <div
                  key={save.save_name}
                  style={{
                    backgroundColor: isActive ? 'rgba(255, 106, 26, 0.06)' : 'rgba(255, 255, 255, 0.02)',
                    border: isActive ? '1px solid rgba(255, 106, 26, 0.4)' : '1px solid rgba(255, 255, 255, 0.06)',
                    borderRadius: '12px',
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '16px',
                    transition: 'all 0.2s ease'
                  }}
                >
                  {/* Info Left */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flex: 1 }}>
                    <div style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '10px',
                      backgroundColor: isActive ? 'rgba(255, 106, 26, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: isActive ? '#ff6a1a' : '#c9a27a'
                    }}>
                      <Trophy size={20} />
                    </div>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <span style={{ fontSize: '15px', fontWeight: 800, color: '#f5ede1' }}>
                          {save.display_name}
                        </span>
                        {isActive && (
                          <span style={{
                            fontSize: '10px',
                            fontWeight: 800,
                            padding: '2px 7px',
                            borderRadius: '999px',
                            backgroundColor: 'rgba(255, 106, 26, 0.2)',
                            color: '#ff6a1a',
                            letterSpacing: '0.5px'
                          }}>
                            {language === 'it' ? 'ATTIVO' : 'ACTIVE'}
                          </span>
                        )}
                        <span style={{
                          fontSize: '11px',
                          padding: '2px 8px',
                          borderRadius: '6px',
                          backgroundColor: 'rgba(255, 255, 255, 0.06)',
                          color: '#c9a27a'
                        }}>
                          {save.era}
                        </span>
                      </div>
                      
                      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', fontSize: '12px', color: '#9a7f62' }}>
                        <span style={{ color: '#d9c9b4', fontWeight: 600 }}>
                          🏀 {save.is_spectator ? t('spectator_role', language) : save.player_team_name}
                        </span>
                        {save.player_team_record && save.player_team_record !== 'N/A' && (
                          <span style={{ color: '#22c55e', fontWeight: 700 }}>
                            W/L: {save.player_team_record}
                          </span>
                        )}
                        <span>• {t('season_label', language)} {save.season}</span>
                        <span>• {save.phase}</span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <Clock size={12} /> {formatDate(save.last_saved)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions Right */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <button
                      onClick={() => handleLoad(save.save_name)}
                      disabled={loading}
                      style={{
                        padding: '8px 18px',
                        borderRadius: '8px',
                        backgroundColor: '#ff6a1a',
                        border: 'none',
                        color: '#150b04',
                        fontWeight: 800,
                        fontSize: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        cursor: 'pointer',
                        transition: 'opacity 0.2s'
                      }}
                      onMouseOver={(e) => (e.currentTarget.style.opacity = '0.9')}
                      onMouseOut={(e) => (e.currentTarget.style.opacity = '1')}
                    >
                      <Play size={14} fill="#150b04" />
                      <span>{t('btn_load', language)}</span>
                    </button>

                    <button
                      onClick={() => {
                        setRenamingTarget(save);
                        setNewRenameTitle(save.display_name);
                      }}
                      title={t('btn_rename', language)}
                      style={{
                        padding: '8px',
                        borderRadius: '8px',
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        color: '#c9a27a',
                        cursor: 'pointer'
                      }}
                    >
                      <Edit3 size={15} />
                    </button>

                    <button
                      onClick={() => {
                        setDuplicatingTarget(save);
                        setNewDuplicateName(`${save.display_name}_Backup`);
                      }}
                      title={t('btn_duplicate', language)}
                      style={{
                        padding: '8px',
                        borderRadius: '8px',
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        color: '#c9a27a',
                        cursor: 'pointer'
                      }}
                    >
                      <Copy size={15} />
                    </button>

                    <button
                      onClick={() => setDeletingTarget(save)}
                      title={t('btn_delete', language)}
                      style={{
                        padding: '8px',
                        borderRadius: '8px',
                        backgroundColor: 'rgba(239, 68, 68, 0.08)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                        color: '#f87171',
                        cursor: 'pointer'
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </ModalShell>

      {/* Sub-Modal: Rename */}
      {renamingTarget && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1100
        }}>
          <div style={{
            backgroundColor: '#1a130e',
            border: '1px solid rgba(255, 106, 26, 0.3)',
            borderRadius: '12px',
            padding: '20px',
            width: '380px'
          }}>
            <h3 style={{ margin: '0 0 12px', fontSize: '15px', color: '#f5ede1' }}>
              {t('rename_title', language)}
            </h3>
            <input
              type="text"
              value={newRenameTitle}
              onChange={(e) => setNewRenameTitle(e.target.value)}
              placeholder={t('rename_placeholder', language)}
              style={{
                width: '100%',
                padding: '9px 12px',
                borderRadius: '8px',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#fff',
                fontSize: '13px',
                marginBottom: '16px',
                outline: 'none'
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                onClick={() => setRenamingTarget(null)}
                style={{
                  padding: '7px 14px',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#c9a27a',
                  cursor: 'pointer'
                }}
              >
                {t('btn_cancel', language)}
              </button>
              <button
                onClick={handleConfirmRename}
                disabled={loading || !newRenameTitle.trim()}
                style={{
                  padding: '7px 16px',
                  borderRadius: '6px',
                  backgroundColor: '#ff6a1a',
                  border: 'none',
                  color: '#150b04',
                  fontWeight: 700,
                  cursor: 'pointer'
                }}
              >
                {t('btn_confirm', language)}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sub-Modal: Duplicate */}
      {duplicatingTarget && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1100
        }}>
          <div style={{
            backgroundColor: '#1a130e',
            border: '1px solid rgba(255, 106, 26, 0.3)',
            borderRadius: '12px',
            padding: '20px',
            width: '380px'
          }}>
            <h3 style={{ margin: '0 0 12px', fontSize: '15px', color: '#f5ede1' }}>
              {t('duplicate_title', language)}
            </h3>
            <input
              type="text"
              value={newDuplicateName}
              onChange={(e) => setNewDuplicateName(e.target.value)}
              placeholder={t('duplicate_placeholder', language)}
              style={{
                width: '100%',
                padding: '9px 12px',
                borderRadius: '8px',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#fff',
                fontSize: '13px',
                marginBottom: '16px',
                outline: 'none'
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                onClick={() => setDuplicatingTarget(null)}
                style={{
                  padding: '7px 14px',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#c9a27a',
                  cursor: 'pointer'
                }}
              >
                {t('btn_cancel', language)}
              </button>
              <button
                onClick={handleConfirmDuplicate}
                disabled={loading || !newDuplicateName.trim()}
                style={{
                  padding: '7px 16px',
                  borderRadius: '6px',
                  backgroundColor: '#ff6a1a',
                  border: 'none',
                  color: '#150b04',
                  fontWeight: 700,
                  cursor: 'pointer'
                }}
              >
                {t('btn_confirm', language)}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sub-Modal: Confirm Delete */}
      {deletingTarget && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1100
        }}>
          <div style={{
            backgroundColor: '#1a130e',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            borderRadius: '12px',
            padding: '24px',
            width: '420px',
            textAlign: 'center'
          }}>
            <ShieldAlert size={36} color="#ef4444" style={{ margin: '0 auto 12px' }} />
            <h3 style={{ margin: '0 0 8px', fontSize: '16px', color: '#f5ede1' }}>
              {t('confirm_delete_title', language)}
            </h3>
            <p style={{ fontSize: '13px', color: '#c9a27a', margin: '0 0 20px', lineHeight: 1.5 }}>
              {t('confirm_delete_msg', language)}
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '12px' }}>
              <button
                onClick={() => setDeletingTarget(null)}
                style={{
                  padding: '8px 18px',
                  borderRadius: '8px',
                  backgroundColor: 'transparent',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  color: '#c9a27a',
                  cursor: 'pointer'
                }}
              >
                {t('btn_cancel', language)}
              </button>
              <button
                onClick={handleConfirmDelete}
                disabled={loading}
                style={{
                  padding: '8px 20px',
                  borderRadius: '8px',
                  backgroundColor: '#ef4444',
                  border: 'none',
                  color: '#fff',
                  fontWeight: 800,
                  cursor: 'pointer'
                }}
              >
                {t('btn_delete', language)}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
