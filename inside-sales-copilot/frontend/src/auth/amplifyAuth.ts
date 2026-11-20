// Cognito sign-in through aws-amplify (R1). Loaded only when the app is not in mock mode.
import { Amplify } from 'aws-amplify'
import { fetchAuthSession, signIn, signOut } from 'aws-amplify/auth'
import { GENERIC_SIGN_IN_ERROR, toBu, type AuthService, type SignedInUser } from './auth'

export interface CognitoConfig {
  region: string
  userPoolId: string
  userPoolClientId: string
}

export function createAmplifyAuth(config: CognitoConfig): AuthService {
  Amplify.configure({ Auth: { Cognito: { userPoolId: config.userPoolId, userPoolClientId: config.userPoolClientId } } })

  async function idToken() {
    try {
      const session = await fetchAuthSession()
      return session.tokens?.idToken ?? null
    } catch {
      return null
    }
  }

  async function current(): Promise<SignedInUser | null> {
    const token = await idToken()
    if (!token) return null
    const payload = token.payload as Record<string, unknown>
    return { email: String(payload.email ?? ''), bu: toBu(payload['custom:bu']) }
  }

  return {
    async signIn(email, password) {
      try {
        const result = await signIn({ username: email.trim(), password })
        if (!result.isSignedIn) throw new Error('not signed in')
      } catch {
        throw new Error(GENERIC_SIGN_IN_ERROR) // never say which part was wrong
      }
      const user = await current()
      if (!user) throw new Error(GENERIC_SIGN_IN_ERROR)
      return user
    },
    async signOut() {
      await signOut()
    },
    currentUser: current,
    async getIdToken() {
      const token = await idToken()
      return token ? token.toString() : null
    },
  }
}
