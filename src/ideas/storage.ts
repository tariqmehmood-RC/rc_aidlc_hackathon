import type { Idea } from './types'

export const STORAGE_KEY = 'idea-board:ideas'

function isIdea(value: unknown): value is Idea {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.text === 'string' &&
    typeof candidate.createdAt === 'number'
  )
}

/** Reads saved ideas. Returns [] if nothing is stored or the data is unusable. */
export function loadIdeas(): Idea[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw === null) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.every(isIdea)) return []
    return parsed
  } catch {
    return []
  }
}

/** Writes the ideas. Returns false if the browser refused (full, blocked). */
export function saveIdeas(ideas: Idea[]): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ideas))
    return true
  } catch {
    return false
  }
}
