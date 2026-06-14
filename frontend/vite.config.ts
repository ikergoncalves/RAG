/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev (`npm run dev`) the frontend talks to the backend through a same-origin
// proxy, so the app code can simply fetch `/health` and `/api/*`. In Docker the
// same paths are proxied by nginx (see frontend/nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/health': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
})
