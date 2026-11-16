// File: frontend/src/pages/TeamSelection.tsx
import React, { useState } from 'react';
import { useLeagueStore } from '../store/leagueStore';
import { Trophy, Star, ShieldAlert, ChevronRight, Play, Eye } from 'lucide-react';

export const TeamSelection: React.FC = () => {
  const { leagueData, setPlayerTeam, loading } = useLeagueStore();
  const [selectedTeam, setSelectedTeam] = useState<string>('');

  if (!leagueData) return null;

  const { east, west } = leagueData.classifica;

  const handleStartCareer = () => {
    if (!selectedTeam) return;
    setPlayerTeam(selectedTeam);
  };

  return (
    <div style={{
      minHeight: 'calc(100vh / var(--ui-zoom, 1))',
      width: 'calc(100vw / var(--ui-zoom, 1))',
      backgroundColor: '#09090b',
      backgroundImage: 'radial-gradient(circle at 50% 30%, rgba(255, 184, 0, 0.05), transparent 60%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '40px 20px',
      overflowY: 'auto'
    }}>
      <div className="card" style={{
        width: '100%',
        maxWidth: '850px',
        padding: '36px',
        background: 'rgba(15, 15, 20, 0.7)',
        backdropFilter: 'blur(20px)',
        border: '1px solid var(--border)',
        boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px'
      }}>
        {/* Logo and Title */}
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: '60px',
            height: '60px',
            borderRadius: '16px',
            background: 'linear-gradient(135deg, var(--primary), var(--accent))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 16px auto',
            boxShadow: '0 0 20px rgba(255, 184, 0, 0.2)'
          }}>
            <Trophy size={30} style={{ color: '#09090b' }} />
          </div>
          <h1 style={{ fontSize: '32px', margin: '0 0 8px 0', fontWeight: 800, letterSpacing: '1px' }}>
            NBA GM <span style={{ color: 'var(--primary)' }}>SIMULATOR</span>
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', maxWidth: '500px', margin: '0 auto', lineHeight: '1.5' }}>
            Select an NBA franchise to manage. Take command as General Manager: manage the roster, negotiate blockbuster trades, design tactical gameplans, and build a dynasty.
          </p>
        </div>

        {/* Categories grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', margin: '10px 0' }}>
          
          {/* East Conference */}
          <div className="card" style={{ padding: '20px', background: 'rgba(255,255,255,0.01)' }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '15px', fontWeight: 700, color: 'var(--primary)', borderBottom: '1px solid var(--border)', paddingBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Star size={16} /> Eastern Conference
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '8px', maxHeight: '300px', overflowY: 'auto', paddingRight: '4px' }}>
              {east.map((t) => (
                <div
                  key={t.nome}
                  onClick={() => setSelectedTeam(t.nome)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '6px',
                    background: selectedTeam === t.nome ? 'var(--primary-trans)' : 'rgba(255,255,255,0.02)',
                    border: selectedTeam === t.nome ? '1px solid var(--primary)' : '1px solid var(--border)',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: selectedTeam === t.nome ? 700 : 600,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    transition: 'all 0.2s ease'
                  }}
                >
                  <span>{t.nome}</span>
                  <ChevronRight size={14} style={{ opacity: selectedTeam === t.nome ? 1 : 0.3 }} />
                </div>
              ))}
            </div>
          </div>

          {/* West Conference */}
          <div className="card" style={{ padding: '20px', background: 'rgba(255,255,255,0.01)' }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '15px', fontWeight: 700, color: '#60a5fa', borderBottom: '1px solid var(--border)', paddingBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Star size={16} /> Western Conference
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '8px', maxHeight: '300px', overflowY: 'auto', paddingRight: '4px' }}>
              {west.map((t) => (
                <div
                  key={t.nome}
                  onClick={() => setSelectedTeam(t.nome)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '6px',
                    background: selectedTeam === t.nome ? 'rgba(96, 165, 250, 0.08)' : 'rgba(255,255,255,0.02)',
                    border: selectedTeam === t.nome ? '1px solid #60a5fa' : '1px solid var(--border)',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: selectedTeam === t.nome ? 700 : 600,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    transition: 'all 0.2s ease'
                  }}
                >
                  <span>{t.nome}</span>
                  <ChevronRight size={14} style={{ opacity: selectedTeam === t.nome ? 1 : 0.3 }} />
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* Start Button Box */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', borderTop: '1px solid var(--border)', paddingTop: '20px' }}>
          {selectedTeam ? (
            <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
              Selected Franchise: <strong style={{ color: 'var(--primary)' }}>{selectedTeam}</strong>
            </div>
          ) : (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <ShieldAlert size={14} /> Select an NBA franchise, or proceed as League Spectator.
            </div>
          )}

          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
            <button
              className="btn btn-primary"
              disabled={!selectedTeam || loading}
              onClick={handleStartCareer}
              style={{
                padding: '12px 36px',
                fontSize: '15px',
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: selectedTeam ? '0 4px 15px rgba(255, 184, 0, 0.2)' : 'none'
              }}
            >
              <Play size={16} /> {loading ? 'Loading Roster...' : 'Start Franchise Career'}
            </button>

            <button
              className="btn btn-secondary"
              disabled={loading}
              onClick={() => setPlayerTeam("")}
              style={{
                padding: '12px 24px',
                fontSize: '15px',
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                borderColor: 'rgba(255,255,255,0.1)',
                background: 'rgba(255,255,255,0.02)'
              }}
            >
              <Eye size={16} style={{ color: 'var(--text-secondary)' }} /> League Spectator
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};
