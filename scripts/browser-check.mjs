// End-to-end browser check: drives the idea board through the same pinned
// @playwright/mcp server Kiro uses (see .kiro/settings/mcp.json), in headless
// Chrome. Adds two ideas, deletes one, reloads, and checks what is left.
//
// Needs: the dev server running (`npm run dev`) and Google Chrome
// (`bash scripts/setup-dev-tools.sh`). Run from the project root:
//   npm run test:browser
// Screenshots are written to docs/screenshots/. Exits non-zero on any failure.
import { startServer } from './mcp-client.mjs'

const URL = 'http://localhost:5173/absproxy/5173/'
const s = startServer(['--headless', '--browser', 'chrome', '--isolated'])
const results = []
let step = 0

function check(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}

async function snapshot() {
  const { text } = await s.call('browser_snapshot')
  return text
}

function escapeRe(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Snapshot lines look like `- button "Add" [ref=e9]`, or, when the name
// contains a colon, `- 'button "Delete idea: X" [ref=e20] ...': Delete`.
function refFor(snap, role, name) {
  const re = new RegExp(`- '?${role} "${escapeRe(name)}"[^\\n]*?\\[ref=([a-z0-9]+)\\]`)
  const m = snap.match(re)
  if (!m) throw new Error(`no ${role} "${name}" in snapshot`)
  return m[1]
}

// Each idea is `- listitem` followed by `- generic [ref=eN]: <idea text>`.
function listItems(snap) {
  const items = []
  const lines = snap.split('\n')
  for (let i = 0; i < lines.length; i++) {
    if (/- listitem\b/.test(lines[i])) {
      const t = lines[i + 1]?.match(/- generic \[ref=[a-z0-9]+\]: (.+)$/)
      if (t) items.push(t[1].trim())
    }
  }
  return items
}

async function shot(label) {
  step += 1
  const filename = `docs/screenshots/${String(step).padStart(2, '0')}-${label}.png`
  const r = await s.call('browser_take_screenshot', { filename, type: 'png' })
  if (r.isError) throw new Error(r.text)
  console.log(`      screenshot ${filename}`)
}

async function addIdea(text) {
  const snap = await snapshot()
  const box = refFor(snap, 'textbox', 'New idea')
  await s.call('browser_type', { element: 'New idea input', target: box, text })
  const add = refFor(await snapshot(), 'button', 'Add')
  await s.call('browser_click', { element: 'Add button', target: add })
}

try {
  await s.init()

  const nav = await s.call('browser_navigate', { url: URL })
  check('page opens', !nav.isError, URL)
  let snap = await snapshot()
  check('heading "Idea board" shown', /heading "Idea board"/.test(snap))
  check('empty state shown', snap.includes('No ideas yet. Add your first one above.'))
  await shot('loaded-empty')

  await addIdea('Try pottery')
  await shot('added-first')
  await addIdea('Learn chess')
  snap = await snapshot()
  let items = listItems(snap)
  check('two ideas, newest first', JSON.stringify(items) === JSON.stringify(['Learn chess', 'Try pottery']), JSON.stringify(items))
  await shot('added-second')

  const del = refFor(snap, 'button', 'Delete idea: Try pottery')
  await s.call('browser_click', { element: 'Delete button for "Try pottery"', target: del })
  snap = await snapshot()
  items = listItems(snap)
  check('deleted the right idea (Try pottery gone, Learn chess kept)', JSON.stringify(items) === JSON.stringify(['Learn chess']), JSON.stringify(items))
  await shot('deleted-older')

  await s.call('browser_navigate', { url: URL })
  // Wait for React to render the reloaded page before reading the list.
  await s.call('browser_wait_for', { text: 'Idea board' })
  await s.call('browser_wait_for', { time: 1 })
  snap = await snapshot()
  items = listItems(snap)
  check('after refresh, remaining idea is still there', JSON.stringify(items) === JSON.stringify(['Learn chess']), JSON.stringify(items))
  await shot('after-refresh')

  const errors = await s.call('browser_console_messages', { level: 'error' })
  const hasErrors = /\[error\]|Error:/i.test(errors.text)
  check('no console errors', !hasErrors, hasErrors ? errors.text.slice(0, 200) : '')
} catch (err) {
  check('flow completed', false, String(err.message ?? err))
} finally {
  await s.call('browser_close').catch(() => {})
  s.proc.kill()
  const failed = results.filter((r) => !r.ok).length
  console.log(`\n${results.length - failed}/${results.length} checks passed`)
  process.exit(failed === 0 ? 0 : 1)
}
