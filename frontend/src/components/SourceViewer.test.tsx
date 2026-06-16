import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Citation, ChunkRead } from '../api'
import { SourceViewer } from './SourceViewer'

afterEach(() => {
  vi.unstubAllGlobals()
})

const citation: Citation = {
  number: 1,
  chunk_id: 'chunk-1',
  quote: 'Paris is the capital of France.',
  document_id: 'doc-1',
  document_name: 'geo.md',
  page: 3,
  section: 'Capitals',
}

const chunk: ChunkRead = {
  id: 'chunk-1',
  document_id: 'doc-1',
  chunk_index: 0,
  content: 'Intro. Paris is the capital of France. More text follows.',
  token_count: 12,
  page_number: 3,
  section_path: 'Capitals',
  char_start: 0,
  char_end: 57,
  embedded_at: null,
}

describe('SourceViewer', () => {
  it('fetches the chunk and highlights the cited quote', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(chunk) })),
    )

    render(<SourceViewer citation={citation} onClose={vi.fn()} />)

    expect(screen.getByText('geo.md')).toBeInTheDocument()
    expect(screen.getByText('Page 3')).toBeInTheDocument()

    const highlighted = await waitFor(() => screen.getByText('Paris is the capital of France.'))
    expect(highlighted.tagName).toBe('MARK')
    expect(global.fetch).toHaveBeenCalledWith('/chunks/chunk-1')
  })

  it('calls onClose when the close button is clicked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(chunk) })),
    )
    const onClose = vi.fn()

    render(<SourceViewer citation={citation} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: /close source viewer/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
