// File: frontend/src/components/SetupWizardModal.tsx
import React, { useState, useEffect } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { useSettingsStore } from '../store/settingsStore';
import { t } from '../utils/i18n';
import { ModalShell } from './ModalShell';
import { 
  Sparkles, 
  ChevronRight, 
  ChevronLeft, 
  Play, 
  Shield, 
  DollarSign, 
  Activity, 
  ArrowLeftRight, 
  Eye, 
  Briefcase, 
  Trophy, 
  Check, 
  Star,
  ClipboardList
} from 'lucide-react';
import './SetupWizardModal.css';

interface SetupWizardModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCareerStarted: () => void;
}

export const SetupWizardModal: React.FC<SetupWizardModalProps> = ({
  isOpen,
  onClose,
  onCareerStarted
}) => {
  const { initSimulation } = useLeagueStore();
  const { language } = useSettingsStore();

  // Wizard Navigation
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4>(1);

  // Step 1: Era
  const [era, setEra] = useState<'modern' | '2002'>('2002'); // the modern era is hidden for now (Early Access plays the 2002 league)
  const [leagueName, setLeagueName] = useState<string>('');

  // Step 2: Sandbox & Rules
  // Play-In: from a chosen season on (real NBA: 2020-21), always, or never
  const [playInMode, setPlayInMode] = useState<'from_year' | 'always' | 'never'>('from_year');
  const [playInYear, setPlayInYear] = useState<number>(2020);
  const [cbaMode, setCbaMode] = useState<'realistic' | 'soft_cap' | 'no_cap'>('realistic');
  const [injuryFrequency, setInjuryFrequency] = useState<'realistic' | 'low' | 'off'>('realistic');
  const [tradeDifficulty, setTradeDifficulty] = useState<'easy' | 'realistic' | 'hardcore'>('realistic');
  const [scoutingFogOfWar, setScoutingFogOfWar] = useState<boolean>(true);
  const [gmFiringEnabled, setGmFiringEnabled] = useState<boolean>(true);

  // Step 3: Role & Team
  const [userRole, setUserRole] = useState<'gm_coach' | 'only_gm' | 'only_coach' | 'spectator'>('gm_coach');
  const [selectedTeam, setSelectedTeam] = useState<string>('');
  const [teamsData, setTeamsData] = useState<{ east: any[]; west: any[] } | null>(null);
  const [loadingTeams, setLoadingTeams] = useState<boolean>(false);
  const [teamSearch, setTeamSearch] = useState<string>('');

  // Step 4: Slot Name & Final Init
  const [saveName, setSaveName] = useState<string>('');
  const [loadingCreation, setLoadingCreation] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // Errors of the active league when /api/era_teams refuses it (400)
  const [leagueErrors, setLeagueErrors] = useState<string[]>([]);

  // Fetch teams when era changes or entering Step 3
  useEffect(() => {
    if (isOpen) {
      setLoadingTeams(true);
      setLeagueErrors([]);
      fetch(`/api/era_teams?era=${era}`)
        .then(res => res.json().then(data => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          if (ok && data && data.east && data.west) {
            setTeamsData(data);
            setLeagueName(data.league?.name || '');
          } else {
            // 400: the active league is invalid; show why instead of an empty team list
            setTeamsData(null);
            setLeagueName('');
            const errs = Array.isArray(data?.errors) && data.errors.length ? data.errors : [data?.error || 'Unknown error'];
            setLeagueErrors(errs.map((e: unknown) => String(e)));
          }
        })
        .catch(err => console.error("Error loading era teams:", err))
        .finally(() => setLoadingTeams(false));
    }
  }, [era, isOpen]);

  if (!isOpen) return null;

  const handleNext = () => {
    setErrorMsg(null);
    if (currentStep < 4) {
      setCurrentStep((prev) => (prev + 1) as any);
    }
  };

  const handlePrev = () => {
    setErrorMsg(null);
    if (currentStep > 1) {
      setCurrentStep((prev) => (prev - 1) as any);
    }
  };

  // Same rule as core.save_manager.default_save_name: team and starting era; the server adds ' (2)' if it exists.
  const defaultSaveName = `${userRole !== 'spectator' && selectedTeam ? selectedTeam : 'League'} · ${era === '2002' ? '2002' : 'Modern'}`;

  const handleStartCareer = async () => {
    setLoadingCreation(true);
    setErrorMsg(null);
    try {
      const generatedName = saveName.trim() || defaultSaveName;
      
      const leagueSettings = {
        ...(playInMode === 'from_year' ? { play_in_start_year: playInYear } : { enable_play_in: playInMode === 'always' }),
        cba_mode: cbaMode,
        injury_frequency: injuryFrequency,
        trade_difficulty: tradeDifficulty,
        scouting_fog_of_war: scoutingFogOfWar,
        gm_firing_enabled: gmFiringEnabled,
        user_role: userRole
      };

      await initSimulation({
        era,
        saveName: generatedName,
        leagueSettings,
        selectedTeam: userRole === 'spectator' ? '' : selectedTeam,
        userRole
      });

      onClose();
      onCareerStarted();
    } catch (err: any) {
      console.error("Error creating career in Setup Wizard:", err);
      setErrorMsg(err.message || 'Error while creating the career.');
    } finally {
      setLoadingCreation(false);
    }
  };

  // Filtered teams for Step 3
  const filterList = (list: any[]) => {
    if (!list) return [];
    if (!teamSearch.trim()) return list;
    const q = teamSearch.toLowerCase();
    return list.filter(t => 
      t.name.toLowerCase().includes(q) || 
      (t.star_player && t.star_player.toLowerCase().includes(q))
    );
  };

  const leagueErrorBox = leagueErrors.length > 0 && (
    <div role="alert" style={{
      padding: '12px 16px',
      borderRadius: '10px',
      backgroundColor: 'rgba(239, 68, 68, 0.15)',
      border: '1px solid rgba(239, 68, 68, 0.3)',
      color: '#ef4444',
      fontSize: '13px',
      marginTop: '16px',
      gridColumn: '1 / -1'  // a full row under the era card
    }}>
      <strong>{t('wizard_league_invalid', language)}</strong>
      <ul style={{ margin: '8px 0', paddingLeft: '18px' }}>
        {leagueErrors.slice(0, 8).map((e, i) => <li key={i}>{e}</li>)}
      </ul>
      {leagueErrors.length > 8 && <p>{t('wizard_league_more_errors', language).replace('{n}', String(leagueErrors.length - 8))}</p>}
      <p style={{ margin: 0 }}>{t('wizard_league_invalid_hint', language)}</p>
    </div>
  );

  const filteredEast = teamsData ? filterList(teamsData.east) : [];
  const filteredWest = teamsData ? filterList(teamsData.west) : [];

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title={t('wizard_title', language)}
      subtitle={t('wizard_subtitle', language)}
      icon={<Sparkles size={22} />}
      maxWidth={960}
      tall
      dismissible={false}
      headerExtra={
        <div className="setup-wizard-stepper">
          <div className={`wizard-step-item ${currentStep === 1 ? 'active' : ''} ${currentStep > 1 ? 'completed' : ''}`} onClick={() => setCurrentStep(1)}>
            <div className="wizard-step-number">{currentStep > 1 ? <Check size={14} /> : 1}</div>
            <div className="wizard-step-label">{t('wizard_step1', language)}</div>
          </div>
          <div className={`wizard-step-item ${currentStep === 2 ? 'active' : ''} ${currentStep > 2 ? 'completed' : ''}`} onClick={() => setCurrentStep(2)}>
            <div className="wizard-step-number">{currentStep > 2 ? <Check size={14} /> : 2}</div>
            <div className="wizard-step-label">{t('wizard_step2', language)}</div>
          </div>
          <div className={`wizard-step-item ${currentStep === 3 ? 'active' : ''} ${currentStep > 3 ? 'completed' : ''}`} onClick={() => setCurrentStep(3)}>
            <div className="wizard-step-number">{currentStep > 3 ? <Check size={14} /> : 3}</div>
            <div className="wizard-step-label">{t('wizard_step3', language)}</div>
          </div>
          <div className={`wizard-step-item ${currentStep === 4 ? 'active' : ''}`} onClick={() => setCurrentStep(4)}>
            <div className="wizard-step-number">4</div>
            <div className="wizard-step-label">{t('wizard_step4', language)}</div>
          </div>
        </div>
      }
      footerStart={<>
            {currentStep > 1 && (
              <button 
                className="ms-btn ms-btn-secondary" 
                onClick={handlePrev}
                disabled={loadingCreation}
              >
                <ChevronLeft size={16} />
                <span>{t('btn_prev_step', language)}</span>
              </button>
            )}
      </>}
      footerEnd={<>
            {currentStep < 4 ? (
              <button 
                className="ms-btn ms-btn-primary" 
                onClick={handleNext}
                disabled={currentStep === 3 && userRole !== 'spectator' && !selectedTeam}
              >
                <span>{t('btn_next_step', language)}</span>
                <ChevronRight size={16} />
              </button>
            ) : (
              <button 
                className="ms-btn ms-btn-primary" 
                onClick={handleStartCareer}
                disabled={loadingCreation}
              >
                {loadingCreation ? (
                  <>
                    <div className="spinner" style={{ width: '16px', height: '16px', borderWidth: '2px', marginRight: '6px' }} />
                    <span>{t('initializing_database', language)}</span>
                  </>
                ) : (
                  <>
                    <Play size={16} fill="currentColor" />
                    <span>{t('btn_start_career', language)}</span>
                  </>
                )}
              </button>
            )}
      </>}
    >
        <div className="setup-wizard-body">
          {/* STEP 1: Era & Database Selection */}
          {currentStep === 1 && (
            <div className="wizard-eras-grid fade-in">
              {/* Golden Era 2002 */}
              <div 
                className={`wizard-era-card ${era === '2002' ? 'selected' : ''}`}
                onClick={() => {
                  setEra('2002');
                }}
              >
                <span className="wizard-era-badge golden">
                  GOLDEN ERA
                </span>
                <h3>{leagueName || t('era_golden_title', language)}</h3>
                <p>{t('era_golden_desc', language)}</p>
                {leagueName && <p>{t('wizard_league_label', language)}: {leagueName}. {t('wizard_league_hint', language)}</p>}
                <div className="wizard-era-footer">
                  {t('era_golden_sub', language)}
                </div>
              </div>
              {era === '2002' && leagueErrorBox}
            </div>
          )}

          {/* STEP 2: League Rules & Sandbox Toggles */}
          {currentStep === 2 && (
            <div className="wizard-rules-grid fade-in">
              {/* 1. Play-In Tournament */}
              <div className="wizard-rule-row">
                <div className="wizard-rule-info">
                  <h4>
                    <Trophy size={16} style={{ color: '#ff6a1a' }} />
                    {t('setting_playin', language)}
                  </h4>
                  <p>{t('setting_playin_desc', language)}</p>
                </div>
                <div className="wizard-playin-controls">
                  <div className="wizard-options-pills">
                    {(['from_year', 'always', 'never'] as const).map((mode) => (
                      <button
                        key={mode}
                        className={`wizard-pill-btn ${playInMode === mode ? 'active' : ''}`}
                        onClick={() => setPlayInMode(mode)}
                      >
                        {t(`setting_playin_${mode}`, language)}
                      </button>
                    ))}
                  </div>
                  {playInMode === 'from_year' && (
                    <input
                      type="number"
                      className="wizard-year-input"
                      aria-label={t('setting_playin_from_year', language)}
                      min={2002}
                      max={2100}
                      value={playInYear}
                      onChange={(e) => setPlayInYear(Number(e.target.value))}
                      onBlur={() => setPlayInYear((y) => Math.min(2100, Math.max(2002, Math.round(y) || 2020)))}
                    />
                  )}
                </div>
              </div>

              {/* 2. Salary Cap & CBA Mode */}
              <div className="wizard-rule-row">
                <div className="wizard-rule-info">
                  <h4>
                    <DollarSign size={16} style={{ color: '#22c55e' }} />
                    {t('setting_cba', language)}
                  </h4>
                  <p>{t('setting_cba_desc', language)}</p>
                </div>
                <div className="wizard-options-pills">
                  <button 
                    className={`wizard-pill-btn ${cbaMode === 'realistic' ? 'active' : ''}`}
                    onClick={() => setCbaMode('realistic')}
                  >
                    {t('setting_cba_realistic', language)}
                  </button>
                  <button 
                    className={`wizard-pill-btn ${cbaMode === 'soft_cap' ? 'active' : ''}`}
                    onClick={() => setCbaMode('soft_cap')}
                  >
                    {t('setting_cba_soft', language)}
                  </button>
                  <button 
                    className={`wizard-pill-btn ${cbaMode === 'no_cap' ? 'active' : ''}`}
                    onClick={() => setCbaMode('no_cap')}
                  >
                    {t('setting_cba_nocap', language)}
                  </button>
                </div>
              </div>

              {/* 3. Injuries Frequency */}
              <div className="wizard-rule-row">
                <div className="wizard-rule-info">
                  <h4>
                    <Activity size={16} style={{ color: '#ef4444' }} />
                    {t('setting_injuries', language)}
                  </h4>
                  <p>{t('setting_injuries_desc', language)}</p>
                </div>
                <div className="wizard-options-pills">
                  <button 
                    className={`wizard-pill-btn ${injuryFrequency === 'realistic' ? 'active' : ''}`}
                    onClick={() => setInjuryFrequency('realistic')}
                  >
                    {t('setting_injuries_realistic', language)}
                  </button>
                  <button 
                    className={`wizard-pill-btn ${injuryFrequency === 'low' ? 'active' : ''}`}
                    onClick={() => setInjuryFrequency('low')}
                  >
                    {t('setting_injuries_low', language)}
                  </button>
                  <button 
                    className={`wizard-pill-btn ${injuryFrequency === 'off' ? 'active' : ''}`}
                    onClick={() => setInjuryFrequency('off')}
                  >
                    {t('setting_injuries_off', language)}
                  </button>
                </div>
              </div>

              {/* 4. AI Trade Difficulty */}
              <div className="wizard-rule-row">
                <div className="wizard-rule-info">
                  <h4>
                    <ArrowLeftRight size={16} style={{ color: '#38bdf8' }} />
                    {t('setting_trades', language)}
                  </h4>
                  <p>{t('setting_trades_desc', language)}</p>
                </div>
                <div className="wizard-options-pills">
                  <button 
                    className={`wizard-pill-btn ${tradeDifficulty === 'easy' ? 'active' : ''}`}
                    onClick={() => setTradeDifficulty('easy')}
                  >
                    {t('setting_trades_easy', language)}
                  </button>
                  <button 
                    className={`wizard-pill-btn ${tradeDifficulty === 'realistic' ? 'active' : ''}`}
                    onClick={() => setTradeDifficulty('realistic')}
                  >
                    {t('setting_trades_realistic', language)}
                  </button>
                  <button 
                    className={`wizard-pill-btn ${tradeDifficulty === 'hardcore' ? 'active' : ''}`}
                    onClick={() => setTradeDifficulty('hardcore')}
                  >
                    {t('setting_trades_hardcore', language)}
                  </button>
                </div>
              </div>

              {/* 5. Scouting Fog of War */}
              <div className="wizard-rule-row">
                <div className="wizard-rule-info">
                  <h4>
                    <Eye size={16} style={{ color: '#a855f7' }} />
                    {t('setting_scouting', language)}
                  </h4>
                  <p>{t('setting_scouting_desc', language)}</p>
                </div>
                <div className="wizard-options-pills">
                  <button 
                    className={`wizard-pill-btn ${scoutingFogOfWar ? 'active' : ''}`}
                    onClick={() => setScoutingFogOfWar(true)}
                  >
                    {t('setting_scouting_fow', language)}
                  </button>
                  <button 
                    className={`wizard-pill-btn ${!scoutingFogOfWar ? 'active' : ''}`}
                    onClick={() => setScoutingFogOfWar(false)}
                  >
                    {t('setting_scouting_open', language)}
                  </button>
                </div>
              </div>

              {/* 6. GM Firing (Job Security) */}
              <div className="wizard-rule-row">
                <div className="wizard-rule-info">
                  <h4>
                    <Shield size={16} style={{ color: '#f59e0b' }} />
                    {t('setting_firing', language)}
                  </h4>
                  <p>{t('setting_firing_desc', language)}</p>
                </div>
                <div className="wizard-options-pills">
                  <button 
                    className={`wizard-pill-btn ${gmFiringEnabled ? 'active' : ''}`}
                    onClick={() => setGmFiringEnabled(true)}
                  >
                    {t('setting_firing_enabled', language)}
                  </button>
                  <button 
                    className={`wizard-pill-btn ${!gmFiringEnabled ? 'active' : ''}`}
                    onClick={() => setGmFiringEnabled(false)}
                  >
                    {t('setting_firing_disabled', language)}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* STEP 3: Team & Role Selection */}
          {currentStep === 3 && (
            <div className="fade-in">
              {/* Mode Selection: Franchise Control vs Manager Only vs Spectator */}
              <div className="wizard-role-section">
                <div className="wizard-role-grid">
                  <div 
                    className={`wizard-role-card ${userRole === 'gm_coach' ? 'selected' : ''}`}
                    onClick={() => setUserRole('gm_coach')}
                  >
                    <h5><Briefcase size={14} style={{ color: '#ff6a1a' }} /> {language === 'it' ? 'Controllo Totale (GM & Coach)' : 'Full Franchise (GM & Coach)'}</h5>
                    <p>{language === 'it' ? 'Autorità completa su mercato, scambi, draft, contratti, rotazioni e strategia di gara.' : 'Full authority over trades, draft, free agency, contracts, rotations and in-game tactics.'}</p>
                  </div>

                  <div 
                    className={`wizard-role-card ${userRole === 'only_coach' ? 'selected' : ''}`}
                    onClick={() => setUserRole('only_coach')}
                  >
                    <h5><ClipboardList size={14} style={{ color: '#38bdf8' }} /> {language === 'it' ? 'Solo Manager (Head Coach)' : 'Manager Only (Head Coach)'}</h5>
                    <p>{language === 'it' ? 'Il front office e gli scambi sono gestiti dal GM (IA). Tu guidi il campo: quintetto, rotazioni a 240m, carichi e summit pre-stagionale!' : 'Front office and trades run by AI General Manager. You command the court: starters, 240m rotations, minutes, schemes, and GM summits!'}</p>
                  </div>

                  <div 
                    className={`wizard-role-card ${userRole === 'spectator' ? 'selected' : ''}`}
                    onClick={() => {
                      setUserRole('spectator');
                      setSelectedTeam('');
                    }}
                  >
                    <h5><Eye size={14} style={{ color: '#a855f7' }} /> {t('wizard_role_spectator', language)}</h5>
                    <p>{t('wizard_role_spectator_desc', language)}</p>
                  </div>
                </div>
              </div>

              {/* Franchise Grid (Only if not pure spectator) */}
              {userRole !== 'spectator' && (
                <div>
                  <div className="wizard-team-header">
                    <span style={{ fontSize: '13px', color: '#c9a27a' }}>
                      {selectedTeam ? (
                        <span>{t('wizard_selected_team', language)}: <strong style={{ color: '#ff6a1a' }}>{selectedTeam}</strong></span>
                      ) : (
                        t('wizard_select_team_prompt', language)
                      )}
                    </span>
                    <input 
                      type="text"
                      className="wizard-team-search"
                      placeholder={t('wizard_team_search_placeholder', language)}
                      value={teamSearch}
                      onChange={(e) => setTeamSearch(e.target.value)}
                    />
                  </div>

                  {loadingTeams ? (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                      <div className="spinner" style={{ margin: '0 auto 12px' }} />
                      <p style={{ color: '#c9a27a', fontSize: '13px' }}>Loading franchises...</p>
                    </div>
                  ) : leagueErrors.length > 0 ? leagueErrorBox : (
                    <div className="wizard-teams-conferences">
                      {/* East Conference */}
                      <div className="wizard-conference-column">
                        <h4><Star size={14} /> Eastern Conference</h4>
                        <div className="wizard-teams-list">
                          {filteredEast.map(tData => (
                            <div 
                              key={tData.name}
                              className={`wizard-team-item ${selectedTeam === tData.name ? 'selected' : ''}`}
                              onClick={() => setSelectedTeam(tData.name)}
                            >
                              <div className="wizard-team-left">
                                <span className="wizard-team-name">{tData.name}</span>
                                <span className="wizard-team-star">
                                  {t('wizard_star_player', language)}: {tData.star_player} ({tData.star_ovr})
                                </span>
                              </div>
                              <span className="wizard-team-ovr-badge">
                                {tData.ovr} {t('wizard_best_ovr', language)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* West Conference */}
                      <div className="wizard-conference-column west">
                        <h4><Star size={14} /> Western Conference</h4>
                        <div className="wizard-teams-list">
                          {filteredWest.map(tData => (
                            <div 
                              key={tData.name}
                              className={`wizard-team-item ${selectedTeam === tData.name ? 'west-selected' : ''}`}
                              onClick={() => setSelectedTeam(tData.name)}
                            >
                              <div className="wizard-team-left">
                                <span className="wizard-team-name">{tData.name}</span>
                                <span className="wizard-team-star">
                                  {t('wizard_star_player', language)}: {tData.star_player} ({tData.star_ovr})
                                </span>
                              </div>
                              <span className="wizard-team-ovr-badge">
                                {tData.ovr} {t('wizard_best_ovr', language)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {userRole === 'spectator' && (
                <div style={{
                  padding: '36px',
                  textAlign: 'center',
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '14px',
                  marginTop: '10px'
                }}>
                  <Eye size={36} style={{ color: '#a855f7', marginBottom: '12px' }} />
                  <h3 style={{ margin: '0 0 8px', color: '#f5ede1' }}>{t('wizard_role_spectator', language)}</h3>
                  <p style={{ margin: 0, color: '#c9a27a', fontSize: '13px', maxWidth: '540px', marginInline: 'auto' }}>
                    {language === 'it' 
                      ? 'No team selected. You will simulate the league as a neutral commissioner, watching the evolution of the 30 teams and the NBA champions.'
                      : 'No franchise selected. You will simulate the entire league as commissioner, observing 30 teams and champions evolve naturally.'}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* STEP 4: Name Slot & Final Launch Summary */}
          {currentStep === 4 && (
            <div className="fade-in">
              {/* Save Slot Name Input */}
              <div style={{ marginBottom: '24px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 700, color: '#d9c9b4', marginBottom: '8px' }}>
                  {t('wizard_slot_name_label', language)}
                </label>
                <input 
                  type="text"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder={defaultSaveName}
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    borderRadius: '10px',
                    backgroundColor: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.12)',
                    color: '#fff',
                    fontSize: '14px',
                    outline: 'none'
                  }}
                />
              </div>

              {/* Executive Summary Card */}
              <div className="wizard-summary-card">
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#f5ede1' }}>
                  {t('wizard_summary_title', language)}
                </h3>

                <div className="wizard-summary-grid">
                  <div className="wizard-summary-item">
                    <span>{t('wizard_step1', language)}</span>
                    <strong>{era === '2002' ? (leagueName || t('era_golden_title', language)) : t('era_modern_title', language)}</strong>
                  </div>

                  <div className="wizard-summary-item">
                    <span>{t('wizard_selected_team', language)}</span>
                    <strong style={{ color: selectedTeam ? '#ff6a1a' : '#a855f7' }}>
                      {userRole === 'spectator' ? t('wizard_role_spectator', language) : (selectedTeam || 'None (Spectator)')}
                    </strong>
                  </div>

                  <div className="wizard-summary-item">
                    <span>{t('role_label', language)}</span>
                    <strong>{userRole === 'gm_coach' ? 'GM + Coach' : (userRole === 'only_gm' ? 'GM only' : (userRole === 'only_coach' ? 'Coach only' : 'Spectator'))}</strong>
                  </div>

                  <div className="wizard-summary-item">
                    <span>{t('setting_playin', language)}</span>
                    <strong>{playInMode === 'from_year' ? `${t('setting_playin_from_year', language)} ${playInYear}` : t(`setting_playin_${playInMode}`, language)}</strong>
                  </div>

                  <div className="wizard-summary-item">
                    <span>{t('setting_cba', language)}</span>
                    <strong>{cbaMode === 'realistic' ? 'Realistic CBA' : (cbaMode === 'soft_cap' ? 'Soft Cap' : 'No Cap')}</strong>
                  </div>

                  <div className="wizard-summary-item">
                    <span>{t('setting_injuries', language)}</span>
                    <strong>{injuryFrequency === 'realistic' ? 'Realistici' : (injuryFrequency === 'low' ? 'Low Frequency' : 'Disattivati')}</strong>
                  </div>

                  <div className="wizard-summary-item">
                    <span>{t('setting_trades', language)}</span>
                    <strong>{tradeDifficulty === 'easy' ? 'Facile' : (tradeDifficulty === 'realistic' ? 'Realistica' : 'Hardcore')}</strong>
                  </div>

                  <div className="wizard-summary-item">
                    <span>{t('setting_scouting', language)}</span>
                    <strong>{scoutingFogOfWar ? 'Fog Active' : '100% Visibile'}</strong>
                  </div>

                  <div className="wizard-summary-item">
                    <span>{t('setting_firing', language)}</span>
                    <strong>{gmFiringEnabled ? 'Firing Risk' : 'Total Immunity'}</strong>
                  </div>
                </div>
              </div>

              {errorMsg && (
                <div style={{
                  padding: '12px 16px',
                  borderRadius: '10px',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#ef4444',
                  fontSize: '13px',
                  marginBottom: '16px'
                }}>
                  {errorMsg}
                </div>
              )}
            </div>
          )}
        </div>
    </ModalShell>
  );
};
