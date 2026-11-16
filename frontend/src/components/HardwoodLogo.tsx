import { useId } from 'react';

// The game's mark: an orange ball whose seams draw an H. Same drawing as frontend/public/favicon.svg and
// scripts/make_icon.py (the .exe icon); keep the three in step.
export const HardwoodLogo = ({ size = 40, className }: { size?: number; className?: string }) => {
  const clipId = `hw-ball-${useId().replace(/:/g, '')}`;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden="true" focusable="false">
      <defs>
        <clipPath id={clipId}>
          <circle cx="32" cy="32" r="22" />
        </clipPath>
      </defs>
      <rect width="64" height="64" rx="14" fill="#14100d" />
      <circle cx="32" cy="32" r="22" fill="#ff6a1a" />
      <g clipPath={`url(#${clipId})`} fill="none" stroke="#14100d" strokeWidth="3.4" strokeLinecap="round">
        <path d="M21 9C28 22 28 42 21 55" />
        <path d="M43 9C36 22 36 42 43 55" />
        <path d="M8 32H56" />
      </g>
    </svg>
  );
};
