// File: frontend/src/store/settingsStore.ts
// Per-computer interface settings (localStorage). Game rules live in the save, not here.
import { create } from 'zustand';
import type { Language } from '../utils/i18n';

export const UI_SCALES = [
  { value: 90, label: 'Small' },
  { value: 100, label: 'Normal' },
  { value: 110, label: 'Large' },
] as const;

interface SettingsState {
  language: Language;
  uiScale: number;
  setUiScale: (scale: number) => void;
  initSettings: () => void;
}

const STORAGE_KEY = 'hardwood_settings';
const LEGACY_STORAGE_KEY = 'nbasim_settings_v2';

/** Nearest offered size, so an old 120% setting becomes Large. */
const clampScale = (scale: unknown): number => {
  const n = typeof scale === 'number' && Number.isFinite(scale) ? scale : 100;
  return UI_SCALES.reduce<number>((best, s) => (Math.abs(s.value - n) < Math.abs(best - n) ? s.value : best), 100);
};

/** CSS zoom on the whole page; --ui-zoom lets full-screen sizes (100vh) divide it back out. */
const applyScale = (scale: number) => {
  const root = document.documentElement;
  root.style.setProperty('zoom', String(scale / 100));
  root.style.setProperty('--ui-zoom', String(scale / 100));
};

export const useSettingsStore = create<SettingsState>((set) => ({
  language: 'en',
  uiScale: 100,

  setUiScale: (scale: number) => {
    const value = clampScale(scale);
    set({ uiScale: value });
    applyScale(value);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ uiScale: value }));
    } catch {
      /* storage blocked: the size still applies for this session */
    }
  },

  initSettings: () => {
    let scale = 100;
    try {
      const saved = localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY);
      if (saved) scale = clampScale(JSON.parse(saved).uiScale);
    } catch {
      /* unreadable settings: defaults */
    }
    set({ language: 'en', uiScale: scale });
    applyScale(scale);
  },
}));
