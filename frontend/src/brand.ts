declare const __GAME_VERSION__: string;
declare const __GAME_CHANNEL__: string;

// Single source of truth for the product name (placeholder until the final name is chosen).
export const BRAND = {
  name: 'Hardwood Basketball Simulator',
  nameLines: ['Hardwood', 'Basketball', 'Simulator'],
  version: `v${__GAME_VERSION__} ${__GAME_CHANNEL__}`.trim(), // from core/version.py via vite.config.ts
} as const;
