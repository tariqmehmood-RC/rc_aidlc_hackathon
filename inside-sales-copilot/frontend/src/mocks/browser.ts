import { setupWorker } from 'msw/browser'
import { MockDb } from './db'
import { createHandlers } from './handlers'

/** Mock API in the browser (VITE_USE_MOCKS=true). Step length from VITE_MOCK_STEP_MS. */
export async function startMockApi() {
  const stepMs = Number(import.meta.env.VITE_MOCK_STEP_MS ?? 2500)
  const db = new MockDb({ stepMs })
  const worker = setupWorker(...createHandlers(db))
  // BASE_URL is "/" normally, or the proxy path (for example "/absproxy/5174/") in the workshop.
  await worker.start({
    onUnhandledFrame: 'bypass',
    quiet: true,
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
  })
  return db
}
