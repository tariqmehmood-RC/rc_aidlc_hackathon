import type { Idea } from './types'

type IdeaListProps = {
  ideas: Idea[]
  onDelete: (id: string) => void
}

export function IdeaList({ ideas, onDelete }: IdeaListProps) {
  return (
    <div aria-live="polite">
      {ideas.length === 0 ? (
        <p className="idea-empty">No ideas yet. Add your first one above.</p>
      ) : (
        <ul className="idea-list" aria-label="Ideas">
          {ideas.map((idea) => (
            <li key={idea.id}>
              <span className="idea-text">{idea.text}</span>
              <button
                type="button"
                onClick={() => onDelete(idea.id)}
                aria-label={`Delete idea: ${idea.text}`}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
