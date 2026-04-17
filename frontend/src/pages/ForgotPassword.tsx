import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Brain, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react'
import LegalFooter from '../components/LegalFooter'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-api.onrender.com'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.message || 'Request failed')
      }

      setSuccess(true)
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
            <p>Recupero password (account email)</p>
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
              Controlla la posta per le istruzioni di reset
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input
                  type="email"
                  className="form-input"
                  placeholder="La tua email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>

              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={loading}
              >
                {loading ? <span className="spinner" /> : 'Invia link di reset'}
              </button>
            </form>
          )}

          <div className="auth-links">
            <Link to="/dashboard" className="auth-link" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
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