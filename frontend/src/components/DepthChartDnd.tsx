// File: frontend/src/components/DepthChartDnd.tsx
import React, { useState } from 'react';
import {
  DndContext,
  DragOverlay,
  useDraggable,
  useDroppable,
  closestCenter,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  defaultDropAnimationSideEffects
} from '@dnd-kit/core';
import type { DragStartEvent, DragEndEvent } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import {
  GripVertical,
  Sparkles,
  Zap,
  Shield,
  Activity,
  ArrowRightLeft,
  Clock,
  Award
} from 'lucide-react';
import { normalizeRole } from '../utils/roles';

export interface DepthRosterPlayer {
  nome: string;
  ruolo: string;
  ovr: number;
  potenziale: number;
  eta: number;
  minuti_target: number;
  infortunato: boolean;
  giorni_infortunio_rimanenti: number;
  is_star: boolean;
  valutazioni_posizionali?: Record<string, number>;
}

interface DepthChartDndProps {
  roster: DepthRosterPlayer[];
  customLineup: Record<string, string>;
  onLineupChange: (newLineup: Record<string, string>) => void;
  minutes?: Record<string, number>;
  onMinutesChange?: (newMinutes: Record<string, number>) => void;
  onAutoOptimize?: () => void;
}

const POSITIONS = ['PG', 'SG', 'SF', 'PF', 'C'] as const;
type PositionKey = typeof POSITIONS[number];

const formatPosition = (pos: string): string => normalizeRole(pos);

const getPositionalFitGrade = (player: DepthRosterPlayer, pos: string) => {
  const rating = player.valutazioni_posizionali?.[pos] ?? (formatPosition(player.ruolo) === pos ? player.ovr : player.ovr - 8);
  if (rating >= 90) return { grade: 'A+', color: '#ffd54f', bg: 'rgba(255,213,79,0.15)', text: 'Elite Fit' };
  if (rating >= 84) return { grade: 'A', color: '#10b981', bg: 'rgba(16,185,129,0.15)', text: 'Ideal' };
  if (rating >= 78) return { grade: 'B+', color: '#38bdf8', bg: 'rgba(56,189,248,0.15)', text: 'Compatible' };
  if (rating >= 72) return { grade: 'B', color: '#818cf8', bg: 'rgba(129,140,248,0.15)', text: 'Secondary' };
  if (rating >= 65) return { grade: 'C', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)', text: 'Out of Position' };
  return { grade: 'D', color: '#ef4444', bg: 'rgba(239,68,68,0.15)', text: 'Mismatched' };
};

const getOvrTierColor = (ovr: number) => {
  if (ovr >= 90) return { border: '#ffd54f', glow: 'rgba(255,213,79,0.4)', badge: '#ffd54f' };
  if (ovr >= 84) return { border: '#a855f7', glow: 'rgba(168,85,247,0.3)', badge: '#c084fc' };
  if (ovr >= 78) return { border: '#38bdf8', glow: 'rgba(56,189,248,0.3)', badge: '#38bdf8' };
  return { border: '#64748b', glow: 'rgba(100,116,139,0.2)', badge: '#94a3b8' };
};

// ---------------------------------------------------------------------------
// Draggable Player Card
// ---------------------------------------------------------------------------
interface DraggableCardProps {
  player: DepthRosterPlayer;
  targetPos?: string;
  isStarter?: boolean;
  mins?: number;
}

const DraggablePlayerCard: React.FC<DraggableCardProps> = ({
  player,
  targetPos,
  isStarter = false,
  mins
}) => {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `player-${player.nome}`,
    data: { player, isStarter, currentPos: targetPos }
  });

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.35 : 1,
    cursor: 'grab',
    touchAction: 'none'
  };

  const tier = getOvrTierColor(player.ovr);
  const fit = targetPos ? getPositionalFitGrade(player, targetPos) : null;
  const currentMins = mins ?? player.minuti_target;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className="player-drag-card"
    >
      <div
        style={{
          background: isStarter
            ? 'linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.98))'
            : 'rgba(15, 23, 42, 0.85)',
          backdropFilter: 'blur(8px)',
          borderRadius: '12px',
          border: isStarter ? `1.5px solid ${tier.border}` : '1px solid rgba(255,255,255,0.12)',
          boxShadow: isStarter ? `0 4px 16px ${tier.glow}` : '0 2px 8px rgba(0,0,0,0.4)',
          padding: '10px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
          userSelect: 'none'
        }}
      >
        <GripVertical size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />

        {/* Player Name & Role */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{
              fontSize: '13px',
              fontWeight: 800,
              color: 'var(--text-primary)',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis'
            }}>
              {player.nome}
            </span>
            {player.is_star && <span style={{ color: '#ffd54f', fontSize: '12px' }}>★</span>}
            {player.infortunato && (
              <span style={{ fontSize: '10px', background: 'rgba(239,68,68,0.2)', color: '#ef4444', padding: '1px 4px', borderRadius: '4px', fontWeight: 700 }}>
                🩹 {player.giorni_infortunio_rimanenti}d
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            <span>Nat: <strong style={{ color: 'var(--text-primary)' }}>{formatPosition(player.ruolo)}</strong></span>
            <span>• Age: {player.eta}</span>
            {currentMins !== undefined && (
              <span style={{ display: 'flex', alignItems: 'center', gap: '2px', color: '#38bdf8' }}>
                <Clock size={11} /> {currentMins}m
              </span>
            )}
          </div>
        </div>

        {/* Fit Badge (if assigned to a slot) */}
        {fit && (
          <span style={{
            background: fit.bg,
            color: fit.color,
            border: `1px solid ${fit.color}50`,
            fontSize: '10px',
            fontWeight: 800,
            padding: '2px 6px',
            borderRadius: '4px',
            flexShrink: 0
          }}>
            {fit.grade}
          </span>
        )}

        {/* OVR Pill */}
        <div style={{
          background: `${tier.badge}20`,
          color: tier.badge,
          border: `1px solid ${tier.badge}60`,
          fontWeight: 900,
          fontSize: '13px',
          padding: '2px 8px',
          borderRadius: '6px',
          flexShrink: 0
        }}>
          {player.ovr}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Droppable Starter Slot Container
// ---------------------------------------------------------------------------
interface StarterSlotProps {
  pos: PositionKey;
  player?: DepthRosterPlayer;
  mins?: number;
  isOver: boolean;
}

const DroppableStarterSlot: React.FC<StarterSlotProps> = ({ pos, player, mins, isOver }) => {
  const { setNodeRef } = useDroppable({
    id: `slot-${pos}`,
    data: { pos, isStarterSlot: true }
  });

  const fit = player ? getPositionalFitGrade(player, pos) : null;

  return (
    <div
      ref={setNodeRef}
      style={{
        background: isOver
          ? 'rgba(255, 184, 0, 0.15)'
          : 'rgba(15, 23, 42, 0.65)',
        border: isOver
          ? '2px dashed #ffd700'
          : player
            ? '1.5px solid rgba(255, 255, 255, 0.15)'
            : '1.5px dashed rgba(255, 255, 255, 0.2)',
        borderRadius: '14px',
        padding: '12px',
        minHeight: '120px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        position: 'relative',
        boxShadow: isOver ? '0 0 20px rgba(255, 184, 0, 0.4)' : 'none',
        transition: 'all 0.2s ease'
      }}
    >
      {/* Slot Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{
            background: 'var(--primary)',
            color: '#000000',
            fontWeight: 900,
            fontSize: '11px',
            padding: '2px 8px',
            borderRadius: '4px'
          }}>
            STARTER {pos}
          </span>
          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Pos #1</span>
        </div>
        {fit && (
          <span style={{ fontSize: '11px', color: fit.color, fontWeight: 800 }}>
            Fit: {fit.grade} ({fit.text})
          </span>
        )}
      </div>

      {/* Assigned Player Card or Empty Drop Target */}
      {player ? (
        <DraggablePlayerCard player={player} targetPos={pos} isStarter mins={mins} />
      ) : (
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          fontSize: '12px',
          border: '1px dashed rgba(255,255,255,0.1)',
          borderRadius: '8px',
          padding: '16px'
        }}>
          <ArrowRightLeft size={18} style={{ opacity: 0.5, marginBottom: '4px' }} />
          <span>Drag player here for <strong>{pos}</strong></span>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Droppable Bench/Reserves Zone
// ---------------------------------------------------------------------------
interface DroppableZoneProps {
  id: string;
  title: string;
  badge: string;
  badgeColor?: string;
  icon?: React.ReactNode;
  players: DepthRosterPlayer[];
  minutes?: Record<string, number>;
  isOver: boolean;
}

const DroppableZone: React.FC<DroppableZoneProps> = ({
  id,
  title,
  badge,
  badgeColor = '#38bdf8',
  icon,
  players,
  minutes,
  isOver
}) => {
  const { setNodeRef } = useDroppable({
    id,
    data: { zoneId: id }
  });

  return (
    <div
      ref={setNodeRef}
      style={{
        background: isOver ? 'rgba(56, 189, 248, 0.12)' : 'rgba(15, 23, 42, 0.5)',
        border: isOver ? '2px dashed #38bdf8' : '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '14px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        minHeight: '180px',
        transition: 'all 0.2s ease'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {icon}
          <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 800, color: 'var(--text-primary)' }}>
            {title}
          </h4>
        </div>
        <span style={{
          background: `${badgeColor}20`,
          color: badgeColor,
          border: `1px solid ${badgeColor}40`,
          fontSize: '11px',
          fontWeight: 800,
          padding: '2px 8px',
          borderRadius: '6px'
        }}>
          {badge} ({players.length})
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '8px' }}>
        {players.length > 0 ? (
          players.map(p => (
            <DraggablePlayerCard
              key={p.nome}
              player={p}
              mins={minutes ? minutes[p.nome] : p.minuti_target}
            />
          ))
        ) : (
          <div style={{
            gridColumn: '1 / -1',
            textAlign: 'center',
            padding: '24px',
            color: 'var(--text-muted)',
            fontSize: '12px',
            fontStyle: 'italic'
          }}>
            Drag players here to move them to {title.toLowerCase()}
          </div>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main Interactive Drag & Drop Depth Chart Component
// ---------------------------------------------------------------------------
export const DepthChartDnd: React.FC<DepthChartDndProps> = ({
  roster,
  customLineup,
  onLineupChange,
  minutes = {},
  onMinutesChange: _onMinutesChange,
  onAutoOptimize
}) => {
  const [activePlayer, setActivePlayer] = useState<DepthRosterPlayer | null>(null);
  const [activeOverId, setActiveOverId] = useState<string | null>(null);

  // Configure Sensors with distance threshold to support smooth click & drag without accidental dragging
  const pointerSensor = useSensor(PointerSensor, {
    activationConstraint: {
      distance: 6
    }
  });

  const touchSensor = useSensor(TouchSensor, {
    activationConstraint: {
      delay: 200,
      tolerance: 5
    }
  });

  const sensors = useSensors(pointerSensor, touchSensor);

  // Helper to get starter for a position
  const getStarterObj = (pos: PositionKey): DepthRosterPlayer | undefined => {
    const selectedName = customLineup[pos];

    if (selectedName) {
      return roster.find(p => p.nome === selectedName);
    }
    return roster.filter(p => !p.infortunato).find(p => normalizeRole(p.ruolo) === pos);
  };

  const starterNames = POSITIONS.map(pos => getStarterObj(pos)?.nome).filter(Boolean) as string[];

  // Bench: healthy players not starting
  const benchPlayers = roster
    .filter(p => !p.infortunato && !starterNames.includes(p.nome))
    .sort((a, b) => b.ovr - a.ovr);

  // Reserves / Inactive / Injured
  const reservePlayers = roster
    .filter(p => p.infortunato)
    .sort((a, b) => b.ovr - a.ovr);

  // Drag Handlers
  const handleDragStart = (event: DragStartEvent) => {
    const player = event.active.data.current?.player as DepthRosterPlayer | undefined;
    if (player) {
      setActivePlayer(player);
    }
  };

  const handleDragOver = (event: any) => {
    setActiveOverId(event.over ? String(event.over.id) : null);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActivePlayer(null);
    setActiveOverId(null);

    if (!over) return;

    const draggedPlayer = active.data.current?.player as DepthRosterPlayer | undefined;
    if (!draggedPlayer) return;

    const overId = String(over.id);

    // Case 1: Dropped onto a starter slot (slot-PG, slot-SG, etc.)
    if (overId.startsWith('slot-')) {
      const targetPos = overId.replace('slot-', '') as PositionKey;

      if (POSITIONS.includes(targetPos)) {
        const newLineup = { ...customLineup };

        // Check if dragged player was already a starter elsewhere
        let prevPosOfDragged: PositionKey | null = null;
        POSITIONS.forEach(pos => {
          if (getStarterObj(pos)?.nome === draggedPlayer.nome) {
            prevPosOfDragged = pos;
          }
        });

        const currentStarterInTargetSlot = getStarterObj(targetPos);

        // Assign dragged player to target slot
        newLineup[targetPos] = draggedPlayer.nome;

        // If dragged player came from another starter slot, swap the previous starter into that slot!
        if (prevPosOfDragged && prevPosOfDragged !== targetPos) {
          if (currentStarterInTargetSlot && currentStarterInTargetSlot.nome !== draggedPlayer.nome) {
            newLineup[prevPosOfDragged] = currentStarterInTargetSlot.nome;
          } else {
            delete newLineup[prevPosOfDragged];
          }
        }

        onLineupChange(newLineup);
      }
    }

    // Case 2: Dropped onto Bench or Reserves
    if (overId === 'slot-bench' || overId === 'slot-reserves') {
      const newLineup = { ...customLineup };
      let changed = false;

      POSITIONS.forEach(pos => {
        if (getStarterObj(pos)?.nome === draggedPlayer.nome) {
          delete newLineup[pos];
          changed = true;
        }
      });

      if (changed) {
        onLineupChange(newLineup);
      }
    }
  };

  // Drop animation config
  const dropAnimationConfig = {
    sideEffects: defaultDropAnimationSideEffects({
      styles: {
        active: {
          opacity: '0.4'
        }
      }
    })
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Header with Quick Actions */}
        <div className="card" style={{ padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles size={18} className="logo-gold" />
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800 }}>
                Interactive Drag & Drop Depth Chart
              </h3>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Drag player cards between Starter slots (PG–C) and Bench to rearrange lineup seamlessly
            </span>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            {onAutoOptimize && (
              <button
                className="btn btn-secondary"
                onClick={onAutoOptimize}
                style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 14px' }}
              >
                <Zap size={14} className="logo-gold" /> Auto-Optimize 5
              </button>
            )}
          </div>
        </div>

        {/* Section 1: 5 Starting Lineup Positions (Droppable) */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
            <Award size={16} style={{ color: '#ffd54f' }} />
            <span style={{ fontSize: '13px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-primary)' }}>
              Starting Unit (5 Starters)
            </span>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '12px'
          }}>
            {POSITIONS.map(pos => {
              const starter = getStarterObj(pos);
              const isOver = activeOverId === `slot-${pos}`;

              return (
                <DroppableStarterSlot
                  key={pos}
                  pos={pos}
                  player={starter}
                  mins={starter ? (minutes[starter.nome] ?? starter.minuti_target) : undefined}
                  isOver={isOver}
                />
              );
            })}
          </div>
        </div>

        {/* Section 2: Bench & Second Unit Pool */}
        <DroppableZone
          id="slot-bench"
          title="Second Unit & Rotation Bench"
          badge="In Rotation"
          badgeColor="#38bdf8"
          icon={<Shield size={16} style={{ color: '#38bdf8' }} />}
          players={benchPlayers}
          minutes={minutes}
          isOver={activeOverId === 'slot-bench'}
        />

        {/* Section 3: Reserves & Inactive (if any injured) */}
        {reservePlayers.length > 0 && (
          <DroppableZone
            id="slot-reserves"
            title="Injured & Inactive Reserve List"
            badge="Inactive"
            badgeColor="#ef4444"
            icon={<Activity size={16} style={{ color: '#ef4444' }} />}
            players={reservePlayers}
            minutes={minutes}
            isOver={activeOverId === 'slot-reserves'}
          />
        )}
      </div>

      {/* Floating Drag Overlay Card */}
      <DragOverlay dropAnimation={dropAnimationConfig}>
        {activePlayer ? (
          <div style={{
            width: '280px',
            transform: 'scale(1.05)',
            boxShadow: '0 20px 40px rgba(0,0,0,0.8), 0 0 20px rgba(255, 184, 0, 0.6)',
            borderRadius: '12px',
            border: '2px solid #ffd700',
            background: 'rgba(15, 23, 42, 0.98)',
            padding: '12px',
            color: '#ffffff',
            pointerEvents: 'none'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <span style={{ fontWeight: 800, fontSize: '14px', color: '#ffd700' }}>
                {activePlayer.nome} {activePlayer.is_star && '★'}
              </span>
              <span style={{ background: '#ffd700', color: '#000', fontWeight: 900, fontSize: '11px', padding: '2px 6px', borderRadius: '4px' }}>
                {activePlayer.ovr} OVR
              </span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              Nat Pos: <strong>{formatPosition(activePlayer.ruolo)}</strong> • Age: {activePlayer.eta}
            </div>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
};
