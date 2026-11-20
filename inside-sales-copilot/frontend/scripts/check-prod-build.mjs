// Fails if a production build could start the mock API (task 5.5: MSW must be off in production).
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const dist = resolve(import.meta.dirname, '..', 'dist')
const problems = []
if (!existsSync(join(dist, 'index.html'))) problems.push('dist/index.html is missing (run the build first)')
if (existsSync(join(dist, 'mockServiceWorker.js'))) problems.push('dist/mockServiceWorker.js must not be shipped')

const walk = (dir) => readdirSync(dir).flatMap((f) => (statSync(join(dir, f)).isDirectory() ? walk(join(dir, f)) : [join(dir, f)]))
const markers = ['setupWorker', 'mockServiceWorker', 'MockDb', 'createMockAuth', 'demo.local']
for (const file of walk(dist).filter((f) => f.endsWith('.js'))) {
  const text = readFileSync(file, 'utf-8')
  for (const m of markers) if (text.includes(m)) problems.push(`${file.slice(dist.length + 1)} contains "${m}"`)
}

if (problems.length) {
  console.error('Production build check FAILED:\n- ' + problems.join('\n- '))
  process.exit(1)
}
console.log('Production build check passed: no mock API, no mock sign-in, no mock service worker.')
