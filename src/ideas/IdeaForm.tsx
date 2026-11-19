import { useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { MAX_IDEA_LENGTH } from './types'
import { validateIdea } from './validate'

type IdeaFormProps = {
  onAdd: (text: string) => void
}

export function IdeaForm({ onAdd }: IdeaFormProps) {
  const inputId = useId()
  const errorId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const result = validateIdea(value)
    if (!result.ok) {
      setError(result.message)
      return
    }
    onAdd(result.text)
    setValue('')
    setError(null)
    inputRef.current?.focus()
  }

  return (
    <form className="idea-form" onSubmit={handleSubmit} noValidate>
      <label htmlFor={inputId}>New idea</label>
      <div className="idea-form-row">
        <input
          id={inputId}
          ref={inputRef}
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-invalid={error !== null}
          aria-describedby={error !== null ? errorId : undefined}
          autoComplete="off"
          placeholder={`Up to ${MAX_IDEA_LENGTH} characters`}
        />
        <button type="submit">Add</button>
      </div>
      {error !== null && (
        <p id={errorId} role="alert" className="idea-error">
          {error}
        </p>
      )}
    </form>
  )
}
