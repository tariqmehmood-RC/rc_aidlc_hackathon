import { setupWorker } from 'msw/browser'
import { MockDb } from './db'
import { createHandlers } from './handlers'

/** Mock API in the browser (VITE_USE_MOCKS=true). Step length from VITE_MOCK_STEP_MS. */
export async function startMockApi() {
  const stepMs = Number(import.meta.env.VITE_MOCK_STEP_MS ?? 2500)
  const db = new MockDb({ stepMs })
  const worker = setupWorker(...createHandlers(db))
  await worker.start({ onUnhandledFrame: 'bypass', quiet: true })
  return db
}
