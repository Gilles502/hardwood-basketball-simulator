import React, { useState, useEffect } from 'react';
import { Eye, ShieldAlert, Award, Compass, Search, UserCheck } from 'lucide-react';
import { normalizeRole } from '../utils/roles';

interface CollegeStats {
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  fg_pct: string;
  tp_pct: string;
}

interface Prospect {
  name: string;
  role: string;
  age: number;
  provenance: string;
  college_stats: CollegeStats;
  scouting_progress: number;
  assigned_scout: string | null;
  projection: string;
  pos: number;
  ovr_display: string;
  pot_display: string;
  archetype: string;
  attributes: Record<string, string>;
}

interface Scout {
  name: string;
  accuracy: string;
  speed: string;
  assigned_to: string | null;
}

interface ScoutingState {
  scout_staff: Scout[];
  workouts_left: number;
  league_state: string;
  prospects: Prospect[];
}

export const Scouting: React.FC = () => {
  const [scoutingState, setScoutingState] = useState<ScoutingState | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState('ALL');
  const [scoutingFilter, setScoutingFilter] = useState('ALL');
  const [selectedProspect, setSelectedProspect] = useState<Prospect | null>(null);
  const [assigningScoutIdx, setAssigningScoutIdx] = useState<number | null>(null);

  const fetchScoutingState = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/scouting/state');
      if (res.ok) {
        const data = await res.json();
        setScoutingState(data);
        // Se c'è un prospetto selezionato, aggiorna i suoi dati
        if (selectedProspect) {
          const updated = data.prospects.find((p: Prospect) => p.name === selectedProspect.name);
          if (updated) {
            setSelectedProspect(updated);
          }
        }
      }
    } catch (e) {
      console.error("Error retrieving the scouting state:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScoutingState();
  }, []);

  const handleAssignScout = async (scoutIdx: number, prospectName: string | null) => {
    try {
      const res = await fetch('/api/scouting/assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scout_index: scoutIdx, prospect_name: prospectName })
      });
      if (res.ok) {
        // Ricarica lo stato
        await fetchScoutingState();
        setAssigningScoutIdx(null);
      }
    } catch (e) {
      console.error("Error assigning the scout:", e);
    }
  };

  const handleRunWorkout = async (prospectName: string) => {
    try {
      const res = await fetch('/api/scouting/workout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prospect_name: prospectName })
      });
      if (res.ok) {
        // Ricarica lo stato
        await fetchScoutingState();
      }
    } catch (e) {
      console.error("Error running the private workout:", e);
    }
  };

  if (loading && !scoutingState) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  if (!scoutingState) {
    return (
      <div className="card" style={{ padding: '40px', textAlign: 'center' }}>
        <ShieldAlert size={48} className="logo-gold" style={{ marginBottom: '16px' }} />
        <h2>No scouting data available</h2>
        <p style={{ color: 'var(--text-secondary)' }}>
          Ensure the simulation is active and the draft class has been generated.
        </p>
      </div>
    );
  }

  const { scout_staff, workouts_left, league_state, prospects } = scoutingState;

  const filteredProspects = prospects.filter(p => {
    const matchesSearch = p.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          p.provenance.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRole = roleFilter === 'ALL' || normalizeRole(p.role) === roleFilter;
    
    let matchesScouting = true;
    if (scoutingFilter === 'NOT_SCOUTED') {
      matchesScouting = p.scouting_progress <= 10.0;
    } else if (scoutingFilter === 'SCOUTING') {
      matchesScouting = p.scouting_progress > 10.0 && p.scouting_progress < 100.0;
    } else if (scoutingFilter === 'COMPLETED') {
      matchesScouting = p.scouting_progress >= 100.0;
    }
    
    return matchesSearch && matchesRole && matchesScouting;
  });

  const getProgressColor = (progress: number) => {
    if (progress >= 100.0) return 'var(--primary)';
    if (progress >= 60.0) return '#60a5fa';
    if (progress >= 30.0) return '#fbbf24';
    return '#a1a1aa';
  };

  const isOffseason = league_state.startsWith('OFFSEASON') || league_state === 'DRAFT_USER_PICK';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Title Banner */}
      <div className="card" style={{ 
        padding: '24px', 
        background: 'linear-gradient(135deg, rgba(39, 39, 42, 0.6) 0%, rgba(9, 9, 11, 0.8) 100%)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
            <Compass className="logo-gold" size={28} />
            <h1 style={{ margin: 0, fontSize: '26px', fontWeight: 800, letterSpacing: '-0.5px' }}>Scouting Center</h1>
          </div>
          <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '14px' }}>
            Scout college prospects during the Regular Season and prepare your Draft Big Board.
          </p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <span className="season-badge" style={{ padding: '6px 12px', fontSize: '13px' }}>
            Pre-Draft Workouts Left: <strong>{workouts_left}</strong>
          </span>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px' }}>
            Current Phase: <strong style={{ color: 'var(--text-primary)' }}>{league_state.replace('_', ' ')}</strong>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 3fr', gap: '20px', alignItems: 'start' }}>
        
        {/* Left Side: Scouting Staff */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ padding: '18px' }}>
            <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Eye size={18} className="logo-gold" />
              Scouting Staff ({scout_staff.length})
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {scout_staff.map((scout, idx) => (
                <div key={idx} style={{ 
                  padding: '12px', 
                  background: 'rgba(255,255,255,0.01)', 
                  border: '1px solid var(--border)', 
                  borderRadius: '8px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontWeight: 600, fontSize: '14px' }}>{scout.name}</span>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      <span style={{ fontSize: '10px', background: 'rgba(96,165,250,0.1)', color: '#60a5fa', padding: '2px 6px', borderRadius: '4px', fontWeight: 'bold' }}>
                        ACC: {scout.accuracy}
                      </span>
                      <span style={{ fontSize: '10px', background: 'rgba(168,85,247,0.1)', color: '#a855f7', padding: '2px 6px', borderRadius: '4px', fontWeight: 'bold' }}>
                        SPD: {scout.speed}
                      </span>
                    </div>
                  </div>
                  
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    Assigned to:{' '}
                    {scout.assigned_to ? (
                      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                        {scout.assigned_to}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--primary)', fontStyle: 'italic' }}>Available (Idle)</span>
                    )}
                  </div>
                  
                  {scout.assigned_to && (
                    <button 
                      className="btn btn-secondary" 
                      onClick={() => handleAssignScout(idx, null)}
                      style={{ width: '100%', padding: '4px 8px', fontSize: '11px', marginTop: '10px' }}
                    >
                      Remove Assignment
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Side: Big Board Prospects */}
        <div className="card" style={{ padding: '20px' }}>
          {/* Filters Bar */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search style={{ position: 'absolute', left: '12px', top: '10px', color: 'var(--text-muted)' }} size={16} />
              <input 
                type="text" 
                placeholder="Search prospect by name or college..." 
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{ 
                  width: '100%', 
                  padding: '8px 12px 8px 36px', 
                  backgroundColor: 'rgba(0,0,0,0.2)', 
                  border: '1px solid var(--border)', 
                  borderRadius: '6px',
                  color: '#fff',
                  fontSize: '13px'
                }}
              />
            </div>
            
            <div style={{ display: 'flex', gap: '10px' }}>
              <select 
                value={roleFilter} 
                onChange={(e) => setRoleFilter(e.target.value)}
                style={{ padding: '8px 12px', backgroundColor: 'rgba(0,0,0,0.2)', border: '1px solid var(--border)', borderRadius: '6px', color: '#fff', fontSize: '13px' }}
              >
                <option value="ALL">All Positions</option>
                <option value="PG">Point Guard (PG)</option>
                <option value="SG">Shooting Guard (SG)</option>
                <option value="SF">Small Forward (SF)</option>
                <option value="PF">Power Forward (PF)</option>
                <option value="C">Center (C)</option>
              </select>

              <select 
                value={scoutingFilter} 
                onChange={(e) => setScoutingFilter(e.target.value)}
                style={{ padding: '8px 12px', backgroundColor: 'rgba(0,0,0,0.2)', border: '1px solid var(--border)', borderRadius: '6px', color: '#fff', fontSize: '13px' }}
              >
                <option value="ALL">All Statuses</option>
                <option value="NOT_SCOUTED">Unscouted (&lt;=10%)</option>
                <option value="SCOUTING">In Progress (11-99%)</option>
                <option value="COMPLETED">Fully Scouted (100%)</option>
              </select>
            </div>
          </div>

          {/* Prospects Table */}
          <div style={{ overflowX: 'auto' }}>
            <table className="table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--border)' }}>
                  <th style={{ padding: '12px 8px', fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Projected Pick</th>
                  <th style={{ padding: '12px 8px', fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Prospect</th>
                  <th style={{ padding: '12px 8px', fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Position</th>
                  <th style={{ padding: '12px 8px', fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>College / Origin</th>
                  <th style={{ padding: '12px 8px', fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Est. OVR</th>
                  <th style={{ padding: '12px 8px', fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Est. POT</th>
                  <th style={{ padding: '12px 8px', fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', width: '140px' }}>Progress</th>
                  <th style={{ padding: '12px 8px', fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Scout</th>
                </tr>
              </thead>
              <tbody>
                {filteredProspects.map((prospect, idx) => (
                  <tr 
                    key={idx} 
                    onClick={() => setSelectedProspect(prospect)}
                    className="table-row-hover"
                    style={{ 
                      borderBottom: '1px solid rgba(255,255,255,0.03)', 
                      cursor: 'pointer',
                      backgroundColor: selectedProspect?.name === prospect.name ? 'rgba(251,191,36,0.03)' : 'transparent'
                    }}
                  >
                    <td style={{ padding: '12px 8px' }}>
                      <span className="season-badge" style={{ 
                        fontSize: '11px', 
                        backgroundColor: prospect.pos <= 14 ? 'rgba(251,191,36,0.1)' : 'rgba(255,255,255,0.03)',
                        color: prospect.pos <= 14 ? 'var(--primary)' : 'var(--text-secondary)'
                      }}>
                        #{prospect.pos} - {prospect.projection}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px', fontWeight: 600 }}>{prospect.name}</td>
                    <td style={{ padding: '12px 8px' }}>{prospect.role}</td>
                    <td style={{ padding: '12px 8px', color: 'var(--text-secondary)', fontSize: '13px' }}>{prospect.provenance}</td>
                    <td style={{ padding: '12px 8px', fontWeight: 'bold', color: prospect.scouting_progress >= 90 ? 'var(--primary)' : '#fff' }}>
                      {prospect.ovr_display}
                    </td>
                    <td style={{ padding: '12px 8px', fontWeight: 'bold' }}>
                      {prospect.pot_display}
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{ flex: 1, height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ 
                            width: `${prospect.scouting_progress}%`, 
                            height: '100%', 
                            background: getProgressColor(prospect.scouting_progress)
                          }} />
                        </div>
                        <span style={{ fontSize: '11px', width: '32px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                          {Math.round(prospect.scouting_progress)}%
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 8px', fontSize: '12px' }}>
                      {prospect.assigned_scout ? (
                        <span style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <UserCheck size={12} className="logo-gold" />
                          {prospect.assigned_scout.split(' ')[0]}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>-</span>
                      )}
                    </td>
                  </tr>
                ))}
                
                {filteredProspects.length === 0 && (
                  <tr>
                    <td colSpan={8} style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No prospects match the selected filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>

      {/* Prospect Detail Drawer / Modal */}
      {selectedProspect && (
        <div style={{ 
          position: 'fixed', 
          top: 0, 
          right: 0, 
          width: '500px', 
          height: 'calc(100vh / var(--ui-zoom, 1))', 
          backgroundColor: 'rgba(15, 15, 20, 0.95)', 
          borderLeft: '1px solid var(--border)',
          boxShadow: '-10px 0 30px rgba(0,0,0,0.5)',
          zIndex: 1000, 
          padding: '30px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '24px',
          backdropFilter: 'blur(10px)'
        }}>
          {/* Header Close */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="season-badge" style={{ fontSize: '12px' }}>#{selectedProspect.pos} - PROSPECT</span>
            <button 
              onClick={() => { setSelectedProspect(null); setAssigningScoutIdx(null); }}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '24px', cursor: 'pointer' }}
            >
              &times;
            </button>
          </div>

          {/* Profile Basic Info */}
          <div>
            <h2 style={{ margin: '0 0 6px 0', fontSize: '24px', fontWeight: 800 }}>{selectedProspect.name}</h2>
            <div style={{ display: 'flex', gap: '12px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              <span>Position: <strong>{selectedProspect.role}</strong></span>
              <span>•</span>
              <span>Age: <strong>{selectedProspect.age} yrs</strong></span>
              <span>•</span>
              <span>{selectedProspect.provenance}</span>
            </div>
          </div>

          {/* Scouting Progress details */}
          <div className="card" style={{ padding: '14px', background: 'rgba(255,255,255,0.01)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '13px' }}>
              <span>Scouting Progress:</span>
              <strong style={{ color: getProgressColor(selectedProspect.scouting_progress) }}>
                {selectedProspect.scouting_progress}%
              </strong>
            </div>
            <div style={{ height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{ 
                width: `${selectedProspect.scouting_progress}%`, 
                height: '100%', 
                background: getProgressColor(selectedProspect.scouting_progress) 
              }} />
            </div>
          </div>

          {/* College Stats Panel (ALWAYS 100% VISIBLE) */}
          <div>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', textTransform: 'uppercase', color: 'var(--primary)', letterSpacing: '0.5px' }}>
              College Stats
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '8px', marginBottom: '12px' }}>
              <div className="card" style={{ padding: '10px', textAlign: 'center' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>PTS</div>
                <div style={{ fontSize: '18px', fontWeight: 800 }}>{selectedProspect.college_stats.pts}</div>
              </div>
              <div className="card" style={{ padding: '10px', textAlign: 'center' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>REB</div>
                <div style={{ fontSize: '18px', fontWeight: 800 }}>{selectedProspect.college_stats.reb}</div>
              </div>
              <div className="card" style={{ padding: '10px', textAlign: 'center' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>AST</div>
                <div style={{ fontSize: '18px', fontWeight: 800 }}>{selectedProspect.college_stats.ast}</div>
              </div>
              <div className="card" style={{ padding: '10px', textAlign: 'center' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>STL</div>
                <div style={{ fontSize: '18px', fontWeight: 800 }}>{selectedProspect.college_stats.stl}</div>
              </div>
              <div className="card" style={{ padding: '10px', textAlign: 'center' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>BLK</div>
                <div style={{ fontSize: '18px', fontWeight: 800 }}>{selectedProspect.college_stats.blk}</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '20px', fontSize: '12px', color: 'var(--text-secondary)', paddingLeft: '4px' }}>
              <span>FG%: <strong>{selectedProspect.college_stats.fg_pct}</strong></span>
              <span>3P%: <strong>{selectedProspect.college_stats.tp_pct}</strong></span>
            </div>
          </div>

          {/* Scouted Skill Ratings (Offuscated based on progress) */}
          <div>
            <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', textTransform: 'uppercase', color: 'var(--primary)', letterSpacing: '0.5px' }}>
              Scouted Skill Ratings
            </h4>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
              <div className="card" style={{ padding: '12px' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Overall Rating (OVR):</div>
                <div style={{ fontSize: '20px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>
                  {selectedProspect.ovr_display}
                </div>
              </div>
              <div className="card" style={{ padding: '12px' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Expected Potential (POT):</div>
                <div style={{ fontSize: '20px', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>
                  {selectedProspect.pot_display}
                </div>
              </div>
            </div>

            {selectedProspect.scouting_progress < 30.0 ? (
              <div className="card" style={{ padding: '20px', textAlign: 'center', background: 'rgba(239, 68, 68, 0.02)', border: '1px solid rgba(239,68,68,0.1)' }}>
                <ShieldAlert size={24} style={{ color: '#ef4444', margin: '0 auto 8px auto' }} />
                <div style={{ fontSize: '13px', fontWeight: 'bold', color: '#ef4444' }}>Insufficient Scouting</div>
                <p style={{ color: 'var(--text-secondary)', fontSize: '11px', margin: '4px 0 0 0' }}>
                  Scouting progress is below 30%. Assign a scout to uncover prospect attributes.
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                  Archetype / Playstyle: <strong style={{ color: '#fff' }}>{selectedProspect.archetype}</strong>
                </div>
                {Object.entries(selectedProspect.attributes).map(([key, val]) => (
                  <div key={key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{key}</span>
                    <strong style={{ color: '#fff' }}>{val}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Action Footer inside Drawer */}
          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {selectedProspect.scouting_progress < 100.0 && (
              <>
                {assigningScoutIdx === null ? (
                  <button 
                    className="btn btn-primary"
                    onClick={() => setAssigningScoutIdx(-1)}
                    style={{ width: '100%', justifyContent: 'center' }}
                  >
                    Assign Team Scout
                  </button>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px', border: '1px solid var(--border)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '12px', fontWeight: 'bold' }}>Select Scout:</div>
                    {scout_staff.map((scout, idx) => (
                      <button 
                        key={idx}
                        className="btn btn-secondary"
                        onClick={() => handleAssignScout(idx, selectedProspect.name)}
                        style={{ fontSize: '12px', padding: '6px 12px', width: '100%', justifyContent: 'space-between' }}
                      >
                        <span>{scout.name}</span>
                        <span style={{ opacity: 0.6 }}>({scout.assigned_to ? 'Reassign' : 'Assign'})</span>
                      </button>
                    ))}
                    <button 
                      className="btn btn-secondary"
                      onClick={() => setAssigningScoutIdx(null)}
                      style={{ fontSize: '12px', padding: '4px 8px', marginTop: '4px' }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </>
            )}

            {isOffseason && workouts_left > 0 && selectedProspect.scouting_progress < 100.0 && (
              <button 
                className="btn btn-primary"
                onClick={() => handleRunWorkout(selectedProspect.name)}
                style={{ width: '100%', justifyContent: 'center', background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)', border: 'none' }}
              >
                Conduct Private Workout (1 Workout)
              </button>
            )}
            
            {selectedProspect.scouting_progress >= 100.0 && (
              <div className="card" style={{ padding: '10px 14px', textAlign: 'center', background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16,185,129,0.2)' }}>
                <span style={{ color: '#10b981', fontWeight: 'bold', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'center' }}>
                  <Award size={16} /> Scouting 100% Complete
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
