import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { createApiClient, type ApiClient } from '../api/client'
import type { AuthService, SignedInUser } from './auth'

interface AuthState {
  user: SignedInUser | null
  ready: boolean
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  api: ApiClient
  /** Set when the session expired during use, to explain why the user is back at sign-in. */
  expired: boolean
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ auth, children, apiBase = '/api' }: { auth: AuthService; children: ReactNode; apiBase?: string }) {
  const [user, setUser] = useState<SignedInUser | null>(null)
  const [ready, setReady] = useState(false)
  const [expired, setExpired] = useState(false)

  useEffect(() => {
    let alive = true
    auth.currentUser().then((u) => {
      if (alive) {
        setUser(u)
        setReady(true)
      }
    })
    return () => {
      alive = false
    }
  }, [auth])

  const signOut = useCallback(async () => {
    await auth.signOut()
    setUser(null)
  }, [auth])

  const api = useMemo(
    () =>
      createApiClient({
        baseUrl: apiBase,
        getToken: () => auth.getIdToken(),
        onUnauthorized: () => {
          setExpired(true)
          void auth.signOut()
          setUser(null)
        },
      }),
    [auth, apiBase],
  )

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      expired,
      api,
      signOut,
      signIn: async (email, password) => {
        const u = await auth.signIn(email, password)
        setExpired(false)
        setUser(u)
      },
    }),
    [user, ready, expired, api, signOut, auth],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const value = useContext(Ctx)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
