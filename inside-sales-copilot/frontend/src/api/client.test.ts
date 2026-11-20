import { describe, expect, it, vi } from 'vitest'
import { ApiError, createApiClient } from './client'

const json = (status: number, body: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('api client', () => {
  it('sends the ID token as a bearer token and JSON bodies', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json(202, { briefId: 'b', status: 'queued' }))
    const api = createApiClient({ getToken: async () => 'tok-123', fetchImpl, baseUrl: 'https://x/api' })
    await api.createBrief('hello')
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('https://x/api/briefs')
    expect(init.method).toBe('POST')
    expect(init.headers.Authorization).toBe('Bearer tok-123')
    expect(JSON.parse(init.body)).toEqual({ inviteText: 'hello' })
  })

  it('sends no Authorization header when signed out', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json(200, { items: [], nextCursor: null }))
    await createApiClient({ getToken: async () => null, fetchImpl }).listBriefs()
    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBeUndefined()
  })

  it('calls onUnauthorized on 401 and throws', async () => {
    const onUnauthorized = vi.fn()
    const api = createApiClient({ getToken: async () => 't', onUnauthorized, fetchImpl: vi.fn().mockResolvedValue(json(401, {})) })
    await expect(api.getBrief('a')).rejects.toMatchObject({ status: 401, code: 'UNAUTHORIZED' })
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('turns the error body into a typed ApiError with details', async () => {
    const body = { error: { code: 'COMPANY_REQUIRED', message: 'Add a company.', details: [{ code: 'COMPANY_REQUIRED', message: 'Add a company.' }] } }
    const api = createApiClient({ getToken: async () => 't', fetchImpl: vi.fn().mockResolvedValue(json(400, body)) })
    const err = await api.confirm('a', {} as never, false).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 400, code: 'COMPANY_REQUIRED', message: 'Add a company.' })
    expect(err.details).toHaveLength(1)
  })

  it('reports a network failure without leaking details', async () => {
    const api = createApiClient({ getToken: async () => 't', fetchImpl: vi.fn().mockRejectedValue(new TypeError('boom at 10.0.0.1')) })
    await expect(api.getBrief('a')).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  })

  it('encodes ids in the path', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json(200, {}))
    await createApiClient({ getToken: async () => 't', fetchImpl, baseUrl: '' }).getBrief('../x')
    expect(fetchImpl.mock.calls[0][0]).toBe('/briefs/..%2Fx')
  })

  it('handles 204 with no body', async () => {
    const api = createApiClient({ getToken: async () => 't', fetchImpl: vi.fn().mockResolvedValue(new Response(null, { status: 204 })) })
    await expect(api.deleteRule('r')).resolves.toBeUndefined()
  })
})
