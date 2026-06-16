import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { DocumentRead } from '../api'
import { DocumentsPage } from './DocumentsPage'

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubBackend() {
  let docs: DocumentRead[] = [
    {
      id: 'd1',
      filename: 'guide.md',
      content_type: 'text/markdown',
      status: 'indexed',
      uploaded_at: '2026-06-15T10:00:00Z',
    },
  ]

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = init?.method ?? 'GET'

    if (url === '/api/documents' && method === 'GET') {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(docs) })
    }
    if (url.startsWith('/api/documents/') && method === 'GET') {
      const id = url.split('/').pop()
      const doc = docs.find((d) => d.id === id)
      if (!doc) return Promise.resolve({ ok: false, status: 404 })
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...doc, chunk_count: 5 }),
      })
    }
    if (url.startsWith('/api/documents/') && method === 'DELETE') {
      const id = url.split('/').pop()
      docs = docs.filter((d) => d.id !== id)
      return Promise.resolve({ ok: true, status: 204 })
    }
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`))
  })

  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock }
}

describe('DocumentsPage', () => {
  it('lists documents with status and chunk count', async () => {
    stubBackend()
    render(<DocumentsPage />)

    expect(await screen.findByText('guide.md')).toBeInTheDocument()
    expect(screen.getByText('indexed')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('deletes a document when the Delete button is clicked', async () => {
    const { fetchMock } = stubBackend()
    render(<DocumentsPage />)

    fireEvent.click(await screen.findByRole('button', { name: /delete guide.md/i }))

    await waitFor(() => expect(screen.queryByText('guide.md')).not.toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/documents/d1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
