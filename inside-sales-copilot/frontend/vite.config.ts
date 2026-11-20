/// <reference types="vitest/config" />
import { rmSync } from 'node:fs'
import { resolve } from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const mockMode = process.env.VITE_USE_MOCKS === 'true'

/** The MSW service worker lives in public/ for development. A production build must not ship it. */
function dropMockWorker(): Plugin {
  return {
    name: 'drop-mock-service-worker',
    apply: 'build',
    closeBundle() {
      if (!mockMode) rmSync(resolve(__dirname, 'dist', 'mockServiceWorker.js'), { force: true })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), dropMockWorker()],
  // Dev server only: the workshop opens forwarded ports through this CloudFront host.
  // Vite blocks unknown Host headers (DNS rebinding protection), so allow exactly this one.
  server: {
    allowedHosts: ['d3bmkqtnxkhne9.cloudfront.net'],
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
