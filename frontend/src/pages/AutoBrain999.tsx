import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-it.onrender.com'

export default function AutoBrain999() {
  const { user } = useAuth()
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')

  const load = async () => {
    const token = localStorage.getItem('token')
    if (!token) return
    try {
      const res = await fetch(`${API_URL}/api/brain/auto-brain`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      const payload = await res.json()
      if (!res.ok) throw new Error(payload?.detail?.message || payload?.detail || 'Errore auto brain')
      setData(payload)
      setError('')
    } catch (e: any) {
      setError(e.message)
    }
  }

  useEffect(() => {
    load()
    const id = window.setInterval(load, 6000)
    return () => window.clearInterval(id)
  }, [])

  return (
    <div className="dashboard">
      <main className="dashboard-content">
        <div className="container">
          <div className="welcome-section">
            <h1>Crazy-Brain.999 Auto</h1>
            <p>Utente: {user?.email} | aggiornamento automatico ogni 6 secondi</p>
          </div>

          {error && <div className="error-message">{error}</div>}

          {data && (
            <>
              <div className="status-grid">
                <div className="status-card">
                  <h3>Fonte</h3>
                  <div className="description">{data.source_url}</div>
                  <div className="description">Ultimo poll: {data.last_poll}</div>
                </div>
                <div className="status-card">
                  <h3>Nuovi spin</h3>
                  <div className="value">{data.new_rows_added}</div>
                  <div className="description">Totale tracciati: {data.tracked_rows}</div>
                </div>
                <div className="status-card">
                  <h3>Segnale caldo</h3>
                  <div className="value">{data.next_hot_signal?.segment || '--'}</div>
                  <div className="description">
                    {data.next_hot_signal ? `EV ${data.next_hot_signal.ev} - conf ${data.next_hot_signal.confidence}` : 'In attesa dati'}
                  </div>
                </div>
              </div>

              <div className="status-card admin-users-table">
                <h3>Cronologia Giocate (auto)</h3>
                <table>
                  <thead>
                    <tr>
                      <th>Alle Ore</th>
                      <th>Risultato Slot</th>
                      <th>Esito Ruota</th>
                      <th>Moltiplicatori</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.latest_rows || []).map((r: any, idx: number) => (
                      <tr key={`${r.time}-${r.segment}-${idx}`}>
                        <td>{r.time}</td>
                        <td>{r.slot_result}</td>
                        <td>{r.wheel_result}</td>
                        <td>{(r.top_slot_multipliers || []).length ? r.top_slot_multipliers.join(' / ') + 'x' : 'nessun top slot'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
