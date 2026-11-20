import type { BU } from '../api/types'

export interface SignedInUser {
  email: string
  bu: BU | null
}

/** Sign-in for the app. The real one uses Cognito through aws-amplify; the mock one is only for
 * local development and tests (VITE_USE_MOCKS=true) and never talks to AWS. */
export interface AuthService {
  signIn(email: string, password: string): Promise<SignedInUser>
  signOut(): Promise<void>
  currentUser(): Promise<SignedInUser | null>
  /** The ID token, or null when signed out or expired. */
  getIdToken(): Promise<string | null>
}

/** Same message for every failure, so it never reveals whether the email exists (R1.3). */
export const GENERIC_SIGN_IN_ERROR = 'Incorrect email or password.'

const BUS: BU[] = ['AWS', 'ServiceNow', 'Salesforce', 'Data & AI']
export const toBu = (value: unknown): BU | null => (BUS.includes(value as BU) ? (value as BU) : null)

