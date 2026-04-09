import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-api.onrender.com'

const SEGMENTS = ['1', '2', '5', '10', 'CH', 'CF', 'PA', 'CT'] as const

function authHeader() {
  const t = localStorage.getItem('token')
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export default function ConnectTelegram() {
  const [status, setStatus] = useState<{ connected: boolean; notify_enabled: boolean; notify_segments: string } | null>(null)
  const [connectUrl, setConnectUrl] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const selectedSegments = useMemo(() => {
    const out: string[] = []
    for (const s of SEGMENTS) if (selected[s]) out.push(s)
    return out
  }, [selected])

  const load = async () => {
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/notify/telegram/status`, { headers: { ...authHeader() } })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Failed')
      setStatus(data)
      setEnabled(Boolean(data.notify_enabled))
      const segCsv = String(data.notify_segments || '')
      const set = new Set(segCsv.split(',').map((x) => x.trim()).filter(Boolean))
      const next: Record<string, boolean> = {}
      for (const s of SEGMENTS) next[s] = set.size ? set.has(s) : true
      setSelected(next)
    } catch (e: any) {
      setError(e?.message || 'Error')
    }
  }

  useEffect(() => {
    load()
  }, [])

  const generateLink = async () => {
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/notify/telegram/connect-link`, { method: 'POST', headers: { ...authHeader() } })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Failed to create link')
      setConnectUrl(data.connect_url)
    } catch (e: any) {
      setError(e?.message || 'Error')
    }
  }

  const savePrefs = async () => {
    setSaving(true)
    setError('')
    try {
      const segments = selectedSegments.length === SEGMENTS.length ? [] : selectedSegments
      const res = await fetch(`${API_URL}/api/notify/preferences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ enabled, segments })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Save failed')
      await load()
    } catch (e: any) {
      setError(e?.message || 'Error')
    } finally {
      setSaving(false)
    }
  }

  const toggleAll = (v: boolean) => {
    const next: Record<string, boolean> = {}
    for (const s of SEGMENTS) next[s] = v
    setSelected(next)
  }

  const disconnected = status && !status.connected

  return (
    <div className="dashboard dashboard--live-full">
      <main className="dashboard-content dashboard-content--live">
        <div className="container container--live-full">
          <div className="welcome-section live-welcome-tight">
            <h1>Collega Telegram</h1>
            <p>
              Telegram serve per 2 cose diverse:
              <br />
              - OTP (obbligatorio): per ricevere il codice devi premere <strong>START</strong> sul bot
              <br />
              - Notifiche segnali (opzionale): si attivano solo con il toggle qui sotto
            </p>
          </div>

          {error && <div className="error-message">{error}</div>}

          {!localStorage.getItem('token') ? (
            <div className="status-card">
              <div className="description">Devi fare login prima.</div>
              <Link to="/login" className="auth-link gold">
                Vai al login
              </Link>
            </div>
          ) : (
            <>
              <div className="status-card" style={{ marginBottom: 12 }}>
                <div className="description">
                  Stato: <strong>{status?.connected ? 'Collegato' : 'Non collegato'}</strong>
                </div>
                <button className="btn btn-primary" type="button" onClick={generateLink}>
                  Genera link Telegram
                </button>

                {connectUrl && (
                  <div style={{ marginTop: 10 }}>
                    <div className="description" style={{ marginBottom: 6 }}>
                      1) Apri il link sotto 2) premi START sul bot.
                    </div>
                    <a href={connectUrl} target="_blank" rel="noreferrer" style={{ wordBreak: 'break-all' }}>
                      {connectUrl}
                    </a>
                    <div className="description" style={{ marginTop: 8 }}>
                      Poi torna qui e attiva le notifiche.
                    </div>
                  </div>
                )}
              </div>

              <div className="status-card" style={{ marginBottom: 12 }}>
                <label style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                  <strong>Attiva notifiche</strong>
                </label>

                <div className="description" style={{ marginTop: 8 }}>
                  Se selezioni tutti i segmenti, verrà salvato come “tutti”.
                </div>

                <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                  <button className="btn" type="button" onClick={() => toggleAll(true)}>
                    Tutti
                  </button>
                  <button className="btn" type="button" onClick={() => toggleAll(false)}>
                    Nessuno
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8, marginTop: 12 }}>
                  {SEGMENTS.map((s) => (
                    <label key={s} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <input
                        type="checkbox"
                        checked={Boolean(selected[s])}
                        onChange={(e) => setSelected((p) => ({ ...p, [s]: e.target.checked }))}
                      />
                      {s}
                    </label>
                  ))}
                </div>

                <button className="btn btn-primary" type="button" onClick={savePrefs} disabled={saving || !status?.connected}>
                  {saving ? 'Salvataggio...' : 'Salva preferenze'}
                </button>
                {disconnected && <div className="description">Collega prima Telegram per salvare e ricevere messaggi.</div>}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

