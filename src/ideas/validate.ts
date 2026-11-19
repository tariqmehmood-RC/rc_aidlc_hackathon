import { MAX_IDEA_LENGTH } from './types'

export const EMPTY_MESSAGE = 'Enter an idea before adding it.'
export const TOO_LONG_MESSAGE = `Ideas can be at most ${MAX_IDEA_LENGTH} characters.`

export type ValidationResult =
  | { ok: true; text: string }
  | { ok: false; message: string }

/** Trims the input, then checks it is 1 to MAX_IDEA_LENGTH characters. */
export function validateIdea(raw: string): ValidationResult {
  const text = raw.trim()
  if (text.length === 0) {
    return { ok: false, message: EMPTY_MESSAGE }
  }
  if (text.length > MAX_IDEA_LENGTH) {
    return { ok: false, message: TOO_LONG_MESSAGE }
  }
  return { ok: true, text }
}
