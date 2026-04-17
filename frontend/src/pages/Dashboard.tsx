import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Brain, Crown, LogOut, Shield, Zap } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'
import LegalFooter from '../components/LegalFooter'
import InstagramMarkLink from '../components/InstagramMarkLink'
import { INSTAGRAM_URL } from '../config/social'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-api.onrender.com'
const instagramHref = INSTAGRAM_URL || 'https://www.instagram.com/'
const SEGMENTS = ['1', '2', '5', '10', 'CF', 'CH', 'PA', 'CT']

type AccessStatus = {
  can_access: boolean
  role: string
  subscription_status: string
  is_trial_active: boolean
  trial_end?: string | null
}

export default function Dashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [loadingCheckout, setLoadingCheckout] = useState(false)
  const [access, setAccess] = useState<AccessStatus | null>(null)
  const [bankroll, setBankroll] = useState('100')
  const [segment, setSegment] = useState('1')
  const [toolMessage, setToolMessage] = useState('')
  const [decision, setDecision] = useState<any>(null)
  const [session, setSession] = useState<any>(null)
  const [adminStats, setAdminStats] = useState<any>(null)
  const [adminUsers, setAdminUsers] = useState<any[]>([])

  const token = localStorage.getItem('token')

  const callApi = async (path: string, options: RequestInit = {}) => {
    const res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(options.headers || {})
      }
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data?.detail?.message || data?.detail || 'Request failed')
    return data
  }

  const refreshAccess = async () => {
    if (!token) return
    try {
      const data = await callApi('/api/brain/access-status')
      setAccess(data)
    } catch (error: any) {
      setToolMessage(error.message)
    }
  }

  useEffect(() => {
    refreshAccess()
  }, [])

  useEffect(() => {
    const loadAdmin = async () => {
      if (user?.role !== 'admin') return
      try {
        const [stats, users] = await Promise.all([
          callApi('/api/admin/stats'),
          callApi('/api/admin/users?limit=20')
        ])
        setAdminStats(stats)
        setAdminUsers(users.users || [])
      } catch {
        // no-op
      }
    }
    loadAdmin()
  }, [user?.role])

  const trialValid = useMemo(() => {
    if (!user?.trial_end) return false
    return new Date(user.trial_end) > new Date()
  }, [user?.trial_end])

  const hasAccess = Boolean(
    access?.can_access ||
      user?.role === 'admin' ||
      user?.role === 'vip' ||
      user?.subscription_status === 'active' ||
      trialValid
  )

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const handleSubscribe = async () => {
    setLoadingCheckout(true)
    try {
      const data = await callApi('/api/stripe/create-checkout-session', {
        method: 'POST',
        body: JSON.stringify({ price_type: 'monthly' })
      })
      window.location.href = data.checkout_url
    } catch (error: any) {
      setToolMessage(error.message)
    } finally {
      setLoadingCheckout(false)
    }
  }

  const startSession = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const data = await callApi('/api/brain/session/start', {
        method: 'POST',
        body: JSON.stringify({ bankroll: Number(bankroll) })
      })
      setSession(data.session)
      setToolMessage('Sessione avviata con successo')
    } catch (error: any) {
      setToolMessage(error.message)
    }
  }

  const addSpin = async () => {
    try {
      const data = await callApi('/api/brain/spin', {
        method: 'POST',
        body: JSON.stringify({ segment })
      })
      setDecision(data.decision)
      setSession(data.session)
      setToolMessage('Spin registrato')
    } catch (error: any) {
      setToolMessage(error.message)
    }
  }

  const loadDecision = async () => {
    try {
      const data = await callApi('/api/brain/decision')
      setDecision(data)
    } catch (error: any) {
      setToolMessage(error.message)
    }
  }

  const badge = user?.role === 'admin'
    ? { icon: Shield, text: 'ADMIN', className: 'admin' }
    : user?.role === 'vip'
      ? { icon: Crown, text: 'VIP LIFETIME', className: 'vip' }
      : trialValid
        ? { icon: Zap, text: 'TRIAL', className: 'trial' }
        : { icon: null, text: 'USER', className: '' }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="container">
          <div className="dashboard-logo">
            <Brain className="brain-icon" />
            <h2>Crazy Brain Luxury</h2>
          </div>

          <div className="user-menu">
            <div className={`user-badge ${badge.className}`}>
              {badge.icon && <badge.icon size={14} />}
              <span>{badge.text}</span>
            </div>
            <span className="user-email">{user?.email}</span>
            <button onClick={handleLogout} className="btn-logout">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </header>

      <main className="dashboard-content">
        <div className="container">
          <div className="welcome-section">
            <h1>VIP Brain Console</h1>
            <p>Nero e oro, controllo totale dello strumento.</p>
            <p style={{ marginTop: 10 }}>
              <button className="btn btn-secondary" onClick={() => navigate('/copia-cervello')}>
                Apri copia cervello (fonte live)
              </button>
            </p>
            <p style={{ marginTop: 10 }}>
              <button className="btn btn-primary" onClick={() => navigate('/auto-brain-999')}>
                Avvia crazy-brain.999 automatico
              </button>
            </p>
            <p style={{ marginTop: 10 }}>
              <InstagramMarkLink
                href={instagramHref}
                title={
                  INSTAGRAM_URL
                    ? 'Profilo Instagram'
                    : 'Instagram — imposta VITE_INSTAGRAM_URL su Render per il tuo profilo'
                }
                className="btn btn-secondary"
              />
            </p>
          </div>

          <div className="status-grid">
            <div className="status-card">
              <h3>Accesso Tool</h3>
              <div className="value">{hasAccess ? 'ATTIVO' : 'BLOCCATO'}</div>
              <div className="description">Stato: {user?.subscription_status || 'none'}</div>
            </div>
            <div className="status-card">
              <h3>Trial</h3>
              <div className="value">{trialValid ? 'IN CORSO' : 'NO'}</div>
              <div className="description">{user?.trial_end || 'Nessuna trial'}</div>
            </div>
          </div>

          {user?.role === 'admin' && adminStats && (
            <div className="admin-grid">
              <div className="admin-card"><h3>Totale utenti</h3><div className="number">{adminStats.total_users}</div></div>
              <div className="admin-card"><h3>VIP</h3><div className="number">{adminStats.vip_users}</div></div>
              <div className="admin-card"><h3>Trial attive</h3><div className="number">{adminStats.active_trials}</div></div>
              <div className="admin-card"><h3>Paganti</h3><div className="number">{adminStats.paid_users}</div></div>
            </div>
          )}

          {user?.role === 'admin' && adminUsers.length > 0 && (
            <div className="status-card admin-users-table">
              <h3>Ultimi iscritti</h3>
              <table>
                <thead><tr><th>Email</th><th>Ruolo</th><th>Status</th></tr></thead>
                <tbody>
                  {adminUsers.map((u) => (
                    <tr key={u.id}><td>{u.email}</td><td>{u.role}</td><td>{u.subscription_status}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {hasAccess ? (
            <div className="tool-section">
              <h2>Brain Tool UI</h2>
              <form className="brain-form" onSubmit={startSession}>
                <input className="form-input" value={bankroll} onChange={(e) => setBankroll(e.target.value)} />
                <button className="btn btn-primary" type="submit">Start Session</button>
              </form>
              <div className="brain-actions">
                <select className="form-input" value={segment} onChange={(e) => setSegment(e.target.value)}>
                  {SEGMENTS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <button className="btn btn-secondary" onClick={addSpin}>Add Spin</button>
                <button className="btn btn-secondary" onClick={loadDecision}>Decision</button>
              </div>
              {toolMessage && <p className="description">{toolMessage}</p>}
              {session && <pre className="tool-json">{JSON.stringify(session, null, 2)}</pre>}
              {decision && <pre className="tool-json">{JSON.stringify(decision, null, 2)}</pre>}
            </div>
          ) : (
            <div className="paywall-section">
              <div className="paywall-content">
                <Crown size={48} style={{ color: 'var(--gold)', marginBottom: 16 }} />
                <h2>Attiva Premium</h2>
                <p>I primi 10 utenti hanno 2 giorni gratis, poi serve abbonamento.</p>
                <div className="price-tag">EUR 29</div>
                <div className="price-period">al mese</div>
                <button className="btn btn-primary" onClick={handleSubscribe} disabled={loadingCheckout}>
                  {loadingCheckout ? 'Loading...' : 'Vai a pagamento'}
                </button>
              </div>
            </div>
          )}
        </div>
        <LegalFooter variant="dashboard" />
      </main>
    </div>
  )
}
