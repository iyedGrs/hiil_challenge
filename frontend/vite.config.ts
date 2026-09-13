/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load frontend/.env* (not just process.env) so API_PROXY_TARGET set there is honored.
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        // Preserve the /api prefix — FastAPI includes it, the proxy must not strip it (local-dev L1).
        '/api': {
          target: env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: true,
    },
  }
})
