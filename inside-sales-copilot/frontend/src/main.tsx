import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { createMockAuth, type AuthService } from './auth/auth'
import { AuthProvider } from './auth/AuthContext'

const mockMode = import.meta.env.VITE_USE_MOCKS === 'true'

async function boot() {
  let auth: AuthService
  if (mockMode) {
    const { startMockApi } = await import('./mocks/browser')
    await startMockApi()
    auth = createMockAuth()
  } else {
    // config.json is written by the CDK web stack: pool id, client id, region. None are secrets.
    const config = await fetch('/config.json').then((r) => r.json())
    const { createAmplifyAuth } = await import('./auth/amplifyAuth')
    auth = createAmplifyAuth(config)
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || undefined}>
        <AuthProvider auth={auth}>
          <App mockMode={mockMode} />
        </AuthProvider>
      </BrowserRouter>
    </StrictMode>,
  )
}

void boot()
