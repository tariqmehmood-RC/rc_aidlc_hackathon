import { render } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { createMockAuth } from '../auth/mockAuth'
import { AuthProvider } from '../auth/AuthContext'
import { MockDb } from '../mocks/db'
import { createHandlers } from '../mocks/handlers'

export const API = 'http://localhost/api'

/** A mock backend with a hand-driven clock, so tests decide when each step finishes. */
export function mockBackend(stepMs = 1000) {
  const clock = { t: 1_790_000_000_000 }
  const db = new MockDb({ stepMs, now: () => clock.t })
  const server = setupServer(...createHandlers(db, API))
  return {
    db,
    server,
    clock,
    advance: (ms: number) => {
      clock.t += ms
    },
  }
}

export async function signInAs(email = 'se-servicenow@demo.local') {
  const auth = createMockAuth(sessionStorage)
  await auth.signIn(email, 'password-123')
  return auth
}

export function renderApp(path: string, auth = createMockAuth(sessionStorage)) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider auth={auth} apiBase={API}>
        <App pollMs={15} />
      </AuthProvider>
    </MemoryRouter>,
  )
}
