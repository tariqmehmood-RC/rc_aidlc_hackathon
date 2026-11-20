/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
