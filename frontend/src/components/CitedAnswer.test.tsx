import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Citation } from '../api'
import { CitedAnswer } from './CitedAnswer'

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    number: 1,
    chunk_id: 'chunk-1',
    quote: 'Paris is the capital of France.',
    document_id: 'doc-1',
    document_name: 'geo.md',
    page: 3,
    section: 'Capitals',
    ...overrides,
  }
}

describe('CitedAnswer', () => {
  it('renders a [n] marker as a clickable badge and fires the click handler', () => {
    const onCitationClick = vi.fn()
    render(
      <CitedAnswer
        text="The capital of France is Paris [1]."
        citations={[citation()]}
        onCitationClick={onCitationClick}
      />,
    )

    expect(screen.getByText(/The capital of France is Paris/)).toBeInTheDocument()

    const badge = screen.getByRole('button', { name: /Open source 1/ })
    expect(badge).toHaveTextContent('1')

    fireEvent.click(badge)
    expect(onCitationClick).toHaveBeenCalledWith(expect.objectContaining({ number: 1 }))
  })

  it('leaves a marker as plain text when no matching citation exists', () => {
    render(<CitedAnswer text="No source here [2]." citations={[]} onCitationClick={vi.fn()} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText(/\[2\]/)).toBeInTheDocument()
  })
})
