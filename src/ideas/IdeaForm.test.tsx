import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { IdeaForm } from './IdeaForm'
import { EMPTY_MESSAGE, TOO_LONG_MESSAGE } from './validate'

function setup() {
  const onAdd = vi.fn()
  const user = userEvent.setup()
  render(<IdeaForm onAdd={onAdd} />)
  const input = screen.getByLabelText('New idea')
  return { onAdd, user, input }
}

describe('IdeaForm', () => {
  it('adds the trimmed text when Add is clicked', async () => {
    const { onAdd, user, input } = setup()
    await user.type(input, '  Try pottery  ')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(onAdd).toHaveBeenCalledExactlyOnceWith('Try pottery')
  })

  it('adds the idea when Enter is pressed', async () => {
    const { onAdd, user, input } = setup()
    await user.type(input, 'Learn chess{Enter}')
    expect(onAdd).toHaveBeenCalledExactlyOnceWith('Learn chess')
  })

  it('clears the input and focuses it after a successful add', async () => {
    const { user, input } = setup()
    await user.type(input, 'Plant herbs')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(input).toHaveValue('')
    expect(input).toHaveFocus()
  })

  it('rejects empty input with a message announced as an alert', async () => {
    const { onAdd, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(onAdd).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(EMPTY_MESSAGE)
  })

  it('rejects whitespace-only input and keeps the typed text', async () => {
    const { onAdd, user, input } = setup()
    await user.type(input, '   ')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(onAdd).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(EMPTY_MESSAGE)
    expect(input).toHaveValue('   ')
  })

  it('accepts exactly 140 characters', async () => {
    const { onAdd, user, input } = setup()
    await user.click(input)
    await user.paste('x'.repeat(140))
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(onAdd).toHaveBeenCalledExactlyOnceWith('x'.repeat(140))
  })

  it('rejects 141 characters and keeps the typed text', async () => {
    const { onAdd, user, input } = setup()
    await user.click(input)
    await user.paste('x'.repeat(141))
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(onAdd).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(TOO_LONG_MESSAGE)
    expect(input).toHaveValue('x'.repeat(141))
  })

  it('hides the error after a later successful add', async () => {
    const { user, input } = setup()
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByRole('alert')).toBeInTheDocument()
    await user.type(input, 'Fine now')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
