// File: frontend/src/utils/teamVisuals.ts

export interface TeamVisuals {
  abbr: string;
  bg: string;
  color: string;
  primaryColor: string;
  secondaryColor: string;
}

export const getTeamVisuals = (teamName: string): TeamVisuals => {
  if (!teamName) {
    return {
      abbr: 'NBA',
      bg: 'linear-gradient(135deg, #1f2937 0%, #111827 100%)',
      color: '#ffffff',
      primaryColor: '#3b82f6',
      secondaryColor: '#1d428a'
    };
  }

  const name = teamName.toLowerCase();

  if (name.includes('lakers')) {
    return {
      abbr: 'LAL',
      bg: 'linear-gradient(135deg, #552583 0%, #FDB927 100%)',
      color: '#ffffff',
      primaryColor: '#552583',
      secondaryColor: '#FDB927'
    };
  }
  if (name.includes('celtics')) {
    return {
      abbr: 'BOS',
      bg: 'linear-gradient(135deg, #007A33 0%, #000000 100%)',
      color: '#ffffff',
      primaryColor: '#007A33',
      secondaryColor: '#BA9653'
    };
  }
  if (name.includes('warriors')) {
    return {
      abbr: 'GSW',
      bg: 'linear-gradient(135deg, #1D428A 0%, #FFC72C 100%)',
      color: '#ffffff',
      primaryColor: '#1D428A',
      secondaryColor: '#FFC72C'
    };
  }
  if (name.includes('bulls')) {
    return {
      abbr: 'CHI',
      bg: 'linear-gradient(135deg, #CE1141 0%, #000000 100%)',
      color: '#ffffff',
      primaryColor: '#CE1141',
      secondaryColor: '#000000'
    };
  }
  if (name.includes('knicks')) {
    return {
      abbr: 'NYK',
      bg: 'linear-gradient(135deg, #006BB6 0%, #F58426 100%)',
      color: '#ffffff',
      primaryColor: '#006BB6',
      secondaryColor: '#F58426'
    };
  }
  if (name.includes('heat')) {
    return {
      abbr: 'MIA',
      bg: 'linear-gradient(135deg, #98002E 0%, #F9A01B 100%)',
      color: '#ffffff',
      primaryColor: '#98002E',
      secondaryColor: '#F9A01B'
    };
  }
  if (name.includes('spurs')) {
    return {
      abbr: 'SAS',
      bg: 'linear-gradient(135deg, #8a8d8f 0%, #000000 100%)',
      color: '#ffffff',
      primaryColor: '#C4CED4',
      secondaryColor: '#000000'
    };
  }
  if (name.includes('suns')) {
    return {
      abbr: 'PHX',
      bg: 'linear-gradient(135deg, #1D1160 0%, #E56020 100%)',
      color: '#ffffff',
      primaryColor: '#E56020',
      secondaryColor: '#1D1160'
    };
  }
  if (name.includes('bucks')) {
    return {
      abbr: 'MIL',
      bg: 'linear-gradient(135deg, #00471B 0%, #EEE1C6 100%)',
      color: '#ffffff',
      primaryColor: '#00471B',
      secondaryColor: '#EEE1C6'
    };
  }
  if (name.includes('sixers') || name.includes('76ers')) {
    return {
      abbr: 'PHI',
      bg: 'linear-gradient(135deg, #006BB6 0%, #ED174C 100%)',
      color: '#ffffff',
      primaryColor: '#006BB6',
      secondaryColor: '#ED174C'
    };
  }
  if (name.includes('clippers')) {
    return {
      abbr: 'LAC',
      bg: 'linear-gradient(135deg, #C8102E 0%, #1D428A 100%)',
      color: '#ffffff',
      primaryColor: '#C8102E',
      secondaryColor: '#1D428A'
    };
  }
  if (name.includes('mavericks')) {
    return {
      abbr: 'DAL',
      bg: 'linear-gradient(135deg, #00538C 0%, #002B5E 100%)',
      color: '#ffffff',
      primaryColor: '#00538C',
      secondaryColor: '#B8C4CA'
    };
  }
  if (name.includes('nets') && !name.includes('hornets')) {
    return {
      abbr: 'BKN',
      bg: 'linear-gradient(135deg, #262626 0%, #000000 100%)',
      color: '#ffffff',
      primaryColor: '#ffffff',
      secondaryColor: '#707271'
    };
  }
  if (name.includes('nuggets')) {
    return {
      abbr: 'DEN',
      bg: 'linear-gradient(135deg, #0E2240 0%, #FEC524 100%)',
      color: '#ffffff',
      primaryColor: '#0E2240',
      secondaryColor: '#FEC524'
    };
  }
  if (name.includes('rockets')) {
    return {
      abbr: 'HOU',
      bg: 'linear-gradient(135deg, #CE1141 0%, #000000 100%)',
      color: '#ffffff',
      primaryColor: '#CE1141',
      secondaryColor: '#939598'
    };
  }
  if (name.includes('pacers')) {
    return {
      abbr: 'IND',
      bg: 'linear-gradient(135deg, #002D62 0%, #FDBB30 100%)',
      color: '#ffffff',
      primaryColor: '#002D62',
      secondaryColor: '#FDBB30'
    };
  }
  if (name.includes('grizzlies')) {
    return {
      abbr: 'MEM',
      bg: 'linear-gradient(135deg, #5D76A9 0%, #12173F 100%)',
      color: '#ffffff',
      primaryColor: '#5D76A9',
      secondaryColor: '#12173F'
    };
  }
  if (name.includes('timberwolves') || name.includes('wolves')) {
    return {
      abbr: 'MIN',
      bg: 'linear-gradient(135deg, #0C2340 0%, #78BE20 100%)',
      color: '#ffffff',
      primaryColor: '#0C2340',
      secondaryColor: '#78BE20'
    };
  }
  if (name.includes('pelicans')) {
    return {
      abbr: 'NOP',
      bg: 'linear-gradient(135deg, #0C2340 0%, #C8102E 100%)',
      color: '#ffffff',
      primaryColor: '#0C2340',
      secondaryColor: '#C8102E'
    };
  }
  if (name.includes('thunder')) {
    return {
      abbr: 'OKC',
      bg: 'linear-gradient(135deg, #007AC1 0%, #EF3B24 100%)',
      color: '#ffffff',
      primaryColor: '#007AC1',
      secondaryColor: '#EF3B24'
    };
  }
  if (name.includes('magic')) {
    return {
      abbr: 'ORL',
      bg: 'linear-gradient(135deg, #0077C0 0%, #000000 100%)',
      color: '#ffffff',
      primaryColor: '#0077C0',
      secondaryColor: '#C4CED4'
    };
  }
  if (name.includes('blazers') || name.includes('trail')) {
    return {
      abbr: 'POR',
      bg: 'linear-gradient(135deg, #E03A3E 0%, #000000 100%)',
      color: '#ffffff',
      primaryColor: '#E03A3E',
      secondaryColor: '#BAC3C9'
    };
  }
  if (name.includes('kings')) {
    return {
      abbr: 'SAC',
      bg: 'linear-gradient(135deg, #5A2D81 0%, #63727A 100%)',
      color: '#ffffff',
      primaryColor: '#5A2D81',
      secondaryColor: '#63727A'
    };
  }
  if (name.includes('raptors')) {
    return {
      abbr: 'TOR',
      bg: 'linear-gradient(135deg, #CE1141 0%, #000000 100%)',
      color: '#ffffff',
      primaryColor: '#CE1141',
      secondaryColor: '#A1A1A4'
    };
  }
  if (name.includes('jazz')) {
    return {
      abbr: 'UTA',
      bg: 'linear-gradient(135deg, #002B5C 0%, #F9A01B 100%)',
      color: '#ffffff',
      primaryColor: '#002B5C',
      secondaryColor: '#F9A01B'
    };
  }
  if (name.includes('wizards')) {
    return {
      abbr: 'WAS',
      bg: 'linear-gradient(135deg, #002B5C 0%, #E31837 100%)',
      color: '#ffffff',
      primaryColor: '#002B5C',
      secondaryColor: '#E31837'
    };
  }
  if (name.includes('hawks')) {
    return {
      abbr: 'ATL',
      bg: 'linear-gradient(135deg, #C8102E 0%, #FDB927 100%)',
      color: '#ffffff',
      primaryColor: '#C8102E',
      secondaryColor: '#FDB927'
    };
  }
  if (name.includes('hornets')) {
    return {
      abbr: 'CHA',
      bg: 'linear-gradient(135deg, #1D1160 0%, #00788C 100%)',
      color: '#ffffff',
      primaryColor: '#00788C',
      secondaryColor: '#1D1160'
    };
  }
  if (name.includes('cavaliers') || name.includes('cavs')) {
    return {
      abbr: 'CLE',
      bg: 'linear-gradient(135deg, #860038 0%, #FDBB30 100%)',
      color: '#ffffff',
      primaryColor: '#860038',
      secondaryColor: '#FDBB30'
    };
  }
  if (name.includes('pistons')) {
    return {
      abbr: 'DET',
      bg: 'linear-gradient(135deg, #1D428A 0%, #C8102E 100%)',
      color: '#ffffff',
      primaryColor: '#1D428A',
      secondaryColor: '#C8102E'
    };
  }

  // Fallback for custom or unknown teams
  const words = teamName.split(' ');
  const abbr = words.length > 1
    ? words.map(w => w[0]).join('').substring(0, 3).toUpperCase()
    : teamName.substring(0, 3).toUpperCase();

  return {
    abbr,
    bg: 'linear-gradient(135deg, #374151 0%, #111827 100%)',
    color: '#ffffff',
    primaryColor: '#4b5563',
    secondaryColor: '#1f2937'
  };
};
