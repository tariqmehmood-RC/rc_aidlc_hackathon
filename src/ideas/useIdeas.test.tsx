import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { STORAGE_KEY } from './storage'
import { useIdeas } from './useIdeas'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useIdeas', () => {
  it('starts empty when nothing is stored', () => {
    const { result } = renderHook(() => useIdeas())
    expect(result.current.ideas).toEqual([])
    expect(result.current.saveError).toBe(false)
  })

  it('puts the newest idea first', () => {
    const { result } = renderHook(() => useIdeas())
    act(() => result.current.addIdea('First'))
    act(() => result.current.addIdea('Second'))
    expect(result.current.ideas.map((i) => i.text)).toEqual(['Second', 'First'])
  })

  it('deletes only the idea with the matching id, even if text is identical', () => {
    const { result } = renderHook(() => useIdeas())
    act(() => result.current.addIdea('Same'))
    act(() => result.current.addIdea('Same'))
    const [newer, older] = result.current.ideas
    act(() => result.current.deleteIdea(newer.id))
    expect(result.current.ideas).toHaveLength(1)
    expect(result.current.ideas[0].id).toBe(older.id)
  })

  it('writes to local storage after every change', () => {
    const { result } = renderHook(() => useIdeas())
    act(() => result.current.addIdea('Kept'))
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null')).toHaveLength(1)
    act(() => result.current.deleteIdea(result.current.ideas[0].id))
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null')).toEqual([])
  })

  it('loads saved ideas on mount', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ id: 'x', text: 'Saved', createdAt: 1 }]),
    )
    const { result } = renderHook(() => useIdeas())
    expect(result.current.ideas.map((i) => i.text)).toEqual(['Saved'])
  })

  it('keeps the idea on screen and flags an error when saving fails', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    const { result } = renderHook(() => useIdeas())
    act(() => result.current.addIdea('Unsaved'))
    expect(result.current.ideas.map((i) => i.text)).toEqual(['Unsaved'])
    expect(result.current.saveError).toBe(true)
  })
})
