import type { ApiErrorBody, BriefContent, BriefSummary, BriefView, ParsedInvite } from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Array<{ code: string; message: string }>

  constructor(status: number, code: string, message: string, details: Array<{ code: string; message: string }> = []) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export interface ClientOptions {
  /** The Cognito ID token (it carries custom:bu). Null when signed out. */
  getToken: () => Promise<string | null>
  /** Called on any 401, so the app can return to sign-in. */
  onUnauthorized?: () => void
  baseUrl?: string
  fetchImpl?: typeof fetch
}

export type ApiClient = ReturnType<typeof createApiClient>

export function createApiClient({ getToken, onUnauthorized, baseUrl = '/api', fetchImpl }: ClientOptions) {
  const doFetch = fetchImpl ?? ((input: RequestInfo | URL, init?: RequestInit) => fetch(input, init))

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = await getToken()
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    let res: Response
    try {
      res = await doFetch(`${baseUrl}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
    } catch {
      throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the server. Check your connection and try again.')
    }
    if (res.status === 401) {
      onUnauthorized?.()
      throw new ApiError(401, 'UNAUTHORIZED', 'Your session has ended. Please sign in again.')
    }
    if (res.status === 204) return undefined as T
    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      data = null
    }
    if (!res.ok) {
      const err = (data as ApiErrorBody | null)?.error
      throw new ApiError(res.status, err?.code ?? 'HTTP_' + res.status, err?.message ?? 'Something went wrong. Please try again.', err?.details ?? [])
    }
    return data as T
  }

  return {
    createBrief: (inviteText: string) => request<{ briefId: string; status: string }>('POST', '/briefs', { inviteText }),
    getBrief: (id: string) => request<BriefView>('GET', `/briefs/${encodeURIComponent(id)}`),
    listBriefs: (cursor?: string) =>
      request<{ items: BriefSummary[]; nextCursor: string | null }>('GET', `/briefs${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`),
    saveParsedInvite: (id: string, parsedInvite: ParsedInvite) =>
      request<BriefView>('PUT', `/briefs/${encodeURIComponent(id)}`, { parsedInvite }),
    saveContent: (id: string, content: BriefContent, version: number) =>
      request<BriefView>('PUT', `/briefs/${encodeURIComponent(id)}`, { content, version }),
    confirm: (id: string, parsedInvite: ParsedInvite, companyConfirmed: boolean) =>
      request<{ status: string }>('POST', `/briefs/${encodeURIComponent(id)}/confirm`, { parsedInvite, companyConfirmed }),
    approve: (id: string) => request<{ status: string; rulesStatus: string }>('POST', `/briefs/${encodeURIComponent(id)}/approve`),
    retry: (id: string) => request<{ status: string }>('POST', `/briefs/${encodeURIComponent(id)}/retry`),
    decideRules: (id: string, decisions: Array<{ proposalId: string; keep: boolean }>) =>
      request<{ saved: string[] }>('POST', `/briefs/${encodeURIComponent(id)}/rules`, { decisions }),
    listRules: () => request<{ items: Array<{ ruleId: string; text: string; createdAt: number }> }>('GET', '/rules'),
    deleteRule: (ruleId: string) => request<void>('DELETE', `/rules/${encodeURIComponent(ruleId)}`),
  }
}
