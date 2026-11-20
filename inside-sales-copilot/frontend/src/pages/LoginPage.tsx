import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { GENERIC_SIGN_IN_ERROR } from '../auth/auth'
import { Button, Card } from '../components/ui'

export function LoginPage({ hint }: { hint?: string }) {
  const { user, signIn, expired } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signIn(email, password)
    } catch {
      setError(GENERIC_SIGN_IN_ERROR)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-navy via-navy-soft to-brand-dark">
      <div className="mx-auto flex min-h-screen max-w-5xl items-center gap-16 px-8">
        <div className="hidden flex-1 text-white md:block">
          <div className="mb-6 grid h-12 w-12 place-items-center rounded-xl bg-brand text-xl font-bold">IS</div>
          <h1 className="text-4xl font-bold leading-tight">Inside Sales Copilot</h1>
          <p className="mt-4 max-w-md text-lg text-blue-100">
            Paste a meeting invite. Get a cited discovery brief, an agenda, and the Royal Cyber case studies that fit, in about a minute.
          </p>
          <ul className="mt-8 space-y-2 text-sm text-blue-100">
            <li>✓ Every fact links to its source</li>
            <li>✓ Discovery questions and agenda ready to edit</li>
            <li>✓ Case studies from your business unit</li>
          </ul>
        </div>
        <Card className="w-full max-w-sm p-8">
          <h2 className="text-xl font-bold">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use your Royal Cyber presales account.</p>
          {expired && <p className="mt-4 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">Your session ended. Please sign in again.</p>}
          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            <label className="block text-sm font-medium">
              Email
              <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required
                     className="mt-1 w-full rounded-lg border border-line px-3 py-2 outline-none focus:border-brand" />
            </label>
            <label className="block text-sm font-medium">
              Password
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required
                     className="mt-1 w-full rounded-lg border border-line px-3 py-2 outline-none focus:border-brand" />
            </label>
            {error && <p role="alert" className="text-sm text-bad">{error}</p>}
            <Button type="submit" className="w-full" disabled={busy || !email || !password}>{busy ? 'Signing in…' : 'Sign in'}</Button>
          </form>
          <p className="mt-6 text-xs text-muted">Accounts are created by an administrator. There is no self sign-up.</p>
          {hint && <p className="mt-3 rounded-md bg-page px-3 py-2 text-xs text-muted">{hint}</p>}
        </Card>
      </div>
    </div>
  )
}
