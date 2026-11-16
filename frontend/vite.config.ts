import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// The game version lives in core/version.py (single source for backend and frontend).
const versionPy = readFileSync(fileURLToPath(new URL('../core/version.py', import.meta.url)), 'utf-8')
const pyString = (name: string) => versionPy.match(new RegExp(`^${name} = "([^"]*)"`, 'm'))?.[1] ?? ''
const GAME_VERSION = pyString('VERSION')
const GAME_CHANNEL = pyString('CHANNEL')
if (!GAME_VERSION) throw new Error('core/version.py: VERSION not found')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __GAME_VERSION__: JSON.stringify(GAME_VERSION),
    __GAME_CHANNEL__: JSON.stringify(GAME_CHANNEL),
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})
