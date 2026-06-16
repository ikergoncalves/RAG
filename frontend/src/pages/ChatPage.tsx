import { type FormEvent, useState } from 'react'

import { type Citation, streamChat } from '../api'
import { CitedAnswer } from '../components/CitedAnswer'
import { SourceViewer } from '../components/SourceViewer'

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  citations: Citation[]
}

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null)

  function updateLastMessage(update: (message: ChatMessage) => ChatMessage): void {
    setMessages((prev) => {
      if (prev.length === 0) return prev
      const next = [...prev]
      next[next.length - 1] = update(next[next.length - 1])
      return next
    })
  }

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    const question = input.trim()
    if (!question || loading) return

    setMessages((prev) => [
      ...prev,
      { role: 'user', text: question, citations: [] },
      { role: 'assistant', text: '', citations: [] },
    ])
    setInput('')
    setLoading(true)

    try {
      await streamChat(question, conversationId, {
        onDelta: (text) => updateLastMessage((m) => ({ ...m, text: m.text + text })),
        onCitations: (id, citations) => {
          setConversationId(id)
          updateLastMessage((m) => ({ ...m, citations }))
        },
      })
    } catch {
      updateLastMessage((m) => ({
        ...m,
        text: m.text || 'Something went wrong while generating the answer.',
      }))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="chat">
      <div className="chat__messages">
        {messages.length === 0 && (
          <p className="muted chat__empty">
            Ask a question about your indexed documents. Answers cite their sources — click a
            citation to see the original passage.
          </p>
        )}

        {messages.map((message, index) =>
          message.role === 'user' ? (
            <div key={index} className="message message--user">
              {message.text}
            </div>
          ) : (
            <div key={index} className="message message--assistant">
              {message.text === '' && loading ? (
                <span className="muted">Thinking…</span>
              ) : (
                <CitedAnswer
                  text={message.text}
                  citations={message.citations}
                  onCitationClick={setActiveCitation}
                />
              )}
            </div>
          ),
        )}
      </div>

      <form className="chat__form" onSubmit={handleSubmit}>
        <input
          className="chat__input"
          type="text"
          value={input}
          placeholder="Ask a question…"
          onChange={(event) => setInput(event.target.value)}
          aria-label="Question"
        />
        <button className="button" type="submit" disabled={loading || input.trim() === ''}>
          {loading ? 'Sending…' : 'Send'}
        </button>
      </form>

      {activeCitation && (
        <SourceViewer citation={activeCitation} onClose={() => setActiveCitation(null)} />
      )}
    </section>
  )
}
