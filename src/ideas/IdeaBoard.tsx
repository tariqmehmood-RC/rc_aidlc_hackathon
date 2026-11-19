import { IdeaForm } from './IdeaForm'
import { IdeaList } from './IdeaList'
import { useIdeas } from './useIdeas'

export function IdeaBoard() {
  const { ideas, saveError, addIdea, deleteIdea } = useIdeas()

  return (
    <main className="idea-board">
      <h1>Idea board</h1>
      <IdeaForm onAdd={addIdea} />
      {saveError && (
        <p role="alert" className="idea-error">
          Could not save your ideas in this browser.
        </p>
      )}
      <IdeaList ideas={ideas} onDelete={deleteIdea} />
    </main>
  )
}
