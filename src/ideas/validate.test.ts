import { describe, expect, it } from 'vitest'
import { EMPTY_MESSAGE, TOO_LONG_MESSAGE, validateIdea } from './validate'

describe('validateIdea', () => {
  it('rejects empty input', () => {
    expect(validateIdea('')).toEqual({ ok: false, message: EMPTY_MESSAGE })
  })

  it('rejects whitespace-only input', () => {
    expect(validateIdea('   \t\n ')).toEqual({ ok: false, message: EMPTY_MESSAGE })
  })

  it('accepts a single character', () => {
    expect(validateIdea('a')).toEqual({ ok: true, text: 'a' })
  })

  it('trims surrounding spaces', () => {
    expect(validateIdea('  Try pottery  ')).toEqual({ ok: true, text: 'Try pottery' })
  })

  it('accepts exactly 140 characters', () => {
    const text = 'x'.repeat(140)
    expect(validateIdea(text)).toEqual({ ok: true, text })
  })

  it('rejects 141 characters', () => {
    expect(validateIdea('x'.repeat(141))).toEqual({ ok: false, message: TOO_LONG_MESSAGE })
  })

  it('applies the limit to trimmed text, not raw text', () => {
    const text = 'x'.repeat(140)
    expect(validateIdea(`   ${text}   `)).toEqual({ ok: true, text })
  })
})
