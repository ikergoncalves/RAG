import { useEffect, useState } from 'react'

import './App.css'
import { fetchHealth, type HealthResponse } from './api'
import { Header } from './components/Header'

type LoadState = 'loading' | 'loaded' | 'error'

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [state, setState] = useState<LoadState>('loading')

  useEffect(() => {
    let cancelled = false

    fetchHealth()
      .then((data) => {
        if (cancelled) return
        setHealth(data)
        setState('loaded')
      })
      .catch(() => {
        if (cancelled) return
        setState('error')
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="app">
      <Header />
      <main className="container">
        <section className="card">
          <h2>Backend health</h2>

          {state === 'loading' && <p className="muted">Checking backend…</p>}

          {state === 'error' && <p className="status status--down">Unable to reach the backend.</p>}

          {state === 'loaded' && health && (
            <>
              <p>
                Overall status:{' '}
                <span
                  className={`status ${health.status === 'ok' ? 'status--ok' : 'status--down'}`}
                >
                  {health.status}
                </span>
              </p>
              <ul className="deps">
                {Object.entries(health.dependencies).map(([name, value]) => (
                  <li key={name} className="deps__item">
                    <span className="deps__name">{name}</span>
                    <span className={`status ${value === 'ok' ? 'status--ok' : 'status--down'}`}>
                      {value}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </main>
    </div>
  )
}
