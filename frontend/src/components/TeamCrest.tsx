import React from 'react';
import { crestHue, crestLabel } from '../utils/crest';
import './WhatsNew.css';

interface TeamCrestProps {
  name: string;
  size?: number;
}

export const TeamCrest: React.FC<TeamCrestProps> = ({ name, size = 44 }) => (
  <div
    className="team-crest"
    aria-hidden="true"
    style={{
      width: size,
      height: size,
      fontSize: Math.round(size * 0.42),
      background: `linear-gradient(145deg, hsl(${crestHue(name)} 58% 38%), hsl(${crestHue(name)} 60% 24%))`,
    }}
  >
    {crestLabel(name)}
  </div>
);
