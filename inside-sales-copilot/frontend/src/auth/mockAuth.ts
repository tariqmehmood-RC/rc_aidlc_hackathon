import type { BU } from '../api/types'
import { GENERIC_SIGN_IN_ERROR, toBu, type AuthService } from './auth'

// Mock sign-in for local development and tests only (VITE_USE_MOCKS=true). It is loaded with a
// dynamic import, so a production build does not contain it.
export const MOCK_USERS: Record<string, BU> = {
  'se-aws@demo.local': 'AWS',
  'se-servicenow@demo.local': 'ServiceNow',
}
const MOCK_STORAGE_KEY = 'isc.mock.session'

/** A readable fake token. The mock API decodes it; it is not a real JWT and has no signature. */
export function makeMockToken(email: string, bu: BU, expiresAt: number): string {
  const payload = { sub: `mock-${email}`, email, 'custom:bu': bu, exp: expiresAt }
  return 'mock.' + btoa(JSON.stringify(payload))
}

export function readMockToken(token: string | null): { sub: string; email: string; 'custom:bu': BU; exp: number } | null {
  if (!token || !token.startsWith('mock.')) return null
  try {
    const payload = JSON.parse(atob(token.slice(5)))
    return payload.exp > Date.now() ? payload : null
  } catch {
    return null
  }
}

export function createMockAuth(storage: Storage = sessionStorage, ttlMs = 60 * 60 * 1000): AuthService {
  return {
    async signIn(email, password) {
      const key = email.trim().toLowerCase()
      const bu = MOCK_USERS[key]
      if (!bu || password.length < 8) throw new Error(GENERIC_SIGN_IN_ERROR)
      storage.setItem(MOCK_STORAGE_KEY, makeMockToken(key, bu, Date.now() + ttlMs))
      return { email: key, bu }
    },
    async signOut() {
      storage.removeItem(MOCK_STORAGE_KEY)
    },
    async currentUser() {
      const payload = readMockToken(storage.getItem(MOCK_STORAGE_KEY))
      return payload ? { email: payload.email, bu: toBu(payload['custom:bu']) } : null
    },
    async getIdToken() {
      const token = storage.getItem(MOCK_STORAGE_KEY)
      return readMockToken(token) ? token : null
    },
  }
}

export const MOCK_LOGIN_HINT = 'Mock mode: se-servicenow@demo.local or se-aws@demo.local with any password of 8+ characters.'
