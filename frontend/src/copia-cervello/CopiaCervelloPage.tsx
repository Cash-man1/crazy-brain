import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-it.onrender.com'

type SourcePayload = {
  source_url: string
  fetched_at: string
  summary: Record<string, string>
}

export default function CopiaCervelloPage() {
  const { user } = useAuth()
  const [data, setData] = useState<SourcePayload | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      const token = localStorage.getItem('token')
      if (!token) {
        setError('Token mancante')
        setLoading(false)
        return
      }

      try {
        const res = await fetch(`${API_URL}/api/brain/casino-source`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        const payload = await res.json()
        if (!res.ok) throw new Error(payload?.detail?.message || payload?.detail || 'Errore fetch')
        setData(payload)
      } catch (e: any) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div className="dashboard">
      <main className="dashboard-content">
        <div className="container">
          <div className="welcome-section">
            <h1>Copia Cervello - Fonte Live</h1>
            <p>Utente: {user?.email} | Dati estratti dalla pagina Crazy Time</p>
          </div>

          {loading && <div className="status-card"><div className="value">Caricamento...</div></div>}
          {error && <div className="error-message">{error}</div>}

          {data && (
            <>
              <div className="status-card">
                <h3>Sorgente</h3>
                <div className="description">{data.source_url}</div>
                <div className="description">Aggiornato: {data.fetched_at}</div>
              </div>
              <div className="status-grid">
                {Object.entries(data.summary).map(([key, value]) => (
                  <div key={key} className="status-card">
                    <h3>{key.replaceAll('_', ' ').toUpperCase()}</h3>
                    <div className="description">{value || 'Nessun dato trovato'}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
