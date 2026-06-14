import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders the header title', () => {
    // Keep the request pending so we render the initial loading state.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    )

    render(<App />)

    expect(screen.getByRole('heading', { name: 'RAG' })).toBeInTheDocument()
  })

  it('renders the health status returned by the backend', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              status: 'ok',
              app: { name: 'RAG', version: '0.1.0', environment: 'test' },
              dependencies: { postgres: 'ok', qdrant: 'ok', redis: 'ok' },
            }),
        }),
      ),
    )

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('postgres')).toBeInTheDocument()
    })
    expect(screen.getAllByText('ok').length).toBeGreaterThan(0)
  })
})
