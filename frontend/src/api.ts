// Thin client for the backend API. Requests use same-origin paths that are
// proxied to the backend by Vite (dev) or nginx (Docker). App endpoints live
// under `/api` so they never collide with the client-side routes (e.g. the
// `/documents` SPA route vs the `/documents` REST resource).

const API = '/api'

export interface AppInfo {
  name: string
  version: string
  environment: string
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  app: AppInfo
  dependencies: Record<string, string>
}

/**
 * Fetch the backend health report. A degraded backend answers `503` but still
 * returns a valid body, so that status code is treated as a successful read.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/health')
  if (!response.ok && response.status !== 503) {
    throw new Error(`Health request failed with status ${response.status}`)
  }
  return (await response.json()) as HealthResponse
}

// --- Documents ------------------------------------------------------------

export type DocumentStatus = 'pending' | 'processing' | 'indexed' | 'failed'

export interface DocumentRead {
  id: string
  filename: string
  content_type: string
  status: DocumentStatus
  uploaded_at: string
}

export interface DocumentDetail extends DocumentRead {
  chunk_count: number
}

export interface ChunkRead {
  id: string
  document_id: string
  chunk_index: number
  content: string
  token_count: number
  page_number: number | null
  section_path: string | null
  char_start: number
  char_end: number
  embedded_at: string | null
}

export async function listDocuments(): Promise<DocumentRead[]> {
  const response = await fetch(`${API}/documents`)
  if (!response.ok) {
    throw new Error(`Listing documents failed with status ${response.status}`)
  }
  return (await response.json()) as DocumentRead[]
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  const response = await fetch(`${API}/documents/${id}`)
  if (!response.ok) {
    throw new Error(`Fetching document ${id} failed with status ${response.status}`)
  }
  return (await response.json()) as DocumentDetail
}

export async function uploadDocument(file: File): Promise<DocumentRead> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${API}/documents`, { method: 'POST', body: form })
  if (!response.ok) {
    const detail = await readErrorDetail(response)
    throw new Error(detail ?? `Upload failed with status ${response.status}`)
  }
  return (await response.json()) as DocumentRead
}

export async function deleteDocument(id: string): Promise<void> {
  const response = await fetch(`${API}/documents/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Deleting document ${id} failed with status ${response.status}`)
  }
}

export async function getChunk(id: string): Promise<ChunkRead> {
  const response = await fetch(`${API}/chunks/${id}`)
  if (!response.ok) {
    throw new Error(`Fetching chunk ${id} failed with status ${response.status}`)
  }
  return (await response.json()) as ChunkRead
}

// --- Chat (Server-Sent Events) --------------------------------------------

export interface Citation {
  number: number
  chunk_id: string
  quote: string
  document_id: string
  document_name: string
  page: number | null
  section: string | null
}

type ChatEvent =
  | { type: 'delta'; text: string }
  | { type: 'citations'; conversation_id: string; citations: Citation[] }

export interface ChatStreamHandlers {
  /** Called for each streamed text fragment as the answer is generated. */
  onDelta: (text: string) => void
  /** Called once with the final citations and the conversation id. */
  onCitations: (conversationId: string, citations: Citation[]) => void
}

/**
 * Stream a cited answer for `question` from `POST /chat`.
 *
 * The backend replies with Server-Sent Events: a run of `delta` events followed
 * by a terminal `citations` event. `EventSource` only supports GET, so we read
 * the streamed response body manually and parse the `data:` lines.
 */
export async function streamChat(
  question: string,
  conversationId: string | null,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, conversation_id: conversationId }),
    signal,
  })
  if (!response.ok || !response.body) {
    const detail = await readErrorDetail(response)
    throw new Error(detail ?? `Chat request failed with status ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line.
    let separator: number
    while ((separator = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, separator)
      buffer = buffer.slice(separator + 2)
      dispatchFrame(frame, handlers)
    }
  }
  // Flush any trailing frame that lacked a final blank line.
  if (buffer.trim()) {
    dispatchFrame(buffer, handlers)
  }
}

function dispatchFrame(frame: string, handlers: ChatStreamHandlers): void {
  const data = frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trimStart())
    .join('\n')
  if (!data) return

  const event = JSON.parse(data) as ChatEvent
  if (event.type === 'delta') {
    handlers.onDelta(event.text)
  } else if (event.type === 'citations') {
    handlers.onCitations(event.conversation_id, event.citations)
  }
}

/** Best-effort extraction of a FastAPI `{ "detail": ... }` error message. */
async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.clone().json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : null
  } catch {
    return null
  }
}
