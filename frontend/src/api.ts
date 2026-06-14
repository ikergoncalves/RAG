// Thin client for the backend API. Requests use same-origin paths that are
// proxied to the backend by Vite (dev) or nginx (Docker).

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
