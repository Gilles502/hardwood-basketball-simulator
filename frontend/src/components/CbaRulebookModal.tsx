// File: frontend/src/components/CbaRulebookModal.tsx
import React, { useState } from 'react';
import { useSettingsStore } from '../store/settingsStore';
import { t } from '../utils/i18n';
import { BRAND } from '../brand';
import { ModalShell } from './ModalShell';
import { 
  BookOpen, 
  Coins, 
  ArrowLeftRight, 
  FileSignature, 
  Sliders, 
  CheckCircle, 
  XCircle 
} from 'lucide-react';

interface CbaRulebookModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type TabType = 'cba' | 'trades' | 'contracts' | 'gameplay';

export const CbaRulebookModal: React.FC<CbaRulebookModalProps> = ({ isOpen, onClose }) => {
  const { language } = useSettingsStore();
  const [activeTab, setActiveTab] = useState<TabType>('cba');

  if (!isOpen) return null;

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      title={t('rulebook_title', language)}
      subtitle={t('rulebook_subtitle', language)}
      icon={<BookOpen size={22} />}
      maxWidth={1020}
      tall
      headerExtra={
        <div className="ms-tabs" role="tablist">
          {[
            { id: 'cba', label: t('rulebook_tab_cba', language), icon: Coins },
            { id: 'trades', label: t('rulebook_tab_trades', language), icon: ArrowLeftRight },
            { id: 'contracts', label: t('rulebook_tab_contracts', language), icon: FileSignature },
            { id: 'gameplay', label: t('rulebook_tab_gameplay', language), icon: Sliders }
          ].map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={activeTab === tab.id}
                className={`ms-tab${activeTab === tab.id ? ' is-active' : ''}`}
                onClick={() => setActiveTab(tab.id as TabType)}
              >
                <Icon size={16} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      }
      footerStart={<span>{BRAND.name} Game Design Document (GDD) • Collective Bargaining Agreement (CBA) Reference</span>}
      footerEnd={<button className="ms-btn ms-btn-secondary" onClick={onClose}>{t('btn_close', language)}</button>}
    >
      <div style={{ padding: '24px', color: '#f5ede1', fontSize: '14px', lineHeight: 1.6 }}>
          {/* TAB 1: CBA & SALARY CAP */}
          {activeTab === 'cba' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{
                padding: '16px',
                borderRadius: '10px',
                backgroundColor: 'rgba(255, 106, 26, 0.05)',
                border: '1px solid rgba(255, 106, 26, 0.2)'
              }}>
                <h3 style={{ margin: '0 0 8px', color: '#ff6a1a', fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Coins size={18} /> NBA Salary Structure (Collective Bargaining Agreement)
                </h3>
                <p style={{ margin: 0, color: '#d9c9b4' }}>
                  Unlike leagues with a hard cap, the NBA uses a <strong>Soft Cap</strong> system with progressive financial penalties and roster restrictions (Apron Tiers).
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#38bdf8' }}>1. Salary Cap (Base Limit)</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    Room available to sign outside Free Agents. Below this line a team can absorb salaries freely without sending out matching salary.
                  </p>
                </div>

                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#fbbf24' }}>2. Luxury Tax Threshold</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    Above this line the franchise pays a progressive tax on every dollar over. Reduced exceptions apply.
                  </p>
                </div>

                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#facc15' }}>3. First Apron</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    • Cannot take back more salary than is sent out in trades (maximum 100%).<br />
                    • The Mid-Level Exception is reduced (Taxpayer MLE).<br />
                    • Cannot sign players waived with a high original salary.
                  </p>
                </div>

                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#ef4444' }}>4. Second Apron</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    • <strong>No MLE</strong> available on the Free Agent market.<br />
                    • <strong>No aggregating</strong> the salaries of several players to take back a single one.<br />
                    • <strong>Frozen</strong> first-round pick seven years out.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: TRADE ENGINE */}
          {activeTab === 'trades' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{
                padding: '16px',
                borderRadius: '10px',
                backgroundColor: 'rgba(56, 189, 248, 0.05)',
                border: '1px solid rgba(56, 189, 248, 0.2)'
              }}>
                <h3 style={{ margin: '0 0 8px', color: '#38bdf8', fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ArrowLeftRight size={18} /> Trade Engine & Salary Matching
                </h3>
                <p style={{ margin: 0, color: '#d9c9b4' }}>
                  Every trade proposal is validated in real time against the CBA salary-matching formulas and the franchise value algorithm (Win-Now vs Rebuilding).
                </p>
              </div>

              {/* Scenarios */}
              <h4 style={{ margin: '10px 0 6px', color: '#f5ede1' }}>Example Scenarios in the Game Engine</h4>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                {/* Scenario Approved */}
                <div style={{
                  padding: '16px',
                  borderRadius: '10px',
                  backgroundColor: 'rgba(34, 197, 94, 0.05)',
                  border: '1px solid rgba(34, 197, 94, 0.2)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', color: '#22c55e', fontWeight: 700 }}>
                    <CheckCircle size={18} />
                    <span>APPROVED: 3-TEAM BLOCKBUSTER</span>
                  </div>
                  <p style={{ fontSize: '13px', color: '#c9a27a', margin: '0 0 10px' }}>
                    <strong>Team A (Contender):</strong> Sends young players + picks for a Superstar ($30M).<br />
                    <strong>Team B (Rebuilder):</strong> Sends the star and receives 2 first-round picks.<br />
                    <strong>Team C (Facilitator):</strong> Uses cap space to absorb a $12M expiring contract and receives a 2nd-round pick.
                  </p>
                  <div style={{ fontSize: '12px', color: '#4ade80', backgroundColor: 'rgba(34, 197, 94, 0.1)', padding: '6px 10px', borderRadius: '6px' }}>
                    All salary returns are valid within the 125% tolerance.
                  </div>
                </div>

                {/* Scenario Rejected */}
                <div style={{
                  padding: '16px',
                  borderRadius: '10px',
                  backgroundColor: 'rgba(239, 68, 68, 0.05)',
                  border: '1px solid rgba(239, 68, 68, 0.2)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', color: '#ef4444', fontWeight: 700 }}>
                    <XCircle size={18} />
                    <span>REJECTED: 2ND APRON VIOLATION</span>
                  </div>
                  <p style={{ fontSize: '13px', color: '#c9a27a', margin: '0 0 10px' }}>
                    <strong>Team over the 2nd Apron:</strong> Vuole scambiare 2 giocatori di rotazione ($8M + $6M = $14M) per un singolo starter da $13.5M.
                  </p>
                  <div style={{ fontSize: '12px', color: '#f87171', backgroundColor: 'rgba(239, 68, 68, 0.1)', padding: '6px 10px', borderRadius: '6px' }}>
                    Blocked: the second apron forbids aggregating several outgoing salaries into a single trade.
                  </div>
                </div>
              </div>

              <div style={{ padding: '14px', borderRadius: '8px', backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                <h4 style={{ margin: '0 0 4px', color: '#fbbf24', fontSize: '14px' }}>📌 Ted Stepien Rule (Draft Picks)</h4>
                <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                  No team may be left without a first-round pick in two consecutive years. The engine checks the Stepien Rule automatically on every proposed trade.
                </p>
              </div>
            </div>
          )}

          {/* TAB 3: CONTRACTS & FREE AGENCY */}
          {activeTab === 'contracts' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{
                padding: '16px',
                borderRadius: '10px',
                backgroundColor: 'rgba(139, 92, 246, 0.05)',
                border: '1px solid rgba(139, 92, 246, 0.2)'
              }}>
                <h3 style={{ margin: '0 0 8px', color: '#a78bfa', fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileSignature size={18} /> Contracts, Extensions & Free Agency
                </h3>
                <p style={{ margin: 0, color: '#d9c9b4' }}>
                  The system covers player/team options, early mid-season extension windows and a 3-round summer Free Agency.
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#f5ede1' }}>Mid-Season Extensions (February)</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    At mid-season, General Managers can offer contract extensions to expiring players, including Player Option or Team Option clauses with franchise loyalty bonuses.
                  </p>
                </div>

                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#f5ede1' }}>Bird Rights & Re-signing Over the Cap</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    Players with Bird Rights can be re-signed by their current team even over the Salary Cap and the Luxury Tax, with raises of up to 8% per year.
                  </p>
                </div>

                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#f5ede1' }}>Free Agency v12.0</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    Team offers consider franchise prestige, competitiveness (Contender vs Rebuilder), market climate, promised role and total financial value.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: GAMEPLAY & ENGINE */}
          {activeTab === 'gameplay' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{
                padding: '16px',
                borderRadius: '10px',
                backgroundColor: 'rgba(255, 106, 26, 0.05)',
                border: '1px solid rgba(255, 106, 26, 0.2)'
              }}>
                <h3 style={{ margin: '0 0 8px', color: '#ff6a1a', fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sliders size={18} /> Game Engine & Possession-by-Possession Simulation
                </h3>
                <p style={{ margin: 0, color: '#d9c9b4' }}>
                  Every game is more than a random dice roll: each possession accounts for pace, individual mismatches, cumulative fatigue and tactical reads.
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#f5ede1' }}>Dynamic Stamina & Fatigue</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    Players lose energy based on continuous minutes on the floor and game intensity. Below a threshold, shooting percentages drop and injury risk rises.
                  </p>
                </div>

                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#f5ede1' }}>Smart Rotations (8-12 Men)</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    The coach makes substitutions based on fatigue, fouls committed and the tactical setup (offensive and defensive Points of Emphasis).
                  </p>
                </div>

                <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ margin: '0 0 6px', color: '#f5ede1' }}>Era Evolution (2002 vs 2026)</h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#c9a27a' }}>
                    The Golden Era has a slower pace, higher mid-range percentages and more inside physicality. The Modern Era favors perimeter spacing, transition threes and a high pace.
                  </p>
                </div>
              </div>
            </div>
          )}
      </div>
    </ModalShell>
  );
};
