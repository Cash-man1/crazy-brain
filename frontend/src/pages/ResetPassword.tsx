import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Brain, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react'
import LegalFooter from '../components/LegalFooter'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-api.onrender.com'

function useQuery() {
  const { search } = useLocation()
  return useMemo(() => new URLSearchParams(search), [search])
}

export default function ResetPassword() {
  const q = useQuery()
  const navigate = useNavigate()
  const token = q.get('token') || ''

  const [newPassword, setNewPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token) {
      setError('Missing token')
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_URL}/api/auth/password-reset-confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: newPassword })
      })
      const data = await response.json()
      if (!response.ok) {
        const msg = data?.detail || data?.message || 'Reset failed'
        throw new Error(Array.isArray(msg) ? msg.join(', ') : String(msg))
      }
      setSuccess(true)
      window.setTimeout(() => navigate('/dashboard'), 1200)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="luxury-bg" />

      <div className="auth-container">
        <div className="auth-card">
          <div className="logo-section">
            <Brain className="brain-icon" />
            <h1>Crazy Brain</h1>
            <p>Nuova password (link da email)</p>
          </div>

          {error && (
            <div className="error-message">
              <AlertCircle size={18} />
              {error}
            </div>
          )}

          {success ? (
            <div className="success-message">
              <CheckCircle size={18} />
              Password aggiornata. Reindirizzamento alla dashboard…
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">Nuova password</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="Scegli una password sicura"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
              </div>

              <button type="submit" className="btn btn-primary" disabled={loading || !token}>
                {loading ? <span className="spinner" /> : 'Aggiorna password'}
              </button>
              {!token && (
                <div className="description" style={{ marginTop: 10, opacity: 0.85 }}>
                  Invalid link: missing token.
                </div>
              )}
            </form>
          )}

          <div className="auth-links">
            <Link
              to="/dashboard"
              className="auth-link"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
            >
              <ArrowLeft size={16} />
              Torna alla dashboard
            </Link>
          </div>
        </div>

        <LegalFooter />
      </div>
    </div>
  )
}

