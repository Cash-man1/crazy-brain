import { useEffect, useState } from 'react'

const API_CANDIDATES = [
  import.meta.env.VITE_API_URL,
  'http://127.0.0.1:8001',
  'http://localhost:8001',
  'http://127.0.0.1:8000',
  'http://localhost:8000',
].filter(Boolean) as string[]

const segmentColor: Record<string, string> = {
  '1': '#00b3a4',
  '2': '#f3c64e',
  '5': '#ff5c63',
  '10': '#c879ff',
  CH: '#58d47f',
  CF: '#66b5ff',
  PA: '#d08bff',
  CT: '#ff4f4f'
}

export default function LiveDashboardNoAuth() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')

  const load = async () => {
    let lastError = 'Failed to fetch'
    for (const base of API_CANDIDATES) {
      try {
        const res = await fetch(`${base}/api/brain/auto-brain-public`)
        const payload = await res.json()
        if (!res.ok) throw new Error(payload?.detail || 'Errore caricamento dati')
        setData(payload)
        setError('')
        return
      } catch (e: any) {
        lastError = `${base}: ${e.message}`
      }
    }
    setError(lastError)
  }

  useEffect(() => {
    load()
    const id = window.setInterval(load, 6000)
    return () => window.clearInterval(id)
  }, [])

  const hot = data?.hot_signals || []
  const brains = data?.mini_brains ? Object.values(data.mini_brains) : []
  const latestRows = data?.latest_rows || []

  return (
    <div className="dashboard">
      <main className="dashboard-content">
        <div className="container">
          <div className="welcome-section">
            <h1>CRAZY BRAIN.999</h1>
            <p>Auto mode attivo - aggiornamento ogni 6 secondi</p>
          </div>

          {error && <div className="error-message">{error}</div>}

          {data && (
            <div className="status-grid" style={{ marginBottom: 18 }}>
              <div className="status-card">
                <h3>Fonte</h3>
                <div className="description">{data.source_url}</div>
                <div className="description">source_ok: {String(data.source_ok)}</div>
                <div className="description">righe lette: {data.scraper_rows_count ?? '--'}</div>
                <div className="description">tracked_rows: {data.tracked_rows ?? 0}</div>
                <div className="description">last_poll: {data.last_poll || '--'}</div>
                <div className="description">errore: {data.source_error || 'nessuno'}</div>
              </div>
            </div>
          )}

          <h3 className="section-title">Mini Brains</h3>
          <div className="mini-brains-grid">
            {brains.map((b: any) => (
              <div className="mini-brain-card" key={b.segment}>
                <div className="mini-top">
                  <span className="mini-badge" style={{ background: segmentColor[b.segment] || '#333' }}>{b.segment}</span>
                  <span className="mini-phase">{String(b.phase).toUpperCase()}</span>
                  <span className={`mini-ev ${b.ev >= 0 ? 'pos' : 'neg'}`}>EV: {b.ev}</span>
                </div>
                <div className="mini-line">Battery {Math.round((b.battery || 0))}%</div>
                <div className="mini-line">Gap {b.gap_current}/{Math.round(b.expected_gap || 0)} - Conf {(b.confidence * 100).toFixed(1)}%</div>
                <div className="mini-line">Heat {b.heat} - Z {b.z_score} - Range {b.range}</div>
              </div>
            ))}
          </div>

          <h3 className="section-title">Segnali Piu Caldi</h3>
          <div className="status-card admin-users-table">
            <table>
              <thead>
                <tr>
                  <th>Segmento</th>
                  <th>Fase</th>
                  <th>Confidence</th>
                  <th>EV</th>
                  <th>Range rimanente</th>
                </tr>
              </thead>
              <tbody>
                {hot.length === 0 && (
                  <tr><td colSpan={5}>Nessun segnale caldo al momento</td></tr>
                )}
                {hot.map((s: any, idx: number) => (
                  <tr key={`${s.segment}-${idx}`}>
                    <td>{s.segment}</td>
                    <td>{s.phase}</td>
                    <td>{(s.confidence * 100).toFixed(1)}%</td>
                    <td>{s.ev}</td>
                    <td>{s.range_remaining}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="section-title" style={{ marginTop: 18 }}>Ultimi Esiti Letti</h3>
          <div className="status-card admin-users-table">
            <table>
              <thead>
                <tr>
                  <th>Ora</th>
                  <th>Segmento</th>
                  <th>Moltiplicatori</th>
                </tr>
              </thead>
              <tbody>
                {latestRows.length === 0 && (
                  <tr><td colSpan={3}>Nessun esito letto ancora</td></tr>
                )}
                {latestRows.map((r: any, idx: number) => (
                  <tr key={`${r.time}-${r.segment}-${idx}`}>
                    <td>{r.time}</td>
                    <td>{r.segment || '-'}</td>
                    <td>{(r.top_slot_multipliers || []).length ? r.top_slot_multipliers.join(' / ') + 'x' : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  )
}
