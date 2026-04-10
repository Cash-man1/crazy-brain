import { Routes, Route, Navigate } from 'react-router-dom'
import LiveDashboardNoAuth from './pages/LiveDashboardNoAuth'
import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import ChatLive from './pages/ChatLive'
import ConnectTelegram from './pages/ConnectTelegram'
import PhoneForgotPassword from './pages/PhoneForgotPassword'
import { useAuth } from './context/AuthContext'

function App() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="app">
        <div className="container" style={{ padding: 24, color: '#c8cde2' }}>
          Caricamento…
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <Routes>
        <Route path="/" element={user ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />} />
        <Route path="/dashboard" element={<LiveDashboardNoAuth />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/phone-forgot-password" element={<PhoneForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/chat" element={<ChatLive />} />
        <Route path="/connect" element={<ConnectTelegram />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default App
