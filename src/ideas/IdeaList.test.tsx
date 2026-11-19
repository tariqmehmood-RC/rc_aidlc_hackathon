import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { IdeaList } from './IdeaList'
import type { Idea } from './types'

const ideas: Idea[] = [
  { id: 'b', text: 'Newer idea', createdAt: 2 },
  { id: 'a', text: 'Older idea', createdAt: 1 },
]

describe('IdeaList', () => {
  it('shows the empty state when there are no ideas', () => {
    render(<IdeaList ideas={[]} onDelete={vi.fn()} />)
    expect(screen.getByText('No ideas yet. Add your first one above.')).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('does not show the empty state when there are ideas', () => {
    render(<IdeaList ideas={ideas} onDelete={vi.fn()} />)
    expect(screen.queryByText(/No ideas yet/)).not.toBeInTheDocument()
  })

  it('renders ideas in the order given (newest first)', () => {
    render(<IdeaList ideas={ideas} onDelete={vi.fn()} />)
    const items = within(screen.getByRole('list')).getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      'Newer ideaDelete',
      'Older ideaDelete',
    ])
  })

  it('shows markup typed by the user literally', () => {
    const risky: Idea[] = [{ id: 'x', text: '<b>bold</b><img src=x onerror=alert(1)>', createdAt: 1 }]
    render(<IdeaList ideas={risky} onDelete={vi.fn()} />)
    expect(screen.getByText('<b>bold</b><img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(document.querySelector('b')).toBeNull()
    expect(document.querySelector('img')).toBeNull()
  })

  it('gives each Delete button an accessible name containing the idea text', () => {
    render(<IdeaList ideas={ideas} onDelete={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Delete idea: Newer idea' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete idea: Older idea' })).toBeInTheDocument()
  })

  it('calls onDelete with the id of the clicked idea only', async () => {
    const onDelete = vi.fn()
    const user = userEvent.setup()
    render(<IdeaList ideas={ideas} onDelete={onDelete} />)
    await user.click(screen.getByRole('button', { name: 'Delete idea: Older idea' }))
    expect(onDelete).toHaveBeenCalledExactlyOnceWith('a')
  })
})
