import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Brain, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'https://crazy-brain-api.onrender.com'

export default function PhoneForgotPassword() {
  const [phoneNumber, setPhoneNumber] = useState('')
  const [otpCode, setOtpCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [otpSent, setOtpSent] = useState(false)
  const [tgLink, setTgLink] = useState('')

  const linkTelegram = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/auth/phone/telegram-link`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.message || 'Link failed')
      setTgLink(String(data.connect_url || ''))
    } catch (e: any) {
      setError(e?.message || 'Error')
    } finally {
      setLoading(false)
    }
  }

  const requestOtp = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/auth/phone/password-reset-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.message || 'OTP request failed')
      setOtpSent(true)
    } catch (e: any) {
      setError(e?.message || 'Error')
    } finally {
      setLoading(false)
    }
  }

  const confirm = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/auth/phone/password-reset-confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber, code: otpCode, password: newPassword })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || data?.message || 'Reset failed')
      setSuccess(true)
    } catch (e: any) {
      setError(e?.message || 'Error')
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
            <p>Reset password (via Telegram OTP)</p>
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
              Password aggiornata. Ora puoi fare login con numero + password.
            </div>
          ) : (
            <form onSubmit={confirm}>
              <div className="form-group">
                <label className="form-label">Phone number</label>
                <input
                  type="tel"
                  className="form-input"
                  placeholder="+39..."
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  required
                />
              </div>

              <div className="description" style={{ marginBottom: 10 }}>
                Telegram è obbligatorio per ricevere l’OTP. Premere START sul bot NON attiva le notifiche segnali.
              </div>

              <button type="button" className="btn" disabled={loading || !phoneNumber} onClick={linkTelegram} style={{ marginBottom: 10 }}>
                Collega Telegram
              </button>
              {tgLink && (
                <div className="description" style={{ marginBottom: 10, wordBreak: 'break-all' }}>
                  Apri e premi START:
                  <br />
                  <a href={tgLink} target="_blank" rel="noreferrer">
                    {tgLink}
                  </a>
                </div>
              )}

              <button type="button" className="btn btn-primary" disabled={loading || !phoneNumber} onClick={requestOtp} style={{ marginBottom: 10 }}>
                {otpSent ? 'Reinvia OTP' : 'Invia OTP su Telegram'}
              </button>

              <div className="form-group">
                <label className="form-label">OTP code</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="6-digit code"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">New password</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="New password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
              </div>

              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? <span className="spinner" /> : 'Conferma reset'}
              </button>
            </form>
          )}

          <div className="auth-links">
            <Link
              to="/login"
              className="auth-link"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
            >
              <ArrowLeft size={16} />
              Back to login
            </Link>
          </div>
        </div>

        <div className="auth-footer">
          <span className="brand">by crazy-brain</span>
        </div>
      </div>
    </div>
  )
}

