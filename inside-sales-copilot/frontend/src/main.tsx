import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import type { AuthService } from './auth/auth'
import { AuthProvider } from './auth/AuthContext'

const mockMode = import.meta.env.VITE_USE_MOCKS === 'true'

async function boot() {
  let auth: AuthService
  let loginHint: string | undefined
  if (mockMode) {
    const { startMockApi } = await import('./mocks/browser')
    await startMockApi()
    const { createMockAuth, MOCK_LOGIN_HINT } = await import('./auth/mockAuth')
    auth = createMockAuth()
    loginHint = MOCK_LOGIN_HINT
  } else {
    // config.json is written by the CDK web stack: pool id, client id, region. None are secrets.
    const config = await fetch(`${import.meta.env.BASE_URL}config.json`, { cache: 'no-store' }).then((r) => r.json())
    const { createAmplifyAuth } = await import('./auth/amplifyAuth')
    auth = createAmplifyAuth(config)
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || undefined}>
        <AuthProvider auth={auth}>
          <App loginHint={loginHint} />
        </AuthProvider>
      </BrowserRouter>
    </StrictMode>,
  )
}

void boot()
