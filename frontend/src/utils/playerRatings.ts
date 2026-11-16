// Rating pillars and attribute badges derived from a player's raw abilities.

export interface BadgeInfo {
  id: string;
  name: string;
  category: 'shooting' | 'defense' | 'playmaking' | 'athletic' | 'iq';
  tier: 'gold' | 'silver' | 'bronze';
  icon: string;
  desc: string;
}

export const computePlayerBadges = (player: any): BadgeInfo[] => {
  if (!player) return [];
  const ab = player.abilita || {};
  const badges: BadgeInfo[] = [];

  const threePt = ab.three_point_shot_rating || 0;
  const midRange = ab.mid_range_shot_rating || 0;
  const perimDef = ab.perimeter_defense_rating || 0;
  const intDef = ab.interior_defense_rating || 0;
  const block = ab.block_rating || 0;
  const steal = ab.steal_rating || 0;
  const vision = ab.passing_vision || 0;
  const passAcc = ab.passing_accuracy || 0;
  const handle = ab.ball_handling || 0;
  const dunk = ab.dunk_rating || 0;
  const vert = ab.vertical || 0;
  const speed = ab.speed || 0;
  const defReb = ab.defensive_rebound_rating || 0;
  const offReb = ab.offensive_rebound_rating || 0;
  const shotIq = ab.shot_iq || 0;
  const offIq = ab.offensive_iq_rating || 0;
  const defIq = ab.defensive_iq_rating || 0;

  // 1. Sniper / Dead-Eye
  if (threePt >= 88) {
    badges.push({ id: 'deadeye', name: 'Dead-Eye Sniper', category: 'shooting', tier: 'gold', icon: '🎯', desc: 'Deadly 3-point marksman with a lightning-quick release' });
  } else if (threePt >= 82) {
    badges.push({ id: 'deadeye', name: 'Sharpshooter', category: 'shooting', tier: 'silver', icon: '🎯', desc: 'Consistent perimeter scoring threat beyond the arc' });
  } else if (threePt >= 76) {
    badges.push({ id: 'deadeye', name: 'Corner Threat', category: 'shooting', tier: 'bronze', icon: '🎯', desc: 'Capable corner shooter punishing double teams' });
  }

  // 2. Mid-Range Maestro
  if (midRange >= 86) {
    badges.push({ id: 'midrange', name: 'Mid-Range Maestro', category: 'shooting', tier: 'gold', icon: '🏹', desc: 'Unguardable pull-up shooter from mid-range' });
  } else if (midRange >= 80) {
    badges.push({ id: 'midrange', name: 'Mid-Range Specialist', category: 'shooting', tier: 'silver', icon: '🏹', desc: 'Lethal and consistent from the mid-range' });
  }

  // 3. Perimeter Lockdown
  if (perimDef >= 88 && steal >= 75) {
    badges.push({ id: 'lockdown', name: 'Lockdown Defender', category: 'defense', tier: 'gold', icon: '🔒', desc: 'Elite perimeter defender capable of neutralizing superstar scorers' });
  } else if (perimDef >= 82) {
    badges.push({ id: 'lockdown', name: 'Perimeter Stopper', category: 'defense', tier: 'silver', icon: '🔒', desc: 'Solid 1v1 on-ball defender with great lateral slides' });
  }

  // 4. Rim Protector & Paint Beast
  if (intDef >= 86 && block >= 82) {
    badges.push({ id: 'rim_protector', name: 'Rim Protector', category: 'defense', tier: 'gold', icon: '🛡️', desc: 'Supreme paint protector and elite rim intimidator' });
  } else if (intDef >= 80 || block >= 78) {
    badges.push({ id: 'rim_protector', name: 'Paint Anchor', category: 'defense', tier: 'silver', icon: '🛡️', desc: 'Reliable rim presence and shot contester' });
  }

  // 5. Glass Cleaner / Rebound Machine
  if (defReb >= 88 || offReb >= 86) {
    badges.push({ id: 'rebound', name: 'Glass Cleaner', category: 'athletic', tier: 'gold', icon: '🧲', desc: 'Dominant force on offensive and defensive glass' });
  } else if (defReb >= 80 || offReb >= 78) {
    badges.push({ id: 'rebound', name: 'Board Crasher', category: 'athletic', tier: 'silver', icon: '🧲', desc: 'Disciplined box-out artist securing second possessions' });
  }

  // 6. Floor General
  if (vision >= 88 && passAcc >= 86) {
    badges.push({ id: 'floor_general', name: 'Floor General', category: 'playmaking', tier: 'gold', icon: '👑', desc: 'Elite floor general with 360-degree court vision elevating teammates' });
  } else if (vision >= 82 || passAcc >= 82) {
    badges.push({ id: 'floor_general', name: 'Primary Playmaker', category: 'playmaking', tier: 'silver', icon: '👑', desc: 'Dependable distributor and skilled setup passer' });
  }

  // 7. Ankle Breaker / Handles
  if (handle >= 88) {
    badges.push({ id: 'handles', name: 'Ankle Breaker', category: 'playmaking', tier: 'gold', icon: '⚡', desc: 'Dazzling handle creating instant separation off the dribble' });
  } else if (handle >= 82) {
    badges.push({ id: 'handles', name: 'Sure Hands', category: 'playmaking', tier: 'silver', icon: '⚡', desc: 'Poised ball control under heavy pressure' });
  }

  // 8. Posterizer / High Flyer
  if (dunk >= 86 && vert >= 84) {
    badges.push({ id: 'posterizer', name: 'Posterizer', category: 'athletic', tier: 'gold', icon: '💥', desc: 'Explosive rim attacker finishing through defenders' });
  } else if (dunk >= 80) {
    badges.push({ id: 'posterizer', name: 'Aerial Finisher', category: 'athletic', tier: 'silver', icon: '💥', desc: 'Above-the-rim finisher in transition' });
  }

  // 9. Speed Demon
  if (speed >= 88) {
    badges.push({ id: 'speed_demon', name: 'Speed Demon', category: 'athletic', tier: 'gold', icon: '🏎️', desc: 'Blistering open-court top-end speed in fast breaks' });
  }

  // 10. Clutch & High IQ
  if (shotIq >= 86 && offIq >= 86 && defIq >= 86) {
    badges.push({ id: 'iq', name: 'Basketball Savant', category: 'iq', tier: 'gold', icon: '🧠', desc: 'Genius basketball IQ reading defensive schemes steps ahead' });
  } else if (shotIq >= 80 || offIq >= 82) {
    badges.push({ id: 'iq', name: 'Decision Maker', category: 'iq', tier: 'silver', icon: '🧠', desc: 'Poised shot selector making high-percentage reads' });
  }

  return badges;
};

export interface RatingPillar {
  label: string;
  value: number;
}

/** The eight pillars shown on the card (same maths as the radar chart); missing abilities fall back on overall. */
export function computeRatingPillars(player: any): RatingPillar[] {
  const ab = player?.abilita || {};
  const ovr = player?.ovr || 75;
  const stamina = ab.stamina || player?.stamina || 80;
  const round = (n: number) => Math.min(99, Math.round(n));

  return [
    { label: '3-Point', value: round(ab.three_point_shot_rating || ovr * 0.9) },
    { label: 'Mid-range', value: round(ab.mid_range_shot_rating || ovr * 0.92) },
    { label: 'Inside', value: round(((ab.close_shot_rating || ovr) + (ab.layup_rating || ovr) + (ab.dunk_rating || 65)) / 3) },
    { label: 'Playmaking', value: round(((ab.passing_vision || ovr * 0.85) + (ab.passing_accuracy || ovr * 0.88) + (ab.ball_handling || ovr * 0.85)) / 3) },
    { label: 'Perim. D', value: round(((ab.perimeter_defense_rating || ovr * 0.88) + (ab.steal_rating || 65)) / 2) },
    { label: 'Interior D', value: round(((ab.interior_defense_rating || ovr * 0.85) + (ab.block_rating || 60)) / 2) },
    { label: 'Rebound', value: round(((ab.defensive_rebound_rating || ovr * 0.8) + (ab.offensive_rebound_rating || 60)) / 2) },
    { label: 'Athleticism', value: round(((ab.speed || 75) + (ab.vertical || 70) + stamina) / 3) },
  ];
}

/** Every rating the player popup lists, grouped; keys are the saved `abilita` fields. */
export const RATING_GROUPS: { label: string; ratings: [key: string, label: string][] }[] = [
  { label: 'Scoring', ratings: [['three_point_shot_rating', '3-point shot'], ['mid_range_shot_rating', 'Mid-range shot'], ['close_shot_rating', 'Close shot'], ['free_throw_rating', 'Free throws']] },
  { label: 'Playmaking', ratings: [['passing_vision', 'Passing vision'], ['passing_accuracy', 'Passing accuracy'], ['ball_handling', 'Ball handling']] },
  { label: 'Defense', ratings: [['perimeter_defense_rating', 'Perimeter defense'], ['interior_defense_rating', 'Interior defense'], ['steal_rating', 'Steals'], ['block_rating', 'Blocks']] },
  { label: 'Rebounding', ratings: [['defensive_rebound_rating', 'Defensive rebound'], ['offensive_rebound_rating', 'Offensive rebound']] },
  { label: 'Athleticism', ratings: [['speed', 'Speed'], ['vertical', 'Vertical'], ['strength', 'Strength'], ['dunk_rating', 'Dunk']] },
  { label: 'IQ', ratings: [['shot_iq', 'Shot IQ'], ['offensive_iq_rating', 'Offensive IQ'], ['defensive_iq_rating', 'Defensive IQ']] },
];

export interface RatedGroup {
  label: string;
  /** Rounded average of the ratings the player has; null when he has none of them. */
  value: number | null;
  ratings: { label: string; value: number | null }[];
}

/** The popup's ratings: no made-up fallbacks — a rating the save doesn't hold is null. */
export function ratingGroups(player: any): RatedGroup[] {
  const ab = player?.abilita || {};
  return RATING_GROUPS.map((g) => {
    const ratings = g.ratings.map(([key, label]) => ({ label, value: typeof ab[key] === 'number' ? ab[key] : null }));
    const known = ratings.map((r) => r.value).filter((v): v is number => v !== null);
    return { label: g.label, value: known.length ? Math.round(known.reduce((a, b) => a + b, 0) / known.length) : null, ratings };
  });
}
