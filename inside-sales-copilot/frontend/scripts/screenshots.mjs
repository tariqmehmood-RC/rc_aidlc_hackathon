// Screenshots of each screen against the mock API (task 4.10 gate).
//   1. npm run dev:mock          (serves http://127.0.0.1:5174 with MSW)
//   2. node scripts/screenshots.mjs
// Uses the installed Google Chrome through playwright-core, so no browser download is needed.
import { mkdir, readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..', '..')
const out = resolve(root, 'docs', 'screenshots')
const base = process.env.APP_URL ?? 'http://127.0.0.1:5174'
const chrome = process.env.CHROME_PATH ?? '/usr/bin/google-chrome'

await mkdir(out, { recursive: true })
const invite = await readFile(resolve(root, 'data', 'sample_invites', '04-allstate.txt'), 'utf-8')

const browser = await chromium.launch({ executablePath: chrome, headless: true, args: ['--no-sandbox', '--disable-gpu'] })
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
const shot = async (name, opts = {}) => {
  await page.waitForTimeout(300)
  await page.screenshot({ path: resolve(out, `${name}.png`), ...opts })
  console.log(`saved docs/screenshots/${name}.png`)
}

// 1. login
await page.goto(`${base}/login`)
await page.getByRole('heading', { name: 'Sign in' }).waitFor()
await page.getByLabel('Email').fill('se-servicenow@demo.local')
await page.getByLabel('Password').fill('demo-password')
await shot('01-login')
await page.getByRole('button', { name: 'Sign in' }).click()

// 2. paste invite
await page.getByRole('heading', { name: 'New discovery brief' }).waitFor()
await page.getByLabel('Meeting invite').fill(invite)
await shot('02-paste-invite')
await page.getByRole('button', { name: 'Read invite' }).click()

// 3. parse preview
await page.getByRole('heading', { name: 'Check what we read' }).waitFor({ timeout: 20_000 })
await shot('03-parse-preview')
await page.getByRole('button', { name: 'Start research' }).click()

// 4. progress, captured while case studies are being matched
await page.locator('li[data-state="current"]', { hasText: 'Matching case studies' }).waitFor({ timeout: 30_000 })
await shot('04-progress')

// 5. brief
await page.getByRole('heading', { name: 'Allstate', level: 1, exact: true }).waitFor({ timeout: 30_000 })
await page.getByTestId('size-tier').waitFor()
await shot('05-brief')
await shot('05-brief-full-page', { fullPage: true })
await page.locator('#attendees').scrollIntoViewIfNeeded()
await shot('05b-brief-attendees')
await page.locator('#cases').scrollIntoViewIfNeeded()
await shot('05c-brief-case-studies')

// 6. edit one line, then approve
await page.getByRole('button', { name: 'Edit question 2' }).click()
await page.getByRole('textbox', { name: 'question 2' }).fill('What is your budget cycle, and when are funds for IT operations tooling decided?')
await shot('06-edit-question')
await page.getByRole('button', { name: 'Save' }).click()
await page.getByText('What is your budget cycle, and when are funds for IT operations tooling decided?').waitFor()
await page.getByRole('button', { name: 'Approve brief' }).click()
await page.getByRole('dialog').waitFor()
await shot('07-approve-dialog')
await page.getByRole('dialog').getByRole('button', { name: 'Approve' }).click()

// 7. rules review
await page.getByTestId('rule-proposal').waitFor({ timeout: 20_000 })
await page.evaluate(() => window.scrollTo(0, 0))
await shot('08-rules-review')

await browser.close()
