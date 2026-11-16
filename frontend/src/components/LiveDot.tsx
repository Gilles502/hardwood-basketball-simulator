import React from 'react';
import type { LiveStatus } from '../store/liveStore';
import './LiveDot.css';

/** Green LIVE when the last refresh worked, amber OFFLINE when it failed, nothing before the first one. */
export const LiveDot: React.FC<{ status: LiveStatus }> = ({ status }) => {
  if (status === 'idle') return null;
  return (
    <span className={`live-dot live-dot-${status}`} role="status">
      {status === 'live' ? 'LIVE' : 'OFFLINE'}
    </span>
  );
};
