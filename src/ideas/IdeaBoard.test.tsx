import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { IdeaBoard } from './IdeaBoard'
import { STORAGE_KEY } from './storage'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function addIdea(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByLabelText('New idea'), text)
  await user.click(screen.getByRole('button', { name: 'Add' }))
}

function itemTexts() {
  const list = screen.queryByRole('list')
  if (list === null) return []
  return within(list)
    .getAllByRole('listitem')
    .map((item) => item.querySelector('.idea-text')?.textContent)
}

describe('IdeaBoard', () => {
  it('shows the empty state at first', () => {
    render(<IdeaBoard />)
    expect(screen.getByText('No ideas yet. Add your first one above.')).toBeInTheDocument()
  })

  it('adds an idea to the top of the list and clears the input', async () => {
    const user = userEvent.setup()
    render(<IdeaBoard />)
    await addIdea(user, 'Try pottery')
    await addIdea(user, 'Learn chess')
    expect(itemTexts()).toEqual(['Learn chess', 'Try pottery'])
    expect(screen.getByLabelText('New idea')).toHaveValue('')
  })

  it('does not add rejected input', async () => {
    const user = userEvent.setup()
    render(<IdeaBoard />)
    await addIdea(user, '   ')
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(itemTexts()).toEqual([])
  })

  it('deletes the older idea and keeps the newer one', async () => {
    const user = userEvent.setup()
    render(<IdeaBoard />)
    await addIdea(user, 'Older')
    await addIdea(user, 'Newer')
    await user.click(screen.getByRole('button', { name: 'Delete idea: Older' }))
    expect(itemTexts()).toEqual(['Newer'])
  })

  it('shows the empty state again after the last idea is deleted', async () => {
    const user = userEvent.setup()
    render(<IdeaBoard />)
    await addIdea(user, 'Only one')
    await user.click(screen.getByRole('button', { name: 'Delete idea: Only one' }))
    expect(screen.getByText('No ideas yet. Add your first one above.')).toBeInTheDocument()
  })

  it('still shows the remaining ideas after the page is reloaded', async () => {
    const user = userEvent.setup()
    const first = render(<IdeaBoard />)
    await addIdea(user, 'Keep me')
    await addIdea(user, 'Remove me')
    await user.click(screen.getByRole('button', { name: 'Delete idea: Remove me' }))
    first.unmount()
    render(<IdeaBoard />)
    expect(itemTexts()).toEqual(['Keep me'])
  })

  it('starts empty instead of crashing when stored data is corrupt', () => {
    window.localStorage.setItem(STORAGE_KEY, '{{{ not json')
    render(<IdeaBoard />)
    expect(screen.getByText('No ideas yet. Add your first one above.')).toBeInTheDocument()
  })

  it('keeps the idea visible and shows a message when saving fails', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    const user = userEvent.setup()
    render(<IdeaBoard />)
    await addIdea(user, 'Unsaved')
    expect(itemTexts()).toEqual(['Unsaved'])
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save your ideas in this browser.')
  })

  it('makes no network request', async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    const user = userEvent.setup()
    render(<IdeaBoard />)
    await addIdea(user, 'Offline')
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
