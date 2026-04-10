import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Brain, AlertCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import LegalFooter from '../components/LegalFooter'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-api.onrender.com'

function mapFetchError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e)
  if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) {
    return (
      'Connessione al server non riuscita (spesso CORS o API offline). ' +
      'Su Render: imposta CORS_EXTRA_ORIGINS con l’URL del sito statico, oppure riprova tra poco.'
    )
  }
  return msg
}

export default function Login() {
  const { loading, error } = useAuth()
  const navigate = useNavigate()
  const [phoneMode, setPhoneMode] = useState<'register' | 'login'>('register')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [otpCode, setOtpCode] = useState('')
  const [phonePassword, setPhonePassword] = useState('')
  const [phonePassword2, setPhonePassword2] = useState('')
  const [otpLoading, setOtpLoading] = useState(false)
  const [otpError, setOtpError] = useState('')
  const [otpSent, setOtpSent] = useState(false)
  const [tgLink, setTgLink] = useState('')

  // login email rimosso: usiamo solo telefono + password

  const requestOtp = async () => {
    setOtpLoading(true)
    setOtpError('')
    try {
      const res = await fetch(`${API_URL}/api/auth/phone/request-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.message || 'OTP request failed')
      setOtpSent(true)
    } catch (e: unknown) {
      setOtpError(mapFetchError(e))
    } finally {
      setOtpLoading(false)
    }
  }

  const createTelegramLinkForPhone = async () => {
    setOtpLoading(true)
    setOtpError('')
    try {
      const res = await fetch(`${API_URL}/api/auth/phone/telegram-link`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.message || 'Link failed')
      setTgLink(String(data.connect_url || ''))
    } catch (e: unknown) {
      setOtpError(mapFetchError(e))
    } finally {
      setOtpLoading(false)
    }
  }

  const registerWithOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setOtpLoading(true)
    setOtpError('')
    try {
      if (phonePassword !== phonePassword2) throw new Error('Passwords do not match')
      const res = await fetch(`${API_URL}/api/auth/phone/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber, code: otpCode, password: phonePassword })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.message || 'Register failed')
      localStorage.setItem('token', data.access_token)
      window.location.href = '/dashboard'
    } catch (e: unknown) {
      setOtpError(mapFetchError(e))
    } finally {
      setOtpLoading(false)
    }
  }

  const phoneLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setOtpLoading(true)
    setOtpError('')
    try {
      const res = await fetch(`${API_URL}/api/auth/phone/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber, password: phonePassword })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.message || 'Login failed')
      localStorage.setItem('token', data.access_token)
      window.location.href = '/dashboard'
    } catch (e: unknown) {
      setOtpError(mapFetchError(e))
    } finally {
      setOtpLoading(false)
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
            <p>Accedi o crea account con numero di telefono + Telegram (OTP)</p>
          </div>

          {(error || otpError) && (
            <div className="error-message">
              <AlertCircle size={18} />
              {error || otpError}
            </div>
          )}

          <div>
            <div className="description" style={{ marginBottom: 10 }}>
              Telegram è obbligatorio per ricevere l’OTP. Premere START sul bot <strong>non</strong> attiva le notifiche segnali.
            </div>

            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <button
                type="button"
                className={`btn ${phoneMode === 'register' ? 'btn-primary' : ''}`}
                style={{ flex: 1, padding: '10px 12px' }}
                onClick={() => setPhoneMode('register')}
                disabled={otpLoading}
              >
                Crea account
              </button>
              <button
                type="button"
                className={`btn ${phoneMode === 'login' ? 'btn-primary' : ''}`}
                style={{ flex: 1, padding: '10px 12px' }}
                onClick={() => setPhoneMode('login')}
                disabled={otpLoading}
              >
                Accedi
              </button>
            </div>

            <form onSubmit={phoneMode === 'register' ? registerWithOtp : phoneLogin}>
              <div className="form-group">
                <label className="form-label">Numero di telefono</label>
                <input
                  type="tel"
                  className="form-input"
                  placeholder="+39..."
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  required
                />
              </div>

              <button
                type="button"
                className="btn"
                disabled={otpLoading || !phoneNumber}
                onClick={createTelegramLinkForPhone}
                style={{ marginBottom: 10 }}
              >
                Collega Telegram (obbligatorio)
              </button>

              {tgLink && (
                <div className="description" style={{ marginBottom: 10, wordBreak: 'break-all' }}>
                  Apri questo link e premi START sul bot:
                  <br />
                  <a href={tgLink} target="_blank" rel="noreferrer">
                    {tgLink}
                  </a>
                </div>
              )}

              {phoneMode === 'register' ? (
                <>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={otpLoading || !phoneNumber}
                    onClick={requestOtp}
                    style={{ marginBottom: 10 }}
                  >
                    {otpLoading ? <span className="spinner" /> : (otpSent ? 'Reinvia OTP su Telegram' : 'Invia OTP su Telegram')}
                  </button>

                  <div className="form-group">
                    <label className="form-label">Codice OTP</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="Codice a 6 cifre"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Password</label>
                    <input
                      type="password"
                      className="form-input"
                      placeholder="Crea una password"
                      value={phonePassword}
                      onChange={(e) => setPhonePassword(e.target.value)}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Conferma password</label>
                    <input
                      type="password"
                      className="form-input"
                      placeholder="Ripeti la password"
                      value={phonePassword2}
                      onChange={(e) => setPhonePassword2(e.target.value)}
                      required
                    />
                  </div>

                  <button type="submit" className="btn btn-primary" disabled={otpLoading || !otpCode || !phoneNumber || !phonePassword}>
                    {otpLoading ? <span className="spinner" /> : 'Crea account'}
                  </button>
                </>
              ) : (
                <>
                  <div className="form-group">
                    <label className="form-label">Password</label>
                    <input
                      type="password"
                      className="form-input"
                      placeholder="Password"
                      value={phonePassword}
                      onChange={(e) => setPhonePassword(e.target.value)}
                      required
                    />
                  </div>

                  <button type="submit" className="btn btn-primary" disabled={otpLoading || !phoneNumber || !phonePassword}>
                    {otpLoading ? <span className="spinner" /> : 'Accedi'}
                  </button>
                </>
              )}
            </form>
          </div>

          <div className="auth-links">
            <Link to="/phone-forgot-password" className="auth-link">
              Password dimenticata (telefono)
            </Link>
          </div>
        </div>

        <LegalFooter />
      </div>
    </div>
  )
}