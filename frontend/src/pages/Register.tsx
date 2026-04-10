import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Brain, AlertCircle } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import LegalFooter from '../components/LegalFooter'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [validationError, setValidationError] = useState('')
  const { register, loading, error } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError('')

    if (password !== confirmPassword) {
      setValidationError('Le password non coincidono')
      return
    }

    if (password.length < 6) {
      setValidationError('La password deve avere almeno 6 caratteri')
      return
    }

    try {
      await register(email, password)
      navigate('/dashboard')
    } catch {
      // Error handled by context
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
            <p>Registrazione con email e password</p>
          </div>

          {(error || validationError) && (
            <div className="error-message">
              <AlertCircle size={18} />
              {error || validationError}
            </div>
          )}

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

            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                type="password"
                className="form-input"
                placeholder="Scegli una password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Conferma password</label>
              <input
                type="password"
                className="form-input"
                placeholder="Ripeti la password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>

            <button 
              type="submit" 
              className="btn btn-primary"
              disabled={loading}
            >
              {loading ? <span className="spinner" /> : 'Crea account'}
            </button>
          </form>

          <div className="auth-links">
            <Link to="/login" className="auth-link gold">
              Hai già un account? Accedi
            </Link>
            <Link to="/login" className="auth-link">
              Registrazione con telefono (OTP) → vai al login e scegli «Telefono»
            </Link>
          </div>
        </div>

        <LegalFooter />
      </div>
    </div>
  )
}