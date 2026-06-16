/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev (`npm run dev`) the frontend talks to the backend through a same-origin
// proxy. App endpoints are namespaced under `/api` (so they never shadow the
// client-side routes) and the `/api` prefix is stripped before forwarding. In
// Docker the same mapping is done by nginx (see frontend/nginx.conf).
const backend = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/health': backend,
      // Strips `/api` so `/api/documents` -> `/documents` on the backend.
      // `/api/chat` streams Server-Sent Events; http-proxy forwards the stream.
      '/api': {
        target: backend,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
})
