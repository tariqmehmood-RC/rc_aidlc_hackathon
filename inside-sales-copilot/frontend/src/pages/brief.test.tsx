import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import fixture from '../mocks/fixtures/allstate.json'
import { mockBackend, renderApp, signInAs } from '../test/helpers'

const backend = mockBackend(1000)
beforeAll(() => backend.server.listen({ onUnhandledFrame: 'error' }))
afterAll(() => backend.server.close())
beforeEach(() => sessionStorage.clear())
afterEach(() => {
  backend.db.briefs.clear()
  backend.db.rules.clear()
})

const owner = 'mock-se-servicenow@demo.local'
function readyBrief() {
  const id = backend.db.create(owner, 'ServiceNow', (fixture as { inviteText: string }).inviteText)
  const b = backend.db.briefs.get(id)!
  backend.advance(1000)
  backend.db.view(b)
  backend.db.startPipeline(b, structuredClone(b.parsedInvite!))
  backend.advance(10_000)
  backend.db.view(b)
  return id
}

async function openBrief() {
  const id = readyBrief()
  renderApp(`/briefs/${id}`, await signInAs())
  await screen.findByRole('heading', { name: 'Allstate' })
  return id
}

describe('brief view', () => {
  it('shows the seven sections in order', async () => {
    await openBrief()
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings.slice(0, 7)).toEqual(['1. Company snapshot', '2. Attendees', '3. Pain-point hypotheses', '4. Agenda (30 min)',
      '5. Discovery questions', '6. Case studies to mention', '7. Sources'])
  })

  it('shows the size tier with its rule and a source link', async () => {
    await openBrief()
    const tier = screen.getByTestId('size-tier')
    expect(tier).toHaveTextContent('Size tier: Enterprise')
    expect(tier).toHaveTextContent('Rule used: 55,000 employees is more than 5,000')
    expect(within(tier).getByRole('link')).toHaveAttribute('href', 'https://en.wikipedia.org/wiki/Allstate')
  })

  it('gives every snapshot fact and hypothesis a source link that opens safely', async () => {
    await openBrief()
    const snapshot = document.getElementById('snapshot')!
    const facts = fixture.brief.content.companySnapshot.filter((i) => i.sourceUrls.length)
    const links = within(snapshot).getAllByRole('link')
    expect(links.length).toBeGreaterThanOrEqual(facts.length)
    for (const a of links) {
      expect(a).toHaveAttribute('target', '_blank')
      expect(a).toHaveAttribute('rel', 'noopener noreferrer')
      expect(a.textContent).not.toMatch(/news\.google\.com|https?:/) // chips show names, not raw URLs
    }
    const pain = document.getElementById('pain')!
    expect(within(pain).getAllByRole('link').length).toBeGreaterThan(0)
  })

  it('flags unverified attendees in amber with the reason', async () => {
    await openBrief()
    const rows = screen.getAllByTestId('attendee')
    expect(rows[0]).toHaveTextContent('Rowan Achterberg')
    expect(rows[0]).toHaveTextContent('✓ Verified')
    expect(rows[1]).toHaveTextContent('⚠ Unverified · Title does not match')
    expect(rows[1]).toHaveTextContent('Invite says: “Chief Information Officer”')
    expect(rows[2]).toHaveTextContent('⚠ Unverified · No profile found')
  })

  it('shows each case study with score, reason, and link', async () => {
    await openBrief()
    const cards = screen.getAllByTestId('case-study')
    expect(cards).toHaveLength(3)
    expect(cards[0]).toHaveTextContent('Accelerating IT Issue Resolution with ServiceNow ITOM')
    expect(cards[0]).toHaveTextContent('95')
    expect(cards[0]).toHaveTextContent('Why:')
    expect(within(cards[0]).getByRole('link', { name: 'Open case study ↗' })).toHaveAttribute('href', expect.stringMatching(/^https:\/\/(www\.)?royalcyber\.com\//))
  })

  it('edits one question in place and saves it with the version', async () => {
    const user = userEvent.setup()
    const id = await openBrief()
    await user.click(screen.getByRole('button', { name: 'Edit question 2' }))
    const box = screen.getByRole('textbox', { name: 'question 2' })
    await user.clear(box)
    await user.type(box, 'What is your budget cycle, and when are IT funds decided?')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('What is your budget cycle, and when are IT funds decided?')).toBeInTheDocument()
    const stored = backend.db.briefs.get(id)!
    expect(stored.version).toBe(1)
    expect(stored.draft!.discoveryQuestions[1].text).not.toMatch(/budget cycle, and when/) // the draft is unchanged
  })

  it('shows a save error from the server inline', async () => {
    const user = userEvent.setup()
    const id = await openBrief()
    backend.db.briefs.get(id)!.version = 7 // someone else saved in between
    await user.click(screen.getByRole('button', { name: 'Edit question 1' }))
    await user.type(screen.getByRole('textbox', { name: 'question 1' }), ' more')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The brief changed since you opened it')
  })
})

describe('approve and rules review', () => {
  it('approves, locks the brief, and lets the SE keep a suggested rule', async () => {
    const user = userEvent.setup()
    const id = await openBrief()
    await user.click(screen.getByRole('button', { name: 'Edit question 2' }))
    const box = screen.getByRole('textbox', { name: 'question 2' })
    await user.clear(box)
    await user.type(box, 'What is your budget cycle?')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText('What is your budget cycle?')

    await user.click(screen.getByRole('button', { name: 'Approve brief' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('You changed the draft')
    await user.click(within(dialog).getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('Checking your edits for reusable rules…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve brief' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit question 1' })).toBeDisabled() // locked

    act(() => backend.advance(1000))
    const proposal = await screen.findByTestId('rule-proposal')
    expect(proposal).toHaveTextContent('“Always ask about the budget cycle.”')
    await user.click(screen.getByRole('button', { name: 'Save choices' }))
    expect(await screen.findByText(/Saved 1 rule/)).toBeInTheDocument()
    expect(backend.db.rules.get(owner)?.map((r) => r.text)).toEqual(['Always ask about the budget cycle.'])
    expect(backend.db.briefs.get(id)!.approved).toBe(true)
  })

  it('discarding saves nothing, and no edits means no suggestions', async () => {
    const user = userEvent.setup()
    await openBrief()
    await user.click(screen.getByRole('button', { name: 'Approve brief' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('You did not change the draft')
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve' }))
    act(() => backend.advance(1000))
    expect(await screen.findByText(/No rules suggested/)).toBeInTheDocument()
    expect(backend.db.rules.get(owner)).toBeUndefined()
  })

  it('cancel keeps the brief editable', async () => {
    const user = userEvent.setup()
    await openBrief()
    await user.click(screen.getByRole('button', { name: 'Approve brief' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Approve brief' })).toBeEnabled()
  })
})
