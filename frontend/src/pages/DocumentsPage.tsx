import { type ChangeEvent, type DragEvent, useCallback, useEffect, useRef, useState } from 'react'

import {
  type DocumentDetail,
  type DocumentStatus,
  deleteDocument,
  getDocument,
  listDocuments,
  uploadDocument,
} from '../api'

const POLL_INTERVAL_MS = 3000

interface Upload {
  name: string
  status: 'uploading' | 'error'
  error?: string
}

export function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentDetail[]>([])
  const [uploads, setUploads] = useState<Upload[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    try {
      const summaries = await listDocuments()
      // The list endpoint omits chunk_count; fetch each document's detail for it.
      // A per-document failure (e.g. a row deleted mid-refresh) degrades to 0
      // rather than failing the whole refresh.
      const details = await Promise.all(
        summaries.map((summary) =>
          getDocument(summary.id).catch(() => ({ ...summary, chunk_count: 0 })),
        ),
      )
      setDocuments(details)
      setLoadError(null)
    } catch {
      setLoadError('Could not load documents.')
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      for (const file of Array.from(files)) {
        setUploads((prev) => [...prev, { name: file.name, status: 'uploading' }])
        try {
          await uploadDocument(file)
          setUploads((prev) => prev.filter((upload) => upload.name !== file.name))
          await refresh()
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Upload failed'
          setUploads((prev) =>
            prev.map((upload) =>
              upload.name === file.name ? { ...upload, status: 'error', error: message } : upload,
            ),
          )
        }
      }
    },
    [refresh],
  )

  function onInputChange(event: ChangeEvent<HTMLInputElement>): void {
    void handleFiles(event.target.files)
    event.target.value = '' // allow re-selecting the same file
  }

  function onDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault()
    setDragOver(false)
    void handleFiles(event.dataTransfer.files)
  }

  async function handleDelete(id: string): Promise<void> {
    setDocuments((prev) => prev.filter((document) => document.id !== id))
    try {
      await deleteDocument(id)
    } finally {
      await refresh()
    }
  }

  return (
    <section className="documents">
      <div
        className={`dropzone${dragOver ? ' dropzone--active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <p>Drag &amp; drop a document here, or</p>
        <button type="button" className="button" onClick={() => fileInputRef.current?.click()}>
          Choose a file
        </button>
        <input
          ref={fileInputRef}
          type="file"
          className="dropzone__input"
          accept=".pdf,.docx,.md,.markdown,.html,.htm"
          aria-label="Upload document"
          onChange={onInputChange}
        />
        <p className="muted dropzone__hint">PDF, DOCX, Markdown or HTML</p>
      </div>

      {uploads.length > 0 && (
        <ul className="uploads">
          {uploads.map((upload) => (
            <li key={upload.name} className="uploads__item">
              <span>{upload.name}</span>
              <span className={upload.status === 'error' ? 'status status--down' : 'muted'}>
                {upload.status === 'error' ? (upload.error ?? 'Failed') : 'Uploading…'}
              </span>
            </li>
          ))}
        </ul>
      )}

      {loadError && <p className="status status--down">{loadError}</p>}

      {documents.length === 0 ? (
        <p className="muted">No documents yet. Upload one to get started.</p>
      ) : (
        <table className="doc-table">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Status</th>
              <th>Chunks</th>
              <th>Uploaded</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.id}>
                <td>{document.filename}</td>
                <td>
                  <span className={statusClassName(document.status)}>{document.status}</span>
                </td>
                <td>{document.chunk_count}</td>
                <td>{new Date(document.uploaded_at).toLocaleString()}</td>
                <td>
                  <button
                    type="button"
                    className="button button--danger"
                    onClick={() => void handleDelete(document.id)}
                    aria-label={`Delete ${document.filename}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function statusClassName(status: DocumentStatus): string {
  if (status === 'indexed') return 'status status--ok'
  if (status === 'failed') return 'status status--down'
  return 'status status--pending'
}
