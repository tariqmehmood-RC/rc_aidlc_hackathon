import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, beforeAll, expect, it } from 'vitest'
import fixture from './mocks/fixtures/allstate.json'
import { mockBackend, renderApp } from './test/helpers'

const backend = mockBackend(1000)
beforeAll(() => backend.server.listen({ onUnhandledFrame: 'error' }))
afterAll(() => backend.server.close())

it('runs the whole demo flow against the mock API: sign in, paste, confirm, progress, brief, edit, approve, keep rule', async () => {
  const user = userEvent.setup()
  renderApp('/login')

  await user.type(await screen.findByLabelText('Email'), 'se-servicenow@demo.local')
  await user.type(screen.getByLabelText('Password'), 'password-123')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByTestId('bu-badge')).toHaveTextContent('ServiceNow')

  await user.click(screen.getByLabelText('Meeting invite'))
  await user.paste((fixture as { inviteText: string }).inviteText)
  await user.click(screen.getByRole('button', { name: 'Read invite' }))
  await screen.findByRole('list', { name: 'Progress' })

  act(() => backend.advance(1000))
  expect(await screen.findByLabelText('Company')).toHaveValue('Allstate')
  await user.click(screen.getByRole('button', { name: 'Start research' }))
  await screen.findByRole('list', { name: 'Progress' })

  act(() => backend.advance(10_000))
  expect(await screen.findByRole('heading', { name: 'Allstate' })).toBeInTheDocument()
  expect(screen.getAllByTestId('case-study')).toHaveLength(3)

  await user.click(screen.getByRole('button', { name: 'Edit question 3' }))
  const box = screen.getByRole('textbox', { name: 'question 3' })
  await user.clear(box)
  await user.type(box, 'What is your budget cycle for IT operations tooling?')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  await screen.findByText('What is your budget cycle for IT operations tooling?')

  await user.click(screen.getByRole('button', { name: 'Approve brief' }))
  await user.click(screen.getByRole('button', { name: 'Approve' }))
  act(() => backend.advance(1000))
  await screen.findByTestId('rule-proposal')
  await user.click(screen.getByRole('button', { name: 'Save choices' }))
  await waitFor(() => expect(screen.getByText(/Saved 1 rule/)).toBeInTheDocument())
}, 20_000)
