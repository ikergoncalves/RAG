import { Fragment, type ReactNode, useEffect, useState } from 'react'

import { type Citation, type ChunkRead, getChunk } from '../api'

interface SourceViewerProps {
  /** The citation whose source chunk should be displayed. */
  citation: Citation
  /** Close the viewer. */
  onClose: () => void
}

type LoadState = 'loading' | 'loaded' | 'error'

/**
 * Side panel that shows the original passage behind a citation.
 *
 * Given the citation's `chunk_id` it fetches the full chunk (`GET /chunks/{id}`)
 * and highlights the cited `quote` within the chunk content. The chunk's
 * `char_start`/`char_end` are offsets into the *document* text, not the chunk,
 * so the quote is located inside the content by substring match.
 */
export function SourceViewer({ citation, onClose }: SourceViewerProps) {
  const [chunk, setChunk] = useState<ChunkRead | null>(null)
  const [state, setState] = useState<LoadState>('loading')

  useEffect(() => {
    let cancelled = false
    setState('loading')
    setChunk(null)

    getChunk(citation.chunk_id)
      .then((data) => {
        if (cancelled) return
        setChunk(data)
        setState('loaded')
      })
      .catch(() => {
        if (cancelled) return
        setState('error')
      })

    return () => {
      cancelled = true
    }
  }, [citation.chunk_id])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="source-viewer__backdrop" onClick={onClose}>
      <aside
        className="source-viewer"
        role="dialog"
        aria-label="Source viewer"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="source-viewer__header">
          <h3 className="source-viewer__title">{citation.document_name}</h3>
          <button
            type="button"
            className="source-viewer__close"
            onClick={onClose}
            aria-label="Close source viewer"
          >
            ×
          </button>
        </header>

        <p className="source-viewer__meta">
          {citation.page != null && <span>Page {citation.page}</span>}
          {citation.section && <span>{citation.section}</span>}
        </p>

        {state === 'loading' && <p className="muted">Loading source…</p>}
        {state === 'error' && (
          <p className="status status--down">Could not load the source passage.</p>
        )}
        {state === 'loaded' && chunk && (
          <blockquote className="source-viewer__content">
            {highlightQuote(chunk.content, citation.quote)}
          </blockquote>
        )}
      </aside>
    </div>
  )
}

/** Render `content` with the first occurrence of `quote` wrapped in a `<mark>`. */
function highlightQuote(content: string, quote: string): ReactNode {
  const index = findQuote(content, quote)
  if (index === -1) {
    return content
  }
  const before = content.slice(0, index)
  const match = content.slice(index, index + quote.length)
  const after = content.slice(index + quote.length)
  return (
    <Fragment>
      {before}
      <mark className="source-viewer__highlight">{match}</mark>
      {after}
    </Fragment>
  )
}

/** Locate `quote` in `content`, trying an exact then a case-insensitive match. */
function findQuote(content: string, quote: string): number {
  if (!quote) return -1
  const exact = content.indexOf(quote)
  if (exact !== -1) return exact
  return content.toLowerCase().indexOf(quote.toLowerCase())
}
