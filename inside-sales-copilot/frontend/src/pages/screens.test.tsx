import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import fixture from '../mocks/fixtures/allstate.json'
import type { BriefView, ParsedInvite } from '../api/types'
import { stepStates, validateInvite } from '../lib/flow'
import { mockBackend, renderApp, signInAs } from '../test/helpers'

const backend = mockBackend(1000)
beforeAll(() => backend.server.listen({ onUnhandledFrame: 'error' }))
afterAll(() => backend.server.close())
beforeEach(() => sessionStorage.clear())
afterEach(() => {
  backend.server.resetHandlers()
  backend.db.briefs.clear()
  backend.db.rules.clear()
})

const INVITE = (fixture as { inviteText: string }).inviteText
const owner = 'mock-se-servicenow@demo.local'

/** Put a brief straight into a state, without clicking through the earlier screens. */
function briefAt(state: 'awaiting' | 'processing' | 'ready' | 'failed') {
  const id = backend.db.create(owner, 'ServiceNow', state === 'failed' ? 'Nonexistent Corp invite' : INVITE)
  const b = backend.db.briefs.get(id)!
  backend.advance(1000)
  backend.db.view(b) // -> awaiting_confirmation
  if (state === 'awaiting') return id
  backend.db.startPipeline(b, structuredClone(b.parsedInvite!))
  if (state === 'processing') {
    backend.advance(500 + 1000 + 100) // into "Checking attendees"
    return id
  }
  backend.advance(10_000)
  backend.db.view(b)
  return id
}

// --- sign in -------------------------------------------------------------------------------------
describe('sign in', () => {
  it('shows only the sign-in page when signed out, with no sign-up link', async () => {
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByText(/sign up/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('bu-badge')).not.toBeInTheDocument()
  })

  it('shows one generic message for a wrong email or a wrong password', async () => {
    const user = userEvent.setup()
    renderApp('/login')
    await user.type(await screen.findByLabelText('Email'), 'nobody@demo.local')
    await user.type(screen.getByLabelText('Password'), 'password-123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
    await user.clear(screen.getByLabelText('Email'))
    await user.type(screen.getByLabelText('Email'), 'se-aws@demo.local')
    await user.clear(screen.getByLabelText('Password'))
    await user.type(screen.getByLabelText('Password'), 'short')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
  })

  it('signs in, shows the BU from the token, and signs out', async () => {
    const user = userEvent.setup()
    renderApp('/login')
    await user.type(await screen.findByLabelText('Email'), 'se-aws@demo.local')
    await user.type(screen.getByLabelText('Password'), 'password-123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByTestId('bu-badge')).toHaveTextContent('BU: AWS')
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('has no BU selector anywhere', async () => {
    renderApp('/', await signInAs())
    await screen.findByRole('heading', { name: 'New discovery brief' })
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})

// --- paste invite ---------------------------------------------------------------------------------------
describe('paste invite', () => {
  it('blocks empty, whitespace-only, and too-long text', async () => {
    const user = userEvent.setup()
    renderApp('/', await signInAs())
    const button = await screen.findByRole('button', { name: 'Read invite' })
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Meeting invite'), '   ')
    expect(button).toBeDisabled()
    await user.clear(screen.getByLabelText('Meeting invite'))
    await user.click(screen.getByLabelText('Meeting invite'))
    await user.paste('x'.repeat(10_001))
    expect(button).toBeDisabled()
    expect(screen.getByTestId('char-count')).toHaveTextContent('10,001 / 10,000')
    expect(screen.getByText(/at most 10,000 characters/)).toBeInTheDocument()
  })

  it('sends the invite and moves to the progress view', async () => {
    const user = userEvent.setup()
    renderApp('/', await signInAs())
    await user.click(await screen.findByLabelText('Meeting invite'))
    await user.paste(INVITE)
    await user.click(screen.getByRole('button', { name: 'Read invite' }))
    expect(await screen.findByRole('list', { name: 'Progress' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(/Queued/)
    expect(backend.db.briefs.size).toBe(1)
  })
})

// --- parse preview -------------------------------------------------------------------------------------
describe('parse preview', () => {
  it('shows every parsed field as editable, next to the pasted text', async () => {
    const id = briefAt('awaiting')
    sessionStorage.setItem(`isc.invite.${id}`, INVITE)
    renderApp(`/briefs/${id}`, await signInAs())
    expect(await screen.findByLabelText('Company')).toHaveValue('Allstate')
    expect(screen.getByLabelText('Company domain')).toHaveValue('allstate.com')
    expect(screen.getByLabelText('Meeting date')).toHaveValue('2026-12-10')
    expect(screen.getByLabelText('Attendee 2 title')).toHaveValue('Chief Information Officer')
    expect(screen.getByText(/Rowan Achterberg, VP, IT Service Management/)).toBeInTheDocument()
  })

  it('blocks an invalid email and a missing company before sending anything', async () => {
    const user = userEvent.setup()
    renderApp(`/briefs/${briefAt('awaiting')}`, await signInAs())
    const email = await screen.findByLabelText('Attendee 1 email')
    await user.clear(email)
    await user.type(email, 'not-an-email')
    expect(screen.getByRole('list', { name: 'Problems to fix' })).toHaveTextContent('Attendee 1: the email address is not valid.')
    expect(screen.getByRole('button', { name: 'Start research' })).toBeDisabled()
    await user.clear(email)
    await user.type(email, 'rowan@allstate.com')
    await user.clear(screen.getByLabelText('Company'))
    await user.clear(screen.getByLabelText('Company domain'))
    expect(screen.getByRole('list', { name: 'Problems to fix' })).toHaveTextContent('Add a company name or a company email domain')
  })

  it('needs the company to be confirmed when the domain does not match', async () => {
    const user = userEvent.setup()
    const id = briefAt('awaiting')
    renderApp(`/briefs/${id}`, await signInAs())
    const domain = await screen.findByLabelText('Company domain')
    await user.clear(domain)
    await user.type(domain, 'globex.com')
    await user.click(screen.getByRole('button', { name: 'Start research' }))
    expect(await screen.findByText(/do not match/, { selector: 'p' })).toBeInTheDocument()
    expect(backend.db.briefs.get(id)!.phase).toBe('parse')
    await user.click(screen.getByLabelText('I confirm the company is correct'))
    await user.click(screen.getByRole('button', { name: 'Start research' }))
    await waitFor(() => expect(backend.db.briefs.get(id)!.phase).toBe('pipeline'))
  })

  it('validates at most 20 attendees', () => {
    const p = structuredClone(fixture.brief.parsedInvite) as ParsedInvite
    p.attendees = Array.from({ length: 21 }, (_, i) => ({ name: `P${i}`, title: null, email: `p${i}@allstate.com` }))
    expect(validateInvite(p)).toContain('An invite can list at most 20 attendees.')
    p.attendees = p.attendees.slice(0, 20)
    expect(validateInvite(p)).toEqual([])
  })
})

// --- progress -----------------------------------------------------------------------------------------------
describe('progress', () => {
  const base = { briefId: 'x', createdAt: 0, version: 0, rulesStatus: 'none' as const }

  it('marks steps done, current, and pending from the API state', () => {
    const v: BriefView = { ...base, status: 'processing', step: 'Matching case studies', confirmedInvite: {} as ParsedInvite }
    expect(stepStates(v)).toEqual({ Parsing: 'done', Researching: 'done', 'Checking attendees': 'done', 'Matching case studies': 'current', 'Writing brief': 'pending' })
    expect(stepStates({ ...base, status: 'queued' }).Parsing).toBe('pending')
    expect(stepStates({ ...base, status: 'queued', confirmedInvite: {} as ParsedInvite }).Parsing).toBe('done')
    const failed: BriefView = { ...base, status: 'failed', error: { code: 'X', step: 'Researching', message: 'm' }, confirmedInvite: {} as ParsedInvite }
    expect(stepStates(failed).Researching).toBe('failed')
  })

  it('shows the 5 steps live and opens the brief when it is ready', async () => {
    const id = briefAt('processing')
    renderApp(`/briefs/${id}`, await signInAs())
    const list = await screen.findByRole('list', { name: 'Progress' })
    const items = within(list).getAllByRole('listitem')
    expect(items.map((li) => li.dataset.state)).toEqual(['done', 'done', 'current', 'pending', 'pending'])
    expect(items).toHaveLength(5)
    act(() => backend.advance(1000))
    await waitFor(() => expect(within(screen.getByRole('list', { name: 'Progress' })).getAllByRole('listitem')[3].dataset.state).toBe('current'))
    act(() => backend.advance(5000))
    expect(await screen.findByRole('heading', { name: 'Allstate' })).toBeInTheDocument()
  })

  it('shows a failed step with the message and a working Retry', async () => {
    const user = userEvent.setup()
    const id = briefAt('failed')
    renderApp(`/briefs/${id}`, await signInAs())
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Stopped at Researching: No public information was found for this company.')
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(backend.db.briefs.get(id)!.error).toBeUndefined())
  })

  it('shows not found for another user\u2019s brief', async () => {
    const id = backend.db.create('mock-someone-else', 'AWS', INVITE)
    renderApp(`/briefs/${id}`, await signInAs())
    expect(await screen.findByRole('alert')).toHaveTextContent('This brief was not found.')
  })
})
