import { afterEach, describe, expect, it, vi } from 'vitest'
import { STORAGE_KEY, loadIdeas, saveIdeas } from './storage'
import type { Idea } from './types'

const sample: Idea[] = [
  { id: 'b', text: 'Second', createdAt: 2 },
  { id: 'a', text: 'First', createdAt: 1 },
]

afterEach(() => {
  vi.restoreAllMocks()
})

describe('loadIdeas', () => {
  it('returns an empty list when nothing is stored', () => {
    expect(loadIdeas()).toEqual([])
  })

  it('returns what saveIdeas wrote', () => {
    expect(saveIdeas(sample)).toBe(true)
    expect(loadIdeas()).toEqual(sample)
  })

  it('returns an empty list for invalid JSON', () => {
    window.localStorage.setItem(STORAGE_KEY, '{not json')
    expect(loadIdeas()).toEqual([])
  })

  it('returns an empty list when the value is not an array', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: 'a', text: 'x' }))
    expect(loadIdeas()).toEqual([])
  })

  it('returns an empty list when an item has the wrong shape', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ id: 'a', text: 'ok', createdAt: 1 }, { id: 5, text: 'bad' }]),
    )
    expect(loadIdeas()).toEqual([])
  })

  it('returns an empty list when reading throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(loadIdeas()).toEqual([])
  })
})

describe('saveIdeas', () => {
  it('writes under the idea-board:ideas key', () => {
    saveIdeas(sample)
    expect(window.localStorage.getItem('idea-board:ideas')).toBe(JSON.stringify(sample))
  })

  it('returns false when the browser refuses the write', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError')
    })
    expect(saveIdeas(sample)).toBe(false)
  })
})
