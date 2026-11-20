import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the app title', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Inside Sales Copilot' })).toBeInTheDocument()
  })

  it('does not show Vite starter content', () => {
    render(<App />)
    expect(screen.queryByText(/vite \+ react/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/count is/i)).not.toBeInTheDocument()
  })
})
