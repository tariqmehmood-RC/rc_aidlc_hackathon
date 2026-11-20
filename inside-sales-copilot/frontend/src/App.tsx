import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { Header } from './components/Header'
import { BriefPage } from './pages/BriefPage'
import { LoginPage } from './pages/LoginPage'
import { NewBriefPage } from './pages/NewBriefPage'

function Protected({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth()
  if (!ready) return <p className="p-8 text-muted" role="status">Loading…</p>
  if (!user) return <Navigate to="/login" replace />
  return (
    <>
      <Header />
      {children}
    </>
  )
}

export default function App({ mockMode = false, pollMs }: { mockMode?: boolean; pollMs?: number }) {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage mockMode={mockMode} />} />
      <Route path="/" element={<Protected><NewBriefPage /></Protected>} />
      <Route path="/briefs/:id" element={<Protected><BriefPage pollMs={pollMs} /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
