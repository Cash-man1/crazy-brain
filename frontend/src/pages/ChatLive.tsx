import { useEffect, useMemo, useRef, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-api.onrender.com'

function toWsUrl(apiUrl: string) {
  try {
    const u = new URL(apiUrl)
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
    u.pathname = '/api/chat/ws'
    u.search = ''
    return u.toString()
  } catch {
    // fallback for localhost style strings
    return apiUrl.replace(/^http/i, 'ws') + '/api/chat/ws'
  }
}

export default function ChatLive() {
  const wsUrl = useMemo(() => toWsUrl(API_URL), [])
  const [activeUsers, setActiveUsers] = useState<number>(0)
  const [messages, setMessages] = useState<{ ts: number; text: string }[]>([])
  const [text, setText] = useState('')
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data?.type === 'presence') setActiveUsers(Number(data.active_users ?? 0))
        if (data?.type === 'message' && typeof data.text === 'string') {
          setMessages((prev) => [...prev, { ts: Number(data.ts ?? Date.now() / 1000), text: data.text }].slice(-80))
        }
      } catch {
        // ignore
      }
    }
    ws.onclose = () => {
      wsRef.current = null
    }
    return () => ws.close()
  }, [wsUrl])

  const send = (e: React.FormEvent) => {
    e.preventDefault()
    const msg = text.trim()
    if (!msg) return
    wsRef.current?.send(msg)
    setText('')
  }

  return (
    <div className="dashboard dashboard--live-full">
      <main className="dashboard-content dashboard-content--live">
        <div className="container container--live-full">
          <div className="welcome-section live-welcome-tight">
            <h1>Live Chat</h1>
            <p>
              Utenti attivi ora: <strong>{activeUsers}</strong>
            </p>
          </div>

          <div className="status-card" style={{ padding: 12, marginBottom: 12, maxHeight: '55vh', overflow: 'auto' }}>
            {messages.length === 0 ? (
              <div className="description">Nessun messaggio ancora.</div>
            ) : (
              messages.map((m, i) => (
                <div key={i} style={{ padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  <div style={{ opacity: 0.7, fontSize: '0.78rem' }}>{new Date(m.ts * 1000).toLocaleTimeString()}</div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
                </div>
              ))
            )}
          </div>

          <form onSubmit={send} className="status-card" style={{ padding: 12, display: 'flex', gap: 10 }}>
            <input
              className="form-input"
              placeholder="Scrivi un messaggio..."
              value={text}
              onChange={(e) => setText(e.target.value)}
              style={{ flex: 1 }}
            />
            <button className="btn btn-primary" type="submit">
              Invia
            </button>
          </form>
        </div>
      </main>
    </div>
  )
}

