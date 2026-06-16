import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Citation, ChunkRead } from '../api'
import { ChatPage } from './ChatPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

const citation: Citation = {
  number: 1,
  chunk_id: 'chunk-1',
  quote: 'Paris is the capital of France',
  document_id: 'doc-1',
  document_name: 'geo.md',
  page: 3,
  section: 'Capitals',
}

const chunk: ChunkRead = {
  id: 'chunk-1',
  document_id: 'doc-1',
  chunk_index: 0,
  content: 'Paris is the capital of France. It sits on the Seine.',
  token_count: 12,
  page_number: 3,
  section_path: 'Capitals',
  char_start: 0,
  char_end: 53,
  embedded_at: null,
}

/** Build a streaming Response body that emits the given SSE events. */
function sseStream(events: object[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))
      }
      controller.close()
    },
  })
}

function stubFetch(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/chat') {
        return Promise.resolve({
          ok: true,
          status: 200,
          body: sseStream([
            { type: 'delta', text: 'Paris is the capital of France ' },
            { type: 'delta', text: '[1].' },
            { type: 'citations', conversation_id: 'conv-1', citations: [citation] },
          ]),
        })
      }
      if (url.startsWith('/chunks/')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(chunk) })
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`))
    }),
  )
}

describe('ChatPage', () => {
  it('streams the answer and turns [n] into a clickable citation that opens the source', async () => {
    stubFetch()
    render(<ChatPage />)

    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'What is the capital of France?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    // The streamed answer is rendered, with the [1] marker as a badge.
    await waitFor(() =>
      expect(screen.getByText(/Paris is the capital of France/)).toBeInTheDocument(),
    )
    const badge = await screen.findByRole('button', { name: /Open source 1/ })

    // Clicking the citation opens the source viewer for that chunk.
    fireEvent.click(badge)
    expect(await screen.findByRole('dialog', { name: /source viewer/i })).toBeInTheDocument()
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/chunks/chunk-1'))
  })

  it('disables the Send button while there is no input', () => {
    stubFetch()
    render(<ChatPage />)
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })
})
