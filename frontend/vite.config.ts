/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev (`npm run dev`) the frontend talks to the backend through a same-origin
// proxy, so the app code can simply fetch backend paths directly. In Docker the
// same paths are proxied by nginx (see frontend/nginx.conf).
const backend = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/health': backend,
      '/api': backend,
      '/documents': backend,
      '/chunks': backend,
      // `/chat` streams Server-Sent Events; http-proxy forwards the stream.
      '/chat': backend,
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
})
