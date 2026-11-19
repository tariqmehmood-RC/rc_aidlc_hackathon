import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Dev only. The IDE's code-server route /absproxy/<port>/ keeps the path
  // prefix, so Vite must serve and emit asset URLs under it. Production
  // builds keep the default base.
  base: command === 'serve' ? '/absproxy/5173/' : '/',
  server: {
    // Leading dot allows cloudfront.net and all its subdomains, so the IDE's
    // hostname can change. Do not use `true`: it disables the host check.
    allowedHosts: ['.cloudfront.net'],
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
}))
