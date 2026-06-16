import { Fragment, type ReactNode } from 'react'

import type { Citation } from '../api'

interface CitedAnswerProps {
  /** The assistant's answer text, possibly containing `[n]` citation markers. */
  text: string
  /** Citations to resolve the markers against (empty while still streaming). */
  citations: Citation[]
  /** Called when a citation badge is clicked, to open the source viewer. */
  onCitationClick: (citation: Citation) => void
}

const MARKER = /\[(\d+)\]/g

/**
 * Render an answer with its `[n]` markers turned into clickable citation badges.
 *
 * A marker is rendered as a badge only when a matching citation exists (the
 * citations event has arrived). Until then — or for an unmatched number — the
 * literal `[n]` text is shown, so the streaming answer stays readable.
 */
export function CitedAnswer({ text, citations, onCitationClick }: CitedAnswerProps) {
  const byNumber = new Map(citations.map((citation) => [citation.number, citation]))
  const nodes: ReactNode[] = []

  let lastIndex = 0
  let key = 0
  for (const match of text.matchAll(MARKER)) {
    const index = match.index ?? 0
    if (index > lastIndex) {
      nodes.push(<Fragment key={key++}>{text.slice(lastIndex, index)}</Fragment>)
    }

    const number = Number(match[1])
    const citation = byNumber.get(number)
    if (citation) {
      nodes.push(
        <button
          key={key++}
          type="button"
          className="citation"
          onClick={() => onCitationClick(citation)}
          aria-label={`Open source ${number}: ${citation.document_name}`}
          title={citation.document_name}
        >
          {number}
        </button>,
      )
    } else {
      nodes.push(<Fragment key={key++}>{match[0]}</Fragment>)
    }
    lastIndex = index + match[0].length
  }

  if (lastIndex < text.length) {
    nodes.push(<Fragment key={key++}>{text.slice(lastIndex)}</Fragment>)
  }

  return <div className="cited-answer">{nodes}</div>
}
