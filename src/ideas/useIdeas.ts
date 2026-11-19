import { useState } from 'react'
import { loadIdeas, saveIdeas } from './storage'
import type { Idea } from './types'

export type UseIdeas = {
  ideas: Idea[]
  saveError: boolean
  addIdea: (text: string) => void
  deleteIdea: (id: string) => void
}

/** Holds the list of ideas (newest first) and keeps local storage in sync. */
export function useIdeas(): UseIdeas {
  const [ideas, setIdeas] = useState<Idea[]>(loadIdeas)
  const [saveError, setSaveError] = useState(false)

  function commit(next: Idea[]) {
    setIdeas(next)
    setSaveError(!saveIdeas(next))
  }

  function addIdea(text: string) {
    const idea: Idea = { id: crypto.randomUUID(), text, createdAt: Date.now() }
    commit([idea, ...ideas])
  }

  function deleteIdea(id: string) {
    commit(ideas.filter((idea) => idea.id !== id))
  }

  return { ideas, saveError, addIdea, deleteIdea }
}
